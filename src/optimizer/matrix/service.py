from __future__ import annotations

from datetime import datetime

import pendulum
from pymongo.asynchronous.database import AsyncDatabase

from src.optimizer.matrix.cache import load_cached_matrix, store_matrix
from src.optimizer.matrix.client import GoogleRoutesManager
from src.optimizer.matrix.models import DistanceMatrix, MatrixEntry, TransportMode


async def get_matrix(
    db: AsyncDatabase,
    manager: GoogleRoutesManager,
    place_coords: list[tuple[str, float, float]],
    transport_mode: TransportMode,
    departure_time: datetime | None = None,
    start_anchor: tuple[str, float, float] | None = None,
    end_anchor: tuple[str, float, float] | None = None,
) -> tuple[DistanceMatrix | None, str | None, str | None]:
    """Return a DistanceMatrix for the requested places and transport mode.

    Checks the MongoDB cache first for the real-place-to-real-place matrix. On a
    cache miss, calls the Google Routes API, stores the result, then returns the
    matrix.

    start_anchor/end_anchor, when given, add a day's start/end location (e.g. a
    hotel) that is not a real place with a stable Google Place ID. Their legs are
    fetched as separate, direction-limited requests (start_anchor -> place_coords
    outgoing only, place_coords -> end_anchor incoming only) merged into the
    result, rather than folded into the square real-place matrix — doing the
    latter would grow that matrix by (N+2)^2 - N^2 elements and could push a
    request that used to fit under Google's ComputeRouteMatrix element cap (625,
    or 100 for TRANSIT) over it. Anchor legs are always fetched fresh, never cached.

    Args:
        db: Async MongoDB database.
        manager: Connected GoogleRoutesManager instance.
        place_coords: List of (place_id, lat, lng) tuples. Must not be empty.
        transport_mode: Travel mode for cost calculation.
        departure_time: Representative departure time (required for TRANSIT).
        start_anchor: Optional (anchor_id, lat, lng) for the day's fixed start location.
        end_anchor: Optional (anchor_id, lat, lng) for the day's fixed end location.

    Returns:
        (matrix, status, error_message). Status is "OK" on success.
    """
    if not place_coords:
        return None, "NO_PLACES", "At least one place is required"

    place_ids = [pid for pid, _, _ in place_coords]

    cached = await load_cached_matrix(db, place_ids, transport_mode)
    if cached is not None and start_anchor is None and end_anchor is None:
        return cached, "OK", None

    if cached is not None:
        entry_map: dict[tuple[str, str], MatrixEntry] = dict(cached.entries)
        computed_at = cached.computed_at
    else:
        entries, status, error = await manager.compute_matrix(place_coords, transport_mode, departure_time)
        if entries is None:
            return None, status, error
        await store_matrix(db, entries, transport_mode)
        entry_map = {(e.origin_id, e.dest_id): e for e in entries}
        computed_at = pendulum.now("UTC")

    if start_anchor is not None:
        entries, status, error = await manager.compute_matrix(
            [start_anchor], transport_mode, departure_time, dest_coords=place_coords
        )
        if entries is None:
            return None, status, error
        entry_map.update({(e.origin_id, e.dest_id): e for e in entries})
        computed_at = pendulum.now("UTC")

    if end_anchor is not None:
        entries, status, error = await manager.compute_matrix(
            place_coords, transport_mode, departure_time, dest_coords=[end_anchor]
        )
        if entries is None:
            return None, status, error
        entry_map.update({(e.origin_id, e.dest_id): e for e in entries})
        computed_at = pendulum.now("UTC")

    matrix = DistanceMatrix(entry_map, transport_mode, computed_at)
    return matrix, "OK", None
