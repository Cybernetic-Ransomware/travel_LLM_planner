from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trips.editing.operations import (
    DaySlotOp,
    RemovePlaceOp,
    SetPlaceFlexibleOp,
    SetPlacePinnedOp,
    TripEditBatch,
    UpdateAccommodationOp,
)


@pytest.mark.unit
class TestDiscrimination:
    def test_op_field_selects_variant(self):
        batch = TripEditBatch(
            operations=[
                {"op": "set_place_pinned", "place_id": "p1", "day_index": 2},
                {"op": "remove_place", "place_id": "p2"},
            ]
        )
        assert isinstance(batch.operations[0], SetPlacePinnedOp)
        assert isinstance(batch.operations[1], RemovePlaceOp)

    def test_unknown_op_rejected(self):
        with pytest.raises(ValidationError):
            TripEditBatch(operations=[{"op": "nuke_trip", "place_id": "p1"}])


@pytest.mark.unit
class TestStrictExtraForbid:
    def test_batch_rejects_extra_key(self):
        with pytest.raises(ValidationError):
            TripEditBatch(
                operations=[{"op": "remove_place", "place_id": "p1"}],
                trip_id="smuggled",
            )

    def test_operation_rejects_smuggled_trip_id(self):
        with pytest.raises(ValidationError):
            TripEditBatch(operations=[{"op": "set_place_pinned", "place_id": "p1", "day_index": 0, "trip_id": "other"}])

    def test_operation_rejects_smuggled_revision_fields(self):
        for forbidden in ("revision", "expected_revision", "allowed_place_ids", "scope"):
            with pytest.raises(ValidationError):
                TripEditBatch(operations=[{"op": "remove_place", "place_id": "p1", forbidden: 1}])

    def test_nested_day_slot_rejects_extra_key(self):
        with pytest.raises(ValidationError):
            SetPlaceFlexibleOp(
                op="set_place_flexible",
                place_id="p1",
                slots=[
                    {"day_index": 0},
                    {"day_index": 1, "trip_id": "x"},
                ],
            )

    def test_day_slot_op_direct_extra_forbidden(self):
        with pytest.raises(ValidationError):
            DaySlotOp(day_index=0, surprise=1)

    def test_update_accommodation_rejects_extra_key(self):
        with pytest.raises(ValidationError):
            UpdateAccommodationOp(op="update_accommodation", stay_index=0, elevation=12)


@pytest.mark.unit
class TestBatchBounds:
    def test_empty_operations_rejected(self):
        with pytest.raises(ValidationError):
            TripEditBatch(operations=[])

    def test_over_max_operations_rejected(self):
        ops = [{"op": "remove_place", "place_id": f"p{i}"} for i in range(41)]
        with pytest.raises(ValidationError):
            TripEditBatch(operations=ops)

    def test_day_slot_bounds(self):
        with pytest.raises(ValidationError):
            DaySlotOp(day_index=-1)
        with pytest.raises(ValidationError):
            DaySlotOp(day_index=0, preferred_hour_from=24)

    def test_flexible_requires_two_slots(self):
        with pytest.raises(ValidationError):
            SetPlaceFlexibleOp(op="set_place_flexible", place_id="p1", slots=[{"day_index": 0}])
