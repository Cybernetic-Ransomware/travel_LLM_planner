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
