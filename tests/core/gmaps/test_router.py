"""Integration tests for gmaps REST endpoints — require MongoDB testcontainer."""

import pytest
from bson import ObjectId

from src.core.db.manager import GMAPS_COLLECTION


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
class TestListPlaces:
    async def test_empty_returns_empty_list(self, client):
        response = await client.get("/api/v1/core/gmaps/places")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_inserted_place(self, client, sample_place):
        response = await client.get("/api/v1/core/gmaps/places")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == sample_place
        assert data[0]["name"] == "Test Place"

    async def test_filter_skipped_true(self, client, test_db):
        await test_db[GMAPS_COLLECTION].insert_many(
            [
                {"name": "A", "skipped": True},
                {"name": "B", "skipped": False},
            ]
        )
        response = await client.get("/api/v1/core/gmaps/places", params={"skipped": "true"})
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == "A"

    async def test_filter_list_name(self, client, test_db):
        await test_db[GMAPS_COLLECTION].insert_many(
            [
                {"name": "A", "list_name": "Warsaw"},
                {"name": "B", "list_name": "Krakow"},
            ]
        )
        response = await client.get("/api/v1/core/gmaps/places", params={"list_name": "Warsaw"})
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == "A"


@pytest.mark.integration
class TestGetPlace:
    async def test_found(self, client, sample_place):
        response = await client.get(f"/api/v1/core/gmaps/places/{sample_place}")
        assert response.status_code == 200
        assert response.json()["id"] == sample_place
        assert response.json()["name"] == "Test Place"

    async def test_not_found(self, client):
        response = await client.get(f"/api/v1/core/gmaps/places/{ObjectId()}")
        assert response.status_code == 404

    async def test_invalid_id(self, client):
        response = await client.get("/api/v1/core/gmaps/places/not-an-id")
        assert response.status_code == 404


@pytest.mark.integration
class TestPatchPlace:
    async def test_updates_preferences(self, client, sample_place):
        payload = {"preferred_hour_from": 9, "preferred_hour_to": 17, "visit_duration_min": 60}
        response = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["preferred_hour_from"] == 9
        assert data["preferred_hour_to"] == 17
        assert data["visit_duration_min"] == 60

    async def test_partial_patch(self, client, sample_place):
        response = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json={"skipped": True})
        assert response.status_code == 200
        assert response.json()["skipped"] is True

    async def test_invalid_payload_rejected(self, client, sample_place):
        response = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json={"preferred_hour_from": 25})
        assert response.status_code == 422

    async def test_not_found(self, client):
        response = await client.patch(f"/api/v1/core/gmaps/places/{ObjectId()}", json={"skipped": True})
        assert response.status_code == 404


@pytest.mark.integration
class TestDeletePlace:
    async def test_deletes_existing(self, client, sample_place):
        response = await client.delete(f"/api/v1/core/gmaps/places/{sample_place}")
        assert response.status_code == 204

    async def test_deleted_place_not_found(self, client, sample_place):
        await client.delete(f"/api/v1/core/gmaps/places/{sample_place}")
        response = await client.get(f"/api/v1/core/gmaps/places/{sample_place}")
        assert response.status_code == 404

    async def test_not_found(self, client):
        response = await client.delete(f"/api/v1/core/gmaps/places/{ObjectId()}")
        assert response.status_code == 404
