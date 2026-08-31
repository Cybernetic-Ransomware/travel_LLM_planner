from typing import Annotated

from fastapi import Depends

from src.core.turso.deps import TripDbDep
from src.trips.repository import TripRepository


def get_trip_repository(db: TripDbDep) -> TripRepository:
    return TripRepository(db)


TripRepositoryDep = Annotated[TripRepository, Depends(get_trip_repository)]
