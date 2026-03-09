from typing import Any

import httpx

from src.config.config import settings


async def fetch_place_details(place_id: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    api_key = settings.google_places_api_key
    if not api_key:
        return None, "MISSING_API_KEY", None

    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": settings.google_places_fields,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            try:
                payload = response.json()
                error = payload.get("error", {})
                return None, error.get("status") or "HTTP_ERROR", error.get("message") or str(response.status_code)
            except Exception:
                return None, "HTTP_ERROR", str(response.status_code)

        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            error = payload.get("error", {})
            return None, error.get("status"), error.get("message")

        return payload, "OK", None


async def search_place_id(
    name: str | None, lat: float | None, lng: float | None
) -> tuple[str | None, str | None, str | None]:
    api_key = settings.google_places_api_key
    if not api_key:
        return None, "MISSING_API_KEY", None
    if not name:
        return None, "MISSING_NAME", None

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress",
    }
    body: dict[str, Any] = {"textQuery": name}
    if lat is not None and lng is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": 2000,
            }
        }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, headers=headers, json=body)
        if response.status_code != 200:
            try:
                payload = response.json()
                error = payload.get("error", {})
                return None, error.get("status") or "HTTP_ERROR", error.get("message") or str(response.status_code)
            except Exception:
                return None, "HTTP_ERROR", str(response.status_code)

        payload = response.json()
        places = payload.get("places") if isinstance(payload, dict) else None
        if not places:
            return None, "NOT_FOUND", None
        place_id = places[0].get("id")
        if not place_id:
            return None, "NOT_FOUND", None
        return place_id, "OK", None
