from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag

from src.optimizer.matrix.models import TransportMode
from src.optimizer.solver.models import (
    MultiDayRequest,
    MultiDayResponse,
    OptimizeRequest,
    OptimizeResponse,
)

SCHEMA_VERSION = 1

TripPlanType = Literal["SINGLE_DAY", "MULTI_DAY"]

# CREATED/REVERT/MIGRATION are minted only inside TripRepository; update() accepts only
# TripUpdateSource (ADR-21).
RevisionSource = Literal["CREATED", "MANUAL", "ORCHESTRATOR", "REVERT", "MIGRATION"]
TripUpdateSource = Literal["MANUAL", "ORCHESTRATOR"]


class SingleDaySaveTripRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_type: Literal["SINGLE_DAY"] = "SINGLE_DAY"
    name: str = Field(min_length=1, max_length=200)
    date: date
    optimizer_request: OptimizeRequest
    optimizer_response: OptimizeResponse
    # Optimistic-concurrency token for updates; ignored by save-as-new (POST). See ADR-20.
    expected_revision: int | None = None


class MultiDaySaveTripRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_type: Literal["MULTI_DAY"] = "MULTI_DAY"
    name: str = Field(min_length=1, max_length=200)
    multi_day_request: MultiDayRequest
    multi_day_response: MultiDayResponse
    # Optimistic-concurrency token for updates; ignored by save-as-new (POST). See ADR-20.
    expected_revision: int | None = None


def _save_trip_request_discriminator(value: Any) -> str:
    """Infer plan_type when absent: legacy flat payloads carry no plan_type key at all and
    must resolve to SINGLE_DAY; a payload carrying multi_day_request implies MULTI_DAY even
    without an explicit tag. The `extra="forbid"` config on both branches then rejects any
    payload that also carries the other variant's fields, instead of silently dropping them.
    """
    if isinstance(value, dict):
        if "plan_type" in value:
            return value["plan_type"]
        if "multi_day_request" in value or "multi_day_response" in value:
            return "MULTI_DAY"
        return "SINGLE_DAY"
    return getattr(value, "plan_type", "SINGLE_DAY")


SaveTripRequest = Annotated[
    Annotated[SingleDaySaveTripRequest, Tag("SINGLE_DAY")] | Annotated[MultiDaySaveTripRequest, Tag("MULTI_DAY")],
    Discriminator(_save_trip_request_discriminator),
]


class TripSummaryOutBase(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: str
    name: str
    created_at: str


class SingleDayTripSummaryOut(TripSummaryOutBase):
    plan_type: Literal["SINGLE_DAY"] = "SINGLE_DAY"
    date: str


class MultiDayTripSummaryOut(TripSummaryOutBase):
    plan_type: Literal["MULTI_DAY"] = "MULTI_DAY"
    start_date: str
    end_date: str
    num_days: int


TripSummaryOut = Annotated[SingleDayTripSummaryOut | MultiDayTripSummaryOut, Field(discriminator="plan_type")]


class TripDetailOutBase(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: str
    name: str
    created_at: str
    updated_at: str | None = None
    # Server-managed current revision; clients echo it back as expected_revision on update. See ADR-20.
    revision: int = 0


class SingleDayTripDetailOut(TripDetailOutBase):
    plan_type: Literal["SINGLE_DAY"] = "SINGLE_DAY"
    date: str
    optimizer_request: OptimizeRequest
    optimizer_response: OptimizeResponse
    selected_place_ids: list[str]
    transport_mode: TransportMode
    day_start_hour: int
    day_end_hour: int


class MultiDayTripDetailOut(TripDetailOutBase):
    plan_type: Literal["MULTI_DAY"] = "MULTI_DAY"
    start_date: str
    end_date: str
    num_days: int
    transport_mode: TransportMode
    multi_day_request: MultiDayRequest
    multi_day_response: MultiDayResponse


TripDetailOut = Annotated[SingleDayTripDetailOut | MultiDayTripDetailOut, Field(discriminator="plan_type")]


class TripRevisionSummaryOut(BaseModel):
    """One row of a trip's revision history — no snapshot body."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    revision: int
    source: RevisionSource
    summary: str
    restored_from_revision: int | None = None
    schema_version: int
    snapshot_hash: str
    # When THIS revision row was written — distinct from the trip's own created_at/updated_at.
    recorded_at: str


class TripRevisionListOut(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    trip_id: str
    current_revision: int
    revisions: list[TripRevisionSummaryOut]


class SingleDayTripRevisionDetailOut(SingleDayTripDetailOut):
    source: RevisionSource
    restored_from_revision: int | None = None
    snapshot_hash: str
    recorded_at: str


class MultiDayTripRevisionDetailOut(MultiDayTripDetailOut):
    source: RevisionSource
    restored_from_revision: int | None = None
    snapshot_hash: str
    recorded_at: str


TripRevisionDetailOut = Annotated[
    SingleDayTripRevisionDetailOut | MultiDayTripRevisionDetailOut,
    Field(discriminator="plan_type"),
]


class RestoreRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Required compare-and-set token: the caller's view of the trip's current revision.
    expected_revision: int = Field(ge=0)
