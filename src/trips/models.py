from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from src.optimizer.matrix.models import TransportMode
from src.optimizer.solver.models import OptimizeRequest, OptimizeResponse


class SaveTripRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    date: date
    optimizer_request: OptimizeRequest
    optimizer_response: OptimizeResponse


class TripSummaryOut(BaseModel):
    id: str
    name: str
    date: str
    created_at: str


class TripDetailOut(TripSummaryOut):
    updated_at: str | None = None
    optimizer_request: OptimizeRequest
    optimizer_response: OptimizeResponse
    selected_place_ids: list[str]
    transport_mode: TransportMode
    day_start_hour: int
    day_end_hour: int
