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
