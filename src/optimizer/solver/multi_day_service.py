"""Multi-day trip optimizer: partitions places across days and runs per-day TSP."""

from __future__ import annotations

from pymongo.asynchronous.database import AsyncDatabase

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
)
from src.optimizer.solver.service import _google_weekday, optimize_route


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


def _partition_places(
    places: list[PlaceDayPreference],
    num_days: int,
    day_configs: list[DayConfig],
    doc_map: dict[str, dict],
) -> dict[int, list[str]]:
    """Assign places to day buckets using a 3-tier strategy.

    Tier 1 — pinned (1 DaySlot):   assigned to that exact day.
    Tier 2 — flexible (>1 DaySlots): assigned to the candidate day with the most remaining capacity.
    Tier 3 — auto (0 DaySlots):    greedy bin-pack to whichever day has the most remaining capacity.

    Within tiers 2 and 3 places are packed in priority order (must_see → normal → optional),
    so higher-priority places claim the roomiest days before lower-priority ones.
    """
    buckets: dict[int, list[str]] = {i: [] for i in range(num_days)}
    fill: dict[int, int] = {i: 0 for i in range(num_days)}
    capacity: dict[int, int] = {i: (cfg.day_end_hour - cfg.day_start_hour) * 60 for i, cfg in enumerate(day_configs)}

    pinned = [p for p in places if len(p.day_preferences) == 1]
    flexible = [p for p in places if len(p.day_preferences) > 1]
    auto = [p for p in places if len(p.day_preferences) == 0]
    flexible.sort(key=lambda p: _priority_rank(p.place_id, doc_map))
    auto.sort(key=lambda p: _priority_rank(p.place_id, doc_map))

    for pref in pinned:
        day_idx = pref.day_preferences[0].day_index
        buckets[day_idx].append(pref.place_id)
        visit_min = (doc_map.get(pref.place_id) or {}).get("visit_duration_min") or 30
        fill[day_idx] += visit_min

    for pref in flexible:
        doc = doc_map.get(pref.place_id) or {}
        open_days = set(_open_day_indices(doc, day_configs))
        candidate_days = [slot.day_index for slot in pref.day_preferences if slot.day_index in open_days]
        if not candidate_days:
            candidate_days = [slot.day_index for slot in pref.day_preferences]
        best_day = max(candidate_days, key=lambda i: capacity[i] - fill[i])
        buckets[best_day].append(pref.place_id)
        visit_min = doc.get("visit_duration_min") or 30
        fill[best_day] += visit_min

    for pref in auto:
        doc = doc_map.get(pref.place_id) or {}
        candidate_days = _open_day_indices(doc, day_configs)
        best_day = max(candidate_days, key=lambda i: capacity[i] - fill[i])
        buckets[best_day].append(pref.place_id)
        visit_min = doc.get("visit_duration_min") or 30
        fill[best_day] += visit_min

    return buckets


def _is_accommodation_transition_day(anchors: DayAccommodationAnchors) -> bool:
    """True when START/END resolve to two different stays — see ADR-15 for why END is then not auto-applied."""
    return anchors.start is not None and anchors.end is not None and anchors.start is not anchors.end


async def optimize_trip(
    db: AsyncDatabase,
    manager: GoogleRoutesManager,
    request: MultiDayRequest,
) -> MultiDayResponse:
    """Run multi-day TSP optimization.

    1. Fetch all place documents from MongoDB in one batch.
    2. Partition places across days (pinned by day_index, others via greedy bin-packing).
    3. For each day, apply per-day preference overrides and run the single-day solver.
    4. Collect DayPlan results and return MultiDayResponse.
    """
    all_place_ids = [p.place_id for p in request.places]
    docs = await fetch_places_by_ids(db, all_place_ids)
    doc_map: dict[str, dict] = {str(doc["_id"]): doc for doc in docs}

    slot_map: dict[tuple[str, int], DaySlot] = {}
    for p in request.places:
        for slot in p.day_preferences:
            slot_map[(p.place_id, slot.day_index)] = slot

    buckets = _partition_places(request.places, len(request.days), request.days, doc_map)
    day_anchors = resolve_day_anchors([cfg.date for cfg in request.days], request.accommodations)

    day_plans: list[DayPlan] = []

    for day_idx, cfg in enumerate(request.days):
        day_place_ids = buckets.get(day_idx, [])

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

        anchors = day_anchors[day_idx]
        accommodation_start = anchors.start
        # Autoderived END is suppressed on a changeover day — see _is_accommodation_transition_day.
        accommodation_end = None if _is_accommodation_transition_day(anchors) else anchors.end

        day_request = OptimizeRequest(
            place_ids=day_place_ids,
            transport_mode=request.transport_mode,
            day_start_hour=cfg.day_start_hour,
            day_end_hour=cfg.day_end_hour,
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
        unassigned=[],
    )
