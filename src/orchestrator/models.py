from typing import Annotated, Literal

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
                "place_ids": [],
                "resume_confirmed": None,
            }
        }
    )

    messages: list[ChatMessage] = Field(min_length=1)
    session_id: str | None = None
    place_ids: list[str] = Field(default_factory=list)
    resume_confirmed: bool | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    place_context: list[dict]
    session_id: str
