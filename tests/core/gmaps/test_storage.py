"""Integration tests for gmaps storage functions — require MongoDB testcontainer."""

import pytest
from bson import ObjectId

from src.core.db.manager import GMAPS_COLLECTION
from src.core.gmaps.models import PlacePatch
from src.core.gmaps.storage import delete_place, fetch_place_by_id, fetch_places, find_and_update_place


@pytest.fixture(autouse=True)
async def clean_collection(test_db):
    yield
    await test_db[GMAPS_COLLECTION].delete_many({})


@pytest.fixture
async def sample_place(test_db):
    result = await test_db[GMAPS_COLLECTION].insert_one(
        {"name": "Test Place", "address": "ul. Testowa 1", "skipped": False, "list_name": "Warsaw"}
    )
    return str(result.inserted_id)


@pytest.mark.integration
class TestFetchPlaces:
    async def test_returns_all(self, test_db, sample_place):
        docs = await fetch_places(test_db)
        assert len(docs) == 1

    async def test_empty_collection(self, test_db):
        docs = await fetch_places(test_db)
        assert docs == []

    async def test_filter_skipped_true(self, test_db):
        await test_db[GMAPS_COLLECTION].insert_many(
            [
                {"name": "A", "skipped": True},
                {"name": "B", "skipped": False},
            ]
        )
        docs = await fetch_places(test_db, skipped=True)
        assert len(docs) == 1
        assert docs[0]["name"] == "A"

    async def test_filter_skipped_false(self, test_db):
        await test_db[GMAPS_COLLECTION].insert_many(
            [
                {"name": "A", "skipped": True},
                {"name": "B", "skipped": False},
            ]
        )
        docs = await fetch_places(test_db, skipped=False)
        assert len(docs) == 1
        assert docs[0]["name"] == "B"

    async def test_filter_list_name(self, test_db):
        await test_db[GMAPS_COLLECTION].insert_many(
            [
                {"name": "A", "list_name": "Warsaw"},
                {"name": "B", "list_name": "Krakow"},
            ]
        )
        docs = await fetch_places(test_db, list_name="Warsaw")
        assert len(docs) == 1
        assert docs[0]["name"] == "A"

    async def test_filter_no_match(self, test_db, sample_place):
        docs = await fetch_places(test_db, list_name="Nonexistent")
        assert docs == []


@pytest.mark.integration
class TestFetchPlaceById:
    async def test_found(self, test_db, sample_place):
        doc = await fetch_place_by_id(test_db, sample_place)
        assert doc is not None
        assert str(doc["_id"]) == sample_place
        assert doc["name"] == "Test Place"

    async def test_not_found(self, test_db):
        doc = await fetch_place_by_id(test_db, str(ObjectId()))
        assert doc is None

    async def test_invalid_id_returns_none(self, test_db):
        doc = await fetch_place_by_id(test_db, "not-a-valid-id")
        assert doc is None


@pytest.mark.integration
class TestFindAndUpdatePlace:
    async def test_updates_fields(self, test_db, sample_place):
        patch = PlacePatch(preferred_hour_from=9, preferred_hour_to=17, visit_duration_min=60)
        doc = await find_and_update_place(test_db, sample_place, patch)
        assert doc is not None
        assert doc["preferred_hour_from"] == 9
        assert doc["preferred_hour_to"] == 17
        assert doc["visit_duration_min"] == 60

    async def test_partial_patch(self, test_db, sample_place):
        doc = await find_and_update_place(test_db, sample_place, PlacePatch(skipped=True))
        assert doc is not None
        assert doc["skipped"] is True
        assert doc["name"] == "Test Place"

    async def test_empty_patch_returns_existing_doc(self, test_db, sample_place):
        doc = await find_and_update_place(test_db, sample_place, PlacePatch())
        assert doc is not None
        assert doc["name"] == "Test Place"

    async def test_not_found_returns_none(self, test_db):
        doc = await find_and_update_place(test_db, str(ObjectId()), PlacePatch(skipped=True))
        assert doc is None

    async def test_invalid_id_returns_none(self, test_db):
        doc = await find_and_update_place(test_db, "bad-id", PlacePatch(skipped=True))
        assert doc is None


@pytest.mark.integration
class TestDeletePlace:
    async def test_deletes_existing(self, test_db, sample_place):
        deleted = await delete_place(test_db, sample_place)
        assert deleted is True
        doc = await test_db[GMAPS_COLLECTION].find_one({"_id": ObjectId(sample_place)})
        assert doc is None

    async def test_not_found_returns_false(self, test_db):
        deleted = await delete_place(test_db, str(ObjectId()))
        assert deleted is False

    async def test_invalid_id_returns_false(self, test_db):
        deleted = await delete_place(test_db, "bad-id")
        assert deleted is False
