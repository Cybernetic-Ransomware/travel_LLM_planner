"""Runtime startup is Turso-only: the boot gate is one SELECT on the Turso app_migrations
marker; the Mongo `trips` collection is never read at startup or by any trips route."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from src.config import lifespan as lifespan_module
from src.core.turso.migration_state import MigrationState
from src.trips.models import SingleDaySaveTripRequest
from src.trips.repository import TripRepository

pytestmark = pytest.mark.integration

_SINGLE = {
    "name": "post-cutover",
    "date": "2026-07-04",
    "optimizer_request": {"place_ids": ["p1"], "transport_mode": "WALK", "day_start_hour": 9, "day_end_hour": 21},
    "optimizer_response": {
        "steps": [],
        "total_travel_time_s": 0,
        "total_visit_time_min": 0,
        "total_wait_min": 0,
        "transport_mode": "WALK",
        "skipped": [],
    },
}


@pytest.fixture
def _wire(monkeypatch, mongo_container, tmp_path):
    monkeypatch.setattr(lifespan_module.settings, "mongo_uri", mongo_container.get_connection_url())
    monkeypatch.setattr(lifespan_module.settings, "mongo_db", "test_travel_planner")
    monkeypatch.setattr(lifespan_module.settings, "turso_database_url", f"file:{tmp_path / 'boot.db'}")
    monkeypatch.setattr(lifespan_module.settings, "turso_auth_token", "")
    # no LLM key -> orchestrator is skipped, keeping the lifespan lean
    monkeypatch.setattr(lifespan_module.settings, "openai_api_key", "")
    monkeypatch.setattr(lifespan_module.settings, "anthropic_api_key", "")
    return monkeypatch


async def test_missing_marker_blocks_startup(_wire):
    _wire.setattr(lifespan_module.settings, "trips_require_migration_marker", True)
    app = FastAPI()
    with pytest.raises(RuntimeError, match="migration marker missing"):
        async with lifespan_module.lifespan(app):
            pass


async def test_marker_present_allows_startup_without_reading_mongo_trips(_wire, tmp_path, mongo_container):
    """Post-cutover shape: `trips` dropped from Mongo; startup passes on the Turso marker alone."""
    _wire.setattr(lifespan_module.settings, "trips_require_migration_marker", True)

    from src.core.db.manager import MongoDBManager
    from src.core.turso.manager import TursoManager

    # Drop any `trips` collection a sibling migration test left behind.
    seed = MongoDBManager(mongo_container.get_connection_url(), "test_travel_planner", 2)
    seed_db = await seed.connect()
    await seed_db["trips"].drop()
    await seed.disconnect()

    mgr = TursoManager(f"file:{tmp_path / 'boot.db'}")
    conn = await mgr.connect()
    await mgr.apply_schema()
    await MigrationState(conn).mark_complete(metadata={"trip_count": 0})
    await mgr.disconnect()

    app = FastAPI()
    async with lifespan_module.lifespan(app):
        assert app.state.trip_db is not None
        # A trips route resolves purely from app.state.trip_db (Turso), never Mongo.
        result = await app.state.trip_db.execute("SELECT count(*) AS n FROM trips")
        assert result.scalar() == 0
        # Startup opened Mongo for the other domains but never created/read `trips`.
        assert "trips" not in await app.state.db.list_collection_names()


async def test_escape_hatch_allows_startup_without_marker(_wire):
    _wire.setattr(lifespan_module.settings, "trips_require_migration_marker", False)
    app = FastAPI()
    async with lifespan_module.lifespan(app):
        assert app.state.trip_db is not None


async def test_boots_with_mongo_trips_collection_absent(_wire, tmp_path):
    """Mongo has no `trips` collection at all; /trips is served entirely from Turso."""
    _wire.setattr(lifespan_module.settings, "trips_require_migration_marker", False)
    app = FastAPI()
    async with lifespan_module.lifespan(app):
        repo = TripRepository(app.state.trip_db)
        saved = await repo.save(SingleDaySaveTripRequest(**_SINGLE))
        assert saved.revision == 0
        assert (await repo.get(saved.id)).name == "post-cutover"
