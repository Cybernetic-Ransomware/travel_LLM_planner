"""Unit tests for multi-day optimizer request/response models."""

from __future__ import annotations

from datetime import date, time, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.accommodations.models import AccommodationStay
from src.optimizer.matrix.models import TransportMode
from src.optimizer.solver.models import (
    DayConfig,
    DayPlan,
    DayRouteSegment,
    DaySlot,
    MultiDayRequest,
    MultiDayResponse,
    PlaceDayPreference,
    RouteStep,
    SkippedPlace,
    TransferEndpoint,
    TransferSegment,
)
from src.transfers.models import TransferBlock


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
        with pytest.raises(ValidationError, match="effective day start"):
            DayConfig(date=date(2026, 6, 1), day_start_hour=18, day_end_hour=10)

    def test_start_equal_to_end_raises(self):
        with pytest.raises(ValidationError, match="effective day start"):
            DayConfig(date=date(2026, 6, 1), day_start_hour=9, day_end_hour=9)

    def test_day_start_time_and_day_end_time_default_to_none(self):
        cfg = DayConfig(date=date(2026, 6, 1))
        assert cfg.day_start_time is None
        assert cfg.day_end_time is None

    def test_explicit_times_override_hours_for_range_check(self):
        with pytest.raises(ValidationError, match="effective day start"):
            DayConfig(date=date(2026, 6, 1), day_start_hour=9, day_start_time=time(22, 30), day_end_hour=21)

    def test_day_end_time_midnight_rejected(self):
        with pytest.raises(ValidationError, match="cannot represent midnight"):
            DayConfig(date=date(2026, 6, 1), day_end_time=time(0, 0))

    def test_day_end_hour_24_with_day_end_time_rejected(self):
        with pytest.raises(ValidationError, match="cannot be combined with day_end_hour=24"):
            DayConfig(date=date(2026, 6, 1), day_end_hour=24, day_end_time=time(23, 30))

    @pytest.mark.parametrize("field", ["day_start_time", "day_end_time"])
    def test_timezone_aware_time_rejected(self, field):
        """Offset-aware time must be a controlled 422, never a naive-vs-aware TypeError."""
        with pytest.raises(ValidationError, match="naive local wall-clock time"):
            DayConfig(date=date(2026, 6, 1), **{field: time(10, 0, tzinfo=timezone(timedelta(hours=9)))})


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

    def test_transfer_defaults_to_none(self):
        plan = DayPlan(
            day_index=0,
            date=date(2026, 6, 1),
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            skipped=[],
        )
        assert plan.transfer is None

    def test_transfer_segment_carries_full_origin_and_destination(self):
        segment = TransferSegment(
            origin=TransferEndpoint(name="Tokyo Hotel", lat=35.6812, lng=139.7671),
            destination=TransferEndpoint(name="Kyoto Hotel", lat=34.9855, lng=135.7588),
            departure_time=time(10, 0),
            arrival_time=time(15, 0),
            duration_s=18000,
            label="Shinkansen Tokyo→Kyoto",
        )
        plan = DayPlan(
            day_index=0,
            date=date(2026, 10, 10),
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            skipped=[],
            transfer=segment,
        )
        assert plan.transfer is not None
        assert plan.transfer.origin.name == "Tokyo Hotel"
        assert plan.transfer.destination.name == "Kyoto Hotel"
        assert plan.transfer.duration_s == 18000

    def test_transfer_segment_label_optional(self):
        segment = TransferSegment(
            origin=TransferEndpoint(name="A", lat=0.0, lng=0.0),
            destination=TransferEndpoint(name="B", lat=1.0, lng=1.0),
            departure_time=time(10, 0),
            arrival_time=time(15, 0),
            duration_s=18000,
        )
        assert segment.label is None

    def test_route_segments_defaults_to_empty_list(self):
        plan = DayPlan(
            day_index=0,
            date=date(2026, 6, 1),
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            skipped=[],
        )
        assert plan.route_segments == []

    def test_day_plan_without_transfer_has_no_route_segments(self):
        """route_segments is populated only for a day with a resolved transfer — see ADR-17."""
        plan = DayPlan(
            day_index=0,
            date=date(2026, 6, 1),
            steps=[self._step()],
            total_travel_time_s=0,
            total_visit_time_min=30,
            total_wait_min=0,
            skipped=[],
        )
        assert plan.transfer is None
        assert plan.route_segments == []

    def test_ordinary_day_construction_unaffected(self):
        """Regression: adding route_segments must not change existing DayPlan construction."""
        plan = DayPlan(
            day_index=0,
            date=date(2026, 6, 1),
            steps=[self._step()],
            total_travel_time_s=100,
            total_visit_time_min=30,
            total_wait_min=5,
            skipped=[SkippedPlace(place_id="p2", name="P2", reason="TIME_WINDOW_INFEASIBLE")],
            travel_to_end_s=200,
        )
        assert plan.steps == [self._step()]
        assert plan.total_travel_time_s == 100
        assert plan.travel_to_end_s == 200
        assert plan.route_segments == []

    def test_day_route_segment_construction(self):
        segment = DayRouteSegment(
            kind="PRE_TRANSFER",
            steps=[self._step()],
            total_travel_time_s=900,
            total_visit_time_min=60,
            total_wait_min=0,
            travel_to_end_s=300,
            skipped=[],
        )
        assert segment.kind == "PRE_TRANSFER"
        assert len(segment.steps) == 1
        assert segment.travel_to_end_s == 300

    def test_day_plan_carries_both_route_segments(self):
        pre_segment = DayRouteSegment(
            kind="PRE_TRANSFER", steps=[], total_travel_time_s=0, total_visit_time_min=0, total_wait_min=0, skipped=[]
        )
        post_segment = DayRouteSegment(
            kind="POST_TRANSFER",
            steps=[self._step()],
            total_travel_time_s=0,
            total_visit_time_min=30,
            total_wait_min=0,
            skipped=[],
        )
        plan = DayPlan(
            day_index=0,
            date=date(2026, 10, 10),
            steps=[self._step()],
            total_travel_time_s=0,
            total_visit_time_min=30,
            total_wait_min=0,
            skipped=[],
            route_segments=[pre_segment, post_segment],
        )
        assert [s.kind for s in plan.route_segments] == ["PRE_TRANSFER", "POST_TRANSFER"]
