"""Integration: MultiDayTripEditor against a real Turso trips backend. optimize_trip is
stubbed (its own suite covers routing) to focus on the CAS-persist + history-row path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.optimizer.solver.models import MultiDayRequest, MultiDayResponse
from src.trips.editing.errors import OptimizerFailedError, TripConcurrencyConflictError
from src.trips.editing.operations import SetPlacePinnedOp, UpdateDayWindowOp
from src.trips.editing.service import MultiDayTripEditor
from src.trips.models import MultiDaySaveTripRequest
from src.trips.repository import TripRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def repo(trip_db) -> TripRepository:
    return TripRepository(trip_db)


def _save_request(base_payload) -> MultiDaySaveTripRequest:
    return MultiDaySaveTripRequest(
        name="Tokyo May",
        multi_day_request=base_payload,
        multi_day_response={"days": [], "transport_mode": "WALK", "unassigned": []},
    )


async def _seed(repo: TripRepository, base_payload) -> str:
    saved = await repo.save(_save_request(base_payload))
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


async def _revision_rows(conn, trip_id: str) -> list[dict]:
    result = await conn.execute(
        "SELECT revision, source, summary FROM trip_revisions WHERE trip_id = ? ORDER BY revision", (trip_id,)
    )
    return result.rows


async def test_apply_persists_request_response_and_orchestrator_revision_row(repo, trip_db, base_payload):
    request = MultiDayRequest.model_validate(base_payload)
    trip_id = await _seed(repo, request)
    editor = MultiDayTripEditor(AsyncMock(), repo, AsyncMock())

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
    reloaded = await repo.get(trip_id)
    pinned = next(p for p in reloaded.multi_day_request.places if p.place_id == "p1")
    assert pinned.day_preferences[0].day_index == 2
    assert reloaded.multi_day_request.days[2].day_start_hour == 8
    assert len(reloaded.multi_day_response.days) == len(reloaded.multi_day_request.days)

    rows = await _revision_rows(trip_db, trip_id)
    assert [r["revision"] for r in rows] == [0, 1]
    assert rows[1]["source"] == "ORCHESTRATOR"
    assert rows[1]["summary"].startswith("2 changes:")


async def test_second_apply_on_stale_revision_conflicts_and_leaves_history(repo, trip_db, base_payload):
    request = MultiDayRequest.model_validate(base_payload)
    trip_id = await _seed(repo, request)
    editor = MultiDayTripEditor(AsyncMock(), repo, AsyncMock())
    ops = [SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=1)]

    with patch(
        "src.trips.editing.service.optimize_trip",
        new=AsyncMock(side_effect=lambda _db, _routes, req: _canned_response(req)),
    ):
        await editor.apply(trip_id, ops, expected_revision=0)
        with pytest.raises(TripConcurrencyConflictError):
            await editor.apply(trip_id, ops, expected_revision=0)

    reloaded = await repo.get(trip_id)
    assert reloaded.revision == 1
    assert len(await _revision_rows(trip_db, trip_id)) == 2


async def test_optimizer_failure_persists_nothing(repo, trip_db, base_payload):
    request = MultiDayRequest.model_validate(base_payload)
    trip_id = await _seed(repo, request)
    editor = MultiDayTripEditor(AsyncMock(), repo, AsyncMock())

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

    reloaded = await repo.get(trip_id)
    assert reloaded.revision == 0
    assert len(await _revision_rows(trip_db, trip_id)) == 1
