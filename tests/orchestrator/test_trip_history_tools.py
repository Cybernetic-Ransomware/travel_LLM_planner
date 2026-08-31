from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.types import Command

from src.core.exceptions import (
    RevisionAlreadyCurrentError,
    RevisionNotFoundError,
    TripConcurrencyConflictError,
)
from src.orchestrator.trip_history_tools import (
    build_list_trip_revisions_tool,
    build_revert_trip_revision_tool,
)
from src.orchestrator.trip_session_state import Binding, PendingScope
from src.trips.models import SingleDayTripDetailOut, TripRevisionListOut, TripRevisionSummaryOut

pytestmark = pytest.mark.unit

_CONFIG = {"configurable": {"thread_id": "t1"}}


def _text(result) -> str:
    return getattr(result, "content", result)


def _trip_binding() -> Binding:
    return Binding(
        thread_id="t1",
        kind="trip",
        trip_id="abc123",
        plan_type="SINGLE_DAY",
        name="Kraków",
        revision=2,
        allowed_place_ids=["p1"],
    )


def _place_binding() -> Binding:
    return Binding(
        thread_id="t1",
        kind="place_selection",
        trip_id=None,
        plan_type=None,
        name=None,
        revision=None,
        allowed_place_ids=["p1"],
    )


def _trip_scope(revision: int = 2, tool_call_id: str = "") -> PendingScope:
    return PendingScope(
        tool_call_id=tool_call_id,
        kind="trip",
        trip_id="abc123",
        plan_type="SINGLE_DAY",
        name="Kraków",
        revision=revision,
        allowed_place_ids=["p1"],
    )


def _history() -> TripRevisionListOut:
    return TripRevisionListOut(
        trip_id="abc123",
        current_revision=2,
        revisions=[
            TripRevisionSummaryOut(
                revision=2,
                source="REVERT",
                summary="Restored revision 0",
                restored_from_revision=0,
                schema_version=1,
                snapshot_hash="h2",
                recorded_at="2026-08-01T12:00:00+00:00",
            ),
            TripRevisionSummaryOut(
                revision=1,
                source="MANUAL",
                summary="Manual update — SINGLE_DAY, 3 places",
                restored_from_revision=None,
                schema_version=1,
                snapshot_hash="h1",
                recorded_at="2026-08-01T11:00:00+00:00",
            ),
            TripRevisionSummaryOut(
                revision=0,
                source="CREATED",
                summary="Trip created",
                restored_from_revision=None,
                schema_version=1,
                snapshot_hash="h0",
                recorded_at="2026-08-01T10:00:00+00:00",
            ),
        ],
    )


def _detail(revision: int) -> SingleDayTripDetailOut:
    return SingleDayTripDetailOut(
        id="abc123",
        name="Kraków",
        created_at="2026-08-01T10:00:00+00:00",
        updated_at="2026-08-01T12:00:00+00:00",
        revision=revision,
        date="2026-07-04",
        optimizer_request={
            "place_ids": ["p1", "p2"],
            "transport_mode": "WALK",
            "day_start_hour": 9,
            "day_end_hour": 21,
        },
        optimizer_response={
            "steps": [],
            "total_travel_time_s": 0,
            "total_visit_time_min": 0,
            "total_wait_min": 0,
            "transport_mode": "WALK",
            "skipped": [],
        },
        selected_place_ids=["p1", "p2"],
        transport_mode="WALK",
        day_start_hour=9,
        day_end_hour=21,
    )


class TestListTripRevisions:
    async def test_lists_history_for_bound_trip(self):
        store = MagicMock()
        store.get_binding = AsyncMock(return_value=_trip_binding())
        store.consume_pending = AsyncMock()
        repo = MagicMock()
        repo.list_revisions = AsyncMock(return_value=_history())
        tool = build_list_trip_revisions_tool(repo, store)

        result = await tool.ainvoke({}, config=_CONFIG)

        assert "revision 2 (current) — REVERT" in result
        assert "restored from revision 0" in result
        assert "revision 0" in result and "CREATED" in result
        store.consume_pending.assert_not_awaited()  # read-only: never spends the scope

    async def test_declines_without_trip_binding(self):
        store = MagicMock()
        store.get_binding = AsyncMock(return_value=_place_binding())
        tool = build_list_trip_revisions_tool(MagicMock(), store)
        result = await tool.ainvoke({}, config=_CONFIG)
        assert "isn't editing a saved trip" in result

    async def test_declines_when_no_binding(self):
        store = MagicMock()
        store.get_binding = AsyncMock(return_value=None)
        tool = build_list_trip_revisions_tool(MagicMock(), store)
        assert "isn't editing a saved trip" in await tool.ainvoke({}, config=_CONFIG)


class TestRevertTripRevision:
    async def test_happy_path_returns_command_and_last_trip_update(self):
        store = MagicMock()
        store.consume_pending = AsyncMock(return_value=_trip_scope(revision=2))
        repo = MagicMock()
        repo.restore_revision = AsyncMock(return_value=_detail(revision=3))
        tool = build_revert_trip_revision_tool(repo, store)

        result = await tool.ainvoke(
            {"name": "revert_trip_revision", "args": {"target_revision": 0}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )

        assert isinstance(result, Command)
        repo.restore_revision.assert_awaited_once_with("abc123", 0, expected_revision=2)
        assert result.update["last_trip_update"] == {
            "trip_id": "abc123",
            "revision": 3,
            "plan_type": "SINGLE_DAY",
            "name": "Kraków",
        }

    async def test_missing_scope_fails_closed(self):
        store = MagicMock()
        store.consume_pending = AsyncMock(return_value=None)
        repo = MagicMock()
        repo.restore_revision = AsyncMock()
        tool = build_revert_trip_revision_tool(repo, store)

        result = await tool.ainvoke(
            {"name": "revert_trip_revision", "args": {"target_revision": 0}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )
        assert "expired" in _text(result)
        repo.restore_revision.assert_not_awaited()

    async def test_place_selection_scope_is_rejected(self):
        store = MagicMock()
        scope = PendingScope(
            tool_call_id="",
            kind="place_selection",
            trip_id=None,
            plan_type=None,
            name=None,
            revision=None,
            allowed_place_ids=["p1"],
        )
        store.consume_pending = AsyncMock(return_value=scope)
        repo = MagicMock()
        repo.restore_revision = AsyncMock()
        tool = build_revert_trip_revision_tool(repo, store)

        result = await tool.ainvoke(
            {"name": "revert_trip_revision", "args": {"target_revision": 0}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )
        assert "expired" in _text(result)
        repo.restore_revision.assert_not_awaited()

    async def test_tool_call_id_mismatch_fails_closed(self):
        store = MagicMock()
        store.consume_pending = AsyncMock(return_value=_trip_scope(tool_call_id="other-call"))
        repo = MagicMock()
        repo.restore_revision = AsyncMock()
        tool = build_revert_trip_revision_tool(repo, store)

        result = await tool.ainvoke(
            {"name": "revert_trip_revision", "args": {"target_revision": 0}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )
        assert "expired" in _text(result)
        repo.restore_revision.assert_not_awaited()

    async def test_concurrency_conflict_becomes_chat_text(self):
        store = MagicMock()
        store.consume_pending = AsyncMock(return_value=_trip_scope())
        repo = MagicMock()
        repo.restore_revision = AsyncMock(side_effect=TripConcurrencyConflictError("abc123", expected=2))
        tool = build_revert_trip_revision_tool(repo, store)

        result = await tool.ainvoke(
            {"name": "revert_trip_revision", "args": {"target_revision": 0}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )
        assert "changed since we started" in _text(result)

    async def test_unknown_revision_becomes_chat_text(self):
        store = MagicMock()
        store.consume_pending = AsyncMock(return_value=_trip_scope())
        repo = MagicMock()
        repo.restore_revision = AsyncMock(side_effect=RevisionNotFoundError("abc123", 9))
        tool = build_revert_trip_revision_tool(repo, store)

        result = await tool.ainvoke(
            {"name": "revert_trip_revision", "args": {"target_revision": 9}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )
        assert "no revision 9" in _text(result)

    async def test_already_current_becomes_chat_text(self):
        store = MagicMock()
        store.consume_pending = AsyncMock(return_value=_trip_scope())
        repo = MagicMock()
        repo.restore_revision = AsyncMock(side_effect=RevisionAlreadyCurrentError("abc123", 2))
        tool = build_revert_trip_revision_tool(repo, store)

        result = await tool.ainvoke(
            {"name": "revert_trip_revision", "args": {"target_revision": 2}, "id": "call-1", "type": "tool_call"},
            config=_CONFIG,
        )
        assert "already the current state" in _text(result)

    async def test_no_thread_id_fails_closed(self):
        store = MagicMock()
        store.consume_pending = AsyncMock()
        repo = MagicMock()
        repo.restore_revision = AsyncMock()
        tool = build_revert_trip_revision_tool(repo, store)

        result = await tool.ainvoke(
            {"name": "revert_trip_revision", "args": {"target_revision": 0}, "id": "call-1", "type": "tool_call"},
            config={"configurable": {}},
        )
        assert "expired" in _text(result)
        store.consume_pending.assert_not_awaited()
        repo.restore_revision.assert_not_awaited()
