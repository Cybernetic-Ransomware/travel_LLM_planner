"""Pure, I/O-free reconciliation the canonical Pydantic validators can't do:
resolve every batch ``stay_index`` against the PRE-BATCH order (so a selector
can't shift mid-batch) and drop transfers orphaned by an accommodation edit
(so a reasonable edit doesn't become a hard validator error).
"""

from __future__ import annotations

from datetime import date

from src.accommodations.models import AccommodationStay
from src.accommodations.resolver import resolve_day_anchors
from src.optimizer.solver.models import _is_transition_day
from src.trips.editing.errors import (
    AccommodationNotFoundError,
    AccommodationSelectorConflictError,
    InvalidDayIndexError,
    OperationValidationError,
    PlaceNotInTripError,
    TooFewPlacesError,
)
from src.trips.editing.operations import (
    AccommodationOp,
    AddAccommodationOp,
    RemoveAccommodationOp,
    SetPlaceFlexibleOp,
    UpdateAccommodationOp,
)

_MIN_PLACES = 2


def assert_place_in_trip(places: list[dict], place_id: str) -> dict:
    """Return the place entry for ``place_id`` or raise ``PlaceNotInTripError``."""
    for place in places:
        if place["place_id"] == place_id:
            return place
    raise PlaceNotInTripError(f"'{place_id}' isn't part of this trip.")


def assert_day_index_in_range(num_days: int, day_index: int) -> None:
    if day_index >= num_days:
        raise InvalidDayIndexError(f"Day {day_index} doesn't exist in this trip (it has {num_days} days).")


def ensure_min_places(count: int) -> None:
    if count < _MIN_PLACES:
        raise TooFewPlacesError("A trip needs at least 2 places.")


def merge_preserved_hours(
    existing_slots: list[dict],
    day_index: int,
    requested_from: int | None,
    requested_to: int | None,
) -> tuple[int | None, int | None]:
    """Keep the preferred window of the slot already on ``day_index`` when the op omits it."""
    if requested_from is not None or requested_to is not None:
        return requested_from, requested_to
    for slot in existing_slots:
        if slot["day_index"] == day_index:
            return slot.get("preferred_hour_from"), slot.get("preferred_hour_to")
    return None, None


def dedupe_flexible_slots(op: SetPlaceFlexibleOp) -> None:
    """Reject a flexible assignment that lists the same day twice."""
    seen: set[int] = set()
    for slot in op.slots:
        if slot.day_index in seen:
            raise OperationValidationError(f"That flexible assignment lists day {slot.day_index} more than once.")
        seen.add(slot.day_index)


def resolve_accommodation_selectors(
    pre_batch_stays: list[AccommodationStay],
    accommodation_ops: list[AccommodationOp],
) -> dict[int, int]:
    """Map each update/remove op (by ``id(op)``) to an index into the PRE-BATCH list.

    ``stay_index`` counts positions in ``sorted(stays, key=check_in_date)``. Two ops
    hitting the same pre-batch stay is a conflict, not last-wins; add ops get no entry.
    """
    sorted_positions = sorted(range(len(pre_batch_stays)), key=lambda i: pre_batch_stays[i].check_in_date)

    resolved: dict[int, int] = {}
    claimed: set[int] = set()
    for op in accommodation_ops:
        if isinstance(op, AddAccommodationOp):
            continue
        if not isinstance(op, UpdateAccommodationOp | RemoveAccommodationOp):
            continue
        selector = op.stay_index
        if selector >= len(sorted_positions):
            raise AccommodationNotFoundError(f"There's no stay {selector} in this trip (it has {len(sorted_positions)}).")
        original_index = sorted_positions[selector]
        if original_index in claimed:
            raise AccommodationSelectorConflictError()
        claimed.add(original_index)
        resolved[id(op)] = original_index
    return resolved


def reconcile_transfers_after_transition_change(
    days: list[dict],
    accommodations: list[dict],
    transfers: list[dict],
    reconcilable_dates: set[date],
) -> list[date]:
    """Silently drop transfers in ``reconcilable_dates`` (pre-batch ones) whose date is no
    longer a changeover; a transfer *added* this batch on a bad day is left for the hard
    validator. Mutates ``transfers``.
    """
    if not transfers:
        return []

    stays = [AccommodationStay.model_validate(entry) for entry in accommodations]
    day_dates = [entry["date"] for entry in days]
    anchors_by_date = dict(zip(day_dates, resolve_day_anchors(day_dates, stays), strict=True))

    kept: list[dict] = []
    dropped: list[date] = []
    for transfer in transfers:
        transfer_date = transfer["date"]
        anchors = anchors_by_date.get(transfer_date)
        is_changeover = anchors is not None and _is_transition_day(anchors)
        if is_changeover or transfer_date not in reconcilable_dates:
            kept.append(transfer)
        else:
            dropped.append(transfer_date)
    transfers[:] = kept
    return dropped
