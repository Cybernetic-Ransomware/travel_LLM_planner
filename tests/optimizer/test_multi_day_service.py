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
    _is_accommodation_transition_day,
    _open_day_indices,
    _partition_places,
    optimize_trip,
)
from src.optimizer.solver.service import optimize_route as solve_single_day


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

        buckets = _partition_places(places, 2, configs, doc_map)

        assert "p1" in buckets[0]
        assert "p2" in buckets[1]

    def test_auto_assign_distributes_across_days(self):
        places = [_pref("p1"), _pref("p2"), _pref("p3"), _pref("p4")]
        configs = [_day_config(), _day_config(date(2026, 6, 2))]
        doc_map = {f"p{i}": _place(f"p{i}") for i in range(1, 5)}

        buckets = _partition_places(places, 2, configs, doc_map)

        assert sum(len(v) for v in buckets.values()) == 4
        assert all(len(buckets[i]) > 0 for i in range(2))

    def test_single_day_gets_all_auto_places(self):
        places = [_pref("p1"), _pref("p2")]
        configs = [_day_config()]
        doc_map = {"p1": _place("p1"), "p2": _place("p2")}

        buckets = _partition_places(places, 1, configs, doc_map)

        assert set(buckets[0]) == {"p1", "p2"}

    def test_more_days_than_places_leaves_some_days_empty(self):
        places = [_pref("p1"), _pref("p2")]
        configs = [_day_config(date(2026, 6, d)) for d in range(1, 5)]
        doc_map = {"p1": _place("p1"), "p2": _place("p2")}

        buckets = _partition_places(places, 4, configs, doc_map)

        assert sum(len(v) for v in buckets.values()) == 2

    def test_mixed_pinned_and_auto_assignment(self):
        places = [_pref("p1", day_index=0), _pref("p2"), _pref("p3")]
        configs = [_day_config(), _day_config(date(2026, 6, 2))]
        doc_map = {f"p{i}": _place(f"p{i}") for i in range(1, 4)}

        buckets = _partition_places(places, 2, configs, doc_map)

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

        buckets = _partition_places(places, 2, configs, doc_map)

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

        buckets = _partition_places(places, 2, self._configs, doc_map)

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

        buckets = _partition_places(places, 2, self._configs, doc_map)

        assert "m1" in buckets[0]
        assert "o1" in buckets[1]

    def test_equal_priorities_preserve_input_order(self):
        """Regression: docs without priority partition exactly as before (stable sort)."""
        places = [_pref("p1"), _pref("p2")]
        doc_map = {
            "p1": _place("p1", visit_min=150),
            "p2": _place("p2", visit_min=150),
        }

        buckets = _partition_places(places, 2, self._configs, doc_map)

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

        buckets = _partition_places(places, 2, configs, doc_map)

        assert "museum" in buckets[1], "museum should be assigned to Tuesday (day index 1)"
        assert "museum" not in buckets[0]

    def test_flexible_place_skips_closed_day(self):
        """Flexible place prefers day 0 and day 1; closed on Monday → should go to Tuesday."""
        doc = _place("p1", opening_hours=_opening_hours(2))  # Tuesday only
        configs = [_day_config(_MON), _day_config(_TUE)]
        places = [_pref_flexible("p1", DaySlot(day_index=0), DaySlot(day_index=1))]
        doc_map = {"p1": doc}

        buckets = _partition_places(places, 2, configs, doc_map)

        assert "p1" in buckets[1]
        assert "p1" not in buckets[0]

    def test_flexible_falls_back_when_all_preferred_days_closed(self):
        """If all preferred days are closed, fall back to original preferences."""
        doc = _place("p1", opening_hours=_opening_hours(3))  # Wednesday only
        configs = [_day_config(_MON), _day_config(_TUE)]
        places = [_pref_flexible("p1", DaySlot(day_index=0), DaySlot(day_index=1))]
        doc_map = {"p1": doc}

        buckets = _partition_places(places, 2, configs, doc_map)

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
