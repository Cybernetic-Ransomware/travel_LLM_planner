"""Synchronous HTTP client for the Travel Planner FastAPI backend."""

import os

import httpx

_API_URL = os.getenv("API_URL", "http://localhost:8080").rstrip("/")
_BASE = f"{_API_URL}/api/v1/core/gmaps"
_OPTIMIZER_BASE = f"{_API_URL}/api/v1/core/optimizer"


def list_places(*, skipped: bool | None = None, list_name: str | None = None) -> list[dict]:
    """Fetch all places, optionally filtered by skipped flag or list name."""
    params: dict = {}
    if skipped is not None:
        params["skipped"] = skipped
    if list_name is not None:
        params["list_name"] = list_name
    r = httpx.get(f"{_BASE}/places", params=params)
    r.raise_for_status()
    return r.json()


def patch_place(place_id: str, payload: dict) -> dict:
    """Update scheduling preferences for a single place."""
    r = httpx.patch(f"{_BASE}/places/{place_id}", json=payload)
    r.raise_for_status()
    return r.json()


def delete_place(place_id: str) -> None:
    """Delete a place by its id."""
    r = httpx.delete(f"{_BASE}/places/{place_id}")
    r.raise_for_status()


def import_list(list_url: str) -> dict:
    """Scrape a public Google Maps list and upsert places. May take up to 2 minutes."""
    r = httpx.post(f"{_BASE}/import", json={"list_url": list_url}, timeout=120.0)
    r.raise_for_status()
    return r.json()


def enrich_places(limit: int = 20) -> dict:
    """Run a batch enrichment of places missing address data."""
    r = httpx.post(f"{_BASE}/enrich", json={"limit": limit}, timeout=120.0)
    r.raise_for_status()
    return r.json()


def optimize_route(payload: dict) -> dict:
    """Request an optimized route from the TSP solver endpoint."""
    r = httpx.post(f"{_OPTIMIZER_BASE}/route", json=payload, timeout=30.0)
    r.raise_for_status()
    return r.json()
