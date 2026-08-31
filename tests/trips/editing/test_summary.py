import pytest

from src.trips.editing.operations import (
    RemovePlaceOp,
    SetPlacePinnedOp,
    SetTransportModeOp,
    UpdateDayWindowOp,
)
from src.trips.editing.summary import manual_update_summary, summarize_operations
from src.trips.models import MultiDaySaveTripRequest, SingleDaySaveTripRequest

pytestmark = pytest.mark.unit


class TestSummarizeOperations:
    def test_single_op(self):
        ops = [RemovePlaceOp(op="remove_place", place_id="p1")]
        assert summarize_operations(ops) == "1 change: removed 1 place"

    def test_multiple_distinct_ops(self):
        ops = [
            SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=0),
            UpdateDayWindowOp(op="update_day_window", day_index=0, day_start_hour=8),
            SetTransportModeOp(op="set_transport_mode", mode="DRIVE"),
        ]
        assert summarize_operations(ops) == "3 changes: pinned 1 place, adjusted 1 day window, changed the transport mode"

    def test_repeated_op_pluralises_with_count(self):
        ops = [
            RemovePlaceOp(op="remove_place", place_id="p1"),
            RemovePlaceOp(op="remove_place", place_id="p2"),
        ]
        assert summarize_operations(ops) == "2 changes: removed 2 places"

    def test_is_deterministic(self):
        ops = [
            UpdateDayWindowOp(op="update_day_window", day_index=1, day_end_hour=20),
            SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=0),
        ]
        assert summarize_operations(ops) == summarize_operations(list(ops))


def _single() -> SingleDaySaveTripRequest:
    return SingleDaySaveTripRequest(
        name="t",
        date="2026-07-04",
        optimizer_request={"place_ids": ["a", "b", "c"], "transport_mode": "WALK", "day_start_hour": 9, "day_end_hour": 21},
        optimizer_response={
            "steps": [],
            "total_travel_time_s": 0,
            "total_visit_time_min": 0,
            "total_wait_min": 0,
            "transport_mode": "WALK",
            "skipped": [],
        },
    )


def _multi() -> MultiDaySaveTripRequest:
    return MultiDaySaveTripRequest(
        name="t",
        multi_day_request={
            "days": [{"date": "2026-07-01"}, {"date": "2026-07-02"}],
            "places": [{"place_id": "p1", "day_preferences": []}, {"place_id": "p2", "day_preferences": []}],
            "transport_mode": "WALK",
            "accommodations": [],
            "transfers": [],
        },
        multi_day_response={"days": [], "transport_mode": "WALK", "unassigned": []},
    )


class TestManualUpdateSummary:
    def test_single_day(self):
        assert manual_update_summary(_single()) == "Manual update — SINGLE_DAY, 3 places"

    def test_multi_day(self):
        assert manual_update_summary(_multi()) == "Manual update — MULTI_DAY, 2 places, 2 days"
