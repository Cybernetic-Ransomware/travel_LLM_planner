from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolCall

from src.orchestrator.graph import build_graph, chatbot_node, router_node
from src.orchestrator.models import AgentState


def _make_state(**kwargs) -> AgentState:
    defaults: AgentState = {"messages": [], "place_context": [], "session_id": "test-session"}
    defaults.update(kwargs)  # type: ignore[typeddict-item]
    return defaults


@pytest.mark.unit
class TestGraphStructure:
    def test_build_graph_returns_compiled_graph(self):
        from langgraph.graph.state import CompiledStateGraph

        mock_llm = MagicMock()
        graph = build_graph(mock_llm)
        assert isinstance(graph, CompiledStateGraph)

    def test_graph_has_chatbot_node(self):
        mock_llm = MagicMock()
        graph = build_graph(mock_llm)
        assert "chatbot" in graph.get_graph().nodes

    def test_graph_accepts_state_with_messages(self):
        mock_llm = MagicMock()
        graph = build_graph(mock_llm)
        assert graph is not None


@pytest.mark.unit
class TestRouterNode:
    async def test_routes_to_chatbot_without_tool_calls(self):
        state = _make_state(messages=[HumanMessage(content="Hello")])
        result = await router_node(state)
        assert result == "chatbot"

    async def test_routes_to_chatbot_when_no_messages(self):
        state = _make_state(messages=[])
        result = await router_node(state)
        assert result == "chatbot"

    async def test_routes_to_end_for_lone_ai_message(self):
        state = _make_state(messages=[AIMessage(content="Hello")])
        result = await router_node(state)
        assert result == "end"

    async def test_routes_to_end_when_last_ai_message_has_no_tool_calls(self):
        state = _make_state(
            messages=[
                HumanMessage(content="Hello"),
                AIMessage(content="Hi there"),
            ]
        )
        result = await router_node(state)
        assert result == "end"


@pytest.mark.unit
class TestChatbotNode:
    async def test_chatbot_node_invokes_llm(self):
        mock_response = AIMessage(content="I can help you plan your trip!")
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = _make_state(messages=[HumanMessage(content="Hello")])
        result = await chatbot_node(state, mock_llm)

        mock_llm.ainvoke.assert_called_once()
        assert "messages" in result

    async def test_chatbot_node_returns_ai_message(self):
        mock_response = AIMessage(content="Here are the places near you.")
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = _make_state(messages=[HumanMessage(content="What places are nearby?")])
        result = await chatbot_node(state, mock_llm)

        messages = result["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], AIMessage)
        assert messages[0].content == "Here are the places near you."

    async def test_chatbot_node_passes_full_message_history(self):
        mock_response = AIMessage(content="Sure!")
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = _make_state(
            messages=[
                HumanMessage(content="Hi"),
                AIMessage(content="Hello"),
                HumanMessage(content="Tell me more"),
            ]
        )
        await chatbot_node(state, mock_llm)

        called_messages = mock_llm.ainvoke.call_args[0][0]
        assert len(called_messages) == 3

    async def test_chatbot_node_with_tool_calls_in_response(self):
        tool_call = ToolCall(name="search_places", args={"query": "museums"}, id="call_1")
        mock_response = AIMessage(content="", tool_calls=[tool_call])
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = _make_state(messages=[HumanMessage(content="Find museums")])
        result = await chatbot_node(state, mock_llm)

        returned_msg = result["messages"][0]
        assert isinstance(returned_msg, AIMessage)
        assert len(returned_msg.tool_calls) == 1
