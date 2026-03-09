"""Synchronous HTTP client for the Travel Planner FastAPI backend."""

import os

import httpx

_API_URL = os.getenv("API_URL", "http://localhost:8080").rstrip("/")
_BASE = f"{_API_URL}/api/v1/core/gmaps"


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
