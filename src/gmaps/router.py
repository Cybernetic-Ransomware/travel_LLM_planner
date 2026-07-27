import pendulum
from fastapi import APIRouter, HTTPException, Query
from pymongo import UpdateOne

from src.config.conf_logger import setup_logger
from src.core.auth import CurrentUserDep
from src.core.db.deps import MongoDbDep
from src.core.exceptions import PlaceResolutionError
from src.gmaps.deps import GooglePlacesDep
from src.gmaps.models import (
    EnrichRequest,
    EnrichResponse,
    ImportRequest,
    ImportResponse,
    PlaceOut,
    PlacePatch,
)
from src.gmaps.scraper import scrape_public_list
from src.gmaps.storage import (
    apply_enrichment_update,
    bulk_update_enrichment,
    delete_place,
    fetch_enrichment_candidates,
    fetch_place_by_id,
    fetch_places,
    find_and_update_place,
    upsert_places,
)

router = APIRouter()
logger = setup_logger(__name__, "gmaps_enrich")


@router.post("/import", response_model=ImportResponse)
async def import_public_list(payload: ImportRequest, db: MongoDbDep, _user: CurrentUserDep) -> ImportResponse:
    scraped_at = pendulum.now("UTC")
    places, list_name = await scrape_public_list(str(payload.list_url))
    upserted = await upsert_places(
        db, places, source_list_url=str(payload.list_url), scraped_at=scraped_at, list_name=list_name
    )

    return ImportResponse(
        list_url=payload.list_url,
        list_name=list_name,
        scraped_at=scraped_at,
        total=len(places),
        upserted=upserted,
    )


@router.post("/enrich", response_model=EnrichResponse)
async def enrich_places(
    payload: EnrichRequest, db: MongoDbDep, gp: GooglePlacesDep, _user: CurrentUserDep
) -> EnrichResponse:
    api_key = gp.api_key
    logger.info(
        "Enrich start: key_present=%s key_len=%s key_last4=%s",
        bool(api_key),
        len(api_key),
        api_key[-4:] if api_key else None,
    )
    candidates = await fetch_enrichment_candidates(db, payload.limit)
    updates: list[UpdateOne] = []
    for doc in candidates:
        update_fields, _ = await gp.build_enrichment_update(doc)
        updates.append(UpdateOne({"_id": doc["_id"]}, {"$set": update_fields}))

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
async def patch_place(place_id: str, payload: PlacePatch, db: MongoDbDep, _user: CurrentUserDep) -> PlaceOut:
    """Update scheduling preferences for a place."""
    doc = await find_and_update_place(db, place_id, payload)
    if doc is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return PlaceOut.model_validate(doc)


@router.delete("/places/{place_id}", status_code=204)
async def remove_place(place_id: str, db: MongoDbDep, _user: CurrentUserDep) -> None:
    """Delete a place by its MongoDB ObjectId."""
    deleted = await delete_place(db, place_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Place not found")


@router.post("/places/{place_id}/enrich", response_model=PlaceOut)
async def enrich_place(place_id: str, db: MongoDbDep, gp: GooglePlacesDep, _user: CurrentUserDep) -> PlaceOut:
    """Enrich a single place via the Google Places API and return the updated record."""
    doc = await fetch_place_by_id(db, place_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Place not found")

    update_fields, resolved = await gp.build_enrichment_update(doc)
    updated = await apply_enrichment_update(db, place_id, update_fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Place not found")

    if not resolved:
        raise PlaceResolutionError(update_fields.get("details_status"), update_fields.get("details_error"))

    return PlaceOut.model_validate(updated)


@router.get("/keycheck")
async def keycheck(gp: GooglePlacesDep):
    api_key = gp.api_key
    return {
        "present": bool(api_key),
        "length": len(api_key),
        "last4": api_key[-4:] if api_key else None,
    }
