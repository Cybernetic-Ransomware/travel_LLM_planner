import json

import pytest

from src.panel.chat_client import ChatHistory, Message, parse_sse_line, stream_chat


@pytest.mark.unit
class TestParseSSELine:
    def test_returns_none_for_empty_line(self):
        assert parse_sse_line("") is None

    def test_returns_none_for_non_data_line(self):
        assert parse_sse_line("event: ping") is None

    def test_returns_none_for_done_sentinel(self):
        assert parse_sse_line("data: [DONE]") is None

    def test_parses_content_event(self):
        result = parse_sse_line('data: {"content": "Hello"}')
        assert result == {"content": "Hello"}

    def test_parses_session_id_event(self):
        result = parse_sse_line('data: {"session_id": "abc-123"}')
        assert result == {"session_id": "abc-123"}

    def test_returns_none_for_invalid_json(self):
        assert parse_sse_line("data: not-json") is None

    def test_parses_error_event(self):
        result = parse_sse_line('data: {"error": "Stream interrupted"}')
        assert result == {"error": "Stream interrupted"}


@pytest.mark.unit
class TestChatHistory:
    def test_empty_history_on_init(self):
        h = ChatHistory()
        assert h.messages == []
        assert h.session_id is None

    def test_add_user_message(self):
        h = ChatHistory()
        h.add("user", "Hello")
        assert len(h.messages) == 1
        assert h.messages[0].role == "user"
        assert h.messages[0].content == "Hello"

    def test_add_assistant_message(self):
        h = ChatHistory()
        h.add("assistant", "Hi there")
        assert h.messages[0].role == "assistant"

    def test_to_api_payload_format(self):
        h = ChatHistory()
        h.add("user", "Hello")
        h.add("assistant", "Hi")
        payload = h.to_api_payload()
        assert payload == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

    def test_to_api_payload_includes_session_id(self):
        h = ChatHistory(session_id="sess-1")
        h.add("user", "Hello")
        payload = h.to_api_payload()
        assert payload == [{"role": "user", "content": "Hello"}]

    def test_session_id_mutable(self):
        h = ChatHistory()
        h.session_id = "new-id"
        assert h.session_id == "new-id"


@pytest.mark.unit
class TestStreamChat:
    def _make_sse_body(self, events: list[dict]) -> bytes:
        lines = []
        for ev in events:
            lines.append(f"data: {json.dumps(ev)}")
            lines.append("")
        lines.append("data: [DONE]")
        lines.append("")
        return "\n".join(lines).encode()

    def test_yields_content_tokens(self, httpx_mock):
        body = self._make_sse_body([
            {"session_id": "s1"},
            {"content": "Hello"},
            {"content": " world"},
        ])
        httpx_mock.add_response(content=body)

        h = ChatHistory()
        tokens = list(stream_chat(h, place_ids=None))
        assert tokens == ["Hello", " world"]

    def test_session_id_set_on_history(self, httpx_mock):
        body = self._make_sse_body([{"session_id": "my-sess"}, {"content": "Hi"}])
        httpx_mock.add_response(content=body)

        h = ChatHistory()
        list(stream_chat(h, place_ids=None))
        assert h.session_id == "my-sess"

    def test_existing_session_id_sent_in_request(self, httpx_mock):
        body = self._make_sse_body([{"session_id": "existing"}, {"content": "Hi"}])
        httpx_mock.add_response(content=body)

        h = ChatHistory(session_id="existing")
        h.add("user", "Hello")
        list(stream_chat(h, place_ids=None))

        request = httpx_mock.get_requests()[0]
        payload = json.loads(request.content)
        assert payload["session_id"] == "existing"

    def test_place_ids_sent_in_request(self, httpx_mock):
        body = self._make_sse_body([{"session_id": "s"}, {"content": "Hi"}])
        httpx_mock.add_response(content=body)

        h = ChatHistory()
        h.add("user", "Plan my trip")
        list(stream_chat(h, place_ids=["id1", "id2"]))

        request = httpx_mock.get_requests()[0]
        payload = json.loads(request.content)
        assert payload["place_ids"] == ["id1", "id2"]

    def test_empty_place_ids_sent_when_none(self, httpx_mock):
        body = self._make_sse_body([{"session_id": "s"}, {"content": "Hi"}])
        httpx_mock.add_response(content=body)

        h = ChatHistory()
        h.add("user", "Hello")
        list(stream_chat(h, place_ids=None))

        request = httpx_mock.get_requests()[0]
        payload = json.loads(request.content)
        assert payload["place_ids"] == []

    def test_raises_runtime_error_on_error_event(self, httpx_mock):
        body = self._make_sse_body([
            {"session_id": "s"},
            {"error": "Stream interrupted"},
        ])
        httpx_mock.add_response(content=body)

        h = ChatHistory()
        with pytest.raises(RuntimeError, match="interrupted"):
            list(stream_chat(h, place_ids=None))

    def test_skips_non_content_events(self, httpx_mock):
        body = self._make_sse_body([
            {"session_id": "s"},
            {"content": "Token"},
        ])
        httpx_mock.add_response(content=body)

        h = ChatHistory()
        tokens = list(stream_chat(h, place_ids=None))
        assert tokens == ["Token"]
        assert "s" == h.session_id
