"""Unit tests for router.inspect_pending_write_interrupt — the guarantee that every
graph state paused before tools_write resolves to a proposal or a fail-closed error.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.tool import ToolCall

from src.orchestrator.router import inspect_pending_write_interrupt

pytestmark = pytest.mark.unit


def _orch(*, next_nodes=("tools_write",), messages=None, has_checkpointer=True):
    graph_state = SimpleNamespace(next=next_nodes, values={"messages": messages or []})
    orch = MagicMock()
    orch.has_checkpointer = has_checkpointer
    orch.graph.aget_state = AsyncMock(return_value=graph_state)
    orch.acancel_pending_tools = AsyncMock()
    return orch


def _store(armed=True):
    store = MagicMock()
    store.arm_pending = AsyncMock(return_value=armed)
    store.clear_pending = AsyncMock()
    return store


def _parse(line: str) -> dict:
    assert line.startswith("data: ")
    return json.loads(line[len("data: ") :])


async def test_returns_none_without_checkpointer():
    assert await inspect_pending_write_interrupt(_orch(has_checkpointer=False), "t", _store()) is None


async def test_returns_none_when_graph_not_paused():
    orch = _orch(next_nodes=())
    assert await inspect_pending_write_interrupt(orch, "t", _store()) is None


async def test_single_write_call_arms_and_proposes():
    call = ToolCall(name="edit_multi_day_trip", args={"operations": []}, id="c1")
    orch = _orch(messages=[AIMessage(content="", tool_calls=[call])])
    store = _store(armed=True)

    line = await inspect_pending_write_interrupt(orch, "t", store)

    payload = _parse(line)
    assert payload["tool_proposal"]["tool"] == "edit_multi_day_trip"
    store.arm_pending.assert_awaited_once_with("t", "c1")


async def test_two_write_calls_fail_closed_no_arm():
    calls = [
        ToolCall(name="edit_multi_day_trip", args={"operations": []}, id="c1"),
        ToolCall(name="update_visit_hours", args={"place_id": "p"}, id="c2"),
    ]
    orch = _orch(messages=[AIMessage(content="", tool_calls=calls)])
    store = _store()

    line = await inspect_pending_write_interrupt(orch, "t", store)

    assert "several separate changes" in _parse(line)["error"]
    store.arm_pending.assert_not_called()
    orch.acancel_pending_tools.assert_awaited_once_with("t")
    store.clear_pending.assert_awaited_once_with("t")


async def test_mixed_read_and_write_arms_the_single_write():
    calls = [
        ToolCall(name="get_trip_details", args={"trip_id": "t1"}, id="r1"),
        ToolCall(name="edit_multi_day_trip", args={"operations": []}, id="w1"),
    ]
    orch = _orch(messages=[AIMessage(content="", tool_calls=calls)])
    store = _store(armed=True)

    line = await inspect_pending_write_interrupt(orch, "t", store)

    assert _parse(line)["tool_proposal"]["tool"] == "edit_multi_day_trip"
    store.arm_pending.assert_awaited_once_with("t", "w1")


async def test_arm_failure_fails_closed_no_proposal():
    call = ToolCall(name="edit_multi_day_trip", args={"operations": []}, id="c1")
    orch = _orch(messages=[AIMessage(content="", tool_calls=call and [call])])
    store = _store(armed=False)

    line = await inspect_pending_write_interrupt(orch, "t", store)

    assert "error" in _parse(line)
    orch.acancel_pending_tools.assert_awaited_once_with("t")
    store.clear_pending.assert_awaited_once_with("t")


async def test_only_read_calls_returns_none():
    call = ToolCall(name="get_trip_details", args={"trip_id": "t1"}, id="r1")
    orch = _orch(messages=[AIMessage(content="", tool_calls=[call])])
    assert await inspect_pending_write_interrupt(orch, "t", _store()) is None


async def test_last_message_not_ai_returns_none():
    orch = _orch(messages=[HumanMessage(content="hi")])
    assert await inspect_pending_write_interrupt(orch, "t", _store()) is None


async def test_aget_state_error_is_swallowed():
    orch = _orch()
    orch.graph.aget_state = AsyncMock(side_effect=RuntimeError("boom"))
    assert await inspect_pending_write_interrupt(orch, "t", _store()) is None
