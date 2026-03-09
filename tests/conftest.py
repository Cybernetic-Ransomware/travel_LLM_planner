import pytest
from httpx import ASGITransport, AsyncClient
from testcontainers.mongodb import MongoDbContainer

from src.core.db.manager import MongoDBManager
from src.main import app


@pytest.fixture(scope="session")
def mongo_container():
    """Start a MongoDB testcontainer once for the entire test session."""
    with MongoDbContainer("mongo:8.0") as container:
        yield container


@pytest.fixture
async def test_db(mongo_container):
    """Function-scoped Motor database connected to the testcontainer.

    A new Motor client is created per test to avoid event loop conflicts.
    The container itself is session-scoped (started once); only the connection is per-test.
    Calls MongoDBManager.connect() so indexes are created identically to prod.
    """
    manager = MongoDBManager(
        uri=mongo_container.get_connection_url(),
        db_name="test_travel_planner",
        pool_size=2,
    )
    db = await manager.connect()
    yield db
    await manager.disconnect()


@pytest.fixture
async def client(test_db):
    """Async HTTP client with the testcontainer database injected into app.state.

    ASGITransport does not trigger the FastAPI lifespan, so app.state.db is set
    directly before the request and cleared afterwards.
    """
    app.state.db = test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    del app.state.db
