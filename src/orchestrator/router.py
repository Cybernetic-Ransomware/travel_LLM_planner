import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.config.conf_logger import setup_logger
from src.core.auth import CurrentUserDep
from src.core.db.deps import MongoDbDep
from src.core.exceptions import OrchestratorUnavailableError
from src.gmaps import fetch_places_by_ids
from src.orchestrator.deps import OrchestratorDep
from src.orchestrator.manager import OrchestratorManager
from src.orchestrator.models import AgentState, ChatMessage, ChatRequest, OrchestratorStatusOut
from src.orchestrator.tools import _WRITE_TOOL_NAMES
from src.orchestrator.trip_context import TripPromptContext, build_trip_context_prompt
from src.orchestrator.trip_session_state import TripSessionStateStore
from src.trips.deps import TripRepositoryDep
from src.trips.repository import TripRepository

router = APIRouter()
logger = setup_logger(__name__, "orchestrator")

_ROLE_TO_LC = {"user": HumanMessage, "assistant": AIMessage, "system": SystemMessage}

_MULTI_WRITE_ERROR = "I tried to make several separate changes at once. Ask me to combine them into a single edit."
_SCOPE_UNAVAILABLE_ERROR = "I couldn't set up a safe scope for that change, so I didn't make it. Please try again."


def _classify_llm_error(exc: Exception) -> str:
    type_name = type(exc).__name__
    module = type(exc).__module__ or ""
    if "RateLimitError" in type_name:
        if "openai" in module:
            return "OpenAI quota exceeded — check your billing."
        if "anthropic" in module:
            return "Anthropic rate limit exceeded — try again shortly."
        return "LLM rate limit exceeded — try again shortly."
    if "AuthenticationError" in type_name:
        return "Invalid API key — check your LLM provider configuration."
    return "Stream interrupted"


def _to_lc_messages(messages: list[ChatMessage]) -> list:
    """Convert Pydantic ChatMessage list to LangChain message objects."""
    return [_ROLE_TO_LC[msg.role](content=msg.content) for msg in messages]


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _fail_closed_write(
    orch: OrchestratorManager,
    thread_id: str,
    session_state_store: TripSessionStateStore,
) -> None:
    """Shared cleanup for every write fail-closed path: cancel dangling calls, drop the armed scope."""
    try:
        await orch.acancel_pending_tools(thread_id)
    except Exception:
        logger.exception("acancel_pending_tools failed during fail-closed for thread_id=%s", thread_id)
    try:
        await session_state_store.clear_pending(thread_id)
    except Exception:
        logger.exception("clear_pending failed during fail-closed for thread_id=%s", thread_id)


async def inspect_pending_write_interrupt(
    orch: OrchestratorManager,
    thread_id: str,
    session_state_store: TripSessionStateStore,
) -> str | None:
    """Resolve a pending write interrupt to a proposal or an explicit fail-closed error — never a silent stall."""
    if not orch.has_checkpointer:
        return None
    try:
        graph_state = await orch.graph.aget_state({"configurable": {"thread_id": thread_id}})
    except Exception:
        logger.exception("Failed to read interrupt state for thread_id=%s", thread_id)
        # Can't confirm the turn is clean or whether a write is paused — fail closed.
        await _fail_closed_write(orch, thread_id, session_state_store)
        return _sse({"error": _SCOPE_UNAVAILABLE_ERROR})
    if not graph_state or not graph_state.next:
        return None

    values = graph_state.values if isinstance(graph_state.values, dict) else {}
    messages = values.get("messages", [])
    last = messages[-1] if messages else None
    if last is None or not isinstance(last, AIMessage) or not last.tool_calls:
        return None

    write_calls = [tc for tc in last.tool_calls if tc["name"] in _WRITE_TOOL_NAMES]
    if not write_calls:
        return None

    if len(write_calls) >= 2:
        await _fail_closed_write(orch, thread_id, session_state_store)
        return _sse({"error": _MULTI_WRITE_ERROR})

    tc = write_calls[0]
    armed = await session_state_store.arm_pending(thread_id, tc["id"])
    if not armed:
        # No trusted binding to arm from — never propose a write without scope.
        await _fail_closed_write(orch, thread_id, session_state_store)
        return _sse({"error": _SCOPE_UNAVAILABLE_ERROR})

    return _sse({"tool_proposal": {"tool": tc["name"], "args": tc["args"]}})


async def _stream_sse(
    orch: OrchestratorManager,
    state: AgentState,
    thread_id: str,
    configurable: dict | None,
    session_state_store: TripSessionStateStore,
) -> AsyncIterator[str]:
    """Stream a new conversation turn as SSE, then surface any pending write interrupt."""
    yield _sse({"session_id": thread_id})
    stream_error = False
    try:
        async for event in orch.astream(state, thread_id=thread_id, configurable=configurable):
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk", {})
                content = chunk.content if hasattr(chunk, "content") else chunk.get("content", "")
                if content:
                    yield _sse({"content": content})
    except Exception as exc:
        logger.exception("Error during orchestrator SSE stream thread_id=%s", thread_id)
        yield _sse({"error": _classify_llm_error(exc)})
        stream_error = True

    if not stream_error:
        async for line in _emit_post_turn(orch, thread_id, session_state_store):
            yield line

    yield "data: [DONE]\n\n"


async def _stream_sse_resume(
    orch: OrchestratorManager,
    thread_id: str,
    confirmed: bool,
    user_message: str | None,
    session_state_store: TripSessionStateStore,
) -> AsyncIterator[str]:
    """Resume an interrupted graph turn as SSE, emit trip_updated, then re-check for a new interrupt."""
    yield _sse({"session_id": thread_id})
    stream_error = False
    try:
        async for event in orch.astream_resume(thread_id, confirmed, user_message):
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk", {})
                content = chunk.content if hasattr(chunk, "content") else chunk.get("content", "")
                if content:
                    yield _sse({"content": content})
    except Exception as exc:
        logger.exception("Error during orchestrator SSE resume thread_id=%s", thread_id)
        yield _sse({"error": _classify_llm_error(exc)})
        stream_error = True

    if not stream_error:
        async for line in _emit_post_turn(orch, thread_id, session_state_store):
            yield line

    yield "data: [DONE]\n\n"


async def _emit_post_turn(
    orch: OrchestratorManager,
    thread_id: str,
    session_state_store: TripSessionStateStore,
) -> AsyncIterator[str]:
    """Emit a trip_updated event (if a write just landed) then any fresh write interrupt line."""
    if orch.has_checkpointer:
        try:
            gs = await orch.graph.aget_state({"configurable": {"thread_id": thread_id}})
            values = gs.values if gs else None
            update = values.get("last_trip_update") if isinstance(values, dict) else None
        except Exception:
            logger.exception("Failed to read last_trip_update for thread_id=%s", thread_id)
            update = None
        if isinstance(update, dict):
            yield _sse({"trip_updated": update})
            try:
                await orch.graph.aupdate_state({"configurable": {"thread_id": thread_id}}, {"last_trip_update": None})
            except Exception:
                logger.exception("Failed to clear last_trip_update for thread_id=%s", thread_id)

    line = await inspect_pending_write_interrupt(orch, thread_id, session_state_store)
    if line is not None:
        yield line


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    orch: OrchestratorDep,
    db: MongoDbDep,
    trips: TripRepositoryDep,
    _user: CurrentUserDep,
) -> StreamingResponse:
    """Stream a chat response using the LangGraph orchestrator.

    The first SSE event carries ``session_id``; later events carry ``content``
    token chunks; ``data: [DONE]`` ends the stream. ``tool_proposal`` and
    ``trip_updated`` events appear around a confirmation-gated write.

    When ``resume_confirmed`` is set the session is assumed interrupted:
    ``True`` executes the pending tool, ``False`` cancels it.

    When ``trip_id`` is set the chat edits that saved trip: ``place_ids`` is
    ignored and the trip's contents and place scope are derived server-side.
    """
    if orch is None:
        raise OrchestratorUnavailableError(provider="configured LLM_PROVIDER")

    session_id = payload.session_id or str(uuid.uuid4())
    session_state_store = orch.trip_session_state or TripSessionStateStore(db)

    if payload.resume_confirmed is not None:
        logger.info("chat resume — session_id=%s confirmed=%s", session_id, payload.resume_confirmed)
        if payload.resume_confirmed is False:
            await session_state_store.clear_pending(session_id)
        return StreamingResponse(
            _stream_sse_resume(orch, session_id, payload.resume_confirmed, None, session_state_store),
            media_type="text/event-stream",
        )

    # A new message abandons any pending proposal: strip dangling tool_calls and drop the armed scope.
    if payload.session_id and orch.has_checkpointer:
        await orch.acancel_pending_tools(session_id)
    await session_state_store.clear_pending(session_id)

    state: AgentState
    configurable: dict | None = None

    if payload.trip_id:
        state = await _bind_trip_and_build_state(trips, session_state_store, session_id, payload, trip_id=payload.trip_id)
    else:
        place_context = await fetch_places_by_ids(db, payload.place_ids) if payload.place_ids else []
        allowed_place_ids = [str(p["_id"]) for p in place_context]
        await session_state_store.bind_place_selection(session_id, allowed_place_ids)
        # Non-authoritative under prod HITL (the store snapshot wins); only the no-checkpointer fallback reads it.
        configurable = {"allowed_place_ids": allowed_place_ids} if allowed_place_ids else None
        state = {
            "messages": _to_lc_messages(payload.messages),
            "place_context": place_context,
            "session_id": session_id,
            "trip_context": "",
            "last_trip_update": None,
        }

    logger.info(
        "chat request — session_id=%s messages=%d trip_id=%s",
        session_id,
        len(payload.messages),
        payload.trip_id,
    )
    return StreamingResponse(
        _stream_sse(orch, state, session_id, configurable, session_state_store),
        media_type="text/event-stream",
    )


async def _bind_trip_and_build_state(
    trips: TripRepository,
    session_state_store: TripSessionStateStore,
    session_id: str,
    payload: ChatRequest,
    trip_id: str,
) -> AgentState:
    try:
        trip = await trips.get(trip_id)
    except Exception:
        logger.exception("Failed to load trip for chat context trip_id=%s", trip_id)
        trip = None

    if trip is None:
        # Drop the binding entirely: an empty place_selection would still let create-only add_place through (ADR-20 §13).
        await session_state_store.clear_binding(session_id)
        note = SystemMessage(content="The referenced trip could not be loaded, so no trip is being edited right now.")
        return {
            "messages": [note, *_to_lc_messages(payload.messages)],
            "place_context": [],
            "session_id": session_id,
            "trip_context": "",
            "last_trip_update": None,
        }

    if payload.place_ids:
        logger.info("chat trip context — trip_id=%s ignoring %d client place_ids", trip_id, len(payload.place_ids))

    plan_type = getattr(trip, "plan_type", "SINGLE_DAY")
    if plan_type == "MULTI_DAY":
        allowed_place_ids = [p.place_id for p in trip.multi_day_request.places]
        trip_context = build_trip_context_prompt(TripPromptContext.from_detail(trip))
    else:
        allowed_place_ids = list(getattr(trip.optimizer_request, "place_ids", []))
        trip_context = ""

    await session_state_store.bind_trip(
        thread_id=session_id,
        trip_id=trip_id,
        plan_type=plan_type,
        name=trip.name,
        revision=trip.revision,
        allowed_place_ids=allowed_place_ids,
    )

    return {
        "messages": _to_lc_messages(payload.messages),
        "place_context": [],
        "session_id": session_id,
        "trip_context": trip_context,
        "last_trip_update": None,
    }


@router.get(
    "/status",
    response_model=OrchestratorStatusOut,
    response_model_exclude_unset=True,
)
async def status(orch: OrchestratorDep) -> OrchestratorStatusOut:
    """Return the orchestrator readiness status."""
    if orch is None:
        return OrchestratorStatusOut(ready=False)
    return OrchestratorStatusOut(ready=orch.is_ready, provider=orch.provider, model=orch.model_name)
