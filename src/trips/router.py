from fastapi import APIRouter, HTTPException

from src.trips.deps import TripsDep
from src.trips.models import SaveTripRequest, TripOut

router = APIRouter()


@router.post("/", response_model=TripOut, status_code=201)
async def save_trip(body: SaveTripRequest, trips: TripsDep) -> TripOut:
    """Persist an optimizer result as a named trip."""
    return await trips.save(body)


@router.get("/", response_model=list[TripOut])
async def list_trips(trips: TripsDep) -> list[TripOut]:
    """Return all saved trips, newest first."""
    return await trips.list_all()


@router.get("/{trip_id}", response_model=TripOut)
async def get_trip(trip_id: str, trips: TripsDep) -> TripOut:
    """Return a single saved trip by its MongoDB id."""
    trip = await trips.find_by_id(trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id!r} not found")
    return trip
