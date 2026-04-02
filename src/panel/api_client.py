"""Synchronous HTTP client for the Travel Planner FastAPI backend."""

import os

import httpx

from src.panel.messages import ERR_UNEXPECTED, FRIENDLY_BY_STATUS

_API_URL = os.getenv("API_URL", "http://localhost:8080").rstrip("/")
_BASE = f"{_API_URL}/api/v1/core/gmaps"
_OPTIMIZER_BASE = f"{_API_URL}/api/v1/core/optimizer"


def _raise_for_status(r: httpx.Response) -> None:
    """Raise RuntimeError with a user-friendly message on non-2xx responses."""
    if not r.is_error:
        return
    try:
        detail = r.json().get("detail", "")
    except Exception:
        detail = ""
    friendly = FRIENDLY_BY_STATUS.get(r.status_code)
    if friendly:
        raise RuntimeError(friendly)
    if detail:
        raise RuntimeError(detail)
    raise RuntimeError(ERR_UNEXPECTED)


def list_places(*, skipped: bool | None = None, list_name: str | None = None) -> list[dict]:
    """Fetch all places, optionally filtered by skipped flag or list name."""
    params: dict = {}
    if skipped is not None:
        params["skipped"] = skipped
    if list_name is not None:
        params["list_name"] = list_name
    r = httpx.get(f"{_BASE}/places", params=params)
    _raise_for_status(r)
    return r.json()


def patch_place(place_id: str, payload: dict) -> dict:
    """Update scheduling preferences for a single place."""
    r = httpx.patch(f"{_BASE}/places/{place_id}", json=payload)
    _raise_for_status(r)
    return r.json()


def delete_place(place_id: str) -> None:
    """Delete a place by its id."""
    r = httpx.delete(f"{_BASE}/places/{place_id}")
    _raise_for_status(r)


def import_list(list_url: str) -> dict:
    """Scrape a public Google Maps list and upsert places. May take up to 2 minutes."""
    r = httpx.post(f"{_BASE}/import", json={"list_url": list_url}, timeout=120.0)
    _raise_for_status(r)
    return r.json()


def enrich_places(limit: int = 20) -> dict:
    """Run a batch enrichment of places missing address data."""
    r = httpx.post(f"{_BASE}/enrich", json={"limit": limit}, timeout=120.0)
    _raise_for_status(r)
    return r.json()


def optimize_route(payload: dict) -> dict:
    """Request an optimized route from the TSP solver endpoint."""
    r = httpx.post(f"{_OPTIMIZER_BASE}/route", json=payload, timeout=30.0)
    _raise_for_status(r)
    return r.json()


def optimize_trip(payload: dict) -> dict:
    """Request a multi-day optimized trip from the TSP solver endpoint."""
    r = httpx.post(f"{_OPTIMIZER_BASE}/trip", json=payload, timeout=60.0)
    _raise_for_status(r)
    return r.json()
