import pendulum
from fastapi import APIRouter
from pymongo import UpdateOne

from src.config.conf_logger import setup_logger
from src.config.config import settings
from src.core.db.deps import MongoDbDep
from src.core.gmaps.enricher import fetch_place_details, search_place_id
from src.core.gmaps.models import (
    EnrichRequest,
    EnrichResponse,
    ImportRequest,
    ImportResponse,
    PlaceOut,
    PlacePatch,
)
from src.core.gmaps.scraper import scrape_public_list
from src.core.gmaps.storage import (
    bulk_update_enrichment,
    delete_place,
    fetch_place_by_id,
    fetch_places,
    fetch_places_missing_address,
    update_place,
    upsert_places,
)

router = APIRouter()
logger = setup_logger(__name__, "gmaps_enrich")


@router.post("/import", response_model=ImportResponse)
async def import_public_list(payload: ImportRequest) -> ImportResponse:
    scraped_at = pendulum.now("UTC")
    places, list_name = await scrape_public_list(str(payload.list_url))
    upserted = upsert_places(places, source_list_url=str(payload.list_url), scraped_at=scraped_at, list_name=list_name)

    return ImportResponse(
        list_url=payload.list_url,
        list_name=list_name,
        scraped_at=scraped_at,
        total=len(places),
        upserted=upserted,
    )


@router.post("/enrich", response_model=EnrichResponse)
async def enrich_places(payload: EnrichRequest, db: MongoDbDep) -> EnrichResponse:
    api_key = settings.google_places_api_key
    logger.info(
        "Enrich start: key_present=%s key_len=%s key_last4=%s",
        bool(api_key),
        len(api_key),
        api_key[-4:] if api_key else None,
    )
    candidates = await fetch_places_missing_address(db, payload.limit)
    updates: list[UpdateOne] = []
    for doc in candidates:
        place_id = doc.get("gmaps_place_id")
        if place_id and not str(place_id).startswith("ChI"):
            place_id = None
        details = None
        status = None
        error_message = None

        if place_id:
            details, status, error_message = await fetch_place_details(place_id)

        if not details:
            resolved_id, resolve_status, resolve_error = await search_place_id(
                doc.get("name"), doc.get("lat"), doc.get("lng")
            )
            update_doc = {
                "details_status": resolve_status or status,
                "details_error": resolve_error or error_message,
                "resolve_status": resolve_status,
                "resolve_error": resolve_error,
                "enriched_at": pendulum.now("UTC"),
            }
            if resolved_id:
                details, status, error_message = await fetch_place_details(resolved_id)
                update_doc["gmaps_place_id"] = resolved_id
                update_doc["details_status"] = status
                update_doc["details_error"] = error_message
            if details:
                update_doc["details"] = details
                update_doc["address"] = details.get("formattedAddress")
            updates.append(UpdateOne({"_id": doc["_id"]}, {"$set": update_doc}))
            continue

        update_doc = {
            "details_status": status,
            "details_error": error_message,
            "details": details,
            "address": details.get("formattedAddress") if details else None,
            "enriched_at": pendulum.now("UTC"),
        }
        updates.append(UpdateOne({"_id": doc["_id"]}, {"$set": update_doc}))

    updated = await bulk_update_enrichment(db, updates)
    return EnrichResponse(scanned=len(candidates), updated=updated)


@router.get("/places", response_model=list[PlaceOut])
async def list_places(
    db: MongoDbDep,
    skipped: bool | None = Query(None),
    list_name: str | None = Query(None),
) -> list[PlaceOut]:
    """Return all places, optionally filtered by skipped flag or list name."""
    docs = await fetch_places(db, skipped=skipped, list_name=list_name)
    return [PlaceOut.model_validate(doc) for doc in docs]


@router.get("/places/{place_id}", response_model=PlaceOut)
async def get_place(place_id: str, db: MongoDbDep) -> PlaceOut:
    """Return a single place by its MongoDB ObjectId."""
    doc = await fetch_place_by_id(db, place_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return PlaceOut.model_validate(doc)


@router.patch("/places/{place_id}", response_model=PlaceOut)
async def patch_place(place_id: str, payload: PlacePatch, db: MongoDbDep) -> PlaceOut:
    """Update scheduling preferences for a place."""
    matched = await update_place(db, place_id, payload)
    if not matched:
        raise HTTPException(status_code=404, detail="Place not found")
    doc = await fetch_place_by_id(db, place_id)
    return PlaceOut.model_validate(doc)


@router.delete("/places/{place_id}", status_code=204)
async def remove_place(place_id: str, db: MongoDbDep) -> None:
    """Delete a place by its MongoDB ObjectId."""
    deleted = await delete_place(db, place_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Place not found")


@router.get("/keycheck")
async def keycheck():
    api_key = settings.google_places_api_key
    return {
        "present": bool(api_key),
        "length": len(api_key),
        "last4": api_key[-4:] if api_key else None,
    }
