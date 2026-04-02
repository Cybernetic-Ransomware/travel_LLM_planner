"""Framework-agnostic SSE client for the orchestrator /chat endpoint."""

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

import httpx

from src.panel.messages import ERR_CHAT_INTERRUPTED, ERR_CHAT_UNAVAILABLE

_API_URL = os.getenv("API_URL", "http://localhost:8080").rstrip("/")
_ORCHESTRATOR_BASE = f"{_API_URL}/api/v1/core/orchestrator"


@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class ChatHistory:
    messages: list[Message] = field(default_factory=list)
    session_id: str | None = None

    def add(self, role: Literal["user", "assistant"], content: str) -> None:
        self.messages.append(Message(role=role, content=content))

    def to_api_payload(self) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in self.messages]


def parse_sse_line(line: str) -> dict | None:
    """Parse a single SSE line into a dict, or return None if not a data event."""
    if not line.startswith("data: "):
        return None
    payload = line[len("data: ") :]
    if payload.strip() == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def stream_chat(history: ChatHistory, place_ids: list[str] | None) -> Iterator[str]:
    """Stream content tokens from the orchestrator /chat endpoint.

    Mutates history.session_id in-place from the first SSE event.
    Yields content token strings. Raises RuntimeError on error events.
    """
    payload = {
        "messages": history.to_api_payload(),
        "session_id": history.session_id,
        "place_ids": place_ids or [],
    }
    with httpx.stream("POST", f"{_ORCHESTRATOR_BASE}/chat", json=payload, timeout=60.0) as response:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise RuntimeError(ERR_CHAT_UNAVAILABLE) from None
        for line in response.iter_lines():
            event = parse_sse_line(line)
            if event is None:
                continue
            if "session_id" in event and history.session_id is None:
                history.session_id = event["session_id"]
            elif "error" in event:
                raise RuntimeError(ERR_CHAT_INTERRUPTED)
            elif "content" in event:
                yield event["content"]


def check_status() -> bool:
    """Return True if the orchestrator is ready to accept requests."""
    try:
        r = httpx.get(f"{_ORCHESTRATOR_BASE}/status")
        r.raise_for_status()
        return r.json().get("ready", False)
    except Exception:
        return False
