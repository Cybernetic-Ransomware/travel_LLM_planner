from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.tools import create_tools


def _make_tool(db=None):
    """Return the update_visit_hours tool with a mock database."""
    return create_tools(db or MagicMock())[0]


def _config(allowed: list[str] | None = None) -> dict:
    """Build a minimal RunnableConfig-style dict for tool invocation."""
    return {"configurable": {"allowed_place_ids": allowed or []}}


@pytest.mark.unit
class TestToolMetadata:
    def test_create_tools_returns_non_empty_list(self):
        tools = create_tools(MagicMock())
        assert len(tools) >= 1

    def test_tool_has_expected_name(self):
        tool = _make_tool()
        assert tool.name == "update_visit_hours"

    def test_tool_has_non_empty_description(self):
        tool = _make_tool()
        assert tool.description and len(tool.description) > 10

    def test_tool_schema_has_place_id_field(self):
        tool = _make_tool()
        props = tool.args_schema.model_json_schema()["properties"]
        assert "place_id" in props

    def test_tool_schema_has_hour_fields(self):
        tool = _make_tool()
        props = tool.args_schema.model_json_schema()["properties"]
        assert "preferred_hour_from" in props
        assert "preferred_hour_to" in props

    def test_tool_schema_has_duration_field(self):
        tool = _make_tool()
        props = tool.args_schema.model_json_schema()["properties"]
        assert "visit_duration_min" in props

    def test_tool_schema_config_not_exposed_to_llm(self):
        tool = _make_tool()
        props = tool.args_schema.model_json_schema()["properties"]
        assert "config" not in props


@pytest.mark.unit
class TestUpdateVisitHoursSuccess:
    async def test_calls_find_and_update_with_correct_patch(self):
        tool = _make_tool()
        updated_doc = {"name": "Wawel Castle", "preferred_hour_from": 9, "preferred_hour_to": 17}
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)) as mock_update:
            await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 9, "preferred_hour_to": 17},
                config=_config([place_id]),
            )

        mock_update.assert_called_once()
        _, called_id, called_patch = mock_update.call_args[0]
        assert called_id == place_id
        assert called_patch.preferred_hour_from == 9
        assert called_patch.preferred_hour_to == 17

    async def test_returns_success_string_with_place_name(self):
        tool = _make_tool()
        updated_doc = {"name": "Wawel Castle", "preferred_hour_from": 9, "preferred_hour_to": 17}
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)):
            result = await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 9, "preferred_hour_to": 17},
                config=_config([place_id]),
            )

        assert isinstance(result, str)
        assert "Wawel Castle" in result
        assert "9:00" in result
        assert "17:00" in result

    async def test_partial_update_only_hour_from(self):
        tool = _make_tool()
        place_id = "abc123"
        updated_doc = {"name": "Wawel", "preferred_hour_from": 10}

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)) as mock_update:
            await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 10},
                config=_config([place_id]),
            )

        _, _, called_patch = mock_update.call_args[0]
        assert called_patch.preferred_hour_from == 10
        assert called_patch.preferred_hour_to is None

    async def test_partial_update_only_hour_to(self):
        tool = _make_tool()
        place_id = "abc123"
        updated_doc = {"name": "Wawel", "preferred_hour_to": 18}

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)) as mock_update:
            await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_to": 18},
                config=_config([place_id]),
            )

        _, _, called_patch = mock_update.call_args[0]
        assert called_patch.preferred_hour_to == 18
        assert called_patch.preferred_hour_from is None

    async def test_boundary_hours_zero_and_twentythree(self):
        tool = _make_tool()
        place_id = "abc123"
        updated_doc = {"name": "Wawel", "preferred_hour_from": 0, "preferred_hour_to": 23}

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)):
            result = await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 0, "preferred_hour_to": 23},
                config=_config([place_id]),
            )

        assert "Failed" not in result
        assert "Invalid" not in result

    async def test_update_visit_duration(self):
        tool = _make_tool()
        place_id = "abc123"
        updated_doc = {"name": "Wawel", "visit_duration_min": 120}

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)) as mock_update:
            await tool.ainvoke(
                {"place_id": place_id, "visit_duration_min": 120},
                config=_config([place_id]),
            )

        _, _, called_patch = mock_update.call_args[0]
        assert called_patch.visit_duration_min == 120

    async def test_empty_allowed_list_skips_scope_check(self):
        tool = _make_tool()
        updated_doc = {"name": "Anywhere", "preferred_hour_from": 9, "preferred_hour_to": 17}

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)):
            result = await tool.ainvoke(
                {"place_id": "any-id", "preferred_hour_from": 9, "preferred_hour_to": 17},
                config=_config([]),
            )

        assert "Cannot update" not in result


@pytest.mark.unit
class TestUpdateVisitHoursErrors:
    async def test_place_not_found_returns_not_found_message(self):
        tool = _make_tool()
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=None)):
            result = await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 9, "preferred_hour_to": 17},
                config=_config([place_id]),
            )

        assert "not found" in result.lower()

    async def test_inverted_hour_range_returns_validation_error_string(self):
        tool = _make_tool()
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock()) as mock_update:
            result = await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 17, "preferred_hour_to": 9},
                config=_config([place_id]),
            )

        assert "Invalid" in result
        mock_update.assert_not_called()

    async def test_equal_hours_returns_validation_error_string(self):
        tool = _make_tool()
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock()) as mock_update:
            result = await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 10, "preferred_hour_to": 10},
                config=_config([place_id]),
            )

        assert "Invalid" in result
        mock_update.assert_not_called()

    async def test_hour_out_of_range_high_returns_error(self):
        tool = _make_tool()
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock()) as mock_update:
            result = await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 25},
                config=_config([place_id]),
            )

        assert "Invalid" in result
        mock_update.assert_not_called()

    async def test_hour_out_of_range_negative_returns_error(self):
        tool = _make_tool()
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock()) as mock_update:
            result = await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_to": -1},
                config=_config([place_id]),
            )

        assert "Invalid" in result
        mock_update.assert_not_called()

    async def test_db_exception_returns_error_string(self):
        tool = _make_tool()
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(side_effect=Exception("connection lost"))):
            result = await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 9, "preferred_hour_to": 17},
                config=_config([place_id]),
            )

        assert "Failed" in result
        assert "connection lost" in result


@pytest.mark.unit
class TestScopeGuard:
    async def test_rejects_place_id_not_in_allowed_list(self):
        tool = _make_tool()

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock()) as mock_update:
            result = await tool.ainvoke(
                {"place_id": "unauthorized-id", "preferred_hour_from": 9, "preferred_hour_to": 17},
                config=_config(["allowed-id-1", "allowed-id-2"]),
            )

        assert "not part of the current trip plan" in result
        mock_update.assert_not_called()

    async def test_allows_place_id_in_allowed_list(self):
        tool = _make_tool()
        place_id = "allowed-id-1"
        updated_doc = {"name": "Wawel", "preferred_hour_from": 9, "preferred_hour_to": 17}

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)):
            result = await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 9, "preferred_hour_to": 17},
                config=_config([place_id, "other-id"]),
            )

        assert "Cannot update" not in result
