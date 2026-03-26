"""Unit tests for PlacePatch and PlaceOut Pydantic models."""

import pytest
from bson import ObjectId
from pydantic import ValidationError

from src.gmaps.models import PlaceOut, PlacePatch


@pytest.mark.unit
class TestPlacePatch:
    def test_valid_preferences(self):
        patch = PlacePatch(preferred_hour_from=9, preferred_hour_to=17, visit_duration_min=60)
        assert patch.preferred_hour_from == 9
        assert patch.preferred_hour_to == 17
        assert patch.visit_duration_min == 60

    def test_empty_patch_is_valid(self):
        patch = PlacePatch()
        assert patch.preferred_hour_from is None
        assert patch.preferred_hour_to is None
        assert patch.visit_duration_min is None
        assert patch.skipped is None

    def test_partial_patch_only_skipped(self):
        patch = PlacePatch(skipped=True)
        assert patch.skipped is True
        assert patch.preferred_hour_from is None

    def test_hour_above_range(self):
        with pytest.raises(ValidationError):
            PlacePatch(preferred_hour_from=24)

    def test_hour_below_range(self):
        with pytest.raises(ValidationError):
            PlacePatch(preferred_hour_to=-1)

    def test_hour_range_inverted(self):
        with pytest.raises(ValidationError):
            PlacePatch(preferred_hour_from=17, preferred_hour_to=9)

    def test_hour_range_equal(self):
        with pytest.raises(ValidationError):
            PlacePatch(preferred_hour_from=9, preferred_hour_to=9)

    def test_hour_boundary_values(self):
        patch = PlacePatch(preferred_hour_from=0, preferred_hour_to=23)
        assert patch.preferred_hour_from == 0
        assert patch.preferred_hour_to == 23

    def test_duration_zero(self):
        with pytest.raises(ValidationError):
            PlacePatch(visit_duration_min=0)

    def test_duration_negative(self):
        with pytest.raises(ValidationError):
            PlacePatch(visit_duration_min=-30)

    def test_duration_minimum_valid(self):
        patch = PlacePatch(visit_duration_min=1)
        assert patch.visit_duration_min == 1


@pytest.mark.unit
class TestPlaceOut:
    def test_object_id_coercion(self):
        oid = ObjectId()
        place = PlaceOut.model_validate({"_id": oid, "skipped": False})
        assert place.id == str(oid)

    def test_string_id_passthrough(self):
        place = PlaceOut.model_validate({"_id": "abc123", "skipped": False})
        assert place.id == "abc123"

    def test_skipped_defaults_to_false(self):
        place = PlaceOut.model_validate({"_id": "abc123"})
        assert place.skipped is False

    def test_optional_fields_default_to_none(self):
        place = PlaceOut.model_validate({"_id": "abc123"})
        assert place.name is None
        assert place.address is None
        assert place.lat is None
        assert place.opening_hours is None
        assert place.preferred_hour_from is None
        assert place.visit_duration_min is None

    def test_opening_hours_populated_from_document(self):
        hours = {"periods": [{"open": {"day": 1, "hour": 9}, "close": {"day": 1, "hour": 18}}]}
        place = PlaceOut.model_validate({"_id": "abc123", "opening_hours": hours})
        assert place.opening_hours == hours
