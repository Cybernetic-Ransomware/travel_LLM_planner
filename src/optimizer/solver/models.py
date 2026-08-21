from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field, model_validator

from src.accommodations.models import AccommodationStay, validate_no_stay_overlaps
from src.accommodations.resolver import DayAccommodationAnchors, resolve_day_anchors
from src.optimizer.matrix.models import TransportMode
from src.time_validation import NaiveTime
from src.transfers.models import TransferBlock

_TRANSIT_MULTI_DAY_ERROR = (
    "TRANSIT mode is not supported for multi-day trips; the distance matrix cache does not track departure_date per day"
)


def resolve_day_bound_s(hour: int, explicit_time: time | None) -> int:
    """Effective seconds-from-midnight for a day bound: explicit_time wins when set."""
    if explicit_time is not None:
        return explicit_time.hour * 3600 + explicit_time.minute * 60 + explicit_time.second
    return hour * 3600


def seconds_to_time(s: int) -> time:
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return time(hour=h % 24, minute=m, second=sec)


def _is_transition_day(anchors: DayAccommodationAnchors) -> bool:
    """True when START/END resolve to two different stays — mirrors multi_day_service, see ADR-15/16."""
    return anchors.start is not None and anchors.end is not None and anchors.start is not anchors.end


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

    place_ids: list[str] = Field(min_length=1, max_length=50)
    transport_mode: TransportMode = TransportMode.WALK
    day_start_hour: int = Field(default=9, ge=0, le=23)
    day_end_hour: int = Field(default=21, ge=1, le=24)
    day_start_time: NaiveTime | None = None
    day_end_time: NaiveTime | None = None
    start_lat: float | None = None
    start_lng: float | None = None
    end_lat: float | None = None
    end_lng: float | None = None
    departure_date: date | None = None

    @model_validator(mode="after")
    def validate_day_end_time_semantics(self) -> OptimizeRequest:
        if self.day_end_time == time(0, 0):
            raise ValueError("day_end_time cannot represent midnight; use day_end_hour=24 instead")
        if self.day_end_hour == 24 and self.day_end_time is not None:
            raise ValueError("day_end_time cannot be combined with day_end_hour=24")
        return self

    @model_validator(mode="after")
    def validate_day_range(self) -> OptimizeRequest:
        start_s = resolve_day_bound_s(self.day_start_hour, self.day_start_time)
        end_s = resolve_day_bound_s(self.day_end_hour, self.day_end_time)
        if start_s >= end_s:
            raise ValueError("effective day start must be before effective day end")
        return self

    @model_validator(mode="after")
    def validate_start_location(self) -> OptimizeRequest:
        if (self.start_lat is None) != (self.start_lng is None):
            raise ValueError("start_lat and start_lng must both be provided or both omitted")
        return self

    @model_validator(mode="after")
    def validate_end_location(self) -> OptimizeRequest:
        if (self.end_lat is None) != (self.end_lng is None):
            raise ValueError("end_lat and end_lng must both be provided or both omitted")
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
    # NO_COORDINATES | TIME_WINDOW_INFEASIBLE | NO_MATRIX_ENTRY | MATRIX_INCOMPLETE | DROPPED_LOW_PRIORITY
    # | TRANSFER_DAY_GEOGRAPHY_MISMATCH | TRANSFER_WINDOW_INFEASIBLE | CAPACITY_EXCEEDED
    reason: str


class OptimizeResponse(BaseModel):
    """Result of a TSP route optimization."""

    steps: list[RouteStep]
    total_travel_time_s: int
    total_visit_time_min: int
    total_wait_min: int
    transport_mode: TransportMode
    skipped: list[SkippedPlace]
    travel_to_end_s: int = 0


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
    day_start_time: NaiveTime | None = None
    day_end_time: NaiveTime | None = None
    start_lat: float | None = None
    start_lng: float | None = None
    end_lat: float | None = None
    end_lng: float | None = None

    @model_validator(mode="after")
    def validate_day_end_time_semantics(self) -> DayConfig:
        if self.day_end_time == time(0, 0):
            raise ValueError("day_end_time cannot represent midnight; use day_end_hour=24 instead")
        if self.day_end_hour == 24 and self.day_end_time is not None:
            raise ValueError("day_end_time cannot be combined with day_end_hour=24")
        return self

    @model_validator(mode="after")
    def validate_day_range(self) -> DayConfig:
        start_s = resolve_day_bound_s(self.day_start_hour, self.day_start_time)
        end_s = resolve_day_bound_s(self.day_end_hour, self.day_end_time)
        if start_s >= end_s:
            raise ValueError("effective day start must be before effective day end")
        return self

    @model_validator(mode="after")
    def validate_start_location(self) -> DayConfig:
        if (self.start_lat is None) != (self.start_lng is None):
            raise ValueError("start_lat and start_lng must both be provided or both omitted")
        return self

    @model_validator(mode="after")
    def validate_end_location(self) -> DayConfig:
        if (self.end_lat is None) != (self.end_lng is None):
            raise ValueError("end_lat and end_lng must both be provided or both omitted")
        return self


class MultiDayRequest(BaseModel):
    """Request body for a multi-day TSP trip optimization."""

    days: list[DayConfig] = Field(min_length=1, max_length=31)
    places: list[PlaceDayPreference] = Field(min_length=2, max_length=50)
    transport_mode: TransportMode = TransportMode.WALK
    start_lat: float | None = None
    start_lng: float | None = None
    end_lat: float | None = None
    end_lng: float | None = None
    accommodations: list[AccommodationStay] = Field(default_factory=list)
    transfers: list[TransferBlock] = Field(default_factory=list)

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

    @model_validator(mode="after")
    def validate_end_location(self) -> MultiDayRequest:
        if (self.end_lat is None) != (self.end_lng is None):
            raise ValueError("end_lat and end_lng must both be provided or both omitted")
        return self

    @model_validator(mode="after")
    def validate_accommodations(self) -> MultiDayRequest:
        validate_no_stay_overlaps(self.accommodations)
        return self

    @model_validator(mode="after")
    def validate_unique_day_dates(self) -> MultiDayRequest:
        dates = [cfg.date for cfg in self.days]
        if len(dates) != len(set(dates)):
            raise ValueError("duplicate date found in days list")
        return self

    @model_validator(mode="after")
    def validate_unique_transfer_dates(self) -> MultiDayRequest:
        dates = [t.date for t in self.transfers]
        if len(dates) != len(set(dates)):
            raise ValueError("duplicate date found in transfers list")
        return self

    @model_validator(mode="after")
    def validate_transfers_on_transition_days(self) -> MultiDayRequest:
        if not self.transfers:
            return self
        day_dates = [cfg.date for cfg in self.days]
        for transfer in self.transfers:
            if transfer.date not in day_dates:
                raise ValueError(f"transfer date {transfer.date} is not among request.days dates")
        anchors_by_date = dict(zip(day_dates, resolve_day_anchors(day_dates, self.accommodations), strict=True))
        for transfer in self.transfers:
            if not _is_transition_day(anchors_by_date[transfer.date]):
                raise ValueError(
                    f"transfer date {transfer.date} is not a transition day "
                    "(no accommodation check-in/check-out changeover on that date)"
                )
        return self

    @model_validator(mode="after")
    def validate_transfer_day_config_conflict(self) -> MultiDayRequest:
        transfer_dates = {t.date for t in self.transfers}
        for cfg in self.days:
            if cfg.date in transfer_dates and (cfg.start_lat is not None or cfg.end_lat is not None):
                raise ValueError(
                    f"DayConfig for {cfg.date} cannot set explicit start/end anchors when a transfer exists "
                    "for that date — this slice models the transfer as door-to-door "
                    "(origin accommodation -> destination accommodation)"
                )
        return self


class TransferEndpoint(BaseModel):
    """Display data for a transfer's origin/destination — not a persisted identifier, see ADR-16."""

    name: str
    lat: float
    lng: float


class TransferSegment(BaseModel):
    """A resolved, time-consuming transfer between two accommodation stays within a DayPlan."""

    origin: TransferEndpoint
    destination: TransferEndpoint
    departure_time: time
    arrival_time: time
    duration_s: int
    label: str | None = None


class DayPlan(BaseModel):
    """Optimized route for a single day within a multi-day trip."""

    day_index: int
    date: date
    steps: list[RouteStep]
    total_travel_time_s: int
    total_visit_time_min: int
    total_wait_min: int
    skipped: list[SkippedPlace]
    travel_to_end_s: int = 0
    transfer: TransferSegment | None = None


class MultiDayResponse(BaseModel):
    """Result of a multi-day TSP trip optimization."""

    days: list[DayPlan]
    transport_mode: TransportMode
    unassigned: list[SkippedPlace]
