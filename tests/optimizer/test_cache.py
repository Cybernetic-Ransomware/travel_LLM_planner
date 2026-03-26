"""Integration tests for distance matrix MongoDB cache — require MongoDB testcontainer."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.core.db.manager import MATRIX_COLLECTION
from src.optimizer.matrix.cache import invalidate_cache, load_cached_matrix, store_matrix
from src.optimizer.matrix.models import MatrixEntry, TransportMode

_PLACE_IDS = ["p1", "p2", "p3"]


@pytest.fixture(autouse=True)
async def clean_matrix_cache(test_db):
    yield
    await test_db[MATRIX_COLLECTION].delete_many({})


def _entry(origin: str, dest: str, distance_m: int = 1000, duration_s: int = 300) -> MatrixEntry:
    return MatrixEntry(origin, dest, distance_m, duration_s)


def _all_pairs(ids: list[str]) -> list[MatrixEntry]:
    return [_entry(o, d) for o in ids for d in ids if o != d]


@pytest.mark.integration
async def test_cache_miss_returns_none(test_db):
    result = await load_cached_matrix(test_db, _PLACE_IDS, TransportMode.WALK)
    assert result is None


@pytest.mark.integration
async def test_store_and_load_returns_matrix(test_db):
    entries = _all_pairs(_PLACE_IDS)
    await store_matrix(test_db, entries, TransportMode.WALK)

    matrix = await load_cached_matrix(test_db, _PLACE_IDS, TransportMode.WALK)

    assert matrix is not None
    assert len(matrix) == len(entries)
    assert matrix.transport_mode == TransportMode.WALK


@pytest.mark.integration
async def test_partial_cache_returns_none(test_db):
    partial_entries = [_entry("p1", "p2"), _entry("p2", "p1")]
    await store_matrix(test_db, partial_entries, TransportMode.WALK)

    result = await load_cached_matrix(test_db, _PLACE_IDS, TransportMode.WALK)
    assert result is None


@pytest.mark.integration
async def test_matrix_values_are_preserved(test_db):
    entries = [
        _entry("p1", "p2", distance_m=800, duration_s=120),
        _entry("p2", "p1", distance_m=820, duration_s=125),
    ]
    await store_matrix(test_db, entries, TransportMode.DRIVE)

    matrix = await load_cached_matrix(test_db, ["p1", "p2"], TransportMode.DRIVE)

    assert matrix is not None
    assert matrix.duration_s("p1", "p2") == 120
    assert matrix.distance_m("p1", "p2") == 800
    assert matrix.duration_s("p2", "p1") == 125


@pytest.mark.integration
async def test_separate_caches_per_transport_mode(test_db):
    entries = _all_pairs(["p1", "p2"])
    await store_matrix(test_db, entries, TransportMode.WALK)

    walk_matrix = await load_cached_matrix(test_db, ["p1", "p2"], TransportMode.WALK)
    drive_matrix = await load_cached_matrix(test_db, ["p1", "p2"], TransportMode.DRIVE)

    assert walk_matrix is not None
    assert drive_matrix is None


@pytest.mark.integration
async def test_stale_entries_not_returned(test_db):
    two_weeks_ago = datetime.now(tz=UTC) - timedelta(days=14)
    await test_db[MATRIX_COLLECTION].insert_one(
        {
            "origin_id": "p1",
            "dest_id": "p2",
            "transport_mode": TransportMode.WALK.value,
            "distance_m": 500,
            "duration_s": 90,
            "computed_at": two_weeks_ago,
        }
    )

    result = await load_cached_matrix(test_db, ["p1", "p2"], TransportMode.WALK)
    assert result is None


@pytest.mark.integration
async def test_upsert_updates_existing_entry(test_db):
    pairs = [_entry("p1", "p2", duration_s=100), _entry("p2", "p1", duration_s=100)]
    await store_matrix(test_db, pairs, TransportMode.WALK)
    updated = [_entry("p1", "p2", duration_s=200), _entry("p2", "p1", duration_s=200)]
    await store_matrix(test_db, updated, TransportMode.WALK)

    count = await test_db[MATRIX_COLLECTION].count_documents({"origin_id": "p1", "dest_id": "p2"})
    assert count == 1

    matrix = await load_cached_matrix(test_db, ["p1", "p2"], TransportMode.WALK)
    assert matrix is not None
    assert matrix.duration_s("p1", "p2") == 200


@pytest.mark.integration
async def test_invalidate_all(test_db):
    await store_matrix(test_db, _all_pairs(["p1", "p2"]), TransportMode.WALK)
    await store_matrix(test_db, _all_pairs(["p1", "p2"]), TransportMode.DRIVE)

    deleted = await invalidate_cache(test_db)

    assert deleted == 4
    assert await test_db[MATRIX_COLLECTION].count_documents({}) == 0


@pytest.mark.integration
async def test_invalidate_by_mode(test_db):
    await store_matrix(test_db, _all_pairs(["p1", "p2"]), TransportMode.WALK)
    await store_matrix(test_db, _all_pairs(["p1", "p2"]), TransportMode.DRIVE)

    deleted = await invalidate_cache(test_db, TransportMode.WALK)

    assert deleted == 2
    remaining = await test_db[MATRIX_COLLECTION].count_documents({})
    assert remaining == 2
