from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

GMAPS_COLLECTION = "gmaps_places"
MATRIX_COLLECTION = "distance_matrix_cache"
CHECKPOINTS_COLLECTION = "orchestrator_checkpoints"


class MongoDBManager:
    """Manages the PyMongo async client lifecycle: connection pooling and index creation."""

    def __init__(self, uri: str, db_name: str, pool_size: int) -> None:
        self._uri = uri
        self._db_name = db_name
        self._pool_size = pool_size
        self._client: AsyncMongoClient | None = None

    @property
    def client(self) -> AsyncMongoClient:
        if self._client is None:
            raise RuntimeError("MongoDBManager: not connected — call connect() first")
        return self._client

    async def connect(self) -> AsyncDatabase:
        """Create the client, connect to the database and ensure indexes exist."""
        self._client = AsyncMongoClient(self._uri, maxPoolSize=self._pool_size)
        db = self._client[self._db_name]
        await self._create_indexes(db)
        return db

    async def disconnect(self) -> None:
        """Close all connections in the pool."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    @staticmethod
    async def _create_indexes(db: AsyncDatabase) -> None:
        collection = db[GMAPS_COLLECTION]
        await collection.create_index("maps_url", unique=True, sparse=True)
        await collection.create_index("source_list_url")
        await collection.create_index("scraped_at")
        await collection.create_index("skipped")
        await collection.create_index(
            [("gmaps_place_id", 1), ("address", 1), ("enriched_at", 1)],
            name="enrichment_candidates",
        )

        matrix = db[MATRIX_COLLECTION]
        await matrix.create_index(
            [("origin_id", 1), ("dest_id", 1), ("transport_mode", 1)],
            unique=True,
        )
        await matrix.create_index("computed_at")

        checkpoints = db[CHECKPOINTS_COLLECTION]
        await checkpoints.create_index(
            [("thread_id", 1), ("checkpoint_id", -1)],
            name="checkpoint_lookup",
        )
        await checkpoints.create_index("expires_at", expireAfterSeconds=0)
