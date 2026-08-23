import pytest
from pydantic import TypeAdapter, ValidationError

from src.trips.models import (
    MultiDaySaveTripRequest,
    MultiDayTripDetailOut,
    MultiDayTripSummaryOut,
    SaveTripRequest,
    SingleDaySaveTripRequest,
    SingleDayTripDetailOut,
    SingleDayTripSummaryOut,
    TripDetailOut,
    TripSummaryOut,
)

_save_trip_request_adapter: TypeAdapter = TypeAdapter(SaveTripRequest)


def _valid_single_day_payload() -> dict:
    return {
        "name": "Test Trip",
        "date": "2026-07-04",
        "optimizer_request": {
            "place_ids": ["p1", "p2"],
            "transport_mode": "WALK",
            "day_start_hour": 9,
            "day_end_hour": 21,
        },
        "optimizer_response": {
            "steps": [],
            "total_travel_time_s": 0,
            "total_visit_time_min": 0,
            "total_wait_min": 0,
            "transport_mode": "WALK",
            "skipped": [],
        },
    }


def _valid_multi_day_payload() -> dict:
    return {
        "name": "Multi Day Trip",
        "multi_day_request": {
            "days": [
                {"date": "2026-07-01"},
                {"date": "2026-07-02"},
                {"date": "2026-07-03"},
            ],
            "places": [
                {"place_id": "p1", "day_preferences": []},
                {"place_id": "p2", "day_preferences": [{"day_index": 1}]},
            ],
            "transport_mode": "WALK",
            "accommodations": [
                {
                    "name": "Hotel A",
                    "lat": 50.06,
                    "lng": 19.94,
                    "check_in_date": "2026-07-01",
                    "check_out_date": "2026-07-03",
                },
                {
                    "name": "Hotel B",
                    "lat": 50.08,
                    "lng": 19.90,
                    "check_in_date": "2026-07-03",
                    "check_out_date": "2026-07-05",
                },
            ],
            "transfers": [
                {
                    "date": "2026-07-03",
                    "departure_time": "11:00:00",
                    "arrival_time": "13:00:00",
                    "label": "Train to Hotel B",
                }
            ],
        },
        "multi_day_response": {
            "days": [
                {
                    "day_index": 0,
                    "date": "2026-07-01",
                    "steps": [
                        {
                            "place_id": "p1",
                            "name": "Museum",
                            "lat": 50.061,
                            "lng": 19.941,
                            "arrival_time": "10:00:00",
                            "departure_time": "11:00:00",
                            "travel_from_previous_s": 300,
                            "visit_duration_min": 60,
                        }
                    ],
                    "total_travel_time_s": 300,
                    "total_visit_time_min": 60,
                    "total_wait_min": 0,
                    "skipped": [],
                },
                {
                    "day_index": 1,
                    "date": "2026-07-02",
                    "steps": [],
                    "total_travel_time_s": 0,
                    "total_visit_time_min": 0,
                    "total_wait_min": 0,
                    "skipped": [{"place_id": "p2", "name": "Closed Park", "reason": "TIME_WINDOW_INFEASIBLE"}],
                },
                {
                    "day_index": 2,
                    "date": "2026-07-03",
                    "steps": [],
                    "total_travel_time_s": 0,
                    "total_visit_time_min": 0,
                    "total_wait_min": 0,
                    "skipped": [],
                    "transfer": {
                        "origin": {"name": "Hotel A", "lat": 50.06, "lng": 19.94},
                        "destination": {"name": "Hotel B", "lat": 50.08, "lng": 19.90},
                        "departure_time": "11:00:00",
                        "arrival_time": "13:00:00",
                        "duration_s": 7200,
                        "label": "Train to Hotel B",
                    },
                    "route_segments": [
                        {
                            "kind": "PRE_TRANSFER",
                            "steps": [],
                            "total_travel_time_s": 0,
                            "total_visit_time_min": 0,
                            "total_wait_min": 0,
                            "skipped": [],
                        },
                        {
                            "kind": "POST_TRANSFER",
                            "steps": [],
                            "total_travel_time_s": 0,
                            "total_visit_time_min": 0,
                            "total_wait_min": 0,
                            "skipped": [],
                        },
                    ],
                },
            ],
            "transport_mode": "WALK",
            "unassigned": [{"place_id": "p3", "name": "Unreachable Cafe", "reason": "CAPACITY_EXCEEDED"}],
        },
    }


@pytest.mark.unit
class TestSingleDaySaveTripRequest:
    def test_valid(self):
        req = SingleDaySaveTripRequest(**_valid_single_day_payload())
        assert req.name == "Test Trip"
        assert str(req.date) == "2026-07-04"
        assert req.plan_type == "SINGLE_DAY"

    def test_name_empty_rejected(self):
        payload = _valid_single_day_payload()
        payload["name"] = ""
        with pytest.raises(ValidationError):
            SingleDaySaveTripRequest(**payload)

    def test_name_too_long_rejected(self):
        payload = _valid_single_day_payload()
        payload["name"] = "x" * 201
        with pytest.raises(ValidationError):
            SingleDaySaveTripRequest(**payload)

    def test_missing_optimizer_request_rejected(self):
        payload = _valid_single_day_payload()
        del payload["optimizer_request"]
        with pytest.raises(ValidationError):
            SingleDaySaveTripRequest(**payload)

    def test_invalid_optimizer_request_rejected(self):
        payload = _valid_single_day_payload()
        payload["optimizer_request"]["day_start_hour"] = 20
        payload["optimizer_request"]["day_end_hour"] = 8
        with pytest.raises(ValidationError):
            SingleDaySaveTripRequest(**payload)


@pytest.mark.unit
class TestMultiDaySaveTripRequest:
    def test_valid(self):
        req = MultiDaySaveTripRequest(**_valid_multi_day_payload())
        assert req.name == "Multi Day Trip"
        assert req.plan_type == "MULTI_DAY"
        assert len(req.multi_day_request.days) == 3
        assert len(req.multi_day_response.days) == 3

    def test_name_empty_rejected(self):
        payload = _valid_multi_day_payload()
        payload["name"] = ""
        with pytest.raises(ValidationError):
            MultiDaySaveTripRequest(**payload)

    def test_missing_multi_day_request_rejected(self):
        payload = _valid_multi_day_payload()
        del payload["multi_day_request"]
        with pytest.raises(ValidationError):
            MultiDaySaveTripRequest(**payload)

    def test_missing_multi_day_response_rejected(self):
        payload = _valid_multi_day_payload()
        del payload["multi_day_response"]
        with pytest.raises(ValidationError):
            MultiDaySaveTripRequest(**payload)

    def test_nested_multi_day_request_validator_delegated(self):
        payload = _valid_multi_day_payload()
        payload["multi_day_request"]["transport_mode"] = "TRANSIT"
        with pytest.raises(ValidationError):
            MultiDaySaveTripRequest(**payload)


@pytest.mark.unit
class TestSaveTripRequestDiscriminator:
    def test_legacy_flat_payload_no_plan_type_infers_single_day(self):
        result = _save_trip_request_adapter.validate_python(_valid_single_day_payload())
        assert isinstance(result, SingleDaySaveTripRequest)
        assert result.plan_type == "SINGLE_DAY"

    def test_explicit_plan_type_single_day(self):
        payload = _valid_single_day_payload()
        payload["plan_type"] = "SINGLE_DAY"
        result = _save_trip_request_adapter.validate_python(payload)
        assert isinstance(result, SingleDaySaveTripRequest)

    def test_explicit_plan_type_multi_day(self):
        payload = _valid_multi_day_payload()
        payload["plan_type"] = "MULTI_DAY"
        result = _save_trip_request_adapter.validate_python(payload)
        assert isinstance(result, MultiDaySaveTripRequest)

    def test_multi_day_request_key_without_plan_type_infers_multi_day(self):
        result = _save_trip_request_adapter.validate_python(_valid_multi_day_payload())
        assert isinstance(result, MultiDaySaveTripRequest)

    def test_unknown_plan_type_value_rejected(self):
        payload = _valid_single_day_payload()
        payload["plan_type"] = "WEEKLY"
        with pytest.raises(ValidationError):
            _save_trip_request_adapter.validate_python(payload)


@pytest.mark.unit
class TestHybridPayloadRejected:
    def test_no_plan_type_both_variant_fields_present_rejected(self):
        payload = _valid_single_day_payload()
        multi = _valid_multi_day_payload()
        payload["multi_day_request"] = multi["multi_day_request"]
        payload["multi_day_response"] = multi["multi_day_response"]
        with pytest.raises(ValidationError):
            _save_trip_request_adapter.validate_python(payload)

    def test_explicit_single_day_with_multi_day_fields_rejected(self):
        payload = _valid_single_day_payload()
        payload["plan_type"] = "SINGLE_DAY"
        multi = _valid_multi_day_payload()
        payload["multi_day_request"] = multi["multi_day_request"]
        payload["multi_day_response"] = multi["multi_day_response"]
        with pytest.raises(ValidationError):
            _save_trip_request_adapter.validate_python(payload)

    def test_explicit_multi_day_with_single_day_fields_rejected(self):
        payload = _valid_multi_day_payload()
        payload["plan_type"] = "MULTI_DAY"
        single = _valid_single_day_payload()
        payload["date"] = single["date"]
        payload["optimizer_request"] = single["optimizer_request"]
        payload["optimizer_response"] = single["optimizer_response"]
        with pytest.raises(ValidationError):
            _save_trip_request_adapter.validate_python(payload)


@pytest.mark.unit
class TestTripSummaryOutDiscriminator:
    def test_single_day_round_trip(self):
        summary = SingleDayTripSummaryOut(id="1", name="Trip", date="2026-07-04", created_at="2026-07-04T00:00:00")
        adapter: TypeAdapter = TypeAdapter(TripSummaryOut)
        result = adapter.validate_python(summary.model_dump())
        assert isinstance(result, SingleDayTripSummaryOut)

    def test_multi_day_round_trip(self):
        summary = MultiDayTripSummaryOut(
            id="1",
            name="Trip",
            start_date="2026-07-01",
            end_date="2026-07-05",
            num_days=3,
            created_at="2026-07-01T00:00:00",
        )
        adapter: TypeAdapter = TypeAdapter(TripSummaryOut)
        result = adapter.validate_python(summary.model_dump())
        assert isinstance(result, MultiDayTripSummaryOut)


@pytest.mark.unit
class TestTripDetailOutDiscriminator:
    def test_single_day_round_trip(self):
        detail = SingleDayTripDetailOut(
            id="1",
            name="Trip",
            date="2026-07-04",
            created_at="2026-07-04T00:00:00",
            optimizer_request=_valid_single_day_payload()["optimizer_request"],
            optimizer_response=_valid_single_day_payload()["optimizer_response"],
            selected_place_ids=["p1", "p2"],
            transport_mode="WALK",
            day_start_hour=9,
            day_end_hour=21,
        )
        adapter: TypeAdapter = TypeAdapter(TripDetailOut)
        result = adapter.validate_python(detail.model_dump(mode="json"))
        assert isinstance(result, SingleDayTripDetailOut)

    def test_multi_day_round_trip(self):
        payload = _valid_multi_day_payload()
        detail = MultiDayTripDetailOut(
            id="1",
            name="Trip",
            created_at="2026-07-01T00:00:00",
            start_date="2026-07-01",
            end_date="2026-07-05",
            num_days=3,
            transport_mode="WALK",
            multi_day_request=payload["multi_day_request"],
            multi_day_response=payload["multi_day_response"],
        )
        adapter: TypeAdapter = TypeAdapter(TripDetailOut)
        result = adapter.validate_python(detail.model_dump(mode="json"))
        assert isinstance(result, MultiDayTripDetailOut)


@pytest.mark.unit
class TestMultiDayRoundTripFields:
    def test_full_payload_round_trip_preserves_all_fields(self):
        payload = _valid_multi_day_payload()
        req = MultiDaySaveTripRequest(**payload)
        dumped = req.model_dump(mode="json")
        rehydrated = MultiDaySaveTripRequest.model_validate(dumped)

        assert len(rehydrated.multi_day_request.accommodations) == 2
        assert len(rehydrated.multi_day_request.transfers) == 1
        assert rehydrated.multi_day_request.places[1].day_preferences[0].day_index == 1

        transition_day = rehydrated.multi_day_response.days[2]
        assert transition_day.transfer is not None
        assert transition_day.transfer.origin.name == "Hotel A"
        assert len(transition_day.route_segments) == 2
        assert {seg.kind for seg in transition_day.route_segments} == {"PRE_TRANSFER", "POST_TRANSFER"}

        assert rehydrated.multi_day_response.days[1].skipped[0].place_id == "p2"
        assert rehydrated.multi_day_response.unassigned[0].place_id == "p3"

        assert dumped == rehydrated.model_dump(mode="json")
