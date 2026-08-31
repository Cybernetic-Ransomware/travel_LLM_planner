import pytest

from src.core.turso.manager import TursoManager

pytestmark = pytest.mark.integration


@pytest.fixture
async def manager(tmp_path):
    mgr = TursoManager(f"file:{tmp_path / 'schema.db'}")
    await mgr.connect()
    yield mgr
    await mgr.disconnect()


async def _table_names(mgr: TursoManager) -> set[str]:
    result = await mgr.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in result.rows}


async def _index_names(mgr: TursoManager) -> set[str]:
    result = await mgr.connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    return {row["name"] for row in result.rows}


class TestApplySchema:
    async def test_creates_all_objects(self, manager):
        await manager.apply_schema()
        tables = await _table_names(manager)
        assert {"trips", "trip_revisions", "app_migrations"} <= tables
        assert "ix_trip_revisions_trip_rev_desc" in await _index_names(manager)

    async def test_is_idempotent_and_bumps_user_version(self, manager):
        await manager.apply_schema()
        first = (await manager.connection.execute("PRAGMA user_version")).scalar()
        await manager.apply_schema()
        second = (await manager.connection.execute("PRAGMA user_version")).scalar()
        assert first == second == 1

    async def test_foreign_keys_pragma_on(self, manager):
        result = await manager.connection.execute("PRAGMA foreign_keys")
        assert result.scalar() == 1

    async def test_backend_is_sqlite_for_file_url(self, manager):
        assert manager.backend == "sqlite"

    async def test_connection_property_raises_before_connect(self, tmp_path):
        mgr = TursoManager(f"file:{tmp_path / 'x.db'}")
        with pytest.raises(RuntimeError, match="not connected"):
            _ = mgr.connection
