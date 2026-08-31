import json

import pytest

from src.trips.models import (
    SCHEMA_VERSION,
    MultiDaySaveTripRequest,
    SingleDaySaveTripRequest,
)
from src.trips.snapshot import (
    build_snapshot,
    canonical_json,
    detail_from_snapshot,
    display_fields,
    load_snapshot,
    snapshot_hash,
)


def _single_day() -> SingleDaySaveTripRequest:
    return SingleDaySaveTripRequest(
        name="Weekend in Kraków — café ☕",
        date="2026-07-04",
        optimizer_request={
            "place_ids": ["p1", "p2"],
            "transport_mode": "WALK",
            "day_start_hour": 9,
            "day_end_hour": 21,
        },
        optimizer_response={
            "steps": [],
            "total_travel_time_s": 0,
            "total_visit_time_min": 0,
            "total_wait_min": 0,
            "transport_mode": "WALK",
            "skipped": [],
        },
    )


def _multi_day() -> MultiDaySaveTripRequest:
    return MultiDaySaveTripRequest(
        name="Kraków then Warsaw",
        multi_day_request={
            "days": [{"date": "2026-07-03"}, {"date": "2026-07-01"}, {"date": "2026-07-02"}],
            "places": [
                {"place_id": "p1", "day_preferences": []},
                {"place_id": "p2", "day_preferences": []},
            ],
            "transport_mode": "WALK",
            "accommodations": [
                {
                    "name": "Hotel A",
                    "lat": 50.06,
                    "lng": 19.94,
                    "check_in_date": "2026-07-01",
                    "check_out_date": "2026-07-03",
                }
            ],
            "transfers": [],
        },
        multi_day_response={"days": [], "transport_mode": "WALK", "unassigned": []},
    )


@pytest.mark.unit
class TestCanonicalJson:
    def test_key_order_independent(self):
        a = canonical_json({"b": 1, "a": {"y": 2, "x": 3}})
        b = canonical_json({"a": {"x": 3, "y": 2}, "b": 1})
        assert a == b

    def test_no_whitespace(self):
        assert canonical_json({"a": 1, "b": 2}) == '{"a":1,"b":2}'

    def test_non_ascii_preserved(self):
        assert "Kraków" in canonical_json({"name": "Kraków"})

    def test_round_trips_losslessly(self):
        payload = {"name": "Kraków ☕", "n": 3, "nested": {"z": [1, 2, 3]}}
        assert json.loads(canonical_json(payload)) == payload


@pytest.mark.unit
class TestSnapshotHash:
    def test_stable_across_calls(self):
        canonical = canonical_json({"a": 1})
        assert snapshot_hash(canonical) == snapshot_hash(canonical)

    def test_changes_with_content(self):
        assert snapshot_hash(canonical_json({"a": 1})) != snapshot_hash(canonical_json({"a": 2}))


@pytest.mark.unit
class TestBuildSnapshot:
    def test_excludes_expected_revision_includes_schema_version(self):
        req = _single_day()
        req.expected_revision = 99
        canonical, _digest, _display = build_snapshot(req)
        payload = json.loads(canonical)
        assert "expected_revision" not in payload
        assert payload["schema_version"] == SCHEMA_VERSION

    def test_single_day_display_fields(self):
        _canonical, _digest, display = build_snapshot(_single_day())
        assert (display.start_date, display.end_date, display.num_days) == ("2026-07-04", "2026-07-04", 1)

    def test_multi_day_display_fields_span_min_max(self):
        _canonical, _digest, display = build_snapshot(_multi_day())
        assert (display.start_date, display.end_date, display.num_days) == ("2026-07-01", "2026-07-03", 3)

    def test_hash_is_order_independent_for_equivalent_requests(self):
        # Two requests built from differently-ordered dicts must hash identically.
        r1 = _single_day()
        r2 = SingleDaySaveTripRequest(
            date="2026-07-04",
            name="Weekend in Kraków — café ☕",
            optimizer_response={
                "skipped": [],
                "transport_mode": "WALK",
                "total_wait_min": 0,
                "total_visit_time_min": 0,
                "total_travel_time_s": 0,
                "steps": [],
            },
            optimizer_request={
                "day_end_hour": 21,
                "day_start_hour": 9,
                "transport_mode": "WALK",
                "place_ids": ["p1", "p2"],
            },
        )
        assert build_snapshot(r1)[1] == build_snapshot(r2)[1]


@pytest.mark.unit
class TestRoundTrip:
    def test_single_day_snapshot_round_trips_to_detail(self):
        canonical, _digest, _display = build_snapshot(_single_day())
        payload = load_snapshot(canonical)
        detail = detail_from_snapshot("id1", payload, revision=3, created_at="2026-01-01T00:00:00", updated_at=None)
        assert detail.plan_type == "SINGLE_DAY"
        assert detail.name == "Weekend in Kraków — café ☕"
        assert detail.revision == 3
        assert detail.selected_place_ids == ["p1", "p2"]

    def test_multi_day_snapshot_round_trips_to_detail(self):
        canonical, _digest, _display = build_snapshot(_multi_day())
        payload = load_snapshot(canonical)
        detail = detail_from_snapshot("id2", payload, revision=1, created_at="2026-01-01T00:00:00", updated_at="x")
        assert detail.plan_type == "MULTI_DAY"
        assert detail.start_date == "2026-07-01"
        assert detail.end_date == "2026-07-03"
        assert detail.num_days == 3

    def test_load_snapshot_rejects_unknown_compression(self):
        with pytest.raises(ValueError, match="compression"):
            load_snapshot("{}", "zlib")

    def test_display_fields_helper_matches_build_snapshot(self):
        canonical, _digest, display = build_snapshot(_multi_day())
        assert display_fields(load_snapshot(canonical)) == display
