"""Integration: MultiDayTripEditor against a real Mongo trips collection. optimize_trip
is stubbed (its own suite covers routing) to focus on the CAS-persist + coherence path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.optimizer.solver.models import MultiDayResponse
from src.trips.editing.errors import OptimizerFailedError, TripConcurrencyConflictError
from src.trips.editing.operations import SetPlacePinnedOp, UpdateDayWindowOp
from src.trips.editing.service import MultiDayTripEditor
from src.trips.manager import TRIPS_COLLECTION, TripsManager
from src.trips.models import MultiDaySaveTripRequest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def clean(test_db):
    yield
    await test_db[TRIPS_COLLECTION].delete_many({})


def _save_request(base_payload) -> MultiDaySaveTripRequest:
    return MultiDaySaveTripRequest(
        name="Tokyo May",
        multi_day_request=base_payload,
        multi_day_response={"days": [], "transport_mode": "WALK", "unassigned": []},
    )


async def _seed(test_db, base_payload) -> str:
    manager = TripsManager(test_db)
    saved = await manager.save(_save_request(base_payload))
    return saved.id


def _canned_response(request) -> MultiDayResponse:
    return MultiDayResponse.model_validate(
        {
            "days": [
                {
                    "day_index": i,
                    "date": str(cfg.date),
                    "steps": [],
                    "total_travel_time_s": i,
                    "total_visit_time_min": 0,
                    "total_wait_min": 0,
                    "skipped": [],
                }
                for i, cfg in enumerate(request.days)
            ],
            "transport_mode": request.transport_mode,
            "unassigned": [],
        }
    )


async def test_apply_persists_new_request_and_coherent_response_and_bumps_revision(test_db, base_payload):
    from src.optimizer.solver.models import MultiDayRequest

    request = MultiDayRequest.model_validate(base_payload)
    trip_id = await _seed(test_db, request)
    editor = MultiDayTripEditor(test_db, TripsManager(test_db), AsyncMock())

    ops = [
        SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=2),
        UpdateDayWindowOp(op="update_day_window", day_index=2, day_start_hour=8),
    ]
    with patch(
        "src.trips.editing.service.optimize_trip",
        new=AsyncMock(side_effect=lambda _db, _routes, req: _canned_response(req)),
    ):
        updated = await editor.apply(trip_id, ops, expected_revision=0)

    assert updated.trip.revision == 1
    reloaded = await TripsManager(test_db).find_by_id(trip_id)
    pinned = next(p for p in reloaded.multi_day_request.places if p.place_id == "p1")
    assert pinned.day_preferences[0].day_index == 2
    assert reloaded.multi_day_request.days[2].day_start_hour == 8
    # response recomputed from the same run: one day plan per (new) day
    assert len(reloaded.multi_day_response.days) == len(reloaded.multi_day_request.days)

    raw = await test_db[TRIPS_COLLECTION].find_one({})
    assert "expected_revision" not in raw


async def test_second_apply_on_stale_revision_conflicts_and_leaves_doc(test_db, base_payload):
    from src.optimizer.solver.models import MultiDayRequest

    request = MultiDayRequest.model_validate(base_payload)
    trip_id = await _seed(test_db, request)
    editor = MultiDayTripEditor(test_db, TripsManager(test_db), AsyncMock())
    ops = [SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=1)]

    with patch(
        "src.trips.editing.service.optimize_trip",
        new=AsyncMock(side_effect=lambda _db, _routes, req: _canned_response(req)),
    ):
        await editor.apply(trip_id, ops, expected_revision=0)
        with pytest.raises(TripConcurrencyConflictError):
            await editor.apply(trip_id, ops, expected_revision=0)

    reloaded = await TripsManager(test_db).find_by_id(trip_id)
    assert reloaded.revision == 1


async def test_optimizer_failure_persists_nothing(test_db, base_payload):
    from src.optimizer.solver.models import MultiDayRequest

    request = MultiDayRequest.model_validate(base_payload)
    trip_id = await _seed(test_db, request)
    before = await test_db[TRIPS_COLLECTION].find_one({})
    editor = MultiDayTripEditor(test_db, TripsManager(test_db), AsyncMock())

    with (
        patch(
            "src.trips.editing.service.optimize_trip",
            new=AsyncMock(side_effect=ValueError("infeasible")),
        ),
        pytest.raises(OptimizerFailedError),
    ):
        await editor.apply(
            trip_id, [SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=1)], expected_revision=0
        )

    after = await test_db[TRIPS_COLLECTION].find_one({})
    assert before == after
