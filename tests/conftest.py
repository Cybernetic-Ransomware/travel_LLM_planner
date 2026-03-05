from contextlib import asynccontextmanager

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


@pytest.fixture(scope="session")
async def test_db(mongo_container):
    """Session-scoped Motor database connected to the testcontainer.

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
    """Async HTTP client with the app lifespan replaced by a test stub.

    Injects the testcontainer database via app.state instead of connecting
    to the prod URI from settings. Restores the original lifespan after the test.
    """

    @asynccontextmanager
    async def _test_lifespan(application):
        application.state.db = test_db
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.router.lifespan_context = original_lifespan
