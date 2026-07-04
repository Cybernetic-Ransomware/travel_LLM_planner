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
        "selected_place_ids": ["p1", "p2"],
        "transport_mode": "WALK",
        "day_start_hour": 9,
        "day_end_hour": 21,
    }


@pytest.fixture(autouse=True)
async def clean_trips(test_db):
    yield
    await test_db[TRIPS_COLLECTION].delete_many({})


@pytest.mark.integration
class TestSaveTrip:
    async def test_returns_201_and_trip_out(self, client: AsyncClient):
        response = await client.post(f"{ENDPOINT}/", json=_payload())
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Weekend in Kraków"
        assert data["date"] == "2026-07-04"
        assert "id" in data
        assert "created_at" in data

    async def test_empty_name_returns_422(self, client: AsyncClient):
        payload = _payload()
        payload["name"] = ""
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


@pytest.mark.integration
class TestGetTrip:
    async def test_returns_trip_by_id(self, client: AsyncClient):
        created = (await client.post(f"{ENDPOINT}/", json=_payload())).json()
        response = await client.get(f"{ENDPOINT}/{created['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    async def test_invalid_id_returns_404(self, client: AsyncClient):
        response = await client.get(f"{ENDPOINT}/not-a-valid-objectid")
        assert response.status_code == 404

    async def test_unknown_valid_objectid_returns_404(self, client: AsyncClient):
        response = await client.get(f"{ENDPOINT}/000000000000000000000000")
        assert response.status_code == 404
