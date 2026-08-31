from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.types import Command
from pydantic import ValidationError

from src.orchestrator.trip_edit_tool import build_edit_multi_day_trip_tool
from src.orchestrator.trip_session_state import PendingScope
from src.trips.editing.errors import TripConcurrencyConflictError
from src.trips.editing.service import AppliedEdit

pytestmark = pytest.mark.unit

_CONFIG = {"configurable": {"thread_id": "thread-1"}}


def _text(result) -> str:
    return result.content if hasattr(result, "content") else result


def _trip_scope(**over) -> PendingScope:
    base = dict(
        tool_call_id="call-1",
        kind="trip",
        trip_id="507f1f77bcf86cd799439011",
        plan_type="MULTI_DAY",
        name="Tokyo May",
        revision=2,
        allowed_place_ids=["p1", "p2"],
    )
    base.update(over)
    return PendingScope(**base)


def _tool(store, editor_apply):
    store_mock = MagicMock()
    store_mock.consume_pending = AsyncMock(return_value=store)
    tool = build_edit_multi_day_trip_tool(MagicMock(), MagicMock(), store_mock)
    return tool, store_mock, editor_apply


def _ops():
    return [{"op": "set_place_pinned", "place_id": "p1", "day_index": 2}]


async def test_schema_hides_injected_params_from_the_model():
    tool = build_edit_multi_day_trip_tool(MagicMock(), MagicMock(), MagicMock())
    props = tool.tool_call_schema.model_json_schema()["properties"]
    assert "operations" in props
    assert "config" not in props
    assert "tool_call_id" not in props


async def test_missing_scope_fails_closed_without_touching_editor():
    store = MagicMock()
    store.consume_pending = AsyncMock(return_value=None)
    tool = build_edit_multi_day_trip_tool(MagicMock(), MagicMock(), store)

    with patch("src.orchestrator.trip_edit_tool.MultiDayTripEditor") as editor_cls:
        result = await tool.ainvoke(
            {"name": "edit_multi_day_trip", "args": {"operations": _ops()}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )

    assert "expired" in _text(result)
    editor_cls.assert_not_called()


async def test_place_selection_scope_is_rejected():
    store = MagicMock()
    store.consume_pending = AsyncMock(return_value=_trip_scope(kind="place_selection", trip_id=None))
    tool = build_edit_multi_day_trip_tool(MagicMock(), MagicMock(), store)

    with patch("src.orchestrator.trip_edit_tool.MultiDayTripEditor") as editor_cls:
        result = await tool.ainvoke(
            {"name": "edit_multi_day_trip", "args": {"operations": _ops()}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )

    assert "expired" in _text(result)
    editor_cls.assert_not_called()


async def test_tool_call_id_mismatch_fails_closed():
    store = MagicMock()
    store.consume_pending = AsyncMock(return_value=_trip_scope(tool_call_id="different"))
    tool = build_edit_multi_day_trip_tool(MagicMock(), MagicMock(), store)

    result = await tool.ainvoke(
        {"name": "edit_multi_day_trip", "args": {"operations": _ops()}, "id": "call-1", "type": "tool_call"},
        config=_CONFIG,
    )
    assert "expired" in _text(result)


async def test_happy_path_uses_scope_trip_id_and_revision_and_returns_command():
    store = MagicMock()
    store.consume_pending = AsyncMock(return_value=_trip_scope())
    tool = build_edit_multi_day_trip_tool(MagicMock(), MagicMock(), store)

    updated = MagicMock(id="507f1f77bcf86cd799439011", revision=3)
    updated.name = "Tokyo May"  # name= is reserved by MagicMock, set it explicitly
    editor = MagicMock()
    editor.apply = AsyncMock(return_value=AppliedEdit(trip=updated, removed_transfer_dates=[]))

    with patch("src.orchestrator.trip_edit_tool.MultiDayTripEditor", return_value=editor):
        result = await tool.ainvoke(
            {"name": "edit_multi_day_trip", "args": {"operations": _ops()}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )

    editor.apply.assert_awaited_once()
    args = editor.apply.call_args[0]
    assert args[0] == "507f1f77bcf86cd799439011"  # scope.trip_id, never an LLM arg
    assert args[2] == 2  # scope.revision
    assert isinstance(result, Command)
    assert result.update["last_trip_update"] == {
        "trip_id": "507f1f77bcf86cd799439011",
        "revision": 3,
        "plan_type": "MULTI_DAY",
        "name": "Tokyo May",
    }


async def test_summary_reports_auto_removed_transfer():
    store = MagicMock()
    store.consume_pending = AsyncMock(return_value=_trip_scope())
    tool = build_edit_multi_day_trip_tool(MagicMock(), MagicMock(), store)

    updated = MagicMock(id="507f1f77bcf86cd799439011", revision=3)
    updated.name = "Tokyo May"
    editor = MagicMock()
    editor.apply = AsyncMock(return_value=AppliedEdit(trip=updated, removed_transfer_dates=[date(2026, 5, 13)]))

    with patch("src.orchestrator.trip_edit_tool.MultiDayTripEditor", return_value=editor):
        result = await tool.ainvoke(
            {"name": "edit_multi_day_trip", "args": {"operations": _ops()}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )

    message = result.update["messages"][0].content
    assert "2026-05-13" in message
    assert "no longer an accommodation changeover" in message


async def test_editor_error_becomes_user_message():
    store = MagicMock()
    store.consume_pending = AsyncMock(return_value=_trip_scope())
    tool = build_edit_multi_day_trip_tool(MagicMock(), MagicMock(), store)

    editor = MagicMock()
    editor.apply = AsyncMock(side_effect=TripConcurrencyConflictError())

    with patch("src.orchestrator.trip_edit_tool.MultiDayTripEditor", return_value=editor):
        result = await tool.ainvoke(
            {"name": "edit_multi_day_trip", "args": {"operations": _ops()}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )

    assert _text(result) == TripConcurrencyConflictError.user_message


async def test_forged_trip_id_in_operations_is_rejected():
    store = MagicMock()
    store.consume_pending = AsyncMock(return_value=_trip_scope())
    tool = build_edit_multi_day_trip_tool(MagicMock(), MagicMock(), store)

    # extra="forbid" on every operation model: langchain rejects the smuggled key at
    # the tool boundary before the body runs. ToolNode turns this into an error message.
    with patch("src.orchestrator.trip_edit_tool.MultiDayTripEditor") as editor_cls, pytest.raises(ValidationError):
        await tool.ainvoke(
            {
                "name": "edit_multi_day_trip",
                "args": {"operations": [{"op": "set_place_pinned", "place_id": "p1", "day_index": 2, "trip_id": "other"}]},
                "id": "call-1",
                "type": "tool_call",
            },
            config=_CONFIG,
        )
    editor_cls.assert_not_called()


async def test_empty_operations_batch_rejected_in_body():
    store = MagicMock()
    store.consume_pending = AsyncMock(return_value=_trip_scope())
    tool = build_edit_multi_day_trip_tool(MagicMock(), MagicMock(), store)

    with patch("src.orchestrator.trip_edit_tool.MultiDayTripEditor") as editor_cls:
        result = await tool.ainvoke(
            {"name": "edit_multi_day_trip", "args": {"operations": []}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )

    assert "isn't valid" in _text(result)
    editor_cls.assert_not_called()
