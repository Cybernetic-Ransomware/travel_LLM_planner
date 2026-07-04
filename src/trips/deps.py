from typing import Annotated

from fastapi import Depends

from src.core.db.deps import MongoDbDep
from src.trips.manager import TripsManager


def get_trips_manager(db: MongoDbDep) -> TripsManager:
    return TripsManager(db)


TripsDep = Annotated[TripsManager, Depends(get_trips_manager)]
