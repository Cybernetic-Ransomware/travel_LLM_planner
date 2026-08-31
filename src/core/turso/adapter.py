"""The single Turso/libSQL driver boundary — stdlib ``sqlite3`` (local/CI) or the ``libsql``
package (production) behind one async contract. See ADR-21 for the driver decision.

Both DB-API drivers are synchronous, so every call runs on a dedicated single worker thread
per connection (``sqlite3`` connections are thread-bound; libSQL transactions are
connection-bound) and an ``asyncio.Lock`` keeps a ``BEGIN -> ... -> COMMIT/ROLLBACK`` block
from interleaving with any other statement on that connection.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sqlite3
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Positional ``?`` params only — named binding is out of scope so both drivers behave alike.
Params = Sequence[Any] | None


class TripDbError(RuntimeError):
    """Any persistence-layer failure, normalised across the two drivers.

    ``is_integrity_error`` is set for PK / FK / UNIQUE / CHECK violations so callers can
    tell a genuine constraint break from a transient failure without importing a driver.
    """

    def __init__(self, message: str, *, is_integrity_error: bool = False) -> None:
        super().__init__(message)
        self.is_integrity_error = is_integrity_error


@dataclass(frozen=True)
class DbResult:
    """Outcome of one statement. ``rows`` is empty for non-SELECT statements."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    rows_affected: int = -1
    last_insert_rowid: int | None = None

    def scalar(self) -> Any:
        """First column of the first row, or ``None`` when there are no rows."""
        if not self.rows:
            return None
        first = self.rows[0]
        return next(iter(first.values()))


@runtime_checkable
class TripDbTransaction(Protocol):
    """Statement executor scoped to an open transaction on one connection."""

    async def execute(self, sql: str, params: Params = None) -> DbResult: ...


@runtime_checkable
class TripDbConnection(Protocol):
    """The persistence contract the trips domain codes against — never a raw driver."""

    async def execute(self, sql: str, params: Params = None) -> DbResult: ...

    def transaction(self) -> Any:
        """Async CM yielding a :class:`TripDbTransaction`: commit on clean exit, rollback on
        exception, connection lock held for the whole body."""
        ...

    async def close(self) -> None: ...


def _rows_from_cursor(cursor: Any) -> list[dict[str, Any]]:
    if cursor.description is None:
        return []
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


def _is_integrity_error(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    # libsql raises its own IntegrityError subclass; match by name to avoid importing it.
    return type(exc).__name__ == "IntegrityError" or "IntegrityError" in [t.__name__ for t in type(exc).__mro__]


def _coerce_params(params: Params) -> tuple[Any, ...]:
    if params is None:
        return ()
    if isinstance(params, str | bytes):  # pragma: no cover - guard against a bare string being passed
        raise TripDbError("query parameters must be a sequence, not a bare string")
    return tuple(params)


def _run_statement(conn: Any, sql: str, params: Params, *, commit: bool) -> DbResult:
    try:
        cursor = conn.execute(sql, _coerce_params(params))
        result = DbResult(
            rows=_rows_from_cursor(cursor),
            rows_affected=cursor.rowcount,
            last_insert_rowid=cursor.lastrowid,
        )
        if commit:
            conn.commit()
        return result
    except Exception as exc:  # noqa: BLE001 - normalise every driver error at the boundary
        raise TripDbError(f"{type(exc).__name__}: {exc}", is_integrity_error=_is_integrity_error(exc)) from exc


class _ConnectionWorker:
    """Owns one sync DB-API connection and runs every call on a single private thread."""

    def __init__(self, connect_fn: Callable[[], Any], *, name: str) -> None:
        self._connect_fn = connect_fn
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=name)
        self._conn: Any | None = None

    async def start(self) -> None:
        await self._submit(self._open)

    def _open(self) -> None:
        self._conn = self._connect_fn()

    async def run(self, fn: Callable[[Any], Any]) -> Any:
        return await self._submit(lambda: fn(self._require_conn()))

    def _require_conn(self) -> Any:
        if self._conn is None:
            raise TripDbError("connection worker is not started")
        return self._conn

    async def _submit(self, fn: Callable[[], Any]) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn)

    async def close(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(Exception):  # close is best-effort
                await self._submit(self._conn.close)
            self._conn = None
        self._executor.shutdown(wait=True)


class _ThreadedConnection:
    """Adapter over a :class:`_ConnectionWorker`, exposing the async persistence contract."""

    def __init__(self, worker: _ConnectionWorker) -> None:
        self._worker = worker
        self._lock = asyncio.Lock()

    async def execute(self, sql: str, params: Params = None) -> DbResult:
        async with self._lock:
            return await self._worker.run(lambda conn: _run_statement(conn, sql, params, commit=True))

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TripDbTransaction]:
        async with self._lock:
            await self._worker.run(lambda conn: _run_statement(conn, "BEGIN", None, commit=False))
            tx = _Transaction(self._worker)
            try:
                yield tx
            except BaseException:
                await self._worker.run(lambda conn: conn.rollback())
                raise
            else:
                await self._worker.run(lambda conn: conn.commit())

    async def close(self) -> None:
        await self._worker.close()


class _Transaction:
    """Statement executor bound to the worker while its transaction lock is held."""

    def __init__(self, worker: _ConnectionWorker) -> None:
        self._worker = worker

    async def execute(self, sql: str, params: Params = None) -> DbResult:
        return await self._worker.run(lambda conn: _run_statement(conn, sql, params, commit=False))


def _sqlite_connect(path: str) -> sqlite3.Connection:
    # isolation_level=None -> autocommit mode: we drive BEGIN/COMMIT/ROLLBACK ourselves.
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if path not in (":memory:", ""):
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _libsql_connect(url: str, auth_token: str | None) -> Any:
    try:
        import libsql  # type: ignore[import-not-found]  # Linux/prod + CI parity job only
    except ImportError as exc:  # pragma: no cover - exercised only where libsql is unavailable
        raise TripDbError(
            "database URL requires the 'libsql' package, which is not installed. "
            "Use a file: URL for local development, or install libsql for a remote Turso database."
        ) from exc

    # libsql.connect rejects auth_token=None outright — pass it only when there is a token.
    conn = libsql.connect(url, **({"auth_token": auth_token} if auth_token else {}))
    with contextlib.suppress(Exception):  # some remote modes reject PRAGMA; FK still enforced server-side
        conn.execute("PRAGMA foreign_keys = ON")
    return conn


_REMOTE_SCHEMES = ("libsql://", "wss://", "ws://", "https://", "http://")


def resolve_backend(database_url: str) -> str:
    """``"libsql"`` for a remote URL, ``"sqlite"`` otherwise. ``TRIP_DB_FORCE_BACKEND`` (set
    only by the CI driver-parity job) overrides it."""
    forced = os.environ.get("TRIP_DB_FORCE_BACKEND")
    if forced in ("sqlite", "libsql"):
        return forced
    if database_url.startswith(_REMOTE_SCHEMES):
        return "libsql"
    return "sqlite"


async def open_connection(database_url: str, auth_token: str | None = None) -> TripDbConnection:
    """Open a connection to the trips database, picking the driver from the URL scheme."""
    if not database_url:
        raise TripDbError(
            "TURSO_DATABASE_URL is not set — the trips domain has no persistence backend. "
            "Set a file: URL for local development or a libsql:// URL for production."
        )

    path = database_url[5:] if database_url.startswith("file:") else database_url
    if resolve_backend(database_url) == "libsql":
        # A remote URL is passed through as-is; a file path is opened as a local libsql DB.
        target = database_url if database_url.startswith(_REMOTE_SCHEMES) else path
        connect_fn: Callable[[], Any] = lambda: _libsql_connect(target, auth_token)  # noqa: E731
        worker_name = "tripdb-libsql"
    else:
        connect_fn = lambda: _sqlite_connect(path)  # noqa: E731
        worker_name = "tripdb-sqlite"

    worker = _ConnectionWorker(connect_fn, name=worker_name)
    await worker.start()
    return _ThreadedConnection(worker)
