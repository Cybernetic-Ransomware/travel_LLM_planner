from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from pymongo.asynchronous.database import AsyncDatabase

from src.gmaps import GooglePlacesManager
from src.optimizer.matrix.client import GoogleRoutesManager
from src.orchestrator.models import AgentState
from src.orchestrator.prompt_util import _MAX_FIELD_LEN, _sanitize_for_prompt
from src.orchestrator.tools import _WRITE_TOOL_NAMES, create_tools
from src.orchestrator.trip_session_state import TripSessionStateStore
from src.trips.repository import TripRepository

__all__ = ["build_graph", "_WRITE_TOOL_NAMES", "_sanitize_for_prompt", "_MAX_FIELD_LEN"]


def _build_place_context_prompt(places: list[dict]) -> str:
    """Build a system prompt describing the user's trip places for the LLM."""
    lines = ["You are a travel planning assistant. The user has the following places in their trip plan:"]
    for p in places:
        pid = str(p.get("_id", ""))
        name = _sanitize_for_prompt(p.get("name") or pid)
        line = f"- [id={pid}] {name}"
        address = p.get("address")
        if address:
            line += f" ({_sanitize_for_prompt(address)})"
        dur = p.get("visit_duration_min")
        if dur is not None:
            line += f", {dur} min visit"
        h_from = p.get("preferred_hour_from")
        h_to = p.get("preferred_hour_to")
        if h_from is not None and h_to is not None:
            line += f", preferred {h_from}:00–{h_to}:00"
        lines.append(line)
    lines.append(
        "\nWhen suggesting changes to visit hours, always describe the proposed change first "
        "and ask the user for confirmation before calling any tool."
    )
    return "\n".join(lines)


async def router_node(state: AgentState) -> str:
    """Conditional edge from START — decides which node handles the current state.

    Returns "end" when the last message is an AI response without tool calls
    (conversation turn is complete). Returns "chatbot" otherwise to invoke the LLM.
    """
    messages = state.get("messages", [])
    if not messages:
        return "chatbot"
    last = messages[-1]
    if isinstance(last, AIMessage) and not last.tool_calls:
        return "end"
    return "chatbot"


async def chatbot_node(state: AgentState, llm: BaseChatModel) -> dict:
    """Invoke the LLM with the full conversation history and return the response.

    Prepends a trip-context SystemMessage when the chat is bound to a saved trip,
    and/or a place-context SystemMessage for generic selection chats.
    """
    prefix: list[SystemMessage] = []
    trip_context = state.get("trip_context")
    if trip_context:
        prefix.append(SystemMessage(content=trip_context))
    place_context = state.get("place_context") or []
    if place_context:
        prefix.append(SystemMessage(content=_build_place_context_prompt(place_context)))

    messages = prefix + list(state["messages"]) if prefix else list(state["messages"])
    response = await llm.ainvoke(messages)
    return {"messages": [response]}


def _after_chatbot(state: AgentState) -> str:
    """Route after chatbot: write batch -> ``tools_write`` (interrupt), reads -> ``tools_read``, else END."""
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last = messages[-1]
    if not (isinstance(last, AIMessage) and last.tool_calls):
        return "end"
    if any(tc["name"] in _WRITE_TOOL_NAMES for tc in last.tool_calls):
        return "tools_write"
    return "tools_read"


def build_graph(
    llm: BaseChatModel,
    checkpointer: BaseCheckpointSaver | None = None,
    db: AsyncDatabase | None = None,
    trips_repo: TripRepository | None = None,
    places_manager: GooglePlacesManager | None = None,
    routes_manager: GoogleRoutesManager | None = None,
    session_state_store: TripSessionStateStore | None = None,
) -> CompiledStateGraph:
    """Build and compile the orchestrator StateGraph.

    With ``db`` the graph is a ReAct loop with a split tool stage:

        START -> router -> chatbot -> (_after_chatbot)
                                       |-> tools_write -> chatbot   (interrupt_before when checkpointed)
                                       |-> tools_read  -> chatbot
                                       |-> END

    ``tools_write`` is built with *every* tool, not just the write ones, so a
    mixed read+write batch still resolves after a single confirmation.
    Without ``db`` the graph keeps the original linear topology.
    """
    if db is not None:
        tools = create_tools(
            db,
            trips_repo=trips_repo,
            places_manager=places_manager,
            routes_manager=routes_manager,
            session_state_store=session_state_store,
        )
        read_tools = [t for t in tools if t.name not in _WRITE_TOOL_NAMES]
        llm_with_tools = llm.bind_tools(tools)

        async def _chatbot(state: AgentState) -> dict:
            return await chatbot_node(state, llm_with_tools)

        graph = StateGraph(AgentState)
        graph.add_node("chatbot", _chatbot)
        graph.add_node("tools_read", ToolNode(read_tools))
        graph.add_node("tools_write", ToolNode(tools))
        graph.add_conditional_edges(START, router_node, {"chatbot": "chatbot", "end": END})
        graph.add_conditional_edges(
            "chatbot",
            _after_chatbot,
            {"tools_write": "tools_write", "tools_read": "tools_read", "end": END},
        )
        graph.add_edge("tools_read", "chatbot")
        graph.add_edge("tools_write", "chatbot")

        interrupt_before = ["tools_write"] if checkpointer is not None else []
        return graph.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)

    async def _chatbot_no_tools(state: AgentState) -> dict:
        return await chatbot_node(state, llm)

    graph = StateGraph(AgentState)
    graph.add_node("chatbot", _chatbot_no_tools)
    graph.add_conditional_edges(START, router_node, {"chatbot": "chatbot", "end": END})
    graph.add_edge("chatbot", END)
    return graph.compile(checkpointer=checkpointer)
