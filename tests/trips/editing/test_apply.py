from __future__ import annotations

from datetime import date, time

import pytest

from src.optimizer.matrix.models import TransportMode
from src.trips.editing.apply import apply_operations
from src.trips.editing.errors import (
    AccommodationSelectorConflictError,
    InvalidDayIndexError,
    OperationValidationError,
    PlaceNotInTripError,
    TooFewPlacesError,
    TransferAlreadyExistsError,
    TransferNotFoundError,
    TripEditValidationError,
)
from src.trips.editing.operations import (
    AddAccommodationOp,
    AddTransferOp,
    RemoveAccommodationOp,
    RemovePlaceOp,
    RemoveTransferOp,
    SetPlaceAutoOp,
    SetPlaceFlexibleOp,
    SetPlacePinnedOp,
    SetTransportModeOp,
    UpdateAccommodationOp,
    UpdateDayWindowOp,
    UpdateTransferOp,
)

pytestmark = pytest.mark.unit


def _place(request, place_id):
    return next(p for p in request.places if p.place_id == place_id)


class TestPlaceAssignment:
    def test_set_place_auto_clears_preferences(self, base_request):
        pinned = apply_operations(base_request, [SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=1)])
        out = apply_operations(pinned.request, [SetPlaceAutoOp(op="set_place_auto", place_id="p1")])
        assert _place(out.request, "p1").day_preferences == []

    def test_set_place_pinned_single_slot(self, base_request):
        out = apply_operations(
            base_request,
            [
                SetPlacePinnedOp(
                    op="set_place_pinned", place_id="p2", day_index=2, preferred_hour_from=10, preferred_hour_to=14
                )
            ],
        )
        slots = _place(out.request, "p2").day_preferences
        assert len(slots) == 1
        assert (slots[0].day_index, slots[0].preferred_hour_from, slots[0].preferred_hour_to) == (2, 10, 14)

    def test_set_place_pinned_preserves_hours_from_existing_same_day(self, base_request):
        first = apply_operations(
            base_request,
            [
                SetPlacePinnedOp(
                    op="set_place_pinned", place_id="p2", day_index=1, preferred_hour_from=8, preferred_hour_to=12
                )
            ],
        )
        again = apply_operations(first.request, [SetPlacePinnedOp(op="set_place_pinned", place_id="p2", day_index=1)])
        slot = _place(again.request, "p2").day_preferences[0]
        assert (slot.preferred_hour_from, slot.preferred_hour_to) == (8, 12)

    def test_set_place_pinned_unknown_place(self, base_request):
        with pytest.raises(PlaceNotInTripError):
            apply_operations(base_request, [SetPlacePinnedOp(op="set_place_pinned", place_id="ghost", day_index=0)])

    def test_set_place_pinned_bad_day(self, base_request):
        with pytest.raises(InvalidDayIndexError):
            apply_operations(base_request, [SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=9)])

    def test_set_place_flexible_two_slots(self, base_request):
        out = apply_operations(
            base_request,
            [SetPlaceFlexibleOp(op="set_place_flexible", place_id="p3", slots=[{"day_index": 0}, {"day_index": 2}])],
        )
        slots = _place(out.request, "p3").day_preferences
        assert sorted(s.day_index for s in slots) == [0, 2]

    def test_set_place_flexible_duplicate_day_rejected(self, base_request):
        with pytest.raises(OperationValidationError):
            apply_operations(
                base_request,
                [SetPlaceFlexibleOp(op="set_place_flexible", place_id="p3", slots=[{"day_index": 1}, {"day_index": 1}])],
            )

    def test_remove_place(self, base_request):
        out = apply_operations(base_request, [RemovePlaceOp(op="remove_place", place_id="p4")])
        assert {p.place_id for p in out.request.places} == {"p1", "p2", "p3"}

    def test_remove_place_below_minimum(self, base_request):
        trimmed = apply_operations(
            base_request,
            [RemovePlaceOp(op="remove_place", place_id="p3"), RemovePlaceOp(op="remove_place", place_id="p4")],
        )
        with pytest.raises(TooFewPlacesError):
            apply_operations(trimmed.request, [RemovePlaceOp(op="remove_place", place_id="p2")])

    def test_remove_unknown_place(self, base_request):
        with pytest.raises(PlaceNotInTripError):
            apply_operations(base_request, [RemovePlaceOp(op="remove_place", place_id="ghost")])


class TestDayWindow:
    def test_hour_only_update_preserves_date(self, base_request):
        out = apply_operations(
            base_request, [UpdateDayWindowOp(op="update_day_window", day_index=1, day_start_hour=8, day_end_hour=22)]
        )
        day = out.request.days[1]
        assert (day.day_start_hour, day.day_end_hour, day.date) == (8, 22, date(2026, 5, 2))

    def test_minute_precision_and_clear(self, base_request):
        with_time = apply_operations(
            base_request,
            [UpdateDayWindowOp(op="update_day_window", day_index=0, day_start_time=time(8, 30))],
        )
        assert with_time.request.days[0].day_start_time == time(8, 30)
        cleared = apply_operations(
            with_time.request, [UpdateDayWindowOp(op="update_day_window", day_index=0, clear_start_time=True)]
        )
        assert cleared.request.days[0].day_start_time is None

    def test_invalid_window_rejected(self, base_request):
        with pytest.raises(TripEditValidationError):
            apply_operations(
                base_request,
                [UpdateDayWindowOp(op="update_day_window", day_index=0, day_start_hour=20, day_end_hour=6)],
            )

    def test_bad_day_index(self, base_request):
        with pytest.raises(InvalidDayIndexError):
            apply_operations(base_request, [UpdateDayWindowOp(op="update_day_window", day_index=5, day_start_hour=8)])


class TestTransport:
    @pytest.mark.parametrize("mode", ["WALK", "DRIVE", "BICYCLE"])
    def test_set_transport_mode(self, base_request, mode):
        out = apply_operations(base_request, [SetTransportModeOp(op="set_transport_mode", mode=mode)])
        assert out.request.transport_mode == TransportMode[mode]


class TestTransfers:
    def test_update_transfer(self, base_request):
        out = apply_operations(
            base_request,
            [UpdateTransferOp(op="update_transfer", date=date(2026, 5, 3), departure_time=time(10, 0))],
        )
        assert out.request.transfers[0].departure_time == time(10, 0)

    def test_remove_transfer(self, base_request):
        out = apply_operations(base_request, [RemoveTransferOp(op="remove_transfer", date=date(2026, 5, 3))])
        assert out.request.transfers == []

    def test_add_transfer_on_existing_date_rejected(self, base_request):
        with pytest.raises(TransferAlreadyExistsError):
            apply_operations(
                base_request,
                [
                    AddTransferOp(
                        op="add_transfer", date=date(2026, 5, 3), departure_time=time(9, 0), arrival_time=time(10, 0)
                    )
                ],
            )

    def test_update_missing_transfer_rejected(self, base_request):
        with pytest.raises(TransferNotFoundError):
            apply_operations(
                base_request,
                [UpdateTransferOp(op="update_transfer", date=date(2026, 5, 2), departure_time=time(9, 0))],
            )

    def test_add_transfer_on_non_transition_day_rejected(self, base_request):
        no_transfer = apply_operations(base_request, [RemoveTransferOp(op="remove_transfer", date=date(2026, 5, 3))])
        with pytest.raises(TripEditValidationError):
            apply_operations(
                no_transfer.request,
                [
                    AddTransferOp(
                        op="add_transfer", date=date(2026, 5, 2), departure_time=time(9, 0), arrival_time=time(10, 0)
                    )
                ],
            )

    def test_add_transfer_arrival_before_departure_rejected(self, base_request):
        no_transfer = apply_operations(base_request, [RemoveTransferOp(op="remove_transfer", date=date(2026, 5, 3))])
        with pytest.raises(TripEditValidationError):
            apply_operations(
                no_transfer.request,
                [
                    AddTransferOp(
                        op="add_transfer", date=date(2026, 5, 3), departure_time=time(14, 0), arrival_time=time(10, 0)
                    )
                ],
            )


class TestAccommodationSelectors:
    def test_remove_then_update_hits_original_stay(self, base_payload):
        from src.optimizer.solver.models import MultiDayRequest

        # 3 stays in check-in order: Tokyo(0) 05-01, Kyoto(1) 05-03, Osaka(2) 05-05
        base_payload["days"].append({"date": "2026-05-04"})
        base_payload["days"].append({"date": "2026-05-05"})
        base_payload["accommodations"] = [
            {"name": "Tokyo", "lat": 0.0, "lng": 0.0, "check_in_date": "2026-05-01", "check_out_date": "2026-05-03"},
            {"name": "Kyoto", "lat": 0.0, "lng": 0.0, "check_in_date": "2026-05-03", "check_out_date": "2026-05-05"},
            {"name": "Osaka", "lat": 0.0, "lng": 0.0, "check_in_date": "2026-05-05", "check_out_date": "2026-05-07"},
        ]
        base_payload["transfers"] = []
        request = MultiDayRequest.model_validate(base_payload)

        out = apply_operations(
            request,
            [
                RemoveAccommodationOp(op="remove_accommodation", stay_index=0),
                UpdateAccommodationOp(op="update_accommodation", stay_index=1, name="Kyoto Renamed"),
            ],
        )
        names = {a.name for a in out.request.accommodations}
        assert names == {"Kyoto Renamed", "Osaka"}

    def test_two_updates_same_stay_conflict(self, base_request):
        with pytest.raises(AccommodationSelectorConflictError):
            apply_operations(
                base_request,
                [
                    UpdateAccommodationOp(op="update_accommodation", stay_index=0, name="X"),
                    UpdateAccommodationOp(op="update_accommodation", stay_index=0, check_in_from=time(14, 0)),
                ],
            )

    def test_target_newly_added_stay_rejected(self, base_request):
        with pytest.raises(Exception) as excinfo:
            apply_operations(
                base_request,
                [
                    AddAccommodationOp(
                        op="add_accommodation",
                        name="C",
                        lat=0.0,
                        lng=0.0,
                        check_in_date=date(2026, 5, 5),
                        check_out_date=date(2026, 5, 7),
                    ),
                    UpdateAccommodationOp(op="update_accommodation", stay_index=2, name="nope"),
                ],
            )
        from src.trips.editing.errors import TripEditError

        assert isinstance(excinfo.value, TripEditError)


class TestAccommodationMutation:
    def test_update_accommodation_patches_named_fields(self, base_request):
        out = apply_operations(
            base_request,
            [UpdateAccommodationOp(op="update_accommodation", stay_index=0, check_in_from=time(14, 0))],
        )
        stays = sorted(out.request.accommodations, key=lambda s: s.check_in_date)
        assert stays[0].check_in_from == time(14, 0)
        assert stays[0].name == "Hotel A"

    def test_update_accommodation_clear_flag(self, base_request):
        out = apply_operations(
            base_request,
            [UpdateAccommodationOp(op="update_accommodation", stay_index=0, clear_check_in_from=True)],
        )
        stays = sorted(out.request.accommodations, key=lambda s: s.check_in_date)
        assert stays[0].check_in_from is None

    def test_remove_accommodation_drops_orphaned_transfer(self, base_request):
        out = apply_operations(base_request, [RemoveAccommodationOp(op="remove_accommodation", stay_index=1)])
        assert out.removed_transfer_dates == [date(2026, 5, 3)]
        assert out.request.transfers == []

    def test_add_accommodation_overlap_rejected(self, base_request):
        with pytest.raises(TripEditValidationError):
            apply_operations(
                base_request,
                [
                    AddAccommodationOp(
                        op="add_accommodation",
                        name="Overlaps A",
                        lat=0.0,
                        lng=0.0,
                        check_in_date=date(2026, 5, 1),
                        check_out_date=date(2026, 5, 2),
                    )
                ],
            )

    def test_add_accommodation_check_out_before_check_in_rejected(self, base_request):
        with pytest.raises(TripEditValidationError):
            apply_operations(
                base_request,
                [
                    AddAccommodationOp(
                        op="add_accommodation",
                        name="Bad",
                        lat=0.0,
                        lng=0.0,
                        check_in_date=date(2026, 5, 20),
                        check_out_date=date(2026, 5, 19),
                    )
                ],
            )


class TestBatchAndPreservation:
    def test_batch_applies_all_operations(self, base_request):
        out = apply_operations(
            base_request,
            [
                SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=2),
                UpdateDayWindowOp(op="update_day_window", day_index=2, day_start_hour=8),
            ],
        )
        assert _place(out.request, "p1").day_preferences[0].day_index == 2
        assert out.request.days[2].day_start_hour == 8

    def test_unrelated_edit_preserves_everything_else(self, base_request):
        out = apply_operations(base_request, [SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=0)])
        assert len(out.request.accommodations) == 2
        assert len(out.request.transfers) == 1
        assert out.request.transport_mode == TransportMode.WALK
        assert [p.place_id for p in out.request.places] == ["p1", "p2", "p3", "p4"]

    def test_later_day_window_op_wins(self, base_request):
        out = apply_operations(
            base_request,
            [
                UpdateDayWindowOp(op="update_day_window", day_index=0, day_start_hour=7),
                UpdateDayWindowOp(op="update_day_window", day_index=0, day_start_hour=10),
            ],
        )
        assert out.request.days[0].day_start_hour == 10

    def test_input_request_not_mutated(self, base_request):
        before = base_request.model_dump(mode="json")
        apply_operations(base_request, [SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=2)])
        assert base_request.model_dump(mode="json") == before
