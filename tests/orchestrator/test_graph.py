from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolCall

from src.orchestrator.graph import _after_chatbot, build_graph, chatbot_node, router_node
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


@pytest.mark.unit
class TestBuildPlaceContextPrompt:
    def test_header_present(self):
        from src.orchestrator.graph import _build_place_context_prompt

        result = _build_place_context_prompt([])
        assert "travel planning assistant" in result

    def test_formats_place_with_all_fields(self):
        from src.orchestrator.graph import _build_place_context_prompt

        place = {
            "_id": "abc123",
            "name": "Wawel Castle",
            "address": "Wawel 5, Kraków",
            "visit_duration_min": 90,
            "preferred_hour_from": 9,
            "preferred_hour_to": 17,
        }
        result = _build_place_context_prompt([place])
        assert "Wawel Castle" in result
        assert "Wawel 5, Kraków" in result
        assert "90 min" in result
        assert "9:00" in result
        assert "17:00" in result

    def test_formats_multiple_places(self):
        from src.orchestrator.graph import _build_place_context_prompt

        places = [
            {"_id": "a", "name": "Place A"},
            {"_id": "b", "name": "Place B"},
        ]
        result = _build_place_context_prompt(places)
        assert "Place A" in result
        assert "Place B" in result

    def test_objectid_used_as_name_fallback(self):
        from bson import ObjectId

        from src.orchestrator.graph import _build_place_context_prompt

        oid = ObjectId()
        place = {"_id": oid}
        result = _build_place_context_prompt([place])
        assert str(oid) in result

    def test_missing_optional_fields_no_crash(self):
        from src.orchestrator.graph import _build_place_context_prompt

        place = {"_id": "xyz", "name": "Minimal Place"}
        result = _build_place_context_prompt([place])
        assert "Minimal Place" in result

    def test_place_id_included_in_prompt(self):
        from src.orchestrator.graph import _build_place_context_prompt

        place = {"_id": "abc123", "name": "Wawel Castle"}
        result = _build_place_context_prompt([place])
        assert "[id=abc123]" in result


@pytest.mark.unit
class TestChatbotNodePlaceContext:
    async def test_system_message_prepended_when_context_nonempty(self):
        mock_response = AIMessage(content="Sure!")
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = _make_state(
            messages=[HumanMessage(content="Tell me about Wawel")],
            place_context=[{"_id": "abc", "name": "Wawel Castle"}],
        )
        await chatbot_node(state, mock_llm)

        called_messages = mock_llm.ainvoke.call_args[0][0]
        assert isinstance(called_messages[0], SystemMessage)

    async def test_system_message_contains_place_name(self):
        mock_response = AIMessage(content="Sure!")
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = _make_state(
            messages=[HumanMessage(content="Hi")],
            place_context=[{"_id": "abc", "name": "Wawel Castle"}],
        )
        await chatbot_node(state, mock_llm)

        called_messages = mock_llm.ainvoke.call_args[0][0]
        assert "Wawel Castle" in called_messages[0].content

    async def test_no_system_message_when_context_empty(self):
        mock_response = AIMessage(content="Sure!")
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = _make_state(messages=[HumanMessage(content="Hi")], place_context=[])
        await chatbot_node(state, mock_llm)

        called_messages = mock_llm.ainvoke.call_args[0][0]
        assert not any(isinstance(m, SystemMessage) for m in called_messages)

    async def test_original_user_message_preserved_in_call(self):
        mock_response = AIMessage(content="Sure!")
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        original = HumanMessage(content="Tell me about Wawel")
        state = _make_state(
            messages=[original],
            place_context=[{"_id": "abc", "name": "Wawel Castle"}],
        )
        await chatbot_node(state, mock_llm)

        called_messages = mock_llm.ainvoke.call_args[0][0]
        assert called_messages[-1] is original

    async def test_message_count_with_context(self):
        mock_response = AIMessage(content="Sure!")
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = _make_state(
            messages=[HumanMessage(content="Hi")],
            place_context=[{"_id": "abc", "name": "Wawel Castle"}],
        )
        await chatbot_node(state, mock_llm)

        called_messages = mock_llm.ainvoke.call_args[0][0]
        assert len(called_messages) == 2


@pytest.mark.unit
class TestGraphStructureWithTools:
    def test_build_graph_with_db_returns_compiled_graph(self):
        from langgraph.graph.state import CompiledStateGraph

        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_db = MagicMock()
        graph = build_graph(mock_llm, db=mock_db)
        assert isinstance(graph, CompiledStateGraph)

    def test_graph_with_db_has_tools_node(self):
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_db = MagicMock()
        graph = build_graph(mock_llm, db=mock_db)
        assert "tools" in graph.get_graph().nodes

    def test_graph_with_db_still_has_chatbot_node(self):
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_db = MagicMock()
        graph = build_graph(mock_llm, db=mock_db)
        assert "chatbot" in graph.get_graph().nodes

    def test_graph_without_db_has_no_tools_node(self):
        mock_llm = MagicMock()
        graph = build_graph(mock_llm)
        assert "tools" not in graph.get_graph().nodes

    def test_graph_without_db_backward_compatible(self):
        from langgraph.graph.state import CompiledStateGraph

        mock_llm = MagicMock()
        graph = build_graph(mock_llm)
        assert isinstance(graph, CompiledStateGraph)


@pytest.mark.unit
class TestAfterChatbot:
    async def test_routes_to_tools_when_ai_message_has_tool_calls(self):
        tool_call = ToolCall(name="update_visit_hours", args={"place_id": "abc"}, id="call_1")
        state = _make_state(messages=[AIMessage(content="", tool_calls=[tool_call])])
        result = _after_chatbot(state)
        assert result == "tools"

    async def test_routes_to_end_when_ai_message_has_no_tool_calls(self):
        state = _make_state(messages=[AIMessage(content="Here is the answer.")])
        result = _after_chatbot(state)
        assert result == "end"

    async def test_routes_to_end_for_human_message(self):
        state = _make_state(messages=[HumanMessage(content="Hello")])
        result = _after_chatbot(state)
        assert result == "end"

    async def test_routes_to_end_for_empty_messages(self):
        state = _make_state(messages=[])
        result = _after_chatbot(state)
        assert result == "end"
