"""Turso / libSQL persistence for the trips domain (ADR-21). ``adapter.py`` is the only
driver boundary — the rest of the codebase depends on the ``TripDbConnection`` protocol."""

from src.core.turso.adapter import (
    DbResult,
    TripDbConnection,
    TripDbError,
    TripDbTransaction,
)
from src.core.turso.manager import TursoManager
from src.core.turso.migration_state import MigrationState

__all__ = [
    "DbResult",
    "MigrationState",
    "TripDbConnection",
    "TripDbError",
    "TripDbTransaction",
    "TursoManager",
]
