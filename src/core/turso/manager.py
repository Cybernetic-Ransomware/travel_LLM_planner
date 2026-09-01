"""Connection lifecycle + idempotent schema for the trips database. ``apply_schema()`` runs a
``PRAGMA user_version`` step ladder — a new migration appends a step, never edits an old one."""

from __future__ import annotations

from src.config.conf_logger import setup_logger
from src.core.turso.adapter import TripDbConnection, TripDbError, open_connection, resolve_backend

logger = setup_logger(__name__, "main")

_SCHEMA_STEP_1: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS trips (
        id                 TEXT    PRIMARY KEY,
        name               TEXT    NOT NULL,
        plan_type          TEXT    NOT NULL CHECK (plan_type IN ('SINGLE_DAY', 'MULTI_DAY')),
        schema_version     INTEGER NOT NULL,
        revision           INTEGER NOT NULL,
        snapshot           TEXT    NOT NULL,
        snapshot_hash      TEXT    NOT NULL,
        compression        TEXT    NOT NULL DEFAULT 'none',
        display_start_date TEXT    NOT NULL,
        display_end_date   TEXT    NOT NULL,
        display_num_days   INTEGER NOT NULL,
        created_at         TEXT    NOT NULL,
        updated_at         TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trip_revisions (
        trip_id                TEXT    NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
        revision               INTEGER NOT NULL,
        source                 TEXT    NOT NULL
            CHECK (source IN ('CREATED', 'MANUAL', 'ORCHESTRATOR', 'REVERT', 'MIGRATION')),
        summary                TEXT    NOT NULL,
        restored_from_revision INTEGER,
        schema_version         INTEGER NOT NULL,
        snapshot               TEXT    NOT NULL,
        snapshot_hash          TEXT    NOT NULL,
        compression            TEXT    NOT NULL DEFAULT 'none',
        recorded_at            TEXT    NOT NULL,
        PRIMARY KEY (trip_id, revision)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_trip_revisions_trip_rev_desc ON trip_revisions (trip_id, revision DESC)",
    """
    CREATE TABLE IF NOT EXISTS app_migrations (
        key          TEXT PRIMARY KEY,
        completed_at TEXT NOT NULL,
        metadata     TEXT NOT NULL DEFAULT '{}'
    )
    """,
)

_SCHEMA_STEPS: tuple[tuple[str, ...], ...] = (_SCHEMA_STEP_1,)


class TursoManager:
    """Owns the single app-wide trips-database connection and its schema."""

    def __init__(self, database_url: str, auth_token: str | None = None) -> None:
        self._database_url = database_url
        self._auth_token = auth_token
        self._connection: TripDbConnection | None = None

    @property
    def backend(self) -> str:
        return resolve_backend(self._database_url)

    @property
    def connection(self) -> TripDbConnection:
        if self._connection is None:
            raise TripDbError("TursoManager: not connected — call connect() first")
        return self._connection

    async def connect(self) -> TripDbConnection:
        self._connection = await open_connection(self._database_url, self._auth_token)
        logger.info("Trips database connected — backend=%s", self.backend)
        return self._connection

    async def apply_schema(self) -> None:
        conn = self.connection
        result = await conn.execute("PRAGMA user_version")
        current = int(result.scalar() or 0)
        for step_number, statements in enumerate(_SCHEMA_STEPS, start=1):
            if current >= step_number:
                continue
            async with conn.transaction() as tx:
                for statement in statements:
                    await tx.execute(statement)
                await tx.execute(f"PRAGMA user_version = {step_number}")
            logger.info("Trips database schema advanced to version %d", step_number)

    async def disconnect(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            logger.info("Trips database disconnected")
