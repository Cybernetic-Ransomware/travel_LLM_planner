from typing import Any

import httpx
import pendulum


class GooglePlacesManager:
    """Manages the httpx async client lifecycle for Google Places API (New) calls.

    Owns a single shared AsyncClient (connection pooling) for the application lifetime.
    Follows the same connect/disconnect pattern as MongoDBManager.
    """

    _BASE_URL = "https://places.googleapis.com/v1/places"

    def __init__(self, api_key: str, fields: str, timeout: float = 20.0) -> None:
        self._api_key = api_key
        self._fields = fields
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("GooglePlacesManager: not connected — call connect() first")
        return self._client

    @property
    def api_key(self) -> str:
        return self._api_key

    async def connect(self) -> None:
        """Create the shared async HTTP client."""
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def disconnect(self) -> None:
        """Close and release the shared async HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> GooglePlacesManager:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    async def fetch_place_details(
        self, place_id: str, fields: str | None = None
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """Fetch full place details by Place ID from the Places API (New).

        Optional per-request field mask overrides the client default.
        Returns (payload, status, error_message).
        """
        if not self._api_key:
            return None, "MISSING_API_KEY", None

        url = f"{self._BASE_URL}/{place_id}"
        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": fields or self._fields,
        }
        response = await self.client.get(url, headers=headers)
        if response.status_code != 200:
            try:
                payload = response.json()
                error = payload.get("error", {})
                return (
                    None,
                    error.get("status") or f"HTTP_{response.status_code}",
                    error.get("message") or response.text[:200],
                )
            except Exception:
                return None, f"HTTP_{response.status_code}", response.text[:200]

        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            error = payload.get("error", {})
            return None, error.get("status"), error.get("message")

        return payload, "OK", None

    async def search_place_id(
        self, name: str | None, lat: float | None, lng: float | None
    ) -> tuple[str | None, str | None, str | None]:
        """Resolve a place name (+ optional coordinates) to a Place ID via text search.

        Returns (place_id, status, error_message).
        """
        if not self._api_key:
            return None, "MISSING_API_KEY", None
        if not name:
            return None, "MISSING_NAME", None

        url = f"{self._BASE_URL}:searchText"
        headers = {
            "X-Goog-Api-Key": self._api_key,
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

        response = await self.client.post(url, headers=headers, json=body)
        if response.status_code != 200:
            try:
                payload = response.json()
                error = payload.get("error", {})
                return (
                    None,
                    error.get("status") or f"HTTP_{response.status_code}",
                    error.get("message") or response.text[:200],
                )
            except Exception:
                return None, f"HTTP_{response.status_code}", response.text[:200]

        payload = response.json()
        places = payload.get("places") if isinstance(payload, dict) else None
        if not places:
            return None, "NOT_FOUND", None
        place_id = places[0].get("id")
        if not place_id:
            return None, "NOT_FOUND", None
        return place_id, "OK", None

    async def build_enrichment_update(self, doc: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Resolve Google Places details for one candidate document.

        Tries the stored gmaps_place_id first, falling back to a text search when it is
        missing or invalid. Returns (update_fields, resolved) where resolved is True once
        usable place details were obtained from Google (even if location/hours are still
        missing), and False when Places API could not locate the place at all.
        """
        place_id = doc.get("gmaps_place_id")
        if place_id and not str(place_id).startswith("ChI"):
            place_id = None

        details = status = error_message = None
        resolved_id = resolve_status = resolve_error = None

        if place_id:
            details, status, error_message = await self.fetch_place_details(place_id)

        if not details:
            resolved_id, resolve_status, resolve_error = await self.search_place_id(
                doc.get("name"), doc.get("lat"), doc.get("lng")
            )
            if resolved_id:
                details, status, error_message = await self.fetch_place_details(resolved_id)

        update_fields: dict[str, Any] = {
            "details_status": status or resolve_status,
            "details_error": error_message or resolve_error,
            "resolve_status": resolve_status,
            "resolve_error": resolve_error,
            "enriched_at": pendulum.now("UTC"),
        }
        if resolved_id:
            update_fields["gmaps_place_id"] = resolved_id
        if details:
            location = details.get("location") or {}
            update_fields["details"] = details
            update_fields["address"] = details.get("formattedAddress")
            update_fields["opening_hours"] = details.get("regularOpeningHours")
            if location.get("latitude") is not None and location.get("longitude") is not None:
                update_fields["lat"] = location["latitude"]
                update_fields["lng"] = location["longitude"]

        return update_fields, details is not None
