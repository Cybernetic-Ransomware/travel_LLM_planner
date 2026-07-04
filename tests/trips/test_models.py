import pytest
from pydantic import ValidationError

from src.trips.models import SaveTripRequest


def _valid_payload() -> dict:
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
        "selected_place_ids": ["p1", "p2"],
        "transport_mode": "WALK",
        "day_start_hour": 9,
        "day_end_hour": 21,
    }


@pytest.mark.unit
class TestSaveTripRequest:
    def test_valid(self):
        req = SaveTripRequest(**_valid_payload())
        assert req.name == "Test Trip"
        assert str(req.date) == "2026-07-04"

    def test_name_empty_rejected(self):
        payload = _valid_payload()
        payload["name"] = ""
        with pytest.raises(ValidationError):
            SaveTripRequest(**payload)

    def test_name_too_long_rejected(self):
        payload = _valid_payload()
        payload["name"] = "x" * 201
        with pytest.raises(ValidationError):
            SaveTripRequest(**payload)

    def test_day_start_hour_above_23_rejected(self):
        payload = _valid_payload()
        payload["day_start_hour"] = 24
        with pytest.raises(ValidationError):
            SaveTripRequest(**payload)

    def test_day_end_hour_zero_rejected(self):
        payload = _valid_payload()
        payload["day_end_hour"] = 0
        with pytest.raises(ValidationError):
            SaveTripRequest(**payload)

    def test_missing_optimizer_request_rejected(self):
        payload = _valid_payload()
        del payload["optimizer_request"]
        with pytest.raises(ValidationError):
            SaveTripRequest(**payload)
