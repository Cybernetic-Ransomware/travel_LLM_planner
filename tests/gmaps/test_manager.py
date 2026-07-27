"""Unit tests for GooglePlacesManager.

HTTP calls are intercepted by pytest-httpx, which replaces the httpx transport
for the duration of each test — no real network requests are made.
"""

import pytest

from src.gmaps.manager import GooglePlacesManager

_FIELDS = "id,displayName"
_PLACE_URL = "https://places.googleapis.com/v1/places/ChIxyz"
_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


@pytest.fixture
async def manager():
    m = GooglePlacesManager(api_key="test-api-key", fields=_FIELDS)
    await m.connect()
    yield m
    await m.disconnect()


@pytest.fixture
async def manager_no_key():
    m = GooglePlacesManager(api_key="", fields=_FIELDS)
    await m.connect()
    yield m
    await m.disconnect()


@pytest.mark.unit
async def test_connect_creates_client():
    m = GooglePlacesManager(api_key="key", fields="id")
    await m.connect()
    assert m.client is not None
    await m.disconnect()


@pytest.mark.unit
async def test_client_property_raises_before_connect():
    m = GooglePlacesManager(api_key="key", fields="id")
    with pytest.raises(RuntimeError, match="not connected"):
        _ = m.client


@pytest.mark.unit
async def test_disconnect_closes_client(manager):
    await manager.disconnect()
    assert manager._client is None


@pytest.mark.unit
async def test_context_manager():
    async with GooglePlacesManager(api_key="key", fields="id") as m:
        assert m.client is not None
    assert m._client is None


@pytest.mark.unit
async def test_disconnect_is_idempotent():
    m = GooglePlacesManager(api_key="key", fields="id")
    await m.connect()
    await m.disconnect()
    await m.disconnect()  # second call must not raise


@pytest.mark.unit
async def test_fetch_place_details_missing_api_key(manager_no_key):
    payload, status, error = await manager_no_key.fetch_place_details("ChIxyz")
    assert payload is None
    assert status == "MISSING_API_KEY"
    assert error is None


@pytest.mark.unit
async def test_fetch_place_details_success(httpx_mock, manager):
    fake_payload = {"id": "ChIxyz", "displayName": {"text": "Café Roma"}}
    httpx_mock.add_response(url=_PLACE_URL, json=fake_payload)

    payload, status, error = await manager.fetch_place_details("ChIxyz")

    assert payload == fake_payload
    assert status == "OK"
    assert error is None
    # Verify the request hit the correct endpoint
    request = httpx_mock.get_requests()[0]
    assert request.headers["X-Goog-Api-Key"] == "test-api-key"
    assert request.headers["X-Goog-FieldMask"] == _FIELDS


@pytest.mark.unit
async def test_fetch_place_details_fields_override(httpx_mock, manager):
    fake_payload = {"id": "ChIxyz", "priceLevel": "PRICE_LEVEL_MODERATE"}
    httpx_mock.add_response(url=_PLACE_URL, json=fake_payload)

    payload, status, error = await manager.fetch_place_details("ChIxyz", fields="id,priceLevel")

    assert payload == fake_payload
    assert status == "OK"
    request = httpx_mock.get_requests()[0]
    assert request.headers["X-Goog-FieldMask"] == "id,priceLevel"


@pytest.mark.unit
async def test_fetch_place_details_http_error(httpx_mock, manager):
    error_body = {"error": {"status": "NOT_FOUND", "message": "Place not found"}}
    httpx_mock.add_response(url=_PLACE_URL, status_code=404, json=error_body)

    payload, status, error = await manager.fetch_place_details("ChIxyz")

    assert payload is None
    assert status == "NOT_FOUND"
    assert error == "Place not found"


@pytest.mark.unit
async def test_fetch_place_details_non_json_error(httpx_mock, manager):
    httpx_mock.add_response(url=_PLACE_URL, status_code=500, text="Internal Server Error")

    payload, status, error = await manager.fetch_place_details("ChIxyz")

    assert payload is None
    assert status == "HTTP_500"
    assert error == "Internal Server Error"


@pytest.mark.unit
async def test_search_place_id_missing_api_key(manager_no_key):
    place_id, status, error = await manager_no_key.search_place_id("Café Roma", 52.2, 21.0)
    assert place_id is None
    assert status == "MISSING_API_KEY"


@pytest.mark.unit
async def test_search_place_id_missing_name(manager):
    place_id, status, error = await manager.search_place_id(None, 52.2, 21.0)
    assert place_id is None
    assert status == "MISSING_NAME"


@pytest.mark.unit
async def test_search_place_id_success(httpx_mock, manager):
    fake_payload = {"places": [{"id": "ChIabc", "displayName": {"text": "Café Roma"}}]}
    httpx_mock.add_response(url=_SEARCH_URL, json=fake_payload)

    place_id, status, error = await manager.search_place_id("Café Roma", 52.2, 21.0)

    assert place_id == "ChIabc"
    assert status == "OK"
    assert error is None
    # Verify locationBias in request body
    import json

    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["textQuery"] == "Café Roma"
    assert body["locationBias"]["circle"]["center"]["latitude"] == 52.2


@pytest.mark.unit
async def test_search_place_id_not_found(httpx_mock, manager):
    httpx_mock.add_response(url=_SEARCH_URL, json={"places": []})

    place_id, status, error = await manager.search_place_id("Nieznane miejsce", None, None)

    assert place_id is None
    assert status == "NOT_FOUND"


@pytest.mark.unit
async def test_search_place_id_http_error(httpx_mock, manager):
    error_body = {"error": {"status": "PERMISSION_DENIED", "message": "API key invalid"}}
    httpx_mock.add_response(url=_SEARCH_URL, status_code=403, json=error_body)

    place_id, status, error = await manager.search_place_id("Café Roma", None, None)

    assert place_id is None
    assert status == "PERMISSION_DENIED"
    assert error == "API key invalid"


@pytest.mark.unit
async def test_build_enrichment_update_extracts_coordinates(httpx_mock, manager):
    fake_payload = {
        "id": "ChIxyz",
        "formattedAddress": "ul. Testowa 1",
        "location": {"latitude": 50.05, "longitude": 19.93},
    }
    httpx_mock.add_response(url=_PLACE_URL, json=fake_payload)

    update_fields, resolved = await manager.build_enrichment_update({"gmaps_place_id": "ChIxyz", "name": "Test"})

    assert resolved is True
    assert update_fields["address"] == "ul. Testowa 1"
    assert update_fields["lat"] == 50.05
    assert update_fields["lng"] == 19.93
    assert update_fields["details_status"] == "OK"


@pytest.mark.unit
async def test_build_enrichment_update_missing_location_leaves_coordinates_unset(httpx_mock, manager):
    fake_payload = {"id": "ChIxyz", "formattedAddress": "ul. Testowa 1"}
    httpx_mock.add_response(url=_PLACE_URL, json=fake_payload)

    update_fields, resolved = await manager.build_enrichment_update({"gmaps_place_id": "ChIxyz", "name": "Test"})

    assert resolved is True
    assert "lat" not in update_fields
    assert "lng" not in update_fields


@pytest.mark.unit
async def test_build_enrichment_update_falls_back_to_search(httpx_mock, manager):
    httpx_mock.add_response(url=_PLACE_URL, status_code=404, json={"error": {"status": "NOT_FOUND"}})
    httpx_mock.add_response(
        url=_SEARCH_URL, json={"places": [{"id": "ChIresolved", "formattedAddress": "ul. Nowa 2"}]}
    )
    httpx_mock.add_response(
        url="https://places.googleapis.com/v1/places/ChIresolved",
        json={"id": "ChIresolved", "formattedAddress": "ul. Nowa 2", "location": {"latitude": 1.0, "longitude": 2.0}},
    )

    update_fields, resolved = await manager.build_enrichment_update({"gmaps_place_id": "ChIxyz", "name": "Test"})

    assert resolved is True
    assert update_fields["gmaps_place_id"] == "ChIresolved"
    assert update_fields["lat"] == 1.0
    assert update_fields["lng"] == 2.0


@pytest.mark.unit
async def test_build_enrichment_update_not_resolved_when_google_finds_nothing(httpx_mock, manager):
    httpx_mock.add_response(url=_SEARCH_URL, json={"places": []})

    update_fields, resolved = await manager.build_enrichment_update({"gmaps_place_id": None, "name": "Unknown"})

    assert resolved is False
    assert "details" not in update_fields
    assert "lat" not in update_fields
