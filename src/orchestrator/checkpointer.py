from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple
from pymongo.asynchronous.database import AsyncDatabase

CHECKPOINTS_COLLECTION = "orchestrator_checkpoints"


class MongoCheckpointSaver(BaseCheckpointSaver):
    """MongoDB-backed checkpoint saver using pymongo 4.16+ native async client.

    Stores LangGraph conversation checkpoints in the ``orchestrator_checkpoints``
    collection, keyed by ``thread_id`` + ``checkpoint_id``.
    """

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__()
        self._collection = db[CHECKPOINTS_COLLECTION]

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Return the latest checkpoint for the given thread, or None."""
        thread_id = config["configurable"].get("thread_id")
        if not thread_id:
            return None

        doc = await self._collection.find_one(
            {"thread_id": thread_id},
            sort=[("checkpoint_id", -1)],
        )
        if doc is None:
            return None

        checkpoint: Checkpoint = doc["checkpoint"]
        metadata: CheckpointMetadata = doc.get("metadata", {})
        saved_config: RunnableConfig = {"configurable": {"thread_id": thread_id, "checkpoint_id": doc["checkpoint_id"]}}
        return CheckpointTuple(config=saved_config, checkpoint=checkpoint, metadata=metadata)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        """Persist a checkpoint and return the updated config."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]

        await self._collection.update_one(
            {"thread_id": thread_id, "checkpoint_id": checkpoint_id},
            {
                "$set": {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                    "checkpoint": checkpoint,
                    "metadata": metadata,
                }
            },
            upsert=True,
        )
        return {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Persist intermediate writes for a checkpoint (no-op for this implementation)."""

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,  # noqa: A002
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        raise NotImplementedError("Use alist() for async listing")

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        raise NotImplementedError("Use aget_tuple() for async access")

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        raise NotImplementedError("Use aput() for async access")
