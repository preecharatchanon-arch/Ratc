from __future__ import annotations

import csv
import hashlib
import json
import threading
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection

from .config import RUNTIME_DIR, settings
from .graph_store import osm_bool

COLORS = {
    "navy": "#0B1F3A",
    "ink": "#172033",
    "teal": "#0F766E",
    "blue": "#2563EB",
    "cyan": "#0E7490",
    "amber": "#B7791F",
    "green": "#15803D",
    "slate": "#64748B",
    "light": "#F4F7FA",
    "grid": "#E2E8F0",
    "border": "#CBD5E1",
    "danger": "#B91C1C",
}
PALETTE = [
    "#0F766E", "#2563EB", "#475569", "#0E7490", "#4F46E5",
    "#B7791F", "#15803D", "#64748B", "#BE123C", "#7C3AED",
]

_FILE_HASH_LOCK = threading.Lock()
_FILE_HASH_CACHE: dict[tuple[str, int, int], str] = {}

_EVIDENCE_ZIP_LOCK = threading.Lock()


def _file_receipt(path: Path | None) -> dict[str, Any] | None:
    """Return a content identity without repeatedly hashing unchanged files."""
    if path is None or not path.is_file():
        return None
    stat = path.stat()
    key = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    with _FILE_HASH_LOCK:
        digest = _FILE_HASH_CACHE.get(key)
    if digest is None:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        with _FILE_HASH_LOCK:
            if len(_FILE_HASH_CACHE) > 96:
                _FILE_HASH_CACHE.clear()
            _FILE_HASH_CACHE[key] = digest
    return {
        "path": str(path),
        "bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": digest,
    }


def _artifact_url(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    try:
        rel = path.resolve().relative_to(RUNTIME_DIR.resolve())
    except ValueError:
        return None
    stat = path.stat()
    revision = f"{int(stat.st_mtime_ns):x}-{int(stat.st_size):x}"
    return "/api/artifacts/" + "/".join(rel.parts) + f"?v={revision}"


def _save_figure(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _axis(ax, title: str, subtitle: str = "") -> None:
    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color=COLORS["navy"], pad=24)
    if subtitle:
        ax.text(0, 1.035, subtitle, transform=ax.transAxes, fontsize=8.5, color=COLORS["slate"], va="bottom")
    ax.grid(True, linestyle=(0, (2, 4)), linewidth=.65, color=COLORS["grid"])
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(COLORS["border"])
    ax.tick_params(colors=COLORS["slate"], labelsize=8.5)


def generate_network_overview(graph, places: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    segments = []
    road_classes = Counter()
    one_way = 0
    named = 0
    speeds = []
    for u, v, _k, data in graph.edges(keys=True, data=True):
        geom = data.get("geometry")
        if geom is not None and hasattr(geom, "coords"):
            coords = [(float(x), float(y)) for x, y in geom.coords]
        else:
            coords = [
                (float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])),
                (float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])),
            ]
        if len(coords) >= 2:
            segments.append(coords)
        highway = data.get("highway", "unclassified")
        if isinstance(highway, list):
            highway = highway[0] if highway else "unclassified"
        road_classes[str(highway)] += 1
        if osm_bool(data.get("oneway")):
            one_way += 1
        if data.get("name"):
            named += 1
        speed = data.get("speed_kph")
        if isinstance(speed, list):
            speed = speed[0] if speed else None
        try:
            speeds.append(float(speed))
        except (TypeError, ValueError):
            pass

    fig, ax = plt.subplots(figsize=(12.4, 8.2))
    if segments:
        ax.add_collection(LineCollection(segments, colors="#9AA7B6", linewidths=.45, alpha=.62))
    for role, color, marker, size in [
        ("depot", COLORS["navy"], "s", 90),
        ("customer", COLORS["teal"], "o", 42),
    ]:
        selected = [p for p in places if p.get("role") == role]
        if selected:
            ax.scatter(
                [float(p["lon"]) for p in selected],
                [float(p["lat"]) for p in selected],
                s=size, c=color, marker=marker, edgecolors="white", linewidths=1.2,
                zorder=5, label="Depot" if role == "depot" else "Customer",
            )
            access = [p for p in selected if p.get("access_lat") is not None]
            for p in access:
                ax.plot(
                    [float(p["lon"]), float(p["access_lon"])],
                    [float(p["lat"]), float(p["access_lat"])],
                    color=COLORS["amber"], linewidth=.8, linestyle="--", alpha=.7,
                )
    ax.autoscale()
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xticks([]); ax.set_yticks([])
    _axis(
        ax,
        "OSM road-network readiness",
        f"{graph.number_of_nodes():,} nodes · {graph.number_of_edges():,} directed edges · road access validated",
    )
    if places:
        ax.legend(loc="lower left", frameon=True, fontsize=8)
    _save_figure(fig, path)
    return {
        "artifact": _artifact_url(path),
        "road_classes": dict(road_classes.most_common(12)),
        "one_way_edges": one_way,
        "named_edges": named,
        "median_speed_kph": float(np.median(speeds)) if speeds else None,
    }


def _read_dataset() -> dict[str, Any] | None:
    if not settings.dataset_json.exists():
        return None
    return json.loads(settings.dataset_json.read_text(encoding="utf-8"))


def parse_cluster_assignments(path: Path | None = None) -> list[dict[str, int]]:
    path = path or settings.clusters_csv
    if not path.exists():
        return []
    rows: list[dict[str, int]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row:
                continue
            try:
                rows.append({"node": int(row["node"]), "cluster": int(row["cluster"])})
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def validate_clusters(
    assignments: list[dict[str, int]],
    dataset: dict[str, Any],
    expected_clusters: int | None = None,
) -> dict[str, Any]:
    """Validate the assignment contract without overstating route feasibility.

    A cluster partition can prove coverage, IDs, and demand capacity.  Directed
    road reachability, visit ordering, time windows, and trip limits are checked
    later by the native solver's hard-feasibility gate.
    """
    customers = {int(c["node"]): c for c in dataset.get("customers", [])}
    maximum_trucks = max(0, int(dataset.get("K_trucks", 0)))
    target_clusters = maximum_trucks
    if expected_clusters is not None:
        target_clusters = max(0, min(maximum_trucks, int(expected_clusters)))
    capacity = float(dataset.get("truck_capacity", 0))
    by_node: dict[int, int] = {}
    duplicate_nodes = []
    for row in assignments:
        node = int(row["node"])
        if node in by_node:
            duplicate_nodes.append(node)
        by_node[node] = int(row["cluster"])
    missing = sorted(set(customers) - set(by_node))
    unexpected = sorted(set(by_node) - set(customers))
    invalid_cluster = sorted({c for c in by_node.values() if c < 0 or c >= target_clusters})
    loads = defaultdict(float)
    counts = defaultdict(int)
    for node, cluster in by_node.items():
        if node in customers:
            loads[cluster] += float(customers[node].get("demand", 0))
            counts[cluster] += 1
    overloads = {
        str(k): max(0.0, v - capacity)
        for k, v in loads.items()
        if v > capacity + 1e-8
    }
    used_ids = sorted({
        cluster for node, cluster in by_node.items()
        if node in customers and 0 <= cluster < target_clusters
    })
    valid = not (
        duplicate_nodes or missing or unexpected or invalid_cluster or overloads
        or target_clusters <= 0 or capacity <= 0
    )
    cluster_loads = {str(i): loads.get(i, 0.0) for i in range(target_clusters)}
    cluster_counts = {str(i): counts.get(i, 0) for i in range(target_clusters)}
    utilization = {
        str(i): (cluster_loads[str(i)] / capacity * 100.0 if capacity > 0 else None)
        for i in range(target_clusters)
    }
    used_utilization = [
        float(utilization[str(i)]) for i in used_ids
        if utilization.get(str(i)) is not None
    ]
    return {
        "valid": valid,
        "assignment_feasible": valid,
        "validation_scope": "coverage_capacity_assignment",
        "route_hard_feasible": None,
        "customer_count": len(customers),
        "assignment_count": len(assignments),
        "missing_nodes": missing[:30],
        "unexpected_nodes": unexpected[:30],
        "duplicate_nodes": sorted(set(duplicate_nodes))[:30],
        "invalid_cluster_ids": invalid_cluster,
        "overloads": overloads,
        "used_clusters": len(used_ids),
        "used_cluster_ids": used_ids,
        "empty_clusters": max(0, target_clusters - len(used_ids)),
        "target_clusters": target_clusters,
        "maximum_available_trucks": maximum_trucks,
        "cluster_loads": cluster_loads,
        "cluster_counts": cluster_counts,
        "cluster_utilization_pct": utilization,
        "max_utilization_pct": max(used_utilization) if used_utilization else 0.0,
        "mean_utilization_pct": float(np.mean(used_utilization)) if used_utilization else 0.0,
        "minimum_capacity_headroom": (
            min((capacity - cluster_loads[str(i)] for i in used_ids), default=capacity)
            if capacity > 0 else None
        ),
        "capacity": capacity,
    }


def generate_cluster_preview(
    assignments: list[dict[str, int]],
    validation: dict[str, Any],
    path: Path,
    method: str,
) -> dict[str, Any]:
    dataset = _read_dataset()
    if not dataset:
        return {"artifact": None}
    nodes = {int(n["id"]): n for n in dataset.get("nodes", [])}
    assignment = {int(r["node"]): int(r["cluster"]) for r in assignments}
    segments = []
    for edge in dataset.get("edges", []):
        geom = edge.get("geometry") or []
        if geom:
            segments.append([(float(p[1]), float(p[0])) for p in geom])
    fig = plt.figure(figsize=(15.8, 8.4))
    grid = fig.add_gridspec(
        2, 2,
        width_ratios=[1.7, 1.0],
        height_ratios=[1.12, .88],
        wspace=.22,
        hspace=.42,
    )
    ax = fig.add_subplot(grid[:, 0])
    load_ax = fig.add_subplot(grid[0, 1])
    pressure_ax = fig.add_subplot(grid[1, 1])
    if segments:
        ax.add_collection(LineCollection(segments, colors="#B7C2CC", linewidths=.34, alpha=.42))
    cluster_ids = sorted(set(assignment.values()))
    for cluster in cluster_ids:
        selected = [node for node, cid in assignment.items() if cid == cluster and node in nodes]
        if not selected:
            continue
        color = PALETTE[cluster % len(PALETTE)]
        ax.scatter(
            [nodes[n]["lon"] for n in selected], [nodes[n]["lat"] for n in selected],
            s=48, color=color, edgecolors="white", linewidths=1,
            label=f"C{cluster + 1}", zorder=4,
        )
        cx = float(np.mean([float(nodes[n]["lon"]) for n in selected]))
        cy = float(np.mean([float(nodes[n]["lat"]) for n in selected]))
        ax.annotate(
            str(cluster + 1), (cx, cy), ha="center", va="center", zorder=7,
            fontsize=7.5, fontweight="bold", color="white",
            bbox={"boxstyle": "round,pad=.28", "fc": color, "ec": "white", "lw": 1.0},
        )
    depot = nodes.get(int(dataset.get("depot", -1)))
    if depot:
        ax.scatter([depot["lon"]], [depot["lat"]], s=145, marker="s", color=COLORS["navy"], edgecolors="white", linewidths=1.5, zorder=6)
    ax.autoscale(); ax.set_aspect("equal", adjustable="datalim"); ax.set_xticks([]); ax.set_yticks([])
    assignment_state = "assignment checks passed" if validation.get("valid") else "assignment checks failed"
    _axis(
        ax,
        "Cluster geography",
        f"{method} · {assignment_state} · native route gate is reported separately",
    )
    if len(cluster_ids) <= 10:
        ax.legend(loc="lower left", ncol=2, fontsize=7.5)
    loads = validation.get("cluster_loads", {})
    counts = validation.get("cluster_counts", {})
    keys = sorted({
        int(k) for k, value in loads.items()
        if float(value or 0) > 0 or int(counts.get(str(k), 0) or 0) > 0
    })
    if not keys:
        keys = sorted(int(k) for k in loads)
    values = [float(loads[str(k)]) for k in keys]
    cap = float(validation.get("capacity", 0))
    ratios = [(value / cap * 100.0 if cap > 0 else 0.0) for value in values]
    bar_colors = [
        COLORS["danger"] if ratio > 100.0 + 1e-8
        else COLORS["amber"] if ratio >= 85.0
        else COLORS["teal"]
        for ratio in ratios
    ]
    bars = load_ax.barh([f"C{k+1}" for k in keys], values, color=bar_colors, alpha=.9)
    if cap:
        load_ax.axvline(cap, color=COLORS["danger"], linestyle="--", linewidth=1.2, label="Capacity")
    load_ax.invert_yaxis(); load_ax.set_xlabel("Assigned demand")
    _axis(
        load_ax,
        "Capacity pressure",
        f"{validation.get('used_clusters', 0)} used / {validation.get('target_clusters', 0)} target · {validation.get('maximum_available_trucks', 0)} max available",
    )
    if cap:
        load_ax.legend(loc="lower right", fontsize=8)
    for bar, value, ratio in zip(bars, values, ratios):
        load_ax.text(
            value, bar.get_y() + bar.get_height() / 2,
            f" {value:.1f} · {ratio:.0f}%", va="center", fontsize=7.7,
            color=COLORS["slate"],
        )

    stop_counts = [int(counts.get(str(k), 0) or 0) for k in keys]
    pressure_ax.scatter(
        stop_counts, ratios,
        s=[42 + min(110, count * 3) for count in stop_counts],
        c=bar_colors, alpha=.88, edgecolors="white", linewidths=1.0, zorder=4,
    )
    for key, count, ratio in zip(keys, stop_counts, ratios):
        pressure_ax.annotate(
            f"C{key + 1}", (count, ratio), xytext=(4, 4),
            textcoords="offset points", fontsize=7, color=COLORS["slate"],
        )
    pressure_ax.axhline(100, color=COLORS["danger"], linestyle="--", linewidth=1.0)
    pressure_ax.axhline(85, color=COLORS["amber"], linestyle=":", linewidth=1.0)
    pressure_ax.set_xlabel("Assigned stops")
    pressure_ax.set_ylabel("Capacity utilization (%)")
    _axis(
        pressure_ax,
        "Cluster pressure map",
        "Stop count versus load; amber marks clusters nearing capacity",
    )
    fig.suptitle(
        "Clustering safety preview",
        x=.055, y=.995, ha="left", fontsize=18, fontweight="bold", color=COLORS["navy"],
    )
    fig.text(
        .055, .950,
        "Assignment validation covers membership and capacity. The native solver separately certifies roads, visit order, time windows, and trip limits.",
        ha="left", va="top", fontsize=8.6, color=COLORS["slate"],
    )
    fig.subplots_adjust(top=.80, left=.055, right=.975, bottom=.075)
    _save_figure(fig, path)
    return {
        "artifact": _artifact_url(path),
        "panels": ["geography", "capacity_pressure", "stops_vs_utilization"],
    }


def _safe_numeric(frame: pd.DataFrame, names: list[str]) -> str | None:
    lowered = {str(c).strip().lower(): str(c) for c in frame.columns}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def convergence_summary(include_points: bool = True) -> dict[str, Any]:
    """Return a process-level convergence view from multi-worker solver telemetry.

    ``best_obj`` in historical files is worker-local. Treating interleaved worker
    rows as one global line creates upward jumps and false diagonals. New solver
    files contain ``global_best_obj`` explicitly; older files are repaired by a
    chronological cumulative minimum.
    """
    path = settings.convergence_csv
    if not path.exists():
        return {"available": False, "message": "No convergence.csv has been produced yet.", "figures": [], "checks": []}
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return {"available": False, "message": f"Could not read convergence.csv: {exc}", "figures": [], "checks": []}
    if frame.empty:
        return {"available": False, "message": "convergence.csv is empty.", "figures": [], "checks": []}

    raw_receipt = _file_receipt(path) or {}
    invocation = _load_json(settings.solver_invocation_json) or {}
    invocation_convergence = (invocation.get("final") or {}).get("convergence_evidence") or {}
    invocation_verified = bool(
        raw_receipt.get("sha256")
        and invocation_convergence.get("sha256") == raw_receipt.get("sha256")
    )
    source_receipt: dict[str, Any] = {
        **raw_receipt,
        "short_sha256": str(raw_receipt.get("sha256") or "")[:12] or None,
        "invocation_verified": invocation_verified,
    }
    if invocation_verified:
        policy = invocation.get("dynamic_policy") or {}
        customer_contract = invocation.get("customer_count_contract") or {}
        materialization = invocation.get("materialization_contract") or {}
        source_receipt.update({
            "solver_job_id": invocation.get("job_id"),
            "customer_count": customer_contract.get("policy_customer_orders"),
            "instances": policy.get("effective_instances"),
            "hard_time_limit_s": policy.get("runtime_s"),
            "no_improve_stop_s": policy.get("no_improve_stop_s"),
            "solver_completed_at": invocation.get("completed_at"),
            "source_signature": materialization.get("source_signature"),
            "materialization_id": materialization.get("materialization_id"),
            "input_sha256": materialization.get("input_sha256"),
            "dataset_sha256": materialization.get("dataset_sha256"),
        })

    time_col = _safe_numeric(frame, ["time_s", "elapsed_s", "time", "wall_s"])
    worker_best_col = _safe_numeric(frame, ["best_obj", "best_objective", "worker_best", "best"])
    global_col = _safe_numeric(frame, ["global_best_obj", "global_best", "process_best"])
    current_col = _safe_numeric(frame, ["current_obj", "current_objective", "current"])
    worker_col = _safe_numeric(frame, ["stream_id", "seed", "worker", "worker_id", "stream"])
    event_col = _safe_numeric(frame, ["event", "type"])
    temp_col = _safe_numeric(frame, ["temperature", "temp", "sa_temperature"])
    acceptance_col = _safe_numeric(frame, ["acceptance_rate", "accept_rate", "acceptance"])
    stagnation_col = _safe_numeric(frame, ["stagnation", "stagnation_counter"])

    for col in [time_col, worker_best_col, global_col, current_col, temp_col, acceptance_col, stagnation_col]:
        if col:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")

    # Preserve a diagnostic check on file ordering before sorting for presentation.
    timeline_regressions = 0
    if time_col:
        raw_time = frame[time_col].dropna().to_numpy(float)
        if len(raw_time) > 1:
            timeline_regressions = int(np.sum(np.diff(raw_time) < -1e-9))
        frame = frame.sort_values(time_col, kind="stable").reset_index(drop=True)

    if global_col:
        process_best = pd.to_numeric(frame[global_col], errors="coerce")
    elif worker_best_col:
        process_best = pd.to_numeric(frame[worker_best_col], errors="coerce").cummin()
    else:
        process_best = pd.Series(np.nan, index=frame.index, dtype=float)
    # Defensive cumulative minimum also repairs a malformed explicit global column
    # without hiding the integrity warning below.
    explicit_values = process_best.copy()
    process_best = process_best.ffill().cummin()
    frame["__process_global_best"] = process_best

    checks: list[dict[str, Any]] = []
    checks.append({
        "key": "columns", "status": "pass" if time_col and worker_best_col else "fail",
        "title": "Required convergence fields",
        "detail": f"time={time_col or 'missing'}, worker-best={worker_best_col or 'missing'}, global={global_col or 'derived cummin'}",
    })
    finite_global = frame["__process_global_best"].dropna()
    checks.append({
        "key": "finite", "status": "pass" if len(finite_global) else "fail",
        "title": "Finite global best observations", "detail": f"{len(finite_global):,} usable rows",
    })
    explicit_violations = 0
    finite_explicit = explicit_values.dropna()
    if len(finite_explicit) > 1:
        vals = finite_explicit.to_numpy(float)
        explicit_violations = int(np.sum(np.diff(vals) > np.maximum(1e-9, np.abs(vals[:-1]) * 1e-10)))
    checks.append({
        "key": "monotonic", "status": "pass" if explicit_violations == 0 else "warn",
        "title": "Process best-so-far monotonicity",
        "detail": "Monotone global trace" if explicit_violations == 0 else f"{explicit_violations} upward global-best steps repaired for display",
    })
    checks.append({
        "key": "timeline", "status": "pass" if timeline_regressions == 0 else "warn",
        "title": "Process timeline ordering",
        "detail": "Rows are process-chronological" if timeline_regressions == 0 else f"{timeline_regressions} timestamp resets/out-of-order rows detected; sorted for analysis",
    })
    missing_ratio = float(frame.isna().mean().mean())
    checks.append({
        "key": "missing", "status": "pass" if missing_ratio < .1 else "warn",
        "title": "Log completeness", "detail": f"{missing_ratio*100:.1f}% missing cells across recorded columns",
    })

    points: list[dict[str, Any]] = []
    improvement_count = 0
    sample = pd.DataFrame()
    if time_col and len(finite_global):
        sample = frame.loc[frame[time_col].notna() & frame["__process_global_best"].notna(), [time_col, "__process_global_best"]].copy()
        if len(sample):
            vals = sample["__process_global_best"].to_numpy(float)
            improvement_count = int(np.sum(np.diff(vals) < -np.maximum(1e-9, np.abs(vals[:-1]) * 1e-10))) if len(vals)>1 else 0
    if include_points and len(sample):
        # Preserve every true improvement point, plus evenly spaced context. This
        # keeps the step curve exact while bounding browser payload size.
        if len(sample) > 2500:
            vals = sample["__process_global_best"].to_numpy(float)
            improvement_idx = np.r_[0, np.where(np.diff(vals) < -1e-12)[0] + 1, len(sample)-1]
            context_idx = np.linspace(0, len(sample)-1, min(1800, len(sample))).astype(int)
            keep = np.unique(np.r_[improvement_idx, context_idx])
            if len(keep) > 2500:
                keep = keep[np.linspace(0, len(keep)-1, 2500).astype(int)]
            sample = sample.iloc[keep]
        points = [{"time_s": float(row[time_col]), "best": float(row["__process_global_best"])} for _, row in sample.iterrows()]

    workers: list[dict[str, Any]] = []
    if worker_col and worker_best_col:
        for worker, group in frame.groupby(worker_col, dropna=False):
            group = group.sort_values(time_col, kind="stable") if time_col else group
            group_best = pd.to_numeric(group[worker_best_col], errors="coerce").dropna()
            if group_best.empty:
                continue
            workers.append({
                "worker": str(worker), "first": float(group_best.iloc[0]), "best": float(group_best.min()),
                "improvement_pct": float((group_best.iloc[0]-group_best.min())/max(abs(group_best.iloc[0]),1e-9)*100),
            })
        workers = sorted(workers, key=lambda x: x["best"])

    events = []
    if event_col:
        events = [{"event": str(k), "count": int(v)} for k, v in frame[event_col].fillna("unknown").astype(str).value_counts().items()]

    figures = []
    report_png = settings.convergence_report_dir / "PNG"
    report_manifest = _load_json(settings.convergence_report_dir / "JSON" / "SourceManifest.json") or {}
    report_source = report_manifest.get("convergence") or {}
    report_source_sha = report_source.get("sha256") if isinstance(report_source, dict) else None
    report_current = bool(report_source_sha and report_source_sha == raw_receipt.get("sha256"))
    figure_descriptions: dict[str, str] = {}
    figure_manifest_path = settings.convergence_report_dir / "CSV" / "FigureManifest.csv"
    if report_current and figure_manifest_path.is_file():
        try:
            figure_manifest = pd.read_csv(figure_manifest_path)
            if {"figure", "description"}.issubset(figure_manifest.columns):
                figure_descriptions = {
                    Path(str(row["figure"])).name: str(row["description"])
                    for _, row in figure_manifest.iterrows()
                    if not pd.isna(row["figure"]) and not pd.isna(row["description"])
                }
        except Exception:
            figure_descriptions = {}
    if report_current and report_png.exists():
        preferred = [
            "01_Publication_Convergence.png", "02_Publication_Convergence_Zoom.png",
            "03_Global_Improvement_Percent.png", "07_Search_Stream_Reconstruction.png",
            "09_SA_Temperature_Decay.png", "10_Acceptance_Rate.png",
            "11_Stagnation_Counter.png", "15_Algorithm_Objective_Comparison.png",
        ]
        for name in preferred:
            p = report_png / name
            if p.exists():
                figures.append({
                    "name": p.stem.replace("_", " "),
                    "description": figure_descriptions.get(name),
                    "url": _artifact_url(p),
                })

    report_zip_path = RUNTIME_DIR / "ConvergenceReport.zip"
    report_zip = _artifact_url(report_zip_path) if report_current else None
    report_exists = report_png.exists() or report_zip_path.is_file()

    initial = float(finite_global.iloc[0]) if len(finite_global) else None
    final = float(finite_global.iloc[-1]) if len(finite_global) else None
    return {
        # Background analysis deliberately calls include_points=False to avoid
        # duplicating a large browser payload in SQLite. Availability means the
        # telemetry is valid—not that points were requested for this response.
        "available": bool(time_col and len(finite_global)), "path": str(path), "rows": int(len(frame)),
        "duration_s": float(frame[time_col].max()) if time_col and frame[time_col].notna().any() else None,
        "initial_best": initial, "final_best": final,
        "improvement_pct": float((initial-final)/max(abs(initial),1e-9)*100) if initial is not None and final is not None else None,
        "improvement_count": improvement_count,
        "global_source": global_col or "derived cumulative minimum of worker best",
        "points": points, "workers": workers, "events": events,
        "temperature_available": bool(temp_col), "acceptance_available": bool(acceptance_col),
        "stagnation_available": bool(stagnation_col), "checks": checks, "figures": figures,
        "source_receipt": source_receipt,
        "report_current": report_current,
        "report_stale": bool(report_exists and not report_current),
        "report_status": "current" if report_current else "stale" if report_exists else "not_built",
        "report_zip": report_zip,
        "can_build_report": True,
        "figure_revision": str(raw_receipt.get("sha256") or "")[:12] or None,
    }

def clustering_benchmark_summary() -> dict[str, Any]:
    root = settings.clustering_benchmark_dir
    comparison = root / "CSV" / "MethodComparison.csv"
    if not comparison.exists():
        return {"available": False, "methods": [], "figures": [], "message": "Run the clustering benchmark to compare methods."}
    try:
        frame = pd.read_csv(comparison)
    except Exception as exc:
        return {"available": False, "methods": [], "figures": [], "message": str(exc)}
    keep = [
        "label", "requested_mode", "effective_mode", "category", "hard_assignment_feasible",
        "fallback_used", "used_clusters", "empty_clusters", "total_overload", "total_s",
        "nn_route_proxy_total_cost", "weighted_mean_road_cost_to_medoid", "load_std",
    ]
    methods = []
    for _, row in frame.iterrows():
        record = {}
        for col in keep:
            if col in frame.columns:
                val = row[col]
                if pd.isna(val): val = None
                elif isinstance(val, np.generic): val = val.item()
                record[col] = val
        methods.append(record)
    selected = _load_json(root / "Selected" / "selection_manifest.json")
    protocol = _load_json(root / "Protocol" / "protocol.json") or {}
    checksum_by_artifact: dict[str, str] = {}
    checksum_path = root / "Protocol" / "checksums.csv"
    if checksum_path.is_file():
        try:
            checksum_frame = pd.read_csv(checksum_path)
            if {"artifact", "sha256"}.issubset(checksum_frame.columns):
                checksum_by_artifact = {
                    str(row["artifact"]): str(row["sha256"])
                    for _, row in checksum_frame.iterrows()
                    if not pd.isna(row["artifact"]) and not pd.isna(row["sha256"])
                }
        except Exception:
            checksum_by_artifact = {}
    source_receipt = {
        "created_at": protocol.get("created_utc"),
        "job_id": protocol.get("fleetroute_job_id"),
        "source_signature": protocol.get("source_signature"),
        "materialization_id": protocol.get("materialization_id"),
        "customer_count": protocol.get("customer_count"),
        "maximum_available_trucks": protocol.get("K"),
        "capacity": protocol.get("capacity"),
        "input_sha256": checksum_by_artifact.get("input.txt"),
        "dataset_sha256": checksum_by_artifact.get("dataset.json"),
    }
    figs = []
    png = root / "PNG"
    descriptions: dict[str, str] = {}
    manifest_path = root / "Presentation" / "figure_manifest.csv"
    if manifest_path.exists():
        try:
            manifest = pd.read_csv(manifest_path)
            if {"figure", "description"}.issubset(manifest.columns):
                descriptions = {
                    str(row["figure"]): str(row["description"])
                    for _, row in manifest.iterrows()
                    if not pd.isna(row["figure"]) and not pd.isna(row["description"])
                }
        except Exception:
            descriptions = {}
    preferred = [
        "AllMethods.png",
        "MethodScorecard.png",
        "RuntimeVsObjective.png",
        "Runtime.png",
        "RouteProxyObjective.png",
        "RoadCompactness.png",
        "LoadBalance.png",
        "CapacityUtilization.png",
        "ClusterLoads.png",
    ]
    selected_label = str((selected or {}).get("selected_label") or "").strip()
    if selected_label:
        preferred.append(f"Selected_{selected_label}.png")
    for name in preferred:
        p = png / name
        if p.exists():
            figs.append({
                "name": p.stem.replace("_", " "),
                "description": descriptions.get(name),
                "url": _artifact_url(p),
            })
    archive_candidates = sorted(RUNTIME_DIR.glob("ClusteringBenchmark_*.zip"), key=lambda p:p.stat().st_mtime, reverse=True)
    return {
        "available": True,
        "methods": methods,
        "figures": figs,
        "selected": selected,
        "source_receipt": source_receipt,
        "archive": _artifact_url(archive_candidates[0]) if archive_candidates else None,
    }


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_artifact_gallery() -> list[dict[str, Any]]:
    candidates = []
    for path in [settings.network_overview_png, settings.cluster_preview_png]:
        if path.exists():
            candidates.append(path)
    for root in [settings.convergence_report_dir / "PNG", settings.clustering_benchmark_dir / "PNG"]:
        if root.exists():
            candidates.extend(sorted(root.glob("*.png")))
    result = []
    for path in candidates:
        url = _artifact_url(path)
        if url:
            result.append({"name": path.stem.replace("_", " "), "url": url, "size": path.stat().st_size})
    return result[:80]


def _safe_runtime_export_file(path: Path) -> Path | None:
    """Return a regular non-symlink file contained by the runtime root."""
    try:
        candidate = Path(path)
        if candidate.is_symlink() or not candidate.is_file():
            return None
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(RUNTIME_DIR.resolve())
        return resolved
    except (OSError, ValueError):
        return None


def create_run_evidence_zip() -> Path:
    path = settings.run_package_zip
    path.parent.mkdir(parents=True, exist_ok=True)
    roots = [
        settings.input_txt, settings.dataset_json, settings.dataset_summary_json,
        settings.solver_invocation_json, settings.solver_stderr,
        RUNTIME_DIR / "solver_attempt_with_clustering.txt",
        RUNTIME_DIR / "solver_attempt_with_clustering.stderr.txt", settings.clusters_csv,
        settings.cluster_summary_csv, settings.cluster_timing_csv,
        settings.solver_output, settings.convergence_csv, settings.run_summary_csv,
        settings.routes_json, settings.network_overview_png, settings.cluster_preview_png,
    ]
    with _EVIDENCE_ZIP_LOCK:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.unlink(missing_ok=True)
        try:
            with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
                for file in roots:
                    safe = _safe_runtime_export_file(file)
                    if safe is not None:
                        archive.write(safe, arcname=safe.name)
                for directory in [settings.convergence_report_dir, settings.clustering_benchmark_dir]:
                    if directory.exists():
                        for file in directory.rglob("*"):
                            safe = _safe_runtime_export_file(file)
                            if safe is not None:
                                archive.write(safe, arcname=str(safe.relative_to(RUNTIME_DIR.resolve())))
            with zipfile.ZipFile(temp, "r") as completed:
                if not completed.namelist():
                    raise ValueError("No run evidence is available yet. Prepare a plan or complete a run before exporting.")
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
    return path
