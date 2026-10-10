from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import math
import os
import random
import re
import shlex
import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
import networkx as nx
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra as sparse_dijkstra
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from .analytics import (
    clustering_benchmark_summary,
    convergence_summary,
    create_run_evidence_zip,
    generate_cluster_preview,
    generate_network_overview,
    list_artifact_gallery,
    parse_cluster_assignments,
    validate_clusters,
)
from .baseline import (
    RoutingContext,
    build_baseline_routes,
    build_route_schedule,
    objective_value,
    routing_context_for_dataset,
    validate_solver_routes,
)
from .config import RUNTIME_DIR, settings
from .db import (
    connect,
    create_job,
    expire_stale_jobs_if_due,
    get_job,
    get_setting,
    get_settings,
    latest_route_version,
    list_active_jobs,
    log_event,
    set_setting,
    update_job,
    utc_now,
)
from .exports import create_driver_package
from .graph_store import GRAPH_STORE, osm_bool
from .jobs import JobCancelled, JobReporter
from .offline_osm import (
    add_edge_speeds_and_times,
    browsed_osm_region,
    download_selected_region_pbf,
    osm_source_library,
    prepare_operating_graph,
    region_points_coverage,
    region_source_status,
    region_target_status,
    remove_selected_region_pbf,
    selected_osm_region,
    set_active_osm_region,
)

_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="fleetroute-worker")
_SOLVE_LOCK = threading.Lock()
_BENCHMARK_LOCK = threading.Lock()
_GEOCODER_LOCK = threading.Lock()
_LAST_GEOCODER_AT = 0.0
_HASH_CACHE_LOCK = threading.Lock()
_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_DATASET_CACHE_LOCK = threading.Lock()
_DATASET_CACHE: tuple[tuple[str, int, int, int], dict[str, Any]] | None = None
_SOLVER_SCHEMA_CACHE_LOCK = threading.Lock()
_SOLVER_SCHEMA_CACHE: tuple[tuple[int, int], dict[str, dict[str, Any]]] | None = None
RESEARCH_SOLVER_OVERRIDES_ENABLED = os.getenv("VRP_ENABLE_RESEARCH_SOLVER_OVERRIDES", "0").strip().lower() in {"1", "true", "yes", "on"}
_ROUTING_CONTEXT_LOCK = threading.Lock()
# Serializes publication of the materialized native input files with route-version
# commits. SQLite protects database writers, but input.txt/dataset.json are files;
# this lock closes the cross-resource race where a closure/scenario could replace
# those files after a route commit check but before the route version is published.
_INPUT_PUBLICATION_LOCK = threading.RLock()
# Serializes the "idle check → operational mutation/job creation" boundary.
# Without this lock, two nearly simultaneous browser/API requests could both
# observe an idle workspace and enqueue conflicting graph/download/solve jobs.
_OPERATION_QUEUE_LOCK = threading.RLock()
# Prevent concurrent partial settings updates from losing each other between the
# read/merge/write/revision steps.
_SETTINGS_UPDATE_LOCK = threading.RLock()
_ACTIVE_ROUTING_CONTEXT: RoutingContext | None = None


def _set_active_routing_context(context: RoutingContext | None) -> None:
    global _ACTIVE_ROUTING_CONTEXT
    with _ROUTING_CONTEXT_LOCK:
        _ACTIVE_ROUTING_CONTEXT = context


def _active_routing_context(
    materialization_id: str, objective_mode: str | None = None
) -> RoutingContext | None:
    """Return a cached path context only when both graph and path objective match."""
    with _ROUTING_CONTEXT_LOCK:
        context = _ACTIVE_ROUTING_CONTEXT
        if context is None or context.materialization_id != str(materialization_id or ""):
            return None
        if objective_mode is not None and context.objective_mode != str(objective_mode):
            return None
        return context


def _mark_routes_stale(reason: str, actor: str = "system") -> dict[str, Any]:
    current = get_setting("route_state") or {}
    payload = {
        "stale": True,
        "reason": str(reason),
        "changed_at": utc_now(),
        "route_version": current.get("route_version"),
        "route_phase": "stale",
        "solution_source": current.get("solution_source"),
        "optimization_completed": bool(current.get("optimization_completed")),
        "optimization_outcome": current.get("optimization_outcome", "not_started"),
        "optimization_completed_at": current.get("optimization_completed_at"),
        "optimization_checked_at": current.get("optimization_checked_at"),
        "closure_revision": int((get_setting("closure_revision") or {}).get("revision", 0)),
    }
    set_setting("route_state", payload)
    # Any mutation that makes a published route stale also invalidates the
    # materialized solver contract. Keep the old files as evidence, but do not
    # advertise them as the current input for a changed plan/fleet/closure.
    set_setting("active_input_state", {})
    _set_active_routing_context(None)
    log_event("routes.stale", payload, actor)
    return payload


def _fresh_route_state_payload(
    route_version: int,
    source_job_id: int,
    solution_source: str = "cpp_optimizer",
    settings_revision: dict[str, int] | None = None,
    *,
    active_input: dict[str, Any] | None = None,
    closure_revision: int | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Build the exact route-state record without performing a database write."""
    rev = dict(settings_revision) if settings_revision is not None else _settings_revision()
    active = dict(active_input) if active_input is not None else dict(get_setting("active_input_state") or {})
    stamp = str(now or utc_now())
    optimizer_completed = str(solution_source) == "cpp_optimizer"
    if closure_revision is None:
        closure_revision = int((get_setting("closure_revision") or {}).get("revision", 0))
    return {
        "stale": False,
        "reason": "optimized route ready" if optimizer_completed else "prepared route ready",
        "changed_at": stamp,
        "route_version": int(route_version),
        "source_job_id": int(source_job_id),
        "solution_source": str(solution_source),
        # A deterministic baseline is a safe, independently feasible fallback,
        # but it is not evidence that the native search has completed.  The UI,
        # driver manifest, and workflow all consume this explicit distinction.
        "route_phase": "optimized" if optimizer_completed else "prepared",
        "optimization_completed": optimizer_completed,
        "optimization_outcome": (
            "improved_route_published" if optimizer_completed else "not_started"
        ),
        "prepared_at": stamp,
        "optimization_completed_at": stamp if optimizer_completed else None,
        "closure_revision": int(closure_revision),
        "fleet_revision": int(rev.get("fleet", 0)),
        "solver_revision": int(rev.get("solver", 0)),
        # Bind the publication to the exact materialized contract.  Older
        # databases may not have these fields; rerun protection also accepts
        # their still-current active_input_state as a compatibility fallback.
        "source_signature": active.get("source_signature"),
        "materialization_id": active.get("materialization_id"),
        "input_sha256": active.get("input_sha256"),
        "dataset_sha256": active.get("dataset_sha256"),
    }


def _mark_routes_fresh(
    route_version: int,
    source_job_id: int,
    solution_source: str = "cpp_optimizer",
    settings_revision: dict[str, int] | None = None,
) -> dict[str, Any]:
    payload = _fresh_route_state_payload(
        route_version, source_job_id, solution_source, settings_revision
    )
    set_setting("route_state", payload)
    return payload


def _mark_route_optimization_checked(
    route_version: int,
    source_job_id: int,
    settings_revision: dict[str, int],
) -> dict[str, Any] | None:
    """Record a successful no-improvement search without minting a route copy."""
    current = dict(get_setting("route_state") or {})
    if current.get("stale") is not False or int(current.get("route_version") or 0) != int(route_version):
        return None
    current.update({
        "solver_revision": int(settings_revision.get("solver", 0)),
        "route_phase": "reviewed",
        "optimization_completed": True,
        "optimization_checked_at": utc_now(),
        "optimization_completed_at": utc_now(),
        "last_optimization_job_id": int(source_job_id),
        "optimization_outcome": "valid_candidate_not_better",
        "reason": "optimization completed; prepared route retained",
    })
    set_setting("route_state", current)
    return current


def _bump_closure_revision(
    reason: str,
    closure_id: int | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Atomically advance the road-closure generation.

    Callers that already hold ``BEGIN IMMEDIATE`` pass their connection so the
    closure state change and its generation are one transaction.  Standalone
    callers acquire the writer transaction here.
    """
    def advance(db: sqlite3.Connection) -> int:
        row = db.execute(
            "SELECT value_json FROM app_settings WHERE key='closure_revision'"
        ).fetchone()
        try:
            current = json.loads(row["value_json"]) if row else {}
        except Exception:
            current = {}
        revision = int(current.get("revision", 0)) + 1
        payload = {"revision": revision, "changed_at": utc_now(), "reason": str(reason)}
        if closure_id is not None:
            payload["closure_id"] = int(closure_id)
        db.execute(
            """INSERT INTO app_settings(key,value_json,updated_at) VALUES('closure_revision',?,?)
               ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
            (json.dumps(payload, ensure_ascii=False), utc_now()),
        )
        return revision

    if conn is not None:
        return advance(conn)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        return advance(db)


def _solver_flag_schema() -> dict[str, dict[str, Any]]:
    global _SOLVER_SCHEMA_CACHE
    stat = settings.solver_cpp.stat()
    signature = (int(stat.st_mtime_ns), int(stat.st_size))
    with _SOLVER_SCHEMA_CACHE_LOCK:
        cached = _SOLVER_SCHEMA_CACHE
        if cached is not None and cached[0] == signature:
            return cached[1]
    text = settings.solver_cpp.read_text(encoding="utf-8", errors="replace")
    schema: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        # One parser branch may expose aliases, e.g.
        # ``s == "--metric_mode" || s == "--metric"``. Index every alias
        # rather than only the first match so validation and protection mirror
        # the real C++ parser exactly.
        matches = re.findall(r's == "(--[A-Za-z0-9_]+)"', line)
        if not matches:
            continue
        for flag in matches:
            schema[flag] = {"takes_value": "i + 1 < argc" in line}
    with _SOLVER_SCHEMA_CACHE_LOCK:
        _SOLVER_SCHEMA_CACHE = (signature, schema)
    return schema


# Typed research controls exposed by the Optimizer.  A missing key means
# "use the selected profile / native default".  Keeping overrides structured in
# SQLite makes the UI auditable and prevents transient DOM state or duplicate raw
# argv flags from changing a run silently.
ADVANCED_SOLVER_SPECS: dict[str, dict[str, Any]] = {
    # Automatic policy values may be overridden here deliberately.  Runtime,
    # instance count, fleet size, and capacity remain first-class controls;
    # lifecycle/evidence flags and automatic no-improvement patience do not.
    "time_limit": {"flag": "--time_limit", "type": "int", "min": 1, "max": 600, "category": "Budget internals", "label": "Native stage slice (s)", "description": "Advanced override for the per-stage slice selected by the customer-count tier."},
    "meaningful_gain_abs": {"flag": "--meaningful_gain_abs", "type": "float", "min": 0.0, "max": 1000000000.0, "step": 0.01, "category": "Budget internals", "label": "Meaningful gain (absolute)", "description": "Absolute objective gain that resets automatic stagnation patience."},
    "meaningful_gain_rel": {"flag": "--meaningful_gain_rel", "type": "float", "min": 0.0, "max": 1.0, "step": 0.0001, "category": "Budget internals", "label": "Meaningful gain (relative)", "description": "Relative objective gain that resets automatic stagnation patience."},
    "use_dense_pair_matrix": {"flag": "--use_dense_pair_matrix", "type": "bool", "category": "Performance engine", "label": "Dense pair matrix", "description": "Use the benchmark-proven dense road-pair cache."},
    "use_dirty_route_recompute": {"flag": "--use_dirty_route_recompute", "type": "bool", "category": "Performance engine", "label": "Dirty-route recompute", "description": "Recompute only routes changed by a move."},
    "euclidean_hgs_only": {"flag": "--euclidean_hgs_only", "type": "bool", "category": "Performance engine", "label": "Euclidean-only HGS", "description": "Restrict HGS to Euclidean instances; disabled by all supplied road benchmarks."},
    # Candidate / insertion engine
    "use_candidate_lists": {"flag": "--use_candidate_lists", "type": "bool", "category": "Candidate & insertion", "label": "Candidate lists", "description": "Restrict expensive neighborhood scans to candidate arcs."},
    "candidate_k": {"flag": "--candidate_k", "type": "int", "min": 4, "max": 512, "category": "Candidate & insertion", "label": "Candidate K", "description": "Nearest/candidate neighbors retained per work point."},
    "candidate_route_probe_k": {"flag": "--candidate_route_probe_k", "type": "int", "min": 1, "max": 64, "category": "Candidate & insertion", "label": "Route probe K", "description": "Candidate routes probed during insertion."},
    "use_topk_insertion": {"flag": "--use_topk_insertion", "type": "bool", "category": "Candidate & insertion", "label": "Top-K insertion", "description": "Rank insertion positions before exact evaluation."},
    "insertion_topk_exact": {"flag": "--insertion_topk_exact", "type": "int", "min": 1, "max": 512, "category": "Candidate & insertion", "label": "Exact insertion Top-K", "description": "Number of ranked insertion positions evaluated exactly."},
    "use_simd_insertion_rank": {"flag": "--use_simd_insertion_rank", "type": "bool", "category": "Candidate & insertion", "label": "SIMD insertion ranking", "description": "Use the AVX2 ranking path when supported."},
    "simd_global_topk_multiplier": {"flag": "--simd_global_topk_multiplier", "type": "int", "min": 1, "max": 16, "category": "Candidate & insertion", "label": "SIMD Top-K multiplier", "description": "Multiplier for the SIMD global candidate shortlist."},
    "regret_k": {"flag": "--regret_k", "type": "int", "min": 2, "max": 8, "category": "Candidate & insertion", "label": "Regret K", "description": "Regret-repair lookahead depth."},
    "insertion_route_cap": {"flag": "--insertion_route_cap", "type": "int", "min": 1, "max": 512, "category": "Candidate & insertion", "label": "Insertion route cap", "description": "Maximum routes considered per insertion."},
    "insertion_pos_cap": {"flag": "--insertion_pos_cap", "type": "int", "min": 1, "max": 4096, "category": "Candidate & insertion", "label": "Insertion position cap", "description": "Maximum positions scanned per insertion route."},

    # Savings / initialization
    "use_savings_warm_start": {"flag": "--use_savings_warm_start", "type": "bool", "category": "Warm start", "label": "Savings warm start", "description": "Build Clarke-Wright style road-metric starts."},
    "savings_variants": {"flag": "--savings_variants", "type": "int", "min": 1, "max": 64, "category": "Warm start", "label": "Savings variants", "description": "Independent Savings variants generated before search."},
    "savings_noise": {"flag": "--savings_noise", "type": "float", "min": 0.0, "max": 1.0, "step": 0.005, "category": "Warm start", "label": "Savings noise", "description": "Controlled diversification applied to Savings scores."},
    "savings_polish_time_s": {"flag": "--savings_polish_time_s", "type": "float", "min": 0.0, "max": 120.0, "step": 0.1, "category": "Warm start", "label": "Savings polish time (s)", "description": "Short polish budget for Savings candidates."},
    "savings_light_polish_rounds": {"flag": "--savings_light_polish_rounds", "type": "int", "min": 0, "max": 100, "category": "Warm start", "label": "Savings light polish rounds", "description": "Cheap local passes applied to Savings starts."},

    # ALNS / fragment LNS
    "use_alns": {"flag": "--use_alns", "type": "bool", "category": "ALNS & Fragment LNS", "label": "ALNS", "description": "Enable adaptive large-neighborhood perturbation."},
    "alns_rounds": {"flag": "--alns_rounds", "type": "int", "min": 0, "max": 100, "category": "ALNS & Fragment LNS", "label": "ALNS rounds", "description": "ALNS rounds per trigger/pass."},
    "alns_destroy_min_ratio": {"flag": "--alns_destroy_min_ratio", "type": "float", "min": 0.01, "max": 0.9, "step": 0.01, "category": "ALNS & Fragment LNS", "label": "Destroy ratio min", "description": "Minimum fraction removed by ALNS."},
    "alns_destroy_max_ratio": {"flag": "--alns_destroy_max_ratio", "type": "float", "min": 0.01, "max": 0.95, "step": 0.01, "category": "ALNS & Fragment LNS", "label": "Destroy ratio max", "description": "Maximum fraction removed by ALNS."},
    "stagnation_trigger": {"flag": "--stagnation_trigger", "type": "int", "min": 1, "max": 1000000, "category": "ALNS & Fragment LNS", "label": "ALNS stagnation trigger", "description": "Stagnation iterations before an ALNS kick."},
    "use_fragment_lns": {"flag": "--use_fragment_lns", "type": "bool", "category": "ALNS & Fragment LNS", "label": "Fragment LNS", "description": "Enable fragment destroy/repair education."},
    "fragment_lns_rounds": {"flag": "--fragment_lns_rounds", "type": "int", "min": 0, "max": 5000, "category": "ALNS & Fragment LNS", "label": "Fragment LNS rounds", "description": "Number of fragment-LNS rounds."},
    "fragment_lns_remove_min": {"flag": "--fragment_lns_remove_min", "type": "int", "min": 1, "max": 500, "category": "ALNS & Fragment LNS", "label": "Fragment remove min", "description": "Minimum customers removed in one fragment ruin."},
    "fragment_lns_remove_max": {"flag": "--fragment_lns_remove_max", "type": "int", "min": 1, "max": 1000, "category": "ALNS & Fragment LNS", "label": "Fragment remove max", "description": "Maximum customers removed in one fragment ruin."},
    "fragment_lns_related_k": {"flag": "--fragment_lns_related_k", "type": "int", "min": 1, "max": 512, "category": "ALNS & Fragment LNS", "label": "Relatedness K", "description": "Neighborhood size for related-customer ruin."},
    "fragment_lns_pos_cap": {"flag": "--fragment_lns_pos_cap", "type": "int", "min": 1, "max": 4096, "category": "ALNS & Fragment LNS", "label": "Fragment position cap", "description": "Insertion positions considered during fragment repair."},
    "fragment_lns_verbose": {"flag": "--fragment_lns_verbose", "type": "bool", "category": "Diagnostics", "label": "Fragment LNS diagnostics", "description": "Emit native fragment-LNS diagnostics to cerr/stderr."},
    "fragment_lns_euclidean_educate": {"flag": "--fragment_lns_euclidean_educate", "type": "bool", "category": "ALNS & Fragment LNS", "label": "Euclidean fragment education", "description": "Use Euclidean education inside fragment LNS; off for road-metric tiers."},
    "use_longest_route_ruin": {"flag": "--use_longest_route_ruin", "type": "bool", "category": "ALNS & Fragment LNS", "label": "Longest-route ruin", "description": "Bias selected ruins toward long/problem routes."},
    "longest_route_ruin_probability": {"flag": "--longest_route_ruin_probability", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05, "category": "ALNS & Fragment LNS", "label": "Longest-route ruin probability", "description": "Probability of using the longest-route ruin operator."},

    # Local / global polishing
    "use_elite_pool": {"flag": "--use_elite_pool", "type": "bool", "category": "Polish & elite", "label": "Elite pool", "description": "Maintain high-quality diverse solutions."},
    "use_path_relink": {"flag": "--use_path_relink", "type": "bool", "category": "Polish & elite", "label": "Path relinking", "description": "Recombine elite solutions by path relinking."},
    "relink_period": {"flag": "--relink_period", "type": "int", "min": 1, "max": 100000, "category": "Polish & elite", "label": "Relink period", "description": "Iteration interval between path-relink attempts."},
    "use_final_polish": {"flag": "--use_final_polish", "type": "bool", "category": "Polish & elite", "label": "Final polish", "description": "Enable final local improvement passes."},
    "final_polish_rounds": {"flag": "--final_polish_rounds", "type": "int", "min": 0, "max": 500, "category": "Polish & elite", "label": "Final polish rounds", "description": "Number of final polishing rounds."},
    "final_refinement_rounds": {"flag": "--final_refinement_rounds", "type": "int", "min": 0, "max": 500, "category": "Polish & elite", "label": "Final refinement rounds", "description": "Extra refinement passes after primary search."},
    "use_interroute_polish": {"flag": "--use_interroute_polish", "type": "bool", "category": "Polish & elite", "label": "Inter-route polish", "description": "Enable moves between routes during polish."},
    "interroute_polish_rounds": {"flag": "--interroute_polish_rounds", "type": "int", "min": 0, "max": 500, "category": "Polish & elite", "label": "Inter-route rounds", "description": "Number of inter-route polishing rounds."},
    "interroute_scan_cap": {"flag": "--interroute_scan_cap", "type": "int", "min": 1, "max": 1000000, "category": "Polish & elite", "label": "Inter-route scan cap", "description": "Upper bound on candidate scans in inter-route polish."},
    "max_interroute_moves": {"flag": "--max_interroute_moves", "type": "int", "min": 0, "max": 100000, "category": "Polish & elite", "label": "Max inter-route moves", "description": "Maximum accepted inter-route moves per pass."},
    "use_oropt": {"flag": "--use_oropt", "type": "bool", "category": "Polish & elite", "label": "Or-opt", "description": "Enable Or-opt local search."},
    "use_2opt": {"flag": "--use_2opt", "type": "bool", "category": "Polish & elite", "label": "2-opt", "description": "Enable intra-route 2-opt."},
    "use_relocate_polish": {"flag": "--use_relocate_polish", "type": "bool", "category": "Polish & elite", "label": "Relocate polish", "description": "Enable relocate-based local polish."},

    # Guided / targeted diversification
    "use_guided_arc_penalty": {"flag": "--use_guided_arc_penalty", "type": "bool", "category": "Guided & targeted search", "label": "Guided arc penalty", "description": "Enable GLS-style arc penalties."},
    "gls_time_limit_s": {"flag": "--gls_time_limit_s", "type": "float", "min": 0.0, "max": 600.0, "step": 0.1, "category": "Guided & targeted search", "label": "GLS time limit (s)", "description": "Dedicated guided-search sub-budget."},
    "gls_max_total_moves": {"flag": "--gls_max_total_moves", "type": "int", "min": 0, "max": 1000000, "category": "Guided & targeted search", "label": "GLS move cap", "description": "Maximum guided local-search moves."},
    "gls_max_stagnation": {"flag": "--gls_max_stagnation", "type": "int", "min": 0, "max": 100000, "category": "Guided & targeted search", "label": "GLS stagnation cap", "description": "Stop a GLS pass after this many stagnant rounds."},
    "gls_try_swaps": {"flag": "--gls_try_swaps", "type": "bool", "category": "Guided & targeted search", "label": "GLS swaps", "description": "Allow swap moves during guided search."},
    "use_granular_tabu": {"flag": "--use_granular_tabu", "type": "bool", "category": "Guided & targeted search", "label": "Granular tabu", "description": "Enable granular tabu refinement."},
    "granular_tabu_iters": {"flag": "--granular_tabu_iters", "type": "int", "min": 0, "max": 1000000, "category": "Guided & targeted search", "label": "Granular tabu iterations", "description": "Iteration budget for granular tabu refinement."},
    "granular_tabu_top_pairs": {"flag": "--granular_tabu_top_pairs", "type": "int", "min": 1, "max": 512, "category": "Guided & targeted search", "label": "Granular top pairs", "description": "Highest-priority route/customer pairs considered by tabu."},
    "granular_tabu_candidate_cap": {"flag": "--granular_tabu_candidate_cap", "type": "int", "min": 1, "max": 100000, "category": "Guided & targeted search", "label": "Granular candidate cap", "description": "Candidate evaluation cap for tabu moves."},
    "use_route_region_lns": {"flag": "--use_route_region_lns", "type": "bool", "category": "Guided & targeted search", "label": "Route-region LNS", "description": "Enable geographically/route targeted LNS."},
    "route_region_lns_rounds": {"flag": "--route_region_lns_rounds", "type": "int", "min": 0, "max": 1000, "category": "Guided & targeted search", "label": "Route-region rounds", "description": "Targeted route-region LNS rounds."},
    "use_boundary_pair_lns": {"flag": "--use_boundary_pair_lns", "type": "bool", "category": "Guided & targeted search", "label": "Boundary-pair LNS", "description": "Enable LNS around expensive route boundaries."},
    "boundary_pair_lns_rounds": {"flag": "--boundary_pair_lns_rounds", "type": "int", "min": 0, "max": 1000, "category": "Guided & targeted search", "label": "Boundary-pair rounds", "description": "Boundary-pair LNS rounds."},
    "route_region_lns_verbose": {"flag": "--route_region_lns_verbose", "type": "bool", "category": "Diagnostics", "label": "Region LNS diagnostics", "description": "Emit native route-region diagnostics to cerr/stderr."},
    "boundary_pair_lns_verbose": {"flag": "--boundary_pair_lns_verbose", "type": "bool", "category": "Diagnostics", "label": "Boundary LNS diagnostics", "description": "Emit native boundary-pair diagnostics to cerr/stderr."},
    "granular_tabu_verbose": {"flag": "--granular_tabu_verbose", "type": "bool", "category": "Diagnostics", "label": "Granular tabu diagnostics", "description": "Emit native tabu diagnostics to cerr/stderr."},

    # Time-window behavior
    "tw_strict_insertion": {"flag": "--tw_strict_insertion", "type": "bool", "category": "Time windows", "label": "Strict TW insertion", "description": "Reject insertion positions that violate hard windows."},
    "tw_sort_seed_by_window": {"flag": "--tw_sort_seed_by_window", "type": "bool", "category": "Time windows", "label": "Sort seed by window", "description": "Bias initial ordering using time-window structure."},
    "tw_use_time_warp": {"flag": "--tw_use_time_warp", "type": "bool", "category": "Time windows", "label": "Time-warp search", "description": "Allow penalized intermediate TW violations during search."},
    "tw_allow_soft_intermediate": {"flag": "--tw_allow_soft_intermediate", "type": "bool", "category": "Time windows", "label": "Soft intermediate TW", "description": "Permit soft intermediate states while keeping final validation strict."},
    "tw_time_warp_penalty": {"flag": "--tw_time_warp_penalty", "type": "float", "min": 0.0, "max": 1000000000.0, "step": 1.0, "category": "Time windows", "label": "Time-warp penalty", "description": "Penalty scale for intermediate lateness."},

    # Detailed GLS controls
    "gls_rounds": {"flag": "--gls_rounds", "type": "int", "min": 0, "max": 10000, "category": "GLS detailed", "label": "GLS rounds", "description": "Number of guided local-search rounds."},
    "gls_moves_per_round": {"flag": "--gls_moves_per_round", "type": "int", "min": 0, "max": 1000000, "category": "GLS detailed", "label": "Moves per GLS round", "description": "Move evaluations/attempts allocated to each GLS round."},
    "gls_lambda": {"flag": "--gls_lambda", "type": "float", "min": 0.0, "max": 1000000.0, "step": 0.01, "category": "GLS detailed", "label": "GLS lambda", "description": "Arc-penalty strength."},
    "gls_penalty_top_k": {"flag": "--gls_penalty_top_k", "type": "int", "min": 1, "max": 10000, "category": "GLS detailed", "label": "Penalty top-K", "description": "Highest-utility arcs penalized per GLS update."},
    "gls_source_route_cap": {"flag": "--gls_source_route_cap", "type": "int", "min": 1, "max": 10000, "category": "GLS detailed", "label": "Source route cap", "description": "Source routes considered by guided moves."},
    "gls_source_customer_cap": {"flag": "--gls_source_customer_cap", "type": "int", "min": 1, "max": 100000, "category": "GLS detailed", "label": "Source customer cap", "description": "Source customers considered by guided moves."},
    "gls_target_route_cap": {"flag": "--gls_target_route_cap", "type": "int", "min": 1, "max": 10000, "category": "GLS detailed", "label": "Target route cap", "description": "Target routes considered during guided relocation."},
    "gls_pos_cap": {"flag": "--gls_pos_cap", "type": "int", "min": 1, "max": 100000, "category": "GLS detailed", "label": "GLS position cap", "description": "Insertion positions inspected by guided moves."},
    "gls_max_exact_worsen_per_move": {"flag": "--gls_max_exact_worsen_per_move", "type": "float", "min": 0.0, "max": 1000000000.0, "step": 1.0, "category": "GLS detailed", "label": "Max exact worsen / move", "description": "Exact objective deterioration permitted in a guided move."},
    "gls_adaptive_lambda": {"flag": "--gls_adaptive_lambda", "type": "bool", "category": "GLS detailed", "label": "Adaptive GLS lambda", "description": "Adapt penalty strength under stagnation."},
    "gls_lambda_base": {"flag": "--gls_lambda_base", "type": "float", "min": 0.0, "max": 1000000.0, "step": 0.01, "category": "GLS detailed", "label": "Lambda base", "description": "Base lambda for adaptive GLS."},
    "gls_lambda_growth": {"flag": "--gls_lambda_growth", "type": "float", "min": 0.0, "max": 100.0, "step": 0.01, "category": "GLS detailed", "label": "Lambda growth", "description": "Adaptive lambda growth factor."},
    "gls_lambda_max": {"flag": "--gls_lambda_max", "type": "float", "min": 0.0, "max": 1000000000.0, "step": 0.1, "category": "GLS detailed", "label": "Lambda maximum", "description": "Maximum adaptive GLS lambda."},
    "gls_adaptive_worsen_cap": {"flag": "--gls_adaptive_worsen_cap", "type": "bool", "category": "GLS detailed", "label": "Adaptive worsen cap", "description": "Adapt controlled worsening allowance during GLS."},
    "gls_worsen_growth": {"flag": "--gls_worsen_growth", "type": "float", "min": 0.0, "max": 100.0, "step": 0.01, "category": "GLS detailed", "label": "Worsen-cap growth", "description": "Growth factor for adaptive worsening allowance."},
    "gls_worsen_max": {"flag": "--gls_worsen_max", "type": "float", "min": 0.0, "max": 1000000000.0, "step": 1.0, "category": "GLS detailed", "label": "Worsen-cap maximum", "description": "Maximum adaptive worsening allowance."},

    # Deeper LNS controls
    "route_region_lns_seed_pairs": {"flag": "--route_region_lns_seed_pairs", "type": "int", "min": 1, "max": 10000, "category": "Deep LNS", "label": "Region seed pairs", "description": "Seed route pairs used by route-region LNS."},
    "route_region_lns_max_routes": {"flag": "--route_region_lns_max_routes", "type": "int", "min": 1, "max": 1000, "category": "Deep LNS", "label": "Region max routes", "description": "Maximum routes included in one route-region neighborhood."},
    "route_region_lns_remove_min": {"flag": "--route_region_lns_remove_min", "type": "int", "min": 1, "max": 1000, "category": "Deep LNS", "label": "Region remove min", "description": "Minimum customers removed by route-region LNS."},
    "route_region_lns_remove_max": {"flag": "--route_region_lns_remove_max", "type": "int", "min": 1, "max": 5000, "category": "Deep LNS", "label": "Region remove max", "description": "Maximum customers removed by route-region LNS."},
    "route_region_lns_neighbor_radius": {"flag": "--route_region_lns_neighbor_radius", "type": "int", "min": 1, "max": 10000, "category": "Deep LNS", "label": "Region neighbor radius", "description": "Candidate-neighbor radius used to form regional neighborhoods."},
    "longest_route_ruin_top_routes": {"flag": "--longest_route_ruin_top_routes", "type": "int", "min": 1, "max": 1000, "category": "Deep LNS", "label": "Longest-route top routes", "description": "Number of expensive routes eligible for targeted ruin."},
    "longest_route_ruin_block_radius": {"flag": "--longest_route_ruin_block_radius", "type": "int", "min": 0, "max": 1000, "category": "Deep LNS", "label": "Ruin block radius", "description": "Contiguous route radius removed around a target."},
    "longest_route_ruin_extra_related": {"flag": "--longest_route_ruin_extra_related", "type": "int", "min": 0, "max": 1000, "category": "Deep LNS", "label": "Extra related removals", "description": "Additional related customers removed with a longest-route block."},
    "boundary_pair_lns_top_pairs": {"flag": "--boundary_pair_lns_top_pairs", "type": "int", "min": 1, "max": 10000, "category": "Deep LNS", "label": "Boundary top pairs", "description": "Highest-cost route-boundary pairs considered."},
    "boundary_pair_lns_max_remove": {"flag": "--boundary_pair_lns_max_remove", "type": "int", "min": 1, "max": 5000, "category": "Deep LNS", "label": "Boundary max remove", "description": "Maximum customers removed in boundary-pair LNS."},
    "boundary_pair_lns_add_neighbors": {"flag": "--boundary_pair_lns_add_neighbors", "type": "int", "min": 0, "max": 1000, "category": "Deep LNS", "label": "Boundary add neighbors", "description": "Related neighbors added around boundary targets."},

    # HGS-lite / population search
    "use_hgs_lite": {"flag": "--use_hgs_lite", "type": "bool", "category": "HGS-lite", "label": "HGS-lite", "description": "Enable the bundled lightweight population-based search."},
    "hgs_population_size": {"flag": "--hgs_population_size", "type": "int", "min": 2, "max": 1000, "category": "HGS-lite", "label": "Population size", "description": "Number of individuals retained by HGS-lite."},
    "hgs_generations": {"flag": "--hgs_generations", "type": "int", "min": 0, "max": 100000, "category": "HGS-lite", "label": "Generations", "description": "Generation budget for HGS-lite."},
    "hgs_elite_keep": {"flag": "--hgs_elite_keep", "type": "int", "min": 1, "max": 1000, "category": "HGS-lite", "label": "Elite keep", "description": "Elite individuals preserved between generations."},
    "hgs_mutation_rate": {"flag": "--hgs_mutation_rate", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "category": "HGS-lite", "label": "Mutation rate", "description": "Mutation probability for HGS-lite children."},
    "hgs_use_order_crossover": {"flag": "--hgs_use_order_crossover", "type": "bool", "category": "HGS-lite", "label": "Order crossover", "description": "Use order-based crossover when creating children."},
    "hgs_educate_children": {"flag": "--hgs_educate_children", "type": "bool", "category": "HGS-lite", "label": "Educate children", "description": "Run local education on generated children."},
    "hgs_deep_every": {"flag": "--hgs_deep_every", "type": "int", "min": 1, "max": 10000, "category": "HGS-lite", "label": "Deep education period", "description": "Generations between deeper education passes."},
    "hgs_child_branch_passes": {"flag": "--hgs_child_branch_passes", "type": "int", "min": 0, "max": 1000, "category": "HGS-lite", "label": "Child branch passes", "description": "Deep branch/refinement passes per selected child."},
    "hgs_exact_fleet_split": {"flag": "--hgs_exact_fleet_split", "type": "bool", "category": "HGS-lite", "label": "Exact fleet split", "description": "Use exact fleet split logic where supported."},

    # Tabu / boundary education
    "granular_tabu_customer_radius": {"flag": "--granular_tabu_customer_radius", "type": "int", "min": 1, "max": 10000, "category": "Tabu & boundary education", "label": "Tabu customer radius", "description": "Candidate customer-neighborhood radius for granular tabu."},
    "granular_tabu_tenure_min": {"flag": "--granular_tabu_tenure_min", "type": "int", "min": 0, "max": 100000, "category": "Tabu & boundary education", "label": "Tabu tenure min", "description": "Minimum tabu tenure."},
    "granular_tabu_tenure_max": {"flag": "--granular_tabu_tenure_max", "type": "int", "min": 0, "max": 100000, "category": "Tabu & boundary education", "label": "Tabu tenure max", "description": "Maximum tabu tenure."},
    "granular_tabu_worsen_cap": {"flag": "--granular_tabu_worsen_cap", "type": "float", "min": 0.0, "max": 1000000000.0, "step": 1.0, "category": "Tabu & boundary education", "label": "Tabu worsen cap", "description": "Controlled worsening limit for tabu exploration."},
    "granular_tabu_allow_worsen": {"flag": "--granular_tabu_allow_worsen", "type": "bool", "category": "Tabu & boundary education", "label": "Allow tabu worsening", "description": "Permit controlled non-improving tabu moves."},
    "use_route_pair_diag": {"flag": "--use_route_pair_diag", "type": "bool", "category": "Tabu & boundary education", "label": "Route-pair diagnostics", "description": "Enable route-pair boundary diagnostics used for targeted search."},
    "route_pair_diag_top": {"flag": "--route_pair_diag_top", "type": "int", "min": 1, "max": 10000, "category": "Tabu & boundary education", "label": "Route-pair top", "description": "Top expensive route pairs retained by diagnostics."},
    "route_pair_diag_neighbor_k": {"flag": "--route_pair_diag_neighbor_k", "type": "int", "min": 1, "max": 10000, "category": "Tabu & boundary education", "label": "Route-pair neighbor K", "description": "Neighbor depth used by route-pair diagnostics."},
    "use_boundary_prioritized_education": {"flag": "--use_boundary_prioritized_education", "type": "bool", "category": "Tabu & boundary education", "label": "Boundary-prioritized education", "description": "Prioritize local education around costly route boundaries."},
    "boundary_prioritized_top_pairs": {"flag": "--boundary_prioritized_top_pairs", "type": "int", "min": 1, "max": 10000, "category": "Tabu & boundary education", "label": "Boundary education top pairs", "description": "Route-boundary pairs retained for prioritized education."},
    "boundary_prioritized_relax_candidate_filter": {"flag": "--boundary_prioritized_relax_candidate_filter", "type": "bool", "category": "Tabu & boundary education", "label": "Relax boundary candidate filter", "description": "Allow broader candidate scans in prioritized boundary education."},

    # Time-window penalty dynamics
    "tw_time_warp_penalty_min": {"flag": "--tw_time_warp_penalty_min", "type": "float", "min": 0.0, "max": 1000000000.0, "step": 1.0, "category": "Time-window penalty dynamics", "label": "Time-warp penalty min", "description": "Lower bound for adaptive time-warp penalties."},
    "tw_time_warp_penalty_max": {"flag": "--tw_time_warp_penalty_max", "type": "float", "min": 0.0, "max": 1000000000.0, "step": 1.0, "category": "Time-window penalty dynamics", "label": "Time-warp penalty max", "description": "Upper bound for adaptive time-warp penalties."},
    "tw_time_warp_growth": {"flag": "--tw_time_warp_growth", "type": "float", "min": 0.0, "max": 100.0, "step": 0.01, "category": "Time-window penalty dynamics", "label": "Time-warp growth", "description": "Adaptive time-warp penalty growth factor."},
    "tw_lateness_eps": {"flag": "--tw_lateness_eps", "type": "float", "min": 0.0, "max": 3600.0, "step": 0.001, "category": "Time-window penalty dynamics", "label": "TW lateness epsilon", "description": "Tolerance used by final time-window lateness checks."},
}




# Operational size bands define only the application-level runtime envelope.
# FleetRoute deliberately leaves internal search scheduling to the optimizer.
# These bands govern stage display timing, no-improve patience, and a conservative
# worker ceiling; they do not inject hidden neighborhood/operator tuning.
DYNAMIC_SOLVER_TIERS: tuple[dict[str, Any], ...] = (
    {"customers": 10, "stage_time_s": 4, "patience_s": 10, "max_instances": 6, "source": "adaptive_10", "tuning": {}},
    {"customers": 15, "stage_time_s": 4, "patience_s": 10, "max_instances": 6, "source": "adaptive_15", "tuning": {}},
    {"customers": 20, "stage_time_s": 4, "patience_s": 15, "max_instances": 6, "source": "adaptive_20", "tuning": {}},
    {"customers": 50, "stage_time_s": 6, "patience_s": 20, "max_instances": 6, "source": "adaptive_50", "tuning": {}},
    {"customers": 100, "stage_time_s": 8, "patience_s": 30, "max_instances": 6, "source": "adaptive_100", "tuning": {}},
    {"customers": 300, "stage_time_s": 10, "patience_s": 45, "max_instances": 6, "source": "adaptive_300", "tuning": {}},
    {"customers": 450, "stage_time_s": 10, "patience_s": 60, "max_instances": 6, "source": "adaptive_450", "tuning": {}},
)


def dynamic_solver_policy(customer_count: int, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve FleetRoute's production routing envelope.

    The application owns lifecycle, operational semantics, validation, and
    evidence. The optimizer owns its internal search schedule. Advanced values
    are explicit research-mode overrides only.
    """
    cfg = dict(config or {})
    customers = max(1, int(customer_count or 1))
    tier = next(
        (item for item in DYNAMIC_SOLVER_TIERS if customers <= int(item["customers"])),
        DYNAMIC_SOLVER_TIERS[-1],
    )
    runtime_s = max(5, min(7200, int(cfg.get("hard_time_limit_s", 30))))
    requested_instances = max(1, min(32, int(cfg.get("instances", 6))))
    instance_cap = int(tier["max_instances"])
    effective_instances = min(requested_instances, instance_cap)
    base_patience_s = int(tier["patience_s"])
    # Half-up 50% keeps browser/backend behavior deterministic for odd budgets.
    runtime_patience_cap_s = max(5, (runtime_s + 1) // 2)
    no_improve_s = min(base_patience_s, runtime_patience_cap_s)
    overrides = _clean_advanced_solver_settings(cfg.get("advanced", {}))
    tuning: dict[str, Any] = dict(overrides)
    return {
        "mode": "adaptive_routing",
        "optimizer_generation": "FleetRoute Optimizer",
        "customer_count": customers,
        "tier_customers": int(tier["customers"]),
        "tier_label": f"≤ {int(tier['customers'])} work points" + (" · upper band" if int(tier["customers"]) == 450 else ""),
        "benchmark_source": str(tier["source"]),  # compatibility field for older cached frontends
        "heavy": int(tier["customers"]) == 450,
        "above_supplied_range": customers > int(DYNAMIC_SOLVER_TIERS[-1]["customers"]),
        "runtime_s": runtime_s,
        "stage_time_s": int(tier["stage_time_s"]),
        "base_no_improve_s": base_patience_s,
        "runtime_patience_cap_s": runtime_patience_cap_s,
        "no_improve_stop_s": no_improve_s,
        "requested_instances": requested_instances,
        "instance_cap": instance_cap,
        "effective_instances": effective_instances,
        "budget_scope": "solve",
        "phase_engine": True,
        "convergence_sample_period_s": 0.50,
        "convergence_max_rows": 80000,
        "policy_ownership": {
            "application": ["objective", "runtime", "workers", "constraints", "warm-start validation", "evidence"],
            "optimizer": ["search schedule", "neighborhoods", "incumbent search"],
        },
        "advanced_override_count": len(overrides),
        "advanced_overrides": overrides,
        "tuning": tuning,
        "selection_rule": "smallest operational size band covering the live work-point count; above 450 reuses the upper safety band",
        "patience_rule": "min(size-band patience, max(5 seconds, half-up 50% of selected runtime))",
    }


def solver_advanced_schema() -> dict[str, Any]:
    schema = _solver_flag_schema()
    fields = []
    if RESEARCH_SOLVER_OVERRIDES_ENABLED:
        for key, spec in ADVANCED_SOLVER_SPECS.items():
            if spec["flag"] in schema:
                fields.append({"key": key, **spec})
    categories: list[str] = []
    for field in fields:
        if field["category"] not in categories:
            categories.append(field["category"])
    tier_defaults: dict[str, dict[str, Any]] = {}
    tier_summaries = []
    for tier in DYNAMIC_SOLVER_TIERS:
        key = str(tier["customers"])
        values = {"time_limit": int(tier["stage_time_s"]), **dict(tier["tuning"])}
        tier_defaults[key] = {
            field["key"]: values[field["key"]]
            for field in fields
            if field["key"] in values
        }
        tier_summaries.append({
            "customers": int(tier["customers"]),
            "label": (
                "450-customer heavy tier · fallback above 450"
                if int(tier["customers"]) == 450
                else f"≤ {int(tier['customers'])} work points"
            ),
            "stage_time_s": int(tier["stage_time_s"]),
            "base_no_improve_s": int(tier["patience_s"]),
            "instance_cap": int(tier["max_instances"]),
            "benchmark_source": str(tier["source"]),
            "optimizer_generation": "FleetRoute Optimizer",
            "phase_engine": True,
            "budget_scope": "solve",
        })
    return {
        "fields": fields,
        "categories": categories,
        "count": len(fields),
        "enabled": RESEARCH_SOLVER_OVERRIDES_ENABLED,
        "production_locked": not RESEARCH_SOLVER_OVERRIDES_ENABLED,
        "mode": "adaptive_routing",
        "tier_defaults": tier_defaults,
        "tiers": tier_summaries,
        # Kept as a harmless compatibility shape for older cached frontends.
        "profile_defaults": {"auto_dynamic": {}},
    }


def _clean_advanced_solver_settings(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not RESEARCH_SOLVER_OVERRIDES_ENABLED:
        return {}
    if not isinstance(value, dict):
        raise ValueError("solver.advanced must be an object")
    cleaned: dict[str, Any] = {}
    schema = _solver_flag_schema()
    for key, raw in value.items():
        if raw is None or raw == "":
            continue
        spec = ADVANCED_SOLVER_SPECS.get(str(key))
        if not spec:
            raise ValueError(f"Unknown advanced solver setting: {key}")
        if spec["flag"] not in schema:
            raise ValueError(f"Bundled solver does not recognize {spec['flag']}")
        kind = spec["type"]
        if kind == "bool":
            if isinstance(raw, bool):
                parsed = raw
            elif str(raw).strip().lower() in {"true", "1", "yes", "on"}:
                parsed = True
            elif str(raw).strip().lower() in {"false", "0", "no", "off"}:
                parsed = False
            else:
                raise ValueError(f"{key} must be true or false")
        elif kind == "int":
            parsed = int(raw)
        elif kind == "float":
            parsed = float(raw)
            if not math.isfinite(parsed):
                raise ValueError(f"{key} must be finite")
        else:
            raise ValueError(f"Unsupported advanced setting type for {key}")
        if kind in {"int", "float"}:
            if spec.get("min") is not None and parsed < spec["min"]:
                raise ValueError(f"{key} must be >= {spec['min']}")
            if spec.get("max") is not None and parsed > spec["max"]:
                raise ValueError(f"{key} must be <= {spec['max']}")
        cleaned[str(key)] = parsed
    return cleaned


def _advanced_solver_tokens(value: Any) -> list[str]:
    cleaned = _clean_advanced_solver_settings(value)
    tokens: list[str] = []
    for key, parsed in cleaned.items():
        spec = ADVANCED_SOLVER_SPECS[key]
        tokens.extend([spec["flag"], ("true" if parsed else "false") if spec["type"] == "bool" else str(parsed)])
    return tokens


def validate_extra_solver_args(value: str | list[str] | None) -> dict[str, Any]:
    if value is None:
        return {"tokens": [], "text": "", "overrides": [], "warnings": []}
    if isinstance(value, list):
        tokens = [str(x) for x in value]
        text = shlex.join(tokens)
    else:
        text = str(value).strip()
        tokens = shlex.split(text) if text else []
    if tokens and not RESEARCH_SOLVER_OVERRIDES_ENABLED:
        raise ValueError("Raw solver overrides are disabled in production mode. Set VRP_ENABLE_RESEARCH_SOLVER_OVERRIDES=1 only for controlled research runs.")
    forbidden_tokens = {"<", ">", ">>", "|", "||", "&&", ";", "`"}
    if any(token in forbidden_tokens or "\n" in token or "\r" in token for token in tokens):
        raise ValueError("Extra solver arguments must contain flags only; shell redirection is managed by FleetRoute")
    schema = _solver_flag_schema()
    # These flags define FleetRoute's execution contract. Allowing a raw extra
    # argument to repeat one of them is dangerous because the bundled C++ parser
    # uses the last occurrence. A user could visibly select a 170 s budget while
    # a hidden extra flag silently changes it later in argv. Search/operator
    # tuning remains available through extra_args; lifecycle and I/O controls do not.
    protected = {
        "--clusters_csv", "--run_summary_csv", "--coords_csv",
        "--seed", "--instances", "--objective_mode", "--time_limit",
        "--hard_time_limit_s", "--no_improve_stop_s",
        "--target_no_improve_stop_s", "--target_objective",
        "--use_time_window", "--route_start_time_s", "--route_start_hour",
        "--allow_multi_trip", "--max_trips_per_truck",
        "--w_wait", "--tw_penalize_waiting_in_distance",
        "--metric", "--metric_mode", "--budget_scope", "--use_phase_specialized_engine",
        "--hybrid_fast_phase_s", "--log_convergence", "--convergence_sample_period_s",
        "--convergence_max_rows",
    } | {spec["flag"] for spec in ADVANCED_SOLVER_SPECS.values()}
    overrides: list[str] = []
    warnings: list[str] = []
    i = 0
    while i < len(tokens):
        flag = tokens[i]
        if not flag.startswith("--"):
            raise ValueError(f"Expected a solver flag at token {i + 1}: {flag}")
        if flag not in schema:
            raise ValueError(f"Unknown solver flag: {flag}")
        if flag in protected:
            raise ValueError(f"FleetRoute manages {flag}; it cannot be overridden")
        overrides.append(flag)
        if schema[flag]["takes_value"]:
            if i + 1 >= len(tokens) or tokens[i + 1].startswith("--"):
                raise ValueError(f"{flag} requires a value")
            i += 2
        else:
            i += 1
    if len(tokens) > 180:
        raise ValueError("Too many extra solver arguments")
    return {"tokens": tokens, "text": text, "overrides": overrides, "warnings": warnings}


def solver_command_preview(config: dict[str, Any] | None = None, clustering_used: bool = False) -> dict[str, Any]:
    cfg = dict(get_setting("solver") or {})
    customer_count: int | None = None
    if config:
        supplied = config.get("solver") if isinstance(config.get("solver"), dict) else config
        cfg.update(supplied)
        raw_count = config.get("customer_count") if isinstance(config, dict) else None
        if raw_count is None and isinstance(supplied, dict):
            raw_count = supplied.get("customer_count")
        if raw_count is not None:
            customer_count = int(raw_count)
    if customer_count is None:
        customer_count = sum(1 for place in list_places() if place.get("role") == "customer")
    cluster = {"used": bool(clustering_used)}
    policy = dynamic_solver_policy(max(1, customer_count), cfg)
    command = _solver_command(cfg, cluster, customer_count=max(1, customer_count))
    return {
        "argv": command,
        "display": shlex.join(command) + " < " + shlex.quote(str(settings.input_txt)),
        "input_path": str(settings.input_txt),
        "known_flag_count": len(_solver_flag_schema()),
        "extra": validate_extra_solver_args(cfg.get("extra_args", "")),
        "dynamic_policy": policy,
    }


def _ensure_operational_idle(requested: str) -> None:
    active = list_active_jobs(include_evidence=False)
    if not active:
        return
    job = active[0]
    raise ValueError(
        f"Operational job #{job['id']} ({job['kind']}) is already {job['status']}: "
        f"{job.get('message') or 'working'}. Wait for it or cancel it before {requested}."
    )


def _create_operational_job(kind: str, message: str, requested: str) -> int:
    """Atomically reserve the single operational-job slot.

    ``_ensure_operational_idle`` by itself is only a snapshot.  This helper
    closes the check/create race so concurrent double-clicks, duplicate mobile
    requests, or two open FleetRoute tabs cannot start conflicting mutations.
    Evidence/post-processing jobs remain intentionally outside this slot.
    """
    with _OPERATION_QUEUE_LOCK:
        _ensure_operational_idle(requested)
        return create_job(kind, message)


def _import_osmnx():
    try:
        import osmnx as ox
    except ImportError as exc:
        raise RuntimeError("OSMnx is not installed. Run the installer cell again.") from exc
    return ox


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _clean_name(value: Any, fallback: str = "Unnamed road") -> str:
    if isinstance(value, list):
        value = " / ".join(str(item) for item in value if item)
    text = str(value or "").strip()
    return text or fallback


def _clean_highway(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "unclassified")


def _edge_geometry(graph, u: Any, v: Any, data: dict[str, Any]) -> list[list[float]]:
    geom = data.get("geometry")
    if geom is not None and hasattr(geom, "coords"):
        return [[float(y), float(x)] for x, y in geom.coords]
    return [
        [float(graph.nodes[u]["y"]), float(graph.nodes[u]["x"])],
        [float(graph.nodes[v]["y"]), float(graph.nodes[v]["x"])],
    ]


def _nearest_point_on_edge(lat: float, lon: float, geometry: list[list[float]]) -> tuple[float, float, float]:
    line = LineString([(float(p[1]), float(p[0])) for p in geometry])
    target = Point(float(lon), float(lat))
    nearest = nearest_points(line, target)[0]
    snapped_lat, snapped_lon = float(nearest.y), float(nearest.x)
    return snapped_lat, snapped_lon, haversine_m(lat, lon, snapped_lat, snapped_lon)


def _edge_preview_from_graph(graph, lat: float, lon: float, source: str) -> dict[str, Any]:
    # The active graph has a persistent metric STRtree/KD-tree index. This path
    # is normally sub-50ms and never reparses GraphML or rebuilds an OSMnx index.
    try:
        active = GRAPH_STORE.get_graph()
        if graph is active:
            result = GRAPH_STORE.nearest_edge(float(lat), float(lon))
            result["source"] = source
            return result
    except Exception:
        pass

    # Compatibility fallback for synthetic/test graphs that are not the active store.
    ox = _import_osmnx()
    edge_id = ox.distance.nearest_edges(graph, X=float(lon), Y=float(lat))
    if not isinstance(edge_id, tuple) or len(edge_id) != 3:
        raise ValueError("No drivable road segment could be identified near this point")
    u, v, key = edge_id
    data = graph.get_edge_data(u, v, key) or {}
    geometry = _edge_geometry(graph, u, v, data)
    snap_lat, snap_lon, snap_distance = _nearest_point_on_edge(lat, lon, geometry)
    access_node = u
    return {
        "source": source, "road_name": _clean_name(data.get("name")),
        "highway": _clean_highway(data.get("highway")), "oneway": osm_bool(data.get("oneway")),
        "direction_text": "one-way" if osm_bool(data.get("oneway")) else "two-way road record",
        "osm_u": str(u), "osm_v": str(v), "osm_key": str(key),
        "access_osm_node": str(access_node), "snap_lat": snap_lat, "snap_lon": snap_lon,
        "snap_distance_m": float(snap_distance), "geometry": geometry,
        "maxspeed": data.get("maxspeed", ""), "lanes": data.get("lanes", ""),
    }



_COORD_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"


def _coordinate_search_result(query: str) -> dict[str, Any] | None:
    """Parse an explicit coordinate search without calling the external geocoder.

    Supported user-facing forms:
      * ``lat, lon`` (the documented/default order)
      * ``lat: 13.7, lon: 100.5`` / ``latitude ... longitude ...``
      * ``lon: 100.5, lat: 13.7``
      * raw ``lon, lat`` only when the first value cannot be a latitude
        (|first| > 90), which makes the order unambiguous.

    Ambiguous unlabeled pairs are deliberately interpreted as ``lat, lon`` so
    FleetRoute never silently swaps two valid latitude-range numbers.
    """
    q = " ".join(str(query or "").strip().split())
    if not q:
        return None
    flags = re.IGNORECASE
    lat_match = re.search(rf"\b(?:lat|latitude)\s*[:=]?\s*({_COORD_NUMBER})", q, flags)
    lon_match = re.search(rf"\b(?:lon|lng|longitude)\s*[:=]?\s*({_COORD_NUMBER})", q, flags)
    order = "labeled"
    if lat_match and lon_match:
        lat = float(lat_match.group(1)); lon = float(lon_match.group(1))
    else:
        stripped = q.strip().strip("()[]{}")
        match = re.fullmatch(rf"\s*({_COORD_NUMBER})\s*,\s*({_COORD_NUMBER})\s*", stripped)
        if not match:
            return None
        first, second = float(match.group(1)), float(match.group(2))
        if abs(first) > 90 and abs(first) <= 180 and abs(second) <= 90:
            lon, lat = first, second
            order = "lon_lat_unambiguous"
        else:
            lat, lon = first, second
            order = "lat_lon"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(
            "Coordinate search is outside valid latitude/longitude ranges. Use decimal degrees as 'lat, lon'."
        )
    label = f"{lat:.6f}, {lon:.6f}"
    return {
        "external_id": f"coordinate:{lat:.7f},{lon:.7f}",
        "name": f"Coordinates {label}",
        "display_name": f"Decimal coordinates · {label}",
        "lat": lat,
        "lon": lon,
        "type": "coordinates",
        "category": "coordinate",
        "country_code": "",
        "country": "",
        "state": "",
        "boundingbox": [],
        "coordinate_input_order": order,
    }

def geocode_search(query: str, limit: int = 7) -> list[dict[str, Any]]:
    query = " ".join(query.strip().split())
    coordinate = _coordinate_search_result(query)
    if coordinate is not None:
        log_event("geocode.coordinate", {"lat": coordinate["lat"], "lon": coordinate["lon"], "input_order": coordinate["coordinate_input_order"]}, "dispatcher")
        return [coordinate]
    if len(query) < 3:
        raise ValueError("Enter at least 3 characters, or decimal coordinates as 'lat, lon', then press Search")
    requested_limit = max(1, min(int(limit), 10))
    cache_key = f"{query.casefold()}|{requested_limit}"
    with connect() as conn:
        row = conn.execute("SELECT response_json FROM geocode_cache WHERE query=?", (cache_key,)).fetchone()
    if row:
        return json.loads(row["response_json"])

    global _LAST_GEOCODER_AT
    with _GEOCODER_LOCK:
        delay = settings.geocoder_min_interval_s - (time.monotonic() - _LAST_GEOCODER_AT)
        if delay > 0:
            time.sleep(delay)
        headers = {"User-Agent": settings.geocoder_user_agent, "Accept": "application/json"}
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": requested_limit,
            "addressdetails": 1,
            "namedetails": 1,
        }
        with httpx.Client(timeout=httpx.Timeout(12.0, connect=5.0, read=10.0, write=5.0, pool=5.0), follow_redirects=True) as client:
            response = client.get(settings.geocoder_url, params=params, headers=headers)
            response.raise_for_status()
            raw = response.json()
        _LAST_GEOCODER_AT = time.monotonic()

    results = []
    for item in raw:
        try:
            bbox = [float(x) for x in item.get("boundingbox", [])]
            results.append({
                "external_id": f"{item.get('osm_type','')}:{item.get('osm_id','')}",
                "name": item.get("name") or item.get("display_name", "").split(",")[0],
                "display_name": item.get("display_name", ""),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
                "type": item.get("type", ""),
                "category": item.get("category", ""),
                "country_code": str((item.get("address") or {}).get("country_code") or "").upper(),
                "country": str((item.get("address") or {}).get("country") or ""),
                "state": str((item.get("address") or {}).get("state") or ""),
                "boundingbox": bbox,
            })
        except (KeyError, TypeError, ValueError):
            continue
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO geocode_cache(query,response_json,cached_at) VALUES(?,?,?)",
            (cache_key, json.dumps(results, ensure_ascii=False), utc_now()),
        )
    log_event("geocode.search", {"query": query, "result_count": len(results)}, "dispatcher")
    return results


def _mark_network_stale(reason: str, place_id: int | None = None) -> None:
    payload: dict[str, Any] = {"stale": True, "changed_at": utc_now(), "reason": reason}
    if place_id is not None:
        payload["place_id"] = int(place_id)
    set_setting("network_stale", payload)


def _plan_points(places: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    source = places if places is not None else list_places()
    points: list[dict[str, Any]] = []
    for item in source:
        if item.get("role") not in {"depot", "customer", "candidate"}:
            continue
        try:
            lat = float(item.get("lat")); lon = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        points.append({
            "id": item.get("id"), "role": item.get("role"), "name": item.get("name"),
            "lat": lat, "lon": lon,
        })
    return points


def active_source_coverage(
    places: list[dict[str, Any]] | None = None,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = source if source is not None else region_source_status(False)
    region = source.get("region") or {}
    points = _plan_points(places)
    if not source.get("ready") or not region.get("id"):
        return {
            "known": True, "covers_all": False, "outside_count": len(points),
            "outside": points[:20], "point_count": len(points),
            "region_id": region.get("id"), "source_ready": False,
        }
    result = region_points_coverage(str(region["id"]), points)
    result["source_ready"] = True
    result["region_name"] = region.get("name") or region.get("id")
    return result


def _source_coverage_error(source: dict[str, Any], coverage: dict[str, Any], action: str) -> str:
    region = source.get("region") or {}
    name = str(region.get("name") or region.get("id") or "active road source")
    outside = coverage.get("outside") or []
    depot_outside = any(item.get("role") == "depot" for item in outside)
    first = next((item for item in outside if item.get("name")), None)
    detail = ""
    if depot_outside:
        detail = " The depot is outside this extract."
    elif first:
        detail = f" Planned work point '{first.get('name')}' is outside this extract."
    return (
        f"{action} cannot use the active road source '{name}'.{detail} "
        "Browse/download a Geofabrik extract that geometrically covers the depot and every planned work point, "
        "then explicitly use that verified source."
    )


def require_active_source_covers(
    places: list[dict[str, Any]] | None = None,
    *,
    action: str = "This operation",
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = source if source is not None else region_source_status(False)
    if not source.get("ready"):
        raise ValueError("No verified active regional road source is ready. Browse/download a road source, then use it for this plan.")
    coverage = active_source_coverage(places, source)
    # Checksum verification proves source-byte integrity, not geographic fit.
    # Once a real plan exists, require positive boundary evidence before roads
    # can be prepared so a stale/different regional extract cannot slip through
    # merely because the boundary catalog is temporarily unavailable.
    if int(coverage.get("point_count") or 0) > 0 and not coverage.get("known"):
        raise ValueError(
            f"{action} cannot verify that the active regional road source covers the current plan. "
            "Refresh Road-source setup (or reselect the verified region) so its boundary can be validated before preparing roads."
        )
    if coverage.get("known") and coverage.get("covers_all") is False:
        raise ValueError(_source_coverage_error(source, coverage, action))
    return coverage


def plan_distance_check(
    places: list[dict[str, Any]] | None = None,
    fleet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    points = places if places is not None else list_places()
    depot = next((item for item in points if item.get("role") == "depot"), None)
    customers = [item for item in points if item.get("role") == "customer"]
    fleet = fleet if fleet is not None else (get_setting("fleet") or {})
    radius_m = max(0.0, float(fleet.get("operating_radius_m") or 8000.0))
    warning_m = max(20_000.0, 1.75 * radius_m)
    severe_m = max(60_000.0, 3.0 * radius_m)
    if not depot or not customers:
        return {
            "available": False, "warning": False, "severe": False,
            "warning_threshold_m": warning_m, "severe_threshold_m": severe_m,
            "far_count": 0, "severe_count": 0, "farthest_m": 0.0, "farthest": None,
        }

    def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6_371_008.8
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = p2 - p1; dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(min(1.0, math.sqrt(max(0.0, a))))

    # This runs on every lightweight /api/state refresh, so keep it O(n).
    # We only need counts, the farthest point, and a handful of examples; sorting
    # every customer by distance adds needless O(n log n) work for 300–450 stops.
    far_count = 0
    severe_count = 0
    farthest_d = -1.0
    farthest_item: dict[str, Any] | None = None
    far_examples: list[tuple[float, dict[str, Any]]] = []
    depot_lat, depot_lon = float(depot["lat"]), float(depot["lon"])
    for item in customers:
        distance = haversine_m(depot_lat, depot_lon, float(item["lat"]), float(item["lon"]))
        if distance > farthest_d:
            farthest_d, farthest_item = distance, item
        if distance > warning_m:
            far_count += 1
            if len(far_examples) < 5:
                far_examples.append((distance, item))
        if distance > severe_m:
            severe_count += 1
    if farthest_item is None:
        return {
            "available": False, "warning": False, "severe": False,
            "warning_threshold_m": warning_m, "severe_threshold_m": severe_m,
            "far_count": 0, "severe_count": 0, "farthest_m": 0.0, "farthest": None,
        }
    return {
        "available": True,
        "warning": far_count > 0,
        "severe": severe_count > 0,
        "warning_threshold_m": warning_m,
        "severe_threshold_m": severe_m,
        "far_count": far_count,
        "severe_count": severe_count,
        "farthest_m": farthest_d,
        "farthest": {
            "id": farthest_item.get("id"), "name": farthest_item.get("name"),
            "lat": farthest_item.get("lat"), "lon": farthest_item.get("lon"),
        },
        "examples": [
            {"id": item.get("id"), "name": item.get("name"), "distance_m": distance}
            for distance, item in far_examples
        ],
    }


def _active_source_identity(source: dict[str, Any] | None = None) -> tuple[str, str, str, int]:
    source = source if source is not None else region_source_status(False)
    region = source.get("region") or {}
    return (
        str(region.get("id") or ""),
        str(source.get("verified_md5") or ""),
        str(source.get("source_timestamp") or ""),
        int(source.get("size_bytes") or 0),
    )


def _invalidate_active_source_derivatives(reason: str, actor: str = "system") -> None:
    GRAPH_STORE.invalidate()
    for path in (settings.network_pickle, settings.network_graphml):
        path.unlink(missing_ok=True)
    set_setting("network_summary", None)
    _mark_network_stale(reason)
    _mark_routes_stale(reason, actor)


def _activate_region_source_internal(
    region_id: str,
    *,
    actor: str = "system",
    invalidate: bool = True,
) -> dict[str, Any]:
    rid = str(region_id or "").strip().lower()
    library = {str(item.get("id") or ""): item for item in osm_source_library() if item.get("ready")}
    if rid not in library:
        raise ValueError("Download and checksum-verify this regional road source before using it")
    plan_points = _plan_points()
    coverage = region_points_coverage(rid, plan_points)
    if plan_points and not coverage.get("known"):
        raise ValueError(
            "Source activation is blocked because FleetRoute cannot verify that this region covers the current depot/work points. "
            "Refresh Road-source setup and select the region again before activation."
        )
    if coverage.get("known") and coverage.get("covers_all") is False:
        fake_source = {"region": {"id": rid, "name": library[rid].get("name") or rid}}
        raise ValueError(_source_coverage_error(fake_source, coverage, "Source activation"))
    before = _active_source_identity()
    status = set_active_osm_region(rid)
    after = _active_source_identity(status)
    if invalidate and before != after:
        _invalidate_active_source_derivatives("active regional road source changed", actor)
    log_event("osm.source.activated", {
        "region_id": rid,
        "previous_region_id": before[0] or None,
        "verified_md5": status.get("verified_md5"),
        "coverage": coverage,
        "derived_state_invalidated": bool(invalidate and before != after),
    }, actor)
    return {**status, "coverage": coverage}


def activate_region_source(region_id: str) -> dict[str, Any]:
    """Explicitly activate one verified cached source for the current plan."""
    with _OPERATION_QUEUE_LOCK:
        _ensure_operational_idle("changing the active regional road source")
        return _activate_region_source_internal(region_id, actor="dispatcher", invalidate=True)


def list_places() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM places WHERE active=1 ORDER BY CASE role WHEN 'depot' THEN 0 ELSE 1 END, id"
        ).fetchall()
    return [dict(row) for row in rows]


def preview_road_access(lat: float, lon: float, max_snap_m: float | None = None) -> dict[str, Any]:
    """Validate a real destination against the saved round-trip operating graph.

    This deliberately never performs a per-click Overpass request. A verified
    regional PBF is prepared once, then an operating graph is extracted locally.
    """
    lat, lon = float(lat), float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Invalid latitude/longitude")
    fleet = get_setting("fleet") or {}
    max_snap = float(max_snap_m or fleet.get("snap_max_m", 350))
    stale_info = get_setting("network_stale") or {"stale": False}
    if not GRAPH_STORE.available() or bool(stale_info.get("stale")):
        return {
            "valid": False,
            "needs_operating_graph": True,
            "reason": "operating_graph_stale" if GRAPH_STORE.available() else "operating_graph_missing",
            "message": (
                "Refresh the offline operating road area before validating destinations."
                if GRAPH_STORE.available()
                else "Prepare the offline operating road area after choosing the depot."
            ),
            "max_snap_m": max_snap,
            "destination": {"lat": lat, "lon": lon},
            "network_stale": stale_info,
        }
    graph = load_base_graph()
    preview = _edge_preview_from_graph(graph, lat, lon, "Regional offline operating graph")
    preview["max_snap_m"] = max_snap
    preview["round_trip_reachable"] = True  # graph is depot SCC by construction
    preview["valid"] = preview["snap_distance_m"] <= max_snap
    preview["status"] = "ready" if preview["valid"] else "too_far"
    if not preview["valid"]:
        preview["warning"] = (
            f"The nearest round-trip drivable road is {preview['snap_distance_m']:.0f} m away, "
            f"beyond the {max_snap:.0f} m acceptance limit."
        )
    return preview

def prepare_candidate_access(lat: float, lon: float, max_snap_m: float | None = None, progress=None) -> dict[str, Any]:
    """Expand/refresh the local operating graph to include one candidate, then validate it.

    This is the deliberate escape hatch for a searched place outside the current
    operating area. It works entirely from the selected cached regional PBF and never calls
    Overpass. Existing destinations are revalidated against the refreshed depot SCC.
    """
    lat, lon = float(lat), float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Invalid latitude/longitude")
    places = list_places()
    depot = next((p for p in places if p["role"] == "depot"), None)
    if not depot:
        raise ValueError("Choose the depot before preparing road access for customers")
    source = region_source_status(False)
    if not source["ready"]:
        raise ValueError("Choose, download, and use a regional road source before preparing an operating area")
    fleet = get_setting("fleet") or {}
    candidate = {"lat": lat, "lon": lon, "role": "candidate", "name": "Candidate destination"}
    require_active_source_covers([*places, candidate], action="Road-access preparation", source=source)
    radius = float(fleet.get("operating_radius_m", 8000))
    depot_lat = float(depot["lat"]); depot_lon = float(depot["lon"])
    cos_lat = max(.18, math.cos(math.radians(depot_lat)))
    effective_places = [
        *places, candidate,
        {"lat": depot_lat + radius / 111_320, "lon": depot_lon},
        {"lat": depot_lat - radius / 111_320, "lon": depot_lon},
        {"lat": depot_lat, "lon": depot_lon + radius / (111_320 * cos_lat)},
        {"lat": depot_lat, "lon": depot_lon - radius / (111_320 * cos_lat)},
    ]
    metadata = prepare_operating_graph(
        effective_places,
        str(fleet.get("network_type", "drive")),
        float(fleet.get("network_margin_m", 1200)),
        float(depot["lat"]),
        float(depot["lon"]),
        settings.network_graphml,
        progress=progress,
    )
    graph = load_base_graph()
    invalid = _update_all_access_points(graph)
    preview = _edge_preview_from_graph(graph, lat, lon, "Regional offline operating graph")
    max_snap = float(max_snap_m or fleet.get("snap_max_m", 350))
    preview.update({
        "max_snap_m": max_snap,
        "round_trip_reachable": True,
        "valid": preview["snap_distance_m"] <= max_snap,
        "status": "ready" if preview["snap_distance_m"] <= max_snap else "too_far",
        "operating_graph_prepared": True,
        "network": metadata,
        "existing_invalid_access": invalid,
    })
    if not preview["valid"]:
        preview["warning"] = (
            f"The nearest round-trip drivable road is {preview['snap_distance_m']:.0f} m away, "
            f"beyond the {max_snap:.0f} m acceptance limit."
        )
    summary = {
        **metadata,
        "invalid_access": invalid,
        "access_ready": not invalid,
        "overview": "/api/artifacts/artifacts/network_overview.png" if settings.network_overview_png.exists() else None,
        "path": str(settings.network_pickle),
        "built_at": utc_now(),
        "source_ready": True,
        "source_mode": "regional_offline",
    }
    set_setting("network_summary", summary)
    set_setting("network_stale", {"stale": False, "changed_at": utc_now(), "reason": "candidate operating area prepared"})
    log_event("network.candidate.prepared", {"lat": lat, "lon": lon, "valid": preview["valid"], "network": metadata}, "dispatcher")
    return preview


def add_place(payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", "customer"))
    if role not in {"depot", "customer"}:
        raise ValueError("role must be depot or customer")
    now = utc_now()
    name = str(payload.get("name") or "Unnamed stop").strip()
    lat = _finite_float(payload["lat"], name="latitude")
    lon = _finite_float(payload["lon"], name="longitude")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Invalid latitude/longitude")
    demand = 0.0 if role == "depot" else max(0.0, _finite_float(payload.get("demand", 1), name="demand"))
    service_s = 0.0 if role == "depot" else max(0.0, _finite_float(payload.get("service_s", 300), name="service time"))
    earliest_s = 0.0 if role == "depot" else max(0.0, _finite_float(payload.get("earliest_s", 0), name="earliest time"))
    latest_s = 86400.0 if role == "depot" else _finite_float(payload.get("latest_s", 86400), name="latest time")
    if latest_s < earliest_s:
        raise ValueError("latest time must be greater than or equal to earliest time")
    access = payload.get("access") or {}
    verified = bool(access.get("valid") and access.get("round_trip_reachable", True))
    # A depot may be selected before the operating graph exists. Customers entered
    # from map/search must be verified unless explicitly imported as pending.
    if role == "customer" and not verified and not bool(payload.get("allow_pending", False)):
        reason = access.get("warning") or access.get("message") or "Preview and confirm a valid road-access segment first"
        raise ValueError(reason)
    with connect() as conn:
        if role == "depot":
            conn.execute("UPDATE places SET active=0,updated_at=? WHERE role='depot' AND active=1", (now,))
        cur = conn.execute(
            """
            INSERT INTO places(
                role,name,address,lat,lon,demand,service_s,earliest_s,latest_s,external_id,
                access_lat,access_lon,access_road,access_distance_m,access_osm_node,
                access_osm_u,access_osm_v,access_osm_key,access_highway,access_direction,
                access_reachable,access_verified,active,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
            """,
            (
                role, name, str(payload.get("address", "")), lat, lon, demand, service_s,
                earliest_s, latest_s, str(payload.get("external_id", "")),
                access.get("snap_lat"), access.get("snap_lon"), str(access.get("road_name", "")),
                access.get("snap_distance_m"), str(access.get("access_osm_node", "")),
                str(access.get("osm_u", "")), str(access.get("osm_v", "")), str(access.get("osm_key", "")),
                str(access.get("highway", "")), str(access.get("direction_text", "")),
                1 if access.get("round_trip_reachable") else 0, 1 if verified else 0,
                now, now,
            ),
        )
        place_id = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM places WHERE id=?", (place_id,)).fetchone()
    result = dict(row)
    set_setting("plan_revision", {"changed_at": now, "reason": f"{role} added", "place_id": place_id})
    if role == "depot":
        _mark_network_stale("depot changed", place_id)
    elif not verified:
        _mark_network_stale("pending customer requires operating-area refresh", place_id)
    log_event("place.added", {"id": place_id, "role": role, "name": name, "road_access_verified": verified}, "dispatcher")
    _mark_routes_stale(f"{role} added: {name}", "dispatcher")
    return result

def update_place(place_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"name", "address", "demand", "service_s", "earliest_s", "latest_s", "lat", "lon"}
    fields = {k: payload[k] for k in allowed if k in payload}
    if not fields:
        raise ValueError("No editable fields supplied")
    with connect() as conn:
        current = conn.execute("SELECT * FROM places WHERE id=? AND active=1", (place_id,)).fetchone()
    if not current:
        raise ValueError("Place not found")
    numeric_names = {
        "lat": "latitude", "lon": "longitude", "demand": "demand",
        "service_s": "service time", "earliest_s": "earliest time", "latest_s": "latest time",
    }
    for key, label in numeric_names.items():
        if key in fields:
            fields[key] = _finite_float(fields[key], name=label)
    lat = float(fields.get("lat", current["lat"]))
    lon = float(fields.get("lon", current["lon"]))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Invalid latitude/longitude")
    for key in ("demand", "service_s", "earliest_s", "latest_s"):
        if key in fields and fields[key] < 0:
            raise ValueError(f"{numeric_names[key]} must be non-negative")
    earliest = float(fields.get("earliest_s", current["earliest_s"]))
    latest = float(fields.get("latest_s", current["latest_s"]))
    if latest < earliest:
        raise ValueError("latest time must be after earliest time")
    if "lat" in fields or "lon" in fields:
        fields.update({
            "access_lat": None, "access_lon": None, "access_road": "",
            "access_distance_m": None, "access_osm_node": "", "access_osm_u": "",
            "access_osm_v": "", "access_osm_key": "", "access_highway": "",
            "access_direction": "", "access_reachable": 0, "access_verified": 0,
        })
    fields["updated_at"] = utc_now()
    columns = ",".join(f"{k}=?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE places SET {columns} WHERE id=? AND active=1", [*fields.values(), place_id])
        row = conn.execute("SELECT * FROM places WHERE id=?", (place_id,)).fetchone()
    set_setting("plan_revision", {"changed_at": utc_now(), "reason": "place updated", "place_id": place_id})
    if "lat" in payload or "lon" in payload:
        _mark_network_stale("destination coordinates changed", place_id)
    log_event("place.updated", {"id": place_id, "changes": fields}, "dispatcher")
    _mark_routes_stale(f"place updated: {place_id}", "dispatcher")
    return dict(row)


def remove_place(place_id: int) -> None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM places WHERE id=? AND active=1", (place_id,)).fetchone()
        if not row:
            raise ValueError("Place not found")
        conn.execute("UPDATE places SET active=0,updated_at=? WHERE id=?", (utc_now(), place_id))
    set_setting("plan_revision", {"changed_at": utc_now(), "reason": "place removed", "place_id": place_id})
    if row["role"] == "depot":
        _mark_network_stale("depot removed", place_id)
    log_event("place.removed", {"id": place_id, "name": row["name"]}, "dispatcher")
    _mark_routes_stale(f"place removed: {row['name']}", "dispatcher")


def clear_active_places(actor: str = "dispatcher") -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        count = int(conn.execute("SELECT COUNT(*) AS n FROM places WHERE active=1").fetchone()["n"])
        conn.execute("UPDATE places SET active=0,updated_at=? WHERE active=1", (now,))
    _mark_network_stale("plan cleared")
    log_event("plan.cleared", {"removed_places": count}, actor)
    _mark_routes_stale("plan cleared", actor)
    return {"ok": True, "removed_places": count}

def _allocate_integer_demands(
    count: int, target_total: int, demand_min: int, demand_max: int, rng: random.Random
) -> list[int]:
    """Allocate an exact integer fleet load while respecting configured bounds."""
    minimum = count * demand_min
    maximum = count * demand_max
    if target_total < minimum or target_total > maximum:
        raise ValueError(
            f"Target demand {target_total} is incompatible with {count} work points and the "
            f"configured demand range {demand_min}–{demand_max}. The feasible total is "
            f"{minimum}–{maximum}. Adjust utilization, work-point count, or demand range."
        )
    values = [demand_min] * count
    remaining = target_total - minimum
    order = list(range(count))
    rng.shuffle(order)
    while remaining > 0:
        changed = False
        for index in order:
            room = demand_max - values[index]
            if room <= 0:
                continue
            # Small randomized increments keep scenarios varied without losing the
            # exact total utilization contract.
            add = min(room, remaining, rng.randint(1, max(1, min(room, 5))))
            values[index] += add
            remaining -= add
            changed = True
            if remaining <= 0:
                break
        if not changed:
            break
        rng.shuffle(order)
    if remaining != 0:
        raise RuntimeError("Could not allocate the requested scenario demand exactly")
    return values


def _allocate_packable_demands(
    count: int, trucks: int, capacity: float, target_total: int,
    demand_min: int, demand_max: int, rng: random.Random,
) -> tuple[list[int], list[int], list[int]]:
    """Create integer demands with a known capacity-feasible truck partition.

    Total fleet capacity alone does not prove bin-packability. Random scenarios
    therefore allocate each truck bucket independently, then shuffle the orders
    while preserving a hidden planned-truck certificate for the baseline builder.
    """
    trucks = max(1, int(trucks))
    count = max(1, int(count))
    cap = int(math.floor(float(capacity) + 1e-9))
    if cap < 1:
        raise ValueError("Truck capacity must allow at least one integer demand unit")
    base, extra = divmod(count, trucks)
    counts = [base + (1 if index < extra else 0) for index in range(trucks)]
    minimums = [n * demand_min for n in counts]
    maximums = [min(cap, n * demand_max) for n in counts]
    if any(lo > hi for lo, hi in zip(minimums, maximums)):
        raise ValueError("The selected demand range cannot fit the planned work points into each truck capacity")
    if target_total < sum(minimums) or target_total > sum(maximums):
        raise ValueError(
            f"Target demand {target_total} cannot be partitioned across {trucks} trucks; "
            f"the guaranteed packable range is {sum(minimums)}–{sum(maximums)}."
        )
    loads = minimums[:]
    remaining = target_total - sum(loads)
    order = list(range(trucks))
    while remaining > 0:
        rng.shuffle(order)
        changed = False
        for truck_id in order:
            room = maximums[truck_id] - loads[truck_id]
            if room <= 0:
                continue
            add = min(room, remaining, max(1, int(math.ceil(remaining / max(1, trucks)))))
            loads[truck_id] += add
            remaining -= add
            changed = True
            if remaining <= 0:
                break
        if not changed:
            break
    if remaining:
        raise RuntimeError("Could not allocate a capacity-feasible demand plan")
    pairs: list[tuple[int, int]] = []
    for truck_id, (bucket_count, bucket_total) in enumerate(zip(counts, loads)):
        if bucket_count <= 0:
            continue
        bucket = _allocate_integer_demands(bucket_count, bucket_total, demand_min, demand_max, rng)
        pairs.extend((value, truck_id) for value in bucket)
    rng.shuffle(pairs)
    return [value for value, _ in pairs], [truck for _, truck in pairs], loads


def _auto_demand_bounds(count: int, target_total: int, capacity: float) -> tuple[int, int]:
    """Choose a forgiving integer range that can realize the exact target load."""
    if count <= 0:
        raise ValueError("Work-point count must be positive")
    maximum_per_order = max(1, int(math.floor(float(capacity))))
    average = float(target_total) / float(count)
    if average > maximum_per_order + 1e-9:
        raise ValueError(
            f"The target load needs an average demand of {average:.2f} per work point, "
            f"but one work point cannot exceed truck capacity {capacity:g}. Increase the "
            "work-point count, lower utilization, or increase truck capacity."
        )
    low = max(1, int(math.floor(average * 0.50)))
    high = max(low, int(math.ceil(average * 1.60)))
    high = min(maximum_per_order, high)
    if count * low > target_total:
        low = max(1, int(target_total // count))
    if count * high < target_total:
        high = min(maximum_per_order, int(math.ceil(target_total / count)))
    if count * low > target_total or count * high < target_total:
        raise ValueError(
            f"Automatic demand allocation could not represent total demand {target_total} "
            f"for {count} work points within per-work-point capacity {maximum_per_order}."
        )
    return low, high


def _auto_service_bounds(count: int, trucks: int) -> tuple[int, int]:
    stops_per_truck = float(count) / max(1, int(trucks))
    if stops_per_truck <= 12:
        return 5, 12
    if stops_per_truck <= 25:
        return 4, 8
    if stops_per_truck <= 40:
        return 2, 6
    return 1, 4


def _profile_demand_bounds(
    profile: str,
    count: int,
    maximum_trucks: int,
    capacity: float,
) -> tuple[int, int, float]:
    """Return an understandable per-stop demand model.

    ``maximum_trucks`` is an availability ceiling, never a target route count.
    The profile determines customer demand; FleetRoute then reports how many
    trucks the generated load actually needs.
    """
    profile = str(profile or "standard").lower()
    ratios = {
        "light": (0.03, 0.08, 0.055),
        "standard": (0.06, 0.14, 0.10),
        "heavy": (0.12, 0.25, 0.18),
    }
    low_ratio, high_ratio, mean_ratio = ratios.get(profile, ratios["standard"])
    cap = max(1, int(math.floor(float(capacity))))
    maximum_total = max(1, int(math.floor(maximum_trucks * capacity)))
    maximum_average = maximum_total / max(1, count)
    target_mean = min(cap * mean_ratio, maximum_average * 0.82)
    target_mean = max(1.0, target_mean)

    # When many customers share a small maximum fleet, capacity—not the nominal
    # profile ratio—must control the lower bound. The previous formula could
    # produce e.g. minimum demand 6 for 250 customers with only 400 total units,
    # making the scenario impossible before randomization even began.
    nominal_low = cap * low_ratio
    nominal_high = cap * high_ratio
    if maximum_average < nominal_low:
        low = 1
        high = max(1, int(math.floor(maximum_average * 1.45)))
    else:
        low = max(1, int(math.floor(max(target_mean * 0.60, nominal_low))))
        high = max(low, int(math.ceil(min(target_mean * 1.45, nominal_high))))

    high = min(cap, high)
    # The minimum sample itself must fit the fleet. Reduce low rather than
    # presenting a profile-generated configuration that can never be created.
    max_safe_low = max(1, int(math.floor(maximum_total / max(1, count))))
    low = min(low, max_safe_low)
    high = max(low, high)
    return low, high, target_mean


def _first_fit_truck_count(demands: list[int], capacity: float) -> tuple[int, list[float]]:
    """Deterministic first-fit-decreasing capacity certificate."""
    loads: list[float] = []
    for demand in sorted((float(x) for x in demands), reverse=True):
        placed = False
        for index, load in enumerate(loads):
            if load + demand <= capacity + 1e-9:
                loads[index] += demand
                placed = True
                break
        if not placed:
            loads.append(demand)
    return len(loads), loads


def _generate_scenario_demands(
    count: int,
    maximum_trucks: int,
    capacity: float,
    demand_min: int,
    demand_max: int,
    rng: random.Random,
) -> tuple[list[int], int, list[float]]:
    if demand_min < 1 or demand_max < demand_min:
        raise ValueError("Demand range must contain positive integers")
    if demand_max > capacity + 1e-9:
        raise ValueError(f"Maximum customer demand {demand_max} exceeds truck capacity {capacity:g}")
    maximum_total = int(math.floor(maximum_trucks * capacity + 1e-9))
    if count * demand_min > maximum_total:
        raise ValueError(
            f"Even the minimum demand requires {count * demand_min:g} capacity, "
            f"but only {maximum_total:g} is available. Increase maximum trucks/capacity, "
            "reduce customers, or choose a lighter demand profile."
        )
    values = [rng.randint(demand_min, demand_max) for _ in range(count)]
    # Rare upper-tail samples may exceed the available fleet although the profile
    # itself is valid. Reduce the largest orders deterministically instead of
    # producing a surprising failed job.
    excess = sum(values) - maximum_total
    while excess > 0:
        changed = False
        for index in sorted(range(len(values)), key=lambda i: values[i], reverse=True):
            if values[index] <= demand_min:
                continue
            values[index] -= 1
            excess -= 1
            changed = True
            if excess <= 0:
                break
        if not changed:
            raise ValueError("The selected demand model cannot fit inside the available fleet")
    used, loads = _first_fit_truck_count(values, capacity)
    if used > maximum_trucks:
        raise ValueError(
            f"The generated orders require at least {used} trucks, but only {maximum_trucks} are available"
        )
    rng.shuffle(values)
    return values, used, loads


def scenario_contract_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve a simple scenario without converting maximum trucks into a target.

    ``K`` is the maximum available fleet. FleetRoute never creates artificial
    demand or a target-stop rule to force all K routes to be active.
    """
    fleet = get_setting("fleet") or {}
    maximum_trucks = max(1, int(payload.get("trucks") or fleet.get("trucks", 4) or 4))
    capacity = max(1.0, float(payload.get("capacity") or fleet.get("capacity", 100) or 100))
    count = max(3, min(500, int(payload.get("count", 20))))
    demand_mode = str(payload.get("demand_mode", "auto") or "auto").lower()
    demand_profile = str(payload.get("demand_profile", "standard") or "standard").lower()
    if demand_profile not in {"light", "standard", "heavy"}:
        demand_profile = "standard"
    errors: list[str] = []
    warnings: list[str] = []
    if demand_mode == "custom":
        demand_min = max(1, int(payload.get("demand_min", 1)))
        demand_max = max(demand_min, int(payload.get("demand_max", demand_min)))
        mean_demand = (demand_min + demand_max) / 2.0
    else:
        demand_mode = "auto"
        demand_min, demand_max, mean_demand = _profile_demand_bounds(
            demand_profile, count, maximum_trucks, capacity
        )
    maximum_capacity = maximum_trucks * capacity
    minimum_total = count * demand_min
    expected_total = count * mean_demand
    maximum_sample_total = count * demand_max
    if demand_max > capacity + 1e-9:
        errors.append(f"Maximum customer demand {demand_max} exceeds truck capacity {capacity:g}.")
    if minimum_total > maximum_capacity + 1e-9:
        errors.append(
            f"Minimum generated demand {minimum_total:g} exceeds available fleet capacity "
            f"{maximum_capacity:g}."
        )
    expected_total = min(expected_total, maximum_capacity)
    expected_active = max(1, min(maximum_trucks, int(math.ceil(expected_total / capacity))))
    expected_used_util = expected_total / max(1.0, expected_active * capacity)
    available_util = expected_total / max(1.0, maximum_capacity)

    service_mode = str(payload.get("service_mode", "auto") or "auto").lower()
    if service_mode == "custom":
        service_min = max(1, int(payload.get("service_min", 5)))
        service_max = max(service_min, int(payload.get("service_max", 15)))
    else:
        service_mode = "auto"
        service_min, service_max = _auto_service_bounds(count, expected_active)
    time_window_mode = str(payload.get("time_window_mode", "open") or "open").lower()
    if time_window_mode not in {"open", "shift", "staggered"}:
        time_window_mode = "open"
    stops_per_active = count / max(1, expected_active)
    average_service = (service_min + service_max) / 2.0
    estimated_hours = stops_per_active * (average_service + 4.0) / 60.0
    if expected_active >= maximum_trucks and maximum_sample_total > maximum_capacity:
        warnings.append(
            "The demand profile is close to the available-fleet limit; actual orders will be safely capped."
        )
    if stops_per_active > 45:
        warnings.append(f"Stress workload: approximately {stops_per_active:.1f} stops per active truck.")
    elif stops_per_active > 30:
        warnings.append(f"Dense workload: approximately {stops_per_active:.1f} stops per active truck.")
    if time_window_mode != "open" and estimated_hours > 12:
        warnings.append("Service workload is high for constrained time windows.")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "count": count,
        "maximum_trucks": maximum_trucks,
        "resolved_trucks": maximum_trucks,  # compatibility: this is the availability ceiling
        "trucks": maximum_trucks,
        "capacity": capacity,
        "maximum_fleet_capacity": maximum_capacity,
        "demand_mode": demand_mode,
        "demand_profile": demand_profile,
        "resolved_demand_min": demand_min,
        "resolved_demand_max": demand_max,
        "expected_total_demand": round(expected_total, 1),
        "expected_active_trucks": expected_active,
        "available_fleet_utilization_pct": round(available_util * 100.0, 1),
        "expected_used_fleet_utilization_pct": round(expected_used_util * 100.0, 1),
        "service_mode": service_mode,
        "resolved_service_min": service_min,
        "resolved_service_max": service_max,
        "time_window_mode": time_window_mode,
        "stops_per_active_truck": round(stops_per_active, 1),
        "estimated_hours_per_active_truck": round(estimated_hours, 1),
        "risk": "blocked" if errors else "stress" if warnings else "ready",
        "vehicle_semantics": "maximum_available_not_required",
    }

def generate_demo_plan(
    *, count: int = 20, radius_m: float = 4200.0, seed: int = 777,
    center_lat: float | None = None, center_lon: float | None = None,
    replace_customers: bool = True, target_utilization: float = 0.80,
    demand_mode: str = "auto", demand_profile: str = "standard",
    demand_min: int = 4, demand_max: int = 18,
    service_mode: str = "auto", service_min: int = 5, service_max: int = 15,
    time_window_mode: str = "open", fleet_mode: str = "fixed",
    target_stops_per_truck: int = 22, trucks: int | None = None,
    capacity: float | None = None, progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Generate customers on reachable nodes without forcing every available truck.

    Legacy target-utilization/fleet-sizing arguments are accepted for notebook/API
    compatibility but are not used to turn the available fleet into a required
    route count.
    """
    count = max(3, min(500, int(count)))
    radius_m = max(400.0, min(150_000.0, float(radius_m)))
    rng = random.Random(int(seed))
    contract = scenario_contract_preview({
        "count": count,
        "demand_mode": demand_mode,
        "demand_profile": demand_profile,
        "demand_min": demand_min,
        "demand_max": demand_max,
        "service_mode": service_mode,
        "service_min": service_min,
        "service_max": service_max,
        "time_window_mode": time_window_mode,
        "trucks": trucks,
        "capacity": capacity,
    })
    if not contract["ok"]:
        raise ValueError(" ".join(contract["errors"]))
    demand_min = int(contract["resolved_demand_min"])
    demand_max = int(contract["resolved_demand_max"])
    service_min = int(contract["resolved_service_min"])
    service_max = int(contract["resolved_service_max"])
    demand_mode = str(contract["demand_mode"])
    demand_profile = str(contract["demand_profile"])
    service_mode = str(contract["service_mode"])
    time_window_mode = str(contract["time_window_mode"])

    places = list_places()
    depot = next((p for p in places if p["role"] == "depot"), None)
    if depot is None:
        if center_lat is None or center_lon is None:
            raise ValueError("Choose a depot first, or select a point on the map before generating a demo scenario")
        depot = add_place({
            "role": "depot", "name": "FleetRoute Demo Depot",
            "address": "Demo operating center",
            "lat": float(center_lat),
            "lon": float(center_lon),
            "allow_pending": True,
        })
    if not region_source_status(False)["ready"]:
        return {"ok": False, "needs_region_source": True, "depot_id": depot["id"],
                "message": "Depot prepared. Choose and verify an operating-region road source, then continue."}
    stale_info = get_setting("network_stale") or {"stale": False}
    if not GRAPH_STORE.available() or bool(stale_info.get("stale")):
        return {"ok": False, "needs_operating_graph": True, "depot_id": depot["id"],
                "message": "Prepare or restore the fixed operating area before generating work points."}

    graph = load_base_graph()
    depot_node = GRAPH_STORE.nearest_node(float(depot["lat"]), float(depot["lon"]))
    nearby = GRAPH_STORE.nodes_within_radius(
        float(depot["lat"]), float(depot["lon"]), radius_m, limit=max(count * 80, 2000)
    )
    minimum_radius = min(radius_m * 0.12, 600.0)
    candidates = [node for node, distance in nearby if node != depot_node and distance >= minimum_radius]
    if len(candidates) < count:
        candidates = [node for node in graph.nodes if node != depot_node]
    if len(candidates) < count:
        raise ValueError(
            f"The active operating graph has only {len(candidates)} usable work-point road nodes; "
            f"{count} were requested. Prepare a larger area or reduce the work-point count."
        )
    chosen = rng.sample(candidates, count)
    maximum_trucks = max(1, int(contract["maximum_trucks"]))
    capacity = max(1.0, float(contract["capacity"]))
    generated_demands, required_trucks, bucket_loads = _generate_scenario_demands(
        count, maximum_trucks, capacity, demand_min, demand_max, rng
    )
    service_min, service_max = (
        _auto_service_bounds(count, required_trucks)
        if service_mode == "auto" else (service_min, service_max)
    )
    names = [
        "Old Town Market", "Riverside Pharmacy", "Central Café", "Northside Hotel",
        "Community Grocer", "Seaview Clinic", "Marina Supplies", "Tech Park Office",
        "Garden Restaurant", "Hill Residence", "Warehouse Annex", "South Gate Shop",
        "University Building", "Museum Café", "Harbor Service", "Lakeside Apartments",
    ]
    now = utc_now()
    # Resolve expensive road-access evidence before opening the SQLite write
    # transaction. Progress heartbeats also write to SQLite; keeping them outside
    # this transaction prevents self-locking while still preserving all-or-nothing
    # publication of the generated customer rows.
    prepared_rows: list[list[Any]] = []
    columns = [
        "role", "name", "address", "lat", "lon", "demand", "service_s",
        "earliest_s", "latest_s", "external_id", "access_lat", "access_lon",
        "access_road", "access_distance_m", "access_osm_node", "access_osm_u",
        "access_osm_v", "access_osm_key", "access_highway", "access_direction",
        "access_reachable", "access_verified", "active", "created_at", "updated_at",
    ]
    for index, node in enumerate(chosen):
        if progress is not None and (index == 0 or index % max(1, count // 50) == 0):
            progress(index, count, f"Validating customer road access {index}/{count}")
        lat = float(graph.nodes[node]["y"]); lon = float(graph.nodes[node]["x"])
        access = GRAPH_STORE.access_for_node(node)
        service_s = rng.randint(service_min, service_max) * 60
        if time_window_mode == "open":
            earliest_s, latest_s = 0.0, 86400.0
        elif time_window_mode == "shift":
            earliest_s, latest_s = 7.0 * 3600.0, 22.0 * 3600.0
        else:
            start_hour = rng.choice([7, 8, 9, 10, 11]); window_hours = rng.choice([8, 9, 10, 11, 12])
            earliest_s = float(start_hour * 3600); latest_s = float(min(23 * 3600, (start_hour + window_hours) * 3600))
        prepared_rows.append([
            "customer", f"{names[index % len(names)]} · {index + 1:02d}",
            "Generated on a verified round-trip road node", lat, lon,
            float(generated_demands[index]), float(service_s), earliest_s, latest_s,
            f"scenario:{seed}:order:{index}", access["snap_lat"], access["snap_lon"],
            access["road_name"], access["snap_distance_m"], str(access["access_osm_node"]),
            str(access["osm_u"]), str(access["osm_v"]), str(access["osm_key"]),
            access["highway"], access["direction_text"], 1, 1, 1, now, now,
        ])
    if progress is not None:
        progress(count, count, f"Validated customer road access {count}/{count}")

    with connect() as conn:
        if replace_customers:
            conn.execute("UPDATE places SET active=0,updated_at=? WHERE active=1 AND role='customer'", (now,))
        created: list[int] = []
        placeholders = ','.join('?' for _ in columns)
        statement = f"INSERT INTO places({','.join(columns)}) VALUES({placeholders})"
        for values in prepared_rows:
            cur = conn.execute(statement, values)
            created.append(int(cur.lastrowid))

    actual_total = float(sum(generated_demands))
    available_utilization = actual_total / max(1.0, maximum_trucks * capacity)
    used_utilization = actual_total / max(1.0, required_trucks * capacity)
    result = {
        "ok": True, "depot_id": depot["id"], "customer_count": len(created),
        "radius_m": radius_m, "seed": int(seed), "maximum_trucks": maximum_trucks,
        "resolved_trucks": maximum_trucks, "trucks": maximum_trucks, "capacity": capacity, "verified_nodes": True,
        "required_trucks_by_capacity": required_trucks, "estimated_active_trucks": required_trucks,
        "bucket_loads": bucket_loads, "total_demand": actual_total,
        "available_fleet_utilization_pct": round(available_utilization * 100.0, 1),
        "used_fleet_utilization_pct": round(used_utilization * 100.0, 1),
        "demand_mode": demand_mode, "demand_profile": demand_profile,
        "demand_min": min(generated_demands), "demand_max": max(generated_demands),
        "service_mode": service_mode, "service_min": service_min, "service_max": service_max,
        "time_window_mode": time_window_mode, "contract": contract,
        "generation_mode": "in_memory_spatial_index",
        "vehicle_semantics": "maximum_available_not_required",
    }
    set_setting("plan_revision", {"changed_at": now, "reason": "verified scenario generated"})
    set_setting("latest_scenario_contract", {**contract, **{
        "actual_total_demand": actual_total,
        "required_trucks_by_capacity": required_trucks,
        "used_fleet_utilization_pct": result["used_fleet_utilization_pct"],
    }})
    log_event("demo.generated", result, "dispatcher")
    _mark_routes_stale("scenario generated", "dispatcher")
    return result

def _settings_revision() -> dict[str, int]:
    raw = get_setting("settings_revision") or {}
    return {"fleet": int(raw.get("fleet", 0)), "solver": int(raw.get("solver", 0))}


def _strict_bool(value: Any, *, name: str, default: bool) -> bool:
    if value is None or value == "":
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"{name} must be true or false")


def _finite_float(value: Any, *, name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return parsed


def _strict_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a whole number")
    number = _finite_float(value, name=name)
    if not number.is_integer():
        raise ValueError(f"{name} must be a whole number")
    return int(number)


def _save_operating_settings_unlocked(fleet: dict[str, Any], solver: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist the operating contract without destroying unrelated state.

    This is intentionally diff-aware. Search-tuning edits do not make an already
    feasible published route invalid; only fleet feasibility or road-graph inputs do.
    The returned revision is used by the browser draft protocol to prevent SSE/state
    refreshes from overwriting in-progress edits.
    """
    # SettingsPayload is intentionally tolerant of partial dictionaries so CSV/rush
    # workflows and future clients can update one concern without resetting the
    # rest of the operating contract to unrelated fallback values.
    old_fleet = get_setting("fleet") or {}
    old_solver = get_setting("solver") or {}
    fleet = {**old_fleet, **dict(fleet or {})}
    solver = {**old_solver, **dict(solver or {})}

    trucks = _strict_int(fleet.get("trucks", 4), name="trucks")
    capacity = _finite_float(fleet.get("capacity", 100), name="capacity")
    margin = _strict_int(fleet.get("network_margin_m", 1200), name="network_margin_m")
    snap_max = _strict_int(fleet.get("snap_max_m", 350), name="snap_max_m")
    operating_radius = _strict_int(fleet.get("operating_radius_m", 8000), name="operating_radius_m")
    if not 1 <= trucks <= 500: raise ValueError("trucks must be between 1 and 500")
    if capacity <= 0: raise ValueError("capacity must be positive")
    if not 500 <= margin <= 80_000: raise ValueError("network margin must be between 500 and 80,000 m")
    if not 25 <= snap_max <= 2000: raise ValueError("road access limit must be between 25 and 2,000 m")
    if not 2_000 <= operating_radius <= 150_000: raise ValueError("operating radius must be between 2 and 150 km")
    network_type = str(fleet.get("network_type", "drive"))
    if network_type not in {"drive", "drive_service"}: network_type = "drive"
    fleet_clean = {
        "trucks": trucks, "capacity": capacity, "network_type": network_type,
        "network_margin_m": margin, "snap_max_m": snap_max,
        "operating_radius_m": operating_radius, "network_scope": "regional_offline",
    }
    clustering = str(solver.get("clustering", "auto"))
    allowed_clusters = {"none", "auto", "road_savings", "network_kmedoids", "sweep", "round_robin", "road_spectral_sparse", "road_spectral_lite", "balanced_kmeans", "route_split"}
    if clustering not in allowed_clusters: clustering = "auto"
    objective = str(solver.get("objective_mode", "distance"))
    if objective not in {"distance", "time", "hybrid"}:
        raise ValueError("objective_mode must be distance, time, or hybrid")
    advanced = _clean_advanced_solver_settings(solver.get("advanced", {}))
    extra = validate_extra_solver_args(solver.get("extra_args", ""))
    route_start_time_s = _finite_float(solver.get("route_start_time_s", 8 * 3600), name="route_start_time_s")
    if not 0 <= route_start_time_s < 86400:
        raise ValueError("route_start_time_s must be within one day [0, 86400)")
    max_trips_per_truck = max(1, min(12, _strict_int(solver.get("max_trips_per_truck", 3), name="max_trips_per_truck")))
    seed = _strict_int(solver.get("seed", 777), name="seed")
    if not 0 <= seed <= 0xFFFFFFFF:
        raise ValueError("seed must be within the native unsigned 32-bit range [0, 4294967295]")
    solver_clean = {
        "seed": seed,
        "instances": max(1, min(32, _strict_int(solver.get("instances", 6), name="instances"))),
        "hard_time_limit_s": max(5, min(7200, _strict_int(solver.get("hard_time_limit_s", 30), name="hard_time_limit_s"))),
        "objective_mode": objective,
        "use_time_window": _strict_bool(solver.get("use_time_window", True), name="use_time_window", default=True),
        "route_start_time_s": route_start_time_s,
        "allow_multi_trip": _strict_bool(solver.get("allow_multi_trip", False), name="allow_multi_trip", default=False),
        "max_trips_per_truck": max_trips_per_truck,
        "clustering": clustering, "clustering_strict": _strict_bool(solver.get("clustering_strict", False), name="clustering_strict", default=False),
        "run_convergence_analysis": _strict_bool(solver.get("run_convergence_analysis", False), name="run_convergence_analysis", default=False),
        "profile": "auto_dynamic",
        "advanced": advanced,
        "extra_args": extra["text"],
        "extra_overrides": extra["overrides"],
    }
    fleet_changed = old_fleet != fleet_clean
    solver_changed = old_solver != solver_clean
    fleet_changed_keys = sorted(k for k in set(old_fleet) | set(fleet_clean) if old_fleet.get(k) != fleet_clean.get(k))
    solver_changed_keys = sorted(k for k in set(old_solver) | set(solver_clean) if old_solver.get(k) != solver_clean.get(k))
    rev = _settings_revision()
    if fleet_changed:
        set_setting("fleet", fleet_clean)
        rev["fleet"] += 1
    if solver_changed:
        set_setting("solver", solver_clean)
        rev["solver"] += 1
    if fleet_changed or solver_changed:
        set_setting("settings_revision", rev)
        log_event("settings.updated", {
            "fleet_changed": fleet_changed_keys, "solver_changed": solver_changed_keys,
            "fleet": fleet_clean, "solver": solver_clean, "revision": rev,
        }, "dispatcher")

    road_keys = {"network_type", "network_margin_m", "operating_radius_m"}
    if road_keys.intersection(fleet_changed_keys):
        set_setting("network_stale", {"stale": True, "changed_at": utc_now(), "reason": "road settings changed"})
    if "snap_max_m" in fleet_changed_keys:
        # The graph itself is reusable. Tightening the last-meter threshold only
        # invalidates stops whose stored snap distance no longer satisfies it;
        # widening the threshold never destroys already-valid certificates. Any
        # previously pending stop will be retried automatically by Optimize.
        invalidated = 0
        with connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM places WHERE active=1 AND access_verified=1 "
                "AND (access_distance_m IS NULL OR access_distance_m>?)",
                (snap_max,),
            ).fetchone()
            invalidated = int(row["n"] if row else 0)
            if invalidated:
                conn.execute(
                    "UPDATE places SET access_verified=0,updated_at=? WHERE active=1 AND access_verified=1 "
                    "AND (access_distance_m IS NULL OR access_distance_m>?)",
                    (utc_now(), snap_max),
                )
        if invalidated:
            _mark_routes_stale("road-access threshold excludes current stops", "dispatcher")
    # Fleet size and routing semantics change the hard feasibility contract.
    # Search-only tuning remains free to change without invalidating a safe route.
    if {"trucks", "capacity"}.intersection(fleet_changed_keys):
        set_setting("active_input_state", {})
        _mark_routes_stale("fleet feasibility contract changed", "dispatcher")
    # Only settings that can change route feasibility invalidate a published plan.
    # ``objective_mode`` changes how feasible alternatives are ranked, not whether
    # the current published route is safe/feasible, so changing distance/time/hybrid
    # must not disable an otherwise valid driver manifest.
    hard_solver_keys = {
        "use_time_window", "route_start_time_s", "allow_multi_trip", "max_trips_per_truck",
    }
    if hard_solver_keys.intersection(solver_changed_keys):
        set_setting("active_input_state", {})
        _mark_routes_stale("route feasibility semantics changed", "dispatcher")

    return {
        "ok": True, "fleet": fleet_clean, "solver": solver_clean,
        "revision": rev, "changed": {"fleet": fleet_changed_keys, "solver": solver_changed_keys},
    }


def save_operating_settings(fleet: dict[str, Any], solver: dict[str, Any]) -> dict[str, Any]:
    """Serialize partial settings merges so revisions and values stay coherent."""
    with _SETTINGS_UPDATE_LOCK:
        return _save_operating_settings_unlocked(fleet, solver)


def _place_extent(places: list[dict[str, Any]]) -> tuple[tuple[float, float], float]:
    lats = [float(p["lat"]) for p in places]
    lons = [float(p["lon"]) for p in places]
    center = (sum(lats) / len(lats), sum(lons) / len(lons))
    radius = max(haversine_m(center[0], center[1], lat, lon) for lat, lon in zip(lats, lons))
    return center, radius


def _add_speeds(graph):
    """Attach robust OSM speed and travel-time attributes.

    Delegating to the regional-road helper keeps every graph-building path on
    the same country-agnostic policy: explicit OSM maxspeed tags win, missing
    values use highway-class defaults, and sparse-tag extracts receive a safe
    fallback instead of raising.
    """
    return add_edge_speeds_and_times(graph, _import_osmnx())


def _update_access_points(
    graph, *, roles: set[str] | None = None, place_ids: set[int] | None = None
) -> list[dict[str, Any]]:
    """Refresh persisted road-access evidence for selected active places.

    A freshly prepared graph must always validate the depot, even when old
    customers are intentionally ignored because they are about to be replaced.
    Keeping role/id filtering inside this helper prevents the old two-run failure
    where generated customers were valid but the pending depot blocked input.txt.
    """
    fleet = get_setting("fleet") or {}
    max_snap = float(fleet.get("snap_max_m", 350))
    invalid: list[dict[str, Any]] = []
    now = utc_now()
    clauses = ["active=1"]
    params: list[Any] = []
    if roles:
        placeholders = ",".join("?" for _ in roles)
        clauses.append(f"role IN ({placeholders})")
        params.extend(sorted(roles))
    if place_ids:
        placeholders = ",".join("?" for _ in place_ids)
        clauses.append(f"id IN ({placeholders})")
        params.extend(sorted(int(value) for value in place_ids))
    query = "SELECT * FROM places WHERE " + " AND ".join(clauses) + " ORDER BY id"
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
        for row in rows:
            place = dict(row)
            preview = _edge_preview_from_graph(
                graph, float(place["lat"]), float(place["lon"]),
                "Regional offline operating graph",
            )
            valid = preview["snap_distance_m"] <= max_snap
            conn.execute(
                """UPDATE places SET access_lat=?,access_lon=?,access_road=?,access_distance_m=?,
                access_osm_node=?,access_osm_u=?,access_osm_v=?,access_osm_key=?,access_highway=?,
                access_direction=?,access_reachable=1,access_verified=?,updated_at=? WHERE id=?""",
                (
                    preview["snap_lat"], preview["snap_lon"], preview["road_name"],
                    preview["snap_distance_m"], preview["access_osm_node"], preview["osm_u"],
                    preview["osm_v"], preview["osm_key"], preview["highway"],
                    preview["direction_text"], 1 if valid else 0, now, place["id"],
                ),
            )
            if not valid:
                invalid.append({
                    "id": place["id"], "role": place["role"], "name": place["name"],
                    "distance_m": preview["snap_distance_m"], "road_name": preview["road_name"],
                    "suggested_lat": preview["snap_lat"], "suggested_lon": preview["snap_lon"],
                })
    return invalid


def _update_all_access_points(graph) -> list[dict[str, Any]]:
    return _update_access_points(graph)

def build_base_network(
    progress=None,
    include_overview: bool = False,
    include_current_customers: bool = True,
    validate_existing: bool = True,
) -> dict[str, Any]:
    """Prepare the fixed depot-centred operating graph.

    Scenario replacement deliberately excludes the old customer set. Otherwise a
    far-away order that is about to be deleted can force a needless regional
    extraction and make the random-customer button look frozen.
    """
    places = list_places()
    depot = next((p for p in places if p["role"] == "depot"), None)
    if not depot: raise ValueError("Choose a depot first")
    source = region_source_status(False)
    if not source["ready"]:
        raise ValueError("No verified active regional road source is ready. Browse/download a road source, then use it for this plan.")
    coverage_places = places if include_current_customers else [depot]
    require_active_source_covers(coverage_places, action="Operating-graph preparation", source=source)
    fleet = get_setting("fleet") or {}
    # Always prepare one stable depot-centred operating region. Customers inside
    # this circle never invalidate the graph, so adding orders becomes an in-memory
    # nearest-road query rather than another full regional-PBF scan. Customers
    # outside the circle are still included and can trigger an explicit expansion.
    effective_places = list(places if include_current_customers else [depot])
    radius = float(fleet.get("operating_radius_m", 8000))
    lat = float(depot["lat"]); lon = float(depot["lon"])
    cos_lat = max(.18, math.cos(math.radians(lat)))
    effective_places += [
        {"lat": lat + radius / 111_320, "lon": lon},
        {"lat": lat - radius / 111_320, "lon": lon},
        {"lat": lat, "lon": lon + radius / (111_320 * cos_lat)},
        {"lat": lat, "lon": lon - radius / (111_320 * cos_lat)},
    ]
    margin = max(750.0, min(5000.0, float(fleet.get("network_margin_m", 1200))))
    log_event(
        "network.offline.started",
        {
            "places": len(effective_places),
            "source": source["path"],
            "include_current_customers": bool(include_current_customers),
            "validate_existing": bool(validate_existing),
        },
        "dispatcher",
    )
    metadata = prepare_operating_graph(
        effective_places, str(fleet.get("network_type", "drive")), margin,
        float(depot["lat"]), float(depot["lon"]), settings.network_graphml,
        progress=progress,
    )
    graph = load_base_graph()
    # The depot is part of every operational contract and must be refreshed on
    # every graph preparation. Existing customers may be skipped only when the
    # caller is about to replace them.
    invalid = (
        _update_all_access_points(graph)
        if validate_existing
        else _update_access_points(graph, roles={"depot"})
    )
    overview = None
    if include_overview:
        overview = generate_network_overview(graph, list_places(), settings.network_overview_png)
    elif settings.network_overview_png.exists():
        overview = "/api/artifacts/artifacts/network_overview.png"
    summary = {
        **metadata,
        "invalid_access": invalid, "access_ready": not invalid,
        "overview": overview, "path": str(settings.network_pickle), "built_at": utc_now(),
        "source_ready": True, "source_mode": "regional_offline",
    }
    set_setting("network_summary", summary)
    set_setting("network_stale", {"stale": False, "changed_at": utc_now(), "reason": "operating graph prepared"})
    log_event("network.offline.completed", summary, "dispatcher")
    return summary

def load_base_graph():
    return GRAPH_STORE.get_graph()


def network_geojson(max_edges: int = 8_000, detail: str = "balanced") -> dict[str, Any]:
    return GRAPH_STORE.geojson(max_edges=max_edges, detail=detail)


def network_viewport_geojson(
    south: float, west: float, north: float, east: float, max_edges: int = 4_000
) -> dict[str, Any]:
    return GRAPH_STORE.geojson_bbox(south, west, north, east, max_edges=max_edges)


def _approved_closures() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM closures WHERE status='approved' AND (expires_at IS NULL OR expires_at='' OR expires_at>?) ORDER BY id""",
            (now,),
        ).fetchall()
    return [dict(row) for row in rows]


def graph_with_closures():
    base = load_base_graph()
    blocked: set[tuple[Any, Any, Any]] = set()
    removed = []
    for closure in _approved_closures():
        matches = GRAPH_STORE.resolve_edge(closure["osm_u"], closure["osm_v"], closure.get("osm_key"))
        if closure["block_reverse"]:
            # A reverse pair is normally stored under the same MultiDiGraph key.
            # If it is not, choose the single reverse geometry closest to the
            # reported segment. Removing every parallel reverse edge can close a
            # different frontage road that merely shares the same end nodes.
            candidates = GRAPH_STORE.resolve_edge(closure["osm_v"], closure["osm_u"], None)
            reverse = [
                edge for edge in candidates
                if str(edge[2]) == str(closure.get("osm_key"))
            ][:1]
            if not reverse:
                if candidates:
                    try:
                        reported_points = json.loads(closure.get("geometry_json") or "[]")
                        reported_line = LineString([
                            (float(point[1]), float(point[0])) for point in reported_points
                        ])
                        reverse = [min(
                            candidates,
                            key=lambda edge: reported_line.hausdorff_distance(LineString([
                                (float(point[1]), float(point[0]))
                                for point in _edge_geometry(
                                    base, edge[0], edge[1], base.get_edge_data(*edge) or {}
                                )
                            ])),
                        )]
                    except Exception:
                        reverse = candidates[:1]
            matches.extend(reverse[:1])
        for edge in dict.fromkeys(matches):
            blocked.add(edge)
            removed.append((str(edge[0]), str(edge[1]), str(edge[2]), closure["id"]))

    if not blocked:
        return base, removed

    def edge_ok(u: Any, v: Any, key: Any) -> bool:
        return (u, v, key) not in blocked

    return nx.subgraph_view(base, filter_edge=edge_ok), removed


def _safe_speed_kph(data: dict[str, Any]) -> float:
    value = data.get("speed_kph", data.get("speed", 35.0))
    if isinstance(value, list):
        value = value[0] if value else 35.0
    try:
        return max(1.0, float(value))
    except (TypeError, ValueError):
        return 35.0


def _instance_feasibility_diagnostics(
    customers: list[dict[str, Any]],
    customer_places: list[dict[str, Any]],
    trucks: int,
    capacity: float,
    *,
    use_time_window: bool = True,
    allow_multi_trip: bool = False,
    max_trips_per_truck: int = 1,
) -> dict[str, Any]:
    total_demand = float(sum(float(item.get("demand", 0.0)) for item in customers))
    total_service_s = float(sum(float(item.get("service_time_s", 0.0)) for item in customers))
    earliest = min((float(item.get("earliest", 0.0)) for item in customers), default=0.0)
    latest = max((float(item.get("latest", 86400.0)) for item in customers), default=86400.0)
    horizon_s = max(1.0, latest - earliest)
    trip_limit = max(1, int(max_trips_per_truck)) if allow_multi_trip else 1
    total_trip_slots = max(1, trucks) * trip_limit
    required_trips_by_capacity = max(1, int(math.ceil(total_demand / max(1.0, capacity))))
    required_by_capacity = max(
        1,
        min(trucks, int(math.ceil(required_trips_by_capacity / trip_limit))),
    )
    stops_per_truck = len(customers) / required_by_capacity
    service_hours_per_truck = total_service_s / required_by_capacity / 3600.0
    generated = [p for p in customer_places if str(p.get("external_id") or "").startswith("scenario:")]
    impossible = []
    warnings = []
    effective_capacity = trucks * capacity * trip_limit
    if total_demand > effective_capacity + 1e-9:
        impossible.append(
            "Total demand exceeds the fleet's permitted trip capacity"
            if allow_multi_trip else "Total demand exceeds total fleet capacity"
        )
    if any(float(item.get("demand", 0.0)) > capacity + 1e-9 for item in customers):
        impossible.append("At least one customer node exceeds truck capacity")
    for item in customers:
        if use_time_window and float(item.get("service_time_s", 0.0)) > float(item.get("latest", 0.0)) - float(item.get("earliest", 0.0)) + 1e-9:
            impossible.append("At least one service duration is longer than its entire time window")
            break
    if use_time_window and total_service_s > max(1, trucks) * horizon_s + 1e-9:
        impossible.append(
            f"Service time alone needs {service_hours_per_truck:.1f} h per truck, "
            f"but the visible time horizon is only {horizon_s / 3600.0:.1f} h"
        )
    if stops_per_truck > 45:
        warnings.append(f"Stress workload: approximately {stops_per_truck:.1f} customer nodes per truck")
    elif stops_per_truck > 30:
        warnings.append(f"High stop density: approximately {stops_per_truck:.1f} customer nodes per truck")
    if use_time_window and total_service_s / max(1, trucks) > horizon_s * 0.75:
        warnings.append("Service workload consumes most of the available time horizon before travel is added")
    return {
        "ok": not impossible,
        "impossible_reasons": impossible,
        "warnings": warnings,
        "customer_nodes": len(customers),
        "customer_orders": len(customer_places),
        "generated_order_count": len(generated),
        "all_generated": bool(customer_places) and len(generated) == len(customer_places),
        "total_demand": round(total_demand, 3),
        "fleet_capacity": round(effective_capacity, 3),
        "single_trip_fleet_capacity": round(trucks * capacity, 3),
        "allow_multi_trip": bool(allow_multi_trip),
        "max_trips_per_truck": trip_limit,
        "maximum_trip_slots": total_trip_slots,
        "capacity_lower_bound_trips": required_trips_by_capacity,
        "maximum_available_trucks": trucks,
        "capacity_lower_bound_trucks": required_by_capacity,
        "fleet_utilization_pct": round(100.0 * total_demand / max(1.0, effective_capacity), 1),
        "required_fleet_utilization_pct": round(
            100.0 * total_demand / max(1.0, required_trips_by_capacity * capacity), 1
        ),
        "stops_per_truck": round(stops_per_truck, 1),
        "service_hours_per_truck": round(service_hours_per_truck, 2),
        "time_horizon_hours": round(horizon_s / 3600.0, 2),
    }



def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    stat = path.stat()
    key = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    with _HASH_CACHE_LOCK:
        cached = _HASH_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    with _HASH_CACHE_LOCK:
        # Keep the cache bounded and discard stale signatures for this path.
        if len(_HASH_CACHE) > 96:
            _HASH_CACHE.clear()
        _HASH_CACHE[key] = value
    return value


def _remember_file_hash(path: Path, digest: str) -> None:
    try:
        stat = path.stat()
    except OSError:
        return
    key = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    with _HASH_CACHE_LOCK:
        _HASH_CACHE[key] = str(digest)


def _load_materialized_dataset() -> dict[str, Any]:
    """Return the current immutable materialized dataset with stat-bound reuse.

    A solve consults dataset.json repeatedly for baseline construction, clustering
    validation, candidate certification, and publication. Re-parsing the same
    multi-megabyte road payload at every stage adds pure Python latency.
    Materializations are atomically replaced and treated as immutable once
    published, so a path/inode/mtime/size signature binds this process-local cache
    to one exact file generation. Any replacement automatically misses.

    Callers must treat the returned object as read-only. FleetRoute's internal
    dataset consumers already follow that contract; route/customer structures are
    built separately rather than mutating the materialized evidence object.
    """
    global _DATASET_CACHE
    path = settings.dataset_json

    def signature() -> tuple[str, int, int, int]:
        stat = path.stat()
        return (
            str(path.resolve()), int(getattr(stat, "st_ino", 0)),
            int(stat.st_mtime_ns), int(stat.st_size),
        )

    initial = signature()
    with _DATASET_CACHE_LOCK:
        cached = _DATASET_CACHE
        if cached is not None and cached[0] == initial:
            return cached[1]

    # The publication lock makes churn rare, but the loader can also be used by
    # read-only diagnostics. Never cache a generation that changed mid-read.
    value: dict[str, Any] | None = None
    stable_signature: tuple[str, int, int, int] | None = None
    before = initial
    for _ in range(3):
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("dataset.json must contain a JSON object")
        after = signature()
        if after == before:
            value = parsed
            stable_signature = after
            break
        before = after
    if value is None or stable_signature is None:
        raise RuntimeError("dataset.json changed repeatedly while being read; retry after the active materialization finishes")
    with _DATASET_CACHE_LOCK:
        _DATASET_CACHE = (stable_signature, value)
    return value


def _runtime_artifact_url(path: Path) -> str | None:
    """Return a cache-busted URL for one file under the active runtime."""
    if not path.is_file():
        return None
    try:
        relative = path.resolve().relative_to(RUNTIME_DIR.resolve())
    except ValueError:
        return None
    stat = path.stat()
    revision = f"{int(stat.st_mtime_ns):x}-{int(stat.st_size):x}"
    return "/api/artifacts/" + "/".join(relative.parts) + f"?v={revision}"


def _clustering_source_receipt(
    dataset: dict[str, Any],
    cluster_input: Path,
    *,
    active_cluster_count: int,
) -> dict[str, Any]:
    active = get_setting("active_input_state") or {}
    customer_nodes = sorted(int(item["node"]) for item in dataset.get("customers") or [])
    input_sha = _sha256_file(settings.input_txt)
    dataset_sha = _sha256_file(settings.dataset_json)
    content_fallback = _sha256_text(input_sha + ":" + dataset_sha)
    return {
        "created_at": utc_now(),
        "source_signature": active.get("source_signature") or content_fallback,
        "materialization_id": active.get("materialization_id"),
        "input_sha256": input_sha,
        "dataset_sha256": dataset_sha,
        "cluster_input_sha256": _sha256_file(cluster_input),
        "customer_node_sha256": _sha256_text(
            json.dumps(customer_nodes, separators=(",", ":"))
        ),
        "customer_count": len(customer_nodes),
        "maximum_available_trucks": int(dataset.get("K_trucks") or 0),
        "capacity": float(dataset.get("truck_capacity") or 0.0),
        "active_cluster_count": int(active_cluster_count),
        "graph_cache_key": active.get("graph_cache_key"),
        "closure_revision": active.get("closure_revision"),
    }


def _atomic_write_bundle(files: dict[Path, str]) -> None:
    """Atomically replace a related text-file set with O(1) rollback renames.

    The old implementation copied every existing file before replacement. For a
    large dataset.json this doubled disk traffic on every solve. Same-filesystem
    os.replace() gives us a rollback snapshot by rename without copying bytes.
    """
    staged: list[tuple[Path, Path]] = []
    backups: dict[Path, Path | None] = {}
    installed: list[Path] = []
    token = f"{os.getpid()}-{threading.get_ident()}-{time.monotonic_ns()}"
    try:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f".{path.name}.tmp-{token}")
            temp.write_text(text, encoding="utf-8")
            staged.append((temp, path))
        for temp, path in staged:
            backup: Path | None = None
            if path.exists():
                backup = path.with_name(f".{path.name}.bak-{token}")
                os.replace(path, backup)
            backups[path] = backup
            try:
                os.replace(temp, path)
                installed.append(path)
            except Exception:
                if backup is not None and backup.exists() and not path.exists():
                    os.replace(backup, path)
                raise
    except Exception:
        for path in reversed(installed):
            backup = backups.get(path)
            try:
                if path.exists():
                    path.unlink()
                if backup is not None and backup.exists():
                    os.replace(backup, path)
            except OSError:
                pass
        # Restore files whose old version was renamed but whose new version was
        # never installed because a later replacement raised.
        for path, backup in backups.items():
            if backup is not None and backup.exists() and not path.exists():
                try:
                    os.replace(backup, path)
                except OSError:
                    pass
        raise
    finally:
        for temp, _ in staged:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        for path, backup in backups.items():
            if backup is not None and backup.exists() and path.exists():
                try:
                    backup.unlink()
                except OSError:
                    pass


def _atomic_promote_files(
    files: dict[Path, Path], *, retain_previous: bool = False,
) -> tuple[dict[str, Any], dict[Path, Path | None]]:
    """Promote an immutable attempt bundle without copying it on normal filesystems.

    ``files`` maps attempt source -> public last-completed destination. Sources
    remain in the per-job workspace for diagnosis. Hard links make the normal
    commit O(1); a copy fallback keeps the contract portable. All public targets
    roll back together if any replacement fails.
    """
    started = time.monotonic()
    token = f"{os.getpid()}-{threading.get_ident()}-{time.monotonic_ns()}"
    staged: list[tuple[Path, Path]] = []
    backups: dict[Path, Path | None] = {}
    installed: list[Path] = []
    linked = 0
    copied_bytes = 0
    succeeded = False
    try:
        for source, target in files.items():
            if not source.is_file():
                raise FileNotFoundError(f"Attempt artifact is missing: {source}")
            target.parent.mkdir(parents=True, exist_ok=True)
            staged_path = target.with_name(f".{target.name}.promote-{token}")
            try:
                os.link(source, staged_path)
                linked += 1
            except OSError:
                shutil.copy2(source, staged_path)
                copied_bytes += source.stat().st_size
            staged.append((staged_path, target))

        for staged_path, target in staged:
            backup: Path | None = None
            if target.exists():
                backup = target.with_name(f".{target.name}.previous-{token}")
                os.replace(target, backup)
            backups[target] = backup
            try:
                os.replace(staged_path, target)
                installed.append(target)
            except Exception:
                if backup is not None and backup.exists() and not target.exists():
                    os.replace(backup, target)
                raise
        succeeded = True
    except Exception:
        for target in reversed(installed):
            backup = backups.get(target)
            try:
                target.unlink(missing_ok=True)
                if backup is not None and backup.exists():
                    os.replace(backup, target)
            except OSError:
                pass
        for target, backup in backups.items():
            if backup is not None and backup.exists() and not target.exists():
                try:
                    os.replace(backup, target)
                except OSError:
                    pass
        raise
    finally:
        for staged_path, _ in staged:
            try:
                staged_path.unlink(missing_ok=True)
            except OSError:
                pass
        if succeeded and not retain_previous:
            for backup in backups.values():
                if backup is not None:
                    try:
                        backup.unlink(missing_ok=True)
                    except OSError:
                        pass
    summary = {
        "files": len(files),
        "hard_linked": linked,
        "copied_bytes": copied_bytes,
        "elapsed_ms": round((time.monotonic() - started) * 1000.0, 3),
        "previous_retained_for_route_commit": bool(retain_previous),
    }
    return summary, (dict(backups) if retain_previous else {})


def _finish_promoted_files(backups: dict[Path, Path | None], *, rollback: bool) -> dict[str, Any]:
    """Finalize or roll back a promoted evidence generation.

    Route publication has a later SQLite/input revision gate than evidence-file
    promotion. Retaining the previous generation across that tiny boundary keeps
    public route state and public evidence from ever describing different solves.
    """
    restored = 0
    removed_new = 0
    cleanup_errors: list[str] = []
    for target, backup in reversed(list(backups.items())):
        try:
            if rollback:
                if target.exists():
                    target.unlink()
                    removed_new += 1
                if backup is not None and backup.exists():
                    os.replace(backup, target)
                    restored += 1
            elif backup is not None:
                backup.unlink(missing_ok=True)
        except OSError as exc:
            cleanup_errors.append(f"{target.name}: {exc}")
    if rollback and cleanup_errors:
        raise RuntimeError("Evidence rollback was incomplete: " + "; ".join(cleanup_errors))
    return {
        "rollback": bool(rollback), "restored": restored,
        "removed_new": removed_new, "cleanup_errors": cleanup_errors,
    }


def _prune_solver_attempt_workspaces(keep: int = 20) -> int:
    """Bound private attempt disk growth while retaining recent diagnostics."""
    root = RUNTIME_DIR / "solver-attempts"
    if not root.is_dir():
        return 0
    candidates = [
        path
        for path in root.iterdir()
        if path.is_dir() and re.fullmatch(r"job_[0-9]+", path.name)
    ]
    candidates.sort(key=lambda path: int(path.name.split("_", 1)[1]), reverse=True)
    removed = 0
    for path in candidates[max(1, int(keep)):]:
        try:
            # ``path`` is a validated direct child of the dedicated attempt root.
            shutil.rmtree(path)
            removed += 1
        except OSError:
            pass
    return removed


def _validate_input_contract_text(text: str, dataset: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse the exact stdin contract and verify counts before exposing it to C++."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cursor = 0

    def take(label: str) -> list[str]:
        nonlocal cursor
        if cursor >= len(lines):
            raise ValueError(f"input.txt ended before {label}")
        parts = lines[cursor].split()
        cursor += 1
        return parts

    header = take("N M")
    if len(header) != 2:
        raise ValueError("input.txt first line must contain exactly N M")
    n_nodes, n_edges = map(int, header)
    fleet_line = take("K")
    depot_line = take("depot")
    if len(fleet_line) != 1 or len(depot_line) != 1:
        raise ValueError("input.txt K and depot lines must each contain one value")
    trucks, depot = int(fleet_line[0]), int(depot_line[0])
    if n_nodes <= 0 or n_edges < 0 or trucks <= 0:
        raise ValueError("input.txt contains non-positive node/fleet counts")
    if not 0 <= depot < n_nodes:
        raise ValueError("input.txt depot index is outside [0, N)")

    edge_pairs: set[tuple[int, int]] = set()
    parsed_edges: list[tuple[int, int, float, float]] = []
    min_length = float("inf")
    min_speed = float("inf")
    for index in range(n_edges):
        parts = take(f"edge {index + 1}/{n_edges}")
        if len(parts) != 4:
            raise ValueError(f"edge line {index + 1} must contain u v length speed")
        u, v = int(parts[0]), int(parts[1])
        length, speed = float(parts[2]), float(parts[3])
        if not (0 <= u < n_nodes and 0 <= v < n_nodes):
            raise ValueError(f"edge line {index + 1} contains an invalid node index")
        if length <= 0 or speed <= 0:
            raise ValueError(f"edge line {index + 1} contains non-positive length/speed")
        edge_pairs.add((u, v))
        parsed_edges.append((u, v, length, speed))
        min_length = min(min_length, length)
        min_speed = min(min_speed, speed)

    customer_count_line = take("customer count")
    if len(customer_count_line) != 1:
        raise ValueError("customer count line must contain one integer")
    customer_count = int(customer_count_line[0])
    if customer_count <= 0:
        raise ValueError("input.txt must contain at least one customer node")
    customer_nodes: set[int] = set()
    parsed_customers: list[tuple[int, float, float, float, float]] = []
    total_demand = 0.0
    for index in range(customer_count):
        parts = take(f"customer {index + 1}/{customer_count}")
        if len(parts) != 5:
            raise ValueError(f"customer line {index + 1} must contain node demand service earliest latest")
        node = int(parts[0])
        demand, service, earliest, latest = map(float, parts[1:])
        if not 0 <= node < n_nodes or node == depot:
            raise ValueError(f"customer line {index + 1} contains an invalid/depot node")
        if node in customer_nodes:
            raise ValueError(f"customer node {node} appears more than once")
        if demand < 0 or service < 0 or earliest < 0 or latest < earliest:
            raise ValueError(f"customer line {index + 1} contains invalid demand/service/time-window data")
        customer_nodes.add(node)
        parsed_customers.append((node, demand, service, earliest, latest))
        total_demand += demand

    capacity_line = take("capacity")
    if len(capacity_line) != 1:
        raise ValueError("capacity line must contain one number")
    capacity = float(capacity_line[0])
    if capacity <= 0:
        raise ValueError("truck capacity must be positive")
    if cursor != len(lines):
        raise ValueError(f"input.txt contains {len(lines) - cursor} unexpected trailing lines")

    checks = [
        {"id": "line_counts", "ok": True, "detail": f"N={n_nodes}, M={n_edges}, G={customer_count}"},
        {"id": "indices", "ok": True, "detail": "Depot, edge, and customer indices are in range"},
        {"id": "positive_weights", "ok": True, "detail": "All edge lengths, speeds, and capacity are positive"},
        {"id": "unique_customers", "ok": True, "detail": f"{len(customer_nodes)} unique customer nodes"},
        {"id": "time_windows", "ok": True, "detail": "Every customer has earliest ≤ latest"},
    ]
    if dataset is not None:
        expected = {
            "num_nodes": n_nodes,
            "num_edges": n_edges,
            "K_trucks": trucks,
            "depot": depot,
        }
        mismatches = [f"{key}: input={value}, dataset={dataset.get(key)}" for key, value in expected.items() if dataset.get(key) != value]
        if len(dataset.get("customers") or []) != customer_count:
            mismatches.append(f"customers: input={customer_count}, dataset={len(dataset.get('customers') or [])}")
        dataset_capacity = float(dataset.get("truck_capacity") or 0.0)
        if abs(dataset_capacity - capacity) > 1e-6:
            mismatches.append(f"capacity: input={capacity}, dataset={dataset_capacity}")
        dataset_nodes = dataset.get("nodes") or []
        dataset_edges = dataset.get("edges") or []
        dataset_customers = dataset.get("customers") or []
        if len(dataset_nodes) != n_nodes:
            mismatches.append(f"nodes array: input N={n_nodes}, dataset nodes={len(dataset_nodes)}")
        if len(dataset_edges) != n_edges:
            mismatches.append(f"edges array: input M={n_edges}, dataset edges={len(dataset_edges)}")
        else:
            for index, (parsed, record) in enumerate(zip(parsed_edges, dataset_edges), start=1):
                expected_edge = (
                    int(record.get("u", -1)), int(record.get("v", -1)),
                    round(float(record.get("length_m", -1.0)), 3),
                    round(float(record.get("speed_kph", -1.0)), 3),
                )
                if parsed[:2] != expected_edge[:2] or abs(parsed[2] - expected_edge[2]) > 1e-9 or abs(parsed[3] - expected_edge[3]) > 1e-9:
                    mismatches.append(f"edge {index}: input={parsed}, dataset-rounded={expected_edge}")
                    break
        if len(dataset_customers) == customer_count:
            for index, (parsed, record) in enumerate(zip(parsed_customers, dataset_customers), start=1):
                expected_customer = (
                    int(record.get("node", -1)),
                    round(float(record.get("demand", -1.0)), 6),
                    round(float(record.get("service_time_s", -1.0)), 3),
                    round(float(record.get("earliest", -1.0)), 3),
                    round(float(record.get("latest", -1.0)), 3),
                )
                if parsed[0] != expected_customer[0] or any(abs(parsed[i] - expected_customer[i]) > 1e-9 for i in range(1, 5)):
                    mismatches.append(f"customer {index}: input={parsed}, dataset-rounded={expected_customer}")
                    break
        if mismatches:
            raise ValueError("input.txt and dataset.json disagree: " + "; ".join(mismatches))
        checks.append({"id": "dataset_match", "ok": True, "detail": "Every serialized edge/customer value and all fleet counts match dataset.json"})

    return {
        "ok": True,
        "nodes": n_nodes,
        "edges": n_edges,
        "unique_directed_pairs": len(edge_pairs),
        "trucks": trucks,
        "depot": depot,
        "customer_nodes": customer_count,
        "capacity": capacity,
        "total_demand": round(total_demand, 6),
        "minimum_edge_length_m": None if n_edges == 0 else round(min_length, 6),
        "minimum_speed_kph": None if n_edges == 0 else round(min_speed, 6),
        "line_count": len(lines),
        "checks": checks,
    }


def _materialization_source_contract(
    fleet_override: dict[str, Any] | None = None,
    solver_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values = get_settings(("plan_revision", "closure_revision", "fleet", "solver", "network_summary"))
    fleet = dict(fleet_override) if fleet_override is not None else (values.get("fleet") or {})
    solver = dict(solver_override) if solver_override is not None else (values.get("solver") or {})
    network = values.get("network_summary") or {}
    # ``plan_revision`` is the fast normal invalidation path, but include a small
    # fingerprint of the actual active rows as a safety net. This catches manual
    # DB recovery/repair and old databases whose access flags changed without a
    # revision bump, so a cached input can never hide stale road-access state.
    place_fingerprint = [
        {
            "id": item.get("id"), "role": item.get("role"), "updated_at": item.get("updated_at"),
            "lat": item.get("lat"), "lon": item.get("lon"), "demand": item.get("demand"),
            "service_s": item.get("service_s"), "earliest_s": item.get("earliest_s"),
            "latest_s": item.get("latest_s"), "access_verified": item.get("access_verified"),
            "access_osm_node": item.get("access_osm_node"), "access_osm_u": item.get("access_osm_u"),
            "access_osm_v": item.get("access_osm_v"), "access_osm_key": item.get("access_osm_key"),
        }
        for item in list_places()
    ]
    return {
        "plan_revision": values.get("plan_revision") or {},
        "places": place_fingerprint,
        "closure_revision": values.get("closure_revision") or {},
        # Canonical numeric types make semantically equal snapshots (100 and
        # 100.0) hash identically. Queue/API round-trips must not invalidate an
        # otherwise exact materialization merely because JSON changed a number's
        # representation.
        "fleet": {
            "trucks": int(fleet.get("trucks") or 0),
            "capacity": float(fleet.get("capacity") or 0.0),
        },
        "routing_contract": {
            "objective_mode": str(solver.get("objective_mode", "distance")),
            "use_time_window": bool(solver.get("use_time_window", True)),
            "route_start_time_s": float(solver.get("route_start_time_s", 8 * 3600)),
            "allow_multi_trip": bool(solver.get("allow_multi_trip", False)),
            "max_trips_per_truck": max(1, int(solver.get("max_trips_per_truck", 3))),
            "travel_time_model": "static_osm_snapshot",
        },
        "network": {
            "cache_key": network.get("cache_key"),
            "built_at": network.get("built_at"),
            "nodes": network.get("nodes"),
            "edges": network.get("edges"),
        },
    }


def _source_contract_component_hashes(source: dict[str, Any]) -> dict[str, str]:
    return {
        key: _sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        for key, value in source.items()
    }


def _materialization_source_signature(
    fleet_override: dict[str, Any] | None = None,
    solver_override: dict[str, Any] | None = None,
) -> str:
    source = _materialization_source_contract(fleet_override, solver_override)
    return _sha256_text(json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _reusable_materialization(source_signature: str) -> dict[str, Any] | None:
    if not (settings.input_txt.is_file() and settings.dataset_json.is_file() and settings.dataset_summary_json.is_file()):
        return None
    try:
        summary = json.loads(settings.dataset_summary_json.read_text(encoding="utf-8"))
        if str(summary.get("source_signature") or "") != str(source_signature):
            return None
        files = summary.get("files") or {}
        expected_input = (files.get("input.txt") or {}).get("sha256")
        expected_dataset = (files.get("dataset.json") or {}).get("sha256")
        if not expected_input or not expected_dataset:
            return None
        if _sha256_file(settings.input_txt) != expected_input or _sha256_file(settings.dataset_json) != expected_dataset:
            return None
        result = dict(summary.get("result") or {})
        if not result or not (summary.get("contract") or {}).get("ok"):
            return None
        result["reused_materialization"] = True
        result["reuse_reason"] = "plan, fleet, graph, closures, and validated file hashes are unchanged"
        return result
    except Exception:
        return None


def _set_active_input_state_from_materialization(
    source_signature: str,
    result: dict[str, Any],
    *,
    reused: bool,
) -> None:
    """Persist exactly which database/graph state owns the active solver input."""
    closure_revision = get_setting("closure_revision") or {}
    network = get_setting("network_summary") or {}
    files = result.get("files") or {}
    set_setting("active_input_state", {
        "current": True,
        "updated_at": utc_now(),
        "source_signature": str(source_signature),
        "materialization_id": result.get("materialization_id"),
        "input_path": str(settings.input_txt),
        "dataset_path": str(settings.dataset_json),
        "input_sha256": (files.get("input.txt") or {}).get("sha256"),
        "dataset_sha256": (files.get("dataset.json") or {}).get("sha256"),
        "closure_revision": int(closure_revision.get("revision", 0)),
        "graph_cache_key": network.get("cache_key"),
        "reused_materialization": bool(reused),
        "source_component_hashes": dict(result.get("source_component_hashes") or {}),
    })


def materialize_solver_instance(
    *,
    fleet_override: dict[str, Any] | None = None,
    solver_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the native stdin contract from one explicit fleet snapshot.

    Queue callers pass the click-time snapshot. Direct maintenance/test callers
    may omit it and retain the historical behavior of reading current settings.
    """
    frozen_fleet = dict(fleet_override) if fleet_override is not None else None
    frozen_solver = dict(solver_override) if solver_override is not None else None
    source_signature = _materialization_source_signature(frozen_fleet, frozen_solver)
    reusable = _reusable_materialization(source_signature)
    if reusable is not None:
        if reusable.get("feasibility"):
            set_setting("latest_feasibility", reusable["feasibility"])
        _set_active_input_state_from_materialization(source_signature, reusable, reused=True)
        log_event("instance.reused", {k: v for k, v in reusable.items() if k != "contract"}, "system")
        return reusable
    graph, removed = graph_with_closures()
    places = list_places()
    depot_place = next((p for p in places if p["role"] == "depot"), None)
    customer_places = [p for p in places if p["role"] == "customer"]
    if not depot_place or not customer_places:
        raise ValueError("A depot and at least one customer are required")
    active_fleet = frozen_fleet if frozen_fleet is not None else (get_setting("fleet") or {})
    active_solver = frozen_solver if frozen_solver is not None else (get_setting("solver") or {})
    current_snap_max = float(active_fleet.get("snap_max_m", 350))
    not_verified = [
        p for p in places
        if (not p.get("access_verified"))
        or p.get("access_distance_m") is None
        or float(p.get("access_distance_m") or 0.0) > current_snap_max
    ]
    if not_verified:
        # Self-repair stale access records whenever the graph is already active.
        # This is intentionally done inside materialization as the last safety net:
        # users must never need to repeat the same workflow just to validate a
        # pending depot left behind by an earlier graph build.
        repaired_invalid = _update_access_points(
            graph, place_ids={int(place["id"]) for place in not_verified}
        )
        places = list_places()
        depot_place = next((p for p in places if p["role"] == "depot"), None)
        customer_places = [p for p in places if p["role"] == "customer"]
        still_pending = [p for p in places if not p.get("access_verified")]
        if still_pending:
            pending_labels = [
                f"{p['name']} ({'Depot' if p['role'] == 'depot' else 'customer'})"
                for p in still_pending
            ]
            details = ""
            if repaired_invalid:
                details = " The selected location is outside the accepted road-access distance."
            raise ValueError(
                "These plan locations are not road-valid on the active operating graph: "
                + ", ".join(pending_labels[:8])
                + details
            )
    points = [depot_place, *customer_places]
    snapped = []
    for place in points:
        stored = str(place.get("access_osm_node") or "")
        node = GRAPH_STORE.resolve_node(stored) if stored else None
        if node is None or node not in graph:
            node = GRAPH_STORE.nearest_node(
                float(place.get("access_lat") or place["lat"]),
                float(place.get("access_lon") or place["lon"]),
            )
        snapped.append(node)
    depot_osm = snapped[0]
    graph_meta = GRAPH_STORE.metadata()
    base_is_round_trip = bool(graph_meta.get("round_trip_component"))
    # The prepared operating graph is already the depot's strongly-connected
    # round-trip component. With no applied closure removals, repeating two full
    # descendant scans and copying a ~65k-node graph adds latency but no safety.
    if removed or not base_is_round_trip:
        reachable = nx.descendants(graph, depot_osm) | {depot_osm}
        unreachable = [p["name"] for p, node in zip(points, snapped) if node not in reachable]
        if unreachable:
            raise ValueError("Approved road closures disconnected these stops from the depot: " + ", ".join(unreachable[:10]))
        reverse_reachable = nx.descendants(graph.reverse(copy=False), depot_osm) | {depot_osm}
        keep_nodes = reachable & reverse_reachable
        if any(node not in keep_nodes for node in snapped):
            raise ValueError("At least one stop cannot return to the depot on the active directed network")
        graph = graph.subgraph(keep_nodes)
    old_nodes = list(graph.nodes())
    old_to_new = {old: i for i, old in enumerate(old_nodes)}
    new_to_old = {i: old for old, i in old_to_new.items()}
    depot = old_to_new[depot_osm]
    grouped: dict[int, dict[str, Any]] = {}
    for place, old_node in zip(customer_places, snapped[1:]):
        node = old_to_new[old_node]
        existing = grouped.setdefault(node, {
            "node": node, "demand": 0.0, "service_time_s": 0.0,
            "earliest": 0.0, "latest": 86400.0, "orders": [],
        })
        existing["demand"] += float(place["demand"])
        existing["service_time_s"] += float(place["service_s"])
        existing["earliest"] = max(existing["earliest"], float(place["earliest_s"]))
        existing["latest"] = min(existing["latest"], float(place["latest_s"]))
        external_id = str(place.get("external_id") or "")
        planned_match = re.search(r"scenario:[^:]+:truck:(\d+):order:", external_id)
        existing["orders"].append({
            "place_id": place["id"], "name": place["name"], "address": place["address"],
            "lat": place["lat"], "lon": place["lon"], "access_lat": place["access_lat"],
            "access_lon": place["access_lon"], "access_road": place["access_road"],
            "demand": place["demand"], "external_id": external_id,
            "planned_truck": int(planned_match.group(1)) if planned_match else None,
        })
    if any(c["latest"] < c["earliest"] for c in grouped.values()):
        raise ValueError("Orders sharing one road-access node have incompatible time windows")
    fleet = active_fleet
    trucks, capacity = int(fleet.get("trucks", 4)), float(fleet.get("capacity", 100))
    use_time_window = bool(active_solver.get("use_time_window", True))
    allow_multi_trip = bool(active_solver.get("allow_multi_trip", False))
    max_trips_per_truck = (
        max(1, int(active_solver.get("max_trips_per_truck", 3)))
        if allow_multi_trip else 1
    )
    route_start_time_s = float(active_solver.get("route_start_time_s", 8 * 3600))
    objective_mode = str(active_solver.get("objective_mode", "distance"))
    customers = list(grouped.values())
    if any(c["demand"] > capacity + 1e-9 for c in customers):
        names = [c["orders"][0]["name"] for c in customers if c["demand"] > capacity + 1e-9]
        raise ValueError("A road-access location exceeds truck capacity: " + ", ".join(names))
    if sum(c["demand"] for c in customers) > trucks * capacity * max_trips_per_truck + 1e-9:
        raise ValueError(
            "Total demand exceeds the permitted fleet trip capacity"
            if allow_multi_trip else "Total demand exceeds total fleet capacity"
        )

    # Keep parallel OSM edges. A shorter edge can be slower than its parallel
    # alternative, so collapsing every (u, v) pair to the fastest edge would
    # make the distance objective incapable of choosing its true road path.
    edges: list[dict[str, Any]] = []
    for u, v, k, data in graph.edges(keys=True, data=True):
        nu, nv = old_to_new[u], old_to_new[v]
        # Round once before deriving travel time so dataset.json and the exact
        # values serialized to C++ stdin describe the same static snapshot.
        length = round(max(.01, float(data.get("length", 1))), 3)
        speed = round(_safe_speed_kph(data), 3)
        travel_time = length / (speed * 1000 / 3600)
        record = {
            "u": nu, "v": nv, "length_m": length, "speed_kph": speed,
            "travel_time_s": travel_time, "osm_u": str(u), "osm_v": str(v), "osm_key": str(k),
            "name": _clean_name(data.get("name"), ""), "highway": _clean_highway(data.get("highway")),
            "geometry": _edge_geometry(graph, u, v, data),
        }
        edges.append(record)
    edges.sort(key=lambda item: (
        int(item["u"]), int(item["v"]), str(item["osm_key"]),
        float(item["length_m"]), float(item["speed_kph"]),
    ))
    materialization_id = f"{utc_now()}-{os.getpid()}-{threading.get_ident()}"
    payload = {
        "app_dataset_version": 3, "created_at": utc_now(), "materialization_id": materialization_id,
        "num_nodes": len(old_nodes),
        "num_edges": len(edges), "K_trucks": trucks, "truck_capacity": capacity,
        "vehicle_count_semantics": "maximum_available_not_required",
        "routing_contract": {
            "objective_mode": objective_mode,
            "use_time_window": use_time_window,
            "route_start_time_s": route_start_time_s,
            "allow_multi_trip": allow_multi_trip,
            "max_trips_per_truck": max_trips_per_truck,
            "travel_time_model": "static_osm_snapshot",
            "road_path_selection": "shortest path under the selected distance, time, or hybrid arc cost",
            "hybrid_objective": "distance_m + 0.25 * (travel_time_s + waiting_s + service_time_s)",
        },
        "depot": depot, "depot_place": depot_place, "customers": customers,
        "approved_closures_removed": [
            {"osm_u": u, "osm_v": v, "osm_key": k, "closure_id": cid}
            for u, v, k, cid in removed
        ],
        "nodes": [
            {
                # cluster.cpp intentionally parses this exact numeric contract:
                # id -> osm_id -> lon -> lat. Keep osm_id numeric and preserve order.
                "id": i, "osm_id": int(new_to_old[i]),
                "lon": float(graph.nodes[new_to_old[i]]["x"]),
                "lat": float(graph.nodes[new_to_old[i]]["y"]),
                "type": "depot" if i == depot else "customer" if i in grouped else "normal",
            }
            for i in range(len(old_nodes))
        ],
        "edges": edges,
    }
    feasibility = _instance_feasibility_diagnostics(
        customers,
        customer_places,
        trucks,
        capacity,
        use_time_window=use_time_window,
        allow_multi_trip=allow_multi_trip,
        max_trips_per_truck=max_trips_per_truck,
    )
    if not feasibility["ok"]:
        raise ValueError("Instance feasibility check: " + "; ".join(feasibility["impossible_reasons"]))

    input_lines = [f"{len(old_nodes)} {len(edges)}", str(trucks), str(depot)]
    input_lines.extend(
        f"{edge['u']} {edge['v']} {edge['length_m']:.3f} {edge['speed_kph']:.3f}"
        for edge in edges
    )
    input_lines.append(str(len(customers)))
    input_lines.extend(
        f"{c['node']} {c['demand']:.6f} {c['service_time_s']:.3f} {c['earliest']:.3f} {c['latest']:.3f}"
        for c in customers
    )
    input_lines.append(f"{capacity:.6f}")
    input_text = "\n".join(input_lines) + "\n"
    contract = _validate_input_contract_text(input_text, payload)
    dataset_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    # Materialization may self-repair old/pending road-access rows above. Those
    # repairs update the place fingerprint, so the signature captured before the
    # repair would already be stale by the time these exact files are written.
    # Recompute after every source mutation; otherwise an unchanged rerun misses
    # the reusable input cache, rebuilds needlessly, and cannot protect its route.
    final_source_contract = _materialization_source_contract(frozen_fleet, frozen_solver)
    source_signature = _sha256_text(json.dumps(
        final_source_contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ))
    source_component_hashes = _source_contract_component_hashes(final_source_contract)
    summary_payload = {
        "summary_version": 1,
        "created_at": utc_now(),
        "materialization_id": materialization_id,
        "source_signature": source_signature,
        "source_component_hashes": source_component_hashes,
        "files": {
            "input.txt": {"bytes": len(input_text.encode('utf-8')), "sha256": _sha256_text(input_text)},
            "dataset.json": {"bytes": len(dataset_text.encode('utf-8')), "sha256": _sha256_text(dataset_text)},
        },
        "contract": contract,
        "feasibility": feasibility,
        "fleet": {
            "maximum_available_trucks": trucks,
            "capacity_per_truck": capacity,
            "capacity_lower_bound_trucks": feasibility.get("capacity_lower_bound_trucks"),
            "total_demand": feasibility.get("total_demand"),
            "fleet_utilization_pct": feasibility.get("fleet_utilization_pct"),
        },
        "graph": {
            "nodes": len(old_nodes),
            "directed_edges": len(edges),
            "depot_node": depot,
            "approved_closures_removed": len(removed),
        },
        "customers": {
            "orders": len(customer_places),
            "solver_nodes": len(customers),
            "collapsed_same_access_node": len(customer_places) - len(customers),
        },
        "semantics": {
            "K": "maximum available vehicles, not required non-empty routes",
            "customer_count": "unique road-access nodes after same-node order aggregation",
            "edge_time": "static travel_time_s = rounded length_m / rounded speed_kph; identical in Python and C++",
            "road_path": "shortest path follows the selected distance, time, or hybrid arc cost in both Python and C++",
            "route_clock": "one continuous clock per physical truck, including depot returns between trips",
            "hybrid_objective": "distance_m + 0.25 * route_duration_s",
        },
    }
    result = {
        "nodes": len(old_nodes), "edges": len(edges), "customer_nodes": len(customers),
        "customer_orders": len(customer_places), "removed_closed_edges": len(removed),
        "feasibility": feasibility,
        "approved_closures_removed": [
            {"osm_u": u, "osm_v": v, "osm_key": k, "closure_id": cid}
            for u, v, k, cid in removed
        ],
        "collapsed_same_access_node": len(customer_places) - len(customers),
        "materialization_id": materialization_id,
        "contract": contract,
        "files": summary_payload["files"],
        "source_component_hashes": source_component_hashes,
        "reused_materialization": False,
    }
    summary_payload["result"] = result
    summary_text = json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n"
    # Keep the exact files and their database identity one publication unit with
    # respect to route commits. The lock is process-local because these workers
    # share one app process/runtime; SQLite still arbitrates the database side.
    with _INPUT_PUBLICATION_LOCK:
        _atomic_write_bundle({
            settings.input_txt: input_text,
            settings.dataset_json: dataset_text,
            settings.dataset_summary_json: summary_text,
        })
        _remember_file_hash(settings.input_txt, summary_payload["files"]["input.txt"]["sha256"])
        _remember_file_hash(settings.dataset_json, summary_payload["files"]["dataset.json"]["sha256"])
        set_setting("latest_feasibility", feasibility)
        _set_active_input_state_from_materialization(source_signature, result, reused=False)
    log_event("instance.materialized", result, "system")
    return result


def build_baseline_certificate(
    *,
    publish_job_id: int | None = None,
    publish: bool = False,
    retain_routing_context: bool = False,
    solver_config: dict[str, Any] | None = None,
    settings_revision: dict[str, int] | None = None,
) -> dict[str, Any]:
    dataset = _load_materialized_dataset()
    solver = dict(solver_config) if solver_config is not None else (get_setting("solver") or {})
    certificate = build_baseline_routes(
        dataset,
        objective_mode=str(solver.get("objective_mode", "distance")),
        route_start_time_s=float(solver.get("route_start_time_s", 8 * 3600)),
        use_time_window=bool(solver.get("use_time_window", True)),
        allow_multi_trip=bool(solver.get("allow_multi_trip", False)),
        max_trips_per_truck=(
            max(1, int(solver.get("max_trips_per_truck", 3)))
            if solver.get("allow_multi_trip", False) else 1
        ),
    )
    routing_context = certificate.pop("_routing_context", None)
    route_paths = certificate.pop("_route_paths", {})
    materialization_id = str(dataset.get("materialization_id") or "")
    certificate["materialization_id"] = materialization_id
    _set_active_routing_context(routing_context if retain_routing_context else None)
    if publish and certificate.get("feasible") and publish_job_id is not None:
        published = publish_routes(
            int(publish_job_id),
            certificate.get("routes") or [],
            solution_source="deterministic_baseline",
            metadata={"baseline_certificate": {key: value for key, value in certificate.items() if key != "routes"}},
            routing_context=routing_context,
            precomputed_paths=route_paths,
            settings_revision=settings_revision,
        )
        certificate["published_route_version"] = published["version_id"]
    # Persist only after optional publication so the durable certificate carries
    # its materialization and published route identity. This also lets an
    # immediately queued improvement job reuse the exact certificate safely.
    set_setting("latest_baseline_certificate", certificate)
    log_event(
        "baseline.checked",
        {key: value for key, value in certificate.items() if key != "routes"},
        "system",
    )
    return certificate


_COMPILER_ID_CACHE_LOCK = threading.Lock()
_COMPILER_ID_CACHE: dict[str, str] = {}


def _compiler_identity(compiler: str) -> str:
    """Resolve the compiler identity once per server process.

    Native binaries are checked on every relevant job for safety, but repeatedly
    launching ``g++ --version`` adds avoidable latency to solve/clustering handoff.
    """
    key = str(Path(compiler).resolve()) if Path(compiler).exists() else str(compiler)
    with _COMPILER_ID_CACHE_LOCK:
        cached = _COMPILER_ID_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        value = subprocess.check_output(
            [compiler, "--version"], text=True, errors="replace", timeout=10
        ).splitlines()[0]
    except Exception:
        value = str(compiler)
    with _COMPILER_ID_CACHE_LOCK:
        _COMPILER_ID_CACHE[key] = value
    return value


def _compile_cpp(
    source: Path,
    binary: Path,
    label: str,
    reporter: JobReporter | None = None,
    progress_start: float = 0.0,
    progress_end: float = 100.0,
) -> None:
    """Build one native component transactionally.

    The lock is process-wide (not only thread-wide), so setup, direct launch,
    and job-level build checks cannot publish competing builds. Notebook setup
    prepares both engines before opening the UI. Compilation targets a temporary file;
    the runtime binary and fingerprint are published only after a successful
    compiler exit, so a cancelled/failed build can never leave a partial
    executable at the production path.
    """
    if not source.exists():
        raise FileNotFoundError(f"Missing {label} source: {source}")
    source_hash = _sha256_file(source)
    compile_flags = ["-O3", "-DNDEBUG", "-std=c++17", "-pthread"]
    compiler = shutil.which("g++") or "g++"
    compiler_id = _compiler_identity(compiler)
    build_signature = hashlib.sha256(
        "\n".join([source_hash, compiler_id, *compile_flags]).encode("utf-8")
    ).hexdigest()
    binary.parent.mkdir(parents=True, exist_ok=True)
    marker = binary.with_suffix(binary.suffix + ".build.sha256")
    lock_path = binary.with_suffix(binary.suffix + ".build.lock")

    def _cache_matches() -> bool:
        try:
            cached_hash = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
        except OSError:
            cached_hash = ""
        return binary.is_file() and binary.stat().st_size > 0 and cached_hash == build_signature

    if _cache_matches():
        binary.chmod(0o755)
        if reporter:
            reporter.append(f"{label}: build fingerprint matched cached binary ({binary})")
            reporter.heartbeat(progress_end, f"{label} binary ready")
        return

    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        if reporter is None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        else:
            # Cell-1/background warmup may already own this exact component lock.
            # Do not leave the operator staring at a frozen compile stage: wait
            # non-blockingly, keep cancellation responsive, and reuse the atomic
            # binary immediately once the warming process publishes it.
            wait_started = time.monotonic()
            next_notice = 0.0
            while True:
                if _cache_matches():
                    binary.chmod(0o755)
                    reporter.append(f"{label}: reused the exact binary published by background warmup")
                    reporter.heartbeat(progress_end, f"{label} binary ready")
                    return
                try:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    reporter.check_cancelled()
                    elapsed_wait = time.monotonic() - wait_started
                    if elapsed_wait >= next_notice:
                        midpoint = progress_start + max(0.2, (progress_end - progress_start) * 0.35)
                        reporter.heartbeat(
                            midpoint,
                            f"{label} is already warming in the background · {elapsed_wait:.0f}s",
                        )
                        next_notice = elapsed_wait + 2.0
                    time.sleep(0.20)
        # Another process may have completed the same build while we waited.
        if _cache_matches():
            binary.chmod(0o755)
            if reporter:
                reporter.append(f"{label}: build completed by another process; reusing exact fingerprint")
                reporter.heartbeat(progress_end, f"{label} binary ready")
            return

        temp_binary = binary.parent / f".{binary.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        temp_marker = marker.parent / f".{marker.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        temp_binary.unlink(missing_ok=True)
        temp_marker.unlink(missing_ok=True)
        command = [compiler, *compile_flags, str(source), "-o", str(temp_binary)]
        try:
            if reporter:
                code, _ = reporter.run_process(
                    command, cwd=RUNTIME_DIR, timeout_s=900,
                    progress_start=progress_start, progress_end=progress_end,
                    progress_label=f"Compiling {label}",
                )
                if code != 0:
                    raise RuntimeError(f"{label} compilation failed with exit code {code}")
            else:
                result = subprocess.run(command, capture_output=True, text=True, timeout=900)
                if result.returncode != 0:
                    raise RuntimeError(f"{label} compilation failed:\n{result.stdout}\n{result.stderr}")
            if not temp_binary.is_file() or temp_binary.stat().st_size <= 0:
                raise RuntimeError(f"{label} compiler exited successfully but produced no executable")
            temp_binary.chmod(0o755)
            os.replace(temp_binary, binary)
            temp_marker.write_text(build_signature + "\n", encoding="utf-8")
            os.replace(temp_marker, marker)
        finally:
            temp_binary.unlink(missing_ok=True)
            temp_marker.unlink(missing_ok=True)


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_cluster_warm_start_receipt(path: Path) -> dict[str, Any] | None:
    """Read the native warm-start decision from the solver's stderr stream."""
    if not path.is_file():
        return None
    marker = "[ClusterWarmStartReceipt]"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        if marker not in line:
            continue
        payload = line.split(marker, 1)[1].strip()
        receipt: dict[str, Any] = {"observed": True, "raw": line.strip()}
        try:
            tokens = shlex.split(payload)
        except ValueError:
            tokens = payload.split()
        for token in tokens:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            lowered = value.lower()
            if lowered in {"true", "false"}:
                receipt[key] = lowered == "true"
                continue
            try:
                receipt[key] = int(value)
                continue
            except ValueError:
                pass
            try:
                receipt[key] = float(value)
                continue
            except ValueError:
                receipt[key] = value
        return receipt
    return None


def _run_one_clustering(
    method: str,
    seed: int,
    reporter: JobReporter | None = None,
    progress_start: float = 0.0,
    progress_end: float = 100.0,
) -> dict[str, Any]:
    for path in [
        settings.clusters_csv,
        settings.cluster_summary_csv,
        settings.cluster_timing_csv,
        settings.cluster_preview_png,
    ]:
        if path.exists():
            path.unlink()
    # Clustering receives only the number of routes that the current demand can
    # plausibly require. The solver still receives the original K as the maximum
    # available fleet. This prevents an optional warm start from forcing all
    # available vehicles to become non-empty clusters.
    dataset_for_cluster = _load_materialized_dataset()
    maximum_trucks = max(1, int(dataset_for_cluster.get("K_trucks") or 1))
    capacity = max(1.0, float(dataset_for_cluster.get("truck_capacity") or 1.0))
    total_demand = sum(float(item.get("demand", 0.0)) for item in dataset_for_cluster.get("customers") or [])
    active_cluster_count = max(1, min(maximum_trucks, int(math.ceil(total_demand / capacity))))
    cluster_input = RUNTIME_DIR / "cluster_input.txt"
    input_lines = settings.input_txt.read_text(encoding="utf-8").splitlines()
    if len(input_lines) < 3:
        raise ValueError("input.txt is incomplete")
    input_lines[1] = str(active_cluster_count)
    cluster_input.write_text("\n".join(input_lines) + "\n", encoding="utf-8")
    source_receipt = _clustering_source_receipt(
        dataset_for_cluster,
        cluster_input,
        active_cluster_count=active_cluster_count,
    )
    command = [
        str(settings.cluster_bin), "--input", str(cluster_input),
        "--dataset", str(settings.dataset_json), "--out", str(settings.clusters_csv),
        "--summary", str(settings.cluster_summary_csv), "--timing", str(settings.cluster_timing_csv),
        "--mode", method, "--seed", str(seed), "--road_cost", "time",
        "--iters", "100", "--savings_variants", "8", "--savings_noise", "0.025",
        "--savings_light_polish_rounds", "2", "--savings_polish_time_s", "0.50",
        "--savings_check_tw", "true", "--spectral_neighbors", "8",
        "--spectral_sigma_rank", "8", "--spectral_eig_tol", "1e-8",
    ]
    log_path = RUNTIME_DIR / f"cluster_{method}.log"
    started = time.monotonic()
    if reporter:
        code, wall_s = reporter.run_process(
            command,
            cwd=RUNTIME_DIR,
            mirror_path=log_path,
            timeout_s=900,
            progress_start=progress_start,
            progress_end=progress_end,
            progress_label=f"Clustering · {method}",
        )
    else:
        result = subprocess.run(command, capture_output=True, text=True, timeout=900, cwd=RUNTIME_DIR)
        wall_s = time.monotonic() - started
        output = result.stdout + ("\n[stderr]\n" + result.stderr if result.stderr else "")
        log_path.write_text(output, encoding="utf-8")
        code = result.returncode
    if code != 0 or not settings.clusters_csv.exists():
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-5000:] if log_path.exists() else ""
        raise RuntimeError(tail.strip() or f"cluster.cpp exited with code {code}")
    # A successful binary exit is not sufficient if another workflow replaced
    # the source files while clustering was running. Never label such output as
    # belonging to the current plan.
    if (
        _sha256_file(settings.input_txt) != source_receipt["input_sha256"]
        or _sha256_file(settings.dataset_json) != source_receipt["dataset_sha256"]
        or _sha256_file(cluster_input) != source_receipt["cluster_input_sha256"]
    ):
        raise RuntimeError("Clustering input changed while the native engine was running; the result was discarded")
    dataset = _load_materialized_dataset()
    assignments = parse_cluster_assignments()
    validation = validate_clusters(
        assignments,
        dataset,
        expected_clusters=active_cluster_count,
    )
    if not validation["valid"]:
        raise RuntimeError("Cluster assignment failed independent validation: " + json.dumps(validation, ensure_ascii=False))
    summary_rows = _read_csv_rows(settings.cluster_summary_csv)
    timing_rows = _read_csv_rows(settings.cluster_timing_csv)
    effective = method
    if summary_rows:
        effective = str(summary_rows[-1].get("effective_mode") or summary_rows[-1].get("mode") or method)
    accepted_aliases = {"kmeans": "balanced_kmeans"}
    expected_effective = accepted_aliases.get(method, method)
    if effective != expected_effective:
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-2500:] if log_path.exists() else ""
        raise RuntimeError(
            f"cluster.cpp requested {method!r} but internally fell back to {effective!r}. "
            "The attempt was rejected instead of being mislabeled as successful.\n" + tail
        )
    # Preview generation is presentation work. Keep it lightweight and non-fatal.
    preview_url = None
    try:
        generate_cluster_preview(assignments, validation, settings.cluster_preview_png, effective)
        if settings.cluster_preview_png.exists():
            preview_url = _runtime_artifact_url(settings.cluster_preview_png)
    except Exception as exc:
        if reporter:
            reporter.append(f"Cluster preview warning: {exc}")
    return {
        "requested_method": method,
        "effective_method": effective,
        "maximum_available_trucks": maximum_trucks,
        "active_cluster_count": active_cluster_count,
        "wall_s": round(float(wall_s), 4),
        "validation": validation,
        "summary": summary_rows[-1] if summary_rows else {},
        "timing": timing_rows[-1] if timing_rows else {},
        "source_receipt": source_receipt,
        "current": True,
        "stale": False,
        "preview": preview_url,
        "log": f"/api/artifacts/cluster_{method}.log",
    }


def run_clustering(
    method: str,
    seed: int,
    strict: bool = False,
    reporter: JobReporter | None = None,
    progress_start: float = 0.0,
    progress_end: float = 100.0,
) -> dict[str, Any]:
    method = str(method or "none")
    if method in {"", "none", "off"}:
        for path in [settings.clusters_csv, settings.cluster_summary_csv, settings.cluster_timing_csv]:
            if path.exists():
                path.unlink()
        result = {"requested_method": method, "effective_method": "none", "used": False, "attempts": [], "warning": None}
        set_setting("latest_clustering", result)
        if reporter:
            reporter.heartbeat(progress_end, "Clustering disabled; continuing directly to the solver")
        return result

    _compile_cpp(
        settings.cluster_cpp,
        settings.cluster_bin,
        "cluster",
        reporter=reporter,
        progress_start=progress_start,
        progress_end=min(progress_end, progress_start + max(1.0, (progress_end - progress_start) * 0.2)),
    )
    candidates = [method]
    if method == "auto":
        candidates = ["road_savings", "network_kmedoids", "sweep", "round_robin"]
    attempts = []
    remaining_start = progress_start + max(1.0, (progress_end - progress_start) * 0.2)
    span = max(1.0, progress_end - remaining_start)
    for index, candidate in enumerate(candidates):
        attempt_start = remaining_start + span * index / len(candidates)
        attempt_end = remaining_start + span * (index + 1) / len(candidates)
        try:
            if reporter:
                reporter.append(f"Clustering attempt {index + 1}/{len(candidates)}: {candidate}")
            result = _run_one_clustering(candidate, seed, reporter, attempt_start, attempt_end)
            result.update({"used": True, "attempts": attempts + [{"method": candidate, "status": "passed"}], "warning": None})
            set_setting("latest_clustering", result)
            log_event("clustering.ready", result, "system")
            return result
        except JobCancelled:
            raise
        except Exception as exc:
            attempts.append({"method": candidate, "status": "failed", "error": str(exc)[-1200:]})
            if reporter:
                reporter.append(f"Clustering attempt failed: {candidate}\n{str(exc)[-1200:]}")
    message = "All requested clustering attempts failed independent validation"
    if strict:
        raise RuntimeError(message + ": " + json.dumps(attempts, ensure_ascii=False))
    for path in [settings.clusters_csv, settings.cluster_summary_csv, settings.cluster_timing_csv]:
        if path.exists():
            path.unlink()
    result = {
        "requested_method": method,
        "effective_method": "none",
        "used": False,
        "attempts": attempts,
        "warning": message + "; solver continued without a cluster warm start.",
    }
    set_setting("latest_clustering", result)
    log_event("clustering.fallback", result, "system")
    if reporter:
        reporter.heartbeat(progress_end, "Clustering validation failed; safe fallback to no cluster warm start")
    return result


def _solver_command(
    config: dict[str, Any],
    clustering: dict[str, Any],
    customer_count: int | None = None,
    *,
    run_summary_path: Path | None = None,
) -> list[str]:
    used = bool(clustering.get("used"))
    count = max(1, int(customer_count or config.get("customer_count") or 1))
    policy = dynamic_solver_policy(count, config)

    def value_text(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    command = [
        str(settings.solver_bin),
        "--seed", str(config.get("seed", 777)),
        "--instances", str(policy["effective_instances"]),
        "--objective_mode", str(config.get("objective_mode", "distance")),
        "--time_limit", str(policy["stage_time_s"]),
        "--hard_time_limit_s", str(policy["runtime_s"]),
        "--no_improve_stop_s", str(policy["no_improve_stop_s"]),
        "--budget_scope", "solve",
        "--use_phase_specialized_engine", "true",
        "--hybrid_fast_phase_s", "0",
        "--log_convergence", "true",
        "--convergence_sample_period_s", str(policy["convergence_sample_period_s"]),
        "--convergence_max_rows", str(policy["convergence_max_rows"]),
        "--run_summary_csv", str(run_summary_path or settings.run_summary_csv),
        "--use_time_window", "true" if config.get("use_time_window", True) else "false",
        "--route_start_time_s", str(float(config.get("route_start_time_s", 8 * 3600))),
        "--allow_multi_trip", "true" if config.get("allow_multi_trip", False) else "false",
        "--max_trips_per_truck", str(
            max(1, int(config.get("max_trips_per_truck", 3)))
            if config.get("allow_multi_trip", False) else 1
        ),
        "--metric", "road",
    ]
    # Emit only explicit Advanced overrides. Use the schema-backed flag mapping
    # rather than manufacturing --<key> names so evidence always reflects the
    # exact C++ CLI contract.
    command.extend(_advanced_solver_tokens(policy["advanced_overrides"]))
    command.extend(["--use_cluster_warm_start", "true" if used else "false"])
    if used:
        command.extend(["--clusters_csv", str(settings.clusters_csv)])
    # Append only validated unmanaged extras after all application-owned flags.
    # Duplicate managed argv entries are rejected by validate_extra_solver_args(),
    # keeping the evidence command unambiguous.
    extra = validate_extra_solver_args(config.get("extra_args", ""))
    command.extend(extra["tokens"])
    return command


def parse_solver_routes(text: str) -> list[dict[str, Any]]:
    section = text
    for marker in ["TRUCK ROUTE BREAKDOWN (FINAL SOLUTION)", "TRUCK ROUTE BREAKDOWN (USED TRUCKS)"]:
        if marker in text:
            section = text.split(marker)[-1]
            break
    routes: dict[int, list[int]] = {}
    current = None
    for line in section.splitlines():
        match = re.search(r"Truck ID\s*:\s*(\d+)", line, re.I)
        if match:
            current = int(match.group(1)); continue
        path = re.search(r"^\s*Path\s*:\s*(.+?)\s*$", line, re.I)
        if path and current is not None:
            nodes = [int(value) for value in re.findall(r"\d+", path.group(1))]
            if len(nodes) >= 2: routes[current] = nodes
            current = None
    if not routes:
        for line in section.splitlines():
            match = re.search(r"^\s*Truck\s+(\d+)\s*:\s*(.+)$", line, re.I)
            if match:
                nodes = [int(value) for value in re.findall(r"\d+", match.group(2))]
                if len(nodes) >= 2: routes[int(match.group(1))] = nodes
    return [{"truck_id": truck, "route_nodes": nodes} for truck, nodes in sorted(routes.items())]


def _all_route_geometries(
    dataset: dict[str, Any],
    parsed: list[dict[str, Any]],
    *,
    routing_context: RoutingContext | None = None,
    precomputed_paths: dict[tuple[int, int], list[int]] | None = None,
    objective_mode: str | None = None,
) -> dict[int, tuple[list[list[float]], float, float]]:
    """Build route geometry, reusing the certificate's shortest-path batch when possible."""
    nodes = {int(node["id"]): node for node in dataset.get("nodes") or []}
    n = int(dataset.get("num_nodes") or len(nodes))
    context = routing_context
    if context is None:
        context = _active_routing_context(
            str(dataset.get("materialization_id") or ""), objective_mode
        )
    elif objective_mode is not None and context.objective_mode != str(objective_mode):
        context = None
    paths = precomputed_paths or {}

    if context is not None and context.materialization_id == str(dataset.get("materialization_id") or ""):
        best = context.best_edges
        def reconstruct(source: int, target: int) -> list[int]:
            cached = paths.get((int(source), int(target)))
            if cached:
                return cached
            return context.reconstruct(int(source), int(target)) or [int(source), int(target)]
    else:
        best: dict[tuple[int, int], dict[str, Any]] = {}
        for edge in dataset.get("edges") or []:
            u, v = int(edge["u"]), int(edge["v"])
            key = (u, v)
            weight = max(0.000001, float(edge.get("travel_time_s", 1.0)))
            if key not in best or weight < float(best[key].get("travel_time_s", math.inf)):
                best[key] = edge
        if not best:
            return {int(route["truck_id"]): ([], 0.0, 0.0) for route in parsed}
        rows = np.fromiter((key[0] for key in best), dtype=np.int64)
        cols = np.fromiter((key[1] for key in best), dtype=np.int64)
        weights = np.fromiter(
            (max(0.000001, float(edge.get("travel_time_s", 1.0))) for edge in best.values()),
            dtype=np.float64,
        )
        matrix = csr_matrix((weights, (rows, cols)), shape=(n, n))
        sources = sorted({int(node) for route in parsed for node in list(route.get("route_nodes") or [])[:-1]})
        if not sources:
            return {int(route["truck_id"]): ([], 0.0, 0.0) for route in parsed}
        _, predecessors = sparse_dijkstra(
            matrix, directed=True, indices=np.asarray(sources, dtype=np.int64), return_predecessors=True
        )
        source_row = {source: index for index, source in enumerate(sources)}
        def reconstruct(source: int, target: int) -> list[int]:
            if source == target:
                return [source]
            row = source_row.get(source)
            if row is None:
                return [source, target]
            path = [target]
            current = target
            for _ in range(n + 1):
                previous = int(predecessors[row, current])
                if previous < 0:
                    return [source, target]
                path.append(previous)
                current = previous
                if current == source:
                    path.reverse()
                    return path
            return [source, target]

    result: dict[int, tuple[list[list[float]], float, float]] = {}
    for route in parsed:
        coords: list[list[float]] = []
        distance_m = 0.0
        travel_time_s = 0.0
        route_nodes = [int(value) for value in route.get("route_nodes") or []]
        for source, target in zip(route_nodes, route_nodes[1:]):
            path = reconstruct(source, target)
            for u, v in zip(path, path[1:]):
                edge = best.get((u, v))
                if edge:
                    segment = edge.get("geometry") or [
                        [float(nodes[u]["lat"]), float(nodes[u]["lon"])],
                        [float(nodes[v]["lat"]), float(nodes[v]["lon"])],
                    ]
                    segment = [[float(point[0]), float(point[1])] for point in segment]
                    if coords and segment and coords[-1] == segment[0]:
                        coords.extend(segment[1:])
                    else:
                        coords.extend(segment)
                    distance_m += float(edge.get("length_m", 0.0))
                    travel_time_s += float(edge.get("travel_time_s", 0.0))
                elif v in nodes:
                    if not coords and u in nodes:
                        coords.append([float(nodes[u]["lat"]), float(nodes[u]["lon"])])
                    coords.append([float(nodes[v]["lat"]), float(nodes[v]["lon"])])
        result[int(route["truck_id"])] = (coords, distance_m, travel_time_s)
    return result


def _assert_route_publication_input_current(
    dataset: dict[str, Any], *, objective_mode: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Reject a route commit if its materialized routing contract is no longer live.

    This is intentionally checked both before route construction and immediately
    before publication to close the small edit-vs-commit race after a long solve.
    At the final boundary ``conn`` is the same BEGIN IMMEDIATE transaction that
    mints the route version, so a settings mutation cannot slip between the check
    and commit. Search-only tuning changes remain allowed, while objective_mode is
    separately pinned because it changes shortest-path semantics without requiring
    graph rematerialization.
    """
    if conn is None:
        active = dict(get_setting("active_input_state") or {})
    else:
        row = conn.execute(
            "SELECT value_json FROM app_settings WHERE key='active_input_state'"
        ).fetchone()
        try:
            active = dict(json.loads(row["value_json"]) if row else {})
        except Exception:
            active = {}
    materialization_id = str(dataset.get("materialization_id") or "")
    if active.get("current") is not True:
        raise RuntimeError("The routing input changed before this route could be published; run Optimize again")
    if not materialization_id or str(active.get("materialization_id") or "") != materialization_id:
        raise RuntimeError("The routing input changed before this route could be published; run Optimize again")
    expected_dataset_sha = str(active.get("dataset_sha256") or "")
    if expected_dataset_sha and (not settings.dataset_json.is_file() or _sha256_file(settings.dataset_json) != expected_dataset_sha):
        raise RuntimeError("The materialized dataset changed before route publication; run Optimize again")
    expected_input_sha = str(active.get("input_sha256") or "")
    if expected_input_sha and (not settings.input_txt.is_file() or _sha256_file(settings.input_txt) != expected_input_sha):
        raise RuntimeError("The native solver input changed before route publication; run Optimize again")
    if objective_mode is not None:
        if conn is None:
            solver_settings = dict(get_setting("solver") or {})
        else:
            row = conn.execute(
                "SELECT value_json FROM app_settings WHERE key='solver'"
            ).fetchone()
            try:
                solver_settings = dict(json.loads(row["value_json"]) if row else {})
            except Exception:
                solver_settings = {}
        current_objective = str(solver_settings.get("objective_mode") or "distance")
        if current_objective != str(objective_mode):
            raise RuntimeError(
                "The optimization objective changed before this route could be published; "
                "run Optimize again"
            )
    return active


def publish_routes(
    job_id: int, parsed: list[dict[str, Any]], *,
    solution_source: str = "cpp_optimizer", metadata: dict[str, Any] | None = None,
    routing_context: RoutingContext | None = None,
    precomputed_paths: dict[tuple[int, int], list[int]] | None = None,
    settings_revision: dict[str, int] | None = None,
) -> dict[str, Any]:
    dataset = _load_materialized_dataset()
    contract = dict(dataset.get("routing_contract") or {})
    metadata_payload = dict(metadata or {})
    validation = dict(metadata_payload.get("candidate_validation") or {})
    baseline_metadata = dict(metadata_payload.get("baseline_certificate") or {})
    solver = get_setting("solver") or {}
    objective_mode = str(
        validation.get("objective_mode")
        or baseline_metadata.get("objective_mode")
        or solver.get("objective_mode")
        or "distance"
    )
    _assert_route_publication_input_current(dataset, objective_mode=objective_mode)
    route_start_time_s = float(contract.get("route_start_time_s", solver.get("route_start_time_s", 8 * 3600)))
    use_time_window = bool(contract.get("use_time_window", solver.get("use_time_window", True)))
    if routing_context is not None and routing_context.objective_mode != objective_mode:
        # Never reuse an objective-specific predecessor forest across a settings
        # change. Rebuild from the same immutable materialized graph instead.
        routing_context = None
    if routing_context is None:
        routing_context = _active_routing_context(
            str(dataset.get("materialization_id") or ""), objective_mode
        )
    if routing_context is None:
        routing_context = routing_context_for_dataset(dataset, objective_mode)
    node_lookup = {int(node["id"]): node for node in dataset["nodes"]}
    customer_lookup = {int(customer["node"]): customer for customer in dataset["customers"]}
    routes, total_visits = [], 0
    geometry_by_truck = _all_route_geometries(
        dataset, parsed, routing_context=routing_context, precomputed_paths=precomputed_paths,
        objective_mode=objective_mode,
    )
    for route in parsed:
        route_nodes = [int(node) for node in route["route_nodes"]]
        schedule = build_route_schedule(
            dataset,
            route_nodes,
            routing_context,
            objective_mode=objective_mode,
            route_start_time_s=route_start_time_s,
            use_time_window=use_time_window,
        )
        if not schedule.get("feasible"):
            raise RuntimeError(
                f"Truck {route.get('truck_id')} schedule failed the independent route-commit check: "
                f"{schedule.get('reason') or 'unknown reason'}"
            )
        schedule_by_sequence = {
            int(item["sequence"]): item for item in schedule.get("stops") or []
        }
        stops = []
        for sequence, node_id in enumerate(route_nodes):
            if node_id not in node_lookup:
                raise RuntimeError(f"Solver route references unknown node {node_id}")
            node = node_lookup[node_id]
            customer = customer_lookup.get(node_id)
            orders = customer.get("orders", []) if customer else []
            timing = dict(schedule_by_sequence.get(sequence) or {})
            timing.pop("sequence", None)
            timing.pop("node_id", None)
            stops.append({
                "sequence": sequence, "node_id": node_id,
                "kind": "depot" if node_id == dataset["depot"] else "customer",
                "lat": node["lat"], "lon": node["lon"], "orders": orders,
                "demand": customer.get("demand", 0) if customer else 0,
                "service_s": customer.get("service_time_s", 0) if customer else 0,
                "earliest": customer.get("earliest", 0) if customer else 0,
                "latest": customer.get("latest", 86400) if customer else 86400,
                **timing,
            })
            total_visits += len(orders)
        geometry, distance_m, travel_time_s = geometry_by_truck.get(
            int(route["truck_id"]), ([], 0.0, 0.0)
        )
        routes.append({
            "truck_id": route["truck_id"], "route_nodes": route_nodes,
            "stops": stops, "geometry": geometry, "distance_m": distance_m,
            "travel_time_s": travel_time_s,
            "route_start_time_s": schedule["route_start_time_s"],
            "finish_time_s": schedule["finish_time_s"],
            "duration_s": schedule["duration_s"],
            "service_time_s": schedule["service_time_s"],
            "waiting_time_s": schedule["waiting_s"],
            "trip_count": schedule["trip_count"],
            "objective_mode": objective_mode,
            "objective": schedule["objective"],
        })
    optimizer_completed = str(solution_source) == "cpp_optimizer"
    payload = {
        "created_at": utc_now(), "source_job_id": job_id,
        "solution_source": str(solution_source),
        "plan_status": {
            "scope": "route_version_creation",
            "phase": "optimized" if optimizer_completed else "prepared",
            "optimization_completed": optimizer_completed,
            "optimization_outcome": (
                "improved_route_published" if optimizer_completed else "not_started"
            ),
            "meaning": (
                "native C++ search completed and this feasible candidate improved the current objective"
                if optimizer_completed
                else "independently feasible initial route; native C++ search has not completed yet"
            ),
        },
        "approved_closure_count": len(_approved_closures()), "routes": routes,
        # objective_mode is a decision/search setting and intentionally does not
        # invalidate the materialized graph. Publish the objective actually used
        # for this route rather than a potentially older dataset snapshot value.
        "routing_contract": {**contract, "objective_mode": objective_mode},
        "metadata": metadata_payload,
    }
    # Re-check at the actual commit boundary. Route geometry/schedule reconstruction
    # can take non-trivial time on a large directed graph, and an operator edit in
    # that window must not resurrect an obsolete route as current.
    _assert_route_publication_input_current(dataset, objective_mode=objective_mode)

    # Publish the database route version, route_state, closure linkage, and the
    # human-readable routes.json snapshot as one logical generation. The
    # process-local input-publication lock also prevents input.txt/dataset.json
    # from being swapped by a concurrent closure/scenario materialization while
    # this cross-resource commit is in flight.
    publication_time = utc_now()
    version_id = 0
    closure_revision = 0
    with _INPUT_PUBLICATION_LOCK:
        previous_routes_bytes = settings.routes_json.read_bytes() if settings.routes_json.is_file() else None
        try:
            with connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                # Repeat the identity test *inside the write transaction*. If a
                # plan/fleet/closure mutation committed just before BEGIN, this
                # sees it. If it starts after BEGIN, SQLite serializes it after
                # this publication, at which point that mutation marks the route
                # stale as intended.
                active_input = _assert_route_publication_input_current(
                    dataset, objective_mode=objective_mode, conn=conn
                )
                revision_row = conn.execute(
                    "SELECT value_json FROM app_settings WHERE key='closure_revision'"
                ).fetchone()
                try:
                    revision_payload = json.loads(revision_row["value_json"]) if revision_row else {}
                except Exception:
                    revision_payload = {}
                closure_revision = int((revision_payload or {}).get("revision", 0))

                cur = conn.execute(
                    "INSERT INTO route_versions(created_at,source_job_id,route_count,customer_count,payload_json) VALUES(?,?,?,?,?)",
                    (publication_time, job_id, len(routes), total_visits, "{}"),
                )
                version_id = int(cur.lastrowid)
                payload["version_id"] = version_id
                final_payload_json = json.dumps(payload, ensure_ascii=False)
                conn.execute(
                    "UPDATE route_versions SET payload_json=? WHERE id=?",
                    (final_payload_json, version_id),
                )
                route_state_payload = _fresh_route_state_payload(
                    version_id, job_id, solution_source, settings_revision,
                    active_input=active_input, closure_revision=closure_revision, now=publication_time,
                )
                conn.execute(
                    """
                    INSERT INTO app_settings(key,value_json,updated_at) VALUES('route_state',?,?)
                    ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at
                    """,
                    (json.dumps(route_state_payload, ensure_ascii=False), publication_time),
                )
                conn.execute(
                    "UPDATE closures SET route_version_after=?,reroute_message=? "
                    "WHERE status='approved' AND (route_version_after IS NULL OR route_version_after<?)",
                    (version_id, f"Applied in route version {version_id}", version_id),
                )
                _atomic_write_bundle({
                    settings.routes_json: json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
                })
        except Exception:
            try:
                if previous_routes_bytes is None:
                    settings.routes_json.unlink(missing_ok=True)
                else:
                    temp_restore = settings.routes_json.with_name(
                        f".{settings.routes_json.name}.restore-{os.getpid()}-{time.monotonic_ns()}"
                    )
                    temp_restore.write_bytes(previous_routes_bytes)
                    os.replace(temp_restore, settings.routes_json)
            except OSError:
                pass
            raise

    # Audit logging is evidence, not part of route safety.  A transient logging
    # failure must not report the already-atomically-published route as failed.
    try:
        log_event(
            "routes.published",
            {
                "version_id": version_id, "routes": len(routes),
                "solution_source": solution_source, "closure_revision": closure_revision,
            },
            "system",
        )
    except Exception:
        pass
    return payload


def _run_convergence_analyzer(
    log_path: Path,
    *,
    source_job_id: int | None = None,
    analysis_job_id: int | None = None,
    reporter: JobReporter | None = None,
    progress_start: float = 5.0,
    progress_end: float = 90.0,
) -> dict[str, Any]:
    if not settings.convergence_csv.is_file() or settings.convergence_csv.stat().st_size <= 1:
        return {"available": False, "warning": "solver did not produce a usable convergence.csv"}
    source_sha256 = _sha256_file(settings.convergence_csv)
    source_bytes = settings.convergence_csv.stat().st_size
    env = os.environ.copy()
    env["SOLVER_RUN_DIR"] = str(RUNTIME_DIR)
    analyzer_log = RUNTIME_DIR / "convergence_analyzer.log"
    command = [os.sys.executable, str(settings.convergence_analyzer)]
    if reporter is not None:
        code, analyzer_wall_s = reporter.run_process(
            command,
            cwd=RUNTIME_DIR,
            env=env,
            mirror_path=analyzer_log,
            timeout_s=900,
            expected_s=35,
            progress_start=progress_start,
            progress_end=progress_end,
            progress_label="Building convergence figures",
        )
    else:
        started = time.monotonic()
        result = subprocess.run(
            command,
            cwd=RUNTIME_DIR, env=env, capture_output=True, text=True, timeout=900,
        )
        analyzer_wall_s = time.monotonic() - started
        code = result.returncode
        analyzer_log.write_text(result.stdout + "\n[stderr]\n" + result.stderr, encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n[CONVERGENCE ANALYZER]\n" + result.stdout[-6000:] + "\n")
            if result.stderr:
                handle.write("[analyzer stderr]\n" + result.stderr[-4000:] + "\n")
    if not settings.convergence_csv.is_file() or _sha256_file(settings.convergence_csv) != source_sha256:
        raise RuntimeError("convergence.csv changed while its report was being built; the report was rejected")
    summary = convergence_summary(include_points=False)
    summary["analyzer_exit_code"] = code
    summary["analyzer_wall_s"] = round(float(analyzer_wall_s), 3)
    summary["analyzer_log"] = _runtime_artifact_url(analyzer_log)
    receipt = dict(summary.get("source_receipt") or {})
    receipt.update({
        "sha256": source_sha256,
        "short_sha256": source_sha256[:12],
        "bytes": int(source_bytes),
        "source_job_id": source_job_id or receipt.get("solver_job_id"),
        "analysis_job_id": analysis_job_id,
        "analyzed_at": utc_now(),
    })
    summary["source_receipt"] = receipt
    if code != 0:
        summary["warning"] = "The solver result is valid, but the full notebook convergence report could not be completed."
    return summary


def _network_progress_adapter(reporter: JobReporter, start: float, end: float):
    # Each phase owns a band. Within long osmium/OSMnx phases, measured elapsed
    # time advances smoothly but never claims completion before the command exits.
    bands = {
        "stage_source": (0.00, 0.12),
        "cache": (0.12, 0.96),
        "extract": (0.12, 0.36),
        "filter": (0.36, 0.48),
        "convert": (0.48, 0.60),
        "graph": (0.60, 0.94),
        "complete": (0.97, 0.99),
    }
    last_phase = {"value": None}

    def callback(info: dict[str, Any]) -> None:
        reporter.check_cancelled()
        phase = str(info.get("phase") or "working")
        lo, hi = bands.get(phase, (0.02, 0.10))
        done = float(info.get("done") or 0.0)
        total = float(info.get("total") or 0.0)
        elapsed = float(info.get("elapsed_s") or 0.0)
        indeterminate = False
        if info.get("phase_complete"):
            ratio = 1.0
        elif total > 0:
            ratio = max(0.0, min(0.97, done / total))
        elif elapsed > 0:
            # Elapsed time proves liveness, not completion. Hold the verified
            # phase boundary and let the UI animate an indeterminate bar.
            ratio = 0.0
            indeterminate = True
        else:
            ratio = 0.0
        local = lo + (hi - lo) * ratio
        progress = start + (end - start) * local
        message = str(info.get("message") or phase.replace("_", " ").title())
        if last_phase["value"] != phase:
            last_phase["value"] = phase
            reporter.append(f"OSM phase: {phase} · {message}")
        reporter.heartbeat(
            progress,
            message,
            data={
                "osm_phase": phase,
                "phase_label": message,
                "done": int(done),
                "total": int(total),
                "elapsed_s": round(elapsed, 2),
                "rate_bps": round(float(info.get("rate_bps") or 0.0), 2),
                "eta_s": round(float(info.get("eta_s")), 2) if info.get("eta_s") is not None else None,
                "phase_ratio": round(ratio, 3),
                "phase_progress": round(ratio * 100.0, 1) if not indeterminate else None,
                "progress_kind": "indeterminate" if indeterminate else "measured",
                "indeterminate": indeterminate,
            },
        )

    return callback


def _diagnose_solver_failure(output: str, instance_summary: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    text = str(output or "")
    lower = text.lower()
    feasibility = dict(instance_summary.get("feasibility") or {})
    if "no hard-feasible candidate" in lower or "no feasible candidate" in lower or "best=n/a" in lower:
        recommendations = []
        if config.get("use_time_window", True):
            recommendations.append("Use Open day for generated scenarios or verify real work-point time windows")
        if float(feasibility.get("stops_per_truck", 0.0)) > 35:
            recommendations.append("Increase trucks or reduce work points per run")
        recommendations.append("Try No clustering or Road Savings if a cluster warm start is too restrictive")
        return {
            "code": "NO_HARD_FEASIBLE_ROUTE",
            "title": "No route satisfied every hard constraint",
            "message": (
                "The road graph and capacity checks passed, but the solver could not construct a "
                "hard-feasible route before the deadline. This is usually caused by time windows, "
                "service workload, or too many stops per truck—not by regional road-source loading."
            ),
            "recommendations": recommendations,
            "feasibility": feasibility,
        }
    if "hard time limit reached" in lower:
        return {
            "code": "SOLVER_DEADLINE_WITHOUT_ROUTE",
            "title": "Solver deadline reached without a validated route",
            "message": "Increase the solver runtime or simplify the scenario; automatic tuning will keep the work-point-size tier consistent.",
            "recommendations": ["Reduce work points", "Increase available trucks", "Disable heavy research operators"],
            "feasibility": feasibility,
        }
    return {
        "code": "SOLVER_PROCESS_FAILED",
        "title": "Solver process failed",
        "message": "Inspect the true raw console for the exact C++ exit reason.",
        "recommendations": [],
        "feasibility": feasibility,
    }


def run_solve_job(
    job_id: int,
    rebuild_network: bool = False,
    *,
    publish_baseline: bool = True,
    retain_baseline_on_failure: bool = True,
    solver_config: dict[str, Any] | None = None,
    fleet_config: dict[str, Any] | None = None,
    settings_revision: dict[str, int] | None = None,
) -> None:
    """Prepare a feasible initial plan, then run C++ as the optimizer.

    A valid input is not a guarantee that a stochastic optimizer will find a hard-
    feasible solution within a finite budget. FleetRoute therefore separates the
    deterministic initial plan from optimization completion. A solver job is only
    successful after the native run and its independent commit gate both succeed.
    """
    log_path = RUNTIME_DIR / f"job_{job_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"FLEETROUTE PRODUCT-GRADE OPTIMIZATION JOB #{job_id}\n"
        f"Started: {utc_now()}\n"
        + "=" * 88
        + "\n",
        encoding="utf-8",
    )
    reporter = JobReporter(job_id, log_path, stage_count=7)
    update_job(job_id, status="running", started_at=utc_now(), message="Starting verified optimization")
    baseline: dict[str, Any] = {"feasible": False}
    baseline_version: int | None = None
    protected_route: dict[str, Any] | None = None
    protected_route_version: int | None = None
    protected_validation: dict[str, Any] = {"ok": False, "errors": ["not evaluated"]}
    artifacts_promoted = False
    attempt_dir = RUNTIME_DIR / "solver-attempts" / f"job_{job_id}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    attempt_stdout = attempt_dir / "solver_output.txt"
    attempt_stderr = attempt_dir / "solver_stderr.txt"
    attempt_invocation = attempt_dir / "solver_invocation.json"
    attempt_convergence = attempt_dir / "convergence.csv"
    attempt_run_summary = attempt_dir / "run_summary.csv"
    transaction: dict[str, Any] = {
        "version": 1,
        "job_id": int(job_id),
        "status": "preparing",
        "started_at": utc_now(),
        "attempt_workspace": str(attempt_dir),
        "public_artifact_policy": "last_complete_valid_run",
        "route_policy": "keep_current_route_until_strictly_better_valid_candidate",
        "protected_route_version": None,
        "route_preserved": False,
        "evidence_preserved": True,
        "artifacts_promoted": False,
        "private_attempt_retention": "20 most recent solver jobs",
    }

    def update_transaction(status: str, **fields: Any) -> None:
        transaction.update(fields)
        transaction["status"] = status
        transaction["updated_at"] = utc_now()
        set_setting("solver_transaction", transaction)
        reporter.merge_result({"transaction": transaction})

    update_transaction("preparing")
    # Freeze the operating contract before any network/materialization/compile
    # work. A user edit made after clicking Optimize belongs to the next run and
    # cannot silently alter this job halfway through.
    config = json.loads(json.dumps(
        solver_config if solver_config is not None else (get_setting("solver") or {})
    ))
    fleet_snapshot = json.loads(json.dumps(
        fleet_config if fleet_config is not None else (get_setting("fleet") or {})
    ))
    raw_revision = settings_revision if settings_revision is not None else _settings_revision()
    revision_snapshot = {
        "fleet": int(raw_revision.get("fleet", 0)),
        "solver": int(raw_revision.get("solver", 0)),
    }
    reporter.append(
        "CLICK-TIME SETTINGS SNAPSHOT\n"
        + json.dumps(
            {
                "revision": revision_snapshot,
                "fleet": fleet_snapshot,
                "solver": config,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    try:
        with _SOLVE_LOCK:
            reporter.check_cancelled()
            # Capture the exact published state before materialization.  It is
            # only eligible for protection if the post-materialization source
            # signature proves that plan, fleet, graph, and closures are equal.
            prior_route_state = dict(get_setting("route_state") or {})
            prior_active_input = dict(get_setting("active_input_state") or {})
            prior_route = latest_route_version()

            if rebuild_network or not GRAPH_STORE.available():
                reporter.stage(
                    "network",
                    "Operating road graph",
                    1,
                    2,
                    "Preparing or restoring the local operating road graph",
                )
                build_base_network(
                    progress=_network_progress_adapter(reporter, 2, 14),
                    include_overview=False,
                )
            else:
                reporter.stage(
                    "network",
                    "Operating road graph",
                    1,
                    6,
                    "Using the active in-memory road graph",
                )
                reporter.heartbeat(10, "Operating graph ready from memory")

            reporter.stage(
                "instance",
                "Exact solver input",
                2,
                12,
                "Applying road closures and materializing input.txt",
            )
            instance_summary = materialize_solver_instance(
                fleet_override=fleet_snapshot,
                solver_override=config,
            )
            active_input = dict(get_setting("active_input_state") or {})
            prior_version = int((prior_route or {}).get("id") or 0)
            state_version = int(prior_route_state.get("route_version") or 0)
            prior_signature = str(
                prior_route_state.get("source_signature")
                or prior_active_input.get("source_signature")
                or ""
            )
            current_signature = str(active_input.get("source_signature") or "")
            protection_checks = {
                "published_route_exists": bool(prior_route),
                "route_marked_current": prior_route_state.get("stale") is False,
                "prior_input_marked_current": prior_active_input.get("current") is True,
                "route_version_matches": prior_version > 0 and prior_version == state_version,
                "source_signature_present": bool(prior_signature and current_signature),
                "source_signature_matches": bool(prior_signature and prior_signature == current_signature),
                "route_payload_present": bool((prior_route or {}).get("payload", {}).get("routes")),
            }
            # Provenance hashes make the fast eligibility receipt stronger, but
            # old databases may predate those fields. A route marked current is
            # therefore treated as a *candidate* for protection when its version
            # and payload agree; it is never trusted blindly. The independent
            # exact road/capacity/time-window validator below makes the final
            # decision before any baseline can replace it.
            protection_candidate = all(
                protection_checks[key]
                for key in (
                    "published_route_exists",
                    "route_marked_current",
                    "route_version_matches",
                    "route_payload_present",
                )
            )
            if protection_candidate:
                protected_route = prior_route
                protected_route_version = prior_version
            update_transaction(
                "running",
                protected_route_version=protected_route_version,
                route_preserved=bool(protected_route_version),
                source_signature=current_signature or None,
                materialization_id=active_input.get("materialization_id"),
                protection_checks=protection_checks,
                protection_candidate=protection_candidate,
            )
            reporter.merge_result({"network": instance_summary})
            reporter.append(
                "SOLVER INSTANCE\n"
                + json.dumps(instance_summary, indent=2, ensure_ascii=False)
            )
            reporter.heartbeat(18, "input.txt, dataset.json, and dataset_summary.json are ready")

            reporter.append(
                "TRANSACTIONAL RERUN PROTECTION\n"
                f"Attempt workspace: {attempt_dir}\n"
                "The public solver artifact bundle remains the last complete valid run until this attempt passes independent validation.\n"
                + (
                    f"Fleet-plan route v{protected_route_version} is protected as the current comparison floor."
                    if protected_route_version
                    else "No current route matched this materialized input; a feasible initial plan may be prepared before optimization."
                )
            )

            reporter.stage(
                "baseline",
                "Initial feasible plan",
                3,
                20,
                "Constructing and independently validating a deterministic starting plan",
            )
            previous_certificate = dict(get_setting("latest_baseline_certificate") or {})
            current_objective_mode = str(config.get("objective_mode", "distance"))
            reusable_context = _active_routing_context(
                instance_summary.get("materialization_id", ""), current_objective_mode
            )
            publish_new_baseline = bool(publish_baseline and protected_route is None)
            expected_multi_trip = bool(config.get("allow_multi_trip", False))
            expected_max_trips = (
                max(1, int(config.get("max_trips_per_truck", 3)))
                if expected_multi_trip else 1
            )
            baseline_contract_matches = bool(
                str(previous_certificate.get("objective_mode") or "") == current_objective_mode
                and abs(
                    float(previous_certificate.get("route_start_time_s") or 0.0)
                    - float(config.get("route_start_time_s", 8 * 3600))
                ) <= 1e-6
                and bool(previous_certificate.get("use_time_window"))
                    == bool(config.get("use_time_window", True))
                and bool(previous_certificate.get("allow_multi_trip")) == expected_multi_trip
                and int(previous_certificate.get("max_trips_per_truck") or 1) == expected_max_trips
            )
            if (
                not publish_new_baseline
                and reusable_context is not None
                and previous_certificate.get("feasible")
                and baseline_contract_matches
                and str(previous_certificate.get("materialization_id") or "")
                    == str(instance_summary.get("materialization_id") or "")
            ):
                baseline = previous_certificate
                baseline["reused_certificate"] = True
                reporter.append(
                    "BASELINE REUSE\n"
                    "Reusing the feasible initial plan and shortest-path context from the current scenario."
                )
            else:
                baseline = build_baseline_certificate(
                    publish_job_id=job_id,
                    publish=publish_new_baseline,
                    retain_routing_context=True,
                    solver_config=config,
                    settings_revision=revision_snapshot,
                )
            baseline_version = baseline.get("published_route_version")
            safe_baseline = {key: value for key, value in baseline.items() if key != "routes"}
            reporter.merge_result({"baseline": safe_baseline})
            reporter.append(
                "INITIAL PLAN VALIDATION\n"
                + json.dumps(safe_baseline, indent=2, ensure_ascii=False)
            )
            if baseline.get("feasible"):
                message = f"Validated initial route ready in {baseline.get('runtime_s', 0):.2f}s"
                if baseline_version:
                    message += f" · route v{baseline_version} is already available"
                reporter.heartbeat(30, message)
            else:
                reporter.heartbeat(
                    24,
                    "The deterministic initial plan could not place every stop; attempting the C++ solver",
                )

            reporter.stage(
                "compile",
                "routing optimizer",
                4,
                32,
                "Checking the precompiled optimizer binary",
            )
            _compile_cpp(
                settings.solver_cpp,
                settings.solver_bin,
                "solver",
                reporter=reporter,
                progress_start=32,
                progress_end=35,
            )

            reporter.stage(
                "clustering",
                "Optional warm start",
                5,
                36,
                f"Selected policy: {config.get('clustering', 'none')}",
            )
            clustering = run_clustering(
                str(config.get("clustering", "none")),
                int(config.get("seed", 777)),
                bool(config.get("clustering_strict", False)),
                reporter=reporter,
                progress_start=36,
                progress_end=42,
            )
            reporter.merge_result({"clustering": clustering})
            reporter.append(
                "CLUSTERING RESULT\n"
                + json.dumps(clustering, indent=2, ensure_ascii=False)
            )

            # Policies are defined by user-visible orders, not the smaller count
            # left after multiple orders happen to share one road-access node.
            customer_count = max(
                1,
                int(
                    instance_summary.get("customer_orders")
                    or instance_summary.get("customer_nodes")
                    or 1
                ),
            )
            dynamic_policy = dynamic_solver_policy(customer_count, config)
            hard_limit = int(dynamic_policy["runtime_s"])
            command = _solver_command(
                config,
                clustering,
                customer_count=customer_count,
                run_summary_path=attempt_run_summary,
            )
            reporter.merge_result({"dynamic_solver_policy": dynamic_policy})
            reporter.append(
                "AUTOMATIC SOLVER POLICY\n"
                + json.dumps(dynamic_policy, indent=2, ensure_ascii=False)
            )
            input_bytes = settings.input_txt.stat().st_size
            input_sha256 = _sha256_file(settings.input_txt)
            dataset_sha256 = _sha256_file(settings.dataset_json)
            watchdog_timeout_s = hard_limit + max(8, min(18, int(round(hard_limit * 0.12))))
            # The native --budget_scope solve clock begins only after directed
            # road-cost preprocessing (dense depot/customer pair costs and
            # candidate lists).  Give that preparation its own hang guard instead
            # of stealing time from the user's search budget.  The post-marker
            # watchdog remains the strict hard-limit-plus-grace contract.
            graph_nodes_for_watchdog = max(0, int(instance_summary.get("nodes") or 0))
            graph_edges_for_watchdog = max(0, int(instance_summary.get("edges") or 0))
            backend_prep_timeout_s = max(
                120,
                min(900, int(round(
                    60.0
                    + 0.0025 * graph_nodes_for_watchdog
                    + 0.0008 * graph_edges_for_watchdog
                    + 0.40 * customer_count
                ))),
            )
            invocation_manifest = {
                "manifest_version": 4,
                "created_at": utc_now(),
                "job_id": job_id,
                "cwd": str(attempt_dir),
                "attempt_workspace": str(attempt_dir),
                "stdin": {
                    "path": str(settings.input_txt),
                    "bytes": input_bytes,
                    "sha256": input_sha256,
                },
                "materialization_contract": {
                    "source_signature": current_signature,
                    "materialization_id": active_input.get("materialization_id"),
                    "input_sha256": input_sha256,
                    "dataset_sha256": dataset_sha256,
                    "source_component_hashes": active_input.get("source_component_hashes") or {},
                },
                "stdout": str(attempt_stdout),
                "stderr": str(attempt_stderr),
                "public_last_completed": {
                    "stdout": str(settings.solver_output),
                    "stderr": str(settings.solver_stderr),
                    "invocation": str(settings.solver_invocation_json),
                    "convergence": str(settings.convergence_csv),
                    "run_summary": str(settings.run_summary_csv),
                    "commit_rule": "replace atomically only after exit 0, independent route validation, complete evidence, and unchanged input",
                },
                "dataset": str(settings.dataset_json),
                "dataset_summary": str(settings.dataset_summary_json),
                "solver_profile": "auto_dynamic",
                "settings_snapshot": {
                    "revision": revision_snapshot,
                    "fleet": fleet_snapshot,
                    "solver": config,
                },
                "customer_count_contract": {
                    "policy_customer_orders": customer_count,
                    "materialized_customer_orders": int(instance_summary.get("customer_orders") or 0),
                    "materialized_customer_nodes": int(instance_summary.get("customer_nodes") or 0),
                    "rule": "dynamic policy uses visible customer orders; shared road nodes never select a lighter tier",
                },
                "dynamic_policy": dynamic_policy,
                "budget_contract": {
                    "requested_search_budget_s": hard_limit,
                    "fill_time_budget": True,
                    "early_stop_no_improve_s": int(dynamic_policy["no_improve_stop_s"]),
                    "watchdog_timeout_s": watchdog_timeout_s,
                    "native_preparation_timeout_s": backend_prep_timeout_s,
                    "watchdog_clock_contract": (
                        "native preparation has a separate hang guard; the user-selected solve budget "
                        "starts at the native BudgetScope receipt, then receives only the fixed shutdown grace"
                    ),
                    "meaning": (
                        "Runtime is user-selected. Stagnation patience is the smaller of the "
                        "customer-tier allowance and max(5 seconds, half-up 50% of runtime)."
                    )
                },
                "attempts": [],
            }

            def persist_invocation() -> None:
                _atomic_write_bundle({
                    attempt_invocation: json.dumps(invocation_manifest, ensure_ascii=False, indent=2) + "\n"
                })

            def file_evidence(path: Path) -> dict[str, Any]:
                if not path.is_file():
                    return {"path": str(path), "exists": False, "bytes": 0, "sha256": None}
                return {
                    "path": str(path),
                    "exists": True,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }

            def record_attempt(name: str, argv: list[str], attempt_config: dict[str, Any], attempt_clustering: dict[str, Any]) -> dict[str, Any]:
                attempt = {
                    "name": name,
                    "created_at": utc_now(),
                    "argv": argv,
                    "display": shlex.join(argv) + " < " + shlex.quote(str(settings.input_txt)),
                    "config": attempt_config,
                    "clustering": {
                        "used": bool(attempt_clustering.get("used")),
                        "effective_method": attempt_clustering.get("effective_method"),
                    },
                    "status": "running",
                }
                invocation_manifest["attempts"].append(attempt)
                persist_invocation()
                return attempt

            def process_timing_values(
                process_timing: dict[str, Any] | None, wall_runtime_s: float
            ) -> tuple[float, float, float]:
                timing = dict(process_timing or {})
                process_runtime_s = float(timing.get("process_elapsed_s") or wall_runtime_s or 0.0)
                governed = timing.get("governed_elapsed_s")
                if timing.get("budget_started") is False:
                    search_runtime_s = 0.0
                elif governed is not None:
                    search_runtime_s = max(0.0, float(governed))
                else:
                    # Compatibility fallback for a child without a budget marker.
                    search_runtime_s = max(0.0, process_runtime_s)
                preparation_runtime_s = max(
                    0.0,
                    float(timing.get("preparation_elapsed_s") or 0.0),
                )
                return process_runtime_s, search_runtime_s, preparation_runtime_s

            def record_outcome(
                attempt: dict[str, Any],
                *,
                exit_code: int | None,
                runtime_s: float,
                parsed_routes: int,
                stdout_path: Path,
                stderr_path: Path,
                process_timing: dict[str, Any] | None = None,
                error: str | None = None,
            ) -> None:
                process_runtime_s, search_runtime_s, preparation_runtime_s = process_timing_values(
                    process_timing, runtime_s
                )
                requested_budget_s = int((attempt.get("config") or {}).get("hard_time_limit_s", 0) or 0)
                attempt.update({
                    "finished_at": utc_now(),
                    "status": (
                        "failed" if error or exit_code not in (0, None)
                        else "completed" if parsed_routes > 0
                        else "completed_no_routes"
                    ),
                    "exit_code": exit_code,
                    # Keep runtime_s as the historical process-wall metric, and
                    # expose search/preparation explicitly so budget accounting is
                    # never distorted by directed-road matrix construction.
                    "runtime_s": round(process_runtime_s, 3),
                    "process_runtime_s": round(process_runtime_s, 3),
                    "search_runtime_s": round(search_runtime_s, 3),
                    "preparation_runtime_s": round(preparation_runtime_s, 3),
                    "requested_budget_s": requested_budget_s,
                    "budget_utilization_pct": round(
                        min(100.0, search_runtime_s / max(1.0, float(requested_budget_s or 1)) * 100.0), 2
                    ),
                    "budget_overrun_s": round(max(0.0, search_runtime_s - float(requested_budget_s)), 3),
                    "parsed_routes": int(parsed_routes),
                    "stdout_evidence": file_evidence(stdout_path),
                    "stderr_evidence": file_evidence(stderr_path),
                })
                if bool((attempt.get("clustering") or {}).get("used")):
                    attempt["cluster_warm_start_receipt"] = (
                        _parse_cluster_warm_start_receipt(stderr_path)
                        or {
                            "observed": False,
                            "accepted": None,
                            "hard_feasible": None,
                            "reason": "receipt_missing",
                        }
                    )
                if error:
                    attempt["error"] = error
                persist_invocation()

            selected_attempt = record_attempt("selected", command, config, clustering)
            reporter.append(
                "SOLVER INVOCATION\n"
                + json.dumps(invocation_manifest, indent=2, ensure_ascii=False)
            )
            reporter.stage(
                "solver",
                "C++ route improvement",
                6,
                44,
                "A validated route remains available while the optimizer searches for an improvement",
            )
            selected_started = time.monotonic()
            dataset_for_validation = _load_materialized_dataset()
            routing_context = _active_routing_context(
                instance_summary.get("materialization_id", ""),
                str(config.get("objective_mode", "distance")),
            )

            def certify_native_routes(routes: list[dict[str, Any]]) -> dict[str, Any]:
                validation_started = time.monotonic()
                if not routes:
                    return {
                        "ok": False,
                        "errors": ["native stdout contained no routes"],
                        "validation_runtime_s": round(time.monotonic() - validation_started, 6),
                    }
                if routing_context is None:
                    return {
                        "ok": False,
                        "errors": ["independent road-path validation context is unavailable"],
                        "validation_runtime_s": round(time.monotonic() - validation_started, 6),
                    }
                receipt = validate_solver_routes(
                    dataset_for_validation,
                    routes,
                    routing_context,
                    objective_mode=str(config.get("objective_mode", "distance")),
                    allow_multi_trip=bool(config.get("allow_multi_trip", False)),
                    max_trips_per_truck=(
                        max(1, int(config.get("max_trips_per_truck", 3)))
                        if config.get("allow_multi_trip", False) else 1
                    ),
                    route_start_time_s=float(config.get("route_start_time_s", 8 * 3600)),
                    use_time_window=bool(config.get("use_time_window", True)),
                )
                receipt["validation_runtime_s"] = round(time.monotonic() - validation_started, 6)
                return receipt

            protected_parsed: list[dict[str, Any]] = []
            if protected_route is not None:
                protected_parsed = [
                    {
                        "truck_id": int(route.get("truck_id", 0)),
                        "route_nodes": [int(node) for node in route.get("route_nodes") or []],
                    }
                    for route in ((protected_route.get("payload") or {}).get("routes") or [])
                ]
                protected_validation = certify_native_routes(protected_parsed)
                reporter.append(
                    "PROTECTED ROUTE RE-CERTIFICATION\n"
                    + json.dumps(
                        {
                            "route_version": protected_route_version,
                            "validation": protected_validation,
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                if not protected_validation.get("ok"):
                    # Compatibility data or changed problem semantics can make a
                    # historically fresh route fail the current independent gate.
                    # In that case it must not be used as an optimization floor.
                    protected_route = None
                    protected_route_version = None
                    protected_parsed = []
                    update_transaction(
                        "running",
                        protected_route_version=None,
                        route_preserved=False,
                        protection_rejected=protected_validation,
                    )
                    if publish_baseline and baseline.get("feasible") and not baseline_version:
                        published_baseline = publish_routes(
                            job_id,
                            list(baseline.get("routes") or []),
                            solution_source="deterministic_baseline",
                            metadata={
                                "baseline_certificate": safe_baseline,
                                "replaced_invalid_protected_route": prior_version,
                            },
                            routing_context=routing_context,
                            settings_revision=revision_snapshot,
                        )
                        baseline_version = int(published_baseline["version_id"])
                        baseline["published_route_version"] = baseline_version
                        safe_baseline["published_route_version"] = baseline_version
                        set_setting("latest_baseline_certificate", baseline)
                        reporter.merge_result({"baseline": safe_baseline})
                else:
                    reporter.merge_result({
                        "protected_route": {
                            "route_version": protected_route_version,
                            "validation": protected_validation,
                        }
                    })

            try:
                code, elapsed_s = reporter.run_process(
                    command,
                    cwd=attempt_dir,
                    stdin_path=settings.input_txt,
                    stdout_mirror_path=attempt_stdout,
                    stderr_mirror_path=attempt_stderr,
                    timeout_s=watchdog_timeout_s,
                    expected_s=max(5, hard_limit),
                    budget_start_marker="[BudgetScope] solve clock started",
                    pre_budget_timeout_s=backend_prep_timeout_s,
                    progress_start=44,
                    progress_end=86,
                    progress_label="Improving the initial fleet plan",
                )
                selected_process_timing = reporter.last_process_timing()
            except Exception as exc:
                selected_process_timing = reporter.last_process_timing()
                record_outcome(
                    selected_attempt, exit_code=None, runtime_s=time.monotonic() - selected_started,
                    parsed_routes=0, stdout_path=attempt_stdout, stderr_path=attempt_stderr,
                    process_timing=selected_process_timing,
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            clustering_warnings: list[str] = []
            if clustering.get("used"):
                native_receipt = _parse_cluster_warm_start_receipt(attempt_stderr)
                if native_receipt is None:
                    native_receipt = {
                        "observed": False,
                        "accepted": None,
                        "hard_feasible": None,
                        "reason": "receipt_missing",
                    }
                    clustering_warnings.append(
                        "The cluster warm-start receipt was missing from native stderr; "
                        "the final route still requires independent commit validation."
                    )
                    reporter.append(
                        "CLUSTER WARM-START RECEIPT MISSING\n"
                        "The solver ran with clustering enabled but emitted no native warm-start receipt."
                    )
                elif native_receipt.get("accepted") is False:
                    clustering_warnings.append(
                        "The native route-safety gate rejected the cluster ordering; "
                        "the solver safely continued from its greedy/savings constructor."
                    )
                    reporter.append(
                        "CLUSTER WARM-START REJECTED SAFELY\n"
                        + json.dumps(native_receipt, indent=2, ensure_ascii=False)
                    )
                else:
                    reporter.append(
                        "CLUSTER WARM-START ACCEPTED\n"
                        + json.dumps(native_receipt, indent=2, ensure_ascii=False)
                    )
                clustering["native_warm_start"] = native_receipt
                set_setting("latest_clustering", clustering)
                reporter.merge_result({"clustering": clustering})
            output = (
                attempt_stdout.read_text(encoding="utf-8", errors="replace")
                if attempt_stdout.exists()
                else ""
            )
            parsed = parse_solver_routes(output) if code == 0 else []
            candidate_validation = certify_native_routes(parsed)
            selected_attempt["route_validation"] = candidate_validation
            if parsed and not candidate_validation.get("ok"):
                reporter.append(
                    "NATIVE ROUTE REJECTED\n"
                    + json.dumps(candidate_validation, indent=2, ensure_ascii=False)
                )
                parsed = []
            selected_process_s, selected_search_s, selected_prep_s = process_timing_values(
                selected_process_timing, elapsed_s
            )
            attempts = [
                {
                    "name": "selected",
                    "exit_code": code,
                    "runtime_s": round(selected_process_s, 3),
                    "process_runtime_s": round(selected_process_s, 3),
                    "search_runtime_s": round(selected_search_s, 3),
                    "preparation_runtime_s": round(selected_prep_s, 3),
                    "validation_runtime_s": round(float(candidate_validation.get("validation_runtime_s") or 0.0), 6),
                    "clustering": clustering.get("effective_method"),
                }
            ]

            # A clustering-specific failure may be retried
            # without clustering, but the retry must use ONLY the unconsumed part
            # of the user's original search budget. Older versions could run a
            # full selected budget and then silently add another 10–24 seconds.
            remaining_budget_s = max(0.0, float(hard_limit) - float(selected_search_s))
            if (
                (code != 0 or not parsed)
                and clustering.get("used")
                and remaining_budget_s >= 5.0
            ):
                first_attempt = attempt_dir / "solver_attempt_with_clustering.txt"
                first_attempt_stderr = attempt_dir / "solver_attempt_with_clustering.stderr.txt"
                if attempt_stdout.exists():
                    shutil.copy2(attempt_stdout, first_attempt)
                    attempt_stdout.unlink()
                if attempt_stderr.exists():
                    shutil.copy2(attempt_stderr, first_attempt_stderr)
                    attempt_stderr.unlink()
                record_outcome(
                    selected_attempt, exit_code=code, runtime_s=elapsed_s, parsed_routes=len(parsed),
                    stdout_path=first_attempt, stderr_path=first_attempt_stderr,
                    process_timing=selected_process_timing,
                )
                rescue = dict(config)
                rescue["instances"] = min(2, max(1, int(config.get("instances", 2))))
                rescue["hard_time_limit_s"] = max(5, int(math.floor(remaining_budget_s)))
                rescue_cluster = {"used": False, "effective_method": "none"}
                reporter.append(
                    "RESCUE RETRY\n"
                    "The selected warm start ended early without a publishable route; "
                    f"retrying without clustering inside the remaining {rescue['hard_time_limit_s']} s of the original budget."
                )
                rescue_command = _solver_command(
                    rescue,
                    rescue_cluster,
                    customer_count=customer_count,
                    run_summary_path=attempt_run_summary,
                )
                rescue_attempt = record_attempt("no-cluster rescue", rescue_command, rescue, rescue_cluster)
                rescue_started = time.monotonic()
                try:
                    code2, elapsed2 = reporter.run_process(
                        rescue_command,
                        cwd=attempt_dir,
                        stdin_path=settings.input_txt,
                        stdout_mirror_path=attempt_stdout,
                        stderr_mirror_path=attempt_stderr,
                        timeout_s=int(rescue["hard_time_limit_s"]) + 10,
                        expected_s=max(5, int(rescue["hard_time_limit_s"])),
                        budget_start_marker="[BudgetScope] solve clock started",
                        pre_budget_timeout_s=backend_prep_timeout_s,
                        progress_start=44,
                        progress_end=86,
                        progress_label="Rescue improvement without clustering",
                    )
                    rescue_process_timing = reporter.last_process_timing()
                except Exception as exc:
                    rescue_process_timing = reporter.last_process_timing()
                    record_outcome(
                        rescue_attempt, exit_code=None, runtime_s=time.monotonic() - rescue_started,
                        parsed_routes=0, stdout_path=attempt_stdout, stderr_path=attempt_stderr,
                        process_timing=rescue_process_timing,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    raise
                output = (
                    attempt_stdout.read_text(encoding="utf-8", errors="replace")
                    if attempt_stdout.exists()
                    else ""
                )
                parsed = parse_solver_routes(output) if code2 == 0 else []
                candidate_validation = certify_native_routes(parsed)
                rescue_attempt["route_validation"] = candidate_validation
                if parsed and not candidate_validation.get("ok"):
                    reporter.append(
                        "RESCUE ROUTE REJECTED\n"
                        + json.dumps(candidate_validation, indent=2, ensure_ascii=False)
                    )
                    parsed = []
                record_outcome(
                    rescue_attempt, exit_code=code2, runtime_s=elapsed2, parsed_routes=len(parsed),
                    stdout_path=attempt_stdout, stderr_path=attempt_stderr,
                    process_timing=rescue_process_timing,
                )
                rescue_process_s, rescue_search_s, rescue_prep_s = process_timing_values(
                    rescue_process_timing, elapsed2
                )
                attempts.append(
                    {
                        "name": "no-cluster rescue",
                        "exit_code": code2,
                        "runtime_s": round(rescue_process_s, 3),
                        "process_runtime_s": round(rescue_process_s, 3),
                        "search_runtime_s": round(rescue_search_s, 3),
                        "preparation_runtime_s": round(rescue_prep_s, 3),
                        "validation_runtime_s": round(float(candidate_validation.get("validation_runtime_s") or 0.0), 6),
                        "clustering": "none",
                    }
                )
                code, elapsed_s = code2, elapsed_s + elapsed2
            else:
                record_outcome(
                    selected_attempt, exit_code=code, runtime_s=elapsed_s, parsed_routes=len(parsed),
                    stdout_path=attempt_stdout, stderr_path=attempt_stderr,
                    process_timing=selected_process_timing,
                )
                if (
                    (code != 0 or not parsed) and clustering.get("used")
                    and remaining_budget_s < 5.0
                ):
                    reporter.append(
                        "RESCUE SKIPPED\n"
                        "The selected attempt consumed the configured search budget; FleetRoute will not silently exceed it with another C++ run."
                    )

            total_search_runtime_s = round(
                sum(float(item.get("search_runtime_s") or 0.0) for item in attempts), 3
            )
            total_preparation_runtime_s = round(
                sum(float(item.get("preparation_runtime_s") or 0.0) for item in attempts), 3
            )
            total_validation_runtime_s = round(
                sum(float(item.get("validation_runtime_s") or 0.0) for item in attempts), 6
            )
            invocation_manifest["completed_at"] = utc_now()
            invocation_manifest["final"] = {
                "attempt": attempts[-1]["name"],
                "exit_code": code,
                "total_runtime_s": round(elapsed_s, 3),
                "total_process_runtime_s": round(elapsed_s, 3),
                "total_search_runtime_s": total_search_runtime_s,
                "total_preparation_runtime_s": total_preparation_runtime_s,
                "total_validation_runtime_s": total_validation_runtime_s,
                "validation_contract": "independent final route certificate using the retained objective-specific road-path context",
                "selected_budget_s": hard_limit,
                "selected_budget_utilization_pct": round(
                    min(100.0, float(selected_attempt.get("search_runtime_s") or 0.0) / max(1.0, float(hard_limit)) * 100.0), 2
                ),
                "selected_budget_overrun_s": round(max(0.0, float(selected_attempt.get("search_runtime_s") or 0.0) - float(hard_limit)), 3),
                "parsed_routes": len(parsed),
                "stdout_evidence": file_evidence(attempt_stdout),
                "stderr_evidence": file_evidence(attempt_stderr),
                "convergence_evidence": file_evidence(attempt_convergence),
                "run_summary_evidence": file_evidence(attempt_run_summary),
            }
            persist_invocation()
            route_summaries = list(baseline.get("route_summaries") or [])
            baseline_distance = float(baseline.get("total_distance_m") or 0.0)
            baseline_travel = sum(float(item.get("travel_time_s") or 0.0) for item in route_summaries)
            baseline_service = sum(float(item.get("service_time_s") or 0.0) for item in route_summaries)
            baseline_waiting = sum(float(item.get("waiting_s") or 0.0) for item in route_summaries)
            objective_mode = str(config.get("objective_mode", "distance"))
            baseline_objective = objective_value(
                objective_mode,
                distance_m=baseline_distance,
                travel_time_s=baseline_travel,
                service_time_s=baseline_service,
                waiting_s=baseline_waiting,
            )
            candidate_objective = float(candidate_validation.get("objective") or math.inf)
            protected_objective = (
                float(protected_validation.get("objective") or math.inf)
                if protected_validation.get("ok")
                else math.inf
            )
            references: list[dict[str, Any]] = []
            if baseline.get("feasible") and math.isfinite(baseline_objective):
                references.append({
                    "source": "deterministic_baseline",
                    "route_version": baseline_version,
                    "objective": baseline_objective,
                })
            if protected_route_version and math.isfinite(protected_objective):
                references.append({
                    "source": "protected_published_route",
                    "route_version": protected_route_version,
                    "objective": protected_objective,
                })
            reference = min(references, key=lambda item: float(item["objective"])) if references else None
            reference_objective = float(reference["objective"]) if reference else math.inf
            comparison_tolerance = max(
                1e-6,
                abs(reference_objective) * 1e-9 if math.isfinite(reference_objective) else 1e-6,
            )

            current_active_input = dict(get_setting("active_input_state") or {})
            current_solver_settings = dict(get_setting("solver") or {})
            decision_objective_still_current = (
                str(current_solver_settings.get("objective_mode") or "distance")
                == str(config.get("objective_mode") or "distance")
            )
            source_still_current = bool(
                current_signature
                and current_active_input.get("current") is True
                and str(current_active_input.get("source_signature") or "") == current_signature
                and _materialization_source_signature() == current_signature
                and settings.input_txt.is_file()
                and settings.dataset_json.is_file()
                and _sha256_file(settings.input_txt) == input_sha256
                and _sha256_file(settings.dataset_json)
                    == str(active_input.get("dataset_sha256") or "")
                and decision_objective_still_current
            )
            bundle_checks = {
                "stdout_nonempty": attempt_stdout.is_file() and attempt_stdout.stat().st_size > 0,
                "stderr_nonempty": attempt_stderr.is_file() and attempt_stderr.stat().st_size > 0,
                "invocation_nonempty": attempt_invocation.is_file() and attempt_invocation.stat().st_size > 0,
                "convergence_nonempty": attempt_convergence.is_file() and attempt_convergence.stat().st_size > 1,
                "run_summary_nonempty": attempt_run_summary.is_file() and attempt_run_summary.stat().st_size > 1,
            }
            bundle_complete = all(bundle_checks.values())
            commit_ready = bool(
                code == 0
                and parsed
                and candidate_validation.get("ok")
                and source_still_current
                and bundle_complete
            )
            candidate_is_better = bool(
                commit_ready
                and (
                    reference is None
                    or candidate_objective < reference_objective - comparison_tolerance
                )
            )
            comparison = {
                "objective_mode": objective_mode,
                "baseline_objective": round(baseline_objective, 6),
                "protected_route_version": protected_route_version,
                "protected_route_objective": (
                    None if not math.isfinite(protected_objective) else round(protected_objective, 6)
                ),
                "publication_reference": reference,
                "candidate_objective": None if not math.isfinite(candidate_objective) else round(candidate_objective, 6),
                "improvement_abs": (
                    None
                    if not math.isfinite(candidate_objective) or not math.isfinite(reference_objective)
                    else round(reference_objective - candidate_objective, 6)
                ),
                "improvement_pct": (
                    None
                    if not math.isfinite(candidate_objective) or not math.isfinite(reference_objective) or reference_objective <= 0
                    else round((reference_objective - candidate_objective) / reference_objective * 100.0, 3)
                ),
                "source_still_current": source_still_current,
                "decision_objective_still_current": decision_objective_still_current,
                "artifact_bundle_complete": bundle_complete,
                "artifact_bundle_checks": bundle_checks,
                "publish_candidate": candidate_is_better,
                "rule": "publish only a complete, independently feasible native run that strictly improves the best current validated objective",
            }
            reporter.append(
                "INDEPENDENT ROUTE VALIDATION\n"
                + json.dumps(
                    {"validation": candidate_validation, "comparison": comparison},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            reporter.merge_result({
                "solver_attempts": attempts,
                "candidate_validation": candidate_validation,
                "objective_comparison": comparison,
            })
            promotion_backups: dict[Path, Path | None] = {}
            if commit_ready:
                promotion, promotion_backups = _atomic_promote_files({
                    attempt_stdout: settings.solver_output,
                    attempt_stderr: settings.solver_stderr,
                    attempt_invocation: settings.solver_invocation_json,
                    attempt_convergence: settings.convergence_csv,
                    attempt_run_summary: settings.run_summary_csv,
                }, retain_previous=candidate_is_better)
                artifacts_promoted = True
                if not candidate_is_better:
                    set_setting("convergence_summary_cached", convergence_summary(include_points=False))
                update_transaction(
                    "evidence_staged_for_route_commit" if candidate_is_better else "evidence_committed",
                    artifacts_promoted=True,
                    evidence_preserved=False,
                    promotion=promotion,
                    artifact_bundle_checks=bundle_checks,
                    candidate_objective=round(candidate_objective, 6),
                )
                reporter.append(
                    ("ATOMIC EVIDENCE STAGE\n" if candidate_is_better else "ATOMIC EVIDENCE COMMIT\n")
                    + json.dumps(promotion, indent=2, ensure_ascii=False)
                )
            else:
                rejection_reasons = []
                if code != 0:
                    rejection_reasons.append(f"native exit code {code}")
                if not candidate_validation.get("ok"):
                    rejection_reasons.append("independent route validation failed")
                if not source_still_current:
                    rejection_reasons.append("input changed while this attempt was running")
                if not bundle_complete:
                    rejection_reasons.append("attempt evidence bundle is incomplete")
                update_transaction(
                    "attempt_rejected_preserved",
                    artifacts_promoted=False,
                    evidence_preserved=True,
                    artifact_bundle_checks=bundle_checks,
                    rejection_reasons=rejection_reasons,
                )
                reporter.append(
                    "ATTEMPT NOT COMMITTED\n"
                    "The prior public evidence bundle remains unchanged.\n"
                    + "\n".join(f"- {reason}" for reason in rejection_reasons)
                )

            def queue_completed_evidence() -> int | None:
                if not config.get("run_convergence_analysis", False):
                    return None
                if artifacts_promoted and settings.convergence_csv.is_file() and settings.convergence_csv.stat().st_size > 1:
                    evidence_id = queue_postprocess_evidence(job_id)
                    reporter.append(
                        f"CONVERGENCE HANDOFF\nCommitted convergence.csv is complete; evidence job #{evidence_id} was queued after the route decision."
                    )
                    return evidence_id
                reporter.append(
                    "CONVERGENCE PRESERVED\nThis attempt was not committed; the last completed convergence.csv and report remain unchanged."
                )
                return None

            if code == 0 and parsed and candidate_is_better:
                reporter.stage(
                    "publish",
                    "Validate and apply optimized routes",
                    7,
                    89,
                    f"Applying {len(parsed)} independently validated truck routes",
                )
                try:
                    published = publish_routes(
                        job_id,
                        parsed,
                        solution_source="cpp_optimizer",
                        metadata={
                            "baseline_route_version": baseline_version,
                            "protected_route_version": protected_route_version,
                            "solver_attempts": attempts,
                            "settings_revision": revision_snapshot,
                            "candidate_validation": candidate_validation,
                            "objective_comparison": comparison,
                        },
                        settings_revision=revision_snapshot,
                    )
                except Exception:
                    rollback = _finish_promoted_files(promotion_backups, rollback=True)
                    artifacts_promoted = False
                    if settings.convergence_csv.is_file():
                        set_setting("convergence_summary_cached", convergence_summary(include_points=False))
                    else:
                        set_setting("convergence_summary_cached", {})
                    update_transaction(
                        "route_commit_rejected_evidence_rolled_back",
                        artifacts_promoted=False, evidence_preserved=True,
                        evidence_rollback=rollback, completed_at=utc_now(),
                    )
                    reporter.append(
                        "ROUTE COMMIT REJECTED · EVIDENCE ROLLED BACK\n"
                        + json.dumps(rollback, indent=2, ensure_ascii=False)
                    )
                    raise
                evidence_finalize = _finish_promoted_files(promotion_backups, rollback=False)
                set_setting("convergence_summary_cached", convergence_summary(include_points=False))
                reporter.append(
                    "ROUTE + EVIDENCE COMMIT FINALIZED\n"
                    + json.dumps(evidence_finalize, indent=2, ensure_ascii=False)
                )
                reporter.heartbeat(97, f"Optimized route version {published['version_id']} applied")
                update_transaction(
                    "committed",
                    artifacts_promoted=True,
                    evidence_preserved=False,
                    route_preserved=False,
                    replaced_route_version=protected_route_version,
                    published_route_version=int(published["version_id"]),
                    route_outcome="strict_improvement_published",
                    completed_at=utc_now(),
                )
                evidence_job_id = queue_completed_evidence()
                result_payload = {
                    "route_version": published["version_id"],
                    "route_count": len(parsed),
                    "solution_source": "cpp_optimizer",
                    "optimizer_improved": True,
                    "solver_runtime_s": round(elapsed_s, 3),
                    "solver_process_runtime_s": round(elapsed_s, 3),
                    "solver_search_runtime_s": total_search_runtime_s,
                    "solver_preparation_runtime_s": total_preparation_runtime_s,
                    "solver_validation_runtime_s": round(float(candidate_validation.get("validation_runtime_s") or 0.0), 6),
                    "network": instance_summary,
                    "clustering": clustering,
                    "baseline_route_version": baseline_version,
                    "protected_route_version": protected_route_version,
                    "evidence_job_id": evidence_job_id,
                    "solver_attempts": attempts,
                    "candidate_validation": candidate_validation,
                    "objective_comparison": comparison,
                    "warnings": clustering_warnings,
                }
                reporter.finish(
                    f"Routing complete · optimized route version {published['version_id']} applied",
                    result_payload,
                )
                log_event("solve.succeeded", {"job_id": job_id, **result_payload}, "system")
                return

            if not source_still_current:
                diagnosis = {
                    "code": "INPUT_CHANGED_DURING_SOLVE",
                    "title": "The plan changed while this attempt was running",
                    "message": "The completed candidate was not committed because its exact plan, fleet, graph, closures, or optimization objective no longer matches the live workspace.",
                    "recommendations": ["Run Optimize again for the current plan"],
                }
            elif code == 0 and candidate_validation.get("ok") and parsed and not bundle_complete:
                diagnosis = {
                    "code": "SOLVER_EVIDENCE_INCOMPLETE",
                    "title": "The native result could not be fully verified",
                    "message": "C++ produced a feasible route, but one or more required stdout/stderr/convergence/summary artifacts were incomplete, so neither route nor public evidence was replaced.",
                    "recommendations": ["Inspect this job's separate stdout and stderr logs"],
                    "artifact_bundle_checks": bundle_checks,
                }
            elif code == 0 and candidate_validation.get("ok") and parsed:
                diagnosis = {
                    "code": "VALID_ROUTE_NOT_BETTER",
                    "title": "The initial plan remains better",
                    "message": "The C++ result was independently feasible but did not improve the selected objective, so the current plan was retained.",
                    "recommendations": [],
                    "comparison": comparison,
                }
            elif code == 0 and candidate_validation.get("errors"):
                diagnosis = {
                    "code": "NATIVE_ROUTE_VALIDATION_FAILED",
                    "title": "Native route failed independent commit checks",
                    "message": "C++ completed, but its stdout route did not satisfy the independent coverage, capacity, depot, or road/time validation contract.",
                    "recommendations": ["Inspect solver_output.txt and solver_stderr.txt"],
                    "validation": candidate_validation,
                }
            else:
                diagnosis = _diagnose_solver_failure(output, instance_summary, config)
            reporter.merge_result({"diagnosis": diagnosis, "solver_exit_code": code})
            reporter.append(
                "SOLVER DIAGNOSIS\n"
                + json.dumps(diagnosis, indent=2, ensure_ascii=False)
            )

            # A retained route is a successful routing result only when the
            # native process itself completed cleanly and the independently
            # validated evidence bundle committed.  On exit/validation/input/
            # evidence failure we still preserve the route, but the job must
            # fail and an initial route must remain merely "prepared".
            if commit_ready and (baseline.get("feasible") or protected_validation.get("ok")) and retain_baseline_on_failure:
                current_route = latest_route_version() or {}
                retained_version = protected_route_version or baseline_version or current_route.get("id")
                retained_route_count = (
                    int(protected_validation.get("route_count") or 0)
                    if protected_route_version
                    else int(baseline.get("active_trucks") or 0)
                )
                retained_source = (
                    str((protected_route or {}).get("payload", {}).get("solution_source") or "published_route")
                    if protected_route_version
                    else "deterministic_baseline"
                )
                optimization_receipt = (
                    _mark_route_optimization_checked(
                        int(retained_version),
                        job_id,
                        revision_snapshot,
                    )
                    if artifacts_promoted and retained_version
                    else None
                )
                update_transaction(
                    "committed_route_preserved" if artifacts_promoted else "attempt_rejected_preserved",
                    artifacts_promoted=artifacts_promoted,
                    evidence_preserved=not artifacts_promoted,
                    route_preserved=bool(protected_route_version),
                    retained_route_version=retained_version,
                    route_outcome="current_route_retained",
                    completed_at=utc_now(),
                )
                evidence_job_id = queue_completed_evidence()
                result_payload = {
                    "route_version": retained_version,
                    "route_count": retained_route_count,
                    "solution_source": retained_source,
                    "optimizer_improved": False,
                    "optimizer_warning": diagnosis,
                    "solver_runtime_s": round(elapsed_s, 3),
                    "solver_process_runtime_s": round(elapsed_s, 3),
                    "solver_search_runtime_s": total_search_runtime_s,
                    "solver_preparation_runtime_s": total_preparation_runtime_s,
                    "solver_validation_runtime_s": round(float(candidate_validation.get("validation_runtime_s") or 0.0), 6),
                    "network": instance_summary,
                    "clustering": clustering,
                    "protected_route_version": protected_route_version,
                    "solver_attempts": attempts,
                    "evidence_job_id": evidence_job_id,
                    "candidate_validation": candidate_validation,
                    "objective_comparison": comparison,
                    "optimization_receipt": optimization_receipt,
                    "warnings": [
                        *clustering_warnings,
                        "The routing optimizer completed but did not improve the independently feasible reference route."
                    ],
                }
                reporter.finish(
                    f"Routing completed; route v{retained_version or '—'} retained because the optimizer produced no improvement",
                    result_payload,
                )
                log_event(
                    "solve.baseline_retained",
                    {"job_id": job_id, **result_payload},
                    "system",
                )
                return

            raise RuntimeError(diagnosis["message"])

    except JobCancelled as exc:
        update_transaction(
            "cancelled_preserved",
            artifacts_promoted=artifacts_promoted,
            evidence_preserved=not artifacts_promoted,
            route_preserved=bool(protected_route_version),
            retained_route_version=protected_route_version or baseline_version,
            completed_at=utc_now(),
        )
        reporter.fail(exc, cancelled=True)
        log_event("solve.cancelled", {"job_id": job_id, "transaction": transaction}, "dispatcher")
    except Exception as exc:
        reporter.append("TRACEBACK\n" + traceback.format_exc())
        update_transaction(
            "failed_preserved" if not artifacts_promoted else "failed_after_evidence_commit",
            artifacts_promoted=artifacts_promoted,
            evidence_preserved=not artifacts_promoted,
            route_preserved=bool(protected_route_version),
            retained_route_version=protected_route_version or baseline_version,
            completed_at=utc_now(),
            failure=f"{type(exc).__name__}: {exc}",
        )
        reporter.fail(exc)
    finally:
        # Release the potentially large predecessor matrix as soon as this solve
        # finishes. It exists only to eliminate duplicate shortest-path batches.
        _set_active_routing_context(None)
        pruned_attempts = _prune_solver_attempt_workspaces(keep=20)
        if pruned_attempts:
            log_event(
                "solve.attempt_workspaces_pruned",
                {"job_id": job_id, "removed": pruned_attempts, "retained": 20},
                "system",
            )

def run_postprocess_evidence_job(job_id: int, source_job_id: int) -> None:
    log_path = RUNTIME_DIR / f"job_{job_id}.log"
    log_path.write_text(f"FLEETROUTE EVIDENCE JOB #{job_id}\nSource solve: #{source_job_id}\n", encoding="utf-8")
    reporter = JobReporter(job_id, log_path, stage_count=3)
    update_job(job_id, status="running", started_at=utc_now(), message="Building non-blocking research evidence")
    try:
        reporter.stage("convergence", "Convergence analysis", 1, 5, "Running integrity checks and publication-ready figures")
        convergence = _run_convergence_analyzer(
            log_path,
            source_job_id=source_job_id,
            analysis_job_id=job_id,
            reporter=reporter,
            progress_start=5,
            progress_end=55,
        )
        set_setting("convergence_summary_cached", convergence)
        reporter.heartbeat(55, "Convergence analysis complete")
        reporter.stage("driver-package", "Driver HTML package", 2, 60, "Generating standalone driver and all-truck HTML")
        driver_zip = create_driver_package()
        reporter.heartbeat(78, "Driver package ready")
        reporter.stage("evidence-package", "Run evidence", 3, 82, "Packaging inputs, outputs, convergence, routes, and figures")
        evidence_zip = create_run_evidence_zip()
        try:
            set_setting("artifact_gallery_cached", list_artifact_gallery())
        except Exception:
            pass
        reporter.finish(
            "Research evidence and standalone driver files are ready",
            {
                "source_job_id": source_job_id,
                "convergence": convergence,
                "driver_package": "/api/artifacts/artifacts/Driver_Operations_Package.zip" if driver_zip else None,
                "run_package": "/api/artifacts/artifacts/FleetRoute_Run_Evidence.zip" if evidence_zip else None,
            },
        )
    except JobCancelled as exc:
        reporter.fail(exc, cancelled=True)
    except Exception as exc:
        reporter.append("TRACEBACK\n" + traceback.format_exc())
        reporter.fail(exc)


def queue_postprocess_evidence(source_job_id: int) -> int:
    job_id = create_job("evidence", f"Post-process evidence for solve #{source_job_id}")
    _EXECUTOR.submit(run_postprocess_evidence_job, job_id, int(source_job_id))
    return job_id


def run_convergence_analysis_job(job_id: int) -> None:
    log_path = RUNTIME_DIR / f"job_{job_id}.log"
    log_path.write_text(f"FLEETROUTE CONVERGENCE REPORT #{job_id}\n", encoding="utf-8")
    reporter = JobReporter(job_id, log_path, stage_count=2)
    update_job(job_id, status="running", started_at=utc_now(), message="Verifying convergence telemetry")
    try:
        reporter.stage(
            "source",
            "Telemetry receipt",
            1,
            5,
            "Hashing the latest raw convergence.csv and matching its solver invocation",
        )
        raw = convergence_summary(include_points=False)
        if not raw.get("available"):
            raise ValueError(raw.get("message") or "No usable convergence.csv is available")
        source_job_id = (raw.get("source_receipt") or {}).get("solver_job_id")
        reporter.append("CONVERGENCE SOURCE RECEIPT\n" + json.dumps(raw.get("source_receipt") or {}, indent=2))
        reporter.stage(
            "figures",
            "Publication figures",
            2,
            12,
            "Verifying the current report or rebuilding it from exact C++ telemetry",
        )
        # The evidence job may already have built a complete report from this exact
        # convergence.csv.  Re-running matplotlib on an identical hash is wasteful
        # (and can be hundreds of MB of transient memory for large traces), so a
        # hash-matched SourceManifest is the cache key.  Any telemetry change makes
        # report_current false and forces a genuine rebuild below.
        if raw.get("report_current"):
            summary = raw
            summary["analyzer_exit_code"] = 0
            summary["analyzer_wall_s"] = 0.0
            summary["report_reused"] = True
            reporter.append(
                "Convergence report reuse: SourceManifest SHA-256 matches the current convergence.csv; "
                "no duplicate analyzer process was started."
            )
            reporter.heartbeat(96, "Verified existing convergence report")
        else:
            summary = _run_convergence_analyzer(
                log_path,
                source_job_id=int(source_job_id) if source_job_id is not None else None,
                analysis_job_id=job_id,
                reporter=reporter,
                progress_start=12,
                progress_end=96,
            )
            summary["report_reused"] = False
        if summary.get("analyzer_exit_code") != 0:
            raise RuntimeError(summary.get("warning") or "Convergence analyzer failed")
        if not summary.get("report_current"):
            raise RuntimeError("The generated figures do not match the current convergence.csv receipt")
        set_setting("convergence_summary_cached", summary)
        try:
            set_setting("artifact_gallery_cached", list_artifact_gallery())
        except Exception:
            pass
        reporter.finish(
            "Convergence report rebuilt from the latest verified solver telemetry",
            {"convergence": summary, "source_job_id": source_job_id},
        )
    except JobCancelled as exc:
        reporter.fail(exc, cancelled=True)
    except Exception as exc:
        reporter.append("TRACEBACK\n" + traceback.format_exc())
        reporter.fail(exc)


def queue_convergence_analysis() -> int:
    active = list_active_jobs(include_evidence=True)
    if active:
        job = active[0]
        raise ValueError(
            f"Job #{job['id']} ({job['kind']}) is already {job['status']}. "
            "Wait for it or cancel it before rebuilding convergence figures."
        )
    if not settings.convergence_csv.is_file() or settings.convergence_csv.stat().st_size <= 1:
        raise ValueError("No raw convergence.csv is available. Run the optimizer once, then build the report here.")
    job_id = create_job("convergence-analysis", "Build convergence figures from the latest solver telemetry")
    _EXECUTOR.submit(run_convergence_analysis_job, job_id)
    return job_id


def run_region_download_job(job_id: int, force: bool = False, region_id: str | None = None) -> None:
    log_path = RUNTIME_DIR / f"job_{job_id}.log"
    log_path.write_text(f"FLEETROUTE REGIONAL OFFLINE DATA #{job_id}\n", encoding="utf-8")
    reporter = JobReporter(job_id, log_path, stage_count=4)
    update_job(job_id, status="running", started_at=utc_now(), message="Reading regional source metadata")

    phase_index = {"metadata": 1, "download": 2, "verify": 3, "complete": 4}
    last_phase = {"value": None}

    def progress(info: dict[str, Any]) -> None:
        reporter.check_cancelled()
        phase = str(info.get("phase") or "metadata")
        done = int(info.get("done") or 0)
        total = int(info.get("total") or 0)
        ratio = min(1.0, done / total) if total else 0.0
        if phase == "metadata":
            pct = 2.0
            label = "Source metadata"
        elif phase == "download":
            # Fresh transfers calculate MD5 in the same byte stream, so network
            # progress now represents both transfer and integrity work.
            pct = 5.0 + 90.0 * ratio
            label = "Download + integrity"
        elif phase == "verify":
            pct = 97.0 + 2.0 * ratio
            label = "Checksum confirmation"
        else:
            pct = 99.5
            label = "Offline source ready"
        message = str(info.get("message") or f"{label} · {pct:.1f}%")
        index = phase_index.get(phase, 1)
        phase_progress = round(ratio * 100.0, 1) if total > 0 else None
        live_data = {
            "phase": phase, "phase_label": label, "done": done, "total": total,
            "phase_progress": phase_progress,
            "elapsed_s": round(float(info.get("elapsed_s") or 0.0), 2),
            "rate_bps": round(float(info.get("rate_bps") or 0.0), 2),
            "eta_s": round(float(info.get("eta_s")), 2) if info.get("eta_s") is not None else None,
            "indeterminate": phase not in {"download", "verify", "complete"} or total <= 0,
            "progress_kind": "measured" if phase_progress is not None else "indeterminate",
        }
        if last_phase["value"] != phase:
            last_phase["value"] = phase
            reporter.stage(phase, label, index, pct, message, data=live_data)
        else:
            reporter.heartbeat(pct, message, data=live_data)
        reporter.merge_result({"phase": phase, "done": done, "total": total, "percent": round(pct, 1), "phase_progress": phase_progress})

    try:
        target_region = str(region_id or ((browsed_osm_region() or {}).get("id") or "")).strip().lower()
        if not target_region:
            raise ValueError("Choose a region before downloading road data")
        active_before = region_source_status(False)
        active_before_identity = _active_source_identity(active_before)
        result = download_selected_region_pbf(progress=progress, force=force, region_id=target_region)
        active_after_download = region_source_status(False)
        active_after_identity = _active_source_identity(active_after_download)
        activated = False
        invalidated = False
        active_region_id = str(((active_after_download.get("region") or {}).get("id") or ""))
        # First verified source may become active automatically, but a second
        # downloaded country is only cached. Never let browsing/downloading B
        # silently replace a known-good active A.
        if not active_region_id or not active_after_download.get("ready"):
            plan_points = _plan_points()
            coverage = region_points_coverage(target_region, plan_points)
            # With no plan, the first verified source is a harmless default.
            # With a real depot/plan, automatic activation requires positive
            # geometric proof of full coverage. Unknown geometry is cached for
            # explicit operator activation rather than guessed safe.
            may_auto_activate = (not plan_points) or bool(
                coverage.get("known") and coverage.get("covers_all") is True
            )
            if may_auto_activate:
                _activate_region_source_internal(target_region, actor="system", invalidate=True)
                activated = True
                active_after_download = region_source_status(False)
                active_after_identity = _active_source_identity(active_after_download)
        elif active_region_id == target_region and active_before_identity != active_after_identity:
            # Same region ID, newer verified source bytes/version. The graph and
            # any route/input derived from the previous snapshot are now stale.
            _invalidate_active_source_derivatives("active regional road source refreshed", "system")
            invalidated = True
        result = {
            **result,
            "download_region_id": target_region,
            "activated": activated,
            "active_source": region_source_status(False),
            "derived_state_invalidated": invalidated,
        }
        reporter.finish("Regional road source downloaded and checksum-verified", result)
    except JobCancelled as exc:
        reporter.fail(exc, cancelled=True)
    except Exception as exc:
        reporter.append("TRACEBACK\n" + traceback.format_exc())
        reporter.fail(exc)


def run_network_build_job(job_id: int, candidate: dict[str, float] | None = None) -> None:
    log_path = RUNTIME_DIR / f"job_{job_id}.log"
    log_path.write_text(f"FLEETROUTE OPERATING GRAPH JOB #{job_id}\n", encoding="utf-8")
    reporter = JobReporter(job_id, log_path, stage_count=4)
    update_job(job_id, status="running", started_at=utc_now(), message="Preparing local operating graph")
    try:
        reporter.stage("source", "Local road source", 1, 2, "Checking the selected regional PBF and prepared-area cache")
        callback = _network_progress_adapter(reporter, 3, 82)
        if candidate:
            result = prepare_candidate_access(
                float(candidate["lat"]),
                float(candidate["lon"]),
                candidate.get("max_snap_m"),
                progress=callback,
            )
            network = result.get("network") or get_setting("network_summary") or {}
        else:
            network = build_base_network(progress=callback, include_overview=False)
            result = {"network": network}
        reporter.stage("access", "Destination road access", 3, 84, "Validating every saved destination against the in-memory graph")
        invalid = (get_setting("network_summary") or {}).get("invalid_access") or []
        reporter.merge_result({"network": network, "candidate": result if candidate else None, "invalid_access": invalid})
        reporter.heartbeat(94, "Road access validation complete")
        reporter.stage("ready", "Operating graph ready", 4, 97, "The graph and spatial indexes are now resident in memory")
        reporter.finish(
            "Operating road graph is ready for instant destination and closure selection",
            {"network": network, "candidate": result if candidate else None, "invalid_access": invalid},
        )
    except JobCancelled as exc:
        reporter.fail(exc, cancelled=True)
    except Exception as exc:
        reporter.append("TRACEBACK\n" + traceback.format_exc())
        reporter.fail(exc)


def queue_network_build(candidate: dict[str, float] | None = None) -> int:
    _ensure_operational_idle("preparing another operating graph")
    points = list_places()
    if candidate:
        points = [*points, {
            "role": "candidate", "name": "Candidate destination",
            "lat": float(candidate["lat"]), "lon": float(candidate["lon"]),
        }]
    require_active_source_covers(points, action="Operating-graph preparation")
    kind = "network-expand" if candidate else "network-build"
    job_id = _create_operational_job(kind, "Preparing local operating graph", "preparing another operating graph")
    _EXECUTOR.submit(run_network_build_job, job_id, candidate)
    return job_id


def queue_region_download(force: bool = False) -> int:
    _ensure_operational_idle("starting the regional road-source download")
    target = region_target_status()
    if not target.get("selected") or not (target.get("region") or {}).get("id"):
        raise ValueError("Choose a region on the map before downloading road data")
    if target.get("ready") and not force:
        raise ValueError("This browsed regional road source is already installed and verified")
    region_id = str(target["region"]["id"])
    job_id = _create_operational_job(
        "osm-source-download",
        f"Preparing regional road source · {target['region'].get('name') or region_id}",
        "starting the regional road-source download",
    )
    _EXECUTOR.submit(run_region_download_job, job_id, force, region_id)
    return job_id


def delete_region_source() -> dict[str, Any]:
    with _OPERATION_QUEUE_LOCK:
        _ensure_operational_idle("deleting the active regional road source")
        source = region_source_status(False)
        region = source.get("region") or {}
        if not region:
            return source
        _invalidate_active_source_derivatives("active regional road source removed", "dispatcher")
        result = remove_selected_region_pbf()
        log_event("osm.source.deleted", {"region_id": region.get("id"), "region_name": region.get("name")}, "dispatcher")
        return result


def preflight_status(
    _places: list[dict[str, Any]] | None = None,
    _settings: dict[str, Any] | None = None,
    _source: dict[str, Any] | None = None,
    _source_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    places = _places if _places is not None else list_places()
    depot = next((p for p in places if p["role"] == "depot"), None)
    customers = [p for p in places if p["role"] == "customer"]
    source = _source if _source is not None else region_source_status(False)
    coverage = _source_coverage if _source_coverage is not None else active_source_coverage(places, source)
    # A verified checksum proves byte integrity; once a real plan exists we also
    # require positive geometric containment.  Treat unknown boundary evidence
    # as not ready rather than letting API callers bypass the stricter UI gate.
    has_plan_points = bool(places)
    source_compatible = bool(source.get("ready")) and (
        not has_plan_points
        or (coverage.get("known") is True and coverage.get("covers_all") is True)
    )
    cached = _settings or get_settings(("network_summary", "network_stale", "fleet"))
    network = cached.get("network_summary") or {}
    stale_info = cached.get("network_stale") or {"stale": False}
    current_snap_max = float((cached.get("fleet") or {}).get("snap_max_m", 350))
    invalid = [
        p for p in places
        if (not p.get("access_verified"))
        or p.get("access_distance_m") is None
        or float(p.get("access_distance_m") or 0.0) > current_snap_max
    ]
    source_region = source.get("region") or {}
    source_label = (
        f"{source_region.get('name')} regional roads"
        if source_region.get("name") else "Regional road source"
    )
    if source.get("ready") and not source_compatible:
        if coverage.get("known") is not True:
            source_label = f"{source_region.get('name') or 'Active road source'} coverage could not be verified"
        else:
            source_label = f"{source_region.get('name') or 'Active road source'} does not cover the current plan"
    checks = [
        {"id": "source", "ok": source_compatible, "label": source_label, "action": "download"},
        {"id": "depot", "ok": bool(depot), "label": "Depot selected", "action": "plan"},
        {"id": "network", "ok": bool(GRAPH_STORE.available() and network) and not bool(stale_info.get("stale")), "label": "Operating graph current", "action": "prepare"},
        {"id": "customers", "ok": bool(customers), "label": "At least one work point", "action": "plan"},
        {"id": "access", "ok": bool(places) and not invalid, "label": "Every planned location has reachable road access", "action": "prepare"},
    ]
    return {
        "ready": all(item["ok"] for item in checks),
        "checks": checks,
        "invalid_places": [{"id": p["id"], "name": p["name"]} for p in invalid],
        "source": source,
        "source_coverage": coverage,
        "network_stale": stale_info,
    }


def queue_solve(
    rebuild_network: bool = False,
    reason: str = "manual solve",
    *,
    publish_baseline: bool = True,
    retain_baseline_on_failure: bool = True,
) -> int:
    _ensure_operational_idle("starting another optimization")
    check = preflight_status()
    # Rebuild requests may fix graph/access checks, but they cannot fix missing source,
    # depot, or customers. Reject before creating a red failed job.
    hard_fail = [item for item in check["checks"] if not item["ok"] and item["id"] in {"source", "depot", "customers"}]
    if hard_fail:
        raise ValueError("Preflight: " + "; ".join(item["label"] for item in hard_fail))
    # Network/access failures are repairable prerequisites, not user errors.
    # A depot change, CSV import, closure revision, or wider customer extent may
    # invalidate the active graph. Queue one network-and-solve job automatically
    # instead of forcing the user to guess which GIS button to press first.
    repairable = [
        item for item in check["checks"]
        if not item["ok"] and item["id"] in {"network", "access"}
    ]
    auto_rebuild = bool(repairable)
    rebuild_network = bool(rebuild_network or auto_rebuild)
    if auto_rebuild:
        reason = reason + " · automatic graph/access repair"
    snapshot = get_settings(("fleet", "solver", "settings_revision"))
    fleet_snapshot = json.loads(json.dumps(snapshot.get("fleet") or {}))
    solver_snapshot = json.loads(json.dumps(snapshot.get("solver") or {}))
    revision_snapshot = {
        "fleet": int((snapshot.get("settings_revision") or {}).get("fleet", 0)),
        "solver": int((snapshot.get("settings_revision") or {}).get("solver", 0)),
    }
    job_id = _create_operational_job(
        "network-and-solve" if rebuild_network else "solve",
        reason,
        "starting another optimization",
    )
    log_event(
        "solve.queued",
        {
            "job_id": job_id,
            "rebuild_network": rebuild_network,
            "reason": reason,
            "publish_baseline": publish_baseline,
            "auto_rebuild": auto_rebuild,
            "repairable_preflight": [item["id"] for item in repairable],
            "settings_revision": revision_snapshot,
            "requested_instances": solver_snapshot.get("instances"),
            "hard_time_limit_s": solver_snapshot.get("hard_time_limit_s"),
        },
        "dispatcher",
    )
    _EXECUTOR.submit(
        run_solve_job,
        job_id,
        rebuild_network,
        publish_baseline=publish_baseline,
        retain_baseline_on_failure=retain_baseline_on_failure,
        solver_config=solver_snapshot,
        fleet_config=fleet_snapshot,
        settings_revision=revision_snapshot,
    )
    return job_id

def _parse_clock_value(value: Any, default: float) -> float:
    if value is None or value == "":
        return float(default)
    if isinstance(value, (int, float)):
        number = _finite_float(value, name="time value")
        if number < 0:
            raise ValueError("time value must be nonnegative")
        return number
    text = str(value).strip()
    if not text:
        return float(default)
    if ":" in text:
        parts = text.split(":")
        if len(parts) not in {2, 3}:
            raise ValueError(f"Invalid time value: {text}")
        hours = int(parts[0]); minutes = int(parts[1]); seconds = int(parts[2]) if len(parts) == 3 else 0
        if not (0 <= hours <= 47 and 0 <= minutes < 60 and 0 <= seconds < 60):
            raise ValueError(f"Invalid time value: {text}")
        return float(hours * 3600 + minutes * 60 + seconds)
    number = _finite_float(text, name="time value")
    if number < 0:
        raise ValueError("time value must be nonnegative")
    return number


def solver_profiles() -> dict[str, dict[str, Any]]:
    return {
        "auto_dynamic": {
            "label": "Adaptive routing policy",
            "description": "FleetRoute scales runtime guardrails by plan size while the optimizer manages its internal search automatically.",
            "settings": {},
        },
    }


def _normalize_plan_rows(
    rows: list[dict[str, Any]], *, replace: bool = True, use_current_depot: bool = True,
) -> dict[str, Any]:
    """Parse a CSV batch without mutating SQLite or routing state."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("CSV contains no data rows")
    if len(rows) > 5000:
        raise ValueError("CSV import supports at most 5,000 rows")
    normalized: list[dict[str, Any]] = []
    depot_rows = 0
    for index, row in enumerate(rows, start=2):
        role = str(row.get("role") or "customer").strip().lower()
        if role not in {"depot", "customer"}:
            raise ValueError(f"CSV row {index}: role must be depot or customer")
        try:
            lat = float(row.get("lat")); lon = float(row.get("lon"))
        except Exception as exc:
            raise ValueError(f"CSV row {index}: invalid lat/lon") from exc
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"CSV row {index}: invalid lat/lon")
        if role == "depot":
            depot_rows += 1
        earliest_s = 0.0 if role == "depot" else _parse_clock_value(
            row.get("earliest_s") if row.get("earliest_s") not in {None, ""} else row.get("earliest"), 0
        )
        latest_s = 86400.0 if role == "depot" else _parse_clock_value(
            row.get("latest_s") if row.get("latest_s") not in {None, ""} else row.get("latest"), 86400
        )
        if latest_s < earliest_s:
            raise ValueError(f"CSV row {index}: latest time must be greater than or equal to earliest time")
        demand = 0.0 if role == "depot" else _finite_float(row.get("demand") or 0, name=f"CSV row {index} demand")
        service_value = row.get("service_s")
        if service_value is None or service_value == "":
            minutes = row.get("service_minutes")
            if minutes is None or minutes == "":
                minutes = row.get("service") or 0
            service_value = _finite_float(minutes, name=f"CSV row {index} service_minutes") * 60
        service_s = 0.0 if role == "depot" else _finite_float(service_value, name=f"CSV row {index} service_s")
        if demand < 0 or service_s < 0:
            raise ValueError(f"CSV row {index}: demand and service time must be nonnegative")
        normalized.append({
            "role": role,
            "name": str(row.get("name") or f"{role.title()} {index - 1}"),
            "address": str(row.get("address") or ""),
            "lat": lat, "lon": lon,
            "demand": demand,
            "service_s": service_s,
            "earliest_s": earliest_s,
            "latest_s": latest_s,
            "external_id": str(row.get("external_id") or f"csv:{index}"),
        })
    if depot_rows > 1:
        raise ValueError("CSV must contain at most one depot row")

    current_depot = next((p for p in list_places() if p["role"] == "depot"), None)
    if depot_rows == 0 and not (use_current_depot and current_depot):
        raise ValueError("CSV needs one depot row, or select a depot before uploading")

    rows_to_insert = list(normalized)
    reused_current_depot = bool(depot_rows == 0 and use_current_depot and current_depot)
    if replace and reused_current_depot:
        rows_to_insert.insert(0, {
            "role": "depot", "name": str(current_depot["name"]),
            "address": str(current_depot.get("address") or ""),
            "lat": float(current_depot["lat"]), "lon": float(current_depot["lon"]),
            "demand": 0.0, "service_s": 0.0, "earliest_s": 0.0, "latest_s": 86400.0,
            "external_id": str(current_depot.get("external_id") or "current-depot"),
        })

    if replace:
        projected_plan = list(rows_to_insert)
    else:
        existing = [dict(item) for item in list_places()]
        if depot_rows:
            existing = [item for item in existing if item.get("role") != "depot"]
        projected_plan = [*existing, *normalized]
    return {
        "normalized": normalized,
        "rows_to_insert": rows_to_insert,
        "projected_plan": projected_plan,
        "depot_rows": depot_rows,
        "reused_current_depot": reused_current_depot,
    }


def preview_plan_rows(
    rows: list[dict[str, Any]], *, replace: bool = True, use_current_depot: bool = True,
) -> dict[str, Any]:
    parsed = _normalize_plan_rows(rows, replace=replace, use_current_depot=use_current_depot)
    projected = parsed["projected_plan"]
    distance = plan_distance_check(projected, get_setting("fleet") or {})
    source = region_source_status(False)
    coverage = active_source_coverage(projected, source)
    return {
        "row_count": len(parsed["normalized"]),
        "customer_count": sum(1 for row in projected if row.get("role") == "customer"),
        "depot_from_csv": parsed["depot_rows"] == 1,
        "used_current_depot": parsed["reused_current_depot"],
        "replace": bool(replace),
        "source_coverage": coverage,
        "distance_check": distance,
        "projected_plan": projected,
    }


def import_plan_rows(
    rows: list[dict[str, Any]], *, replace: bool = True, use_current_depot: bool = True,
    event_action: str = "plan.csv.imported",
) -> dict[str, Any]:
    """Validate and import a CSV plan in one SQLite transaction."""
    parsed = _normalize_plan_rows(rows, replace=replace, use_current_depot=use_current_depot)
    normalized = parsed["normalized"]
    rows_to_insert = parsed["rows_to_insert"]
    depot_rows = int(parsed["depot_rows"])
    reused_current_depot = bool(parsed["reused_current_depot"])

    now = utc_now()
    inserted_ids: list[int] = []
    with connect() as conn:
        if replace:
            conn.execute("UPDATE places SET active=0,updated_at=? WHERE active=1", (now,))
        elif depot_rows:
            conn.execute("UPDATE places SET active=0,updated_at=? WHERE role='depot' AND active=1", (now,))
        for row in rows_to_insert:
            cur = conn.execute(
                """
                INSERT INTO places(
                    role,name,address,lat,lon,demand,service_s,earliest_s,latest_s,external_id,
                    access_lat,access_lon,access_road,access_distance_m,access_osm_node,
                    access_osm_u,access_osm_v,access_osm_key,access_highway,access_direction,
                    access_reachable,access_verified,active,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
                """,
                (
                    row["role"], row["name"], row["address"], row["lat"], row["lon"],
                    row["demand"], row["service_s"], row["earliest_s"], row["latest_s"], row["external_id"],
                    None, None, "", None, "", "", "", "", "", "", 0, 0, now, now,
                ),
            )
            inserted_ids.append(int(cur.lastrowid))

    revision = {"changed_at": now, "reason": "CSV plan imported", "rows": len(normalized)}
    set_setting("plan_revision", revision)
    _mark_network_stale("CSV imported; road access requires validation")
    _mark_routes_stale("CSV plan imported", "dispatcher")
    result = {
        "row_count": len(normalized),
        "inserted_rows": len(rows_to_insert),
        "customer_count": sum(1 for row in normalized if row["role"] == "customer"),
        "depot_from_csv": depot_rows == 1,
        "used_current_depot": reused_current_depot,
        "replace": bool(replace),
        "inserted_ids": inserted_ids,
        "source_coverage": active_source_coverage(list_places()),
        "distance_check": plan_distance_check(list_places(), get_setting("fleet") or {}),
    }
    log_event(str(event_action or "plan.csv.imported"), result, "dispatcher")
    return result


def run_scenario_generation_job(job_id: int, payload: dict[str, Any]) -> None:
    """Prepare customers, publish a certificate, then always optimize routed runs."""
    log_path = RUNTIME_DIR / f"job_{job_id}.log"
    log_path.write_text(f"FLEETROUTE EASY SCENARIO #{job_id}\n", encoding="utf-8")
    auto_optimize = bool(payload.get("auto_optimize", True))
    # ``auto_optimize`` is the Create stops + run optimizer action. Never let a
    # stale/legacy run_optimizer=false field turn that action into a silent
    # deterministic-only fast path.
    run_optimizer = auto_optimize
    solver_snapshot = json.loads(json.dumps(
        payload.get("_solver_snapshot") or get_setting("solver") or {}
    ))
    fleet_snapshot = json.loads(json.dumps(
        payload.get("_fleet_snapshot") or get_setting("fleet") or {}
    ))
    raw_revision = payload.get("_settings_revision") or _settings_revision()
    revision_snapshot = {
        "fleet": int(raw_revision.get("fleet", 0)),
        "solver": int(raw_revision.get("solver", 0)),
    }
    reporter = JobReporter(job_id, log_path, stage_count=5 if auto_optimize else 3)
    update_job(job_id, status="running", started_at=utc_now(), message="Preparing a capacity-checked scenario")
    try:
        reporter.stage(
            "preflight",
            "Scenario contract",
            1,
            5,
            "Checking depot, regional roads, fleet size, and exact capacity packing",
        )
        places = list_places()
        depot = next((item for item in places if item.get("role") == "depot"), None)
        if depot is None:
            raise ValueError("Choose the depot before generating customers")
        if not region_source_status(False)["ready"]:
            raise ValueError("Choose and verify an active operating-region road source before generating work points")
        require_active_source_covers([depot], action="Scenario generation")

        stale = get_setting("network_stale") or {"stale": False}
        if not GRAPH_STORE.available() or bool(stale.get("stale")):
            reporter.stage(
                "network",
                "Fixed operating area",
                2,
                12,
                "Preparing or restoring the depot operating graph",
            )
            replace_customers = bool(payload.get("replace_customers", True))
            build_base_network(
                progress=_network_progress_adapter(reporter, 12, 58 if auto_optimize else 72),
                include_overview=False,
                include_current_customers=not replace_customers,
                validate_existing=not replace_customers,
            )
        else:
            reporter.stage(
                "network",
                "Fixed operating area",
                2,
                48 if auto_optimize else 52,
                "Reusing the active in-memory graph and spatial indexes",
            )

        reporter.stage(
            "scenario",
            "Verified customers",
            3,
            62 if auto_optimize else 78,
            "Sampling round-trip road nodes and allocating an exact packable fleet load",
        )
        generation_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"auto_optimize", "run_optimizer", "optimizer_clustering"}
            and not str(key).startswith("_")
        }
        generation_start = 62 if auto_optimize else 78
        generation_end = 73 if auto_optimize else 96
        last_scenario_progress_emit = [0.0]
        def scenario_progress(done: int, total: int, message: str) -> None:
            total = max(1, int(total))
            done = max(0, min(total, int(done)))
            now_mono = time.monotonic()
            # Keep slow work visibly live while avoiding dozens of SQLite writes
            # when exact-node access validation finishes in a few milliseconds.
            if done not in {0, total} and now_mono - last_scenario_progress_emit[0] < 0.20:
                return
            last_scenario_progress_emit[0] = now_mono
            phase = done / total * 100.0
            overall = generation_start + (generation_end - generation_start) * done / total
            reporter.heartbeat(
                overall, message,
                data={
                    "progress_kind": "measured",
                    "phase_progress": round(phase, 2),
                    "done": done,
                    "total": total,
                    "unit": "customers",
                    "phase_metric": "customer_access_validation",
                    "indeterminate": False,
                },
            )
        result = generate_demo_plan(**generation_payload, progress=scenario_progress)
        if not result.get("ok"):
            raise ValueError(result.get("message") or "Scenario generation could not complete")

        summary = dict(get_setting("network_summary") or {})
        summary.update(
            {
                "invalid_access": [],
                "access_ready": True,
                "verified_customer_count": int(result.get("customer_count", 0)),
                "last_scenario_at": utc_now(),
            }
        )
        set_setting("network_summary", summary)

        if not auto_optimize:
            reporter.finish("Verified customer scenario is ready", {"scenario": result})
            log_event("scenario.workflow.ready", {"job_id": job_id, **result}, "system")
            return

        reporter.stage(
            "certificate",
            "Immediate route validation",
            4,
            76,
            "Creating input.txt and publishing a deterministic road-feasible route",
        )
        instance_summary = materialize_solver_instance(
            fleet_override=fleet_snapshot,
            solver_override=solver_snapshot,
        )
        certificate = build_baseline_certificate(
            publish_job_id=job_id,
            publish=True,
            retain_routing_context=run_optimizer,
            solver_config=solver_snapshot,
            settings_revision=revision_snapshot,
        )
        if not certificate.get("feasible"):
            raise ValueError(
                certificate.get("reason")
                or "The generated scenario could not be validated as route-feasible"
            )
        route_version = certificate.get("published_route_version")
        reporter.merge_result(
            {
                "scenario": result,
                "network": instance_summary,
                "baseline": {k: v for k, v in certificate.items() if k != "routes"},
            }
        )
        reporter.stage(
            "handoff",
            "Background improvement",
            5,
            94,
            f"Route v{route_version} is usable now; handing the same instance to the routing optimizer",
        )
        improvement_job: int | None = None
        if run_optimizer:
            improvement_job = create_job(
                "solve",
                f"Optimize scenario route v{route_version} with the saved click-time settings",
            )
            reporter.append(
                "C++ SOLVER HANDOFF\n"
                + json.dumps(
                    {
                        "optimizer_job_id": improvement_job,
                        "baseline_route_version": route_version,
                        "settings_revision": revision_snapshot,
                        "solver": solver_snapshot,
                        "fleet": fleet_snapshot,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        reporter.finish(
            f"Created {result['customer_count']} work points, prepared initial plan v{route_version}, and queued C++ optimization",
            {
                "scenario": result,
                "route_version": route_version,
                "solution_source": "deterministic_baseline",
                "network": instance_summary,
                "optimizer_queued": bool(run_optimizer),
                "optimizer_required": bool(run_optimizer),
                "optimizer_job_id": improvement_job,
                "settings_revision": revision_snapshot,
            },
        )
        log_event(
            "scenario.route.ready",
            {"job_id": job_id, "route_version": route_version, **result},
            "system",
        )

        if improvement_job is not None:
            log_event(
                "solve.queued",
                {
                    "job_id": improvement_job,
                    "rebuild_network": False,
                    "reason": "scenario background improvement",
                    "baseline_route_version": route_version,
                    "settings_revision": revision_snapshot,
                    "requested_instances": solver_snapshot.get("instances"),
                    "hard_time_limit_s": solver_snapshot.get("hard_time_limit_s"),
                },
                "system",
            )
            _EXECUTOR.submit(
                run_solve_job,
                improvement_job,
                False,
                publish_baseline=False,
                retain_baseline_on_failure=True,
                solver_config=solver_snapshot,
                fleet_config=fleet_snapshot,
                settings_revision=revision_snapshot,
            )

    except JobCancelled as exc:
        reporter.fail(exc, cancelled=True)
    except Exception as exc:
        reporter.append("TRACEBACK\n" + traceback.format_exc())
        reporter.fail(exc)


def queue_scenario_generation(payload: dict[str, Any]) -> int:
    """Queue one verified scenario using K only as maximum fleet availability."""
    _ensure_operational_idle("generating a verified customer scenario")
    existing_places = list_places()
    depot_only = [item for item in existing_places if item.get("role") == "depot"]
    if not depot_only:
        raise ValueError("Choose the depot before generating customers")
    require_active_source_covers(depot_only, action="Scenario generation")
    clean = {
        "count": max(3, min(500, int(payload.get("count", 20)))),
        "radius_m": max(400.0, min(150_000.0, float(payload.get("radius_m", 4200)))),
        "seed": int(payload.get("seed", 777)),
        "replace_customers": bool(payload.get("replace_customers", True)),
        "demand_mode": str(payload.get("demand_mode", "auto") or "auto").lower(),
        "demand_profile": str(payload.get("demand_profile", "standard") or "standard").lower(),
        "demand_min": max(1, int(payload.get("demand_min", 4))),
        "demand_max": max(1, int(payload.get("demand_max", 18))),
        "service_mode": str(payload.get("service_mode", "auto") or "auto").lower(),
        "service_min": max(1, int(payload.get("service_min", 5))),
        "service_max": max(1, int(payload.get("service_max", 15))),
        "time_window_mode": str(payload.get("time_window_mode", "open") or "open").lower(),
        "auto_optimize": bool(payload.get("auto_optimize", False)),
        # One public action has one unambiguous meaning: when a route is
        # requested, the C++ solver is required after the immediate certificate.
        "run_optimizer": bool(payload.get("auto_optimize", False)),
    }
    if payload.get("trucks") is not None:
        clean["trucks"] = max(1, int(payload.get("trucks")))
    if payload.get("capacity") is not None:
        clean["capacity"] = max(1.0, float(payload.get("capacity")))
    if clean["demand_mode"] == "custom" and clean["demand_max"] < clean["demand_min"]:
        raise ValueError("Maximum demand must be greater than or equal to minimum demand")
    if clean["service_mode"] == "custom" and clean["service_max"] < clean["service_min"]:
        raise ValueError("Maximum service time must be greater than or equal to minimum service time")
    contract = scenario_contract_preview(clean)
    if not contract["ok"]:
        raise ValueError(" ".join(contract["errors"]))
    clean["demand_mode"] = contract["demand_mode"]
    clean["demand_profile"] = contract["demand_profile"]
    clean["service_mode"] = contract["service_mode"]
    clean["time_window_mode"] = contract["time_window_mode"]
    # The value passed to input.txt remains the maximum fleet ceiling. It is
    # deliberately never replaced by an expected/target active-route count.
    clean["trucks"] = contract["maximum_trucks"]
    clean["capacity"] = contract["capacity"]
    snapshot = get_settings(("fleet", "solver", "settings_revision"))
    clean["_fleet_snapshot"] = json.loads(json.dumps(snapshot.get("fleet") or {}))
    clean["_fleet_snapshot"]["trucks"] = clean["trucks"]
    clean["_fleet_snapshot"]["capacity"] = clean["capacity"]
    clean["_solver_snapshot"] = json.loads(json.dumps(snapshot.get("solver") or {}))
    clean["_settings_revision"] = {
        "fleet": int((snapshot.get("settings_revision") or {}).get("fleet", 0)),
        "solver": int((snapshot.get("settings_revision") or {}).get("solver", 0)),
    }
    kind = "scenario-route" if clean["auto_optimize"] else "scenario-generate"
    message = (
        "Create work points, publish an immediate validated route, and run the routing optimizer"
        if clean["auto_optimize"]
        else "Prepare graph and generate verified customers"
    )
    job_id = _create_operational_job(kind, message, "generating a verified customer scenario")
    _EXECUTOR.submit(run_scenario_generation_job, job_id, clean)
    return job_id

def run_complete_demo_job(job_id: int, count: int, cluster_method: str) -> None:
    log_path = RUNTIME_DIR / f"job_{job_id}.log"
    log_path.write_text(f"FLEETROUTE COMPLETE DEMO #{job_id}\n", encoding="utf-8")
    reporter = JobReporter(job_id, log_path, stage_count=3)
    update_job(job_id, status="running", started_at=utc_now(), message="Preparing the complete real-road demo")
    try:
        reporter.stage("source", "Regional roads", 1, 5, "Checking the verified operating-region road source")
        if not region_source_status(False)["ready"]:
            raise ValueError("The demo needs a verified operating-region road source. Choose a region on the map and prepare its road data first.")

        # Prepare the depot before the graph so the expensive graph build can emit
        # real progress and heartbeats instead of appearing frozen inside the demo helper.
        places = list_places()
        depot = next((item for item in places if item.get("role") == "depot"), None)
        if depot is None:
            raise ValueError("Choose a depot on the map before starting the complete demo")
        require_active_source_covers([depot], action="Complete demo")
        stale = get_setting("network_stale") or {"stale": False}
        if not GRAPH_STORE.available() or bool(stale.get("stale")):
            fleet = dict(get_setting("fleet") or {})
            fleet["operating_radius_m"] = max(int(fleet.get("operating_radius_m", 8000)), 6500)
            set_setting("fleet", fleet)
            reporter.stage("scenario", "Verified demo plan", 2, 14, "Preparing or restoring the demo operating graph")
            build_base_network(
                progress=_network_progress_adapter(reporter, 14, 66),
                include_overview=False,
                include_current_customers=False,
                validate_existing=False,
            )

        reporter.stage("scenario", "Verified demo plan", 2, 70, "Generating reachable customers on verified road nodes")
        result = generate_demo_plan(
            count=count,
            replace_customers=True,
            target_utilization=0.72,
            demand_mode="auto",
            service_mode="auto",
            time_window_mode="open",
        )
        if not result.get("ok"):
            raise ValueError(result.get("message") or "Demo plan could not be generated")
        solver = get_setting("solver") or {}
        solver["clustering"] = cluster_method if cluster_method in {"none", "road_savings", "auto"} else "road_savings"
        save_operating_settings(get_setting("fleet") or {}, solver)
        reporter.stage("handoff", "Automatic optimization", 3, 92, "Demo plan ready; queuing the solver without another manual click")
        reporter.finish("Demo plan ready; optimization is being queued", {"demo": result})
        solve_job_id = queue_solve(False, reason=f"Complete demo from job #{job_id}")
        current_job = get_job(job_id) or {}
        current_result = dict(current_job.get("result") or {})
        current_result.update({"demo": result, "next_job_id": solve_job_id, "next_kind": "solve"})
        update_job(job_id, result_json=current_result)
        log_event("demo.workflow.queued", {"job_id": job_id, "solve_job_id": solve_job_id}, "system")
    except JobCancelled as exc:
        reporter.fail(exc, cancelled=True)
    except Exception as exc:
        reporter.append("TRACEBACK\n" + traceback.format_exc())
        reporter.fail(exc)


def queue_complete_demo(count: int = 12, cluster_method: str = "road_savings") -> int:
    _ensure_operational_idle("starting the complete demo")
    depot_only = [item for item in list_places() if item.get("role") == "depot"]
    if not depot_only:
        raise ValueError("Choose a depot on the map before starting the complete demo")
    require_active_source_covers(depot_only, action="Complete demo")
    job_id = _create_operational_job(
        "complete-demo",
        "Prepare verified demo work points and optimize automatically",
        "starting the complete demo",
    )
    _EXECUTOR.submit(run_complete_demo_job, job_id, max(3, min(100, int(count))), str(cluster_method))
    return job_id


def run_rush_workflow_job(job_id: int, payload: dict[str, Any]) -> None:
    log_path = RUNTIME_DIR / f"job_{job_id}.log"
    log_path.write_text(f"FLEETROUTE RUSH WORKFLOW #{job_id}\n", encoding="utf-8")
    reporter = JobReporter(job_id, log_path, stage_count=4)
    update_job(job_id, status="running", started_at=utc_now(), message="Importing CSV and preparing automatic optimization")
    try:
        reporter.stage("source", "Regional roads", 1, 4, "Checking the verified operating-region road source")
        if not region_source_status(False)["ready"]:
            raise ValueError("CSV routing needs a verified operating-region road source. Choose a region and prepare its road data first.")

        reporter.stage("import", "CSV plan", 2, 14, "Validating and importing depot and customers")
        rush_preview = preview_plan_rows(
            list(payload.get("rows") or []),
            replace=bool(payload.get("replace", True)),
            use_current_depot=bool(payload.get("use_current_depot", True)),
        )
        coverage = rush_preview.get("source_coverage") or {}
        if coverage.get("known") is not True:
            raise ValueError(
                "Rush CSV routing cannot verify that the active regional road source covers every imported plan location. "
                "Refresh Road-source setup and reselect the verified region before routing this CSV."
            )
        if coverage.get("covers_all") is False:
            raise ValueError(_source_coverage_error(region_source_status(False), coverage, "Rush CSV routing"))
        imported = import_plan_rows(
            list(payload.get("rows") or []),
            replace=bool(payload.get("replace", True)),
            use_current_depot=bool(payload.get("use_current_depot", True)),
            event_action="rush.csv.imported",
        )
        current_fleet = dict(get_setting("fleet") or {})
        current_solver = dict(get_setting("solver") or {})
        current_fleet.update(dict(payload.get("fleet") or {}))
        current_solver.update(dict(payload.get("solver") or {}))
        clustering = str(payload.get("clustering") or "road_savings")
        current_solver["clustering"] = clustering if clustering in {"none", "road_savings"} else "road_savings"
        save_operating_settings(current_fleet, current_solver)

        reporter.stage("preflight", "Automatic preparation", 3, 32, "Preparing or reusing the operating graph and validating every destination")
        must_rebuild = not GRAPH_STORE.available()
        if not must_rebuild:
            graph = load_base_graph()
            invalid = _update_all_access_points(graph)
            if invalid:
                names = ", ".join(str(item.get("name") or item.get("id")) for item in invalid[:5])
                suffix = " ..." if len(invalid) > 5 else ""
                reporter.append(
                    "RUSH AUTO-REPAIR\n"
                    f"The imported plan does not fit the active operating graph ({len(invalid)} unresolved place(s): {names}{suffix}). "
                    "FleetRoute will rebuild/expand the depot-centred graph automatically instead of rejecting the CSV."
                )
                must_rebuild = True
            else:
                set_setting("network_stale", {"stale": False, "changed_at": utc_now(), "reason": "Rush CSV validated on active graph"})
                reporter.stage("preflight", "Automatic preparation", 3, 65, "Reused the active graph; every CSV destination is road-valid")
        if must_rebuild:
            summary = build_base_network(
                progress=_network_progress_adapter(reporter, 32, 72),
                include_overview=False,
                include_current_customers=True,
                validate_existing=True,
            )
            invalid_after = list(summary.get("invalid_access") or [])
            if invalid_after:
                names = ", ".join(str(item.get("name") or item.get("id")) for item in invalid_after[:5])
                raise ValueError(
                    "FleetRoute automatically rebuilt the operating graph, but some CSV destinations still have no valid round-trip road access: "
                    + names
                )
            reporter.stage("preflight", "Automatic preparation", 3, 72, "Operating graph rebuilt automatically for the imported depot and destinations")
        materialize_solver_instance()

        reporter.stage("handoff", "Automatic optimization", 4, 92, "CSV plan is valid; handing off to the solver")
        reporter.finish("Rush plan validated; optimization is being queued", {"import": imported, "clustering": current_solver["clustering"]})
        solve_job_id = queue_solve(False, reason=f"Rush mode from job #{job_id}")
        current_job = get_job(job_id) or {}
        result = dict(current_job.get("result") or {})
        result.update({"import": imported, "clustering": current_solver["clustering"], "next_job_id": solve_job_id, "next_kind": "solve"})
        update_job(job_id, result_json=result)
        log_event("rush.workflow.queued", {"job_id": job_id, "solve_job_id": solve_job_id, **imported}, "system")
    except JobCancelled as exc:
        reporter.fail(exc, cancelled=True)
    except Exception as exc:
        reporter.append("TRACEBACK\n" + traceback.format_exc())
        reporter.fail(exc)


def queue_rush_workflow(payload: dict[str, Any]) -> int:
    _ensure_operational_idle("starting Rush mode")
    rows = list(payload.get("rows") or [])
    if not rows:
        raise ValueError("Rush mode requires at least one CSV row")
    source = region_source_status(False)
    if not source.get("ready"):
        raise ValueError("CSV routing needs a verified active regional road source. Browse/download a source, then use it for this plan.")
    preview = preview_plan_rows(
        rows,
        replace=bool(payload.get("replace", True)),
        use_current_depot=bool(payload.get("use_current_depot", True)),
    )
    coverage = preview.get("source_coverage") or {}
    if coverage.get("known") is not True:
        raise ValueError(
            "Rush CSV routing cannot verify that the active regional road source covers every imported plan location. "
            "Refresh Road-source setup and reselect the verified region before routing this CSV."
        )
    if coverage.get("covers_all") is False:
        raise ValueError(_source_coverage_error(source, coverage, "Rush CSV routing"))
    job_id = _create_operational_job(
        "rush",
        "CSV to verified graph, initial plan, and C++ optimization",
        "starting Rush mode",
    )
    _EXECUTOR.submit(run_rush_workflow_job, job_id, dict(payload))
    return job_id


def run_single_clustering_job(job_id: int, method: str) -> None:
    log_path = RUNTIME_DIR / f"job_{job_id}.log"
    log_path.write_text(f"FLEETROUTE CLUSTER TEST #{job_id} · {method}\n", encoding="utf-8")
    reporter = JobReporter(job_id, log_path, stage_count=3)
    update_job(job_id, status="running", started_at=utc_now(), message=f"Testing clustering method: {method}")
    try:
        reporter.stage("instance", "Clustering input", 1, 8, "Materializing the current verified road instance")
        materialize_solver_instance()
        # A user can open Clustering Lab while launch-time warm-up is still
        # running, or start the app locally without the Colab warm-up at all.
        # Join the fingerprinted build lock before invoking the binary.
        _compile_cpp(settings.cluster_cpp, settings.cluster_bin, "clustering engine", reporter, 12, 26)
        reporter.stage("method", "Selected clustering method", 2, 28, f"Running and validating {method}")
        result = _run_one_clustering(method, int((get_setting("solver") or {}).get("seed", 777)), reporter, 28, 88)
        result["used"] = True
        result["attempts"] = [{"method": method, "status": "passed"}]
        set_setting("latest_clustering", result)
        reporter.stage("ready", "Validated partition", 3, 94, "Saving the validated assignment and preview")
        reporter.finish(f"{method} passed independent validation", {"clustering": result})
        log_event("clustering.single.ready", {"method": method, "job_id": job_id}, "system")
    except JobCancelled as exc:
        reporter.fail(exc, cancelled=True)
    except Exception as exc:
        reason = str(exc).strip() or type(exc).__name__
        expected_rejection = any(token in reason.lower() for token in (
            "independent validation",
            "assignment failed",
            "hard-feasible",
            "hard feasible",
            "no feasible",
            "internally fell back",
            "overload",
            "infeasible",
        ))
        if expected_rejection:
            for path in (
                settings.clusters_csv,
                settings.cluster_summary_csv,
                settings.cluster_timing_csv,
                settings.cluster_preview_png,
            ):
                if path.exists():
                    path.unlink()
            warning = (
                f"{method} could not produce an assignment that passed the selected "
                "coverage/capacity contract. It was rejected safely and will not be "
                "sent to the route solver."
            )
            result = {
                "requested_method": method,
                "effective_method": "none",
                "used": False,
                "rejected": True,
                "validation": None,
                "attempts": [{"method": method, "status": "rejected", "error": reason[-1200:]}],
                "warning": warning,
            }
            set_setting("latest_clustering", result)
            reporter.append(
                "CLUSTER METHOD REJECTED SAFELY\n"
                + json.dumps(result, indent=2, ensure_ascii=False)
            )
            reporter.stage(
                "ready",
                "Safe rejection",
                3,
                94,
                "The invalid partition was discarded; solver state was not changed",
            )
            reporter.finish(
                f"{method} rejected safely; choose another method or Auto",
                {"clustering": result, "warnings": [warning]},
            )
            log_event(
                "clustering.single.rejected",
                {"method": method, "job_id": job_id, "reason": reason[-1200:]},
                "system",
            )
        else:
            reporter.append("TRACEBACK\n" + traceback.format_exc())
            reporter.fail(exc)


def queue_single_clustering(method: str) -> int:
    _ensure_operational_idle("testing a clustering method")
    allowed = {"road_savings", "network_kmedoids", "sweep", "round_robin", "road_spectral_sparse", "road_spectral_lite", "balanced_kmeans"}
    if method not in allowed:
        raise ValueError("Choose one concrete clustering method to test")
    job_id = _create_operational_job(
        "clustering-test", f"Test and validate {method}", "testing a clustering method"
    )
    _EXECUTOR.submit(run_single_clustering_job, job_id, method)
    return job_id


def run_clustering_benchmark_job(job_id: int, root_mode: str = "road_savings") -> None:
    log_path = RUNTIME_DIR / f"job_{job_id}.log"
    log_path.write_text(f"FLEETROUTE CLUSTERING BENCHMARK #{job_id}\n", encoding="utf-8")
    reporter = JobReporter(job_id, log_path, stage_count=4)
    update_job(job_id, status="running", started_at=utc_now(), message="Preparing clustering benchmark")
    try:
        with _BENCHMARK_LOCK:
            reporter.stage("network", "Operating graph", 1, 3, "Checking the validated in-memory road graph")
            if not GRAPH_STORE.available():
                build_base_network(progress=_network_progress_adapter(reporter, 3, 18), include_overview=False)
            reporter.stage("instance", "Benchmark input", 2, 20, "Materializing the exact clustering input")
            materialized = materialize_solver_instance()
            active_input = get_setting("active_input_state") or {}
            expected_input_sha = _sha256_file(settings.input_txt)
            expected_dataset_sha = _sha256_file(settings.dataset_json)
            env = os.environ.copy()
            env.update({
                "VRP_INPUT_TXT": str(settings.input_txt),
                "VRP_DATASET_JSON": str(settings.dataset_json),
                "VRP_CLUSTER_CPP": str(settings.cluster_cpp),
                "VRP_CLUSTER_EXE": str(settings.cluster_bin),
                "VRP_CLUSTERING_OUTPUT": str(settings.clustering_benchmark_dir),
                "VRP_CLUSTER_ROOT": str(RUNTIME_DIR),
                "VRP_CLUSTER_ROOT_MODE": root_mode,
                "VRP_CLUSTER_JOB_ID": str(job_id),
                "VRP_CLUSTER_SOURCE_SIGNATURE": str(active_input.get("source_signature") or ""),
                "VRP_CLUSTER_MATERIALIZATION_ID": str(active_input.get("materialization_id") or ""),
            })
            reporter.stage("benchmark", "All clustering methods", 3, 28, "Running the benchmark; output is streaming live")
            code, _ = reporter.run_process(
                [os.sys.executable, str(settings.clustering_benchmark_runner)],
                cwd=RUNTIME_DIR,
                env=env,
                timeout_s=3600,
                expected_s=600,
                progress_start=28,
                progress_end=92,
                progress_label="Clustering benchmark",
            )
            if code != 0:
                raise RuntimeError("Clustering benchmark failed; inspect the true streamed log")
            if (
                _sha256_file(settings.input_txt) != expected_input_sha
                or _sha256_file(settings.dataset_json) != expected_dataset_sha
            ):
                raise RuntimeError("Benchmark source files changed while methods were running; the report was discarded")
            reporter.stage("figures", "Scorecard and figures", 4, 94, "Loading benchmark metrics and presentation figures")
            summary = clustering_benchmark_summary()
            receipt = summary.get("source_receipt") or {}
            if (
                receipt.get("input_sha256") != expected_input_sha
                or receipt.get("dataset_sha256") != expected_dataset_sha
                or receipt.get("source_signature") != active_input.get("source_signature")
            ):
                raise RuntimeError("Benchmark protocol receipt does not match the materialized current instance")
            dataset = _load_materialized_dataset()
            customer_nodes = sorted(int(item["node"]) for item in dataset.get("customers") or [])
            receipt.update({
                "customer_node_sha256": _sha256_text(json.dumps(customer_nodes, separators=(",", ":"))),
                "customer_count": len(customer_nodes),
                "customer_order_count": int(materialized.get("customer_orders") or len(customer_nodes)),
            })
            summary.update({"source_receipt": receipt, "current": True, "stale": False})
            set_setting("clustering_benchmark_cached", summary)
            set_setting("latest_clustering_benchmark", {
                "job_id": job_id,
                "completed_at": utc_now(),
                "root_mode": root_mode,
                "source_receipt": receipt,
            })
            try:
                set_setting("artifact_gallery_cached", list_artifact_gallery())
            except Exception:
                pass
            reporter.finish("Clustering benchmark and presentation figures are ready", {"benchmark": summary})
    except JobCancelled as exc:
        reporter.fail(exc, cancelled=True)
    except Exception as exc:
        reporter.append("TRACEBACK\n" + traceback.format_exc())
        reporter.fail(exc)


def queue_clustering_benchmark(root_mode: str = "road_savings") -> int:
    _ensure_operational_idle("starting the clustering benchmark")
    allowed = {"road_savings", "network_kmedoids", "sweep", "round_robin", "road_spectral_sparse", "road_spectral_lite", "balanced_kmeans"}
    if root_mode not in allowed:
        raise ValueError("Unsupported root clustering method")
    job_id = _create_operational_job(
        "clustering-benchmark",
        f"Benchmark all clustering methods; selected root={root_mode}",
        "starting the clustering benchmark",
    )
    _EXECUTOR.submit(run_clustering_benchmark_job, job_id, root_mode)
    return job_id


def preview_road_edge(lat: float, lon: float) -> dict[str, Any]:
    graph = load_base_graph()
    preview = _edge_preview_from_graph(graph, float(lat), float(lon), "active operating network")
    preview["human_label"] = f"{preview['road_name']} · {preview['highway']}"
    return preview


def report_closure(payload: dict[str, Any]) -> dict[str, Any]:
    graph = load_base_graph()
    lat, lon = float(payload["lat"]), float(payload["lon"])
    supplied = payload.get("edge") or {}
    if supplied.get("osm_u") is not None:
        matches = GRAPH_STORE.resolve_edge(
            supplied.get("osm_u"), supplied.get("osm_v"), supplied.get("osm_key")
        )
        if not matches:
            raise ValueError("The selected road segment no longer exists in the active road graph")
        u, v, key = matches[0]
        data = graph.get_edge_data(u, v, key) or {}
        geometry = _edge_geometry(graph, u, v, data)
        snap_lat, snap_lon, snap_distance = _nearest_point_on_edge(lat, lon, geometry)
        preview = {
            "road_name": _clean_name(data.get("name")), "highway": _clean_highway(data.get("highway")),
            "osm_u": str(u), "osm_v": str(v), "osm_key": str(key), "geometry": geometry,
            "snap_lat": snap_lat, "snap_lon": snap_lon, "snap_distance_m": snap_distance,
            "direction_text": "one-way" if osm_bool(data.get("oneway")) else "two-way road record",
        }
    else:
        preview = _edge_preview_from_graph(graph, lat, lon, "active operating network")
    now = utc_now()
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO closures(
                reported_at,reporter,source_truck_id,note,lat,lon,road_name,highway,osm_u,osm_v,osm_key,
                geometry_json,snap_distance_m,direction_text,block_reverse,status,expires_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                now, str(payload.get("reporter", "driver")), payload.get("source_truck_id"), str(payload.get("note", "")),
                preview["snap_lat"], preview["snap_lon"], preview["road_name"], preview["highway"],
                preview["osm_u"], preview["osm_v"], preview["osm_key"],
                json.dumps(preview["geometry"]), preview["snap_distance_m"], preview["direction_text"],
                1 if payload.get("block_reverse", True) else 0, "pending", payload.get("expires_at"),
            ),
        )
        closure_id = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM closures WHERE id=?", (closure_id,)).fetchone()
    result = dict(row)
    result["geometry"] = json.loads(result.pop("geometry_json") or "[]")
    result["requires_dispatch_approval"] = True
    result["route_changed"] = False
    result["message"] = "Report received. The road is not removed until dispatch approves the exact edge."
    log_event("closure.reported", {"id": closure_id, "road_name": result["road_name"], "reporter": result["reporter"], "edge": [result["osm_u"], result["osm_v"], result["osm_key"]]}, result["reporter"])
    return result


def expire_due_closures(now_iso: str | None = None) -> list[int]:
    """Atomically retire approved closures whose declared expiry has passed.

    The graph filter already ignores a past expiry.  This function keeps the
    durable status, route freshness, revision, and reroute queue in agreement
    with that graph fact so the UI never shows an edge as both open and active.
    """
    now = str(now_iso or utc_now())
    expired_ids: list[int] = []
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT id FROM closures
               WHERE status='approved' AND expires_at IS NOT NULL AND expires_at!=''
                 AND expires_at<=? ORDER BY id""",
            (now,),
        ).fetchall()
        for row in rows:
            closure_id = int(row["id"])
            changed = conn.execute(
                """UPDATE closures SET status='expired',application_status='removed',
                   applied_at=?,reroute_message='Expired automatically; reroute pending'
                   WHERE id=? AND status='approved'""",
                (now, closure_id),
            )
            if changed.rowcount:
                expired_ids.append(closure_id)
    if not expired_ids:
        return []

    revision = _bump_closure_revision("road closure expiry", expired_ids[0] if len(expired_ids) == 1 else None)
    placeholders = ",".join("?" for _ in expired_ids)
    with connect() as conn:
        conn.execute(
            f"UPDATE closures SET applied_revision=? WHERE id IN ({placeholders})",
            (revision, *expired_ids),
        )
    label = ", ".join(f"#{closure_id}" for closure_id in expired_ids)
    reason = f"Road closure expired automatically: {label}"
    _mark_routes_stale(reason, "system")
    _set_pending_reroute(reason, expired_ids[0] if len(expired_ids) == 1 else None)
    log_event(
        "closure.expired.automatic",
        {"closure_ids": expired_ids, "revision": revision, "expired_at": now},
        "system",
    )
    return expired_ids


def list_closures(*, expire: bool = True) -> list[dict[str, Any]]:
    # Most callers want expiry reconciliation before reading. app_state() has
    # already performed that reconciliation once at the start of the heartbeat,
    # so it opts out here to avoid a duplicate write-transaction/check every
    # refresh.
    if expire:
        expire_due_closures()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM closures ORDER BY id DESC").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try: item["geometry"] = json.loads(item.pop("geometry_json") or "[]")
        except Exception: item["geometry"] = []
        result.append(item)
    return result


def _apply_closure_to_active_input(closure_id: int, revision: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "input_updated": False,
        "input_revision": int(revision),
        "input_path": str(settings.input_txt),
    }
    try:
        check = preflight_status()
        structural = {item["id"]: item["ok"] for item in check.get("checks", [])}
        if not all(structural.get(key, False) for key in ("depot", "network", "customers", "access")):
            result["input_message"] = "Closure is active, but solver input waits for a valid plan and graph"
            return result
        summary = materialize_solver_instance()
        # materialize_solver_instance() already writes the authoritative input
        # identity. Add closure metadata without replacing its hashes/signature.
        state = get_setting("active_input_state") or {}
        state.update({
            "revision": int(revision),
            "closure_id": int(closure_id),
            "updated_at": utc_now(),
            "removed_edges": summary.get("approved_closures_removed", []),
        })
        set_setting("active_input_state", state)
        result.update({
            "input_updated": True,
            "input_message": "Approved edge was removed and input.txt was regenerated",
            "removed_edge_count": len(summary.get("approved_closures_removed", [])),
        })
        return result
    except Exception as exc:
        result["input_message"] = f"Closure is active; input regeneration needs review: {exc}"
        return result


def _set_pending_reroute(reason: str, closure_id: int | None = None) -> None:
    set_setting("pending_reroute", {
        "pending": True,
        "reason": str(reason),
        "closure_id": int(closure_id) if closure_id is not None else None,
        "requested_at": utc_now(),
    })


def drain_pending_reroute() -> int | None:
    pending = get_setting("pending_reroute") or {}
    if not pending.get("pending"):
        return None
    if list_active_jobs(include_evidence=False):
        return None
    try:
        job_id = queue_solve(False, reason=str(pending.get("reason") or "Deferred road-closure reroute"))
    except Exception:
        return None
    set_setting("pending_reroute", {**pending, "pending": False, "queued_at": utc_now(), "job_id": job_id})
    closure_id = pending.get("closure_id")
    if closure_id is not None:
        with connect() as conn:
            conn.execute(
                "UPDATE closures SET reroute_job_id=?,reroute_deferred=0,reroute_message=? WHERE id=?",
                (job_id, "Deferred reroute queued automatically", int(closure_id)),
            )
    log_event("reroute.deferred.queued", {"job_id": job_id, **pending}, "system")
    return job_id


def _queue_closure_reroute(reason: str, closure_id: int | None = None) -> tuple[int | None, bool, str | None]:
    """Queue a reroute when the optimizer is idle without undoing the decision.

    A closure approval is an operational fact and must be stored immediately.
    If another heavy job is active, the reroute is explicitly deferred instead
    of throwing after the approval has already been committed.
    """
    try:
        return queue_solve(False, reason=reason), False, None
    except ValueError as exc:
        _set_pending_reroute(reason, closure_id)
        return None, True, str(exc)


def decide_closure(closure_id: int, approve: bool, actor: str, rerun: bool = True) -> dict[str, Any]:
    status = "approved" if approve else "rejected"
    now = utc_now()
    revision = 0
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM closures WHERE id=?", (closure_id,)).fetchone()
        if not row:
            raise ValueError("Road report not found")
        if str(row["status"]) != "pending":
            raise ValueError(f"Road report #{closure_id} has already been decided ({row['status']})")
        if approve:
            revision = _bump_closure_revision("road closure approved", closure_id, conn=conn)
            conn.execute(
                """UPDATE closures SET status=?,approved_at=?,approved_by=?,application_status='applied',
                   applied_at=?,applied_revision=?,reroute_message='' WHERE id=?""",
                (status, now, actor, now, revision, closure_id),
            )
        else:
            conn.execute(
                "UPDATE closures SET status=?,approved_at=NULL,approved_by=?,application_status='rejected',reroute_message='' WHERE id=?",
                (status, actor, closure_id),
            )
    input_result: dict[str, Any] = {"input_updated": False}
    job_id = None
    deferred = False
    deferred_reason = None
    if approve:
        _mark_routes_stale(f"approved closed road segment #{closure_id}", actor)
        input_result = _apply_closure_to_active_input(closure_id, revision)
        if rerun:
            job_id, deferred, deferred_reason = _queue_closure_reroute(
                f"Approved closed road segment #{closure_id}", closure_id
            )
        with connect() as conn:
            conn.execute(
                """UPDATE closures SET reroute_job_id=?,reroute_deferred=?,reroute_message=? WHERE id=?""",
                (
                    job_id,
                    1 if deferred else 0,
                    deferred_reason or ("Reroute queued" if job_id else "Applied without reroute"),
                    closure_id,
                ),
            )
    details = {
        "closure_id": closure_id,
        "status": status,
        "application_status": "applied" if approve else "rejected",
        "applied_revision": revision,
        "reroute_job_id": job_id,
        "reroute_deferred": deferred,
        "deferred_reason": deferred_reason,
        **input_result,
    }
    log_event("closure.decision", details, actor)
    return {"id": closure_id, **details}

def deactivate_closure(closure_id: int, actor: str, rerun: bool = True) -> dict[str, Any]:
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM closures WHERE id=?", (closure_id,)).fetchone()
        if not row:
            raise ValueError("Road report not found")
        if str(row["status"]) != "approved":
            raise ValueError(f"Road closure #{closure_id} is not currently active")
        revision = _bump_closure_revision("road reopened", closure_id, conn=conn)
        conn.execute(
            """UPDATE closures SET status='expired',application_status='removed',applied_at=?,
               applied_revision=?,reroute_message='' WHERE id=?""",
            (utc_now(), revision, closure_id),
        )
    _mark_routes_stale(f"road reopened #{closure_id}", actor)
    input_result = _apply_closure_to_active_input(closure_id, revision)
    job_id = None
    deferred = False
    deferred_reason = None
    if rerun:
        job_id, deferred, deferred_reason = _queue_closure_reroute(
            f"Road reopened #{closure_id}", closure_id
        )
    with connect() as conn:
        conn.execute(
            "UPDATE closures SET reroute_job_id=?,reroute_deferred=?,reroute_message=? WHERE id=?",
            (job_id, 1 if deferred else 0, deferred_reason or ("Reroute queued" if job_id else "Reopened"), closure_id),
        )
    details = {
        "closure_id": closure_id,
        "reroute_job_id": job_id,
        "reroute_deferred": deferred,
        "deferred_reason": deferred_reason,
        "applied_revision": revision,
        **input_result,
    }
    log_event("closure.reopened", details, actor)
    return {"id": closure_id, "status": "expired", "application_status": "removed", **details}

def operational_context(
    _places: list[dict[str, Any]] | None = None,
    _closures: list[dict[str, Any]] | None = None,
    _settings: dict[str, Any] | None = None,
    _source: dict[str, Any] | None = None,
    _source_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    places = _places if _places is not None else list_places()
    depot = next((p for p in places if p["role"] == "depot"), None)
    customers = [p for p in places if p["role"] == "customer"]
    cached = _settings or get_settings((
        "network_summary", "route_state", "closure_revision", "active_input_state",
        "pending_reroute", "fleet", "solver", "network_stale",
    ))
    network = cached.get("network_summary") or {}
    network_stale = bool((cached.get("network_stale") or {}).get("stale"))
    route_state = cached.get("route_state") or {"stale": True, "reason": "No route has been published"}
    closure_revision = cached.get("closure_revision") or {"revision": 0}
    input_state = cached.get("active_input_state") or {}
    pending_reroute = cached.get("pending_reroute") or {"pending": False}
    fleet = cached.get("fleet") or {}
    solver = cached.get("solver") or {}
    closures = _closures if _closures is not None else list_closures()
    active_closures = [c for c in closures if c.get("status") == "approved"]
    pending_closures = [c for c in closures if c.get("status") == "pending"]
    graph_id = str(network.get("cache_key") or "")[:12] or None
    source = _source if _source is not None else region_source_status(False)
    source_coverage = _source_coverage if _source_coverage is not None else active_source_coverage(places, source)
    source_current = bool(source.get("ready")) and not (
        source_coverage.get("known") and source_coverage.get("covers_all") is False
    )
    return {
        "source": {
            "mode": "regional_offline", "ready": source_current, "verified": bool(source.get("ready")),
            "region": source.get("region"), "coverage": source_coverage,
        },
        "graph": {
            "ready": bool(GRAPH_STORE.available() and network and not network_stale),
            "id": graph_id, "nodes": network.get("nodes"), "edges": network.get("edges"),
            "bbox": network.get("bbox"), "radius_m": fleet.get("operating_radius_m"),
            "network_type": network.get("network_type") or fleet.get("network_type"),
            "cache_hit": network.get("cache_hit"), "built_at": network.get("built_at"),
        },
        "depot": {
            "id": depot.get("id"), "name": depot.get("name"), "lat": depot.get("lat"), "lon": depot.get("lon"),
            "access_verified": bool(depot.get("access_verified")),
        } if depot else None,
        "plan": {
            "customer_count": len(customers),
            "verified_count": sum(1 for p in customers if p.get("access_verified")),
            "total_demand": sum(float(p.get("demand") or 0) for p in customers),
        },
        "closures": {
            "active": len(active_closures), "pending": len(pending_closures),
            "revision": int(closure_revision.get("revision", 0)),
            "input_revision": input_state.get("revision"),
            "pending_reroute": bool(pending_reroute.get("pending")),
        },
        "routes": route_state,
        "solver": {"profile": "auto_dynamic", "clustering": solver.get("clustering", "auto")},
    }



def workflow_state(
    places: list[dict[str, Any]],
    values: dict[str, Any],
    source: dict[str, Any],
    source_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One backend-owned workflow contract shared by every page.

    Pages should display this state rather than inventing different prerequisite
    rules. Network/access are repairable by Optimize; source/depot/customers are
    true user prerequisites. Completed graph work is therefore reusable and never
    presented as a mandatory repeated step.
    """
    depot = next((p for p in places if p.get("role") == "depot"), None)
    customers = [p for p in places if p.get("role") == "customer"]
    network = values.get("network_summary") or {}
    network_stale = bool((values.get("network_stale") or {}).get("stale"))
    graph_ready = bool(network) and not network_stale and GRAPH_STORE.available()
    current_snap_max = float((values.get("fleet") or {}).get("snap_max_m", 350))
    access_ready = bool(places) and all(
        bool(p.get("access_verified"))
        and p.get("access_distance_m") is not None
        and float(p.get("access_distance_m") or 0.0) <= current_snap_max
        for p in places
    ) and graph_ready
    route_state = values.get("route_state") or {}
    route_current = bool(route_state.get("route_version")) and route_state.get("stale") is False
    solution_source = str(route_state.get("solution_source") or "")
    optimization_completed = bool(
        route_current
        and (
            route_state.get("optimization_completed")
            or route_state.get("optimization_checked_at")
            or solution_source == "cpp_optimizer"
        )
    )
    revision = values.get("settings_revision") or {"fleet": 0, "solver": 0}
    route_solver_revision = int(route_state.get("solver_revision", -1))
    solver_revision = int(revision.get("solver", 0))
    optimization_current = (
        route_current
        and optimization_completed
        and route_solver_revision == solver_revision
    )
    if not route_current:
        route_phase = "stale" if route_state.get("route_version") else "empty"
    elif not optimization_completed:
        route_phase = "prepared"
    elif solution_source == "cpp_optimizer":
        route_phase = "optimized"
    else:
        route_phase = "reviewed"
    input_state = values.get("active_input_state") or {}

    source_coverage = source_coverage if source_coverage is not None else active_source_coverage(places, source)
    source_current = bool(source.get("ready")) and not (
        source_coverage.get("known") and source_coverage.get("covers_all") is False
    )
    completed = {
        "source": source_current,
        "depot": bool(depot),
        "customers": bool(customers),
        "graph": graph_ready,
        "access": access_ready,
        "input": bool(
            input_state.get("current")
            and input_state.get("source_signature")
            and input_state.get("input_path")
            and Path(str(input_state.get("input_path"))).exists()
        ),
        "route": route_current,
        "route_prepared": route_current,
        "optimization_completed": optimization_completed,
        "optimization_current": optimization_current,
    }
    if not completed["source"]:
        next_action = {"key": "install_roads", "view": "command", "label": "Choose operating region", "automatic": False}
    elif not completed["depot"]:
        next_action = {"key": "choose_depot", "view": "plan", "label": "Choose depot", "automatic": False}
    elif not completed["customers"]:
        next_action = {"key": "add_customers", "view": "plan", "label": "Add or import work points", "automatic": False}
    elif not completed["graph"] or not completed["access"]:
        next_action = {
            "key": "optimize_auto_repair", "view": "optimize", "label": "Optimize — graph will be prepared automatically",
            "automatic": True, "reason": "operating graph/access is missing or stale",
        }
    elif not completed["route"]:
        next_action = {"key": "optimize", "view": "optimize", "label": "Optimize current plan", "automatic": False}
    elif not completed["optimization_completed"]:
        next_action = {
            "key": "continue_optimization", "view": "optimize",
            "label": "Initial plan prepared — run the optimizer to finish routing",
            "automatic": False,
        }
    elif not completed["optimization_current"]:
        next_action = {"key": "reoptimize_settings", "view": "optimize", "label": "Solver settings changed — run Optimize to apply them", "automatic": False}
    else:
        next_action = {"key": "dispatch", "view": "dispatch", "label": "Open current fleet plan", "automatic": False}

    return {
        "completed": completed, "next_action": next_action,
        "graph_reusable": graph_ready, "graph_id": str(network.get("cache_key") or "")[:12] or None,
        "depot_id": depot.get("id") if depot else None, "customer_count": len(customers),
        "route_version": route_state.get("route_version"),
        "route_phase": route_phase,
        "optimization_outcome": route_state.get("optimization_outcome", "not_started"),
    }


def _with_input_currentness(
    payload: dict[str, Any] | None,
    active_input: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Annotate source-scoped analysis without destroying historical evidence."""
    if not isinstance(payload, dict):
        return payload
    result = dict(payload)
    receipt = result.get("source_receipt") or {}
    active = active_input or {}
    has_result = bool(
        result.get("available")
        or result.get("used")
        or result.get("preview")
        or result.get("validation")
        or result.get("methods")
    )
    if not has_result:
        result.setdefault("current", False)
        result.setdefault("stale", False)
        return result
    signatures_match = bool(
        receipt.get("source_signature")
        and active.get("source_signature")
        and receipt.get("source_signature") == active.get("source_signature")
    )
    input_hashes_match = bool(
        receipt.get("input_sha256")
        and receipt.get("dataset_sha256")
        and receipt.get("input_sha256") == active.get("input_sha256")
        and receipt.get("dataset_sha256") == active.get("dataset_sha256")
    )
    current = bool(active.get("current") and signatures_match and input_hashes_match)
    result["current"] = current
    result["stale"] = not current
    if not current:
        result["stale_reason"] = (
            "This result belongs to an older materialized plan, fleet, capacity, graph, or closure revision. "
            "Run the clustering test or benchmark again for the current input."
        )
    else:
        result.pop("stale_reason", None)
    return result


def app_state(include_routes: bool = True) -> dict[str, Any]:
    expire_stale_jobs_if_due()
    expire_due_closures()
    try:
        drain_pending_reroute()
    except Exception:
        pass
    with connect() as conn:
        jobs = [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 25").fetchall()]
        events = [dict(row) for row in conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50").fetchall()]
        versions = [dict(row) for row in conn.execute(
            "SELECT id,created_at,source_job_id,route_count,customer_count FROM route_versions ORDER BY id DESC LIMIT 15"
        ).fetchall()]
        latest_meta_row = conn.execute(
            "SELECT id,created_at,source_job_id,route_count,customer_count FROM route_versions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    for job in jobs:
        try:
            job["result"] = json.loads(job.pop("result_json"))
        except Exception:
            job["result"] = {}
        job["progress"] = round(float(job.get("progress") or 0.0), 1)
    for event in events:
        try:
            event["details"] = json.loads(event.pop("details_json"))
        except Exception:
            event["details"] = {}
    latest_meta = dict(latest_meta_row) if latest_meta_row else None
    latest_routes = latest_route_version() if include_routes and latest_meta else None

    setting_keys = (
        "fleet", "solver", "ui", "network_summary", "latest_clustering",
        "latest_scenario_contract", "latest_feasibility", "latest_baseline_certificate",
        "convergence_summary_cached", "clustering_benchmark_cached", "artifact_gallery_cached",
        "network_stale", "route_state", "active_input_state", "pending_reroute",
        "closure_revision", "settings_revision", "solver_transaction",
    )
    values = get_settings(setting_keys)
    places = list_places()
    closures = list_closures(expire=False)
    source = region_source_status(False)
    browse = region_target_status()
    source_coverage = active_source_coverage(places, source)
    distance_check = plan_distance_check(places, values.get("fleet") or {})
    active_input = values.get("active_input_state") or {}
    latest_clustering = _with_input_currentness(values.get("latest_clustering"), active_input)
    clustering_benchmark = _with_input_currentness(
        values.get("clustering_benchmark_cached") or {"available": False, "methods": [], "figures": []},
        active_input,
    )
    convergence = dict(values.get("convergence_summary_cached") or {"available": False})
    convergence_receipt = dict(convergence.get("source_receipt") or {})
    has_convergence_provenance = bool(
        convergence_receipt.get("input_sha256")
        and convergence_receipt.get("dataset_sha256")
    )
    if has_convergence_provenance:
        evidence_input_current = bool(
            active_input.get("current")
            and convergence_receipt.get("input_sha256") == active_input.get("input_sha256")
            and convergence_receipt.get("dataset_sha256") == active_input.get("dataset_sha256")
            and (
                not convergence_receipt.get("source_signature")
                or convergence_receipt.get("source_signature") == active_input.get("source_signature")
            )
        )
        convergence["input_current"] = evidence_input_current
        convergence["historical"] = not evidence_input_current
        if not evidence_input_current:
            convergence["historical_reason"] = (
                "The last completed solver evidence is preserved, but the live plan, fleet, graph, or closures now differ."
            )
    else:
        convergence["input_current"] = None
    preview_customer_count = max(1, sum(1 for place in places if place.get("role") == "customer"))
    solver_dynamic_policy = dynamic_solver_policy(preview_customer_count, values.get("solver") or {})

    # /api/state is the browser heartbeat. Do not retransmit persistence-only
    # columns for every stop: at 450 customers those unused SQLite fields add
    # ~80 KB per refresh over a tunnel. Keep the complete records internally
    # for validation, while exposing exactly the fields the operational UI edits,
    # maps, and audits.
    state_place_keys = (
        "id", "role", "name", "address", "lat", "lon", "demand",
        "service_s", "earliest_s", "latest_s", "external_id",
        "access_lat", "access_lon", "access_road", "access_distance_m",
        "access_osm_node", "access_highway", "access_direction", "access_verified",
    )
    state_places = [{key: place.get(key) for key in state_place_keys} for place in places]
    return {
        "fleet": values.get("fleet"),
        "solver": values.get("solver"),
        "ui": values.get("ui"),
        "network": values.get("network_summary"),
        "places": state_places,
        "closures": closures,
        "jobs": jobs,
        "events": events,
        "route_versions": versions,
        "latest_route_summary": latest_meta,
        "latest_routes": latest_routes,
        "latest_clustering": latest_clustering,
        "latest_scenario_contract": values.get("latest_scenario_contract"),
        "latest_feasibility": values.get("latest_feasibility"),
        "latest_baseline_certificate": values.get("latest_baseline_certificate"),
        "convergence_summary": convergence,
        "clustering_benchmark": clustering_benchmark,
        "artifact_gallery": values.get("artifact_gallery_cached") or [],
        "osm_source": source,
        "osm_browse": browse,
        "osm_source_coverage": source_coverage,
        "plan_distance_check": distance_check,
        "preflight": preflight_status(places, values, source, source_coverage),
        "network_stale": values.get("network_stale") or {"stale": False},
        "operational_context": operational_context(places, closures, values, source, source_coverage),
        "workflow": workflow_state(places, values, source, source_coverage),
        "route_state": values.get("route_state") or {"stale": True, "reason": "No route has been published"},
        "active_input_state": active_input,
        "solver_transaction": values.get("solver_transaction") or {
            "status": "idle",
            "public_artifact_policy": "last_complete_valid_run",
        },
        "pending_reroute": values.get("pending_reroute") or {"pending": False},
        "solver_profiles": solver_profiles(),
        "solver_dynamic_policy": solver_dynamic_policy,
        "solver_advanced_schema": solver_advanced_schema(),
        "settings_revision": values.get("settings_revision") or {"fleet": 0, "solver": 0},
        "server_time": utc_now(),
    }


def _job_log_path(audit_path: Path, source: str) -> Path:
    mapping = {
        "raw": audit_path.with_suffix(".raw.log"),
        "stdout": audit_path.with_suffix(".stdout.log"),
        "stderr": audit_path.with_suffix(".stderr.log"),
        "audit": audit_path,
    }
    return mapping.get(source, audit_path)


def read_job_log(job_id: int, source: str = "raw") -> str:
    with connect() as conn:
        row = conn.execute("SELECT log_path FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row or not row["log_path"]:
        return ""
    path = _job_log_path(Path(row["log_path"]), source)
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _runtime_file_registry() -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {
        "input": {"label": "input.txt", "path": settings.input_txt, "group": "solver input", "description": "Exact text fed to C++ through stdin"},
        "dataset": {"label": "dataset.json", "path": settings.dataset_json, "group": "solver input", "description": "Full graph, nodes, edges, orders, and OSM mapping"},
        "dataset_summary": {"label": "dataset_summary.json", "path": settings.dataset_summary_json, "group": "solver input", "description": "Compact counts, semantics, hashes, and contract checks"},
        "solver_provenance": {"label": "solver_provenance.json", "path": settings.solver_provenance, "group": "optimizer provenance", "description": "Optimizer source identity, SHA-256, compile flags, and reproducibility metadata"},
        "solver_invocation": {"label": "solver_invocation.json", "path": settings.solver_invocation_json, "group": "execution", "description": "Last complete valid run: exact argv, input hashes, private attempt paths, policy, and retry outcomes"},
        "solver_stdout": {"label": "solver_output.txt", "path": settings.solver_output, "group": "execution", "description": "Last complete valid C++ stdout; interrupted attempts remain in their separate job streams"},
        "solver_stderr": {"label": "solver_stderr.txt", "path": settings.solver_stderr, "group": "execution", "description": "Last complete valid native cerr/stderr plus FleetRoute lifecycle evidence; every attempt also has a per-job stream"},
        "solver_first_attempt_stdout": {"label": "solver_attempt_with_clustering.txt", "path": RUNTIME_DIR / "solver_attempt_with_clustering.txt", "group": "execution", "description": "Preserved stdout from a failed clustering warm-start attempt"},
        "solver_first_attempt_stderr": {"label": "solver_attempt_with_clustering.stderr.txt", "path": RUNTIME_DIR / "solver_attempt_with_clustering.stderr.txt", "group": "execution", "description": "Preserved stderr/cerr from a failed clustering warm-start attempt"},
        "convergence": {"label": "convergence.csv", "path": settings.convergence_csv, "group": "search evidence", "description": "Last complete valid best-so-far and worker search trace"},
        "run_summary": {"label": "run_summary.csv", "path": settings.run_summary_csv, "group": "search evidence", "description": "Last complete valid per-run solver summary"},
        "routes": {"label": "routes.json", "path": settings.routes_json, "group": "fleet plan", "description": "Latest retained fleet-plan payload and route version"},
        "clusters": {"label": "clusters.csv", "path": settings.clusters_csv, "group": "clustering", "description": "Selected warm-start assignments"},
        "cluster_summary": {"label": "cluster_summary.csv", "path": settings.cluster_summary_csv, "group": "clustering", "description": "Cluster load and feasibility summary"},
        "cluster_timing": {"label": "cluster_timing.csv", "path": settings.cluster_timing_csv, "group": "clustering", "description": "Clustering method runtime"},
    }
    with connect() as conn:
        row = conn.execute("SELECT id,log_path FROM jobs ORDER BY id DESC LIMIT 1").fetchone()
    if row and row["log_path"]:
        audit = Path(row["log_path"])
        for source, label, description in [
            ("raw", "latest_job.raw.log", "Merged process stream with command and exit boundaries"),
            ("stdout", "latest_job.stdout.log", "Decoded stdout text from child processes in the latest job"),
            ("stderr", "latest_job.stderr.log", "Decoded stderr text from child processes in the latest job"),
            ("audit", "latest_job.audit.log", "FleetRoute stages, commands, heartbeats, and errors"),
        ]:
            files[f"latest_job_{source}"] = {
                "label": label,
                "path": _job_log_path(audit, source),
                "group": f"job #{int(row['id'])}",
                "description": description,
                "job_id": int(row["id"]),
            }
    return files


def developer_runtime_overview() -> dict[str, Any]:
    """Return runtime evidence without rescanning a large dataset unnecessarily.

    Materialization already performs the expensive edge-by-edge contract check and
    records content hashes in dataset_summary.json. We reuse that certified result
    while the on-disk hashes still match, and fall back to a full validation only
    after external modification or when the summary is missing.
    """
    registry = _runtime_file_registry()
    summary: dict[str, Any] = {}
    if settings.dataset_summary_json.is_file():
        try:
            summary = json.loads(settings.dataset_summary_json.read_text(encoding="utf-8"))
        except Exception:
            summary = {}
    certified_files = summary.get("files") or {}

    items: list[dict[str, Any]] = []
    actual_hashes: dict[str, str | None] = {}
    for key, spec in registry.items():
        path = Path(spec["path"])
        try:
            stat = path.stat()
            exists = path.is_file()
        except OSError:
            stat = None
            exists = False
        size = int(stat.st_size) if exists and stat is not None else 0
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if exists and stat is not None else None
        digest = None
        if exists:
            # input/dataset are hash-cached when materialized; logs/output are
            # limited to 32 MiB to keep Evidence & Logs instantaneous.
            if key in {"input", "dataset"} or size <= 32 * 1024 * 1024:
                digest = _sha256_file(path)
        if key == "input":
            actual_hashes["input.txt"] = digest
        elif key == "dataset":
            actual_hashes["dataset.json"] = digest
        try:
            relative = str(path.resolve().relative_to(RUNTIME_DIR.resolve()))
            download_url = "/api/artifacts/" + relative.replace(os.sep, "/")
        except ValueError:
            download_url = None
        items.append({
            "key": key,
            "label": spec["label"],
            "group": spec["group"],
            "description": spec["description"],
            "exists": exists,
            "bytes": size,
            "modified_at": modified,
            "sha256": digest,
            "download_url": download_url,
            "job_id": spec.get("job_id"),
        })

    summary_matches = bool(summary and summary.get("contract", {}).get("ok"))
    for name in ("input.txt", "dataset.json"):
        expected = (certified_files.get(name) or {}).get("sha256")
        actual = actual_hashes.get(name)
        if not expected or not actual or str(expected) != str(actual):
            summary_matches = False
            break
    if summary_matches:
        contract = dict(summary.get("contract") or {})
        contract["runtime_integrity"] = "certified materialization hashes match current files"
        contract["validation_source"] = "dataset_summary.json"
    else:
        try:
            input_text = settings.input_txt.read_text(encoding="utf-8")
            dataset = _load_materialized_dataset()
            contract = _validate_input_contract_text(input_text, dataset)
            contract["validation_source"] = "full runtime revalidation"
        except Exception as exc:
            contract = {"ok": False, "error": str(exc), "checks": [{"id": "runtime_contract", "ok": False, "detail": str(exc)}]}

    try:
        command = solver_command_preview()
    except Exception as exc:
        command = {"display": "Unavailable: " + str(exc), "argv": [], "input_path": str(settings.input_txt)}

    last_invocation = None
    if settings.solver_invocation_json.is_file():
        try:
            last_invocation = json.loads(settings.solver_invocation_json.read_text(encoding="utf-8"))
        except Exception as exc:
            last_invocation = {"error": "Could not parse solver_invocation.json: " + str(exc), "attempts": []}

    provenance: dict[str, Any] = {}
    try:
        if settings.solver_provenance.is_file():
            provenance = json.loads(settings.solver_provenance.read_text(encoding="utf-8"))
        active_solver_sha = _sha256_file(settings.solver_cpp) if settings.solver_cpp.is_file() else None
        provenance["active_solver_source_sha256"] = active_solver_sha
        provenance["source_matches_declared"] = bool(
            active_solver_sha
            and provenance.get("integrated_solver_source_sha256") == active_solver_sha
        )
    except Exception as exc:
        provenance = {"source_matches_declared": False, "error": str(exc)}

    setting_values = get_settings(("fleet", "solver", "network_summary", "network_stale"))
    return {
        "runtime_dir": str(RUNTIME_DIR),
        "solver_provenance": provenance,
        "generated_at": utc_now(),
        "contract": contract,
        "command": command,
        "last_invocation": last_invocation,
        "effective_settings": {
            "fleet": setting_values.get("fleet") or {},
            "solver": setting_values.get("solver") or {},
            "network_summary": setting_values.get("network_summary") or {},
            "network_stale": setting_values.get("network_stale") or {},
        },
        "files": items,
        "stream_semantics": {
            "solver_output.txt": "stdout only; final route/report stream used for route parsing",
            "solver_stderr.txt": "stderr/cerr evidence; native diagnostics plus FleetRoute START/progress/terminal lifecycle lines",
            "latest_job.raw.log": "merged reader-arrival text stream plus FleetRoute command/exit boundaries",
            "latest_job.stdout.log": "decoded stdout text only",
            "latest_job.stderr.log": "decoded stderr text only",
            "latest_job.audit.log": "structured FleetRoute audit trace",
        },
    }


def read_runtime_file(key: str, offset: int = 0, limit: int = 512 * 1024) -> dict[str, Any]:
    registry = _runtime_file_registry()
    if key not in registry:
        raise ValueError("Unknown runtime file key")
    path = Path(registry[key]["path"])
    if not path.is_file():
        return {"key": key, "label": registry[key]["label"], "exists": False, "offset": 0, "next_offset": 0, "size": 0, "text": "", "complete": True}
    size = path.stat().st_size
    safe_offset = max(0, min(int(offset), size))
    safe_limit = max(1, min(int(limit), 2 * 1024 * 1024))
    with path.open("rb") as handle:
        handle.seek(safe_offset)
        raw = handle.read(safe_limit)
    return {
        "key": key,
        "label": registry[key]["label"],
        "exists": True,
        "offset": safe_offset,
        "next_offset": safe_offset + len(raw),
        "size": size,
        "text": raw.decode("utf-8", errors="replace"),
        "complete": safe_offset + len(raw) >= size,
    }
