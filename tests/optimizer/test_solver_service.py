"""Unit tests for the optimizer solver service (optimize_route orchestration)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.optimizer.matrix.models import DistanceMatrix, MatrixEntry, TransportMode
from src.optimizer.solver.models import OptimizeRequest
from src.optimizer.solver.service import _google_weekday, _parse_time_window, optimize_route

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_9H = 9 * 3600
_21H = 21 * 3600


def _make_matrix(*pairs: tuple[str, str, int]) -> DistanceMatrix:
    entries = {(o, d): MatrixEntry(o, d, t * 80, t) for o, d, t in pairs}
    return DistanceMatrix(entries, TransportMode.WALK, _NOW)


def _place(pid: str, *, lat: float = 50.0, lng: float = 20.0, visit_min: int = 30, **kwargs) -> dict:
    return {"_id": pid, "name": f"Place {pid}", "lat": lat, "lng": lng, "visit_duration_min": visit_min, **kwargs}


@pytest.mark.unit
class TestGoogleWeekday:
    def test_sunday(self):
        assert _google_weekday(date(2026, 1, 4)) == 0  # Sunday

    def test_monday(self):
        assert _google_weekday(date(2026, 1, 5)) == 1  # Monday

    def test_saturday(self):
        assert _google_weekday(date(2026, 1, 3)) == 6  # Saturday


@pytest.mark.unit
class TestParseTimeWindow:
    def test_default_window_from_day_bounds(self):
        tw = _parse_time_window({}, _9H, _21H, None)
        assert tw is not None
        assert tw.open_s == _9H
        assert tw.close_s == _21H

    def test_user_preference_overrides_day_bounds(self):
        doc = {"preferred_hour_from": 10, "preferred_hour_to": 17}
        tw = _parse_time_window(doc, _9H, _21H, None)
        assert tw is not None
        assert tw.open_s == 10 * 3600
        assert tw.close_s == 17 * 3600

    def test_opening_hours_narrows_window(self):
        doc = {
            "opening_hours": {
                "periods": [{"open": {"day": 1, "hour": 10, "minute": 0}, "close": {"day": 1, "hour": 18, "minute": 0}}]
            }
        }
        tw = _parse_time_window(doc, _9H, _21H, 1)  # Monday
        assert tw is not None
        assert tw.open_s == 10 * 3600
        assert tw.close_s == 18 * 3600

    def test_closed_on_day_returns_none(self):
        doc = {
            "opening_hours": {
                "periods": [{"open": {"day": 1, "hour": 9, "minute": 0}, "close": {"day": 1, "hour": 21, "minute": 0}}]
            }
        }
        # Sunday (day=0) — no period exists → closed
        tw = _parse_time_window(doc, _9H, _21H, 0)
        assert tw is None

    def test_midnight_close_treated_as_end_of_day(self):
        """Close on the next day (e.g. bar open 17:00 → midnight) must not produce close_s=0."""
        doc = {
            "opening_hours": {
                "periods": [{"open": {"day": 2, "hour": 17, "minute": 0}, "close": {"day": 3, "hour": 0, "minute": 0}}]
            }
        }
        tw = _parse_time_window(doc, _9H, _21H, 2)  # Tuesday
        assert tw is not None
        assert tw.open_s == 17 * 3600
        assert tw.close_s == _21H  # capped by day_end_s (min of 24h and 21h)

    def test_no_opening_hours_data_uses_day_bounds(self):
        doc = {"opening_hours": None}
        tw = _parse_time_window(doc, _9H, _21H, 1)
        assert tw is not None
        assert tw.open_s == _9H

    def test_intersected_window_results_in_none_when_inverted(self):
        """User preference 10-12, opening hours 14-18 → intersection is empty."""
        doc = {
            "preferred_hour_from": 10,
            "preferred_hour_to": 12,
            "opening_hours": {
                "periods": [{"open": {"day": 1, "hour": 14, "minute": 0}, "close": {"day": 1, "hour": 18, "minute": 0}}]
            },
        }
        tw = _parse_time_window(doc, _9H, _21H, 1)
        assert tw is None


@pytest.mark.unit
async def test_optimize_skips_places_without_coordinates(test_db, google_routes_manager):
    docs = [{"_id": "p1", "name": "No coords", "lat": None, "lng": None}]

    with patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)):
        request = OptimizeRequest(place_ids=["p1", "p2"], transport_mode=TransportMode.WALK)
        result = await optimize_route(test_db, google_routes_manager, request)

    assert result.steps == []
    reasons = {s.reason for s in result.skipped}
    assert "NO_COORDINATES" in reasons


@pytest.mark.unit
async def test_optimize_skips_closed_place(test_db, google_routes_manager):
    monday_doc = {
        "_id": "p1",
        "name": "Closed Sunday",
        "lat": 50.0,
        "lng": 20.0,
        "opening_hours": {
            "periods": [{"open": {"day": 1, "hour": 9}, "close": {"day": 1, "hour": 18}}]  # Mon only
        },
    }

    with patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=[monday_doc])):
        # Requesting on a Sunday (2026-01-04)
        request = OptimizeRequest(
            place_ids=["p1", "p2"],
            transport_mode=TransportMode.WALK,
            departure_date=date(2026, 1, 4),
        )
        result = await optimize_route(test_db, google_routes_manager, request)

    assert any(s.reason == "TIME_WINDOW_INFEASIBLE" for s in result.skipped)


@pytest.mark.unit
async def test_optimize_raises_502_on_matrix_error(test_db, google_routes_manager):
    from fastapi import HTTPException

    docs = [_place("p1"), _place("p2")]

    with (
        patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
        patch(
            "src.optimizer.solver.service.get_matrix",
            new=AsyncMock(return_value=(None, "PERMISSION_DENIED", "key invalid")),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        request = OptimizeRequest(place_ids=["p1", "p2"], transport_mode=TransportMode.WALK)
        await optimize_route(test_db, google_routes_manager, request)

    assert exc_info.value.status_code == 502
    assert "PERMISSION_DENIED" in exc_info.value.detail


@pytest.mark.unit
async def test_optimize_two_places_happy_path(test_db, google_routes_manager):
    docs = [_place("p1"), _place("p2")]
    matrix = _make_matrix(("p1", "p2", 600), ("p2", "p1", 600))

    with (
        patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
        patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
    ):
        request = OptimizeRequest(place_ids=["p1", "p2"], transport_mode=TransportMode.WALK)
        result = await optimize_route(test_db, google_routes_manager, request)

    assert len(result.steps) == 2
    assert result.skipped == []
    assert result.total_travel_time_s == 600
    assert result.total_visit_time_min == 60  # 2 × 30 min


@pytest.mark.unit
async def test_optimize_departure_date_forwarded_to_get_matrix(test_db, google_routes_manager):
    docs = [_place("p1"), _place("p2")]
    matrix = _make_matrix(("p1", "p2", 300), ("p2", "p1", 300))
    mock_get_matrix = AsyncMock(return_value=(matrix, "OK", None))

    with (
        patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
        patch("src.optimizer.solver.service.get_matrix", new=mock_get_matrix),
    ):
        request = OptimizeRequest(
            place_ids=["p1", "p2"],
            transport_mode=TransportMode.TRANSIT,
            departure_date=date(2026, 6, 15),
        )
        await optimize_route(test_db, google_routes_manager, request)

    _, kwargs = mock_get_matrix.call_args
    departure_time = mock_get_matrix.call_args[0][4]
    assert departure_time is not None
    assert departure_time.date().isoformat() == "2026-06-15"


@pytest.mark.unit
async def test_optimize_step_fields_populated(test_db, google_routes_manager):
    docs = [_place("p1", lat=50.1, lng=20.1), _place("p2", lat=50.2, lng=20.2)]
    matrix = _make_matrix(("p1", "p2", 600), ("p2", "p1", 600))

    with (
        patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
        patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
    ):
        request = OptimizeRequest(place_ids=["p1", "p2"], transport_mode=TransportMode.WALK)
        result = await optimize_route(test_db, google_routes_manager, request)

    first_step = result.steps[0]
    assert first_step.travel_from_previous_s == 0  # first stop, no travel
    second_step = result.steps[1]
    assert second_step.travel_from_previous_s == 600
    assert second_step.lat is not None
    assert second_step.lng is not None
