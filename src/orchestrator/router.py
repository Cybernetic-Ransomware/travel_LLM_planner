import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.config.conf_logger import setup_logger
from src.core.db.deps import MongoDbDep
from src.core.exceptions import OrchestratorUnavailableError
from src.gmaps import fetch_places_by_ids
from src.orchestrator.deps import OrchestratorDep
from src.orchestrator.models import AgentState, ChatMessage, ChatRequest

router = APIRouter()
logger = setup_logger(__name__, "orchestrator")

_ROLE_TO_LC = {"user": HumanMessage, "assistant": AIMessage, "system": SystemMessage}


def _to_lc_messages(messages: list[ChatMessage]) -> list:
    """Convert Pydantic ChatMessage list to LangChain message objects."""
    return [_ROLE_TO_LC[msg.role](content=msg.content) for msg in messages]


async def _stream_sse(
    orch,
    state: AgentState,
    thread_id: str,
    configurable: dict | None,
) -> AsyncIterator[str]:
    """Stream a new conversation turn as SSE.

    After the LLM finishes, checks the checkpointed graph state for a pending
    interrupt (tool awaiting user confirmation) and emits a ``tool_proposal``
    event so the client can surface the confirmation UI.
    """
    yield f"data: {json.dumps({'session_id': thread_id})}\n\n"
    stream_error = False
    try:
        async for event in orch.astream(state, thread_id=thread_id, configurable=configurable):
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk", {})
                content = chunk.content if hasattr(chunk, "content") else chunk.get("content", "")
                if content:
                    yield f"data: {json.dumps({'content': content})}\n\n"
    except Exception:
        logger.exception("Error during orchestrator SSE stream thread_id=%s", thread_id)
        yield f"data: {json.dumps({'error': 'Stream interrupted'})}\n\n"
        stream_error = True

    if not stream_error and orch.has_checkpointer:
        try:
            graph_state = await orch.graph.aget_state({"configurable": {"thread_id": thread_id}})
            if graph_state and graph_state.next:
                messages = graph_state.values.get("messages", [])
                last = messages[-1] if messages else None
                if last is not None and isinstance(last, AIMessage) and last.tool_calls:
                    for tc in last.tool_calls:
                        yield f"data: {json.dumps({'tool_proposal': {'tool': tc['name'], 'args': tc['args']}})}\n\n"
        except Exception:
            logger.exception("Failed to read interrupt state for thread_id=%s", thread_id)

    yield "data: [DONE]\n\n"


async def _stream_sse_resume(
    orch,
    thread_id: str,
    confirmed: bool,
    user_message: str | None,
) -> AsyncIterator[str]:
    """Resume an interrupted graph turn as SSE.

    Delegates confirm/cancel logic to ``OrchestratorManager.astream_resume``.
    """
    yield f"data: {json.dumps({'session_id': thread_id})}\n\n"
    try:
        async for event in orch.astream_resume(thread_id, confirmed, user_message):
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk", {})
                content = chunk.content if hasattr(chunk, "content") else chunk.get("content", "")
                if content:
                    yield f"data: {json.dumps({'content': content})}\n\n"
    except Exception:
        logger.exception("Error during orchestrator SSE resume thread_id=%s", thread_id)
        yield f"data: {json.dumps({'error': 'Stream interrupted'})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat(payload: ChatRequest, orch: OrchestratorDep, db: MongoDbDep) -> StreamingResponse:
    """Stream a chat response using the LangGraph orchestrator.

    Returns Server-Sent Events (text/event-stream). The first event carries
    ``session_id``. Subsequent events carry ``content`` token chunks.
    A final ``data: [DONE]`` line signals the end of the stream.

    When ``resume_confirmed`` is set (``True`` or ``False``), the session is
    assumed to be in an interrupted state (tool awaiting confirmation).
    ``True`` executes the pending tool; ``False`` cancels it.
    """
    if orch is None:
        raise OrchestratorUnavailableError(provider="configured LLM_PROVIDER")

    session_id = payload.session_id or str(uuid.uuid4())

    if payload.resume_confirmed is not None:
        user_message = payload.messages[-1].content if payload.messages else None
        logger.info("chat resume — session_id=%s confirmed=%s", session_id, payload.resume_confirmed)
        return StreamingResponse(
            _stream_sse_resume(orch, session_id, payload.resume_confirmed, user_message),
            media_type="text/event-stream",
        )

    place_context = await fetch_places_by_ids(db, payload.place_ids) if payload.place_ids else []
    allowed_place_ids = [str(p["_id"]) for p in place_context]
    configurable = {"allowed_place_ids": allowed_place_ids} if allowed_place_ids else None

    state: AgentState = {
        "messages": _to_lc_messages(payload.messages),
        "place_context": place_context,
        "session_id": session_id,
    }
    logger.info(
        "chat request — session_id=%s messages=%d places=%d",
        session_id,
        len(payload.messages),
        len(place_context),
    )
    return StreamingResponse(
        _stream_sse(orch, state, session_id, configurable),
        media_type="text/event-stream",
    )


@router.get("/status")
async def status(orch: OrchestratorDep) -> dict:
    """Return the orchestrator readiness status."""
    if orch is None:
        return {"ready": False}
    return {
        "ready": orch.is_ready,
        "provider": orch.provider,
        "model": orch.model_name,
    }
