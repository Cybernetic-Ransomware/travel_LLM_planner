"""Unit tests for the optimizer solver service (optimize_route orchestration)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

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

    def test_split_hours_two_periods_produces_two_segments(self):
        """Two disjoint periods on the same day → two segments in the TimeWindow."""
        doc = {
            "opening_hours": {
                "periods": [
                    {"open": {"day": 1, "hour": 9, "minute": 0}, "close": {"day": 1, "hour": 13, "minute": 0}},
                    {"open": {"day": 1, "hour": 15, "minute": 0}, "close": {"day": 1, "hour": 18, "minute": 0}},
                ]
            }
        }
        tw = _parse_time_window(doc, _9H, _21H, 1)
        assert tw is not None
        assert len(tw.segments) == 2
        assert tw.segments[0] == (9 * 3600, 13 * 3600)
        assert tw.segments[1] == (15 * 3600, 18 * 3600)

    def test_single_continuous_period_produces_one_segment(self):
        """One period → single segment; backward-compatible behaviour."""
        doc = {
            "opening_hours": {
                "periods": [{"open": {"day": 2, "hour": 10, "minute": 0}, "close": {"day": 2, "hour": 19, "minute": 0}}]
            }
        }
        tw = _parse_time_window(doc, _9H, _21H, 2)
        assert tw is not None
        assert len(tw.segments) == 1
        assert tw.open_s == 10 * 3600
        assert tw.close_s == 19 * 3600

    def test_split_hours_one_segment_outside_day_bounds_is_dropped(self):
        """If one period falls outside day bounds after intersection, only valid ones survive."""
        doc = {
            "opening_hours": {
                "periods": [
                    # period 1: 06:00–08:00 → before day_start 09:00 → intersection empty → dropped
                    {"open": {"day": 1, "hour": 6, "minute": 0}, "close": {"day": 1, "hour": 8, "minute": 0}},
                    # period 2: 10:00–18:00 → valid
                    {"open": {"day": 1, "hour": 10, "minute": 0}, "close": {"day": 1, "hour": 18, "minute": 0}},
                ]
            }
        }
        tw = _parse_time_window(doc, _9H, _21H, 1)
        assert tw is not None
        assert len(tw.segments) == 1
        assert tw.open_s == 10 * 3600


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
@freeze_time("2026-06-01")
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


@pytest.mark.unit
async def test_optimize_past_departure_time_clamped_to_now(test_db, google_routes_manager):
    """A departure_time in the past must be clamped to now before calling get_matrix."""
    docs = [_place("p1"), _place("p2")]
    matrix = _make_matrix(("p1", "p2", 300), ("p2", "p1", 300))
    mock_get_matrix = AsyncMock(return_value=(matrix, "OK", None))
    before_call = datetime.now(UTC)

    with (
        patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
        patch("src.optimizer.solver.service.get_matrix", new=mock_get_matrix),
    ):
        request = OptimizeRequest(
            place_ids=["p1", "p2"],
            transport_mode=TransportMode.TRANSIT,
            departure_date=date(2020, 1, 1),  # well in the past
        )
        await optimize_route(test_db, google_routes_manager, request)

    departure_time = mock_get_matrix.call_args[0][4]
    assert departure_time is not None
    assert departure_time >= before_call


@pytest.mark.regression
async def test_split_hours_no_visit_scheduled_in_break(test_db, google_routes_manager):
    """Regression: a place with a lunch break must not receive a visit during that break.

    Place 'p2' is open 09:00–13:00 and 15:00–18:00.  The solver must schedule the
    visit either before 13:00 or after 15:00, never between 13:00 and 15:00.
    """
    from src.optimizer.solver.models import TimeWindow  # noqa: PLC0415

    _13H = 13 * 3600
    _15H = 15 * 3600

    docs = [
        _place("p1", visit_min=30),  # no split hours
        _place(
            "p2",
            visit_min=30,
            opening_hours={
                "periods": [
                    {"open": {"day": 1, "hour": 9, "minute": 0}, "close": {"day": 1, "hour": 13, "minute": 0}},
                    {"open": {"day": 1, "hour": 15, "minute": 0}, "close": {"day": 1, "hour": 18, "minute": 0}},
                ]
            },
        ),
    ]
    matrix = _make_matrix(("p1", "p2", 600), ("p2", "p1", 600))

    with (
        patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
        patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
    ):
        request = OptimizeRequest(
            place_ids=["p1", "p2"],
            transport_mode=TransportMode.WALK,
            departure_date=date(2026, 1, 5),  # Monday
        )
        result = await optimize_route(test_db, google_routes_manager, request)

    p2_steps = [s for s in result.steps if s.place_id == "p2"]
    assert p2_steps, "p2 should be included in the route"
    p2_step = p2_steps[0]
    arrival_s = p2_step.arrival_time.hour * 3600 + p2_step.arrival_time.minute * 60
    departure_s = p2_step.departure_time.hour * 3600 + p2_step.departure_time.minute * 60
    visit_start_s = departure_s - p2_step.visit_duration_min * 60
    assert not (_13H < visit_start_s < _15H), (
        f"Visit started at {visit_start_s // 3600:02d}:{(visit_start_s % 3600) // 60:02d} — inside the break window"
    )


def _full_matrix(*pairs: tuple[str, str, int]) -> DistanceMatrix:
    """Symmetric matrix: every pair gets entries in both directions."""
    entries = {}
    for o, d, t in pairs:
        entries[(o, d)] = MatrixEntry(o, d, t * 80, t)
        entries[(d, o)] = MatrixEntry(d, o, t * 80, t)
    return DistanceMatrix(entries, TransportMode.WALK, _NOW)


@pytest.mark.unit
class TestPriorityRetry:
    """Hard must-see guarantee: low-priority places are dropped to fit must-see ones."""

    @staticmethod
    def _run(docs: list[dict], matrix: DistanceMatrix, **request_kwargs):
        async def go(test_db, google_routes_manager):
            with (
                patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
                patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
            ):
                request = OptimizeRequest(
                    place_ids=[str(d["_id"]) for d in docs],
                    transport_mode=TransportMode.WALK,
                    **request_kwargs,
                )
                return await optimize_route(test_db, google_routes_manager, request)

        return go

    async def test_optional_dropped_to_fit_must_see(self, test_db, google_routes_manager):
        """Two must-see (20 min each) and one optional in a 1-hour day: the optional
        lures the greedy path away from the second must-see, so it must be dropped."""
        docs = [
            _place("m1", visit_min=20, priority="must_see"),
            _place("m2", visit_min=20, priority="must_see"),
            _place("o1", visit_min=20, priority="optional"),
        ]
        matrix = _full_matrix(("m1", "m2", 600), ("m1", "o1", 60), ("m2", "o1", 60))
        result = await self._run(docs, matrix, day_start_hour=9, day_end_hour=10)(test_db, google_routes_manager)

        routed = {s.place_id for s in result.steps}
        assert routed == {"m1", "m2"}
        assert [s.place_id for s in result.skipped] == ["o1"]
        assert result.skipped[0].reason == "DROPPED_LOW_PRIORITY"

    async def test_normal_dropped_when_no_optional_left(self, test_db, google_routes_manager):
        docs = [
            _place("m1", visit_min=20, priority="must_see"),
            _place("m2", visit_min=20, priority="must_see"),
            _place("n1", visit_min=20, priority="normal"),
        ]
        matrix = _full_matrix(("m1", "m2", 600), ("m1", "n1", 60), ("m2", "n1", 60))
        result = await self._run(docs, matrix, day_start_hour=9, day_end_hour=10)(test_db, google_routes_manager)

        routed = {s.place_id for s in result.steps}
        assert routed == {"m1", "m2"}
        assert [s.place_id for s in result.skipped] == ["n1"]
        assert result.skipped[0].reason == "DROPPED_LOW_PRIORITY"

    async def test_infeasible_must_see_does_not_drop_others(self, test_db, google_routes_manager):
        """A must-see that cannot fit its own window keeps the standard skip reason
        and must not cause lower-priority places to be dropped."""
        docs = [
            _place("p1"),
            _place("p2"),
            _place("p3", visit_min=90, preferred_hour_from=20, preferred_hour_to=21, priority="must_see"),
        ]
        matrix = _full_matrix(("p1", "p2", 600), ("p1", "p3", 600), ("p2", "p3", 600))
        result = await self._run(docs, matrix)(test_db, google_routes_manager)

        routed = {s.place_id for s in result.steps}
        assert routed == {"p1", "p2"}
        assert [s.place_id for s in result.skipped] == ["p3"]
        assert result.skipped[0].reason == "TIME_WINDOW_INFEASIBLE"
        assert not any(s.reason == "DROPPED_LOW_PRIORITY" for s in result.skipped)

    async def test_no_priorities_single_pass_no_drops(self, test_db, google_routes_manager):
        """Documents without a priority field behave exactly as before."""
        docs = [_place("p1"), _place("p2")]
        matrix = _full_matrix(("p1", "p2", 600))
        result = await self._run(docs, matrix)(test_db, google_routes_manager)

        assert len(result.steps) == 2
        assert result.skipped == []


@pytest.mark.unit
async def test_optimize_skip_reason_matrix_incomplete(test_db, google_routes_manager):
    """A place with some but not all matrix edges should be reported as MATRIX_INCOMPLETE.

    p3 has a 60-min window (20:00–21:00) but a 90-min visit, so no start time fits —
    nearest_neighbor puts it in solver_skipped.  Matrix has one edge for p3 (p1→p3)
    but not both (p3→p1 and p2→p3 are absent), so actual_edges=1 < expected=2.
    """
    docs = [
        _place("p1"),
        _place("p2"),
        # p3: window too tight for the visit → solver skips it
        _place("p3", visit_min=90, preferred_hour_from=20, preferred_hour_to=21),
    ]
    # p3 has exactly one edge (p1→p3) out of two expected — partial coverage
    matrix = _make_matrix(
        ("p1", "p2", 600),
        ("p2", "p1", 600),
        ("p1", "p3", 600),  # one direction for p3; p3→p1 and p2↔p3 absent
    )

    with (
        patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
        patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
    ):
        request = OptimizeRequest(place_ids=["p1", "p2", "p3"], transport_mode=TransportMode.WALK)
        result = await optimize_route(test_db, google_routes_manager, request)

    p3_skips = [s for s in result.skipped if s.place_id == "p3"]
    assert p3_skips, "p3 should be in skipped"
    assert p3_skips[0].reason == "MATRIX_INCOMPLETE"


def _anchor_matrix(*pairs: tuple[str, str, int]) -> DistanceMatrix:
    """Directed matrix (no auto-reverse) — anchor legs are direction-limited by design."""
    entries = {(o, d): MatrixEntry(o, d, t * 80, t) for o, d, t in pairs}
    return DistanceMatrix(entries, TransportMode.WALK, _NOW)


@pytest.mark.unit
class TestOptimizeRouteAnchors:
    """End-to-end anchor behaviour: geometry only, no leak into public steps/skipped."""

    async def test_no_anchors_behaves_as_before(self, test_db, google_routes_manager):
        docs = [_place("p1"), _place("p2")]
        matrix = _full_matrix(("p1", "p2", 600))

        with (
            patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
        ):
            request = OptimizeRequest(place_ids=["p1", "p2"], transport_mode=TransportMode.WALK)
            result = await optimize_route(test_db, google_routes_manager, request)

        assert len(result.steps) == 2
        assert result.travel_to_end_s == 0

    async def test_start_only_first_step_travels_from_anchor(self, test_db, google_routes_manager):
        docs = [_place("p1"), _place("p2")]
        matrix = _anchor_matrix(
            ("__start__", "p1", 400),
            ("__start__", "p2", 900),
            ("p1", "p2", 600),
            ("p2", "p1", 600),
        )
        mock_get_matrix = AsyncMock(return_value=(matrix, "OK", None))

        with (
            patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.service.get_matrix", new=mock_get_matrix),
        ):
            request = OptimizeRequest(
                place_ids=["p1", "p2"], transport_mode=TransportMode.WALK, start_lat=50.0, start_lng=20.0
            )
            result = await optimize_route(test_db, google_routes_manager, request)

        # __start__/__end__ must never leak into the public step list
        assert {s.place_id for s in result.steps} == {"p1", "p2"}
        # p1 is closer to the anchor (400s) — the pinned start must route there first
        assert result.steps[0].place_id == "p1"
        assert result.steps[0].travel_from_previous_s == 400
        assert result.travel_to_end_s == 0
        # get_matrix must have been called with the anchor forwarded, not silently dropped
        assert mock_get_matrix.call_args.kwargs["start_anchor"] == ("__start__", 50.0, 20.0)
        assert mock_get_matrix.call_args.kwargs["end_anchor"] is None

    async def test_end_only_last_leg_captured_in_travel_to_end_s(self, test_db, google_routes_manager):
        docs = [_place("p1"), _place("p2")]
        matrix = _anchor_matrix(
            ("p1", "p2", 600),
            ("p2", "p1", 600),
            ("p1", "__end__", 900),
            ("p2", "__end__", 200),
        )

        with (
            patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
        ):
            request = OptimizeRequest(place_ids=["p1", "p2"], transport_mode=TransportMode.WALK, end_lat=51.0, end_lng=21.0)
            result = await optimize_route(test_db, google_routes_manager, request)

        assert {s.place_id for s in result.steps} == {"p1", "p2"}
        # p2 is closer to the anchor (200s) — must be visited last to minimize the final leg
        assert result.steps[-1].place_id == "p2"
        assert result.travel_to_end_s == 200
        assert result.total_travel_time_s == 600 + 200

    async def test_start_and_end_same_coordinates_round_trip(self, test_db, google_routes_manager):
        """START == END (the future 'hotel' case): two distinct internal legs, not one node."""
        docs = [_place("p1"), _place("p2")]
        matrix = _anchor_matrix(
            ("__start__", "p1", 300),
            ("__start__", "p2", 700),
            ("p1", "p2", 500),
            ("p2", "p1", 500),
            ("p1", "__end__", 700),
            ("p2", "__end__", 300),
        )

        with (
            patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
        ):
            request = OptimizeRequest(
                place_ids=["p1", "p2"],
                transport_mode=TransportMode.WALK,
                start_lat=50.0,
                start_lng=20.0,
                end_lat=50.0,
                end_lng=20.0,
            )
            result = await optimize_route(test_db, google_routes_manager, request)

        assert {s.place_id for s in result.steps} == {"p1", "p2"}
        assert result.steps[0].place_id == "p1"
        assert result.steps[0].travel_from_previous_s == 300
        assert result.steps[-1].place_id == "p2"
        assert result.travel_to_end_s == 300
        assert result.total_travel_time_s == 300 + 500 + 300

    async def test_single_place_with_anchors_has_nonzero_travel(self, test_db, google_routes_manager):
        """Regression: a day with exactly one place must not teleport — see multi_day_service fix."""
        docs = [_place("p1")]
        matrix = _anchor_matrix(("__start__", "p1", 500), ("p1", "__end__", 700))

        with (
            patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
        ):
            request = OptimizeRequest(
                place_ids=["p1"],
                transport_mode=TransportMode.WALK,
                start_lat=50.0,
                start_lng=20.0,
                end_lat=51.0,
                end_lng=21.0,
            )
            result = await optimize_route(test_db, google_routes_manager, request)

        assert len(result.steps) == 1
        assert result.steps[0].place_id == "p1"
        assert result.steps[0].travel_from_previous_s == 500
        assert result.travel_to_end_s == 700
        assert result.total_travel_time_s == 500 + 700

    async def test_anchor_never_appears_in_skipped(self, test_db, google_routes_manager):
        """Anchor ids must never leak into SkippedPlace/DROPPED_LOW_PRIORITY across any tier."""
        docs = [
            _place("m1", visit_min=20, priority="must_see"),
            _place("o1", visit_min=20, priority="optional"),
        ]
        matrix = _anchor_matrix(
            ("__start__", "m1", 100),
            ("__start__", "o1", 100),
            ("m1", "o1", 100),
            ("o1", "m1", 100),
            ("m1", "__end__", 100),
            ("o1", "__end__", 100),
        )

        with (
            patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
        ):
            request = OptimizeRequest(
                place_ids=["m1", "o1"],
                transport_mode=TransportMode.WALK,
                day_start_hour=9,
                day_end_hour=10,
                start_lat=50.0,
                start_lng=20.0,
                end_lat=51.0,
                end_lng=21.0,
            )
            result = await optimize_route(test_db, google_routes_manager, request)

        skipped_ids = {s.place_id for s in result.skipped}
        assert "__start__" not in skipped_ids
        assert "__end__" not in skipped_ids
        step_ids = {s.place_id for s in result.steps}
        assert "__start__" not in step_ids
        assert "__end__" not in step_ids
