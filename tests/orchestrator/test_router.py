import contextlib
import importlib
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.main import app

_router_mod = importlib.import_module("src.orchestrator.router")


def _fake_trip_session_state() -> MagicMock:
    """Explicit async-capable double for TripSessionStateStore — every awaited method is an AsyncMock."""
    store = MagicMock()
    store.clear_pending = AsyncMock()
    store.bind_place_selection = AsyncMock()
    store.bind_trip = AsyncMock()
    store.arm_pending = AsyncMock(return_value=True)
    store.consume_pending = AsyncMock(return_value=None)
    return store


def _make_mock_orchestrator(events: list | None = None) -> MagicMock:
    """Create a mock OrchestratorManager that streams the given events."""

    async def _astream(*args, **kwargs):
        for event in events or []:
            yield event

    mock = MagicMock()
    mock.astream = _astream
    mock.is_ready = True
    mock.has_checkpointer = False
    mock.acancel_pending_tools = AsyncMock()
    mock.provider = "openai"
    mock.model_name = "gpt-4o-mini"
    mock.trip_session_state = _fake_trip_session_state()

    idle_state = MagicMock()
    idle_state.next = ()
    idle_state.values = {}
    mock.graph.aget_state = AsyncMock(return_value=idle_state)
    mock.graph.aupdate_state = AsyncMock()
    return mock


def _parse_sse(content: bytes) -> list[dict]:
    """Parse raw SSE bytes into a list of JSON data objects."""
    result = []
    for line in content.decode().splitlines():
        if line.startswith("data: "):
            payload = line[len("data: ") :]
            if payload.strip() == "[DONE]":
                continue
            with contextlib.suppress(json.JSONDecodeError):
                result.append(json.loads(payload))
    return result


@pytest.mark.unit
class TestChatEndpointUnit:
    async def test_valid_request_streams_200(self, client):
        events = [
            {"event": "on_chat_model_stream", "data": {"chunk": type("C", (), {"content": "Hello"})()}},
        ]
        app.state.orchestrator = _make_mock_orchestrator(events)
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
        finally:
            app.state.orchestrator = None

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    async def test_sse_response_contains_streamed_chunks(self, client):
        events = [
            {"event": "on_chat_model_stream", "data": {"chunk": type("C", (), {"content": "Krakow"})()}},
            {"event": "on_chat_model_stream", "data": {"chunk": type("C", (), {"content": " is"})()}},
        ]
        app.state.orchestrator = _make_mock_orchestrator(events)
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={"messages": [{"role": "user", "content": "Tell me about Krakow"}]},
            )
        finally:
            app.state.orchestrator = None

        parsed = _parse_sse(response.content)
        contents = [p["content"] for p in parsed if "content" in p]
        assert "Krakow" in contents

    async def test_empty_messages_returns_422(self, client):
        response = await client.post(
            "/api/v1/core/orchestrator/chat",
            json={"messages": []},
        )
        assert response.status_code == 422

    async def test_missing_body_returns_422(self, client):
        response = await client.post("/api/v1/core/orchestrator/chat")
        assert response.status_code == 422

    async def test_no_orchestrator_returns_503(self, client):
        response = await client.post(
            "/api/v1/core/orchestrator/chat",
            json={"messages": [{"role": "user", "content": "Hi"}]},
        )
        assert response.status_code == 503

    async def test_session_id_forwarded_to_astream(self, client):
        received_thread_ids = []

        async def _capturing_astream(state, thread_id=None, **kwargs):
            received_thread_ids.append(thread_id)
            yield {"event": "on_chain_end", "data": {}}

        mock_orch = _make_mock_orchestrator()
        mock_orch.astream = _capturing_astream
        app.state.orchestrator = mock_orch
        try:
            await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "session_id": "my-session-123",
                },
            )
        finally:
            app.state.orchestrator = None

        assert received_thread_ids == ["my-session-123"]


@pytest.mark.unit
class TestChatEndpointPendingToolCleanup:
    async def test_existing_session_with_checkpointer_cancels_pending_tools(self, client):
        mock_orch = _make_mock_orchestrator([{"event": "on_chain_end", "data": {}}])
        mock_orch.has_checkpointer = True
        app.state.orchestrator = mock_orch
        try:
            await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "session_id": "existing-session",
                },
            )
        finally:
            app.state.orchestrator = None

        mock_orch.acancel_pending_tools.assert_awaited_once_with("existing-session")

    async def test_new_session_skips_pending_tool_cleanup(self, client):
        mock_orch = _make_mock_orchestrator([{"event": "on_chain_end", "data": {}}])
        mock_orch.has_checkpointer = True
        app.state.orchestrator = mock_orch
        try:
            await client.post(
                "/api/v1/core/orchestrator/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
        finally:
            app.state.orchestrator = None

        mock_orch.acancel_pending_tools.assert_not_awaited()

    async def test_no_checkpointer_skips_pending_tool_cleanup(self, client):
        mock_orch = _make_mock_orchestrator([{"event": "on_chain_end", "data": {}}])
        app.state.orchestrator = mock_orch
        try:
            await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "session_id": "existing-session",
                },
            )
        finally:
            app.state.orchestrator = None

        mock_orch.acancel_pending_tools.assert_not_awaited()

    async def test_resume_flow_skips_pending_tool_cleanup(self, client):
        async def _astream_resume(thread_id, confirmed, user_message=None):
            yield {"event": "on_chain_end", "data": {}}

        mock_orch = _make_mock_orchestrator()
        mock_orch.has_checkpointer = True
        mock_orch.astream_resume = _astream_resume
        app.state.orchestrator = mock_orch
        try:
            await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "session_id": "existing-session",
                    "resume_confirmed": True,
                },
            )
        finally:
            app.state.orchestrator = None

        mock_orch.acancel_pending_tools.assert_not_awaited()


@pytest.mark.unit
class TestChatEndpointPlaceContext:
    async def test_place_ids_trigger_db_fetch(self, client, monkeypatch):
        fetched_calls = []

        async def mock_fetch(db, place_ids):
            fetched_calls.append(place_ids)
            return []

        monkeypatch.setattr(_router_mod, "fetch_places_by_ids", mock_fetch)
        app.state.orchestrator = _make_mock_orchestrator()
        try:
            await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "place_ids": ["abc123", "def456"],
                },
            )
        finally:
            app.state.orchestrator = None

        assert fetched_calls == [["abc123", "def456"]]

    async def test_empty_place_ids_skips_db_fetch(self, client, monkeypatch):
        fetched_calls = []

        async def mock_fetch(db, place_ids):
            fetched_calls.append(place_ids)
            return []

        monkeypatch.setattr(_router_mod, "fetch_places_by_ids", mock_fetch)
        app.state.orchestrator = _make_mock_orchestrator()
        try:
            await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "place_ids": [],
                },
            )
        finally:
            app.state.orchestrator = None

        assert fetched_calls == []

    async def test_session_id_emitted_as_first_sse_event(self, client):
        app.state.orchestrator = _make_mock_orchestrator()
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
        finally:
            app.state.orchestrator = None

        parsed = _parse_sse(response.content)
        assert len(parsed) > 0
        assert "session_id" in parsed[0]

    async def test_client_session_id_echoed_in_first_sse_event(self, client):
        app.state.orchestrator = _make_mock_orchestrator()
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "session_id": "my-sess-42",
                },
            )
        finally:
            app.state.orchestrator = None

        parsed = _parse_sse(response.content)
        assert parsed[0].get("session_id") == "my-sess-42"

    async def test_place_context_populated_in_agent_state(self, client, monkeypatch):
        received_states = []

        async def mock_fetch(db, place_ids):
            return [{"_id": "abc", "name": "Wawel"}]

        monkeypatch.setattr(_router_mod, "fetch_places_by_ids", mock_fetch)

        async def _capturing_astream(state, thread_id=None, **kwargs):
            received_states.append(state)
            yield {"event": "on_chain_end", "data": {}}

        mock_orch = _make_mock_orchestrator()
        mock_orch.astream = _capturing_astream
        app.state.orchestrator = mock_orch
        try:
            await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "place_ids": ["abc"],
                },
            )
        finally:
            app.state.orchestrator = None

        assert len(received_states) == 1
        assert received_states[0]["place_context"] == [{"_id": "abc", "name": "Wawel"}]


@pytest.mark.unit
class TestChatEndpointResume:
    async def test_resume_confirmed_true_returns_200(self, client):
        async def _astream_resume(thread_id, confirmed, user_message=None):
            yield {"event": "on_chain_end", "data": {}}

        mock_orch = _make_mock_orchestrator()
        mock_orch.astream_resume = _astream_resume
        app.state.orchestrator = mock_orch
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Yes, go ahead"}],
                    "session_id": "sess-resume-1",
                    "resume_confirmed": True,
                },
            )
        finally:
            app.state.orchestrator = None

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    async def test_resume_confirmed_false_returns_200(self, client):
        async def _astream_resume(thread_id, confirmed, user_message=None):
            yield {"event": "on_chain_end", "data": {}}

        mock_orch = _make_mock_orchestrator()
        mock_orch.astream_resume = _astream_resume
        app.state.orchestrator = mock_orch
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "No, cancel"}],
                    "session_id": "sess-resume-2",
                    "resume_confirmed": False,
                },
            )
        finally:
            app.state.orchestrator = None

        assert response.status_code == 200

    async def test_resume_session_id_emitted_as_first_event(self, client):
        async def _astream_resume(thread_id, confirmed, user_message=None):
            yield {"event": "on_chain_end", "data": {}}

        mock_orch = _make_mock_orchestrator()
        mock_orch.astream_resume = _astream_resume
        app.state.orchestrator = mock_orch
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Yes"}],
                    "session_id": "sess-42",
                    "resume_confirmed": True,
                },
            )
        finally:
            app.state.orchestrator = None

        parsed = _parse_sse(response.content)
        assert parsed[0].get("session_id") == "sess-42"

    async def test_resume_forwards_content_chunks(self, client):
        async def _astream_resume(thread_id, confirmed, user_message=None):
            yield {"event": "on_chat_model_stream", "data": {"chunk": type("C", (), {"content": "Updated!"})()}}

        mock_orch = _make_mock_orchestrator()
        mock_orch.astream_resume = _astream_resume
        app.state.orchestrator = mock_orch
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Yes"}],
                    "session_id": "sess-chunks",
                    "resume_confirmed": True,
                },
            )
        finally:
            app.state.orchestrator = None

        parsed = _parse_sse(response.content)
        contents = [p["content"] for p in parsed if "content" in p]
        assert "Updated!" in contents

    async def test_resume_does_not_pass_user_message(self, client):
        """Client history is already checkpointed — re-sending its last message
        would insert a duplicate between the interrupted AIMessage(tool_calls)
        and the ToolMessage, breaking the provider history and rerouting the
        resumed graph to END before the tool executes."""
        captured = []

        async def _astream_resume(thread_id, confirmed, user_message=None):
            captured.append(user_message)
            yield {"event": "on_chain_end", "data": {}}

        mock_orch = _make_mock_orchestrator()
        mock_orch.astream_resume = _astream_resume
        app.state.orchestrator = mock_orch
        try:
            await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Yes please"}],
                    "session_id": "sess-msg",
                    "resume_confirmed": True,
                },
            )
        finally:
            app.state.orchestrator = None

        assert captured == [None]

    async def test_resume_skips_astream_and_calls_astream_resume(self, client):
        astream_called = []
        astream_resume_called = []

        async def _astream(state, thread_id=None, **kwargs):
            astream_called.append(True)
            yield {"event": "on_chain_end", "data": {}}

        async def _astream_resume(thread_id, confirmed, user_message=None):
            astream_resume_called.append(True)
            yield {"event": "on_chain_end", "data": {}}

        mock_orch = _make_mock_orchestrator()
        mock_orch.astream = _astream
        mock_orch.astream_resume = _astream_resume
        app.state.orchestrator = mock_orch
        try:
            await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Yes"}],
                    "session_id": "sess-dispatch",
                    "resume_confirmed": True,
                },
            )
        finally:
            app.state.orchestrator = None

        assert astream_called == []
        assert astream_resume_called == [True]

    async def test_resume_stream_error_yields_error_event(self, client):
        async def _astream_resume(thread_id, confirmed, user_message=None):
            raise RuntimeError("graph exploded")
            yield  # make it a generator

        mock_orch = _make_mock_orchestrator()
        mock_orch.astream_resume = _astream_resume
        app.state.orchestrator = mock_orch
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "Yes"}],
                    "session_id": "sess-err",
                    "resume_confirmed": True,
                },
            )
        finally:
            app.state.orchestrator = None

        parsed = _parse_sse(response.content)
        assert any("error" in p for p in parsed)


@pytest.mark.unit
class TestChatEndpointToolProposal:
    async def test_tool_proposal_emitted_on_pending_interrupt(self, client):
        from langchain_core.messages import AIMessage

        tool_calls = [
            {"name": "update_visit_hours", "args": {"place_id": "abc123", "preferred_hour_from": 9}, "id": "call_1"}
        ]
        interrupted_msg = AIMessage(id="msg-1", content="Let me update that.", tool_calls=tool_calls)

        graph_state = MagicMock()
        graph_state.next = ("tools_write",)
        graph_state.values = {"messages": [interrupted_msg]}

        mock_orch = _make_mock_orchestrator()
        mock_orch.has_checkpointer = True
        mock_orch.graph.aget_state = AsyncMock(return_value=graph_state)

        app.state.orchestrator = mock_orch
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={"messages": [{"role": "user", "content": "Update visit hours for Wawel"}]},
            )
        finally:
            app.state.orchestrator = None

        parsed = _parse_sse(response.content)
        proposals = [p["tool_proposal"] for p in parsed if "tool_proposal" in p]
        assert len(proposals) == 1
        assert proposals[0]["tool"] == "update_visit_hours"
        assert proposals[0]["args"]["place_id"] == "abc123"

    async def test_multiple_write_calls_fail_closed(self, client):
        """Two write tool calls in one interrupted turn: no proposal, no armed scope, an error event."""
        from langchain_core.messages import AIMessage

        tool_calls = [
            {"name": "update_visit_hours", "args": {"place_id": "abc"}, "id": "call_1"},
            {"name": "skip_place", "args": {"place_id": "def"}, "id": "call_2"},
        ]
        interrupted_msg = AIMessage(id="msg-2", content="Updating...", tool_calls=tool_calls)

        graph_state = MagicMock()
        graph_state.next = ("tools_write",)
        graph_state.values = {"messages": [interrupted_msg]}

        mock_orch = _make_mock_orchestrator()
        mock_orch.has_checkpointer = True
        mock_orch.graph.aget_state = AsyncMock(return_value=graph_state)

        app.state.orchestrator = mock_orch
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={"messages": [{"role": "user", "content": "Update both"}]},
            )
        finally:
            app.state.orchestrator = None

        parsed = _parse_sse(response.content)
        assert not any("tool_proposal" in p for p in parsed)
        assert any("error" in p for p in parsed)
        mock_orch.acancel_pending_tools.assert_awaited()
        mock_orch.trip_session_state.arm_pending.assert_not_awaited()
        mock_orch.trip_session_state.clear_pending.assert_awaited()

    async def test_no_tool_proposal_when_graph_next_is_empty(self, client):
        graph_state = MagicMock()
        graph_state.next = ()
        graph_state.values = {}

        mock_orch = _make_mock_orchestrator()
        mock_orch.has_checkpointer = True
        mock_orch.graph.aget_state = AsyncMock(return_value=graph_state)

        app.state.orchestrator = mock_orch
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
        finally:
            app.state.orchestrator = None

        parsed = _parse_sse(response.content)
        assert not any("tool_proposal" in p for p in parsed)

    async def test_no_tool_proposal_when_no_checkpointer(self, client):
        mock_orch = _make_mock_orchestrator()
        mock_orch.has_checkpointer = False

        app.state.orchestrator = mock_orch
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
        finally:
            app.state.orchestrator = None

        parsed = _parse_sse(response.content)
        assert not any("tool_proposal" in p for p in parsed)

    async def test_aget_state_error_fails_closed(self, client):
        """Unreadable graph state: stream still ends cleanly, but with a fail-closed error and no write."""
        mock_orch = _make_mock_orchestrator()
        mock_orch.has_checkpointer = True
        mock_orch.graph.aget_state = AsyncMock(side_effect=RuntimeError("DB unavailable"))

        app.state.orchestrator = mock_orch
        try:
            response = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
        finally:
            app.state.orchestrator = None

        assert response.status_code == 200
        parsed = _parse_sse(response.content)
        assert not any("tool_proposal" in p for p in parsed)
        assert any("error" in p for p in parsed)
        mock_orch.trip_session_state.arm_pending.assert_not_awaited()
        mock_orch.acancel_pending_tools.assert_awaited()


@pytest.mark.unit
class TestStatusEndpoint:
    async def test_status_ready_when_orchestrator_connected(self, client):
        app.state.orchestrator = _make_mock_orchestrator()
        try:
            response = await client.get("/api/v1/core/orchestrator/status")
        finally:
            app.state.orchestrator = None

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o-mini"

    async def test_status_not_ready_when_no_orchestrator(self, client):
        response = await client.get("/api/v1/core/orchestrator/status")
        assert response.status_code == 200
        assert response.json() == {"ready": False}


@pytest.mark.unit
class TestClassifyLlmError:
    def test_openai_rate_limit(self):
        class RateLimitError(Exception):
            pass

        RateLimitError.__module__ = "openai"
        exc = RateLimitError("quota exceeded")
        assert _router_mod._classify_llm_error(exc) == "OpenAI quota exceeded — check your billing."

    def test_anthropic_rate_limit(self):
        class RateLimitError(Exception):
            pass

        RateLimitError.__module__ = "anthropic"
        exc = RateLimitError("rate limited")
        assert _router_mod._classify_llm_error(exc) == "Anthropic rate limit exceeded — try again shortly."

    def test_unknown_rate_limit(self):
        class RateLimitError(Exception):
            pass

        RateLimitError.__module__ = "some_other_llm"
        exc = RateLimitError("rate limited")
        assert _router_mod._classify_llm_error(exc) == "LLM rate limit exceeded — try again shortly."

    def test_authentication_error(self):
        class AuthenticationError(Exception):
            pass

        exc = AuthenticationError("bad key")
        assert _router_mod._classify_llm_error(exc) == "Invalid API key — check your LLM provider configuration."

    def test_generic_exception(self):
        exc = RuntimeError("graph exploded")
        assert _router_mod._classify_llm_error(exc) == "Stream interrupted"
