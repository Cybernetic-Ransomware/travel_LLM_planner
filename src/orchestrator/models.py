from typing import Annotated, Literal, NotRequired

from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import TypedDict


class ChatMessage(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"role": "user", "content": "What are the opening hours?"}})

    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def content_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "messages": [{"role": "user", "content": "Tell me about Wawel Castle"}],
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "trip_id": None,
                "place_ids": [],
                "resume_confirmed": None,
            }
        }
    )

    messages: list[ChatMessage] = Field(min_length=1)
    session_id: str | None = None
    # When set, the chat edits this persisted trip; place_ids is ignored and scope is server-derived (ADR-20).
    trip_id: str | None = None
    place_ids: list[str] = Field(default_factory=list)
    resume_confirmed: bool | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class OrchestratorStatusOut(BaseModel):
    ready: bool
    provider: str | None = None
    model: str | None = None


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    place_context: list[dict]
    session_id: str
    # Rendered system-prompt block for the bound trip ("" when the chat isn't trip-scoped).
    trip_context: NotRequired[str]
    # Result echo written by edit_multi_day_trip so the router can emit a trip_updated SSE event.
    last_trip_update: NotRequired[dict | None]
