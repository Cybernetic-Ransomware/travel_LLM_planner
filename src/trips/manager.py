from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from src.core.exceptions import (
    MissingExpectedRevisionError,
    TripConcurrencyConflictError,
    TripPlanTypeConflictError,
)
from src.optimizer.solver.models import (
    MultiDayRequest,
    MultiDayResponse,
    OptimizeRequest,
    OptimizeResponse,
)
from src.trips.models import (
    SCHEMA_VERSION,
    MultiDayTripDetailOut,
    MultiDayTripSummaryOut,
    SaveTripRequest,
    SingleDayTripDetailOut,
    SingleDayTripSummaryOut,
    TripDetailOut,
    TripSummaryOut,
)

TRIPS_COLLECTION = "trips"

_LIST_PROJECTION = {
    "name": 1,
    "date": 1,
    "plan_type": 1,
    "created_at": 1,
    "multi_day_request.days.date": 1,
}


class TripsManager:
    def __init__(self, db: AsyncDatabase) -> None:
        self._collection = db[TRIPS_COLLECTION]

    async def save(self, request: SaveTripRequest) -> TripDetailOut:
        # save-as-new ignores any expected_revision the client sent; a brand-new trip starts at revision 0.
        doc = request.model_dump(mode="json", exclude={"expected_revision"})
        doc["schema_version"] = SCHEMA_VERSION
        doc["revision"] = 0
        doc["created_at"] = datetime.now(UTC)
        result = await self._collection.insert_one(doc)
        return _to_trip_detail_out({**doc, "_id": result.inserted_id})

    async def list_all(self) -> list[TripSummaryOut]:
        cursor = self._collection.find({}, _LIST_PROJECTION, sort=[("created_at", -1)])
        trips: list[TripSummaryOut] = []
        async for doc in cursor:
            trips.append(_to_trip_summary_out(doc))
        return trips

    async def find_by_id(self, trip_id: str) -> TripDetailOut | None:
        oid = _parse_object_id(trip_id)
        if oid is None:
            return None
        doc = await self._collection.find_one({"_id": oid})
        if doc is None:
            return None
        return _to_trip_detail_out(doc)

    async def update(self, trip_id: str, request: SaveTripRequest) -> TripDetailOut | None:
        """Compare-and-set update shared by ``PUT /core/trips/{id}`` and the chat editor.

        ``expected_revision`` is mandatory: a missing token is a 428, a stale token is
        a 409, a match writes request+response and ``$inc``s ``revision`` in one atomic
        ``find_one_and_update``. Legacy docs without a ``revision`` field count as 0.
        """
        oid = _parse_object_id(trip_id)
        if oid is None:
            return None

        existing = await self._collection.find_one({"_id": oid}, {"plan_type": 1})
        if existing is None:
            return None
        existing_plan_type = existing.get("plan_type", "SINGLE_DAY")
        if existing_plan_type != request.plan_type:
            raise TripPlanTypeConflictError(trip_id, existing_plan_type, request.plan_type)

        # 428 only after id/plan_type checks, so the missing token can't mask a more fundamental error.
        if request.expected_revision is None:
            raise MissingExpectedRevisionError(trip_id)
        expected = request.expected_revision
        if expected == 0:
            revision_filter: dict = {"$or": [{"revision": 0}, {"revision": {"$exists": False}}]}
        else:
            revision_filter = {"revision": expected}

        update = request.model_dump(mode="json", exclude={"expected_revision"})
        update["schema_version"] = SCHEMA_VERSION
        update["updated_at"] = datetime.now(UTC)
        doc = await self._collection.find_one_and_update(
            {"_id": oid, **revision_filter},
            {"$set": update, "$inc": {"revision": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            raise TripConcurrencyConflictError(trip_id, expected=expected)
        return _to_trip_detail_out(doc)

    async def delete(self, trip_id: str) -> bool:
        oid = _parse_object_id(trip_id)
        if oid is None:
            return False
        result = await self._collection.delete_one({"_id": oid})
        return result.deleted_count > 0


def _parse_object_id(trip_id: str) -> ObjectId | None:
    try:
        return ObjectId(trip_id)
    except Exception:
        return None


def _to_trip_summary_out(doc: dict) -> TripSummaryOut:
    plan_type = doc.get("plan_type", "SINGLE_DAY")
    if plan_type == "MULTI_DAY":
        days_raw = doc["multi_day_request"]["days"]
        dates = [d["date"] for d in days_raw]
        return MultiDayTripSummaryOut(
            id=str(doc["_id"]),
            name=doc["name"],
            created_at=doc["created_at"].isoformat(),
            start_date=min(dates),
            end_date=max(dates),
            num_days=len(days_raw),
        )
    return SingleDayTripSummaryOut(
        id=str(doc["_id"]),
        name=doc["name"],
        date=str(doc["date"]),
        created_at=doc["created_at"].isoformat(),
    )


def _to_trip_detail_out(doc: dict) -> TripDetailOut:
    plan_type = doc.get("plan_type", "SINGLE_DAY")
    if plan_type == "MULTI_DAY":
        req = MultiDayRequest.model_validate(doc["multi_day_request"])
        resp = MultiDayResponse.model_validate(doc["multi_day_response"])
        dates = [d.date for d in req.days]
        return MultiDayTripDetailOut(
            id=str(doc["_id"]),
            name=doc["name"],
            created_at=doc["created_at"].isoformat(),
            updated_at=doc["updated_at"].isoformat() if doc.get("updated_at") else None,
            revision=doc.get("revision", 0),
            start_date=str(min(dates)),
            end_date=str(max(dates)),
            num_days=len(req.days),
            transport_mode=req.transport_mode,
            multi_day_request=req,
            multi_day_response=resp,
        )
    req = OptimizeRequest.model_validate(doc["optimizer_request"])
    resp = OptimizeResponse.model_validate(doc["optimizer_response"])
    return SingleDayTripDetailOut(
        id=str(doc["_id"]),
        name=doc["name"],
        date=str(doc["date"]),
        created_at=doc["created_at"].isoformat(),
        updated_at=doc["updated_at"].isoformat() if doc.get("updated_at") else None,
        revision=doc.get("revision", 0),
        optimizer_request=req,
        optimizer_response=resp,
        selected_place_ids=req.place_ids,
        transport_mode=req.transport_mode,
        day_start_hour=req.day_start_hour,
        day_end_hour=req.day_end_hour,
    )
