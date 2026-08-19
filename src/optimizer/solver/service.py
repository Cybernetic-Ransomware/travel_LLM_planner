"""Optimizer service: orchestrates TSP solving for a set of places."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from pymongo.asynchronous.database import AsyncDatabase

from src.config.conf_logger import setup_logger
from src.core.exceptions import MatrixUnavailableError
from src.gmaps import fetch_places_by_ids
from src.optimizer.matrix.client import GoogleRoutesManager
from src.optimizer.matrix.models import DistanceMatrix
from src.optimizer.matrix.service import get_matrix
from src.optimizer.solver.engine import nearest_neighbor, nn_from_start, schedule_route, two_opt
from src.optimizer.solver.models import (
    OptimizeRequest,
    OptimizeResponse,
    RouteStep,
    SkippedPlace,
    TimeWindow,
)

logger = setup_logger(__name__, "optimizer")

# Weights are spaced so a single must_see place always outweighs any combination of
# lower-priority places. This holds as long as a route has fewer than 1000 places;
# OptimizeRequest and MultiDayRequest cap requests at 50 places.
_PRIORITY_WEIGHTS = {"must_see": 1_000_000, "normal": 1_000, "optional": 1}

# Sentinel ids for day-start/day-end anchors — must never collide with real node/place ids, never exposed publicly.
_START_ANCHOR_ID = "__start__"
_END_ANCHOR_ID = "__end__"


def _google_weekday(d: date) -> int:
    """Convert a Python date to Google day-of-week (0=Sunday, 1=Monday, ..., 6=Saturday)."""
    # Python weekday(): 0=Monday ... 6=Sunday → shift by 1 and wrap
    return (d.weekday() + 1) % 7


def _parse_time_window(
    doc: dict,
    day_start_s: int,
    day_end_s: int,
    google_weekday: int | None,
) -> TimeWindow | None:
    """Build a TimeWindow from user preferences intersected with opening hours.

    Returns None when the place is definitively closed on the requested day
    or the resulting window is zero/negative after intersection.
    """
    pref_from = doc.get("preferred_hour_from")
    pref_to = doc.get("preferred_hour_to")
    open_s = (pref_from * 3600) if pref_from is not None else day_start_s
    close_s = (pref_to * 3600) if pref_to is not None else day_end_s

    if google_weekday is not None:
        opening_hours = doc.get("opening_hours")
        periods: list[dict] = (opening_hours or {}).get("periods", [])
        if periods:
            day_periods = [p for p in periods if p.get("open", {}).get("day") == google_weekday]
            if not day_periods:
                return None  # closed on this day of week

            segments: list[tuple[int, int]] = []
            for day_period in day_periods:
                oh_open = day_period["open"]
                oh_open_s = oh_open.get("hour", 0) * 3600 + oh_open.get("minute", 0) * 60
                oh_close_data = day_period.get("close")
                if oh_close_data is not None:
                    close_day = oh_close_data.get("day")
                    open_day = oh_open.get("day")
                    if close_day is not None and open_day is not None and close_day != open_day:
                        # Closes past midnight — treat as open until end of planning day
                        oh_close_s = 24 * 3600
                    else:
                        oh_close_s = oh_close_data.get("hour", 0) * 3600 + oh_close_data.get("minute", 0) * 60
                    seg_open = max(open_s, oh_open_s)
                    seg_close = min(close_s, oh_close_s)
                else:
                    seg_open = max(open_s, oh_open_s)
                    seg_close = close_s

                if seg_close > seg_open:
                    segments.append((seg_open, seg_close))

            if not segments:
                return None

            return TimeWindow.from_segments(segments)

    if close_s <= open_s:
        return None

    return TimeWindow(open_s=open_s, close_s=close_s)


def _solve_with_priorities(
    node_ids: list[str],
    matrix: DistanceMatrix,
    time_windows: dict[str, TimeWindow],
    visit_durations_s: dict[str, int],
    day_start_s: int,
    day_end_s: int,
    priorities: dict[str, str],
    start_anchor: str | None = None,
    end_anchor: str | None = None,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Solve the route with a hard must-see guarantee.

    Runs Nearest Neighbor on progressively smaller candidate sets (all places →
    without optional → must-see only) until the solver no longer leaves out any
    must-see place, then keeps the attempt with the highest total priority weight.
    A must-see that is physically infeasible even alone cannot improve any attempt,
    so the best earlier attempt wins and the place stays in solver_skipped for
    standard reason classification.

    When start_anchor is given, NN is pinned to start there instead of trying every
    node as a candidate start. end_anchor, when given, is threaded through so it is
    appended as the route's forced final stop (see engine.nn_from_start). Returned
    routes may include start_anchor/end_anchor as regular elements — callers must
    exclude them from anything keyed by node_ids (they are not real places).

    Returns:
        (route, solver_skipped, dropped_low_priority, final_candidates)
    """
    weights = {n: _PRIORITY_WEIGHTS.get(priorities.get(n, "normal"), 1_000) for n in node_ids}

    tiers = [
        node_ids,
        [n for n in node_ids if priorities.get(n, "normal") != "optional"],
        [n for n in node_ids if priorities.get(n, "normal") == "must_see"],
    ]

    best: tuple[list[str], list[str], list[str]] | None = None
    best_score = -1
    prev_size: int | None = None
    for tier in tiers:
        if prev_size is not None and len(tier) == prev_size:
            continue  # tier removes nothing — rerun would produce the same result
        prev_size = len(tier)
        if start_anchor is not None:
            route, solver_skipped = nn_from_start(
                start_anchor,
                tier,
                matrix,
                time_windows,
                visit_durations_s,
                day_start_s,
                day_end_s,
                end_anchor=end_anchor,
            )
        else:
            route, solver_skipped = nearest_neighbor(
                tier, matrix, time_windows, visit_durations_s, day_start_s, day_end_s, weights, end_anchor=end_anchor
            )
        score = sum(weights.get(n, 0) for n in route)
        if score > best_score:
            best_score = score
            best = (route, solver_skipped, tier)
        if not any(priorities.get(n, "normal") == "must_see" for n in solver_skipped):
            break

    assert best is not None  # the first tier always runs
    route, solver_skipped, candidates = best
    candidate_set = set(candidates)
    dropped = [n for n in node_ids if n not in candidate_set]
    return route, solver_skipped, dropped, candidates


def _seconds_to_time(s: int) -> time:
    """Convert integer seconds-from-midnight to a datetime.time object."""
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return time(hour=h % 24, minute=m, second=sec)


async def optimize_route(
    db: AsyncDatabase,
    manager: GoogleRoutesManager,
    request: OptimizeRequest,
    docs: list[dict] | None = None,
) -> OptimizeResponse:
    """Run the full TSP optimization pipeline.

    1. Fetch place documents from MongoDB (skipped when docs are provided).
    2. Filter out places without coordinates or with an infeasible time window.
    3. Build a distance matrix (cache → Google Routes API).
    4. Run Nearest Neighbor construction + 2-opt improvement.
    5. Schedule wall-clock arrival/departure times and build the response.

    Args:
        docs: Pre-fetched place documents. When supplied the DB fetch is skipped,
              allowing callers to apply in-memory overrides before optimization.
    """
    day_start_s = request.day_start_hour * 3600
    day_end_s = request.day_end_hour * 3600
    google_weekday = _google_weekday(request.departure_date) if request.departure_date else None

    departure_time: datetime | None = None
    if request.departure_date is not None:
        departure_time = datetime(
            request.departure_date.year,
            request.departure_date.month,
            request.departure_date.day,
            request.day_start_hour,
            tzinfo=UTC,
        )
        now = datetime.now(UTC)
        if departure_time < now:
            logger.warning(
                "departure_time %s is in the past — clamping to now (%s)",
                departure_time.isoformat(),
                now.isoformat(),
            )
            departure_time = now

    if docs is None:
        docs = await fetch_places_by_ids(db, request.place_ids)
    doc_map = {str(doc["_id"]): doc for doc in docs}

    skipped: list[SkippedPlace] = []
    coords: list[tuple[str, float, float]] = []
    time_windows: dict[str, TimeWindow] = {}
    visit_durations_s: dict[str, int] = {}

    for place_id in request.place_ids:
        doc = doc_map.get(place_id)
        if doc is None:
            skipped.append(SkippedPlace(place_id=place_id, name=None, reason="NO_COORDINATES"))
            continue

        lat = doc.get("lat")
        lng = doc.get("lng")
        if lat is None or lng is None:
            skipped.append(SkippedPlace(place_id=place_id, name=doc.get("name"), reason="NO_COORDINATES"))
            continue

        tw = _parse_time_window(doc, day_start_s, day_end_s, google_weekday)
        if tw is None:
            skipped.append(SkippedPlace(place_id=place_id, name=doc.get("name"), reason="TIME_WINDOW_INFEASIBLE"))
            continue

        coords.append((place_id, float(lat), float(lng)))
        time_windows[place_id] = tw
        visit_durations_s[place_id] = (doc.get("visit_duration_min") or 30) * 60

    if not coords:
        return OptimizeResponse(
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            transport_mode=request.transport_mode,
            skipped=skipped,
        )

    start_anchor: tuple[str, float, float] | None = None
    if request.start_lat is not None and request.start_lng is not None:
        start_anchor = (_START_ANCHOR_ID, request.start_lat, request.start_lng)

    end_anchor: tuple[str, float, float] | None = None
    if request.end_lat is not None and request.end_lng is not None:
        end_anchor = (_END_ANCHOR_ID, request.end_lat, request.end_lng)

    start_anchor_id = start_anchor[0] if start_anchor is not None else None
    end_anchor_id = end_anchor[0] if end_anchor is not None else None

    matrix, status, error = await get_matrix(
        db, manager, coords, request.transport_mode, departure_time, start_anchor=start_anchor, end_anchor=end_anchor
    )

    if matrix is None:
        logger.error("Distance matrix unavailable: status=%s error=%s", status, error)
        raise MatrixUnavailableError(status=status or "UNKNOWN", error=error)

    node_ids = [pid for pid, _, _ in coords]
    priorities = {pid: (doc_map[pid].get("priority") or "normal") for pid in node_ids}
    route, solver_skipped, dropped, final_candidates = _solve_with_priorities(
        node_ids,
        matrix,
        time_windows,
        visit_durations_s,
        day_start_s,
        day_end_s,
        priorities,
        start_anchor=start_anchor_id,
        end_anchor=end_anchor_id,
    )
    route = two_opt(
        route, matrix, time_windows, visit_durations_s, day_start_s, day_end_s, pin_end=end_anchor_id is not None
    )

    for place_id in dropped:
        skipped.append(SkippedPlace(place_id=place_id, name=doc_map[place_id].get("name"), reason="DROPPED_LOW_PRIORITY"))

    expected_edges = len(final_candidates) - 1
    for place_id in solver_skipped:
        actual_edges = sum(
            1
            for other in final_candidates
            if other != place_id and (matrix.get(place_id, other) is not None or matrix.get(other, place_id) is not None)
        )
        if actual_edges == 0:
            reason = "NO_MATRIX_ENTRY"
        elif actual_edges < expected_edges:
            reason = "MATRIX_INCOMPLETE"
        else:
            reason = "TIME_WINDOW_INFEASIBLE"
        skipped.append(SkippedPlace(place_id=place_id, name=doc_map[place_id].get("name"), reason=reason))

    schedule = schedule_route(route, matrix, time_windows, visit_durations_s, day_start_s)

    steps: list[RouteStep] = []
    total_travel_s = 0
    total_visit_min = 0
    total_wait_min = 0
    travel_to_end_s = 0

    for place_id, arrival_s, departure_s, travel_s in schedule:
        total_travel_s += travel_s

        if place_id == end_anchor_id:
            travel_to_end_s = travel_s
            continue
        if place_id == start_anchor_id:
            continue

        doc = doc_map[place_id]
        visit_s = visit_durations_s[place_id]
        wait_s = max(0, departure_s - visit_s - arrival_s)

        steps.append(
            RouteStep(
                place_id=place_id,
                name=doc.get("name"),
                lat=doc.get("lat"),
                lng=doc.get("lng"),
                arrival_time=_seconds_to_time(arrival_s),
                departure_time=_seconds_to_time(departure_s),
                travel_from_previous_s=travel_s,
                visit_duration_min=visit_s // 60,
                wait_min=wait_s // 60,
            )
        )
        total_visit_min += visit_s // 60
        total_wait_min += wait_s // 60

    return OptimizeResponse(
        steps=steps,
        total_travel_time_s=total_travel_s,
        total_visit_time_min=total_visit_min,
        total_wait_min=total_wait_min,
        transport_mode=request.transport_mode,
        skipped=skipped,
        travel_to_end_s=travel_to_end_s,
    )
