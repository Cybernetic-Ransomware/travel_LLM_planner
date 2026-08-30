"""Typed, discriminated batch of edit operations for a persisted MULTI_DAY trip.

Every operation model is LLM-visible (the batch is the argument schema of the
``edit_multi_day_trip`` chat tool). They all inherit ``extra="forbid"`` from
``TripEditOperationBase`` so an unknown key smuggled through the LLM's tool
arguments — ``trip_id``, ``revision``, ``expected_revision``, a scope selector —
is a validation error, never silently ignored. Nested payload models
(``DaySlotOp``) carry the same config.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.time_validation import NaiveTime


class TripEditOperationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DaySlotOp(TripEditOperationBase):
    """One candidate day + optional preferred window for a flexible place assignment."""

    day_index: int = Field(ge=0)
    preferred_hour_from: int | None = Field(default=None, ge=0, le=23)
    preferred_hour_to: int | None = Field(default=None, ge=0, le=23)


class SetPlaceAutoOp(TripEditOperationBase):
    op: Literal["set_place_auto"]
    place_id: str = Field(min_length=1)


class SetPlacePinnedOp(TripEditOperationBase):
    op: Literal["set_place_pinned"]
    place_id: str = Field(min_length=1)
    day_index: int = Field(ge=0)
    preferred_hour_from: int | None = Field(default=None, ge=0, le=23)
    preferred_hour_to: int | None = Field(default=None, ge=0, le=23)


class SetPlaceFlexibleOp(TripEditOperationBase):
    op: Literal["set_place_flexible"]
    place_id: str = Field(min_length=1)
    slots: list[DaySlotOp] = Field(min_length=2)


class RemovePlaceOp(TripEditOperationBase):
    op: Literal["remove_place"]
    place_id: str = Field(min_length=1)


class UpdateDayWindowOp(TripEditOperationBase):
    op: Literal["update_day_window"]
    day_index: int = Field(ge=0)
    day_start_hour: int | None = Field(default=None, ge=0, le=23)
    day_end_hour: int | None = Field(default=None, ge=1, le=24)
    day_start_time: NaiveTime | None = None
    day_end_time: NaiveTime | None = None
    clear_start_time: bool = False
    clear_end_time: bool = False


class SetTransportModeOp(TripEditOperationBase):
    op: Literal["set_transport_mode"]
    mode: Literal["WALK", "DRIVE", "BICYCLE"]


class AddTransferOp(TripEditOperationBase):
    op: Literal["add_transfer"]
    date: date
    departure_time: NaiveTime
    arrival_time: NaiveTime
    label: str | None = Field(default=None, max_length=200)


class UpdateTransferOp(TripEditOperationBase):
    op: Literal["update_transfer"]
    date: date
    departure_time: NaiveTime | None = None
    arrival_time: NaiveTime | None = None
    label: str | None = Field(default=None, max_length=200)
    clear_label: bool = False


class RemoveTransferOp(TripEditOperationBase):
    op: Literal["remove_transfer"]
    date: date


class AddAccommodationOp(TripEditOperationBase):
    op: Literal["add_accommodation"]
    name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    check_in_date: date
    check_out_date: date
    check_in_from: NaiveTime | None = None
    check_out_by: NaiveTime | None = None


class UpdateAccommodationOp(TripEditOperationBase):
    op: Literal["update_accommodation"]
    stay_index: int = Field(ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    check_in_date: date | None = None
    check_out_date: date | None = None
    check_in_from: NaiveTime | None = None
    check_out_by: NaiveTime | None = None
    clear_check_in_from: bool = False
    clear_check_out_by: bool = False


class RemoveAccommodationOp(TripEditOperationBase):
    op: Literal["remove_accommodation"]
    stay_index: int = Field(ge=0)


TripEditOperation = Annotated[
    SetPlaceAutoOp
    | SetPlacePinnedOp
    | SetPlaceFlexibleOp
    | RemovePlaceOp
    | UpdateDayWindowOp
    | SetTransportModeOp
    | AddTransferOp
    | UpdateTransferOp
    | RemoveTransferOp
    | AddAccommodationOp
    | UpdateAccommodationOp
    | RemoveAccommodationOp,
    Field(discriminator="op"),
]

AccommodationOp = AddAccommodationOp | UpdateAccommodationOp | RemoveAccommodationOp
_ACCOMMODATION_OPS = (AddAccommodationOp, UpdateAccommodationOp, RemoveAccommodationOp)


class TripEditBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[TripEditOperation] = Field(min_length=1, max_length=40)
