"""TSP solver: Nearest Neighbor construction + 2-opt improvement with time windows.

All times are represented as integer seconds from midnight (e.g. 9 * 3600 = 32400).
"""

from __future__ import annotations

from src.optimizer.matrix.models import DistanceMatrix
from src.optimizer.solver.models import TimeWindow

_LARGE = 10**9  # sentinel for unreachable travel cost


def schedule_route(
    route: list[str],
    matrix: DistanceMatrix,
    time_windows: dict[str, TimeWindow],
    visit_durations_s: dict[str, int],
    day_start_s: int,
) -> list[tuple[str, int, int, int]]:
    """Compute arrival/departure times for each node following the route order.

    Returns a list of (place_id, arrival_s, departure_s, travel_s) tuples.
    arrival_s and departure_s are seconds from midnight.
    travel_s is time spent travelling from the previous node (0 for the first).
    """
    result: list[tuple[str, int, int, int]] = []
    current_s = day_start_s

    for idx, node in enumerate(route):
        travel_s = 0
        if idx > 0:
            prev = route[idx - 1]
            entry = matrix.get(prev, node)
            if entry is None:
                return []  # no connection between consecutive nodes
            travel_s = entry.duration_s

        arrival_s = current_s + travel_s
        tw = time_windows.get(node)
        visit_s = visit_durations_s.get(node, 0)

        if tw is not None:
            start_s = tw.earliest_start(arrival_s, visit_s)
            if start_s is None:
                return []  # infeasible — caller must handle
        else:
            start_s = max(arrival_s, day_start_s)

        departure_s = start_s + visit_s

        result.append((node, arrival_s, departure_s, travel_s))
        current_s = departure_s

    return result


def is_feasible(
    route: list[str],
    matrix: DistanceMatrix,
    time_windows: dict[str, TimeWindow],
    visit_durations_s: dict[str, int],
    day_start_s: int,
    day_end_s: int,
) -> bool:
    """Return True if the route satisfies all time windows and ends before day_end_s."""
    sched = schedule_route(route, matrix, time_windows, visit_durations_s, day_start_s)
    if not sched:
        return False
    _, _, last_departure_s, _ = sched[-1]
    return last_departure_s <= day_end_s


def _route_travel_time(route: list[str], matrix: DistanceMatrix) -> int:
    """Sum of travel times along the route (seconds). Returns _LARGE if any leg is missing."""
    total = 0
    for i in range(1, len(route)):
        entry = matrix.get(route[i - 1], route[i])
        if entry is None:
            return _LARGE
        total += entry.duration_s
    return total


def _route_score(route: list[str], weights: dict[str, int] | None) -> int:
    """Total priority weight of the route. Without weights every node counts as 1."""
    if weights is None:
        return len(route)
    return sum(weights.get(node, 1) for node in route)


def nearest_neighbor(
    nodes: list[str],
    matrix: DistanceMatrix,
    time_windows: dict[str, TimeWindow],
    visit_durations_s: dict[str, int],
    day_start_s: int,
    day_end_s: int,
    weights: dict[str, int] | None = None,
    end_anchor: str | None = None,
) -> tuple[list[str], list[str]]:
    """Build an initial route using the Nearest Neighbor heuristic.

    Tries every node as the starting point. Selects the route with the highest
    total priority weight (node count when weights is None); among ties, prefers
    the shortest total travel time. Nodes that cannot be reached within their
    time window are left out and returned in the skipped list.

    end_anchor, when given, is appended as a forced final stop (see nn_from_start).

    Returns:
        (route, skipped_ids)
    """
    if not nodes:
        return [], []

    best_route: list[str] = []
    best_score = 0
    best_time = _LARGE

    for start in nodes:
        route, _ = nn_from_start(
            start, nodes, matrix, time_windows, visit_durations_s, day_start_s, day_end_s, end_anchor=end_anchor
        )
        t = _route_travel_time(route, matrix)
        score = _route_score(route, weights)
        if score > best_score or (score == best_score and t < best_time):
            best_score = score
            best_time = t
            best_route = route

    visited = set(best_route)
    skipped = [n for n in nodes if n not in visited]
    return best_route, skipped


def nn_from_start(
    start: str,
    nodes: list[str],
    matrix: DistanceMatrix,
    time_windows: dict[str, TimeWindow],
    visit_durations_s: dict[str, int],
    day_start_s: int,
    day_end_s: int,
    end_anchor: str | None = None,
) -> tuple[list[str], list[str]]:
    """Run Nearest Neighbor with Earliest Deadline First from a fixed starting node.

    Among feasible candidates the one with the soonest close time is chosen.
    When close times are equal (e.g. all unconstrained nodes sharing day_end_s),
    the shortest travel time breaks the tie — preserving classic NN behaviour.
    Returns an empty route when the start node itself cannot be visited.

    end_anchor, when given, must be the final stop of the day (e.g. a hotel). A
    candidate is rejected during construction if visiting it would leave no way to
    still reach end_anchor by day_end_s — the anchor is never added mid-route, only
    appended once no further real place can be visited. If end_anchor turns out to
    be unreachable at all, the whole attempt is infeasible (empty route).
    """
    route = [start]
    unvisited = set(nodes) - {start}

    tw = time_windows.get(start)
    visit_s_start = visit_durations_s.get(start, 0)
    if tw is not None:
        start_time = tw.earliest_start(day_start_s, visit_s_start)
        if start_time is None:
            return [], list(nodes)
    else:
        start_time = day_start_s
    if start_time + visit_s_start > day_end_s:
        return [], list(nodes)
    current_s = start_time + visit_s_start

    while unvisited:
        best_node: str | None = None
        best_close = _LARGE
        best_travel = _LARGE

        for candidate in unvisited:
            entry = matrix.get(route[-1], candidate)
            if entry is None:
                continue
            travel = entry.duration_s
            arrival = current_s + travel

            tw = time_windows.get(candidate)
            visit_s_cand = visit_durations_s.get(candidate, 0)
            if tw is not None:
                effective_start_cand = tw.earliest_start(arrival, visit_s_cand)
                if effective_start_cand is None:
                    continue
                close_s = tw.close_s  # last deadline, used for EDF ordering
            else:
                if arrival > day_end_s:
                    continue
                effective_start_cand = max(arrival, day_start_s)
                close_s = day_end_s

            if end_anchor is not None:
                end_entry = matrix.get(candidate, end_anchor)
                if end_entry is None or effective_start_cand + visit_s_cand + end_entry.duration_s > day_end_s:
                    continue  # visiting this candidate would strand the route before reaching end_anchor

            if close_s < best_close or (close_s == best_close and travel < best_travel):
                best_close = close_s
                best_travel = travel
                best_node = candidate

        if best_node is None:
            break

        arrival = current_s + best_travel
        visit_s_node = visit_durations_s.get(best_node, 0)
        tw = time_windows.get(best_node)
        if tw is not None:
            effective_start = tw.earliest_start(arrival, visit_s_node)
            if effective_start is None:
                break
        else:
            effective_start = max(arrival, day_start_s)
        next_departure = effective_start + visit_s_node

        if next_departure > day_end_s:
            break

        route.append(best_node)
        unvisited.remove(best_node)
        current_s = next_departure

    skipped = list(unvisited)

    if end_anchor is not None:
        end_entry = matrix.get(route[-1], end_anchor)
        if end_entry is None or current_s + end_entry.duration_s > day_end_s:
            return [], list(nodes)
        route.append(end_anchor)

    return route, skipped


def two_opt(
    route: list[str],
    matrix: DistanceMatrix,
    time_windows: dict[str, TimeWindow],
    visit_durations_s: dict[str, int],
    day_start_s: int,
    day_end_s: int,
    max_iterations: int = 100,
    pin_end: bool = False,
) -> list[str]:
    """Improve a route using the 2-opt local search.

    For each pair of edges (i, i+1) and (j, j+1), reverse the segment
    between i+1 and j. Accept the swap only if the new route is both
    feasible (all time windows satisfied) and strictly shorter.

    Position 0 is structurally never moved by this loop (i always starts at 0,
    so route[:i+1] is always copied unchanged) — a fixed start needs no extra
    handling. pin_end additionally excludes the last position from j's range,
    so a fixed end anchor is never reordered out of its final slot.

    Returns the improved route (or the original if no improvement was found).
    """
    if len(route) < 4:
        return route

    improved = True
    iterations = 0
    j_upper = len(route) - 1 if pin_end else len(route)

    while improved and iterations < max_iterations:
        improved = False
        iterations += 1
        current_time = _route_travel_time(route, matrix)

        for i in range(len(route) - 1):
            for j in range(i + 2, j_upper):
                candidate = route[: i + 1] + list(reversed(route[i + 1 : j + 1])) + route[j + 1 :]
                candidate_time = _route_travel_time(candidate, matrix)

                if candidate_time < current_time and is_feasible(
                    candidate, matrix, time_windows, visit_durations_s, day_start_s, day_end_s
                ):
                    route = candidate
                    current_time = candidate_time
                    improved = True
                    break
            if improved:
                break

    return route
