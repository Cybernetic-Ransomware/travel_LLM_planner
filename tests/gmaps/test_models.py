"""Unit tests for PlaceCreate, PlacePatch, and PlaceOut Pydantic models."""

import pytest
from bson import ObjectId
from pydantic import ValidationError

from src.gmaps.models import PlaceCreate, PlaceOut, PlacePatch


@pytest.mark.unit
class TestPlaceCreate:
    def test_valid_minimal_creates_instance(self):
        place = PlaceCreate(name="Wawel Castle")
        assert place.name == "Wawel Castle"
        assert place.address is None
        assert place.lat is None
        assert place.lng is None
        assert place.visit_duration_min is None
        assert place.preferred_hour_from is None
        assert place.preferred_hour_to is None

    def test_valid_full_creates_instance(self):
        place = PlaceCreate(
            name="Wawel Castle",
            address="Wawel 5, Krakow",
            lat=50.054,
            lng=19.935,
            visit_duration_min=120,
            preferred_hour_from=9,
            preferred_hour_to=17,
        )
        assert place.name == "Wawel Castle"
        assert place.visit_duration_min == 120
        assert place.preferred_hour_from == 9
        assert place.preferred_hour_to == 17

    def test_name_required(self):
        with pytest.raises(ValidationError):
            PlaceCreate()

    def test_hour_above_range(self):
        with pytest.raises(ValidationError):
            PlaceCreate(name="Place", preferred_hour_from=24)

    def test_hour_below_range(self):
        with pytest.raises(ValidationError):
            PlaceCreate(name="Place", preferred_hour_to=-1)

    def test_hour_range_inverted(self):
        with pytest.raises(ValidationError):
            PlaceCreate(name="Place", preferred_hour_from=17, preferred_hour_to=9)

    def test_hour_range_equal(self):
        with pytest.raises(ValidationError):
            PlaceCreate(name="Place", preferred_hour_from=9, preferred_hour_to=9)

    def test_hour_boundary_values(self):
        place = PlaceCreate(name="Place", preferred_hour_from=0, preferred_hour_to=23)
        assert place.preferred_hour_from == 0
        assert place.preferred_hour_to == 23

    def test_duration_zero(self):
        with pytest.raises(ValidationError):
            PlaceCreate(name="Place", visit_duration_min=0)

    def test_duration_negative(self):
        with pytest.raises(ValidationError):
            PlaceCreate(name="Place", visit_duration_min=-30)

    def test_duration_minimum_valid(self):
        place = PlaceCreate(name="Place", visit_duration_min=1)
        assert place.visit_duration_min == 1

    def test_only_hour_from_without_hour_to_is_valid(self):
        place = PlaceCreate(name="Place", preferred_hour_from=10)
        assert place.preferred_hour_from == 10
        assert place.preferred_hour_to is None

    @pytest.mark.parametrize("priority", ["must_see", "normal", "optional"])
    def test_priority_accepts_literals(self, priority):
        place = PlaceCreate(name="Place", priority=priority)
        assert place.priority == priority

    def test_priority_defaults_to_none(self):
        place = PlaceCreate(name="Place")
        assert place.priority is None

    def test_priority_rejects_invalid_value(self):
        with pytest.raises(ValidationError):
            PlaceCreate(name="Place", priority="high")


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

    @pytest.mark.parametrize("priority", ["must_see", "normal", "optional"])
    def test_priority_accepts_literals(self, priority):
        patch = PlacePatch(priority=priority)
        assert patch.priority == priority

    def test_priority_rejects_invalid_value(self):
        with pytest.raises(ValidationError):
            PlacePatch(priority="high")

    def test_explicit_null_priority_is_valid_and_marked_set(self):
        patch = PlacePatch(priority=None)
        fields = patch.model_dump(exclude_unset=True)
        assert fields == {"priority": None}

    def test_omitted_fields_excluded_from_unset_dump(self):
        patch = PlacePatch(visit_duration_min=45)
        fields = patch.model_dump(exclude_unset=True)
        assert fields == {"visit_duration_min": 45}

    def test_explicit_null_skipped_rejected(self):
        with pytest.raises(ValidationError):
            PlacePatch(skipped=None)

    def test_omitted_skipped_is_valid(self):
        patch = PlacePatch(preferred_hour_from=9)
        assert patch.skipped is None
        assert "skipped" not in patch.model_fields_set


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

    def test_priority_defaults_to_normal(self):
        place = PlaceOut.model_validate({"_id": ObjectId()})
        assert place.priority == "normal"

    def test_priority_populated_from_document(self):
        place = PlaceOut.model_validate({"_id": "abc123", "priority": "must_see"})
        assert place.priority == "must_see"
