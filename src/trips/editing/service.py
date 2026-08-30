"""The single load -> mutate -> re-validate -> optimize -> compare-and-set-persist path.

Any failure before the final write raises first, so a failed edit leaves the stored
trip untouched; the persisted request and response are from the same ``optimize_trip`` run.
"""

from __future__ import annotations

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from src.config.conf_logger import setup_logger
from src.core.exceptions import (
    MatrixUnavailableError,
)
from src.core.exceptions import (
    TripConcurrencyConflictError as HTTPTripConcurrencyConflictError,
)
from src.optimizer.matrix.client import GoogleRoutesManager
from src.optimizer.solver.multi_day_service import optimize_trip
from src.trips.editing.apply import apply_operations
from src.trips.editing.errors import (
    OptimizerFailedError,
    TripConcurrencyConflictError,
    TripDeletedError,
    TripNotFoundError,
    TripPersistenceError,
    UnsupportedPlanTypeError,
)
from src.trips.editing.operations import TripEditOperation
from src.trips.manager import TripsManager
from src.trips.models import MultiDaySaveTripRequest, MultiDayTripDetailOut

logger = setup_logger(__name__, "orchestrator")


class MultiDayTripEditor:
    def __init__(self, db: AsyncDatabase, trips_manager: TripsManager, routes_manager: GoogleRoutesManager) -> None:
        self._db = db
        self._trips = trips_manager
        self._routes = routes_manager

    async def apply(
        self,
        trip_id: str,
        operations: list[TripEditOperation],
        expected_revision: int,
    ) -> MultiDayTripDetailOut:
        trip = await self._trips.find_by_id(trip_id)
        if trip is None:
            raise TripNotFoundError()
        # find_by_id returns a concrete class, so this equals a plan_type check (ADR-18) and narrows.
        if not isinstance(trip, MultiDayTripDetailOut):
            raise UnsupportedPlanTypeError()
        if trip.revision != expected_revision:
            raise TripConcurrencyConflictError()

        outcome = apply_operations(trip.multi_day_request, operations)

        try:
            response = await optimize_trip(self._db, self._routes, outcome.request)
        except MatrixUnavailableError as exc:
            raise OptimizerFailedError("The routing service is unavailable right now; nothing was saved.") from exc
        except (ValueError, TypeError) as exc:
            raise OptimizerFailedError() from exc

        save_request = MultiDaySaveTripRequest(
            plan_type="MULTI_DAY",
            name=trip.name,
            multi_day_request=outcome.request,
            multi_day_response=response,
            expected_revision=expected_revision,
        )

        try:
            updated = await self._trips.update(trip_id, save_request)
        except HTTPTripConcurrencyConflictError as exc:
            raise TripConcurrencyConflictError() from exc
        except PyMongoError as exc:
            logger.exception("Trip persistence failed for trip_id=%s", trip_id)
            raise TripPersistenceError() from exc

        if updated is None:
            # update() returns None only when the document vanished between the read and the write.
            raise TripDeletedError()
        if not isinstance(updated, MultiDayTripDetailOut):  # pragma: no cover - update() preserves plan_type
            raise UnsupportedPlanTypeError()
        return updated
