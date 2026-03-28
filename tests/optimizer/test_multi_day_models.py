"""Unit tests for multi-day optimizer request/response models."""

from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from src.optimizer.matrix.models import TransportMode
from src.optimizer.solver.models import (
    DayConfig,
    DayPlan,
    DaySlot,
    MultiDayRequest,
    MultiDayResponse,
    PlaceDayPreference,
    RouteStep,
    SkippedPlace,
)


def _day_config(**kwargs) -> DayConfig:
    defaults: dict = {"date": date(2026, 6, 1)}
    return DayConfig(**{**defaults, **kwargs})


def _slot(day_index: int = 0, **kwargs) -> DaySlot:
    return DaySlot(day_index=day_index, **kwargs)


def _pref(place_id: str = "p1", day_preferences: list[DaySlot] | None = None) -> PlaceDayPreference:
    return PlaceDayPreference(place_id=place_id, day_preferences=day_preferences or [])


def _req(**kwargs) -> MultiDayRequest:
    defaults: dict = {
        "days": [_day_config(), _day_config(date=date(2026, 6, 2))],
        "places": [_pref("p1"), _pref("p2")],
        "transport_mode": TransportMode.WALK,
    }
    return MultiDayRequest(**{**defaults, **kwargs})


@pytest.mark.unit
class TestDaySlot:
    def test_valid_slot_with_all_fields(self):
        slot = DaySlot(day_index=1, preferred_hour_from=14, preferred_hour_to=16)
        assert slot.day_index == 1
        assert slot.preferred_hour_from == 14
        assert slot.preferred_hour_to == 16

    def test_negative_day_index_raises(self):
        with pytest.raises(ValidationError):
            DaySlot(day_index=-1)


@pytest.mark.unit
class TestPlaceDayPreference:
    def test_auto_assignment_when_no_day_preferences(self):
        pref = PlaceDayPreference(place_id="abc123")
        assert pref.place_id == "abc123"
        assert pref.day_preferences == []

    def test_pinned_with_single_day_preference(self):
        pref = PlaceDayPreference(place_id="p1", day_preferences=[_slot(2)])
        assert len(pref.day_preferences) == 1
        assert pref.day_preferences[0].day_index == 2

    def test_flexible_with_multiple_day_preferences(self):
        pref = PlaceDayPreference(
            place_id="p1",
            day_preferences=[
                _slot(0, preferred_hour_from=14, preferred_hour_to=16),
                _slot(2, preferred_hour_from=10, preferred_hour_to=12),
            ],
        )
        assert len(pref.day_preferences) == 2

    def test_negative_day_index_in_slot_raises(self):
        with pytest.raises(ValidationError):
            PlaceDayPreference(place_id="p1", day_preferences=[DaySlot(day_index=-1)])


@pytest.mark.unit
class TestDayConfig:
    def test_defaults_applied(self):
        cfg = DayConfig(date=date(2026, 6, 1))
        assert cfg.day_start_hour == 9
        assert cfg.day_end_hour == 21

    def test_custom_hours(self):
        cfg = DayConfig(date=date(2026, 6, 1), day_start_hour=10, day_end_hour=18)
        assert cfg.day_start_hour == 10
        assert cfg.day_end_hour == 18

    def test_start_greater_than_end_raises(self):
        with pytest.raises(ValidationError, match="day_start_hour"):
            DayConfig(date=date(2026, 6, 1), day_start_hour=18, day_end_hour=10)

    def test_start_equal_to_end_raises(self):
        with pytest.raises(ValidationError, match="day_start_hour"):
            DayConfig(date=date(2026, 6, 1), day_start_hour=9, day_end_hour=9)


@pytest.mark.unit
class TestMultiDayRequest:
    def test_minimal_valid_request(self):
        req = _req()
        assert len(req.days) == 2
        assert len(req.places) == 2
        assert req.transport_mode == TransportMode.WALK

    def test_days_must_have_at_least_one_entry(self):
        with pytest.raises(ValidationError):
            _req(days=[])

    def test_places_must_have_at_least_two(self):
        with pytest.raises(ValidationError):
            _req(places=[_pref("p1")])

    def test_transit_mode_rejected(self):
        with pytest.raises(ValidationError, match="TRANSIT"):
            _req(transport_mode=TransportMode.TRANSIT)

    def test_day_index_out_of_range_raises(self):
        with pytest.raises(ValidationError, match="day_index"):
            _req(places=[_pref("p1", day_preferences=[_slot(5)]), _pref("p2")])

    def test_duplicate_place_ids_raises(self):
        with pytest.raises(ValidationError, match="place_id"):
            _req(places=[_pref("p1"), _pref("p1"), _pref("p2")])

    def test_start_location_only_lat_raises(self):
        with pytest.raises(ValidationError, match="start_lat"):
            _req(start_lat=50.0)

    def test_start_location_both_provided_is_valid(self):
        req = _req(start_lat=50.0, start_lng=20.0)
        assert req.start_lat == 50.0
        assert req.start_lng == 20.0


@pytest.mark.unit
class TestDayPlanAndResponse:
    def _step(self) -> RouteStep:
        return RouteStep(
            place_id="p1",
            name="Place",
            lat=50.0,
            lng=20.0,
            arrival_time=time(10, 0),
            departure_time=time(10, 30),
            travel_from_previous_s=0,
            visit_duration_min=30,
        )

    def test_day_plan_construction(self):
        plan = DayPlan(
            day_index=0,
            date=date(2026, 6, 1),
            steps=[self._step()],
            total_travel_time_s=0,
            total_visit_time_min=30,
            total_wait_min=0,
            skipped=[],
        )
        assert plan.day_index == 0
        assert len(plan.steps) == 1

    def test_multi_day_response_construction(self):
        plan = DayPlan(
            day_index=0,
            date=date(2026, 6, 1),
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            skipped=[],
        )
        resp = MultiDayResponse(days=[plan], transport_mode=TransportMode.WALK, unassigned=[])
        assert len(resp.days) == 1
        assert resp.unassigned == []

    def test_multi_day_response_with_unassigned(self):
        resp = MultiDayResponse(
            days=[],
            transport_mode=TransportMode.WALK,
            unassigned=[SkippedPlace(place_id="p1", name="X", reason="TIME_WINDOW_INFEASIBLE")],
        )
        assert len(resp.unassigned) == 1
