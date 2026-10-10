from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra


# One transparent objective contract shared with solver.cpp.  The hybrid score
# converts one second of route duration to 0.25 distance-score units.  Service
# time is included for an operationally complete duration; because total
# service is fixed for a served-once solution it does not bias route ordering.
HYBRID_TIME_WEIGHT = 0.25


def objective_value(
    objective_mode: str,
    *,
    distance_m: float,
    travel_time_s: float,
    service_time_s: float,
    waiting_s: float,
) -> float:
    duration_s = travel_time_s + service_time_s + waiting_s
    if objective_mode == "time":
        return duration_s
    if objective_mode == "hybrid":
        return distance_m + HYBRID_TIME_WEIGHT * duration_s
    return distance_m


@dataclass
class RouteMetrics:
    feasible: bool
    objective: float
    distance_m: float
    travel_time_s: float
    service_time_s: float
    waiting_s: float
    finish_time_s: float
    reason: str = ""


@dataclass
class RoutingContext:
    """One objective-specific shortest-path batch reused by validation/publication."""

    materialization_id: str
    objective_mode: str
    relevant: list[int]
    source_row: dict[int, int]
    predecessors: np.ndarray
    best_edges: dict[tuple[int, int], dict[str, Any]]
    node_count: int
    # Exact terminal-pair metrics for the selected path objective.  Distance and
    # hybrid modes can certify a native route without replaying every road edge;
    # time mode keeps distance=None so its selected-path distance still falls
    # back to exact predecessor reconstruction rather than adding an expensive
    # all-pairs distance pass to baseline construction.
    pair_travel_s: np.ndarray | None
    pair_distance_m: np.ndarray | None

    def reconstruct(self, source: int, target: int) -> list[int] | None:
        source, target = int(source), int(target)
        if source == target:
            return [source]
        row = self.source_row.get(source)
        if row is None or not (0 <= target < self.node_count):
            return None
        path = [target]
        current = target
        for _ in range(self.node_count + 1):
            predecessor = int(self.predecessors[row, current])
            if predecessor < 0:
                return None
            path.append(predecessor)
            current = predecessor
            if current == source:
                path.reverse()
                return path
        return None


def _edge_objective(edge: dict[str, Any], objective_mode: str) -> float:
    distance = max(0.0, float(edge.get("length_m") or 0.0))
    travel = max(0.000001, float(edge.get("travel_time_s") or 1.0))
    if objective_mode == "time":
        return travel
    if objective_mode == "hybrid":
        return distance + HYBRID_TIME_WEIGHT * travel
    return max(0.000001, distance)


def _fastest_graph(
    dataset: dict[str, Any],
    objective_mode: str = "time",
) -> tuple[csr_matrix, dict[tuple[int, int], dict[str, Any]]]:
    """Build the directed graph for the selected public route objective."""
    n = int(dataset.get("num_nodes") or len(dataset.get("nodes") or []))
    best: dict[tuple[int, int], dict[str, Any]] = {}
    for edge in dataset.get("edges") or []:
        u, v = int(edge["u"]), int(edge["v"])
        weight = _edge_objective(edge, objective_mode)
        key = (u, v)
        previous = best.get(key)
        previous_weight = _edge_objective(previous, objective_mode) if previous is not None else math.inf
        if previous is None or weight < previous_weight - 1e-12 or (
            abs(weight - previous_weight) <= 1e-12
            and (float(edge.get("travel_time_s") or 0.0), float(edge.get("length_m") or 0.0))
            < (float(previous.get("travel_time_s") or 0.0), float(previous.get("length_m") or 0.0))
        ):
            best[key] = edge
    if not best:
        raise ValueError("The solver dataset contains no road edges")
    rows = np.fromiter((key[0] for key in best), dtype=np.int64)
    cols = np.fromiter((key[1] for key in best), dtype=np.int64)
    weights = np.fromiter(
        (_edge_objective(edge, objective_mode) for edge in best.values()),
        dtype=np.float64,
    )
    return csr_matrix((weights, (rows, cols)), shape=(n, n)), best


def _path_metric_matrix(
    relevant: list[int],
    predecessors: np.ndarray,
    best_edges: dict[tuple[int, int], dict[str, Any]],
    metric_key: str,
) -> np.ndarray:
    size = len(relevant)
    matrix = np.full((size, size), np.inf, dtype=np.float64)
    for row_index, source in enumerate(relevant):
        memo: dict[int, float] = {int(source): 0.0}
        pred_row = predecessors[row_index]
        for col_index, target in enumerate(relevant):
            target = int(target)
            if target in memo:
                matrix[row_index, col_index] = memo[target]
                continue
            trail: list[tuple[int, int, float]] = []
            current = target
            seen: set[int] = set()
            while current not in memo:
                if current in seen:
                    trail = []
                    break
                seen.add(current)
                predecessor = int(pred_row[current])
                if predecessor < 0:
                    trail = []
                    break
                edge = best_edges.get((predecessor, current))
                if edge is None:
                    trail = []
                    break
                trail.append((current, predecessor, max(0.0, float(edge.get(metric_key) or 0.0))))
                current = predecessor
            if current not in memo:
                continue
            distance = memo[current]
            for node, predecessor, length in reversed(trail):
                distance += length
                memo[node] = distance
            matrix[row_index, col_index] = memo.get(target, np.inf)
    return matrix


def _fastest_path_length_matrix(relevant: list[int], predecessors: np.ndarray, best_edges: dict[tuple[int, int], dict[str, Any]]) -> np.ndarray:
    return _path_metric_matrix(relevant, predecessors, best_edges, "length_m")

def _great_circle_matrix(dataset: dict[str, Any], relevant: list[int]) -> np.ndarray:
    """Cheap distance heuristic for insertion; final metrics use real road paths."""
    nodes = {int(node["id"]): node for node in dataset.get("nodes") or []}
    coords = np.asarray(
        [[float(nodes[node]["lat"]), float(nodes[node]["lon"])] for node in relevant],
        dtype=np.float64,
    )
    lat = np.radians(coords[:, 0])[:, None]
    lon = np.radians(coords[:, 1])[:, None]
    dlat = lat.T - lat
    dlon = lon.T - lon
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat) * np.cos(lat.T) * np.sin(dlon / 2.0) ** 2
    return 6_371_008.8 * 2.0 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(0.0, 1.0 - a)))


def _routing_matrices(
    dataset: dict[str, Any],
    objective_mode: str = "distance",
) -> tuple[np.ndarray, np.ndarray, RoutingContext]:
    depot = int(dataset["depot"])
    customer_nodes = [int(item["node"]) for item in dataset.get("customers") or []]
    relevant = [depot, *customer_nodes]
    graph, best_edges = _fastest_graph(dataset, objective_mode)
    objective_costs, predecessors = dijkstra(
        graph,
        directed=True,
        indices=np.asarray(relevant, dtype=np.int64),
        return_predecessors=True,
    )
    objective_matrix = np.asarray(objective_costs[:, relevant], dtype=np.float64)
    # Release the large all-node objective matrix immediately; predecessors are
    # retained because route publication can reuse them without another Dijkstra.
    del objective_costs
    if not np.isfinite(objective_matrix[0, :]).all() or not np.isfinite(objective_matrix[:, 0]).all():
        raise ValueError("At least one customer is not reachable from and back to the depot")
    time_matrix = (
        objective_matrix
        if objective_mode == "time"
        else _path_metric_matrix(relevant, predecessors, best_edges, "travel_time_s")
    )
    # Assignment needs a deterministic ranking heuristic, not an all-pairs
    # exact road-length matrix. Computing every selected-objective path length from the
    # predecessor forest in Python can dominate certificate time at 100–500
    # customers. Great-circle distance is cheap and stable; hard feasibility is
    # still evaluated with exact road travel times, and final published metrics
    # are reconstructed from the selected objective's exact road paths below.
    try:
        heuristic_distance = objective_matrix if objective_mode == "distance" else _great_circle_matrix(dataset, relevant)
    except Exception:
        # Legacy/malformed datasets without node coordinates retain the exact
        # predecessor-derived fallback rather than weakening correctness.
        heuristic_distance = _fastest_path_length_matrix(relevant, predecessors, best_edges)
    # Keep exact terminal-pair metrics alongside the predecessor forest.  This
    # makes the post-native independent certificate O(route legs) for the common
    # distance/hybrid objectives while preserving the exact same selected paths.
    # For hybrid, selected edge score = distance + 0.25 * travel, so distance on
    # that exact path is recovered algebraically without another graph traversal.
    pair_distance_m: np.ndarray | None
    if objective_mode == "distance":
        pair_distance_m = np.asarray(objective_matrix, dtype=np.float64)
    elif objective_mode == "hybrid":
        pair_distance_m = np.maximum(
            0.0,
            np.asarray(objective_matrix, dtype=np.float64)
            - HYBRID_TIME_WEIGHT * np.asarray(time_matrix, dtype=np.float64),
        )
    else:
        pair_distance_m = None
    context = RoutingContext(
        materialization_id=str(dataset.get("materialization_id") or ""),
        objective_mode=str(objective_mode),
        relevant=relevant,
        source_row={node: i for i, node in enumerate(relevant)},
        predecessors=np.asarray(predecessors),
        best_edges=best_edges,
        node_count=int(dataset.get("num_nodes") or graph.shape[0]),
        pair_travel_s=np.asarray(time_matrix, dtype=np.float64),
        pair_distance_m=pair_distance_m,
    )
    return time_matrix, heuristic_distance, context


def routing_context_for_dataset(dataset: dict[str, Any], objective_mode: str = "distance") -> RoutingContext:
    """Build the exact shortest-path context used for certification/publication.

    This intentionally exposes only the reusable path context; callers that need
    route scoring should use the public validation and scheduling functions.
    """
    _, _, context = _routing_matrices(dataset, objective_mode)
    return context


def _evaluate_route(
    sequence: list[int],
    customers: list[dict[str, Any]],
    time_matrix: np.ndarray,
    distance_matrix: np.ndarray,
    objective_mode: str,
    *,
    route_start_time_s: float = 0.0,
    use_time_window: bool = True,
) -> RouteMetrics:
    current_rel = 0
    current_time = float(route_start_time_s)
    distance_m = 0.0
    travel_time_s = 0.0
    service_time_s = 0.0
    waiting_s = 0.0
    for customer_index in sequence:
        next_rel = customer_index + 1
        travel = float(time_matrix[current_rel, next_rel])
        distance = float(distance_matrix[current_rel, next_rel])
        if not math.isfinite(travel) or not math.isfinite(distance):
            return RouteMetrics(False, math.inf, math.inf, math.inf, 0.0, 0.0, math.inf, "unreachable road pair")
        arrival = current_time + travel
        item = customers[customer_index]
        earliest = float(item.get("earliest", 0.0))
        latest = float(item.get("latest", 86400.0))
        start = max(arrival, earliest) if use_time_window else arrival
        if use_time_window and start > latest + 1e-6:
            return RouteMetrics(False, math.inf, math.inf, math.inf, 0.0, 0.0, start, "time window")
        wait = max(0.0, earliest - arrival) if use_time_window else 0.0
        service = max(0.0, float(item.get("service_time_s", 0.0)))
        current_time = start + service
        travel_time_s += travel
        distance_m += distance
        waiting_s += wait
        service_time_s += service
        current_rel = next_rel
    return_travel = float(time_matrix[current_rel, 0])
    return_distance = float(distance_matrix[current_rel, 0])
    if not math.isfinite(return_travel) or not math.isfinite(return_distance):
        return RouteMetrics(False, math.inf, math.inf, math.inf, 0.0, 0.0, math.inf, "cannot return to depot")
    travel_time_s += return_travel
    distance_m += return_distance
    finish = current_time + return_travel
    objective = objective_value(
        objective_mode,
        distance_m=distance_m,
        travel_time_s=travel_time_s,
        service_time_s=service_time_s,
        waiting_s=waiting_s,
    )
    return RouteMetrics(True, objective, distance_m, travel_time_s, service_time_s, waiting_s, finish)


def _insert_best(
    route: list[int],
    customer_index: int,
    customers: list[dict[str, Any]],
    time_matrix: np.ndarray,
    distance_matrix: np.ndarray,
    objective_mode: str,
    *,
    route_start_time_s: float = 0.0,
    use_time_window: bool = True,
) -> tuple[list[int] | None, RouteMetrics | None, float]:
    evaluate = lambda candidate: _evaluate_route(
        candidate, customers, time_matrix, distance_matrix, objective_mode,
        route_start_time_s=route_start_time_s, use_time_window=use_time_window,
    )
    base = evaluate(route)
    base_objective = base.objective if base.feasible else 0.0
    best_route: list[int] | None = None
    best_metrics: RouteMetrics | None = None
    best_delta = math.inf
    for position in range(len(route) + 1):
        candidate = [*route[:position], customer_index, *route[position:]]
        metrics = evaluate(candidate)
        if not metrics.feasible:
            continue
        delta = metrics.objective - base_objective
        if delta < best_delta - 1e-9:
            best_route, best_metrics, best_delta = candidate, metrics, delta
    return best_route, best_metrics, best_delta


def _insert_best_open(
    route: list[int],
    customer_index: int,
    customers: list[dict[str, Any]],
    time_matrix: np.ndarray,
    distance_matrix: np.ndarray,
    objective_mode: str,
    *,
    route_start_time_s: float = 0.0,
    use_time_window: bool = True,
) -> tuple[list[int] | None, RouteMetrics | None, float]:
    """Rank open-window insertion positions in O(route length), then validate."""
    evaluate = lambda candidate: _evaluate_route(
        candidate, customers, time_matrix, distance_matrix, objective_mode,
        route_start_time_s=route_start_time_s, use_time_window=use_time_window,
    )
    base = evaluate(route)
    base_objective = base.objective if base.feasible else 0.0
    new_rel = customer_index + 1
    ranked: list[tuple[float, int]] = []
    for position in range(len(route) + 1):
        prev_rel = 0 if position == 0 else route[position - 1] + 1
        next_rel = 0 if position == len(route) else route[position] + 1
        time_delta = float(time_matrix[prev_rel, new_rel] + time_matrix[new_rel, next_rel] - time_matrix[prev_rel, next_rel])
        distance_delta = float(distance_matrix[prev_rel, new_rel] + distance_matrix[new_rel, next_rel] - distance_matrix[prev_rel, next_rel])
        if objective_mode == "time":
            score = time_delta
        elif objective_mode == "hybrid":
            score = distance_delta + HYBRID_TIME_WEIGHT * time_delta
        else:
            score = distance_delta
        ranked.append((score, position))
    for _, position in sorted(ranked, key=lambda item: (item[0], item[1])):
        candidate = [*route[:position], customer_index, *route[position:]]
        metrics = evaluate(candidate)
        if metrics.feasible:
            return candidate, metrics, metrics.objective - base_objective
    return None, None, math.inf

def _append_best(
    route: list[int],
    customer_index: int,
    customers: list[dict[str, Any]],
    time_matrix: np.ndarray,
    distance_matrix: np.ndarray,
    objective_mode: str,
    *,
    route_start_time_s: float = 0.0,
    use_time_window: bool = True,
) -> tuple[list[int] | None, RouteMetrics | None, float]:
    """O(route length) fast path for unconstrained/open-window scenarios."""
    evaluate = lambda candidate: _evaluate_route(
        candidate, customers, time_matrix, distance_matrix, objective_mode,
        route_start_time_s=route_start_time_s, use_time_window=use_time_window,
    )
    base = evaluate(route)
    candidate = [*route, customer_index]
    metrics = evaluate(candidate)
    if not metrics.feasible:
        return None, None, math.inf
    return candidate, metrics, metrics.objective - (base.objective if base.feasible else 0.0)


def _exact_route_metrics(
    sequence: list[int],
    customers: list[dict[str, Any]],
    depot: int,
    context: RoutingContext,
    objective_mode: str,
    *,
    route_start_time_s: float = 0.0,
    use_time_window: bool = True,
    include_paths: bool = True,
) -> tuple[RouteMetrics, dict[tuple[int, int], list[int]]]:
    terminal_nodes = [depot, *[int(customers[index]["node"]) for index in sequence], depot]
    current_time = float(route_start_time_s)
    distance_m = travel_time_s = service_time_s = waiting_s = 0.0
    paths: dict[tuple[int, int], list[int]] = {}
    matrix_fast_path = bool(
        not include_paths
        and context.objective_mode == str(objective_mode)
        and context.pair_travel_s is not None
        and context.pair_distance_m is not None
    )
    for leg_index, (source, target) in enumerate(zip(terminal_nodes, terminal_nodes[1:])):
        leg_distance = leg_time = math.inf
        if matrix_fast_path:
            row = context.source_row.get(int(source))
            col = context.source_row.get(int(target))
            if row is not None and col is not None:
                leg_time = float(context.pair_travel_s[row, col])
                leg_distance = float(context.pair_distance_m[row, col])
        else:
            path = context.reconstruct(source, target)
            if not path:
                return RouteMetrics(False, math.inf, math.inf, math.inf, 0, 0, math.inf, "route path reconstruction failed"), paths
            if include_paths:
                paths[(source, target)] = path
            leg_distance = leg_time = 0.0
            for u, v in zip(path, path[1:]):
                edge = context.best_edges.get((u, v))
                if edge is None:
                    return RouteMetrics(False, math.inf, math.inf, math.inf, 0, 0, math.inf, "missing road edge during validation"), paths
                leg_distance += max(0.0, float(edge.get("length_m") or 0.0))
                leg_time += max(0.0, float(edge.get("travel_time_s") or 0.0))
        if not math.isfinite(leg_time) or not math.isfinite(leg_distance):
            return RouteMetrics(False, math.inf, math.inf, math.inf, 0, 0, math.inf, "unreachable road pair"), paths
        distance_m += leg_distance
        travel_time_s += leg_time
        if leg_index < len(sequence):
            item = customers[sequence[leg_index]]
            arrival = current_time + leg_time
            earliest = float(item.get("earliest", 0.0))
            latest = float(item.get("latest", 86400.0))
            start = max(arrival, earliest) if use_time_window else arrival
            if use_time_window and start > latest + 1e-6:
                return RouteMetrics(False, math.inf, math.inf, math.inf, 0, 0, start, "time window"), paths
            wait = max(0.0, earliest - arrival) if use_time_window else 0.0
            service = max(0.0, float(item.get("service_time_s", 0.0)))
            waiting_s += wait
            service_time_s += service
            current_time = start + service
        else:
            current_time += leg_time
    objective = objective_value(
        objective_mode,
        distance_m=distance_m,
        travel_time_s=travel_time_s,
        service_time_s=service_time_s,
        waiting_s=waiting_s,
    )
    return RouteMetrics(True, objective, distance_m, travel_time_s, service_time_s, waiting_s, current_time), paths


def validate_solver_routes(
    dataset: dict[str, Any],
    parsed_routes: list[dict[str, Any]],
    context: RoutingContext,
    *,
    objective_mode: str = "distance",
    allow_multi_trip: bool = False,
    max_trips_per_truck: int = 1,
    route_start_time_s: float | None = None,
    use_time_window: bool | None = None,
) -> dict[str, Any]:
    """Independently certify native routes against the serialized contract.

    The C++ solver performs its own hard-feasibility checks. This second,
    implementation-independent receipt protects publication from parser bugs,
    truncated output, duplicated customers, and accidental regressions.
    """
    if context.objective_mode != str(objective_mode):
        return {
            "ok": False,
            "errors": [
                "routing validation context objective mismatch: "
                f"context={context.objective_mode}, requested={objective_mode}"
            ],
            "objective_mode": str(objective_mode),
            "route_count": len(parsed_routes),
            "customer_nodes": len(dataset.get("customers") or []),
            "served_visits": 0,
        }

    customers = list(dataset.get("customers") or [])
    depot = int(dataset.get("depot", -1))
    maximum_trucks = int(dataset.get("K_trucks") or 0)
    capacity = float(dataset.get("truck_capacity") or 0.0)
    routing_contract = dict(dataset.get("routing_contract") or {})
    if route_start_time_s is None:
        route_start_time_s = float(routing_contract.get("route_start_time_s", 0.0))
    if use_time_window is None:
        use_time_window = bool(routing_contract.get("use_time_window", True))
    customer_index = {int(item["node"]): index for index, item in enumerate(customers)}
    expected_nodes = set(customer_index)
    errors: list[str] = []
    covered: list[int] = []
    truck_ids: set[int] = set()
    route_receipts: list[dict[str, Any]] = []
    total_objective = total_distance = total_travel = total_service = total_waiting = 0.0
    maximum_finish = 0.0

    if not parsed_routes:
        errors.append("native stdout contained no routes")
    if maximum_trucks <= 0 or len(parsed_routes) > maximum_trucks:
        errors.append(f"route count {len(parsed_routes)} exceeds maximum fleet {maximum_trucks}")

    for route in parsed_routes:
        truck_id = int(route.get("truck_id", -1))
        if truck_id in truck_ids:
            errors.append(f"truck {truck_id} appears more than once")
        truck_ids.add(truck_id)
        nodes = [int(node) for node in (route.get("route_nodes") or [])]
        if len(nodes) < 2 or nodes[0] != depot or nodes[-1] != depot:
            errors.append(f"truck {truck_id} route must start and end at depot {depot}")
            continue

        trips: list[list[int]] = []
        current: list[int] = []
        for node in nodes[1:]:
            if node == depot:
                if current:
                    trips.append(current)
                    current = []
                continue
            if node not in customer_index:
                errors.append(f"truck {truck_id} references non-customer node {node}")
                continue
            current.append(customer_index[node])
            covered.append(node)
        if current:
            errors.append(f"truck {truck_id} has customer nodes after its final depot")
        if not trips:
            errors.append(f"truck {truck_id} has no customer trip")
            continue
        if not allow_multi_trip and len(trips) != 1:
            errors.append(f"truck {truck_id} uses {len(trips)} trips while multi-trip is disabled")
        if max_trips_per_truck > 0 and len(trips) > max_trips_per_truck:
            errors.append(f"truck {truck_id} exceeds the {max_trips_per_truck}-trip limit")

        truck_objective = truck_distance = truck_travel = truck_service = truck_waiting = 0.0
        truck_finish = float(route_start_time_s)
        for trip_number, sequence in enumerate(trips, start=1):
            load = sum(float(customers[index].get("demand", 0.0)) for index in sequence)
            if load > capacity + 1e-9:
                errors.append(
                    f"truck {truck_id} trip {trip_number} load {load:.6f} exceeds capacity {capacity:.6f}"
                )
            # A physical truck keeps one continuous clock across depot returns.
            # Only load is reset between trips; time is never reset.
            metrics, _ = _exact_route_metrics(
                sequence,
                customers,
                depot,
                context,
                objective_mode,
                route_start_time_s=truck_finish,
                use_time_window=bool(use_time_window),
                include_paths=False,
            )
            if not metrics.feasible:
                errors.append(f"truck {truck_id} trip {trip_number} failed {metrics.reason}")
                continue
            truck_objective += metrics.objective
            truck_distance += metrics.distance_m
            truck_travel += metrics.travel_time_s
            truck_service += metrics.service_time_s
            truck_waiting += metrics.waiting_s
            truck_finish = metrics.finish_time_s
        total_objective += truck_objective
        total_distance += truck_distance
        total_travel += truck_travel
        total_service += truck_service
        total_waiting += truck_waiting
        maximum_finish = max(maximum_finish, truck_finish)
        route_receipts.append({
            "truck_id": truck_id,
            "trips": len(trips),
            "customer_nodes": sum(len(trip) for trip in trips),
            "objective": round(truck_objective, 6),
            "distance_m": round(truck_distance, 3),
            "travel_time_s": round(truck_travel, 3),
            "service_time_s": round(truck_service, 3),
            "waiting_s": round(truck_waiting, 3),
            "max_finish_time_s": round(truck_finish, 3),
        })

    missing = sorted(expected_nodes - set(covered))
    duplicates = sorted(node for node in set(covered) if covered.count(node) != 1)
    if missing:
        errors.append(f"missing {len(missing)} customer nodes")
    if duplicates:
        errors.append(f"duplicated {len(duplicates)} customer nodes")
    if len(covered) != len(expected_nodes):
        errors.append(f"served {len(covered)} visits for {len(expected_nodes)} customer nodes")

    return {
        "ok": not errors,
        "errors": errors,
        "objective_mode": objective_mode,
        "objective_contract": (
            "duration_s" if objective_mode == "time"
            else "distance_m + 0.25 * duration_s" if objective_mode == "hybrid"
            else "distance_m"
        ),
        "route_start_time_s": round(float(route_start_time_s), 3),
        "use_time_window": bool(use_time_window),
        "objective": round(total_objective, 6),
        "total_distance_m": round(total_distance, 3),
        "total_travel_time_s": round(total_travel, 3),
        "total_service_time_s": round(total_service, 3),
        "total_waiting_s": round(total_waiting, 3),
        "max_finish_time_s": round(maximum_finish, 3),
        "route_count": len(parsed_routes),
        "customer_nodes": len(expected_nodes),
        "served_visits": len(covered),
        "routes": route_receipts,
    }


def build_route_schedule(
    dataset: dict[str, Any],
    route_nodes: list[int],
    context: RoutingContext,
    *,
    objective_mode: str = "distance",
    route_start_time_s: float | None = None,
    use_time_window: bool | None = None,
) -> dict[str, Any]:
    """Create the exact driver-facing clock schedule for one physical truck."""
    if context.objective_mode != str(objective_mode):
        return {
            "feasible": False,
            "reason": (
                "routing context objective mismatch: "
                f"context={context.objective_mode}, requested={objective_mode}"
            ),
            "stops": [],
        }
    depot = int(dataset.get("depot", -1))
    customers = {int(item["node"]): item for item in dataset.get("customers") or []}
    contract = dict(dataset.get("routing_contract") or {})
    start_clock = float(
        contract.get("route_start_time_s", 0.0)
        if route_start_time_s is None else route_start_time_s
    )
    enforce_tw = bool(
        contract.get("use_time_window", True)
        if use_time_window is None else use_time_window
    )
    nodes = [int(node) for node in route_nodes]
    if len(nodes) < 2 or nodes[0] != depot or nodes[-1] != depot:
        return {"feasible": False, "reason": "route must start and end at the depot", "stops": []}

    clock = start_clock
    distance_m = travel_time_s = service_time_s = waiting_s = 0.0
    trip_number = 1
    paths: dict[tuple[int, int], list[int]] = {}
    schedule: list[dict[str, Any]] = [{
        "sequence": 0,
        "node_id": depot,
        "trip_number": trip_number,
        "arrival_s": start_clock,
        "service_start_s": start_clock,
        "departure_s": start_clock,
        "waiting_s": 0.0,
        "time_window_status": "depot",
    }]
    feasible = True
    reason = ""
    for sequence, (source, target) in enumerate(zip(nodes, nodes[1:]), start=1):
        path = context.reconstruct(source, target)
        if not path:
            return {"feasible": False, "reason": "route path reconstruction failed", "stops": schedule}
        paths[(source, target)] = path
        leg_distance = leg_time = 0.0
        for u, v in zip(path, path[1:]):
            edge = context.best_edges.get((u, v))
            if edge is None:
                return {"feasible": False, "reason": "missing road edge during scheduling", "stops": schedule}
            leg_distance += max(0.0, float(edge.get("length_m") or 0.0))
            leg_time += max(0.0, float(edge.get("travel_time_s") or 0.0))
        distance_m += leg_distance
        travel_time_s += leg_time
        clock += leg_time

        if target == depot:
            schedule.append({
                "sequence": sequence,
                "node_id": depot,
                "trip_number": trip_number,
                "arrival_s": clock,
                "service_start_s": clock,
                "departure_s": clock,
                "waiting_s": 0.0,
                "time_window_status": "depot",
            })
            if sequence < len(nodes) - 1:
                trip_number += 1
            continue

        item = customers.get(target)
        if item is None:
            return {"feasible": False, "reason": f"unknown customer node {target}", "stops": schedule}
        arrival = clock
        earliest = float(item.get("earliest", 0.0))
        latest = float(item.get("latest", 86400.0))
        service_start = max(arrival, earliest) if enforce_tw else arrival
        wait = max(0.0, earliest - arrival) if enforce_tw else 0.0
        service = max(0.0, float(item.get("service_time_s", 0.0)))
        if not enforce_tw:
            window_status = "not_enforced"
        elif service_start > latest + 1e-6:
            window_status = "late"
            feasible = False
            reason = reason or "time window"
        elif wait > 1e-6:
            window_status = "waiting"
        else:
            window_status = "on_time"
        clock = service_start + service
        waiting_s += wait
        service_time_s += service
        schedule.append({
            "sequence": sequence,
            "node_id": target,
            "trip_number": trip_number,
            "arrival_s": arrival,
            "service_start_s": service_start,
            "departure_s": clock,
            "waiting_s": wait,
            "earliest_s": earliest,
            "latest_s": latest,
            "time_window_status": window_status,
        })

    return {
        "feasible": feasible,
        "reason": reason,
        "stops": schedule,
        "trip_count": max((int(stop["trip_number"]) for stop in schedule), default=0),
        "route_start_time_s": start_clock,
        "finish_time_s": clock,
        "duration_s": max(0.0, clock - start_clock),
        "distance_m": distance_m,
        "travel_time_s": travel_time_s,
        "service_time_s": service_time_s,
        "waiting_s": waiting_s,
        "objective": objective_value(
            objective_mode,
            distance_m=distance_m,
            travel_time_s=travel_time_s,
            service_time_s=service_time_s,
            waiting_s=waiting_s,
        ),
        "paths": paths,
    }


def _evaluate_trip_plan(
    trips: list[list[int]],
    customers: list[dict[str, Any]],
    time_matrix: np.ndarray,
    distance_matrix: np.ndarray,
    objective_mode: str,
    *,
    route_start_time_s: float,
    use_time_window: bool,
) -> RouteMetrics:
    clock = float(route_start_time_s)
    distance_m = travel_time_s = service_time_s = waiting_s = 0.0
    for trip in trips:
        metrics = _evaluate_route(
            trip,
            customers,
            time_matrix,
            distance_matrix,
            objective_mode,
            route_start_time_s=clock,
            use_time_window=use_time_window,
        )
        if not metrics.feasible:
            return metrics
        clock = metrics.finish_time_s
        distance_m += metrics.distance_m
        travel_time_s += metrics.travel_time_s
        service_time_s += metrics.service_time_s
        waiting_s += metrics.waiting_s
    return RouteMetrics(
        True,
        objective_value(
            objective_mode,
            distance_m=distance_m,
            travel_time_s=travel_time_s,
            service_time_s=service_time_s,
            waiting_s=waiting_s,
        ),
        distance_m,
        travel_time_s,
        service_time_s,
        waiting_s,
        clock,
    )


def build_baseline_routes(
    dataset: dict[str, Any],
    *,
    objective_mode: str = "distance",
    route_start_time_s: float | None = None,
    use_time_window: bool | None = None,
    allow_multi_trip: bool | None = None,
    max_trips_per_truck: int | None = None,
) -> dict[str, Any]:
    """Construct a deterministic road-feasible certificate with one shortest-path batch.

    The certificate is a safety/rescue route, not the optimizer. Hard feasibility
    and final metrics use the same fastest-road paths that are later published.
    """
    started = time.perf_counter()
    customers = list(dataset.get("customers") or [])
    trucks = max(1, int(dataset.get("K_trucks") or 1))
    capacity = float(dataset.get("truck_capacity") or 0.0)
    depot = int(dataset["depot"])
    contract = dict(dataset.get("routing_contract") or {})
    start_clock = float(
        contract.get("route_start_time_s", 0.0)
        if route_start_time_s is None else route_start_time_s
    )
    enforce_tw = bool(
        contract.get("use_time_window", True)
        if use_time_window is None else use_time_window
    )
    multi_trip = bool(
        contract.get("allow_multi_trip", False)
        if allow_multi_trip is None else allow_multi_trip
    )
    max_trips = max(1, int(
        contract.get("max_trips_per_truck", 1)
        if max_trips_per_truck is None else max_trips_per_truck
    )) if multi_trip else 1
    if not customers:
        raise ValueError("The current solver instance has no customers")
    if capacity <= 0:
        raise ValueError("Truck capacity must be positive")

    time_matrix, heuristic_distance, routing_context = _routing_matrices(dataset, objective_mode)
    # Build capacity-feasible trip units first. In multi-trip mode these are
    # virtual trip slots, later assigned to physical trucks with a continuous
    # clock and an independently rechecked ordering.
    trip_slot_count = trucks * max_trips
    routes: list[list[int]] = [[] for _ in range(trip_slot_count)]
    loads = [0.0] * trip_slot_count
    metrics = [
        _evaluate_route(
            [], customers, time_matrix, heuristic_distance, objective_mode,
            route_start_time_s=start_clock, use_time_window=enforce_tw,
        )
        for _ in range(trip_slot_count)
    ]
    open_windows = (not enforce_tw) or all(
        float(item.get("earliest", 0.0)) <= 1e-9 and float(item.get("latest", 86400.0)) >= 86399.0
        for item in customers
    )
    placement = _insert_best_open if open_windows else _insert_best

    unassigned: list[int] = []
    active_routes = 0
    order = sorted(
        range(len(customers)),
        key=lambda i: (
            float(customers[i].get("latest", 86400.0)),
            -float(customers[i].get("demand", 0.0)),
            -float(time_matrix[0, i + 1]),
        ),
    )
    for index in order:
        demand = float(customers[index].get("demand", 0.0))
        best: tuple[float, int, list[int], RouteMetrics] | None = None
        for truck_id in range(active_routes):
            if loads[truck_id] + demand > capacity + 1e-9:
                continue
            candidate, candidate_metrics, delta = placement(
                routes[truck_id], index, customers, time_matrix, heuristic_distance, objective_mode,
                route_start_time_s=start_clock, use_time_window=enforce_tw,
            )
            if candidate is None or candidate_metrics is None:
                continue
            score = float(delta)
            if best is None or score < best[0] - 1e-9 or (abs(score - best[0]) <= 1e-9 and truck_id < best[1]):
                best = (score, truck_id, candidate, candidate_metrics)
        if best is None and active_routes < trip_slot_count:
            truck_id = active_routes
            candidate, candidate_metrics, delta = placement(
                routes[truck_id], index, customers, time_matrix, heuristic_distance, objective_mode,
                route_start_time_s=start_clock, use_time_window=enforce_tw,
            )
            if candidate is not None and candidate_metrics is not None:
                best = (float(delta), truck_id, candidate, candidate_metrics)
                active_routes += 1
        if best is None:
            unassigned.append(index)
            continue
        _, truck_id, candidate, candidate_metrics = best
        routes[truck_id] = candidate
        metrics[truck_id] = candidate_metrics
        loads[truck_id] += demand

    private = {"_routing_context": routing_context, "_route_paths": {}}
    if unassigned:
        names = [str((customers[index].get("orders") or [{}])[0].get("name") or customers[index].get("node")) for index in unassigned[:8]]
        return {
            "feasible": False,
            "reason": "The deterministic baseline could not place every customer within capacity/time-window constraints",
            "unassigned_customer_indices": unassigned,
            "unassigned_preview": names,
            "runtime_s": round(time.perf_counter() - started, 4),
            "matrix_shape": list(time_matrix.shape),
            "shortest_path_batches": 1,
            **private,
        }

    # Assign non-empty trip units to physical trucks. Every candidate insertion
    # is evaluated from the previous trip's actual depot-return time.
    physical: list[list[list[int]]] = [[] for _ in range(trucks)]
    trip_units = [route for route in routes if route]
    trip_units.sort(key=lambda trip: (
        min(float(customers[index].get("latest", 86400.0)) for index in trip),
        -sum(float(customers[index].get("demand", 0.0)) for index in trip),
    ))
    for trip in trip_units:
        best_assignment: tuple[float, int, int, RouteMetrics] | None = None
        for truck_id, assigned in enumerate(physical):
            if len(assigned) >= max_trips:
                continue
            base = _evaluate_trip_plan(
                assigned, customers, time_matrix, heuristic_distance, objective_mode,
                route_start_time_s=start_clock, use_time_window=enforce_tw,
            )
            for position in range(len(assigned) + 1):
                candidate_plan = [*assigned[:position], trip, *assigned[position:]]
                candidate_metrics = _evaluate_trip_plan(
                    candidate_plan, customers, time_matrix, heuristic_distance, objective_mode,
                    route_start_time_s=start_clock, use_time_window=enforce_tw,
                )
                if not candidate_metrics.feasible:
                    continue
                delta = candidate_metrics.objective - (base.objective if base.feasible else 0.0)
                key = (float(delta), truck_id, position)
                if best_assignment is None or key < best_assignment[:3]:
                    best_assignment = (float(delta), truck_id, position, candidate_metrics)
        if best_assignment is None:
            return {
                "feasible": False,
                "reason": "Trip units could not be assigned to physical trucks with a continuous time-window clock",
                "runtime_s": round(time.perf_counter() - started, 4),
                "matrix_shape": list(time_matrix.shape),
                "shortest_path_batches": 1,
                **private,
            }
        _, truck_id, position, _ = best_assignment
        physical[truck_id].insert(position, trip)

    parsed_routes: list[dict[str, Any]] = []
    route_summaries: list[dict[str, Any]] = []
    route_paths: dict[tuple[int, int], list[int]] = {}
    covered: list[int] = []
    exact_ok = True
    exact_reason = ""
    total_objective = 0.0
    for truck_id, trips in enumerate(physical):
        if not trips:
            continue
        clock = start_clock
        truck_distance = truck_travel = truck_service = truck_waiting = 0.0
        trip_loads: list[float] = []
        route_nodes = [depot]
        for trip in trips:
            exact, paths = _exact_route_metrics(
                trip, customers, depot, routing_context, objective_mode,
                route_start_time_s=clock, use_time_window=enforce_tw,
            )
            if not exact.feasible:
                exact_ok = False
                exact_reason = exact.reason
                break
            route_paths.update(paths)
            clock = exact.finish_time_s
            truck_distance += exact.distance_m
            truck_travel += exact.travel_time_s
            truck_service += exact.service_time_s
            truck_waiting += exact.waiting_s
            trip_loads.append(sum(float(customers[index].get("demand", 0.0)) for index in trip))
            route_nodes.extend(int(customers[index]["node"]) for index in trip)
            route_nodes.append(depot)
            covered.extend(trip)
        if not exact_ok:
            break
        truck_objective = objective_value(
            objective_mode,
            distance_m=truck_distance,
            travel_time_s=truck_travel,
            service_time_s=truck_service,
            waiting_s=truck_waiting,
        )
        total_objective += truck_objective
        parsed_routes.append({"truck_id": truck_id, "route_nodes": route_nodes})
        route_summaries.append({
            "truck_id": truck_id,
            "customer_nodes": sum(len(trip) for trip in trips),
            "trips": len(trips),
            "trip_loads": [round(load, 3) for load in trip_loads],
            "load": round(max(trip_loads, default=0.0), 3),
            "capacity": capacity,
            "objective": round(truck_objective, 6),
            "distance_m": round(truck_distance, 3),
            "travel_time_s": round(truck_travel, 3),
            "service_time_s": round(truck_service, 3),
            "waiting_s": round(truck_waiting, 3),
            "finish_time_s": round(clock, 3),
        })

    coverage_ok = sorted(covered) == list(range(len(customers))) and len(set(covered)) == len(customers)
    feasible = bool(coverage_ok and exact_ok)
    return {
        "feasible": feasible,
        "reason": "" if feasible else (exact_reason or "Baseline coverage validation failed"),
        "routes": parsed_routes if feasible else [],
        "route_summaries": route_summaries if feasible else [],
        "customer_nodes": len(customers),
        "active_trucks": len(parsed_routes) if feasible else 0,
        "total_trips": sum(item["trips"] for item in route_summaries) if feasible else 0,
        "total_objective": round(total_objective, 6) if feasible else 0.0,
        "total_distance_m": round(sum(item["distance_m"] for item in route_summaries), 3) if feasible else 0.0,
        "max_finish_time_s": round(max((item["finish_time_s"] for item in route_summaries), default=0.0), 3) if feasible else 0.0,
        "runtime_s": round(time.perf_counter() - started, 4),
        "matrix_shape": list(time_matrix.shape),
        "assignment_source": "fast_local_insertion_certificate" if open_windows else "compact_deterministic_best_insertion",
        "objective_mode": objective_mode,
        "objective_contract": (
            "duration_s" if objective_mode == "time"
            else "distance_m + 0.25 * duration_s" if objective_mode == "hybrid"
            else "distance_m"
        ),
        "route_start_time_s": round(start_clock, 3),
        "use_time_window": enforce_tw,
        "allow_multi_trip": multi_trip,
        "max_trips_per_truck": max_trips,
        "shortest_path_batches": 1,
        "distance_heuristic": "great_circle_for_assignment; selected_objective_road_path_for_published_metrics",
        "_routing_context": routing_context,
        "_route_paths": route_paths,
    }
