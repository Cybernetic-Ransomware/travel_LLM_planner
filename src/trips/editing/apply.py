"""Pure mutation + re-validation of a ``MultiDayRequest``.

Every handler works on a deep copy of ``request.model_dump(mode="python")`` — a
half-applied batch never yields a partial model. The model is constructed exactly
once, at the end, by ``MultiDayRequest.model_validate``, which re-runs every
``@model_validator`` for free. Any ``ValidationError`` there is wrapped as
``TripEditValidationError``.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError

from src.optimizer.solver.models import MultiDayRequest
from src.trips.editing.errors import (
    InvalidDayIndexError,
    TransferAlreadyExistsError,
    TransferNotFoundError,
    TripEditValidationError,
)
from src.trips.editing.operations import (
    _ACCOMMODATION_OPS,
    AccommodationOp,
    AddAccommodationOp,
    AddTransferOp,
    RemoveAccommodationOp,
    RemovePlaceOp,
    RemoveTransferOp,
    SetPlaceAutoOp,
    SetPlaceFlexibleOp,
    SetPlacePinnedOp,
    SetTransportModeOp,
    TripEditOperation,
    UpdateAccommodationOp,
    UpdateDayWindowOp,
    UpdateTransferOp,
)
from src.trips.editing.reconcile import (
    assert_day_index_in_range,
    assert_place_in_trip,
    dedupe_flexible_slots,
    ensure_min_places,
    merge_preserved_hours,
    reconcile_transfers_after_transition_change,
    resolve_accommodation_selectors,
)


@dataclass
class ApplyOutcome:
    request: MultiDayRequest
    removed_transfer_dates: list[date] = field(default_factory=list)


def apply_operations(request: MultiDayRequest, operations: list[TripEditOperation]) -> ApplyOutcome:
    data = deepcopy(request.model_dump(mode="python"))

    accommodation_ops: list[AccommodationOp] = [op for op in operations if isinstance(op, _ACCOMMODATION_OPS)]
    resolved = resolve_accommodation_selectors(request.accommodations, accommodation_ops)
    _apply_accommodation_ops(data, accommodation_ops, resolved)

    for op in operations:
        if isinstance(op, _ACCOMMODATION_OPS):
            continue
        _NON_ACCOMMODATION_HANDLERS[type(op)](data, op)

    pre_batch_transfer_dates = {transfer.date for transfer in request.transfers}

    try:
        removed_transfer_dates = reconcile_transfers_after_transition_change(
            data["days"], data["accommodations"], data["transfers"], pre_batch_transfer_dates
        )
        mutated = MultiDayRequest.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        detail = first.get("msg", "invalid trip state")
        raise TripEditValidationError(f"Those changes leave the trip in an invalid state: {detail}") from exc

    return ApplyOutcome(request=mutated, removed_transfer_dates=removed_transfer_dates)


def _apply_accommodation_ops(data: dict, accommodation_ops: list[AccommodationOp], resolved: dict[int, int]) -> None:
    """Updates in place, then removes (selectors already resolved to pre-batch indices), then adds.

    Updates run before removes so a deletion never invalidates an update's resolved
    index; ``resolve_accommodation_selectors`` has already guaranteed no stay is
    both updated and removed.
    """
    stays = data["accommodations"]

    for op in accommodation_ops:
        if isinstance(op, UpdateAccommodationOp):
            _apply_accommodation_update(stays[resolved[id(op)]], op)

    removed = {resolved[id(op)] for op in accommodation_ops if isinstance(op, RemoveAccommodationOp)}
    data["accommodations"] = [stay for index, stay in enumerate(stays) if index not in removed]

    for op in accommodation_ops:
        if isinstance(op, AddAccommodationOp):
            data["accommodations"].append(
                {
                    "name": op.name,
                    "lat": op.lat,
                    "lng": op.lng,
                    "check_in_date": op.check_in_date,
                    "check_out_date": op.check_out_date,
                    "check_in_from": op.check_in_from,
                    "check_out_by": op.check_out_by,
                }
            )


def _apply_accommodation_update(stay: dict, op: UpdateAccommodationOp) -> None:
    for attr in ("name", "lat", "lng", "check_in_date", "check_out_date", "check_in_from", "check_out_by"):
        value = getattr(op, attr)
        if value is not None:
            stay[attr] = value
    if op.clear_check_in_from:
        stay["check_in_from"] = None
    if op.clear_check_out_by:
        stay["check_out_by"] = None


def _handle_set_place_auto(data: dict, op: SetPlaceAutoOp) -> None:
    place = assert_place_in_trip(data["places"], op.place_id)
    place["day_preferences"] = []


def _handle_set_place_pinned(data: dict, op: SetPlacePinnedOp) -> None:
    place = assert_place_in_trip(data["places"], op.place_id)
    assert_day_index_in_range(len(data["days"]), op.day_index)

    existing = place["day_preferences"]
    hour_from, hour_to = merge_preserved_hours(existing, op.day_index, op.preferred_hour_from, op.preferred_hour_to)
    if hour_from is None and hour_to is None and len(existing) == 1:
        hour_from = existing[0].get("preferred_hour_from")
        hour_to = existing[0].get("preferred_hour_to")

    place["day_preferences"] = [{"day_index": op.day_index, "preferred_hour_from": hour_from, "preferred_hour_to": hour_to}]


def _handle_set_place_flexible(data: dict, op: SetPlaceFlexibleOp) -> None:
    place = assert_place_in_trip(data["places"], op.place_id)
    dedupe_flexible_slots(op)

    num_days = len(data["days"])
    existing = place["day_preferences"]
    new_slots: list[dict] = []
    for slot in op.slots:
        assert_day_index_in_range(num_days, slot.day_index)
        hour_from, hour_to = merge_preserved_hours(
            existing, slot.day_index, slot.preferred_hour_from, slot.preferred_hour_to
        )
        new_slots.append({"day_index": slot.day_index, "preferred_hour_from": hour_from, "preferred_hour_to": hour_to})
    place["day_preferences"] = new_slots


def _handle_remove_place(data: dict, op: RemovePlaceOp) -> None:
    assert_place_in_trip(data["places"], op.place_id)
    ensure_min_places(len(data["places"]) - 1)
    data["places"] = [p for p in data["places"] if p["place_id"] != op.place_id]


def _handle_update_day_window(data: dict, op: UpdateDayWindowOp) -> None:
    assert_day_index_in_range(len(data["days"]), op.day_index)
    day = data["days"][op.day_index]
    if op.day_start_hour is not None:
        day["day_start_hour"] = op.day_start_hour
    if op.day_end_hour is not None:
        day["day_end_hour"] = op.day_end_hour
    if op.day_start_time is not None:
        day["day_start_time"] = op.day_start_time
    if op.day_end_time is not None:
        day["day_end_time"] = op.day_end_time
    if op.clear_start_time:
        day["day_start_time"] = None
    if op.clear_end_time:
        day["day_end_time"] = None


def _handle_set_transport_mode(data: dict, op: SetTransportModeOp) -> None:
    data["transport_mode"] = op.mode


def _handle_add_transfer(data: dict, op: AddTransferOp) -> None:
    if any(entry["date"] == op.date for entry in data["transfers"]):
        raise TransferAlreadyExistsError(f"There's already a transfer on {op.date}.")
    if op.date not in [entry["date"] for entry in data["days"]]:
        raise InvalidDayIndexError(f"{op.date} isn't one of this trip's days.")
    data["transfers"].append(
        {
            "date": op.date,
            "departure_time": op.departure_time,
            "arrival_time": op.arrival_time,
            "label": op.label,
        }
    )


def _handle_update_transfer(data: dict, op: UpdateTransferOp) -> None:
    transfer = _find_transfer(data, op.date)
    if op.departure_time is not None:
        transfer["departure_time"] = op.departure_time
    if op.arrival_time is not None:
        transfer["arrival_time"] = op.arrival_time
    if op.label is not None:
        transfer["label"] = op.label
    if op.clear_label:
        transfer["label"] = None


def _handle_remove_transfer(data: dict, op: RemoveTransferOp) -> None:
    _find_transfer(data, op.date)
    data["transfers"] = [entry for entry in data["transfers"] if entry["date"] != op.date]


def _find_transfer(data: dict, on_date: date) -> dict:
    for entry in data["transfers"]:
        if entry["date"] == on_date:
            return entry
    raise TransferNotFoundError(f"There's no transfer on {on_date} to change.")


_NON_ACCOMMODATION_HANDLERS: dict[type, Callable[[dict, Any], None]] = {
    SetPlaceAutoOp: _handle_set_place_auto,
    SetPlacePinnedOp: _handle_set_place_pinned,
    SetPlaceFlexibleOp: _handle_set_place_flexible,
    RemovePlaceOp: _handle_remove_place,
    UpdateDayWindowOp: _handle_update_day_window,
    SetTransportModeOp: _handle_set_transport_mode,
    AddTransferOp: _handle_add_transfer,
    UpdateTransferOp: _handle_update_transfer,
    RemoveTransferOp: _handle_remove_transfer,
}
