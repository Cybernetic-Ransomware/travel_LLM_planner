"""The one reader/writer of ``app_migrations``. Runtime startup consults only this table (one
``SELECT``), never MongoDB; source-vs-Turso verification is an ops-path job (ADR-21)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from src.core.turso.adapter import TripDbConnection

TRIPS_MIGRATION_KEY = "mongo_trips_to_turso_v1"


class MigrationState:
    def __init__(self, connection: TripDbConnection) -> None:
        self._conn = connection

    async def is_complete(self, key: str = TRIPS_MIGRATION_KEY) -> bool:
        result = await self._conn.execute("SELECT 1 FROM app_migrations WHERE key = ?", (key,))
        return bool(result.rows)

    async def read(self, key: str = TRIPS_MIGRATION_KEY) -> dict[str, Any] | None:
        result = await self._conn.execute("SELECT key, completed_at, metadata FROM app_migrations WHERE key = ?", (key,))
        if not result.rows:
            return None
        row = dict(result.rows[0])
        try:
            row["metadata"] = json.loads(row.get("metadata") or "{}")
        except json.JSONDecodeError:
            row["metadata"] = {}
        return row

    async def mark_complete(
        self,
        key: str = TRIPS_MIGRATION_KEY,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Stamp (or re-stamp, after a clean re-verify) the migration-complete marker."""
        now = datetime.now(UTC).isoformat()
        payload = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))
        await self._conn.execute(
            "INSERT INTO app_migrations (key, completed_at, metadata) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET completed_at = excluded.completed_at, metadata = excluded.metadata",
            (key, now, payload),
        )
