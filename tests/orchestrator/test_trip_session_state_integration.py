"""Integration tests for TripSessionStateStore — require the MongoDB testcontainer."""

from __future__ import annotations

import pytest

from src.core.db.manager import THREAD_TRIP_STATE_COLLECTION
from src.orchestrator.trip_session_state import TripSessionStateStore

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def clean(test_db):
    yield
    await test_db[THREAD_TRIP_STATE_COLLECTION].delete_many({})


@pytest.fixture
def store(test_db) -> TripSessionStateStore:
    return TripSessionStateStore(test_db, retention_days=30)


async def test_bind_trip_then_arm_then_single_use_consume(store):
    await store.bind_trip("t1", "trip-1", "MULTI_DAY", "Tokyo", 3, ["p1", "p2"])
    assert await store.arm_pending("t1", "call-1") is True

    scope = await store.consume_pending("t1")
    assert scope is not None
    assert (scope.kind, scope.trip_id, scope.revision, scope.tool_call_id) == ("trip", "trip-1", 3, "call-1")
    assert scope.allowed_place_ids == ["p1", "p2"]

    # single use: the document remains, but pending is gone
    assert await store.consume_pending("t1") is None
    assert await store.get_binding("t1") is not None


async def test_bind_clears_stale_pending(store):
    await store.bind_trip("t1", "trip-1", "MULTI_DAY", "Tokyo", 1, [])
    await store.arm_pending("t1", "call-1")
    await store.bind_trip("t1", "trip-1", "MULTI_DAY", "Tokyo", 2, [])
    assert await store.consume_pending("t1") is None


async def test_arm_pending_without_binding_returns_false(store):
    assert await store.arm_pending("never-bound", "call-1") is False


async def test_place_selection_binding_carries_scope(store):
    await store.bind_place_selection("t2", ["p9"])
    await store.arm_pending("t2", "call-2")
    scope = await store.consume_pending("t2")
    assert scope is not None
    assert scope.kind == "place_selection"
    assert scope.trip_id is None
    assert scope.allowed_place_ids == ["p9"]


async def test_thread_isolation(store):
    await store.bind_trip("tA", "trip-A", "MULTI_DAY", "A", 0, [])
    await store.bind_trip("tB", "trip-B", "MULTI_DAY", "B", 0, [])
    await store.arm_pending("tA", "cA")
    await store.arm_pending("tB", "cB")

    a = await store.consume_pending("tA")
    assert a is not None and a.trip_id == "trip-A"
    b = await store.get_binding("tB")
    assert b is not None and b.trip_id == "trip-B"


async def test_clear_pending_forces_fail_closed(store):
    await store.bind_trip("t1", "trip-1", "MULTI_DAY", "Tokyo", 0, [])
    await store.arm_pending("t1", "call-1")
    await store.clear_pending("t1")
    assert await store.consume_pending("t1") is None


async def test_thread_id_index_is_unique(test_db, store):
    await store.bind_trip("dup", "trip-1", "MULTI_DAY", "x", 0, [])
    await store.bind_trip("dup", "trip-2", "MULTI_DAY", "y", 1, [])
    count = await test_db[THREAD_TRIP_STATE_COLLECTION].count_documents({"thread_id": "dup"})
    assert count == 1
    binding = await store.get_binding("dup")
    assert binding is not None and binding.trip_id == "trip-2"
