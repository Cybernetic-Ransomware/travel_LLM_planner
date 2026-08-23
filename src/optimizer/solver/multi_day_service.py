"""Multi-day trip optimizer: partitions places across days and runs per-day TSP."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time
from typing import Literal

from pymongo.asynchronous.database import AsyncDatabase

from src.accommodations.models import AccommodationStay
from src.accommodations.resolver import DayAccommodationAnchors, resolve_day_anchors
from src.gmaps import fetch_places_by_ids
from src.optimizer.matrix.client import GoogleRoutesManager
from src.optimizer.solver.models import (
    DayConfig,
    DayPlan,
    DayRouteSegment,
    DaySlot,
    MultiDayRequest,
    MultiDayResponse,
    OptimizeRequest,
    OptimizeResponse,
    PlaceDayPreference,
    SkippedPlace,
    TransferEndpoint,
    TransferSegment,
    resolve_day_bound_s,
    seconds_to_time,
)
from src.optimizer.solver.service import _google_weekday, optimize_route
from src.transfers.models import TransferBlock
from src.transfers.resolver import resolve_day_transfer

_TransitionSide = Literal["ORIGIN", "DESTINATION", "NO_COORDINATES"]


@dataclass(frozen=True)
class TransitionDayContext:
    """Resolved transfer wiring for one transition day: PRE/POST windows and per-side visit budgets — see ADR-17."""

    transfer: TransferBlock
    origin: AccommodationStay
    destination: AccommodationStay
    pre_start_s: int
    pre_end_s: int
    post_start_s: int
    post_end_s: int
    pre_visit_budget_min: int
    post_visit_budget_min: int


@dataclass(frozen=True)
class TransferSideBuckets:
    """Place ids assigned to either side of one transition day."""

    pre: list[str]
    post: list[str]


@dataclass(frozen=True)
class PartitionResult:
    buckets: dict[int, list[str]]
    transfer_buckets: dict[int, TransferSideBuckets]
    unassigned: list[SkippedPlace]
    pre_solver_skipped_by_day: dict[int, list[SkippedPlace]]


def _open_day_indices(doc: dict, day_configs: list[DayConfig]) -> list[int]:
    """Return indices of days on which the place has at least one opening-hours period.

    Falls back to all days when the place has no opening_hours data — the single-day
    solver will then decide feasibility at runtime.
    """
    periods: list[dict] = (doc.get("opening_hours") or {}).get("periods", [])
    if not periods:
        return list(range(len(day_configs)))

    open_google_days = {p.get("open", {}).get("day") for p in periods}
    result = []
    for i, cfg in enumerate(day_configs):
        if _google_weekday(cfg.date) in open_google_days:
            result.append(i)
    return result if result else list(range(len(day_configs)))


_PRIORITY_ORDER = {"must_see": 0, "normal": 1, "optional": 2}


def _priority_rank(place_id: str, doc_map: dict[str, dict]) -> int:
    """Packing rank for a place: must_see first, optional last. Unknown values rank as normal."""
    priority = (doc_map.get(place_id) or {}).get("priority") or "normal"
    return _PRIORITY_ORDER.get(priority, 1)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return 2 * r_km * math.asin(math.sqrt(a))


def _transition_side(doc: dict, origin: AccommodationStay, destination: AccommodationStay) -> _TransitionSide:
    """Nearest-of-two-accommodations heuristic. A dead-even tie resolves to ORIGIN — see ADR-17."""
    lat, lng = doc.get("lat"), doc.get("lng")
    if lat is None or lng is None:
        return "NO_COORDINATES"
    dist_to_destination = _haversine_km(lat, lng, destination.lat, destination.lng)
    dist_to_origin = _haversine_km(lat, lng, origin.lat, origin.lng)
    return "DESTINATION" if dist_to_destination < dist_to_origin else "ORIGIN"


def _partition_places(
    places: list[PlaceDayPreference],
    num_days: int,
    day_configs: list[DayConfig],
    doc_map: dict[str, dict],
    transfer_contexts: dict[int, TransitionDayContext] | None = None,
) -> PartitionResult:
    """Assign places to day buckets using a 3-tier strategy.

    Tier 1 — pinned (1 DaySlot):   assigned to that exact day.
    Tier 2 — flexible (>1 DaySlots): assigned to the candidate day with the most remaining capacity.
    Tier 3 — auto (0 DaySlots):    greedy bin-pack to whichever day has the most remaining capacity.

    Within tiers 2 and 3 places are packed in priority order (must_see → normal → optional),
    so higher-priority places claim the roomiest days before lower-priority ones.

    On a transition day (TransitionDayContext present), every place — pinned, flexible, or
    auto — is classified ORIGIN/DESTINATION/NO_COORDINATES and routed to that day's PRE or
    POST bucket; auto/flexible are also bound by that side's visit budget as an admission
    ceiling, not a feasibility guarantee. Failures go to `unassigned` (auto/flexible) or
    `pre_solver_skipped_by_day` (pinned NO_COORDINATES only) instead of being force-packed —
    see ADR-17.
    """
    transfer_contexts = transfer_contexts or {}
    buckets: dict[int, list[str]] = {i: [] for i in range(num_days)}
    fill: dict[int, int] = {i: 0 for i in range(num_days)}
    capacity: dict[int, int] = {i: (cfg.day_end_hour - cfg.day_start_hour) * 60 for i, cfg in enumerate(day_configs)}

    pre_buckets: dict[int, list[str]] = {i: [] for i in transfer_contexts}
    post_buckets: dict[int, list[str]] = {i: [] for i in transfer_contexts}
    pre_fill: dict[int, int] = {i: 0 for i in transfer_contexts}
    post_fill: dict[int, int] = {i: 0 for i in transfer_contexts}

    unassigned: list[SkippedPlace] = []
    pre_solver_skipped_by_day: dict[int, list[SkippedPlace]] = {i: [] for i in range(num_days)}

    def remaining_capacity(day_idx: int, side: _TransitionSide | None) -> int:
        ctx = transfer_contexts.get(day_idx)
        if ctx is None:
            return capacity[day_idx] - fill[day_idx]
        if side == "ORIGIN":
            return ctx.pre_visit_budget_min - pre_fill[day_idx]
        return ctx.post_visit_budget_min - post_fill[day_idx]

    def admissible(day_idx: int, doc: dict, visit_min: int) -> tuple[bool, _TransitionSide | None]:
        ctx = transfer_contexts.get(day_idx)
        if ctx is None:
            return True, None
        side = _transition_side(doc, ctx.origin, ctx.destination)
        if side == "NO_COORDINATES":
            return False, side
        return remaining_capacity(day_idx, side) >= visit_min, side

    def rejection_reason(side: _TransitionSide | None) -> str:
        if side == "NO_COORDINATES":
            return "NO_COORDINATES"
        if side == "ORIGIN":
            return "PRE_TRANSFER_CAPACITY_EXCEEDED"
        return "CAPACITY_EXCEEDED"

    def place_into_bucket(day_idx: int, side: _TransitionSide | None, place_id: str, visit_min: int) -> None:
        ctx = transfer_contexts.get(day_idx)
        if ctx is None:
            buckets[day_idx].append(place_id)
            fill[day_idx] += visit_min
            return
        if side == "ORIGIN":
            pre_buckets[day_idx].append(place_id)
            pre_fill[day_idx] += visit_min
        else:
            post_buckets[day_idx].append(place_id)
            post_fill[day_idx] += visit_min

    def pack_unpinned(
        pref: PlaceDayPreference, doc: dict, visit_min: int, candidate_days: list[int]
    ) -> SkippedPlace | None:
        """None on success; a SkippedPlace for `unassigned` when no (day, side) candidate is admissible."""
        classified = [(d, *admissible(d, doc, visit_min)) for d in candidate_days]
        admissible_candidates = [(d, side) for d, ok, side in classified if ok]
        if admissible_candidates:
            best_day, best_side = max(admissible_candidates, key=lambda pair: remaining_capacity(*pair))
            place_into_bucket(best_day, best_side, pref.place_id, visit_min)
            return None
        best_day, _, best_side = max(classified, key=lambda triple: remaining_capacity(triple[0], triple[2]))
        return SkippedPlace(place_id=pref.place_id, name=doc.get("name"), reason=rejection_reason(best_side))

    pinned = [p for p in places if len(p.day_preferences) == 1]
    flexible = [p for p in places if len(p.day_preferences) > 1]
    auto = [p for p in places if len(p.day_preferences) == 0]
    flexible.sort(key=lambda p: _priority_rank(p.place_id, doc_map))
    auto.sort(key=lambda p: _priority_rank(p.place_id, doc_map))

    for pref in pinned:
        day_idx = pref.day_preferences[0].day_index
        doc = doc_map.get(pref.place_id) or {}
        visit_min = doc.get("visit_duration_min") or 30
        ctx = transfer_contexts.get(day_idx)
        if ctx is not None:
            side = _transition_side(doc, ctx.origin, ctx.destination)
            if side == "NO_COORDINATES":
                pre_solver_skipped_by_day[day_idx].append(
                    SkippedPlace(place_id=pref.place_id, name=doc.get("name"), reason="NO_COORDINATES")
                )
                continue
            place_into_bucket(day_idx, side, pref.place_id, visit_min)
            continue
        place_into_bucket(day_idx, None, pref.place_id, visit_min)

    for pref in flexible:
        doc = doc_map.get(pref.place_id) or {}
        visit_min = doc.get("visit_duration_min") or 30
        open_days = set(_open_day_indices(doc, day_configs))
        candidate_days = [slot.day_index for slot in pref.day_preferences if slot.day_index in open_days]
        if not candidate_days:
            candidate_days = [slot.day_index for slot in pref.day_preferences]
        rejection = pack_unpinned(pref, doc, visit_min, candidate_days)
        if rejection is not None:
            unassigned.append(rejection)

    for pref in auto:
        doc = doc_map.get(pref.place_id) or {}
        visit_min = doc.get("visit_duration_min") or 30
        candidate_days = _open_day_indices(doc, day_configs)
        rejection = pack_unpinned(pref, doc, visit_min, candidate_days)
        if rejection is not None:
            unassigned.append(rejection)

    transfer_buckets = {
        day_idx: TransferSideBuckets(pre=pre_buckets[day_idx], post=post_buckets[day_idx]) for day_idx in transfer_contexts
    }

    return PartitionResult(
        buckets=buckets,
        transfer_buckets=transfer_buckets,
        unassigned=unassigned,
        pre_solver_skipped_by_day=pre_solver_skipped_by_day,
    )


def _is_accommodation_transition_day(anchors: DayAccommodationAnchors) -> bool:
    """True when START/END resolve to two different stays — neither is then auto-applied, see ADR-15."""
    return anchors.start is not None and anchors.end is not None and anchors.start is not anchors.end


def _resolve_segment_end_bound_fields(end_s: int) -> tuple[int, time | None]:
    """Encode a resolved end bound as an OptimizeRequest-safe (day_end_hour, day_end_time) pair — see ADR-17."""
    if end_s >= 24 * 3600:
        return 24, None
    return 23, seconds_to_time(end_s)


def _build_transition_day_context(
    transfer: TransferBlock, anchors: DayAccommodationAnchors, cfg: DayConfig
) -> TransitionDayContext:
    """Resolve a TransferBlock into PRE/POST windows and per-side visit budgets — see ADR-17."""
    origin = anchors.start
    destination = anchors.end
    assert origin is not None and destination is not None  # guaranteed by _is_accommodation_transition_day

    configured_start_s = resolve_day_bound_s(cfg.day_start_hour, cfg.day_start_time)
    configured_end_s = resolve_day_bound_s(cfg.day_end_hour, cfg.day_end_time)
    departure_s = resolve_day_bound_s(0, transfer.departure_time)
    arrival_s = resolve_day_bound_s(0, transfer.arrival_time)
    check_in_s = resolve_day_bound_s(0, destination.check_in_from) if destination.check_in_from else configured_start_s
    check_out_s = resolve_day_bound_s(0, origin.check_out_by) if origin.check_out_by else departure_s

    pre_start_s = configured_start_s
    pre_end_s = min(departure_s, configured_end_s, check_out_s)
    post_start_s = max(arrival_s, check_in_s, configured_start_s)
    post_end_s = configured_end_s

    return TransitionDayContext(
        transfer=transfer,
        origin=origin,
        destination=destination,
        pre_start_s=pre_start_s,
        pre_end_s=pre_end_s,
        post_start_s=post_start_s,
        post_end_s=post_end_s,
        pre_visit_budget_min=max(0, (pre_end_s - pre_start_s) // 60),
        post_visit_budget_min=max(0, (post_end_s - post_start_s) // 60),
    )


def _build_transfer_segment(ctx: TransitionDayContext) -> TransferSegment:
    departure_s = resolve_day_bound_s(0, ctx.transfer.departure_time)
    arrival_s = resolve_day_bound_s(0, ctx.transfer.arrival_time)
    return TransferSegment(
        origin=TransferEndpoint(name=ctx.origin.name, lat=ctx.origin.lat, lng=ctx.origin.lng),
        destination=TransferEndpoint(name=ctx.destination.name, lat=ctx.destination.lat, lng=ctx.destination.lng),
        departure_time=ctx.transfer.departure_time,
        arrival_time=ctx.transfer.arrival_time,
        duration_s=arrival_s - departure_s,
        label=ctx.transfer.label,
    )


def _segment_from_result(
    kind: Literal["PRE_TRANSFER", "POST_TRANSFER"], result: OptimizeResponse | None, window_skipped: list[SkippedPlace]
) -> DayRouteSegment:
    """Build a segment from a solver result, or an empty one (window_skipped then carries the rejected pinned)."""
    if result is None:
        return DayRouteSegment(
            kind=kind, steps=[], total_travel_time_s=0, total_visit_time_min=0, total_wait_min=0, skipped=window_skipped
        )
    return DayRouteSegment(
        kind=kind,
        steps=result.steps,
        total_travel_time_s=result.total_travel_time_s,
        total_visit_time_min=result.total_visit_time_min,
        total_wait_min=result.total_wait_min,
        travel_to_end_s=result.travel_to_end_s,
        skipped=result.skipped,
    )


def _build_day_docs(
    day_place_ids: list[str], doc_map: dict[str, dict], slot_map: dict[tuple[str, int], DaySlot], day_idx: int
) -> list[dict]:
    day_docs: list[dict] = []
    for pid in day_place_ids:
        if pid not in doc_map:
            continue
        doc = dict(doc_map[pid])
        slot = slot_map.get((pid, day_idx))
        if slot:
            if slot.preferred_hour_from is not None:
                doc["preferred_hour_from"] = slot.preferred_hour_from
            if slot.preferred_hour_to is not None:
                doc["preferred_hour_to"] = slot.preferred_hour_to
        day_docs.append(doc)
    return day_docs


async def _build_transition_day_plan(
    db: AsyncDatabase,
    manager: GoogleRoutesManager,
    request: MultiDayRequest,
    cfg: DayConfig,
    day_idx: int,
    ctx: TransitionDayContext,
    side_buckets: TransferSideBuckets,
    pre_solver_skipped: list[SkippedPlace],
    doc_map: dict[str, dict],
    slot_map: dict[tuple[str, int], DaySlot],
) -> DayPlan:
    """Build a transition day's DayPlan from two independent optimize_route calls — see ADR-17."""
    transfer_segment = _build_transfer_segment(ctx)

    pre_result: OptimizeResponse | None = None
    if side_buckets.pre and ctx.pre_visit_budget_min > 0:
        pre_docs = _build_day_docs(side_buckets.pre, doc_map, slot_map, day_idx)
        pre_end_hour, pre_end_time = _resolve_segment_end_bound_fields(ctx.pre_end_s)
        pre_request = OptimizeRequest(
            place_ids=side_buckets.pre,
            transport_mode=request.transport_mode,
            day_start_hour=cfg.day_start_hour,
            day_end_hour=pre_end_hour,
            day_start_time=cfg.day_start_time,
            day_end_time=pre_end_time,
            departure_date=cfg.date,
            start_lat=ctx.origin.lat,
            start_lng=ctx.origin.lng,
            end_lat=ctx.origin.lat,
            end_lng=ctx.origin.lng,
        )
        pre_result = await optimize_route(db, manager, pre_request, docs=pre_docs)

    post_result: OptimizeResponse | None = None
    if side_buckets.post and ctx.post_visit_budget_min > 0:
        post_docs = _build_day_docs(side_buckets.post, doc_map, slot_map, day_idx)
        post_request = OptimizeRequest(
            place_ids=side_buckets.post,
            transport_mode=request.transport_mode,
            day_start_hour=cfg.day_start_hour,
            day_end_hour=cfg.day_end_hour,
            day_start_time=seconds_to_time(ctx.post_start_s),
            day_end_time=cfg.day_end_time,
            departure_date=cfg.date,
            start_lat=ctx.destination.lat,
            start_lng=ctx.destination.lng,
            end_lat=ctx.destination.lat,
            end_lng=ctx.destination.lng,
        )
        post_result = await optimize_route(db, manager, post_request, docs=post_docs)

    pre_window_skipped = (
        [
            SkippedPlace(place_id=pid, name=(doc_map.get(pid) or {}).get("name"), reason="PRE_TRANSFER_WINDOW_INFEASIBLE")
            for pid in side_buckets.pre
        ]
        if ctx.pre_visit_budget_min == 0
        else []
    )
    post_window_skipped = (
        [
            SkippedPlace(place_id=pid, name=(doc_map.get(pid) or {}).get("name"), reason="TRANSFER_WINDOW_INFEASIBLE")
            for pid in side_buckets.post
        ]
        if ctx.post_visit_budget_min == 0
        else []
    )

    pre_segment = _segment_from_result("PRE_TRANSFER", pre_result, pre_window_skipped)
    post_segment = _segment_from_result("POST_TRANSFER", post_result, post_window_skipped)

    return DayPlan(
        day_index=day_idx,
        date=cfg.date,
        steps=post_segment.steps,
        total_travel_time_s=post_segment.total_travel_time_s,
        total_visit_time_min=post_segment.total_visit_time_min,
        total_wait_min=post_segment.total_wait_min,
        skipped=pre_solver_skipped + pre_segment.skipped + post_segment.skipped,
        travel_to_end_s=post_segment.travel_to_end_s,
        transfer=transfer_segment,
        route_segments=[pre_segment, post_segment],
    )


async def optimize_trip(
    db: AsyncDatabase,
    manager: GoogleRoutesManager,
    request: MultiDayRequest,
) -> MultiDayResponse:
    """Run multi-day TSP optimization.

    1. Fetch all place documents from MongoDB in one batch.
    2. Resolve accommodation anchors and, for transition days with a TransferBlock,
       the PRE/POST windows and per-side visit budgets (see ADR-16/ADR-17).
    3. Partition places across days (pinned by day_index, others via greedy
       bin-packing, transfer-day-aware — see _partition_places).
    4. For each day, apply per-day preference overrides and run the single-day solver.
       A transition day runs it up to twice (PRE and POST, independently); an
       ordinary day runs it once, or not at all when empty of places.
    5. Collect DayPlan results and return MultiDayResponse.
    """
    all_place_ids = [p.place_id for p in request.places]
    docs = await fetch_places_by_ids(db, all_place_ids)
    doc_map: dict[str, dict] = {str(doc["_id"]): doc for doc in docs}

    slot_map: dict[tuple[str, int], DaySlot] = {}
    for p in request.places:
        for slot in p.day_preferences:
            slot_map[(p.place_id, slot.day_index)] = slot

    day_dates = [cfg.date for cfg in request.days]
    day_anchors = resolve_day_anchors(day_dates, request.accommodations)
    transfer_for_day = resolve_day_transfer(day_dates, request.transfers)

    transfer_contexts: dict[int, TransitionDayContext] = {}
    for day_idx, cfg in enumerate(request.days):
        transfer = transfer_for_day[day_idx]
        anchors = day_anchors[day_idx]
        if transfer is not None and _is_accommodation_transition_day(anchors):
            transfer_contexts[day_idx] = _build_transition_day_context(transfer, anchors, cfg)

    partition = _partition_places(request.places, len(request.days), request.days, doc_map, transfer_contexts)

    day_plans: list[DayPlan] = []

    for day_idx, cfg in enumerate(request.days):
        ctx = transfer_contexts.get(day_idx)

        if ctx is not None:
            side_buckets = partition.transfer_buckets.get(day_idx, TransferSideBuckets(pre=[], post=[]))
            pre_solver_skipped = partition.pre_solver_skipped_by_day.get(day_idx, [])
            day_plans.append(
                await _build_transition_day_plan(
                    db, manager, request, cfg, day_idx, ctx, side_buckets, pre_solver_skipped, doc_map, slot_map
                )
            )
            continue

        day_place_ids = partition.buckets.get(day_idx, [])

        if not day_place_ids:
            day_plans.append(
                DayPlan(
                    day_index=day_idx,
                    date=cfg.date,
                    steps=[],
                    total_travel_time_s=0,
                    total_visit_time_min=0,
                    total_wait_min=0,
                    skipped=[],
                )
            )
            continue

        day_docs = _build_day_docs(day_place_ids, doc_map, slot_map, day_idx)
        anchors = day_anchors[day_idx]
        is_transition_day = _is_accommodation_transition_day(anchors)
        accommodation_start = None if is_transition_day else anchors.start
        accommodation_end = None if is_transition_day else anchors.end

        day_request = OptimizeRequest(
            place_ids=day_place_ids,
            transport_mode=request.transport_mode,
            day_start_hour=cfg.day_start_hour,
            day_end_hour=cfg.day_end_hour,
            day_start_time=cfg.day_start_time,
            day_end_time=cfg.day_end_time,
            departure_date=cfg.date,
            start_lat=cfg.start_lat
            if cfg.start_lat is not None
            else (accommodation_start.lat if accommodation_start is not None else request.start_lat),
            start_lng=cfg.start_lng
            if cfg.start_lng is not None
            else (accommodation_start.lng if accommodation_start is not None else request.start_lng),
            end_lat=cfg.end_lat
            if cfg.end_lat is not None
            else (accommodation_end.lat if accommodation_end is not None else request.end_lat),
            end_lng=cfg.end_lng
            if cfg.end_lng is not None
            else (accommodation_end.lng if accommodation_end is not None else request.end_lng),
        )

        single_result = await optimize_route(db, manager, day_request, docs=day_docs)

        day_plans.append(
            DayPlan(
                day_index=day_idx,
                date=cfg.date,
                steps=single_result.steps,
                total_travel_time_s=single_result.total_travel_time_s,
                total_visit_time_min=single_result.total_visit_time_min,
                total_wait_min=single_result.total_wait_min,
                skipped=single_result.skipped,
                travel_to_end_s=single_result.travel_to_end_s,
            )
        )

    return MultiDayResponse(
        days=day_plans,
        transport_mode=request.transport_mode,
        unassigned=partition.unassigned,
    )
