"""Unit tests for the multi-day trip optimizer service."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.accommodations.models import AccommodationStay
from src.accommodations.resolver import DayAccommodationAnchors
from src.optimizer.matrix.models import DistanceMatrix, MatrixEntry, TransportMode
from src.optimizer.solver.models import (
    DayConfig,
    DaySlot,
    MultiDayRequest,
    MultiDayResponse,
    OptimizeRequest,
    OptimizeResponse,
    PlaceDayPreference,
    RouteStep,
    SkippedPlace,
)
from src.optimizer.solver.multi_day_service import (
    TransitionDayContext,
    _is_accommodation_transition_day,
    _open_day_indices,
    _partition_places,
    _resolve_segment_end_bound_fields,
    _transition_side,
    optimize_trip,
)
from src.optimizer.solver.service import optimize_route as solve_single_day
from src.transfers.models import TransferBlock


def _day_config(d: date = date(2026, 6, 1), **kwargs) -> DayConfig:
    return DayConfig(date=d, **kwargs)


def _pref(
    place_id: str,
    *,
    day_index: int | None = None,
    preferred_hour_from: int | None = None,
    preferred_hour_to: int | None = None,
) -> PlaceDayPreference:
    if day_index is not None:
        slot = DaySlot(day_index=day_index, preferred_hour_from=preferred_hour_from, preferred_hour_to=preferred_hour_to)
        return PlaceDayPreference(place_id=place_id, day_preferences=[slot])
    return PlaceDayPreference(place_id=place_id, day_preferences=[])


def _pref_flexible(place_id: str, *slots: DaySlot) -> PlaceDayPreference:
    return PlaceDayPreference(place_id=place_id, day_preferences=list(slots))


def _place(pid: str, *, lat: float = 50.0, lng: float = 20.0, visit_min: int = 30, **kwargs) -> dict:
    return {"_id": pid, "name": f"Place {pid}", "lat": lat, "lng": lng, "visit_duration_min": visit_min, **kwargs}


def _req(**kwargs) -> MultiDayRequest:
    defaults: dict = {
        "days": [_day_config(), _day_config(date(2026, 6, 2))],
        "places": [_pref("p1"), _pref("p2"), _pref("p3"), _pref("p4")],
        "transport_mode": TransportMode.WALK,
    }
    return MultiDayRequest(**{**defaults, **kwargs})


def _single_day_response(*place_ids: str) -> OptimizeResponse:
    steps = [
        RouteStep(
            place_id=pid,
            name=f"Place {pid}",
            lat=50.0,
            lng=20.0,
            arrival_time=time(10, 0),
            departure_time=time(10, 30),
            travel_from_previous_s=0,
            visit_duration_min=30,
        )
        for pid in place_ids
    ]
    return OptimizeResponse(
        steps=steps,
        total_travel_time_s=0,
        total_visit_time_min=30 * len(place_ids),
        total_wait_min=0,
        transport_mode=TransportMode.WALK,
        skipped=[],
    )


@pytest.mark.unit
class TestPlacePartitioning:
    def test_pinned_places_go_to_correct_day(self):
        places = [_pref("p1", day_index=0), _pref("p2", day_index=1)]
        configs = [_day_config(), _day_config(date(2026, 6, 2))]
        doc_map = {"p1": _place("p1"), "p2": _place("p2")}

        buckets = _partition_places(places, 2, configs, doc_map).buckets

        assert "p1" in buckets[0]
        assert "p2" in buckets[1]

    def test_auto_assign_distributes_across_days(self):
        places = [_pref("p1"), _pref("p2"), _pref("p3"), _pref("p4")]
        configs = [_day_config(), _day_config(date(2026, 6, 2))]
        doc_map = {f"p{i}": _place(f"p{i}") for i in range(1, 5)}

        buckets = _partition_places(places, 2, configs, doc_map).buckets

        assert sum(len(v) for v in buckets.values()) == 4
        assert all(len(buckets[i]) > 0 for i in range(2))

    def test_single_day_gets_all_auto_places(self):
        places = [_pref("p1"), _pref("p2")]
        configs = [_day_config()]
        doc_map = {"p1": _place("p1"), "p2": _place("p2")}

        buckets = _partition_places(places, 1, configs, doc_map).buckets

        assert set(buckets[0]) == {"p1", "p2"}

    def test_more_days_than_places_leaves_some_days_empty(self):
        places = [_pref("p1"), _pref("p2")]
        configs = [_day_config(date(2026, 6, d)) for d in range(1, 5)]
        doc_map = {"p1": _place("p1"), "p2": _place("p2")}

        buckets = _partition_places(places, 4, configs, doc_map).buckets

        assert sum(len(v) for v in buckets.values()) == 2

    def test_mixed_pinned_and_auto_assignment(self):
        places = [_pref("p1", day_index=0), _pref("p2"), _pref("p3")]
        configs = [_day_config(), _day_config(date(2026, 6, 2))]
        doc_map = {f"p{i}": _place(f"p{i}") for i in range(1, 4)}

        buckets = _partition_places(places, 2, configs, doc_map).buckets

        assert "p1" in buckets[0]
        assert sum(len(v) for v in buckets.values()) == 3

    def test_flexible_place_goes_to_best_candidate_day(self):
        # p1 pinned to day 0 (fill: 30 min); p2 flexible (day 0 or day 1)
        # day 0 remaining after p1: 720-30=690, day 1 remaining: 720
        # p2 should go to day 1 (more remaining capacity)
        configs = [_day_config(), _day_config(date(2026, 6, 2))]
        places = [
            _pref("p1", day_index=0),
            _pref_flexible("p2", DaySlot(day_index=0), DaySlot(day_index=1)),
        ]
        doc_map = {"p1": _place("p1"), "p2": _place("p2")}

        buckets = _partition_places(places, 2, configs, doc_map).buckets

        assert "p1" in buckets[0]
        assert "p2" in buckets[1]


@pytest.mark.unit
class TestPartitionPriorityOrder:
    """Priority-ordered packing: must_see claims the roomiest day before lower priorities."""

    # day 0: 9-13 → 240 min capacity; day 1: 9-12 → 180 min capacity
    _configs = [
        DayConfig(date=date(2026, 6, 1), day_start_hour=9, day_end_hour=13),
        DayConfig(date=date(2026, 6, 2), day_start_hour=9, day_end_hour=12),
    ]

    def test_auto_must_see_claims_roomiest_day_before_optional(self):
        # 150-min visits: whoever packs first takes day 0 (240), the other gets day 1 (180)
        places = [_pref("o1"), _pref("m1")]  # optional listed first — sorting must reorder
        doc_map = {
            "o1": _place("o1", visit_min=150, priority="optional"),
            "m1": _place("m1", visit_min=150, priority="must_see"),
        }

        buckets = _partition_places(places, 2, self._configs, doc_map).buckets

        assert "m1" in buckets[0]
        assert "o1" in buckets[1]

    def test_flexible_must_see_claims_roomiest_day_before_optional(self):
        places = [
            _pref_flexible("o1", DaySlot(day_index=0), DaySlot(day_index=1)),
            _pref_flexible("m1", DaySlot(day_index=0), DaySlot(day_index=1)),
        ]
        doc_map = {
            "o1": _place("o1", visit_min=150, priority="optional"),
            "m1": _place("m1", visit_min=150, priority="must_see"),
        }

        buckets = _partition_places(places, 2, self._configs, doc_map).buckets

        assert "m1" in buckets[0]
        assert "o1" in buckets[1]

    def test_equal_priorities_preserve_input_order(self):
        """Regression: docs without priority partition exactly as before (stable sort)."""
        places = [_pref("p1"), _pref("p2")]
        doc_map = {
            "p1": _place("p1", visit_min=150),
            "p2": _place("p2", visit_min=150),
        }

        buckets = _partition_places(places, 2, self._configs, doc_map).buckets

        assert "p1" in buckets[0]
        assert "p2" in buckets[1]


def _opening_hours(*google_days: int) -> dict:
    """Build a minimal opening_hours dict with periods for the given Google weekday numbers."""
    return {"periods": [{"open": {"day": d, "hour": 9}, "close": {"day": d, "hour": 17}} for d in google_days]}


# 2026-03-30 = Monday (Python weekday 0, Google weekday 1)
# 2026-03-31 = Tuesday (Python weekday 1, Google weekday 2)
_MON = date(2026, 3, 30)
_TUE = date(2026, 3, 31)


@pytest.mark.unit
class TestOpenDayIndices:
    def test_no_opening_hours_returns_all_days(self):
        configs = [_day_config(_MON), _day_config(_TUE)]
        assert _open_day_indices({}, configs) == [0, 1]

    def test_open_on_tuesday_only(self):
        doc = {"opening_hours": _opening_hours(2)}  # Google day 2 = Tuesday
        configs = [_day_config(_MON), _day_config(_TUE)]
        assert _open_day_indices(doc, configs) == [1]

    def test_open_on_both_days(self):
        doc = {"opening_hours": _opening_hours(1, 2)}  # Mon + Tue
        configs = [_day_config(_MON), _day_config(_TUE)]
        assert _open_day_indices(doc, configs) == [0, 1]

    def test_open_on_neither_day_falls_back_to_all(self):
        doc = {"opening_hours": _opening_hours(3, 4, 5)}  # Wed-Fri only
        configs = [_day_config(_MON), _day_config(_TUE)]
        assert _open_day_indices(doc, configs) == [0, 1]

    def test_single_day_open(self):
        doc = {"opening_hours": _opening_hours(2)}  # Tuesday only
        configs = [_day_config(_TUE)]
        assert _open_day_indices(doc, configs) == [0]


@pytest.mark.unit
class TestPartitionOpeningHoursAware:
    def test_auto_place_assigned_to_open_day(self):
        """Muzeum scenario: Auto place closed Monday, open Tuesday → must go to Day 1 (Tue)."""
        doc = _place("museum", opening_hours=_opening_hours(2))  # Tuesday only
        configs = [_day_config(_MON), _day_config(_TUE)]
        places = [_pref("museum")]
        doc_map = {"museum": doc}

        buckets = _partition_places(places, 2, configs, doc_map).buckets

        assert "museum" in buckets[1], "museum should be assigned to Tuesday (day index 1)"
        assert "museum" not in buckets[0]

    def test_flexible_place_skips_closed_day(self):
        """Flexible place prefers day 0 and day 1; closed on Monday → should go to Tuesday."""
        doc = _place("p1", opening_hours=_opening_hours(2))  # Tuesday only
        configs = [_day_config(_MON), _day_config(_TUE)]
        places = [_pref_flexible("p1", DaySlot(day_index=0), DaySlot(day_index=1))]
        doc_map = {"p1": doc}

        buckets = _partition_places(places, 2, configs, doc_map).buckets

        assert "p1" in buckets[1]
        assert "p1" not in buckets[0]

    def test_flexible_falls_back_when_all_preferred_days_closed(self):
        """If all preferred days are closed, fall back to original preferences."""
        doc = _place("p1", opening_hours=_opening_hours(3))  # Wednesday only
        configs = [_day_config(_MON), _day_config(_TUE)]
        places = [_pref_flexible("p1", DaySlot(day_index=0), DaySlot(day_index=1))]
        doc_map = {"p1": doc}

        buckets = _partition_places(places, 2, configs, doc_map).buckets

        assert "p1" in buckets[0] or "p1" in buckets[1]


def _mock_db():
    return AsyncMock()


def _mock_manager():
    return AsyncMock()


@pytest.mark.unit
class TestOptimizeTrip:
    async def test_two_days_happy_path(self):
        docs = [_place("p1"), _place("p2"), _place("p3"), _place("p4")]

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_single_day_response("p1", "p2")),
            ),
        ):
            result = await optimize_trip(_mock_db(), _mock_manager(), _req())

        assert isinstance(result, MultiDayResponse)
        assert len(result.days) == 2

    async def test_departure_dates_per_day(self):
        docs = [_place("p1"), _place("p2"), _place("p3"), _place("p4")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 10)), _day_config(date(2026, 6, 11))],
                places=[
                    _pref("p1", day_index=0),
                    _pref("p2", day_index=0),
                    _pref("p3", day_index=1),
                    _pref("p4", day_index=1),
                ],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        assert mock_optimize.call_count == 2
        assert mock_optimize.call_args_list[0][0][2].departure_date == date(2026, 6, 10)
        assert mock_optimize.call_args_list[1][0][2].departure_date == date(2026, 6, 11)

    async def test_per_day_hours_forwarded(self):
        docs = [_place("p1"), _place("p2"), _place("p3"), _place("p4")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[
                    DayConfig(date=date(2026, 6, 10), day_start_hour=8, day_end_hour=13),
                    DayConfig(date=date(2026, 6, 11), day_start_hour=14, day_end_hour=21),
                ],
                places=[
                    _pref("p1", day_index=0),
                    _pref("p2", day_index=0),
                    _pref("p3", day_index=1),
                    _pref("p4", day_index=1),
                ],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        first_request = mock_optimize.call_args_list[0][0][2]
        assert first_request.day_start_hour == 8
        assert first_request.day_end_hour == 13

    async def test_day_plan_index_and_date_in_response(self):
        docs = [_place("p1"), _place("p2")]

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_single_day_response("p1")),
            ),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 10)), _day_config(date(2026, 6, 11))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=1)],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert result.days[0].day_index == 0
        assert result.days[0].date == date(2026, 6, 10)
        assert result.days[1].day_index == 1
        assert result.days[1].date == date(2026, 6, 11)

    async def test_skipped_places_appear_in_day_plan(self):
        docs = [_place("p1"), _place("p2"), _place("p3")]
        skipped_response = OptimizeResponse(
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            transport_mode=TransportMode.WALK,
            skipped=[SkippedPlace(place_id="p1", name="P1", reason="TIME_WINDOW_INFEASIBLE")],
        )

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=AsyncMock(return_value=skipped_response)),
        ):
            result = await optimize_trip(
                _mock_db(),
                _mock_manager(),
                _req(places=[_pref("p1", day_index=0), _pref("p2", day_index=0), _pref("p3", day_index=1)]),
            )

        assert any(len(d.skipped) > 0 for d in result.days)

    async def test_per_day_preference_overrides_doc_fields(self):
        docs = [_place("p1", preferred_hour_from=9, preferred_hour_to=17), _place("p2"), _place("p3")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(), _day_config(date(2026, 6, 2))],
                places=[
                    _pref("p1", day_index=0, preferred_hour_from=10, preferred_hour_to=14),
                    _pref("p2", day_index=0),
                    _pref("p3", day_index=1),
                ],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_call = mock_optimize.call_args_list[0]
        day0_docs = day0_call.kwargs.get("docs")
        assert day0_docs is not None
        p1_doc = next(d for d in day0_docs if str(d["_id"]) == "p1")
        assert p1_doc["preferred_hour_from"] == 10
        assert p1_doc["preferred_hour_to"] == 14

    async def test_response_transport_mode_preserved(self):
        docs = [_place("p1"), _place("p2")]

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_single_day_response("p1")),
            ),
        ):
            result = await optimize_trip(_mock_db(), _mock_manager(), _req())

        assert result.transport_mode == TransportMode.WALK

    async def test_matrix_error_propagates_as_502(self):
        docs = [_place("p1"), _place("p2")]

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(side_effect=HTTPException(status_code=502, detail="Matrix error")),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await optimize_trip(
                _mock_db(),
                _mock_manager(),
                _req(places=[_pref("p1", day_index=0), _pref("p2", day_index=0)]),
            )

        assert exc_info.value.status_code == 502

    async def test_day_with_no_places_produces_empty_steps(self):
        docs = [_place("p1"), _place("p2")]

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_single_day_response("p1", "p2")),
            ),
        ):
            req = _req(places=[_pref("p1", day_index=0), _pref("p2", day_index=0)])
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert result.days[1].steps == []


@pytest.mark.unit
class TestOptimizeTripAnchors:
    async def test_single_place_day_routes_through_optimize_route(self):
        """Regression: the removed _build_single_place_plan hardcoded zero travel cost."""
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 10)), _day_config(date(2026, 6, 11))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=1)],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        assert mock_optimize.call_count == 2
        day0_request = mock_optimize.call_args_list[0][0][2]
        assert day0_request.place_ids == ["p1"]

    async def test_travel_to_end_s_propagated_to_day_plan(self):
        docs = [_place("p1"), _place("p2")]
        response = OptimizeResponse(
            steps=[],
            total_travel_time_s=100,
            total_visit_time_min=0,
            total_wait_min=0,
            transport_mode=TransportMode.WALK,
            skipped=[],
            travel_to_end_s=250,
        )

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=AsyncMock(return_value=response)),
        ):
            req = _req(places=[_pref("p1", day_index=0), _pref("p2", day_index=0)])
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert result.days[0].travel_to_end_s == 250

    async def test_per_day_anchor_overrides_trip_level_default(self):
        docs = [_place("p1"), _place("p2"), _place("p3"), _place("p4")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[
                    DayConfig(date=date(2026, 6, 10), start_lat=1.0, start_lng=2.0),
                    _day_config(date(2026, 6, 11)),
                ],
                places=[
                    _pref("p1", day_index=0),
                    _pref("p2", day_index=0),
                    _pref("p3", day_index=1),
                    _pref("p4", day_index=1),
                ],
                start_lat=9.0,
                start_lng=9.0,
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        day1_request = mock_optimize.call_args_list[1][0][2]
        assert (day0_request.start_lat, day0_request.start_lng) == (1.0, 2.0)  # per-day override wins
        assert (day1_request.start_lat, day1_request.start_lng) == (9.0, 9.0)  # falls back to trip-level

    async def test_per_day_end_anchor_overrides_trip_level_default(self):
        docs = [_place("p1"), _place("p2"), _place("p3"), _place("p4")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[
                    DayConfig(date=date(2026, 6, 10), end_lat=3.0, end_lng=4.0),
                    _day_config(date(2026, 6, 11)),
                ],
                places=[
                    _pref("p1", day_index=0),
                    _pref("p2", day_index=0),
                    _pref("p3", day_index=1),
                    _pref("p4", day_index=1),
                ],
                end_lat=9.0,
                end_lng=9.0,
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        day1_request = mock_optimize.call_args_list[1][0][2]
        assert (day0_request.end_lat, day0_request.end_lng) == (3.0, 4.0)  # per-day override wins
        assert (day1_request.end_lat, day1_request.end_lng) == (9.0, 9.0)  # falls back to trip-level

    async def test_no_anchors_set_leaves_request_fields_none(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(places=[_pref("p1", day_index=0), _pref("p2", day_index=0)])
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert day0_request.start_lat is None
        assert day0_request.end_lat is None


def _stay(name: str, check_in: date, check_out: date, *, lat: float = 1.0, lng: float = 2.0) -> AccommodationStay:
    return AccommodationStay(name=name, lat=lat, lng=lng, check_in_date=check_in, check_out_date=check_out)


# 06-12 is the changeover day: START resolves to Tokyo, END resolves to Kyoto.
TOKYO = _stay("Tokyo Hotel", date(2026, 6, 10), date(2026, 6, 12), lat=10.0, lng=20.0)
KYOTO = _stay("Kyoto Hotel", date(2026, 6, 12), date(2026, 6, 14), lat=30.0, lng=40.0)


def _tokyo_with_check_out_by(check_out_by: time) -> AccommodationStay:
    return AccommodationStay(
        name="Tokyo Hotel",
        lat=TOKYO.lat,
        lng=TOKYO.lng,
        check_in_date=date(2026, 6, 10),
        check_out_date=date(2026, 6, 12),
        check_out_by=check_out_by,
    )


@pytest.mark.unit
class TestAccommodationAnchorPrecedence:
    async def test_accommodation_derived_anchors_used_when_no_explicit_dayconfig(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 11))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert (day0_request.start_lat, day0_request.start_lng) == (10.0, 20.0)
        assert (day0_request.end_lat, day0_request.end_lng) == (10.0, 20.0)

    async def test_explicit_dayconfig_anchor_overrides_accommodation(self):
        """Manual override: sleeping at the Tokyo hotel, but this day explicitly starts at the airport."""
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[DayConfig(date=date(2026, 6, 11), start_lat=99.0, start_lng=98.0)],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert (day0_request.start_lat, day0_request.start_lng) == (99.0, 98.0)

    async def test_accommodation_overrides_global_anchor_when_dayconfig_unset(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 11))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                start_lat=1.0,
                start_lng=1.0,
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert (day0_request.start_lat, day0_request.start_lng) == (10.0, 20.0)

    async def test_global_anchor_used_when_no_accommodation_and_no_dayconfig(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 11))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                start_lat=1.0,
                start_lng=2.0,
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert (day0_request.start_lat, day0_request.start_lng) == (1.0, 2.0)

    async def test_no_anchor_anywhere_resolves_to_none(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 11))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert day0_request.start_lat is None
        assert day0_request.end_lat is None


@pytest.mark.unit
class TestIsAccommodationTransitionDay:
    def test_same_stay_on_both_sides_is_not_a_transition(self):
        anchors = DayAccommodationAnchors(start=TOKYO, end=TOKYO)
        assert _is_accommodation_transition_day(anchors) is False

    def test_different_stays_is_a_transition(self):
        anchors = DayAccommodationAnchors(start=TOKYO, end=KYOTO)
        assert _is_accommodation_transition_day(anchors) is True

    def test_missing_start_is_not_a_transition(self):
        assert _is_accommodation_transition_day(DayAccommodationAnchors(start=None, end=KYOTO)) is False

    def test_missing_end_is_not_a_transition(self):
        assert _is_accommodation_transition_day(DayAccommodationAnchors(start=TOKYO, end=None)) is False

    def test_both_none_is_not_a_transition(self):
        assert _is_accommodation_transition_day(DayAccommodationAnchors(start=None, end=None)) is False


def _anchor_matrix(*pairs: tuple[str, str, int]) -> DistanceMatrix:
    """Directed matrix (no auto-reverse) — anchor legs are direction-limited by design."""
    entries = {(o, d): MatrixEntry(o, d, t * 80, t) for o, d, t in pairs}
    return DistanceMatrix(entries, TransportMode.WALK, datetime(2026, 1, 1, tzinfo=UTC))


@pytest.mark.unit
class TestTransitionDaySafety:
    """Regression coverage: an unconditional accommodation END on a changeover day must not be wired through."""

    async def test_transition_day_does_not_inject_accommodation_end_anchor(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert day0_request.end_lat is None
        assert day0_request.end_lng is None

    async def test_transition_day_does_not_inject_accommodation_start_anchor(self):
        """A fixed START also consumes the day's budget via its travel leg — equally dangerous as END."""
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert day0_request.start_lat is None
        assert day0_request.start_lng is None

    async def test_transition_day_explicit_dayconfig_start_override_still_respected(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[DayConfig(date=date(2026, 6, 12), start_lat=11.0, start_lng=12.0)],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert (day0_request.start_lat, day0_request.start_lng) == (11.0, 12.0)

    async def test_transition_day_explicit_global_start_anchor_still_applied(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                start_lat=33.0,
                start_lng=34.0,
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert (day0_request.start_lat, day0_request.start_lng) == (33.0, 34.0)

    async def test_transition_day_explicit_dayconfig_end_override_still_respected(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[DayConfig(date=date(2026, 6, 12), end_lat=77.0, end_lng=78.0)],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert (day0_request.end_lat, day0_request.end_lng) == (77.0, 78.0)

    async def test_transition_day_explicit_global_end_anchor_still_applied(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                end_lat=55.0,
                end_lng=56.0,
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert (day0_request.end_lat, day0_request.end_lng) == (55.0, 56.0)

    async def test_ordinary_day_end_anchor_unaffected_by_transition_day_policy(self):
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 11))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert (day0_request.end_lat, day0_request.end_lng) == (10.0, 20.0)

    async def test_naive_end_anchor_would_have_stranded_a_reachable_place(self):
        """Proves the risk this branch avoids is real: a far-away END as a hard deadline strands reachable places."""
        docs = [_place("p1"), _place("p2")]
        matrix = _anchor_matrix(
            ("p1", "p2", 300),
            ("p2", "p1", 300),
            ("p1", "__end__", 41400),  # 11h30 — a plausible Tokyo-to-Kyoto leg under WALK/DRIVE
            ("p2", "__end__", 41400),
        )

        with (
            patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
        ):
            request = OptimizeRequest(
                place_ids=["p1", "p2"],
                transport_mode=TransportMode.WALK,
                end_lat=KYOTO.lat,
                end_lng=KYOTO.lng,
            )
            result = await solve_single_day(_mock_db(), _mock_manager(), request)

        assert len(result.steps) == 1
        assert len(result.skipped) == 1

    async def test_naive_start_anchor_would_have_stranded_a_reachable_place(self):
        """Symmetric to the END proof: a far-away fixed START consumes the day's budget just as badly."""
        docs = [_place("p1"), _place("p2")]
        matrix = _anchor_matrix(
            ("__start__", "p1", 41400),  # 11h30 — a plausible Tokyo-to-Kyoto leg under WALK/DRIVE
            ("__start__", "p2", 41400),
            ("p1", "p2", 300),
            ("p2", "p1", 300),
        )

        with (
            patch("src.optimizer.solver.service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.service.get_matrix", new=AsyncMock(return_value=(matrix, "OK", None))),
        ):
            request = OptimizeRequest(
                place_ids=["p1", "p2"],
                transport_mode=TransportMode.WALK,
                start_lat=TOKYO.lat,
                start_lng=TOKYO.lng,
            )
            result = await solve_single_day(_mock_db(), _mock_manager(), request)

        assert len(result.steps) == 1
        assert len(result.skipped) == 1


def _transfer_ctx(
    *,
    post_start_s: int = 15 * 3600,
    post_visit_budget_min: int = 360,
    pre_visit_budget_min: int = 0,
    transfer_date: date = date(2026, 6, 12),
) -> TransitionDayContext:
    return TransitionDayContext(
        transfer=TransferBlock(date=transfer_date, departure_time=time(10, 0), arrival_time=time(15, 0)),
        origin=TOKYO,
        destination=KYOTO,
        pre_start_s=9 * 3600,
        pre_end_s=9 * 3600 + pre_visit_budget_min * 60,
        post_start_s=post_start_s,
        post_end_s=post_start_s + post_visit_budget_min * 60,
        pre_visit_budget_min=pre_visit_budget_min,
        post_visit_budget_min=post_visit_budget_min,
    )


@pytest.mark.unit
class TestTransitionSide:
    def test_place_closer_to_destination_is_destination_side(self):
        doc = _place("kyoto_place", lat=KYOTO.lat + 0.1, lng=KYOTO.lng + 0.1)
        assert _transition_side(doc, TOKYO, KYOTO) == "DESTINATION"

    def test_place_closer_to_origin_is_origin_side(self):
        """Behavior inversion vs pre-ADR-17: an origin-side place is a valid PRE candidate, not a rejection."""
        doc = _place("tokyo_place", lat=TOKYO.lat + 0.1, lng=TOKYO.lng + 0.1)
        assert _transition_side(doc, TOKYO, KYOTO) == "ORIGIN"

    def test_exact_tie_resolves_to_origin(self):
        """Same latitude on both sides makes the haversine tie exact and deterministic."""
        origin = _stay("Origin", date(2026, 6, 1), date(2026, 6, 2), lat=0.0, lng=0.0)
        destination = _stay("Destination", date(2026, 6, 2), date(2026, 6, 3), lat=0.0, lng=10.0)
        doc = _place("midpoint", lat=0.0, lng=5.0)
        assert _transition_side(doc, origin, destination) == "ORIGIN"

    def test_missing_coordinates_is_no_coordinates(self):
        doc = {"_id": "no_coords", "name": "Mystery Place"}
        assert _transition_side(doc, TOKYO, KYOTO) == "NO_COORDINATES"


@pytest.mark.unit
class TestPartitionPlacesTransferAware:
    """Direct unit tests of _partition_places with transfer_contexts — see ADR-16/ADR-17."""

    def test_destination_side_auto_place_exceeding_post_budget_is_unassigned_not_force_packed(self):
        ctx = _transfer_ctx(post_visit_budget_min=360)
        doc = _place("big_attraction", lat=KYOTO.lat, lng=KYOTO.lng, visit_min=400)
        configs = [_day_config(date(2026, 6, 12))]

        result = _partition_places([_pref("big_attraction")], 1, configs, {"big_attraction": doc}, {0: ctx})

        assert "big_attraction" not in result.transfer_buckets[0].post
        assert len(result.unassigned) == 1
        assert result.unassigned[0].reason == "CAPACITY_EXCEEDED"
        assert result.pre_solver_skipped_by_day[0] == []

    def test_destination_side_auto_place_within_post_budget_is_assigned(self):
        ctx = _transfer_ctx(post_visit_budget_min=360)
        doc = _place("small_attraction", lat=KYOTO.lat, lng=KYOTO.lng, visit_min=60)
        configs = [_day_config(date(2026, 6, 12))]

        result = _partition_places([_pref("small_attraction")], 1, configs, {"small_attraction": doc}, {0: ctx})

        assert "small_attraction" in result.transfer_buckets[0].post
        assert result.unassigned == []

    def test_origin_side_auto_place_exceeding_pre_budget_is_unassigned_with_pre_reason(self):
        ctx = _transfer_ctx(pre_visit_budget_min=60)
        doc = _place("big_landmark", lat=TOKYO.lat, lng=TOKYO.lng, visit_min=90)
        configs = [_day_config(date(2026, 6, 12))]

        result = _partition_places([_pref("big_landmark")], 1, configs, {"big_landmark": doc}, {0: ctx})

        assert "big_landmark" not in result.transfer_buckets[0].pre
        assert len(result.unassigned) == 1
        assert result.unassigned[0].reason == "PRE_TRANSFER_CAPACITY_EXCEEDED"

    def test_origin_side_pinned_place_goes_to_pre_bucket(self):
        """Behavior inversion vs pre-ADR-17: a pinned Tokyo place is now a valid PRE candidate."""
        ctx = _transfer_ctx()
        doc = _place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng)
        configs = [_day_config(date(2026, 6, 12))]

        result = _partition_places([_pref("tokyo_tower", day_index=0)], 1, configs, {"tokyo_tower": doc}, {0: ctx})

        assert "tokyo_tower" in result.transfer_buckets[0].pre
        assert result.unassigned == []
        assert result.pre_solver_skipped_by_day[0] == []

    def test_destination_side_pinned_place_goes_to_post_bucket(self):
        ctx = _transfer_ctx()
        doc = _place("kyoto_shrine", lat=KYOTO.lat, lng=KYOTO.lng)
        configs = [_day_config(date(2026, 6, 12))]

        result = _partition_places([_pref("kyoto_shrine", day_index=0)], 1, configs, {"kyoto_shrine": doc}, {0: ctx})

        assert "kyoto_shrine" in result.transfer_buckets[0].post

    def test_pinned_place_without_coordinates_is_skipped_as_no_coordinates(self):
        ctx = _transfer_ctx()
        doc = {"_id": "mystery", "name": "Mystery Place"}
        configs = [_day_config(date(2026, 6, 12))]

        result = _partition_places([_pref("mystery", day_index=0)], 1, configs, {"mystery": doc}, {0: ctx})

        assert result.pre_solver_skipped_by_day[0][0].reason == "NO_COORDINATES"

    def test_rejected_pinned_place_does_not_consume_either_segment_budget(self):
        """A NO_COORDINATES pinned place is rejected before bucketing — it must not touch PRE or POST fill."""
        ctx = _transfer_ctx(post_visit_budget_min=60)
        rejected_pinned = {"_id": "mystery", "name": "Mystery Place", "visit_duration_min": 60}
        auto_kyoto_place = _place("kyoto_shrine", lat=KYOTO.lat, lng=KYOTO.lng, visit_min=60)
        configs = [_day_config(date(2026, 6, 12))]
        doc_map = {"mystery": rejected_pinned, "kyoto_shrine": auto_kyoto_place}

        result = _partition_places([_pref("mystery", day_index=0), _pref("kyoto_shrine")], 1, configs, doc_map, {0: ctx})

        assert "kyoto_shrine" in result.transfer_buckets[0].post
        assert result.unassigned == []
        assert result.pre_solver_skipped_by_day[0][0].place_id == "mystery"

    def test_flexible_place_filters_admissible_candidates_before_picking_best_day(self):
        """Regression: a roomy-looking but already-exhausted day must not win over an admissible one."""
        transfer_ctx = _transfer_ctx(pre_visit_budget_min=1000)
        configs = [_day_config(date(2026, 6, 12)), _day_config(date(2026, 6, 13))]
        exhausting_pinned = _place("tokyo_landmark", lat=TOKYO.lat, lng=TOKYO.lng, visit_min=990)
        doc = _place("tokyo_place", lat=TOKYO.lat, lng=TOKYO.lng, visit_min=30)
        doc_map = {"tokyo_landmark": exhausting_pinned, "tokyo_place": doc}

        result = _partition_places(
            [
                _pref("tokyo_landmark", day_index=0),
                _pref_flexible("tokyo_place", DaySlot(day_index=0), DaySlot(day_index=1)),
            ],
            2,
            configs,
            doc_map,
            {0: transfer_ctx},
        )

        assert "tokyo_place" in result.buckets[1]
        assert "tokyo_place" not in result.transfer_buckets[0].pre
        assert result.unassigned == []

    def test_non_transfer_day_capacity_remains_ranking_only_heuristic(self):
        """No transfer_contexts entry: today's unconstrained behavior, unaffected by this feature."""
        configs = [_day_config(date(2026, 6, 12))]
        doc = _place("any_place", visit_min=10_000)  # absurdly large — would exceed any real capacity

        result = _partition_places([_pref("any_place")], 1, configs, {"any_place": doc}, None)

        assert "any_place" in result.buckets[0]
        assert result.unassigned == []


@pytest.mark.unit
class TestOptimizeTripTransfer:
    def _stay_with_check_in_from(self, *, check_in_from: time) -> AccommodationStay:
        return AccommodationStay(
            name="Kyoto Hotel",
            lat=KYOTO.lat,
            lng=KYOTO.lng,
            check_in_date=date(2026, 6, 12),
            check_out_date=date(2026, 6, 14),
            check_in_from=check_in_from,
        )

    async def test_start_and_end_both_resolve_to_destination_hotel(self):
        docs = [_place("p1", lat=KYOTO.lat, lng=KYOTO.lng), _place("p2", lat=KYOTO.lat, lng=KYOTO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(10, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert (day0_request.start_lat, day0_request.start_lng) == (KYOTO.lat, KYOTO.lng)
        assert (day0_request.end_lat, day0_request.end_lng) == (KYOTO.lat, KYOTO.lng)
        assert result.days[0].transfer is not None
        assert result.days[0].transfer.origin.name == "Tokyo Hotel"
        assert result.days[0].transfer.destination.name == "Kyoto Hotel"
        assert result.days[0].transfer.duration_s == 18000

    async def test_arrival_before_check_in_from_waits_until_check_in(self):
        """arrival 13:17 + check-in 15:00 -> first activity not before 15:00."""
        kyoto = self._stay_with_check_in_from(check_in_from=time(15, 0))
        docs = [_place("p1", lat=KYOTO.lat, lng=KYOTO.lng), _place("p2", lat=KYOTO.lat, lng=KYOTO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, kyoto],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(10, 0), arrival_time=time(13, 17))],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert day0_request.day_start_time == time(15, 0)

    async def test_arrival_after_check_in_from_never_earlier_than_arrival(self):
        """arrival 16:20 + check-in 15:00 -> first activity not before 16:20 (never faked earlier than arrival)."""
        kyoto = self._stay_with_check_in_from(check_in_from=time(15, 0))
        docs = [_place("p1", lat=KYOTO.lat, lng=KYOTO.lng), _place("p2", lat=KYOTO.lat, lng=KYOTO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, kyoto],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(10, 0), arrival_time=time(16, 20))],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert day0_request.day_start_time == time(16, 20)

    async def test_no_transition_day_transfer_still_suppresses_both_anchors(self):
        """Backward compatibility: transition day without a transfer keeps exact ADR-15 behavior."""
        docs = [_place("p1"), _place("p2")]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1", "p2"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        day0_request = mock_optimize.call_args_list[0][0][2]
        assert day0_request.start_lat is None
        assert day0_request.end_lat is None
        assert result.days[0].transfer is None

    async def test_arrival_after_day_end_skips_solver_and_marks_pinned_place_window_infeasible(self):
        """arrival 22:15 vs day_end 21:00 -> no viable window; pinned place must not vanish, just be skipped."""
        docs = [_place("p1", lat=KYOTO.lat, lng=KYOTO.lng), _place("p2", lat=KYOTO.lat, lng=KYOTO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("p1"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12), day_end_hour=21)],
                places=[_pref("p1", day_index=0), _pref("p2", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(20, 0), arrival_time=time(22, 15))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert mock_optimize.call_count == 0
        assert result.days[0].steps == []
        assert result.days[0].transfer is not None
        assert len(result.days[0].skipped) == 2
        assert all(s.reason == "TRANSFER_WINDOW_INFEASIBLE" for s in result.days[0].skipped)

    async def test_transfer_day_with_no_attractions_is_not_degenerate(self):
        """A transfer-only day must still show the transfer and two route_segments, not collapse to empty."""
        docs = [_place("p1", lat=TOKYO.lat, lng=TOKYO.lng), _place("p2", lat=TOKYO.lat, lng=TOKYO.lng)]

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(side_effect=AssertionError("optimize_route must not be called")),
            ),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("p1"), _pref("p2")],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(9, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert result.days[0].steps == []
        assert result.days[0].transfer is not None
        assert [s.kind for s in result.days[0].route_segments] == ["PRE_TRANSFER", "POST_TRANSFER"]
        assert result.days[0].route_segments[0].steps == []
        assert result.days[0].route_segments[1].steps == []
        assert any(u.reason == "PRE_TRANSFER_CAPACITY_EXCEEDED" for u in result.unassigned)

    async def test_pinned_places_merge_skip_sources_across_both_segments(self):
        """DayPlan.skipped is a deliberate aggregate of independent PRE/POST sources — see ADR-17."""
        docs = [
            _place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng),
            _place("kyoto_place", lat=KYOTO.lat, lng=KYOTO.lng),
        ]
        pre_response = _single_day_response("tokyo_tower")
        post_response = OptimizeResponse(
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            transport_mode=TransportMode.WALK,
            skipped=[SkippedPlace(place_id="kyoto_place", name="Kyoto Place", reason="TIME_WINDOW_INFEASIBLE")],
        )
        mock_optimize = AsyncMock(side_effect=[pre_response, post_response])

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("tokyo_tower", day_index=0), _pref("kyoto_place", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(10, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert mock_optimize.call_count == 2
        reasons = {s.place_id: s.reason for s in result.days[0].skipped}
        assert reasons["kyoto_place"] == "TIME_WINDOW_INFEASIBLE"
        assert "tokyo_tower" not in reasons
        assert result.days[0].route_segments[0].kind == "PRE_TRANSFER"
        assert [s.place_id for s in result.days[0].route_segments[0].steps] == ["tokyo_tower"]
        assert result.days[0].route_segments[1].kind == "POST_TRANSFER"
        assert result.days[0].route_segments[1].skipped[0].place_id == "kyoto_place"


@pytest.mark.unit
class TestOptimizeTripPreTransferSegment:
    """PRE solver call: origin-anchored, window bounded by departure/check_out_by/day_end — see ADR-17."""

    async def test_pre_segment_start_and_end_both_resolve_to_origin_hotel(self):
        docs = [_place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("tokyo_tower"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("tokyo_tower", day_index=0), _pref("filler", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        assert mock_optimize.call_count == 1
        pre_request = mock_optimize.call_args_list[0][0][2]
        assert (pre_request.start_lat, pre_request.start_lng) == (TOKYO.lat, TOKYO.lng)
        assert (pre_request.end_lat, pre_request.end_lng) == (TOKYO.lat, TOKYO.lng)

    async def test_pre_segment_day_end_time_equals_transfer_departure_when_no_checkout_by(self):
        docs = [_place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("tokyo_tower"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("tokyo_tower", day_index=0), _pref("filler", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        pre_request = mock_optimize.call_args_list[0][0][2]
        assert pre_request.day_end_time == time(11, 0)

    async def test_pre_segment_day_end_time_equals_checkout_by_when_earlier_than_departure(self):
        tokyo = _tokyo_with_check_out_by(time(10, 0))
        docs = [_place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("tokyo_tower"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("tokyo_tower", day_index=0), _pref("filler", day_index=0)],
                accommodations=[tokyo, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        pre_request = mock_optimize.call_args_list[0][0][2]
        assert pre_request.day_end_time == time(10, 0)

    async def test_pre_segment_day_end_time_equals_departure_when_checkout_by_later(self):
        tokyo = _tokyo_with_check_out_by(time(14, 0))
        docs = [_place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("tokyo_tower"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("tokyo_tower", day_index=0), _pref("filler", day_index=0)],
                accommodations=[tokyo, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)

        pre_request = mock_optimize.call_args_list[0][0][2]
        assert pre_request.day_end_time == time(11, 0)

    async def test_pre_segment_end_bounded_by_configured_day_end_even_when_transfer_departs_later(self):
        """Regression: DayConfig.day_end limits PRE sightseeing even when the transfer departs later."""
        docs = [_place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("tokyo_tower"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12), day_start_hour=9, day_end_hour=18)],
                places=[_pref("tokyo_tower", day_index=0), _pref("filler", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(23, 0), arrival_time=time(23, 30))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        pre_request = mock_optimize.call_args_list[0][0][2]
        assert pre_request.day_end_time == time(18, 0)
        assert result.days[0].transfer is not None
        assert result.days[0].transfer.departure_time == time(23, 0)

    async def test_pre_segment_request_never_conflicts_day_end_hour_24_validator(self):
        """Regression: day_end_hour=24 must never be combined with an explicit PRE day_end_time."""
        docs = [_place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("tokyo_tower"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12), day_end_hour=24)],
                places=[_pref("tokyo_tower", day_index=0), _pref("filler", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            await optimize_trip(_mock_db(), _mock_manager(), req)  # must not raise ValidationError

        pre_request = mock_optimize.call_args_list[0][0][2]
        assert not (pre_request.day_end_hour == 24 and pre_request.day_end_time is not None)
        assert pre_request.day_end_time == time(11, 0)

    async def test_pre_segment_not_called_when_departure_equals_day_start(self):
        docs = [
            _place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng),
            _place("kyoto_place", lat=KYOTO.lat, lng=KYOTO.lng),
        ]
        mock_optimize = AsyncMock(return_value=_single_day_response("kyoto_place"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12), day_start_hour=9)],
                places=[_pref("tokyo_tower", day_index=0), _pref("kyoto_place", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(9, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert mock_optimize.call_count == 1  # POST only — PRE budget is 0
        called_request = mock_optimize.call_args_list[0][0][2]
        assert (called_request.start_lat, called_request.start_lng) == (KYOTO.lat, KYOTO.lng)
        assert result.days[0].route_segments[0].kind == "PRE_TRANSFER"
        assert result.days[0].route_segments[0].steps == []
        assert result.days[0].route_segments[0].skipped[0].reason == "PRE_TRANSFER_WINDOW_INFEASIBLE"

    async def test_pre_segment_not_called_when_no_origin_side_places(self):
        docs = [_place("kyoto_place", lat=KYOTO.lat, lng=KYOTO.lng)]
        mock_optimize = AsyncMock(return_value=_single_day_response("kyoto_place"))

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("kyoto_place", day_index=0), _pref("filler", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert mock_optimize.call_count == 1  # POST only — PRE bucket is empty
        assert result.days[0].route_segments[0].kind == "PRE_TRANSFER"
        assert result.days[0].route_segments[0].steps == []
        assert result.days[0].route_segments[0].skipped == []


@pytest.mark.unit
class TestOptimizeTripFullTransitionDay:
    """PRE + TRANSFER + POST end-to-end scenario — see ADR-17 motivating example."""

    async def _run(self, *, check_out_by: time | None) -> MultiDayResponse:
        tokyo = AccommodationStay(
            name="Tokyo Hotel",
            lat=TOKYO.lat,
            lng=TOKYO.lng,
            check_in_date=date(2026, 6, 10),
            check_out_date=date(2026, 6, 12),
            check_out_by=check_out_by,
        )
        kyoto = AccommodationStay(
            name="Kyoto Hotel",
            lat=KYOTO.lat,
            lng=KYOTO.lng,
            check_in_date=date(2026, 6, 12),
            check_out_date=date(2026, 6, 14),
            check_in_from=time(15, 0),
        )
        docs = [
            _place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng),
            _place("fushimi_inari", lat=KYOTO.lat, lng=KYOTO.lng),
        ]
        mock_optimize = AsyncMock(side_effect=[_single_day_response("tokyo_tower"), _single_day_response("fushimi_inari")])

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12), day_start_hour=9, day_end_hour=21)],
                places=[_pref("tokyo_tower", day_index=0), _pref("fushimi_inari", day_index=0)],
                accommodations=[tokyo, kyoto],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert mock_optimize.call_count == 2
        return result

    async def test_check_out_by_none_variant(self):
        result = await self._run(check_out_by=None)
        day = result.days[0]
        assert [s.kind for s in day.route_segments] == ["PRE_TRANSFER", "POST_TRANSFER"]
        assert [s.place_id for s in day.route_segments[0].steps] == ["tokyo_tower"]
        assert [s.place_id for s in day.route_segments[1].steps] == ["fushimi_inari"]
        assert day.transfer is not None
        assert day.transfer.departure_time == time(11, 0)
        assert day.transfer.arrival_time == time(15, 0)
        all_place_ids = {s.place_id for seg in day.route_segments for s in seg.steps}
        all_place_ids |= {s.place_id for s in day.skipped}
        all_place_ids |= {u.place_id for u in result.unassigned}
        assert all_place_ids == {"tokyo_tower", "fushimi_inari"}

    async def test_check_out_by_before_departure_variant(self):
        result = await self._run(check_out_by=time(10, 0))
        day = result.days[0]
        assert [s.place_id for s in day.route_segments[0].steps] == ["tokyo_tower"]
        assert [s.place_id for s in day.route_segments[1].steps] == ["fushimi_inari"]


@pytest.mark.unit
class TestOptimizeTripIndependentSegmentFailure:
    async def test_pre_infeasible_post_still_succeeds(self):
        docs = [
            _place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng),
            _place("fushimi_inari", lat=KYOTO.lat, lng=KYOTO.lng),
        ]
        pre_response = OptimizeResponse(
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            transport_mode=TransportMode.WALK,
            skipped=[SkippedPlace(place_id="tokyo_tower", name="Tokyo Tower", reason="TIME_WINDOW_INFEASIBLE")],
        )
        post_response = _single_day_response("fushimi_inari")
        mock_optimize = AsyncMock(side_effect=[pre_response, post_response])

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("tokyo_tower", day_index=0), _pref("fushimi_inari", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert result.days[0].route_segments[0].steps == []
        assert result.days[0].route_segments[0].skipped[0].reason == "TIME_WINDOW_INFEASIBLE"
        assert [s.place_id for s in result.days[0].route_segments[1].steps] == ["fushimi_inari"]

    async def test_post_infeasible_pre_still_succeeds(self):
        docs = [
            _place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng),
            _place("fushimi_inari", lat=KYOTO.lat, lng=KYOTO.lng),
        ]
        pre_response = _single_day_response("tokyo_tower")
        post_response = OptimizeResponse(
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            transport_mode=TransportMode.WALK,
            skipped=[SkippedPlace(place_id="fushimi_inari", name="Fushimi Inari", reason="TIME_WINDOW_INFEASIBLE")],
        )
        mock_optimize = AsyncMock(side_effect=[pre_response, post_response])

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("tokyo_tower", day_index=0), _pref("fushimi_inari", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert [s.place_id for s in result.days[0].route_segments[0].steps] == ["tokyo_tower"]
        assert result.days[0].route_segments[1].steps == []
        assert result.days[0].route_segments[1].skipped[0].reason == "TIME_WINDOW_INFEASIBLE"


@pytest.mark.unit
class TestOptimizeTripTransitionDayTotals:
    """DayPlan top-level fields are a compatibility projection of route_segments[1] — see ADR-17."""

    async def test_day_plan_steps_and_totals_are_post_segment_projection(self):
        docs = [
            _place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng),
            _place("fushimi_inari", lat=KYOTO.lat, lng=KYOTO.lng),
        ]
        mock_optimize = AsyncMock(side_effect=[_single_day_response("tokyo_tower"), _single_day_response("fushimi_inari")])

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("tokyo_tower", day_index=0), _pref("fushimi_inari", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        day = result.days[0]
        post_segment = day.route_segments[1]
        assert post_segment.kind == "POST_TRANSFER"
        assert day.steps == post_segment.steps
        assert day.total_travel_time_s == post_segment.total_travel_time_s
        assert day.total_visit_time_min == post_segment.total_visit_time_min
        assert day.total_wait_min == post_segment.total_wait_min
        assert day.travel_to_end_s == post_segment.travel_to_end_s

    async def test_no_place_has_contradictory_outcome_across_visited_skipped_unassigned(self):
        """Regression: a union-of-outcomes check alone would miss a contradictory double-appearance."""
        docs = [
            _place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng),
            _place("fushimi_inari", lat=KYOTO.lat, lng=KYOTO.lng),
            {"_id": "mystery_place", "name": "Mystery Place", "visit_duration_min": 30},
            _place("overbooked_landmark", lat=TOKYO.lat, lng=TOKYO.lng, visit_min=10_000),
        ]
        mock_optimize = AsyncMock(side_effect=[_single_day_response("tokyo_tower"), _single_day_response("fushimi_inari")])

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[
                    _pref("tokyo_tower", day_index=0),
                    _pref("fushimi_inari", day_index=0),
                    _pref("mystery_place", day_index=0),
                    _pref("overbooked_landmark"),
                ],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        day = result.days[0]
        visited_ids = {step.place_id for seg in day.route_segments for step in seg.steps}
        skipped_ids = {s.place_id for s in day.skipped}
        unassigned_ids = {u.place_id for u in result.unassigned}

        assert visited_ids == {"tokyo_tower", "fushimi_inari"}
        assert skipped_ids == {"mystery_place"}
        assert unassigned_ids == {"overbooked_landmark"}
        assert visited_ids.isdisjoint(skipped_ids)
        assert visited_ids.isdisjoint(unassigned_ids)
        assert skipped_ids.isdisjoint(unassigned_ids)

    async def test_route_segments_always_has_exactly_two_entries_when_transfer_present(self):
        """Transfer-only day with no resolvable places still gets [PRE_TRANSFER, POST_TRANSFER], not []."""
        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=[])),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(side_effect=AssertionError("optimize_route must not be called")),
            ),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("ghost1"), _pref("ghost2")],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        assert [s.kind for s in result.days[0].route_segments] == ["PRE_TRANSFER", "POST_TRANSFER"]
        assert result.days[0].route_segments[0].steps == []
        assert result.days[0].route_segments[1].steps == []
        assert len(result.unassigned) == 2

    async def test_transfer_duration_not_double_counted_in_either_segment_total(self):
        docs = [
            _place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng),
            _place("fushimi_inari", lat=KYOTO.lat, lng=KYOTO.lng),
        ]
        pre_response = OptimizeResponse(
            steps=[],
            total_travel_time_s=100,
            total_visit_time_min=30,
            total_wait_min=0,
            transport_mode=TransportMode.WALK,
            skipped=[],
        )
        post_response = OptimizeResponse(
            steps=[],
            total_travel_time_s=200,
            total_visit_time_min=30,
            total_wait_min=0,
            transport_mode=TransportMode.WALK,
            skipped=[],
        )
        mock_optimize = AsyncMock(side_effect=[pre_response, post_response])

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("tokyo_tower", day_index=0), _pref("fushimi_inari", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        day = result.days[0]
        assert day.transfer.duration_s == 14400
        assert day.route_segments[0].total_travel_time_s == 100
        assert day.route_segments[1].total_travel_time_s == 200
        assert day.total_travel_time_s == 200

    async def test_route_segments_travel_to_end_s_independent_per_segment(self):
        docs = [
            _place("tokyo_tower", lat=TOKYO.lat, lng=TOKYO.lng),
            _place("fushimi_inari", lat=KYOTO.lat, lng=KYOTO.lng),
        ]
        pre_response = OptimizeResponse(
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            transport_mode=TransportMode.WALK,
            skipped=[],
            travel_to_end_s=500,
        )
        post_response = OptimizeResponse(
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            transport_mode=TransportMode.WALK,
            skipped=[],
            travel_to_end_s=900,
        )
        mock_optimize = AsyncMock(side_effect=[pre_response, post_response])

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch("src.optimizer.solver.multi_day_service.optimize_route", new=mock_optimize),
        ):
            req = _req(
                days=[_day_config(date(2026, 6, 12))],
                places=[_pref("tokyo_tower", day_index=0), _pref("fushimi_inari", day_index=0)],
                accommodations=[TOKYO, KYOTO],
                transfers=[TransferBlock(date=date(2026, 6, 12), departure_time=time(11, 0), arrival_time=time(15, 0))],
            )
            result = await optimize_trip(_mock_db(), _mock_manager(), req)

        day = result.days[0]
        assert day.route_segments[0].travel_to_end_s == 500
        assert day.route_segments[1].travel_to_end_s == 900
        assert day.travel_to_end_s == 900
