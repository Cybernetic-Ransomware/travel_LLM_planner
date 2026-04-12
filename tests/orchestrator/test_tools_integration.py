"""Integration tests for the update_visit_hours tool — require MongoDB testcontainer."""

import pytest
from bson import ObjectId

from src.core.db.manager import GMAPS_COLLECTION
from src.orchestrator.tools import create_tools


@pytest.fixture(autouse=True)
async def clean_collection(test_db):
    yield
    await test_db[GMAPS_COLLECTION].delete_many({})


@pytest.fixture
async def sample_place(test_db):
    result = await test_db[GMAPS_COLLECTION].insert_one(
        {"name": "Wawel Castle", "address": "Wawel 5, Kraków", "skipped": False}
    )
    return str(result.inserted_id)


def _config(allowed: list[str]) -> dict:
    return {"configurable": {"allowed_place_ids": allowed}}


@pytest.mark.integration
class TestUpdateVisitHoursIntegration:
    async def test_updates_hours_persisted_in_db(self, test_db, sample_place):
        tool = create_tools(test_db)[0]
        await tool.ainvoke(
            {"place_id": sample_place, "preferred_hour_from": 9, "preferred_hour_to": 17},
            config=_config([sample_place]),
        )

        doc = await test_db[GMAPS_COLLECTION].find_one({"_id": ObjectId(sample_place)})
        assert doc["preferred_hour_from"] == 9
        assert doc["preferred_hour_to"] == 17

    async def test_partial_update_preserves_existing_fields(self, test_db, sample_place):
        tool = create_tools(test_db)[0]
        await tool.ainvoke(
            {"place_id": sample_place, "preferred_hour_from": 10, "preferred_hour_to": 18},
            config=_config([sample_place]),
        )

        doc = await test_db[GMAPS_COLLECTION].find_one({"_id": ObjectId(sample_place)})
        assert doc["name"] == "Wawel Castle"
        assert doc["address"] == "Wawel 5, Kraków"
        assert doc["preferred_hour_from"] == 10
        assert doc["preferred_hour_to"] == 18

    async def test_update_duration_persisted_in_db(self, test_db, sample_place):
        tool = create_tools(test_db)[0]
        await tool.ainvoke(
            {"place_id": sample_place, "visit_duration_min": 90},
            config=_config([sample_place]),
        )

        doc = await test_db[GMAPS_COLLECTION].find_one({"_id": ObjectId(sample_place)})
        assert doc["visit_duration_min"] == 90

    async def test_nonexistent_place_returns_not_found(self, test_db):
        tool = create_tools(test_db)[0]
        nonexistent_id = str(ObjectId())
        result = await tool.ainvoke(
            {"place_id": nonexistent_id, "preferred_hour_from": 9, "preferred_hour_to": 17},
            config=_config([nonexistent_id]),
        )

        assert "not found" in result.lower()

    async def test_scope_guard_rejects_unauthorized_place_id(self, test_db, sample_place):
        tool = create_tools(test_db)[0]
        result = await tool.ainvoke(
            {"place_id": sample_place, "preferred_hour_from": 9, "preferred_hour_to": 17},
            config=_config(["different-id-1", "different-id-2"]),
        )

        assert "not part of the current trip plan" in result
        doc = await test_db[GMAPS_COLLECTION].find_one({"_id": ObjectId(sample_place)})
        assert doc.get("preferred_hour_from") is None

    async def test_sequential_updates_apply_latest_values(self, test_db, sample_place):
        tool = create_tools(test_db)[0]
        await tool.ainvoke(
            {"place_id": sample_place, "preferred_hour_from": 9, "preferred_hour_to": 17},
            config=_config([sample_place]),
        )
        await tool.ainvoke(
            {"place_id": sample_place, "preferred_hour_from": 10, "preferred_hour_to": 18},
            config=_config([sample_place]),
        )

        doc = await test_db[GMAPS_COLLECTION].find_one({"_id": ObjectId(sample_place)})
        assert doc["preferred_hour_from"] == 10
        assert doc["preferred_hour_to"] == 18
