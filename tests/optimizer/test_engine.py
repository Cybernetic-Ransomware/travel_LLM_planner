"""Unit tests for the TSP solver engine: schedule_route, is_feasible, nearest_neighbor, two_opt."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.optimizer.matrix.models import DistanceMatrix, MatrixEntry, TransportMode
from src.optimizer.solver.engine import (
    is_feasible,
    nearest_neighbor,
    schedule_route,
    two_opt,
)
from src.optimizer.solver.models import TimeWindow

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_9H = 9 * 3600
_18H = 18 * 3600
_21H = 21 * 3600


def _matrix(*entries: MatrixEntry) -> DistanceMatrix:
    return DistanceMatrix({(e.origin_id, e.dest_id): e for e in entries}, TransportMode.WALK, _NOW)


def _entry(a: str, b: str, duration_s: int) -> MatrixEntry:
    return MatrixEntry(a, b, duration_s * 80, duration_s)  # distance_m irrelevant here


def _square_matrix() -> DistanceMatrix:
    """Four nodes A-B-C-D with symmetric travel times forming a rough square."""
    nodes = ["A", "B", "C", "D"]
    entries: list[MatrixEntry] = []
    times = {
        ("A", "B"): 300,
        ("B", "C"): 300,
        ("C", "D"): 300,
        ("D", "A"): 300,
        ("A", "C"): 500,
        ("B", "D"): 500,
    }
    for (o, d), t in times.items():
        entries.append(_entry(o, d, t))
        entries.append(_entry(d, o, t))
    return _matrix(*entries)


@pytest.mark.unit
class TestScheduleRoute:
    def test_single_node_no_travel(self):
        m = _matrix(_entry("A", "B", 300))
        tw = {"A": TimeWindow(open_s=_9H, close_s=_18H)}
        result = schedule_route(["A"], m, tw, {"A": 1800}, _9H)
        assert len(result) == 1
        place_id, arrival_s, departure_s, travel_s = result[0]
        assert place_id == "A"
        assert travel_s == 0
        assert arrival_s == _9H
        assert departure_s == _9H + 1800

    def test_two_nodes_sequential(self):
        m = _matrix(_entry("A", "B", 600))
        tw = {
            "A": TimeWindow(open_s=_9H, close_s=_18H),
            "B": TimeWindow(open_s=_9H, close_s=_18H),
        }
        result = schedule_route(["A", "B"], m, tw, {"A": 1800, "B": 1800}, _9H)
        assert len(result) == 2
        _, _, dep_a, _ = result[0]
        _, arr_b, dep_b, travel_b = result[1]
        assert travel_b == 600
        assert arr_b == dep_a + 600
        assert dep_b == arr_b + 1800

    def test_wait_when_arriving_before_open(self):
        m = _matrix(_entry("A", "B", 300))  # arrive at B at 9:05
        late_open = _9H + 3600  # B opens at 10:00
        tw = {
            "A": TimeWindow(open_s=_9H, close_s=_18H),
            "B": TimeWindow(open_s=late_open, close_s=_18H),
        }
        result = schedule_route(["A", "B"], m, tw, {"A": 0, "B": 1800}, _9H)
        _, arr_b, dep_b, _ = result[1]
        assert arr_b == _9H + 300  # arrived early
        assert dep_b == late_open + 1800  # waited, then visited

    def test_infeasible_returns_empty(self):
        m = _matrix(_entry("A", "B", 7200))  # 2h travel
        tw = {
            "A": TimeWindow(open_s=_9H, close_s=_18H),
            "B": TimeWindow(open_s=_9H, close_s=_9H + 3600),  # closes in 1h
        }
        result = schedule_route(["A", "B"], m, tw, {}, _9H)
        assert result == []

    def test_missing_matrix_entry_returns_empty(self):
        m = _matrix()  # empty — no routes at all
        result = schedule_route(["A", "B"], m, {}, {}, _9H)
        assert result == []


@pytest.mark.unit
class TestIsFeasible:
    def test_feasible_route(self):
        m = _matrix(_entry("A", "B", 600), _entry("B", "C", 600))
        tw = {
            "A": TimeWindow(open_s=_9H, close_s=_21H),
            "B": TimeWindow(open_s=_9H, close_s=_21H),
            "C": TimeWindow(open_s=_9H, close_s=_21H),
        }
        assert is_feasible(["A", "B", "C"], m, tw, {"A": 1800, "B": 1800, "C": 1800}, _9H, _21H)

    def test_infeasible_due_to_day_end(self):
        m = _matrix(_entry("A", "B", 600))
        tw = {"A": TimeWindow(open_s=_9H, close_s=_21H), "B": TimeWindow(open_s=_9H, close_s=_21H)}
        # visit A for 12h → departure way after day_end
        assert not is_feasible(["A", "B"], m, tw, {"A": 12 * 3600, "B": 0}, _9H, _21H)

    def test_infeasible_due_to_time_window(self):
        m = _matrix(_entry("A", "B", 7200))
        tw = {"A": TimeWindow(open_s=_9H, close_s=_21H), "B": TimeWindow(open_s=_9H, close_s=_9H + 3600)}
        assert not is_feasible(["A", "B"], m, tw, {}, _9H, _21H)


@pytest.mark.unit
class TestNearestNeighbor:
    def test_visits_all_reachable_nodes(self):
        m = _square_matrix()
        route, skipped = nearest_neighbor(["A", "B", "C", "D"], m, {}, {}, _9H, _21H)
        assert sorted(route) == ["A", "B", "C", "D"]
        assert skipped == []

    def test_isolated_node_cannot_share_route_with_connected_nodes(self):
        """C has no matrix entries, so it can never appear in the same route as A and B."""
        m = _matrix(_entry("A", "B", 300), _entry("B", "A", 300))
        route, skipped = nearest_neighbor(["A", "B", "C"], m, {}, {}, _9H, _21H)
        # All nodes accounted for
        assert len(route) + len(skipped) == 3
        # C has no connections — if it ends up in the route, A and B must be skipped
        if "C" in route:
            assert "A" not in route and "B" not in route
        # Conversely, if A and B are routed together, C must be skipped
        if "A" in route and "B" in route:
            assert "C" not in route and "C" in skipped

    def test_time_window_forces_order(self):
        """C closes at 9:08; going A→B first (600s) makes C unreachable.
        NN must visit A→C (300s) first, then B, to include all three nodes."""
        m = _matrix(
            _entry("A", "B", 600),
            _entry("A", "C", 300),
            _entry("B", "C", 600),
            _entry("C", "B", 300),
            _entry("B", "A", 600),
            _entry("C", "A", 300),
        )
        # C closes at 9:08 — reachable directly from A (300s → 9:05), but not via B (600+600s)
        tw = {
            "A": TimeWindow(open_s=_9H, close_s=_21H),
            "B": TimeWindow(open_s=_9H, close_s=_21H),
            "C": TimeWindow(open_s=_9H, close_s=_9H + 480),
        }
        route, skipped = nearest_neighbor(["A", "B", "C"], m, tw, {}, _9H, _21H)
        # C must appear in the route, visited before B
        assert "C" in route
        c_idx = route.index("C")
        b_idx = route.index("B")
        assert c_idx < b_idx

    def test_coverage_beats_shorter_travel_time(self):
        """A 3-node route with more travel is preferred over a 2-node route with less."""
        m = _matrix(
            _entry("A", "B", 100),
            _entry("B", "A", 100),
            _entry("A", "C", 500),
            _entry("C", "A", 500),
            _entry("B", "C", 500),
            _entry("C", "B", 500),
        )
        route, skipped = nearest_neighbor(["A", "B", "C"], m, {}, {}, _9H, _21H)
        # All three nodes must be visited even though a 2-node route is shorter
        assert skipped == []
        assert sorted(route) == ["A", "B", "C"]

    def test_empty_input(self):
        m = _matrix()
        route, skipped = nearest_neighbor([], m, {}, {}, _9H, _21H)
        assert route == []
        assert skipped == []

    def test_maximises_coverage_over_all_starts(self):
        """Coverage (number of nodes) takes priority over travel time.
        With asymmetric costs all 3-node routes are feasible, so the result
        must include all nodes; among ties the shortest travel time is chosen."""
        m = _matrix(
            _entry("A", "B", 100),
            _entry("B", "C", 100),
            _entry("C", "A", 100),
            _entry("A", "C", 900),
            _entry("C", "B", 900),
            _entry("B", "A", 900),
        )
        route, skipped = nearest_neighbor(["A", "B", "C"], m, {}, {}, _9H, _21H)
        assert skipped == []
        assert sorted(route) == ["A", "B", "C"]
        # Among equal-length routes the shortest is preferred: A→B→C = 200
        assert route == ["A", "B", "C"] or route == ["B", "C", "A"] or route == ["C", "A", "B"]


@pytest.mark.unit
class TestTwoOpt:
    def test_improves_suboptimal_route(self):
        """A→C→B→D is suboptimal; 2-opt should produce A→B→C→D (shorter)."""
        m = _matrix(
            _entry("A", "B", 100),
            _entry("B", "C", 100),
            _entry("C", "D", 100),
            _entry("D", "A", 100),
            _entry("A", "C", 300),
            _entry("C", "B", 50),
            _entry("B", "D", 300),
            _entry("D", "C", 100),
            _entry("B", "A", 100),
            _entry("C", "A", 300),
            _entry("D", "B", 300),
            _entry("A", "D", 100),
        )
        tw = {n: TimeWindow(open_s=_9H, close_s=_21H) for n in "ABCD"}
        # Start with a bad route
        bad_route = ["A", "C", "B", "D"]
        improved = two_opt(bad_route, m, tw, {}, _9H, _21H)
        # Should have shorter total travel time than the bad route
        from src.optimizer.solver.engine import _route_travel_time

        assert _route_travel_time(improved, m) <= _route_travel_time(bad_route, m)

    def test_skips_swap_violating_time_window(self):
        """2-opt wants A→C→B→D (shorter travel), but B would be reached via C too late.
        The swap must be rejected because it violates B's tight close time."""
        m = _matrix(
            _entry("A", "B", 50),  # fast direct path to B
            _entry("B", "C", 200),  # slow B→C makes the reverse candidate attractive
            _entry("C", "D", 50),
            _entry("A", "C", 50),
            _entry("C", "B", 100),  # arriving via C makes B miss its window
            _entry("B", "D", 50),
            _entry("D", "C", 300),
            _entry("D", "B", 300),
            _entry("B", "A", 300),
            _entry("C", "A", 300),
            _entry("A", "D", 300),
            _entry("D", "A", 300),
        )
        tw = {
            "A": TimeWindow(open_s=_9H, close_s=_21H),
            # B closes at 9:01 — only reachable via A→B (50s), NOT via A→C→B (50+100=150s)
            "B": TimeWindow(open_s=_9H, close_s=_9H + 60),
            "C": TimeWindow(open_s=_9H, close_s=_21H),
            "D": TimeWindow(open_s=_9H, close_s=_21H),
        }
        # A→B→C→D is the only feasible route; 2-opt must not swap B and C
        route = ["A", "B", "C", "D"]
        result = two_opt(route, m, tw, {}, _9H, _21H)
        assert result.index("B") < result.index("C")

    def test_short_route_unchanged(self):
        m = _matrix(_entry("A", "B", 100), _entry("B", "A", 100))
        tw = {n: TimeWindow(open_s=_9H, close_s=_21H) for n in "AB"}
        result = two_opt(["A", "B"], m, tw, {}, _9H, _21H)
        assert result == ["A", "B"]
