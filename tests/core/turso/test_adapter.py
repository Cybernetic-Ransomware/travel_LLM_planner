"""Adapter contract on the sqlite backend (the libsql backend runs the same suite in the
Linux CI driver-parity job). Confirms the transactional semantics TripRepository relies on."""

import pytest

from src.core.turso.adapter import TripDbError, open_connection, resolve_backend

pytestmark = pytest.mark.integration


@pytest.fixture
async def conn(tmp_path):
    connection = await open_connection(f"file:{tmp_path / 'adapter.db'}")
    await connection.execute("CREATE TABLE t (id TEXT PRIMARY KEY, n INTEGER NOT NULL)")
    await connection.execute(
        "CREATE TABLE child (t_id TEXT NOT NULL REFERENCES t(id) ON DELETE CASCADE, k INTEGER, PRIMARY KEY (t_id, k))"
    )
    yield connection
    await connection.close()


class TestBackendResolution:
    def test_file_url_is_sqlite(self):
        assert resolve_backend("file:/tmp/x.db") == "sqlite"
        assert resolve_backend("/var/data/x.db") == "sqlite"

    def test_remote_url_is_libsql(self):
        assert resolve_backend("libsql://db.turso.io") == "libsql"
        assert resolve_backend("https://db.turso.io") == "libsql"

    async def test_empty_url_raises(self):
        with pytest.raises(TripDbError):
            await open_connection("")


class TestExecute:
    async def test_insert_then_select(self, conn):
        await conn.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("a", 1))
        result = await conn.execute("SELECT n FROM t WHERE id = ?", ("a",))
        assert result.rows == [{"n": 1}]
        assert result.scalar() == 1

    async def test_rows_affected_zero_and_one(self, conn):
        await conn.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("a", 1))
        miss = await conn.execute("UPDATE t SET n = 2 WHERE id = ? AND n = ?", ("a", 99))
        assert miss.rows_affected == 0
        hit = await conn.execute("UPDATE t SET n = 2 WHERE id = ? AND n = ?", ("a", 1))
        assert hit.rows_affected == 1

    async def test_parameter_binding_is_not_interpolated(self, conn):
        await conn.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("x'); DROP TABLE t;--", 5))
        result = await conn.execute("SELECT count(*) AS c FROM t")
        assert result.scalar() == 1

    async def test_integrity_error_is_normalised(self, conn):
        await conn.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("a", 1))
        with pytest.raises(TripDbError) as excinfo:
            await conn.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("a", 2))
        assert excinfo.value.is_integrity_error is True


class TestTransaction:
    async def test_commit_persists_all_statements(self, conn):
        async with conn.transaction() as tx:
            await tx.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("a", 1))
            await tx.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("b", 2))
        result = await conn.execute("SELECT count(*) AS c FROM t")
        assert result.scalar() == 2

    async def test_exception_rolls_everything_back(self, conn):
        await conn.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("a", 1))
        with pytest.raises(RuntimeError, match="boom"):
            async with conn.transaction() as tx:
                await tx.execute("UPDATE t SET n = 99 WHERE id = ?", ("a",))
                raise RuntimeError("boom")
        result = await conn.execute("SELECT n FROM t WHERE id = ?", ("a",))
        assert result.scalar() == 1

    async def test_integrity_error_inside_tx_rolls_back(self, conn):
        await conn.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("a", 1))
        with pytest.raises(TripDbError):
            async with conn.transaction() as tx:
                await tx.execute("UPDATE t SET n = 5 WHERE id = ?", ("a",))
                await tx.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("a", 2))  # PK clash
        assert (await conn.execute("SELECT n FROM t WHERE id = ?", ("a",))).scalar() == 1

    async def test_foreign_keys_enforced_and_cascade(self, conn):
        with pytest.raises(TripDbError):
            await conn.execute("INSERT INTO child (t_id, k) VALUES (?, ?)", ("ghost", 1))
        async with conn.transaction() as tx:
            await tx.execute("INSERT INTO t (id, n) VALUES (?, ?)", ("a", 1))
            await tx.execute("INSERT INTO child (t_id, k) VALUES (?, ?)", ("a", 1))
        await conn.execute("DELETE FROM t WHERE id = ?", ("a",))
        assert (await conn.execute("SELECT count(*) AS c FROM child")).scalar() == 0
