import pytest
from pydantic import ValidationError

from src.orchestrator.models import AgentState, ChatMessage, ChatRequest, ChatResponse


@pytest.mark.unit
class TestChatMessage:
    def test_valid_user_message(self):
        msg = ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_valid_assistant_message(self):
        msg = ChatMessage(role="assistant", content="Hi there")
        assert msg.role == "assistant"

    def test_valid_system_message(self):
        msg = ChatMessage(role="system", content="You are a travel assistant.")
        assert msg.role == "system"

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError):
            ChatMessage(role="banana", content="Hello")

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            ChatMessage(role="user", content="")

    def test_whitespace_only_content_rejected(self):
        with pytest.raises(ValidationError):
            ChatMessage(role="user", content="   ")


@pytest.mark.unit
class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(messages=[ChatMessage(role="user", content="Hello")])
        assert len(req.messages) == 1
        assert req.session_id is None
        assert req.place_ids == []

    def test_empty_messages_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(messages=[])

    def test_session_id_optional(self):
        req = ChatRequest(
            messages=[ChatMessage(role="user", content="Hi")],
            session_id="abc-123",
        )
        assert req.session_id == "abc-123"

    def test_place_ids_accepted(self):
        req = ChatRequest(
            messages=[ChatMessage(role="user", content="Hi")],
            place_ids=["id1", "id2"],
        )
        assert req.place_ids == ["id1", "id2"]

    def test_multiple_messages_accepted(self):
        req = ChatRequest(
            messages=[
                ChatMessage(role="user", content="Hello"),
                ChatMessage(role="assistant", content="Hi"),
                ChatMessage(role="user", content="Tell me more"),
            ]
        )
        assert len(req.messages) == 3


@pytest.mark.unit
class TestChatResponse:
    def test_valid_response(self):
        resp = ChatResponse(reply="Here is your answer", session_id="abc-123")
        assert resp.reply == "Here is your answer"
        assert resp.session_id == "abc-123"

    def test_reply_required(self):
        with pytest.raises(ValidationError):
            ChatResponse(session_id="abc-123")

    def test_session_id_required(self):
        with pytest.raises(ValidationError):
            ChatResponse(reply="Hello")


@pytest.mark.unit
class TestAgentState:
    def test_default_state(self):
        state: AgentState = {"messages": [], "place_context": [], "session_id": ""}
        assert state["messages"] == []
        assert state["place_context"] == []
        assert state["session_id"] == ""

    def test_state_accepts_messages(self):
        state: AgentState = {
            "messages": [{"role": "user", "content": "Hello"}],
            "place_context": [],
            "session_id": "test-session",
        }
        assert len(state["messages"]) == 1

    def test_state_is_typed_dict(self):
        from typing import get_type_hints
        hints = get_type_hints(AgentState)
        assert "messages" in hints
        assert "place_context" in hints
        assert "session_id" in hints
