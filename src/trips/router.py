from fastapi import APIRouter, HTTPException

from src.trips.deps import TripsDep
from src.trips.models import SaveTripRequest, TripDetailOut, TripSummaryOut

router = APIRouter()


@router.post("/", response_model=TripDetailOut, status_code=201)
async def save_trip(body: SaveTripRequest, trips: TripsDep) -> TripDetailOut:
    """Persist an optimizer result as a named trip."""
    return await trips.save(body)


@router.get("/", response_model=list[TripSummaryOut])
async def list_trips(trips: TripsDep) -> list[TripSummaryOut]:
    """Return all saved trips, newest first."""
    return await trips.list_all()


@router.get("/{trip_id}", response_model=TripDetailOut)
async def get_trip(trip_id: str, trips: TripsDep) -> TripDetailOut:
    """Return a single saved trip by its MongoDB id."""
    trip = await trips.find_by_id(trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id!r} not found")
    return trip
