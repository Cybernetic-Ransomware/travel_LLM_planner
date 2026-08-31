from datetime import UTC, datetime

import pytest
from bson import ObjectId
from pydantic import ValidationError

from src.core.exceptions import (
    MissingExpectedRevisionError,
    TripConcurrencyConflictError,
    TripPlanTypeConflictError,
)
from src.trips.manager import _LIST_PROJECTION, TRIPS_COLLECTION, TripsManager
from src.trips.models import MultiDaySaveTripRequest, SingleDaySaveTripRequest


def _single_day_payload() -> dict:
    return {
        "name": "Weekend in Kraków",
        "date": "2026-07-04",
        "optimizer_request": {
            "place_ids": ["p1", "p2"],
            "transport_mode": "WALK",
            "day_start_hour": 9,
            "day_end_hour": 21,
        },
        "optimizer_response": {
            "steps": [],
            "total_travel_time_s": 0,
            "total_visit_time_min": 0,
            "total_wait_min": 0,
            "transport_mode": "WALK",
            "skipped": [],
        },
    }


def _multi_day_payload() -> dict:
    return {
        "name": "Kraków then Warsaw",
        "multi_day_request": {
            "days": [
                {"date": "2026-07-01"},
                {"date": "2026-07-02"},
                {"date": "2026-07-03"},
            ],
            "places": [
                {"place_id": "p1", "day_preferences": []},
                {"place_id": "p2", "day_preferences": []},
            ],
            "transport_mode": "WALK",
            "accommodations": [
                {
                    "name": "Hotel A",
                    "lat": 50.06,
                    "lng": 19.94,
                    "check_in_date": "2026-07-01",
                    "check_out_date": "2026-07-03",
                },
                {
                    "name": "Hotel B",
                    "lat": 50.08,
                    "lng": 19.90,
                    "check_in_date": "2026-07-03",
                    "check_out_date": "2026-07-05",
                },
            ],
            "transfers": [
                {
                    "date": "2026-07-03",
                    "departure_time": "11:00:00",
                    "arrival_time": "13:00:00",
                    "label": "Train to Hotel B",
                }
            ],
        },
        "multi_day_response": {
            "days": [
                {
                    "day_index": 0,
                    "date": "2026-07-01",
                    "steps": [],
                    "total_travel_time_s": 0,
                    "total_visit_time_min": 0,
                    "total_wait_min": 0,
                    "skipped": [],
                },
                {
                    "day_index": 1,
                    "date": "2026-07-02",
                    "steps": [],
                    "total_travel_time_s": 0,
                    "total_visit_time_min": 0,
                    "total_wait_min": 0,
                    "skipped": [],
                },
                {
                    "day_index": 2,
                    "date": "2026-07-03",
                    "steps": [],
                    "total_travel_time_s": 0,
                    "total_visit_time_min": 0,
                    "total_wait_min": 0,
                    "skipped": [],
                },
            ],
            "transport_mode": "WALK",
            "unassigned": [],
        },
    }


@pytest.fixture(autouse=True)
async def clean_trips(test_db):
    yield
    await test_db[TRIPS_COLLECTION].delete_many({})


@pytest.mark.integration
class TestLegacyDocumentInference:
    async def test_find_by_id_infers_single_day(self, test_db):
        doc = {**_single_day_payload(), "created_at": datetime.now(UTC)}
        result = await test_db[TRIPS_COLLECTION].insert_one(doc)
        manager = TripsManager(test_db)

        trip = await manager.find_by_id(str(result.inserted_id))

        assert trip is not None
        assert trip.plan_type == "SINGLE_DAY"

    async def test_list_all_infers_single_day(self, test_db):
        doc = {**_single_day_payload(), "created_at": datetime.now(UTC)}
        await test_db[TRIPS_COLLECTION].insert_one(doc)
        manager = TripsManager(test_db)

        trips = await manager.list_all()

        assert len(trips) == 1
        assert trips[0].plan_type == "SINGLE_DAY"


@pytest.mark.integration
class TestListAllStaysCheapForMultiDay:
    async def test_list_all_succeeds_despite_invalid_nested_accommodation(self, test_db):
        payload = _multi_day_payload()
        payload["multi_day_request"]["accommodations"][1]["check_out_date"] = "2026-07-02"
        doc = {**payload, "plan_type": "MULTI_DAY", "created_at": datetime.now(UTC)}
        result = await test_db[TRIPS_COLLECTION].insert_one(doc)
        manager = TripsManager(test_db)

        trips = await manager.list_all()
        assert len(trips) == 1
        assert trips[0].plan_type == "MULTI_DAY"
        assert trips[0].start_date == "2026-07-01"
        assert trips[0].end_date == "2026-07-03"

        with pytest.raises(ValidationError):
            await manager.find_by_id(str(result.inserted_id))

    async def test_list_projection_excludes_full_multi_day_payload(self, test_db):
        payload = _multi_day_payload()
        doc = {**payload, "plan_type": "MULTI_DAY", "created_at": datetime.now(UTC)}
        await test_db[TRIPS_COLLECTION].insert_one(doc)

        raw = await test_db[TRIPS_COLLECTION].find_one({}, _LIST_PROJECTION)

        assert "multi_day_response" not in raw
        assert "accommodations" not in raw["multi_day_request"]
        assert "transfers" not in raw["multi_day_request"]
        assert all(set(d.keys()) == {"date"} for d in raw["multi_day_request"]["days"])


@pytest.mark.integration
class TestUpdatePlanTypeProtection:
    async def test_single_to_multi_raises_conflict(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(SingleDaySaveTripRequest(**_single_day_payload()))

        with pytest.raises(TripPlanTypeConflictError):
            await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload(), expected_revision=0))

    async def test_multi_to_single_raises_conflict(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(MultiDaySaveTripRequest(**_multi_day_payload()))

        with pytest.raises(TripPlanTypeConflictError):
            await manager.update(saved.id, SingleDaySaveTripRequest(**_single_day_payload(), expected_revision=0))

    async def test_conflict_leaves_document_unchanged(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(SingleDaySaveTripRequest(**_single_day_payload()))
        before = await test_db[TRIPS_COLLECTION].find_one({"_id": ObjectId(saved.id)})

        with pytest.raises(TripPlanTypeConflictError):
            await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload(), expected_revision=0))

        after = await test_db[TRIPS_COLLECTION].find_one({"_id": ObjectId(saved.id)})
        assert before == after

    async def test_update_valid_but_nonexistent_id_returns_none(self, test_db):
        manager = TripsManager(test_db)

        result = await manager.update(
            str(ObjectId()), SingleDaySaveTripRequest(**_single_day_payload(), expected_revision=0)
        )

        assert result is None


@pytest.mark.integration
class TestOptimisticConcurrency:
    async def test_save_starts_at_revision_zero_without_token_in_doc(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(MultiDaySaveTripRequest(**_multi_day_payload(), expected_revision=99))

        assert saved.revision == 0
        raw = await test_db[TRIPS_COLLECTION].find_one({"_id": ObjectId(saved.id)})
        assert raw["revision"] == 0
        assert "expected_revision" not in raw

    async def test_update_without_expected_revision_raises_428(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(MultiDaySaveTripRequest(**_multi_day_payload()))

        with pytest.raises(MissingExpectedRevisionError):
            await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload()))

    async def test_update_with_matching_revision_increments_and_preserves_created_at(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(MultiDaySaveTripRequest(**_multi_day_payload()))
        before = await test_db[TRIPS_COLLECTION].find_one({"_id": ObjectId(saved.id)})

        updated = await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload(), expected_revision=0))

        assert updated.revision == 1
        after = await test_db[TRIPS_COLLECTION].find_one({"_id": ObjectId(saved.id)})
        assert after["created_at"] == before["created_at"]
        assert after["updated_at"] is not None
        assert "expected_revision" not in after

    async def test_update_with_stale_revision_raises_409_and_leaves_doc_untouched(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(MultiDaySaveTripRequest(**_multi_day_payload()))
        await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload(), expected_revision=0))
        before = await test_db[TRIPS_COLLECTION].find_one({"_id": ObjectId(saved.id)})

        with pytest.raises(TripConcurrencyConflictError):
            await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload(), expected_revision=0))

        after = await test_db[TRIPS_COLLECTION].find_one({"_id": ObjectId(saved.id)})
        assert before == after

    async def test_legacy_doc_without_revision_accepts_expected_zero(self, test_db):
        doc = {**_multi_day_payload(), "plan_type": "MULTI_DAY", "created_at": datetime.now(UTC)}
        result = await test_db[TRIPS_COLLECTION].insert_one(doc)
        manager = TripsManager(test_db)

        updated = await manager.update(
            str(result.inserted_id), MultiDaySaveTripRequest(**_multi_day_payload(), expected_revision=0)
        )

        assert updated.revision == 1

    async def test_direction_a_two_updates_same_token_second_conflicts(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(MultiDaySaveTripRequest(**_multi_day_payload()))

        await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload(), expected_revision=0))
        with pytest.raises(TripConcurrencyConflictError):
            await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload(), expected_revision=0))

    async def test_direction_b_ui_put_after_chat_edit_conflicts(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(MultiDaySaveTripRequest(**_multi_day_payload()))

        # chat editor writes first, moving revision 0 -> 1
        chat_payload = _multi_day_payload()
        chat_payload["name"] = "Renamed by chat"
        await manager.update(saved.id, MultiDaySaveTripRequest(**chat_payload, expected_revision=0))

        # stale UI PUT still holding revision 0
        with pytest.raises(TripConcurrencyConflictError):
            await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload(), expected_revision=0))

        current = await manager.find_by_id(saved.id)
        assert current.name == "Renamed by chat"
        assert current.revision == 1
