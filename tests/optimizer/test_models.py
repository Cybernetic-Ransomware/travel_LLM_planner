"""Unit tests for optimizer matrix models: TransportMode, MatrixEntry, DistanceMatrix."""

from datetime import UTC, datetime, timezone

import pytest

from src.optimizer.matrix.models import DistanceMatrix, MatrixEntry, TransportMode


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
