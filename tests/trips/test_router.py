import pytest
from httpx import AsyncClient

ENDPOINT = "/api/v1/core/trips"

pytestmark = pytest.mark.integration


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


def _updated_single(**over) -> dict:
    payload = _payload()
    payload["name"] = "Updated name"
    payload["optimizer_request"]["place_ids"] = ["p3", "p4"]
    payload["optimizer_response"]["total_wait_min"] = 123
    payload["expected_revision"] = 0
    payload.update(over)
    return payload


class TestSaveTrip:
    async def test_returns_201_with_detail(self, trips_client: AsyncClient):
        response = await trips_client.post(f"{ENDPOINT}/", json=_payload())
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Weekend in Kraków"
        assert data["date"] == "2026-07-04"
        assert data["revision"] == 0
        assert data["updated_at"] is None
        assert data["selected_place_ids"] == ["p1", "p2"]
        assert data["plan_type"] == "SINGLE_DAY"

    async def test_legacy_flat_payload_no_plan_type_accepted(self, trips_client: AsyncClient):
        payload = _payload()
        assert "plan_type" not in payload
        response = await trips_client.post(f"{ENDPOINT}/", json=payload)
        assert response.status_code == 201
        assert response.json()["plan_type"] == "SINGLE_DAY"

    async def test_empty_name_returns_422(self, trips_client: AsyncClient):
        payload = _payload()
        payload["name"] = ""
        assert (await trips_client.post(f"{ENDPOINT}/", json=payload)).status_code == 422

    async def test_creates_created_revision(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        history = (await trips_client.get(f"{ENDPOINT}/{created['id']}/revisions")).json()
        assert history["current_revision"] == 0
        assert len(history["revisions"]) == 1
        assert history["revisions"][0]["source"] == "CREATED"
        assert history["revisions"][0]["recorded_at"]


class TestListTrips:
    async def test_empty_returns_empty_list(self, trips_client: AsyncClient):
        assert (await trips_client.get(f"{ENDPOINT}/")).json() == []

    async def test_newest_first(self, trips_client: AsyncClient):
        await trips_client.post(f"{ENDPOINT}/", json={**_payload(), "name": "First"})
        await trips_client.post(f"{ENDPOINT}/", json={**_payload(), "name": "Second"})
        data = (await trips_client.get(f"{ENDPOINT}/")).json()
        assert data[0]["name"] == "Second"

    async def test_list_items_are_summary_only(self, trips_client: AsyncClient):
        await trips_client.post(f"{ENDPOINT}/", json=_payload())
        data = (await trips_client.get(f"{ENDPOINT}/")).json()
        assert "optimizer_request" not in data[0]
        assert "optimizer_response" not in data[0]

    async def test_multi_day_summary_has_date_range_fields(self, trips_client: AsyncClient):
        await trips_client.post(f"{ENDPOINT}/", json=_multi_day_payload())
        data = (await trips_client.get(f"{ENDPOINT}/")).json()
        assert data[0]["plan_type"] == "MULTI_DAY"
        assert data[0]["start_date"] == "2026-08-01"
        assert data[0]["end_date"] == "2026-08-03"
        assert data[0]["num_days"] == 3


class TestGetTrip:
    async def test_returns_detail_by_id(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        data = (await trips_client.get(f"{ENDPOINT}/{created['id']}")).json()
        assert data["id"] == created["id"]
        assert data["day_start_hour"] == 9

    async def test_invalid_id_returns_404(self, trips_client: AsyncClient):
        assert (await trips_client.get(f"{ENDPOINT}/not-a-valid-objectid")).status_code == 404

    async def test_unknown_valid_objectid_returns_404(self, trips_client: AsyncClient):
        assert (await trips_client.get(f"{ENDPOINT}/000000000000000000000000")).status_code == 404


class TestSaveTripMultiDay:
    async def test_returns_201_with_detail(self, trips_client: AsyncClient):
        data = (await trips_client.post(f"{ENDPOINT}/", json=_multi_day_payload())).json()
        assert data["plan_type"] == "MULTI_DAY"
        assert data["num_days"] == 3

    async def test_hybrid_payload_rejected(self, trips_client: AsyncClient):
        payload = _multi_day_payload()
        single = _payload()
        payload["date"] = single["date"]
        payload["optimizer_request"] = single["optimizer_request"]
        payload["optimizer_response"] = single["optimizer_response"]
        assert (await trips_client.post(f"{ENDPOINT}/", json=payload)).status_code == 422


class TestGetTripMultiDay:
    async def test_full_round_trip_preserves_all_fields(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_multi_day_payload())).json()
        data = (await trips_client.get(f"{ENDPOINT}/{created['id']}")).json()
        mdr = data["multi_day_request"]
        assert len(mdr["accommodations"]) == 2
        assert len(mdr["transfers"]) == 1
        days = data["multi_day_response"]["days"]
        assert days[0]["steps"][0]["place_id"] == "p1"
        assert days[1]["skipped"][0]["place_id"] == "p2"
        transition_day = days[2]
        assert {seg["kind"] for seg in transition_day["route_segments"]} == {"PRE_TRANSFER", "POST_TRANSFER"}
        assert data["multi_day_response"]["unassigned"][0]["place_id"] == "p3"


class TestUpdateTrip:
    async def test_returns_200_with_updated_detail(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        data = (await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single())).json()
        assert data["name"] == "Updated name"
        assert data["selected_place_ids"] == ["p3", "p4"]
        assert data["revision"] == 1

    async def test_created_at_unchanged_updated_at_set(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        assert created["updated_at"] is None
        after = (await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single())).json()
        assert after["created_at"] == created["created_at"]
        assert after["updated_at"]

    async def test_adds_manual_revision_row(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single())
        history = (await trips_client.get(f"{ENDPOINT}/{created['id']}/revisions")).json()
        assert [r["source"] for r in history["revisions"]] == ["MANUAL", "CREATED"]
        assert history["revisions"][0]["summary"].startswith("Manual update — SINGLE_DAY")

    async def test_unknown_valid_objectid_returns_404(self, trips_client: AsyncClient):
        assert (await trips_client.put(f"{ENDPOINT}/000000000000000000000000", json=_updated_single())).status_code == 404


class TestUpdateTripPlanTypeConflict:
    async def test_single_to_multi_day_returns_409(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        body = {**_multi_day_payload(), "expected_revision": 0}
        assert (await trips_client.put(f"{ENDPOINT}/{created['id']}", json=body)).status_code == 409

    async def test_conflict_leaves_existing_document_unchanged(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json={**_multi_day_payload(), "expected_revision": 0})
        data = (await trips_client.get(f"{ENDPOINT}/{created['id']}")).json()
        assert data["plan_type"] == "SINGLE_DAY"


class TestUpdateTripConcurrency:
    async def test_put_without_expected_revision_returns_428(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        body = {**_payload(), "name": "No token"}
        assert (await trips_client.put(f"{ENDPOINT}/{created['id']}", json=body)).status_code == 428

    async def test_put_with_stale_expected_revision_returns_409(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="First"))
        response = await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="Second"))
        assert response.status_code == 409

    async def test_two_sequential_updates_with_refreshed_token_succeed(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        first = (await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="First"))).json()
        assert first["revision"] == 1
        second = await trips_client.put(
            f"{ENDPOINT}/{created['id']}", json=_updated_single(name="Second", expected_revision=first["revision"])
        )
        assert second.status_code == 200
        assert second.json()["revision"] == 2

    async def test_stale_put_after_concurrent_edit_does_not_clobber(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="Winner"))
        loser = await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="Loser"))
        assert loser.status_code == 409
        assert (await trips_client.get(f"{ENDPOINT}/{created['id']}")).json()["name"] == "Winner"


class TestDeleteTrip:
    async def test_deletes_and_returns_204(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        response = await trips_client.delete(f"{ENDPOINT}/{created['id']}")
        assert response.status_code == 204
        assert response.content == b""

    async def test_get_after_delete_returns_404(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.delete(f"{ENDPOINT}/{created['id']}")
        assert (await trips_client.get(f"{ENDPOINT}/{created['id']}")).status_code == 404

    async def test_history_gone_after_delete(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single())
        await trips_client.delete(f"{ENDPOINT}/{created['id']}")
        assert (await trips_client.get(f"{ENDPOINT}/{created['id']}/revisions")).status_code == 404

    async def test_second_delete_returns_404(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.delete(f"{ENDPOINT}/{created['id']}")
        assert (await trips_client.delete(f"{ENDPOINT}/{created['id']}")).status_code == 404

    async def test_invalid_id_returns_404(self, trips_client: AsyncClient):
        assert (await trips_client.delete(f"{ENDPOINT}/not-a-valid-objectid")).status_code == 404


class TestListTripRevisions:
    async def test_fresh_trip_has_one_created_row(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        data = (await trips_client.get(f"{ENDPOINT}/{created['id']}/revisions")).json()
        assert data["trip_id"] == created["id"]
        assert data["current_revision"] == 0
        assert len(data["revisions"]) == 1
        row = data["revisions"][0]
        assert row["source"] == "CREATED"
        assert "recorded_at" in row and "created_at" not in row
        assert "snapshot" not in row

    async def test_newest_first_after_edits(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="v1"))
        data = (await trips_client.get(f"{ENDPOINT}/{created['id']}/revisions")).json()
        assert [r["revision"] for r in data["revisions"]] == [1, 0]

    async def test_unknown_trip_returns_404(self, trips_client: AsyncClient):
        assert (await trips_client.get(f"{ENDPOINT}/000000000000000000000000/revisions")).status_code == 404


class TestGetTripRevision:
    async def test_returns_historical_snapshot(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="changed"))
        rev0 = (await trips_client.get(f"{ENDPOINT}/{created['id']}/revisions/0")).json()
        assert rev0["name"] == "Weekend in Kraków"
        assert rev0["revision"] == 0
        assert rev0["source"] == "CREATED"
        assert rev0["recorded_at"]

    async def test_unknown_revision_returns_404(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        assert (await trips_client.get(f"{ENDPOINT}/{created['id']}/revisions/9")).status_code == 404

    async def test_negative_revision_returns_422(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        assert (await trips_client.get(f"{ENDPOINT}/{created['id']}/revisions/-1")).status_code == 422


class TestRestoreTripRevision:
    async def test_restore_creates_new_revert_revision(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="v1"))
        restored = await trips_client.post(f"{ENDPOINT}/{created['id']}/revisions/0/restore", json={"expected_revision": 1})
        assert restored.status_code == 200
        data = restored.json()
        assert data["revision"] == 2
        assert data["name"] == "Weekend in Kraków"
        history = (await trips_client.get(f"{ENDPOINT}/{created['id']}/revisions")).json()
        assert history["revisions"][0]["source"] == "REVERT"
        assert history["revisions"][0]["restored_from_revision"] == 0

    async def test_stale_expected_revision_returns_409_and_no_new_row(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="v1"))
        response = await trips_client.post(f"{ENDPOINT}/{created['id']}/revisions/0/restore", json={"expected_revision": 0})
        assert response.status_code == 409
        history = (await trips_client.get(f"{ENDPOINT}/{created['id']}/revisions")).json()
        assert history["current_revision"] == 1

    async def test_restore_current_revision_returns_400(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="v1"))
        response = await trips_client.post(f"{ENDPOINT}/{created['id']}/revisions/1/restore", json={"expected_revision": 1})
        assert response.status_code == 400

    async def test_unknown_revision_returns_404(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        response = await trips_client.post(f"{ENDPOINT}/{created['id']}/revisions/9/restore", json={"expected_revision": 0})
        assert response.status_code == 404

    async def test_missing_expected_revision_returns_422(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        response = await trips_client.post(f"{ENDPOINT}/{created['id']}/revisions/0/restore", json={})
        assert response.status_code == 422

    async def test_restored_state_visible_on_get(self, trips_client: AsyncClient):
        created = (await trips_client.post(f"{ENDPOINT}/", json=_payload())).json()
        await trips_client.put(f"{ENDPOINT}/{created['id']}", json=_updated_single(name="v1"))
        await trips_client.post(f"{ENDPOINT}/{created['id']}/revisions/0/restore", json={"expected_revision": 1})
        current = (await trips_client.get(f"{ENDPOINT}/{created['id']}")).json()
        assert current["name"] == "Weekend in Kraków"
        assert current["revision"] == 2
