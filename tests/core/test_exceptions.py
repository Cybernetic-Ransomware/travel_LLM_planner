"""Unit tests for ErrorResponse model and custom exception classes."""

import pytest

from src.core.exceptions import EndpointUnexpectedException, EndpointUnimplementedException, ErrorResponse


class TestErrorResponse:
    def test_model_fields(self):
        response = ErrorResponse(status_code=404, error="Not Found", detail="Resource missing")
        assert response.status_code == 404
        assert response.error == "Not Found"
        assert response.detail == "Resource missing"

    def test_model_dump(self):
        response = ErrorResponse(status_code=500, error="Internal Server Error", detail="Oops")
        data = response.model_dump()
        assert set(data.keys()) == {"status_code", "error", "detail"}
        assert data["status_code"] == 500


class TestEndpointUnimplementedException:
    def test_status_code(self):
        exc = EndpointUnimplementedException()
        assert exc.status_code == 501

    def test_detail_contains_message(self):
        exc = EndpointUnimplementedException(message="GET /foo")
        assert "GET /foo" in exc.detail

    def test_default_message(self):
        exc = EndpointUnimplementedException()
        assert exc.detail == "Endpoint not implemented: "


class TestEndpointUnexpectedException:
    def test_status_code(self):
        exc = EndpointUnexpectedException()
        assert exc.status_code == 500

    def test_detail_contains_message(self):
        exc = EndpointUnexpectedException(message="db timeout")
        assert "db timeout" in exc.detail
