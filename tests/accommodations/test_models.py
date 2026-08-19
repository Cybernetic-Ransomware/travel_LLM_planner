"""Unit tests for AccommodationStay and validate_no_stay_overlaps."""

from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from src.accommodations.models import AccommodationStay, validate_no_stay_overlaps


def _stay(name: str = "Hotel", check_in: date = date(2026, 10, 5), check_out: date = date(2026, 10, 10), **kwargs):
    return AccommodationStay(name=name, lat=35.0, lng=139.0, check_in_date=check_in, check_out_date=check_out, **kwargs)


@pytest.mark.unit
class TestAccommodationStayValidation:
    def test_valid_stay_constructs(self):
        stay = _stay()
        assert stay.name == "Hotel"
        assert stay.lat == 35.0
        assert stay.lng == 139.0

    def test_optional_time_fields_default_to_none(self):
        stay = _stay()
        assert stay.check_in_from is None
        assert stay.check_out_by is None

    def test_time_fields_accepted(self):
        stay = _stay(check_in_from=time(15, 0), check_out_by=time(10, 0))
        assert stay.check_in_from == time(15, 0)
        assert stay.check_out_by == time(10, 0)

    def test_check_out_equal_check_in_rejected(self):
        with pytest.raises(ValidationError, match="check_out_date"):
            _stay(check_in=date(2026, 10, 5), check_out=date(2026, 10, 5))

    def test_check_out_before_check_in_rejected(self):
        with pytest.raises(ValidationError, match="check_out_date"):
            _stay(check_in=date(2026, 10, 10), check_out=date(2026, 10, 5))

    def test_lat_above_range_rejected(self):
        with pytest.raises(ValidationError):
            AccommodationStay(
                name="Hotel", lat=91.0, lng=0.0, check_in_date=date(2026, 10, 5), check_out_date=date(2026, 10, 6)
            )

    def test_lat_below_range_rejected(self):
        with pytest.raises(ValidationError):
            AccommodationStay(
                name="Hotel", lat=-91.0, lng=0.0, check_in_date=date(2026, 10, 5), check_out_date=date(2026, 10, 6)
            )

    def test_lng_above_range_rejected(self):
        with pytest.raises(ValidationError):
            AccommodationStay(
                name="Hotel", lat=0.0, lng=181.0, check_in_date=date(2026, 10, 5), check_out_date=date(2026, 10, 6)
            )

    def test_lng_below_range_rejected(self):
        with pytest.raises(ValidationError):
            AccommodationStay(
                name="Hotel", lat=0.0, lng=-181.0, check_in_date=date(2026, 10, 5), check_out_date=date(2026, 10, 6)
            )


@pytest.mark.unit
class TestValidateNoStayOverlaps:
    def test_empty_list_is_valid(self):
        validate_no_stay_overlaps([])

    def test_single_stay_is_valid(self):
        validate_no_stay_overlaps([_stay()])

    def test_touching_stays_are_valid(self):
        stays = [
            _stay("Tokyo", date(2026, 10, 5), date(2026, 10, 10)),
            _stay("Kyoto", date(2026, 10, 10), date(2026, 10, 14)),
        ]
        validate_no_stay_overlaps(stays)

    def test_gap_between_stays_is_valid(self):
        stays = [
            _stay("Tokyo", date(2026, 10, 5), date(2026, 10, 10)),
            _stay("Kyoto", date(2026, 10, 11), date(2026, 10, 14)),
        ]
        validate_no_stay_overlaps(stays)

    def test_overlapping_stays_rejected(self):
        stays = [
            _stay("Tokyo", date(2026, 10, 5), date(2026, 10, 11)),
            _stay("Kyoto", date(2026, 10, 10), date(2026, 10, 14)),
        ]
        with pytest.raises(ValueError, match="overlap"):
            validate_no_stay_overlaps(stays)

    def test_overlap_detected_regardless_of_input_order(self):
        stays = [
            _stay("Kyoto", date(2026, 10, 10), date(2026, 10, 14)),
            _stay("Tokyo", date(2026, 10, 5), date(2026, 10, 11)),
        ]
        with pytest.raises(ValueError, match="overlap"):
            validate_no_stay_overlaps(stays)
