from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from src.trips.models import SaveTripRequest, TripOut


class TripsManager:
    def __init__(self, db: AsyncDatabase) -> None:
        self._collection = db["trips"]

    async def save(self, request: SaveTripRequest) -> TripOut:
        doc = request.model_dump(mode="json")
        doc["created_at"] = datetime.now(UTC)
        result = await self._collection.insert_one(doc)
        return TripOut(
            id=str(result.inserted_id),
            name=request.name,
            date=str(request.date),
            created_at=doc["created_at"].isoformat(),
        )

    async def list_all(self) -> list[TripOut]:
        cursor = self._collection.find({}, sort=[("created_at", -1)])
        trips: list[TripOut] = []
        async for doc in cursor:
            trips.append(_to_trip_out(doc))
        return trips

    async def find_by_id(self, trip_id: str) -> TripOut | None:
        try:
            oid = ObjectId(trip_id)
        except Exception:
            return None
        doc = await self._collection.find_one({"_id": oid})
        if doc is None:
            return None
        return _to_trip_out(doc)


def _to_trip_out(doc: dict) -> TripOut:
    return TripOut(
        id=str(doc["_id"]),
        name=doc["name"],
        date=str(doc["date"]),
        created_at=doc["created_at"].isoformat(),
    )
