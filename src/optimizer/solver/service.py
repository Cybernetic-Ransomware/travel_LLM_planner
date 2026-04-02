"""Optimizer service: orchestrates TSP solving for a set of places."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from fastapi import HTTPException
from pymongo.asynchronous.database import AsyncDatabase

from src.gmaps.storage import fetch_places_by_ids
from src.optimizer.matrix.client import GoogleRoutesManager
from src.optimizer.matrix.service import get_matrix
from src.optimizer.solver.engine import nearest_neighbor, schedule_route, two_opt
from src.optimizer.solver.models import (
    OptimizeRequest,
    OptimizeResponse,
    RouteStep,
    SkippedPlace,
    TimeWindow,
)


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
            day_period = next((p for p in periods if p.get("open", {}).get("day") == google_weekday), None)
            if day_period is None:
                return None  # closed on this day of week

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
                open_s = max(open_s, oh_open_s)
                close_s = min(close_s, oh_close_s)
            else:
                open_s = max(open_s, oh_open_s)

    if close_s <= open_s:
        return None

    return TimeWindow(open_s=open_s, close_s=close_s)


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

    matrix, status, error = await get_matrix(db, manager, coords, request.transport_mode, departure_time)

    if matrix is None:
        raise HTTPException(status_code=502, detail=f"Distance matrix unavailable: {status} — {error}")

    node_ids = [pid for pid, _, _ in coords]
    route, solver_skipped = nearest_neighbor(node_ids, matrix, time_windows, visit_durations_s, day_start_s, day_end_s)
    route = two_opt(route, matrix, time_windows, visit_durations_s, day_start_s, day_end_s)

    for place_id in solver_skipped:
        has_any_entry = any(
            matrix.get(place_id, other) is not None or matrix.get(other, place_id) is not None
            for other in node_ids
            if other != place_id
        )
        reason = "TIME_WINDOW_INFEASIBLE" if has_any_entry else "NO_MATRIX_ENTRY"
        skipped.append(SkippedPlace(place_id=place_id, name=doc_map[place_id].get("name"), reason=reason))

    schedule = schedule_route(route, matrix, time_windows, visit_durations_s, day_start_s)

    steps: list[RouteStep] = []
    total_travel_s = 0
    total_visit_min = 0
    total_wait_min = 0

    for place_id, arrival_s, departure_s, travel_s in schedule:
        doc = doc_map[place_id]
        wait_s = max(0, time_windows[place_id].open_s - arrival_s)
        visit_s = visit_durations_s[place_id]

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
        total_travel_s += travel_s
        total_visit_min += visit_s // 60
        total_wait_min += wait_s // 60

    return OptimizeResponse(
        steps=steps,
        total_travel_time_s=total_travel_s,
        total_visit_time_min=total_visit_min,
        total_wait_min=total_wait_min,
        transport_mode=request.transport_mode,
        skipped=skipped,
    )
