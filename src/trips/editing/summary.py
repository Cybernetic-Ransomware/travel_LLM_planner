"""Deterministic, backend-owned ``trip_revisions.summary`` strings (no LLM): a count-by-type
of the applied operations, or a shape description of a manually saved request."""

from __future__ import annotations

from src.trips.editing.operations import TripEditOperation
from src.trips.models import MultiDaySaveTripRequest, SaveTripRequest

_OP_LABELS: dict[str, tuple[str, str]] = {
    "set_place_auto": ("set 1 place to auto", "set {n} places to auto"),
    "set_place_pinned": ("pinned 1 place", "pinned {n} places"),
    "set_place_flexible": ("made 1 place flexible", "made {n} places flexible"),
    "remove_place": ("removed 1 place", "removed {n} places"),
    "update_day_window": ("adjusted 1 day window", "adjusted {n} day windows"),
    "set_transport_mode": ("changed the transport mode", "changed the transport mode {n} times"),
    "add_transfer": ("added 1 transfer", "added {n} transfers"),
    "update_transfer": ("updated 1 transfer", "updated {n} transfers"),
    "remove_transfer": ("removed 1 transfer", "removed {n} transfers"),
    "add_accommodation": ("added 1 stay", "added {n} stays"),
    "update_accommodation": ("updated 1 stay", "updated {n} stays"),
    "remove_accommodation": ("removed 1 stay", "removed {n} stays"),
}


def summarize_operations(operations: list[TripEditOperation]) -> str:
    """e.g. ``"3 changes: pinned 1 place, adjusted 1 day window, changed the transport mode"``."""
    counts: dict[str, int] = {}
    for op in operations:
        counts[op.op] = counts.get(op.op, 0) + 1

    parts: list[str] = []
    for key, singular_plural in _OP_LABELS.items():
        n = counts.get(key, 0)
        if n == 0:
            continue
        singular, plural = singular_plural
        parts.append(singular if n == 1 else plural.format(n=n))

    total = len(operations)
    noun = "change" if total == 1 else "changes"
    detail = ", ".join(parts) if parts else "no-op"
    return f"{total} {noun}: {detail}"


def manual_update_summary(request: SaveTripRequest) -> str:
    """e.g. ``"Manual update — MULTI_DAY, 12 places, 4 days"``."""
    if isinstance(request, MultiDaySaveTripRequest):
        places = len(request.multi_day_request.places)
        days = len(request.multi_day_request.days)
        return f"Manual update — MULTI_DAY, {places} places, {days} days"
    places = len(request.optimizer_request.place_ids)
    return f"Manual update — SINGLE_DAY, {places} places"
