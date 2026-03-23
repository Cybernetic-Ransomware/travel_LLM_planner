from typing import Any

import httpx


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

    async def fetch_place_details(self, place_id: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """Fetch full place details by Place ID from the Places API (New).

        Returns (payload, status, error_message).
        """
        if not self._api_key:
            return None, "MISSING_API_KEY", None

        url = f"{self._BASE_URL}/{place_id}"
        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": self._fields,
        }
        response = await self.client.get(url, headers=headers)
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
