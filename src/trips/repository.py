"""The one persistence boundary for the trips domain (ADR-21). Every write pairs a
current-state row with an immutable ``trip_revisions`` row in a single Turso transaction;
there is no raw SQL against these tables elsewhere (the migration script calls
``import_migration_baseline``). Provenance is server-enforced — ``save`` / ``restore_revision``
/ ``import_migration_baseline`` hard-code their ``source``; ``update`` takes only
``TripUpdateSource``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from bson import ObjectId

from src.core.exceptions import (
    MissingExpectedRevisionError,
    RevisionAlreadyCurrentError,
    RevisionNotFoundError,
    TripConcurrencyConflictError,
    TripNotFoundError,
    TripPlanTypeConflictError,
)
from src.core.turso.adapter import TripDbConnection, TripDbTransaction
from src.trips.models import (
    MultiDayTripRevisionDetailOut,
    MultiDayTripSummaryOut,
    RevisionSource,
    SaveTripRequest,
    SingleDayTripRevisionDetailOut,
    SingleDayTripSummaryOut,
    TripDetailOut,
    TripRevisionDetailOut,
    TripRevisionListOut,
    TripRevisionSummaryOut,
    TripSummaryOut,
    TripUpdateSource,
)
from src.trips.snapshot import (
    SnapshotDisplayFields,
    build_snapshot,
    detail_from_snapshot,
    display_fields,
    load_snapshot,
)

_TRIP_COLUMNS = (
    "id, name, plan_type, schema_version, revision, snapshot, snapshot_hash, compression, "
    "display_start_date, display_end_date, display_num_days, created_at, updated_at"
)


class MigrationBaselineConflictError(RuntimeError):
    """Raised only in the migration CLI (never HTTP): the source and the Turso baseline
    disagree, and overwriting an immutable ``MIGRATION`` row is forbidden."""

    def __init__(self, trip_id: str, revision: int, reason: str) -> None:
        super().__init__(f"trip {trip_id!r} revision {revision}: {reason}")
        self.trip_id = trip_id
        self.revision = revision
        self.reason = reason


class _CasMiss(Exception):
    """Internal: the CAS ``UPDATE`` affected zero rows — roll back and report a conflict."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class TripRepository:
    def __init__(self, connection: TripDbConnection) -> None:
        self._conn = connection

    async def save(self, request: SaveTripRequest) -> TripDetailOut:
        """Create a new trip at revision 0 with its matching ``CREATED`` revision row."""
        trip_id = str(ObjectId())
        canonical, digest, display = build_snapshot(request)
        payload = load_snapshot(canonical)
        now = _now()

        async with self._conn.transaction() as tx:
            await self._insert_trip_row(
                tx,
                trip_id=trip_id,
                name=payload["name"],
                plan_type=payload["plan_type"],
                schema_version=payload["schema_version"],
                revision=0,
                snapshot=canonical,
                snapshot_hash=digest,
                display=display,
                created_at=now,
                updated_at=None,
            )
            await self._insert_revision(
                tx,
                trip_id=trip_id,
                revision=0,
                source="CREATED",
                summary="Trip created",
                restored_from_revision=None,
                schema_version=payload["schema_version"],
                snapshot=canonical,
                snapshot_hash=digest,
                recorded_at=now,
            )

        return detail_from_snapshot(trip_id, payload, revision=0, created_at=now, updated_at=None)

    async def list_all(self) -> list[TripSummaryOut]:
        result = await self._conn.execute(
            "SELECT id, name, plan_type, display_start_date, display_end_date, display_num_days, created_at "
            "FROM trips ORDER BY created_at DESC"
        )
        trips: list[TripSummaryOut] = []
        for row in result.rows:
            if row["plan_type"] == "MULTI_DAY":
                trips.append(
                    MultiDayTripSummaryOut(
                        id=row["id"],
                        name=row["name"],
                        created_at=row["created_at"],
                        start_date=row["display_start_date"],
                        end_date=row["display_end_date"],
                        num_days=row["display_num_days"],
                    )
                )
            else:
                trips.append(
                    SingleDayTripSummaryOut(
                        id=row["id"],
                        name=row["name"],
                        date=row["display_start_date"],
                        created_at=row["created_at"],
                    )
                )
        return trips

    async def get(self, trip_id: str) -> TripDetailOut | None:
        row = await self._trip_row(trip_id)
        if row is None:
            return None
        payload = load_snapshot(row["snapshot"], row["compression"])
        return detail_from_snapshot(
            trip_id,
            payload,
            revision=row["revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def update(
        self,
        trip_id: str,
        request: SaveTripRequest,
        *,
        source: TripUpdateSource,
        summary: str,
    ) -> TripDetailOut | None:
        """Compare-and-set update (``PUT`` + chat editor): missing token -> 428, stale -> 409,
        byte-identical snapshot + matching token -> no-op; else one tx writes both rows."""
        row = await self._trip_row(trip_id)
        if row is None:
            return None
        if row["plan_type"] != request.plan_type:
            raise TripPlanTypeConflictError(trip_id, row["plan_type"], request.plan_type)
        if request.expected_revision is None:
            raise MissingExpectedRevisionError(trip_id)
        expected = request.expected_revision

        canonical, digest, display = build_snapshot(request)
        payload = load_snapshot(canonical)

        if digest == row["snapshot_hash"]:
            if expected == row["revision"]:
                return detail_from_snapshot(
                    trip_id,
                    load_snapshot(row["snapshot"], row["compression"]),
                    revision=row["revision"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            raise TripConcurrencyConflictError(trip_id, expected=expected)

        new_revision = row["revision"] + 1
        now = _now()
        try:
            async with self._conn.transaction() as tx:
                res = await tx.execute(
                    "UPDATE trips SET name = ?, plan_type = ?, schema_version = ?, revision = revision + 1, "
                    "snapshot = ?, snapshot_hash = ?, compression = 'none', "
                    "display_start_date = ?, display_end_date = ?, display_num_days = ?, updated_at = ? "
                    "WHERE id = ? AND revision = ?",
                    (
                        payload["name"],
                        payload["plan_type"],
                        payload["schema_version"],
                        canonical,
                        digest,
                        display.start_date,
                        display.end_date,
                        display.num_days,
                        now,
                        trip_id,
                        expected,
                    ),
                )
                if res.rows_affected != 1:
                    raise _CasMiss
                await self._insert_revision(
                    tx,
                    trip_id=trip_id,
                    revision=new_revision,
                    source=source,
                    summary=summary,
                    restored_from_revision=None,
                    schema_version=payload["schema_version"],
                    snapshot=canonical,
                    snapshot_hash=digest,
                    recorded_at=now,
                )
        except _CasMiss:
            raise TripConcurrencyConflictError(trip_id, expected=expected) from None

        return detail_from_snapshot(trip_id, payload, revision=new_revision, created_at=row["created_at"], updated_at=now)

    async def delete(self, trip_id: str) -> bool:
        async with self._conn.transaction() as tx:
            await tx.execute("DELETE FROM trip_revisions WHERE trip_id = ?", (trip_id,))
            res = await tx.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
        return res.rows_affected > 0

    async def list_revisions(self, trip_id: str) -> TripRevisionListOut | None:
        current = await self._current_revision(trip_id)
        if current is None:
            return None
        result = await self._conn.execute(
            "SELECT revision, source, summary, restored_from_revision, schema_version, snapshot_hash, recorded_at "
            "FROM trip_revisions WHERE trip_id = ? ORDER BY revision DESC",
            (trip_id,),
        )
        revisions = [
            TripRevisionSummaryOut(
                revision=row["revision"],
                source=row["source"],
                summary=row["summary"],
                restored_from_revision=row["restored_from_revision"],
                schema_version=row["schema_version"],
                snapshot_hash=row["snapshot_hash"],
                recorded_at=row["recorded_at"],
            )
            for row in result.rows
        ]
        return TripRevisionListOut(trip_id=trip_id, current_revision=current, revisions=revisions)

    async def get_revision(self, trip_id: str, revision: int) -> TripRevisionDetailOut | None:
        result = await self._conn.execute(
            "SELECT revision, source, restored_from_revision, snapshot, snapshot_hash, compression, recorded_at "
            "FROM trip_revisions WHERE trip_id = ? AND revision = ?",
            (trip_id, revision),
        )
        if not result.rows:
            return None
        row = result.rows[0]
        trip_row = await self._trip_row(trip_id)
        trip_created_at = trip_row["created_at"] if trip_row else row["recorded_at"]
        payload = load_snapshot(row["snapshot"], row["compression"])
        base = detail_from_snapshot(trip_id, payload, revision=row["revision"], created_at=trip_created_at, updated_at=None)
        data: dict[str, Any] = base.model_dump()
        data.update(
            source=row["source"],
            restored_from_revision=row["restored_from_revision"],
            snapshot_hash=row["snapshot_hash"],
            recorded_at=row["recorded_at"],
        )
        if payload["plan_type"] == "MULTI_DAY":
            return MultiDayTripRevisionDetailOut.model_validate(data)
        return SingleDayTripRevisionDetailOut.model_validate(data)

    async def restore_revision(
        self,
        trip_id: str,
        target_revision: int,
        *,
        expected_revision: int,
    ) -> TripDetailOut:
        """Restore an earlier revision: always mints ``revision + 1`` (``source='REVERT'``, no
        no-op dedup) except ``target == current`` (-> 400). The optimizer is never invoked."""
        row = await self._trip_row(trip_id)
        if row is None:
            raise TripNotFoundError(trip_id)
        if expected_revision != row["revision"]:
            raise TripConcurrencyConflictError(trip_id, expected=expected_revision)
        if target_revision == row["revision"]:
            raise RevisionAlreadyCurrentError(trip_id, target_revision)

        target = await self._conn.execute(
            "SELECT snapshot, snapshot_hash, schema_version, compression "
            "FROM trip_revisions WHERE trip_id = ? AND revision = ?",
            (trip_id, target_revision),
        )
        if not target.rows:
            raise RevisionNotFoundError(trip_id, target_revision)
        target_row = target.rows[0]

        payload = load_snapshot(target_row["snapshot"], target_row["compression"])
        display = display_fields(payload)
        new_revision = row["revision"] + 1
        now = _now()

        try:
            async with self._conn.transaction() as tx:
                res = await tx.execute(
                    "UPDATE trips SET name = ?, plan_type = ?, schema_version = ?, revision = revision + 1, "
                    "snapshot = ?, snapshot_hash = ?, compression = 'none', "
                    "display_start_date = ?, display_end_date = ?, display_num_days = ?, updated_at = ? "
                    "WHERE id = ? AND revision = ?",
                    (
                        payload["name"],
                        payload["plan_type"],
                        target_row["schema_version"],
                        target_row["snapshot"],
                        target_row["snapshot_hash"],
                        display.start_date,
                        display.end_date,
                        display.num_days,
                        now,
                        trip_id,
                        expected_revision,
                    ),
                )
                if res.rows_affected != 1:
                    raise _CasMiss
                await self._insert_revision(
                    tx,
                    trip_id=trip_id,
                    revision=new_revision,
                    source="REVERT",
                    summary=f"Restored revision {target_revision}",
                    restored_from_revision=target_revision,
                    schema_version=target_row["schema_version"],
                    snapshot=target_row["snapshot"],
                    snapshot_hash=target_row["snapshot_hash"],
                    recorded_at=now,
                )
        except _CasMiss:
            raise TripConcurrencyConflictError(trip_id, expected=expected_revision) from None

        return detail_from_snapshot(trip_id, payload, revision=new_revision, created_at=row["created_at"], updated_at=now)

    async def import_migration_baseline(
        self,
        trip_id: str,
        request: SaveTripRequest,
        revision: int,
        *,
        created_at: str,
    ) -> Literal["created", "skipped_identical"]:
        """The only migration write path: one tx creates ``trips`` at ``revision`` + its
        ``MIGRATION`` row; idempotent on an identical hash; hard-fails rather than overwrite a
        baseline or adopt an unbacked trip."""
        canonical, digest, display = build_snapshot(request)
        payload = load_snapshot(canonical)

        existing = await self._conn.execute(
            "SELECT snapshot_hash FROM trip_revisions WHERE trip_id = ? AND revision = ? AND source = 'MIGRATION'",
            (trip_id, revision),
        )
        if existing.rows:
            if existing.rows[0]["snapshot_hash"] == digest:
                return "skipped_identical"
            raise MigrationBaselineConflictError(trip_id, revision, "existing MIGRATION baseline has a different hash")

        trip_exists = await self._conn.execute("SELECT 1 FROM trips WHERE id = ?", (trip_id,))
        if trip_exists.rows:
            raise MigrationBaselineConflictError(trip_id, revision, "trip present without a matching MIGRATION baseline")

        now = _now()
        async with self._conn.transaction() as tx:
            await self._insert_trip_row(
                tx,
                trip_id=trip_id,
                name=payload["name"],
                plan_type=payload["plan_type"],
                schema_version=payload["schema_version"],
                revision=revision,
                snapshot=canonical,
                snapshot_hash=digest,
                display=display,
                created_at=created_at,
                updated_at=None,
            )
            await self._insert_revision(
                tx,
                trip_id=trip_id,
                revision=revision,
                source="MIGRATION",
                summary=f"Imported from previous store at revision {revision}",
                restored_from_revision=None,
                schema_version=payload["schema_version"],
                snapshot=canonical,
                snapshot_hash=digest,
                recorded_at=now,
            )
        return "created"

    async def has_matching_migration_baseline(self, trip_id: str, revision: int, snapshot_hash: str) -> bool:
        result = await self._conn.execute(
            "SELECT 1 FROM trip_revisions "
            "WHERE trip_id = ? AND revision = ? AND source = 'MIGRATION' AND snapshot_hash = ?",
            (trip_id, revision, snapshot_hash),
        )
        return bool(result.rows)

    async def migration_baseline_ids(self) -> set[str]:
        result = await self._conn.execute("SELECT DISTINCT trip_id FROM trip_revisions WHERE source = 'MIGRATION'")
        return {row["trip_id"] for row in result.rows}

    async def count_trips(self) -> int:
        result = await self._conn.execute("SELECT count(*) AS n FROM trips")
        return int(result.scalar() or 0)

    async def _trip_row(self, trip_id: str) -> dict[str, Any] | None:
        result = await self._conn.execute(f"SELECT {_TRIP_COLUMNS} FROM trips WHERE id = ?", (trip_id,))
        return result.rows[0] if result.rows else None

    async def _current_revision(self, trip_id: str) -> int | None:
        result = await self._conn.execute("SELECT revision FROM trips WHERE id = ?", (trip_id,))
        return int(result.rows[0]["revision"]) if result.rows else None

    async def _insert_trip_row(
        self,
        tx: TripDbTransaction,
        *,
        trip_id: str,
        name: str,
        plan_type: str,
        schema_version: int,
        revision: int,
        snapshot: str,
        snapshot_hash: str,
        display: SnapshotDisplayFields,
        created_at: str,
        updated_at: str | None,
    ) -> None:
        await tx.execute(
            "INSERT INTO trips "
            "(id, name, plan_type, schema_version, revision, snapshot, snapshot_hash, compression, "
            "display_start_date, display_end_date, display_num_days, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'none', ?, ?, ?, ?, ?)",
            (
                trip_id,
                name,
                plan_type,
                schema_version,
                revision,
                snapshot,
                snapshot_hash,
                display.start_date,
                display.end_date,
                display.num_days,
                created_at,
                updated_at,
            ),
        )

    async def _insert_revision(
        self,
        tx: TripDbTransaction,
        *,
        trip_id: str,
        revision: int,
        source: RevisionSource,
        summary: str,
        restored_from_revision: int | None,
        schema_version: int,
        snapshot: str,
        snapshot_hash: str,
        recorded_at: str,
    ) -> None:
        await tx.execute(
            "INSERT INTO trip_revisions "
            "(trip_id, revision, source, summary, restored_from_revision, schema_version, snapshot, "
            "snapshot_hash, compression, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'none', ?)",
            (
                trip_id,
                revision,
                source,
                summary,
                restored_from_revision,
                schema_version,
                snapshot,
                snapshot_hash,
                recorded_at,
            ),
        )
