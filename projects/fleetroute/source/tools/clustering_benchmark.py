
# =============================================================================
# PURPOSE
# =============================================================================
# Runs every clustering method available in cluster.cpp, shows the important
# results directly in Colab, creates presentation-ready PNG figures, preserves
# the solver-compatible clusters.csv contract, and packages all benchmark
# evidence into one ZIP.
#
# Root solver contract:
#     /content/clusters.csv -> node,cluster
#
# Explicit benchmark structure:
#     /content/Clustering/
#       Protocol/
#       Methods/
#       CSV/
#       PNG/
#       Logs/
#       Selected/
#       Presentation/
#
# The complete /content/Clustering folder is flushed on each run.
# =============================================================================

from __future__ import annotations

import hashlib
import heapq
import json
import math
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

try:
    from IPython.display import Image, Markdown, display
except Exception:
    display = print
    Image = None
    Markdown = None


# =============================================================================
# CONFIGURATION
# =============================================================================

INPUT_FILE = Path(os.environ.get("VRP_INPUT_TXT", "/content/input.txt"))
DATASET_JSON = Path(os.environ.get("VRP_DATASET_JSON", "/content/dataset.json"))
CLUSTER_CPP = Path(os.environ.get("VRP_CLUSTER_CPP", "/content/cluster.cpp"))
CLUSTER_EXE = Path(os.environ.get("VRP_CLUSTER_EXE", "/content/cluster"))

OUTPUT_ROOT = Path(os.environ.get("VRP_CLUSTERING_OUTPUT", "/content/Clustering"))
ROOT_OUTPUT_DIR = Path(os.environ.get("VRP_CLUSTER_ROOT", str(OUTPUT_ROOT.parent)))
FLUSH_OUTPUT_ROOT = True

ROAD_COST = "time"          # "time" or "distance"
SEED = 42
ITERS = 100

# Run every method for a complete benchmark and visual comparison.
RUN_BASELINE_METHODS = True
RUN_GEOMETRIC_METHODS = True
RUN_PAPER_METHODS = True
RUN_ROAD_REFERENCE_METHODS = True
RUN_LEGACY_SPECTRAL_METHODS = True

# Show tables and generated figures directly in the Colab output.
DISPLAY_TABLES_INLINE = False
DISPLAY_FIGURES_INLINE = False
DISPLAY_ALL_METHOD_MAPS_INLINE = False

# Technical presentation system.
# Cluster IDs are categorical; they are deliberately NOT mapped to a rainbow
# or continuous numeric colormap.
PRESENTATION_COLORS = {
    "navy": "#0B1F3A",
    "ink": "#172033",
    "teal": "#0F766E",
    "blue": "#2563EB",
    "cyan": "#0E7490",
    "indigo": "#4F46E5",
    "amber": "#B7791F",
    "green": "#15803D",
    "slate": "#475569",
    "muted": "#64748B",
    "road": "#A8B3C2",
    "grid": "#E7ECF2",
    "border": "#CBD5E1",
    "paper": "#FFFFFF",
    "panel": "#F8FAFC",
    "danger": "#B91C1C",
    "success": "#15803D",
}

# Only a small restrained set is repeated. Cluster structure is primarily
# communicated by boundaries, medoid links, and spatial grouping—not by a
# rainbow scale.
TECHNICAL_CLUSTER_PALETTE = [
    "#0F766E",  # teal
    "#2563EB",  # blue
    "#475569",  # slate
    "#0E7490",  # cyan
    "#4F46E5",  # indigo
    "#B7791F",  # muted amber
    "#15803D",  # green
    "#64748B",  # neutral slate
]


def choose_presentation_font() -> str:
    """Choose a clean font from Matplotlib's validated font registry."""
    preferred = [
        "Inter",
        "Aptos",
        "Arial",
        "Liberation Sans",
        "DejaVu Sans",
    ]

    # fontManager.ttflist contains fonts Matplotlib has already validated.
    # This avoids crashing on malformed/non-font files returned by a raw
    # operating-system font scan.
    available = {
        font_entry.name
        for font_entry in font_manager.fontManager.ttflist
        if getattr(font_entry, "name", None)
    }

    for font_name in preferred:
        if font_name in available:
            return font_name

    return "DejaVu Sans"


PRESENTATION_FONT = choose_presentation_font()

plt.rcParams.update(
    {
        "font.family": PRESENTATION_FONT,
        "font.size": 10.5,
        "axes.titlesize": 14,
        "axes.titleweight": "semibold",
        "axes.labelsize": 10.5,
        "axes.labelcolor": PRESENTATION_COLORS["slate"],
        "axes.edgecolor": PRESENTATION_COLORS["border"],
        "axes.linewidth": 0.8,
        "xtick.color": PRESENTATION_COLORS["slate"],
        "ytick.color": PRESENTATION_COLORS["slate"],
        "text.color": PRESENTATION_COLORS["ink"],
        "figure.facecolor": PRESENTATION_COLORS["paper"],
        "axes.facecolor": PRESENTATION_COLORS["paper"],
        "savefig.facecolor": PRESENTATION_COLORS["paper"],
        "savefig.edgecolor": PRESENTATION_COLORS["paper"],
        "grid.color": PRESENTATION_COLORS["grid"],
        "grid.linewidth": 0.6,
        "grid.alpha": 0.75,
        "legend.frameon": True,
        "legend.framealpha": 0.96,
        "legend.edgecolor": PRESENTATION_COLORS["border"],
    }
)

# ROOT_MODE controls only the solver-facing /content/clusters.csv.
# It does not hide or discard results from the other methods.
ROOT_MODE = os.environ.get("VRP_CLUSTER_ROOT_MODE", "road_savings")

# Sparse spectral parameters.
SPECTRAL_NEIGHBORS = 8
SPECTRAL_SIGMA_RANK = 8
SPECTRAL_LANCZOS_DIM = 0
SPECTRAL_EIG_TOL = 1e-8

# Directed parallel Clarke-Wright Savings parameters.
SAVINGS_VARIANTS = 8
SAVINGS_NOISE = 0.025
SAVINGS_TARGET_ROUTES = 0
SAVINGS_TARGET_EXTRA_ROUTES = 1
SAVINGS_LIGHT_POLISH_ROUNDS = 2
SAVINGS_POLISH_TIME_S = 0.50
SAVINGS_CHECK_TW = True

# Build profile.
COMPILE = True
SYNTAX_FLAGS = ["-std=c++17", "-O0", "-fsyntax-only"]
BUILD_FLAGS = ["-O2", "-std=c++17", "-pthread"]

# Serious evidence, not plot-first output.
COMPUTE_ROAD_EVIDENCE = True
GENERATE_FIGURES = True
CREATE_ZIP = True


# =============================================================================
# GENERAL HELPERS
# =============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def flush_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

    if not FLUSH_OUTPUT_ROOT:
        return

    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)

    return h.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_process(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()

    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    wall_s = time.perf_counter() - started

    payload = {
        "command": cmd,
        "command_text": " ".join(cmd),
        "returncode": int(result.returncode),
        "wall_s": float(wall_s),
        "output": result.stdout,
    }

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with return code {result.returncode}:\n"
            f"{payload['command_text']}\n\n{result.stdout}"
        )

    return payload


def safe_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


# =============================================================================
# INPUT AND DATASET PARSING
# =============================================================================

def parse_input_txt(path: Path) -> dict[str, Any]:
    tokens = path.read_text(encoding="utf-8").split()
    p = 0

    def take_int() -> int:
        nonlocal p
        value = int(tokens[p])
        p += 1
        return value

    def take_float() -> float:
        nonlocal p
        value = float(tokens[p])
        p += 1
        return value

    N = take_int()
    M = take_int()
    K = take_int()
    depot = take_int()

    edges: list[dict[str, Any]] = []

    for _ in range(M):
        u = take_int()
        v = take_int()
        length_m = take_float()
        speed_kph = take_float()
        speed_ms = max(1e-12, speed_kph * 1000.0 / 3600.0)

        edges.append(
            {
                "u": u,
                "v": v,
                "length_m": length_m,
                "speed_kph": speed_kph,
                "travel_time_s": length_m / speed_ms,
            }
        )

    customer_count = take_int()
    customers: list[dict[str, Any]] = []

    for customer_index in range(customer_count):
        customers.append(
            {
                "customer_index": customer_index,
                "node": take_int(),
                "demand": take_float(),
                "service_time_s": take_float(),
                "earliest": take_float(),
                "latest": take_float(),
            }
        )

    capacity = take_float()

    if p != len(tokens):
        raise ValueError(
            f"input.txt parse ended at token {p}, "
            f"but the file contains {len(tokens)} tokens."
        )

    customer_nodes = [int(c["node"]) for c in customers]

    if len(set(customer_nodes)) != len(customer_nodes):
        raise ValueError("input.txt contains duplicate customer nodes.")

    if not (0 <= depot < N):
        raise ValueError("Depot index is outside 0..N-1.")

    if any(not (0 <= node < N) for node in customer_nodes):
        raise ValueError("A customer node is outside 0..N-1.")

    return {
        "N": N,
        "M": M,
        "K": K,
        "depot": depot,
        "edges": edges,
        "customers": customers,
        "customer_count": customer_count,
        "capacity": capacity,
        "total_demand": float(sum(c["demand"] for c in customers)),
        "fleet_capacity": float(K * capacity),
    }


def load_dataset_json(path: Path) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))

    nodes: dict[int, dict[str, Any]] = {}

    for raw in data.get("nodes", []):
        node_id = int(raw["id"])
        nodes[node_id] = {
            "id": node_id,
            "osm_id": raw.get("osm_id"),
            "lon": float(raw.get("lon", 0.0)),
            "lat": float(raw.get("lat", 0.0)),
            "type": raw.get("type", "normal"),
        }

    return data, nodes


# =============================================================================
# TERMINAL ROAD MATRIX FOR INDEPENDENT EVIDENCE
# =============================================================================

def build_adjacency(
    meta: dict[str, Any],
    cost_mode: str,
) -> list[list[tuple[int, float]]]:
    adjacency: list[list[tuple[int, float]]] = [
        [] for _ in range(int(meta["N"]))
    ]

    key = "travel_time_s" if cost_mode == "time" else "length_m"

    for edge in meta["edges"]:
        adjacency[int(edge["u"])].append(
            (int(edge["v"]), float(edge[key]))
        )

    return adjacency


def dijkstra_to_terminals(
    source: int,
    adjacency: list[list[tuple[int, float]]],
    terminal_index: dict[int, int],
) -> np.ndarray:
    terminal_count = len(terminal_index)
    result = np.full(terminal_count, np.inf, dtype=np.float64)

    dist = [math.inf] * len(adjacency)
    dist[source] = 0.0

    pq: list[tuple[float, int]] = [(0.0, source)]
    remaining = terminal_count

    while pq and remaining > 0:
        du, u = heapq.heappop(pq)

        if du != dist[u]:
            continue

        terminal_pos = terminal_index.get(u)

        if terminal_pos is not None and not math.isfinite(result[terminal_pos]):
            result[terminal_pos] = du
            remaining -= 1

        for v, weight in adjacency[u]:
            candidate = du + weight

            if candidate < dist[v]:
                dist[v] = candidate
                heapq.heappush(pq, (candidate, v))

    return result


def build_terminal_matrix(
    meta: dict[str, Any],
    cost_mode: str,
) -> tuple[list[int], np.ndarray, float]:
    started = time.perf_counter()

    terminal_nodes = [
        int(meta["depot"]),
        *[int(c["node"]) for c in meta["customers"]],
    ]

    terminal_index = {
        node: index for index, node in enumerate(terminal_nodes)
    }

    adjacency = build_adjacency(meta, cost_mode)

    matrix = np.empty(
        (len(terminal_nodes), len(terminal_nodes)),
        dtype=np.float64,
    )

    for row, source in enumerate(terminal_nodes):
        matrix[row, :] = dijkstra_to_terminals(
            source,
            adjacency,
            terminal_index,
        )

        if row == 0 or (row + 1) % 25 == 0 or row + 1 == len(terminal_nodes):
            print(
                f"[road-evidence] terminal source "
                f"{row + 1}/{len(terminal_nodes)}"
            )

    if not np.isfinite(matrix).all():
        bad_count = int((~np.isfinite(matrix)).sum())
        raise RuntimeError(
            f"Independent terminal matrix has {bad_count} unreachable pairs."
        )

    return terminal_nodes, matrix, time.perf_counter() - started


# =============================================================================
# ASSIGNMENT VALIDATION AND ROAD-QUALITY EVIDENCE
# =============================================================================

def validate_clusters_csv(
    clusters_path: Path,
    meta: dict[str, Any],
) -> pd.DataFrame:
    df = pd.read_csv(clusters_path)

    if list(df.columns) != ["node", "cluster"]:
        raise ValueError(
            f"{clusters_path} must preserve the exact solver contract "
            "with columns: node,cluster"
        )

    if df.empty:
        raise ValueError(f"{clusters_path} is empty.")

    if df["node"].isna().any() or df["cluster"].isna().any():
        raise ValueError(f"{clusters_path} contains missing values.")

    df["node"] = df["node"].astype(int)
    df["cluster"] = df["cluster"].astype(int)

    expected = [int(c["node"]) for c in meta["customers"]]
    expected_set = set(expected)
    actual = df["node"].tolist()
    actual_set = set(actual)

    if len(actual) != len(actual_set):
        duplicate_nodes = (
            df[df["node"].duplicated(keep=False)]["node"]
            .astype(int)
            .tolist()
        )
        raise ValueError(
            f"{clusters_path} contains duplicate customer nodes: "
            f"{duplicate_nodes[:20]}"
        )

    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)

    if missing:
        raise ValueError(
            f"{clusters_path} is missing customer nodes: {missing[:20]}"
        )

    if extra:
        raise ValueError(
            f"{clusters_path} contains non-customer nodes: {extra[:20]}"
        )

    K = int(meta["K"])

    if ((df["cluster"] < 0) | (df["cluster"] >= K)).any():
        invalid = df.loc[
            (df["cluster"] < 0) | (df["cluster"] >= K),
            ["node", "cluster"],
        ]
        raise ValueError(
            f"{clusters_path} contains invalid cluster IDs:\n{invalid.head(20)}"
        )

    return df


def nearest_neighbor_route_proxy(
    member_customer_indices: list[int],
    directed_terminal_matrix: np.ndarray,
) -> tuple[float, list[int]]:
    if not member_customer_indices:
        return 0.0, []

    unvisited = set(member_customer_indices)
    route: list[int] = []
    current_terminal = 0
    total = 0.0

    while unvisited:
        next_customer = min(
            unvisited,
            key=lambda customer_index: (
                directed_terminal_matrix[
                    current_terminal,
                    customer_index + 1,
                ],
                customer_index,
            ),
        )

        next_terminal = next_customer + 1
        total += float(
            directed_terminal_matrix[current_terminal, next_terminal]
        )
        route.append(next_customer)
        current_terminal = next_terminal
        unvisited.remove(next_customer)

    total += float(directed_terminal_matrix[current_terminal, 0])

    return total, route


def evaluate_assignment(
    *,
    mode: str,
    clusters_df: pd.DataFrame,
    meta: dict[str, Any],
    dataset_nodes: dict[int, dict[str, Any]],
    terminal_matrix: np.ndarray | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    customer_df = pd.DataFrame(meta["customers"]).copy()

    assignment = customer_df.merge(
        clusters_df,
        on="node",
        how="left",
        validate="one_to_one",
    )

    assignment["mode"] = mode
    assignment["capacity"] = float(meta["capacity"])

    assignment["lon"] = assignment["node"].map(
        lambda node: dataset_nodes.get(int(node), {}).get("lon", np.nan)
    )
    assignment["lat"] = assignment["node"].map(
        lambda node: dataset_nodes.get(int(node), {}).get("lat", np.nan)
    )
    assignment["osm_id"] = assignment["node"].map(
        lambda node: dataset_nodes.get(int(node), {}).get("osm_id")
    )

    K = int(meta["K"])
    capacity = float(meta["capacity"])

    if terminal_matrix is not None:
        sym_matrix = 0.5 * (terminal_matrix + terminal_matrix.T)
    else:
        sym_matrix = None

    cluster_rows: list[dict[str, Any]] = []
    medoid_by_cluster: dict[int, int | None] = {}
    distance_to_medoid: dict[int, float] = {}
    route_rank_by_customer: dict[int, int] = {}

    for cluster_id in range(K):
        group = assignment[assignment["cluster"] == cluster_id].copy()
        member_indices = group["customer_index"].astype(int).tolist()

        count = len(member_indices)
        load = float(group["demand"].sum())
        utilization = load / capacity if capacity > 0 else math.nan
        overload = max(0.0, load - capacity)

        medoid_customer_index: int | None = None
        medoid_node: int | None = None
        mean_to_medoid = math.nan
        max_to_medoid = math.nan
        mean_pairwise = math.nan
        route_proxy_cost = 0.0
        route_proxy_customer_indices: list[int] = []

        if member_indices and sym_matrix is not None:
            terminals = [idx + 1 for idx in member_indices]
            sub = sym_matrix[np.ix_(terminals, terminals)]
            row_sums = sub.sum(axis=1)
            local_medoid = int(np.argmin(row_sums))
            medoid_customer_index = member_indices[local_medoid]
            medoid_node = int(
                meta["customers"][medoid_customer_index]["node"]
            )

            medoid_distances = sub[local_medoid, :]
            mean_to_medoid = float(np.mean(medoid_distances))
            max_to_medoid = float(np.max(medoid_distances))

            if len(member_indices) >= 2:
                upper = sub[np.triu_indices(len(member_indices), k=1)]
                mean_pairwise = float(np.mean(upper))
            else:
                mean_pairwise = 0.0

            route_proxy_cost, route_proxy_customer_indices = (
                nearest_neighbor_route_proxy(
                    member_indices,
                    terminal_matrix,
                )
            )

            medoid_terminal = medoid_customer_index + 1

            for customer_index in member_indices:
                distance_to_medoid[customer_index] = float(
                    sym_matrix[customer_index + 1, medoid_terminal]
                )

            for rank, customer_index in enumerate(
                route_proxy_customer_indices,
                start=1,
            ):
                route_rank_by_customer[customer_index] = rank

        elif member_indices:
            medoid_customer_index = member_indices[0]
            medoid_node = int(
                meta["customers"][medoid_customer_index]["node"]
            )

        medoid_by_cluster[cluster_id] = medoid_customer_index

        route_nodes = [
            int(meta["customers"][idx]["node"])
            for idx in route_proxy_customer_indices
        ]

        cluster_rows.append(
            {
                "mode": mode,
                "cluster": cluster_id,
                "count": count,
                "load": load,
                "capacity": capacity,
                "utilization": utilization,
                "overload": overload,
                "medoid_customer_index": medoid_customer_index,
                "medoid_node": medoid_node,
                "mean_road_cost_to_medoid": mean_to_medoid,
                "max_road_cost_to_medoid": max_to_medoid,
                "mean_pairwise_sym_road_cost": mean_pairwise,
                "nn_route_proxy_cost": route_proxy_cost,
                "nn_route_proxy_nodes": "|".join(map(str, route_nodes)),
                "centroid_lon": (
                    float(group["lon"].mean()) if count else math.nan
                ),
                "centroid_lat": (
                    float(group["lat"].mean()) if count else math.nan
                ),
            }
        )

    cluster_metrics = pd.DataFrame(cluster_rows)

    assignment["cluster_count"] = assignment["cluster"].map(
        cluster_metrics.set_index("cluster")["count"]
    )
    assignment["cluster_load"] = assignment["cluster"].map(
        cluster_metrics.set_index("cluster")["load"]
    )
    assignment["cluster_utilization"] = assignment["cluster"].map(
        cluster_metrics.set_index("cluster")["utilization"]
    )
    assignment["cluster_overload"] = assignment["cluster"].map(
        cluster_metrics.set_index("cluster")["overload"]
    )
    assignment["medoid_node"] = assignment["cluster"].map(
        cluster_metrics.set_index("cluster")["medoid_node"]
    )
    assignment["distance_to_medoid_road_cost"] = assignment[
        "customer_index"
    ].map(distance_to_medoid)
    assignment["nn_route_rank"] = assignment[
        "customer_index"
    ].map(route_rank_by_customer)
    assignment["is_medoid"] = (
        assignment["node"] == assignment["medoid_node"]
    )

    total_overload = float(cluster_metrics["overload"].sum())
    max_overload = float(cluster_metrics["overload"].max())
    used_clusters = int((cluster_metrics["count"] > 0).sum())
    empty_clusters = int((cluster_metrics["count"] == 0).sum())
    load_std = float(cluster_metrics["load"].std(ddof=0))
    utilization_mean = float(cluster_metrics["utilization"].mean())
    utilization_min = float(cluster_metrics["utilization"].min())
    utilization_max = float(cluster_metrics["utilization"].max())

    nonempty_metrics = cluster_metrics[cluster_metrics["count"] > 0]

    total_proxy = float(cluster_metrics["nn_route_proxy_cost"].sum())

    weighted_mean_to_medoid = math.nan
    weighted_mean_pairwise = math.nan

    if terminal_matrix is not None and not nonempty_metrics.empty:
        counts = nonempty_metrics["count"].to_numpy(dtype=float)

        weighted_mean_to_medoid = float(
            np.average(
                nonempty_metrics["mean_road_cost_to_medoid"],
                weights=counts,
            )
        )

        pair_weights = counts * np.maximum(counts - 1.0, 1.0)

        weighted_mean_pairwise = float(
            np.average(
                nonempty_metrics["mean_pairwise_sym_road_cost"],
                weights=pair_weights,
            )
        )

    hard_assignment_feasible = (
        len(assignment) == int(meta["customer_count"])
        and assignment["cluster"].notna().all()
        and total_overload <= 1e-7
    )

    method_metrics = {
        "mode": mode,
        "customer_count": int(meta["customer_count"]),
        "K": K,
        "used_clusters": used_clusters,
        "empty_clusters": empty_clusters,
        "total_demand": float(meta["total_demand"]),
        "fleet_capacity": float(meta["fleet_capacity"]),
        "total_overload": total_overload,
        "max_overload": max_overload,
        "load_std": load_std,
        "mean_utilization": utilization_mean,
        "min_utilization": utilization_min,
        "max_utilization": utilization_max,
        "nn_route_proxy_total_cost": total_proxy,
        "weighted_mean_road_cost_to_medoid": weighted_mean_to_medoid,
        "weighted_mean_pairwise_sym_road_cost": weighted_mean_pairwise,
        "hard_assignment_feasible": bool(hard_assignment_feasible),
    }

    return assignment, cluster_metrics, method_metrics



# =============================================================================
# RESEARCH FIGURE HELPERS
# =============================================================================

def build_road_segments(meta, dataset_nodes):
    """Return road edges in geographic coordinates."""
    segments = []

    for edge in meta["edges"]:
        u = int(edge["u"])
        v = int(edge["v"])

        if u not in dataset_nodes or v not in dataset_nodes:
            continue

        a = dataset_nodes[u]
        b = dataset_nodes[v]

        segments.append(
            [
                (float(a["lon"]), float(a["lat"])),
                (float(b["lon"]), float(b["lat"])),
            ]
        )

    return segments


def lonlat_to_local_km(lon, lat, lon0, lat0):
    """
    Equirectangular local projection centred on the depot.

    Using kilometres makes the axes physically meaningful and avoids the
    misleading equal scaling of raw longitude/latitude degrees.
    """
    km_per_degree_lon = 111.320 * math.cos(math.radians(lat0))
    km_per_degree_lat = 110.574

    x_km = (np.asarray(lon, dtype=float) - lon0) * km_per_degree_lon
    y_km = (np.asarray(lat, dtype=float) - lat0) * km_per_degree_lat

    return x_km, y_km


def project_road_segments_to_km(road_segments, lon0, lat0):
    projected = []

    for segment in road_segments:
        (lon1, lat1), (lon2, lat2) = segment
        x, y = lonlat_to_local_km(
            [lon1, lon2],
            [lat1, lat2],
            lon0,
            lat0,
        )
        projected.append([(float(x[0]), float(y[0])), (float(x[1]), float(y[1]))])

    return projected


def convex_hull_xy(points):
    """Monotonic-chain convex hull with no SciPy dependency."""
    unique = sorted(
        {
            (float(point[0]), float(point[1]))
            for point in points
            if math.isfinite(float(point[0]))
            and math.isfinite(float(point[1]))
        }
    )

    if len(unique) <= 2:
        return unique

    def cross(origin, a, b):
        return (
            (a[0] - origin[0]) * (b[1] - origin[1])
            - (a[1] - origin[1]) * (b[0] - origin[0])
        )

    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def prepare_metric_map_data(
    assignment_df,
    meta,
    dataset_nodes,
    road_segments,
):
    depot = int(meta["depot"])
    depot_info = dataset_nodes.get(depot)

    if depot_info is None:
        raise ValueError(f"Depot {depot} has no coordinate in dataset.json")

    lon0 = float(depot_info["lon"])
    lat0 = float(depot_info["lat"])

    valid = assignment_df.dropna(subset=["lon", "lat"]).copy()
    valid["x_km"], valid["y_km"] = lonlat_to_local_km(
        valid["lon"],
        valid["lat"],
        lon0,
        lat0,
    )

    projected_roads = project_road_segments_to_km(
        road_segments,
        lon0,
        lat0,
    )

    return valid, projected_roads


def draw_road_background(
    ax,
    projected_road_segments,
    linewidth=0.34,
    alpha=0.22,
):
    if not projected_road_segments:
        return

    ax.add_collection(
        LineCollection(
            projected_road_segments,
            colors=PRESENTATION_COLORS["road"],
            linewidths=linewidth,
            alpha=alpha,
            zorder=1,
            rasterized=True,
        )
    )


def technical_cluster_color(cluster_id):
    return TECHNICAL_CLUSTER_PALETTE[
        int(cluster_id) % len(TECHNICAL_CLUSTER_PALETTE)
    ]


def draw_cluster_structure(
    ax,
    valid,
    *,
    draw_spokes=True,
    draw_hulls=True,
    compact=False,
):
    """
    Draw restrained categorical structure.

    No colorbar is used because cluster IDs are labels, not magnitudes.
    Repeated muted colours are supplemented by hulls and medoid links.
    """
    customer_colors = [
        technical_cluster_color(cluster_id)
        for cluster_id in valid["cluster"]
    ]

    medoid_rows = []

    for cluster_id, group in valid.groupby("cluster", sort=True):
        color = technical_cluster_color(cluster_id)
        points = group[["x_km", "y_km"]].to_numpy(dtype=float)

        medoid_group = group[group["is_medoid"] == True]

        if medoid_group.empty:
            center_x = float(group["x_km"].mean())
            center_y = float(group["y_km"].mean())
            distances = (
                (group["x_km"] - center_x) ** 2
                + (group["y_km"] - center_y) ** 2
            )
            medoid_row = group.loc[distances.idxmin()]
        else:
            medoid_row = medoid_group.iloc[0]

        medoid_rows.append(medoid_row)

        if draw_hulls and len(points) >= 3:
            hull = convex_hull_xy(points)

            if len(hull) >= 3:
                hull_array = np.asarray(hull, dtype=float)

                ax.fill(
                    hull_array[:, 0],
                    hull_array[:, 1],
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.65 if not compact else 0.45,
                    alpha=0.045 if not compact else 0.035,
                    zorder=2,
                )

        elif len(points) == 2:
            ax.plot(
                points[:, 0],
                points[:, 1],
                color=color,
                linewidth=0.65,
                alpha=0.32,
                zorder=2,
            )

        if draw_spokes and len(points) > 1:
            mx = float(medoid_row["x_km"])
            my = float(medoid_row["y_km"])

            spoke_segments = [
                [(mx, my), (float(x), float(y))]
                for x, y in points
            ]

            ax.add_collection(
                LineCollection(
                    spoke_segments,
                    colors=color,
                    linewidths=0.42 if not compact else 0.30,
                    alpha=0.075 if not compact else 0.055,
                    zorder=2,
                    rasterized=True,
                )
            )

    ax.scatter(
        valid["x_km"],
        valid["y_km"],
        c=customer_colors,
        s=np.clip(
            13.0 + valid["demand"] * 1.55,
            18.0 if compact else 22.0,
            52.0 if compact else 68.0,
        ),
        alpha=0.88,
        edgecolors="white",
        linewidths=0.42 if not compact else 0.28,
        zorder=3,
        rasterized=True,
    )

    if medoid_rows:
        medoids = pd.DataFrame(medoid_rows)

        ax.scatter(
            medoids["x_km"],
            medoids["y_km"],
            marker="D",
            s=20 if compact else 30,
            facecolors="white",
            edgecolors=PRESENTATION_COLORS["navy"],
            linewidths=0.85,
            alpha=0.96,
            zorder=4,
            rasterized=True,
        )

        # Cluster-ID labels are useful only when the number of clusters is low.
        if not compact and valid["cluster"].nunique() <= 30:
            for _, row in medoids.iterrows():
                ax.annotate(
                    str(int(row["cluster"])),
                    (float(row["x_km"]), float(row["y_km"])),
                    xytext=(4, 4),
                    textcoords="offset points",
                    fontsize=6.4,
                    color=PRESENTATION_COLORS["slate"],
                    zorder=5,
                )


def style_metric_map_axis(ax, *, compact=False):
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_axisbelow(True)
    ax.set_facecolor(PRESENTATION_COLORS["paper"])

    if compact:
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
    else:
        ax.xaxis.set_major_locator(MaxNLocator(nbins=7))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=7))
        ax.grid(
            True,
            linestyle=(0, (2, 4)),
            linewidth=0.55,
            alpha=0.75,
        )
        ax.set_xlabel("East–west offset from depot (km)")
        ax.set_ylabel("North–south offset from depot (km)")

    for spine in ax.spines.values():
        spine.set_color(PRESENTATION_COLORS["border"])
        spine.set_linewidth(0.8)


def save_cluster_map(
    mode,
    assignment_df,
    meta,
    dataset_nodes,
    road_segments,
    output_path,
    subtitle="",
):
    """
    Presentation-ready technical map.

    The visual avoids the previous rainbow ID scale and instead uses muted
    categorical colours, cluster footprints, and medoid links.
    """
    fig, ax = plt.subplots(figsize=(11.2, 8.4))
    fig.patch.set_facecolor(PRESENTATION_COLORS["paper"])

    valid, projected_roads = prepare_metric_map_data(
        assignment_df,
        meta,
        dataset_nodes,
        road_segments,
    )

    draw_road_background(
        ax,
        projected_roads,
        linewidth=0.34,
        alpha=0.17,
    )

    draw_cluster_structure(
        ax,
        valid,
        draw_spokes=True,
        draw_hulls=True,
        compact=False,
    )

    # Depot is exactly at the local projection origin.
    ax.scatter(
        [0.0],
        [0.0],
        marker="*",
        s=175,
        facecolors=PRESENTATION_COLORS["navy"],
        edgecolors="white",
        linewidths=0.85,
        zorder=6,
    )

    style_metric_map_axis(ax, compact=False)

    # Editorial title hierarchy instead of one oversized title line.
    fig.suptitle(
        f"{mode} — road-network clustering",
        x=0.085,
        y=0.968,
        ha="left",
        va="top",
        fontsize=18,
        fontweight="semibold",
        color=PRESENTATION_COLORS["navy"],
    )

    if subtitle:
        fig.text(
            0.085,
            0.925,
            subtitle.replace(" | ", "  ·  "),
            ha="left",
            va="top",
            fontsize=10.2,
            color=PRESENTATION_COLORS["slate"],
        )

    fig.add_artist(
        Line2D(
            [0.085, 0.915],
            [0.905, 0.905],
            transform=fig.transFigure,
            color=PRESENTATION_COLORS["teal"],
            linewidth=1.8,
        )
    )

    used_clusters = int(valid["cluster"].nunique())
    total_overload = float(
        valid[["cluster", "cluster_overload"]]
        .drop_duplicates("cluster")["cluster_overload"]
        .sum()
    )

    status_text = (
        f"{len(valid):,} customers    "
        f"{used_clusters}/{int(meta['K'])} clusters used    "
        f"overload={total_overload:,.2f}"
    )

    ax.text(
        0.012,
        0.015,
        status_text,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=8.2,
        color=PRESENTATION_COLORS["slate"],
        bbox={
            "boxstyle": "round,pad=0.34",
            "facecolor": "white",
            "edgecolor": PRESENTATION_COLORS["border"],
            "alpha": 0.96,
        },
        zorder=10,
    )

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markersize=6,
            markerfacecolor=PRESENTATION_COLORS["teal"],
            markeredgecolor="white",
            label="Customer",
        ),
        Line2D(
            [0],
            [0],
            marker="D",
            linestyle="None",
            markersize=5,
            markerfacecolor="white",
            markeredgecolor=PRESENTATION_COLORS["navy"],
            label="Cluster medoid",
        ),
        Line2D(
            [0],
            [0],
            marker="*",
            linestyle="None",
            markersize=10,
            markerfacecolor=PRESENTATION_COLORS["navy"],
            markeredgecolor="white",
            label=f"Depot {int(meta['depot'])}",
        ),
    ]

    ax.legend(
        handles=legend_handles,
        loc="upper right",
        fontsize=8.2,
        borderpad=0.65,
        labelspacing=0.55,
    )

    # Leave room for title/subtitle.
    fig.subplots_adjust(left=0.085, right=0.96, bottom=0.09, top=0.885)
    fig.savefig(
        output_path,
        dpi=250,
        bbox_inches="tight",
        facecolor=PRESENTATION_COLORS["paper"],
    )
    plt.close(fig)


def save_method_map_grid(
    assignments_all,
    meta,
    dataset_nodes,
    road_segments,
    output_path,
):
    """Clean small-multiple comparison without a rainbow colorbar."""
    modes = assignments_all["mode"].drop_duplicates().astype(str).tolist()

    if not modes:
        return

    cols = 3
    rows = math.ceil(len(modes) / cols)

    fig, axes = plt.subplots(
        rows,
        cols,
        figsize=(17.0, max(6.0, rows * 4.55)),
        squeeze=False,
    )
    fig.patch.set_facecolor(PRESENTATION_COLORS["paper"])

    for ax in axes.flat:
        ax.axis("off")

    for index, mode in enumerate(modes):
        ax = axes.flat[index]
        ax.axis("on")

        group = assignments_all[
            assignments_all["mode"] == mode
        ].dropna(subset=["lon", "lat"])

        valid, projected_roads = prepare_metric_map_data(
            group,
            meta,
            dataset_nodes,
            road_segments,
        )

        draw_road_background(
            ax,
            projected_roads,
            linewidth=0.23,
            alpha=0.15,
        )

        draw_cluster_structure(
            ax,
            valid,
            draw_spokes=True,
            draw_hulls=True,
            compact=True,
        )

        ax.scatter(
            [0.0],
            [0.0],
            marker="*",
            s=70,
            facecolors=PRESENTATION_COLORS["navy"],
            edgecolors="white",
            linewidths=0.55,
            zorder=6,
        )

        style_metric_map_axis(ax, compact=True)

        label = globals().get("METHOD_LABEL_BY_MODE", {}).get(mode, mode)

        ax.set_title(
            label,
            fontsize=11.2,
            fontweight="semibold",
            color=PRESENTATION_COLORS["navy"],
            pad=7,
        )

        ax.text(
            0.02,
            0.02,
            f"{valid['cluster'].nunique()} clusters",
            transform=ax.transAxes,
            fontsize=7.2,
            color=PRESENTATION_COLORS["slate"],
            bbox={
                "boxstyle": "round,pad=0.22",
                "facecolor": "white",
                "edgecolor": PRESENTATION_COLORS["border"],
                "alpha": 0.88,
            },
        )

    fig.suptitle(
        "Clustering-method comparison on the same road network",
        x=0.05,
        y=0.985,
        ha="left",
        fontsize=17,
        fontweight="semibold",
        color=PRESENTATION_COLORS["navy"],
    )

    fig.text(
        0.05,
        0.958,
        (
            f"{int(meta['customer_count']):,} customers  ·  "
            f"K={int(meta['K'])}  ·  "
            f"muted categorical grouping with medoid-linked footprints"
        ),
        ha="left",
        fontsize=9.5,
        color=PRESENTATION_COLORS["slate"],
    )

    fig.add_artist(
        Line2D(
            [0.05, 0.95],
            [0.944, 0.944],
            transform=fig.transFigure,
            color=PRESENTATION_COLORS["teal"],
            linewidth=1.6,
        )
    )

    fig.subplots_adjust(
        left=0.045,
        right=0.97,
        bottom=0.04,
        top=0.92,
        wspace=0.10,
        hspace=0.18,
    )
    fig.savefig(
        output_path,
        dpi=235,
        bbox_inches="tight",
        facecolor=PRESENTATION_COLORS["paper"],
    )
    plt.close(fig)


def save_cluster_load_grid(cluster_metrics_all, capacity, output_path):
    """
    Technical utilization heatmap.

    This replaces dozens of tiny bar charts and avoids another rainbow view.
    """
    if cluster_metrics_all.empty:
        return

    pivot = (
        cluster_metrics_all
        .pivot(index="mode", columns="cluster", values="utilization")
        .sort_index()
    )

    labels = [
        globals().get("METHOD_LABEL_BY_MODE", {}).get(str(mode), str(mode))
        for mode in pivot.index
    ]

    utilization_cmap = LinearSegmentedColormap.from_list(
        "technical_utilization",
        [
            "#F8FAFC",
            "#DDEFEA",
            "#8CC7BE",
            "#0F766E",
            "#0B1F3A",
        ],
    )

    finite_values = pivot.to_numpy(dtype=float)
    finite_values = finite_values[np.isfinite(finite_values)]

    vmax = 1.05
    if finite_values.size:
        vmax = max(1.05, float(np.nanpercentile(finite_values, 99)))

    fig_height = max(4.8, 0.42 * len(labels) + 2.4)
    fig, ax = plt.subplots(figsize=(15.5, fig_height))

    image = ax.imshow(
        pivot.to_numpy(dtype=float),
        aspect="auto",
        interpolation="nearest",
        cmap=utilization_cmap,
        vmin=0.0,
        vmax=vmax,
    )

    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_ylabel("Method")
    ax.set_xlabel("Cluster ID")

    cluster_count = pivot.shape[1]
    tick_step = max(1, int(math.ceil(cluster_count / 12)))
    x_ticks = np.arange(0, cluster_count, tick_step)

    ax.set_xticks(x_ticks)
    ax.set_xticklabels([str(int(pivot.columns[i])) for i in x_ticks])

    fig.suptitle(
        "Cluster capacity-utilization matrix",
        x=0.11,
        y=0.985,
        ha="left",
        fontsize=15.5,
        fontweight="semibold",
        color=PRESENTATION_COLORS["navy"],
    )

    fig.text(
        0.11,
        0.925,
        (
            "Sequential navy–teal scale: pale = under-utilized, "
            "dark = near/full capacity"
        ),
        ha="left",
        fontsize=9.2,
        color=PRESENTATION_COLORS["slate"],
    )

    colorbar = fig.colorbar(image, ax=ax, fraction=0.025, pad=0.02)
    colorbar.set_label("Capacity utilization")

    for spine in ax.spines.values():
        spine.set_color(PRESENTATION_COLORS["border"])

    ax.tick_params(labelsize=8.5)
    fig.subplots_adjust(top=0.865)
    fig.savefig(
        output_path,
        dpi=240,
        bbox_inches="tight",
        facecolor=PRESENTATION_COLORS["paper"],
    )
    plt.close(fig)


def write_figure_manifest(figures_dir, report_ready_dir):
    descriptions = {
        "selected_cluster_map.png":
            "Primary geographic visualization of the selected warm start.",
        "method_comparison_grid.png":
            "Side-by-side geographic comparison of validated methods.",
        "cluster_loads_by_method.png":
            "Capacity utilization and overload check by method.",
        "method_total_runtime.png":
            "Total clustering runtime comparison.",
        "method_route_proxy.png":
            "Independent nearest-neighbor route proxy comparison.",
        "method_road_compactness.png":
            "Independent within-cluster road compactness comparison.",
        "cluster_utilization_by_method.png":
            "Per-cluster capacity utilization profiles.",
        "Runtime.png":
            "End-to-end clustering runtime by method.",
        "RouteProxyObjective.png":
            "Independent warm-start route-proxy objective comparison.",
        "RuntimeVsObjective.png":
            "Runtime-quality trade-off and Pareto candidates.",
        "RoadCompactness.png":
            "Within-cluster road-cost compactness comparison.",
        "LoadBalance.png":
            "Dispersion of cluster loads by method.",
        "CapacityUtilization.png":
            "Capacity utilization profile for every method.",
        "ClusterLoads.png":
            "Per-method cluster loads against capacity.",
        "MethodScorecard.png":
            "Presentation-ready clustering benchmark scorecard.",
        "AllMethods.png":
            "Geographic comparison grid for all validated methods.",
    }

    rows = []
    for figure in sorted(figures_dir.glob("*.png")):
        rows.append({
            "figure": figure.name,
            "description": descriptions.get(
                figure.name,
                "Method-specific clustering map or benchmark figure.",
            ),
            "path": str(figure),
        })

    manifest = pd.DataFrame(rows)
    manifest.to_csv(
        report_ready_dir / "figure_manifest.csv",
        index=False,
    )
    return manifest



# =============================================================================
# PRESENTATION STYLE AND BENCHMARK DERIVED METRICS
# =============================================================================

def apply_axis_style(ax, *, title=None, xlabel=None, ylabel=None):
    ax.set_facecolor("white")
    if title is not None:
        ax.set_title(
            title,
            color=PRESENTATION_COLORS["navy"],
            fontsize=14,
            fontweight="bold",
            pad=12,
        )
    if xlabel is not None:
        ax.set_xlabel(xlabel, color=PRESENTATION_COLORS["slate"])
    if ylabel is not None:
        ax.set_ylabel(ylabel, color=PRESENTATION_COLORS["slate"])
    ax.grid(True, axis="y", alpha=0.18, linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CBD5E1")
    ax.spines["bottom"].set_color("#CBD5E1")
    ax.tick_params(colors=PRESENTATION_COLORS["slate"])


METHOD_CATEGORY_COLORS = {
    "baseline": "#64748B",
    "geometric": "#2563EB",
    "paper_method": "#0F766E",
    "road_reference": "#0E7490",
    "legacy_spectral": "#B7791F",
}


def method_bar_colors(labels):
    category_map = globals().get("METHOD_CATEGORY_BY_LABEL", {})

    return [
        METHOD_CATEGORY_COLORS.get(
            category_map.get(str(label), ""),
            PRESENTATION_COLORS["muted"],
        )
        for label in labels
    ]


def add_value_labels(ax, bars, values, formatter):
    if len(bars) > 14:
        return
    for bar, value in zip(bars, values):
        if not math.isfinite(float(value)):
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height(),
            formatter(float(value)),
            ha="center",
            va="bottom",
            fontsize=8,
            color=PRESENTATION_COLORS["slate"],
        )


def derive_method_rankings(method_comparison):
    df = method_comparison.copy()

    rank_specs = [
        ("total_s", "runtime_rank"),
        ("nn_route_proxy_total_cost", "proxy_objective_rank"),
        ("weighted_mean_road_cost_to_medoid", "road_compactness_rank"),
        ("load_std", "load_balance_rank"),
    ]

    for value_column, rank_column in rank_specs:
        if value_column in df.columns:
            values = pd.to_numeric(df[value_column], errors="coerce")
            df[rank_column] = values.rank(
                method="min",
                ascending=True,
                na_option="bottom",
            ).astype("Int64")

    if {
        "total_s",
        "runtime_rank",
        "nn_route_proxy_total_cost",
        "proxy_objective_rank",
    }.issubset(df.columns):
        runtime = pd.to_numeric(df["total_s"], errors="coerce")
        proxy = pd.to_numeric(
            df["nn_route_proxy_total_cost"],
            errors="coerce",
        )

        pareto = []
        for i in range(len(df)):
            if not math.isfinite(float(runtime.iloc[i])) or not math.isfinite(float(proxy.iloc[i])):
                pareto.append(False)
                continue

            dominated = False
            for j in range(len(df)):
                if i == j:
                    continue
                if not math.isfinite(float(runtime.iloc[j])) or not math.isfinite(float(proxy.iloc[j])):
                    continue

                no_worse = (
                    runtime.iloc[j] <= runtime.iloc[i]
                    and proxy.iloc[j] <= proxy.iloc[i]
                )
                strictly_better = (
                    runtime.iloc[j] < runtime.iloc[i]
                    or proxy.iloc[j] < proxy.iloc[i]
                )

                if no_worse and strictly_better:
                    dominated = True
                    break

            pareto.append(not dominated)

        df["pareto_runtime_proxy"] = pareto

    return df


# =============================================================================
# METHOD SPECIFICATIONS
# =============================================================================

METHODS: list[dict[str, Any]] = []


def register_method(
    mode: str,
    label: str,
    category: str,
    paper_role: str,
    selectable: bool,
    flags: list[str],
) -> None:
    METHODS.append(
        {
            "mode": mode,
            "label": label,
            "category": category,
            "paper_role": paper_role,
            "selectable": selectable,
            "flags": flags,
        }
    )


if RUN_BASELINE_METHODS:
    register_method(
        mode="round_robin",
        label="RoundRobin",
        category="baseline",
        paper_role="demand-balanced non-spatial baseline",
        selectable=False,
        flags=[],
    )

if RUN_GEOMETRIC_METHODS:
    register_method(
        mode="sweep",
        label="Sweep",
        category="geometric",
        paper_role="angular sweep around the depot",
        selectable=False,
        flags=["--seed", str(SEED)],
    )
    register_method(
        mode="balanced_kmeans",
        label="BalancedKMeans",
        category="geometric",
        paper_role="capacity-aware coordinate K-means",
        selectable=False,
        flags=[
            "--iters", str(ITERS),
            "--seed", str(SEED),
        ],
    )
    register_method(
        mode="kd_split",
        label="KDSplit",
        category="geometric",
        paper_role="recursive capacity-aware spatial partition",
        selectable=False,
        flags=[],
    )
    register_method(
        mode="spatial_grid",
        label="SpatialGrid",
        category="geometric",
        paper_role="grid-based spatial clustering",
        selectable=False,
        flags=[],
    )

if RUN_LEGACY_SPECTRAL_METHODS:
    register_method(
        mode="spectral_lite",
        label="SpectralLite",
        category="legacy_spectral",
        paper_role="coordinate spectral-lite using dense Jacobi",
        selectable=False,
        flags=[
            "--spectral_neighbors", str(SPECTRAL_NEIGHBORS),
            "--iters", str(ITERS),
            "--seed", str(SEED),
        ],
    )

if RUN_PAPER_METHODS:
    register_method(
        mode="road_savings",
        label="Savings",
        category="paper_method",
        paper_role="directed parallel Clarke-Wright Savings",
        selectable=True,
        flags=[
            "--road_cost", ROAD_COST,
            "--seed", str(SEED),
            "--savings_variants", str(SAVINGS_VARIANTS),
            "--savings_noise", str(SAVINGS_NOISE),
            "--savings_target_routes", str(SAVINGS_TARGET_ROUTES),
            "--savings_target_extra_routes",
            str(SAVINGS_TARGET_EXTRA_ROUTES),
            "--savings_light_polish_rounds",
            str(SAVINGS_LIGHT_POLISH_ROUNDS),
            "--savings_polish_time_s",
            str(SAVINGS_POLISH_TIME_S),
            "--savings_check_tw",
            "true" if SAVINGS_CHECK_TW else "false",
        ],
    )
    register_method(
        mode="road_spectral_sparse",
        label="SparseSpectral",
        category="paper_method",
        paper_role="full sparse road-aware spectral clustering",
        selectable=True,
        flags=[
            "--road_cost", ROAD_COST,
            "--seed", str(SEED),
            "--iters", str(ITERS),
            "--spectral_neighbors", str(SPECTRAL_NEIGHBORS),
            "--spectral_sigma_rank", str(SPECTRAL_SIGMA_RANK),
            "--spectral_lanczos_dim", str(SPECTRAL_LANCZOS_DIM),
            "--spectral_eig_tol", str(SPECTRAL_EIG_TOL),
        ],
    )

if RUN_ROAD_REFERENCE_METHODS:
    register_method(
        mode="network_kmedoids",
        label="KMedoids",
        category="road_reference",
        paper_role="road-cost K-medoids reference",
        selectable=True,
        flags=[
            "--road_cost", ROAD_COST,
            "--iters", str(ITERS),
            "--seed", str(SEED),
        ],
    )
    register_method(
        mode="route_split",
        label="RouteSplit",
        category="road_reference",
        paper_role="road-nearest giant-tour capacity split",
        selectable=True,
        flags=[
            "--road_cost", ROAD_COST,
            "--seed", str(SEED),
        ],
    )

if RUN_LEGACY_SPECTRAL_METHODS:
    register_method(
        mode="road_spectral_lite",
        label="RoadSpectralLite",
        category="legacy_spectral",
        paper_role="legacy road spectral-lite using dense Jacobi",
        selectable=False,
        flags=[
            "--road_cost", ROAD_COST,
            "--spectral_neighbors", str(SPECTRAL_NEIGHBORS),
            "--iters", str(ITERS),
            "--seed", str(SEED),
        ],
    )


METHOD_LABEL_BY_MODE = {
    method["mode"]: method["label"]
    for method in METHODS
}


METHOD_CATEGORY_BY_LABEL = {
    method["label"]: method["category"]
    for method in METHODS
}


# =============================================================================
# PREPARE STRUCTURED OUTPUT
# =============================================================================

flush_directory(OUTPUT_ROOT)

PROTOCOL_DIR = OUTPUT_ROOT / "Protocol"
METHODS_DIR = OUTPUT_ROOT / "Methods"
COMPARISON_DIR = OUTPUT_ROOT / "CSV"
FIGURES_DIR = OUTPUT_ROOT / "PNG"
LOGS_DIR = OUTPUT_ROOT / "Logs"
SELECTED_DIR = OUTPUT_ROOT / "Selected"
REPORT_READY_DIR = OUTPUT_ROOT / "Presentation"

for directory in [
    PROTOCOL_DIR,
    METHODS_DIR,
    COMPARISON_DIR,
    FIGURES_DIR,
    LOGS_DIR,
    SELECTED_DIR,
    REPORT_READY_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)

for required_path in [INPUT_FILE, DATASET_JSON, CLUSTER_CPP]:
    if not required_path.exists():
        raise FileNotFoundError(f"Required file not found: {required_path}")

input_meta = parse_input_txt(INPUT_FILE)
dataset_data, dataset_nodes = load_dataset_json(DATASET_JSON)

dataset_id = (
    dataset_data.get("benchmark_id")
    or f"osm{input_meta['N']}_{input_meta['customer_count']}"
)

run_started_utc = utc_now()

shutil.copy2(INPUT_FILE, PROTOCOL_DIR / "input_snapshot.txt")
shutil.copy2(DATASET_JSON, PROTOCOL_DIR / "dataset_snapshot.json")
shutil.copy2(CLUSTER_CPP, PROTOCOL_DIR / "cluster_snapshot.cpp")

checksums = pd.DataFrame(
    [
        {
            "artifact": "input.txt",
            "path": str(INPUT_FILE),
            "sha256": sha256_file(INPUT_FILE),
        },
        {
            "artifact": "dataset.json",
            "path": str(DATASET_JSON),
            "sha256": sha256_file(DATASET_JSON),
        },
        {
            "artifact": "cluster.cpp",
            "path": str(CLUSTER_CPP),
            "sha256": sha256_file(CLUSTER_CPP),
        },
    ]
)
checksums.to_csv(PROTOCOL_DIR / "checksums.csv", index=False)

protocol = {
    "created_utc": run_started_utc,
    "fleetroute_job_id": os.environ.get("VRP_CLUSTER_JOB_ID"),
    "source_signature": os.environ.get("VRP_CLUSTER_SOURCE_SIGNATURE"),
    "materialization_id": os.environ.get("VRP_CLUSTER_MATERIALIZATION_ID"),
    "dataset_id": dataset_id,
    "N": int(input_meta["N"]),
    "M": int(input_meta["M"]),
    "K": int(input_meta["K"]),
    "depot": int(input_meta["depot"]),
    "customer_count": int(input_meta["customer_count"]),
    "capacity": float(input_meta["capacity"]),
    "total_demand": float(input_meta["total_demand"]),
    "fleet_capacity": float(input_meta["fleet_capacity"]),
    "road_cost": ROAD_COST,
    "seed": SEED,
    "iterations": ITERS,
    "root_mode": ROOT_MODE,
    "methods": METHODS,
    "method_labels": METHOD_LABEL_BY_MODE,
    "display_tables_inline": DISPLAY_TABLES_INLINE,
    "display_figures_inline": DISPLAY_FIGURES_INLINE,
    "syntax_flags": SYNTAX_FLAGS,
    "build_flags": BUILD_FLAGS,
    "python_version": platform.python_version(),
    "platform": platform.platform(),
    "cpu_count": os.cpu_count(),
}
write_json(PROTOCOL_DIR / "protocol.json", protocol)


# =============================================================================
# SAFE COMPILE
# =============================================================================

compile_rows: list[dict[str, Any]] = []

if COMPILE:
    if CLUSTER_EXE.exists():
        CLUSTER_EXE.unlink()

    syntax_cmd = ["g++", *SYNTAX_FLAGS, str(CLUSTER_CPP)]
    syntax_result = run_process(syntax_cmd, check=False)
    write_text(PROTOCOL_DIR / "syntax_check.log", syntax_result["output"])

    compile_rows.append(
        {
            "stage": "syntax_check",
            "command": syntax_result["command_text"],
            "returncode": syntax_result["returncode"],
            "wall_s": syntax_result["wall_s"],
        }
    )

    if syntax_result["returncode"] != 0:
        raise RuntimeError(
            "cluster.cpp syntax check failed.\n\n"
            + syntax_result["output"]
        )

    build_cmd = [
        "g++",
        *BUILD_FLAGS,
        str(CLUSTER_CPP),
        "-o",
        str(CLUSTER_EXE),
    ]
    build_result = run_process(build_cmd, check=False)
    write_text(PROTOCOL_DIR / "compile.log", build_result["output"])

    compile_rows.append(
        {
            "stage": "compile",
            "command": build_result["command_text"],
            "returncode": build_result["returncode"],
            "wall_s": build_result["wall_s"],
        }
    )

    if build_result["returncode"] != 0:
        if CLUSTER_EXE.exists():
            CLUSTER_EXE.unlink()

        raise RuntimeError(
            "cluster.cpp compilation failed.\n\n"
            + build_result["output"]
        )

if not CLUSTER_EXE.exists():
    raise FileNotFoundError(
        f"Compiled cluster executable was not found: {CLUSTER_EXE}"
    )

pd.DataFrame(compile_rows).to_csv(
    PROTOCOL_DIR / "build_timing.csv",
    index=False,
)

compiler_version = run_process(
    ["g++", "--version"],
    check=False,
)
write_text(
    PROTOCOL_DIR / "compiler_version.txt",
    compiler_version["output"],
)


# =============================================================================
# BUILD INDEPENDENT ROAD EVIDENCE ONCE
# =============================================================================

terminal_nodes: list[int] | None = None
terminal_matrix: np.ndarray | None = None
road_evidence_s = 0.0

if COMPUTE_ROAD_EVIDENCE:
    terminal_nodes, terminal_matrix, road_evidence_s = (
        build_terminal_matrix(input_meta, ROAD_COST)
    )

    np.savez_compressed(
        PROTOCOL_DIR / f"terminal_matrix_{ROAD_COST}.npz",
        terminal_nodes=np.asarray(terminal_nodes, dtype=np.int64),
        matrix=terminal_matrix,
    )

write_json(
    PROTOCOL_DIR / "road_evidence.json",
    {
        "enabled": COMPUTE_ROAD_EVIDENCE,
        "road_cost": ROAD_COST,
        "terminal_count": (
            len(terminal_nodes) if terminal_nodes is not None else 0
        ),
        "build_seconds": road_evidence_s,
    },
)


# =============================================================================
# RUN METHODS AND CREATE EVIDENCE
# =============================================================================

method_rows: list[dict[str, Any]] = []
all_cluster_metrics: list[pd.DataFrame] = []
all_assignments: list[pd.DataFrame] = []
run_rows: list[dict[str, Any]] = []

for method_spec in METHODS:
    requested_mode = str(method_spec["mode"])
    method_label = str(method_spec["label"])
    method_category = str(method_spec["category"])
    method_dir = METHODS_DIR / method_label
    method_dir.mkdir(parents=True, exist_ok=True)

    clusters_path = method_dir / "clusters.csv"
    summary_path = method_dir / "cluster_summary.csv"
    timing_path = method_dir / "cluster_timing.csv"

    cmd = [
        str(CLUSTER_EXE),
        "--mode", requested_mode,
        "--input", str(INPUT_FILE),
        "--dataset", str(DATASET_JSON),
        "--out", str(clusters_path),
        "--summary", str(summary_path),
        "--timing", str(timing_path),
        *method_spec["flags"],
    ]

    write_text(method_dir / "command.txt", " ".join(cmd) + "\n")
    write_json(method_dir / "method_config.json", method_spec)

    print("\n" + "=" * 100)
    print(f"RUNNING METHOD: {method_label} [{requested_mode}]")
    print(f"CATEGORY: {method_category}")
    print(f"ROLE: {method_spec['paper_role']}")
    print("=" * 100)

    result = run_process(cmd, check=False)
    write_text(method_dir / "stdout_stderr.txt", result["output"])

    success = (
        result["returncode"] == 0
        and clusters_path.exists()
        and summary_path.exists()
        and timing_path.exists()
    )

    run_row = {
        "label": method_label,
        "requested_mode": requested_mode,
        "category": method_category,
        "paper_role": method_spec["paper_role"],
        "selectable": bool(method_spec["selectable"]),
        "success": bool(success),
        "returncode": int(result["returncode"]),
        "runner_wall_s": float(result["wall_s"]),
        "command": result["command_text"],
        "error": "",
        "method_folder": str(method_dir),
    }

    if not success:
        run_row["error"] = result["output"][-4000:]
        run_rows.append(run_row)
        print(f"FAILED: {requested_mode}")
        continue

    try:
        clusters_df = validate_clusters_csv(
            clusters_path,
            input_meta,
        )

        summary_df = pd.read_csv(summary_path)
        timing_df = pd.read_csv(timing_path)

        if len(timing_df) != 1:
            raise ValueError(
                f"{timing_path} must contain exactly one data row."
            )

        timing_row = {
            key: safe_scalar(value)
            for key, value in timing_df.iloc[0].to_dict().items()
        }

        effective_mode = str(timing_row["effective_mode"])

        assignment_df, cluster_metrics_df, assignment_metrics = (
            evaluate_assignment(
                mode=requested_mode,
                clusters_df=clusters_df,
                meta=input_meta,
                dataset_nodes=dataset_nodes,
                terminal_matrix=terminal_matrix,
            )
        )

        assignment_df.to_csv(
            method_dir / "clusters_enriched.csv",
            index=False,
        )
        cluster_metrics_df.to_csv(
            method_dir / "cluster_metrics.csv",
            index=False,
        )

        # Explicit benchmark exports with human-readable names.
        shutil.copy2(
            clusters_path,
            COMPARISON_DIR / f"{method_label}_Clusters.csv",
        )
        shutil.copy2(
            summary_path,
            COMPARISON_DIR / f"{method_label}_Summary.csv",
        )
        shutil.copy2(
            timing_path,
            COMPARISON_DIR / f"{method_label}_Timing.csv",
        )
        shutil.copy2(
            method_dir / "clusters_enriched.csv",
            COMPARISON_DIR / f"{method_label}_Assignments.csv",
        )
        shutil.copy2(
            method_dir / "cluster_metrics.csv",
            COMPARISON_DIR / f"{method_label}_Metrics.csv",
        )
        shutil.copy2(
            method_dir / "stdout_stderr.txt",
            LOGS_DIR / f"{method_label}.txt",
        )

        summary_total_overload = float(summary_df["overload"].sum())
        summary_count = int(summary_df["count"].sum())

        crosscheck_ok = (
            summary_count == int(input_meta["customer_count"])
            and abs(summary_total_overload) <= 1e-7
            and bool(assignment_metrics["hard_assignment_feasible"])
        )

        method_row = {
            "label": method_label,
            "requested_mode": requested_mode,
            "effective_mode": effective_mode,
            "category": method_category,
            "paper_role": method_spec["paper_role"],
            "selectable": bool(method_spec["selectable"]),
            "success": True,
            "fallback_used": int(timing_row.get("fallback_used", 0) or 0),
            "runner_wall_s": float(result["wall_s"]),
            "crosscheck_ok": bool(crosscheck_ok),
            **assignment_metrics,
            **timing_row,
        }

        method_rows.append(method_row)
        all_cluster_metrics.append(cluster_metrics_df)
        all_assignments.append(assignment_df)

        run_row["effective_mode"] = effective_mode
        run_row["crosscheck_ok"] = bool(crosscheck_ok)
        run_rows.append(run_row)

        method_manifest = {
            "dataset_id": dataset_id,
            "label": method_label,
            "requested_mode": requested_mode,
            "effective_mode": effective_mode,
            "category": method_category,
            "paper_role": method_spec["paper_role"],
            "selectable": bool(method_spec["selectable"]),
            "command": result["command_text"],
            "returncode": result["returncode"],
            "runner_wall_s": result["wall_s"],
            "crosscheck_ok": bool(crosscheck_ok),
            "hard_assignment_feasible": bool(
                assignment_metrics["hard_assignment_feasible"]
            ),
            "output_files": {
                "clusters": str(clusters_path),
                "summary": str(summary_path),
                "timing": str(timing_path),
                "enriched_assignments": str(
                    method_dir / "clusters_enriched.csv"
                ),
                "cluster_metrics": str(
                    method_dir / "cluster_metrics.csv"
                ),
                "stdout_stderr": str(
                    method_dir / "stdout_stderr.txt"
                ),
            },
        }
        write_json(method_dir / "method_manifest.json", method_manifest)

        print(
            f"SUCCESS: requested={requested_mode}, "
            f"effective={effective_mode}, "
            f"total_s={timing_row.get('total_s')}, "
            f"proxy_cost={assignment_metrics['nn_route_proxy_total_cost']}, "
            f"feasible={assignment_metrics['hard_assignment_feasible']}"
        )

    except Exception as exc:
        run_row["success"] = False
        run_row["error"] = str(exc)
        run_rows.append(run_row)
        write_text(method_dir / "validation_error.txt", str(exc) + "\n")
        print(f"VALIDATION FAILED: {requested_mode}: {exc}")


# =============================================================================
# MASTER COMPARISON TABLES
# =============================================================================

run_df = pd.DataFrame(run_rows)
run_df.to_csv(
    COMPARISON_DIR / "MethodRunManifest.csv",
    index=False,
)

if not method_rows:
    raise RuntimeError(
        "No clustering method produced a validated result."
    )

method_comparison = pd.DataFrame(method_rows)
method_comparison = derive_method_rankings(method_comparison)

preferred_columns = [
    "label",
    "requested_mode",
    "effective_mode",
    "category",
    "paper_role",
    "selectable",
    "success",
    "crosscheck_ok",
    "hard_assignment_feasible",
    "fallback_used",
    "customers",
    "K",
    "used_clusters",
    "empty_clusters",
    "total_overload",
    "max_overload",
    "mean_utilization",
    "min_utilization",
    "max_utilization",
    "nn_route_proxy_total_cost",
    "proxy_objective_rank",
    "weighted_mean_road_cost_to_medoid",
    "road_compactness_rank",
    "load_std",
    "load_balance_rank",
    "runtime_rank",
    "pareto_runtime_proxy",
    "weighted_mean_pairwise_sym_road_cost",
    "parse_s",
    "coordinate_s",
    "road_matrix_s",
    "method_s",
    "repair_s",
    "polish_s",
    "write_s",
    "total_s",
    "runner_wall_s",
    "k_eff",
    "candidate_arcs",
    "sparse_edges",
    "lanczos_dimension",
    "lanczos_steps",
    "eig_converged",
    "eig_max_residual",
    "median_local_scale",
    "savings_variants_requested",
    "savings_variants_feasible",
    "savings_best_variant",
    "savings_target_routes",
    "savings_final_routes",
    "savings_light_relocates",
    "savings_hard_feasible",
    "savings_route_cost",
]

ordered_columns = [
    column
    for column in preferred_columns
    if column in method_comparison.columns
]
remaining_columns = [
    column
    for column in method_comparison.columns
    if column not in ordered_columns
]

method_comparison = method_comparison[
    ordered_columns + remaining_columns
]

method_comparison.to_csv(
    COMPARISON_DIR / "MethodComparison.csv",
    index=False,
)

timing_columns = [
    column
    for column in [
        "requested_mode",
        "effective_mode",
        "parse_s",
        "coordinate_s",
        "road_matrix_s",
        "method_s",
        "repair_s",
        "polish_s",
        "write_s",
        "total_s",
        "runner_wall_s",
    ]
    if column in method_comparison.columns
]

method_comparison[timing_columns].to_csv(
    COMPARISON_DIR / "TimingComparison.csv",
    index=False,
)

feasibility_columns = [
    column
    for column in [
        "requested_mode",
        "effective_mode",
        "crosscheck_ok",
        "hard_assignment_feasible",
        "fallback_used",
        "used_clusters",
        "empty_clusters",
        "total_overload",
        "max_overload",
    ]
    if column in method_comparison.columns
]

method_comparison[feasibility_columns].to_csv(
    COMPARISON_DIR / "FeasibilityComparison.csv",
    index=False,
)

objective_columns = [
    column
    for column in [
        "label",
        "requested_mode",
        "effective_mode",
        "category",
        "hard_assignment_feasible",
        "fallback_used",
        "total_s",
        "runtime_rank",
        "nn_route_proxy_total_cost",
        "proxy_objective_rank",
        "weighted_mean_road_cost_to_medoid",
        "road_compactness_rank",
        "load_std",
        "load_balance_rank",
        "total_overload",
        "pareto_runtime_proxy",
    ]
    if column in method_comparison.columns
]

method_comparison[objective_columns].to_csv(
    COMPARISON_DIR / "ObjectiveComparison.csv",
    index=False,
)

cluster_metrics_all = pd.concat(
    all_cluster_metrics,
    ignore_index=True,
)
cluster_metrics_all.to_csv(
    COMPARISON_DIR / "ClusterMetricsAll.csv",
    index=False,
)

assignments_all = pd.concat(
    all_assignments,
    ignore_index=True,
)
assignments_all.to_csv(
    COMPARISON_DIR / "AssignmentsAll.csv",
    index=False,
)


# =============================================================================
# SELECT ROOT METHOD EXPLICITLY
# =============================================================================

available_modes = set(
    method_comparison.loc[
        (
            method_comparison["success"].astype(bool)
            & method_comparison["crosscheck_ok"].astype(bool)
            & method_comparison["hard_assignment_feasible"].astype(bool)
        ),
        "requested_mode",
    ].astype(str)
)

if ROOT_MODE not in available_modes:
    raise RuntimeError(
        f"ROOT_MODE={ROOT_MODE!r} is not a successful, independently "
        f"validated method. Available validated modes: "
        f"{sorted(available_modes)}"
    )

if ROOT_MODE not in METHOD_LABEL_BY_MODE:
    raise RuntimeError(
        f"ROOT_MODE={ROOT_MODE!r} is not registered in METHODS."
    )

selected_label = METHOD_LABEL_BY_MODE[ROOT_MODE]
selected_source_dir = METHODS_DIR / selected_label

selected_files = {
    "clusters.csv": selected_source_dir / "clusters.csv",
    "cluster_summary.csv": selected_source_dir / "cluster_summary.csv",
    "cluster_timing.csv": selected_source_dir / "cluster_timing.csv",
    "clusters_enriched.csv": (
        selected_source_dir / "clusters_enriched.csv"
    ),
    "cluster_metrics.csv": (
        selected_source_dir / "cluster_metrics.csv"
    ),
    "clustering_stdout.txt": (
        selected_source_dir / "stdout_stderr.txt"
    ),
}

for output_name, source_path in selected_files.items():
    shutil.copy2(source_path, SELECTED_DIR / output_name)
    shutil.copy2(source_path, ROOT_OUTPUT_DIR / output_name)

write_text(SELECTED_DIR / "clusters_method.txt", ROOT_MODE + "\n")
write_text(ROOT_OUTPUT_DIR / "clusters_method.txt", ROOT_MODE + "\n")

selected_row = (
    method_comparison[
        method_comparison["requested_mode"] == ROOT_MODE
    ]
    .iloc[0]
    .to_dict()
)

selection_manifest = {
    "dataset_id": dataset_id,
    "selected_label": selected_label,
    "selected_requested_mode": ROOT_MODE,
    "selected_effective_mode": selected_row.get("effective_mode"),
    "selection_policy": (
        "explicit ROOT_MODE; no ad-hoc automatic winner"
    ),
    "hard_assignment_feasible": bool(
        selected_row.get("hard_assignment_feasible")
    ),
    "crosscheck_ok": bool(selected_row.get("crosscheck_ok")),
    "fallback_used": int(selected_row.get("fallback_used", 0)),
    "selected_metrics": {
        key: safe_scalar(value)
        for key, value in selected_row.items()
    },
}
write_json(SELECTED_DIR / "selection_manifest.json", selection_manifest)
write_json(ROOT_OUTPUT_DIR / "clustering_manifest.json", selection_manifest)


# =============================================================================
# PRESENTATION-READY FIGURES
# =============================================================================

figure_manifest = pd.DataFrame()
inline_figure_paths: list[Path] = []

if GENERATE_FIGURES:
    road_segments = build_road_segments(input_meta, dataset_nodes)

    # One beautiful geographic road-network image per validated method.
    for mode, assignment_group in assignments_all.groupby("mode"):
        mode = str(mode)
        label = METHOD_LABEL_BY_MODE.get(mode, mode)

        image_path = FIGURES_DIR / f"{label}.png"
        effective_mode = str(
            method_comparison.loc[
                method_comparison["requested_mode"] == mode,
                "effective_mode",
            ].iloc[0]
        )

        save_cluster_map(
            mode=label,
            assignment_df=assignment_group,
            meta=input_meta,
            dataset_nodes=dataset_nodes,
            road_segments=road_segments,
            output_path=image_path,
            subtitle=(
                f"{input_meta['N']:,} road nodes | "
                f"{input_meta['customer_count']} customers | "
                f"K={input_meta['K']} | {ROAD_COST} cost | "
                f"effective: {effective_mode}"
            ),
        )

        inline_figure_paths.append(image_path)

    selected_assignment_df = pd.read_csv(
        SELECTED_DIR / "clusters_enriched.csv"
    )
    selected_label = METHOD_LABEL_BY_MODE.get(ROOT_MODE, ROOT_MODE)

    selected_image = FIGURES_DIR / f"Selected_{selected_label}.png"

    save_cluster_map(
        mode=selected_label,
        assignment_df=selected_assignment_df,
        meta=input_meta,
        dataset_nodes=dataset_nodes,
        road_segments=road_segments,
        output_path=selected_image,
        subtitle="Selected solver warm-start partition",
    )

    all_methods_image = FIGURES_DIR / "AllMethods.png"

    save_method_map_grid(
        assignments_all=assignments_all,
        meta=input_meta,
        dataset_nodes=dataset_nodes,
        road_segments=road_segments,
        output_path=all_methods_image,
    )

    load_image = FIGURES_DIR / "ClusterLoads.png"

    save_cluster_load_grid(
        cluster_metrics_all=cluster_metrics_all,
        capacity=float(input_meta["capacity"]),
        output_path=load_image,
    )

    plot_df = method_comparison.copy()

    # Runtime: end-to-end clustering time from cluster.cpp.
    runtime_image = FIGURES_DIR / "Runtime.png"
    if "total_s" in plot_df.columns:
        runtime_df = plot_df.sort_values("total_s")

        fig, ax = plt.subplots(figsize=(11.5, 6.2))
        bars = ax.bar(
            runtime_df["label"],
            runtime_df["total_s"],
            color=method_bar_colors(runtime_df["label"]),
        )
        apply_axis_style(
            ax,
            title="Clustering runtime comparison",
            xlabel="Method",
            ylabel="Total time (s)",
        )
        ax.tick_params(axis="x", rotation=30)

        for bar, value in zip(bars, runtime_df["total_s"]):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{float(value):.3f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

        fig.tight_layout()
        fig.savefig(runtime_image, dpi=240, bbox_inches="tight")
        plt.close(fig)

    # This is a diagnostic warm-start proxy, not the final solver objective.
    proxy_image = FIGURES_DIR / "RouteProxyObjective.png"
    if "nn_route_proxy_total_cost" in plot_df.columns:
        proxy_df = plot_df.sort_values("nn_route_proxy_total_cost")

        fig, ax = plt.subplots(figsize=(11.5, 6.2))
        bars = ax.bar(
            proxy_df["label"],
            proxy_df["nn_route_proxy_total_cost"],
            color=method_bar_colors(proxy_df["label"]),
        )
        proxy_unit = "seconds" if ROAD_COST == "time" else "metres"
        apply_axis_style(
            ax,
            title=(
                "Warm-start route-proxy objective "
                f"({ROAD_COST}; lower is better)"
            ),
            xlabel="Method",
            ylabel=f"Nearest-neighbor proxy ({proxy_unit})",
        )
        ax.tick_params(axis="x", rotation=30)

        for bar, value in zip(
            bars,
            proxy_df["nn_route_proxy_total_cost"],
        ):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{float(value):,.1f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

        fig.tight_layout()
        fig.savefig(proxy_image, dpi=240, bbox_inches="tight")
        plt.close(fig)

    tradeoff_image = FIGURES_DIR / "RuntimeVsObjective.png"
    if {
        "total_s",
        "nn_route_proxy_total_cost",
    }.issubset(plot_df.columns):
        tradeoff_df = plot_df.dropna(
            subset=["total_s", "nn_route_proxy_total_cost"]
        ).copy()

        if not tradeoff_df.empty:
            fig, ax = plt.subplots(figsize=(10.5, 6.6))

            point_colors = [
                (
                    PRESENTATION_COLORS["teal"]
                    if bool(pareto)
                    else PRESENTATION_COLORS["blue"]
                )
                for pareto in tradeoff_df.get(
                    "pareto_runtime_proxy",
                    pd.Series(False, index=tradeoff_df.index),
                )
            ]

            ax.scatter(
                tradeoff_df["total_s"],
                tradeoff_df["nn_route_proxy_total_cost"],
                s=95,
                c=point_colors,
                edgecolors="white",
                linewidths=0.8,
                alpha=0.92,
            )

            label_offsets = [
                (7, 7),
                (7, -14),
                (-46, 7),
                (-46, -14),
                (12, 18),
                (-58, 18),
                (12, -24),
                (-58, -24),
            ]

            ordered_tradeoff = tradeoff_df.sort_values(
                ["nn_route_proxy_total_cost", "total_s", "label"]
            )

            for label_index, (_, row) in enumerate(ordered_tradeoff.iterrows()):
                offset = label_offsets[label_index % len(label_offsets)]
                ax.annotate(
                    str(row["label"]),
                    (
                        float(row["total_s"]),
                        float(row["nn_route_proxy_total_cost"]),
                    ),
                    xytext=offset,
                    textcoords="offset points",
                    fontsize=8,
                    color=PRESENTATION_COLORS["slate"],
                    bbox={
                        "boxstyle": "round,pad=0.18",
                        "facecolor": "white",
                        "edgecolor": "none",
                        "alpha": 0.72,
                    },
                )

            apply_axis_style(
                ax,
                title="Runtime–quality trade-off",
                xlabel="Total clustering time (s)",
                ylabel=(
                    "Nearest-neighbor route-proxy objective "
                    "(lower is better)"
                ),
            )
            fig.tight_layout()
            fig.savefig(
                tradeoff_image,
                dpi=240,
                bbox_inches="tight",
            )
            plt.close(fig)

    compactness_image = FIGURES_DIR / "RoadCompactness.png"
    if "weighted_mean_road_cost_to_medoid" in plot_df.columns:
        compact_df = (
            plot_df
            .dropna(subset=["weighted_mean_road_cost_to_medoid"])
            .sort_values("weighted_mean_road_cost_to_medoid")
        )

        if not compact_df.empty:
            fig, ax = plt.subplots(figsize=(11.5, 6.2))
            bars = ax.bar(
                compact_df["label"],
                compact_df["weighted_mean_road_cost_to_medoid"],
                color=method_bar_colors(compact_df["label"]),
            )
            apply_axis_style(
                ax,
                title="Within-cluster road compactness (lower is better)",
                xlabel="Method",
                ylabel="Weighted mean road cost to medoid",
            )
            ax.tick_params(axis="x", rotation=30)

            for bar, value in zip(
                bars,
                compact_df["weighted_mean_road_cost_to_medoid"],
            ):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height(),
                    f"{float(value):,.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

            fig.tight_layout()
            fig.savefig(
                compactness_image,
                dpi=240,
                bbox_inches="tight",
            )
            plt.close(fig)

    balance_image = FIGURES_DIR / "LoadBalance.png"
    if "load_std" in plot_df.columns:
        balance_df = plot_df.sort_values("load_std")

        fig, ax = plt.subplots(figsize=(11.5, 6.2))
        bars = ax.bar(
            balance_df["label"],
            balance_df["load_std"],
            color=method_bar_colors(balance_df["label"]),
        )
        apply_axis_style(
            ax,
            title="Cluster load-balance dispersion",
            xlabel="Method",
            ylabel="Standard deviation of cluster load",
        )
        ax.tick_params(axis="x", rotation=30)

        for bar, value in zip(bars, balance_df["load_std"]):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{float(value):.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

        fig.tight_layout()
        fig.savefig(balance_image, dpi=240, bbox_inches="tight")
        plt.close(fig)

    utilization_image = FIGURES_DIR / "CapacityUtilization.png"

    utilization_summary = (
        cluster_metrics_all
        .groupby("mode", as_index=False)
        .agg(
            utilization_min=("utilization", "min"),
            utilization_mean=("utilization", "mean"),
            utilization_max=("utilization", "max"),
        )
    )

    utilization_summary["label"] = utilization_summary["mode"].map(
        lambda mode: METHOD_LABEL_BY_MODE.get(str(mode), str(mode))
    )
    utilization_summary = utilization_summary.sort_values(
        "utilization_mean",
        ascending=True,
    ).reset_index(drop=True)

    fig_height = max(5.0, 0.47 * len(utilization_summary) + 2.2)
    fig, ax = plt.subplots(figsize=(10.8, fig_height))

    y_positions = np.arange(len(utilization_summary))
    range_colors = method_bar_colors(utilization_summary["label"])

    for y, (_, row), color in zip(
        y_positions,
        utilization_summary.iterrows(),
        range_colors,
    ):
        ax.hlines(
            y,
            float(row["utilization_min"]),
            float(row["utilization_max"]),
            color=color,
            linewidth=3.0,
            alpha=0.42,
        )
        ax.scatter(
            [float(row["utilization_mean"])],
            [y],
            s=58,
            facecolor=color,
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )

    ax.axvline(
        1.0,
        color=PRESENTATION_COLORS["navy"],
        linestyle="--",
        linewidth=1.4,
        alpha=0.85,
        label="Capacity limit",
    )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(utilization_summary["label"])
    ax.set_xlabel("Capacity utilization")
    ax.set_ylabel("Method")
    fig.suptitle(
        "Capacity-utilization range by method",
        x=0.14,
        y=0.985,
        ha="left",
        fontsize=15.5,
        fontweight="semibold",
        color=PRESENTATION_COLORS["navy"],
    )
    fig.text(
        0.14,
        0.925,
        "Line = min–max across clusters; marker = mean utilization",
        ha="left",
        fontsize=9.2,
        color=PRESENTATION_COLORS["slate"],
    )
    ax.grid(True, axis="x", linestyle=(0, (2, 4)), linewidth=0.55)
    ax.grid(False, axis="y")
    ax.legend(loc="lower right", fontsize=8.5)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.subplots_adjust(
        left=0.19,
        right=0.96,
        bottom=0.10,
        top=0.86,
    )
    fig.savefig(
        utilization_image,
        dpi=240,
        bbox_inches="tight",
        facecolor=PRESENTATION_COLORS["paper"],
    )
    plt.close(fig)

    # Compact benchmark scorecard with report-friendly labels.
    scorecard_source_columns = [
        column
        for column in [
            "label",
            "effective_mode",
            "hard_assignment_feasible",
            "fallback_used",
            "total_s",
            "nn_route_proxy_total_cost",
            "weighted_mean_road_cost_to_medoid",
            "load_std",
            "total_overload",
        ]
        if column in plot_df.columns
    ]

    scorecard_df = plot_df[scorecard_source_columns].copy()

    scorecard_rename = {
        "label": "Method",
        "effective_mode": "Effective mode",
        "hard_assignment_feasible": "Feasible",
        "fallback_used": "Fallback",
        "total_s": "Time (s)",
        "nn_route_proxy_total_cost": "Route proxy",
        "weighted_mean_road_cost_to_medoid": "Road compactness",
        "load_std": "Load SD",
        "total_overload": "Overload",
    }
    scorecard_df = scorecard_df.rename(columns=scorecard_rename)

    for numeric_column in [
        "Time (s)",
        "Route proxy",
        "Road compactness",
        "Load SD",
        "Overload",
    ]:
        if numeric_column in scorecard_df.columns:
            numeric_values = pd.to_numeric(
                scorecard_df[numeric_column],
                errors="coerce",
            )

            if numeric_column == "Time (s)":
                scorecard_df[numeric_column] = numeric_values.map(
                    lambda value: (
                        ""
                        if pd.isna(value)
                        else (
                            f"{value:.6f}"
                            if abs(value) < 0.01
                            else f"{value:.3f}"
                        )
                    )
                )
            else:
                scorecard_df[numeric_column] = numeric_values.map(
                    lambda value: (
                        ""
                        if pd.isna(value)
                        else f"{value:,.3f}"
                    )
                )

    scorecard_df["Feasible"] = scorecard_df["Feasible"].map(
        lambda value: "YES" if bool(value) else "NO"
    )
    scorecard_df["Fallback"] = scorecard_df["Fallback"].map(
        lambda value: "YES" if int(value) else "NO"
    )

    scorecard_image = FIGURES_DIR / "MethodScorecard.png"

    fig_height = max(4.8, 0.48 * len(scorecard_df) + 2.3)
    fig, ax = plt.subplots(figsize=(17.5, fig_height))
    ax.axis("off")

    column_count = max(1, len(scorecard_df.columns))
    default_width = 1.0 / column_count
    column_widths = [default_width] * column_count

    # Give text-heavy columns slightly more room.
    for column_index, column_name in enumerate(scorecard_df.columns):
        if column_name == "Method":
            column_widths[column_index] = 0.12
        elif column_name == "Effective mode":
            column_widths[column_index] = 0.17
        elif column_name in {"Feasible", "Fallback"}:
            column_widths[column_index] = 0.08
        elif column_name in {"Route proxy", "Road compactness"}:
            column_widths[column_index] = 0.13
        else:
            column_widths[column_index] = 0.095

    width_total = sum(column_widths)
    column_widths = [width / width_total for width in column_widths]

    table = ax.table(
        cellText=scorecard_df.astype(str).values,
        colLabels=scorecard_df.columns,
        colWidths=column_widths,
        bbox=[0.015, 0.02, 0.97, 0.86],
        cellLoc="center",
        colLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.6)
    table.scale(1.0, 1.48)

    for (row_index, column_index), cell in table.get_celld().items():
        cell.set_edgecolor("#CBD5E1")
        cell.set_linewidth(0.55)

        if row_index == 0:
            cell.set_facecolor(PRESENTATION_COLORS["navy"])
            cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold")
        else:
            cell.set_facecolor(
                "#F8FAFC" if row_index % 2 else "#EAF0F7"
            )
            cell.get_text().set_color(PRESENTATION_COLORS["navy"])

            header_name = scorecard_df.columns[column_index]
            cell_value = str(scorecard_df.iloc[row_index - 1, column_index])

            if header_name == "Feasible":
                cell.get_text().set_color(
                    PRESENTATION_COLORS["success"]
                    if cell_value == "YES"
                    else PRESENTATION_COLORS["danger"]
                )
                cell.get_text().set_fontweight("bold")

            if header_name == "Fallback" and cell_value == "YES":
                cell.get_text().set_color(PRESENTATION_COLORS["amber"])
                cell.get_text().set_fontweight("bold")

    ax.set_title(
        "Clustering benchmark scorecard",
        color=PRESENTATION_COLORS["navy"],
        fontsize=16,
        fontweight="bold",
        pad=18,
    )
    ax.text(
        0.5,
        0.905,
        (
            "Route proxy and road compactness are independent warm-start "
            "diagnostics; lower values are better."
        ),
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=9.5,
        color=PRESENTATION_COLORS["slate"],
    )

    fig.savefig(scorecard_image, dpi=240, bbox_inches="tight")
    plt.close(fig)

    key_figures = [
        selected_image,
        all_methods_image,
        runtime_image,
        proxy_image,
        tradeoff_image,
        compactness_image,
        balance_image,
        utilization_image,
        load_image,
        scorecard_image,
    ]

    for source in key_figures:
        if source.exists():
            shutil.copy2(source, REPORT_READY_DIR / source.name)

    for source in [
        COMPARISON_DIR / "MethodComparison.csv",
        COMPARISON_DIR / "TimingComparison.csv",
        COMPARISON_DIR / "FeasibilityComparison.csv",
        COMPARISON_DIR / "ObjectiveComparison.csv",
        COMPARISON_DIR / "ClusterMetricsAll.csv",
        COMPARISON_DIR / "AssignmentsAll.csv",
    ]:
        if source.exists():
            shutil.copy2(source, REPORT_READY_DIR / source.name)

    figure_manifest = write_figure_manifest(
        FIGURES_DIR,
        REPORT_READY_DIR,
    )

    # Direct Colab visual output.
    if DISPLAY_FIGURES_INLINE and Image is not None:
        print("\n" + "=" * 100)
        print("PRESENTATION VISUALS")
        print("=" * 100)

        inline_order = [
            all_methods_image,
            scorecard_image,
            runtime_image,
            proxy_image,
            tradeoff_image,
            compactness_image,
            balance_image,
            utilization_image,
            load_image,
            *inline_figure_paths,
        ]

        shown = set()

        for image_path in inline_order:
            if image_path in shown or not image_path.exists():
                continue

            shown.add(image_path)

            if Markdown is not None:
                display(Markdown(f"### {image_path.stem}"))

            display(Image(filename=str(image_path), width=1050))



# =============================================================================
# HUMAN-READABLE BENCHMARK SUMMARY LOG
# =============================================================================

summary_columns = [
    column
    for column in [
        "label",
        "requested_mode",
        "effective_mode",
        "category",
        "hard_assignment_feasible",
        "fallback_used",
        "total_s",
        "runtime_rank",
        "nn_route_proxy_total_cost",
        "proxy_objective_rank",
        "weighted_mean_road_cost_to_medoid",
        "road_compactness_rank",
        "load_std",
        "load_balance_rank",
        "total_overload",
        "pareto_runtime_proxy",
    ]
    if column in method_comparison.columns
]

summary_lines = [
    "FULL CLUSTERING BENCHMARK SUMMARY",
    "=" * 80,
    f"Created UTC: {utc_now()}",
    f"Dataset: {dataset_id}",
    (
        f"N={input_meta['N']}, M={input_meta['M']}, "
        f"customers={input_meta['customer_count']}, K={input_meta['K']}"
    ),
    f"Road cost: {ROAD_COST}",
    f"Selected root mode: {ROOT_MODE}",
    f"Independent road-evidence build: {road_evidence_s:.6f} s",
    "",
    "IMPORTANT:",
    (
        "nn_route_proxy_total_cost is an independent warm-start diagnostic, "
        "not the final solver objective."
    ),
    "",
    method_comparison[summary_columns].to_string(index=False),
    "",
]

write_text(
    LOGS_DIR / "BenchmarkSummary.txt",
    "\n".join(summary_lines),
)


# =============================================================================
# FINAL MANIFEST AND ZIP
# =============================================================================

final_manifest = {
    "created_utc": utc_now(),
    "dataset_id": dataset_id,
    "output_root": str(OUTPUT_ROOT),
    "selected_mode": ROOT_MODE,
    "selected_effective_mode": selected_row.get("effective_mode"),
    "method_count_attempted": len(METHODS),
    "method_count_validated": len(method_comparison),
    "independent_road_evidence_seconds": road_evidence_s,
    "root_outputs": [
        "/content/clusters.csv",
        "/content/cluster_summary.csv",
        "/content/cluster_timing.csv",
        "/content/clusters_enriched.csv",
        "/content/cluster_metrics.csv",
        "/content/clusters_method.txt",
        "/content/clustering_manifest.json",
    ],
    "comparison_outputs": [
        str(COMPARISON_DIR / "MethodComparison.csv"),
        str(COMPARISON_DIR / "TimingComparison.csv"),
        str(COMPARISON_DIR / "FeasibilityComparison.csv"),
        str(COMPARISON_DIR / "ObjectiveComparison.csv"),
        str(COMPARISON_DIR / "ClusterMetricsAll.csv"),
        str(COMPARISON_DIR / "AssignmentsAll.csv"),
        str(COMPARISON_DIR / "MethodRunManifest.csv"),
    ],
    "figure_outputs": (
        figure_manifest["path"].tolist()
        if not figure_manifest.empty
        else []
    ),
    "report_ready_directory": str(REPORT_READY_DIR),
    "benchmark_summary_log": str(LOGS_DIR / "BenchmarkSummary.txt"),
}
write_json(OUTPUT_ROOT / "BenchmarkManifest.json", final_manifest)

zip_path = OUTPUT_ROOT.parent / f"ClusteringBenchmark_{dataset_id}"

if CREATE_ZIP:
    archive_path = shutil.make_archive(
        str(zip_path),
        "zip",
        root_dir=str(OUTPUT_ROOT.parent),
        base_dir=OUTPUT_ROOT.name,
    )
else:
    archive_path = ""


# =============================================================================
# FINAL COLAB OUTPUT
# =============================================================================

print("\n" + "=" * 100)
print("FULL CLUSTERING BENCHMARK COMPLETE")
print("=" * 100)
print(f"Dataset: {dataset_id}")
print(
    f"N={input_meta['N']:,}, M={input_meta['M']:,}, "
    f"customers={input_meta['customer_count']}, K={input_meta['K']}"
)
print(f"Road cost: {ROAD_COST}")
print(f"Selected solver warm start: {ROOT_MODE}")
print(f"Benchmark folder: {OUTPUT_ROOT}")
print(f"CSV folder: {COMPARISON_DIR}")
print(f"PNG folder: {FIGURES_DIR}")
print(f"Logs folder: {LOGS_DIR}")
print(f"Presentation folder: {REPORT_READY_DIR}")
print(f"Independent road-evidence build: {road_evidence_s:.6f} s")

if archive_path:
    print(f"Benchmark ZIP: {archive_path}")

print("\nROOT SOLVER FILES")
print("  /content/clusters.csv")
print("  /content/cluster_summary.csv")
print("  /content/cluster_timing.csv")
print("  /content/clusters_enriched.csv")
print("  /content/cluster_metrics.csv")
print("  /content/clusters_method.txt")
print("  /content/clustering_manifest.json")

display_columns = [
    column
    for column in [
        "label",
        "requested_mode",
        "effective_mode",
        "category",
        "hard_assignment_feasible",
        "fallback_used",
        "used_clusters",
        "empty_clusters",
        "total_overload",
        "total_s",
        "nn_route_proxy_total_cost",
        "weighted_mean_road_cost_to_medoid",
        "load_std",
    ]
    if column in method_comparison.columns
]

if DISPLAY_TABLES_INLINE:
    print("\nMETHOD BENCHMARK SUMMARY")
    display(
        method_comparison[display_columns]
        .sort_values(
            ["hard_assignment_feasible", "total_s"],
            ascending=[False, True],
        )
        .reset_index(drop=True)
    )

    print("\nRUNTIME RANKING")
    if "total_s" in method_comparison.columns:
        display(
            method_comparison[
                ["label", "effective_mode", "total_s", "runner_wall_s"]
            ]
            .sort_values("total_s")
            .reset_index(drop=True)
        )

    print("\nWARM-START PROXY OBJECTIVE RANKING")
    print(
        "Important: this is an independent clustering diagnostic, "
        "not the final solver objective."
    )
    if "nn_route_proxy_total_cost" in method_comparison.columns:
        display(
            method_comparison[
                [
                    "label",
                    "effective_mode",
                    "nn_route_proxy_total_cost",
                    "weighted_mean_road_cost_to_medoid",
                    "load_std",
                    "total_overload",
                ]
            ]
            .sort_values("nn_route_proxy_total_cost")
            .reset_index(drop=True)
        )

    print("\nSELECTED CLUSTER METRICS")
    display(pd.read_csv("/content/cluster_metrics.csv"))

print("\nSAVE THIS FILE FOR THE BENCHMARK")
if archive_path:
    print(f"  {archive_path}")

print(
    "The ZIP contains all methods, explicit CSVs, explicit PNGs, logs, "
    "source/input snapshots, timings, independent road metrics, the selected "
    "solver warm start, and presentation-ready figures."
)

print("\nRunner completed successfully. [EOF]")
# END OF CLUSTERING BENCHMARK RUNNER
