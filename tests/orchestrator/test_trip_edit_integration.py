"""End-to-end vertical slice for confirmation-gated multi-day trip editing (ADR-20):
persisted trip -> POST /chat (trip_id) -> interrupt -> tool_proposal -> POST /chat
(resume_confirmed) -> consume scope -> MultiDayTripEditor -> CAS persist -> trip_updated
SSE -> GET. Real Mongo, real graph, real editor/store; only the LLM and optimize_trip
are stubbed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from src.core.db.manager import THREAD_TRIP_STATE_COLLECTION
from src.main import app
from src.optimizer.solver.models import MultiDayRequest, MultiDayResponse
from src.orchestrator.manager import OrchestratorManager
from src.trips.manager import TRIPS_COLLECTION, TripsManager
from src.trips.models import MultiDaySaveTripRequest

pytestmark = pytest.mark.integration

_SESSION = "sess-trip-edit-int"

_TRIP_PAYLOAD = {
    "days": [{"date": "2026-05-01"}, {"date": "2026-05-02"}, {"date": "2026-05-03"}],
    "places": [
        {"place_id": "p1", "day_preferences": []},
        {"place_id": "p2", "day_preferences": []},
    ],
    "transport_mode": "WALK",
}

_PIN_P2_TO_DAY_3 = {
    "name": "edit_multi_day_trip",
    "args": {"operations": [{"op": "set_place_pinned", "place_id": "p2", "day_index": 2}]},
    "id": "call-1",
    "type": "tool_call",
}


class _ScriptedLLM(GenericFakeChatModel):
    """GenericFakeChatModel doesn't implement bind_tools; the graph binds tools before use."""

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003
        return self


def _canned_response(request: MultiDayRequest) -> MultiDayResponse:
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


def _parse_sse(body: str) -> list[dict]:
    events: list[dict] = []
    for block in body.split("\n\n"):
        line = block.strip()
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        if payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events


@pytest.fixture(autouse=True)
async def _clean(test_db):
    yield
    await test_db[TRIPS_COLLECTION].delete_many({})
    await test_db[THREAD_TRIP_STATE_COLLECTION].delete_many({})


async def _seed_trip(test_db) -> str:
    saved = await TripsManager(test_db).save(
        MultiDaySaveTripRequest(
            plan_type="MULTI_DAY",
            name="Tokyo",
            multi_day_request=MultiDayRequest.model_validate(_TRIP_PAYLOAD),
            multi_day_response={"days": [], "transport_mode": "WALK", "unassigned": []},
        )
    )
    return saved.id


async def _connected_manager(test_db, routes_manager, monkeypatch, scripted: list[AIMessage]) -> OrchestratorManager:
    mgr = OrchestratorManager(
        provider="openai",
        api_key="test",
        model_name="fake",
        langsmith_api_key="",
        langsmith_tracing=False,
        langsmith_project="",
        db=test_db,
        routes_manager=routes_manager,
    )
    monkeypatch.setattr(mgr, "_create_llm", lambda: _ScriptedLLM(messages=iter(scripted)))
    await mgr.connect()
    return mgr


async def test_full_chat_edit_flow_persists_and_emits_trip_updated(client, test_db, google_routes_manager, monkeypatch):
    trip_id = await _seed_trip(test_db)
    mgr = await _connected_manager(
        test_db,
        google_routes_manager,
        monkeypatch,
        [
            AIMessage(content="I'll pin p2 to day 3.", tool_calls=[_PIN_P2_TO_DAY_3]),
            AIMessage(content="Done — p2 is pinned to day 3."),
        ],
    )
    app.state.orchestrator = mgr
    try:
        with patch(
            "src.trips.editing.service.optimize_trip",
            new=AsyncMock(side_effect=lambda _db, _routes, req: _canned_response(req)),
        ):
            propose = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={
                    "messages": [{"role": "user", "content": "pin p2 to day 3"}],
                    "session_id": _SESSION,
                    "trip_id": trip_id,
                },
            )
            proposal = next(e for e in _parse_sse(propose.text) if "tool_proposal" in e)
            assert proposal["tool_proposal"]["tool"] == "edit_multi_day_trip"

            armed = await test_db[THREAD_TRIP_STATE_COLLECTION].find_one({"thread_id": _SESSION})
            assert armed["pending"]["kind"] == "trip"
            assert armed["pending"]["trip_id"] == trip_id
            assert armed["pending"]["revision"] == 0

            confirm = await client.post(
                "/api/v1/core/orchestrator/chat",
                json={"messages": [], "session_id": _SESSION, "trip_id": trip_id, "resume_confirmed": True},
            )
            updated = next(e for e in _parse_sse(confirm.text) if "trip_updated" in e)
            assert updated["trip_updated"] == {
                "trip_id": trip_id,
                "revision": 1,
                "plan_type": "MULTI_DAY",
                "name": "Tokyo",
            }

        detail = (await client.get(f"/api/v1/core/trips/{trip_id}")).json()
        assert detail["revision"] == 1
        p2 = next(p for p in detail["multi_day_request"]["places"] if p["place_id"] == "p2")
        assert p2["day_preferences"] == [{"day_index": 2, "preferred_hour_from": None, "preferred_hour_to": None}]
        assert len(detail["multi_day_response"]["days"]) == 3  # response recomputed from the same run
        assert detail["updated_at"] is not None

        raw = await test_db[TRIPS_COLLECTION].find_one({})
        assert "expected_revision" not in raw

        # single-use: the armed scope is spent, a repeat confirm has nothing to consume
        assert await mgr.trip_session_state.consume_pending(_SESSION) is None
    finally:
        await mgr.disconnect()
        app.state.orchestrator = None
