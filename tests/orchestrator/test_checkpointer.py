from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.orchestrator.checkpointer import CHECKPOINTS_COLLECTION, MongoCheckpointSaver


def _make_saver(retention_days: int = 30) -> tuple[MongoCheckpointSaver, AsyncMock]:
    """Return a saver and the mock collection it uses."""
    mock_collection = AsyncMock()
    mock_collection.update_one = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    saver = MongoCheckpointSaver(mock_db, retention_days=retention_days)
    return saver, mock_collection


def _make_config(thread_id: str = "t-1", checkpoint_id: str = "cp-1") -> dict:
    return {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}


def _make_checkpoint(checkpoint_id: str = "cp-1") -> dict:
    return {"id": checkpoint_id, "v": 1, "ts": "2024-01-01T00:00:00Z", "channel_values": {}, "channel_versions": {}, "versions_seen": {}, "pending_sends": []}


@pytest.mark.unit
class TestMongoCheckpointSaverInit:
    def test_default_retention_is_30_days(self):
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=MagicMock())
        saver = MongoCheckpointSaver(mock_db)
        assert saver._retention_days == 30

    def test_custom_retention_stored(self):
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=MagicMock())
        saver = MongoCheckpointSaver(mock_db, retention_days=7)
        assert saver._retention_days == 7

    def test_uses_checkpoints_collection(self):
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        MongoCheckpointSaver(mock_db)
        mock_db.__getitem__.assert_called_once_with(CHECKPOINTS_COLLECTION)


@pytest.mark.unit
class TestMongoCheckpointSaverAput:
    async def test_aput_calls_update_one(self):
        saver, mock_collection = _make_saver()
        config = _make_config()
        checkpoint = _make_checkpoint()

        await saver.aput(config, checkpoint, {}, {})

        mock_collection.update_one.assert_awaited_once()

    async def test_aput_includes_expires_at_field(self):
        saver, mock_collection = _make_saver(retention_days=30)
        before = datetime.now(timezone.utc)

        await saver.aput(_make_config(), _make_checkpoint(), {}, {})

        after = datetime.now(timezone.utc)
        call_kwargs = mock_collection.update_one.call_args
        set_doc = call_kwargs[0][1]["$set"]
        assert "expires_at" in set_doc
        expires_at: datetime = set_doc["expires_at"]
        assert isinstance(expires_at, datetime)
        assert expires_at.tzinfo is not None
        assert before + timedelta(days=30) <= expires_at <= after + timedelta(days=30)

    async def test_aput_expires_at_respects_retention_days(self):
        saver, mock_collection = _make_saver(retention_days=7)
        before = datetime.now(timezone.utc)

        await saver.aput(_make_config(), _make_checkpoint(), {}, {})

        after = datetime.now(timezone.utc)
        set_doc = mock_collection.update_one.call_args[0][1]["$set"]
        expires_at: datetime = set_doc["expires_at"]
        assert before + timedelta(days=7) <= expires_at <= after + timedelta(days=7)

    async def test_aput_stores_thread_and_checkpoint_ids(self):
        saver, mock_collection = _make_saver()
        config = _make_config(thread_id="my-thread", checkpoint_id="my-cp")
        checkpoint = _make_checkpoint(checkpoint_id="my-cp")

        await saver.aput(config, checkpoint, {"meta": "data"}, {})

        set_doc = mock_collection.update_one.call_args[0][1]["$set"]
        assert set_doc["thread_id"] == "my-thread"
        assert set_doc["checkpoint_id"] == "my-cp"
        assert set_doc["metadata"] == {"meta": "data"}

    async def test_aput_uses_upsert(self):
        saver, mock_collection = _make_saver()

        await saver.aput(_make_config(), _make_checkpoint(), {}, {})

        _, kwargs = mock_collection.update_one.call_args
        assert kwargs.get("upsert") is True

    async def test_aput_returns_updated_config(self):
        saver, _ = _make_saver()
        result = await saver.aput(_make_config(thread_id="t-x", checkpoint_id="cp-x"), _make_checkpoint("cp-x"), {}, {})
        assert result["configurable"]["thread_id"] == "t-x"
        assert result["configurable"]["checkpoint_id"] == "cp-x"


@pytest.mark.unit
class TestMongoCheckpointSaverSyncRaiseNotImplemented:
    def test_list_raises(self):
        saver, _ = _make_saver()
        with pytest.raises(NotImplementedError):
            list(saver.list(None))

    def test_get_tuple_raises(self):
        saver, _ = _make_saver()
        with pytest.raises(NotImplementedError):
            saver.get_tuple({})

    def test_put_raises(self):
        saver, _ = _make_saver()
        with pytest.raises(NotImplementedError):
            saver.put({}, {}, {}, {})


@pytest.mark.integration
class TestMongoCheckpointSaverIndexes:
    async def test_checkpoint_lookup_index_exists(self, test_db):
        """After connect(), the compound lookup index must exist on the checkpoints collection."""
        from src.core.db.manager import CHECKPOINTS_COLLECTION

        info = await test_db[CHECKPOINTS_COLLECTION].index_information()
        assert "checkpoint_lookup" in info, "compound index 'checkpoint_lookup' is missing"
        keys = info["checkpoint_lookup"]["key"]
        assert keys == [("thread_id", 1), ("checkpoint_id", -1)]

    async def test_expires_at_ttl_index_exists(self, test_db):
        """After connect(), a TTL index on expires_at with expireAfterSeconds=0 must exist."""
        from src.core.db.manager import CHECKPOINTS_COLLECTION

        info = await test_db[CHECKPOINTS_COLLECTION].index_information()
        ttl_indexes = [
            idx
            for idx in info.values()
            if "expireAfterSeconds" in idx and any(k == "expires_at" for k, _ in idx["key"])
        ]
        assert ttl_indexes, "TTL index on 'expires_at' is missing"
        assert ttl_indexes[0]["expireAfterSeconds"] == 0
