"""Unit tests for the multi-day trip optimizer service."""

from __future__ import annotations

from datetime import date, time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.optimizer.matrix.models import TransportMode
from src.optimizer.solver.models import (
    DayConfig,
    DaySlot,
    MultiDayRequest,
    MultiDayResponse,
    OptimizeResponse,
    PlaceDayPreference,
    RouteStep,
    SkippedPlace,
)
from src.optimizer.solver.multi_day_service import _open_day_indices, _partition_places, optimize_trip


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


def _opening_hours(*google_days: int) -> dict:
    """Build a minimal opening_hours dict with periods for the given Google weekday numbers."""
    return {
        "periods": [{"open": {"day": d, "hour": 9}, "close": {"day": d, "hour": 17}} for d in google_days]
    }


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
