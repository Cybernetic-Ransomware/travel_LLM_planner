from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pendulum
from pymongo.asynchronous.database import AsyncDatabase

from src.core.db.manager import MATRIX_COLLECTION
from src.optimizer.matrix.models import DistanceMatrix, MatrixEntry, TransportMode

_NON_TRANSIT_TTL_DAYS = 7
_TRANSIT_TTL_HOURS = 1


def _ttl_for_mode(mode: TransportMode) -> timedelta:
    if mode == TransportMode.TRANSIT:
        return timedelta(hours=_TRANSIT_TTL_HOURS)
    return timedelta(days=_NON_TRANSIT_TTL_DAYS)


async def load_cached_matrix(
    db: AsyncDatabase,
    place_ids: list[str],
    transport_mode: TransportMode,
) -> DistanceMatrix | None:
    """Return a cached DistanceMatrix for all requested pairs, or None if any pair is stale/missing."""
    now = pendulum.now("UTC")
    ttl = _ttl_for_mode(transport_mode)
    cutoff = now - ttl

    origin_dest_pairs = [(o, d) for o in place_ids for d in place_ids if o != d]
    if not origin_dest_pairs:
        return None

    cursor = db[MATRIX_COLLECTION].find(
        {
            "transport_mode": transport_mode.value,
            "origin_id": {"$in": place_ids},
            "dest_id": {"$in": place_ids},
            "computed_at": {"$gte": cutoff},
        }
    )
    docs = await cursor.to_list(length=None)

    found: dict[tuple[str, str], MatrixEntry] = {}
    for doc in docs:
        key = (doc["origin_id"], doc["dest_id"])
        found[key] = MatrixEntry(doc["origin_id"], doc["dest_id"], doc["distance_m"], doc["duration_s"])

    if len(found) < len(origin_dest_pairs):
        return None

    computed_at = min((doc["computed_at"] for doc in docs), default=now)
    if isinstance(computed_at, datetime) and computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=UTC)

    return DistanceMatrix(found, transport_mode, computed_at)


async def store_matrix(
    db: AsyncDatabase,
    entries: list[MatrixEntry],
    transport_mode: TransportMode,
) -> None:
    """Upsert matrix entries into the cache collection."""
    if not entries:
        return

    now = pendulum.now("UTC")
    collection = db[MATRIX_COLLECTION]

    for entry in entries:
        await collection.update_one(
            {"origin_id": entry.origin_id, "dest_id": entry.dest_id, "transport_mode": transport_mode.value},
            {
                "$set": {
                    "distance_m": entry.distance_m,
                    "duration_s": entry.duration_s,
                    "computed_at": now,
                }
            },
            upsert=True,
        )


async def invalidate_cache(db: AsyncDatabase, transport_mode: TransportMode | None = None) -> int:
    """Delete cached entries. Optionally filter by transport mode. Returns deleted count."""
    query: dict = {}
    if transport_mode is not None:
        query["transport_mode"] = transport_mode.value
    result = await db[MATRIX_COLLECTION].delete_many(query)
    return result.deleted_count
