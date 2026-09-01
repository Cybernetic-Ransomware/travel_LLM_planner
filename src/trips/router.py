from fastapi import APIRouter, HTTPException, Path

from src.trips.deps import TripRepositoryDep
from src.trips.editing.summary import manual_update_summary
from src.trips.models import (
    RestoreRevisionRequest,
    SaveTripRequest,
    TripDetailOut,
    TripRevisionDetailOut,
    TripRevisionListOut,
    TripSummaryOut,
)

router = APIRouter()


@router.post("/", response_model=TripDetailOut, status_code=201)
async def save_trip(body: SaveTripRequest, trips: TripRepositoryDep) -> TripDetailOut:
    """Persist an optimizer result (single-day or multi-day) as a named trip."""
    return await trips.save(body)


@router.get("/", response_model=list[TripSummaryOut])
async def list_trips(trips: TripRepositoryDep) -> list[TripSummaryOut]:
    """Return all saved trips, newest first."""
    return await trips.list_all()


@router.get("/{trip_id}", response_model=TripDetailOut)
async def get_trip(trip_id: str, trips: TripRepositoryDep) -> TripDetailOut:
    """Return a single saved trip by its id."""
    trip = await trips.get(trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id!r} not found")
    return trip


@router.put("/{trip_id}", response_model=TripDetailOut)
async def update_trip(trip_id: str, body: SaveTripRequest, trips: TripRepositoryDep) -> TripDetailOut:
    """Replace a saved trip's content. Rejects changing plan_type (409); requires
    ``expected_revision`` (428 if missing, 409 if stale)."""
    trip = await trips.update(trip_id, body, source="MANUAL", summary=manual_update_summary(body))
    if trip is None:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id!r} not found")
    return trip


@router.delete("/{trip_id}", status_code=204)
async def delete_trip(trip_id: str, trips: TripRepositoryDep) -> None:
    """Delete a saved trip and its whole revision history."""
    deleted = await trips.delete(trip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id!r} not found")


@router.get("/{trip_id}/revisions", response_model=TripRevisionListOut)
async def list_trip_revisions(trip_id: str, trips: TripRepositoryDep) -> TripRevisionListOut:
    """List every persisted revision of a trip, newest first (no snapshot bodies)."""
    revisions = await trips.list_revisions(trip_id)
    if revisions is None:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id!r} not found")
    return revisions


@router.get("/{trip_id}/revisions/{revision}", response_model=TripRevisionDetailOut)
async def get_trip_revision(
    trip_id: str,
    trips: TripRepositoryDep,
    revision: int = Path(ge=0),
) -> TripRevisionDetailOut:
    """Return the full snapshot of one historical revision."""
    detail = await trips.get_revision(trip_id, revision)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Trip {trip_id!r} has no revision {revision}")
    return detail


@router.post("/{trip_id}/revisions/{revision}/restore", response_model=TripDetailOut)
async def restore_trip_revision(
    trip_id: str,
    body: RestoreRevisionRequest,
    trips: TripRepositoryDep,
    revision: int = Path(ge=0),
) -> TripDetailOut:
    """Restore an earlier revision. Creates a new higher revision that byte-copies the
    target snapshot (``source='REVERT'``); never re-runs the optimizer. 409 on a stale
    ``expected_revision``, 404 for an unknown revision, 400 if the target is already current.
    """
    return await trips.restore_revision(trip_id, revision, expected_revision=body.expected_revision)
