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
) -> tuple[DistanceMatrix | None, str | None, str | None]:
    """Return a DistanceMatrix for the requested places and transport mode.

    Checks the MongoDB cache first. On a cache miss, calls the Google Routes API,
    stores the result, then returns the matrix.

    Args:
        db: Async MongoDB database.
        manager: Connected GoogleRoutesManager instance.
        place_coords: List of (place_id, lat, lng) tuples. Must not be empty.
        transport_mode: Travel mode for cost calculation.
        departure_time: Representative departure time (required for TRANSIT).

    Returns:
        (matrix, status, error_message). Status is "OK" on success.
    """
    if not place_coords:
        return None, "NO_PLACES", "At least two places are required"

    place_ids = [pid for pid, _, _ in place_coords]

    cached = await load_cached_matrix(db, place_ids, transport_mode)
    if cached is not None:
        return cached, "OK", None

    entries, status, error = await manager.compute_matrix(place_coords, transport_mode, departure_time)
    if entries is None:
        return None, status, error

    await store_matrix(db, entries, transport_mode)

    entry_map: dict[tuple[str, str], MatrixEntry] = {(e.origin_id, e.dest_id): e for e in entries}
    matrix = DistanceMatrix(entry_map, transport_mode, pendulum.now("UTC"))
    return matrix, "OK", None
