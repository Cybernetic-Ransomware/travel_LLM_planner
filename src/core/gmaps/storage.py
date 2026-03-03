from collections.abc import Iterable
from datetime import datetime

from pymongo import MongoClient, UpdateOne

from src.config.config import settings
from src.core.gmaps.models import ScrapedPlace


def _get_collection():
    client = MongoClient(settings.mongo_uri)
    db = client[settings.mongo_db]
    collection = db["gmaps_places"]
    collection.create_index("maps_url", unique=True, sparse=True)
    collection.create_index("source_list_url")
    collection.create_index("scraped_at")
    return collection


def upsert_places(
    places: Iterable[ScrapedPlace], *, source_list_url: str, scraped_at: datetime, list_name: str | None = None
) -> int:
    collection = _get_collection()
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

    result = collection.bulk_write(ops, ordered=False)
    return result.upserted_count + result.modified_count


def fetch_places_missing_address(limit: int) -> list[dict]:
    collection = _get_collection()
    cursor = collection.find(
        {
            "gmaps_place_id": {"$ne": None},
            "$or": [{"address": None}, {"address": ""}],
        },
        {"gmaps_place_id": 1, "name": 1, "lat": 1, "lng": 1},
        limit=limit,
    )
    return list(cursor)


def bulk_update_enrichment(updates: list[UpdateOne]) -> int:
    if not updates:
        return 0
    collection = _get_collection()
    result = collection.bulk_write(updates, ordered=False)
    return result.modified_count
