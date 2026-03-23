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
            travel_s = entry.duration_s if entry is not None else _LARGE

        arrival_s = current_s + travel_s
        tw = time_windows.get(node)
        open_s = tw.open_s if tw is not None else day_start_s
        close_s = tw.close_s if tw is not None else _LARGE

        if arrival_s > close_s:
            return []  # infeasible — caller must handle

        effective_start_s = max(arrival_s, open_s)
        visit_s = visit_durations_s.get(node, 0)
        departure_s = effective_start_s + visit_s

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


def nearest_neighbor(
    nodes: list[str],
    matrix: DistanceMatrix,
    time_windows: dict[str, TimeWindow],
    visit_durations_s: dict[str, int],
    day_start_s: int,
    day_end_s: int,
) -> tuple[list[str], list[str]]:
    """Build an initial route using the Nearest Neighbor heuristic.

    Tries every node as the starting point and returns the route with the
    shortest total travel time. Nodes that cannot be reached within their
    time window are left out and returned in the skipped list.

    Returns:
        (route, skipped_ids)
    """
    if not nodes:
        return [], []

    best_route: list[str] = []
    best_time = _LARGE

    for start in nodes:
        route, _ = _nn_from_start(start, nodes, matrix, time_windows, visit_durations_s, day_start_s, day_end_s)
        t = _route_travel_time(route, matrix)
        if t < best_time:
            best_time = t
            best_route = route

    visited = set(best_route)
    skipped = [n for n in nodes if n not in visited]
    return best_route, skipped


def _nn_from_start(
    start: str,
    nodes: list[str],
    matrix: DistanceMatrix,
    time_windows: dict[str, TimeWindow],
    visit_durations_s: dict[str, int],
    day_start_s: int,
    day_end_s: int,
) -> tuple[list[str], list[str]]:
    """Run Nearest Neighbor from a fixed starting node."""
    route = [start]
    unvisited = set(nodes) - {start}
    current_s = day_start_s

    tw = time_windows.get(start)
    open_s = tw.open_s if tw is not None else day_start_s
    current_s = max(current_s, open_s) + visit_durations_s.get(start, 0)

    while unvisited:
        best_node: str | None = None
        best_travel = _LARGE

        for candidate in unvisited:
            entry = matrix.get(route[-1], candidate)
            if entry is None:
                continue
            travel = entry.duration_s
            arrival = current_s + travel

            tw = time_windows.get(candidate)
            close_s = tw.close_s if tw is not None else day_end_s

            if arrival > close_s:
                continue

            if travel < best_travel:
                best_travel = travel
                best_node = candidate

        if best_node is None:
            break

        tw = time_windows.get(best_node)
        open_s = tw.open_s if tw is not None else day_start_s
        arrival = current_s + best_travel
        effective_start = max(arrival, open_s)
        next_departure = effective_start + visit_durations_s.get(best_node, 0)

        if next_departure > day_end_s:
            break

        route.append(best_node)
        unvisited.remove(best_node)
        current_s = next_departure

    skipped = list(unvisited)
    return route, skipped


def two_opt(
    route: list[str],
    matrix: DistanceMatrix,
    time_windows: dict[str, TimeWindow],
    visit_durations_s: dict[str, int],
    day_start_s: int,
    day_end_s: int,
    max_iterations: int = 100,
) -> list[str]:
    """Improve a route using the 2-opt local search.

    For each pair of edges (i, i+1) and (j, j+1), reverse the segment
    between i+1 and j. Accept the swap only if the new route is both
    feasible (all time windows satisfied) and strictly shorter.

    Returns the improved route (or the original if no improvement was found).
    """
    if len(route) < 4:
        return route

    improved = True
    iterations = 0

    while improved and iterations < max_iterations:
        improved = False
        iterations += 1
        current_time = _route_travel_time(route, matrix)

        for i in range(len(route) - 1):
            for j in range(i + 2, len(route)):
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
