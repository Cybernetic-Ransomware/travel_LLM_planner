import importlib
import json
from unittest.mock import MagicMock

import pytest

from src.main import app

_router_mod = importlib.import_module("src.orchestrator.router")


def _make_mock_orchestrator(events: list | None = None) -> MagicMock:
    """Create a mock OrchestratorManager that streams the given events."""

    async def _astream(*args, **kwargs):
        for event in (events or []):
            yield event

    mock = MagicMock()
    mock.astream = _astream
    mock.is_ready = True
    mock.has_checkpointer = False
    mock.provider = "openai"
    mock.model_name = "gpt-4o-mini"
    return mock


def _parse_sse(content: bytes) -> list[dict]:
    """Parse raw SSE bytes into a list of JSON data objects."""
    result = []
    for line in content.decode().splitlines():
        if line.startswith("data: "):
            payload = line[len("data: "):]
            if payload.strip() == "[DONE]":
                continue
            try:
                result.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
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

    async def test_resume_passes_last_message_as_user_message(self, client):
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

        assert captured == ["Yes please"]

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
        data = response.json()
        assert data["ready"] is False
