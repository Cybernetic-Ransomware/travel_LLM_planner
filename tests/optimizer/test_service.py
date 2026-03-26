"""Unit tests for the distance matrix service orchestration layer.

Dependencies (cache and client) are replaced with async fakes so no
MongoDB or real HTTP calls are made.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.optimizer.matrix.client import GoogleRoutesManager
from src.optimizer.matrix.models import DistanceMatrix, MatrixEntry, TransportMode
from src.optimizer.matrix.service import get_matrix

_COORDS = [
    ("p1", 50.061, 19.938),
    ("p2", 50.054, 19.944),
]

_ENTRIES = [
    MatrixEntry("p1", "p2", 800, 120),
    MatrixEntry("p2", "p1", 810, 125),
]

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _make_matrix(entries: list[MatrixEntry]) -> DistanceMatrix:
    return DistanceMatrix(
        {(e.origin_id, e.dest_id): e for e in entries},
        TransportMode.WALK,
        _NOW,
    )


@pytest.fixture
async def routes_manager():
    m = GoogleRoutesManager(api_key="test-key")
    await m.connect()
    yield m
    await m.disconnect()


@pytest.mark.unit
async def test_empty_coords_returns_error(test_db, routes_manager):
    matrix, status, error = await get_matrix(test_db, routes_manager, [], TransportMode.WALK)
    assert matrix is None
    assert status == "NO_PLACES"


@pytest.mark.unit
async def test_cache_hit_returns_without_api_call(test_db, routes_manager):
    cached = _make_matrix(_ENTRIES)

    with (
        patch("src.optimizer.matrix.service.load_cached_matrix", new=AsyncMock(return_value=cached)),
        patch("src.optimizer.matrix.service.store_matrix", new=AsyncMock()) as mock_store,
        patch.object(routes_manager, "compute_matrix", new=AsyncMock()) as mock_api,
    ):
        matrix, status, error = await get_matrix(test_db, routes_manager, _COORDS, TransportMode.WALK)

    assert status == "OK"
    assert matrix is cached
    mock_api.assert_not_called()
    mock_store.assert_not_called()


@pytest.mark.unit
async def test_cache_miss_calls_api_and_stores(test_db, routes_manager):
    with (
        patch("src.optimizer.matrix.service.load_cached_matrix", new=AsyncMock(return_value=None)),
        patch("src.optimizer.matrix.service.store_matrix", new=AsyncMock()) as mock_store,
        patch.object(routes_manager, "compute_matrix", new=AsyncMock(return_value=(_ENTRIES, "OK", None))),
    ):
        matrix, status, error = await get_matrix(test_db, routes_manager, _COORDS, TransportMode.WALK)

    assert status == "OK"
    assert matrix is not None
    assert len(matrix) == len(_ENTRIES)
    mock_store.assert_awaited_once()


@pytest.mark.unit
async def test_cache_miss_api_error_propagates(test_db, routes_manager):
    with (
        patch("src.optimizer.matrix.service.load_cached_matrix", new=AsyncMock(return_value=None)),
        patch.object(
            routes_manager, "compute_matrix", new=AsyncMock(return_value=(None, "PERMISSION_DENIED", "key invalid"))
        ),
        patch("src.optimizer.matrix.service.store_matrix", new=AsyncMock()) as mock_store,
    ):
        matrix, status, error = await get_matrix(test_db, routes_manager, _COORDS, TransportMode.WALK)

    assert matrix is None
    assert status == "PERMISSION_DENIED"
    assert error == "key invalid"
    mock_store.assert_not_called()


@pytest.mark.unit
async def test_returned_matrix_has_correct_entries(test_db, routes_manager):
    with (
        patch("src.optimizer.matrix.service.load_cached_matrix", new=AsyncMock(return_value=None)),
        patch("src.optimizer.matrix.service.store_matrix", new=AsyncMock()),
        patch.object(routes_manager, "compute_matrix", new=AsyncMock(return_value=(_ENTRIES, "OK", None))),
    ):
        matrix, status, _ = await get_matrix(test_db, routes_manager, _COORDS, TransportMode.WALK)

    assert matrix is not None
    assert matrix.duration_s("p1", "p2") == 120
    assert matrix.duration_s("p2", "p1") == 125
    assert matrix.transport_mode == TransportMode.WALK


@pytest.mark.unit
async def test_departure_time_passed_to_api(test_db, routes_manager):
    departure = datetime(2026, 6, 15, 10, 0, 0, tzinfo=UTC)

    with (
        patch("src.optimizer.matrix.service.load_cached_matrix", new=AsyncMock(return_value=None)),
        patch("src.optimizer.matrix.service.store_matrix", new=AsyncMock()),
        patch.object(routes_manager, "compute_matrix", new=AsyncMock(return_value=(_ENTRIES, "OK", None))) as mock_api,
    ):
        await get_matrix(test_db, routes_manager, _COORDS, TransportMode.TRANSIT, departure_time=departure)

    _, call_kwargs = mock_api.call_args
    assert mock_api.call_args[0][2] == departure
