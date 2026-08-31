from __future__ import annotations

import pytest

from src.optimizer.solver.models import MultiDayRequest


def _base_payload() -> dict:
    """3 days, 4 AUTO places, 2 non-overlapping stays, 1 transfer on the 2026-05-03 changeover."""
    return {
        "days": [
            {"date": "2026-05-01"},
            {"date": "2026-05-02"},
            {"date": "2026-05-03"},
        ],
        "places": [
            {"place_id": "p1", "day_preferences": []},
            {"place_id": "p2", "day_preferences": []},
            {"place_id": "p3", "day_preferences": []},
            {"place_id": "p4", "day_preferences": []},
        ],
        "transport_mode": "WALK",
        "accommodations": [
            {
                "name": "Hotel A",
                "lat": 35.68,
                "lng": 139.76,
                "check_in_date": "2026-05-01",
                "check_out_date": "2026-05-03",
                "check_in_from": "15:00:00",
            },
            {
                "name": "Hotel B",
                "lat": 34.69,
                "lng": 135.50,
                "check_in_date": "2026-05-03",
                "check_out_date": "2026-05-05",
            },
        ],
        "transfers": [
            {
                "date": "2026-05-03",
                "departure_time": "11:00:00",
                "arrival_time": "13:00:00",
                "label": "Shinkansen",
            }
        ],
    }


@pytest.fixture
def base_request() -> MultiDayRequest:
    return MultiDayRequest.model_validate(_base_payload())


@pytest.fixture
def base_payload() -> dict:
    return _base_payload()
