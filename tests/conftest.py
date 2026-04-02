import pytest
from httpx import ASGITransport, AsyncClient
from testcontainers.mongodb import MongoDbContainer

from src.core.db.manager import MongoDBManager
from src.gmaps.manager import GooglePlacesManager
from src.main import app
from src.optimizer.matrix.client import GoogleRoutesManager


@pytest.fixture(scope="session")
def mongo_container():
    """Start a MongoDB testcontainer once for the entire test session."""
    with MongoDbContainer("mongo:8.0") as container:
        yield container


@pytest.fixture
async def test_db(mongo_container):
    """Function-scoped PyMongo async database connected to the testcontainer.

    A new client is created per test to avoid event loop conflicts.
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
async def google_places_manager():
    """Function-scoped GooglePlacesManager with a test API key.

    Provides a connected manager without hitting the real Google API.
    Tests that need to assert API calls should mock the underlying httpx client.
    """
    manager = GooglePlacesManager(api_key="test-key", fields="id,displayName")
    await manager.connect()
    yield manager
    await manager.disconnect()


@pytest.fixture
async def google_routes_manager():
    """Function-scoped GoogleRoutesManager with a test API key.

    Provides a connected manager without hitting the real Google Routes API.
    Tests that need to assert API calls should mock the underlying httpx client.
    """
    manager = GoogleRoutesManager(api_key="test-routes-key")
    await manager.connect()
    yield manager
    await manager.disconnect()


@pytest.fixture
async def client(test_db, google_places_manager, google_routes_manager):
    """Async HTTP client with the testcontainer database injected into app.state.

    ASGITransport does not trigger the FastAPI lifespan, so app.state.db,
    app.state.client, app.state.google_places and app.state.google_routes
    are set directly before the request and cleared afterwards.
    """
    app.state.db = test_db
    app.state.client = test_db.client
    app.state.google_places = google_places_manager
    app.state.google_routes = google_routes_manager
    app.state.orchestrator = None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    del app.state.orchestrator
    del app.state.google_routes
    del app.state.google_places
    del app.state.db
    del app.state.client
