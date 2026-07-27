"""Integration tests for gmaps REST endpoints — require MongoDB testcontainer."""

import pendulum
import pytest
from bson import ObjectId
from pytest_httpx import HTTPXMock

from src.core.db.manager import GMAPS_COLLECTION

_PLACES_API_URL = "https://places.googleapis.com/v1/places"


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

    async def test_sets_priority(self, client, sample_place):
        response = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json={"priority": "must_see"})
        assert response.status_code == 200
        assert response.json()["priority"] == "must_see"

    async def test_invalid_priority_rejected(self, client, sample_place):
        response = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json={"priority": "urgent"})
        assert response.status_code == 422

    async def test_null_clears_preference(self, client, sample_place):
        await client.patch(
            f"/api/v1/core/gmaps/places/{sample_place}",
            json={"preferred_hour_from": 9, "preferred_hour_to": 17},
        )
        response = await client.patch(
            f"/api/v1/core/gmaps/places/{sample_place}", json={"preferred_hour_from": None}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["preferred_hour_from"] is None
        assert data["preferred_hour_to"] == 17

    async def test_null_skipped_rejected(self, client, sample_place):
        response = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json={"skipped": None})
        assert response.status_code == 422

    async def test_single_field_patch_does_not_clear_others(self, client, sample_place):
        await client.patch(
            f"/api/v1/core/gmaps/places/{sample_place}",
            json={"preferred_hour_from": 9, "preferred_hour_to": 17},
        )
        response = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json={"visit_duration_min": 60})
        assert response.status_code == 200
        data = response.json()
        assert data["preferred_hour_from"] == 9
        assert data["preferred_hour_to"] == 17
        assert data["visit_duration_min"] == 60

    async def test_partial_patch_cannot_make_hour_from_exceed_stored_to(self, client, sample_place):
        await client.patch(
            f"/api/v1/core/gmaps/places/{sample_place}",
            json={"preferred_hour_from": 9, "preferred_hour_to": 17},
        )

        response = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json={"preferred_hour_from": 18})
        assert response.status_code == 422

        data = (await client.get(f"/api/v1/core/gmaps/places/{sample_place}")).json()
        assert data["preferred_hour_from"] == 9
        assert data["preferred_hour_to"] == 17

    async def test_partial_patch_cannot_make_hour_to_precede_stored_from(self, client, sample_place):
        await client.patch(
            f"/api/v1/core/gmaps/places/{sample_place}",
            json={"preferred_hour_from": 9, "preferred_hour_to": 17},
        )

        response = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json={"preferred_hour_to": 8})
        assert response.status_code == 422

        data = (await client.get(f"/api/v1/core/gmaps/places/{sample_place}")).json()
        assert data["preferred_hour_from"] == 9
        assert data["preferred_hour_to"] == 17

    async def test_clearing_one_hour_allows_later_single_hour_patch(self, client, sample_place):
        await client.patch(
            f"/api/v1/core/gmaps/places/{sample_place}",
            json={"preferred_hour_from": 9, "preferred_hour_to": 17},
        )

        clear = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json={"preferred_hour_to": None})
        assert clear.status_code == 200

        update = await client.patch(f"/api/v1/core/gmaps/places/{sample_place}", json={"preferred_hour_from": 18})
        assert update.status_code == 200
        assert update.json()["preferred_hour_from"] == 18


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


@pytest.mark.integration
class TestEnrichPlaces:
    @pytest.fixture
    async def place_without_address(self, test_db):
        result = await test_db[GMAPS_COLLECTION].insert_one(
            {"name": "Wawel Castle", "gmaps_place_id": "ChItest123", "lat": 50.054, "lng": 19.935}
        )
        return str(result.inserted_id)

    async def test_enrich_updates_address_and_opening_hours(
        self, client, test_db, place_without_address, httpx_mock: HTTPXMock
    ):
        fake_details = {
            "id": "ChItest123",
            "formattedAddress": "Wawel 5, 31-001 Kraków",
            "regularOpeningHours": {"periods": [{"open": {"day": 1, "hour": 9}, "close": {"day": 1, "hour": 17}}]},
        }
        httpx_mock.add_response(
            url=f"{_PLACES_API_URL}/ChItest123",
            json=fake_details,
        )

        response = await client.post("/api/v1/core/gmaps/enrich", json={"limit": 10})

        assert response.status_code == 200
        data = response.json()
        assert data["scanned"] == 1
        assert data["updated"] == 1

        doc = await test_db[GMAPS_COLLECTION].find_one({"name": "Wawel Castle"})
        assert doc["address"] == "Wawel 5, 31-001 Kraków"
        assert doc["opening_hours"] is not None
        assert "periods" in doc["opening_hours"]

    async def test_enrich_no_candidates_returns_zero(self, client, test_db):
        await test_db[GMAPS_COLLECTION].insert_one(
            {"name": "Already Enriched", "gmaps_place_id": "ChIdone", "address": "ul. Gotowa 1"}
        )
        response = await client.post("/api/v1/core/gmaps/enrich", json={"limit": 10})
        assert response.status_code == 200
        assert response.json()["scanned"] == 0

    async def test_enrich_without_opening_hours_in_response(
        self, client, test_db, place_without_address, httpx_mock: HTTPXMock
    ):
        fake_details = {
            "id": "ChItest123",
            "formattedAddress": "Wawel 5, 31-001 Kraków",
        }
        httpx_mock.add_response(url=f"{_PLACES_API_URL}/ChItest123", json=fake_details)

        await client.post("/api/v1/core/gmaps/enrich", json={"limit": 10})

        doc = await test_db[GMAPS_COLLECTION].find_one({"name": "Wawel Castle"})
        assert doc["address"] == "Wawel 5, 31-001 Kraków"
        assert doc.get("opening_hours") is None


@pytest.mark.integration
class TestEnrichBackoff:
    async def test_backoff_excluded_place_not_scanned(self, test_db, client):
        now = pendulum.now("UTC")
        await test_db[GMAPS_COLLECTION].insert_one({
            "name": "Failed",
            "gmaps_place_id": "ChIfailed",
            "address": None,
            "enriched_at": now.subtract(hours=1),
            "details_status": "NOT_FOUND",
            "lat": 52.0,
            "lng": 21.0,
        })
        response = await client.post("/api/v1/core/gmaps/enrich", json={"limit": 10})
        assert response.status_code == 200
        assert response.json()["scanned"] == 0


@pytest.mark.integration
class TestEnrichPlace:
    @pytest.fixture
    async def place_without_coordinates(self, test_db):
        result = await test_db[GMAPS_COLLECTION].insert_one(
            {"name": "Wawel Castle", "gmaps_place_id": "ChItest123", "lat": None, "lng": None}
        )
        return str(result.inserted_id)

    async def test_enriches_target_place_and_sets_coordinates(
        self, client, test_db, place_without_coordinates, httpx_mock: HTTPXMock
    ):
        fake_details = {
            "id": "ChItest123",
            "formattedAddress": "Wawel 5, 31-001 Kraków",
            "location": {"latitude": 50.054, "longitude": 19.935},
        }
        httpx_mock.add_response(url=f"{_PLACES_API_URL}/ChItest123", json=fake_details)

        response = await client.post(f"/api/v1/core/gmaps/places/{place_without_coordinates}/enrich")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == place_without_coordinates
        assert data["address"] == "Wawel 5, 31-001 Kraków"
        assert data["lat"] == 50.054
        assert data["lng"] == 19.935

    async def test_does_not_touch_other_places(
        self, client, test_db, place_without_coordinates, httpx_mock: HTTPXMock
    ):
        other = await test_db[GMAPS_COLLECTION].insert_one(
            {"name": "Other Place", "gmaps_place_id": "ChIother", "address": None, "lat": None, "lng": None}
        )
        fake_details = {
            "id": "ChItest123",
            "formattedAddress": "Wawel 5, 31-001 Kraków",
            "location": {"latitude": 50.054, "longitude": 19.935},
        }
        httpx_mock.add_response(url=f"{_PLACES_API_URL}/ChItest123", json=fake_details)

        await client.post(f"/api/v1/core/gmaps/places/{place_without_coordinates}/enrich")

        other_doc = await test_db[GMAPS_COLLECTION].find_one({"_id": other.inserted_id})
        assert other_doc["address"] is None
        assert other_doc["lat"] is None

    async def test_not_found(self, client):
        response = await client.post(f"/api/v1/core/gmaps/places/{ObjectId()}/enrich")
        assert response.status_code == 404

    async def test_invalid_id(self, client):
        response = await client.post("/api/v1/core/gmaps/places/not-an-id/enrich")
        assert response.status_code == 404

    async def test_returns_error_when_google_cannot_resolve_location(
        self, client, place_without_coordinates, httpx_mock: HTTPXMock
    ):
        httpx_mock.add_response(
            url=f"{_PLACES_API_URL}/ChItest123", status_code=404, json={"error": {"status": "NOT_FOUND"}}
        )
        httpx_mock.add_response(url=f"{_PLACES_API_URL}:searchText", json={"places": []})

        response = await client.post(f"/api/v1/core/gmaps/places/{place_without_coordinates}/enrich")

        assert response.status_code == 502
