from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from src.optimizer.matrix.models import MatrixEntry, TransportMode


class GoogleRoutesManager:
    """Manages the httpx async client lifecycle for Google Routes API calls.

    Owns a single shared AsyncClient (connection pooling) for the application lifetime.
    Follows the same connect/disconnect pattern as GooglePlacesManager.
    """

    _BASE_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    _FIELD_MASK = "originIndex,destinationIndex,duration,distanceMeters,status"

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("GoogleRoutesManager: not connected — call connect() first")
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

    async def __aenter__(self) -> GoogleRoutesManager:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    async def compute_matrix(
        self,
        place_coords: list[tuple[str, float, float]],
        transport_mode: TransportMode,
        departure_time: datetime | None = None,
    ) -> tuple[list[MatrixEntry] | None, str | None, str | None]:
        """Fetch travel costs for all pairs from the Routes API.

        Args:
            place_coords: List of (place_id, lat, lng) tuples.
            transport_mode: One of WALK, DRIVE, BICYCLE, TRANSIT.
            departure_time: Required for TRANSIT; used as the representative departure time.

        Returns:
            (entries, status, error_message). Status is "OK" on success.
        """
        if not self._api_key:
            return None, "MISSING_API_KEY", None

        waypoints = [
            {"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lng}}}} for _, lat, lng in place_coords
        ]

        body: dict[str, Any] = {
            "origins": waypoints,
            "destinations": waypoints,
            "travelMode": transport_mode.value,
        }

        if departure_time is not None:
            body["departureTime"] = departure_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": self._FIELD_MASK,
        }

        response = await self.client.post(self._BASE_URL, headers=headers, json=body)

        if response.status_code != 200:
            try:
                payload = response.json()
                if isinstance(payload, list) and payload:
                    payload = payload[0]
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                return (
                    None,
                    error.get("status") or f"HTTP_{response.status_code}",
                    error.get("message") or response.text[:200],
                )
            except Exception:
                return None, f"HTTP_{response.status_code}", response.text[:200]

        raw_entries: list[dict[str, Any]] = response.json()
        if not isinstance(raw_entries, list):
            return None, "UNEXPECTED_RESPONSE", "Expected a JSON array from computeRouteMatrix"

        entries: list[MatrixEntry] = []
        ids = [place_id for place_id, _, _ in place_coords]

        for item in raw_entries:
            item_status = item.get("status", {})
            if isinstance(item_status, dict) and item_status.get("code", 0) != 0:
                continue

            origin_idx: int = item["originIndex"]
            dest_idx: int = item["destinationIndex"]

            if origin_idx == dest_idx:
                continue

            duration_str: str = item.get("duration", "0s")
            duration_s = int(duration_str.rstrip("s")) if duration_str.endswith("s") else 0
            distance_m: int = item.get("distanceMeters", 0)

            entries.append(MatrixEntry(ids[origin_idx], ids[dest_idx], distance_m, duration_s))

        return entries, "OK", None
