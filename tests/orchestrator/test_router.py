import json
from unittest.mock import MagicMock

import pytest

from src.main import app


def _make_mock_orchestrator(events: list | None = None) -> MagicMock:
    """Create a mock OrchestratorManager that streams the given events."""

    async def _astream(*args, **kwargs):
        for event in (events or []):
            yield event

    mock = MagicMock()
    mock.astream = _astream
    mock._graph = MagicMock()
    mock._provider = "openai"
    mock._model_name = "gpt-4o-mini"
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

        async def _capturing_astream(state, thread_id=None):
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
