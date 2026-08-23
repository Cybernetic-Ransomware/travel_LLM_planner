from datetime import UTC, datetime

import pytest
from bson import ObjectId
from pydantic import ValidationError

from src.core.exceptions import TripPlanTypeConflictError
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
            await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload()))

    async def test_multi_to_single_raises_conflict(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(MultiDaySaveTripRequest(**_multi_day_payload()))

        with pytest.raises(TripPlanTypeConflictError):
            await manager.update(saved.id, SingleDaySaveTripRequest(**_single_day_payload()))

    async def test_conflict_leaves_document_unchanged(self, test_db):
        manager = TripsManager(test_db)
        saved = await manager.save(SingleDaySaveTripRequest(**_single_day_payload()))
        before = await test_db[TRIPS_COLLECTION].find_one({"_id": ObjectId(saved.id)})

        with pytest.raises(TripPlanTypeConflictError):
            await manager.update(saved.id, MultiDaySaveTripRequest(**_multi_day_payload()))

        after = await test_db[TRIPS_COLLECTION].find_one({"_id": ObjectId(saved.id)})
        assert before == after

    async def test_update_valid_but_nonexistent_id_returns_none(self, test_db):
        manager = TripsManager(test_db)

        result = await manager.update(str(ObjectId()), SingleDaySaveTripRequest(**_single_day_payload()))

        assert result is None
