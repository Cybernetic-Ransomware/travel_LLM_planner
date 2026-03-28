from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.orchestrator.models import AgentState


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
    """Invoke the LLM with the full conversation history and return the response."""
    response = await llm.ainvoke(state["messages"])
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
