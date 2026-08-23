from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from src.trips.manager import TRIPS_COLLECTION

ENDPOINT = "/api/v1/core/trips"


def _payload() -> dict:
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
                {"date": "2026-08-01"},
                {"date": "2026-08-02"},
                {"date": "2026-08-03"},
            ],
            "places": [
                {"place_id": "p1", "day_preferences": []},
                {"place_id": "p2", "day_preferences": [{"day_index": 1}]},
            ],
            "transport_mode": "WALK",
            "accommodations": [
                {
                    "name": "Hotel A",
                    "lat": 50.06,
                    "lng": 19.94,
                    "check_in_date": "2026-08-01",
                    "check_out_date": "2026-08-03",
                },
                {
                    "name": "Hotel B",
                    "lat": 50.08,
                    "lng": 19.90,
                    "check_in_date": "2026-08-03",
                    "check_out_date": "2026-08-05",
                },
            ],
            "transfers": [
                {
                    "date": "2026-08-03",
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
                    "date": "2026-08-01",
                    "steps": [
                        {
                            "place_id": "p1",
                            "name": "Museum",
                            "lat": 50.061,
                            "lng": 19.941,
                            "arrival_time": "10:00:00",
                            "departure_time": "11:00:00",
                            "travel_from_previous_s": 300,
                            "visit_duration_min": 60,
                        }
                    ],
                    "total_travel_time_s": 300,
                    "total_visit_time_min": 60,
                    "total_wait_min": 0,
                    "skipped": [],
                },
                {
                    "day_index": 1,
                    "date": "2026-08-02",
                    "steps": [],
                    "total_travel_time_s": 0,
                    "total_visit_time_min": 0,
                    "total_wait_min": 0,
                    "skipped": [{"place_id": "p2", "name": "Closed Park", "reason": "TIME_WINDOW_INFEASIBLE"}],
                },
                {
                    "day_index": 2,
                    "date": "2026-08-03",
                    "steps": [],
                    "total_travel_time_s": 0,
                    "total_visit_time_min": 0,
                    "total_wait_min": 0,
                    "skipped": [],
                    "transfer": {
                        "origin": {"name": "Hotel A", "lat": 50.06, "lng": 19.94},
                        "destination": {"name": "Hotel B", "lat": 50.08, "lng": 19.90},
                        "departure_time": "11:00:00",
                        "arrival_time": "13:00:00",
                        "duration_s": 7200,
                        "label": "Train to Hotel B",
                    },
                    "route_segments": [
                        {
                            "kind": "PRE_TRANSFER",
                            "steps": [],
                            "total_travel_time_s": 0,
                            "total_visit_time_min": 0,
                            "total_wait_min": 0,
                            "skipped": [],
                        },
                        {
                            "kind": "POST_TRANSFER",
                            "steps": [],
                            "total_travel_time_s": 0,
                            "total_visit_time_min": 0,
                            "total_wait_min": 0,
                            "skipped": [],
                        },
                    ],
                },
            ],
            "transport_mode": "WALK",
            "unassigned": [{"place_id": "p3", "name": "Unreachable Cafe", "reason": "CAPACITY_EXCEEDED"}],
        },
    }


@pytest.fixture(autouse=True)
async def clean_trips(test_db):
    yield
    await test_db[TRIPS_COLLECTION].delete_many({})


@pytest.mark.integration
class TestSaveTrip:
    async def test_returns_201_with_detail(self, client: AsyncClient):
        response = await client.post(f"{ENDPOINT}/", json=_payload())
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Weekend in Kraków"
        assert data["date"] == "2026-07-04"
        assert "id" in data
        assert "created_at" in data
        assert "optimizer_request" in data
        assert "optimizer_response" in data
        assert data["selected_place_ids"] == ["p1", "p2"]
        assert data["transport_mode"] == "WALK"
        assert data["day_start_hour"] == 9
        assert data["plan_type"] == "SINGLE_DAY"

    async def test_legacy_flat_payload_no_plan_type_accepted(self, client: AsyncClient):
        payload = _payload()
        assert "plan_type" not in payload
        response = await client.post(f"{ENDPOINT}/", json=payload)
        assert response.status_code == 201
        assert response.json()["plan_type"] == "SINGLE_DAY"

    async def test_empty_name_returns_422(self, client: AsyncClient):
        payload = _payload()
        payload["name"] = ""
        response = await client.post(f"{ENDPOINT}/", json=payload)
        assert response.status_code == 422

    async def test_single_place_in_optimizer_request_accepted(self, client: AsyncClient):
        """place_ids min_length was relaxed to 1 so single-place days (with anchors) can be optimized."""
        payload = _payload()
        payload["optimizer_request"]["place_ids"] = ["only-one"]
        response = await client.post(f"{ENDPOINT}/", json=payload)
        assert response.status_code == 201

    async def test_empty_place_ids_in_optimizer_request_returns_422(self, client: AsyncClient):
        payload = _payload()
        payload["optimizer_request"]["place_ids"] = []
        response = await client.post(f"{ENDPOINT}/", json=payload)
        assert response.status_code == 422

    async def test_trip_persisted_in_db(self, client: AsyncClient, test_db):
        await client.post(f"{ENDPOINT}/", json=_payload())
        count = await test_db[TRIPS_COLLECTION].count_documents({})
        assert count == 1


@pytest.mark.integration
class TestListTrips:
    async def test_empty_returns_empty_list(self, client: AsyncClient):
        response = await client.get(f"{ENDPOINT}/")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_all_saved_trips(self, client: AsyncClient):
        await client.post(f"{ENDPOINT}/", json=_payload())
        await client.post(f"{ENDPOINT}/", json={**_payload(), "name": "Second trip"})
        response = await client.get(f"{ENDPOINT}/")
        assert response.status_code == 200
        assert len(response.json()) == 2

    async def test_newest_first(self, client: AsyncClient):
        await client.post(f"{ENDPOINT}/", json={**_payload(), "name": "First"})
        await client.post(f"{ENDPOINT}/", json={**_payload(), "name": "Second"})
        data = (await client.get(f"{ENDPOINT}/")).json()
        assert data[0]["name"] == "Second"

    async def test_list_items_are_summary_only(self, client: AsyncClient):
        await client.post(f"{ENDPOINT}/", json=_payload())
        data = (await client.get(f"{ENDPOINT}/")).json()
        assert "optimizer_request" not in data[0]
        assert "optimizer_response" not in data[0]

    async def test_multi_day_summary_has_date_range_fields(self, client: AsyncClient):
        await client.post(f"{ENDPOINT}/", json=_multi_day_payload())
        data = (await client.get(f"{ENDPOINT}/")).json()
        assert data[0]["plan_type"] == "MULTI_DAY"
        assert data[0]["start_date"] == "2026-08-01"
        assert data[0]["end_date"] == "2026-08-03"
        assert data[0]["num_days"] == 3
        assert "multi_day_request" not in data[0]
        assert "multi_day_response" not in data[0]

    async def test_mixed_single_and_multi_day_list(self, client: AsyncClient):
        await client.post(f"{ENDPOINT}/", json=_payload())
        await client.post(f"{ENDPOINT}/", json=_multi_day_payload())
        data = (await client.get(f"{ENDPOINT}/")).json()
        plan_types = {trip["plan_type"] for trip in data}
        assert plan_types == {"SINGLE_DAY", "MULTI_DAY"}


@pytest.mark.integration
class TestGetTrip:
    async def test_returns_detail_by_id(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        response = await client.get(f"{ENDPOINT}/{created['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == created["id"]
        assert "optimizer_request" in data
        assert "optimizer_response" in data
        assert data["day_start_hour"] == 9

    async def test_invalid_id_returns_404(self, client: AsyncClient):
        response = await client.get(f"{ENDPOINT}/not-a-valid-objectid")
        assert response.status_code == 404

    async def test_unknown_valid_objectid_returns_404(self, client: AsyncClient):
        response = await client.get(f"{ENDPOINT}/000000000000000000000000")
        assert response.status_code == 404


@pytest.mark.integration
class TestSaveTripMultiDay:
    async def test_returns_201_with_detail(self, client: AsyncClient):
        response = await client.post(f"{ENDPOINT}/", json=_multi_day_payload())
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Kraków then Warsaw"
        assert data["plan_type"] == "MULTI_DAY"
        assert data["start_date"] == "2026-08-01"
        assert data["end_date"] == "2026-08-03"
        assert data["num_days"] == 3
        assert data["transport_mode"] == "WALK"
        assert "multi_day_request" in data
        assert "multi_day_response" in data

    async def test_trip_persisted_in_db(self, client: AsyncClient, test_db):
        await client.post(f"{ENDPOINT}/", json=_multi_day_payload())
        count = await test_db[TRIPS_COLLECTION].count_documents({})
        assert count == 1

    async def test_empty_name_returns_422(self, client: AsyncClient):
        payload = _multi_day_payload()
        payload["name"] = ""
        response = await client.post(f"{ENDPOINT}/", json=payload)
        assert response.status_code == 422

    async def test_invalid_nested_multi_day_request_returns_422(self, client: AsyncClient):
        payload = _multi_day_payload()
        payload["multi_day_request"]["transport_mode"] = "TRANSIT"
        response = await client.post(f"{ENDPOINT}/", json=payload)
        assert response.status_code == 422

    async def test_hybrid_payload_rejected(self, client: AsyncClient):
        payload = _multi_day_payload()
        single = _payload()
        payload["date"] = single["date"]
        payload["optimizer_request"] = single["optimizer_request"]
        payload["optimizer_response"] = single["optimizer_response"]
        response = await client.post(f"{ENDPOINT}/", json=payload)
        assert response.status_code == 422


@pytest.mark.integration
class TestGetTripMultiDay:
    async def test_full_round_trip_preserves_all_fields(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_multi_day_payload())).json()
        response = await client.get(f"{ENDPOINT}/{created['id']}")
        assert response.status_code == 200
        data = response.json()

        mdr = data["multi_day_request"]
        assert len(mdr["accommodations"]) == 2
        assert mdr["accommodations"][0]["name"] == "Hotel A"
        assert len(mdr["transfers"]) == 1
        assert mdr["places"][1]["day_preferences"][0]["day_index"] == 1

        days = data["multi_day_response"]["days"]
        assert len(days) == 3
        assert days[0]["steps"][0]["place_id"] == "p1"
        assert days[1]["skipped"][0]["place_id"] == "p2"

        transition_day = days[2]
        assert transition_day["transfer"]["origin"]["name"] == "Hotel A"
        assert transition_day["transfer"]["destination"]["name"] == "Hotel B"
        assert len(transition_day["route_segments"]) == 2
        kinds = {seg["kind"] for seg in transition_day["route_segments"]}
        assert kinds == {"PRE_TRANSFER", "POST_TRANSFER"}

        assert data["multi_day_response"]["unassigned"][0]["place_id"] == "p3"

    async def test_unknown_valid_objectid_returns_404(self, client: AsyncClient):
        response = await client.get(f"{ENDPOINT}/000000000000000000000000")
        assert response.status_code == 404


@pytest.mark.integration
class TestLegacyDocumentCompatibility:
    async def test_raw_legacy_document_get_by_id(self, client: AsyncClient, test_db):
        doc = {**_payload(), "created_at": datetime.now(UTC)}
        assert "plan_type" not in doc
        result = await test_db[TRIPS_COLLECTION].insert_one(doc)

        response = await client.get(f"{ENDPOINT}/{result.inserted_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["plan_type"] == "SINGLE_DAY"
        assert data["date"] == "2026-07-04"
        assert "optimizer_request" in data

    async def test_raw_legacy_document_list(self, client: AsyncClient, test_db):
        doc = {**_payload(), "created_at": datetime.now(UTC)}
        await test_db[TRIPS_COLLECTION].insert_one(doc)

        response = await client.get(f"{ENDPOINT}/")
        assert response.status_code == 200
        data = response.json()
        assert data[0]["plan_type"] == "SINGLE_DAY"


@pytest.mark.integration
class TestUpdateTrip:
    def _updated_payload(self) -> dict:
        payload = _payload()
        payload["name"] = "Updated name"
        payload["optimizer_request"]["place_ids"] = ["p3", "p4"]
        payload["optimizer_response"]["total_wait_min"] = 123
        return payload

    async def test_returns_200_with_updated_detail(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        response = await client.put(f"{ENDPOINT}/{created['id']}", json=self._updated_payload())
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == created["id"]
        assert data["name"] == "Updated name"
        assert data["selected_place_ids"] == ["p3", "p4"]
        assert data["optimizer_response"]["total_wait_min"] == 123

    async def test_created_at_unchanged(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        before = (await client.get(f"{ENDPOINT}/{created['id']}")).json()
        await client.put(f"{ENDPOINT}/{created['id']}", json=self._updated_payload())
        after = (await client.get(f"{ENDPOINT}/{created['id']}")).json()
        assert after["created_at"] == before["created_at"]

    async def test_sets_updated_at(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        assert created["updated_at"] is None
        data = (await client.put(f"{ENDPOINT}/{created['id']}", json=self._updated_payload())).json()
        assert data["updated_at"]

    async def test_get_after_update_returns_new_data(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        await client.put(f"{ENDPOINT}/{created['id']}", json=self._updated_payload())
        data = (await client.get(f"{ENDPOINT}/{created['id']}")).json()
        assert data["name"] == "Updated name"
        assert data["optimizer_request"]["place_ids"] == ["p3", "p4"]

    async def test_invalid_id_returns_404(self, client: AsyncClient):
        response = await client.put(f"{ENDPOINT}/not-a-valid-objectid", json=self._updated_payload())
        assert response.status_code == 404

    async def test_unknown_valid_objectid_returns_404(self, client: AsyncClient):
        response = await client.put(f"{ENDPOINT}/000000000000000000000000", json=self._updated_payload())
        assert response.status_code == 404

    async def test_empty_name_returns_422(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        payload = self._updated_payload()
        payload["name"] = ""
        response = await client.put(f"{ENDPOINT}/{created['id']}", json=payload)
        assert response.status_code == 422

    async def test_only_targeted_trip_updated(self, client: AsyncClient):
        first = (await client.post(f"{ENDPOINT}/", json={**_payload(), "name": "First"})).json()
        await client.post(f"{ENDPOINT}/", json={**_payload(), "name": "Second"})
        await client.put(f"{ENDPOINT}/{first['id']}", json=self._updated_payload())
        data = (await client.get(f"{ENDPOINT}/")).json()
        names = {trip["name"] for trip in data}
        assert names == {"Updated name", "Second"}


@pytest.mark.integration
class TestUpdateTripMultiDay:
    def _updated_payload(self) -> dict:
        payload = _multi_day_payload()
        payload["name"] = "Updated multi-day name"
        payload["multi_day_response"]["unassigned"] = []
        return payload

    async def test_returns_200_with_updated_detail(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_multi_day_payload())).json()
        response = await client.put(f"{ENDPOINT}/{created['id']}", json=self._updated_payload())
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == created["id"]
        assert data["name"] == "Updated multi-day name"
        assert data["multi_day_response"]["unassigned"] == []

    async def test_created_at_unchanged(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_multi_day_payload())).json()
        before = (await client.get(f"{ENDPOINT}/{created['id']}")).json()
        await client.put(f"{ENDPOINT}/{created['id']}", json=self._updated_payload())
        after = (await client.get(f"{ENDPOINT}/{created['id']}")).json()
        assert after["created_at"] == before["created_at"]

    async def test_sets_updated_at(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_multi_day_payload())).json()
        assert created["updated_at"] is None
        data = (await client.put(f"{ENDPOINT}/{created['id']}", json=self._updated_payload())).json()
        assert data["updated_at"]

    async def test_get_after_update_returns_new_data(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_multi_day_payload())).json()
        await client.put(f"{ENDPOINT}/{created['id']}", json=self._updated_payload())
        data = (await client.get(f"{ENDPOINT}/{created['id']}")).json()
        assert data["name"] == "Updated multi-day name"


@pytest.mark.integration
class TestUpdateTripPlanTypeConflict:
    async def test_single_to_multi_day_returns_409(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        response = await client.put(f"{ENDPOINT}/{created['id']}", json=_multi_day_payload())
        assert response.status_code == 409

    async def test_multi_to_single_day_returns_409(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_multi_day_payload())).json()
        response = await client.put(f"{ENDPOINT}/{created['id']}", json=_payload())
        assert response.status_code == 409

    async def test_conflict_leaves_existing_document_unchanged(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        await client.put(f"{ENDPOINT}/{created['id']}", json=_multi_day_payload())
        response = await client.get(f"{ENDPOINT}/{created['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["plan_type"] == "SINGLE_DAY"
        assert data["date"] == "2026-07-04"

    async def test_error_response_matches_error_response_shape(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        response = await client.put(f"{ENDPOINT}/{created['id']}", json=_multi_day_payload())
        data = response.json()
        assert data["status_code"] == 409
        assert "error" in data
        assert "detail" in data

    async def test_valid_but_nonexistent_id_returns_404_not_409(self, client: AsyncClient):
        response = await client.put(f"{ENDPOINT}/000000000000000000000000", json=_multi_day_payload())
        assert response.status_code == 404


@pytest.mark.integration
class TestDeleteTrip:
    async def test_deletes_and_returns_204(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        response = await client.delete(f"{ENDPOINT}/{created['id']}")
        assert response.status_code == 204
        assert response.content == b""

    async def test_trip_removed_from_db(self, client: AsyncClient, test_db):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        await client.delete(f"{ENDPOINT}/{created['id']}")
        count = await test_db[TRIPS_COLLECTION].count_documents({})
        assert count == 0

    async def test_get_after_delete_returns_404(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        await client.delete(f"{ENDPOINT}/{created['id']}")
        response = await client.get(f"{ENDPOINT}/{created['id']}")
        assert response.status_code == 404

    async def test_second_delete_returns_404(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        await client.delete(f"{ENDPOINT}/{created['id']}")
        response = await client.delete(f"{ENDPOINT}/{created['id']}")
        assert response.status_code == 404

    async def test_invalid_id_returns_404(self, client: AsyncClient):
        response = await client.delete(f"{ENDPOINT}/not-a-valid-objectid")
        assert response.status_code == 404

    async def test_unknown_valid_objectid_returns_404(self, client: AsyncClient):
        response = await client.delete(f"{ENDPOINT}/000000000000000000000000")
        assert response.status_code == 404

    async def test_only_targeted_trip_deleted(self, client: AsyncClient):
        first = (await client.post(f"{ENDPOINT}/", json={**_payload(), "name": "First"})).json()
        await client.post(f"{ENDPOINT}/", json={**_payload(), "name": "Second"})
        await client.delete(f"{ENDPOINT}/{first['id']}")
        data = (await client.get(f"{ENDPOINT}/")).json()
        assert len(data) == 1
        assert data[0]["name"] == "Second"

    async def test_deletes_multi_day_trip(self, client: AsyncClient, test_db):
        created = (await client.post(f"{ENDPOINT}/", json=_multi_day_payload())).json()
        response = await client.delete(f"{ENDPOINT}/{created['id']}")
        assert response.status_code == 204
        count = await test_db[TRIPS_COLLECTION].count_documents({})
        assert count == 0
