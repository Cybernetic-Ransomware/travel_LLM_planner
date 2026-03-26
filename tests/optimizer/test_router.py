"""Integration tests for optimizer REST endpoints — require MongoDB testcontainer."""

import pytest

from src.core.db.manager import MATRIX_COLLECTION
from src.optimizer.matrix.cache import store_matrix
from src.optimizer.matrix.models import MatrixEntry, TransportMode


@pytest.fixture(autouse=True)
async def clean_matrix_cache(test_db):
    yield
    await test_db[MATRIX_COLLECTION].delete_many({})


@pytest.mark.integration
class TestMatrixCacheStatus:
    async def test_returns_zero_counts_when_empty(self, client):
        response = await client.get("/api/v1/core/optimizer/matrix/status")
        assert response.status_code == 200
        data = response.json()
        assert "cache_entries" in data
        for mode in TransportMode:
            assert data["cache_entries"][mode.value] == 0

    async def test_reflects_stored_entries(self, client, test_db):
        entries = [MatrixEntry("p1", "p2", 1000, 300), MatrixEntry("p2", "p1", 1000, 310)]
        await store_matrix(test_db, entries, TransportMode.WALK)

        response = await client.get("/api/v1/core/optimizer/matrix/status")
        data = response.json()

        assert data["cache_entries"]["WALK"] == 2
        assert data["cache_entries"]["DRIVE"] == 0


@pytest.mark.integration
class TestMatrixCacheInvalidation:
    async def test_delete_all_cache_returns_204(self, client, test_db):
        entries = [MatrixEntry("p1", "p2", 500, 120)]
        await store_matrix(test_db, entries, TransportMode.WALK)

        response = await client.delete("/api/v1/core/optimizer/matrix/cache")

        assert response.status_code == 204
        assert await test_db[MATRIX_COLLECTION].count_documents({}) == 0

    async def test_delete_by_mode_removes_only_that_mode(self, client, test_db):
        await store_matrix(test_db, [MatrixEntry("p1", "p2", 500, 120)], TransportMode.WALK)
        await store_matrix(test_db, [MatrixEntry("p1", "p2", 600, 240)], TransportMode.DRIVE)

        response = await client.delete("/api/v1/core/optimizer/matrix/cache", params={"transport_mode": "WALK"})

        assert response.status_code == 204
        assert await test_db[MATRIX_COLLECTION].count_documents({"transport_mode": "WALK"}) == 0
        assert await test_db[MATRIX_COLLECTION].count_documents({"transport_mode": "DRIVE"}) == 1

    async def test_delete_empty_cache_returns_204(self, client):
        response = await client.delete("/api/v1/core/optimizer/matrix/cache")
        assert response.status_code == 204


@pytest.mark.integration
class TestRoutesKeycheck:
    async def test_returns_key_info(self, client):
        response = await client.get("/api/v1/core/optimizer/keycheck")
        assert response.status_code == 200
        data = response.json()
        assert data["present"] is True
        assert data["last4"] == "s-key"[-4:]
