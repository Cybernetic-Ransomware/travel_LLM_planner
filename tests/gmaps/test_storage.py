"""Integration tests for gmaps storage functions — require MongoDB testcontainer."""

import pytest
import pendulum
from bson import ObjectId

from src.core.db.manager import GMAPS_COLLECTION
from src.gmaps.models import PlaceOut, PlacePatch
from src.gmaps.storage import (
    delete_place,
    fetch_enrichment_candidates,
    fetch_place_by_id,
    fetch_places,
    find_and_update_place,
)


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

    async def test_sets_priority(self, test_db, sample_place):
        doc = await find_and_update_place(test_db, sample_place, PlacePatch(priority="must_see"))
        assert doc is not None
        assert doc["priority"] == "must_see"

    async def test_explicit_null_unsets_field(self, test_db, sample_place):
        await find_and_update_place(
            test_db, sample_place, PlacePatch(preferred_hour_from=9, preferred_hour_to=17, visit_duration_min=60)
        )
        doc = await find_and_update_place(test_db, sample_place, PlacePatch(preferred_hour_from=None))
        assert doc is not None
        assert "preferred_hour_from" not in doc
        assert doc["preferred_hour_to"] == 17
        assert doc["visit_duration_min"] == 60

    async def test_omitted_fields_left_unchanged(self, test_db, sample_place):
        await find_and_update_place(test_db, sample_place, PlacePatch(preferred_hour_from=9, preferred_hour_to=17))
        doc = await find_and_update_place(test_db, sample_place, PlacePatch(visit_duration_min=60))
        assert doc is not None
        assert doc["preferred_hour_from"] == 9
        assert doc["preferred_hour_to"] == 17
        assert doc["visit_duration_min"] == 60

    async def test_null_priority_unsets_and_reads_back_as_normal(self, test_db, sample_place):
        await find_and_update_place(test_db, sample_place, PlacePatch(priority="optional"))
        doc = await find_and_update_place(test_db, sample_place, PlacePatch(priority=None))
        assert doc is not None
        assert "priority" not in doc
        assert PlaceOut.model_validate(doc).priority == "normal"

    async def test_mixed_set_and_unset_in_one_call(self, test_db, sample_place):
        await find_and_update_place(test_db, sample_place, PlacePatch(preferred_hour_to=17))
        doc = await find_and_update_place(
            test_db, sample_place, PlacePatch(visit_duration_min=45, preferred_hour_to=None)
        )
        assert doc is not None
        assert doc["visit_duration_min"] == 45
        assert "preferred_hour_to" not in doc


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


@pytest.mark.integration
class TestFetchEnrichmentCandidates:
    async def test_empty_collection(self, test_db):
        result = await fetch_enrichment_candidates(test_db, limit=10)
        assert result == []

    async def test_never_attempted_returned_before_stale(self, test_db):
        now = pendulum.now("UTC")
        await test_db[GMAPS_COLLECTION].insert_many([
            {
                "name": "Stale", "gmaps_place_id": "ChIStale", "address": None,
                "enriched_at": now.subtract(hours=48), "details_status": "OK",
            },
            {
                "name": "Fresh", "gmaps_place_id": "ChIFresh", "address": None,
                "enriched_at": None, "details_status": None,
            },
        ])
        result = await fetch_enrichment_candidates(test_db, limit=2)
        assert len(result) == 2
        assert result[0]["name"] == "Fresh"
        assert result[1]["name"] == "Stale"

    async def test_recent_failure_excluded(self, test_db):
        now = pendulum.now("UTC")
        await test_db[GMAPS_COLLECTION].insert_many([
            {
                "name": "A", "gmaps_place_id": "ChIA", "address": None,
                "enriched_at": now.subtract(hours=1), "details_status": "NOT_FOUND",
            },
            {
                "name": "B", "gmaps_place_id": "ChIB", "address": None,
                "enriched_at": now.subtract(hours=1), "details_status": "HTTP_404",
            },
        ])
        result = await fetch_enrichment_candidates(test_db, limit=10)
        assert result == []

    async def test_backoff_expires_after_24h(self, test_db):
        now = pendulum.now("UTC")
        await test_db[GMAPS_COLLECTION].insert_one({
            "name": "OldFail", "gmaps_place_id": "ChIOld", "address": None,
            "enriched_at": now.subtract(hours=25), "details_status": "NOT_FOUND",
        })
        result = await fetch_enrichment_candidates(test_db, limit=10)
        assert len(result) == 1

    async def test_recent_ok_not_excluded(self, test_db):
        now = pendulum.now("UTC")
        await test_db[GMAPS_COLLECTION].insert_one({
            "name": "OkPlace", "gmaps_place_id": "ChIOk", "address": None,
            "enriched_at": now.subtract(hours=1), "details_status": "OK",
        })
        result = await fetch_enrichment_candidates(test_db, limit=10)
        assert len(result) == 1

    async def test_tier1_sorted_by_enriched_at_asc(self, test_db):
        now = pendulum.now("UTC")
        await test_db[GMAPS_COLLECTION].insert_many([
            {
                "name": "C", "gmaps_place_id": "ChIC", "address": None,
                "enriched_at": now.subtract(hours=36), "details_status": "NOT_FOUND",
            },
            {
                "name": "A", "gmaps_place_id": "ChIA", "address": None,
                "enriched_at": now.subtract(hours=72), "details_status": "NOT_FOUND",
            },
            {
                "name": "B", "gmaps_place_id": "ChIB", "address": None,
                "enriched_at": now.subtract(hours=48), "details_status": "NOT_FOUND",
            },
        ])
        result = await fetch_enrichment_candidates(test_db, limit=3)
        assert [r["name"] for r in result] == ["A", "B", "C"]

    async def test_places_with_address_excluded(self, test_db):
        await test_db[GMAPS_COLLECTION].insert_many([
            {"name": "HasAddress", "gmaps_place_id": "ChIHas", "address": "ul. Testowa 1",
             "enriched_at": None},
            {"name": "NoAddress", "gmaps_place_id": "ChINo", "address": None,
             "enriched_at": None},
        ])
        result = await fetch_enrichment_candidates(test_db, limit=10)
        assert len(result) == 1
        assert result[0]["name"] == "NoAddress"

    async def test_null_place_id_excluded(self, test_db):
        await test_db[GMAPS_COLLECTION].insert_many([
            {"name": "NullId", "gmaps_place_id": None, "address": None, "enriched_at": None},
            {"name": "HasId", "gmaps_place_id": "ChIHas", "address": None, "enriched_at": None},
        ])
        result = await fetch_enrichment_candidates(test_db, limit=10)
        assert len(result) == 1
        assert result[0]["name"] == "HasId"

    async def test_limit_respected(self, test_db):
        await test_db[GMAPS_COLLECTION].insert_many([
            {"name": f"P{i}", "gmaps_place_id": f"ChI{i}", "address": None, "enriched_at": None}
            for i in range(5)
        ])
        result = await fetch_enrichment_candidates(test_db, limit=3)
        assert len(result) == 3
