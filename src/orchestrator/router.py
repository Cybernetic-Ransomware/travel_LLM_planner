import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.config.conf_logger import setup_logger
from src.orchestrator.deps import OrchestratorDep
from src.orchestrator.models import AgentState, ChatMessage, ChatRequest

router = APIRouter()
logger = setup_logger(__name__, "orchestrator")

_ROLE_TO_LC = {"user": HumanMessage, "assistant": AIMessage, "system": SystemMessage}


def _to_lc_messages(messages: list[ChatMessage]) -> list:
    """Convert Pydantic ChatMessage list to LangChain message objects."""
    return [_ROLE_TO_LC[msg.role](content=msg.content) for msg in messages]


async def _stream_sse(orch, state: AgentState, thread_id: str) -> AsyncIterator[str]:
    """Convert OrchestratorManager astream events into SSE-formatted strings."""
    try:
        async for event in orch.astream(state, thread_id=thread_id):
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk", {})
                content = chunk.content if hasattr(chunk, "content") else chunk.get("content", "")
                if content:
                    yield f"data: {json.dumps({'content': content})}\n\n"
    except Exception:
        logger.exception("Error during orchestrator SSE stream thread_id=%s", thread_id)
        yield f"data: {json.dumps({'error': 'Stream interrupted'})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat(payload: ChatRequest, orch: OrchestratorDep) -> StreamingResponse:
    """Stream a chat response using the LangGraph orchestrator.

    Returns Server-Sent Events (text/event-stream). Each event carries a JSON
    object with a ``content`` key containing the next token chunk.
    A final ``data: [DONE]`` line signals the end of the stream.
    """
    if orch is None:
        raise HTTPException(
            status_code=503, detail="Orchestrator not available — configure LLM_PROVIDER and the corresponding API key."
        )

    session_id = payload.session_id or str(uuid.uuid4())
    state: AgentState = {
        "messages": _to_lc_messages(payload.messages),
        "place_context": [],
        "session_id": session_id,
    }
    logger.info("chat request — session_id=%s messages=%d", session_id, len(payload.messages))
    return StreamingResponse(_stream_sse(orch, state, session_id), media_type="text/event-stream")


@router.get("/status")
async def status(orch: OrchestratorDep) -> dict:
    """Return the orchestrator readiness status."""
    if orch is None:
        return {"ready": False}
    return {
        "ready": orch._graph is not None,
        "provider": orch._provider,
        "model": orch._model_name,
    }
