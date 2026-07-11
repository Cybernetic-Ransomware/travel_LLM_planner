from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from src.optimizer.solver.models import OptimizeRequest, OptimizeResponse
from src.trips.models import SaveTripRequest, TripDetailOut, TripSummaryOut

TRIPS_COLLECTION = "trips"


class TripsManager:
    def __init__(self, db: AsyncDatabase) -> None:
        self._collection = db[TRIPS_COLLECTION]

    async def save(self, request: SaveTripRequest) -> TripDetailOut:
        doc = request.model_dump(mode="json")
        doc["created_at"] = datetime.now(UTC)
        result = await self._collection.insert_one(doc)
        return _to_trip_detail_out({**doc, "_id": result.inserted_id})

    async def list_all(self) -> list[TripSummaryOut]:
        cursor = self._collection.find({}, sort=[("created_at", -1)])
        trips: list[TripSummaryOut] = []
        async for doc in cursor:
            trips.append(_to_trip_summary_out(doc))
        return trips

    async def find_by_id(self, trip_id: str) -> TripDetailOut | None:
        try:
            oid = ObjectId(trip_id)
        except Exception:
            return None
        doc = await self._collection.find_one({"_id": oid})
        if doc is None:
            return None
        return _to_trip_detail_out(doc)

    async def update(self, trip_id: str, request: SaveTripRequest) -> TripDetailOut | None:
        try:
            oid = ObjectId(trip_id)
        except Exception:
            return None
        update = request.model_dump(mode="json")
        update["updated_at"] = datetime.now(UTC)
        doc = await self._collection.find_one_and_update(
            {"_id": oid}, {"$set": update}, return_document=ReturnDocument.AFTER
        )
        if doc is None:
            return None
        return _to_trip_detail_out(doc)

    async def delete(self, trip_id: str) -> bool:
        try:
            oid = ObjectId(trip_id)
        except Exception:
            return False
        result = await self._collection.delete_one({"_id": oid})
        return result.deleted_count > 0


def _to_trip_summary_out(doc: dict) -> TripSummaryOut:
    return TripSummaryOut(
        id=str(doc["_id"]),
        name=doc["name"],
        date=str(doc["date"]),
        created_at=doc["created_at"].isoformat(),
    )


def _to_trip_detail_out(doc: dict) -> TripDetailOut:
    req = OptimizeRequest.model_validate(doc["optimizer_request"])
    resp = OptimizeResponse.model_validate(doc["optimizer_response"])
    return TripDetailOut(
        id=str(doc["_id"]),
        name=doc["name"],
        date=str(doc["date"]),
        created_at=doc["created_at"].isoformat(),
        updated_at=doc["updated_at"].isoformat() if doc.get("updated_at") else None,
        optimizer_request=req,
        optimizer_response=resp,
        selected_place_ids=req.place_ids,
        transport_mode=req.transport_mode,
        day_start_hour=req.day_start_hour,
        day_end_hour=req.day_end_hour,
    )
