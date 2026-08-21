"""Multi-day trip optimizer: partitions places across days and runs per-day TSP."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from pymongo.asynchronous.database import AsyncDatabase

from src.accommodations.models import AccommodationStay
from src.accommodations.resolver import DayAccommodationAnchors, resolve_day_anchors
from src.gmaps import fetch_places_by_ids
from src.optimizer.matrix.client import GoogleRoutesManager
from src.optimizer.solver.models import (
    DayConfig,
    DayPlan,
    DaySlot,
    MultiDayRequest,
    MultiDayResponse,
    OptimizeRequest,
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

_Eligibility = Literal["ELIGIBLE", "GEOGRAPHY_MISMATCH", "NO_COORDINATES"]


@dataclass(frozen=True)
class TransferDayContext:
    """Resolved transfer wiring for one transition day — see ADR-16."""

    transfer: TransferBlock
    origin: AccommodationStay
    destination: AccommodationStay
    effective_start_s: int
    visit_budget_min: int  # hard admission budget for visit_duration_min sums; 0 when no viable window


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


def _transition_day_eligibility(doc: dict, origin: AccommodationStay, destination: AccommodationStay) -> _Eligibility:
    """Missing coordinates are reported distinctly from a geography mismatch, see ADR-16."""
    lat, lng = doc.get("lat"), doc.get("lng")
    if lat is None or lng is None:
        return "NO_COORDINATES"
    dist_to_destination = _haversine_km(lat, lng, destination.lat, destination.lng)
    dist_to_origin = _haversine_km(lat, lng, origin.lat, origin.lng)
    return "ELIGIBLE" if dist_to_destination < dist_to_origin else "GEOGRAPHY_MISMATCH"


def _eligibility_skip_reason(eligibility: _Eligibility) -> str:
    return "NO_COORDINATES" if eligibility == "NO_COORDINATES" else "TRANSFER_DAY_GEOGRAPHY_MISMATCH"


def _partition_places(
    places: list[PlaceDayPreference],
    num_days: int,
    day_configs: list[DayConfig],
    doc_map: dict[str, dict],
    transfer_contexts: dict[int, TransferDayContext] | None = None,
) -> tuple[dict[int, list[str]], list[SkippedPlace], dict[int, list[SkippedPlace]]]:
    """Assign places to day buckets using a 3-tier strategy.

    Tier 1 — pinned (1 DaySlot):   assigned to that exact day.
    Tier 2 — flexible (>1 DaySlots): assigned to the candidate day with the most remaining capacity.
    Tier 3 — auto (0 DaySlots):    greedy bin-pack to whichever day has the most remaining capacity.

    Within tiers 2 and 3 places are packed in priority order (must_see → normal → optional),
    so higher-priority places claim the roomiest days before lower-priority ones.

    On a transition day (TransferDayContext present), every place must be destination-eligible
    before landing in that day's bucket; auto/flexible are also bound by visit_budget_min as an
    admission ceiling, not a feasibility guarantee. Failures go to `unassigned` (auto/flexible)
    or `pre_solver_skipped_by_day` (pinned) instead of being force-packed — see ADR-16.
    """
    transfer_contexts = transfer_contexts or {}
    buckets: dict[int, list[str]] = {i: [] for i in range(num_days)}
    fill: dict[int, int] = {i: 0 for i in range(num_days)}
    capacity: dict[int, int] = {i: (cfg.day_end_hour - cfg.day_start_hour) * 60 for i, cfg in enumerate(day_configs)}
    for day_idx, ctx in transfer_contexts.items():
        capacity[day_idx] = ctx.visit_budget_min

    unassigned: list[SkippedPlace] = []
    pre_solver_skipped_by_day: dict[int, list[SkippedPlace]] = {i: [] for i in range(num_days)}

    def admissible(day_idx: int, doc: dict, visit_min: int) -> tuple[bool, _Eligibility | None]:
        ctx = transfer_contexts.get(day_idx)
        if ctx is None:
            return True, None
        eligibility = _transition_day_eligibility(doc, ctx.origin, ctx.destination)
        if eligibility != "ELIGIBLE":
            return False, eligibility
        if ctx.visit_budget_min - fill[day_idx] < visit_min:
            return False, None
        return True, None

    def unassigned_reason(day_idx: int, doc: dict, visit_min: int) -> str:
        _, eligibility = admissible(day_idx, doc, visit_min)
        return _eligibility_skip_reason(eligibility) if eligibility is not None else "CAPACITY_EXCEEDED"

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
            eligibility = _transition_day_eligibility(doc, ctx.origin, ctx.destination)
            if eligibility != "ELIGIBLE":
                pre_solver_skipped_by_day[day_idx].append(
                    SkippedPlace(place_id=pref.place_id, name=doc.get("name"), reason=_eligibility_skip_reason(eligibility))
                )
                continue
        buckets[day_idx].append(pref.place_id)
        fill[day_idx] += visit_min

    for pref in flexible:
        doc = doc_map.get(pref.place_id) or {}
        visit_min = doc.get("visit_duration_min") or 30
        open_days = set(_open_day_indices(doc, day_configs))
        candidate_days = [slot.day_index for slot in pref.day_preferences if slot.day_index in open_days]
        if not candidate_days:
            candidate_days = [slot.day_index for slot in pref.day_preferences]
        admissible_days = [d for d in candidate_days if admissible(d, doc, visit_min)[0]]
        if not admissible_days:
            best_original = max(candidate_days, key=lambda i: capacity[i] - fill[i])
            unassigned.append(
                SkippedPlace(
                    place_id=pref.place_id, name=doc.get("name"), reason=unassigned_reason(best_original, doc, visit_min)
                )
            )
            continue
        best_day = max(admissible_days, key=lambda i: capacity[i] - fill[i])
        buckets[best_day].append(pref.place_id)
        fill[best_day] += visit_min

    for pref in auto:
        doc = doc_map.get(pref.place_id) or {}
        visit_min = doc.get("visit_duration_min") or 30
        candidate_days = _open_day_indices(doc, day_configs)
        admissible_days = [d for d in candidate_days if admissible(d, doc, visit_min)[0]]
        if not admissible_days:
            best_original = max(candidate_days, key=lambda i: capacity[i] - fill[i])
            unassigned.append(
                SkippedPlace(
                    place_id=pref.place_id, name=doc.get("name"), reason=unassigned_reason(best_original, doc, visit_min)
                )
            )
            continue
        best_day = max(admissible_days, key=lambda i: capacity[i] - fill[i])
        buckets[best_day].append(pref.place_id)
        fill[best_day] += visit_min

    return buckets, unassigned, pre_solver_skipped_by_day


def _is_accommodation_transition_day(anchors: DayAccommodationAnchors) -> bool:
    """True when START/END resolve to two different stays — neither is then auto-applied, see ADR-15."""
    return anchors.start is not None and anchors.end is not None and anchors.start is not anchors.end


def _build_transfer_day_context(
    transfer: TransferBlock, anchors: DayAccommodationAnchors, cfg: DayConfig
) -> TransferDayContext:
    """Resolve a TransferBlock into effective post-transfer timing/anchors — see ADR-16 §effective_start."""
    origin = anchors.start
    destination = anchors.end
    assert origin is not None and destination is not None  # guaranteed by _is_accommodation_transition_day

    configured_start_s = resolve_day_bound_s(cfg.day_start_hour, cfg.day_start_time)
    configured_end_s = resolve_day_bound_s(cfg.day_end_hour, cfg.day_end_time)
    arrival_s = resolve_day_bound_s(0, transfer.arrival_time)
    check_in_s = resolve_day_bound_s(0, destination.check_in_from) if destination.check_in_from else configured_start_s

    effective_start_s = max(arrival_s, check_in_s, configured_start_s)
    visit_budget_min = max(0, (configured_end_s - effective_start_s) // 60)

    return TransferDayContext(
        transfer=transfer,
        origin=origin,
        destination=destination,
        effective_start_s=effective_start_s,
        visit_budget_min=visit_budget_min,
    )


def _build_transfer_segment(ctx: TransferDayContext) -> TransferSegment:
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


async def optimize_trip(
    db: AsyncDatabase,
    manager: GoogleRoutesManager,
    request: MultiDayRequest,
) -> MultiDayResponse:
    """Run multi-day TSP optimization.

    1. Fetch all place documents from MongoDB in one batch.
    2. Resolve accommodation anchors and, for transition days with a TransferBlock,
       the effective post-transfer window (see ADR-16).
    3. Partition places across days (pinned by day_index, others via greedy
       bin-packing, transfer-day-aware — see _partition_places).
    4. For each day, apply per-day preference overrides and run the single-day solver
       (or, for a transfer day with no viable post-transfer window, skip the solver
       entirely — an OptimizeRequest cannot have an empty place_ids list).
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

    transfer_contexts: dict[int, TransferDayContext] = {}
    for day_idx, cfg in enumerate(request.days):
        transfer = transfer_for_day[day_idx]
        anchors = day_anchors[day_idx]
        if transfer is not None and _is_accommodation_transition_day(anchors):
            transfer_contexts[day_idx] = _build_transfer_day_context(transfer, anchors, cfg)

    buckets, unassigned, pre_solver_skipped_by_day = _partition_places(
        request.places, len(request.days), request.days, doc_map, transfer_contexts
    )

    day_plans: list[DayPlan] = []

    for day_idx, cfg in enumerate(request.days):
        day_place_ids = buckets.get(day_idx, [])
        ctx = transfer_contexts.get(day_idx)

        if ctx is not None:
            pre_solver_skipped = pre_solver_skipped_by_day.get(day_idx, [])
            transfer_segment = _build_transfer_segment(ctx)

            if ctx.visit_budget_min == 0:
                window_skipped = [
                    SkippedPlace(
                        place_id=pid, name=(doc_map.get(pid) or {}).get("name"), reason="TRANSFER_WINDOW_INFEASIBLE"
                    )
                    for pid in day_place_ids
                ]
                day_plans.append(
                    DayPlan(
                        day_index=day_idx,
                        date=cfg.date,
                        steps=[],
                        total_travel_time_s=0,
                        total_visit_time_min=0,
                        total_wait_min=0,
                        skipped=pre_solver_skipped + window_skipped,
                        transfer=transfer_segment,
                    )
                )
                continue

            if not day_place_ids:
                day_plans.append(
                    DayPlan(
                        day_index=day_idx,
                        date=cfg.date,
                        steps=[],
                        total_travel_time_s=0,
                        total_visit_time_min=0,
                        total_wait_min=0,
                        skipped=pre_solver_skipped,
                        transfer=transfer_segment,
                    )
                )
                continue

            day_docs = _build_day_docs(day_place_ids, doc_map, slot_map, day_idx)
            day_request = OptimizeRequest(
                place_ids=day_place_ids,
                transport_mode=request.transport_mode,
                day_start_hour=cfg.day_start_hour,
                day_end_hour=cfg.day_end_hour,
                day_start_time=seconds_to_time(ctx.effective_start_s),
                day_end_time=cfg.day_end_time,
                departure_date=cfg.date,
                start_lat=ctx.destination.lat,
                start_lng=ctx.destination.lng,
                end_lat=ctx.destination.lat,
                end_lng=ctx.destination.lng,
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
                    skipped=pre_solver_skipped + single_result.skipped,
                    travel_to_end_s=single_result.travel_to_end_s,
                    transfer=transfer_segment,
                )
            )
            continue

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
        unassigned=unassigned,
    )
