from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field, model_validator

from src.optimizer.matrix.models import TransportMode


class TimeWindow:
    """Open/close bounds for a single place, in seconds from midnight."""

    __slots__ = ("open_s", "close_s")

    def __init__(self, open_s: int, close_s: int) -> None:
        self.open_s = open_s
        self.close_s = close_s

    def __repr__(self) -> str:
        open_h, open_m = self.open_s // 3600, (self.open_s % 3600) // 60
        close_h, close_m = self.close_s // 3600, (self.close_s % 3600) // 60
        return f"TimeWindow({open_h:02d}:{open_m:02d}–{close_h:02d}:{close_m:02d})"


class OptimizeRequest(BaseModel):
    """Request body for a TSP route optimization."""

    place_ids: list[str] = Field(min_length=2)
    transport_mode: TransportMode = TransportMode.WALK
    day_start_hour: int = Field(default=9, ge=0, le=23)
    day_end_hour: int = Field(default=21, ge=1, le=24)
    start_lat: float | None = None
    start_lng: float | None = None
    departure_date: date | None = None

    @model_validator(mode="after")
    def validate_day_range(self) -> OptimizeRequest:
        if self.day_start_hour >= self.day_end_hour:
            raise ValueError("day_start_hour must be less than day_end_hour")
        return self

    @model_validator(mode="after")
    def validate_start_location(self) -> OptimizeRequest:
        if (self.start_lat is None) != (self.start_lng is None):
            raise ValueError("start_lat and start_lng must both be provided or both omitted")
        return self


class RouteStep(BaseModel):
    """A single stop in the optimized route."""

    place_id: str
    name: str | None
    lat: float | None
    lng: float | None
    arrival_time: time
    departure_time: time
    travel_from_previous_s: int
    visit_duration_min: int
    wait_min: int = 0  # waiting time if arrived before place opens


class SkippedPlace(BaseModel):
    """A place that could not be included in the route."""

    place_id: str
    name: str | None
    reason: str  # NO_COORDINATES | TIME_WINDOW_INFEASIBLE | NO_MATRIX_ENTRY


class OptimizeResponse(BaseModel):
    """Result of a TSP route optimization."""

    steps: list[RouteStep]
    total_travel_time_s: int
    total_visit_time_min: int
    total_wait_min: int
    transport_mode: TransportMode
    skipped: list[SkippedPlace]
