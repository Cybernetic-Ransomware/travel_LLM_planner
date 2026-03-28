from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.orchestrator.models import AgentState


def _build_place_context_prompt(places: list[dict]) -> str:
    """Build a system prompt describing the user's trip places for the LLM."""
    lines = ["You are a travel planning assistant. The user has the following places in their trip plan:"]
    for p in places:
        name = p.get("name") or str(p.get("_id", ""))
        line = f"- {name}"
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


def build_graph(llm: BaseChatModel, checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """Build and compile the LangGraph StateGraph for the orchestrator.

    The graph topology for this skeleton:
        START → router_node ─── "chatbot" ──→ chatbot_node → END
                             └── "end" ──→ END

    Future extensions: add tool nodes and wire them from router_node.
    """

    async def _chatbot(state: AgentState) -> dict:
        return await chatbot_node(state, llm)

    graph = StateGraph(AgentState)
    graph.add_node("chatbot", _chatbot)
    graph.add_conditional_edges(START, router_node, {"chatbot": "chatbot", "end": END})
    graph.add_edge("chatbot", END)
    return graph.compile(checkpointer=checkpointer)
