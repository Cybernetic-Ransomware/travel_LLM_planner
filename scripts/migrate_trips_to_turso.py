"""One-off Mongo ``trips`` -> Turso import (ADR-21). Reads Mongo, validates via the existing
Pydantic contracts, writes only through ``TripRepository.import_migration_baseline``, verifies
coverage + hashes, and stamps the ``app_migrations`` marker only on a fully clean pass. Never
mutates Mongo.

Usage:
    $env:PYTHONPATH = "."; uv run python scripts/migrate_trips_to_turso.py [--dry-run] [--skip-invalid]

Exit 0 = clean (marker stamped, or --dry-run with no problems); exit 1 = inconsistent (marker untouched).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError

from src.config.config import settings
from src.core.db.manager import MongoDBManager
from src.core.turso.manager import TursoManager
from src.core.turso.migration_state import TRIPS_MIGRATION_KEY, MigrationState
from src.trips.models import SaveTripRequest
from src.trips.repository import MigrationBaselineConflictError, TripRepository
from src.trips.snapshot import build_snapshot

_LEGACY_TRIPS_COLLECTION = "trips"
_SERVER_KEYS = {"_id", "revision", "created_at", "updated_at", "schema_version"}
_TOOL_VERSION = "mongo_trips_to_turso_v1"

_request_adapter: TypeAdapter[Any] = TypeAdapter(SaveTripRequest)


def _request_from_doc(doc: dict) -> SaveTripRequest:
    payload = {k: v for k, v in doc.items() if k not in _SERVER_KEYS}
    return _request_adapter.validate_python(payload)


def _created_at(doc: dict) -> str:
    value = doc.get("created_at")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, str) and value:
        return value
    return datetime.now(UTC).isoformat()


async def _run(dry_run: bool, skip_invalid: bool) -> int:
    mongo = MongoDBManager(settings.mongo_uri, settings.mongo_db, settings.mongo_pool_size)
    mongo_db = await mongo.connect()
    turso = TursoManager(settings.turso_database_url, settings.turso_auth_token)
    conn = await turso.connect()
    await turso.apply_schema()
    repo = TripRepository(conn)
    marker = MigrationState(conn)

    imported = 0
    skipped_identical = 0
    invalid: list[str] = []
    # trip_id -> (mongo_revision, recomputed_hash) for the verification pass
    expected: dict[str, tuple[int, str]] = {}

    try:
        cursor = mongo_db[_LEGACY_TRIPS_COLLECTION].find({}, sort=[("_id", 1)])
        async for doc in cursor:
            trip_id = str(doc["_id"])
            mongo_revision = int(doc.get("revision", 0))
            try:
                request = _request_from_doc(doc)
            except (ValidationError, KeyError, TypeError) as exc:
                if not skip_invalid:
                    print(f"ABORT: {trip_id} is not a valid trip document: {exc}", file=sys.stderr)
                    return 1
                print(f"SKIP (invalid): {trip_id}: {exc}", file=sys.stderr)
                invalid.append(trip_id)
                continue

            _canonical, digest, _display = build_snapshot(request)
            expected[trip_id] = (mongo_revision, digest)

            if dry_run:
                imported += 1
                continue

            try:
                outcome = await repo.import_migration_baseline(
                    trip_id, request, mongo_revision, created_at=_created_at(doc)
                )
            except MigrationBaselineConflictError as exc:
                print(f"ABORT: {exc}", file=sys.stderr)
                return 1
            if outcome == "created":
                imported += 1
            else:
                skipped_identical += 1

        print(
            f"{'DRY-RUN: would import' if dry_run else 'Imported'} {imported}, "
            f"skipped-identical {skipped_identical}, invalid {len(invalid)}"
        )

        if dry_run:
            print("DRY-RUN: marker not stamped.")
            return 0 if not invalid else 1

        # Verify every Mongo trip has a matching baseline and no baseline lacks a source doc.
        problems = 0
        for trip_id, (revision, digest) in expected.items():
            if not await repo.has_matching_migration_baseline(trip_id, revision, digest):
                print(f"VERIFY FAIL: {trip_id} has no matching MIGRATION baseline at revision {revision}", file=sys.stderr)
                problems += 1
        stray = await repo.migration_baseline_ids() - set(expected)
        for trip_id in sorted(stray):
            print(f"VERIFY FAIL: stray MIGRATION baseline {trip_id} has no source document", file=sys.stderr)
            problems += 1

        if invalid:
            print(f"REFUSING to stamp marker: {len(invalid)} source document(s) were skipped as invalid.", file=sys.stderr)
            return 1
        if problems:
            print(f"REFUSING to stamp marker: {problems} verification problem(s).", file=sys.stderr)
            return 1

        await marker.mark_complete(
            TRIPS_MIGRATION_KEY,
            metadata={
                "trip_count": await repo.count_trips(),
                "verified_at": datetime.now(UTC).isoformat(),
                "tool_version": _TOOL_VERSION,
            },
        )
        print(f"Marker {TRIPS_MIGRATION_KEY!r} stamped — {await repo.count_trips()} trips in Turso.")
        return 0
    finally:
        await turso.disconnect()
        await mongo.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="validate + report only; never write to Turso")
    parser.add_argument(
        "--skip-invalid",
        action="store_true",
        help="skip malformed source documents instead of aborting (still exits non-zero, marker not stamped)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.dry_run, args.skip_invalid)))


if __name__ == "__main__":
    main()
