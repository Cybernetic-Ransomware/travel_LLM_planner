import pytest

from src.core.turso.migration_state import TRIPS_MIGRATION_KEY, MigrationState

pytestmark = pytest.mark.integration


class TestMigrationState:
    async def test_incomplete_on_fresh_db(self, trip_db_unmarked):
        assert await MigrationState(trip_db_unmarked).is_complete() is False
        assert await MigrationState(trip_db_unmarked).read() is None

    async def test_mark_complete_then_is_complete(self, trip_db_unmarked):
        state = MigrationState(trip_db_unmarked)
        await state.mark_complete(metadata={"trip_count": 3})
        assert await state.is_complete() is True

    async def test_read_returns_parsed_metadata(self, trip_db_unmarked):
        state = MigrationState(trip_db_unmarked)
        await state.mark_complete(metadata={"trip_count": 7, "tool_version": "abc"})
        row = await state.read()
        assert row["key"] == TRIPS_MIGRATION_KEY
        assert row["metadata"] == {"trip_count": 7, "tool_version": "abc"}
        assert row["completed_at"]

    async def test_re_stamp_is_safe_and_updates_timestamp(self, trip_db_unmarked):
        state = MigrationState(trip_db_unmarked)
        await state.mark_complete(metadata={"trip_count": 1})
        first = (await state.read())["completed_at"]
        await state.mark_complete(metadata={"trip_count": 2})
        row = await state.read()
        assert row["metadata"] == {"trip_count": 2}
        assert row["completed_at"] >= first

    async def test_trip_db_fixture_is_pre_marked(self, trip_db):
        assert await MigrationState(trip_db).is_complete() is True
