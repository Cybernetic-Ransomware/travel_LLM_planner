"""Mongo -> Turso migration script: coverage, idempotence, hash reconciliation, and
transactionally-honest marker stamping. Needs the Mongo testcontainer + a Turso file DB."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter

from scripts.migrate_trips_to_turso import _run
from src.core.turso.migration_state import MigrationState
from src.trips.models import SaveTripRequest
from src.trips.repository import TripRepository
from src.trips.snapshot import build_snapshot

_request_adapter: TypeAdapter = TypeAdapter(SaveTripRequest)

pytestmark = pytest.mark.integration

_LEGACY = "trips"


def _single_doc(name: str = "Kraków", revision: int = 0) -> dict:
    return {
        "name": name,
        "plan_type": "SINGLE_DAY",
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
        "revision": revision,
        "schema_version": 1,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }


@pytest.fixture(autouse=True)
def _wire_settings(monkeypatch, mongo_container, tmp_path):
    monkeypatch.setattr("scripts.migrate_trips_to_turso.settings.mongo_uri", mongo_container.get_connection_url())
    monkeypatch.setattr("scripts.migrate_trips_to_turso.settings.mongo_db", "test_travel_planner")
    monkeypatch.setattr("scripts.migrate_trips_to_turso.settings.turso_database_url", f"file:{tmp_path / 'migrate.db'}")
    monkeypatch.setattr("scripts.migrate_trips_to_turso.settings.turso_auth_token", "")
    yield


@pytest.fixture(autouse=True)
async def _clean(test_db):
    await test_db[_LEGACY].delete_many({})
    yield
    await test_db[_LEGACY].delete_many({})


async def _turso(tmp_path):
    from src.core.turso.manager import TursoManager

    mgr = TursoManager(f"file:{tmp_path / 'migrate.db'}")
    conn = await mgr.connect()
    await mgr.apply_schema()
    return mgr, conn


async def test_imports_legacy_revision_n_as_single_migration_row(test_db, tmp_path):
    await test_db[_LEGACY].insert_one(_single_doc(revision=6))
    assert await _run(dry_run=False, skip_invalid=False) == 0

    mgr, conn = await _turso(tmp_path)
    try:
        repo = TripRepository(conn)
        trips = await repo.list_all()
        assert len(trips) == 1
        data = await repo.list_revisions(trips[0].id)
        assert data.current_revision == 6
        assert [r.source for r in data.revisions] == ["MIGRATION"]
        assert await MigrationState(conn).is_complete() is True
        marker = await MigrationState(conn).read()
        assert marker["metadata"]["trip_count"] == 1
    finally:
        await mgr.disconnect()


async def test_second_run_is_idempotent(test_db, tmp_path):
    await test_db[_LEGACY].insert_one(_single_doc(revision=2))
    assert await _run(dry_run=False, skip_invalid=False) == 0
    assert await _run(dry_run=False, skip_invalid=False) == 0

    mgr, conn = await _turso(tmp_path)
    try:
        repo = TripRepository(conn)
        trips = await repo.list_all()
        data = await repo.list_revisions(trips[0].id)
        assert len(data.revisions) == 1
    finally:
        await mgr.disconnect()


async def test_re_run_after_new_trip_imports_only_the_new_one(test_db, tmp_path):
    await test_db[_LEGACY].insert_one(_single_doc(name="first"))
    assert await _run(dry_run=False, skip_invalid=False) == 0
    await test_db[_LEGACY].insert_one(_single_doc(name="second"))
    assert await _run(dry_run=False, skip_invalid=False) == 0

    mgr, conn = await _turso(tmp_path)
    try:
        assert await TripRepository(conn).count_trips() == 2
    finally:
        await mgr.disconnect()


async def test_dry_run_writes_nothing_and_no_marker(test_db, tmp_path):
    await test_db[_LEGACY].insert_one(_single_doc())
    assert await _run(dry_run=True, skip_invalid=False) == 0

    mgr, conn = await _turso(tmp_path)
    try:
        assert await TripRepository(conn).count_trips() == 0
        assert await MigrationState(conn).is_complete() is False
    finally:
        await mgr.disconnect()


async def test_malformed_doc_aborts_and_no_marker(test_db, tmp_path):
    await test_db[_LEGACY].insert_one({"name": "broken", "plan_type": "SINGLE_DAY"})  # no request/response
    assert await _run(dry_run=False, skip_invalid=False) == 1

    mgr, conn = await _turso(tmp_path)
    try:
        assert await MigrationState(conn).is_complete() is False
    finally:
        await mgr.disconnect()


async def test_skip_invalid_leaves_marker_unstamped(test_db, tmp_path):
    await test_db[_LEGACY].insert_one(_single_doc(name="ok"))
    await test_db[_LEGACY].insert_one({"name": "broken", "plan_type": "SINGLE_DAY"})
    assert await _run(dry_run=False, skip_invalid=True) == 1

    mgr, conn = await _turso(tmp_path)
    try:
        assert await TripRepository(conn).count_trips() == 1  # the good one still imported
        assert await MigrationState(conn).is_complete() is False
    finally:
        await mgr.disconnect()


async def test_empty_source_stamps_marker_with_zero_count(test_db, tmp_path):
    assert await _run(dry_run=False, skip_invalid=False) == 0
    mgr, conn = await _turso(tmp_path)
    try:
        assert await MigrationState(conn).is_complete() is True
        assert (await MigrationState(conn).read())["metadata"]["trip_count"] == 0
    finally:
        await mgr.disconnect()


def _request(doc: dict):
    payload = {k: v for k, v in doc.items() if k not in {"_id", "revision", "schema_version", "created_at"}}
    return _request_adapter.validate_python(payload)


async def test_baseline_hash_mismatch_hard_fails_on_rerun(test_db, tmp_path):
    doc = _single_doc(revision=3)
    inserted = await test_db[_LEGACY].insert_one(doc)
    assert await _run(dry_run=False, skip_invalid=False) == 0
    _canonical, original_hash, _display = build_snapshot(_request(doc))

    # The source document changes (rename) but the immutable MIGRATION baseline must not move.
    await test_db[_LEGACY].update_one({"_id": inserted.inserted_id}, {"$set": {"name": "renamed"}})
    assert await _run(dry_run=False, skip_invalid=False) == 1

    mgr, conn = await _turso(tmp_path)
    try:
        assert await TripRepository(conn).has_matching_migration_baseline(str(inserted.inserted_id), 3, original_hash)
    finally:
        await mgr.disconnect()


async def test_stray_baseline_fails_verification(test_db, tmp_path):
    await test_db[_LEGACY].insert_one(_single_doc(name="real"))
    assert await _run(dry_run=False, skip_invalid=False) == 0

    # Inject a MIGRATION baseline for a trip that has no source document, then re-run.
    mgr, conn = await _turso(tmp_path)
    try:
        await TripRepository(conn).import_migration_baseline(
            "dead0dead0dead0dead0dead0", _request(_single_doc()), 0, created_at="2026-01-01T00:00:00+00:00"
        )
    finally:
        await mgr.disconnect()

    assert await _run(dry_run=False, skip_invalid=False) == 1
