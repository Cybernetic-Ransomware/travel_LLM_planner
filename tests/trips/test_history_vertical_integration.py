"""Full history vertical slice (create -> manual PUT -> orchestrator edit -> list -> restore
-> reload -> stale conflict) against a real Turso file DB; only optimize_trip is stubbed."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.optimizer.solver.models import MultiDayRequest, MultiDayResponse
from src.trips.editing.operations import SetPlacePinnedOp
from src.trips.editing.service import MultiDayTripEditor
from src.trips.repository import TripRepository

pytestmark = pytest.mark.integration

_MULTI_DAY = {
    "name": "Kyoto",
    "multi_day_request": {
        "days": [{"date": "2026-05-01"}, {"date": "2026-05-02"}, {"date": "2026-05-03"}],
        "places": [
            {"place_id": "p1", "day_preferences": []},
            {"place_id": "p2", "day_preferences": []},
        ],
        "transport_mode": "WALK",
        "accommodations": [],
        "transfers": [],
    },
    "multi_day_response": {"days": [], "transport_mode": "WALK", "unassigned": []},
}


def _canned(request: MultiDayRequest) -> MultiDayResponse:
    return MultiDayResponse.model_validate(
        {
            "days": [
                {
                    "day_index": i,
                    "date": str(cfg.date),
                    "steps": [],
                    "total_travel_time_s": 0,
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


async def test_history_vertical_slice(trips_client, trip_db):
    endpoint = "/api/v1/core/trips"
    repo = TripRepository(trip_db)

    # 1. create -> revision 0, CREATED
    created = (await trips_client.post(f"{endpoint}/", json=_MULTI_DAY)).json()
    trip_id = created["id"]
    assert created["revision"] == 0

    # 2. manual PUT -> revision 1, MANUAL row
    put_body = {**_MULTI_DAY, "name": "Kyoto (manual)", "expected_revision": 0}
    assert (await trips_client.put(f"{endpoint}/{trip_id}", json=put_body)).json()["revision"] == 1

    # 3. orchestrator edit through the real editor -> revision 2, ORCHESTRATOR row
    editor = MultiDayTripEditor(AsyncMock(), repo, AsyncMock())
    with patch(
        "src.trips.editing.service.optimize_trip",
        new=AsyncMock(side_effect=lambda _db, _routes, req: _canned(req)),
    ):
        applied = await editor.apply(
            trip_id, [SetPlacePinnedOp(op="set_place_pinned", place_id="p2", day_index=2)], expected_revision=1
        )
    assert applied.trip.revision == 2

    # 4. GET /revisions — all three newest-first
    history = (await trips_client.get(f"{endpoint}/{trip_id}/revisions")).json()
    assert history["current_revision"] == 2
    assert [r["source"] for r in history["revisions"]] == ["ORCHESTRATOR", "MANUAL", "CREATED"]

    # 5. restore revision 0 with the right token -> revision 3 REVERT, snapshot == target
    restored = (await trips_client.post(f"{endpoint}/{trip_id}/revisions/0/restore", json={"expected_revision": 2})).json()
    assert restored["revision"] == 3
    assert restored["name"] == "Kyoto"
    hist2 = (await trips_client.get(f"{endpoint}/{trip_id}/revisions")).json()
    assert hist2["revisions"][0]["source"] == "REVERT"
    assert hist2["revisions"][0]["restored_from_revision"] == 0
    rev0 = (await trips_client.get(f"{endpoint}/{trip_id}/revisions/0")).json()
    rev3 = (await trips_client.get(f"{endpoint}/{trip_id}/revisions/3")).json()
    assert rev0["snapshot_hash"] == rev3["snapshot_hash"]

    # 6. reload stays coherent
    current = (await trips_client.get(f"{endpoint}/{trip_id}")).json()
    assert current["revision"] == 3
    assert current["name"] == "Kyoto"

    # 7. a stale restore attempt with the pre-restore token -> 409, no new row
    stale = await trips_client.post(f"{endpoint}/{trip_id}/revisions/1/restore", json={"expected_revision": 2})
    assert stale.status_code == 409
    assert (await trips_client.get(f"{endpoint}/{trip_id}/revisions")).json()["current_revision"] == 3
