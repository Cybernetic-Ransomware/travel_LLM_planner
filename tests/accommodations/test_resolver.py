"""Unit tests for resolve_day_anchors — pure calendar-date semantics, no solver knowledge."""

from __future__ import annotations

from datetime import date

import pytest

from src.accommodations.models import AccommodationStay
from src.accommodations.resolver import resolve_day_anchors


def _stay(name: str, check_in: date, check_out: date) -> AccommodationStay:
    return AccommodationStay(name=name, lat=35.0, lng=139.0, check_in_date=check_in, check_out_date=check_out)


TOKYO = _stay("Tokyo Hotel", date(2026, 10, 5), date(2026, 10, 10))
KYOTO = _stay("Kyoto Hotel", date(2026, 10, 10), date(2026, 10, 14))
_TRIP_DAYS = [date(2026, 10, d) for d in range(5, 15)]


@pytest.mark.unit
class TestResolveDayAnchors:
    def test_ordinary_day_resolves_same_stay_for_start_and_end(self):
        [anchors] = resolve_day_anchors([date(2026, 10, 7)], [TOKYO, KYOTO])
        assert anchors.start is TOKYO
        assert anchors.end is TOKYO

    def test_isolated_check_in_day_has_no_start(self):
        """Only Kyoto (10-14) exists: on its own check-in day (10.10) nobody has a START yet."""
        [anchors] = resolve_day_anchors([date(2026, 10, 10)], [KYOTO])
        assert anchors.start is None
        assert anchors.end is KYOTO

    def test_check_out_day_has_start_only_no_end(self):
        [anchors] = resolve_day_anchors([date(2026, 10, 14)], [TOKYO, KYOTO])
        assert anchors.start is KYOTO
        assert anchors.end is None

    def test_changeover_day_resolves_two_different_stay_objects(self):
        [anchors] = resolve_day_anchors([date(2026, 10, 10)], [TOKYO, KYOTO])
        assert anchors.start is not None
        assert anchors.end is not None
        assert anchors.start is not anchors.end

    def test_first_day_of_trip_has_no_start(self):
        [anchors] = resolve_day_anchors([date(2026, 10, 5)], [TOKYO, KYOTO])
        assert anchors.start is None
        assert anchors.end is TOKYO

    def test_last_day_of_trip_has_no_end(self):
        [anchors] = resolve_day_anchors([date(2026, 10, 14)], [TOKYO, KYOTO])
        assert anchors.end is None

    def test_checkout_day_before_gap_has_start_but_no_end(self):
        tokyo = _stay("Tokyo Hotel", date(2026, 10, 5), date(2026, 10, 10))
        kyoto = _stay("Kyoto Hotel", date(2026, 10, 11), date(2026, 10, 14))
        [anchors] = resolve_day_anchors([date(2026, 10, 10)], [tokyo, kyoto])
        assert anchors.start is tokyo
        assert anchors.end is None

    def test_day_fully_inside_a_gap_resolves_to_no_anchor_either_side(self):
        """A two-night gap (Tokyo checks out 10.10, Kyoto checks in 12.10): 11.10 touches neither stay."""
        tokyo = _stay("Tokyo Hotel", date(2026, 10, 5), date(2026, 10, 10))
        kyoto = _stay("Kyoto Hotel", date(2026, 10, 12), date(2026, 10, 14))
        [anchors] = resolve_day_anchors([date(2026, 10, 11)], [tokyo, kyoto])
        assert anchors.start is None
        assert anchors.end is None

    def test_no_accommodations_resolves_all_days_to_none(self):
        results = resolve_day_anchors(_TRIP_DAYS, [])
        assert all(a.start is None and a.end is None for a in results)

    def test_stay_outside_requested_days_has_no_effect(self):
        far_away = _stay("Osaka Hotel", date(2027, 1, 1), date(2027, 1, 5))
        [anchors] = resolve_day_anchors([date(2026, 10, 7)], [TOKYO, KYOTO, far_away])
        assert anchors.start is TOKYO
        assert anchors.end is TOKYO

    def test_full_trip_matches_expected_table(self):
        results = resolve_day_anchors(_TRIP_DAYS, [TOKYO, KYOTO])
        by_date = dict(zip(_TRIP_DAYS, results, strict=True))

        assert by_date[date(2026, 10, 5)].start is None
        assert by_date[date(2026, 10, 5)].end is TOKYO
        for d in range(6, 10):
            assert by_date[date(2026, 10, d)].start is TOKYO
            assert by_date[date(2026, 10, d)].end is TOKYO
        assert by_date[date(2026, 10, 10)].start is TOKYO
        assert by_date[date(2026, 10, 10)].end is KYOTO
        for d in range(11, 14):
            assert by_date[date(2026, 10, d)].start is KYOTO
            assert by_date[date(2026, 10, d)].end is KYOTO
        assert by_date[date(2026, 10, 14)].start is KYOTO
        assert by_date[date(2026, 10, 14)].end is None

    def test_two_stays_with_same_name_are_disambiguated_by_identity(self):
        first = _stay("Business Hotel", date(2026, 10, 5), date(2026, 10, 8))
        second = _stay("Business Hotel", date(2026, 10, 8), date(2026, 10, 12))
        [anchors] = resolve_day_anchors([date(2026, 10, 8)], [first, second])
        assert anchors.start is first
        assert anchors.end is second
        assert anchors.start is not anchors.end
