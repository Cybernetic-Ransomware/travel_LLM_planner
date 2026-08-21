from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import InvalidHourRangeError
from src.orchestrator.tools import PRICING_FIELD_MASK, create_tools


def _make_tool(db=None):
    """Return the update_visit_hours tool with a mock database."""
    return create_tools(db or MagicMock())[0]


def _tool_by_name(name: str, db=None, places_manager=None):
    """Return a tool from create_tools by its name."""
    tools = create_tools(db or MagicMock(), places_manager)
    return next(t for t in tools if t.name == name)


def _config(allowed: list[str] | None = None) -> dict:
    """Build a minimal RunnableConfig-style dict for tool invocation."""
    return {"configurable": {"allowed_place_ids": allowed or []}}


@pytest.mark.unit
class TestToolMetadata:
    def test_create_tools_returns_five_tools_without_places_manager(self):
        tools = create_tools(MagicMock())
        assert len(tools) == 5

    def test_create_tools_returns_seven_tools_with_places_manager(self):
        tools = create_tools(MagicMock(), MagicMock())
        assert len(tools) == 7

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

    @pytest.mark.regression
    async def test_omitted_args_not_marked_set_on_patch(self):
        """Regression: PlacePatch clears explicitly-null fields, so the tool must
        build the patch only from provided arguments — omitted args must not appear
        in model_fields_set or they would be $unset in storage."""
        tool = _make_tool()
        place_id = "abc123"
        updated_doc = {"name": "Wawel", "visit_duration_min": 45}

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)) as mock_update:
            await tool.ainvoke(
                {"place_id": place_id, "visit_duration_min": 45},
                config=_config([place_id]),
            )

        _, _, called_patch = mock_update.call_args[0]
        assert called_patch.model_fields_set == {"visit_duration_min"}

    @pytest.mark.regression
    async def test_no_args_returns_message_without_db_call(self):
        tool = _make_tool()
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock()) as mock_update:
            result = await tool.ainvoke({"place_id": place_id}, config=_config([place_id]))

        assert "No fields to update" in result
        mock_update.assert_not_called()


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

    @pytest.mark.regression
    async def test_invalid_hour_range_error_returns_friendly_message(self):
        tool = _make_tool()
        place_id = "abc123"

        with patch(
            "src.orchestrator.tools.find_and_update_place",
            new=AsyncMock(side_effect=InvalidHourRangeError()),
        ):
            result = await tool.ainvoke(
                {"place_id": place_id, "preferred_hour_from": 18},
                config=_config([place_id]),
            )

        assert result == "Invalid visit hours: preferred_hour_from must be less than preferred_hour_to"


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


@pytest.mark.unit
class TestSkipPlaceMetadata:
    def test_tool_has_expected_name(self):
        tool = _tool_by_name("skip_place")
        assert tool.name == "skip_place"

    def test_tool_has_non_empty_description(self):
        tool = _tool_by_name("skip_place")
        assert tool.description and len(tool.description) > 10

    def test_tool_schema_config_not_exposed_to_llm(self):
        tool = _tool_by_name("skip_place")
        props = tool.args_schema.model_json_schema()["properties"]
        assert "config" not in props

    def test_tool_schema_has_place_id_and_skipped(self):
        tool = _tool_by_name("skip_place")
        props = tool.args_schema.model_json_schema()["properties"]
        assert "place_id" in props
        assert "skipped" in props


@pytest.mark.unit
class TestSkipPlaceSuccess:
    async def test_skip_returns_skipped_message(self):
        place_id = "abc123"
        updated_doc = {"name": "Wawel Castle", "skipped": True}

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)):
            result = await _tool_by_name("skip_place").ainvoke(
                {"place_id": place_id, "skipped": True},
                config=_config([place_id]),
            )

        assert "Skipped" in result
        assert "Wawel Castle" in result

    async def test_unskip_returns_restored_message(self):
        place_id = "abc123"
        updated_doc = {"name": "Wawel Castle", "skipped": False}

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)):
            result = await _tool_by_name("skip_place").ainvoke(
                {"place_id": place_id, "skipped": False},
                config=_config([place_id]),
            )

        assert "Restored" in result
        assert "Wawel Castle" in result

    async def test_passes_skipped_flag_in_patch(self):
        place_id = "abc123"
        updated_doc = {"name": "Wawel", "skipped": True}

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=updated_doc)) as mock_update:
            await _tool_by_name("skip_place").ainvoke(
                {"place_id": place_id, "skipped": True},
                config=_config([place_id]),
            )

        _, _, called_patch = mock_update.call_args[0]
        assert called_patch.skipped is True


@pytest.mark.unit
class TestSkipPlaceErrors:
    async def test_place_not_found_returns_not_found_message(self):
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(return_value=None)):
            result = await _tool_by_name("skip_place").ainvoke(
                {"place_id": place_id, "skipped": True},
                config=_config([place_id]),
            )

        assert "not found" in result.lower()

    async def test_db_exception_returns_error_string(self):
        place_id = "abc123"

        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock(side_effect=Exception("timeout"))):
            result = await _tool_by_name("skip_place").ainvoke(
                {"place_id": place_id, "skipped": True},
                config=_config([place_id]),
            )

        assert "Failed" in result

    async def test_scope_guard_rejects_place_not_in_allowed_list(self):
        with patch("src.orchestrator.tools.find_and_update_place", new=AsyncMock()) as mock_update:
            result = await _tool_by_name("skip_place").ainvoke(
                {"place_id": "unauthorized", "skipped": True},
                config=_config(["allowed-id"]),
            )

        assert "not part of the current trip plan" in result
        mock_update.assert_not_called()


@pytest.mark.unit
class TestAddPlaceMetadata:
    def test_tool_has_expected_name(self):
        tool = _tool_by_name("add_place")
        assert tool.name == "add_place"

    def test_tool_has_non_empty_description(self):
        tool = _tool_by_name("add_place")
        assert tool.description and len(tool.description) > 10

    def test_tool_schema_config_not_exposed_to_llm(self):
        tool = _tool_by_name("add_place")
        props = tool.args_schema.model_json_schema()["properties"]
        assert "config" not in props

    def test_tool_schema_has_name_field(self):
        tool = _tool_by_name("add_place")
        props = tool.args_schema.model_json_schema()["properties"]
        assert "name" in props


@pytest.mark.unit
class TestAddPlaceSuccess:
    async def test_minimal_call_returns_added_message_with_id(self):
        from bson import ObjectId

        inserted_doc = {"_id": ObjectId("507f1f77bcf86cd799439011"), "name": "My Cafe", "skipped": False}

        with patch("src.orchestrator.tools.insert_place", new=AsyncMock(return_value=inserted_doc)):
            result = await _tool_by_name("add_place").ainvoke({"name": "My Cafe"})

        assert "Added" in result
        assert "My Cafe" in result
        assert "507f1f77bcf86cd799439011" in result

    async def test_full_call_passes_all_fields_to_insert(self):
        from bson import ObjectId

        inserted_doc = {"_id": ObjectId("507f1f77bcf86cd799439011"), "name": "Rynek Główny", "skipped": False}

        with patch("src.orchestrator.tools.insert_place", new=AsyncMock(return_value=inserted_doc)) as mock_insert:
            await _tool_by_name("add_place").ainvoke(
                {
                    "name": "Rynek Główny",
                    "address": "Rynek Główny, Kraków",
                    "lat": 50.0617,
                    "lng": 19.9373,
                    "visit_duration_min": 60,
                    "preferred_hour_from": 9,
                    "preferred_hour_to": 17,
                }
            )

        _, called_place = mock_insert.call_args[0]
        assert called_place.name == "Rynek Główny"
        assert called_place.lat == 50.0617
        assert called_place.visit_duration_min == 60


@pytest.mark.unit
class TestAddPlaceErrors:
    async def test_invalid_hour_returns_validation_error(self):
        with patch("src.orchestrator.tools.insert_place", new=AsyncMock()) as mock_insert:
            result = await _tool_by_name("add_place").ainvoke({"name": "Test Place", "preferred_hour_from": 25})

        assert "Invalid" in result
        mock_insert.assert_not_called()

    async def test_inverted_hour_range_returns_validation_error(self):
        with patch("src.orchestrator.tools.insert_place", new=AsyncMock()) as mock_insert:
            result = await _tool_by_name("add_place").ainvoke(
                {"name": "Test Place", "preferred_hour_from": 18, "preferred_hour_to": 9}
            )

        assert "Invalid" in result
        mock_insert.assert_not_called()

    async def test_db_exception_returns_error_string(self):
        with patch("src.orchestrator.tools.insert_place", new=AsyncMock(side_effect=Exception("write error"))):
            result = await _tool_by_name("add_place").ainvoke({"name": "Test Place"})

        assert "Failed" in result


@pytest.mark.unit
class TestSearchPlaceConditional:
    def test_search_place_not_in_tools_without_places_manager(self):
        tools = create_tools(MagicMock())
        names = [t.name for t in tools]
        assert "search_place" not in names

    def test_search_place_in_tools_with_places_manager(self):
        tools = create_tools(MagicMock(), MagicMock())
        names = [t.name for t in tools]
        assert "search_place" in names


@pytest.mark.unit
class TestSearchPlaceMetadata:
    def test_tool_has_expected_name(self):
        tool = _tool_by_name("search_place", places_manager=MagicMock())
        assert tool.name == "search_place"

    def test_tool_schema_config_not_exposed_to_llm(self):
        tool = _tool_by_name("search_place", places_manager=MagicMock())
        props = tool.args_schema.model_json_schema()["properties"]
        assert "config" not in props


@pytest.mark.unit
class TestSearchPlaceSuccess:
    async def test_found_place_returns_details_string(self):
        places_manager = MagicMock()
        places_manager.search_place_id = AsyncMock(return_value=("ChIabc123", "OK", None))
        places_manager.fetch_place_details = AsyncMock(
            return_value=(
                {
                    "displayName": {"text": "Wawel Castle"},
                    "formattedAddress": "Wawel 5, 31-001 Kraków",
                    "location": {"latitude": 50.0547, "longitude": 19.9354},
                },
                "OK",
                None,
            )
        )

        result = await _tool_by_name("search_place", places_manager=places_manager).ainvoke(
            {"query": "Wawel Castle Krakow"}
        )

        assert "Wawel Castle" in result
        assert "Kraków" in result
        assert "ChIabc123" in result

    async def test_not_found_returns_not_found_message(self):
        places_manager = MagicMock()
        places_manager.search_place_id = AsyncMock(return_value=(None, "NOT_FOUND", None))

        result = await _tool_by_name("search_place", places_manager=places_manager).ainvoke(
            {"query": "Nonexistent Place XYZ"}
        )

        assert "No place found" in result

    async def test_api_error_returns_error_string(self):
        places_manager = MagicMock()
        places_manager.search_place_id = AsyncMock(return_value=(None, "REQUEST_DENIED", "API key invalid"))

        result = await _tool_by_name("search_place", places_manager=places_manager).ainvoke({"query": "Some Place"})

        assert "Search failed" in result
        assert "API key invalid" in result


def _make_pricing_manager(payload=None, search_result=("ChIabc123", "OK", None)):
    places_manager = MagicMock()
    places_manager.search_place_id = AsyncMock(return_value=search_result)
    places_manager.fetch_place_details = AsyncMock(return_value=(payload, "OK" if payload else "NOT_FOUND", None))
    return places_manager


@pytest.mark.unit
class TestGetPlacePricingConditional:
    def test_not_in_tools_without_places_manager(self):
        tools = create_tools(MagicMock())
        names = [t.name for t in tools]
        assert "get_place_pricing" not in names

    def test_in_tools_with_places_manager(self):
        tools = create_tools(MagicMock(), MagicMock())
        names = [t.name for t in tools]
        assert "get_place_pricing" in names


@pytest.mark.unit
class TestGetPlacePricingMetadata:
    def test_tool_has_expected_name(self):
        tool = _tool_by_name("get_place_pricing", places_manager=MagicMock())
        assert tool.name == "get_place_pricing"

    def test_tool_has_non_empty_description(self):
        tool = _tool_by_name("get_place_pricing", places_manager=MagicMock())
        assert tool.description and len(tool.description) > 10

    def test_tool_schema_has_id_and_query_fields(self):
        tool = _tool_by_name("get_place_pricing", places_manager=MagicMock())
        props = tool.args_schema.model_json_schema()["properties"]
        assert "gmaps_place_id" in props
        assert "query" in props
        assert "lat" in props
        assert "lng" in props


@pytest.mark.unit
class TestGetPlacePricingSuccess:
    async def test_direct_place_id_skips_search(self):
        payload = {"displayName": {"text": "Magia Cafe"}, "priceLevel": "PRICE_LEVEL_MODERATE"}
        places_manager = _make_pricing_manager(payload)

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke(
            {"gmaps_place_id": "ChIabc123"}
        )

        places_manager.search_place_id.assert_not_called()
        places_manager.fetch_place_details.assert_called_once_with("ChIabc123", fields=PRICING_FIELD_MASK)
        assert "Magia Cafe" in result

    async def test_query_resolves_via_search(self):
        payload = {"displayName": {"text": "Magia Cafe"}, "priceLevel": "PRICE_LEVEL_INEXPENSIVE"}
        places_manager = _make_pricing_manager(payload)

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke(
            {"query": "Magia Cafe Krakow"}
        )

        places_manager.search_place_id.assert_called_once_with("Magia Cafe Krakow", None, None)
        places_manager.fetch_place_details.assert_called_once_with("ChIabc123", fields=PRICING_FIELD_MASK)
        assert "inexpensive" in result

    async def test_full_payload_formats_all_sections(self):
        payload = {
            "displayName": {"text": "Magia Cafe"},
            "priceLevel": "PRICE_LEVEL_MODERATE",
            "priceRange": {
                "startPrice": {"units": "20", "currencyCode": "PLN"},
                "endPrice": {"units": "40", "currencyCode": "PLN"},
            },
            "websiteUri": "https://magiacafe.pl",
            "editorialSummary": {"text": "Cozy cafe near the main square."},
            "servesCoffee": True,
            "servesBreakfast": True,
            "servesBeer": False,
        }
        places_manager = _make_pricing_manager(payload)

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke(
            {"gmaps_place_id": "ChIabc123"}
        )

        assert "moderate" in result
        assert "$$" in result
        assert "20 PLN" in result
        assert "40 PLN" in result
        assert "https://magiacafe.pl" in result
        assert "Cozy cafe near the main square." in result
        assert "coffee" in result
        assert "breakfast" in result
        assert "beer" not in result

    async def test_price_range_without_end_price(self):
        payload = {
            "displayName": {"text": "Magia Cafe"},
            "priceRange": {"startPrice": {"units": "20", "currencyCode": "PLN"}},
        }
        places_manager = _make_pricing_manager(payload)

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke(
            {"gmaps_place_id": "ChIabc123"}
        )

        assert "from 20 PLN" in result

    async def test_price_range_with_fractional_nanos(self):
        payload = {
            "displayName": {"text": "Magia Cafe"},
            "priceRange": {
                "startPrice": {"units": "20", "nanos": 500000000, "currencyCode": "PLN"},
                "endPrice": {"units": "40", "currencyCode": "PLN"},
            },
        }
        places_manager = _make_pricing_manager(payload)

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke(
            {"gmaps_place_id": "ChIabc123"}
        )

        assert "20.5 PLN–40 PLN" in result

    async def test_no_pricing_data_with_website_suggests_website(self):
        payload = {"displayName": {"text": "Magia Cafe"}, "websiteUri": "https://magiacafe.pl"}
        places_manager = _make_pricing_manager(payload)

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke(
            {"gmaps_place_id": "ChIabc123"}
        )

        assert "no pricing data" in result
        assert "https://magiacafe.pl" in result

    async def test_no_pricing_data_without_website(self):
        payload = {"displayName": {"text": "Magia Cafe"}}
        places_manager = _make_pricing_manager(payload)

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke(
            {"gmaps_place_id": "ChIabc123"}
        )

        assert "no pricing data" in result
        assert "Magia Cafe" in result


@pytest.mark.unit
class TestGetPlacePricingErrors:
    async def test_no_id_and_no_query_returns_guidance(self):
        places_manager = _make_pricing_manager()

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke({})

        assert "Provide either" in result
        places_manager.search_place_id.assert_not_called()
        places_manager.fetch_place_details.assert_not_called()

    async def test_search_not_found_returns_message(self):
        places_manager = _make_pricing_manager(search_result=(None, "NOT_FOUND", None))

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke(
            {"query": "Nonexistent Place XYZ"}
        )

        assert "No place found" in result

    async def test_missing_api_key_returns_message(self):
        places_manager = _make_pricing_manager(search_result=(None, "MISSING_API_KEY", None))

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke({"query": "Magia Cafe"})

        assert "API key not configured" in result

    async def test_search_api_error_returns_error_string(self):
        places_manager = _make_pricing_manager(search_result=(None, "REQUEST_DENIED", "API key invalid"))

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke({"query": "Magia Cafe"})

        assert "Search failed" in result
        assert "API key invalid" in result

    async def test_fetch_details_failure_returns_error_string(self):
        places_manager = MagicMock()
        places_manager.search_place_id = AsyncMock(return_value=("ChIabc123", "OK", None))
        places_manager.fetch_place_details = AsyncMock(return_value=(None, "HTTP_500", "boom"))

        result = await _tool_by_name("get_place_pricing", places_manager=places_manager).ainvoke({"query": "Magia Cafe"})

        assert "Could not retrieve pricing details" in result
        assert "boom" in result


def _make_trip_summary(id_="abc123", name="Test Krakow", date="2026-07-05"):
    summary = MagicMock()
    summary.id = id_
    summary.name = name
    summary.date = date
    return summary


def _make_route_step(
    name="Muzeum Przyrodnicze", place_id="pid1", arrival="09:00", departure="10:30", visit_min=90, travel_s=0
):
    step = MagicMock()
    step.name = name
    step.place_id = place_id
    step.arrival_time = time.fromisoformat(arrival)
    step.departure_time = time.fromisoformat(departure)
    step.visit_duration_min = visit_min
    step.travel_from_previous_s = travel_s
    return step


def _make_trip_detail(name="Test Krakow", date="2026-07-05", steps=None, skipped=None):
    from src.optimizer.matrix.models import TransportMode

    trip = MagicMock()
    trip.name = name
    trip.date = date
    trip.transport_mode = TransportMode.WALK
    trip.day_start_hour = 9
    trip.day_end_hour = 20
    resp = MagicMock()
    resp.steps = steps if steps is not None else [_make_route_step()]
    resp.skipped = skipped or []
    resp.total_travel_time_s = 540
    resp.total_visit_time_min = 90
    resp.total_wait_min = 0
    trip.optimizer_response = resp
    return trip


@pytest.mark.unit
class TestListSavedTripsMetadata:
    def test_tool_has_expected_name(self):
        tool = _tool_by_name("list_saved_trips")
        assert tool.name == "list_saved_trips"

    def test_tool_has_non_empty_description(self):
        tool = _tool_by_name("list_saved_trips")
        assert tool.description and len(tool.description) > 10


@pytest.mark.unit
class TestListSavedTripsSuccess:
    async def test_returns_formatted_list_when_trips_exist(self):
        trips = [_make_trip_summary("abc", "Test Krakow", "2026-07-05"), _make_trip_summary("def", "Warsaw", "2026-07-10")]

        with patch("src.orchestrator.tools.TripsManager") as MockManager:
            MockManager.return_value.list_all = AsyncMock(return_value=trips)
            result = await _tool_by_name("list_saved_trips").ainvoke({})

        assert "Test Krakow" in result
        assert "Warsaw" in result
        assert "abc" in result
        assert "def" in result

    async def test_returns_no_trips_message_when_empty(self):
        with patch("src.orchestrator.tools.TripsManager") as MockManager:
            MockManager.return_value.list_all = AsyncMock(return_value=[])
            result = await _tool_by_name("list_saved_trips").ainvoke({})

        assert "No saved trips found" in result


@pytest.mark.unit
class TestListSavedTripsErrors:
    async def test_db_exception_returns_error_string(self):
        with patch("src.orchestrator.tools.TripsManager") as MockManager:
            MockManager.return_value.list_all = AsyncMock(side_effect=Exception("connection lost"))
            result = await _tool_by_name("list_saved_trips").ainvoke({})

        assert "Failed to retrieve trips" in result
        assert "connection lost" in result


@pytest.mark.unit
class TestGetTripDetailsMetadata:
    def test_tool_has_expected_name(self):
        tool = _tool_by_name("get_trip_details")
        assert tool.name == "get_trip_details"

    def test_tool_has_non_empty_description(self):
        tool = _tool_by_name("get_trip_details")
        assert tool.description and len(tool.description) > 10

    def test_tool_schema_has_trip_id_field(self):
        tool = _tool_by_name("get_trip_details")
        props = tool.args_schema.model_json_schema()["properties"]
        assert "trip_id" in props


@pytest.mark.unit
class TestGetTripDetailsSuccess:
    async def test_returns_header_and_place_list_for_valid_trip(self):
        trip = _make_trip_detail()

        with patch("src.orchestrator.tools.TripsManager") as MockManager:
            MockManager.return_value.find_by_id = AsyncMock(return_value=trip)
            result = await _tool_by_name("get_trip_details").ainvoke({"trip_id": "abc123"})

        assert "Test Krakow" in result
        assert "Muzeum Przyrodnicze" in result
        assert "09:00" in result
        assert "10:30" in result
        assert "90 min visit" in result

    async def test_includes_travel_time_for_subsequent_steps(self):
        steps = [
            _make_route_step("Place A", travel_s=0),
            _make_route_step("Place B", travel_s=600),
        ]
        trip = _make_trip_detail(steps=steps)

        with patch("src.orchestrator.tools.TripsManager") as MockManager:
            MockManager.return_value.find_by_id = AsyncMock(return_value=trip)
            result = await _tool_by_name("get_trip_details").ainvoke({"trip_id": "abc123"})

        assert "10 min travel" in result

    async def test_formats_skipped_places(self):
        skipped = MagicMock()
        skipped.name = "Skipped Place"
        skipped.place_id = "skip1"
        trip = _make_trip_detail(skipped=[skipped])

        with patch("src.orchestrator.tools.TripsManager") as MockManager:
            MockManager.return_value.find_by_id = AsyncMock(return_value=trip)
            result = await _tool_by_name("get_trip_details").ainvoke({"trip_id": "abc123"})

        assert "Skipped Place" in result

    async def test_no_places_in_route_message(self):
        trip = _make_trip_detail(steps=[])

        with patch("src.orchestrator.tools.TripsManager") as MockManager:
            MockManager.return_value.find_by_id = AsyncMock(return_value=trip)
            result = await _tool_by_name("get_trip_details").ainvoke({"trip_id": "abc123"})

        assert "No places in route" in result

    async def test_includes_summary_totals(self):
        trip = _make_trip_detail()

        with patch("src.orchestrator.tools.TripsManager") as MockManager:
            MockManager.return_value.find_by_id = AsyncMock(return_value=trip)
            result = await _tool_by_name("get_trip_details").ainvoke({"trip_id": "abc123"})

        assert "Total:" in result
        assert "min travel" in result
        assert "min visits" in result


@pytest.mark.unit
class TestGetTripDetailsErrors:
    async def test_not_found_returns_not_found_message(self):
        with patch("src.orchestrator.tools.TripsManager") as MockManager:
            MockManager.return_value.find_by_id = AsyncMock(return_value=None)
            result = await _tool_by_name("get_trip_details").ainvoke({"trip_id": "abc123"})

        assert "not found" in result.lower()

    async def test_db_exception_returns_error_string(self):
        with patch("src.orchestrator.tools.TripsManager") as MockManager:
            MockManager.return_value.find_by_id = AsyncMock(side_effect=Exception("timeout"))
            result = await _tool_by_name("get_trip_details").ainvoke({"trip_id": "abc123"})

        assert "Failed to retrieve trip" in result
        assert "timeout" in result
