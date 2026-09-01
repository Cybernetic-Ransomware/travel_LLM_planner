"""TripRepository against a real sqlite-file Turso backend (the libsql backend runs the
same suite in the Linux CI driver-parity job)."""

from __future__ import annotations

import contextlib
from unittest.mock import patch

import pytest

from src.core.exceptions import (
    MissingExpectedRevisionError,
    RevisionAlreadyCurrentError,
    RevisionNotFoundError,
    TripConcurrencyConflictError,
    TripNotFoundError,
    TripPlanTypeConflictError,
)
from src.core.turso.manager import TursoManager
from src.core.turso.migration_state import MigrationState
from src.trips.models import MultiDaySaveTripRequest, SingleDaySaveTripRequest
from src.trips.repository import MigrationBaselineConflictError, TripRepository
from src.trips.snapshot import build_snapshot

pytestmark = pytest.mark.integration


def _single(name: str = "Weekend in Kraków", **over) -> SingleDaySaveTripRequest:
    payload = {
        "name": name,
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
    payload.update(over)
    return SingleDaySaveTripRequest(**payload)


def _multi(name: str = "Kraków then Warsaw", **over) -> MultiDaySaveTripRequest:
    payload = {
        "name": name,
        "multi_day_request": {
            "days": [{"date": "2026-07-01"}, {"date": "2026-07-02"}, {"date": "2026-07-03"}],
            "places": [
                {"place_id": "p1", "day_preferences": []},
                {"place_id": "p2", "day_preferences": []},
            ],
            "transport_mode": "WALK",
            "accommodations": [
                {
                    "name": "Hotel A",
                    "lat": 50.06,
                    "lng": 19.94,
                    "check_in_date": "2026-07-01",
                    "check_out_date": "2026-07-03",
                }
            ],
            "transfers": [],
        },
        "multi_day_response": {"days": [], "transport_mode": "WALK", "unassigned": []},
    }
    payload.update(over)
    return MultiDaySaveTripRequest(**payload)


async def _revision_rows(conn, trip_id: str) -> list[dict]:
    result = await conn.execute(
        "SELECT revision, source, summary, restored_from_revision, snapshot_hash, recorded_at "
        "FROM trip_revisions WHERE trip_id = ? ORDER BY revision",
        (trip_id,),
    )
    return result.rows


async def _trip_row(conn, trip_id: str) -> dict | None:
    result = await conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
    return result.rows[0] if result.rows else None


@pytest.fixture
def repo(trip_db) -> TripRepository:
    return TripRepository(trip_db)


class TestSave:
    async def test_creates_revision_zero_and_created_row(self, repo, trip_db):
        saved = await repo.save(_single())
        assert saved.revision == 0
        rows = await _revision_rows(trip_db, saved.id)
        assert len(rows) == 1
        assert rows[0]["revision"] == 0
        assert rows[0]["source"] == "CREATED"
        trip = await _trip_row(trip_db, saved.id)
        assert trip["revision"] == 0
        assert trip["updated_at"] is None
        assert trip["snapshot_hash"] == rows[0]["snapshot_hash"]

    async def test_ignores_expected_revision(self, repo):
        saved = await repo.save(_single(expected_revision=99))
        assert saved.revision == 0

    async def test_multi_day_round_trips(self, repo):
        saved = await repo.save(_multi())
        got = await repo.get(saved.id)
        assert got.plan_type == "MULTI_DAY"
        assert got.num_days == 3
        assert got.start_date == "2026-07-01"

    async def test_list_all_is_column_only_and_newest_first(self, repo):
        await repo.save(_single(name="First"))
        await repo.save(_multi(name="Second"))
        listed = await repo.list_all()
        assert [t.name for t in listed] == ["Second", "First"]
        assert listed[0].plan_type == "MULTI_DAY"
        assert listed[0].start_date == "2026-07-01"


class TestUpdate:
    async def test_matching_token_bumps_revision_and_adds_row(self, repo, trip_db):
        saved = await repo.save(_single())
        updated = await repo.update(
            saved.id, _single(name="Renamed", expected_revision=0), source="MANUAL", summary="rename"
        )
        assert updated.revision == 1
        assert updated.name == "Renamed"
        rows = await _revision_rows(trip_db, saved.id)
        assert [r["revision"] for r in rows] == [0, 1]
        assert rows[1]["source"] == "MANUAL"
        assert rows[1]["summary"] == "rename"
        trip = await _trip_row(trip_db, saved.id)
        assert trip["updated_at"] is not None
        assert trip["snapshot_hash"] == rows[1]["snapshot_hash"]

    async def test_missing_token_raises_428(self, repo):
        saved = await repo.save(_single())
        with pytest.raises(MissingExpectedRevisionError):
            await repo.update(saved.id, _single(name="x"), source="MANUAL", summary="s")

    async def test_stale_token_raises_409_and_leaves_everything(self, repo, trip_db):
        saved = await repo.save(_single())
        await repo.update(saved.id, _single(name="First", expected_revision=0), source="MANUAL", summary="s")
        before_trip = await _trip_row(trip_db, saved.id)
        before_rows = await _revision_rows(trip_db, saved.id)
        with pytest.raises(TripConcurrencyConflictError):
            await repo.update(saved.id, _single(name="Second", expected_revision=0), source="MANUAL", summary="s")
        assert await _trip_row(trip_db, saved.id) == before_trip
        assert await _revision_rows(trip_db, saved.id) == before_rows

    async def test_plan_type_change_raises_409(self, repo):
        saved = await repo.save(_single())
        with pytest.raises(TripPlanTypeConflictError):
            await repo.update(saved.id, _multi(expected_revision=0), source="MANUAL", summary="s")

    async def test_unknown_id_returns_none(self, repo):
        assert (
            await repo.update("000000000000000000000000", _single(expected_revision=0), source="MANUAL", summary="s")
            is None
        )

    async def test_noop_with_matching_token_writes_nothing(self, repo, trip_db):
        saved = await repo.save(_single())
        result = await repo.update(saved.id, _single(expected_revision=0), source="MANUAL", summary="s")
        assert result.revision == 0
        assert len(await _revision_rows(trip_db, saved.id)) == 1

    async def test_noop_with_stale_token_still_409(self, repo):
        saved = await repo.save(_single())
        await repo.update(saved.id, _single(name="moved", expected_revision=0), source="MANUAL", summary="s")
        with pytest.raises(TripConcurrencyConflictError):
            # byte-identical to revision 0 but the token is stale
            await repo.update(saved.id, _single(expected_revision=0), source="MANUAL", summary="s")

    async def test_history_insert_failure_rolls_back_trips_update(self, repo, trip_db):
        saved = await repo.save(_single())
        before = await _trip_row(trip_db, saved.id)
        with (
            patch.object(TripRepository, "_insert_revision", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await repo.update(saved.id, _single(name="x", expected_revision=0), source="MANUAL", summary="s")
        assert await _trip_row(trip_db, saved.id) == before
        assert len(await _revision_rows(trip_db, saved.id)) == 1


class TestUpdateConcurrency:
    async def test_noop_path_is_linearized_against_a_concurrent_bump(self, tmp_path):
        """A stale-revision no-op racing a concurrent N -> N+1 must 409, not fake-succeed."""
        url = f"file:{tmp_path / 'race.db'}"
        mgr_a = TursoManager(url)
        conn_a = await mgr_a.connect()
        await mgr_a.apply_schema()
        await MigrationState(conn_a).mark_complete(metadata={})
        mgr_b = TursoManager(url)
        conn_b = await mgr_b.connect()
        repo_a, repo_b = TripRepository(conn_a), TripRepository(conn_b)

        saved = await repo_a.save(_single(name="v0"))

        # B commits N -> N+1 the first time A opens its tx, before A's in-tx SELECT reads.
        real_transaction = conn_a.transaction
        fired = False

        @contextlib.asynccontextmanager
        async def racing_transaction():
            nonlocal fired
            async with real_transaction() as tx:
                if not fired:
                    fired = True
                    await repo_b.update(saved.id, _single(name="v1", expected_revision=0), source="MANUAL", summary="b")
                yield tx

        conn_a.transaction = racing_transaction
        try:
            with pytest.raises(TripConcurrencyConflictError):
                await repo_a.update(saved.id, _single(name="v0", expected_revision=0), source="MANUAL", summary="a")
        finally:
            conn_a.transaction = real_transaction

        rows = await _revision_rows(conn_b, saved.id)
        assert [r["revision"] for r in rows] == [0, 1]  # only save() + B's update, nothing from A
        assert rows[1]["summary"] == "b"

        await mgr_a.disconnect()
        await mgr_b.disconnect()


class TestRevisionReads:
    async def test_list_revisions_desc_and_no_snapshot(self, repo):
        saved = await repo.save(_single())
        await repo.update(saved.id, _single(name="v1", expected_revision=0), source="MANUAL", summary="a")
        await repo.update(saved.id, _single(name="v2", expected_revision=1), source="ORCHESTRATOR", summary="b")
        data = await repo.list_revisions(saved.id)
        assert data.current_revision == 2
        assert [r.revision for r in data.revisions] == [2, 1, 0]
        assert not hasattr(data.revisions[0], "snapshot")
        assert all(r.recorded_at for r in data.revisions)

    async def test_list_revisions_unknown_trip_is_none(self, repo):
        assert await repo.list_revisions("000000000000000000000000") is None

    async def test_get_revision_returns_exact_snapshot(self, repo):
        saved = await repo.save(_single(name="original"))
        await repo.update(saved.id, _single(name="changed", expected_revision=0), source="MANUAL", summary="s")
        detail = await repo.get_revision(saved.id, 0)
        assert detail.name == "original"
        assert detail.revision == 0
        assert detail.source == "CREATED"
        assert detail.recorded_at

    async def test_get_revision_unknown_is_none(self, repo):
        saved = await repo.save(_single())
        assert await repo.get_revision(saved.id, 7) is None


class TestRestore:
    async def test_restore_older_mints_revert_revision(self, repo, trip_db):
        saved = await repo.save(_single(name="v0"))
        await repo.update(saved.id, _single(name="v1", expected_revision=0), source="MANUAL", summary="s")
        restored = await repo.restore_revision(saved.id, 0, expected_revision=1)
        assert restored.revision == 2
        assert restored.name == "v0"
        rows = await _revision_rows(trip_db, saved.id)
        assert rows[-1]["source"] == "REVERT"
        assert rows[-1]["restored_from_revision"] == 0
        # current snapshot hash == the restored revision's hash
        trip = await _trip_row(trip_db, saved.id)
        assert trip["snapshot_hash"] == rows[0]["snapshot_hash"]

    async def test_restore_does_not_call_optimizer(self, repo):
        saved = await repo.save(_multi(name="v0"))
        await repo.update(saved.id, _multi(name="v1", expected_revision=0), source="MANUAL", summary="s")
        with patch("src.optimizer.solver.multi_day_service.optimize_trip", side_effect=AssertionError("optimizer called")):
            restored = await repo.restore_revision(saved.id, 0, expected_revision=1)
        assert restored.revision == 2

    async def test_restore_stale_token_conflicts_and_writes_nothing(self, repo, trip_db):
        saved = await repo.save(_single(name="v0"))
        await repo.update(saved.id, _single(name="v1", expected_revision=0), source="MANUAL", summary="s")
        before = await _revision_rows(trip_db, saved.id)
        with pytest.raises(TripConcurrencyConflictError):
            await repo.restore_revision(saved.id, 0, expected_revision=0)
        assert await _revision_rows(trip_db, saved.id) == before

    async def test_restore_byte_identical_older_still_mints_revert(self, repo, trip_db):
        saved = await repo.save(_single(name="same"))
        # update to a genuinely different state, then back — revision 0 and 2 share a hash
        await repo.update(saved.id, _single(name="different", expected_revision=0), source="MANUAL", summary="s")
        restored = await repo.restore_revision(saved.id, 0, expected_revision=1)
        assert restored.revision == 2
        rows = await _revision_rows(trip_db, saved.id)
        assert rows[-1]["source"] == "REVERT"
        assert rows[-1]["snapshot_hash"] == rows[0]["snapshot_hash"]

    async def test_restore_current_revision_raises_400(self, repo):
        saved = await repo.save(_single())
        await repo.update(saved.id, _single(name="v1", expected_revision=0), source="MANUAL", summary="s")
        with pytest.raises(RevisionAlreadyCurrentError):
            await repo.restore_revision(saved.id, 1, expected_revision=1)

    async def test_restore_unknown_revision_raises_404(self, repo):
        saved = await repo.save(_single())
        with pytest.raises(RevisionNotFoundError):
            await repo.restore_revision(saved.id, 9, expected_revision=0)

    async def test_restore_unknown_trip_raises_404(self, repo):
        with pytest.raises(TripNotFoundError):
            await repo.restore_revision("000000000000000000000000", 0, expected_revision=0)


class TestDelete:
    async def test_delete_removes_trip_and_all_history(self, repo, trip_db):
        saved = await repo.save(_single())
        await repo.update(saved.id, _single(name="v1", expected_revision=0), source="MANUAL", summary="s")
        assert await repo.delete(saved.id) is True
        assert await _trip_row(trip_db, saved.id) is None
        assert await _revision_rows(trip_db, saved.id) == []

    async def test_delete_unknown_returns_false(self, repo):
        assert await repo.delete("000000000000000000000000") is False


class TestMigrationBaseline:
    async def test_first_import_creates_trip_and_single_migration_row(self, repo, trip_db):
        trip_id = "0123456789abcdef01234567"
        outcome = await repo.import_migration_baseline(trip_id, _multi(), 6, created_at="2026-01-01T00:00:00+00:00")
        assert outcome == "created"
        trip = await _trip_row(trip_db, trip_id)
        assert trip["revision"] == 6
        assert trip["created_at"] == "2026-01-01T00:00:00+00:00"
        assert trip["updated_at"] is None
        rows = await _revision_rows(trip_db, trip_id)
        assert len(rows) == 1
        assert rows[0]["revision"] == 6
        assert rows[0]["source"] == "MIGRATION"
        assert rows[0]["recorded_at"]
        assert trip["snapshot_hash"] == rows[0]["snapshot_hash"]

    async def test_second_identical_import_is_skipped(self, repo, trip_db):
        trip_id = "0123456789abcdef01234567"
        await repo.import_migration_baseline(trip_id, _multi(), 6, created_at="2026-01-01T00:00:00+00:00")
        outcome = await repo.import_migration_baseline(trip_id, _multi(), 6, created_at="2026-01-01T00:00:00+00:00")
        assert outcome == "skipped_identical"
        assert len(await _revision_rows(trip_db, trip_id)) == 1

    async def test_different_hash_same_revision_hard_fails(self, repo, trip_db):
        trip_id = "0123456789abcdef01234567"
        await repo.import_migration_baseline(trip_id, _multi(name="a"), 6, created_at="2026-01-01T00:00:00+00:00")
        with pytest.raises(MigrationBaselineConflictError):
            await repo.import_migration_baseline(trip_id, _multi(name="b"), 6, created_at="2026-01-01T00:00:00+00:00")

    async def test_trip_without_baseline_hard_fails(self, repo):
        saved = await repo.save(_single())  # a normal trip -> has a CREATED row, not MIGRATION
        with pytest.raises(MigrationBaselineConflictError):
            await repo.import_migration_baseline(saved.id, _single(), 0, created_at="2026-01-01T00:00:00+00:00")

    async def test_history_insert_failure_rolls_back_trip_insert(self, repo, trip_db):
        trip_id = "0123456789abcdef01234567"
        with (
            patch.object(TripRepository, "_insert_revision", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await repo.import_migration_baseline(trip_id, _multi(), 6, created_at="2026-01-01T00:00:00+00:00")
        assert await _trip_row(trip_db, trip_id) is None

    async def test_baseline_survives_later_update(self, repo):
        trip_id = "0123456789abcdef01234567"
        req = _multi()
        await repo.import_migration_baseline(trip_id, req, 6, created_at="2026-01-01T00:00:00+00:00")
        _canonical, digest, _display = build_snapshot(req)
        assert await repo.has_matching_migration_baseline(trip_id, 6, digest) is True
        await repo.update(trip_id, _multi(name="after", expected_revision=6), source="MANUAL", summary="s")
        assert await repo.has_matching_migration_baseline(trip_id, 6, digest) is True
        data = await repo.list_revisions(trip_id)
        assert data.current_revision == 7
        assert [r.revision for r in data.revisions] == [7, 6]

    async def test_migration_baseline_ids_and_count(self, repo):
        await repo.import_migration_baseline(
            "aaaaaaaaaaaaaaaaaaaaaaaa", _single(), 1, created_at="2026-01-01T00:00:00+00:00"
        )
        await repo.import_migration_baseline(
            "bbbbbbbbbbbbbbbbbbbbbbbb", _single(), 2, created_at="2026-01-01T00:00:00+00:00"
        )
        await repo.save(_single())
        assert await repo.migration_baseline_ids() == {"aaaaaaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbbbbbb"}
        assert await repo.count_trips() == 3


class TestProvenanceAndTimestamps:
    async def test_save_and_restore_hardcode_source(self, repo, trip_db):
        saved = await repo.save(_single())
        await repo.update(saved.id, _single(name="v1", expected_revision=0), source="ORCHESTRATOR", summary="s")
        await repo.restore_revision(saved.id, 0, expected_revision=1)
        rows = await _revision_rows(trip_db, saved.id)
        assert [r["source"] for r in rows] == ["CREATED", "ORCHESTRATOR", "REVERT"]

    async def test_trip_created_at_unchanged_by_update_and_restore(self, repo, trip_db):
        saved = await repo.save(_single())
        original_created = (await _trip_row(trip_db, saved.id))["created_at"]
        await repo.update(saved.id, _single(name="v1", expected_revision=0), source="MANUAL", summary="s")
        await repo.restore_revision(saved.id, 0, expected_revision=1)
        assert (await _trip_row(trip_db, saved.id))["created_at"] == original_created

    async def test_recorded_at_is_monotonic_across_revisions(self, repo):
        saved = await repo.save(_single())
        await repo.update(saved.id, _single(name="v1", expected_revision=0), source="MANUAL", summary="s")
        data = await repo.list_revisions(saved.id)
        recorded = [r.recorded_at for r in sorted(data.revisions, key=lambda r: r.revision)]
        assert recorded[0] <= recorded[1]
