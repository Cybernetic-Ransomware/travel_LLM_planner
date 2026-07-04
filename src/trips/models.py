from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from src.optimizer.matrix.models import TransportMode
from src.optimizer.solver.models import OptimizeRequest, OptimizeResponse


class SaveTripRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    date: date
    optimizer_request: OptimizeRequest
    optimizer_response: OptimizeResponse
    selected_place_ids: list[str] = Field(min_length=2)
    transport_mode: TransportMode
    day_start_hour: int = Field(ge=0, le=23)
    day_end_hour: int = Field(ge=1, le=24)

    @model_validator(mode="after")
    def validate_hours(self) -> SaveTripRequest:
        if self.day_start_hour >= self.day_end_hour:
            raise ValueError("day_end_hour must be later than day_start_hour")
        return self


class TripSummaryOut(BaseModel):
    id: str
    name: str
    date: str
    created_at: str


class TripDetailOut(TripSummaryOut):
    optimizer_request: OptimizeRequest
    optimizer_response: OptimizeResponse
    selected_place_ids: list[str]
    transport_mode: TransportMode
    day_start_hour: int
    day_end_hour: int
