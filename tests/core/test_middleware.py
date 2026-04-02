"""Unit tests for ExceptionHandlerMiddleware and register_exception_handlers."""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.exceptions import EndpointUnexpectedException, EndpointUnimplementedException
from src.core.middleware import ExceptionHandlerMiddleware, register_exception_handlers

test_app = FastAPI()
test_app.add_middleware(ExceptionHandlerMiddleware)  # type: ignore[arg-type]
register_exception_handlers(test_app)


class _Body(BaseModel):
    value: int


@test_app.get("/ok")
async def route_ok():
    return {"status": "ok"}


@test_app.get("/http-error")
async def route_http_error():
    raise StarletteHTTPException(status_code=404, detail="not found")


@test_app.get("/custom-501")
async def route_custom_501():
    raise EndpointUnimplementedException(message="GET /custom-501")


@test_app.get("/custom-500")
async def route_custom_500():
    raise EndpointUnexpectedException(message="something went wrong")


@test_app.post("/validation")
async def route_validation(body: _Body):
    return body


@test_app.get("/unhandled")
async def route_unhandled():
    raise RuntimeError("totally unexpected")


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        yield ac


class TestHTTPExceptionHandler:
    async def test_404_format(self, client):
        response = await client.get("/http-error")
        assert response.status_code == 404
        data = response.json()
        assert data["status_code"] == 404
        assert data["error"] == "Not Found"
        assert "not found" in data["detail"]

    async def test_custom_501(self, client):
        response = await client.get("/custom-501")
        assert response.status_code == 501
        data = response.json()
        assert data["status_code"] == 501
        assert data["error"] == "Not Implemented"
        assert "GET /custom-501" in data["detail"]

    async def test_custom_500(self, client):
        response = await client.get("/custom-500")
        assert response.status_code == 500
        data = response.json()
        assert data["status_code"] == 500
        assert data["error"] == "Internal Server Error"
        assert "something went wrong" in data["detail"]


class TestValidationHandler:
    async def test_422_format(self, client):
        response = await client.post("/validation", json={"value": "not-an-int"})
        assert response.status_code == 422
        data = response.json()
        assert data["status_code"] == 422
        assert data["error"] == "Unprocessable Entity"
        detail = data["detail"]
        assert "[{" not in detail, "detail must not be raw Pydantic error list"
        assert "value" in detail

    async def test_missing_body_422(self, client):
        response = await client.post("/validation", json={})
        assert response.status_code == 422
        assert response.json()["status_code"] == 422


class TestMiddlewareCatchAll:
    async def test_unhandled_returns_500(self, client):
        response = await client.get("/unhandled")
        assert response.status_code == 500
        data = response.json()
        assert data["status_code"] == 500
        assert data["error"] == "Internal Server Error"
        assert "RuntimeError" not in data["detail"]
        assert data["detail"] == "An unexpected error occurred."

    async def test_unhandled_logs_traceback(self, client, caplog):
        with caplog.at_level(logging.ERROR, logger="src.core.middleware"):
            await client.get("/unhandled")
        assert any("RuntimeError" in record.message for record in caplog.records)

    async def test_success_passes_through(self, client):
        response = await client.get("/ok")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
