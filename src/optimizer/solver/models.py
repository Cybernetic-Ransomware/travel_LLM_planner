from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field, model_validator

from src.optimizer.matrix.models import TransportMode

_TRANSIT_MULTI_DAY_ERROR = (
    "TRANSIT mode is not supported for multi-day trips; the distance matrix cache does not track departure_date per day"
)


class TimeWindow:
    """Open/close bounds for a place, in seconds from midnight.

    Supports multiple non-overlapping segments (e.g. a lunch break splits the day into
    two valid windows).  The single-argument constructor ``TimeWindow(open_s, close_s)``
    creates a one-segment window and is fully backward-compatible; use
    ``TimeWindow.from_segments`` when multiple periods exist.
    """

    __slots__ = ("_segments",)

    def __init__(self, open_s: int, close_s: int) -> None:
        self._segments: list[tuple[int, int]] = [(open_s, close_s)]

    @classmethod
    def from_segments(cls, segments: list[tuple[int, int]]) -> TimeWindow:
        """Create a multi-segment window from a list of (open_s, close_s) pairs.

        Segments must be non-overlapping; they are sorted by open time.
        """
        obj = cls.__new__(cls)
        obj._segments = sorted(segments)
        return obj

    @property
    def segments(self) -> list[tuple[int, int]]:
        """All (open_s, close_s) segments, sorted by open time."""
        return self._segments

    @property
    def open_s(self) -> int:
        """Start of the first segment (used as EDF open in heuristics)."""
        return self._segments[0][0]

    @property
    def close_s(self) -> int:
        """End of the last segment (used as EDF deadline in heuristics)."""
        return self._segments[-1][1]

    def earliest_start(self, arrival_s: int, visit_s: int) -> int | None:
        """Return the earliest second the visit can begin, or None if it cannot fit.

        The visit of ``visit_s`` seconds must fit entirely within one segment.
        Waiting until a segment opens is allowed; arriving mid-break jumps to
        the next segment automatically.
        """
        for seg_open, seg_close in self._segments:
            start = max(arrival_s, seg_open)
            if start + visit_s <= seg_close:
                return start
        return None

    def __repr__(self) -> str:
        parts = []
        for seg_open, seg_close in self._segments:
            open_h, open_m = seg_open // 3600, (seg_open % 3600) // 60
            close_h, close_m = seg_close // 3600, (seg_close % 3600) // 60
            parts.append(f"{open_h:02d}:{open_m:02d}–{close_h:02d}:{close_m:02d}")
        return f"TimeWindow({', '.join(parts)})"


class OptimizeRequest(BaseModel):
    """Request body for a TSP route optimization."""

    place_ids: list[str] = Field(min_length=2, max_length=50)
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
    reason: str  # NO_COORDINATES | TIME_WINDOW_INFEASIBLE | NO_MATRIX_ENTRY | MATRIX_INCOMPLETE | DROPPED_LOW_PRIORITY


class OptimizeResponse(BaseModel):
    """Result of a TSP route optimization."""

    steps: list[RouteStep]
    total_travel_time_s: int
    total_visit_time_min: int
    total_wait_min: int
    transport_mode: TransportMode
    skipped: list[SkippedPlace]


class DaySlot(BaseModel):
    """A candidate day with optional time window for a multi-day place preference."""

    day_index: int = Field(ge=0)
    preferred_hour_from: int | None = None
    preferred_hour_to: int | None = None


class PlaceDayPreference(BaseModel):
    """Per-place day assignment and optional time overrides for a multi-day trip.

    day_preferences semantics:
    - empty list  → auto-assign to any day (greedy bin-pack)
    - one slot    → pinned to that day
    - two or more → flexible; assigned to the candidate day with most remaining capacity
    """

    place_id: str
    day_preferences: list[DaySlot] = []


class DayConfig(BaseModel):
    """Configuration for a single day in a multi-day trip."""

    date: date
    day_start_hour: int = Field(default=9, ge=0, le=23)
    day_end_hour: int = Field(default=21, ge=1, le=24)

    @model_validator(mode="after")
    def validate_day_range(self) -> DayConfig:
        if self.day_start_hour >= self.day_end_hour:
            raise ValueError("day_start_hour must be less than day_end_hour")
        return self


class MultiDayRequest(BaseModel):
    """Request body for a multi-day TSP trip optimization."""

    days: list[DayConfig] = Field(min_length=1, max_length=14)
    places: list[PlaceDayPreference] = Field(min_length=2, max_length=50)
    transport_mode: TransportMode = TransportMode.WALK
    start_lat: float | None = None
    start_lng: float | None = None

    @model_validator(mode="after")
    def validate_no_transit(self) -> MultiDayRequest:
        if self.transport_mode == TransportMode.TRANSIT:
            raise ValueError(_TRANSIT_MULTI_DAY_ERROR)
        return self

    @model_validator(mode="after")
    def validate_day_indices(self) -> MultiDayRequest:
        num_days = len(self.days)
        for pref in self.places:
            for slot in pref.day_preferences:
                if slot.day_index >= num_days:
                    raise ValueError(f"day_index {slot.day_index} is out of range for {num_days} day(s)")
        return self

    @model_validator(mode="after")
    def validate_unique_place_ids(self) -> MultiDayRequest:
        ids = [p.place_id for p in self.places]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate place_id found in places list")
        return self

    @model_validator(mode="after")
    def validate_start_location(self) -> MultiDayRequest:
        if (self.start_lat is None) != (self.start_lng is None):
            raise ValueError("start_lat and start_lng must both be provided or both omitted")
        return self


class DayPlan(BaseModel):
    """Optimized route for a single day within a multi-day trip."""

    day_index: int
    date: date
    steps: list[RouteStep]
    total_travel_time_s: int
    total_visit_time_min: int
    total_wait_min: int
    skipped: list[SkippedPlace]


class MultiDayResponse(BaseModel):
    """Result of a multi-day TSP trip optimization."""

    days: list[DayPlan]
    transport_mode: TransportMode
    unassigned: list[SkippedPlace]
