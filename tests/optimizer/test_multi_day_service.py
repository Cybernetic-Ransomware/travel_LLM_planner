"""Unit tests for the multi-day trip optimizer service."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.optimizer.matrix.models import DistanceMatrix, MatrixEntry, TransportMode
from src.optimizer.solver.models import (
    DayConfig,
    MultiDayRequest,
    MultiDayResponse,
    OptimizeResponse,
    PlaceDayPreference,
    RouteStep,
    SkippedPlace,
)
from src.optimizer.solver.multi_day_service import _partition_places, optimize_trip

_NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _day_config(d: date = date(2026, 6, 1), **kwargs) -> DayConfig:
    return DayConfig(date=d, **kwargs)


def _pref(place_id: str, *, day_index: int | None = None, **kwargs) -> PlaceDayPreference:
    return PlaceDayPreference(place_id=place_id, day_index=day_index, **kwargs)


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


@pytest.mark.unit
class TestOptimizeTrip:
    async def test_two_days_happy_path(self, test_db, google_routes_manager):
        docs = [_place("p1"), _place("p2"), _place("p3"), _place("p4")]

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_single_day_response("p1", "p2")),
            ),
        ):
            result = await optimize_trip(test_db, google_routes_manager, _req())

        assert isinstance(result, MultiDayResponse)
        assert len(result.days) == 2

    async def test_departure_dates_per_day(self, test_db, google_routes_manager):
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
            await optimize_trip(test_db, google_routes_manager, req)

        assert mock_optimize.call_count == 2
        assert mock_optimize.call_args_list[0][0][2].departure_date == date(2026, 6, 10)
        assert mock_optimize.call_args_list[1][0][2].departure_date == date(2026, 6, 11)

    async def test_per_day_hours_forwarded(self, test_db, google_routes_manager):
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
            await optimize_trip(test_db, google_routes_manager, req)

        first_request = mock_optimize.call_args_list[0][0][2]
        assert first_request.day_start_hour == 8
        assert first_request.day_end_hour == 13

    async def test_day_plan_index_and_date_in_response(self, test_db, google_routes_manager):
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
            result = await optimize_trip(test_db, google_routes_manager, req)

        assert result.days[0].day_index == 0
        assert result.days[0].date == date(2026, 6, 10)
        assert result.days[1].day_index == 1
        assert result.days[1].date == date(2026, 6, 11)

    async def test_skipped_places_appear_in_day_plan(self, test_db, google_routes_manager):
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
                test_db,
                google_routes_manager,
                _req(places=[_pref("p1", day_index=0), _pref("p2", day_index=0), _pref("p3", day_index=1)]),
            )

        assert any(len(d.skipped) > 0 for d in result.days)

    async def test_per_day_preference_overrides_doc_fields(self, test_db, google_routes_manager):
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
            await optimize_trip(test_db, google_routes_manager, req)

        day0_call = mock_optimize.call_args_list[0]
        day0_docs = day0_call.kwargs.get("docs")
        assert day0_docs is not None
        p1_doc = next(d for d in day0_docs if str(d["_id"]) == "p1")
        assert p1_doc["preferred_hour_from"] == 10
        assert p1_doc["preferred_hour_to"] == 14

    async def test_response_transport_mode_preserved(self, test_db, google_routes_manager):
        docs = [_place("p1"), _place("p2")]

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_single_day_response("p1")),
            ),
        ):
            result = await optimize_trip(test_db, google_routes_manager, _req())

        assert result.transport_mode == TransportMode.WALK

    async def test_matrix_error_propagates_as_502(self, test_db, google_routes_manager):
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
                test_db,
                google_routes_manager,
                _req(places=[_pref("p1", day_index=0), _pref("p2", day_index=0)]),
            )

        assert exc_info.value.status_code == 502

    async def test_day_with_no_places_produces_empty_steps(self, test_db, google_routes_manager):
        docs = [_place("p1"), _place("p2")]

        with (
            patch("src.optimizer.solver.multi_day_service.fetch_places_by_ids", new=AsyncMock(return_value=docs)),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_single_day_response("p1", "p2")),
            ),
        ):
            req = _req(places=[_pref("p1", day_index=0), _pref("p2", day_index=0)])
            result = await optimize_trip(test_db, google_routes_manager, req)

        assert result.days[1].steps == []
