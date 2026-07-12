from collections.abc import Iterable

import pendulum
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument, UpdateOne
from pymongo.asynchronous.database import AsyncDatabase

from src.core.db.manager import GMAPS_COLLECTION
from src.core.exceptions import InvalidHourRangeError
from src.gmaps.models import PlaceCreate, PlacePatch, ScrapedPlace


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
        query["skipped"] = True if skipped else {"$ne": True}
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
    """Apply patch and return the updated document, or None if not found or invalid id.

    Fields omitted from the patch are left unchanged; fields explicitly set to None are removed
    from the document ($unset), so cleared preferences read back as their model defaults.

    Raises InvalidHourRangeError when the patch combined with the stored values would leave
    preferred_hour_from >= preferred_hour_to. PlacePatch validates the range only within a
    single payload, so a one-sided patch must be checked against the stored counterpart.
    """
    try:
        oid = ObjectId(place_id)
    except InvalidId:
        return None
    fields = patch.model_dump(exclude_unset=True)
    collection = db[GMAPS_COLLECTION]

    # Only a one-sided non-null hour patch can conflict with a stored value: a payload with
    # both hours was already validated by PlacePatch, and clearing (null) cannot create a
    # violation. The read-then-update pair is not atomic, which is acceptable for this app.
    hour_keys = ("preferred_hour_from", "preferred_hour_to")
    if any(fields.get(k) is not None for k in hour_keys) and not all(k in fields for k in hour_keys):
        existing = await collection.find_one({"_id": oid})
        if existing is None:
            return None
        eff_from = fields.get("preferred_hour_from", existing.get("preferred_hour_from"))
        eff_to = fields.get("preferred_hour_to", existing.get("preferred_hour_to"))
        if eff_from is not None and eff_to is not None and eff_from >= eff_to:
            raise InvalidHourRangeError()

    set_fields = {k: v for k, v in fields.items() if v is not None}
    unset_fields = {k: "" for k, v in fields.items() if v is None}
    update: dict = {}
    if set_fields:
        update["$set"] = set_fields
    if unset_fields:
        update["$unset"] = unset_fields
    if not update:
        return await collection.find_one({"_id": oid})
    return await collection.find_one_and_update(
        {"_id": oid},
        update,
        return_document=ReturnDocument.AFTER,
    )


async def insert_place(db: AsyncDatabase, place: PlaceCreate) -> dict:
    """Insert a new place document and return the inserted document."""
    doc = place.model_dump(exclude_none=True)
    doc["skipped"] = False
    collection = db[GMAPS_COLLECTION]
    result = await collection.insert_one(doc)
    inserted = await collection.find_one({"_id": result.inserted_id})
    assert inserted is not None
    return inserted


async def delete_place(db: AsyncDatabase, place_id: str) -> bool:
    """Delete a place by its MongoDB ObjectId string. Returns True if a document was deleted."""
    try:
        oid = ObjectId(place_id)
    except InvalidId:
        return False
    result = await db[GMAPS_COLLECTION].delete_one({"_id": oid})
    return result.deleted_count > 0


async def fetch_enrichment_candidates(db: AsyncDatabase, limit: int) -> list[dict]:
    """Return places that have a place_id but no address, ordered by enrichment priority.

    Priority order:
    1. Never attempted (enriched_at is None) — returned first.
    2. Places within the 24-hour backoff window after a non-OK attempt — excluded entirely.
    3. All others sorted by enriched_at ASC so the stalest data is refreshed first.
    """
    collection = db[GMAPS_COLLECTION]
    pipeline = [
        {
            "$match": {
                "gmaps_place_id": {"$ne": None},
                "$or": [{"address": None}, {"address": ""}],
            }
        },
        {
            "$addFields": {
                "_never_attempted": {"$eq": ["$enriched_at", None]},
                "_recent_failure": {
                    "$and": [
                        {"$ne": ["$enriched_at", None]},
                        {"$ne": ["$details_status", None]},
                        {"$ne": ["$details_status", "OK"]},
                        {
                            "$gte": [
                                "$enriched_at",
                                {
                                    "$dateSubtract": {
                                        "startDate": "$$NOW",
                                        "unit": "hour",
                                        "amount": 24,
                                    }
                                },
                            ]
                        },
                    ]
                },
            }
        },
        {"$match": {"_recent_failure": False}},
        {"$addFields": {"_sort_tier": {"$cond": {"if": "$_never_attempted", "then": 0, "else": 1}}}},
        {"$sort": {"_sort_tier": 1, "enriched_at": 1}},
        {"$limit": limit},
        {"$project": {"gmaps_place_id": 1, "name": 1, "lat": 1, "lng": 1}},
    ]
    cursor = await collection.aggregate(pipeline)
    return await cursor.to_list(length=limit)


async def bulk_update_enrichment(db: AsyncDatabase, updates: list[UpdateOne]) -> int:
    """Apply a batch of enrichment updates. Returns the number of modified documents."""
    if not updates:
        return 0
    collection = db[GMAPS_COLLECTION]
    result = await collection.bulk_write(updates, ordered=False)
    return result.modified_count
