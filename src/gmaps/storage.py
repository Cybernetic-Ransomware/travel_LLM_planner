from collections.abc import Iterable

import pendulum
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument, UpdateOne
from pymongo.asynchronous.database import AsyncDatabase

from src.core.db.manager import GMAPS_COLLECTION
from src.gmaps.models import PlacePatch, ScrapedPlace


async def upsert_places(
    db: AsyncDatabase,
    places: Iterable[ScrapedPlace],
    *,
    source_list_url: str,
    scraped_at: pendulum.DateTime,
    list_name: str | None = None,
) -> int:
    """Insert or update scraped places. Returns the number of affected documents."""
    collection = db[GMAPS_COLLECTION]
    ops: list[UpdateOne] = []

    for place in places:
        doc = place.model_dump(mode="json")
        doc["source_list_url"] = source_list_url
        doc["list_name"] = list_name
        doc["scraped_at"] = scraped_at

        key = {"maps_url": doc.get("maps_url")}
        if not key["maps_url"]:
            key = {"name": doc.get("name"), "address": doc.get("address")}

        ops.append(UpdateOne(key, {"$set": doc}, upsert=True))

    if not ops:
        return 0

    result = await collection.bulk_write(ops, ordered=False)
    return result.upserted_count + result.modified_count


async def fetch_places(
    db: AsyncDatabase,
    *,
    skipped: bool | None = None,
    list_name: str | None = None,
) -> list[dict]:
    """Return all places, optionally filtered by skipped flag or list name."""
    collection = db[GMAPS_COLLECTION]
    query: dict = {}
    if skipped is not None:
        query["skipped"] = skipped
    if list_name is not None:
        query["list_name"] = list_name
    return await collection.find(query).to_list(length=None)


async def fetch_place_by_id(db: AsyncDatabase, place_id: str) -> dict | None:
    """Return a single place by its MongoDB ObjectId string. Returns None if not found."""
    try:
        oid = ObjectId(place_id)
    except InvalidId:
        return None
    return await db[GMAPS_COLLECTION].find_one({"_id": oid})


async def fetch_places_by_ids(db: AsyncDatabase, place_ids: list[str]) -> list[dict]:
    """Return all places whose _id is in the given list, preserving order."""
    oids = []
    for pid in place_ids:
        try:
            oids.append(ObjectId(pid))
        except InvalidId:
            continue
    if not oids:
        return []
    docs = await db[GMAPS_COLLECTION].find({"_id": {"$in": oids}}).to_list(length=None)
    order = {str(doc["_id"]): doc for doc in docs}
    return [order[pid] for pid in place_ids if pid in order]


async def find_and_update_place(db: AsyncDatabase, place_id: str, patch: PlacePatch) -> dict | None:
    """Atomically apply patch and return the updated document, or None if not found or invalid id."""
    try:
        oid = ObjectId(place_id)
    except InvalidId:
        return None
    fields = patch.model_dump(exclude_none=True)
    collection = db[GMAPS_COLLECTION]
    if not fields:
        return await collection.find_one({"_id": oid})
    return await collection.find_one_and_update(
        {"_id": oid},
        {"$set": fields},
        return_document=ReturnDocument.AFTER,
    )


async def delete_place(db: AsyncDatabase, place_id: str) -> bool:
    """Delete a place by its MongoDB ObjectId string. Returns True if a document was deleted."""
    try:
        oid = ObjectId(place_id)
    except InvalidId:
        return False
    result = await db[GMAPS_COLLECTION].delete_one({"_id": oid})
    return result.deleted_count > 0


async def fetch_places_missing_address(db: AsyncDatabase, limit: int) -> list[dict]:
    """Return places that have a place_id but no address yet — candidates for enrichment."""
    collection = db[GMAPS_COLLECTION]
    cursor = collection.find(
        {"gmaps_place_id": {"$ne": None}, "$or": [{"address": None}, {"address": ""}]},
        {"gmaps_place_id": 1, "name": 1, "lat": 1, "lng": 1},
    ).limit(limit)
    return await cursor.to_list(length=limit)


async def bulk_update_enrichment(db: AsyncDatabase, updates: list[UpdateOne]) -> int:
    """Apply a batch of enrichment updates. Returns the number of modified documents."""
    if not updates:
        return 0
    collection = db[GMAPS_COLLECTION]
    result = await collection.bulk_write(updates, ordered=False)
    return result.modified_count
