"""Unit tests for GoogleRoutesManager.

HTTP calls are intercepted by pytest-httpx, which replaces the httpx transport
for the duration of each test — no real network requests are made.
"""

import json
from datetime import UTC, datetime, timezone

import pytest

from src.optimizer.matrix.client import GoogleRoutesManager
from src.optimizer.matrix.models import TransportMode

_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"

_PLACE_COORDS = [
    ("place_a", 50.061, 19.938),
    ("place_b", 50.054, 19.944),
    ("place_c", 50.049, 19.930),
]


@pytest.fixture
async def manager():
    m = GoogleRoutesManager(api_key="test-routes-key")
    await m.connect()
    yield m
    await m.disconnect()


@pytest.fixture
async def manager_no_key():
    m = GoogleRoutesManager(api_key="")
    await m.connect()
    yield m
    await m.disconnect()


def _make_entry(origin_idx: int, dest_idx: int, distance_m: int, duration_s: int) -> dict:
    return {
        "originIndex": origin_idx,
        "destinationIndex": dest_idx,
        "distanceMeters": distance_m,
        "duration": f"{duration_s}s",
        "status": {"code": 0},
    }


@pytest.mark.unit
async def test_connect_creates_client():
    m = GoogleRoutesManager(api_key="key")
    await m.connect()
    assert m.client is not None
    await m.disconnect()


@pytest.mark.unit
async def test_client_property_raises_before_connect():
    m = GoogleRoutesManager(api_key="key")
    with pytest.raises(RuntimeError, match="not connected"):
        _ = m.client


@pytest.mark.unit
async def test_disconnect_is_idempotent():
    m = GoogleRoutesManager(api_key="key")
    await m.connect()
    await m.disconnect()
    await m.disconnect()


@pytest.mark.unit
async def test_context_manager():
    async with GoogleRoutesManager(api_key="key") as m:
        assert m.client is not None
    assert m._client is None


@pytest.mark.unit
async def test_missing_api_key_returns_error(manager_no_key):
    entries, status, error = await manager_no_key.compute_matrix(_PLACE_COORDS, TransportMode.WALK)
    assert entries is None
    assert status == "MISSING_API_KEY"


@pytest.mark.unit
async def test_successful_response_returns_entries(httpx_mock, manager):
    raw = [
        _make_entry(0, 1, 800, 600),
        _make_entry(0, 2, 1200, 900),
        _make_entry(1, 0, 810, 610),
        _make_entry(1, 2, 600, 450),
        _make_entry(2, 0, 1190, 895),
        _make_entry(2, 1, 610, 455),
        {"originIndex": 0, "destinationIndex": 0, "distanceMeters": 0, "duration": "0s"},
        {"originIndex": 1, "destinationIndex": 1, "distanceMeters": 0, "duration": "0s"},
        {"originIndex": 2, "destinationIndex": 2, "distanceMeters": 0, "duration": "0s"},
    ]
    httpx_mock.add_response(url=_MATRIX_URL, json=raw)

    entries, status, error = await manager.compute_matrix(_PLACE_COORDS, TransportMode.WALK)

    assert status == "OK"
    assert error is None
    assert len(entries) == 6
    ids = {(e.origin_id, e.dest_id) for e in entries}
    assert ("place_a", "place_b") in ids
    assert ("place_b", "place_a") in ids
    assert ("place_a", "place_a") not in ids


@pytest.mark.unit
async def test_duration_string_parsed_correctly(httpx_mock, manager):
    httpx_mock.add_response(url=_MATRIX_URL, json=[_make_entry(0, 1, 1000, 375)])

    entries, status, _ = await manager.compute_matrix(_PLACE_COORDS, TransportMode.WALK)

    assert status == "OK"
    assert entries[0].duration_s == 375
    assert entries[0].distance_m == 1000


@pytest.mark.unit
async def test_entry_with_nonzero_status_code_is_skipped(httpx_mock, manager):
    raw = [
        _make_entry(0, 1, 800, 600),
        {
            "originIndex": 0,
            "destinationIndex": 2,
            "distanceMeters": 0,
            "duration": "0s",
            "status": {"code": 2, "message": "NOT_FOUND"},
        },
    ]
    httpx_mock.add_response(url=_MATRIX_URL, json=raw)

    entries, status, _ = await manager.compute_matrix(_PLACE_COORDS, TransportMode.WALK)

    assert status == "OK"
    assert len(entries) == 1
    assert entries[0].origin_id == "place_a"
    assert entries[0].dest_id == "place_b"


@pytest.mark.unit
async def test_http_error_returns_error_status(httpx_mock, manager):
    error_body = {"error": {"status": "PERMISSION_DENIED", "message": "API key invalid"}}
    httpx_mock.add_response(url=_MATRIX_URL, status_code=403, json=error_body)

    entries, status, error = await manager.compute_matrix(_PLACE_COORDS, TransportMode.WALK)

    assert entries is None
    assert status == "PERMISSION_DENIED"
    assert error == "API key invalid"


@pytest.mark.unit
async def test_non_json_error_response(httpx_mock, manager):
    httpx_mock.add_response(url=_MATRIX_URL, status_code=500, text="Internal Server Error")

    entries, status, error = await manager.compute_matrix(_PLACE_COORDS, TransportMode.WALK)

    assert entries is None
    assert status == "HTTP_500"
    assert error == "Internal Server Error"


@pytest.mark.unit
async def test_array_error_response_parsed(httpx_mock, manager):
    """Google Routes API sometimes wraps errors in a JSON array."""
    error_body = [{"error": {"status": "INVALID_ARGUMENT", "message": "Timestamp must be set to a future time."}}]
    httpx_mock.add_response(url=_MATRIX_URL, status_code=400, json=error_body)

    entries, status, error = await manager.compute_matrix(_PLACE_COORDS, TransportMode.WALK)

    assert entries is None
    assert status == "INVALID_ARGUMENT"
    assert error == "Timestamp must be set to a future time."


@pytest.mark.unit
async def test_unexpected_response_format(httpx_mock, manager):
    httpx_mock.add_response(url=_MATRIX_URL, json={"not": "a list"})

    entries, status, error = await manager.compute_matrix(_PLACE_COORDS, TransportMode.WALK)

    assert entries is None
    assert status == "UNEXPECTED_RESPONSE"


@pytest.mark.unit
async def test_transit_mode_sends_departure_time(httpx_mock, manager):
    httpx_mock.add_response(url=_MATRIX_URL, json=[_make_entry(0, 1, 500, 900)])
    departure = datetime(2026, 6, 15, 10, 0, 0, tzinfo=UTC)

    await manager.compute_matrix(_PLACE_COORDS, TransportMode.TRANSIT, departure_time=departure)

    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["travelMode"] == "TRANSIT"
    assert "departureTime" in body
    assert body["departureTime"] == "2026-06-15T10:00:00Z"


@pytest.mark.unit
async def test_correct_headers_sent(httpx_mock, manager):
    httpx_mock.add_response(url=_MATRIX_URL, json=[])

    await manager.compute_matrix(_PLACE_COORDS, TransportMode.DRIVE)

    request = httpx_mock.get_requests()[0]
    assert request.headers["X-Goog-Api-Key"] == "test-routes-key"
    assert "originIndex" in request.headers["X-Goog-FieldMask"]


@pytest.mark.unit
async def test_waypoints_built_from_coords(httpx_mock, manager):
    httpx_mock.add_response(url=_MATRIX_URL, json=[])

    await manager.compute_matrix(_PLACE_COORDS, TransportMode.WALK)

    body = json.loads(httpx_mock.get_requests()[0].content)
    assert len(body["origins"]) == 3
    first_origin = body["origins"][0]["waypoint"]["location"]["latLng"]
    assert first_origin["latitude"] == 50.061
    assert first_origin["longitude"] == 19.938
