"""Unit tests for the trip-context binding the /chat router does on a normal turn."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.models import ChatRequest
from src.orchestrator.router import _bind_trip_and_build_state

pytestmark = pytest.mark.unit


def _payload(trip_id="trip-1", place_ids=None):
    return ChatRequest(
        messages=[{"role": "user", "content": "pin TeamLab to day 3"}],
        session_id="sess-1",
        trip_id=trip_id,
        place_ids=place_ids or [],
    )


def _multi_day_trip():
    trip = MagicMock()
    trip.plan_type = "MULTI_DAY"
    trip.name = "Tokyo May"
    trip.revision = 4
    trip.multi_day_request.places = [MagicMock(place_id="p1"), MagicMock(place_id="p2")]
    return trip


async def test_missing_trip_binds_place_selection_and_adds_note():
    store = MagicMock()
    store.bind_place_selection = AsyncMock()
    store.bind_trip = AsyncMock()

    with patch("src.orchestrator.router.TripsManager") as tm:
        tm.return_value.find_by_id = AsyncMock(return_value=None)
        state = await _bind_trip_and_build_state(MagicMock(), store, "sess-1", _payload(), trip_id="ghost")

    store.bind_place_selection.assert_awaited_once_with("sess-1", [])
    store.bind_trip.assert_not_called()
    assert state["trip_context"] == ""
    assert "could not be loaded" in state["messages"][0].content


async def test_multi_day_trip_binds_trip_with_server_derived_scope():
    store = MagicMock()
    store.bind_trip = AsyncMock()
    trip = _multi_day_trip()

    with (
        patch("src.orchestrator.router.TripsManager") as tm,
        patch("src.orchestrator.router.build_trip_context_prompt", return_value="TRIP PROMPT"),
        patch("src.orchestrator.router.TripPromptContext"),
    ):
        tm.return_value.find_by_id = AsyncMock(return_value=trip)
        state = await _bind_trip_and_build_state(
            MagicMock(), store, "sess-1", _payload(place_ids=["ignored"]), trip_id="trip-1"
        )

    store.bind_trip.assert_awaited_once()
    kwargs = store.bind_trip.call_args.kwargs
    assert kwargs["trip_id"] == "trip-1"
    assert kwargs["revision"] == 4
    assert kwargs["allowed_place_ids"] == ["p1", "p2"]  # from persisted request, not client place_ids
    assert state["place_context"] == []  # client place_ids ignored under trip context
