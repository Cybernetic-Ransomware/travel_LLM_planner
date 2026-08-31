from __future__ import annotations

from datetime import date

import pytest

from src.accommodations.models import AccommodationStay
from src.trips.editing.errors import (
    AccommodationNotFoundError,
    AccommodationSelectorConflictError,
    OperationValidationError,
)
from src.trips.editing.operations import (
    AddAccommodationOp,
    RemoveAccommodationOp,
    SetPlaceFlexibleOp,
    UpdateAccommodationOp,
)
from src.trips.editing.reconcile import (
    dedupe_flexible_slots,
    merge_preserved_hours,
    reconcile_transfers_after_transition_change,
    resolve_accommodation_selectors,
)


def _stay(name: str, check_in: str, check_out: str) -> AccommodationStay:
    return AccommodationStay.model_validate(
        {"name": name, "lat": 0.0, "lng": 0.0, "check_in_date": check_in, "check_out_date": check_out}
    )


@pytest.mark.unit
class TestResolveAccommodationSelectors:
    def test_selector_uses_check_in_date_order_not_list_order(self):
        # list order: Osaka, Tokyo, Kyoto ; check-in order: Tokyo(0), Kyoto(1), Osaka(2)
        stays = [
            _stay("Osaka", "2026-05-10", "2026-05-12"),
            _stay("Tokyo", "2026-05-01", "2026-05-05"),
            _stay("Kyoto", "2026-05-05", "2026-05-10"),
        ]
        op = UpdateAccommodationOp(op="update_accommodation", stay_index=1, name="Kyoto Renamed")
        resolved = resolve_accommodation_selectors(stays, [op])
        # stay_index 1 (Kyoto) -> original list position 2
        assert resolved[id(op)] == 2

    def test_remove_and_update_same_stay_conflicts(self):
        stays = [_stay("A", "2026-05-01", "2026-05-03"), _stay("B", "2026-05-03", "2026-05-05")]
        ops = [
            RemoveAccommodationOp(op="remove_accommodation", stay_index=0),
            UpdateAccommodationOp(op="update_accommodation", stay_index=0, name="X"),
        ]
        with pytest.raises(AccommodationSelectorConflictError):
            resolve_accommodation_selectors(stays, ops)

    def test_two_updates_same_stay_conflicts(self):
        stays = [_stay("A", "2026-05-01", "2026-05-03"), _stay("B", "2026-05-03", "2026-05-05")]
        ops = [
            UpdateAccommodationOp(op="update_accommodation", stay_index=1, name="X"),
            UpdateAccommodationOp(op="update_accommodation", stay_index=1, check_out_date="2026-05-06"),
        ]
        with pytest.raises(AccommodationSelectorConflictError):
            resolve_accommodation_selectors(stays, ops)

    def test_out_of_range_selector(self):
        stays = [_stay("A", "2026-05-01", "2026-05-03")]
        with pytest.raises(AccommodationNotFoundError):
            resolve_accommodation_selectors(
                stays, [UpdateAccommodationOp(op="update_accommodation", stay_index=3, name="X")]
            )

    def test_add_ops_get_no_selector(self):
        stays = [_stay("A", "2026-05-01", "2026-05-03")]
        add = AddAccommodationOp(
            op="add_accommodation",
            name="New",
            lat=0.0,
            lng=0.0,
            check_in_date=date(2026, 5, 3),
            check_out_date=date(2026, 5, 5),
        )
        assert resolve_accommodation_selectors(stays, [add]) == {}


@pytest.mark.unit
class TestMergePreservedHours:
    def test_requested_wins(self):
        assert merge_preserved_hours([{"day_index": 0, "preferred_hour_from": 9}], 0, 10, 14) == (10, 14)

    def test_preserved_by_day_index(self):
        slots = [{"day_index": 1, "preferred_hour_from": 8, "preferred_hour_to": 12}]
        assert merge_preserved_hours(slots, 1, None, None) == (8, 12)

    def test_no_match_yields_none(self):
        assert merge_preserved_hours([{"day_index": 2, "preferred_hour_from": 8}], 0, None, None) == (None, None)

    def test_partial_patch_keeps_other_bound(self):
        slots = [{"day_index": 0, "preferred_hour_from": 10, "preferred_hour_to": 14}]
        assert merge_preserved_hours(slots, 0, 11, None) == (11, 14)
        assert merge_preserved_hours(slots, 0, None, 12) == (10, 12)

    def test_partial_patch_without_existing_slot_is_passthrough(self):
        assert merge_preserved_hours([], 0, 11, None) == (11, None)


@pytest.mark.unit
class TestDedupeFlexibleSlots:
    def test_duplicate_day_index_rejected(self):
        op = SetPlaceFlexibleOp(op="set_place_flexible", place_id="p1", slots=[{"day_index": 1}, {"day_index": 1}])
        with pytest.raises(OperationValidationError):
            dedupe_flexible_slots(op)

    def test_distinct_days_ok(self):
        op = SetPlaceFlexibleOp(op="set_place_flexible", place_id="p1", slots=[{"day_index": 0}, {"day_index": 2}])
        dedupe_flexible_slots(op)


@pytest.mark.unit
class TestReconcileTransfers:
    def _days(self) -> list[dict]:
        return [{"date": date(2026, 5, 1)}, {"date": date(2026, 5, 2)}, {"date": date(2026, 5, 3)}]

    def _acc(self, entries: list[tuple[str, str, str]]) -> list[dict]:
        return [{"name": n, "lat": 0.0, "lng": 0.0, "check_in_date": ci, "check_out_date": co} for n, ci, co in entries]

    def test_keeps_transfer_on_still_transition_day(self):
        transfers = [{"date": date(2026, 5, 3), "departure_time": None, "arrival_time": None, "label": None}]
        acc = self._acc([("A", "2026-05-01", "2026-05-03"), ("B", "2026-05-03", "2026-05-05")])
        dropped = reconcile_transfers_after_transition_change(self._days(), acc, transfers, {date(2026, 5, 3)})
        assert dropped == []
        assert len(transfers) == 1

    def test_drops_pre_existing_transfer_when_changeover_gone(self):
        transfers = [{"date": date(2026, 5, 3), "departure_time": None, "arrival_time": None, "label": None}]
        acc = self._acc([("A", "2026-05-01", "2026-05-06")])  # single stay spans everything, no changeover
        dropped = reconcile_transfers_after_transition_change(self._days(), acc, transfers, {date(2026, 5, 3)})
        assert dropped == [date(2026, 5, 3)]
        assert transfers == []

    def test_leaves_newly_added_transfer_for_hard_validation(self):
        transfers = [{"date": date(2026, 5, 3), "departure_time": None, "arrival_time": None, "label": None}]
        acc = self._acc([("A", "2026-05-01", "2026-05-06")])  # not a changeover
        dropped = reconcile_transfers_after_transition_change(self._days(), acc, transfers, reconcilable_dates=set())
        assert dropped == []
        assert len(transfers) == 1

    def test_no_transfers_is_noop(self):
        assert reconcile_transfers_after_transition_change(self._days(), [], [], set()) == []
