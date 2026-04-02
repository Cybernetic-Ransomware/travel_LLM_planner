"""Unit tests for the panel API client error handling."""

import pytest

from src.panel.api_client import _raise_for_status
from src.panel.messages import (
    ERR_MATRIX_UNAVAILABLE,
    ERR_NOT_IMPLEMENTED,
    ERR_ORCHESTRATOR_UNAVAILABLE,
    ERR_UNEXPECTED,
)


@pytest.mark.unit
class TestRaiseForStatus:
    def test_2xx_does_not_raise(self, httpx_mock):
        httpx_mock.add_response(status_code=200, json={"ok": True})
        import httpx

        r = httpx.get("http://test/ok")
        _raise_for_status(r)  # must not raise

    def test_502_raises_matrix_unavailable_message(self, httpx_mock):
        httpx_mock.add_response(status_code=502, json={"detail": "Distance matrix unavailable: MISSING_API_KEY"})
        import httpx

        r = httpx.get("http://test/route")
        with pytest.raises(RuntimeError, match=ERR_MATRIX_UNAVAILABLE):
            _raise_for_status(r)

    def test_503_raises_orchestrator_unavailable_message(self, httpx_mock):
        httpx_mock.add_response(status_code=503, json={"detail": "Orchestrator not available — configure LLM_PROVIDER"})
        import httpx

        r = httpx.get("http://test/chat")
        with pytest.raises(RuntimeError, match="AI assistant"):
            _raise_for_status(r)

    def test_501_raises_not_implemented_message(self, httpx_mock):
        httpx_mock.add_response(status_code=501, json={"detail": "Endpoint not implemented"})
        import httpx

        r = httpx.get("http://test/future")
        with pytest.raises(RuntimeError, match=ERR_NOT_IMPLEMENTED):
            _raise_for_status(r)

    def test_404_uses_backend_detail(self, httpx_mock):
        httpx_mock.add_response(status_code=404, json={"detail": "Place not found"})
        import httpx

        r = httpx.get("http://test/places/missing")
        with pytest.raises(RuntimeError, match="Place not found"):
            _raise_for_status(r)

    def test_non_json_response_falls_back_to_unexpected(self, httpx_mock):
        httpx_mock.add_response(status_code=500, text="Internal Server Error")
        import httpx

        r = httpx.get("http://test/crash")
        with pytest.raises(RuntimeError, match=ERR_UNEXPECTED):
            _raise_for_status(r)

    def test_empty_detail_falls_back_to_unexpected(self, httpx_mock):
        httpx_mock.add_response(status_code=400, json={"detail": ""})
        import httpx

        r = httpx.get("http://test/bad")
        with pytest.raises(RuntimeError, match=ERR_UNEXPECTED):
            _raise_for_status(r)
