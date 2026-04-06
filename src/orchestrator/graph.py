from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from pymongo.asynchronous.database import AsyncDatabase

from src.orchestrator.models import AgentState
from src.orchestrator.tools import create_tools


def _build_place_context_prompt(places: list[dict]) -> str:
    """Build a system prompt describing the user's trip places for the LLM."""
    lines = ["You are a travel planning assistant. The user has the following places in their trip plan:"]
    for p in places:
        pid = str(p.get("_id", ""))
        name = p.get("name") or pid
        line = f"- [id={pid}] {name}"
        address = p.get("address")
        if address:
            line += f" ({address})"
        dur = p.get("visit_duration_min")
        if dur is not None:
            line += f", {dur} min visit"
        h_from = p.get("preferred_hour_from")
        h_to = p.get("preferred_hour_to")
        if h_from is not None and h_to is not None:
            line += f", preferred {h_from}:00\u2013{h_to}:00"
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

    When place_context is provided, prepends a SystemMessage describing the trip
    so the LLM can reason about the user's specific places.
    """
    place_context = state.get("place_context") or []
    if place_context:
        messages = [SystemMessage(content=_build_place_context_prompt(place_context))] + list(state["messages"])
    else:
        messages = list(state["messages"])
    response = await llm.ainvoke(messages)
    return {"messages": [response]}


def _after_chatbot(state: AgentState) -> str:
    """Conditional edge after chatbot — routes to tool execution or END."""
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "end"


def build_graph(
    llm: BaseChatModel,
    checkpointer: BaseCheckpointSaver | None = None,
    db: AsyncDatabase | None = None,
) -> CompiledStateGraph:
    """Build and compile the LangGraph StateGraph for the orchestrator.

    When ``db`` is provided, the graph is extended with a tool node for
    ``update_visit_hours``. The LLM is bound with tool schemas so it can emit
    tool calls, and the graph topology becomes a ReAct loop:

        START → router_node ─── "chatbot" ──→ chatbot ──→ (tool_calls?) ──→ tools ──→ chatbot
                             └── "end" ──→ END                           └── END

    ``interrupt_before=["tools"]`` is applied only when a checkpointer is present,
    enabling human-in-the-loop confirmation before any tool writes to MongoDB.

    Without ``db`` the graph retains the original linear topology.
    """
    if db is not None:
        tools = create_tools(db)
        llm_with_tools = llm.bind_tools(tools)

        async def _chatbot(state: AgentState) -> dict:
            return await chatbot_node(state, llm_with_tools)

        graph = StateGraph(AgentState)
        graph.add_node("chatbot", _chatbot)
        graph.add_node("tools", ToolNode(tools))
        graph.add_conditional_edges(START, router_node, {"chatbot": "chatbot", "end": END})
        graph.add_conditional_edges("chatbot", _after_chatbot, {"tools": "tools", "end": END})
        graph.add_edge("tools", "chatbot")

        interrupt_before = ["tools"] if checkpointer is not None else []
        return graph.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)

    async def _chatbot_no_tools(state: AgentState) -> dict:
        return await chatbot_node(state, llm)

    graph = StateGraph(AgentState)
    graph.add_node("chatbot", _chatbot_no_tools)
    graph.add_conditional_edges(START, router_node, {"chatbot": "chatbot", "end": END})
    graph.add_edge("chatbot", END)
    return graph.compile(checkpointer=checkpointer)
