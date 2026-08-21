"""Integration tests for the multi-day trip optimizer endpoint."""

from __future__ import annotations

from datetime import time
from unittest.mock import AsyncMock, patch

import pytest

from src.optimizer.matrix.models import TransportMode
from src.optimizer.solver.models import (
    DayPlan,
    MultiDayResponse,
    OptimizeResponse,
    RouteStep,
    SkippedPlace,
)

_BASE = "/api/v1/core/optimizer"

_VALID_PAYLOAD = {
    "days": [
        {"date": "2026-06-01", "day_start_hour": 9, "day_end_hour": 21},
        {"date": "2026-06-02", "day_start_hour": 9, "day_end_hour": 21},
    ],
    "places": [
        {"place_id": "p1"},
        {"place_id": "p2"},
        {"place_id": "p3"},
        {"place_id": "p4"},
    ],
    "transport_mode": "WALK",
}


def _canned_single_day() -> OptimizeResponse:
    return OptimizeResponse(
        steps=[
            RouteStep(
                place_id="p1",
                name="Place p1",
                lat=50.0,
                lng=20.0,
                arrival_time=time(10, 0),
                departure_time=time(10, 30),
                travel_from_previous_s=0,
                visit_duration_min=30,
            )
        ],
        total_travel_time_s=0,
        total_visit_time_min=30,
        total_wait_min=0,
        transport_mode=TransportMode.WALK,
        skipped=[],
    )


def _canned_docs() -> list[dict]:
    return [
        {"_id": f"p{i}", "name": f"Place p{i}", "lat": 50.0, "lng": 20.0, "visit_duration_min": 30} for i in range(1, 5)
    ]


@pytest.mark.integration
class TestMultiDayRouteEndpoint:
    async def test_valid_request_returns_200(self, client):
        with (
            patch(
                "src.optimizer.solver.multi_day_service.fetch_places_by_ids",
                new=AsyncMock(return_value=_canned_docs()),
            ),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_canned_single_day()),
            ),
        ):
            response = await client.post(f"{_BASE}/trip", json=_VALID_PAYLOAD)

        assert response.status_code == 200

    async def test_response_contains_days_list(self, client):
        with (
            patch(
                "src.optimizer.solver.multi_day_service.fetch_places_by_ids",
                new=AsyncMock(return_value=_canned_docs()),
            ),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_canned_single_day()),
            ),
        ):
            response = await client.post(f"{_BASE}/trip", json=_VALID_PAYLOAD)

        body = response.json()
        assert "days" in body
        assert len(body["days"]) == 2
        assert "transport_mode" in body
        assert "unassigned" in body

    async def test_zero_days_returns_422(self, client):
        payload = {**_VALID_PAYLOAD, "days": []}
        response = await client.post(f"{_BASE}/trip", json=payload)
        assert response.status_code == 422

    async def test_one_place_returns_422(self, client):
        payload = {**_VALID_PAYLOAD, "places": [{"place_id": "p1"}]}
        response = await client.post(f"{_BASE}/trip", json=payload)
        assert response.status_code == 422

    async def test_transit_mode_returns_422(self, client):
        payload = {**_VALID_PAYLOAD, "transport_mode": "TRANSIT"}
        response = await client.post(f"{_BASE}/trip", json=payload)
        assert response.status_code == 422

    async def test_day_index_out_of_range_returns_422(self, client):
        payload = {
            **_VALID_PAYLOAD,
            "places": [
                {"place_id": "p1", "day_preferences": [{"day_index": 99}]},
                {"place_id": "p2"},
            ],
        }
        response = await client.post(f"{_BASE}/trip", json=payload)
        assert response.status_code == 422

    async def test_matrix_error_returns_502(self, client):
        from fastapi import HTTPException

        with (
            patch(
                "src.optimizer.solver.multi_day_service.fetch_places_by_ids",
                new=AsyncMock(return_value=_canned_docs()),
            ),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(side_effect=HTTPException(status_code=502, detail="Matrix unavailable")),
            ),
        ):
            response = await client.post(f"{_BASE}/trip", json=_VALID_PAYLOAD)

        assert response.status_code == 502

    async def test_skipped_places_appear_in_response(self, client):
        skipped_response = OptimizeResponse(
            steps=[],
            total_travel_time_s=0,
            total_visit_time_min=0,
            total_wait_min=0,
            transport_mode=TransportMode.WALK,
            skipped=[SkippedPlace(place_id="p1", name="P1", reason="TIME_WINDOW_INFEASIBLE")],
        )
        with (
            patch(
                "src.optimizer.solver.multi_day_service.fetch_places_by_ids",
                new=AsyncMock(return_value=_canned_docs()),
            ),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=skipped_response),
            ),
        ):
            response = await client.post(f"{_BASE}/trip", json=_VALID_PAYLOAD)

        body = response.json()
        assert response.status_code == 200
        total_skipped = sum(len(d["skipped"]) for d in body["days"])
        assert total_skipped > 0


@pytest.mark.integration
class TestMultiDayRouteAccommodations:
    async def test_accommodations_field_accepted_returns_200(self, client):
        payload = {
            **_VALID_PAYLOAD,
            "accommodations": [
                {
                    "name": "Tokyo Hotel",
                    "lat": 35.6895,
                    "lng": 139.6917,
                    "check_in_date": "2026-06-01",
                    "check_out_date": "2026-06-03",
                }
            ],
        }
        with (
            patch(
                "src.optimizer.solver.multi_day_service.fetch_places_by_ids",
                new=AsyncMock(return_value=_canned_docs()),
            ),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_canned_single_day()),
            ),
        ):
            response = await client.post(f"{_BASE}/trip", json=payload)

        assert response.status_code == 200

    async def test_overlapping_accommodations_returns_422(self, client):
        payload = {
            **_VALID_PAYLOAD,
            "accommodations": [
                {
                    "name": "Tokyo Hotel",
                    "lat": 35.6895,
                    "lng": 139.6917,
                    "check_in_date": "2026-06-01",
                    "check_out_date": "2026-06-03",
                },
                {
                    "name": "Kyoto Hotel",
                    "lat": 35.0116,
                    "lng": 135.7681,
                    "check_in_date": "2026-06-02",
                    "check_out_date": "2026-06-05",
                },
            ],
        }
        response = await client.post(f"{_BASE}/trip", json=payload)
        assert response.status_code == 422

    async def test_request_without_accommodations_field_still_works(self, client):
        with (
            patch(
                "src.optimizer.solver.multi_day_service.fetch_places_by_ids",
                new=AsyncMock(return_value=_canned_docs()),
            ),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_canned_single_day()),
            ),
        ):
            response = await client.post(f"{_BASE}/trip", json=_VALID_PAYLOAD)

        assert response.status_code == 200


_TOKYO_KYOTO_ACCOMMODATIONS = [
    {
        "name": "Tokyo Hotel",
        "lat": 35.6895,
        "lng": 139.6917,
        "check_in_date": "2026-05-30",
        "check_out_date": "2026-06-01",
        "check_out_by": "10:00:00",
    },
    {
        "name": "Kyoto Hotel",
        "lat": 35.0116,
        "lng": 135.7681,
        "check_in_date": "2026-06-01",
        "check_out_date": "2026-06-03",
        "check_in_from": "15:00:00",
    },
]

_TRANSFER_PAYLOAD = {
    "days": [{"date": "2026-06-01", "day_start_hour": 9, "day_end_hour": 21}],
    "places": [{"place_id": "p1"}, {"place_id": "p2"}],
    "transport_mode": "WALK",
    "accommodations": _TOKYO_KYOTO_ACCOMMODATIONS,
    "transfers": [
        {"date": "2026-06-01", "departure_time": "10:00:00", "arrival_time": "15:00:00", "label": "Shinkansen Tokyo→Kyoto"}
    ],
}


def _kyoto_docs() -> list[dict]:
    return [
        {"_id": "p1", "name": "Fushimi Inari", "lat": 34.9671, "lng": 135.7727, "visit_duration_min": 60},
        {"_id": "p2", "name": "Kinkaku-ji", "lat": 35.0394, "lng": 135.7292, "visit_duration_min": 60},
    ]


@pytest.mark.integration
class TestMultiDayRouteTransfers:
    """End-to-end Tokyo→Kyoto transfer scenario through POST /trip — see ADR-16."""

    async def test_transfer_scenario_returns_transfer_segment_and_post_transfer_steps(self, client):
        with (
            patch(
                "src.optimizer.solver.multi_day_service.fetch_places_by_ids",
                new=AsyncMock(return_value=_kyoto_docs()),
            ),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_canned_single_day()),
            ),
        ):
            response = await client.post(f"{_BASE}/trip", json=_TRANSFER_PAYLOAD)

        assert response.status_code == 200
        body = response.json()
        day0 = body["days"][0]
        assert day0["transfer"] is not None
        assert day0["transfer"]["origin"]["name"] == "Tokyo Hotel"
        assert day0["transfer"]["destination"]["name"] == "Kyoto Hotel"
        assert day0["transfer"]["duration_s"] == 18000
        assert len(day0["steps"]) > 0

    async def test_sibling_request_without_transfer_keeps_pre_branch_behavior(self, client):
        """Backward compatibility: same fixture minus `transfers` behaves exactly like ADR-15."""
        payload = {k: v for k, v in _TRANSFER_PAYLOAD.items() if k != "transfers"}

        with (
            patch(
                "src.optimizer.solver.multi_day_service.fetch_places_by_ids",
                new=AsyncMock(return_value=_kyoto_docs()),
            ),
            patch(
                "src.optimizer.solver.multi_day_service.optimize_route",
                new=AsyncMock(return_value=_canned_single_day()),
            ),
        ):
            response = await client.post(f"{_BASE}/trip", json=payload)

        assert response.status_code == 200
        assert response.json()["days"][0]["transfer"] is None

    async def test_transfer_on_non_transition_day_returns_422(self, client):
        payload = {**_TRANSFER_PAYLOAD, "accommodations": []}
        response = await client.post(f"{_BASE}/trip", json=payload)
        assert response.status_code == 422

    async def test_transfer_with_explicit_day_config_anchor_returns_422(self, client):
        """Guards against silently teleporting the post-transfer segment — see ADR-16."""
        payload = {
            **_TRANSFER_PAYLOAD,
            "days": [
                {
                    "date": "2026-06-01",
                    "day_start_hour": 9,
                    "day_end_hour": 21,
                    "start_lat": 0.0,
                    "start_lng": 0.0,
                }
            ],
        }
        response = await client.post(f"{_BASE}/trip", json=payload)
        assert response.status_code == 422
