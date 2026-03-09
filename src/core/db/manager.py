from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

GMAPS_COLLECTION = "gmaps_places"


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
