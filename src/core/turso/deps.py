from typing import Annotated

from fastapi import Depends, Request

from src.core.turso.adapter import TripDbConnection


def get_trip_db(request: Request) -> TripDbConnection:
    """FastAPI dependency — the shared Turso/libSQL connection for the trips domain."""
    return request.app.state.trip_db


TripDbDep = Annotated[TripDbConnection, Depends(get_trip_db)]
