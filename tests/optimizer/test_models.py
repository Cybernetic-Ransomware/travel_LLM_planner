"""Unit tests for optimizer models: TransportMode, MatrixEntry, DistanceMatrix, OptimizeRequest."""

from datetime import UTC, date, datetime, timezone

import pytest
from pydantic import ValidationError

from src.accommodations.models import AccommodationStay
from src.optimizer.matrix.models import DistanceMatrix, MatrixEntry, TransportMode
from src.optimizer.solver.models import DayConfig, MultiDayRequest, OptimizeRequest, PlaceDayPreference


@pytest.mark.unit
class TestTransportMode:
    def test_values_are_strings(self):
        assert TransportMode.WALK == "WALK"
        assert TransportMode.DRIVE == "DRIVE"
        assert TransportMode.BICYCLE == "BICYCLE"
        assert TransportMode.TRANSIT == "TRANSIT"

    def test_all_four_modes_exist(self):
        assert len(TransportMode) == 4


@pytest.mark.unit
class TestMatrixEntry:
    def test_construction(self):
        entry = MatrixEntry("a", "b", 1500, 300)
        assert entry.origin_id == "a"
        assert entry.dest_id == "b"
        assert entry.distance_m == 1500
        assert entry.duration_s == 300

    def test_repr(self):
        entry = MatrixEntry("a", "b", 100, 60)
        assert "a" in repr(entry)
        assert "b" in repr(entry)


@pytest.mark.unit
class TestDistanceMatrix:
    @pytest.fixture
    def matrix(self):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        entries = {
            ("p1", "p2"): MatrixEntry("p1", "p2", 1000, 120),
            ("p2", "p1"): MatrixEntry("p2", "p1", 1000, 130),
            ("p1", "p3"): MatrixEntry("p1", "p3", 2000, 240),
            ("p3", "p1"): MatrixEntry("p3", "p1", 2000, 250),
            ("p2", "p3"): MatrixEntry("p2", "p3", 1500, 180),
            ("p3", "p2"): MatrixEntry("p3", "p2", 1500, 190),
        }
        return DistanceMatrix(entries, TransportMode.WALK, now)

    def test_get_existing_pair(self, matrix):
        entry = matrix.get("p1", "p2")
        assert entry is not None
        assert entry.duration_s == 120

    def test_get_missing_pair_returns_none(self, matrix):
        assert matrix.get("p1", "p99") is None

    def test_duration_s(self, matrix):
        assert matrix.duration_s("p2", "p1") == 130

    def test_duration_s_missing_raises_key_error(self, matrix):
        with pytest.raises(KeyError):
            matrix.duration_s("p1", "p99")

    def test_distance_m(self, matrix):
        assert matrix.distance_m("p1", "p3") == 2000

    def test_len(self, matrix):
        assert len(matrix) == 6

    def test_asymmetry(self, matrix):
        assert matrix.duration_s("p1", "p2") != matrix.duration_s("p2", "p1")

    def test_transport_mode_stored(self, matrix):
        assert matrix.transport_mode == TransportMode.WALK


@pytest.mark.unit
class TestOptimizeRequestPlaceIdsLimit:
    def test_accepts_fifty_places(self):
        request = OptimizeRequest(place_ids=[f"p{i}" for i in range(50)])
        assert len(request.place_ids) == 50

    def test_rejects_more_than_fifty_places(self):
        with pytest.raises(ValidationError, match="place_ids"):
            OptimizeRequest(place_ids=[f"p{i}" for i in range(51)])

    def test_accepts_single_place(self):
        request = OptimizeRequest(place_ids=["p1"])
        assert len(request.place_ids) == 1

    def test_rejects_empty_list(self):
        with pytest.raises(ValidationError, match="place_ids"):
            OptimizeRequest(place_ids=[])


@pytest.mark.unit
class TestOptimizeRequestEndLocation:
    def test_neither_end_field_set_by_default(self):
        request = OptimizeRequest(place_ids=["p1", "p2"])
        assert request.end_lat is None
        assert request.end_lng is None

    def test_both_end_fields_accepted(self):
        request = OptimizeRequest(place_ids=["p1", "p2"], end_lat=50.0, end_lng=20.0)
        assert request.end_lat == 50.0
        assert request.end_lng == 20.0

    def test_end_lat_without_lng_rejected(self):
        with pytest.raises(ValidationError, match="end_lat"):
            OptimizeRequest(place_ids=["p1", "p2"], end_lat=50.0)

    def test_end_lng_without_lat_rejected(self):
        with pytest.raises(ValidationError, match="end_lat"):
            OptimizeRequest(place_ids=["p1", "p2"], end_lng=20.0)

    def test_start_and_end_independent(self):
        """A valid start pair alongside an incomplete end pair must still fail."""
        with pytest.raises(ValidationError, match="end_lat"):
            OptimizeRequest(place_ids=["p1", "p2"], start_lat=1.0, start_lng=2.0, end_lat=3.0)


@pytest.mark.unit
class TestDayConfigAnchors:
    def test_start_and_end_optional_by_default(self):
        cfg = DayConfig(date=date(2026, 6, 1))
        assert cfg.start_lat is None
        assert cfg.end_lat is None

    def test_full_anchors_accepted(self):
        cfg = DayConfig(date=date(2026, 6, 1), start_lat=1.0, start_lng=2.0, end_lat=3.0, end_lng=4.0)
        assert cfg.start_lat == 1.0
        assert cfg.end_lat == 3.0

    def test_start_lat_without_lng_rejected(self):
        with pytest.raises(ValidationError, match="start_lat"):
            DayConfig(date=date(2026, 6, 1), start_lat=1.0)

    def test_end_lat_without_lng_rejected(self):
        with pytest.raises(ValidationError, match="end_lat"):
            DayConfig(date=date(2026, 6, 1), end_lat=1.0)

    def test_start_and_end_validated_independently(self):
        """A valid start pair with an incomplete end pair must still fail."""
        with pytest.raises(ValidationError, match="end_lat"):
            DayConfig(date=date(2026, 6, 1), start_lat=1.0, start_lng=2.0, end_lat=3.0)


@pytest.mark.unit
class TestMultiDayRequestEndLocation:
    @staticmethod
    def _base_kwargs() -> dict:
        return {
            "days": [DayConfig(date=date(2026, 6, 1))],
            "places": [PlaceDayPreference(place_id="p1"), PlaceDayPreference(place_id="p2")],
        }

    def test_neither_end_field_set_by_default(self):
        request = MultiDayRequest(**self._base_kwargs())
        assert request.end_lat is None
        assert request.end_lng is None

    def test_both_end_fields_accepted(self):
        request = MultiDayRequest(**self._base_kwargs(), end_lat=1.0, end_lng=2.0)
        assert request.end_lat == 1.0
        assert request.end_lng == 2.0

    def test_end_lat_without_lng_rejected(self):
        with pytest.raises(ValidationError, match="end_lat"):
            MultiDayRequest(**self._base_kwargs(), end_lat=1.0)


@pytest.mark.unit
class TestMultiDayRequestAccommodations:
    @staticmethod
    def _base_kwargs() -> dict:
        return {
            "days": [DayConfig(date=date(2026, 10, 5))],
            "places": [PlaceDayPreference(place_id="p1"), PlaceDayPreference(place_id="p2")],
        }

    @staticmethod
    def _stay(name: str, check_in: date, check_out: date) -> AccommodationStay:
        return AccommodationStay(name=name, lat=35.0, lng=139.0, check_in_date=check_in, check_out_date=check_out)

    def test_default_accommodations_is_empty_list(self):
        request = MultiDayRequest(**self._base_kwargs())
        assert request.accommodations == []

    def test_touching_stays_are_valid(self):
        stays = [
            self._stay("Tokyo Hotel", date(2026, 10, 5), date(2026, 10, 10)),
            self._stay("Kyoto Hotel", date(2026, 10, 10), date(2026, 10, 14)),
        ]
        request = MultiDayRequest(**self._base_kwargs(), accommodations=stays)
        assert len(request.accommodations) == 2

    def test_overlapping_stays_rejected(self):
        stays = [
            self._stay("Tokyo Hotel", date(2026, 10, 5), date(2026, 10, 11)),
            self._stay("Kyoto Hotel", date(2026, 10, 10), date(2026, 10, 14)),
        ]
        with pytest.raises(ValidationError, match="overlap"):
            MultiDayRequest(**self._base_kwargs(), accommodations=stays)

    def test_gap_between_stays_is_valid(self):
        stays = [
            self._stay("Tokyo Hotel", date(2026, 10, 5), date(2026, 10, 10)),
            self._stay("Kyoto Hotel", date(2026, 10, 11), date(2026, 10, 14)),
        ]
        request = MultiDayRequest(**self._base_kwargs(), accommodations=stays)
        assert len(request.accommodations) == 2
