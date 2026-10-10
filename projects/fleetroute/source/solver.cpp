// E1 PHASE-SPECIALIZED ROAD ENGINE — 2026-08-31
// E25 architecture: phase-specialized search with low-latency two-wave epochs, inherited-elite late exploitation, and road-operator pruning.
// Wave A performs heterogeneous parallel discovery; its candidates are immediately
// admitted to the persistent diversity archive. Wave B then spends the remaining
// epoch on region intensification + elite breeding from that *fresh* archive,
// eliminating the former 8-10 s information delay between discovery and recombination.
// E3 persistent destroy/intensity learning, hardware-aware role scheduling, quench,
// adaptive local search, archive quality guards, and road-enabled tail are retained.
// Small/tight instances below phase_structure_min_customers retain legacy M1.
// V40 FROZEN research solver.
// Consolidates the audited search core with:
//  - dual hard/search incumbents and deadline-censored evidence
//  - explicit portfolio worker roles and fleet descent
//  - cooperative stage deadlines and removal of double refinement
//  - feasible path relinking, directed 2-opt semantics, sparse CVRP Split
//  - route-local granular tabu evaluation
//  - work-conserving intensification tail
//  - O(M) direct-arc dense-matrix construction and no redundant road/direct precompute
//  - explicit search-vs-solve budget scope and phase timing ledger
// AAAI_HOMBERGER_200_SCALING_STRESS_FROZEN_V1_ADAPTER_PATCH
// AAAI_PAPER_PROTOCOL_FROZEN_V2
// Final reporting/instrumentation cleanup. Search operators and hot-path
// objective consistency and benchmark isolation were audited and corrected.
//  - initialized summaries and robust comparison selection
//  - correct Greedy/Cluster/Savings baseline attribution
//  - full-pipeline runtime and aggregate SA statistics
//  - active-truck fleet statistics; depot-only routes hidden
// V14 research upgrade: V13 robust calibration sampled from active routes only
//  - preserves all V6 invariants and multi-step hard-feasible fleet descent
//  - when direct source-route elimination is blocked, a bounded ejection chain
//    can move one blocking customer out of a destination route, insert the source
//    customer, and immediately reinsert the ejected customer elsewhere
//  - when any worker discovers a strictly smaller hard-feasible fleet, selected
//    peer workers migrate to that lexicographically dominant basin and reheat
//    their local search; one explorer worker is kept unmigrated for diversity
//  - thread-safe coarse profiling; noisy diagnostics disabled by default
//  - HGS-lite disabled by default, retained only for compatibility
// VRP solver — v8 patched: record/per-route max single-trip load and print it.
// V33 research branch: explicit worker roles + ablatable fleet descent + unbiased candidate-route affinity.
// Worker role is passed explicitly and is never inferred from seed arithmetic.
// Extra fixes in this version:
//  - same-route swap / relocate handled correctly
//  - cross-exchange skips same-route cases
//  - route rec omputation is more consistent
//  - quieter recompute loop (no repeated stderr spam)
//  - output formatting rstored after percentage prints
//
// Build:
//   g++ -std=c++17 -O3 -pthread solver_lns_benchmark.cpp -o solver_lns_benchmark

#include <bits/stdc++.h>
#include <thread>
#include <mutex>
#include <chrono>
#include <fstream>
#include <csignal>

#if defined(__x86_64__) || defined(__i386__)
#include <immintrin.h>
#endif

#ifndef VRP_PROFILE_DENSE_HITS
#define VRP_PROFILE_DENSE_HITS 0
#endif

using namespace std;
using Clock = chrono::steady_clock;
const double INF_D = 1e18;

static mutex console_log_mutex;

template <typename... Args>
static void safe_log_line(Args&&... args) {
    ostringstream oss;
    (oss << ... << std::forward<Args>(args));
    lock_guard<mutex> lock(console_log_mutex);
    cerr << oss.str() << "\n";
}

/* ---------------- Repair benchmark modes ---------------- */
enum class RepairMode {
    LEGACY,
    GREEDY_FAST,
    GREEDY_EXACT,
    REGRET_2,
    REGRET_3,
    REGRET_K
};

// V41 per-thread repair policy. This lets one portfolio worker use the cheap
// GREEDY_FAST reconstruction without mutating global configuration seen by
// sibling threads.
static thread_local bool tls_repair_mode_override_enabled = false;
static thread_local RepairMode tls_repair_mode_override = RepairMode::LEGACY;
static thread_local bool tls_disable_post_repair_polish = false;
// V57: barriered portfolio lanes can keep discoveries private until a stage
// boundary, avoiding race-dependent migrations/publication while ranking basins.
thread_local bool tls_defer_global_publish = false;

static const char *repair_mode_name(RepairMode mode) {
    switch (mode) {
        case RepairMode::GREEDY_FAST: return "greedy_fast";
        case RepairMode::GREEDY_EXACT: return "greedy_exact";
        case RepairMode::REGRET_2: return "regret2";
        case RepairMode::REGRET_3: return "regret3";
        case RepairMode::REGRET_K: return "regret_k";
        default: return "legacy";
    }
}

/* ---------------- Config ---------------- */
struct Config {
    /* ============================================================
    Problem / instance settings
    ============================================================ */
    int num_trucks = 4;
    double truck_capacity = 100.0;

    bool allow_splitting = false;
    bool allow_multi_trip = false;
    int max_trips_per_truck = 1;
    string capacity_mode = "strict";

    bool use_time_window = true;
    string objective_mode = "distance"; // distance, time, hybrid

    // Cost backend:
    //   road      = directed road graph + LineGraph + TDijkstra/PairwiseManager
    //   direct    = immediate explicit arc lookup, useful for complete-arc CVRPLIB-style input
    //   euclidean = complete symmetric metric from node coordinates
    string metric_mode = "euclidean";

    // Backward-compatible old flag.
    // If user passes --use_direct_arc_costs true, metric_mode becomes "direct".
    // If false, metric_mode becomes "road".
    bool use_direct_arc_costs = false;

    // Euclidean benchmark settings.
    // IMPORTANT: coordinates must be loaded into NodeC.lon/lat in meter-like units.
    // Do not use raw lon/lat degrees unless your generator projected them first.
    double euclidean_speed_kph = 30.0;
    string coords_csv = "";
    string initial_routes_file = "";             // common externally validated warm start
    double external_depot_earliest = -1.0;         // negative = keep default
    double external_depot_latest = -1.0;           // negative = keep default
    bool require_coords_for_euclidean = true;

    // Euclidean benchmark / branch-cut controls.
    // These are ignored in road/direct mode.
    bool euclidean_round_distance = true;          // CVRPLIB-style rounded EUC_2D
    bool euclidean_truncate_1_decimal = false;   // compatibility flag; unused here
    bool euclidean_branch_cuts = true;             // master switch for safe geometric cuts
    bool euclidean_candidate_2opt_cut = true;      // only try plausible 2-opt reconnect edges
    bool euclidean_uncross_routes = true;          // remove geometric crossings exactly
    int euclidean_uncross_passes = 30;             // max passes per route
    bool euclidean_ranked_insert_cut = true;       // rank insertion positions by delta
    int euclidean_insert_keep = 36;                // keep best K insertion positions per route
    double euclidean_gls_depot_arc_factor = 0.35;  // downweight depot arcs in GLS utility

    // Exact Euclidean CVRP intensification.
    // Safe: accepts only full-objective improving feasible moves.
    bool euclidean_deep_interroute = true;
    int euclidean_deep_interroute_rounds = 12;
    bool euclidean_deep_try_relocate = true;
    bool euclidean_deep_try_swap = true;

    // SWAP* Euclidean education.
    // Stronger than normal 1-1 swap: after swapping ownership,
    // each customer is reinserted at its best position in the other route.
    bool euclidean_swapstar = true;
    int euclidean_swapstar_rounds = 8;
    int euclidean_swapstar_scan_cap = 60000;

    // 2-opt* Euclidean education.
    // Swaps route tails between two routes. This is stronger than
    // one-customer relocate/swap when route partition is wrong.
    bool euclidean_two_opt_star = true;
    int euclidean_two_opt_star_rounds = 8;
    int euclidean_two_opt_star_scan_cap = 100000;

    /* ============================================================
    HGS-lite Euclidean CVRP
    ============================================================ */
    bool use_hgs_lite = false;
    bool euclidean_hgs_only = false;

    // Population should not be huge. Good split + education matters more.
    int hgs_population_size = 18;
    int hgs_generations = 80;
    int hgs_elite_keep = 5;

    // Mutation/diversity.
    double hgs_mutation_rate = 0.12;
    bool hgs_use_order_crossover = true;

    // Education is expensive, so do not deep-polish every child.
    bool hgs_educate_children = true;
    int hgs_deep_every = 8;              // deep interroute only every N accepted children
    int hgs_child_branch_passes = 8;     // temporary uncross passes during child education

    // Split options.
    bool hgs_allow_empty_routes = true;
    bool hgs_exact_fleet_split = true;

    // HGS population quality / diversity control.
    bool hgs_use_biased_fitness = true;
    double hgs_diversity_weight = 0.35;
    double hgs_duplicate_edge_distance = 0.03;
    int hgs_diversity_neighbors = 4;

    /* ============================================================
    Objective weights
    ============================================================ */
    // FleetRoute public objective contract: hybrid = distance_m + 0.25 * route_duration_s.
    // Time-only remains unscaled route duration. CO2 remains an observable metric,
    // not a hidden optimization term.
    double w_time = 0.25;
    double w_co2 = 0.001;
    double w_late = 10.0;
    double w_capacity = 1000.0;
    double w_trip_excess = 10000.0;
    double solomon_vehicle_penalty = 0.0;       // lexicographic CVRPTW fleet-first objective
    double co2_per_meter = 0.2;
    double w_wait = 0.02;                 // waiting seconds penalty, useful for TW
    bool tw_strict_insertion = true;      // reject repair insertions that violate TW
    bool tw_sort_seed_by_window = true;   // sort initial customers by latest time
    double tw_lateness_eps = 1e-7;

    bool tw_use_time_warp = true;

    // Allow infeasible TW routes during search, but never as final/global-best.
    bool tw_allow_soft_intermediate = true;

    // Time-warp penalty used during search.
    double tw_time_warp_penalty = 25.0;
    double tw_time_warp_penalty_min = 5.0;
    double tw_time_warp_penalty_max = 5000.0;
    double tw_time_warp_growth = 1.20;

    // For benchmark distance objective, usually keep waiting out of objective.
    bool tw_penalize_waiting_in_distance = false;

    double route_start_time_s = 8.0 * 3600.0;       // road-generator default
    bool euclidean_time_equals_distance = false;   // Solomon: time = distance

    /* ============================================================
    Run control / reproducibility
    ============================================================ */
    int sa_instances = 6;
    double sa_time_limit = 10.0;

    unsigned base_seed =
        (unsigned)chrono::duration_cast<chrono::milliseconds>(
            Clock::now().time_since_epoch()
        ).count();

    bool deterministic_seed = false;
    int stability_runs = 1;

    // Anytime governor / Colab-safe stop controls.
    // 0 means disabled. Hard limit always has priority.
    double hard_time_limit_s = 0.0;
    // V35: reserve a small explicit wall-clock tail for sequential
    // intensification modules that were previously placed *after* budget
    // saturation and therefore received zero compute. Zero preserves V34.
    double final_intensification_reserve_s = 0.0;

    // V40 benchmark semantics:
    //   search = legacy/paper-compatible clock starts after common warm start
    //   solve  = clock starts before method-specific warm start / HGS seed
    // Backend metric construction is always reported separately.
    string budget_scope = "search";
    bool work_conserving_tail = true;

    // V41: use the six cores as a heterogeneous portfolio rather than six
    // copies of the same search. The last slot can run a cheap feasible LNS.
    bool use_parallel_fast_worker = true;
    // Fraction of every SA worker allocation protected for deterministic
    // refinement of its hard-feasible incumbent.
    double sa_refinement_reserve_fraction = 0.0;
    // Exploiters may adopt a substantially better same-fleet global incumbent
    // after local stagnation; structural/explorer workers remain independent.
    bool use_same_fleet_migration = false;
    double same_fleet_migration_min_gain = 5.0;
    double same_fleet_migration_stagnation_s = 0.40;
    // Run complementary final intensifiers concurrently from one incumbent.
    bool parallel_intensification_tail = true;

    // V56 diagnostic lab: when diagnostic_probe_csv is non-empty, the supplied
    // --initial_routes_file is treated as a frozen incumbent. Each existing
    // neighborhood/search role receives the same isolated wall-clock allowance
    // from that exact state, then the solver exits. This distinguishes missing
    // capability from scheduling/throughput problems before changing production.
    string diagnostic_probe_csv = "";
    double diagnostic_probe_budget_s = 1.0;

    // V56 production candidate: barriered diversify/intensify tail. A single
    // one-shot parallel tail cannot exploit complementarity (e.g. an LNS move
    // can expose large gains to inter-route search only afterwards). This tail
    // alternates objective-improving local search -> parallel diversification ->
    // local search again, with all decisions based only on the benchmark objective.
    bool staged_portfolio_tail = false;
    double staged_portfolio_first_intensify_s = 0.75;
    double staged_portfolio_final_intensify_s = 1.00;
    int staged_portfolio_fast_lanes = 3;
    double staged_portfolio_post_fraction = 0.28;
    // V61 controlled scheduler A/B. "v60" preserves the 2S+2FAST+Frag+Explorer
    // layout; "s1f3fragx" replaces the duplicate second structural lane and
    // unproductive short-tail explorer with one extra FAST basin and an exploiter.
    string staged_portfolio_layout = "v60";

    double no_improve_stop_s = 0.0;
    double target_no_improve_stop_s = 0.0;
    double target_objective = 0.0;
    double meaningful_gain_abs = 500.0;
    double meaningful_gain_rel = 0.0015;

    /* ============================================================
    SA core
    ============================================================ */
    bool use_sa = true;
    double sa_T0 = 1000.0;
    double sa_alpha = 0.9996;
    bool auto_T0 = true;

    bool use_cross2 = true;

    // V33: fleet descent is now explicitly ablatable instead of being hard-wired
    // into worker slots 0-1. This is required for mechanism-level experiments.
    bool use_fleet_descent = true;

    // V33: candidate-route scoring can scan the whole route for its closest
    // structural affinity instead of stopping after the first K candidate-list
    // matches in route order. The legacy cap is retained for controlled A/B.
    bool candidate_route_unbiased_scan = false;

    // V21 fixed-time audit: 0 means unlimited.  A proposal cap is exposed only
    // for controlled fixed-work diagnostics; production fixed-time runs should
    // leave this at zero so hot-loop optimization cannot silently shorten SA.
    long long sa_max_effective_proposals = 0;

    /* ============================================================
    Global feature switches
    ============================================================ */
    bool use_greedy_baseline = true;

    // Clarke-Wright savings warm start.
    // Kept deliberately lightweight: it runs once in main, never inside SA workers.
    bool use_savings_warm_start = true;
    int savings_variants = 4;
    double savings_noise = 0.015;
    double savings_polish_time_s = 3.0;
    int savings_light_polish_rounds = 2;
    // Default 1 preserves the historically benchmarked one-relocation-per-round warm start.
    int savings_relocate_accepts_per_round = 1;
    bool savings_verbose = false;

    bool use_alns = true;
    bool use_elite_pool = true;
    bool use_path_relink = true;

    bool use_local_polish = true;
    bool use_final_polish = true;

    /* ============================================================
    Fleet-first structural descent (V10)
    ============================================================ */
    bool use_fleet_ejection_chain = true;
    int fleet_ejection_max_per_source = 3;
    int fleet_ejection_route_scan_cap = 14;
    int fleet_ejection_customer_scan_cap = 14;

    // Dominance-aware incumbent migration (DAIM). For fleet-first objectives,
    // a feasible K-1 incumbent dominates every feasible K solution regardless
    // of distance. Selected workers therefore stop spending exploitation time
    // in a dominated fleet basin once a smaller hard-feasible fleet is known.
    bool use_global_fleet_migration = true;
    int global_fleet_migration_period = 5000; // legacy iteration cadence, retained for CLI compatibility
    double global_fleet_migration_period_s = 0.25;
    double global_fleet_migration_reheat = 0.35;
    int global_fleet_migration_preserve_explorers = 2;

    /* ============================================================
    Speed / caching / evaluation
    ============================================================ */
    bool use_dense_pair_matrix = true;
    bool use_dirty_route_recompute = false;

    // Keep exact full recompute after destructive/global operators.
    bool full_recompute_after_lns = true;
    bool full_recompute_after_final_pipeline = true;

    /* ============================================================
    Logging / output files
    ============================================================ */
    bool log_convergence = true;
    bool verbose_trip_order = false;

    string convergence_csv = "convergence.csv";
    string run_summary_csv = "run_summary.csv";
    double convergence_sample_period_s = 0.25;
    long long convergence_max_rows = 250000;

    /* ============================================================
    Candidate lists / insertion limits
    ============================================================ */
    bool use_candidate_lists = true;
    int candidate_k = 32;
    int candidate_route_probe_k = 4;

    bool use_regret_repair = true;
    int regret_k = 4;

    // Controlled repair selector for the LNS paper benchmark.
    // LEGACY preserves --no_regret / --regret_k behavior.
    RepairMode repair_mode = RepairMode::LEGACY;

    // Dedicated Large Neighborhood Search benchmark mode.
    // It reuses the production destroy/repair path but bypasses SA and
    // disables unrelated final intensification so only repair mode differs.
    bool lns_benchmark_mode = false;
    long long lns_benchmark_iterations = 0; // 0 = time-budget run

    // Phase-specialized search. When positive, the production/full engine first
    // runs the isolated greedy-fast LNS kernel for this many seconds, then
    // hands the exact hard-feasible incumbent directly to the existing deep
    // pipeline under the same global search clock and hard time limit.
    double hybrid_fast_phase_s = 0.0;

    // E1 phase-specialized production engine. This is an orchestration layer
    // around the existing proven neighborhoods: structure acquisition first,
    // then persistent heterogeneous worker identities connected through a
    // diversity-aware elite archive. Disabled by default for clean A/B.
    bool use_phase_specialized_engine = false;
    int phase_structure_min_customers = 140;
    int phase_structure_parallel_min_customers = 350;
    double phase_structure_fraction = 0.12;
    double phase_structure_min_time_s = 4.0;
    double phase_structure_max_time_s = 45.0;
    double phase_structure_no_improve_s = 6.0;
    double phase_structure_destroy_min_ratio = 0.04;
    double phase_structure_destroy_max_ratio = 0.16;
    double phase_macro_destroy_min_ratio = 0.08;
    double phase_macro_destroy_max_ratio = 0.24;
    double phase_epoch_s = 10.0;
    int phase_archive_size = 8;
    double phase_archive_clone_distance = 0.015;
    double phase_archive_quality_weight = 0.58;
    double phase_archive_max_quality_gap = 0.08;
    double phase_parent_quality_band = 0.04;
    double phase_parent_min_distance = 0.035;
    int phase_worker_stale_epochs = 2;
    double phase_breeder_fraction = 0.70;

    // E3 scheduler / learned-search controls. Logical roles remain six, but the
    // number executing concurrently respects available compute by default.
    bool phase_respect_hardware_concurrency = true;
    int phase_min_active_workers = 2;
    double phase_role_credit_decay = 0.72;
    double phase_role_idle_bonus = 0.24;
    bool phase_persist_lns_policy = true;
    bool phase_adapt_destroy_intensity = true;
    double phase_macro_search_fraction = 0.72;
    double phase_macro_recovery_quality_gap = 0.022;
    bool phase_adaptive_region_policy = true;
    double phase_region_slice_fraction = 0.22;
    // E33: lane 4 is a deadline-safe ownership-correction pipeline.  Region
    // search usually exhausts itself far before a full epoch; reuse the same
    // reserved core sequentially on Fragment LNS and exact refinement.
    bool phase_ownership_pipeline = true;
    int phase_ownership_min_customers = 350;
    double phase_ownership_region_fraction = 0.46;
    double phase_ownership_fragment_min_s = 0.22;
    double phase_ownership_refine_min_s = 0.18;
    // E33: cooperative large neighborhoods need a realistic minimum slice.
    // Do not launch them with a tiny remainder merely because remaining>0.
    double phase_ownership_fragment_floor_per_customer_s = 0.00220;
    double phase_ownership_refine_floor_per_customer_s = 0.00280;
    bool phase_skip_duplicate_cascade_region = true;
    bool phase_breed_requires_strong_pair = true;
    // E5: split each main-search epoch into discovery -> immediate archive handoff ->
    // exploitation/recombination. This reduces information latency without adding
    // wall-clock budget and avoids keeping all memory-heavy roles active for the full epoch.
    bool phase_two_wave_epochs = true;
    double phase_handoff_fraction = 0.28;
    double phase_handoff_min_s = 0.65;
    int phase_handoff_max_workers = 2;
    // E6: the phase archive is already diversity-filtered. Reusing it avoids
    // rebuilding another elite population during the final second.
    bool phase_reuse_inherited_elites = true;
    double phase_tail_deadline_guard_s = 0.10;
    // E35: recombination must recompute the *actual* envelope after archive
    // construction; the original stage budget may already be mostly consumed.
    double phase_elite_recombine_min_safe_s = 0.24;
    double phase_elite_recombine_full_tasks_s = 0.52;
    double phase_elite_archive_min_entry_s = 0.30;
    double phase_elite_archive_floor_per_customer_s = 0.00150;

    // E10: do not waste tiny pre-tail fragments on a fresh heterogeneous epoch.
    // Large-instance handoff is a cascade: correct the fresh best with the
    // region/interroute specialist, publish it, then breed from that corrected
    // archive. This removes the remaining within-epoch information latency.
    double phase_min_epoch_launch_s = 1.20;
    bool phase_cascade_handoff = true;
    double phase_cascade_region_fraction = 0.62;
    bool phase_dynamic_active_cap = true;
    int phase_late_discovery_max_workers = 4;
    string phase_trace_csv = "";

    // E11 readiness-gated anytime entry.  Expensive intensification is not
    // assumed to be useful at t=0.  Compact road instances first run a tiny
    // cold-exact vs FAST-structure race.  Large instances may extend their
    // uninterrupted structure prefix only when the winning lane is still hot.
    bool phase_readiness_gate = true;
    bool phase_entry_try_savings = true;
    int phase_entry_savings_max_customers = 180;
    double phase_entry_probe_fraction = 0.0125;
    double phase_entry_probe_min_s = 0.45;
    double phase_entry_probe_max_s = 2.00;
    int phase_entry_probe_workers = 2;
    double phase_entry_hot_age_fraction = 0.18;
    double phase_entry_extension_fraction = 0.75;
    double phase_entry_extension_max_s = 0.0;
    double phase_structure_hot_age_fraction = 0.15;
    double phase_structure_extension_fraction = 0.18;
    double phase_structure_extension_max_s = 8.0;
    // Compact/tight instances benefit from frequent barriers and should stop
    // repeating heavy handoffs once a full discovery wave has gone flat.
    double phase_compact_epoch_s = 3.0;
    double phase_compact_first_epoch_s = 7.0;
    bool phase_compact_stall_to_tail = true;
    double phase_compact_stall_gain_multiplier = 0.25;
    bool phase_compact_deadline_finish = true;
    int phase_compact_finish_workers = 2;
    double phase_compact_finish_min_s = 0.60;

    // E16 state-adaptive tail audition.  A short equal-budget race among proven
    // late components identifies what is still alive in the current basin before
    // the remaining staged tail commits compute.
    bool phase_adaptive_tail_probe = true;
    double phase_tail_probe_fraction = 0.14;
    double phase_tail_probe_min_s = 0.30;
    double phase_tail_probe_max_s = 1.00;
    int phase_tail_probe_max_workers = 5;
    double phase_tail_probe_repeat_gain_multiplier = 0.70;
    double phase_tail_probe_repeat_max_s = 1.00;

    // E2/E3 structure destroy policy. Two cheap operators (multi-route blocks and
    // expensive-arc blocks) complement the historical random/related ruins.
    // The benchmark selector is isolation-only: -1 means the normal adaptive
    // policy, 0..5 forces one destroy family for controlled measurement.
    bool phase_e2_destroy_policy = true;
    int lns_benchmark_destroy_mode = -1;

    bool lns_benchmark_disable_post_repair_polish = true;
    // In benchmark mode, exact/regret repairs scan every route and position.
    // GREEDY_FAST intentionally keeps the configured caps as the speed baseline.
    bool lns_benchmark_full_scan_exact_repairs = true;
    string benchmark_tag = "";
    string repair_summary_csv = "repair_summary.csv";
    string repair_trace_csv = ""; // empty = aggregate counters only
    int repair_trace_sample_every = 1;
    long long repair_trace_max_rows = 200000;

    int insertion_route_cap = 8;
    int insertion_pos_cap = 120;

    bool use_topk_insertion = true;
    int insertion_topk_exact = 18;

    // SIMD insertion ranking.
    // This only ranks insertion positions.
    // Exact route recompute still decides the final move.
    bool use_simd_insertion_rank = true;

    // Budget multiplier for exact checks after SIMD ranking.
    // exact_budget = insertion_topk_exact * number_of_candidate_routes * multiplier
    int simd_global_topk_multiplier = 1;

    double insertion_capacity_soft_penalty = 500.0;
    double insertion_tw_soft_penalty = 0.05;

    /* ============================================================
    Local polish controls
    ============================================================ */
    bool use_oropt = true;
    bool use_2opt = true;
    bool use_relocate_polish = true;

    bool use_interroute_polish = true;
    // E10: exact O(1) arc-delta pruning for distance/single-trip interroute moves.
    bool use_interroute_arc_delta_prune = true;
    int interroute_polish_rounds = 4;
    int interroute_scan_cap = 30000;
    int max_interroute_moves = 60;
    // V21: rank route pairs by cross-route interaction before a capped scan.
    // This removes deterministic early-route starvation under scan caps.
    bool interroute_rank_pairs = true;

    /* ============================================================
    Route-pair boundary diagnostics
    ============================================================ */
    bool use_route_pair_diag = false;
    int route_pair_diag_top = 12;
    int route_pair_diag_neighbor_k = 4;

    /* ============================================================
    Boundary Pair LNS
    ============================================================ */
    bool use_boundary_pair_lns = false;
    int boundary_pair_lns_rounds = 4;
    int boundary_pair_lns_top_pairs = 8;
    int boundary_pair_lns_max_remove = 12;
    bool boundary_pair_lns_add_neighbors = true;
    bool boundary_pair_lns_verbose = false;

    /* ============================================================
    Granular Tabu Repair
    ============================================================ */
    bool use_granular_tabu = true;
    int granular_tabu_iters = 5000;
    int granular_tabu_top_pairs = 8;
    int granular_tabu_customer_radius = 1;

    int granular_tabu_tenure_min = 7;
    int granular_tabu_tenure_max = 17;

    double granular_tabu_worsen_cap = 6.0;
    bool granular_tabu_allow_worsen = true;

    int granular_tabu_candidate_cap = 80;
    bool granular_tabu_verbose = false;

    /* ============================================================
    Boundary-prioritized Euclidean education
    ============================================================ */
    bool use_boundary_prioritized_education = true;
    int boundary_prioritized_top_pairs = 8;
    bool boundary_prioritized_verbose = false;
    bool boundary_prioritized_relax_candidate_filter = false;

    /* ============================================================
    ALNS
    ============================================================ */
    int alns_rounds = 2;
    double alns_destroy_min_ratio = 0.04;
    double alns_destroy_max_ratio = 0.16;
    int stagnation_alns_trigger = 800; // legacy consecutive-rejection trigger
    double alns_kick_cooldown_s = 0.25;
    bool use_time_stagnation_alns_kick = false;
    double alns_stagnation_s = 0.75;
    int alns_kick_specialist_workers = 1;
    bool lns_macro_metropolis = false;

    // V31 optional structural string-LNS. Kept opt-in until multi-seed evidence.
    bool use_string_slack_kick = false;
    double string_slack_kick_period_s = 1.0;
    int string_slack_stagnation_trigger = 800; // legacy consecutive-rejection trigger (diagnostic only)
    double string_slack_stagnation_s = 0.75;   // V31.2: wall time since last hard-feasible best improvement
    int string_slack_max_string_length = 6;
    int string_slack_max_strings = 8;
    double string_slack_route_top_fraction = 0.35;

    /* ============================================================
    Elite pool / path relinking
    ============================================================ */
    int relink_period = 5000;       // legacy iteration cadence
    int elite_update_period = 5000; // legacy iteration cadence
    double relink_period_s = 1.00;
    double elite_update_period_s = 0.25;

    /* ============================================================
    Final refinement pipeline
    ============================================================ */
    int final_polish_rounds = 4;
    int final_refinement_rounds = 2;

    /* ============================================================
    FragmentLNS
    ============================================================ */
    bool use_fragment_lns = true;
    int fragment_lns_rounds = 80;
    int fragment_lns_remove_min = 6;
    int fragment_lns_remove_max = 10;
    int fragment_lns_source_route_cap = 3;
    int fragment_lns_related_k = 18;
    int fragment_lns_pos_cap = 120;
    bool fragment_lns_verbose = false;

    // Longest-route biased ruin.
    // Targets the currently most expensive / longest route and removes
    // a compact block plus related customers. This is meant to reduce
    // bad-run upper bounds by breaking bad route partitions.
    bool use_longest_route_ruin = true;
    double longest_route_ruin_probability = 0.65;
    int longest_route_ruin_top_routes = 3;
    int longest_route_ruin_block_radius = 3;
    int longest_route_ruin_extra_related = 8;

    // Euclidean mini-education for FragmentLNS candidates.
    // This tries to rescue repaired candidates before rejecting them.
    bool fragment_lns_euclidean_educate = true;
    int fragment_lns_educate_swapstar_rounds = 2;
    int fragment_lns_educate_two_opt_star_rounds = 2;
    int fragment_lns_educate_deep_rounds = 2;
    int fragment_lns_educate_swapstar_cap = 40000;
    int fragment_lns_educate_two_opt_star_cap = 50000;

    /* ============================================================
    Targeted Route-Region LNS
    ============================================================ */
    // Deterministic/semi-deterministic large-region repair.
    // Unlike FragmentLNS, this targets suspicious route pairs/regions.
    bool use_route_region_lns = false;

    // Number of accepted-descent attempts. Each round reranks route regions.
    int route_region_lns_rounds = 8;

    // Number of suspicious route pairs considered each round.
    int route_region_lns_seed_pairs = 16;

    // Region size: start from one suspicious pair, then add nearby routes.
    int route_region_lns_max_routes = 6;

    // Removed customer budget from the selected route region.
    int route_region_lns_remove_min = 20;
    int route_region_lns_remove_max = 60;

    // Neighbor radius around selected boundary customers inside a route.
    int route_region_lns_neighbor_radius = 2;

    bool route_region_lns_verbose = false;

    /* ============================================================
    GLS: Guided Arc Penalty Search
    ============================================================ */
    bool use_guided_arc_penalty = true;

    int gls_rounds = 6;
    int gls_moves_per_round = 10;

    // Fixed fallback lambda.
    double gls_lambda = 0.20;

    // Adaptive exponential lambda.
    bool gls_adaptive_lambda = true;
    double gls_lambda_base = 0.20;
    double gls_lambda_growth = 1.45;
    double gls_lambda_max = 1.50;

    int gls_penalty_top_k = 12;

    int gls_source_route_cap = 4;
    int gls_source_customer_cap = 20;
    int gls_target_route_cap = 4;
    int gls_pos_cap = 200;

    double gls_max_exact_worsen_per_move = 25.0;

    bool gls_adaptive_worsen_cap = true;
    double gls_worsen_growth = 1.25;
    double gls_worsen_max = 100.0;

    double gls_time_limit_s = 0.75;
    int gls_max_total_moves = 40;
    int gls_max_stagnation = 5;

    bool gls_try_swaps = true;
    bool gls_verbose = false;
    bool gls_print_moves = false;

    /* ============================================================
    Cluster warm start
    ============================================================ */
    bool use_cluster_warm_start = false;
    string clusters_csv = "clusters.csv";
} cfg;

/* ---------------- Profiling counters ---------------- */
static struct ProfileCounters {
    atomic<long long> sa_iterations{0};
    atomic<long long> sa_accepted_moves{0};
    atomic<long long> sa_attempted_moves{0};
    atomic<long long> sa_effective_proposals{0};
    atomic<long long> sa_route_draw_failures{0};
    atomic<long long> sa_drift_corrections{0};
    atomic<long long> sa_capacity_violation_trials{0};
    atomic<long long> sa_total_overload_milli{0};

    atomic<long long> alns_calls{0};
    atomic<long long> polish_calls{0};
    atomic<long long> recompute_calls{0};
    atomic<long long> pair_queries{0};

    atomic<long long> sa_time_us{0};
    atomic<long long> alns_time_us{0};
    atomic<long long> polish_time_us{0};

    // V5 deadline-accounting audit counters.
    atomic<long long> late_feasible_improvements_rejected{0};
    atomic<long long> cooperative_stop_polls{0};
    atomic<long long> fleet_elim_calls{0};
    atomic<long long> fleet_elim_successes{0};
    atomic<long long> fleet_ejection_chain_attempts{0};
    atomic<long long> fleet_ejection_chain_successes{0};
    atomic<long long> fleet_ejection_chain_candidates{0};
    atomic<long long> global_fleet_migration_checks{0};
    atomic<long long> global_fleet_migration_adoptions{0};
    atomic<long long> budget_saturation_rounds{0};

    // V20 feature-reachability / structural-search audit counters.
    atomic<long long> path_relink_calls{0};
    atomic<long long> path_relink_steps{0};
    atomic<long long> path_relink_feasible_progress{0};
    atomic<long long> path_relink_best_improvements{0};
    atomic<long long> asymmetric_2opt_candidates{0};
    atomic<long long> asymmetric_2opt_improvements{0};
    atomic<long long> two_opt_route_calls{0};
    atomic<long long> two_opt_route_time_us{0};
    atomic<long long> boundary_pair_calls{0};
    atomic<long long> granular_tabu_calls{0};
    atomic<long long> granular_tabu_candidate_evals{0};
    atomic<long long> granular_tabu_accepted_moves{0};
    atomic<long long> granular_tabu_time_us{0};

    // V21 fixed-time / inter-route audit counters.
    atomic<long long> sa_stop_local_time{0};
    atomic<long long> sa_stop_global_deadline{0};
    atomic<long long> sa_stop_proposal_cap{0};
    atomic<long long> interroute_relocate_calls{0};
    atomic<long long> interroute_swap_calls{0};
    atomic<long long> interroute_twooptstar_calls{0};
    atomic<long long> interroute_pairs_available{0};
    atomic<long long> interroute_pairs_touched{0};
    atomic<long long> interroute_candidate_scans{0};
    atomic<long long> interroute_exact_evals{0};
    atomic<long long> interroute_arc_delta_pruned{0};
    atomic<long long> interroute_arc_delta_survivors{0};
    atomic<long long> interroute_time_us{0};

    // V31 candidate: CVRP Split + structural string-LNS audit.
    atomic<long long> hgs_split_calls{0};
    atomic<long long> hgs_split_fast_segments{0};
    atomic<long long> hgs_split_exact_segments{0};
    atomic<long long> hgs_split_time_us{0};
    atomic<long long> candidate_route_affinity_nodes_scanned{0};
    atomic<long long> candidate_route_affinity_calls{0};
    atomic<long long> worker_role_structural{0};
    atomic<long long> worker_role_exploiter{0};
    atomic<long long> worker_role_explorer{0};

    atomic<long long> string_slack_kick_calls{0};
    atomic<long long> string_slack_kick_improvements{0};
    atomic<long long> string_slack_kick_time_us{0};
    atomic<long long> string_slack_kick_trigger_checks{0};
    atomic<long long> string_slack_kick_stagnation_eligible{0};
    atomic<long long> string_slack_kick_feasible_best_improvements{0};
    atomic<long long> string_slack_kick_global_best_improvements{0};
    atomic<long long> string_slack_kick_metropolis_worse_accepts{0};
    atomic<long long> alns_kick_calls{0};
    atomic<long long> alns_kick_state_improvements{0};
    atomic<long long> alns_kick_feasible_best_improvements{0};
    atomic<long long> alns_kick_global_best_improvements{0};
    atomic<long long> alns_kick_metropolis_worse_accepts{0};
    atomic<long long> alns_kick_time_us{0};
    atomic<long long> alns_kick_destroy0_calls{0};
    atomic<long long> alns_kick_destroy1_calls{0};
    atomic<long long> alns_kick_destroy2_calls{0};
} profile;

static double profile_seconds(const atomic<long long> &microseconds) {
    return static_cast<double>(microseconds.load(memory_order_relaxed)) /
        1'000'000.0;
}

struct RepairWorkStats {
    uint64_t customers_requested = 0;
    uint64_t customers_inserted = 0;
    uint64_t candidate_routes_examined = 0;
    uint64_t positions_ranked = 0;
    uint64_t exact_route_evaluations = 0;
};

static struct RepairProfileCounters {
    atomic<long long> calls{0};
    atomic<long long> successful_calls{0};
    atomic<long long> failed_calls{0};
    atomic<long long> customers_requested{0};
    atomic<long long> customers_inserted{0};
    atomic<long long> candidate_routes_examined{0};
    atomic<long long> positions_ranked{0};
    atomic<long long> exact_route_evaluations{0};
    atomic<long long> repair_time_us{0};
    atomic<long long> improving_lns_moves{0};
    atomic<long long> benchmark_iterations{0};
    atomic<long long> benchmark_noop_iterations{0};
    atomic<long long> benchmark_time_us{0};
} repair_profile;

static double repair_benchmark_seed_objective = INF_D;
static string repair_benchmark_seed_name = "";
static unsigned repair_benchmark_effective_seed = 0;
static int repair_benchmark_graph_nodes = 0;
static int repair_benchmark_graph_edges = 0;
static int repair_benchmark_customer_count = 0;
static double repair_benchmark_requested_time_s = 0.0;
static double repair_benchmark_time_overshoot_s = 0.0;

struct RepairTraceRow {
    long long call_id = 0;
    string mode;
    int destroy_mode = -1;
    int removed_count = 0;
    int inserted_count = 0;
    int failed_count = 0;
    int success = 0;
    long long repair_time_us = 0;
    long long candidate_routes_examined = 0;
    long long positions_ranked = 0;
    long long exact_route_evaluations = 0;
    double base_objective = INF_D;
    double repaired_objective = INF_D;
};

static mutex repair_trace_mutex;
static vector<RepairTraceRow> repair_trace_rows;

/* ---------------- Types ---------------- */
struct NodeC {
    int id;
    long long orig_id;
    double lon = 0, lat = 0;
    int type = 0; // 0 normal, 1 depot, 2 customer
    double service_time_s = 0;
    double garbage_amount = 0;
    double earliest = 0, latest = 1e12;
    NodeC() : id(-1), orig_id(-1) {}
};
// Position cap per insertion route.
struct EdgeC {
    int id;
    int u = 0, v = 0;
    double length_m = 0;
    double speed_kph = 30.0;
    double travel_time(double /*tod*/) const {
        // input.txt is a static directed-road snapshot. FleetRoute materializes
        // the active road-speed model into each edge, so the native optimizer
        // must not inject a second synthetic rush-hour multiplier. This keeps
        // C++ feasibility/objectives identical to the independent Python route
        // certificate and makes traffic extensions explicit data revisions.
        double speed_ms = max(0.1, speed_kph * 1000.0 / 3600.0);
        return length_m / speed_ms;
    }
    double co2() const { return length_m * cfg.co2_per_meter; }
};

struct Compressed {
    vector<NodeC> nodes;
    vector<EdgeC> edges;
    vector<vector<int>> out_edges;
    unordered_map<long long, int> orig_to_idx;

    int add_node(long long orig_id, double lon = 0, double lat = 0, int type = 0) {
        if (orig_to_idx.count(orig_id)) return orig_to_idx[orig_id];
        int idx = (int)nodes.size();
        NodeC n;
        n.id = idx;
        n.orig_id = orig_id;
        n.lon = lon;
        n.lat = lat;
        n.type = type;
        nodes.push_back(n);
        out_edges.emplace_back();
        orig_to_idx[orig_id] = idx;
        return idx;
    }

    int add_edge_directed(int u, int v, double len, double sp) {
        int maxidx = max(u, v);
        if (maxidx >= (int)nodes.size()) {
            while (maxidx >= (int)nodes.size()) add_node((long long)nodes.size(), 0, 0, 0);
        }
        int eid = (int)edges.size();
        EdgeC e;
        e.id = eid;
        e.u = u;
        e.v = v;
        e.length_m = len;
        e.speed_kph = sp;
        edges.push_back(e);
        if (u >= 0 && u < (int)out_edges.size()) out_edges[u].push_back(eid);
        return eid;
    }

    pair<int, int> add_edge_bidir(int u, int v, double len, double sp) {
        int a = add_edge_directed(u, v, len, sp);
        int b = add_edge_directed(v, u, len, sp);
        return {a, b};
    }
};

/* ---------------- LineGraph + TDijkstra ---------------- */
struct LineGraph {
    int E = 0;
    vector<vector<pair<int, double>>> adj;
    unordered_map<long long, double> turn_penalty;

    inline long long key(int a, int b) const {
        return (((long long)a) << 32) | (unsigned long long)b;
    }

    void build_from_compressed(const Compressed &G) {
        E = (int)G.edges.size();
        adj.assign(E, {});
        for (int e = 0; e < E; ++e) {
            int v = G.edges[e].v;
            if (v < 0 || v >= (int)G.out_edges.size()) continue;
            for (int e2 : G.out_edges[v]) {
                double pen = 0.0;
                auto it = turn_penalty.find(key(e, e2));
                if (it != turn_penalty.end()) pen = it->second;
                adj[e].push_back({e2, pen});
            }
        }
    }

    void set_turn_penalty(int a, int b, double p) { turn_penalty[key(a, b)] = p; }
};

struct TDijkstra {
    const Compressed *G;
    const LineGraph *LG;
    TDijkstra(const Compressed *g, const LineGraph *lg) : G(g), LG(lg) {}

    pair<double, vector<int>> shortest_from_node_to_node(int s, int t, double start_time) {
        if (s < 0 || s >= (int)G->out_edges.size()) return {INF_D, {}};
        vector<int> starts = G->out_edges[s];
        vector<int> targets;
        for (int e = 0; e < (int)G->edges.size(); ++e)
            if (G->edges[e].v == t) targets.push_back(e);
        return shortest_edge_set(starts, targets, start_time);
    }

    pair<double, vector<int>> shortest_edge_set(const vector<int> &starts, const vector<int> &targets, double start_time) {
        const double INF = INF_D;
        int E = (int)G->edges.size();
        vector<double> best(E, INF);
        vector<int> prev(E, -1);
        using P = pair<double, int>;
        priority_queue<P, vector<P>, greater<P>> pq;

        for (int e : starts) {
            if (e < 0 || e >= E) continue;
            double t = G->edges[e].travel_time(start_time);
            double arr = start_time + t;
            if (arr < best[e]) {
                best[e] = arr;
                prev[e] = -1;
                pq.push({arr, e});
            }
        }

        unordered_set<int> target_set(targets.begin(), targets.end());
        int found = -1;
        while (!pq.empty()) {
            auto [arr, e] = pq.top();
            pq.pop();
            if (arr > best[e] + 1e-9) continue;
            if (target_set.count(e)) {
                found = e;
                break;
            }
            for (auto &pr : LG->adj[e]) {
                int e2 = pr.first;
                double pen = pr.second;
                double t2 = G->edges[e2].travel_time(arr);
                double arr2 = arr + pen + t2;
                if (arr2 + 1e-9 < best[e2]) {
                    best[e2] = arr2;
                    prev[e2] = e;
                    pq.push({arr2, e2});
                }
            }
        }

        if (found == -1) return {INF, {}};
        vector<int> rev;
        int cur = found;
        while (cur != -1) {
            rev.push_back(cur);
            cur = prev[cur];
        }
        reverse(rev.begin(), rev.end());
        double cost = best[found] - start_time;
        return {cost, rev};
    }
};

static vector<int> node_alias;

static inline int canonical_node(int x) {
    if (x >= 0 && x < (int)node_alias.size() &&
        node_alias[x] >= 0 &&
        node_alias[x] < (int)node_alias.size()) {
        return node_alias[x];
    }
    return x;
}

/* ---------------- PairwiseManager ---------------- */

struct LRUCache {
    size_t cap;
    list<uint64_t> order;
    unordered_map<
        uint64_t,
        pair<pair<double, shared_ptr<vector<int>>>, list<uint64_t>::iterator>
    > map;
    mutex mtx;

    LRUCache(size_t c = 200000) : cap(c) {}

    static uint64_t key_pair(int a, int b) {
        return (((uint64_t)(uint32_t)a) << 32) | (uint32_t)b;
    }

    bool get(uint64_t k, pair<double, shared_ptr<vector<int>>> &out) {
        lock_guard<mutex> lk(mtx);

        auto it = map.find(k);
        if (it == map.end()) return false;

        order.erase(it->second.second);
        order.push_front(k);
        it->second.second = order.begin();

        out = it->second.first;
        return true;
    }

    void put(uint64_t k, const pair<double, shared_ptr<vector<int>>> &val) {
        lock_guard<mutex> lk(mtx);

        auto it = map.find(k);
        if (it != map.end()) {
            order.erase(it->second.second);
            order.push_front(k);
            it->second = {val, order.begin()};
            return;
        }

        if (map.size() >= cap) {
            uint64_t old = order.back();
            order.pop_back();
            map.erase(old);
        }

        order.push_front(k);
        map[k] = {val, order.begin()};
    }
};

struct PairMetric {
    double time_s = INF_D;
    double dist_m = INF_D;
};

struct PairwiseManager {
    Compressed *G;
    LineGraph *LG;

    // Path cache only. Used when final output needs real road geometry.
    // Do not use this for dense metric construction.
    LRUCache path_cache;

    // Scalar metric cache for optimization.
    unordered_map<uint64_t, PairMetric> metric_cache;
    mutex metric_mtx;

    // Reverse edge incidence is graph-static.  Older road-mode code rebuilt
    // this O(N+M) vector-of-vectors for every depot/customer source Dijkstra,
    // which becomes pure overhead on large regional graphs.  Build it once and
    // share it read-only across all source searches; path costs are unchanged.
    vector<vector<int>> incoming_edges;

    PairwiseManager(
        Compressed *g,
        LineGraph *lg,
        size_t cap = 200000
    ) : G(g), LG(lg), path_cache(cap) {
        incoming_edges.assign(G ? G->nodes.size() : 0, {});
        if (G) {
            for (int eid = 0; eid < (int)G->edges.size(); ++eid) {
                const int v = G->edges[eid].v;
                if (v >= 0 && v < (int)incoming_edges.size()) {
                    incoming_edges[v].push_back(eid);
                }
            }
        }
    }

    static uint64_t key_pair(int a, int b) {
        return LRUCache::key_pair(a, b);
    }

    void store_metric(int a, int b, double time_s, double dist_m) {
        uint64_t k = key_pair(a, b);

        lock_guard<mutex> lk(metric_mtx);
        metric_cache[k] = {time_s, dist_m};
    }

    bool get_metric_cached(int a, int b, PairMetric &out) {
        uint64_t k = key_pair(a, b);

        lock_guard<mutex> lk(metric_mtx);
        auto it = metric_cache.find(k);

        if (it == metric_cache.end()) return false;

        out = it->second;
        return true;
    }

    static double objective_edge_score(double elapsed_s, double dist_m) {
        if (cfg.objective_mode == "distance") return dist_m;
        if (cfg.objective_mode == "time") return elapsed_s;
        return dist_m + cfg.w_time * elapsed_s;
    }

    pair<PairMetric, vector<int>> compute_objective_path(
        int src,
        int dst
    ) {
        const int src_c = canonical_node(src);
        const int dst_c = canonical_node(dst);

        if (src_c == dst_c) return {{0.0, 0.0}, {}};
        if (src_c < 0 || dst_c < 0 ||
            src_c >= (int)G->out_edges.size() ||
            dst_c >= (int)G->nodes.size()) {
            return {{INF_D, INF_D}, {}};
        }

        const int E = (int)G->edges.size();
        vector<double> best_score(E, INF_D);
        vector<double> best_arr(E, INF_D);
        vector<double> best_dist(E, INF_D);
        vector<int> prev(E, -1);

        using Q = tuple<double, double, double, int>;
        priority_queue<Q, vector<Q>, greater<Q>> pq;

        for (int eid : G->out_edges[src_c]) {
            if (eid < 0 || eid >= E) continue;
            const EdgeC &e = G->edges[eid];
            const double travel = e.travel_time(cfg.route_start_time_s);
            const double arr = cfg.route_start_time_s + travel;
            const double dist = e.length_m;
            const double score = objective_edge_score(travel, dist);

            if (score + 1e-9 < best_score[eid] ||
                (fabs(score - best_score[eid]) <= 1e-9 &&
                (arr + 1e-9 < best_arr[eid] ||
                (fabs(arr - best_arr[eid]) <= 1e-9 &&
                dist + 1e-9 < best_dist[eid])))) {
                best_score[eid] = score;
                best_arr[eid] = arr;
                best_dist[eid] = dist;
                prev[eid] = -1;
                pq.push({score, arr, dist, eid});
            }
        }

        int found = -1;
        while (!pq.empty()) {
            auto [score, arr, dist, eid] = pq.top();
            pq.pop();

            if (score > best_score[eid] + 1e-9) continue;
            if (fabs(score - best_score[eid]) <= 1e-9 &&
                arr > best_arr[eid] + 1e-9) continue;
            if (fabs(score - best_score[eid]) <= 1e-9 &&
                fabs(arr - best_arr[eid]) <= 1e-9 &&
                dist > best_dist[eid] + 1e-9) continue;

            if (G->edges[eid].v == dst_c) {
                found = eid;
                break;
            }

            for (const auto &pr : LG->adj[eid]) {
                const int e2 = pr.first;
                const double turn_penalty_s = pr.second;
                if (e2 < 0 || e2 >= E) continue;

                const EdgeC &edge2 = G->edges[e2];
                const double travel2 = edge2.travel_time(arr);
                const double elapsed2 = turn_penalty_s + travel2;
                const double arr2 = arr + elapsed2;
                const double dist2 = dist + edge2.length_m;
                const double score2 = score +
                    objective_edge_score(elapsed2, edge2.length_m);

                if (score2 + 1e-9 < best_score[e2] ||
                    (fabs(score2 - best_score[e2]) <= 1e-9 &&
                    (arr2 + 1e-9 < best_arr[e2] ||
                    (fabs(arr2 - best_arr[e2]) <= 1e-9 &&
                    dist2 + 1e-9 < best_dist[e2])))) {
                    best_score[e2] = score2;
                    best_arr[e2] = arr2;
                    best_dist[e2] = dist2;
                    prev[e2] = eid;
                    pq.push({score2, arr2, dist2, e2});
                }
            }
        }

        if (found < 0) return {{INF_D, INF_D}, {}};

        vector<int> edge_path;
        for (int cur = found; cur >= 0; cur = prev[cur]) {
            edge_path.push_back(cur);
        }
        reverse(edge_path.begin(), edge_path.end());

        return {{
            best_arr[found] - cfg.route_start_time_s,
            best_dist[found]
        }, std::move(edge_path)};
    }

    // One-source line-graph Dijkstra.
    // The selected physical path is consistent with the active objective:
    // distance minimizes meters, time minimizes travel seconds, and hybrid
    // minimizes distance_m + 0.25 * travel_seconds. The stored time
    // and distance always belong to that same chosen path.
    void precompute_from_source(int src, const vector<int> &targets) {
        int src_c = canonical_node(src);

        if (src_c < 0 || src_c >= (int)G->out_edges.size()) {
            return;
        }

        const int E = (int)G->edges.size();
        const int N = (int)G->nodes.size();

        vector<double> best_score(E, INF_D);
        vector<double> best_arr(E, INF_D);
        vector<double> best_dist(E, INF_D);

        using Q = tuple<double, double, double, int>;
        priority_queue<Q, vector<Q>, greater<Q>> pq;

        for (int eid : G->out_edges[src_c]) {
            if (eid < 0 || eid >= E) continue;

            const EdgeC &e = G->edges[eid];
            double travel = e.travel_time(cfg.route_start_time_s);
            double arr = cfg.route_start_time_s + travel;
            double dist = e.length_m;
            double score = objective_edge_score(travel, dist);

            if (score + 1e-9 < best_score[eid] ||
                (fabs(score - best_score[eid]) <= 1e-9 &&
                (arr + 1e-9 < best_arr[eid] ||
                (fabs(arr - best_arr[eid]) <= 1e-9 &&
                dist + 1e-9 < best_dist[eid])))) {
                best_score[eid] = score;
                best_arr[eid] = arr;
                best_dist[eid] = dist;
                pq.push({score, arr, dist, eid});
            }
        }

        while (!pq.empty()) {
            auto [score, arr, dist, eid] = pq.top();
            pq.pop();

            if (score > best_score[eid] + 1e-9) continue;
            if (fabs(score - best_score[eid]) <= 1e-9 &&
                arr > best_arr[eid] + 1e-9) continue;
            if (fabs(score - best_score[eid]) <= 1e-9 &&
                fabs(arr - best_arr[eid]) <= 1e-9 &&
                dist > best_dist[eid] + 1e-9) continue;

            for (const auto &pr : LG->adj[eid]) {
                int e2 = pr.first;
                double turn_penalty_s = pr.second;
                if (e2 < 0 || e2 >= E) continue;

                const EdgeC &edge2 = G->edges[e2];
                double travel2 = edge2.travel_time(arr);
                double elapsed2 = turn_penalty_s + travel2;
                double arr2 = arr + elapsed2;
                double dist2 = dist + edge2.length_m;
                double score2 = score + objective_edge_score(elapsed2, edge2.length_m);

                if (score2 + 1e-9 < best_score[e2] ||
                    (fabs(score2 - best_score[e2]) <= 1e-9 &&
                    (arr2 + 1e-9 < best_arr[e2] ||
                    (fabs(arr2 - best_arr[e2]) <= 1e-9 &&
                    dist2 + 1e-9 < best_dist[e2])))) {
                    best_score[e2] = score2;
                    best_arr[e2] = arr2;
                    best_dist[e2] = dist2;
                    pq.push({score2, arr2, dist2, e2});
                }
            }
        }

        for (int t : targets) {
            int t_c = canonical_node(t);

            if (src_c == t_c) {
                store_metric(src, t, 0.0, 0.0);
                continue;
            }
            if (t_c < 0 || t_c >= N) continue;

            double target_score = INF_D;
            double target_arr = INF_D;
            double target_dist = INF_D;

            for (int eid : incoming_edges[t_c]) {
                double score = best_score[eid];
                double arr = best_arr[eid];
                double dist = best_dist[eid];

                if (score + 1e-9 < target_score ||
                    (fabs(score - target_score) <= 1e-9 &&
                    (arr + 1e-9 < target_arr ||
                    (fabs(arr - target_arr) <= 1e-9 &&
                    dist + 1e-9 < target_dist)))) {
                    target_score = score;
                    target_arr = arr;
                    target_dist = dist;
                }
            }

            if (target_score >= INF_D / 2 ||
                target_arr >= INF_D / 2 ||
                target_dist >= INF_D / 2) {
                continue;
            }

            store_metric(
                src,
                t,
                target_arr - cfg.route_start_time_s,
                target_dist
            );
        }
    }

    PairMetric get_pair_metric(int a, int b) {
        int a_c = canonical_node(a);
        int b_c = canonical_node(b);

        if (a_c == b_c) return {0.0, 0.0};

        PairMetric cached;
        if (get_metric_cached(a, b, cached)) return cached;

        precompute_from_source(a, vector<int>{b});
        if (get_metric_cached(a, b, cached)) return cached;

        return {INF_D, INF_D};
    }

    double get_pair_time_s(int a, int b) {
        return get_pair_metric(a, b).time_s;
    }

    double get_pair_distance_m(int a, int b) {
        return get_pair_metric(a, b).dist_m;
    }

    // Path retrieval only. This is intentionally separate from metric cache.
    pair<double, vector<int>> get_pair(int a, int b) {
        int a_c = canonical_node(a);
        int b_c = canonical_node(b);

        if (a_c == b_c) {
            return {0.0, vector<int>{a, b}};
        }

        uint64_t k = key_pair(a, b);

        pair<double, shared_ptr<vector<int>>> val;
        if (path_cache.get(k, val)) {
            return {val.first, *(val.second)};
        }

        auto result = compute_objective_path(a_c, b_c);
        const PairMetric metric = result.first;
        const vector<int> &edge_path = result.second;

        auto path_ptr = make_shared<vector<int>>();
        path_ptr->reserve(edge_path.size() + 1);

        for (int eid : edge_path) {
            path_ptr->push_back(G->edges[eid].u);
        }
        if (!edge_path.empty()) {
            path_ptr->push_back(G->edges[edge_path.back()].v);
        }

        path_cache.put(k, {metric.time_s, path_ptr});
        if (metric.time_s < INF_D / 2 && metric.dist_m < INF_D / 2) {
            store_metric(a, b, metric.time_s, metric.dist_m);
        }

        return {metric.time_s, *path_ptr};
    }
};

/* ---------------- Dense compact pairwise matrix ---------------- */

struct DensePairMatrix {
    bool ready = false;

    // compact nodes: depot + all customers
    vector<int> compact_to_node;
    vector<int> node_to_compact;

    vector<vector<double>> time_s;
    vector<vector<double>> dist_m;

    // Flat row-major storage for hot loops.
    // index = compact_from * C + compact_to
    int C = 0;
    vector<double> time_s_flat;
    vector<double> dist_m_flat;

    atomic<long long> fast_time_hits{0};
    atomic<long long> fast_dist_hits{0};
    atomic<long long> fallback_time_calls{0};
    atomic<long long> fallback_dist_calls{0};

    void clear() {
        ready = false;
        compact_to_node.clear();
        node_to_compact.clear();
        time_s.clear();
        dist_m.clear();

        C = 0;
        time_s_flat.clear();
        dist_m_flat.clear();
        fast_time_hits.store(0);
        fast_dist_hits.store(0);
        fallback_time_calls.store(0);
        fallback_dist_calls.store(0);
    }
};

static DensePairMatrix dense_pairs;

static pair<double, double> direct_arc_time_dist(
    const Compressed &CG,
    int a,
    int b
) {
    a = canonical_node(a);
    b = canonical_node(b);

    if (a == b) return {0.0, 0.0};

    if (a < 0 || a >= (int)CG.out_edges.size()) {
        return {INF_D, INF_D};
    }

    // Choose the physical arc coherently for the active objective.
    // Old behavior minimized distance only, which silently made time/hybrid
    // direct-mode runs use the wrong arc when parallel arcs existed.
    double best_score = INF_D;
    double best_d = INF_D;
    double best_t = INF_D;

    for (int eid : CG.out_edges[a]) {
        const EdgeC &e = CG.edges[eid];
        if (e.v != b) continue;

        double d = e.length_m;
        double t = e.travel_time(cfg.route_start_time_s);

        double score = d;
        if (cfg.objective_mode == "time") {
            score = t;
        }
        else if (cfg.objective_mode == "hybrid") {
            score = d + cfg.w_time * t;
        }

        if (score + 1e-12 < best_score) {
            best_score = score;
            best_d = d;
            best_t = t;
        }
    }

    return {best_t, best_d};
}

static inline bool metric_is_road() {
    return cfg.metric_mode == "road";
}

static inline bool metric_is_direct() {
    return cfg.metric_mode == "direct";
}

static inline bool metric_is_euclidean() {
    return cfg.metric_mode == "euclidean";
}

static inline bool metric_is_symmetric() {
    return cfg.metric_mode == "euclidean";
}

static double euclidean_distance_m(
    const Compressed &CG,
    int a,
    int b
) {
    a = canonical_node(a);
    b = canonical_node(b);

    if (a == b) return 0.0;

    const NodeC &A = CG.nodes[a];
    const NodeC &B = CG.nodes[b];

    double dx = A.lon - B.lon;
    double dy = A.lat - B.lat;

    double d = sqrt(dx * dx + dy * dy);

    // Optional Homberger compatibility mode; unused by this Homberger runner.
    // Keep this mutually exclusive with nearest-integer CVRPLIB EUC_2D.
    if (metric_is_euclidean() && cfg.euclidean_truncate_1_decimal) {
        d = floor(d * 10.0 + 1e-12) / 10.0;
    }
    else if (metric_is_euclidean() && cfg.euclidean_round_distance) {
        d = floor(d + 0.5);
    }

    return d;
}

static pair<double, double> euclidean_time_dist(
    const Compressed &CG,
    int a,
    int b
) {
    if (a == b) return {0.0, 0.0};

    double d = euclidean_distance_m(CG, a, b);

    if (cfg.euclidean_time_equals_distance) {
        return {d, d};
    }

    double speed_ms =
        max(0.1, cfg.euclidean_speed_kph * 1000.0 / 3600.0);

    double t = d / speed_ms;

    return {t, d};
}

static inline bool euclidean_cuts_enabled() {
    return metric_is_euclidean() && cfg.euclidean_branch_cuts;
}

static double orient2d(
    double ax, double ay,
    double bx, double by,
    double cx, double cy
) {
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
}

static bool bbox_overlap_1d(double a, double b, double c, double d) {
    if (a > b) swap(a, b);
    if (c > d) swap(c, d);
    return max(a, c) <= min(b, d) + 1e-12;
}

static bool segments_cross_strict(
    const NodeC &A,
    const NodeC &B,
    const NodeC &C,
    const NodeC &D
) {
    // Shared endpoints are not crossings.
    if (A.id == C.id || A.id == D.id || B.id == C.id || B.id == D.id) {
        return false;
    }

    if (!bbox_overlap_1d(A.lon, B.lon, C.lon, D.lon)) return false;
    if (!bbox_overlap_1d(A.lat, B.lat, C.lat, D.lat)) return false;

    double o1 = orient2d(A.lon, A.lat, B.lon, B.lat, C.lon, C.lat);
    double o2 = orient2d(A.lon, A.lat, B.lon, B.lat, D.lon, D.lat);
    double o3 = orient2d(C.lon, C.lat, D.lon, D.lat, A.lon, A.lat);
    double o4 = orient2d(C.lon, C.lat, D.lon, D.lat, B.lon, B.lat);

    return (o1 * o2 < -1e-12) && (o3 * o4 < -1e-12);
}

static bool load_coords_csv(
    Compressed &CG,
    const string &path
) {
    if (path.empty()) return true;

    ifstream in(path);
    if (!in.good()) {
        cerr << "[coords] failed to open " << path << "\n";
        return false;
    }

    string line;
    int loaded = 0;
    int skipped = 0;
    bool first = true;

    while (getline(in, line)) {
        if (line.empty()) continue;

        for (char &c : line) {
            if (c == ';' || c == '\t') c = ',';
        }

        string lower = line;
        transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        // Optional header: node,x,y OR node,lon,lat
        if (first) {
            first = false;
            if (lower.find("node") != string::npos &&
                (lower.find("x") != string::npos ||
                lower.find("lon") != string::npos)) {
                continue;
            }
        }

        stringstream ss(line);
        string a, b, c;

        if (!getline(ss, a, ',')) {
            skipped++;
            continue;
        }
        if (!getline(ss, b, ',')) {
            skipped++;
            continue;
        }
        if (!getline(ss, c, ',')) {
            skipped++;
            continue;
        }

        try {
            long long orig = stoll(a);
            double x = stod(b);
            double y = stod(c);

            auto it = CG.orig_to_idx.find(orig);
            if (it == CG.orig_to_idx.end()) {
                skipped++;
                continue;
            }

            int idx = it->second;
            CG.nodes[idx].lon = x;
            CG.nodes[idx].lat = y;
            loaded++;
        } catch (...) {
            skipped++;
        }
    }

    cerr << "[coords] loaded=" << loaded
        << " skipped=" << skipped
        << " file=" << path << "\n";

    return loaded > 0;
}

static bool validate_euclidean_coordinates(
    const Compressed &CG,
    const vector<int> &collections,
    int depot
) {
    if (!metric_is_euclidean()) return true;

    vector<int> must_have;
    must_have.push_back(depot);
    for (int c : collections) must_have.push_back(c);

    bool all_zero = true;

    for (int nid : must_have) {
        if (nid < 0 || nid >= (int)CG.nodes.size()) {
            cerr << "[euclidean] invalid node id in coordinate check: "
                << nid << "\n";
            return false;
        }

        int physical = canonical_node(nid);
        if (physical < 0 || physical >= (int)CG.nodes.size()) {
            cerr << "[euclidean] invalid physical node id in coordinate check: "
                << physical << "\n";
            return false;
        }

        const NodeC &n = CG.nodes[physical];

        if (fabs(n.lon) > 1e-12 || fabs(n.lat) > 1e-12) {
            all_zero = false;
        }
    }

    if (all_zero) {
        cerr << "[euclidean] all depot/customer coordinates are zero.\n"
            << "[euclidean] Provide --coords_csv node,x,y or generate input with coordinates.\n";
        return !cfg.require_coords_for_euclidean;
    }

    return true;
}

static void build_dense_pair_matrix(
    const Compressed &CG,
    PairwiseManager &pm,
    int depot
) {
    dense_pairs.clear();

    int N = (int)CG.nodes.size();
    dense_pairs.node_to_compact.assign(N, -1);

    dense_pairs.compact_to_node.push_back(depot);

    for (const auto &n : CG.nodes) {
        if (n.type == 2) {
            dense_pairs.compact_to_node.push_back(n.id);
        }
    }

    int C = (int)dense_pairs.compact_to_node.size();
    dense_pairs.C = C;

    for (int i = 0; i < C; ++i) {
        int node = dense_pairs.compact_to_node[i];
        if (node >= 0 && node < N) {
            dense_pairs.node_to_compact[node] = i;
        }
    }

    dense_pairs.time_s.assign(C, vector<double>(C, INF_D));
    dense_pairs.dist_m.assign(C, vector<double>(C, INF_D));

    dense_pairs.time_s_flat.assign((size_t)C * (size_t)C, INF_D);
    dense_pairs.dist_m_flat.assign((size_t)C * (size_t)C, INF_D);

    // V40 direct-mode fast path: the benchmark already supplies explicit arcs.
    // The old implementation called direct_arc_time_dist(a,b) for every pair,
    // which linearly scanned a's outgoing edges each time (O(C^3) on complete
    // direct benchmarks), after an unnecessary all-source shortest-path pass.
    // Fill the compact matrix by scanning the edge list exactly once.
    if (metric_is_direct()) {
        vector<double> best_score((size_t)C * (size_t)C, INF_D);
        for (int i = 0; i < C; ++i) {
            dense_pairs.time_s[i][i] = 0.0;
            dense_pairs.dist_m[i][i] = 0.0;
            dense_pairs.time_s_flat[(size_t)i * C + i] = 0.0;
            dense_pairs.dist_m_flat[(size_t)i * C + i] = 0.0;
            best_score[(size_t)i * C + i] = 0.0;
        }

        for (const EdgeC &e : CG.edges) {
            int a = canonical_node(e.u);
            int b = canonical_node(e.v);
            if (a < 0 || b < 0 ||
                a >= (int)dense_pairs.node_to_compact.size() ||
                b >= (int)dense_pairs.node_to_compact.size()) continue;
            int ca = dense_pairs.node_to_compact[a];
            int cb = dense_pairs.node_to_compact[b];
            if (ca < 0 || cb < 0 || ca == cb) continue;

            const double d = e.length_m;
            const double t = e.travel_time(cfg.route_start_time_s);
            double score = d;
            if (cfg.objective_mode == "time") score = t;
            else if (cfg.objective_mode == "hybrid")
                score = d + cfg.w_time * t;

            const size_t idx = (size_t)ca * C + cb;
            if (score + 1e-12 < best_score[idx]) {
                best_score[idx] = score;
                dense_pairs.time_s[ca][cb] = t;
                dense_pairs.dist_m[ca][cb] = d;
                dense_pairs.time_s_flat[idx] = t;
                dense_pairs.dist_m_flat[idx] = d;
            }
        }

        dense_pairs.ready = true;
        cerr << "[DensePairMatrix] ready=1 metric_mode=direct compact_nodes="
            << C << " customers=" << max(0, C - 1)
            << " construction=edge_scan_O(M)\n";
        return;
    }

    if (metric_is_road()) {
        const auto dense_prep_started = Clock::now();
        const int progress_step = max(1, C / 10);
        safe_log_line(
            "[BackendPrep] event=dense_pair_start sources_total=", C,
            " graph_nodes=", CG.nodes.size(),
            " graph_edges=", CG.edges.size()
        );
        for (int i = 0; i < C; ++i) {
            int a = dense_pairs.compact_to_node[i];
            pm.precompute_from_source(a, dense_pairs.compact_to_node);
            if (i == 0 || i + 1 == C || (i + 1) % progress_step == 0) {
                safe_log_line(
                    "[BackendPrep] event=dense_pair_progress sources_done=", i + 1,
                    " sources_total=", C,
                    " elapsed_s=", chrono::duration<double>(Clock::now() - dense_prep_started).count()
                );
            }
        }
        safe_log_line(
            "[BackendPrep] event=dense_pair_complete sources_total=", C,
            " elapsed_s=", chrono::duration<double>(Clock::now() - dense_prep_started).count()
        );
    }

    for (int i = 0; i < C; ++i) {
        int a = dense_pairs.compact_to_node[i];

        for (int j = 0; j < C; ++j) {
            int b = dense_pairs.compact_to_node[j];

            if (a == b) {
                dense_pairs.time_s[i][j] = 0.0;
                dense_pairs.dist_m[i][j] = 0.0;

                dense_pairs.time_s_flat[(size_t)i * C + j] = 0.0;
                dense_pairs.dist_m_flat[(size_t)i * C + j] = 0.0;
                continue;
            }

            double t = INF_D;
            double d = INF_D;

            if (metric_is_euclidean()) {
                auto td = euclidean_time_dist(CG, a, b);
                t = td.first;
                d = td.second;
            }
            else if (metric_is_direct()) {
                auto td = direct_arc_time_dist(CG, a, b);
                t = td.first;
                d = td.second;
            }
            else {
                t = pm.get_pair_time_s(a, b);
                d = pm.get_pair_distance_m(a, b);
            }

            if (!isfinite(t)) t = INF_D;
            if (!isfinite(d)) d = INF_D;

            dense_pairs.time_s[i][j] = t;
            dense_pairs.dist_m[i][j] = d;

            dense_pairs.time_s_flat[(size_t)i * C + j] = t;
            dense_pairs.dist_m_flat[(size_t)i * C + j] = d;
        }
    }

    dense_pairs.ready = true;

    cerr << "[DensePairMatrix] ready=1"
        << " metric_mode=" << cfg.metric_mode
        << " compact_nodes=" << C
        << " customers=" << max(0, C - 1)
        << "\n";
}

static bool validate_dense_pair_matrix_reachable() {
    if (!dense_pairs.ready) return false;

    int bad = 0;
    const int max_print = 20;

    for (int i = 0; i < (int)dense_pairs.compact_to_node.size(); ++i) {
        for (int j = 0; j < (int)dense_pairs.compact_to_node.size(); ++j) {
            if (i == j) continue;

            double t = dense_pairs.time_s[i][j];
            double d = dense_pairs.dist_m[i][j];

            if (!isfinite(t) || !isfinite(d) ||
                t >= INF_D / 2 ||
                d >= INF_D / 2) {
                if (bad < max_print) {
                    cerr << "[reachability] unreachable compact pair "
                        << dense_pairs.compact_to_node[i]
                        << " -> "
                        << dense_pairs.compact_to_node[j]
                        << " time=" << t
                        << " dist=" << d
                        << "\n";
                }
                bad++;
            }
        }
    }

    if (bad > 0) {
        cerr << "[reachability] invalid required pair count=" << bad << "\n";
        return false;
    }

    return true;
}

static inline double fast_pair_time(
    int a,
    int b,
    PairwiseManager *pm
) {
    if (a == b) return 0.0;

    if (cfg.use_dense_pair_matrix &&
        dense_pairs.ready &&
        a >= 0 &&
        b >= 0 &&
        a < (int)dense_pairs.node_to_compact.size() &&
        b < (int)dense_pairs.node_to_compact.size()) {

        int ca = dense_pairs.node_to_compact[a];
        int cb = dense_pairs.node_to_compact[b];

        if (ca >= 0 && cb >= 0) {
        #if VRP_PROFILE_DENSE_HITS
            dense_pairs.fast_time_hits.fetch_add(1, memory_order_relaxed);
        #endif

            if (!dense_pairs.time_s_flat.empty()) {
                return dense_pairs.time_s_flat[(size_t)ca * dense_pairs.C + cb];
            }

            return dense_pairs.time_s[ca][cb];
        }
    }

    dense_pairs.fallback_time_calls++;
    profile.pair_queries.fetch_add(1, memory_order_relaxed);

    return pm->get_pair_time_s(a, b);
}

static inline double fast_pair_dist(
    int a,
    int b,
    PairwiseManager *pm
) {
    if (a == b) return 0.0;

    if (cfg.use_dense_pair_matrix &&
        dense_pairs.ready &&
        a >= 0 &&
        b >= 0 &&
        a < (int)dense_pairs.node_to_compact.size() &&
        b < (int)dense_pairs.node_to_compact.size()) {

        int ca = dense_pairs.node_to_compact[a];
        int cb = dense_pairs.node_to_compact[b];

        if (ca >= 0 && cb >= 0) {
        #if VRP_PROFILE_DENSE_HITS
            dense_pairs.fast_dist_hits.fetch_add(1, memory_order_relaxed);
        #endif

            if (!dense_pairs.dist_m_flat.empty()) {
                return dense_pairs.dist_m_flat[(size_t)ca * dense_pairs.C + cb];
            }

            return dense_pairs.dist_m[ca][cb];
        }
    }

    dense_pairs.fallback_dist_calls++;
    profile.pair_queries.fetch_add(1, memory_order_relaxed);

    return pm->get_pair_distance_m(a, b);
}

static inline double fast_pair_search_cost(
    int a,
    int b,
    PairwiseManager *pm
) {
    if (cfg.objective_mode == "distance") {
        return fast_pair_dist(a, b, pm);
    }

    if (cfg.objective_mode == "time") {
        return fast_pair_time(a, b, pm);
    }

    double t = fast_pair_time(a, b, pm);
    double d = fast_pair_dist(a, b, pm);

    if (!isfinite(t)) t = 1e12;
    if (!isfinite(d)) d = 1e12;

    return d + cfg.w_time * t;
}

/* ---------------- AVX2 insertion delta kernel ---------------- */

// Computes insertion deltas:
//
// delta = D[prev][x] + D[x][next] - D[prev][next]
//
// This is only for fast ranking. Exact route recompute should still decide
// whether an insertion is accepted.

static inline bool cpu_has_avx2_runtime() {
#if defined(__GNUC__) && (defined(__x86_64__) || defined(__i386__))
    static const bool ok = []() {
        __builtin_cpu_init();
        return __builtin_cpu_supports("avx2");
    }();
    return ok;
#else
    return false;
#endif
}

static inline void insertion_deltas_scalar_dist(
    const double *D,
    int C,
    int x_c,
    const int *prev_c,
    const int *next_c,
    int n,
    double *out
) {
    const size_t x_base = (size_t)x_c * (size_t)C;

    for (int k = 0; k < n; ++k) {
        const int p = prev_c[k];
        const int q = next_c[k];

        out[k] =
            D[(size_t)p * (size_t)C + x_c] +
            D[x_base + q] -
            D[(size_t)p * (size_t)C + q];
    }
}

#if defined(__GNUC__) && (defined(__x86_64__) || defined(__i386__))
__attribute__((target("avx2")))
static void insertion_deltas_avx2_dist(
    const double *D,
    int C,
    int x_c,
    const int *prev_c,
    const int *next_c,
    int n,
    double *out
) {
    int k = 0;

    const __m128i vC = _mm_set1_epi32(C);
    const __m128i vx = _mm_set1_epi32(x_c);
    const __m128i vxrow = _mm_set1_epi32(x_c * C);

    for (; k + 4 <= n; k += 4) {
        __m128i vp = _mm_loadu_si128((const __m128i *)(prev_c + k));
        __m128i vq = _mm_loadu_si128((const __m128i *)(next_c + k));

        __m128i vpC = _mm_mullo_epi32(vp, vC);

        __m128i idx_px = _mm_add_epi32(vpC, vx);      // prev*C + x
        __m128i idx_xq = _mm_add_epi32(vxrow, vq);    // x*C + next
        __m128i idx_pq = _mm_add_epi32(vpC, vq);      // prev*C + next

        __m256d d_px = _mm256_i32gather_pd(D, idx_px, 8);
        __m256d d_xq = _mm256_i32gather_pd(D, idx_xq, 8);
        __m256d d_pq = _mm256_i32gather_pd(D, idx_pq, 8);

        __m256d delta = _mm256_sub_pd(
            _mm256_add_pd(d_px, d_xq),
            d_pq
        );

        _mm256_storeu_pd(out + k, delta);
    }

    for (; k < n; ++k) {
        const int p = prev_c[k];
        const int q = next_c[k];

        out[k] =
            D[(size_t)p * (size_t)C + x_c] +
            D[(size_t)x_c * (size_t)C + q] -
            D[(size_t)p * (size_t)C + q];
    }
}
#endif

static inline void insertion_deltas_fast_dist(
    const double *D,
    int C,
    int x_c,
    const int *prev_c,
    const int *next_c,
    int n,
    double *out
) {
#if defined(__GNUC__) && (defined(__x86_64__) || defined(__i386__))
    if (n >= 8 && cpu_has_avx2_runtime()) {
        insertion_deltas_avx2_dist(
            D,
            C,
            x_c,
            prev_c,
            next_c,
            n,
            out
        );
        return;
    }
#endif

    insertion_deltas_scalar_dist(
        D,
        C,
        x_c,
        prev_c,
        next_c,
        n,
        out
    );
}

/* ---------------- Route metrics & state ---------------- */
struct RouteMetrics {
    double travel_seconds = 0.0;
    double distance_m = 0.0;
    double service = 0.0;
    double waiting = 0.0;
    double lateness = 0.0;
    double time_warp = 0.0;
    double co2_g = 0.0;
    double capacity_penalty = 0.0;
    double weighted_cost = 0.0;
    double route_penalty = 0.0;

    int trip_count = 0;
    double max_trip_load = 0.0;
    double trip_excess_penalty = 0.0;
};

/* ---------------- Route metrics cache ---------------- */

struct RouteMetricCache {
    unordered_map<uint64_t, RouteMetrics> mp;
    deque<uint64_t> order;
    mutex mtx;

    size_t cap = 300000;

    long long hits = 0;
    long long misses = 0;
    long long puts = 0;
    long long signature_clears = 0;

    uint64_t active_signature = 0;

    uint64_t splitmix64(uint64_t x) const {
        x += 0x9e3779b97f4a7c15ULL;
        x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
        x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
        return x ^ (x >> 31);
    }

    uint64_t hash_route(const vector<int> &route) const {
        uint64_t h = 1469598103934665603ULL;

        for (int x : route) {
            uint64_t z = splitmix64((uint64_t)(uint32_t)x + 0x9e3779b97f4a7c15ULL);
            h ^= z;
            h *= 1099511628211ULL;
        }

        h ^= splitmix64(route.size());
        return h;
    }

    uint64_t current_signature() const {
        uint64_t h = 1469598103934665603ULL;

        auto mix_u64 = [&](uint64_t x) {
            h ^= splitmix64(x);
            h *= 1099511628211ULL;
        };

        auto mix_double = [&](double x) {
            uint64_t u = 0;
            memcpy(&u, &x, sizeof(double));
            mix_u64(u);
        };

        auto mix_string = [&](const string &s) {
            for (unsigned char c : s) mix_u64((uint64_t)c);
        };

        mix_string(cfg.objective_mode);
        mix_string(cfg.metric_mode);

        mix_double(cfg.w_wait);
        mix_double(cfg.w_late);
        mix_double(cfg.w_capacity);
        mix_double(cfg.w_trip_excess);
        mix_double(cfg.tw_time_warp_penalty);
        mix_double(cfg.route_start_time_s);

        mix_u64(cfg.use_time_window ? 1 : 0);
        mix_u64(cfg.tw_use_time_warp ? 1 : 0);
        mix_u64(cfg.tw_penalize_waiting_in_distance ? 1 : 0);
        mix_u64(cfg.allow_multi_trip ? 1 : 0);
        mix_u64((uint64_t)cfg.max_trips_per_truck);

        return h;
    }

    void clear_unlocked() {
        mp.clear();
        order.clear();
        hits = 0;
        misses = 0;
        puts = 0;
    }

    void ensure_signature_current_unlocked() {
        uint64_t sig = current_signature();

        if (sig == active_signature) return;

        clear_unlocked();
        active_signature = sig;
        signature_clears++;
    }

    bool get(const vector<int> &route, RouteMetrics &out) {
        uint64_t h = hash_route(route);

        lock_guard<mutex> lk(mtx);
        ensure_signature_current_unlocked();

        auto it = mp.find(h);
        if (it == mp.end()) {
            misses++;
            return false;
        }

        hits++;
        out = it->second;
        return true;
    }

    void put(const vector<int> &route, const RouteMetrics &m) {
        uint64_t h = hash_route(route);

        lock_guard<mutex> lk(mtx);
        ensure_signature_current_unlocked();

        if (mp.find(h) == mp.end()) {
            order.push_back(h);

            if (order.size() > cap) {
                uint64_t old = order.front();
                order.pop_front();
                mp.erase(old);
            }
        }

        mp[h] = m;
        puts++;
    }

    void clear_all() {
        lock_guard<mutex> lk(mtx);
        clear_unlocked();
        active_signature = current_signature();
        signature_clears++;
    }
};

static RouteMetricCache route_metric_cache;

struct SolutionState {
    vector<vector<int>> routes;
    vector<double> route_load;
    vector<double> route_max_trip_load;
    vector<RouteMetrics> route_metrics;
    double objective = 0.0;
    vector<int> served_count;

    SolutionState() {}

    SolutionState(int R, int n_nodes) {
        routes.assign(R, {});
        route_load.assign(R, 0.0);
        route_max_trip_load.assign(R, 0.0);
        route_metrics.assign(R, {});
        objective = INF_D;
        served_count.assign(n_nodes, 0);
    }
};

/* ---------------- Global state for interruption handling ---------------- */
static volatile sig_atomic_t interrupted = 0;

static std::mutex global_best_mutex;
static SolutionState global_best_state;

/* ---------------- Anytime stop governor ---------------- */
static Clock::time_point solver_start_time;
static Clock::time_point solver_last_meaningful_improve_time;
static std::mutex solver_governor_mutex;
static bool solver_governor_started = false;
static double solver_last_meaningful_objective = INF_D;
static std::atomic<bool> solver_stop_requested{false};
// E1: in the phase-specialized engine, meaningful stagnation requests a
// transition to recombination/final intensification instead of killing the
// whole process before the reserved tail can execute.
static std::atomic<bool> solver_phase_transition_requested{false};
static string solver_stop_reason = "";

// V34: nested operators inside one SA worker must obey the worker's *local*
// stage budget as well as the global solver deadline. The old code stopped the
// SA hot loop at time_limit, then could spend several additional seconds in
// final_refinement_pass(), making a nominal 2 s worker last 4-7 s.
static thread_local bool tls_local_deadline_enabled = false;
static thread_local Clock::time_point tls_local_deadline;

struct ScopedWorkerDeadline {
    bool old_enabled = false;
    Clock::time_point old_deadline{};
    explicit ScopedWorkerDeadline(double seconds) {
        old_enabled = tls_local_deadline_enabled;
        old_deadline = tls_local_deadline;
        if (seconds > 0.0) {
            tls_local_deadline_enabled = true;
            tls_local_deadline = Clock::now() + chrono::duration_cast<Clock::duration>(chrono::duration<double>(seconds));
        }
    }
    ~ScopedWorkerDeadline() {
        tls_local_deadline_enabled = old_enabled;
        tls_local_deadline = old_deadline;
    }
};

static double solver_elapsed_seconds() {
    if (!solver_governor_started) return 0.0;
    return chrono::duration<double>(Clock::now() - solver_start_time).count();
}

// V5: pure deadline query used by evidence censoring. Unlike solver_should_stop(),
// this does not mutate interruption state. An improvement is admissible only when
// its complete hard-feasibility check has finished no later than the deadline.
static bool solver_deadline_passed() {
    return solver_governor_started &&
        cfg.hard_time_limit_s > 0.0 &&
        solver_elapsed_seconds() > cfg.hard_time_limit_s + 1e-9;
}

static double solver_deadline_overrun_seconds() {
    if (!solver_governor_started || cfg.hard_time_limit_s <= 0.0) return 0.0;
    return max(0.0, solver_elapsed_seconds() - cfg.hard_time_limit_s);
}

static bool governor_has_recorded_best() {
    return isfinite(solver_last_meaningful_objective) &&
        solver_last_meaningful_objective < INF_D / 2;
}

static double meaningful_gain_threshold(double obj) {
    double base = isfinite(obj) ? max(1.0, fabs(obj)) : 1.0;
    return max(cfg.meaningful_gain_abs, cfg.meaningful_gain_rel * base);
}

static void solver_governor_start() {
    lock_guard<mutex> lk(solver_governor_mutex);
    solver_start_time = Clock::now();
    solver_last_meaningful_improve_time = solver_start_time;
    solver_last_meaningful_objective = INF_D;
    solver_governor_started = true;
    solver_stop_requested.store(false, memory_order_relaxed);
    solver_phase_transition_requested.store(false, memory_order_relaxed);
    solver_stop_reason.clear();
}

static void solver_request_stop(const string &reason) {
    bool expected = false;
    if (!solver_stop_requested.compare_exchange_strong(expected, true)) {
        return;
    }

    double best_snapshot = INF_D;
    {
        lock_guard<mutex> lk(solver_governor_mutex);
        solver_stop_reason = reason;
        best_snapshot = solver_last_meaningful_objective;
    }

    if (isfinite(best_snapshot) && best_snapshot < INF_D / 2) {
        safe_log_line(
            "[AnytimeStop] ", reason,
            " elapsed=", solver_elapsed_seconds(), "s",
            " best=", best_snapshot
        );
    }
    else {
        safe_log_line(
            "[AnytimeStop] ", reason,
            " elapsed=", solver_elapsed_seconds(), "s",
            " best=N/A"
        );
    }
}

static void solver_note_global_best(double obj) {
    if (!solver_governor_started || !isfinite(obj)) return;

    bool should_log = false;
    double old = INF_D;
    double need = 0.0;

    {
        lock_guard<mutex> lk(solver_governor_mutex);

        if (!governor_has_recorded_best()) {
            solver_last_meaningful_objective = obj;
            solver_last_meaningful_improve_time = Clock::now();
            return;
        }

        need = meaningful_gain_threshold(solver_last_meaningful_objective);
        if (obj + need < solver_last_meaningful_objective) {
            old = solver_last_meaningful_objective;
            solver_last_meaningful_objective = obj;
            solver_last_meaningful_improve_time = Clock::now();
            solver_phase_transition_requested.store(false, memory_order_relaxed);
            should_log = true;
        }
    }

    if (should_log) {
        safe_log_line(
            "[Anytime] meaningful best ", old,
            " -> ", obj,
            " gain=", (old - obj),
            " threshold=", need,
            " elapsed=", solver_elapsed_seconds(), "s"
        );
    }
}

static bool solver_should_stop() {
    if (interrupted) {
        solver_request_stop("external interrupt");
        return true;
    }

    // A local worker deadline is cooperative and thread-local. It must never
    // set the process-wide interrupted flag or stop sibling portfolio workers.
    if (tls_local_deadline_enabled && Clock::now() >= tls_local_deadline) {
        return true;
    }

    if (!solver_governor_started) return false;

    double elapsed = solver_elapsed_seconds();

    if (cfg.hard_time_limit_s > 0.0 && elapsed >= cfg.hard_time_limit_s) {
        solver_request_stop("hard time limit reached");
        interrupted = 1;
        return true;
    }

    double patience = cfg.no_improve_stop_s;

    if (cfg.target_objective > 0.0 &&
        isfinite(solver_last_meaningful_objective) &&
        solver_last_meaningful_objective <= cfg.target_objective &&
        cfg.target_no_improve_stop_s > 0.0) {
        patience = cfg.target_no_improve_stop_s;
    }

    if (patience > 0.0 && governor_has_recorded_best()) {
        double no_gain_time = 0.0;
        {
            lock_guard<mutex> lk(solver_governor_mutex);
            no_gain_time = chrono::duration<double>(
                Clock::now() - solver_last_meaningful_improve_time
            ).count();
        }

        if (no_gain_time >= patience) {
            if (cfg.use_phase_specialized_engine) {
                bool expected = false;
                if (solver_phase_transition_requested.compare_exchange_strong(
                        expected, true, memory_order_relaxed)) {
                    safe_log_line(
                        "[AnytimeTransition-E1] no meaningful improvement for ",
                        no_gain_time, "s; request final phase elapsed=", elapsed,
                        " best=", solver_last_meaningful_objective
                    );
                }
                // Do not poison nested operators with a process-wide stop.
                // The epoch scheduler observes this flag at the next barrier.
                return solver_stop_requested.load(memory_order_relaxed);
            }
            solver_request_stop("no meaningful improvement timeout");
            interrupted = 1;
            return true;
        }
    }

    return solver_stop_requested.load(memory_order_relaxed);
}

static bool state_basic_feasible_for_global_best(const SolutionState &s) {
    if (s.routes.empty()) return false;
    if (s.served_count.empty()) return false;
    for (int c : s.served_count) {
        if (c > 1) return false;
    }

    return true;
}

static bool update_global_best(const SolutionState &s) {
    std::lock_guard<std::mutex> lock(global_best_mutex);
    if (!state_basic_feasible_for_global_best(s)) return false;
    if (global_best_state.routes.empty() ||
        s.objective + 1e-9 < global_best_state.objective) {
        global_best_state = s;
        solver_note_global_best(s.objective);
        return true;
    }
    return false;
}

static void signal_handler(int signum) {
    (void)signum;
    interrupted = 1;
}

/* ---------------- ObjectiveEvaluator ---------------- */
struct ObjectiveEvaluator {
    PairwiseManager *pm;
    Compressed *CG;
    double w_time;
    double w_co2;
    double w_late;
    double w_capacity;
    double co2_per_meter;
    const double HEAVY_OVERLOAD_PENALTY = 5000.0;

    ObjectiveEvaluator(PairwiseManager *p, Compressed *c, double wt, double wc, double wl, double wcap, double co2pm)
        : pm(p), CG(c), w_time(wt), w_co2(wc), w_late(wl), w_capacity(wcap), co2_per_meter(co2pm) {}

    RouteMetrics compute_route_metrics(const vector<int> &route, double /*unused*/ = 0.0) {
    RouteMetrics m;

    if (route.size() < 2) {
        return m;
    }

        double cur = cfg.route_start_time_s;
        double cur_trip_load = 0.0;
        double max_trip = 0.0;

        for (size_t i = 0; i + 1 < route.size(); ++i) {
            int a = route[i], b = route[i + 1];
            double tcost = fast_pair_time(a, b, pm);
            double dist_m = fast_pair_dist(a, b, pm);
            if (!isfinite(tcost)) tcost = 1e9;
            if (!isfinite(dist_m)) dist_m = 1e9;

            m.travel_seconds += min(tcost, 1e9);
            m.distance_m += min(dist_m, 1e9);
            m.co2_g += min(dist_m * co2_per_meter, 1e12);
            cur += tcost;

            if (CG->nodes[b].type == 1) {
                if (cfg.use_time_window) {
                    double late = max(0.0, cur - CG->nodes[b].latest);
                    m.lateness += late;
                    m.time_warp += late;
                }
                max_trip = max(max_trip, cur_trip_load);
                cur_trip_load = 0.0;
                continue;
            }
            if (CG->nodes[b].type == 2) {
                cur_trip_load += CG->nodes[b].garbage_amount;
                if (cfg.use_time_window) {
                    double start_service = max(cur, CG->nodes[b].earliest);

                    double wait = max(0.0, CG->nodes[b].earliest - cur);
                    m.waiting += wait;

                    double late = max(0.0, start_service - CG->nodes[b].latest);
                    m.lateness += late;
                    m.time_warp += late;

                    m.service += CG->nodes[b].service_time_s;
                    cur = start_service + CG->nodes[b].service_time_s;
                } else {
                    m.service += CG->nodes[b].service_time_s;
                    cur += CG->nodes[b].service_time_s;
                }
            }
        }

        max_trip = max(max_trip, cur_trip_load);

        m.max_trip_load = max_trip;
        m.capacity_penalty = max(0.0, max_trip - cfg.truck_capacity);

        // Count non-empty trips.
        m.trip_count = 0;
        bool has_customer_in_trip = false;

        for (size_t i = 1; i < route.size(); ++i) {
            int nid = route[i];

            if (CG->nodes[nid].type == 1) {
                if (has_customer_in_trip) {
                    m.trip_count++;
                    has_customer_in_trip = false;
                }
                continue;
            }

            if (CG->nodes[nid].type == 2) {
                has_customer_in_trip = true;
            }
        }

        if (has_customer_in_trip) {
            m.trip_count++;
        }

        // Optional max-trip penalty.
        if (cfg.max_trips_per_truck > 0 && m.trip_count > cfg.max_trips_per_truck) {
            m.trip_excess_penalty =
                cfg.w_trip_excess * (double)(m.trip_count - cfg.max_trips_per_truck);
        } else {
            m.trip_excess_penalty = 0.0;
        }

        int customers = 0;
        for (int nid : route) {
            if (CG->nodes[nid].type == 2) customers++;
        }

        m.route_penalty = (customers > 0) ? 0.01 * (double)customers : 0.0;

        double overload_penalty =
            w_capacity * m.capacity_penalty +
            HEAVY_OVERLOAD_PENALTY * m.capacity_penalty;

        double duration_seconds =
            m.travel_seconds +
            m.waiting +
            m.service;

        double tw_penalty_cost = 0.0;

        if (cfg.use_time_window) {
            if (cfg.tw_use_time_warp) {
                tw_penalty_cost = cfg.tw_time_warp_penalty * m.time_warp;
            }
            else {
                tw_penalty_cost = w_late * m.lateness;
            }
        }

        double wait_penalty_cost = 0.0;

        if (cfg.objective_mode != "distance" || cfg.tw_penalize_waiting_in_distance) {
            wait_penalty_cost = cfg.w_wait * m.waiting;
        }

        if (cfg.objective_mode == "distance") {
            m.weighted_cost =
                m.distance_m +
                tw_penalty_cost +
                overload_penalty +
                m.trip_excess_penalty +
                ((customers > 0) ? cfg.solomon_vehicle_penalty : 0.0);
        }
        else if (cfg.objective_mode == "time") {
            m.weighted_cost =
                duration_seconds +
                tw_penalty_cost +
                overload_penalty +
                m.trip_excess_penalty;
        }
        else {
            m.weighted_cost =
                m.distance_m +
                w_time * duration_seconds +
                tw_penalty_cost +
                overload_penalty +
                m.trip_excess_penalty;
        }
        return m;
    }

    double compute_objective_from_metrics(const vector<RouteMetrics> &metrics) {
        double total = 0.0;
        for (const auto &m : metrics) total += m.weighted_cost;
        return total;
    }

    /* approx deltas */
    double delta_swap_approx(const SolutionState &state, int r1, int i, int r2, int j) {
        if (i <= 0 || j <= 0) return INF_D;
        if (i + 1 >= (int)state.routes[r1].size() || j + 1 >= (int)state.routes[r2].size()) return INF_D;

        if (r1 == r2) {
            const auto &r = state.routes[r1];
            int a_prev = r[i - 1], a = r[i], a_next = r[i + 1];
            int b_prev = r[j - 1], b = r[j], b_next = r[j + 1];

            // If adjacent, the local edges overlap; safest is fallback to zero.
            if (abs(i - j) <= 1) return INF_D;

            double ap_a = fast_pair_search_cost(a_prev, a, pm);
            double a_an = fast_pair_search_cost(a, a_next, pm);
            double bp_b = fast_pair_search_cost(b_prev, b, pm);
            double b_bn = fast_pair_search_cost(b, b_next, pm);

            double ap_b = fast_pair_search_cost(a_prev, b, pm);
            double b_an = fast_pair_search_cost(b, a_next, pm);
            double bp_a = fast_pair_search_cost(b_prev, a, pm);
            double a_bn = fast_pair_search_cost(a, b_next, pm);

            double cur_local = ap_a + a_an + bp_b + b_bn;
            double new_local = ap_b + b_an + bp_a + a_bn;
            return new_local - cur_local;
        }

        int a_prev = state.routes[r1][i - 1];
        int a = state.routes[r1][i];
        int a_next = state.routes[r1][i + 1];

        int b_prev = state.routes[r2][j - 1];
        int b = state.routes[r2][j];
        int b_next = state.routes[r2][j + 1];

        double ap_a = fast_pair_search_cost(a_prev, a, pm);
        double a_an = fast_pair_search_cost(a, a_next, pm);

        double bp_b = fast_pair_search_cost(b_prev, b, pm);
        double b_bn = fast_pair_search_cost(b, b_next, pm);

        double ap_b = fast_pair_search_cost(a_prev, b, pm);
        double b_an = fast_pair_search_cost(b, a_next, pm);

        double bp_a = fast_pair_search_cost(b_prev, a, pm);
        double a_bn = fast_pair_search_cost(a, b_next, pm);

        double cur_local = ap_a + a_an + bp_b + b_bn;
        double new_local = ap_b + b_an + bp_a + a_bn;

        return new_local - cur_local;
    }

    double delta_relocate_approx(const SolutionState &state, int r_from, int pos_from, int r_to, int pos_to) {
        if (pos_from <= 0 || pos_from + 1 >= (int)state.routes[r_from].size()) return 0.0;

        if (r_from == r_to) {
            const auto &r = state.routes[r_from];
            int node = r[pos_from];
            vector<int> tmp = r;
            tmp.erase(tmp.begin() + pos_from);
            if (pos_to > pos_from) pos_to--;
            tmp.insert(tmp.begin() + pos_to, node);

            // Local exact recompute is safer for same-route relocate.
            double load = 0.0;
            for (int nid : tmp) if (CG->nodes[nid].type == 2) load += CG->nodes[nid].garbage_amount;
            RouteMetrics m = compute_route_metrics(tmp, load);
            return m.weighted_cost - state.route_metrics[r_from].weighted_cost;
        }

        int node = state.routes[r_from][pos_from];
        int prev_from = state.routes[r_from][pos_from - 1];
        int next_from = state.routes[r_from][pos_from + 1];
        int prev_to = state.routes[r_to][pos_to - 1];
        int next_to = state.routes[r_to][pos_to];

        double pf_node = fast_pair_search_cost(prev_from, node, pm);
        double node_nf = fast_pair_search_cost(node, next_from, pm);
        double pf_nf = fast_pair_search_cost(prev_from, next_from, pm);
        double pt_nt = fast_pair_search_cost(prev_to, next_to, pm);
        double pt_node = fast_pair_search_cost(prev_to, node, pm);
        double node_nt = fast_pair_search_cost(node, next_to, pm);

        double cur_from = pf_node + node_nf;
        double new_from = pf_nf;
        double cur_to = pt_nt;
        double new_to = pt_node + node_nt;
        return (new_from + new_to) - (cur_from + cur_to);
    }

    double delta_cross2_approx(const SolutionState &state, int r1, int i1, int r2, int i2) {
        // V18: the SA operator below exchanges complete route tails beginning at
        // i1/i2.  The legacy approximation accidentally scored a two-customer
        // block exchange instead.  For a tail exchange (without reversal), all
        // internal tail arcs are preserved; only the two cut arcs change.
        if (r1 == r2) return INF_D;
        if (i1 <= 0 || i2 <= 0) return INF_D;
        if (i1 >= (int)state.routes[r1].size() || i2 >= (int)state.routes[r2].size()) return INF_D;

        int a_prev = state.routes[r1][i1 - 1];
        int a1 = state.routes[r1][i1];
        int b_prev = state.routes[r2][i2 - 1];
        int b1 = state.routes[r2][i2];

        const double old_cut =
            fast_pair_search_cost(a_prev, a1, pm) +
            fast_pair_search_cost(b_prev, b1, pm);
        const double new_cut =
            fast_pair_search_cost(a_prev, b1, pm) +
            fast_pair_search_cost(b_prev, a1, pm);

        if (!isfinite(old_cut) || !isfinite(new_cut)) return INF_D;
        return new_cut - old_cut;
    }
};

/* ---------------- Validation helpers ---------------- */
struct ValidationReport {
    int total_nodes = 0, customers = 0, vehicles = 0, reachable_customers = 0, unreachable_customers = 0;
    double total_demand = 0.0;
    int total_capacity = 0;
    bool valid = false;
    vector<int> unreachable_list;
    string message;
};

vector<double> dijkstra_simple(const Compressed &CG, int src) {
    int N = (int)CG.nodes.size();
    vector<double> dist(N, INF_D);
    using P = pair<double, int>;
    priority_queue<P, vector<P>, greater<P>> pq;
    dist[src] = 0;
    pq.push({0, src});
    while (!pq.empty()) {
        auto [d, u] = pq.top();
        pq.pop();
        if (d > dist[u]) continue;
        for (int eid : CG.out_edges[u]) {
            int v = CG.edges[eid].v;
            double w = CG.edges[eid].length_m;
            if (dist[v] > d + w) {
                dist[v] = d + w;
                pq.push({dist[v], v});
            }
        }
    }
    return dist;
}

ValidationReport validate_compressed(const Compressed &CG) {
    ValidationReport r;
    r.total_nodes = (int)CG.nodes.size();
    r.customers = 0;
    r.vehicles = cfg.num_trucks;
    r.total_capacity = (int)round(cfg.num_trucks * cfg.truck_capacity);
    r.valid = true;
    r.message = "VALID";

    for (auto &n : CG.nodes) if (n.type == 2) r.customers++;
    for (auto &e : CG.edges) {
        if (e.length_m < 0) {
            r.valid = false;
            r.message = "Negative edge length";
            return r;
        }
    }
    if (CG.nodes.empty()) {
        r.valid = false;
        r.message = "Empty graph";
        return r;
    }

    int depot_idx = -1;
    for (auto &n : CG.nodes) if (n.type == 1) {
        depot_idx = n.id;
        break;
    }
    if (depot_idx == -1) {
        r.valid = false;
        r.message = "No depot defined";
        return r;
    }

    auto dist = dijkstra_simple(CG, depot_idx);
    int reachable = 0;
    for (auto &n : CG.nodes) {
        if (n.type == 2) {
            int physical = canonical_node(n.id);
            if (physical < 0 || physical >= (int)dist.size() ||
                dist[physical] >= INF_D / 2) {
                r.unreachable_customers++;
                r.unreachable_list.push_back(n.id);
            } else {
                reachable++;
            }
        }
    }
    r.reachable_customers = reachable;
    double total_demand = 0.0;
    for (auto &n : CG.nodes) if (n.type == 2) total_demand += n.garbage_amount;
    r.total_demand = total_demand;

    if (!r.unreachable_list.empty()) {
        r.valid = false;
        r.message = "Unreachable customers exist";
    }
    return r;
}

/* ---------------- Helpers: normalize & enforce trip separators ---------------- */
static int find_depot_idx(const Compressed &CG) {
    for (size_t i = 0; i < CG.nodes.size(); ++i) if (CG.nodes[i].type == 1) return (int)i;
    return 0;
}

static void normalize_route(vector<int> &route, int depot) {
    if (route.empty()) {
        route.push_back(depot);
        route.push_back(depot);
        return;
    }
    vector<int> out;
    out.reserve(route.size());
    for (size_t i = 0; i < route.size(); ++i) {
        if (i > 0 && route[i] == depot && route[i - 1] == depot) continue;
        out.push_back(route[i]);
    }
    if (out.empty() || out.front() != depot) out.insert(out.begin(), depot);
    if (out.empty() || out.back() != depot) out.push_back(depot);
    route.swap(out);
}

// Ensure depot separators and split trips when needed
static void enforce_trip_separators(vector<int> &route, const Compressed &CG, int depot) {
    normalize_route(route, depot);

    if (!cfg.allow_multi_trip) {
        vector<int> out;
        out.reserve(route.size());
        out.push_back(depot);

        for (int nid : route) {
            if (nid == depot) continue;
            out.push_back(nid);
        }
        out.push_back(depot);
        normalize_route(out, depot);
        route.swap(out);
        return;
    }

    vector<int> out;
    out.reserve(route.size() * 2);
    out.push_back(depot);
    double cur_load = 0.0;

    for (size_t i = 1; i < route.size(); ++i) {
        int nid = route[i];
        if (nid == depot) {
            if (out.empty() || out.back() != depot) out.push_back(depot);
            cur_load = 0.0;
            continue;
        }
        double demand = (CG.nodes[nid].type == 2) ? CG.nodes[nid].garbage_amount : 0.0;
        if (cur_load + demand > cfg.truck_capacity + 1e-9) {
            if (out.empty() || out.back() != depot) out.push_back(depot);
            out.push_back(depot);
            out.push_back(nid);
            cur_load = demand;
        } else {
            out.push_back(nid);
            if (CG.nodes[nid].type == 2) cur_load += demand;
        }
    }
    if (out.empty() || out.back() != depot) out.push_back(depot);
    normalize_route(out, depot);
    route.swap(out);
}

// compute maximum single-trip overload (max trip load - capacity if positive)
static double compute_route_overload_max(const vector<int> &route_in, const Compressed &CG, int depot) {
    vector<int> route = route_in;
    enforce_trip_separators(route, CG, depot);
    double cur_load = 0.0;
    double max_trip = 0.0;
    for (size_t i = 1; i < route.size(); ++i) {
        int nid = route[i];
        if (nid == depot) {
            max_trip = max(max_trip, cur_load);
            cur_load = 0.0;
            continue;
        }
        if (CG.nodes[nid].type == 2) cur_load += CG.nodes[nid].garbage_amount;
    }
    max_trip = max(max_trip, cur_load);
    return max(0.0, max_trip - cfg.truck_capacity);
}

/* ---------------- Central recompute ---------------- */
static void recompute_state_metrics_and_loads(SolutionState &state, ObjectiveEvaluator &ev) {
    if ((int)state.routes.size() != cfg.num_trucks) {
        state.routes.resize(cfg.num_trucks);
    }
    int R = (int)state.routes.size();
    int depot_idx = find_depot_idx(*ev.CG);
    if (depot_idx < 0) depot_idx = 0;

    for (int r = 0; r < R; ++r) {
        enforce_trip_separators(state.routes[r], *ev.CG, depot_idx);
    }

    state.route_metrics.assign(R, RouteMetrics());
    state.route_load.assign(R, 0.0);
    state.route_max_trip_load.assign(R, 0.0);
    state.served_count.assign(ev.CG->nodes.size(), 0);

    for (int r = 0; r < R; ++r) {
        double total_load = 0.0;
        double cur_trip = 0.0;
        double max_trip = 0.0;
        for (int nid : state.routes[r]) {
            if (ev.CG->nodes[nid].type == 1) {
                max_trip = max(max_trip, cur_trip);
                cur_trip = 0.0;
            } else if (ev.CG->nodes[nid].type == 2) {
                total_load += ev.CG->nodes[nid].garbage_amount;
                cur_trip += ev.CG->nodes[nid].garbage_amount;
                state.served_count[nid]++;
            }
        }
        max_trip = max(max_trip, cur_trip);
        state.route_load[r] = total_load;
        state.route_max_trip_load[r] = max_trip;
        state.route_metrics[r] = ev.compute_route_metrics(state.routes[r], max_trip);
    }
    state.objective = ev.compute_objective_from_metrics(state.route_metrics);

    // Profiling: count how many times we recomputed state metrics
    profile.recompute_calls.fetch_add(1, memory_order_relaxed);
}

/* ---------------- Dirty route recompute ---------------- */

static void recompute_dirty_routes(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    const vector<int> &dirty_routes
) {
    if (!cfg.use_dirty_route_recompute) {
        recompute_state_metrics_and_loads(state, ev);
        return;
    }

    int depot_idx = find_depot_idx(*ev.CG);
    if (depot_idx < 0) depot_idx = 0;

    if ((int)state.routes.size() != cfg.num_trucks) {
        state.routes.resize(cfg.num_trucks);
    }

    int R = (int)state.routes.size();

    if ((int)state.route_metrics.size() != R) {
        // Metrics missing means we cannot safely reuse clean routes.
        recompute_state_metrics_and_loads(state, ev);
        return;
    }

    if ((int)state.route_load.size() != R) {
        state.route_load.assign(R, 0.0);
    }

    if ((int)state.route_max_trip_load.size() != R) {
        state.route_max_trip_load.assign(R, 0.0);
    }

    vector<int> unique_dirty;
    vector<char> seen(R, 0);

    for (int r : dirty_routes) {
        if (r < 0 || r >= R) continue;
        if (!seen[r]) {
            seen[r] = 1;
            unique_dirty.push_back(r);
        }
    }

    if (unique_dirty.empty()) {
        return;
    }

    // Recompute only dirty route metrics/load.
    for (int r : unique_dirty) {
        enforce_trip_separators(state.routes[r], *ev.CG, depot_idx);

        double total_load = 0.0;
        double cur_trip = 0.0;
        double max_trip = 0.0;

        for (int nid : state.routes[r]) {
            if (ev.CG->nodes[nid].type == 1) {
                max_trip = max(max_trip, cur_trip);
                cur_trip = 0.0;
            } else if (ev.CG->nodes[nid].type == 2) {
                total_load += ev.CG->nodes[nid].garbage_amount;
                cur_trip += ev.CG->nodes[nid].garbage_amount;
            }
        }

        max_trip = max(max_trip, cur_trip);

        state.route_load[r] = total_load;
        state.route_max_trip_load[r] = max_trip;
        state.route_metrics[r] = ev.compute_route_metrics(state.routes[r], max_trip);
    }

    // Rebuild served_count globally. Cheap and safe.
    state.served_count.assign(ev.CG->nodes.size(), 0);

    for (int r = 0; r < R; ++r) {
        for (int nid : state.routes[r]) {
            if (nid >= 0 &&
                nid < (int)ev.CG->nodes.size() &&
                ev.CG->nodes[nid].type == 2) {
                state.served_count[nid]++;
            }
        }
    }

    state.objective = ev.compute_objective_from_metrics(state.route_metrics);

    profile.recompute_calls.fetch_add(1, memory_order_relaxed);
}

[[maybe_unused]] static bool dirty_recompute_matches_full(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    double eps = 1e-6
) {
    SolutionState full = state;
    recompute_state_metrics_and_loads(full, ev);

    if (fabs(full.objective - state.objective) > eps) {
        cerr << "[DirtyRecomputeCheck] objective mismatch dirty="
            << state.objective
            << " full=" << full.objective
            << " diff=" << fabs(full.objective - state.objective)
            << "\n";
        return false;
    }

    if (full.served_count.size() != state.served_count.size()) {
        cerr << "[DirtyRecomputeCheck] served_count size mismatch\n";
        return false;
    }

    for (int i = 0; i < (int)full.served_count.size(); ++i) {
        if (full.served_count[i] != state.served_count[i]) {
            cerr << "[DirtyRecomputeCheck] served_count mismatch node="
                << i
                << " dirty=" << state.served_count[i]
                << " full=" << full.served_count[i]
                << "\n";
            return false;
        }
    }

    return true;
}

/* ---------------- Utility helpers ---------------- */
static bool route_has_duplicate_customers_strict(const vector<int> &route, const Compressed &CG) {
    unordered_set<int> s;
    for (int nid : route) {
        if (CG.nodes[nid].type == 2) {
            if (s.count(nid)) return true;
            s.insert(nid);
        }
    }
    return false;
}

static bool trips_feasible_for_route(const vector<int> &route, const Compressed &CG, int depot) {
    vector<int> tmp = route;
    enforce_trip_separators(tmp, CG, depot);
    double cur_load = 0.0;
    for (size_t i = 1; i < tmp.size(); ++i) {
        int nid = tmp[i];
        if (nid == depot) {
            if (cur_load > cfg.truck_capacity + 1e-9) return false;
            cur_load = 0.0;
            continue;
        }
        if (CG.nodes[nid].type == 2) cur_load += CG.nodes[nid].garbage_amount;
    }
    if (cur_load > cfg.truck_capacity + 1e-9) return false;
    return true;
}

static bool solution_serves_all_customers_once(
    const SolutionState &state,
    const Compressed &CG
) {
    vector<int> cnt(CG.nodes.size(), 0);

    for (const auto &route : state.routes) {
        for (int nid : route) {
            if (nid >= 0 &&
                nid < (int)CG.nodes.size() &&
                CG.nodes[nid].type == 2) {
                cnt[nid]++;
            }
        }
    }

    for (const auto &n : CG.nodes) {
        if (n.type == 2 && cnt[n.id] != 1) {
            return false;
        }
    }

    return true;
}

static bool solution_capacity_feasible(
    const SolutionState &state,
    const Compressed &CG
) {
    int depot = find_depot_idx(CG);
    for (const auto &route : state.routes) {
        if (!trips_feasible_for_route(route, CG, depot)) {
            return false;
        }
    }
    return true;
}

static int count_nonempty_trips_in_route(
    const vector<int> &route,
    const Compressed &CG
) {
    int trips = 0;
    bool has_customer = false;

    for (int nid : route) {
        if (nid < 0 || nid >= (int)CG.nodes.size()) continue;

        if (CG.nodes[nid].type == 1) {
            if (has_customer) {
                trips++;
                has_customer = false;
            }
        }
        else if (CG.nodes[nid].type == 2) {
            has_customer = true;
        }
    }

    if (has_customer) trips++;
    return trips;
}

static bool solution_trip_limit_feasible(
    const SolutionState &state,
    const Compressed &CG
) {
    if (cfg.max_trips_per_truck <= 0) return true;

    for (const auto &route : state.routes) {
        if (count_nonempty_trips_in_route(route, CG) > cfg.max_trips_per_truck) {
            return false;
        }
    }

    return true;
}

static bool solution_route_structure_feasible(
    const SolutionState &state,
    const Compressed &CG
) {
    // V21: validate the solver's *actual canonical representation*.  Empty
    // vehicles normalize to a single depot token; non-empty routes must start
    // and end at the unique depot and may contain only customers internally
    // (plus depot separators when multi-trip is enabled).
    const int depot = find_depot_idx(CG);
    if (depot < 0 || depot >= (int)CG.nodes.size()) return false;

    for (const auto &route : state.routes) {
        if (route.empty()) return false;

        bool has_customer = false;
        for (int nid : route) {
            if (nid < 0 || nid >= (int)CG.nodes.size()) return false;
            if (CG.nodes[nid].type == 2) has_customer = true;
        }

        if (!has_customer) {
            // normalize_route() intentionally canonicalizes an empty vehicle as
            // {depot}; accept repeated depot tokens defensively but nothing else.
            for (int nid : route) if (nid != depot) return false;
            continue;
        }

        if (route.size() < 3) return false;
        if (route.front() != depot || route.back() != depot) return false;

        for (size_t i = 0; i < route.size(); ++i) {
            const int nid = route[i];
            const int type = CG.nodes[nid].type;
            if (type == 1) {
                if (nid != depot) return false;
                if (!cfg.allow_multi_trip && i != 0 && i + 1 != route.size()) return false;
            }
            else if (type != 2) {
                return false; // compact routes may not contain arbitrary road nodes
            }
        }
    }
    return true;
}

static bool solution_fully_feasible(
    const SolutionState &state,
    const Compressed &CG
) {
    return solution_serves_all_customers_once(state, CG) &&
        solution_capacity_feasible(state, CG) &&
        solution_trip_limit_feasible(state, CG);
}

static bool solution_hard_feasible(
    const SolutionState &state,
    const Compressed &CG,
    PairwiseManager &pm
) {
    if (!solution_route_structure_feasible(state, CG)) return false;
    if (!solution_fully_feasible(state, CG)) return false;

    for (const auto &route : state.routes) {
        double cur = cfg.route_start_time_s;

        for (size_t i = 0; i + 1 < route.size(); ++i) {
            int a = route[i];
            int b = route[i + 1];

            if (a < 0 || b < 0 ||
                a >= (int)CG.nodes.size() ||
                b >= (int)CG.nodes.size()) {
                return false;
            }

            double t = fast_pair_time(a, b, &pm);
            double d = fast_pair_dist(a, b, &pm);

            if (!isfinite(t) || !isfinite(d) ||
                t >= INF_D / 2 ||
                d >= INF_D / 2) {
                return false;
            }

            cur += t;

            if (CG.nodes[b].type == 1 && cfg.use_time_window &&
                cur > CG.nodes[b].latest + cfg.tw_lateness_eps) {
                return false;
            }

            if (CG.nodes[b].type == 2) {
                if (cfg.use_time_window) {
                    double start_service = max(cur, CG.nodes[b].earliest);
                    if (start_service > CG.nodes[b].latest + cfg.tw_lateness_eps) {
                        return false;
                    }
                    cur = start_service + CG.nodes[b].service_time_s;
                }
                else {
                    cur += CG.nodes[b].service_time_s;
                }
            }
        }
    }

    return true;
}

static bool route_hard_tw_feasible(
    const vector<int> &route_in,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const Compressed &CG = *ev.CG;
    int depot = find_depot_idx(CG);

    vector<int> route = route_in;
    normalize_route(route, depot);
    enforce_trip_separators(route, CG, depot);

    if (!trips_feasible_for_route(route, CG, depot)) {
        return false;
    }

    double cur = cfg.route_start_time_s;

    for (int i = 0; i + 1 < (int)route.size(); ++i) {
        int a = route[i];
        int b = route[i + 1];

        if (a < 0 || b < 0 ||
            a >= (int)CG.nodes.size() ||
            b >= (int)CG.nodes.size()) {
            return false;
        }

        double t = fast_pair_time(a, b, &pm);
        double d = fast_pair_dist(a, b, &pm);

        if (!isfinite(t) || !isfinite(d) ||
            t >= INF_D / 2 ||
            d >= INF_D / 2) {
            return false;
        }

        cur += t;

        if (CG.nodes[b].type == 1 && cfg.use_time_window &&
            cur > CG.nodes[b].latest + cfg.tw_lateness_eps) {
            return false;
        }

        if (CG.nodes[b].type == 2) {
            if (cfg.use_time_window) {
                double start_service = max(cur, CG.nodes[b].earliest);

                if (start_service > CG.nodes[b].latest + cfg.tw_lateness_eps) {
                    return false;
                }

                cur = start_service + CG.nodes[b].service_time_s;
            }
            else {
                cur += CG.nodes[b].service_time_s;
            }
        }
    }

    return true;
}

static bool take_if_better_feasible(
    SolutionState &dst,
    SolutionState cand,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    recompute_state_metrics_and_loads(cand, ev);

    if (!solution_hard_feasible(cand, *ev.CG, pm)) {
        return false;
    }

    if (dst.routes.empty() || cand.objective + 1e-9 < dst.objective) {
        dst = std::move(cand);
        return true;
    }

    return false;
}

static bool update_global_best_checked(
    const SolutionState &s,
    const Compressed &CG,
    PairwiseManager &pm
);

static bool accept_improving_hard_candidate(
    SolutionState &best,
    SolutionState cand,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const string &label
) {
    recompute_state_metrics_and_loads(cand, ev);

    double before = best.objective;
    double after = cand.objective;

    if (!solution_hard_feasible(cand, *ev.CG, pm)) {
        cerr << "[" << label << "] rejected infeasible"
            << " before=" << before
            << " after=" << after
            << "\n";
        return false;
    }

    if (after + 1e-9 < before) {
        best = std::move(cand);
        recompute_state_metrics_and_loads(best, ev);
        update_global_best_checked(best, *ev.CG, pm);

        cerr << "[" << label << "] accepted"
            << " before=" << before
            << " after=" << best.objective
            << " gain=" << (before - best.objective)
            << "\n";

        return true;
    }

    cerr << "[" << label << "] rejected no-improve"
        << " before=" << before
        << " after=" << after
        << "\n";

    return false;
}

static void clear_route_metric_cache() {
    route_metric_cache.clear_all();
}
static double total_time_warp_of_state(const SolutionState &s) {
    double tw = 0.0;

    for (const auto &m : s.route_metrics) {
        tw += m.time_warp;
    }

    return tw;
}

[[maybe_unused]] static bool adapt_time_warp_penalty_after_phase(
    SolutionState &s,
    ObjectiveEvaluator &ev
) {
    if (!cfg.use_time_window) return false;
    if (!cfg.tw_use_time_warp) return false;

    double old_penalty = cfg.tw_time_warp_penalty;
    double tw = total_time_warp_of_state(s);

    if (tw > cfg.tw_lateness_eps) {
        cfg.tw_time_warp_penalty = min(
            cfg.tw_time_warp_penalty_max,
            cfg.tw_time_warp_penalty * cfg.tw_time_warp_growth
        );
    }
    else {
        cfg.tw_time_warp_penalty = max(
            cfg.tw_time_warp_penalty_min,
            cfg.tw_time_warp_penalty / sqrt(cfg.tw_time_warp_growth)
        );
    }

    if (fabs(cfg.tw_time_warp_penalty - old_penalty) <= 1e-12) {
        return false;
    }

    clear_route_metric_cache();
    recompute_state_metrics_and_loads(s, ev);

    cerr << "[TW-ADAPT]"
        << " time_warp=" << tw
        << " lambda_old=" << old_penalty
        << " lambda_new=" << cfg.tw_time_warp_penalty
        << " obj=" << s.objective
        << "\n";

    return true;
}

static vector<int> get_missing_customers(
    const SolutionState &state,
    const Compressed &CG
) {
    vector<int> cnt(CG.nodes.size(), 0);

    for (const auto &route : state.routes) {
        for (int nid : route) {
            if (nid >= 0 &&
                nid < (int)CG.nodes.size() &&
                CG.nodes[nid].type == 2) {
                cnt[nid]++;
            }
        }
    }

    vector<int> missing;
    for (const auto &n : CG.nodes) {
        if (n.type == 2 && cnt[n.id] == 0) {
            missing.push_back(n.id);
        }
    }

    return missing;
}

static vector<int> get_duplicate_customers(
    const SolutionState &state,
    const Compressed &CG
) {
    vector<int> cnt(CG.nodes.size(), 0);

    for (const auto &route : state.routes) {
        for (int nid : route) {
            if (nid >= 0 &&
                nid < (int)CG.nodes.size() &&
                CG.nodes[nid].type == 2) {
                cnt[nid]++;
            }
        }
    }

    vector<int> dup;
    for (const auto &n : CG.nodes) {
        if (n.type == 2 && cnt[n.id] > 1) {
            dup.push_back(n.id);
        }
    }

    return dup;
}

static double route_exact_cost(const vector<int>& route, ObjectiveEvaluator &ev) {
    double load = 0.0;
    for (int nid : route) if (ev.CG->nodes[nid].type == 2) load += ev.CG->nodes[nid].garbage_amount;
    return ev.compute_route_metrics(route, load).weighted_cost;
}

static bool euclidean_uncross_route_once(
    vector<int> &route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!euclidean_cuts_enabled() || !cfg.euclidean_uncross_routes) return false;
    if ((int)route.size() < 6) return false;

    const Compressed &CG = *ev.CG;
    double old_cost = route_exact_cost(route, ev);

    for (int i = 1; i + 2 < (int)route.size(); ++i) {
        int a = route[i - 1];
        int b = route[i];

        for (int k = i + 2; k + 1 < (int)route.size(); ++k) {
            int c = route[k];
            int d = route[k + 1];

            // Avoid weird depot separator interactions.
            if (CG.nodes[a].type == 1 || CG.nodes[b].type == 1 ||
                CG.nodes[c].type == 1 || CG.nodes[d].type == 1) {
                continue;
            }

            if (!segments_cross_strict(CG.nodes[a], CG.nodes[b], CG.nodes[c], CG.nodes[d])) {
                continue;
            }

            double old_edges =
                fast_pair_dist(a, b, &pm) +
                fast_pair_dist(c, d, &pm);

            double new_edges =
                fast_pair_dist(a, c, &pm) +
                fast_pair_dist(b, d, &pm);

            if (new_edges + 1e-9 >= old_edges) {
                continue;
            }

            vector<int> cand = route;
            reverse(cand.begin() + i, cand.begin() + k + 1);

            double new_cost = route_exact_cost(cand, ev);

            if (new_cost + 1e-9 < old_cost) {
                route.swap(cand);
                return true;
            }
        }
    }

    return false;
}

static void euclidean_uncross_route_full(
    vector<int> &route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!euclidean_cuts_enabled() || !cfg.euclidean_uncross_routes) return;

    int passes = max(0, cfg.euclidean_uncross_passes);

    for (int p = 0; p < passes; ++p) {
        if (!euclidean_uncross_route_once(route, ev, pm)) {
            break;
        }
    }
}

static void euclidean_branch_polish_solution(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!euclidean_cuts_enabled()) return;

    int depot = find_depot_idx(*ev.CG);

    for (auto &route : state.routes) {
        normalize_route(route, depot);
        euclidean_uncross_route_full(route, ev, pm);
        normalize_route(route, depot);
    }

    recompute_state_metrics_and_loads(state, ev);
}

static bool euclidean_deep_interroute_once(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    (void)pm;
    if (!metric_is_euclidean()) return false;
    if (!cfg.euclidean_deep_interroute) return false;

    const Compressed &CG = *ev.CG;
    int depot = find_depot_idx(CG);

    SolutionState best_state = state;
    double best_obj = state.objective;
    bool improved = false;

    int R = (int)state.routes.size();

    // ------------------------------------------------------------
    // 1-customer relocate between different routes.
    // Exact accept only.
    // ------------------------------------------------------------
    if (cfg.euclidean_deep_try_relocate) {
        for (int r_from = 0; r_from < R; ++r_from) {
            const auto &src = state.routes[r_from];

            for (int i = 1; i + 1 < (int)src.size(); ++i) {
                int node = src[i];

                if (node < 0 || node >= (int)CG.nodes.size()) continue;
                if (CG.nodes[node].type != 2) continue;

                for (int r_to = 0; r_to < R; ++r_to) {
                    if (r_to == r_from) continue;

                    const auto &dst = state.routes[r_to];

                    for (int pos = 1; pos < (int)dst.size(); ++pos) {
                        SolutionState cand = state;

                        // Remove node from source route.
                        auto &A = cand.routes[r_from];
                        auto &B = cand.routes[r_to];

                        if (i <= 0 || i >= (int)A.size()) continue;
                        if (A[i] != node) continue;

                        A.erase(A.begin() + i);

                        // Insert into target route.
                        int insert_pos = min(pos, (int)B.size() - 1);
                        insert_pos = max(1, insert_pos);

                        B.insert(B.begin() + insert_pos, node);

                        enforce_trip_separators(A, CG, depot);
                        enforce_trip_separators(B, CG, depot);

                        if (!trips_feasible_for_route(A, CG, depot)) continue;
                        if (!trips_feasible_for_route(B, CG, depot)) continue;

                        recompute_state_metrics_and_loads(cand, ev);

                        if (!solution_fully_feasible(cand, CG)) continue;

                        if (cand.objective + 1e-9 < best_obj) {
                            best_obj = cand.objective;
                            best_state = std::move(cand);
                            improved = true;
                        }
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------
    // 1-1 swap between different routes.
    // Exact accept only.
    // ------------------------------------------------------------
    if (cfg.euclidean_deep_try_swap) {
        for (int r1 = 0; r1 < R; ++r1) {
            for (int r2 = r1 + 1; r2 < R; ++r2) {
                const auto &A0 = state.routes[r1];
                const auto &B0 = state.routes[r2];

                for (int i = 1; i + 1 < (int)A0.size(); ++i) {
                    int a = A0[i];
                    if (a < 0 || a >= (int)CG.nodes.size()) continue;
                    if (CG.nodes[a].type != 2) continue;

                    for (int j = 1; j + 1 < (int)B0.size(); ++j) {
                        int b = B0[j];
                        if (b < 0 || b >= (int)CG.nodes.size()) continue;
                        if (CG.nodes[b].type != 2) continue;

                        SolutionState cand = state;

                        auto &A = cand.routes[r1];
                        auto &B = cand.routes[r2];

                        if (i <= 0 || i >= (int)A.size()) continue;
                        if (j <= 0 || j >= (int)B.size()) continue;
                        if (A[i] != a || B[j] != b) continue;

                        swap(A[i], B[j]);

                        enforce_trip_separators(A, CG, depot);
                        enforce_trip_separators(B, CG, depot);

                        if (!trips_feasible_for_route(A, CG, depot)) continue;
                        if (!trips_feasible_for_route(B, CG, depot)) continue;

                        recompute_state_metrics_and_loads(cand, ev);

                        if (!solution_fully_feasible(cand, CG)) continue;

                        if (cand.objective + 1e-9 < best_obj) {
                            best_obj = cand.objective;
                            best_state = std::move(cand);
                            improved = true;
                        }
                    }
                }
            }
        }
    }

    if (improved) {
        state = std::move(best_state);
        return true;
    }

    return false;
}

static void euclidean_deep_interroute_descent(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!metric_is_euclidean()) return;
    if (!cfg.euclidean_deep_interroute) return;

    double start_obj = state.objective;

    int rounds = max(0, cfg.euclidean_deep_interroute_rounds);
    int accepted = 0;

    for (int it = 0; it < rounds; ++it) {
        bool ok = euclidean_deep_interroute_once(state, ev, pm);
        if (!ok) break;
        accepted++;

        // Clean geometry after each accepted inter-route change.
        if (euclidean_cuts_enabled()) {
            euclidean_branch_polish_solution(state, ev, pm);
        }
    }

    if (accepted > 0) {
        cerr << "[euclidean-deep] start=" << start_obj
            << " end=" << state.objective
            << " gain=" << (start_obj - state.objective)
            << " accepted=" << accepted
            << "\n";
    }
}

static bool is_candidate_neighbor(int a, int b);

/* ---------------- Boundary Signal declarations ---------------- */

struct BoundaryPairSignal {
    int ra = -1;
    int rb = -1;
    double score = INF_D;
    vector<int> AtoB;
    vector<int> BtoA;
};

static vector<BoundaryPairSignal> build_boundary_signals(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int topK
);

static vector<int> route_positions_priority_first(
    const vector<int> &route,
    const vector<int> &priority_nodes,
    const Compressed &CG
);

static vector<pair<int, int>> boundary_prioritized_route_pairs(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int fallback_R
);

static bool euclidean_swapstar_once(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!metric_is_euclidean()) return false;
    if (!cfg.euclidean_swapstar) return false;

    const Compressed &CG = *ev.CG;
    int depot = find_depot_idx(CG);

    SolutionState best_state = state;
    double best_obj = state.objective;
    bool improved = false;

    int attempted = 0;
    int R = (int)state.routes.size();

    vector<pair<int, int>> route_pairs =
        boundary_prioritized_route_pairs(state, ev, pm, R);

    if (cfg.boundary_prioritized_verbose &&
        cfg.use_boundary_prioritized_education) {
        cerr << "[BoundaryEdu-SWAP*] pairs=" << route_pairs.size()
            << " top=" << cfg.boundary_prioritized_top_pairs
            << "\n";
    }

    for (int pair_idx = 0; pair_idx < (int)route_pairs.size(); ++pair_idx) {
        auto [r1, r2] = route_pairs[pair_idx];

        bool is_boundary_priority_pair =
            cfg.use_boundary_prioritized_education &&
            pair_idx < cfg.boundary_prioritized_top_pairs;
        const vector<int> &A0 = state.routes[r1];
        const vector<int> &B0 = state.routes[r2];

        if ((int)A0.size() <= 2 || (int)B0.size() <= 2) continue;

        // Build boundary customer priority only for the first top boundary pairs.
        vector<int> A_priority_nodes;
        vector<int> B_priority_nodes;

        if (is_boundary_priority_pair) {
            vector<BoundaryPairSignal> signals = build_boundary_signals(
                state,
                ev,
                pm,
                cfg.boundary_prioritized_top_pairs
            );

            for (const auto &sig : signals) {
                if (sig.ra == r1 && sig.rb == r2) {
                    A_priority_nodes = sig.AtoB;
                    B_priority_nodes = sig.BtoA;
                    break;
                }
                if (sig.ra == r2 && sig.rb == r1) {
                    A_priority_nodes = sig.BtoA;
                    B_priority_nodes = sig.AtoB;
                    break;
                }
            }
        }

        vector<int> A_positions = route_positions_priority_first(
            A0,
            A_priority_nodes,
            CG
        );

        vector<int> B_positions = route_positions_priority_first(
            B0,
            B_priority_nodes,
            CG
        );

        for (int i : A_positions) {
            int a = A0[i];

            if (a < 0 || a >= (int)CG.nodes.size()) continue;
            if (CG.nodes[a].type != 2) continue;

            for (int j : B_positions) {
                int b = B0[j];

                if (b < 0 || b >= (int)CG.nodes.size()) continue;
                if (CG.nodes[b].type != 2) continue;

                bool candidate_related =
                    is_candidate_neighbor(a, b) ||
                    is_candidate_neighbor(b, a);

                // Boundary-priority pairs are already selected by structural diagnosis,
                // so do not over-prune them using candidate lists.
                bool a_is_priority = false;
                bool b_is_priority = false;

                if (is_boundary_priority_pair) {
                    a_is_priority = find(A_priority_nodes.begin(), A_priority_nodes.end(), a) != A_priority_nodes.end();
                    b_is_priority = find(B_priority_nodes.begin(), B_priority_nodes.end(), b) != B_priority_nodes.end();
                }

                // Only bypass candidate filtering for exact boundary-customer pairs.
                // Do not globally relax the whole route pair.
                if (cfg.use_candidate_lists &&
                    !candidate_related &&
                    !(a_is_priority || b_is_priority)) {
                    continue;
                }

                // Count scan budget only after cheap filters pass.
                if (++attempted > cfg.euclidean_swapstar_scan_cap) {
                    goto END_SEARCH;
                }

                vector<int> A_base = A0;
                vector<int> B_base = B0;

                if (i <= 0 || i >= (int)A_base.size()) continue;
                if (j <= 0 || j >= (int)B_base.size()) continue;
                if (A_base[i] != a || B_base[j] != b) continue;

                // Remove a from route A, b from route B.
                A_base.erase(A_base.begin() + i);
                B_base.erase(B_base.begin() + j);

                normalize_route(A_base, depot);
                normalize_route(B_base, depot);

                double best_pair_cost = INF_D;
                vector<int> best_A;
                vector<int> best_B;

                // Insert b into A at best position, and a into B at best position.
                for (int posA = 1; posA < (int)A_base.size(); ++posA) {
                    vector<int> A_cand = A_base;
                    A_cand.insert(A_cand.begin() + posA, b);

                    enforce_trip_separators(A_cand, CG, depot);

                    if (!trips_feasible_for_route(A_cand, CG, depot)) continue;

                    double costA = route_exact_cost(A_cand, ev);
                    if (!isfinite(costA) || costA >= INF_D / 2) continue;

                    for (int posB = 1; posB < (int)B_base.size(); ++posB) {
                        vector<int> B_cand = B_base;
                        B_cand.insert(B_cand.begin() + posB, a);

                        enforce_trip_separators(B_cand, CG, depot);

                        if (!trips_feasible_for_route(B_cand, CG, depot)) continue;

                        double costB = route_exact_cost(B_cand, ev);
                        if (!isfinite(costB) || costB >= INF_D / 2) continue;

                        double pair_cost = costA + costB;

                        if (pair_cost + 1e-9 < best_pair_cost) {
                            best_pair_cost = pair_cost;
                            best_A = std::move(A_cand);
                            best_B = std::move(B_cand);
                        }
                    }
                }

                if (best_A.empty() || best_B.empty()) continue;

                SolutionState cand = state;
                cand.routes[r1] = best_A;
                cand.routes[r2] = best_B;

                recompute_state_metrics_and_loads(cand, ev);

                if (!solution_fully_feasible(cand, CG)) continue;

                if (cand.objective + 1e-9 < best_obj) {
                    best_obj = cand.objective;
                    best_state = std::move(cand);
                    improved = true;
                }
            }
        }
    }

END_SEARCH:

    if (improved) {
        state = std::move(best_state);
        return true;
    }

    return false;
}

static void euclidean_swapstar_descent(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!metric_is_euclidean()) return;
    if (!cfg.euclidean_swapstar) return;

    double start_obj = state.objective;
    int accepted = 0;

    int rounds = max(0, cfg.euclidean_swapstar_rounds);

    for (int it = 0; it < rounds; ++it) {
        bool ok = euclidean_swapstar_once(state, ev, pm);

        if (!ok) break;

        accepted++;

        if (euclidean_cuts_enabled()) {
            euclidean_branch_polish_solution(state, ev, pm);
        }

        recompute_state_metrics_and_loads(state, ev);
    }

    if (accepted > 0) {
        cerr << "[SWAP*] start=" << start_obj
            << " end=" << state.objective
            << " gain=" << (start_obj - state.objective)
            << " accepted=" << accepted
            << "\n";
    }
}

static bool euclidean_two_opt_star_once(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    (void)pm;

    if (!metric_is_euclidean()) return false;
    if (!cfg.euclidean_two_opt_star) return false;

    const Compressed &CG = *ev.CG;
    int depot = find_depot_idx(CG);

    SolutionState best_state = state;
    double best_obj = state.objective;
    bool improved = false;

    int attempted = 0;
    int R = (int)state.routes.size();

    for (int r1 = 0; r1 < R; ++r1) {
        for (int r2 = r1 + 1; r2 < R; ++r2) {
            const vector<int> &A0 = state.routes[r1];
            const vector<int> &B0 = state.routes[r2];

            if ((int)A0.size() <= 3 || (int)B0.size() <= 3) continue;

            double old_pair_cost =
                route_exact_cost(A0, ev) +
                route_exact_cost(B0, ev);

            // Cut after i in A and after j in B.
            // A_new = A prefix + B tail
            // B_new = B prefix + A tail
            for (int i = 1; i + 1 < (int)A0.size(); ++i) {
                int a = A0[i];
                int a_next = A0[i + 1];

                if (a == depot || a_next == depot) continue;
                if (a < 0 || a >= (int)CG.nodes.size()) continue;
                if (a_next < 0 || a_next >= (int)CG.nodes.size()) continue;
                if (CG.nodes[a].type != 2 || CG.nodes[a_next].type != 2) continue;

                for (int j = 1; j + 1 < (int)B0.size(); ++j) {
                    int b = B0[j];
                    int b_next = B0[j + 1];

                    if (++attempted > cfg.euclidean_two_opt_star_scan_cap) {
                        goto END_SEARCH;
                    }

                    if (b == depot || b_next == depot) continue;
                    if (b < 0 || b >= (int)CG.nodes.size()) continue;
                    if (b_next < 0 || b_next >= (int)CG.nodes.size()) continue;
                    if (CG.nodes[b].type != 2 || CG.nodes[b_next].type != 2) continue;

                    // Granular filter: only try locally plausible reconnects.
                    if (cfg.use_candidate_lists) {
                        bool ok =
                            is_candidate_neighbor(a, b_next) ||
                            is_candidate_neighbor(b_next, a) ||
                            is_candidate_neighbor(b, a_next) ||
                            is_candidate_neighbor(a_next, b);

                        if (!ok) continue;
                    }

                    vector<int> A_new;
                    vector<int> B_new;

                    A_new.reserve(A0.size() + B0.size());
                    B_new.reserve(A0.size() + B0.size());

                    // A prefix: A0[0..i]
                    for (int p = 0; p <= i; ++p) {
                        A_new.push_back(A0[p]);
                    }

                    // B tail: B0[j+1..end]
                    for (int p = j + 1; p < (int)B0.size(); ++p) {
                        A_new.push_back(B0[p]);
                    }

                    // B prefix: B0[0..j]
                    for (int p = 0; p <= j; ++p) {
                        B_new.push_back(B0[p]);
                    }

                    // A tail: A0[i+1..end]
                    for (int p = i + 1; p < (int)A0.size(); ++p) {
                        B_new.push_back(A0[p]);
                    }

                    normalize_route(A_new, depot);
                    normalize_route(B_new, depot);

                    enforce_trip_separators(A_new, CG, depot);
                    enforce_trip_separators(B_new, CG, depot);

                    if (!trips_feasible_for_route(A_new, CG, depot)) continue;
                    if (!trips_feasible_for_route(B_new, CG, depot)) continue;

                    double new_pair_cost =
                        route_exact_cost(A_new, ev) +
                        route_exact_cost(B_new, ev);

                    if (new_pair_cost + 1e-9 >= old_pair_cost) continue;

                    SolutionState cand = state;
                    cand.routes[r1] = std::move(A_new);
                    cand.routes[r2] = std::move(B_new);

                    recompute_state_metrics_and_loads(cand, ev);

                    if (!solution_fully_feasible(cand, CG)) continue;

                    if (cand.objective + 1e-9 < best_obj) {
                        best_obj = cand.objective;
                        best_state = std::move(cand);
                        improved = true;
                    }
                }
            }
        }
    }

END_SEARCH:

    if (improved) {
        state = std::move(best_state);
        recompute_state_metrics_and_loads(state, ev);
        return true;
    }

    return false;
}

static void euclidean_two_opt_star_descent(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!metric_is_euclidean()) return;
    if (!cfg.euclidean_two_opt_star) return;

    double start_obj = state.objective;
    int accepted = 0;

    int rounds = max(0, cfg.euclidean_two_opt_star_rounds);

    for (int it = 0; it < rounds; ++it) {
        bool ok = euclidean_two_opt_star_once(state, ev, pm);

        if (!ok) break;

        accepted++;

        if (euclidean_cuts_enabled()) {
            euclidean_branch_polish_solution(state, ev, pm);
        }

        recompute_state_metrics_and_loads(state, ev);
    }

    if (accepted > 0) {
        cerr << "[2-opt*] start=" << start_obj
            << " end=" << state.objective
            << " gain=" << (start_obj - state.objective)
            << " accepted=" << accepted
            << "\n";
    }
}

/* --------------- HGS-lite ---------------- */

static vector<int> solution_to_giant_tour(
    const SolutionState &s,
    const Compressed &CG
) {
    vector<int> tour;
    vector<char> seen(CG.nodes.size(), 0);

    for (const auto &route : s.routes) {
        for (int nid : route) {
            if (nid >= 0 &&
                nid < (int)CG.nodes.size() &&
                CG.nodes[nid].type == 2 &&
                !seen[nid]) {
                seen[nid] = 1;
                tour.push_back(nid);
            }
        }
    }

    return tour;
}

static vector<int> all_customers_as_tour(
    const Compressed &CG
) {
    vector<int> tour;

    for (const auto &n : CG.nodes) {
        if (n.type == 2) {
            tour.push_back(n.id);
        }
    }

    return tour;
}

static SolutionState split_giant_tour_to_solution(
    const vector<int> &tour,
    const Compressed &CG,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const auto split_t0 = Clock::now();
    profile.hgs_split_calls.fetch_add(1, memory_order_relaxed);

    const int depot = find_depot_idx(CG);
    const int n = (int)tour.size();
    const int K = cfg.num_trucks;
    const double INF = INF_D;

    SolutionState empty(cfg.num_trucks, (int)CG.nodes.size());
    empty.routes.assign(cfg.num_trucks, vector<int>{depot, depot});
    auto finish_timing = [&]() {
        profile.hgs_split_time_us.fetch_add(
            chrono::duration_cast<chrono::microseconds>(Clock::now() - split_t0).count(),
            memory_order_relaxed);
    };
    if (n == 0) {
        recompute_state_metrics_and_loads(empty, ev);
        finish_timing();
        return empty;
    }

    const bool fast_cvrp_split =
        cfg.objective_mode == "distance" &&
        !cfg.use_time_window &&
        !cfg.allow_multi_trip;

    // V29: pure-CVRP Split stores only capacity-feasible predecessor arcs.
    // With capacity 100 and typical customer demands, only a small contiguous
    // window of i values can precede each end j. Iterating every i=0..j in
    // every fleet layer wastes most of the O(K n^2) DP on INF entries.
    vector<vector<pair<int,double>>> feasible_pred;
    vector<vector<double>> seg_cost;

    if (fast_cvrp_split) {
        feasible_pred.assign(n + 1, {});
        for (int i = 0; i < n; ++i) {
            double load = 0.0;
            double cost = INF;
            int prev = depot;
            for (int j = i; j < n; ++j) {
                const int node = tour[j];
                if (node < 0 || node >= (int)CG.nodes.size()) break;
                if (CG.nodes[node].type != 2) break;
                load += CG.nodes[node].garbage_amount;
                if (load > cfg.truck_capacity + 1e-9) break;

                const double prev_to_node = fast_pair_dist(prev, node, &pm);
                const double node_to_depot = fast_pair_dist(node, depot, &pm);
                if (!isfinite(prev_to_node) || !isfinite(node_to_depot)) break;
                if (j == i) {
                    const double depot_to_node = fast_pair_dist(depot, node, &pm);
                    if (!isfinite(depot_to_node)) break;
                    cost = depot_to_node + node_to_depot;
                } else {
                    const double prev_to_depot = fast_pair_dist(prev, depot, &pm);
                    if (!isfinite(prev_to_depot) || !isfinite(cost)) break;
                    cost += prev_to_node + node_to_depot - prev_to_depot;
                }
                feasible_pred[j + 1].push_back({i, cost});
                profile.hgs_split_fast_segments.fetch_add(1, memory_order_relaxed);
                prev = node;
            }
        }
    } else {
        seg_cost.assign(n + 1, vector<double>(n + 1, INF));
        for (int i = 0; i < n; ++i) {
            double load = 0.0;
            vector<int> route;
            route.reserve(n - i + 2);
            route.push_back(depot);
            for (int j = i; j < n; ++j) {
                const int node = tour[j];
                if (node < 0 || node >= (int)CG.nodes.size()) break;
                if (CG.nodes[node].type != 2) break;
                load += CG.nodes[node].garbage_amount;
                if (load > cfg.truck_capacity + 1e-9) break;
                route.push_back(node);
                vector<int> closed = route;
                closed.push_back(depot);
                if (cfg.use_time_window && cfg.tw_strict_insertion &&
                    !cfg.tw_allow_soft_intermediate &&
                    !route_hard_tw_feasible(closed, ev, pm)) continue;
                seg_cost[i][j + 1] = route_exact_cost(closed, ev);
                profile.hgs_split_exact_segments.fetch_add(1, memory_order_relaxed);
            }
        }
    }

    vector<vector<double>> dp(K + 1, vector<double>(n + 1, INF));
    vector<vector<int>> parent(K + 1, vector<int>(n + 1, -1));
    dp[0][0] = 0.0;

    for (int k = 1; k <= K; ++k) {
        for (int j = 1; j <= n; ++j) {
            double best = INF;
            int best_i = -1;
            if (fast_cvrp_split) {
                for (const auto &arc : feasible_pred[j]) {
                    const int i = arc.first;
                    if (dp[k - 1][i] >= INF / 2) continue;
                    const double cand = dp[k - 1][i] + arc.second;
                    if (cand + 1e-9 < best) { best = cand; best_i = i; }
                }
            } else {
                for (int i = 0; i < j; ++i) {
                    if (dp[k - 1][i] >= INF / 2 || seg_cost[i][j] >= INF / 2) continue;
                    const double cand = dp[k - 1][i] + seg_cost[i][j];
                    if (cand + 1e-9 < best) { best = cand; best_i = i; }
                }
            }
            dp[k][j] = best;
            parent[k][j] = best_i;
        }
    }

    int best_k = -1;
    double best_obj = INF;
    for (int k = 1; k <= K; ++k) {
        if (dp[k][n] + 1e-9 < best_obj) {
            best_obj = dp[k][n];
            best_k = k;
        }
    }
    if (best_k < 0 || best_obj >= INF / 2) {
        recompute_state_metrics_and_loads(empty, ev);
        finish_timing();
        return empty;
    }

    vector<vector<int>> recovered;
    int cur = n, k = best_k;
    while (k > 0 && cur > 0) {
        const int p = parent[k][cur];
        if (p < 0 || p >= cur) {
            recompute_state_metrics_and_loads(empty, ev);
            finish_timing();
            return empty;
        }
        vector<int> route;
        route.reserve(cur - p + 2);
        route.push_back(depot);
        for (int idx = p; idx < cur; ++idx) route.push_back(tour[idx]);
        route.push_back(depot);
        recovered.push_back(std::move(route));
        cur = p;
        --k;
    }
    if (cur != 0) {
        recompute_state_metrics_and_loads(empty, ev);
        finish_timing();
        return empty;
    }
    reverse(recovered.begin(), recovered.end());

    SolutionState out(cfg.num_trucks, (int)CG.nodes.size());
    out.routes.assign(cfg.num_trucks, vector<int>{depot, depot});
    for (int r = 0; r < (int)recovered.size() && r < cfg.num_trucks; ++r) {
        out.routes[r] = std::move(recovered[r]);
    }
    recompute_state_metrics_and_loads(out, ev);
    finish_timing();
    return out;
}

static vector<int> euclidean_sweep_tour(
    const Compressed &CG,
    double offset
) {
    int depot = find_depot_idx(CG);
    const NodeC &D = CG.nodes[depot];

    vector<pair<double, int>> arr;

    for (const auto &n : CG.nodes) {
        if (n.type != 2) continue;

        double ang = atan2(n.lat - D.lat, n.lon - D.lon) + offset;

        while (ang < 0) ang += 2.0 * M_PI;
        while (ang >= 2.0 * M_PI) ang -= 2.0 * M_PI;

        arr.push_back({ang, n.id});
    }

    sort(arr.begin(), arr.end());

    vector<int> tour;
    tour.reserve(arr.size());

    for (auto &p : arr) {
        tour.push_back(p.second);
    }

    return tour;
}

static vector<int> order_crossover_tour(
    const vector<int> &a,
    const vector<int> &b,
    mt19937 &rng
) {
    int n = (int)a.size();
    if (n <= 2) return a;

    uniform_int_distribution<int> dist(0, n - 1);
    int l = dist(rng);
    int r = dist(rng);

    if (l > r) swap(l, r);

    vector<int> child(n, -1);
    unordered_set<int> used;

    for (int i = l; i <= r; ++i) {
        child[i] = a[i];
        used.insert(a[i]);
    }

    int pos = (r + 1) % n;

    for (int t = 0; t < n; ++t) {
        int gene = b[(r + 1 + t) % n];

        if (used.count(gene)) continue;

        child[pos] = gene;
        used.insert(gene);

        pos = (pos + 1) % n;
    }

    return child;
}

static void mutate_tour_swap(
    vector<int> &tour,
    mt19937 &rng
) {
    int n = (int)tour.size();
    if (n < 2) return;

    uniform_int_distribution<int> dist(0, n - 1);
    int i = dist(rng);
    int j = dist(rng);

    if (i != j) {
        swap(tour[i], tour[j]);
    }
}

static SolutionState hgs_lite_euclidean(
    const SolutionState &seed_state,
    const Compressed &CG,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    unsigned seed
) {
    if (!metric_is_euclidean()) return seed_state;
    if (!cfg.use_hgs_lite) return seed_state;

    mt19937 rng(seed);

    vector<int> base_tour = solution_to_giant_tour(seed_state, CG);

    if (base_tour.empty()) {
        base_tour = all_customers_as_tour(CG);
    }

    struct Individual {
        vector<int> tour;
        SolutionState state;
        double obj = INF_D;

        // Old cheap tie-breaker.
        double diversity_key = 0.0;

        // Real HGS-like diversity.
        double diversity_score = 0.0;
        double biased_fitness = INF_D;
    };

    auto compute_diversity_key = [&](const vector<int> &tour) {
        // Cheap diversity signal: weighted sum of first few genes.
        double v = 0.0;
        int lim = min((int)tour.size(), 12);

        for (int i = 0; i < lim; ++i) {
            v += (double)(i + 1) * (double)(tour[i] + 1);
        }

        return v;
    };

    auto edge_key_undirected = [&](int a, int b) -> uint64_t {
        uint32_t x = (uint32_t)min(a, b);
        uint32_t y = (uint32_t)max(a, b);
        return (((uint64_t)x) << 32) | (uint64_t)y;
    };

    auto route_edge_set = [&](const SolutionState &s) {
        unordered_set<uint64_t> edges;

        for (const auto &r : s.routes) {
            for (int i = 0; i + 1 < (int)r.size(); ++i) {
                int a = r[i];
                int b = r[i + 1];

                if (a == b) continue;
                if (a < 0 || b < 0) continue;

                edges.insert(edge_key_undirected(a, b));
            }
        }

        return edges;
    };

    auto route_edge_distance = [&](const SolutionState &a, const SolutionState &b) -> double {
        unordered_set<uint64_t> A = route_edge_set(a);
        unordered_set<uint64_t> B = route_edge_set(b);

        if (A.empty() && B.empty()) return 0.0;

        int shared = 0;

        if (A.size() < B.size()) {
            for (uint64_t e : A) {
                if (B.count(e)) shared++;
            }
        }
        else {
            for (uint64_t e : B) {
                if (A.count(e)) shared++;
            }
        }

        int denom = max((int)A.size(), (int)B.size());
        if (denom <= 0) return 0.0;

        return 1.0 - (double)shared / (double)denom;
    };

    int accepted_children = 0;

    auto make_individual = [&](vector<int> tour, bool heavy_educate) {
        Individual ind;
        ind.tour = std::move(tour);
        if (solver_should_stop()) {
            ind.state = seed_state;
            ind.obj = INF_D;
            return ind;
        }

        ind.state = split_giant_tour_to_solution(ind.tour, CG, ev, pm);

        if (cfg.hgs_educate_children) {
            if (euclidean_cuts_enabled()) {
                int old_passes = cfg.euclidean_uncross_passes;
                cfg.euclidean_uncross_passes = min(old_passes, cfg.hgs_child_branch_passes);

                euclidean_branch_polish_solution(ind.state, ev, pm);

                cfg.euclidean_uncross_passes = old_passes;
            }

            if (cfg.euclidean_swapstar) {
                int old_rounds = cfg.euclidean_swapstar_rounds;
                int old_scan_cap = cfg.euclidean_swapstar_scan_cap;

                cfg.euclidean_swapstar_rounds = heavy_educate ? min(old_rounds, 4) : min(old_rounds, 1);
                cfg.euclidean_swapstar_scan_cap = min(old_scan_cap, 25000);

                euclidean_swapstar_descent(ind.state, ev, pm);

                cfg.euclidean_swapstar_rounds = old_rounds;
                cfg.euclidean_swapstar_scan_cap = old_scan_cap;
            }

            if (cfg.euclidean_two_opt_star) {
                int old_rounds = cfg.euclidean_two_opt_star_rounds;
                int old_scan_cap = cfg.euclidean_two_opt_star_scan_cap;

                cfg.euclidean_two_opt_star_rounds =
                    heavy_educate ? min(old_rounds, 4) : min(old_rounds, 1);

                cfg.euclidean_two_opt_star_scan_cap =
                    min(old_scan_cap, 60000);

                euclidean_two_opt_star_descent(ind.state, ev, pm);

                cfg.euclidean_two_opt_star_rounds = old_rounds;
                cfg.euclidean_two_opt_star_scan_cap = old_scan_cap;

                recompute_state_metrics_and_loads(ind.state, ev);
            }

            // Heavy exact inter-route polish only sometimes.
            if (heavy_educate && cfg.euclidean_deep_interroute) {
                int old_rounds = cfg.euclidean_deep_interroute_rounds;
                cfg.euclidean_deep_interroute_rounds = min(old_rounds, 4);

                euclidean_deep_interroute_descent(ind.state, ev, pm);

                cfg.euclidean_deep_interroute_rounds = old_rounds;
            }
        }

        recompute_state_metrics_and_loads(ind.state, ev);

        ind.obj = ind.state.objective;
        ind.tour = solution_to_giant_tour(ind.state, CG);

        if ((int)ind.tour.size() != (int)base_tour.size()) {
            // Lost/missing customer: make it unattractive.
            ind.obj = INF_D;
        }

        ind.diversity_key = compute_diversity_key(ind.tour);

        return ind;
    };

    auto feasible_individual = [&](const Individual &ind) {
        if (!isfinite(ind.obj) || ind.obj >= INF_D / 2) return false;
        if ((int)ind.tour.size() != (int)base_tour.size()) return false;
        return solution_fully_feasible(ind.state, CG);
    };

    vector<Individual> pop;
    pop.reserve(cfg.hgs_population_size * 2 + 10);

    // ------------------------------------------------------------
    // Seed population:
    // 1. current solution tour
    // 2. sweep tours
    // 3. shuffled tours
    // ------------------------------------------------------------
    {
        Individual base = make_individual(base_tour, true);

        if (feasible_individual(base)) {
            pop.push_back(std::move(base));
        }
    }

    int sweep_count = min(10, max(2, cfg.hgs_population_size / 2));

    for (int sidx = 0; sidx < sweep_count && !solver_should_stop(); ++sidx) {
        double off = (2.0 * M_PI * sidx) / max(1, sweep_count);
        vector<int> t = euclidean_sweep_tour(CG, off);

        if (!t.empty()) {
            Individual ind = make_individual(t, sidx % 3 == 0);

            if (feasible_individual(ind)) {
                pop.push_back(std::move(ind));
            }
        }
    }

    while ((int)pop.size() < cfg.hgs_population_size && !solver_should_stop()) {
        vector<int> t = base_tour;
        shuffle(t.begin(), t.end(), rng);

        Individual ind = make_individual(t, false);

        if (feasible_individual(ind)) {
            pop.push_back(std::move(ind));
        }
        else {
            // Avoid infinite loop on bad cases.
            if ((int)pop.size() == 0) {
                return seed_state;
            }

            if ((int)pop.size() >= max(4, cfg.hgs_population_size / 3)) {
                break;
            }
        }
    }

    auto assign_biased_fitness = [&]() {
    int P = (int)pop.size();
    if (P == 0) return;

    for (auto &ind : pop) {
        ind.diversity_score = 0.0;
        ind.biased_fitness = ind.obj;
    }

    if (!cfg.hgs_use_biased_fitness || P == 1) {
        for (auto &ind : pop) {
            ind.biased_fitness = ind.obj;
        }
        return;
    }

    // ------------------------------------------------------------
    // Diversity score = average distance to closest neighbors.
    // Higher is more diverse.
    // ------------------------------------------------------------
    int neigh = max(1, min(cfg.hgs_diversity_neighbors, P - 1));

    for (int i = 0; i < P; ++i) {
        vector<double> dists;
        dists.reserve(P - 1);

        for (int j = 0; j < P; ++j) {
            if (i == j) continue;
            dists.push_back(route_edge_distance(pop[i].state, pop[j].state));
        }

        sort(dists.begin(), dists.end());

        double avg = 0.0;
        int cnt = min(neigh, (int)dists.size());

        for (int k = 0; k < cnt; ++k) {
            avg += dists[k];
        }

        if (cnt > 0) avg /= (double)cnt;

        pop[i].diversity_score = avg;
    }

    // ------------------------------------------------------------
    // Rank objective ascending.
    // ------------------------------------------------------------
    vector<int> by_obj(P);
    iota(by_obj.begin(), by_obj.end(), 0);

    sort(by_obj.begin(), by_obj.end(), [&](int a, int b) {
        if (fabs(pop[a].obj - pop[b].obj) > 1e-9) {
            return pop[a].obj < pop[b].obj;
        }
        return pop[a].diversity_key < pop[b].diversity_key;
    });

    vector<int> obj_rank(P, 0);
    for (int r = 0; r < P; ++r) {
        obj_rank[by_obj[r]] = r;
    }

    // ------------------------------------------------------------
    // Rank diversity descending.
    // Most diverse gets best diversity rank.
    // ------------------------------------------------------------
    vector<int> by_div(P);
    iota(by_div.begin(), by_div.end(), 0);

    sort(by_div.begin(), by_div.end(), [&](int a, int b) {
        if (fabs(pop[a].diversity_score - pop[b].diversity_score) > 1e-12) {
            return pop[a].diversity_score > pop[b].diversity_score;
        }
        return pop[a].obj < pop[b].obj;
    });

    vector<int> div_rank(P, 0);
    for (int r = 0; r < P; ++r) {
        div_rank[by_div[r]] = r;
    }

    for (int i = 0; i < P; ++i) {
        pop[i].biased_fitness =
            (double)obj_rank[i] +
            cfg.hgs_diversity_weight * (double)div_rank[i];
    }
};

auto sort_pop = [&]() {
    assign_biased_fitness();

    sort(pop.begin(), pop.end(), [](const Individual &x, const Individual &y) {
        if (fabs(x.biased_fitness - y.biased_fitness) > 1e-9) {
            return x.biased_fitness < y.biased_fitness;
        }
        if (fabs(x.obj - y.obj) > 1e-9) {
            return x.obj < y.obj;
        }
        return x.diversity_key < y.diversity_key;
    });
};

auto prune_pop = [&]() {
    sort_pop();

    vector<Individual> kept;
    kept.reserve(cfg.hgs_population_size);

    for (auto &ind : pop) {
        bool too_same = false;

        for (const auto &k : kept) {
            double edge_dist = route_edge_distance(ind.state, k.state);

            // Always protect very top objective-quality solutions.
            // But reject near-identical route structures later.
            if ((int)kept.size() >= cfg.hgs_elite_keep &&
                edge_dist < cfg.hgs_duplicate_edge_distance) {
                too_same = true;
                break;
            }
        }

        if (!too_same) {
            kept.push_back(std::move(ind));
        }

        if ((int)kept.size() >= cfg.hgs_population_size) {
            break;
        }
    }

    // If diversity filtering was too strict, refill by biased order.
    if ((int)kept.size() < min(cfg.hgs_population_size, (int)pop.size())) {
        for (auto &ind : pop) {
            if ((int)kept.size() >= cfg.hgs_population_size) break;

            bool already = false;
            for (const auto &k : kept) {
                if (fabs(ind.obj - k.obj) < 1e-9 &&
                    fabs(ind.diversity_key - k.diversity_key) < 1e-9) {
                    already = true;
                    break;
                }
            }

            if (!already) {
                kept.push_back(std::move(ind));
            }
        }
    }

    pop.swap(kept);
};

    prune_pop();

    if (pop.empty()) {
        return seed_state;
    }

    // ------------------------------------------------------------
    // Evolution loop.
    // ------------------------------------------------------------
    for (int gen = 0; gen < cfg.hgs_generations && !solver_should_stop(); ++gen) {
        int elite = min(cfg.hgs_elite_keep, (int)pop.size());

        if (elite <= 0) break;

        uniform_int_distribution<int> elite_dist(0, elite - 1);
        uniform_int_distribution<int> pop_dist(0, (int)pop.size() - 1);

        int p1 = elite_dist(rng);

        // Tournament for p2: choose better biased-fitness among two random candidates.
        // This keeps quality pressure while still allowing non-elite diversity.
        int cand_a = pop_dist(rng);
        int cand_b = pop_dist(rng);

        int p2 = cand_a;
        if (cand_b != cand_a &&
            pop[cand_b].biased_fitness < pop[cand_a].biased_fitness) {
            p2 = cand_b;
        }

        if (p1 == p2 && (int)pop.size() > 1) {
            p2 = (p2 + 1) % (int)pop.size();
        }

        vector<int> child_tour;

        if (cfg.hgs_use_order_crossover) {
            child_tour = order_crossover_tour(pop[p1].tour, pop[p2].tour, rng);
        }
        else {
            child_tour = pop[p1].tour;
        }

        uniform_real_distribution<double> real01(0.0, 1.0);

        if (real01(rng) < cfg.hgs_mutation_rate) {
            mutate_tour_swap(child_tour, rng);
        }

        // Small extra mutation: reverse a small segment sometimes.
        if (real01(rng) < 0.08 && child_tour.size() >= 6) {
            uniform_int_distribution<int> d(0, (int)child_tour.size() - 1);
            int a = d(rng);
            int b = d(rng);

            if (a > b) swap(a, b);

            if (b - a >= 2) {
                reverse(child_tour.begin() + a, child_tour.begin() + b + 1);
            }
        }

        bool heavy_educate =
            (accepted_children % max(1, cfg.hgs_deep_every) == 0);

        Individual child = make_individual(child_tour, heavy_educate);

        if (feasible_individual(child)) {
            pop.push_back(std::move(child));
            accepted_children++;

            if ((int)pop.size() > cfg.hgs_population_size + 4) {
                prune_pop();
            }
        }
    }

    prune_pop();

    if (pop.empty()) {
        return seed_state;
    }

    cerr << "[HGS-lite] best=" << pop.front().obj
        << " pop=" << pop.size()
        << " generations=" << cfg.hgs_generations
        << " accepted_children=" << accepted_children
        << " best_div=" << pop.front().diversity_score
        << " best_biased=" << pop.front().biased_fitness
        << "\n";

    return pop.front().state;
}

static vector<int> get_best_routes_for_node(
    const vector<vector<int>>& routes,
    PairwiseManager &pm,
    int node,
    int topK
);

static bool insert_customer_best_place_fast(
    SolutionState &state,
    int node,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    RepairWorkStats *stats = nullptr
);

static void local_polish_solution(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
);

static void relocate_route_local_best(
    vector<int> &route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const Compressed &CG,
    int depot
);

static void or_opt_k_route(
    vector<int> &route,
    int k,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const Compressed &CG,
    int depot
);

static void two_opt_multi_trip_route(
    vector<int> &route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const Compressed &CG,
    int depot
);

static int depot_of(const ObjectiveEvaluator &ev) {
    return find_depot_idx(*ev.CG);
}

static bool update_global_best_checked(
    const SolutionState &s,
    const Compressed &CG,
    PairwiseManager &pm
) {
    if (s.routes.empty()) return false;
    if (!solution_hard_feasible(s, CG, pm)) return false;

    // V5 evidence invariant: deadline is checked *after* independent hard
    // feasibility validation, so the timestamp is the completion time of the
    // candidate. Late improvements stay visible in logs but cannot contaminate
    // objective-at-budget or the final deadline snapshot.
    const double completed_at = solver_elapsed_seconds();
    if (solver_governor_started && cfg.hard_time_limit_s > 0.0 &&
        completed_at > cfg.hard_time_limit_s + 1e-9) {
        profile.late_feasible_improvements_rejected.fetch_add(1, memory_order_relaxed);
        safe_log_line(
            "[DeadlineCensor] time_s=", setprecision(15), completed_at,
            " objective=", setprecision(15), s.objective,
            " event=late_feasible_improvement_rejected"
        );
        return false;
    }

    if (tls_defer_global_publish) return false;

    if (update_global_best(s)) {
        safe_log_line(
            "[EvidenceGlobal] time_s=", setprecision(15), completed_at,
            " objective=", setprecision(15), s.objective,
            " event=global_feasible_improvement"
        );
        return true;
    }
    return false;
}

// V61 anytime checkpoint: stage workers deliberately suppress peer migration while
// evaluating private basins, but a hard-feasible candidate that has *already*
// completed validation before T is still a legitimate anytime incumbent.  This
// helper publishes only that validated snapshot; sibling stage workers remain
// migration-disabled because tls_defer_global_publish stays true in their threads.
static bool checkpoint_validated_global_best(
    const SolutionState &s,
    const char *event_name
) {
    if (s.routes.empty() || !state_basic_feasible_for_global_best(s)) return false;

    // The caller invokes this immediately after solution_hard_feasible() returns
    // true, so this timestamp is the completion time of that validation without
    // redundantly re-running the expensive validator.
    const double completed_at = solver_elapsed_seconds();
    if (solver_governor_started && cfg.hard_time_limit_s > 0.0 &&
        completed_at > cfg.hard_time_limit_s + 1e-9) {
        profile.late_feasible_improvements_rejected.fetch_add(1, memory_order_relaxed);
        safe_log_line(
            "[DeadlineCensorCheckpoint] time_s=", setprecision(15), completed_at,
            " objective=", setprecision(15), s.objective,
            " event=late_validated_checkpoint_rejected"
        );
        return false;
    }

    if (update_global_best(s)) {
        safe_log_line(
            "[EvidenceCheckpoint] time_s=", setprecision(15), completed_at,
            " objective=", setprecision(15), s.objective,
            " event=", event_name
        );
        return true;
    }
    return false;
}

static void euclidean_branch_polish_solution(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
);

static void euclidean_deep_interroute_descent(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
);

/* ---------------- Candidate neighbor lists ---------------- */

static vector<int> customer_nodes_global;
static vector<vector<int>> candidate_neighbors; // indexed by graph node id

static void build_candidate_lists(const Compressed &CG, PairwiseManager &pm) {
    customer_nodes_global.clear();

    for (const auto &n : CG.nodes) {
        if (n.type == 2) {
            customer_nodes_global.push_back(n.id);
        }
    }

    candidate_neighbors.assign(CG.nodes.size(), {});

    if (!cfg.use_candidate_lists || cfg.candidate_k <= 0) {
        return;
    }

    for (int a : customer_nodes_global) {
        vector<pair<double, int>> scored;
        scored.reserve(customer_nodes_global.size());

        for (int b : customer_nodes_global) {
            if (a == b) continue;

            double d;

            if (metric_is_symmetric()) {
                d = fast_pair_dist(a, b, &pm);
            } else {
                double d_ab = fast_pair_dist(a, b, &pm);
                double d_ba = fast_pair_dist(b, a, &pm);

                if (isfinite(d_ab) && isfinite(d_ba)) d = min(d_ab, d_ba);
                else if (isfinite(d_ab)) d = d_ab;
                else d = d_ba;
            }

            if (!isfinite(d)) continue;

            double demand_gap = fabs(CG.nodes[a].garbage_amount - CG.nodes[b].garbage_amount);
            double tw_gap =
                fabs(CG.nodes[a].latest - CG.nodes[b].latest) +
                fabs(CG.nodes[a].earliest - CG.nodes[b].earliest);

            double score = d + 0.5 * demand_gap + 0.001 * tw_gap;
            scored.push_back({score, b});
        }

        sort(scored.begin(), scored.end());

        int keep = min((int)scored.size(), max(1, cfg.candidate_k));
        candidate_neighbors[a].reserve(keep);

        for (int i = 0; i < keep; ++i) {
            candidate_neighbors[a].push_back(scored[i].second);
        }
    }

    cerr << "[candidate_lists] customers=" << customer_nodes_global.size()
        << " candidate_k=" << cfg.candidate_k << "\n";
}

static bool is_candidate_neighbor(int a, int b) {
    if (!cfg.use_candidate_lists) return true;
    if (a < 0 || a >= (int)candidate_neighbors.size()) return true;
    if (candidate_neighbors[a].empty()) return true;

    const auto &v = candidate_neighbors[a];
    return find(v.begin(), v.end(), b) != v.end();
}

static bool euclidean_candidate_edge_ok(int a, int b) {
    if (!euclidean_cuts_enabled()) return true;
    if (!cfg.euclidean_candidate_2opt_cut) return true;
    if (!cfg.use_candidate_lists) return true;

    if (a < 0 || b < 0) return true;
    if (a >= (int)candidate_neighbors.size()) return true;
    if (b >= (int)candidate_neighbors.size()) return true;

    // Depot arcs stay allowed. Candidate lists are customer-customer focused.
    // Blocking depot arcs here can break route starts/ends.
    return is_candidate_neighbor(a, b) || is_candidate_neighbor(b, a);
}

static vector<int> collect_customers_from_state(const SolutionState &state, const Compressed &CG) {
    vector<int> nodes;
    for (const auto &r : state.routes) for (int nid : r) if (CG.nodes[nid].type == 2) nodes.push_back(nid);
    return nodes;
}

static vector<int> collect_customers_from_route(const vector<int> &route, const Compressed &CG) {
    vector<int> out;
    for (int nid : route) if (CG.nodes[nid].type == 2) out.push_back(nid);
    return out;
}

static vector<int> remove_nodes_from_route(const vector<int>& route, const unordered_set<int>& removed) {
    vector<int> out;
    out.reserve(route.size());
    for (int nid : route) if (!removed.count(nid)) out.push_back(nid);
    return out;
}

static double relatedness_score(int a, int b, PairwiseManager &pm, const Compressed &CG) {
    if (a == b) return 1e18;

    double d = fast_pair_dist(a, b, &pm);
    if (!isfinite(d)) d = 1e15;

    double demand_gap = fabs(CG.nodes[a].garbage_amount - CG.nodes[b].garbage_amount);
    double tw_gap =
        fabs(CG.nodes[a].latest - CG.nodes[b].latest) +
        fabs(CG.nodes[a].earliest - CG.nodes[b].earliest);

    double score = d + 0.5 * demand_gap + 0.001 * tw_gap;

    // Soft penalty, not hard ban. Keeps ALNS robust if candidate list is imperfect.
    if (cfg.use_candidate_lists && !is_candidate_neighbor(a, b) && !is_candidate_neighbor(b, a)) {
        score += 1e9;
    }

    return score;
}

static vector<int> get_best_routes_for_node(
    const vector<vector<int>>& routes,
    PairwiseManager &pm,
    int node,
    int topK = 3
) {
    vector<pair<double,int>> score;
    score.reserve(routes.size());

    for (int r = 0; r < (int)routes.size(); ++r) {
        const auto &route = routes[r];

        double best = INF_D;

        // 1) Strong signal: nearest existing customer in this route.
        // V33 audit: the legacy implementation stopped after the first K
        // candidate-neighbor nodes encountered in *route order*. That makes a
        // route's score depend on where its close customers happen to appear.
        // In unbiased mode, scan the whole route and retain the true best
        // structural affinity. On asymmetric metrics use min(a->b,b->a) for
        // route proximity; actual insertion evaluation remains fully directed.
        profile.candidate_route_affinity_calls.fetch_add(1, memory_order_relaxed);
        int checked = 0;
        for (int x : route) {
            if (x == node) continue;

            bool useful = true;
            if (cfg.use_candidate_lists &&
                node >= 0 &&
                node < (int)candidate_neighbors.size() &&
                !candidate_neighbors[node].empty()) {
                useful = is_candidate_neighbor(node, x) || is_candidate_neighbor(x, node);
            }
            if (!useful) continue;

            double affinity = fast_pair_search_cost(node, x, &pm);
            if (!metric_is_symmetric()) {
                double rev = fast_pair_search_cost(x, node, &pm);
                if (isfinite(rev)) affinity = isfinite(affinity) ? min(affinity, rev) : rev;
            }
            best = min(best, affinity);
            checked++;
            profile.candidate_route_affinity_nodes_scanned.fetch_add(1, memory_order_relaxed);

            if (!cfg.candidate_route_unbiased_scan &&
                checked >= cfg.candidate_route_probe_k) break;
        }

        // 2) Fallback: sample actual internal route nodes.
        // Do this even if depot distance exists, because depot endpoints are weak in multi-trip.
        if (!isfinite(best) || best >= INF_D / 2) {
            int internal_count = max(0, (int)route.size() - 2);
            int step = max(1, internal_count / max(1, cfg.candidate_route_probe_k));

            for (int i = 1; i + 1 < (int)route.size(); i += step) {
                if (route[i] == node) continue;
                best = min(best, fast_pair_search_cost(route[i], node, &pm));
            }
        }

        // 3) Empty route fallback: depot distance only.
        if (!isfinite(best) || best >= INF_D / 2) {
            if (!route.empty()) {
                best = min(best, fast_pair_search_cost(route.front(), node, &pm));
            } else {
                best = INF_D / 2;
            }
        }

        score.push_back({best, r});
    }

    sort(score.begin(), score.end());

    if ((int)score.size() > topK) {
        score.resize(topK);
    }

    vector<int> res;
    res.reserve(score.size());

    for (auto &p : score) {
        res.push_back(p.second);
    }

    return res;
}

static bool try_insert_customer_simd_rank(
    SolutionState &state,
    int node,
    const vector<int> &candidate_routes,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    RepairWorkStats *stats
) {
    if (!cfg.use_topk_insertion ||
        !cfg.use_simd_insertion_rank ||
        cfg.objective_mode != "distance") {
        return false;
    }

    if (!dense_pairs.ready ||
        dense_pairs.dist_m_flat.empty() ||
        dense_pairs.C <= 0 ||
        node < 0 ||
        node >= (int)dense_pairs.node_to_compact.size()) {
        return false;
    }

    int x_c = dense_pairs.node_to_compact[node];
    if (x_c < 0) {
        return false;
    }

    int depot = depot_of(ev);

    vector<int> prev_c;
    vector<int> next_c;
    vector<int> route_id;
    vector<int> pos_id;
    vector<double> old_cost_by_slot;

    prev_c.reserve(256);
    next_c.reserve(256);
    route_id.reserve(256);
    pos_id.reserve(256);
    old_cost_by_slot.reserve(256);

    for (int r : candidate_routes) {
        if (r < 0 || r >= (int)state.routes.size()) {
            continue;
        }

        const auto &route = state.routes[r];

        if ((int)route.size() < 2) {
            continue;
        }

        if (stats) {
            stats->candidate_routes_examined++;
            stats->exact_route_evaluations++;
        }

        double old_cost = route_exact_cost(route, ev);
        if (!isfinite(old_cost) || old_cost >= INF_D / 2) {
            continue;
        }

        const int max_pos = min(
            (int)route.size() - 1,
            max(1, cfg.insertion_pos_cap)
        );

        for (int pos = 1; pos <= max_pos; ++pos) {
            int prev = route[pos - 1];
            int next = route[pos];

            if (prev < 0 || next < 0) {
                continue;
            }

            if (prev >= (int)dense_pairs.node_to_compact.size() ||
                next >= (int)dense_pairs.node_to_compact.size()) {
                continue;
            }

            int pc = dense_pairs.node_to_compact[prev];
            int nc = dense_pairs.node_to_compact[next];

            if (pc < 0 || nc < 0) {
                continue;
            }

            prev_c.push_back(pc);
            next_c.push_back(nc);
            route_id.push_back(r);
            pos_id.push_back(pos);
            old_cost_by_slot.push_back(old_cost);
            if (stats) stats->positions_ranked++;
        }
    }

    int n = (int)pos_id.size();

    if (n <= 0) {
        return false;
    }

    vector<double> deltas(n);

    insertion_deltas_fast_dist(
        dense_pairs.dist_m_flat.data(),
        dense_pairs.C,
        x_c,
        prev_c.data(),
        next_c.data(),
        n,
        deltas.data()
    );

    vector<int> order;
    order.reserve(n);

    for (int k = 0; k < n; ++k) {
        if (!isfinite(deltas[k]) || deltas[k] >= INF_D / 2) {
            continue;
        }

        order.push_back(k);
    }

    if (order.empty()) {
        return false;
    }

    int exact_budget =
        max(1, cfg.insertion_topk_exact) *
        max(1, (int)candidate_routes.size()) *
        max(1, cfg.simd_global_topk_multiplier);

    int keep = min((int)order.size(), exact_budget);

    if ((int)order.size() > keep) {
        nth_element(
            order.begin(),
            order.begin() + keep,
            order.end(),
            [&](int a, int b) {
                if (deltas[a] != deltas[b]) {
                    return deltas[a] < deltas[b];
                }

                if (route_id[a] != route_id[b]) {
                    return route_id[a] < route_id[b];
                }

                return pos_id[a] < pos_id[b];
            }
        );

        order.resize(keep);
    }

    sort(
        order.begin(),
        order.end(),
        [&](int a, int b) {
            if (deltas[a] != deltas[b]) {
                return deltas[a] < deltas[b];
            }

            if (route_id[a] != route_id[b]) {
                return route_id[a] < route_id[b];
            }

            return pos_id[a] < pos_id[b];
        }
    );

    double best_delta = INF_D;
    int best_r = -1;
    int best_pos = -1;

    for (int idx : order) {
        int r = route_id[idx];
        int pos = pos_id[idx];

        if (r < 0 || r >= (int)state.routes.size()) {
            continue;
        }

        const auto &route = state.routes[r];

        if (pos <= 0 || pos > (int)route.size()) {
            continue;
        }

        vector<int> cand = route;
        cand.insert(cand.begin() + pos, node);

        normalize_route(cand, depot);
        enforce_trip_separators(cand, *ev.CG, depot);

        if (!trips_feasible_for_route(cand, *ev.CG, depot)) {
            continue;
        }

        bool hard_filter_insert =
            cfg.use_time_window &&
            cfg.tw_strict_insertion &&
            !cfg.tw_allow_soft_intermediate;

        if (hard_filter_insert && !route_hard_tw_feasible(cand, ev, pm)) {
            continue;
        }

        if (stats) stats->exact_route_evaluations++;
        double new_cost = route_exact_cost(cand, ev);
        double exact_delta = new_cost - old_cost_by_slot[idx];

        if (exact_delta < best_delta) {
            best_delta = exact_delta;
            best_r = r;
            best_pos = pos;
        }
    }

    if (best_r < 0 || best_pos < 0) {
        return false;
    }

    state.routes[best_r].insert(
        state.routes[best_r].begin() + best_pos,
        node
    );

    normalize_route(state.routes[best_r], depot);
    enforce_trip_separators(state.routes[best_r], *ev.CG, depot);

    return true;
}

static bool insert_customer_best_place_fast(
    SolutionState &state,
    int node,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    RepairWorkStats *stats
) {
    int depot = depot_of(ev);

    vector<int> candidate_routes =
        get_best_routes_for_node(state.routes, pm, node, cfg.insertion_route_cap);

    double best_delta = INF_D;
    int best_r = -1;
    int best_pos = -1;

    if (try_insert_customer_simd_rank(
            state,
            node,
            candidate_routes,
            ev,
            pm,
            stats
        )) {
        return true;
    }

    for (int r : candidate_routes) {
        if (r < 0 || r >= (int)state.routes.size()) continue;

        const auto &route = state.routes[r];

        if ((int)route.size() < 2) continue;

        if (stats) {
            stats->candidate_routes_examined++;
            stats->exact_route_evaluations++;
        }
        double old_cost = route_exact_cost(route, ev);

        const int max_pos = min(
            (int)route.size() - 1,
            max(1, cfg.insertion_pos_cap)
        );

        vector<int> positions;
        positions.reserve(max_pos);

        if (cfg.use_topk_insertion) {
            vector<pair<double, int>> ranked_pos;
            ranked_pos.reserve(max_pos);

            for (int pos = 1; pos <= max_pos; ++pos) {
                if (stats) stats->positions_ranked++;
                int prev = route[pos - 1];
                int next = route[pos];

                double old_edge = fast_pair_search_cost(prev, next, &pm);
                double new_edges =
                    fast_pair_search_cost(prev, node, &pm) +
                    fast_pair_search_cost(node, next, &pm);

                if (!isfinite(old_edge) || !isfinite(new_edges)) continue;

                double cheap_delta = new_edges - old_edge;
                ranked_pos.push_back({cheap_delta, pos});
            }

            sort(ranked_pos.begin(), ranked_pos.end());

            int keep = min(
                (int)ranked_pos.size(),
                max(1, cfg.insertion_topk_exact)
            );

            for (int i = 0; i < keep; ++i) {
                positions.push_back(ranked_pos[i].second);
            }
        }
        else {
            for (int pos = 1; pos <= max_pos; ++pos) {
                positions.push_back(pos);
                if (stats) stats->positions_ranked++;
            }
        }

        for (int pos : positions) {
            vector<int> cand = route;
            cand.insert(cand.begin() + pos, node);

            normalize_route(cand, depot);
            enforce_trip_separators(cand, *ev.CG, depot);

            if (!trips_feasible_for_route(cand, *ev.CG, depot)) {
                continue;
            }

            bool hard_filter_insert =
                cfg.use_time_window &&
                cfg.tw_strict_insertion &&
                !cfg.tw_allow_soft_intermediate;

            if (hard_filter_insert) {
                if (!route_hard_tw_feasible(cand, ev, pm)) {
                    continue;
                }
            }

            if (stats) stats->exact_route_evaluations++;
            double new_cost = route_exact_cost(cand, ev);
            double delta = new_cost - old_cost;

            if (delta < best_delta) {
                best_delta = delta;
                best_r = r;
                best_pos = pos;
            }
        }
    }

    if (best_r < 0 || best_pos < 0) {
        return false;
    }

    state.routes[best_r].insert(
        state.routes[best_r].begin() + best_pos,
        node
    );

    normalize_route(state.routes[best_r], depot);
    enforce_trip_separators(state.routes[best_r], *ev.CG, depot);

    return true;
}

/* ---------------- Route-pair boundary diagnostics ---------------- */

static vector<int> route_customer_nodes(
    const vector<int> &route,
    const Compressed &CG
) {
    vector<int> out;

    for (int nid : route) {
        if (nid >= 0 &&
            nid < (int)CG.nodes.size() &&
            CG.nodes[nid].type == 2) {
            out.push_back(nid);
        }
    }

    return out;
}

static double route_centroid_distance(
    const vector<int> &A,
    const vector<int> &B,
    const Compressed &CG
) {
    auto centroid = [&](const vector<int> &v) -> pair<double, double> {
        double sx = 0.0;
        double sy = 0.0;
        int cnt = 0;

        for (int nid : v) {
            if (nid < 0 || nid >= (int)CG.nodes.size()) continue;
            sx += CG.nodes[nid].lon;
            sy += CG.nodes[nid].lat;
            cnt++;
        }

        if (cnt == 0) return {0.0, 0.0};
        return {sx / cnt, sy / cnt};
    };

    auto ca = centroid(A);
    auto cb = centroid(B);

    double dx = ca.first - cb.first;
    double dy = ca.second - cb.second;

    return sqrt(dx * dx + dy * dy);
}

static void route_bbox(
    const vector<int> &nodes,
    const Compressed &CG,
    double &minx,
    double &maxx,
    double &miny,
    double &maxy
) {
    minx = INF_D;
    maxx = -INF_D;
    miny = INF_D;
    maxy = -INF_D;

    for (int nid : nodes) {
        if (nid < 0 || nid >= (int)CG.nodes.size()) continue;

        minx = min(minx, CG.nodes[nid].lon);
        maxx = max(maxx, CG.nodes[nid].lon);
        miny = min(miny, CG.nodes[nid].lat);
        maxy = max(maxy, CG.nodes[nid].lat);
    }

    if (minx >= INF_D / 2) {
        minx = maxx = miny = maxy = 0.0;
    }
}

static double route_bbox_overlap_score(
    const vector<int> &A,
    const vector<int> &B,
    const Compressed &CG
) {
    double aminx, amaxx, aminy, amaxy;
    double bminx, bmaxx, bminy, bmaxy;

    route_bbox(A, CG, aminx, amaxx, aminy, amaxy);
    route_bbox(B, CG, bminx, bmaxx, bminy, bmaxy);

    double ix = max(0.0, min(amaxx, bmaxx) - max(aminx, bminx));
    double iy = max(0.0, min(amaxy, bmaxy) - max(aminy, bminy));

    double inter = ix * iy;

    double areaA = max(1e-9, (amaxx - aminx) * (amaxy - aminy));
    double areaB = max(1e-9, (bmaxx - bminx) * (bmaxy - bminy));

    return inter / max(areaA, areaB);
}

static double route_pair_boundary_score(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int ra,
    int rb,
    int &near_hits,
    double &min_cross_dist,
    double &centroid_dist,
    double &bbox_overlap
) {
    const Compressed &CG = *ev.CG;

    vector<int> A = route_customer_nodes(state.routes[ra], CG);
    vector<int> B = route_customer_nodes(state.routes[rb], CG);

    near_hits = 0;
    min_cross_dist = INF_D;

    if (A.empty() || B.empty()) {
        centroid_dist = INF_D;
        bbox_overlap = 0.0;
        return INF_D;
    }

    for (int a : A) {
        vector<pair<double, int>> close_to_b;
        close_to_b.reserve(B.size());

        for (int b : B) {
            double d = fast_pair_dist(a, b, &pm);
            if (!isfinite(d)) continue;

            min_cross_dist = min(min_cross_dist, d);
            close_to_b.push_back({d, b});
        }

        sort(close_to_b.begin(), close_to_b.end());

        int k = min((int)close_to_b.size(), cfg.route_pair_diag_neighbor_k);
        for (int i = 0; i < k; ++i) {
            near_hits++;
        }
    }

    centroid_dist = route_centroid_distance(A, B, CG);
    bbox_overlap = route_bbox_overlap_score(A, B, CG);

    double costA = state.route_metrics[ra].weighted_cost;
    double costB = state.route_metrics[rb].weighted_cost;

    // Lower score = more suspicious / more worth attacking.
    // min_cross_dist is the main signal.
    // bbox overlap and many cross-neighbors make the pair more suspicious.
    double score =
    min_cross_dist
        + 0.20 * centroid_dist
        - 5.00 * bbox_overlap
        - 0.10 * near_hits
        - 0.0001 * (costA + costB);

    return score;
}

static void print_route_pair_diagnostics(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!cfg.use_route_pair_diag) return;
    if (cfg.route_pair_diag_top <= 0) return;

    int R = (int)state.routes.size();

    vector<tuple<double, int, int, int, double, double, double, double, double>> rows;

    for (int ra = 0; ra < R; ++ra) {
        for (int rb = ra + 1; rb < R; ++rb) {
            int near_hits = 0;
            double min_cross_dist = INF_D;
            double centroid_dist = INF_D;
            double bbox_overlap = 0.0;

            double score = route_pair_boundary_score(
                state,
                ev,
                pm,
                ra,
                rb,
                near_hits,
                min_cross_dist,
                centroid_dist,
                bbox_overlap
            );

            if (!isfinite(score) || score >= INF_D / 2) continue;

            double costA = state.route_metrics[ra].weighted_cost;
            double costB = state.route_metrics[rb].weighted_cost;

            rows.push_back({
                score,
                ra,
                rb,
                near_hits,
                min_cross_dist,
                centroid_dist,
                bbox_overlap,
                costA,
                costB
            });
        }
    }

    sort(rows.begin(), rows.end());

    cerr << "\n[RoutePairDiag] metric=" << cfg.metric_mode
        << " objective=" << state.objective
        << " top=" << min(cfg.route_pair_diag_top, (int)rows.size())
        << "\n";

    int lim = min(cfg.route_pair_diag_top, (int)rows.size());

    for (int i = 0; i < lim; ++i) {
        auto [score, ra, rb, near_hits, min_cross_dist,
            centroid_dist, bbox_overlap, costA, costB] = rows[i];

        cerr << "[RoutePairDiag] rank=" << i
            << " pair=(" << ra << "," << rb << ")"
            << " score=" << score
            << " min_cross=" << min_cross_dist
            << " centroid=" << centroid_dist
            << " bbox_overlap=" << bbox_overlap
            << " near_hits=" << near_hits
            << " costA=" << costA
            << " costB=" << costB
            << " sizeA=" << max(0, (int)state.routes[ra].size() - 2)
            << " sizeB=" << max(0, (int)state.routes[rb].size() - 2)
            << "\n";
    }

    cerr << "\n";
}

static double own_route_local_scale(
    const vector<int> &route,
    const Compressed &CG,
    PairwiseManager &pm,
    int pos
) {
    int node = route[pos];

    double best = INF_D;

    if (pos - 1 >= 0) {
        int p = route[pos - 1];
        if (p >= 0 && p < (int)CG.nodes.size()) {
            best = min(best, fast_pair_dist(node, p, &pm));
        }
    }

    if (pos + 1 < (int)route.size()) {
        int q = route[pos + 1];
        if (q >= 0 && q < (int)CG.nodes.size()) {
            best = min(best, fast_pair_dist(node, q, &pm));
        }
    }

    return best;
}

static vector<int> route_boundary_customers_against(
    const vector<int> &A,
    const vector<int> &B,
    const Compressed &CG,
    PairwiseManager &pm,
    double attraction_ratio = 0.85
) {
    vector<int> boundary;

    for (int i = 1; i + 1 < (int)A.size(); ++i) {
        int a = A[i];

        if (a < 0 || a >= (int)CG.nodes.size()) continue;
        if (CG.nodes[a].type != 2) continue;

        double own_scale = own_route_local_scale(A, CG, pm, i);
        if (!isfinite(own_scale) || own_scale >= INF_D / 2) continue;

        double best_cross = INF_D;

        for (int b : B) {
            if (b < 0 || b >= (int)CG.nodes.size()) continue;
            if (CG.nodes[b].type != 2) continue;

            best_cross = min(best_cross, fast_pair_dist(a, b, &pm));
        }

        if (best_cross < attraction_ratio * own_scale) {
            boundary.push_back(a);
        }
    }

    return boundary;
}

static void print_route_pair_boundary_customers(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int top_pairs = 8
) {
    const Compressed &CG = *ev.CG;
    int R = (int)state.routes.size();

    vector<tuple<double, int, int>> scored;

    for (int ra = 0; ra < R; ++ra) {
        for (int rb = ra + 1; rb < R; ++rb) {
            vector<int> AtoB = route_boundary_customers_against(
                state.routes[ra], state.routes[rb], CG, pm
            );

            vector<int> BtoA = route_boundary_customers_against(
                state.routes[rb], state.routes[ra], CG, pm
            );

            int suspicious = (int)AtoB.size() + (int)BtoA.size();

            if (suspicious == 0) continue;

            double min_cross = INF_D;

            for (int a : state.routes[ra]) {
                if (a < 0 || a >= (int)CG.nodes.size()) continue;
                if (CG.nodes[a].type != 2) continue;

                for (int b : state.routes[rb]) {
                    if (b < 0 || b >= (int)CG.nodes.size()) continue;
                    if (CG.nodes[b].type != 2) continue;

                    min_cross = min(min_cross, fast_pair_dist(a, b, &pm));
                }
            }

            double score = min_cross - 2.0 * suspicious;

            scored.push_back({score, ra, rb});
        }
    }

    sort(scored.begin(), scored.end());

    int lim = min(top_pairs, (int)scored.size());

    cerr << "\n[BoundaryDiag] objective=" << state.objective
        << " top=" << lim << "\n";

    for (int k = 0; k < lim; ++k) {
        auto [score, ra, rb] = scored[k];

        vector<int> AtoB = route_boundary_customers_against(
            state.routes[ra], state.routes[rb], CG, pm
        );

        vector<int> BtoA = route_boundary_customers_against(
            state.routes[rb], state.routes[ra], CG, pm
        );

        cerr << "[BoundaryDiag] rank=" << k
            << " pair=(" << ra << "," << rb << ")"
            << " score=" << score
            << " AtoB={";

        for (int x : AtoB) cerr << x << " ";

        cerr << "} BtoA={";

        for (int x : BtoA) cerr << x << " ";

        cerr << "}\n";
    }

    cerr << "\n";
}

/* ---------------- Unified Boundary Signal ---------------- */

static vector<BoundaryPairSignal> build_boundary_signals(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int topK
) {
    const Compressed &CG = *ev.CG;
    int R = (int)state.routes.size();

    vector<BoundaryPairSignal> signals;

    for (int ra = 0; ra < R; ++ra) {
        for (int rb = ra + 1; rb < R; ++rb) {
            vector<int> AtoB = route_boundary_customers_against(
                state.routes[ra],
                state.routes[rb],
                CG,
                pm
            );

            vector<int> BtoA = route_boundary_customers_against(
                state.routes[rb],
                state.routes[ra],
                CG,
                pm
            );

            int suspicious = (int)AtoB.size() + (int)BtoA.size();
            if (suspicious == 0) continue;

            double min_cross = INF_D;

            for (int a : state.routes[ra]) {
                if (a < 0 || a >= (int)CG.nodes.size()) continue;
                if (CG.nodes[a].type != 2) continue;

                for (int b : state.routes[rb]) {
                    if (b < 0 || b >= (int)CG.nodes.size()) continue;
                    if (CG.nodes[b].type != 2) continue;

                    min_cross = min(min_cross, fast_pair_dist(a, b, &pm));
                }
            }

            BoundaryPairSignal s;
            s.ra = ra;
            s.rb = rb;
            s.score = min_cross - 2.0 * suspicious;
            s.AtoB = std::move(AtoB);
            s.BtoA = std::move(BtoA);

            signals.push_back(std::move(s));
        }
    }

    sort(signals.begin(), signals.end(), [](const auto &a, const auto &b) {
        if (fabs(a.score - b.score) > 1e-9) return a.score < b.score;
        if (a.ra != b.ra) return a.ra < b.ra;
        return a.rb < b.rb;
    });

    if (topK > 0 && (int)signals.size() > topK) {
        signals.resize(topK);
    }

    return signals;
}

static vector<int> route_positions_priority_first(
    const vector<int> &route,
    const vector<int> &priority_nodes,
    const Compressed &CG
) {
    vector<int> out;
    vector<char> used(route.size(), 0);
    unordered_set<int> priority_set(priority_nodes.begin(), priority_nodes.end());

    // Priority boundary customers first.
    for (int i = 1; i + 1 < (int)route.size(); ++i) {
        int x = route[i];

        if (x < 0 || x >= (int)CG.nodes.size()) continue;
        if (CG.nodes[x].type != 2) continue;

        if (priority_set.count(x)) {
            out.push_back(i);
            used[i] = 1;
        }
    }

    // Then normal route order fallback.
    for (int i = 1; i + 1 < (int)route.size(); ++i) {
        if (used[i]) continue;

        int x = route[i];

        if (x < 0 || x >= (int)CG.nodes.size()) continue;
        if (CG.nodes[x].type != 2) continue;

        out.push_back(i);
    }

    return out;
}

/* ---------------- Boundary Pair LNS ---------------- */

static void add_boundary_node_with_neighbors(
    vector<int> &out,
    unordered_set<int> &seen,
    const vector<int> &route,
    const Compressed &CG,
    int node
) {
    auto add_one = [&](int x) {
        if (x < 0 || x >= (int)CG.nodes.size()) return;
        if (CG.nodes[x].type != 2) return;
        if (seen.insert(x).second) out.push_back(x);
    };

    for (int i = 0; i < (int)route.size(); ++i) {
        if (route[i] != node) continue;

        add_one(route[i]);

        if (cfg.boundary_pair_lns_add_neighbors) {
            if (i - 1 >= 0) add_one(route[i - 1]);
            if (i + 1 < (int)route.size()) add_one(route[i + 1]);
        }

        return;
    }
}

static vector<int> boundary_pair_extract_set(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int ra,
    int rb
) {
    const Compressed &CG = *ev.CG;

    vector<int> AtoB = route_boundary_customers_against(
        state.routes[ra],
        state.routes[rb],
        CG,
        pm
    );

    vector<int> BtoA = route_boundary_customers_against(
        state.routes[rb],
        state.routes[ra],
        CG,
        pm
    );

    vector<int> remove_set;
    unordered_set<int> seen;

    for (int x : AtoB) {
        add_boundary_node_with_neighbors(
            remove_set,
            seen,
            state.routes[ra],
            CG,
            x
        );
    }

    for (int x : BtoA) {
        add_boundary_node_with_neighbors(
            remove_set,
            seen,
            state.routes[rb],
            CG,
            x
        );
    }

    // If too large, keep the customers most cross-attracted to the opposite route.
    if ((int)remove_set.size() > cfg.boundary_pair_lns_max_remove) {
        vector<pair<double, int>> scored;

        auto best_cross_to_route = [&](int x, const vector<int> &route) -> double {
            double best = INF_D;

            for (int y : route) {
                if (y < 0 || y >= (int)CG.nodes.size()) continue;
                if (CG.nodes[y].type != 2) continue;
                if (y == x) continue;

                best = min(best, fast_pair_dist(x, y, &pm));
            }

            return best;
        };

        for (int x : remove_set) {
            double d1 = best_cross_to_route(x, state.routes[ra]);
            double d2 = best_cross_to_route(x, state.routes[rb]);
            double d = min(d1, d2);

            if (!isfinite(d)) d = INF_D;
            scored.push_back({d, x});
        }

        sort(scored.begin(), scored.end());

        vector<int> trimmed;
        for (auto &p : scored) {
            trimmed.push_back(p.second);
            if ((int)trimmed.size() >= cfg.boundary_pair_lns_max_remove) break;
        }

        remove_set.swap(trimmed);
    }

    return remove_set;
}

static void boundary_pair_remove_nodes_from_route(
    vector<int> &route,
    const unordered_set<int> &remove_nodes,
    int depot
) {
    vector<int> out;
    out.reserve(route.size());

    for (int nid : route) {
        if (nid != depot && remove_nodes.count(nid)) continue;
        out.push_back(nid);
    }

    normalize_route(out, depot);
    route.swap(out);
}

static bool boundary_pair_insert_one_best(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int node,
    int ra,
    int rb
) {
    (void)pm;
    const Compressed &CG = *ev.CG;

    SolutionState best_state;
    double best_obj = INF_D;
    bool found = false;

    int routes_to_try[2] = {ra, rb};

    for (int rr_i = 0; rr_i < 2; ++rr_i) {
        int r = routes_to_try[rr_i];

        if (r < 0 || r >= (int)state.routes.size()) {
            continue;
        }

        int sz = (int)state.routes[r].size();

        for (int pos = 1; pos < sz; ++pos) {
            SolutionState cand = state;

            cand.routes[r].insert(cand.routes[r].begin() + pos, node);

            recompute_state_metrics_and_loads(cand, ev);

            // IMPORTANT:
            // During boundary repair, other removed customers may still be missing.
            // So we must NOT call solution_fully_feasible() here.
            // Only check capacity/trip feasibility at intermediate insertion steps.
            if (!solution_capacity_feasible(cand, CG)) {
                continue;
            }

            // Also prevent accidental duplicate service of this inserted node.
            if (node >= 0 &&
                node < (int)cand.served_count.size() &&
                cand.served_count[node] > 1) {
                continue;
            }

            if (cand.objective + 1e-9 < best_obj) {
                best_obj = cand.objective;
                best_state = std::move(cand);
                found = true;
            }
        }
    }

    if (!found) {
        return false;
    }

    state = std::move(best_state);
    recompute_state_metrics_and_loads(state, ev);

    return true;
}

static bool boundary_pair_repair_order(
    SolutionState base,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const vector<int> &order,
    int ra,
    int rb,
    SolutionState &out
) {
    for (int node : order) {
        bool ok = boundary_pair_insert_one_best(
            base,
            ev,
            pm,
            node,
            ra,
            rb
        );

        if (!ok) {
            return false;
        }
    }

    recompute_state_metrics_and_loads(base, ev);

    if (!solution_fully_feasible(base, *ev.CG)) {
        return false;
    }

    out = std::move(base);
    return true;
}

static bool boundary_pair_lns_once(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int ra,
    int rb
) {
    const Compressed &CG = *ev.CG;
    int depot = find_depot_idx(CG);

    if (ra == rb) return false;
    if (ra < 0 || rb < 0) return false;
    if (ra >= (int)state.routes.size() || rb >= (int)state.routes.size()) return false;

    vector<int> remove_set = boundary_pair_extract_set(
        state,
        ev,
        pm,
        ra,
        rb
    );

    if (remove_set.empty()) return false;

    unordered_set<int> rem(remove_set.begin(), remove_set.end());

    SolutionState base = state;

    boundary_pair_remove_nodes_from_route(base.routes[ra], rem, depot);
    boundary_pair_remove_nodes_from_route(base.routes[rb], rem, depot);

    recompute_state_metrics_and_loads(base, ev);

    vector<vector<int>> orders;

    // 1. Original diagnostic order.
    orders.push_back(remove_set);

    // 2. Reverse order.
    vector<int> rev = remove_set;
    reverse(rev.begin(), rev.end());
    orders.push_back(rev);

    // 3. Demand descending.
    vector<int> demand_order = remove_set;
    sort(demand_order.begin(), demand_order.end(), [&](int a, int b) {
        return CG.nodes[a].garbage_amount > CG.nodes[b].garbage_amount;
    });
    orders.push_back(demand_order);

    // 4. Best local-route scale first: most boundary-like first.
    vector<int> closeness_order = remove_set;
    sort(closeness_order.begin(), closeness_order.end(), [&](int a, int b) {
        auto best_to_pair = [&](int x) -> double {
            double best = INF_D;

            for (int y : state.routes[ra]) {
                if (y >= 0 && y < (int)CG.nodes.size() && CG.nodes[y].type == 2 && y != x) {
                    best = min(best, fast_pair_dist(x, y, &pm));
                }
            }

            for (int y : state.routes[rb]) {
                if (y >= 0 && y < (int)CG.nodes.size() && CG.nodes[y].type == 2 && y != x) {
                    best = min(best, fast_pair_dist(x, y, &pm));
                }
            }

            return best;
        };

        return best_to_pair(a) < best_to_pair(b);
    });
    orders.push_back(closeness_order);

    SolutionState best_candidate = state;
    double best_obj = state.objective;
    bool improved = false;

    for (const auto &ord : orders) {
        SolutionState cand;

        bool ok = boundary_pair_repair_order(
            base,
            ev,
            pm,
            ord,
            ra,
            rb,
            cand
        );

        if (!ok) continue;

        if (metric_is_euclidean() && euclidean_cuts_enabled()) {
            euclidean_branch_polish_solution(cand, ev, pm);
            recompute_state_metrics_and_loads(cand, ev);
        }

        if (!solution_fully_feasible(cand, CG)) {
            continue;
        }

        if (cand.objective + 1e-9 < best_obj) {
            best_obj = cand.objective;
            best_candidate = std::move(cand);
            improved = true;
        }
    }

    if (!improved) return false;

    double old_obj = state.objective;
    state = std::move(best_candidate);
    recompute_state_metrics_and_loads(state, ev);

    if (cfg.boundary_pair_lns_verbose) {
        cerr << "[BoundaryPairLNS] accept pair=(" << ra << "," << rb << ")"
            << " removed={";

        for (int x : remove_set) cerr << x << " ";

        cerr << "} old=" << old_obj
            << " new=" << state.objective
            << " gain=" << (old_obj - state.objective)
            << "\n";
    }

    return true;
}

static vector<pair<int, int>> boundary_pair_rank_pairs(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const Compressed &CG = *ev.CG;
    int R = (int)state.routes.size();

    vector<tuple<double, int, int>> scored;

    for (int ra = 0; ra < R; ++ra) {
        for (int rb = ra + 1; rb < R; ++rb) {
            vector<int> AtoB = route_boundary_customers_against(
                state.routes[ra],
                state.routes[rb],
                CG,
                pm
            );

            vector<int> BtoA = route_boundary_customers_against(
                state.routes[rb],
                state.routes[ra],
                CG,
                pm
            );

            int suspicious = (int)AtoB.size() + (int)BtoA.size();
            if (suspicious == 0) continue;

            double min_cross = INF_D;

            for (int a : state.routes[ra]) {
                if (a < 0 || a >= (int)CG.nodes.size()) continue;
                if (CG.nodes[a].type != 2) continue;

                for (int b : state.routes[rb]) {
                    if (b < 0 || b >= (int)CG.nodes.size()) continue;
                    if (CG.nodes[b].type != 2) continue;

                    min_cross = min(min_cross, fast_pair_dist(a, b, &pm));
                }
            }

            double score = min_cross - 2.0 * suspicious;
            scored.push_back({score, ra, rb});
        }
    }

    sort(scored.begin(), scored.end());

    vector<pair<int, int>> out;
    int lim = min(cfg.boundary_pair_lns_top_pairs, (int)scored.size());

    for (int i = 0; i < lim; ++i) {
        auto [score, ra, rb] = scored[i];
        (void)score;
        out.push_back({ra, rb});
    }

    return out;
}

static vector<pair<int, int>> boundary_prioritized_route_pairs(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int fallback_R
) {
    vector<pair<int, int>> out;
    set<pair<int, int>> seen;

    if (cfg.use_boundary_prioritized_education) {
        vector<BoundaryPairSignal> signals = build_boundary_signals(
            state,
            ev,
            pm,
            cfg.boundary_prioritized_top_pairs
        );

        for (const auto &s : signals) {
            int a = s.ra;
            int b = s.rb;
            if (a > b) swap(a, b);

            if (a < 0 || b < 0 || a == b) continue;
            if (a >= fallback_R || b >= fallback_R) continue;

            if (seen.insert({a, b}).second) {
                out.push_back({a, b});
            }
        }
    }

    // Fallback normal order.
    for (int a = 0; a < fallback_R; ++a) {
        for (int b = a + 1; b < fallback_R; ++b) {
            if (seen.insert({a, b}).second) {
                out.push_back({a, b});
            }
        }
    }

    return out;
}

static void boundary_pair_lns_descent(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!cfg.use_boundary_pair_lns) return;
    profile.boundary_pair_calls.fetch_add(1, memory_order_relaxed);
    if (cfg.boundary_pair_lns_rounds <= 0) return;

    double start_obj = state.objective;
    int accepted = 0;

    for (int round = 0; round < cfg.boundary_pair_lns_rounds; ++round) {
        if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); break; }
        vector<pair<int, int>> pairs = boundary_pair_rank_pairs(state, ev, pm);

        bool round_improved = false;

        for (auto [ra, rb] : pairs) {
            bool ok = boundary_pair_lns_once(state, ev, pm, ra, rb);

            if (ok) {
                accepted++;
                round_improved = true;
                break; // recompute pair ranking after each accepted move
            }
        }

        if (!round_improved) break;
    }

    if (cfg.boundary_pair_lns_verbose) {
        cerr << "[BoundaryPairLNS] start=" << start_obj
            << " end=" << state.objective
            << " gain=" << (start_obj - state.objective)
            << " accepted=" << accepted
            << " rounds=" << cfg.boundary_pair_lns_rounds
            << " top_pairs=" << cfg.boundary_pair_lns_top_pairs
            << " max_remove=" << cfg.boundary_pair_lns_max_remove
            << "\n";
    }
}

/* ---------------- Granular Tabu Repair ---------------- */

struct GranularTabuMove {
    enum Type {
        RELOCATE = 0,
        SWAP = 1
    };

    Type type = RELOCATE;

    int r1 = -1;
    int p1 = -1;
    int r2 = -1;
    int p2 = -1;

    int a = -1;
    int b = -1;

    double new_obj = INF_D;
    double delta = INF_D;

    // V36: store only the two changed routes. The old implementation copied
    // the entire SolutionState for every candidate relocation/swap, which is
    // especially expensive on 200-1000 customer instances.
    vector<int> new_r1;
    vector<int> new_r2;
};

static int find_pos_in_route(
    const vector<int> &route,
    int node
) {
    for (int i = 0; i < (int)route.size(); ++i) {
        if (route[i] == node) return i;
    }
    return -1;
}

static void add_node_and_neighbors_for_granular(
    vector<int> &nodes,
    unordered_set<int> &seen,
    const vector<int> &route,
    const Compressed &CG,
    int node,
    int radius
) {
    int pos = find_pos_in_route(route, node);
    if (pos < 0) return;

    auto add_one = [&](int x) {
        if (x < 0 || x >= (int)CG.nodes.size()) return;
        if (CG.nodes[x].type != 2) return;
        if (seen.insert(x).second) {
            nodes.push_back(x);
        }
    };

    add_one(route[pos]);

    for (int d = 1; d <= radius; ++d) {
        if (pos - d >= 0) add_one(route[pos - d]);
        if (pos + d < (int)route.size()) add_one(route[pos + d]);
    }
}

static vector<int> granular_nodes_for_pair(
    const SolutionState &state,
    const BoundaryPairSignal &sig,
    int route_id,
    const Compressed &CG,
    PairwiseManager &pm
) {
    vector<int> nodes;
    unordered_set<int> seen;

    int radius = max(0, cfg.granular_tabu_customer_radius);

    if (route_id == sig.ra) {
        for (int x : sig.AtoB) {
            add_node_and_neighbors_for_granular(
                nodes,
                seen,
                state.routes[route_id],
                CG,
                x,
                radius
            );
        }
    }
    else if (route_id == sig.rb) {
        for (int x : sig.BtoA) {
            add_node_and_neighbors_for_granular(
                nodes,
                seen,
                state.routes[route_id],
                CG,
                x,
                radius
            );
        }
    }

    // Fallback: if no boundary nodes found, use route customers closest to opposite route.
    if (nodes.empty()) {
        vector<pair<double, int>> scored;

        int other = (route_id == sig.ra) ? sig.rb : sig.ra;

        for (int x : state.routes[route_id]) {
            if (x < 0 || x >= (int)CG.nodes.size()) continue;
            if (CG.nodes[x].type != 2) continue;

            double best_cross = INF_D;

            for (int y : state.routes[other]) {
                if (y < 0 || y >= (int)CG.nodes.size()) continue;
                if (CG.nodes[y].type != 2) continue;
                best_cross = min(best_cross, fast_pair_dist(x, y, &pm));
            }

            scored.push_back({best_cross, x});
        }

        sort(scored.begin(), scored.end());

        int lim = min(cfg.granular_tabu_candidate_cap, (int)scored.size());

        for (int i = 0; i < lim; ++i) {
            if (seen.insert(scored[i].second).second) {
                nodes.push_back(scored[i].second);
            }
        }
    }

    if ((int)nodes.size() > cfg.granular_tabu_candidate_cap) {
        nodes.resize(cfg.granular_tabu_candidate_cap);
    }

    return nodes;
}

static bool granular_route_basic_ok(
    const vector<int> &route,
    const Compressed &CG,
    int depot
) {
    if (route.empty()) return false;
    if (route.front() != depot) return false;
    if (route.back() != depot) return false;
    if (route_has_duplicate_customers_strict(route, CG)) return false;
    if (!trips_feasible_for_route(route, CG, depot)) return false;
    return true;
}

[[maybe_unused]] static bool granular_candidate_feasible(
    const SolutionState &cand,
    const Compressed &CG,
    PairwiseManager &pm
) {
    if (!solution_serves_all_customers_once(cand, CG)) return false;
    if (!solution_capacity_feasible(cand, CG)) return false;
    if (cfg.use_time_window && !solution_hard_feasible(cand, CG, pm)) return false;
    return true;
}

static bool is_tabu_customer_route(
    const vector<vector<int>> &tabu_until,
    int customer,
    int route_id,
    int iter
) {
    if (customer < 0 || customer >= (int)tabu_until.size()) return false;
    if (route_id < 0 || route_id >= (int)tabu_until[customer].size()) return false;
    return tabu_until[customer][route_id] > iter;
}

static void mark_tabu_customer_route(
    vector<vector<int>> &tabu_until,
    int customer,
    int route_id,
    int until_iter
) {
    if (customer < 0 || customer >= (int)tabu_until.size()) return;
    if (route_id < 0 || route_id >= (int)tabu_until[customer].size()) return;
    tabu_until[customer][route_id] = max(tabu_until[customer][route_id], until_iter);
}

static bool try_build_granular_relocate(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    int r_from,
    int pos_from,
    int r_to,
    int insert_pos,
    GranularTabuMove &out,
    PairwiseManager &pm
) {
    if (r_from == r_to) return false;

    const Compressed &CG = *ev.CG;
    int depot = find_depot_idx(CG);

    if (r_from < 0 || r_to < 0) return false;
    if (r_from >= (int)state.routes.size() || r_to >= (int)state.routes.size()) return false;

    const vector<int> &A = state.routes[r_from];
    const vector<int> &B = state.routes[r_to];
    if (pos_from <= 0 || pos_from + 1 >= (int)A.size()) return false;
    if (insert_pos <= 0 || insert_pos >= (int)B.size()) return false;

    int node = A[pos_from];
    if (node < 0 || node >= (int)CG.nodes.size() || CG.nodes[node].type != 2) return false;

    vector<int> newA = A;
    vector<int> newB = B;
    newA.erase(newA.begin() + pos_from);
    newB.insert(newB.begin() + insert_pos, node);
    normalize_route(newA, depot);
    normalize_route(newB, depot);

    if (!granular_route_basic_ok(newA, CG, depot) || !granular_route_basic_ok(newB, CG, depot)) return false;
    if (cfg.use_time_window &&
        (!route_hard_tw_feasible(newA, ev, pm) || !route_hard_tw_feasible(newB, ev, pm))) return false;

    RouteMetrics mA = ev.compute_route_metrics(newA, 0.0);
    RouteMetrics mB = ev.compute_route_metrics(newB, 0.0);
    const double old_pair = state.route_metrics[r_from].weighted_cost + state.route_metrics[r_to].weighted_cost;
    const double new_pair = mA.weighted_cost + mB.weighted_cost;

    out.type = GranularTabuMove::RELOCATE;
    out.r1 = r_from; out.p1 = pos_from;
    out.r2 = r_to;   out.p2 = insert_pos;
    out.a = node; out.b = -1;
    out.delta = new_pair - old_pair;
    out.new_obj = state.objective + out.delta;
    out.new_r1 = std::move(newA);
    out.new_r2 = std::move(newB);
    return true;
}

static bool try_build_granular_swap(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    int r1,
    int p1,
    int r2,
    int p2,
    GranularTabuMove &out,
    PairwiseManager &pm
) {
    if (r1 == r2) return false;

    const Compressed &CG = *ev.CG;
    int depot = find_depot_idx(CG);
    if (r1 < 0 || r2 < 0 || r1 >= (int)state.routes.size() || r2 >= (int)state.routes.size()) return false;

    const vector<int> &A = state.routes[r1];
    const vector<int> &B = state.routes[r2];
    if (p1 <= 0 || p1 + 1 >= (int)A.size() || p2 <= 0 || p2 + 1 >= (int)B.size()) return false;

    int a = A[p1], b = B[p2];
    if (a < 0 || a >= (int)CG.nodes.size() || b < 0 || b >= (int)CG.nodes.size()) return false;
    if (CG.nodes[a].type != 2 || CG.nodes[b].type != 2) return false;

    vector<int> newA = A;
    vector<int> newB = B;
    newA[p1] = b;
    newB[p2] = a;
    normalize_route(newA, depot);
    normalize_route(newB, depot);

    if (!granular_route_basic_ok(newA, CG, depot) || !granular_route_basic_ok(newB, CG, depot)) return false;
    if (cfg.use_time_window &&
        (!route_hard_tw_feasible(newA, ev, pm) || !route_hard_tw_feasible(newB, ev, pm))) return false;

    RouteMetrics mA = ev.compute_route_metrics(newA, 0.0);
    RouteMetrics mB = ev.compute_route_metrics(newB, 0.0);
    const double old_pair = state.route_metrics[r1].weighted_cost + state.route_metrics[r2].weighted_cost;
    const double new_pair = mA.weighted_cost + mB.weighted_cost;

    out.type = GranularTabuMove::SWAP;
    out.r1 = r1; out.p1 = p1;
    out.r2 = r2; out.p2 = p2;
    out.a = a; out.b = b;
    out.delta = new_pair - old_pair;
    out.new_obj = state.objective + out.delta;
    out.new_r1 = std::move(newA);
    out.new_r2 = std::move(newB);
    return true;
}

static bool granular_tabu_repair(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!cfg.use_granular_tabu) return false;
    profile.granular_tabu_calls.fetch_add(1, memory_order_relaxed);
    const auto granular_t0 = Clock::now();
    if (cfg.granular_tabu_iters <= 0) return false;

    const Compressed &CG = *ev.CG;
    int R = (int)state.routes.size();

    if (R <= 1) return false;

    mt19937 rng(cfg.base_seed ^ 0xBADC0FFEu ^ (unsigned)(state.objective * 1000.0));
    uniform_int_distribution<int> tenure_dist(
        max(1, cfg.granular_tabu_tenure_min),
        max(cfg.granular_tabu_tenure_min, cfg.granular_tabu_tenure_max)
    );

    vector<vector<int>> tabu_until(
        CG.nodes.size(),
        vector<int>(R, 0)
    );

    double start_obj = state.objective;
    double global_best_obj = state.objective;

    SolutionState global_best = state;

    int accepted = 0;
    int improving = 0;
    int worsening = 0;
    int attempted = 0;
    int tabu_skipped = 0;

    for (int iter = 1; iter <= cfg.granular_tabu_iters; ++iter) {
        if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); break; }
        vector<BoundaryPairSignal> signals = build_boundary_signals(
            state,
            ev,
            pm,
            cfg.granular_tabu_top_pairs
        );

        if (signals.empty()) {
            vector<pair<int, int>> pairs = boundary_pair_rank_pairs(state, ev, pm);

            for (auto [ra, rb] : pairs) {
                BoundaryPairSignal s;
                s.ra = ra;
                s.rb = rb;
                s.score = 0.0;
                signals.push_back(std::move(s));

                if ((int)signals.size() >= cfg.granular_tabu_top_pairs) break;
            }
        }

        if (signals.empty()) break;

        GranularTabuMove best_move;
        bool found = false;
        bool stop_scan = false;

        for (const auto &sig : signals) {
            if (stop_scan) break;
            int ra = sig.ra;
            int rb = sig.rb;

            if (ra < 0 || rb < 0 || ra >= R || rb >= R || ra == rb) continue;
            if ((int)state.routes[ra].size() <= 2) continue;
            if ((int)state.routes[rb].size() <= 2) continue;

            vector<int> A_nodes = granular_nodes_for_pair(state, sig, ra, CG, pm);
            vector<int> B_nodes = granular_nodes_for_pair(state, sig, rb, CG, pm);

            if (A_nodes.empty()) {
                for (int x : state.routes[ra]) {
                    if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) {
                        A_nodes.push_back(x);
                    }
                }
            }

            if (B_nodes.empty()) {
                for (int x : state.routes[rb]) {
                    if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) {
                        B_nodes.push_back(x);
                    }
                }
            }

            if ((int)A_nodes.size() > cfg.granular_tabu_candidate_cap) {
                A_nodes.resize(cfg.granular_tabu_candidate_cap);
            }

            if ((int)B_nodes.size() > cfg.granular_tabu_candidate_cap) {
                B_nodes.resize(cfg.granular_tabu_candidate_cap);
            }

            auto eval_move = [&](GranularTabuMove &&mv) {
                attempted++;

                bool tabu = false;

                if (mv.type == GranularTabuMove::RELOCATE) {
                    tabu = is_tabu_customer_route(tabu_until, mv.a, mv.r2, iter);
                }
                else {
                    tabu =
                        is_tabu_customer_route(tabu_until, mv.a, mv.r2, iter) ||
                        is_tabu_customer_route(tabu_until, mv.b, mv.r1, iter);
                }

                bool aspiration = mv.new_obj + 1e-9 < global_best_obj;

                if (tabu && !aspiration) {
                    tabu_skipped++;
                    return;
                }

                bool acceptable =
                    mv.delta < -1e-9 ||
                    (
                        cfg.granular_tabu_allow_worsen &&
                        mv.delta <= cfg.granular_tabu_worsen_cap
                    );

                if (!acceptable && !aspiration) return;

                if (!found || mv.new_obj + 1e-9 < best_move.new_obj) {
                    best_move = std::move(mv);
                    found = true;
                }
            };

            // Relocate A -> B.
            for (int a : A_nodes) {
                int pa = find_pos_in_route(state.routes[ra], a);
                if (pa <= 0) continue;

                int max_pos_b = (int)state.routes[rb].size() - 1;

                for (int ins = 1; ins <= max_pos_b; ++ins) {
                    if ((attempted & 63) == 0 && solver_should_stop()) { stop_scan = true; break; }
                    GranularTabuMove mv;

                    if (try_build_granular_relocate(
                            state,
                            ev,
                            ra,
                            pa,
                            rb,
                            ins,
                            mv,
                            pm
                        )) {
                        eval_move(std::move(mv));
                    }
                }
            }

            // Relocate B -> A.
            for (int b : B_nodes) {
                int pb = find_pos_in_route(state.routes[rb], b);
                if (pb <= 0) continue;

                int max_pos_a = (int)state.routes[ra].size() - 1;

                for (int ins = 1; ins <= max_pos_a; ++ins) {
                    if ((attempted & 63) == 0 && solver_should_stop()) { stop_scan = true; break; }
                    GranularTabuMove mv;

                    if (try_build_granular_relocate(
                            state,
                            ev,
                            rb,
                            pb,
                            ra,
                            ins,
                            mv,
                            pm
                        )) {
                        eval_move(std::move(mv));
                    }
                }
            }

            // Swap A <-> B.
            for (int a : A_nodes) {
                int pa = find_pos_in_route(state.routes[ra], a);
                if (pa <= 0) continue;

                for (int b : B_nodes) {
                    if ((attempted & 63) == 0 && solver_should_stop()) { stop_scan = true; break; }
                    int pb = find_pos_in_route(state.routes[rb], b);
                    if (pb <= 0) continue;

                    GranularTabuMove mv;

                    if (try_build_granular_swap(
                            state,
                            ev,
                            ra,
                            pa,
                            rb,
                            pb,
                            mv,
                            pm
                        )) {
                        eval_move(std::move(mv));
                    }
                }
            }
        }

        if (!found) {
            break;
        }

        // Mark reverse ownership as tabu.
        int tenure = tenure_dist(rng);
        int until = iter + tenure;

        if (best_move.type == GranularTabuMove::RELOCATE) {
            mark_tabu_customer_route(
                tabu_until,
                best_move.a,
                best_move.r1,
                until
            );
        }
        else {
            mark_tabu_customer_route(
                tabu_until,
                best_move.a,
                best_move.r1,
                until
            );

            mark_tabu_customer_route(
                tabu_until,
                best_move.b,
                best_move.r2,
                until
            );
        }

        // V36: apply only the two modified routes, then refresh exactly those
        // route caches plus global served_count. No full-state candidate copy.
        state.routes[best_move.r1] = std::move(best_move.new_r1);
        state.routes[best_move.r2] = std::move(best_move.new_r2);
        recompute_dirty_routes(state, ev, {best_move.r1, best_move.r2});
        accepted++;

        if (best_move.delta < -1e-9) improving++;
        else worsening++;

        if (state.objective + 1e-9 < global_best_obj) {
            global_best_obj = state.objective;
            global_best = state;
            update_global_best_checked(global_best, CG, pm);
        }

        // Every few iterations, refresh exactly to avoid drift.
        if ((iter % 50) == 0) {
            recompute_state_metrics_and_loads(state, ev);
        }
    }

    if (global_best.objective + 1e-9 < state.objective) {
        state = global_best;
    }

    recompute_state_metrics_and_loads(state, ev);

    double gain = start_obj - state.objective;
    const long long granular_us = chrono::duration_cast<chrono::microseconds>(Clock::now() - granular_t0).count();
    profile.granular_tabu_candidate_evals.fetch_add(attempted, memory_order_relaxed);
    profile.granular_tabu_accepted_moves.fetch_add(accepted, memory_order_relaxed);
    profile.granular_tabu_time_us.fetch_add(granular_us, memory_order_relaxed);

    if (cfg.granular_tabu_verbose) {
        cerr << "[GranularTabu]"
            << " start=" << start_obj
            << " end=" << state.objective
            << " gain=" << max(0.0, gain)
            << " accepted=" << accepted
            << " improving=" << improving
            << " worsening=" << worsening
            << " attempted=" << attempted
            << " tabu_skipped=" << tabu_skipped
            << " iters=" << cfg.granular_tabu_iters
            << " top_pairs=" << cfg.granular_tabu_top_pairs
            << " time_s=" << (double)granular_us / 1e6
            << "\n";
    }

    return gain > 1e-9;
}

/* ---------------- Cluster warm start ---------------- */

static string trim_copy(string s) {
    auto is_space = [](unsigned char c) {
        return std::isspace(c);
    };

    while (!s.empty() && is_space((unsigned char)s.front())) {
        s.erase(s.begin());
    }

    while (!s.empty() && is_space((unsigned char)s.back())) {
        s.pop_back();
    }

    return s;
}

static bool file_exists_simple(const string &path) {
    ifstream f(path);
    return f.good();
}

static unordered_map<int, int> load_clusters_csv_map(const string &path) {
    unordered_map<int, int> mp;

    ifstream in(path);
    if (!in.good()) {
        cerr << "[clusters] file not found: " << path << "\n";
        return mp;
    }

    string line;
    bool first = true;

    while (getline(in, line)) {
        line = trim_copy(line);
        if (line.empty()) continue;

        for (char &c : line) {
            if (c == ';' || c == '\t') c = ',';
        }

        string lower = line;
        transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

        if (first) {
            first = false;
            if (lower.find("node") != string::npos &&
                lower.find("cluster") != string::npos) {
                continue;
            }
        }

        stringstream ss(line);
        string a, b;

        if (!getline(ss, a, ',')) continue;
        if (!getline(ss, b, ',')) continue;

        a = trim_copy(a);
        b = trim_copy(b);

        try {
            int node = stoi(a);
            int cluster = stoi(b);
            mp[node] = cluster;
        } catch (...) {
            cerr << "[clusters] skip bad line: " << line << "\n";
        }
    }

    cerr << "[clusters] loaded assignments=" << mp.size()
        << " from " << path << "\n";

    return mp;
}

// Insert a customer while preserving the native route contract immediately.
// Cluster files describe membership, not visit order; appending rows in CSV
// order can violate directed-road reachability, time windows, or trip limits.
// This routine evaluates every legal position on the requested routes and
// commits only a route that is hard-feasible under the active solver flags.
static bool insert_customer_hard_on_routes(
    SolutionState &state,
    int node,
    const vector<int> &candidate_routes,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const Compressed &CG = *ev.CG;
    int depot = depot_of(ev);
    double best_delta = INF_D;
    int best_route_id = -1;
    vector<int> best_route;

    for (int route_id : candidate_routes) {
        if (route_id < 0 || route_id >= (int)state.routes.size()) continue;

        vector<int> base = state.routes[route_id];
        normalize_route(base, depot);
        enforce_trip_separators(base, CG, depot);
        // normalize_route intentionally removes consecutive depots.  For an
        // empty vehicle that leaves a single depot node, but insertion needs a
        // start and end boundary so position 1 is legal.
        if (base.size() < 2) {
            base = {depot, depot};
        }
        double old_cost = route_exact_cost(base, ev);

        for (int pos = 1; pos < (int)base.size(); ++pos) {
            vector<int> candidate = base;
            candidate.insert(candidate.begin() + pos, node);
            normalize_route(candidate, depot);
            enforce_trip_separators(candidate, CG, depot);

            if (!trips_feasible_for_route(candidate, CG, depot)) continue;
            if (cfg.max_trips_per_truck > 0 &&
                count_nonempty_trips_in_route(candidate, CG) > cfg.max_trips_per_truck) {
                continue;
            }
            if (!route_hard_tw_feasible(candidate, ev, pm)) continue;

            double delta = route_exact_cost(candidate, ev) - old_cost;
            if (delta < best_delta) {
                best_delta = delta;
                best_route_id = route_id;
                best_route = std::move(candidate);
            }
        }
    }

    if (best_route_id < 0) return false;
    state.routes[best_route_id] = std::move(best_route);
    return true;
}

static bool build_cluster_warm_start_solution(
    SolutionState &state,
    const vector<int> &collections,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!cfg.use_cluster_warm_start) {
        return false;
    }

    // The main thread resolves the cluster seed before SA workers launch.  A
    // process-local cache prevents every cold worker from repeating the same
    // membership parsing and hard insertion search.  The mutex also keeps this
    // correct if a future call site reaches the builder concurrently.
    static mutex cache_mutex;
    static bool cache_resolved = false;
    static bool cache_accepted = false;
    static string cache_reason = "not_resolved";
    static SolutionState cache_state;
    unique_lock<mutex> cache_lock(cache_mutex);
    if (cache_resolved) {
        if (cache_accepted) state = cache_state;
        cerr << "[ClusterWarmStartReceipt] requested=true"
            << " accepted=" << (cache_accepted ? "true" : "false")
            << " hard_feasible=" << (cache_accepted ? "true" : "false")
            << " reason=" << cache_reason
            << " source=certified_process_cache"
            << " fallback=" << (cache_accepted ? "none" : "greedy_savings")
            << "\n";
        return cache_accepted;
    }

    auto cache_rejection = [&](const string &reason) {
        cache_resolved = true;
        cache_accepted = false;
        cache_reason = reason;
        cache_state = SolutionState();
    };

    if (!file_exists_simple(cfg.clusters_csv)) {
        cerr << "[clusters] disabled: missing " << cfg.clusters_csv << "\n";
        cerr << "[ClusterWarmStartReceipt] requested=true accepted=false"
            << " hard_feasible=false reason=missing_clusters_csv"
            << " fallback=greedy_savings\n";
        cache_rejection("missing_clusters_csv");
        return false;
    }

    int depot = depot_of(ev);
    unordered_map<int, int> cluster_of = load_clusters_csv_map(cfg.clusters_csv);

    if (cluster_of.empty()) {
        cerr << "[clusters] disabled: no assignments loaded\n";
        cerr << "[ClusterWarmStartReceipt] requested=true accepted=false"
            << " hard_feasible=false reason=no_assignments"
            << " fallback=greedy_savings\n";
        cache_rejection("no_assignments");
        return false;
    }

    state = SolutionState(cfg.num_trucks, ev.CG->nodes.size());

    for (int r = 0; r < cfg.num_trucks; ++r) {
        state.routes[r] = {depot, depot};
    }

    vector<vector<int>> assigned_by_route(cfg.num_trucks);
    vector<int> leftovers;
    int assigned_requested = 0;

    for (int node : collections) {
        auto it = cluster_of.find(node);

        if (it == cluster_of.end()) {
            leftovers.push_back(node);
            continue;
        }

        int cluster = it->second;

        if (cluster < 0 || cluster >= cfg.num_trucks) {
            leftovers.push_back(node);
            continue;
        }

        assigned_by_route[cluster].push_back(node);
        assigned_requested++;
    }

    auto deadline_order = [&](int a, int b) {
        const auto &na = ev.CG->nodes[a];
        const auto &nb = ev.CG->nodes[b];
        if (na.latest != nb.latest) return na.latest < nb.latest;
        if (na.earliest != nb.earliest) return na.earliest < nb.earliest;
        return a < b;
    };

    int assigned_kept = 0;
    for (int route_id = 0; route_id < cfg.num_trucks; ++route_id) {
        auto &bucket = assigned_by_route[route_id];
        stable_sort(bucket.begin(), bucket.end(), deadline_order);
        const vector<int> designated_route = {route_id};
        for (int node : bucket) {
            if (insert_customer_hard_on_routes(
                    state, node, designated_route, ev, pm)) {
                assigned_kept++;
            } else {
                leftovers.push_back(node);
            }
        }
    }

    stable_sort(leftovers.begin(), leftovers.end(), deadline_order);
    vector<int> all_routes(cfg.num_trucks);
    iota(all_routes.begin(), all_routes.end(), 0);
    int globally_inserted = 0;
    for (int node : leftovers) {
        bool ok = insert_customer_hard_on_routes(
            state, node, all_routes, ev, pm);
        if (!ok) {
            cerr << "[clusters] failed to insert leftover node " << node << "\n";
            cerr << "[ClusterWarmStartReceipt] requested=true accepted=false"
                << " hard_feasible=false reason=hard_insertion_failed"
                << " node=" << node
                << " assigned_requested=" << assigned_requested
                << " assigned_kept=" << assigned_kept
                << " fallback=greedy_savings\n";
            cache_rejection("hard_insertion_failed");
            return false;
        }
        globally_inserted++;
    }

    recompute_state_metrics_and_loads(state, ev);

    if (!solution_hard_feasible(state, *ev.CG, pm)) {
        cerr << "[clusters] rejected: native hard-feasibility gate failed\n";
        cerr << "[ClusterWarmStartReceipt] requested=true accepted=false"
            << " hard_feasible=false reason=final_native_gate_failed"
            << " assigned_requested=" << assigned_requested
            << " assigned_kept=" << assigned_kept
            << " globally_inserted=" << globally_inserted
            << " fallback=greedy_savings\n";
        cache_rejection("final_native_gate_failed");
        return false;
    }

    cerr << "[clusters] warm start OK"
        << " assigned=" << assigned_kept
        << " leftovers=" << leftovers.size()
        << " objective=" << state.objective
        << "\n";
    cerr << "[ClusterWarmStartReceipt] requested=true accepted=true"
        << " hard_feasible=true reason=accepted"
        << " assigned_requested=" << assigned_requested
        << " assigned_kept=" << assigned_kept
        << " globally_inserted=" << globally_inserted
        << " objective=" << state.objective
        << " fallback=none\n";

    cache_resolved = true;
    cache_accepted = true;
    cache_reason = "accepted";
    cache_state = state;

    return true;
}

[[maybe_unused]] static void two_opt_trip_segment(
    vector<int> &route,
    int L,
    int R,
    PairwiseManager &pm,
    const Compressed &CG
) {
    if (R - L + 1 <= 3) return;

    bool improved = true;

    while (improved) {
        improved = false;

        for (int i = L + 1; i < R - 1; ++i) {
            for (int k = i + 1; k < R; ++k) {
                int a = route[i - 1];
                int b = route[i];
                int c = route[k];
                int d = route[k + 1];

                // Euclidean branch cut:
                // In metric space, most useful 2-opt reconnects use near edges.
                // Do not apply this to road/direct.
                if (euclidean_cuts_enabled() && cfg.euclidean_candidate_2opt_cut) {
                    bool has_depot =
                        CG.nodes[a].type == 1 ||
                        CG.nodes[b].type == 1 ||
                        CG.nodes[c].type == 1 ||
                        CG.nodes[d].type == 1;

                    if (!has_depot) {
                        if (!euclidean_candidate_edge_ok(a, c) &&
                            !euclidean_candidate_edge_ok(b, d)) {
                            continue;
                        }
                    }
                }

                double ab = fast_pair_dist(a, b, &pm);
                double cd = fast_pair_dist(c, d, &pm);
                double ac = fast_pair_dist(a, c, &pm);
                double bd = fast_pair_dist(b, d, &pm);

                if (!isfinite(ab) || !isfinite(cd) || !isfinite(ac) || !isfinite(bd)) {
                    continue;
                }

                [[maybe_unused]] bool crossing = false;

                if (euclidean_cuts_enabled() && cfg.euclidean_uncross_routes) {
                    crossing = segments_cross_strict(
                        CG.nodes[a],
                        CG.nodes[b],
                        CG.nodes[c],
                        CG.nodes[d]
                    );
                }

                // Trustworthy rule:
                // We only reverse if exact route edge delta improves.
                // Crossing only prioritizes candidate checks; it does not force unsafe moves.
                if (ac + bd + 1e-9 < ab + cd) {
                    reverse(route.begin() + i, route.begin() + k + 1);
                    improved = true;

                    // Restart after first change to avoid stale indices.
                    goto next_pass;
                }
            }
        }

        next_pass:
        ;
    }
}

static void two_opt_multi_trip_route(
    vector<int> &route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const Compressed &CG,
    int depot
) {
    normalize_route(route, depot);
    enforce_trip_separators(route, CG, depot);
    if (!cfg.use_2opt) return;

    vector<int> dep;
    for (int i = 0; i < (int)route.size(); ++i) {
        if (route[i] == depot) dep.push_back(i);
    }
    if (dep.size() < 2) return;

    double current_exact = route_exact_cost(route, ev);

    for (int trip = 0; trip + 1 < (int)dep.size(); ++trip) {
        int L = dep[trip];
        int R = dep[trip + 1];
        if (R - L < 3) continue;

        bool improved = true;
        int moves = 0;

        while (improved && moves < cfg.insertion_pos_cap) {
            if (solver_should_stop()) {
                profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed);
                return;
            }
            improved = false;

            // V20: on a directed/asymmetric metric, reversing [a,b] changes every
            // internal arc direction, not just the two boundary arcs. The legacy
            // boundary-only gate could therefore reject a truly improving 2-opt.
            // Precompute the exact directed reversal contribution for O(1) gates.
            vector<double> rev_prefix(route.size(), 0.0);
            if (!metric_is_symmetric()) {
                for (int k = L + 1; k < R; ++k) {
                    int x = route[k];
                    int y = route[k + 1];
                    double xy = fast_pair_search_cost(x, y, &pm);
                    double yx = fast_pair_search_cost(y, x, &pm);
                    double term = (isfinite(xy) && isfinite(yx)) ? (yx - xy) : INF_D;
                    rev_prefix[k + 1] = rev_prefix[k] + term;
                }
            }

            for (int a = L + 1; a < R - 1 && !improved; ++a) {
                for (int b = a + 1; b < R; ++b) {
                    int u1 = route[a - 1];
                    int v1 = route[a];
                    int u2 = route[b];
                    int v2 = route[b + 1];

                    double before =
                        fast_pair_search_cost(u1, v1, &pm) +
                        fast_pair_search_cost(u2, v2, &pm);
                    double after =
                        fast_pair_search_cost(u1, u2, &pm) +
                        fast_pair_search_cost(v1, v2, &pm);

                    if (!isfinite(before) || !isfinite(after)) continue;

                    double exact_edge_delta = after - before;
                    if (!metric_is_symmetric()) {
                        profile.asymmetric_2opt_candidates.fetch_add(1, memory_order_relaxed);
                        double internal = rev_prefix[b] - rev_prefix[a];
                        if (!isfinite(internal)) continue;
                        exact_edge_delta += internal;
                    }

                    // This gate is now exact for the distance contribution of the
                    // reversed directed path. Hard TW feasibility and the complete
                    // configured route objective are still verified below.
                    if (!(exact_edge_delta < -1e-9)) continue;

                    vector<int> cand = route;
                    reverse(cand.begin() + a, cand.begin() + b + 1);
                    normalize_route(cand, depot);
                    enforce_trip_separators(cand, CG, depot);
                    if (!trips_feasible_for_route(cand, CG, depot)) continue;
                    if (cfg.use_time_window && !route_hard_tw_feasible(cand, ev, pm)) continue;

                    double candidate_exact = route_exact_cost(cand, ev);
                    if (candidate_exact + 1e-9 < current_exact) {
                        route.swap(cand);
                        current_exact = candidate_exact;
                        improved = true;
                        moves++;
                        if (!metric_is_symmetric()) {
                            profile.asymmetric_2opt_improvements.fetch_add(1, memory_order_relaxed);
                        }
                        break;
                    }
                }
            }
        }
    }
}

static void or_opt_k_route(vector<int> &route, int k, ObjectiveEvaluator &ev, PairwiseManager &pm, const Compressed &CG, int depot) {
    (void)pm;
    normalize_route(route, depot);
    enforce_trip_separators(route, CG, depot);
    if ((int)route.size() <= k + 2) return;

    // Perform a bounded, first-improvement OR-opt. Stops after a limited number of improving moves
    // to avoid O(n^3) scanning. Controlled by cfg.use_oropt.
    if (!cfg.use_oropt) return;
    int max_moves = cfg.insertion_pos_cap; // reuse insertion_pos_cap as a simple bound
    int moves = 0;
    double cur_cost = route_exact_cost(route, ev);
    bool improved = true;
    while (improved && moves < max_moves) {
        if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); return; }
        improved = false;
        for (int i = 1; i + k <= (int)route.size() - 1 && moves < max_moves; ++i) {
            bool block_is_customers = true;
            for (int q = i; q < i + k; ++q) {
                int nid = route[q];
                if (nid < 0 || nid >= (int)CG.nodes.size() || CG.nodes[nid].type != 2) {
                    block_is_customers = false;
                    break;
                }
            }
            if (!block_is_customers) continue;
            for (int j = 1; j <= (int)route.size() - 1 && moves < max_moves; ++j) {
                if (j >= i && j <= i + k) continue;
                vector<int> cand = route;
                vector<int> block(cand.begin() + i, cand.begin() + i + k);
                cand.erase(cand.begin() + i, cand.begin() + i + k);
                int insert_pos = j;
                if (j > i) insert_pos -= k;
                insert_pos = max(1, min(insert_pos, (int)cand.size() - 1));
                cand.insert(cand.begin() + insert_pos, block.begin(), block.end());
                normalize_route(cand, depot);
                enforce_trip_separators(cand, CG, depot);
                if (!trips_feasible_for_route(cand, CG, depot)) continue;
                double cc = route_exact_cost(cand, ev);
                if (cc + 1e-9 < cur_cost) {
                    // first improvement
                    route.swap(cand);
                    cur_cost = cc;
                    improved = true;
                    moves++;
                    break;
                }
            }
            if (improved) break;
        }
    }
}

static void relocate_route_local_best(vector<int> &route, ObjectiveEvaluator &ev, PairwiseManager &pm, const Compressed &CG, int depot) {
    (void)pm;
    normalize_route(route, depot);
    enforce_trip_separators(route, CG, depot);
    // Bounded relocate: stops after a limited number of improving moves to avoid cubic behaviour.
    if (!cfg.use_relocate_polish) return;
    int moves = 0;
    double cur_cost = route_exact_cost(route, ev);
    bool improved = true;
    while (improved && moves < cfg.insertion_pos_cap) {
        if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); return; }
        improved = false;
        for (int i = 1; i + 1 < (int)route.size() && moves < cfg.insertion_pos_cap; ++i) {
            int node = route[i];
            if (node < 0 || node >= (int)CG.nodes.size() || CG.nodes[node].type != 2) {
                continue;
            }
            for (int j = 1; j < (int)route.size() && moves < cfg.insertion_pos_cap; ++j) {
                if (j == i || j == i + 1) continue;
                vector<int> cand = route;
                cand.erase(cand.begin() + i);
                int pos = j;
                if (j > i) pos--;
                cand.insert(cand.begin() + pos, node);
                normalize_route(cand, depot);
                enforce_trip_separators(cand, CG, depot);
                if (!trips_feasible_for_route(cand, CG, depot)) continue;
                double cc = route_exact_cost(cand, ev);
                if (cc + 1e-9 < cur_cost) {
                    route.swap(cand);
                    cur_cost = cc;
                    improved = true;
                    moves++;
                    break;
                }
            }
            if (improved) break;
        }
    }
}

struct TopoBranchStats {
    double start_obj = 0.0;
    double end_obj = 0.0;
    double gain = 0.0;
    int accepted = 0;
    int attempted = 0;
    int removed_total = 0;
    double time_s = 0.0;
};

[[maybe_unused]] static vector<int> customers_in_route_set(
    const vector<int> &route,
    const Compressed &CG
) {
    vector<int> out;
    for (int nid : route) {
        if (nid >= 0 && nid < (int)CG.nodes.size() && CG.nodes[nid].type == 2) {
            out.push_back(nid);
        }
    }
    return out;
}

[[maybe_unused]] static bool remove_customer_set_from_state(
    SolutionState &state,
    const unordered_set<int> &removed,
    const Compressed &CG
) {
    if (removed.empty()) return false;

    for (auto &route : state.routes) {
        vector<int> out;
        out.reserve(route.size());

        for (int nid : route) {
            if (CG.nodes[nid].type == 2 && removed.count(nid)) {
                continue;
            }
            out.push_back(nid);
        }

        route.swap(out);
    }

    return true;
}

static void local_polish_solution(SolutionState &state, ObjectiveEvaluator &ev, PairwiseManager &pm) {
    int depot = depot_of(ev);
    for (auto &r : state.routes) {
        if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); break; }
        normalize_route(r, depot);
        enforce_trip_separators(r, *ev.CG, depot);
        relocate_route_local_best(r, ev, pm, *ev.CG, depot);
        or_opt_k_route(r, 2, ev, pm, *ev.CG, depot);
        or_opt_k_route(r, 3, ev, pm, *ev.CG, depot);
        two_opt_multi_trip_route(r, ev, pm, *ev.CG, depot);
    }
    if (euclidean_cuts_enabled()) {
        euclidean_branch_polish_solution(state, ev, pm);
    }
    recompute_state_metrics_and_loads(state, ev);
}

struct InsertionOption {
    int r = -1;
    int pos = -1;
    double cost = INF_D;
};

static vector<InsertionOption> collect_insertion_options(
    const SolutionState &state,
    int node,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    RepairWorkStats *stats,
    bool full_scan
) {
    vector<InsertionOption> opts;
    int depot = depot_of(ev);

    vector<int> route_ids;
    if (full_scan) {
        route_ids.resize(state.routes.size());
        iota(route_ids.begin(), route_ids.end(), 0);
    }
    else {
        route_ids = get_best_routes_for_node(
            state.routes, pm, node, max(1, cfg.insertion_route_cap)
        );
    }

    for (int r : route_ids) {
        if (r < 0 || r >= (int)state.routes.size()) continue;
        const auto &route = state.routes[r];
        if (route.size() < 2) continue;

        if (stats) {
            stats->candidate_routes_examined++;
            stats->exact_route_evaluations++;
        }
        double old_cost = route_exact_cost(route, ev);
        if (!isfinite(old_cost)) continue;

        const int max_pos = full_scan
            ? (int)route.size() - 1
            : min(
                (int)route.size() - 1,
                max(1, cfg.insertion_pos_cap)
            );

        for (int pos = 1; pos <= max_pos; ++pos) {
            if (stats) stats->positions_ranked++;

            vector<int> cand = route;
            cand.insert(cand.begin() + pos, node);
            normalize_route(cand, depot);
            enforce_trip_separators(cand, *ev.CG, depot);
            if (!trips_feasible_for_route(cand, *ev.CG, depot)) continue;

            bool hard_filter_insert =
                cfg.use_time_window &&
                cfg.tw_strict_insertion &&
                !cfg.tw_allow_soft_intermediate;

            if (hard_filter_insert && !route_hard_tw_feasible(cand, ev, pm)) {
                continue;
            }

            if (stats) stats->exact_route_evaluations++;
            double new_cost = route_exact_cost(cand, ev);
            if (!isfinite(new_cost)) continue;

            opts.push_back({r, pos, new_cost - old_cost});
        }
    }

    sort(opts.begin(), opts.end(), [](const InsertionOption &a, const InsertionOption &b) {
        if (a.cost != b.cost) return a.cost < b.cost;
        if (a.r != b.r) return a.r < b.r;
        return a.pos < b.pos;
    });

    return opts;
}

static bool apply_insertion_option(
    SolutionState &state,
    int node,
    const InsertionOption &choice,
    ObjectiveEvaluator &ev
) {
    if (choice.r < 0 || choice.pos < 0) return false;
    if (choice.r >= (int)state.routes.size()) return false;

    int depot = depot_of(ev);
    auto &route = state.routes[choice.r];

    int pos = choice.pos;
    pos = max(1, min(pos, (int)route.size() - 1));

    route.insert(route.begin() + pos, node);
    normalize_route(route, depot);
    enforce_trip_separators(route, *ev.CG, depot);
    return true;
}

static bool insert_customer_best_place_exact(
    SolutionState &state,
    int node,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    RepairWorkStats *stats
) {
    auto opts = collect_insertion_options(
        state, node, ev, pm, stats, true
    );
    if (opts.empty()) return false;
    return apply_insertion_option(state, node, opts.front(), ev);
}

static void regret_repair_remaining_nodes(
    SolutionState &cur,
    vector<int> &remaining,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int regret_k,
    RepairWorkStats *stats,
    bool full_scan
) {
    vector<int> unplaced = remaining;
    remaining.clear();

    while (!unplaced.empty()) {
        int pick_idx = -1;
        InsertionOption pick_choice;
        double best_regret = -INF_D;
        double best_best_cost = INF_D;

        for (int i = 0; i < (int)unplaced.size(); ++i) {
            int node = unplaced[i];
            auto opts = collect_insertion_options(
                cur, node, ev, pm, stats, full_scan
            );
            if (opts.empty()) continue;

            int kk = min((int)opts.size(), max(2, regret_k));
            double regret = 0.0;

            if ((int)opts.size() == 1) {
                regret = 1e12;
            }
            else {
                regret = opts[kk - 1].cost - opts[0].cost;
            }

            if (regret > best_regret + 1e-9 ||
                (fabs(regret - best_regret) <= 1e-9 &&
                opts[0].cost < best_best_cost)) {
                best_regret = regret;
                best_best_cost = opts[0].cost;
                pick_idx = i;
                pick_choice = opts[0];
            }
        }

        if (pick_idx == -1) break;

        int node = unplaced[pick_idx];
        if (!apply_insertion_option(cur, node, pick_choice, ev)) break;

        if (stats) stats->customers_inserted++;
        unplaced.erase(unplaced.begin() + pick_idx);
    }

    remaining = std::move(unplaced);
}

static RepairMode effective_repair_mode() {
    if (tls_repair_mode_override_enabled) return tls_repair_mode_override;
    if (cfg.repair_mode != RepairMode::LEGACY) {
        return cfg.repair_mode;
    }

    if (!cfg.use_regret_repair) {
        return RepairMode::GREEDY_FAST;
    }

    if (cfg.regret_k == 2) return RepairMode::REGRET_2;
    if (cfg.regret_k == 3) return RepairMode::REGRET_3;
    return RepairMode::REGRET_K;
}

static int effective_regret_k(RepairMode mode) {
    if (mode == RepairMode::REGRET_2) return 2;
    if (mode == RepairMode::REGRET_3) return 3;
    return max(2, cfg.regret_k);
}

static bool repair_removed_customers(
    SolutionState &cur,
    vector<int> &remaining,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int destroy_mode,
    double base_objective
) {
    const RepairMode mode = effective_repair_mode();
    const long long call_id =
        repair_profile.calls.fetch_add(1, memory_order_relaxed) + 1;

    RepairWorkStats work;
    work.customers_requested = remaining.size();

    const auto t0 = Clock::now();

    if (mode == RepairMode::GREEDY_FAST ||
        mode == RepairMode::GREEDY_EXACT) {
        sort(remaining.begin(), remaining.end(), [&](int a, int b) {
            const double da = ev.CG->nodes[a].garbage_amount;
            const double db = ev.CG->nodes[b].garbage_amount;
            if (fabs(da - db) > 1e-12) return da > db;
            return a < b;
        });

        vector<int> failed;
        failed.reserve(remaining.size());

        for (int node : remaining) {
            bool ok = false;

            if (mode == RepairMode::GREEDY_FAST) {
                ok = insert_customer_best_place_fast(cur, node, ev, pm, &work);
            }
            else {
                ok = insert_customer_best_place_exact(cur, node, ev, pm, &work);
            }

            if (ok) {
                work.customers_inserted++;
            }
            else {
                failed.push_back(node);
            }
        }

        remaining.swap(failed);
    }
    else {
        const bool full_scan =
            cfg.lns_benchmark_mode &&
            cfg.lns_benchmark_full_scan_exact_repairs;

        regret_repair_remaining_nodes(
            cur,
            remaining,
            ev,
            pm,
            effective_regret_k(mode),
            &work,
            full_scan
        );
    }

    recompute_state_metrics_and_loads(cur, ev);

    const bool success = remaining.empty();
    const long long elapsed_us = chrono::duration_cast<chrono::microseconds>(
        Clock::now() - t0
    ).count();

    if (success) {
        repair_profile.successful_calls.fetch_add(1, memory_order_relaxed);
    }
    else {
        repair_profile.failed_calls.fetch_add(1, memory_order_relaxed);
    }

    repair_profile.customers_requested.fetch_add(
        (long long)work.customers_requested, memory_order_relaxed
    );
    repair_profile.customers_inserted.fetch_add(
        (long long)work.customers_inserted, memory_order_relaxed
    );
    repair_profile.candidate_routes_examined.fetch_add(
        (long long)work.candidate_routes_examined, memory_order_relaxed
    );
    repair_profile.positions_ranked.fetch_add(
        (long long)work.positions_ranked, memory_order_relaxed
    );
    repair_profile.exact_route_evaluations.fetch_add(
        (long long)work.exact_route_evaluations, memory_order_relaxed
    );
    repair_profile.repair_time_us.fetch_add(elapsed_us, memory_order_relaxed);

    if (!cfg.repair_trace_csv.empty() &&
        cfg.repair_trace_sample_every > 0 &&
        ((call_id - 1) % cfg.repair_trace_sample_every == 0)) {
        RepairTraceRow row;
        row.call_id = call_id;
        row.mode = repair_mode_name(mode);
        row.destroy_mode = destroy_mode;
        row.removed_count = (int)work.customers_requested;
        row.inserted_count = (int)work.customers_inserted;
        row.failed_count = (int)remaining.size();
        row.success = success ? 1 : 0;
        row.repair_time_us = elapsed_us;
        row.candidate_routes_examined =
            (long long)work.candidate_routes_examined;
        row.positions_ranked = (long long)work.positions_ranked;
        row.exact_route_evaluations =
            (long long)work.exact_route_evaluations;
        row.base_objective = base_objective;
        row.repaired_objective = cur.objective;

        lock_guard<mutex> lk(repair_trace_mutex);
        if ((long long)repair_trace_rows.size() < cfg.repair_trace_max_rows) {
            repair_trace_rows.push_back(std::move(row));
        }
    }

    return success;
}

// V31 SISR-inspired adjacent-string destroy. This is an original, lightweight
// integration of the adjacent-string/slack idea, not a verbatim SISR implementation.
static vector<int> string_slack_removal_pool_v31(
    const SolutionState &base,
    int remove_cnt,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    mt19937 &rng
) {
    const auto &CG = *ev.CG;
    vector<int> all = collect_customers_from_state(base, CG);
    if (all.empty() || remove_cnt <= 0) return {};

    uniform_int_distribution<int> seed_dist(0, (int)all.size() - 1);
    const int anchor = all[seed_dist(rng)];
    struct RS { double score; int r; };
    vector<RS> routes;
    for (int r = 0; r < (int)base.routes.size(); ++r) {
        vector<int> cust = collect_customers_from_route(base.routes[r], CG);
        if (cust.empty()) continue;
        double best_rel = INF_D;
        for (int x : cust) best_rel = min(best_rel, relatedness_score(anchor, x, pm, CG));
        if (isfinite(best_rel)) routes.push_back({best_rel, r});
    }
    if (routes.empty()) return {};
    sort(routes.begin(), routes.end(), [](const RS &a, const RS &b) {
        if (a.score != b.score) return a.score < b.score;
        return a.r < b.r;
    });
    const double frac = max(0.05, min(1.0, cfg.string_slack_route_top_fraction));
    const int top_routes = max(1, min((int)routes.size(), (int)ceil(frac * routes.size())));

    unordered_set<int> removed;
    vector<int> pool;
    uniform_real_distribution<double> U(0.0,1.0);
    int strings = 0;
    while ((int)pool.size() < remove_cnt && strings < max(1, cfg.string_slack_max_strings)) {
        int ridx = min(top_routes - 1, (int)floor(pow(U(rng),2.0) * top_routes));
        const auto &route = base.routes[routes[ridx].r];
        vector<int> cpos;
        for (int i=1;i+1<(int)route.size();++i) {
            int x=route[i]; if (x>=0 && x<(int)CG.nodes.size() && CG.nodes[x].type==2) cpos.push_back(i);
        }
        if (cpos.empty()) { ++strings; continue; }
        vector<pair<double,int>> centers;
        for (int pos:cpos) centers.push_back({relatedness_score(anchor,route[pos],pm,CG),pos});
        sort(centers.begin(),centers.end());
        const int center_top=min((int)centers.size(),4);
        const int center_pos=centers[min(center_top-1,(int)floor(U(rng)*center_top))].second;
        int max_len=min({max(1,cfg.string_slack_max_string_length),(int)cpos.size(),remove_cnt-(int)pool.size()});
        if (max_len<=0) break;
        uniform_int_distribution<int> len_dist(1,max_len);
        const int len=len_dist(rng);
        int cidx=0; for (int i=0;i<(int)cpos.size();++i) if (cpos[i]==center_pos) { cidx=i; break; }
        const int left=max(0,min(cidx-len/2,(int)cpos.size()-len));
        for (int j=left;j<left+len && (int)pool.size()<remove_cnt;++j) {
            const int node=route[cpos[j]]; if (removed.insert(node).second) pool.push_back(node);
        }
        ++strings;
    }
    if ((int)pool.size() < remove_cnt) {
        vector<pair<double,int>> related;
        for (int x:all) if (!removed.count(x)) related.push_back({relatedness_score(anchor,x,pm,CG),x});
        sort(related.begin(),related.end());
        for (auto &p:related) { if ((int)pool.size()>=remove_cnt) break; if (removed.insert(p.second).second) pool.push_back(p.second); }
    }
    return pool;
}


// E2 cheap structure ruins -------------------------------------------------
// These operators deliberately avoid an O(n log n) relatedness sort whose
// comparator repeatedly performs pair-distance work.  They are meant for the
// throughput/structure phase, where changing route ownership quickly matters
// more than carefully destroying one semantic neighborhood.

static vector<int> phase_multiroute_block_removal_pool_e2(
    const SolutionState &base,
    int remove_cnt,
    ObjectiveEvaluator &ev,
    mt19937 &rng
) {
    struct RouteInfo {
        int r = -1;
        vector<int> customer_pos;
        double weight = 1.0;
    };
    vector<RouteInfo> routes;
    routes.reserve(base.routes.size());

    double max_cost = 1.0;
    for (int r = 0; r < (int)base.routes.size(); ++r) {
        RouteInfo info;
        info.r = r;
        const auto &route = base.routes[r];
        for (int p = 1; p + 1 < (int)route.size(); ++p) {
            int x = route[p];
            if (x >= 0 && x < (int)ev.CG->nodes.size() &&
                ev.CG->nodes[x].type == 2) {
                info.customer_pos.push_back(p);
            }
        }
        if (info.customer_pos.empty()) continue;
        double c = (r < (int)base.route_metrics.size() &&
                    isfinite(base.route_metrics[r].weighted_cost))
            ? max(0.0, base.route_metrics[r].weighted_cost)
            : 1.0;
        max_cost = max(max_cost, c);
        info.weight = c;
        routes.push_back(std::move(info));
    }
    if (routes.empty()) return {};

    for (auto &ri : routes) {
        // Keep a substantial uniform component so the operator is not just a
        // disguised worst-route destroy.
        ri.weight = 0.35 + 0.65 * (ri.weight / max_cost);
    }

    unordered_set<int> removed;
    vector<int> pool;
    pool.reserve(remove_cnt);
    vector<char> route_used(routes.size(), 0);
    uniform_real_distribution<double> U(0.0, 1.0);

    const int target_blocks = max(2, min((int)routes.size(),
        max(2, (int)round(sqrt((double)max(2, remove_cnt))))));
    int blocks = 0;
    int guard = 0;
    while ((int)pool.size() < remove_cnt &&
           guard++ < max(16, (int)routes.size() * 5)) {
        double total_w = 0.0;
        for (int i = 0; i < (int)routes.size(); ++i) {
            double mult = route_used[i] && blocks < target_blocks ? 0.18 : 1.0;
            total_w += routes[i].weight * mult;
        }
        if (total_w <= 0.0) break;
        double ticket = U(rng) * total_w;
        int pick = 0;
        for (; pick + 1 < (int)routes.size(); ++pick) {
            double mult = route_used[pick] && blocks < target_blocks ? 0.18 : 1.0;
            const double w = routes[pick].weight * mult;
            if (ticket < w) break;
            ticket -= w;
        }

        const auto &ri = routes[pick];
        const int avail = (int)ri.customer_pos.size();
        if (avail <= 0) continue;
        const int left_to_remove = remove_cnt - (int)pool.size();
        int nominal = max(2, min(10,
            (int)ceil((double)left_to_remove /
                      (double)max(1, target_blocks - blocks))));
        nominal = min(nominal, avail);
        int len_lo = max(1, nominal / 2);
        int len_hi = max(len_lo, min(avail, nominal + 2));
        int len = len_lo;
        if (len_hi > len_lo) {
            len += (int)(rng() % (unsigned)(len_hi - len_lo + 1));
        }
        int start = 0;
        if (avail > len) start = (int)(rng() % (unsigned)(avail - len + 1));

        for (int j = start; j < start + len && (int)pool.size() < remove_cnt; ++j) {
            const int node = base.routes[ri.r][ri.customer_pos[j]];
            if (removed.insert(node).second) pool.push_back(node);
        }
        route_used[pick] = 1;
        ++blocks;
    }

    if ((int)pool.size() < remove_cnt) {
        vector<int> all = collect_customers_from_state(base, *ev.CG);
        shuffle(all.begin(), all.end(), rng);
        for (int x : all) {
            if ((int)pool.size() >= remove_cnt) break;
            if (removed.insert(x).second) pool.push_back(x);
        }
    }
    return pool;
}

static vector<int> phase_expensive_arc_block_removal_pool_e2(
    const SolutionState &base,
    int remove_cnt,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    mt19937 &rng
) {
    // E2.1 "seam scatter": keep the useful signal from expensive/detour arcs,
    // but do NOT remove a large contiguous neighborhood around one seam.  That
    // first design had poor repair feasibility.  Instead, take a limited set
    // of bad-seam customers across distinct routes and fill the rest randomly.
    // This preserves the high feasibility of random ruin while biasing the
    // perturbation toward structurally suspicious route ownership.
    struct Seam {
        double score = 0.0;
        int r = -1;
        int node = -1;
    };
    vector<Seam> seams;
    vector<int> all = collect_customers_from_state(base, *ev.CG);
    seams.reserve(all.size());

    for (int r = 0; r < (int)base.routes.size(); ++r) {
        const auto &route = base.routes[r];
        for (int p = 1; p + 1 < (int)route.size(); ++p) {
            const int x = route[p];
            if (x < 0 || x >= (int)ev.CG->nodes.size() ||
                ev.CG->nodes[x].type != 2) continue;
            const int a = route[p - 1];
            const int c = route[p + 1];
            double ab = fast_pair_search_cost(a, x, &pm);
            double bc = fast_pair_search_cost(x, c, &pm);
            double ac = fast_pair_search_cost(a, c, &pm);
            if (!isfinite(ab) || !isfinite(bc)) continue;
            if (!isfinite(ac)) ac = ab + bc;
            const double detour = max(0.0, ab + bc - ac);
            const double score = detour + 0.10 * (ab + bc);
            seams.push_back({score, r, x});
        }
    }
    if (seams.empty()) {
        shuffle(all.begin(), all.end(), rng);
        if ((int)all.size() > remove_cnt) all.resize(remove_cnt);
        return all;
    }

    const int elite = min((int)seams.size(),
        max(12, min(96, max(12, (int)seams.size() / 3))));
    if ((int)seams.size() > elite) {
        nth_element(seams.begin(), seams.begin() + elite, seams.end(),
            [](const Seam &a, const Seam &b) { return a.score > b.score; });
        seams.resize(elite);
    }
    sort(seams.begin(), seams.end(),
        [](const Seam &a, const Seam &b) { return a.score > b.score; });

    unordered_set<int> removed;
    vector<int> pool;
    pool.reserve(remove_cnt);
    unordered_map<int,int> per_route;

    const int targeted = max(1, min(remove_cnt,
        (int)round(0.42 * (double)remove_cnt)));
    const int active_routes = max(1, (int)base.routes.size());
    const int per_route_cap = max(1, min(3,
        (int)ceil((double)targeted /
                  (double)max(4, min(16, active_routes)))));

    uniform_real_distribution<double> U(0.0, 1.0);
    int guard = 0;
    while ((int)pool.size() < targeted && guard++ < elite * 4) {
        const int window = max(1, min(elite, 24));
        const int rank = min(window - 1,
            (int)floor(pow(U(rng), 1.8) * window));
        const Seam &s = seams[rank];
        if (per_route[s.r] >= per_route_cap) continue;
        if (removed.insert(s.node).second) {
            pool.push_back(s.node);
            ++per_route[s.r];
        }
    }

    // Random completion is intentional: it keeps repair feasibility high and
    // lets the targeted seams exchange ownership with unrelated routes.
    shuffle(all.begin(), all.end(), rng);
    for (int x : all) {
        if ((int)pool.size() >= remove_cnt) break;
        if (removed.insert(x).second) pool.push_back(x);
    }
    return pool;
}

static SolutionState alns_destroy_repair(
    const SolutionState &base, ObjectiveEvaluator &ev, PairwiseManager &pm,
    mt19937 &rng, int destroy_mode,
    double destroy_min_override = -1.0,
    double destroy_max_override = -1.0
) {
    SolutionState cur = base;
    int depot = depot_of(ev);
    vector<int> all_customers = collect_customers_from_state(cur, *ev.CG);
    if (all_customers.empty()) return cur;

    uniform_real_distribution<double> ur(0.0, 1.0);
    // Sample removal ratio from configurable bounds
    const double destroy_min = destroy_min_override > 0.0
        ? destroy_min_override : cfg.alns_destroy_min_ratio;
    const double destroy_max = destroy_max_override > 0.0
        ? max(destroy_min, destroy_max_override) : cfg.alns_destroy_max_ratio;
    double remove_ratio = destroy_min
                        + (destroy_max - destroy_min) * ur(rng);
    int remove_cnt = max(2, (int)round(remove_ratio * (double)all_customers.size()));
    unordered_set<int> removed;

    if (destroy_mode == 0) {
        shuffle(all_customers.begin(), all_customers.end(), rng);
        for (int i = 0; i < remove_cnt && i < (int)all_customers.size(); ++i) removed.insert(all_customers[i]);
    } else if (destroy_mode == 1) {
        vector<pair<double,int>> route_scores;
        for (int r = 0; r < (int)cur.routes.size(); ++r) {
            if (collect_customers_from_route(cur.routes[r], *ev.CG).empty()) continue;
            route_scores.push_back({route_exact_cost(cur.routes[r], ev), r});
        }
        if (route_scores.empty()) return cur;

        sort(route_scores.begin(), route_scores.end(), greater<>());
        int top_pool = min(3, (int)route_scores.size());
        int seed_route = route_scores[(size_t)(rng() % (unsigned)top_pool)].second;
        vector<int> seed_customers = collect_customers_from_route(cur.routes[seed_route], *ev.CG);
        int seed_node = seed_customers[rng() % seed_customers.size()];
        removed.insert(seed_node);
        vector<int> candidates = all_customers;
        sort(candidates.begin(), candidates.end(), [&](int a, int b) { return relatedness_score(seed_node, a, pm, *ev.CG) < relatedness_score(seed_node, b, pm, *ev.CG); });
        for (int x : candidates) { if ((int)removed.size() >= remove_cnt) break; removed.insert(x); }
    } else if (destroy_mode == 2) {
        int seed_node = all_customers[rng() % all_customers.size()];
        removed.insert(seed_node);
        vector<int> candidates = all_customers;
        sort(candidates.begin(), candidates.end(), [&](int a, int b) { return relatedness_score(seed_node, a, pm, *ev.CG) < relatedness_score(seed_node, b, pm, *ev.CG); });
        for (int x : candidates) { if ((int)removed.size() >= remove_cnt) break; removed.insert(x); }
    } else if (destroy_mode == 3) {
        vector<int> pool = string_slack_removal_pool_v31(base, remove_cnt, ev, pm, rng);
        for (int x : pool) removed.insert(x);
        if (removed.empty()) return base;
    } else if (destroy_mode == 4) {
        vector<int> pool = phase_multiroute_block_removal_pool_e2(
            base, remove_cnt, ev, rng);
        for (int x : pool) removed.insert(x);
        if (removed.empty()) return base;
    } else {
        vector<int> pool = phase_expensive_arc_block_removal_pool_e2(
            base, remove_cnt, ev, pm, rng);
        for (int x : pool) removed.insert(x);
        if (removed.empty()) return base;
    }

    for (auto &r : cur.routes) {
        r = remove_nodes_from_route(r, removed);
        normalize_route(r, depot);
        enforce_trip_separators(r, *ev.CG, depot);
    }

    vector<int> rem_list(removed.begin(), removed.end());
    sort(rem_list.begin(), rem_list.end());

    const bool repair_ok = repair_removed_customers(
        cur,
        rem_list,
        ev,
        pm,
        destroy_mode,
        base.objective
    );

    if (!repair_ok) {
        return base;
    }

    // Production behavior keeps the light local polish. The dedicated paper
    // benchmark can disable it so the measured difference is repair only.
    const bool run_post_repair_polish =
        !tls_disable_post_repair_polish &&
        (!cfg.lns_benchmark_mode ||
         !cfg.lns_benchmark_disable_post_repair_polish);

    if (run_post_repair_polish) {
        for (auto &r : cur.routes) {
            normalize_route(r, depot);
            enforce_trip_separators(r, *ev.CG, depot);

            if (cfg.use_relocate_polish) {
                relocate_route_local_best(r, ev, pm, *ev.CG, depot);
            }

            if (cfg.use_oropt) {
                or_opt_k_route(r, 2, ev, pm, *ev.CG, depot);
            }

            if (cfg.use_2opt) {
                two_opt_multi_trip_route(r, ev, pm, *ev.CG, depot);
            }
        }

        recompute_state_metrics_and_loads(cur, ev);
    }

    // Hard safety: ALNS must never return incomplete candidate.
    if (!solution_fully_feasible(cur, *ev.CG)) {
        return base;
    }

    return cur;
}

static void adaptive_lns_polish(SolutionState &state, ObjectiveEvaluator &ev, PairwiseManager &pm, int rounds, unsigned seed) {
    // Skip if ALNS is disabled
    if (!cfg.use_alns) return;
    auto start_alns = Clock::now();
    mt19937 rng(seed);
    SolutionState best = state;
    double best_obj = state.objective;
    array<double,3> destroy_w = {1.0, 1.0, 1.0};
    for (int t = 0; t < rounds; ++t) {
        if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); break; }
        double sum = destroy_w[0] + destroy_w[1] + destroy_w[2];
        uniform_real_distribution<double> ur(0.0, max(1e-9, sum));
        double x = ur(rng);
        int op = (x < destroy_w[0]) ? 0 : (x < destroy_w[0] + destroy_w[1]) ? 1 : 2;
        SolutionState cand = alns_destroy_repair(best, ev, pm, rng, op);
        recompute_state_metrics_and_loads(cand, ev);
        if (cand.objective + 1e-9 < best_obj) {
            best = std::move(cand);
            best_obj = best.objective;
            repair_profile.improving_lns_moves.fetch_add(1, memory_order_relaxed);
            destroy_w[op] += 2.0;
        } else {
            destroy_w[op] *= 0.97;
        }
        for (double &w : destroy_w) w = max(0.15, min(w, 10.0));
    }
    state = std::move(best);
    profile.alns_time_us.fetch_add(
        chrono::duration_cast<chrono::microseconds>(
            Clock::now() - start_alns
        ).count(),
        memory_order_relaxed
    );
    profile.alns_calls.fetch_add(1, memory_order_relaxed);
}

static void final_route_cleanup(SolutionState &state, ObjectiveEvaluator &ev, PairwiseManager &pm) {
    // Perform bounded final polish. Controlled by cfg.use_final_polish and cfg.final_polish_rounds
    if (!cfg.use_final_polish) return;
    auto start_polish = Clock::now();
    int depot = depot_of(ev);
    for (int round = 0; round < cfg.final_polish_rounds; ++round) {
        if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); break; }
        for (auto &r : state.routes) {
            if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); break; }
            normalize_route(r, depot);
            enforce_trip_separators(r, *ev.CG, depot);
            if (cfg.use_relocate_polish) relocate_route_local_best(r, ev, pm, *ev.CG, depot);
            if (cfg.use_oropt) or_opt_k_route(r, 2, ev, pm, *ev.CG, depot);
            if (cfg.use_2opt) two_opt_multi_trip_route(r, ev, pm, *ev.CG, depot);
        }
        recompute_state_metrics_and_loads(state, ev);
    }
    profile.polish_time_us.fetch_add(
        chrono::duration_cast<chrono::microseconds>(
            Clock::now() - start_polish
        ).count(),
        memory_order_relaxed
    );
    profile.polish_calls.fetch_add(1, memory_order_relaxed);
}

static inline bool interroute_exact_arc_delta_prune_enabled() {
    return cfg.use_interroute_arc_delta_prune &&
           cfg.objective_mode == "distance" &&
           !cfg.allow_multi_trip;
}

static inline double interroute_arc_dist_exact_fast(int a, int b, PairwiseManager &pm) {
    const double d = fast_pair_dist(a, b, &pm);
    return isfinite(d) ? d : INF_D;
}

static bool inter_route_relocate_best_pass(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const auto audit_t0 = Clock::now();
    profile.interroute_relocate_calls.fetch_add(1, memory_order_relaxed);

    int depot = depot_of(ev);
    int R = (int)state.routes.size();

    recompute_state_metrics_and_loads(state, ev);

    double best_delta = -1e-9;
    int best_from = -1, best_to = -1;
    vector<int> best_route_from, best_route_to;

    int scans = 0;

    vector<pair<int,int>> pair_order;
    if (cfg.interroute_rank_pairs) pair_order = boundary_prioritized_route_pairs(state, ev, pm, R);
    else {
        for (int a = 0; a < R; ++a) for (int b = a + 1; b < R; ++b) pair_order.push_back({a,b});
    }
    profile.interroute_pairs_available.fetch_add((long long)pair_order.size(), memory_order_relaxed);
    unordered_set<unsigned long long> touched_pairs;

    for (const auto &[pa, pb] : pair_order) {
        for (int dir = 0; dir < 2; ++dir) {
            const int from = (dir == 0 ? pa : pb);
            const int to   = (dir == 0 ? pb : pa);
            if (from == to) continue;
            touched_pairs.insert((static_cast<unsigned long long>((unsigned)min(from,to)) << 32) | (unsigned)max(from,to));

            const auto &rf = state.routes[from];
            const auto &rt = state.routes[to];

            if ((int)rf.size() <= 2) continue;

            for (int pos_from = 1; pos_from + 1 < (int)rf.size(); ++pos_from) {
                int node = rf[pos_from];
                if (ev.CG->nodes[node].type != 2) continue;

                for (int pos_to = 1; pos_to < (int)rt.size(); ++pos_to) {
                    ++scans;
                    if ((scans & 255) == 0 && solver_should_stop()) {
                        profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed);
                        goto finish_scan;
                    }
                    if (cfg.interroute_scan_cap > 0 && scans > cfg.interroute_scan_cap) {
                        goto finish_scan;
                    }

                    const int insert_pos = max(1, min(pos_to, (int)rt.size() - 1));
                    if (interroute_exact_arc_delta_prune_enabled()) {
                        const int pf = rf[pos_from - 1], nf = rf[pos_from + 1];
                        const int pt = rt[insert_pos - 1], nt = rt[insert_pos];
                        const double d_pf_node = interroute_arc_dist_exact_fast(pf, node, pm);
                        const double d_node_nf = interroute_arc_dist_exact_fast(node, nf, pm);
                        const double d_pf_nf = interroute_arc_dist_exact_fast(pf, nf, pm);
                        const double d_pt_nt = interroute_arc_dist_exact_fast(pt, nt, pm);
                        const double d_pt_node = interroute_arc_dist_exact_fast(pt, node, pm);
                        const double d_node_nt = interroute_arc_dist_exact_fast(node, nt, pm);
                        if (isfinite(d_pf_node) && isfinite(d_node_nf) && isfinite(d_pf_nf) &&
                            isfinite(d_pt_nt) && isfinite(d_pt_node) && isfinite(d_node_nt)) {
                            const double arc_delta =
                                (d_pf_nf - d_pf_node - d_node_nf) +
                                (d_pt_node + d_node_nt - d_pt_nt);
                            if (arc_delta >= best_delta - 1e-12) {
                                profile.interroute_arc_delta_pruned.fetch_add(1, memory_order_relaxed);
                                continue;
                            }
                            profile.interroute_arc_delta_survivors.fetch_add(1, memory_order_relaxed);
                        }
                    }

                    vector<int> cand_from = rf;
                    vector<int> cand_to = rt;
                    cand_from.erase(cand_from.begin() + pos_from);
                    cand_to.insert(cand_to.begin() + insert_pos, node);

                    normalize_route(cand_from, depot);
                    normalize_route(cand_to, depot);

                    enforce_trip_separators(cand_from, *ev.CG, depot);
                    enforce_trip_separators(cand_to, *ev.CG, depot);

                    if (!trips_feasible_for_route(cand_from, *ev.CG, depot)) continue;
                    if (!trips_feasible_for_route(cand_to, *ev.CG, depot)) continue;

                    if (!cfg.allow_splitting) {
                        if (route_has_duplicate_customers_strict(cand_from, *ev.CG)) continue;
                        if (route_has_duplicate_customers_strict(cand_to, *ev.CG)) continue;
                    }

                    double old_cost =
                        state.route_metrics[from].weighted_cost +
                        state.route_metrics[to].weighted_cost;

                    profile.interroute_exact_evals.fetch_add(2, memory_order_relaxed);
                    double new_cost =
                        route_exact_cost(cand_from, ev) +
                        route_exact_cost(cand_to, ev);

                    double delta = new_cost - old_cost;

                    if (delta < best_delta) {
                        best_delta = delta;
                        best_from = from;
                        best_to = to;
                        best_route_from = std::move(cand_from);
                        best_route_to = std::move(cand_to);
                    }
                }
            }
        }
    }

    profile.interroute_pairs_touched.fetch_add((long long)touched_pairs.size(), memory_order_relaxed);
    profile.interroute_candidate_scans.fetch_add(scans, memory_order_relaxed);
    profile.interroute_time_us.fetch_add(
        chrono::duration_cast<chrono::microseconds>(Clock::now() - audit_t0).count(),
        memory_order_relaxed
    );

finish_scan:

    if (solver_should_stop()) return false;
    if (best_from == -1) return false;

    state.routes[best_from] = std::move(best_route_from);
    state.routes[best_to] = std::move(best_route_to);

    recompute_state_metrics_and_loads(state, ev);
    update_global_best_checked(state, *ev.CG, pm);

    return true;
}


static bool inter_route_swap_best_pass(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const auto audit_t0 = Clock::now();
    profile.interroute_swap_calls.fetch_add(1, memory_order_relaxed);

    int depot = depot_of(ev);
    int R = (int)state.routes.size();

    recompute_state_metrics_and_loads(state, ev);

    double best_delta = -1e-9;
    int best_r1 = -1, best_r2 = -1;
    vector<int> best_route_1, best_route_2;

    int scans = 0;

    vector<pair<int,int>> pair_order;
    if (cfg.interroute_rank_pairs) pair_order = boundary_prioritized_route_pairs(state, ev, pm, R);
    else {
        for (int a0 = 0; a0 < R; ++a0) for (int b0 = a0 + 1; b0 < R; ++b0) pair_order.push_back({a0,b0});
    }
    profile.interroute_pairs_available.fetch_add((long long)pair_order.size(), memory_order_relaxed);
    unordered_set<unsigned long long> touched_pairs;

    for (const auto &[r1, r2] : pair_order) {
        touched_pairs.insert((static_cast<unsigned long long>((unsigned)r1) << 32) | (unsigned)r2);
            const auto &a = state.routes[r1];
            const auto &b = state.routes[r2];

            if ((int)a.size() <= 2 || (int)b.size() <= 2) continue;

            for (int i = 1; i + 1 < (int)a.size(); ++i) {
                if (ev.CG->nodes[a[i]].type != 2) continue;

                for (int j = 1; j + 1 < (int)b.size(); ++j) {
                    if (ev.CG->nodes[b[j]].type != 2) continue;

                    ++scans;
                    if ((scans & 255) == 0 && solver_should_stop()) {
                        profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed);
                        goto finish_scan;
                    }
                    if (cfg.interroute_scan_cap > 0 && scans > cfg.interroute_scan_cap) {
                        goto finish_scan;
                    }

                    if (interroute_exact_arc_delta_prune_enabled()) {
                        const int x = a[i], y = b[j];
                        const int pa = a[i-1], na = a[i+1];
                        const int pb = b[j-1], nb = b[j+1];
                        const double old_a = interroute_arc_dist_exact_fast(pa,x,pm) +
                                             interroute_arc_dist_exact_fast(x,na,pm);
                        const double new_a = interroute_arc_dist_exact_fast(pa,y,pm) +
                                             interroute_arc_dist_exact_fast(y,na,pm);
                        const double old_b = interroute_arc_dist_exact_fast(pb,y,pm) +
                                             interroute_arc_dist_exact_fast(y,nb,pm);
                        const double new_b = interroute_arc_dist_exact_fast(pb,x,pm) +
                                             interroute_arc_dist_exact_fast(x,nb,pm);
                        if (isfinite(old_a) && isfinite(new_a) && isfinite(old_b) && isfinite(new_b)) {
                            const double arc_delta = (new_a - old_a) + (new_b - old_b);
                            if (arc_delta >= best_delta - 1e-12) {
                                profile.interroute_arc_delta_pruned.fetch_add(1, memory_order_relaxed);
                                continue;
                            }
                            profile.interroute_arc_delta_survivors.fetch_add(1, memory_order_relaxed);
                        }
                    }

                    vector<int> cand1 = a;
                    vector<int> cand2 = b;
                    swap(cand1[i], cand2[j]);

                    normalize_route(cand1, depot);
                    normalize_route(cand2, depot);

                    enforce_trip_separators(cand1, *ev.CG, depot);
                    enforce_trip_separators(cand2, *ev.CG, depot);

                    if (!trips_feasible_for_route(cand1, *ev.CG, depot)) continue;
                    if (!trips_feasible_for_route(cand2, *ev.CG, depot)) continue;

                    if (!cfg.allow_splitting) {
                        if (route_has_duplicate_customers_strict(cand1, *ev.CG)) continue;
                        if (route_has_duplicate_customers_strict(cand2, *ev.CG)) continue;
                    }

                    double old_cost =
                        state.route_metrics[r1].weighted_cost +
                        state.route_metrics[r2].weighted_cost;

                    profile.interroute_exact_evals.fetch_add(2, memory_order_relaxed);
                    double new_cost =
                        route_exact_cost(cand1, ev) +
                        route_exact_cost(cand2, ev);

                    double delta = new_cost - old_cost;

                    if (delta < best_delta) {
                        best_delta = delta;
                        best_r1 = r1;
                        best_r2 = r2;
                        best_route_1 = std::move(cand1);
                        best_route_2 = std::move(cand2);
                    }
                }
            }
    }

    profile.interroute_pairs_touched.fetch_add((long long)touched_pairs.size(), memory_order_relaxed);
    profile.interroute_candidate_scans.fetch_add(scans, memory_order_relaxed);
    profile.interroute_time_us.fetch_add(
        chrono::duration_cast<chrono::microseconds>(Clock::now() - audit_t0).count(),
        memory_order_relaxed
    );

finish_scan:

    if (solver_should_stop()) return false;
    if (best_r1 == -1) return false;

    state.routes[best_r1] = std::move(best_route_1);
    state.routes[best_r2] = std::move(best_route_2);

    recompute_state_metrics_and_loads(state, ev);
    update_global_best_checked(state, *ev.CG, pm);

    return true;
}


static bool inter_route_two_opt_star_best_pass(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const auto audit_t0 = Clock::now();
    profile.interroute_twooptstar_calls.fetch_add(1, memory_order_relaxed);

    int depot = depot_of(ev);
    int R = (int)state.routes.size();

    recompute_state_metrics_and_loads(state, ev);

    double best_delta = -1e-9;
    int best_r1 = -1, best_r2 = -1;
    vector<int> best_route_1, best_route_2;

    int scans = 0;

    vector<pair<int,int>> pair_order;
    if (cfg.interroute_rank_pairs) pair_order = boundary_prioritized_route_pairs(state, ev, pm, R);
    else {
        for (int a0 = 0; a0 < R; ++a0) for (int b0 = a0 + 1; b0 < R; ++b0) pair_order.push_back({a0,b0});
    }
    profile.interroute_pairs_available.fetch_add((long long)pair_order.size(), memory_order_relaxed);
    unordered_set<unsigned long long> touched_pairs;

    for (const auto &[r1, r2] : pair_order) {
        touched_pairs.insert((static_cast<unsigned long long>((unsigned)r1) << 32) | (unsigned)r2);
            const auto &a = state.routes[r1];
            const auto &b = state.routes[r2];

            if ((int)a.size() <= 3 || (int)b.size() <= 3) continue;

            for (int cut1 = 0; cut1 + 1 < (int)a.size(); ++cut1) {
                for (int cut2 = 0; cut2 + 1 < (int)b.size(); ++cut2) {
                    ++scans;
                    if ((scans & 255) == 0 && solver_should_stop()) {
                        profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed);
                        goto finish_scan;
                    }
                    if (cfg.interroute_scan_cap > 0 && scans > cfg.interroute_scan_cap) {
                        goto finish_scan;
                    }

                    if (interroute_exact_arc_delta_prune_enabled()) {
                        const int a0 = a[cut1], a1 = a[cut1 + 1];
                        const int b0 = b[cut2], b1 = b[cut2 + 1];
                        const double old_cut = interroute_arc_dist_exact_fast(a0,a1,pm) +
                                               interroute_arc_dist_exact_fast(b0,b1,pm);
                        const double new_cut = interroute_arc_dist_exact_fast(a0,b1,pm) +
                                               interroute_arc_dist_exact_fast(b0,a1,pm);
                        if (isfinite(old_cut) && isfinite(new_cut)) {
                            const double arc_delta = new_cut - old_cut;
                            if (arc_delta >= best_delta - 1e-12) {
                                profile.interroute_arc_delta_pruned.fetch_add(1, memory_order_relaxed);
                                continue;
                            }
                            profile.interroute_arc_delta_survivors.fetch_add(1, memory_order_relaxed);
                        }
                    }

                    vector<int> cand1;
                    vector<int> cand2;
                    cand1.reserve(a.size() + b.size());
                    cand2.reserve(a.size() + b.size());

                    cand1.insert(cand1.end(), a.begin(), a.begin() + cut1 + 1);
                    cand1.insert(cand1.end(), b.begin() + cut2 + 1, b.end());

                    cand2.insert(cand2.end(), b.begin(), b.begin() + cut2 + 1);
                    cand2.insert(cand2.end(), a.begin() + cut1 + 1, a.end());

                    normalize_route(cand1, depot);
                    normalize_route(cand2, depot);

                    enforce_trip_separators(cand1, *ev.CG, depot);
                    enforce_trip_separators(cand2, *ev.CG, depot);

                    if (!trips_feasible_for_route(cand1, *ev.CG, depot)) continue;
                    if (!trips_feasible_for_route(cand2, *ev.CG, depot)) continue;

                    if (!cfg.allow_splitting) {
                        if (route_has_duplicate_customers_strict(cand1, *ev.CG)) continue;
                        if (route_has_duplicate_customers_strict(cand2, *ev.CG)) continue;
                    }

                    double old_cost =
                        state.route_metrics[r1].weighted_cost +
                        state.route_metrics[r2].weighted_cost;

                    profile.interroute_exact_evals.fetch_add(2, memory_order_relaxed);
                    double new_cost =
                        route_exact_cost(cand1, ev) +
                        route_exact_cost(cand2, ev);

                    double delta = new_cost - old_cost;

                    if (delta < best_delta) {
                        best_delta = delta;
                        best_r1 = r1;
                        best_r2 = r2;
                        best_route_1 = std::move(cand1);
                        best_route_2 = std::move(cand2);
                    }
                }
            }
    }

    profile.interroute_pairs_touched.fetch_add((long long)touched_pairs.size(), memory_order_relaxed);
    profile.interroute_candidate_scans.fetch_add(scans, memory_order_relaxed);
    profile.interroute_time_us.fetch_add(
        chrono::duration_cast<chrono::microseconds>(Clock::now() - audit_t0).count(),
        memory_order_relaxed
    );

finish_scan:

    if (solver_should_stop()) return false;
    if (best_r1 == -1) return false;

    state.routes[best_r1] = std::move(best_route_1);
    state.routes[best_r2] = std::move(best_route_2);

    recompute_state_metrics_and_loads(state, ev);
    update_global_best_checked(state, *ev.CG, pm);

    return true;
}


static void interroute_polish_solution(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!cfg.use_interroute_polish) return;

    recompute_state_metrics_and_loads(state, ev);

    int moves = 0;

    for (int round = 0; round < cfg.interroute_polish_rounds; ++round) {
        if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); break; }
        bool improved = false;

        if (moves < cfg.max_interroute_moves) {
            if (inter_route_relocate_best_pass(state, ev, pm)) {
                improved = true;
                moves++;
            }
        }

        if (moves < cfg.max_interroute_moves) {
            if (inter_route_swap_best_pass(state, ev, pm)) {
                improved = true;
                moves++;
            }
        }

        if (moves < cfg.max_interroute_moves) {
            if (inter_route_two_opt_star_best_pass(state, ev, pm)) {
                improved = true;
                moves++;
            }
        }

        if (improved) {
            recompute_state_metrics_and_loads(state, ev);
            update_global_best_checked(state, *ev.CG, pm);
        }

        if (!improved) break;
        if (moves >= cfg.max_interroute_moves) break;
    }

    local_polish_solution(state, ev, pm);
    recompute_state_metrics_and_loads(state, ev);
    update_global_best_checked(state, *ev.CG, pm);
}

/* ---------------- GLS-lite: Guided Arc Penalty Search ---------------- */

struct GLSMove {
    bool valid = false;
    bool is_swap = false;

    int r1 = -1;
    int r2 = -1;
    int p1 = -1;
    int p2 = -1;

    int node1 = -1;
    int node2 = -1;

    double exact_delta = INF_D;
    double penalized_delta = INF_D;

    vector<int> new_r1;
    vector<int> new_r2;
};

static uint64_t gls_arc_key(int a, int b) {
    return (((uint64_t)(uint32_t)a) << 32) | (uint32_t)b;
}

static bool gls_is_customer_node(int node, ObjectiveEvaluator &ev) {
    if (node < 0 || node >= (int)ev.CG->nodes.size()) return false;
    return ev.CG->nodes[node].type == 2;
}

static double gls_arc_base_cost(
    int a,
    int b,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    (void)ev;
    if (a == b) return 0.0;

    double t = fast_pair_time(a, b, &pm);
    double d = fast_pair_dist(a, b, &pm);

    if (!isfinite(t)) t = 1e12;
    if (!isfinite(d)) d = 1e12;

    if (cfg.objective_mode == "distance") {
        return d;
    }

    if (cfg.objective_mode == "hybrid") {
        return d + cfg.w_time * t;
    }

    return t;
}

static double gls_route_penalty_term(
    const vector<int> &route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const unordered_map<uint64_t, int> &penalty,
    double lambda
) {
    if (route.size() < 2) return 0.0;

    double total = 0.0;

    for (int i = 0; i + 1 < (int)route.size(); ++i) {
        int a = route[i];
        int b = route[i + 1];

        uint64_t key = gls_arc_key(a, b);
        auto it = penalty.find(key);

        if (it == penalty.end()) continue;
        if (it->second <= 0) continue;

        double base = gls_arc_base_cost(a, b, ev, pm);
        total += (double)it->second * base;
    }

    return lambda * total;
}

static double gls_route_score(
    const vector<int> &route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const unordered_map<uint64_t, int> &penalty,
    double lambda
) {
    return route_exact_cost(route, ev) +
        gls_route_penalty_term(route, ev, pm, penalty, lambda);
}

static bool gls_validate_route_candidate(
    vector<int> &route,
    ObjectiveEvaluator &ev
) {
    int depot = depot_of(ev);

    normalize_route(route, depot);
    enforce_trip_separators(route, *ev.CG, depot);

    if (!trips_feasible_for_route(route, *ev.CG, depot)) {
        return false;
    }

    if (!cfg.allow_splitting) {
        if (route_has_duplicate_customers_strict(route, *ev.CG)) {
            return false;
        }
    }

    return true;
}

static vector<int> gls_rank_routes_by_cost(
    const SolutionState &state,
    ObjectiveEvaluator &ev
) {
    vector<pair<double, int>> ranked;

    for (int r = 0; r < (int)state.routes.size(); ++r) {
        int customers = 0;
        for (int x : state.routes[r]) {
            if (gls_is_customer_node(x, ev)) customers++;
        }

        if (customers == 0) continue;

        double cost =
            r < (int)state.route_metrics.size()
                ? state.route_metrics[r].weighted_cost
                : route_exact_cost(state.routes[r], ev);

        ranked.push_back({cost, r});
    }

    sort(ranked.begin(), ranked.end(), [](const auto &a, const auto &b) {
        if (fabs(a.first - b.first) > 1e-9) return a.first > b.first;
        return a.second < b.second;
    });

    vector<int> out;
    for (auto &p : ranked) out.push_back(p.second);

    return out;
}

static vector<int> gls_rank_source_positions(
    const vector<int> &route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    vector<pair<double, int>> ranked;

    for (int p = 1; p + 1 < (int)route.size(); ++p) {
        int node = route[p];
        if (!gls_is_customer_node(node, ev)) continue;

        int a = route[p - 1];
        int b = route[p];
        int c = route[p + 1];

        double before =
            gls_arc_base_cost(a, b, ev, pm) +
            gls_arc_base_cost(b, c, ev, pm);

        double after =
            gls_arc_base_cost(a, c, ev, pm);

        double removal_gain = before - after;

        ranked.push_back({removal_gain, p});
    }

    sort(ranked.begin(), ranked.end(), [](const auto &a, const auto &b) {
        if (fabs(a.first - b.first) > 1e-9) return a.first > b.first;
        return a.second < b.second;
    });

    vector<int> pos;
    for (auto &x : ranked) pos.push_back(x.second);

    return pos;
}

static void gls_update_arc_penalties(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    unordered_map<uint64_t, int> &penalty
) {
    struct ArcUtility {
        double utility = 0.0;
        int a = -1;
        int b = -1;
        int route = -1;
    };

    vector<int> ranked_routes = gls_rank_routes_by_cost(state, ev);

    int route_cap = max(1, cfg.gls_source_route_cap);
    int used_routes = 0;

    vector<ArcUtility> arcs;

    for (int r : ranked_routes) {
        if (used_routes >= route_cap) break;
        used_routes++;

        if (r < 0 || r >= (int)state.routes.size()) continue;

        const auto &route = state.routes[r];

        for (int i = 0; i + 1 < (int)route.size(); ++i) {
            int a = route[i];
            int b = route[i + 1];

            if (a == b) continue;
            if (a < 0 || b < 0) continue;
            if (a >= (int)ev.CG->nodes.size()) continue;
            if (b >= (int)ev.CG->nodes.size()) continue;

            double base = gls_arc_base_cost(a, b, ev, pm);
            if (!isfinite(base) || base <= 1e-9) continue;

            uint64_t key = gls_arc_key(a, b);
            int p = 0;

            auto it = penalty.find(key);
            if (it != penalty.end()) {
                p = it->second;
            }

            // Classic GLS-ish utility:
            // high cost and low current penalty = attractive to penalize.
            double utility = base / (1.0 + (double)p);

            // Euclidean-specific adjustment:
            // Do NOT ban depot arcs. Just stop depot arcs from dominating every GLS round.
            if (metric_is_euclidean()) {
                bool depot_arc =
                    ev.CG->nodes[a].type == 1 ||
                    ev.CG->nodes[b].type == 1;

                if (depot_arc) {
                    utility *= cfg.euclidean_gls_depot_arc_factor;
                }
            }

            arcs.push_back({utility, a, b, r});
        }
    }

    sort(arcs.begin(), arcs.end(), [](const ArcUtility &x, const ArcUtility &y) {
        if (fabs(x.utility - y.utility) > 1e-9) return x.utility > y.utility;
        if (x.a != y.a) return x.a < y.a;
        return x.b < y.b;
    });

    int top_k = max(1, cfg.gls_penalty_top_k);
    top_k = min(top_k, (int)arcs.size());

    for (int i = 0; i < top_k; ++i) {
        uint64_t key = gls_arc_key(arcs[i].a, arcs[i].b);
        penalty[key]++;
    }

    if (cfg.gls_verbose && top_k > 0) {
        cerr << "[GLS] penalized_arcs=" << top_k
            << " top=(" << arcs[0].a << "->" << arcs[0].b << ")"
            << " util=" << arcs[0].utility
            << " penalty=" << penalty[gls_arc_key(arcs[0].a, arcs[0].b)]
            << "\n";
    }
}

static void gls_consider_relocate(
    const SolutionState &state,
    int r1,
    int r2,
    int p1,
    int p2,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const unordered_map<uint64_t, int> &penalty,
    double lambda,
    double exact_worsen_cap,
    GLSMove &best
) {
    if (r1 == r2) return;
    if (p1 <= 0 || p1 + 1 >= (int)state.routes[r1].size()) return;

    int node = state.routes[r1][p1];
    if (!gls_is_customer_node(node, ev)) return;

    vector<int> cand1 = state.routes[r1];
    vector<int> cand2 = state.routes[r2];

    cand1.erase(cand1.begin() + p1);

    p2 = max(1, min(p2, (int)cand2.size() - 1));
    cand2.insert(cand2.begin() + p2, node);

    if (!gls_validate_route_candidate(cand1, ev)) return;
    if (!gls_validate_route_candidate(cand2, ev)) return;

    double old_exact =
        route_exact_cost(state.routes[r1], ev) +
        route_exact_cost(state.routes[r2], ev);

    double new_exact =
        route_exact_cost(cand1, ev) +
        route_exact_cost(cand2, ev);

    double exact_delta = new_exact - old_exact;

    // Allow small temporary exact worsening only.
    if (exact_delta > exact_worsen_cap + 1e-9) {
        return;
    }

    double old_pen =
        gls_route_score(state.routes[r1], ev, pm, penalty, lambda) +
        gls_route_score(state.routes[r2], ev, pm, penalty, lambda);

    double new_pen =
        gls_route_score(cand1, ev, pm, penalty, lambda) +
        gls_route_score(cand2, ev, pm, penalty, lambda);

    double pen_delta = new_pen - old_pen;

    // GLS move must improve penalized structure.
    if (pen_delta >= -1e-9) return;

    if (pen_delta + 1e-9 < best.penalized_delta) {
        best.valid = true;
        best.is_swap = false;
        best.r1 = r1;
        best.r2 = r2;
        best.p1 = p1;
        best.p2 = p2;
        best.node1 = node;
        best.node2 = -1;
        best.exact_delta = exact_delta;
        best.penalized_delta = pen_delta;
        best.new_r1 = std::move(cand1);
        best.new_r2 = std::move(cand2);
    }
}

static void gls_consider_swap(
    const SolutionState &state,
    int r1,
    int r2,
    int p1,
    int p2,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const unordered_map<uint64_t, int> &penalty,
    double lambda,
    double exact_worsen_cap,
    GLSMove &best
) {
    if (r1 == r2) return;

    if (p1 <= 0 || p1 + 1 >= (int)state.routes[r1].size()) return;
    if (p2 <= 0 || p2 + 1 >= (int)state.routes[r2].size()) return;

    int a = state.routes[r1][p1];
    int b = state.routes[r2][p2];

    if (!gls_is_customer_node(a, ev)) return;
    if (!gls_is_customer_node(b, ev)) return;

    vector<int> cand1 = state.routes[r1];
    vector<int> cand2 = state.routes[r2];

    cand1[p1] = b;
    cand2[p2] = a;

    if (!gls_validate_route_candidate(cand1, ev)) return;
    if (!gls_validate_route_candidate(cand2, ev)) return;

    double old_exact =
        route_exact_cost(state.routes[r1], ev) +
        route_exact_cost(state.routes[r2], ev);

    double new_exact =
        route_exact_cost(cand1, ev) +
        route_exact_cost(cand2, ev);

    double exact_delta = new_exact - old_exact;

    if (exact_delta > exact_worsen_cap + 1e-9) {
        return;
    }

    double old_pen =
        gls_route_score(state.routes[r1], ev, pm, penalty, lambda) +
        gls_route_score(state.routes[r2], ev, pm, penalty, lambda);

    double new_pen =
        gls_route_score(cand1, ev, pm, penalty, lambda) +
        gls_route_score(cand2, ev, pm, penalty, lambda);

    double pen_delta = new_pen - old_pen;

    if (pen_delta >= -1e-9) return;

    if (pen_delta + 1e-9 < best.penalized_delta) {
        best.valid = true;
        best.is_swap = true;
        best.r1 = r1;
        best.r2 = r2;
        best.p1 = p1;
        best.p2 = p2;
        best.node1 = a;
        best.node2 = b;
        best.exact_delta = exact_delta;
        best.penalized_delta = pen_delta;
        best.new_r1 = std::move(cand1);
        best.new_r2 = std::move(cand2);
    }
}

static bool guided_arc_penalty_move_pass(
    SolutionState &work,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const unordered_map<uint64_t, int> &penalty,
    double lambda,
    double exact_worsen_cap
) {
    recompute_state_metrics_and_loads(work, ev);

    vector<int> source_routes = gls_rank_routes_by_cost(work, ev);

    int source_route_cap = max(1, cfg.gls_source_route_cap);
    int source_customer_cap = max(1, cfg.gls_source_customer_cap);
    int target_route_cap = max(1, cfg.gls_target_route_cap);
    int pos_cap = max(1, cfg.gls_pos_cap);

    GLSMove best;

    int used_sources = 0;

    for (int r1 : source_routes) {
        if (used_sources >= source_route_cap) break;
        used_sources++;

        vector<int> src_pos = gls_rank_source_positions(work.routes[r1], ev, pm);

        if ((int)src_pos.size() > source_customer_cap) {
            src_pos.resize(source_customer_cap);
        }

        vector<int> target_routes;

        for (int r = 0; r < (int)work.routes.size(); ++r) {
            if (r != r1) target_routes.push_back(r);
        }

        sort(target_routes.begin(), target_routes.end(), [&](int a, int b) {
            double ca =
                a < (int)work.route_metrics.size()
                    ? work.route_metrics[a].weighted_cost
                    : route_exact_cost(work.routes[a], ev);

            double cb =
                b < (int)work.route_metrics.size()
                    ? work.route_metrics[b].weighted_cost
                    : route_exact_cost(work.routes[b], ev);

            return ca < cb;
        });

        if ((int)target_routes.size() > target_route_cap) {
            target_routes.resize(target_route_cap);
        }

        for (int p1 : src_pos) {
            for (int r2 : target_routes) {
                int tested = 0;

                for (int p2 = 1; p2 <= (int)work.routes[r2].size() - 1; ++p2) {
                    if (tested >= pos_cap) break;
                    tested++;

                    gls_consider_relocate(
                        work,
                        r1,
                        r2,
                        p1,
                        p2,
                        ev,
                        pm,
                        penalty,
                        lambda,
                        exact_worsen_cap,
                        best
                    );
                }

                if (cfg.gls_try_swaps) {
                    int tested_swaps = 0;

                    for (int p2 = 1; p2 + 1 < (int)work.routes[r2].size(); ++p2) {
                        if (tested_swaps >= pos_cap) break;
                        tested_swaps++;

                        gls_consider_swap(
                            work,
                            r1,
                            r2,
                            p1,
                            p2,
                            ev,
                            pm,
                            penalty,
                            lambda,
                            exact_worsen_cap,
                            best
                        );
                    }
                }
            }
        }
    }

    if (!best.valid) return false;

    work.routes[best.r1] = std::move(best.new_r1);
    work.routes[best.r2] = std::move(best.new_r2);

    recompute_state_metrics_and_loads(work, ev);

    if (cfg.gls_verbose && cfg.gls_print_moves) {
        cerr << "[GLS] "
            << (best.is_swap ? "swap" : "relocate")
            << " r1=" << best.r1
            << " r2=" << best.r2
            << " node1=" << best.node1;

        if (best.is_swap) {
            cerr << " node2=" << best.node2;
        }

        cerr << " exact_delta=" << best.exact_delta
            << " penalized_delta=" << best.penalized_delta
            << " work_obj=" << work.objective
            << "\n";
    }

    return true;
}

static void guided_arc_penalty_search(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!cfg.use_guided_arc_penalty) return;

    // Zero budget means zero behavior. Do not penalize, print, or loop.
    if (cfg.gls_time_limit_s <= 0.0 ||
        cfg.gls_max_total_moves <= 0 ||
        cfg.gls_moves_per_round <= 0 ||
        cfg.gls_rounds <= 0) {
        return;
    }

    auto t0 = Clock::now();

    recompute_state_metrics_and_loads(state, ev);

    double start_obj = state.objective;

    SolutionState best = state;
    double best_obj = state.objective;

    unordered_map<uint64_t, int> penalty;

    int accepted_exact = 0;
    int penalized_moves = 0;
    int stagnation_level = 0;

    int rounds = max(1, cfg.gls_rounds);
    int moves_per_round = max(1, cfg.gls_moves_per_round);

    for (int round = 0; round < rounds; ++round) {
        if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); break; }
        double elapsed_so_far =
            chrono::duration<double>(Clock::now() - t0).count();

        if (cfg.gls_time_limit_s > 0.0 &&
            elapsed_so_far >= cfg.gls_time_limit_s) {
            if (cfg.gls_verbose) {
                cerr << "[GLS] stop: time limit reached elapsed="
                    << elapsed_so_far << "s\n";
            }
            break;
        }

        if (cfg.gls_max_total_moves > 0 &&
            penalized_moves >= cfg.gls_max_total_moves) {
            if (cfg.gls_verbose) {
                cerr << "[GLS] stop: move cap reached moves="
                    << penalized_moves << "\n";
            }
            break;
        }

        if (cfg.gls_max_stagnation > 0 &&
            stagnation_level >= cfg.gls_max_stagnation) {
            if (cfg.gls_verbose) {
                cerr << "[GLS] stop: stagnation cap reached stagnation="
                    << stagnation_level << "\n";
            }
            break;
        }

        double effective_lambda = cfg.gls_lambda;

        if (cfg.gls_adaptive_lambda) {
            effective_lambda =
                cfg.gls_lambda_base *
                pow(cfg.gls_lambda_growth, (double)stagnation_level);

            effective_lambda = min(effective_lambda, cfg.gls_lambda_max);
        }

        double effective_worsen_cap = cfg.gls_max_exact_worsen_per_move;

        if (cfg.gls_adaptive_worsen_cap) {
            effective_worsen_cap =
                cfg.gls_max_exact_worsen_per_move *
                pow(cfg.gls_worsen_growth, (double)stagnation_level);

            effective_worsen_cap = min(effective_worsen_cap, cfg.gls_worsen_max);
        }

        if (cfg.gls_verbose) {
            cerr << "[GLS] round=" << round
                << " stagnation=" << stagnation_level
                << " lambda=" << effective_lambda
                << " worsen_cap=" << effective_worsen_cap
                << " moves=" << penalized_moves
                << "\n";
        }

        SolutionState work = best;
        recompute_state_metrics_and_loads(work, ev);

        gls_update_arc_penalties(work, ev, pm, penalty);

        bool moved = false;

        for (int mv = 0; mv < moves_per_round; ++mv) {
            if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); break; }
            double elapsed_inner =
                chrono::duration<double>(Clock::now() - t0).count();

            if (cfg.gls_time_limit_s > 0.0 &&
                elapsed_inner >= cfg.gls_time_limit_s) {
                break;
            }

            if (cfg.gls_max_total_moves > 0 &&
                penalized_moves >= cfg.gls_max_total_moves) {
                break;
            }

            bool ok = guided_arc_penalty_move_pass(
                work,
                ev,
                pm,
                penalty,
                effective_lambda,
                effective_worsen_cap
            );

            if (!ok) break;

            moved = true;
            penalized_moves++;
        }

        if (!moved) {
            stagnation_level++;
            continue;
        }

        // Repair/tighten after penalized escape.
        if (cfg.use_relocate_polish || cfg.use_oropt || cfg.use_2opt) {
            local_polish_solution(work, ev, pm);
            recompute_state_metrics_and_loads(work, ev);
        }

        if (cfg.use_interroute_polish) {
            interroute_polish_solution(work, ev, pm);
            recompute_state_metrics_and_loads(work, ev);
        }

        if (work.objective + 1e-9 < best_obj) {
            best = std::move(work);
            best_obj = best.objective;
            accepted_exact++;
            stagnation_level = 0;
            update_global_best_checked(best, *ev.CG, pm);
        } else {
            stagnation_level++;
        }
    }

    state = std::move(best);
    recompute_state_metrics_and_loads(state, ev);

    double elapsed = chrono::duration<double>(Clock::now() - t0).count();

    if (cfg.gls_verbose) {
        cerr << "[GLS] start=" << start_obj
            << " end=" << state.objective
            << " gain=" << (start_obj - state.objective)
            << " penalized_moves=" << penalized_moves
            << " accepted_exact=" << accepted_exact
            << " penalties=" << penalty.size()
            << " time=" << elapsed
            << "s\n";
    }
}

/* ---------------- Fragment LNS: multi-route reassignment breaker ---------------- */

static vector<int> expensive_customers_fragment_lns(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    struct Cand {
        double score;
        int node;
        int route;
        int pos;
    };

    vector<Cand> cands;

    for (int r = 0; r < (int)state.routes.size(); ++r) {
        const auto &route = state.routes[r];

        for (int i = 1; i + 1 < (int)route.size(); ++i) {
            int node = route[i];
            if (ev.CG->nodes[node].type != 2) continue;

            int prev = route[i - 1];
            int next = route[i + 1];

            double before =
                fast_pair_time(prev, node, &pm) +
                fast_pair_time(node, next, &pm);

            double after = fast_pair_time(prev, next, &pm);

            if (!isfinite(before)) before = 1e12;
            if (!isfinite(after)) after = 1e12;

            double remove_gain = before - after;

            double route_pressure = 0.001 * state.route_metrics[r].weighted_cost;

            cands.push_back({
                remove_gain + route_pressure,
                node,
                r,
                i
            });
        }
    }

    sort(cands.begin(), cands.end(), [](const Cand &a, const Cand &b) {
        return a.score > b.score;
    });

    vector<int> out;
    unordered_set<int> used;

    for (const auto &c : cands) {
        if (used.count(c.node)) continue;
        used.insert(c.node);
        out.push_back(c.node);

        if ((int)out.size() >= max(1, cfg.fragment_lns_related_k)) break;
    }

    return out;
}

static double route_ruin_score_for_longest(
    const SolutionState &state,
    int r
) {
    if (r < 0 || r >= (int)state.routes.size()) return -INF_D;
    if (r >= (int)state.route_metrics.size()) return -INF_D;

    const RouteMetrics &m = state.route_metrics[r];

    // In distance mode, distance_m is the clearest signal.
    // In other modes, weighted_cost includes time/lateness/penalties.
    double score = m.weighted_cost;

    if (cfg.objective_mode == "distance") {
        score = m.distance_m;
    }

    // Tiny pressure from load helps target heavy routes when distances tie.
    if (r < (int)state.route_load.size()) {
        score += 0.01 * state.route_load[r];
    }

    return score;
}

static vector<int> customer_positions_in_route(
    const vector<int> &route,
    const Compressed &CG
) {
    vector<int> pos;

    for (int i = 1; i + 1 < (int)route.size(); ++i) {
        int node = route[i];

        if (node >= 0 &&
            node < (int)CG.nodes.size() &&
            CG.nodes[node].type == 2) {
            pos.push_back(i);
        }
    }

    return pos;
}

static vector<int> longest_route_ruin_pool(
    const SolutionState &base,
    int remove_target,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    mt19937 &rng
) {
    const Compressed &CG = *ev.CG;

    vector<pair<double, int>> routes;

    for (int r = 0; r < (int)base.routes.size(); ++r) {
        vector<int> cpos = customer_positions_in_route(base.routes[r], CG);
        if (cpos.empty()) continue;

        double score = route_ruin_score_for_longest(base, r);
        routes.push_back({score, r});
    }

    if (routes.empty()) return {};

    sort(routes.begin(), routes.end(), [](const auto &a, const auto &b) {
        return a.first > b.first;
    });

    int top = min((int)routes.size(), max(1, cfg.longest_route_ruin_top_routes));
    uniform_int_distribution<int> pick_route_dist(0, top - 1);

    int r = routes[pick_route_dist(rng)].second;
    const vector<int> &route = base.routes[r];

    vector<int> cpos = customer_positions_in_route(route, CG);
    if (cpos.empty()) return {};

    // Choose seed position. Bias toward high local removal gain inside the bad route.
    struct PosCand {
        double score;
        int pos;
    };

    vector<PosCand> pcands;

    for (int pos : cpos) {
        int node = route[pos];
        int prev = route[pos - 1];
        int next = route[pos + 1];

        double before =
            fast_pair_dist(prev, node, &pm) +
            fast_pair_dist(node, next, &pm);

        double after = fast_pair_dist(prev, next, &pm);

        if (!isfinite(before)) before = 1e12;
        if (!isfinite(after)) after = 1e12;

        double gain = before - after;

        // Demand bias: large-demand customers often dominate capacity partition.
        gain += 0.05 * CG.nodes[node].garbage_amount;

        pcands.push_back({gain, pos});
    }

    sort(pcands.begin(), pcands.end(), [](const PosCand &a, const PosCand &b) {
        return a.score > b.score;
    });

    int seed_pick_top = min((int)pcands.size(), 4);
    uniform_int_distribution<int> pick_seed_dist(0, seed_pick_top - 1);

    int seed_pos = pcands[pick_seed_dist(rng)].pos;
    int seed_node = route[seed_pos];

    vector<int> pool;
    unordered_set<int> used;

    auto add_node = [&](int node) {
        if ((int)pool.size() >= remove_target) return;
        if (node < 0 || node >= (int)CG.nodes.size()) return;
        if (CG.nodes[node].type != 2) return;
        if (used.count(node)) return;

        used.insert(node);
        pool.push_back(node);
    };

    // 1) Remove a compact block around seed inside the longest route.
    int radius = max(0, cfg.longest_route_ruin_block_radius);

    for (int delta = 0; delta <= radius; ++delta) {
        int p1 = seed_pos - delta;
        int p2 = seed_pos + delta;

        if (p1 >= 1 && p1 + 1 < (int)route.size()) {
            add_node(route[p1]);
        }

        if (p2 != p1 && p2 >= 1 && p2 + 1 < (int)route.size()) {
            add_node(route[p2]);
        }

        if ((int)pool.size() >= remove_target) break;
    }

    // 2) Add other expensive customers from the same bad route.
    vector<pair<double, int>> same_route_expensive;

    for (int pos : cpos) {
        int node = route[pos];
        if (used.count(node)) continue;

        int prev = route[pos - 1];
        int next = route[pos + 1];

        double before =
            fast_pair_dist(prev, node, &pm) +
            fast_pair_dist(node, next, &pm);

        double after = fast_pair_dist(prev, next, &pm);

        if (!isfinite(before)) before = 1e12;
        if (!isfinite(after)) after = 1e12;

        double gain = before - after;
        gain += 0.05 * CG.nodes[node].garbage_amount;

        same_route_expensive.push_back({gain, node});
    }

    sort(same_route_expensive.begin(), same_route_expensive.end(),
        [](const auto &a, const auto &b) {
            return a.first > b.first;
        });

    for (auto &p : same_route_expensive) {
        if ((int)pool.size() >= remove_target) break;
        add_node(p.second);
    }

    // 3) Add related customers globally, so repair can rebuild route ownership.
    vector<pair<double, int>> related;

    vector<int> all_customers = collect_customers_from_state(base, CG);

    for (int node : all_customers) {
        if (used.count(node)) continue;

        double sc = relatedness_score(seed_node, node, pm, CG);
        related.push_back({sc, node});
    }

    sort(related.begin(), related.end());

    int related_added = 0;
    int related_cap = cfg.longest_route_ruin_extra_related;

    for (auto &p : related) {
        if ((int)pool.size() >= remove_target) break;
        if (related_added >= related_cap && (int)pool.size() >= cfg.fragment_lns_remove_min) break;

        add_node(p.second);
        related_added++;
    }

    return pool;
}

static bool fragment_lns_repair_pool(
    SolutionState &cand,
    vector<int> pool,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    sort(pool.begin(), pool.end(), [&](int a, int b) {
        return ev.CG->nodes[a].garbage_amount > ev.CG->nodes[b].garbage_amount;
    });

    for (int node : pool) {
        bool ok = insert_customer_best_place_fast(cand, node, ev, pm);
        if (!ok) {
            return false;
        }
    }

    recompute_state_metrics_and_loads(cand, ev);
    return solution_hard_feasible(cand, *ev.CG, pm);
}

static void educate_fragment_lns_candidate_euclidean(
    SolutionState &cand,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!metric_is_euclidean()) return;
    if (!cfg.fragment_lns_euclidean_educate) return;

    recompute_state_metrics_and_loads(cand, ev);

    double start_obj = cand.objective;

    // Save old global settings.
    int old_swap_rounds = cfg.euclidean_swapstar_rounds;
    int old_swap_cap = cfg.euclidean_swapstar_scan_cap;

    int old_two_rounds = cfg.euclidean_two_opt_star_rounds;
    int old_two_cap = cfg.euclidean_two_opt_star_scan_cap;

    int old_deep_rounds = cfg.euclidean_deep_interroute_rounds;

    // Use small, cheap education inside LNS.
    cfg.euclidean_swapstar_rounds =
        min(old_swap_rounds, cfg.fragment_lns_educate_swapstar_rounds);
    cfg.euclidean_swapstar_scan_cap =
        min(old_swap_cap, cfg.fragment_lns_educate_swapstar_cap);

    cfg.euclidean_two_opt_star_rounds =
        min(old_two_rounds, cfg.fragment_lns_educate_two_opt_star_rounds);
    cfg.euclidean_two_opt_star_scan_cap =
        min(old_two_cap, cfg.fragment_lns_educate_two_opt_star_cap);

    cfg.euclidean_deep_interroute_rounds =
        min(old_deep_rounds, cfg.fragment_lns_educate_deep_rounds);

    if (cfg.euclidean_swapstar) {
        euclidean_swapstar_descent(cand, ev, pm);
        recompute_state_metrics_and_loads(cand, ev);
    }

    if (cfg.euclidean_two_opt_star) {
        euclidean_two_opt_star_descent(cand, ev, pm);
        recompute_state_metrics_and_loads(cand, ev);
    }

    if (cfg.euclidean_deep_interroute) {
        euclidean_deep_interroute_descent(cand, ev, pm);
        recompute_state_metrics_and_loads(cand, ev);
    }

    // Restore old settings.
    cfg.euclidean_swapstar_rounds = old_swap_rounds;
    cfg.euclidean_swapstar_scan_cap = old_swap_cap;

    cfg.euclidean_two_opt_star_rounds = old_two_rounds;
    cfg.euclidean_two_opt_star_scan_cap = old_two_cap;

    cfg.euclidean_deep_interroute_rounds = old_deep_rounds;

    recompute_state_metrics_and_loads(cand, ev);

    if (cand.objective + 1e-9 < start_obj) {
        cerr << "[FragmentLNS-edu] start=" << start_obj
            << " end=" << cand.objective
            << " gain=" << (start_obj - cand.objective)
            << "\n";
    }
}

static bool fragment_lns_once(
    const SolutionState &base,
    SolutionState &best,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    mt19937 &rng
) {
    int depot = depot_of(ev);

    vector<int> seeds = expensive_customers_fragment_lns(base, ev, pm);
    if (seeds.empty()) return false;

    uniform_int_distribution<int> seed_dist(0, (int)seeds.size() - 1);
    int seed = seeds[seed_dist(rng)];

    int remove_target = cfg.fragment_lns_remove_min;
    if (cfg.fragment_lns_remove_max > cfg.fragment_lns_remove_min) {
        uniform_int_distribution<int> rem_dist(
            cfg.fragment_lns_remove_min,
            cfg.fragment_lns_remove_max
        );
        remove_target = rem_dist(rng);
    }

    vector<int> pool;

    [[maybe_unused]] bool used_longest_ruin = false;

    if (cfg.use_longest_route_ruin) {
        uniform_real_distribution<double> prob_dist(0.0, 1.0);

        if (prob_dist(rng) < cfg.longest_route_ruin_probability) {
            pool = longest_route_ruin_pool(base, remove_target, ev, pm, rng);
            used_longest_ruin = !pool.empty();
        }
    }

    // Fallback: original related-customer ruin.
    if (pool.empty()) {
        vector<pair<double, int>> related;
        vector<int> all_customers = collect_customers_from_state(base, *ev.CG);

        for (int node : all_customers) {
            if (node == seed) continue;

            double sc = relatedness_score(seed, node, pm, *ev.CG);
            related.push_back({sc, node});
        }

        sort(related.begin(), related.end());

        unordered_set<int> used;

        pool.push_back(seed);
        used.insert(seed);

        for (auto &p : related) {
            if ((int)pool.size() >= remove_target) break;
            if (used.count(p.second)) continue;

            pool.push_back(p.second);
            used.insert(p.second);
        }

        // Add a few expensive customers too, to break assignment basins.
        vector<int> expensive = expensive_customers_fragment_lns(base, ev, pm);

        for (int node : expensive) {
            if ((int)pool.size() >= remove_target) break;
            if (used.count(node)) continue;

            pool.push_back(node);
            used.insert(node);
        }
    }

    // Safety: ensure pool is unique and non-empty.
    {
        vector<int> unique_pool;
        unordered_set<int> seen;

        for (int node : pool) {
            if (seen.count(node)) continue;
            seen.insert(node);
            unique_pool.push_back(node);
        }

        pool.swap(unique_pool);
    }

    if (pool.empty()) return false;

    unordered_set<int> rem(pool.begin(), pool.end());

    SolutionState cand = base;

    for (int r = 0; r < (int)cand.routes.size(); ++r) {
        cand.routes[r] = remove_nodes_from_route(cand.routes[r], rem);
        normalize_route(cand.routes[r], depot);
        enforce_trip_separators(cand.routes[r], *ev.CG, depot);
    }

    bool ok = fragment_lns_repair_pool(cand, pool, ev, pm);
    if (!ok) return false;

    // First normal local polish.
    local_polish_solution(cand, ev, pm);
    recompute_state_metrics_and_loads(cand, ev);

    // Only educate candidates that are close enough to matter.
    // This prevents FragmentLNS from spending huge time polishing hopeless repairs.
    bool promising =
        cand.objective < best.objective + 80.0 ||
        cand.objective < base.objective + 40.0;

    if (metric_is_euclidean() && cfg.fragment_lns_euclidean_educate && promising) {
        educate_fragment_lns_candidate_euclidean(cand, ev, pm);
        recompute_state_metrics_and_loads(cand, ev);
    }

    if (cand.objective + 1e-9 < best.objective) {
        best = cand;
        return true;
    }

    return false;
}

static bool fragment_lns_search(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!cfg.use_fragment_lns) return false;

    auto t0 = Clock::now();

    double start_obj = state.objective;

    SolutionState best = state;

    mt19937 rng(cfg.base_seed ^ 0x9e3779b9u ^ (unsigned)(start_obj * 1000.0));

    int accepted = 0;
    int attempted = 0;

    for (int it = 0; it < cfg.fragment_lns_rounds; ++it) {
        if (solver_should_stop()) break;

        attempted++;

        bool improved = fragment_lns_once(state, best, ev, pm, rng);

        if (improved) {
            state = best;
            accepted++;
        }
    }

    if (best.objective + 1e-9 < state.objective) {
        state = best;
    }

    recompute_state_metrics_and_loads(state, ev);

    double end_obj = state.objective;
    double gain = start_obj - end_obj;
    double elapsed = chrono::duration<double>(Clock::now() - t0).count();

    if (cfg.fragment_lns_verbose) {
        cerr << "[FragmentLNS]"
            << " start=" << start_obj
            << " end=" << end_obj
            << " gain=" << max(0.0, gain)
            << " accepted=" << accepted
            << " attempted=" << attempted
            << " removed_min=" << cfg.fragment_lns_remove_min
            << " removed_max=" << cfg.fragment_lns_remove_max
            << " longest_ruin=" << cfg.use_longest_route_ruin
            << " lr_prob=" << cfg.longest_route_ruin_probability
            << " time=" << elapsed << "s\n";
    }

    return gain > 1e-9;
}

/* ---------------- Targeted Route-Region LNS ---------------- */

static int route_region_customer_count(
    const vector<int> &route,
    const Compressed &CG
) {
    int cnt = 0;
    for (int x : route) {
        if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) {
            cnt++;
        }
    }
    return cnt;
}

static vector<pair<int, int>> route_region_rank_pairs(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const Compressed &CG = *ev.CG;
    int R = (int)state.routes.size();

    vector<tuple<double, int, int>> rows;

    for (int ra = 0; ra < R; ++ra) {
        if (route_region_customer_count(state.routes[ra], CG) == 0) continue;

        for (int rb = ra + 1; rb < R; ++rb) {
            if (route_region_customer_count(state.routes[rb], CG) == 0) continue;

            int near_hits = 0;
            double min_cross_dist = INF_D;
            double centroid_dist = INF_D;
            double bbox_overlap = 0.0;

            double score = route_pair_boundary_score(
                state,
                ev,
                pm,
                ra,
                rb,
                near_hits,
                min_cross_dist,
                centroid_dist,
                bbox_overlap
            );

            if (!isfinite(score) || score >= INF_D / 2) continue;

            // Extra pressure: expensive routes are more worth rebuilding.
            double cost_pressure = 0.0;
            if (ra < (int)state.route_metrics.size()) {
                cost_pressure += state.route_metrics[ra].weighted_cost;
            }
            if (rb < (int)state.route_metrics.size()) {
                cost_pressure += state.route_metrics[rb].weighted_cost;
            }

            // Lower score = more suspicious.
            score -= 0.00015 * cost_pressure;

            rows.push_back({score, ra, rb});
        }
    }

    sort(rows.begin(), rows.end());

    vector<pair<int, int>> out;
    int lim = min((int)rows.size(), max(1, cfg.route_region_lns_seed_pairs));

    for (int i = 0; i < lim; ++i) {
        auto [score, ra, rb] = rows[i];
        (void)score;
        out.push_back({ra, rb});
    }

    return out;
}

static double route_to_region_distance(
    const SolutionState &state,
    const Compressed &CG,
    PairwiseManager &pm,
    int route_id,
    const vector<int> &region_routes
) {
    if (route_id < 0 || route_id >= (int)state.routes.size()) {
        return INF_D;
    }

    vector<int> A = route_customer_nodes(state.routes[route_id], CG);
    if (A.empty()) return INF_D;

    double best = INF_D;

    for (int rr : region_routes) {
        if (rr < 0 || rr >= (int)state.routes.size()) continue;
        if (rr == route_id) continue;

        vector<int> B = route_customer_nodes(state.routes[rr], CG);
        if (B.empty()) continue;

        for (int a : A) {
            for (int b : B) {
                double d1 = fast_pair_dist(a, b, &pm);
                double d2 = fast_pair_dist(b, a, &pm);

                if (isfinite(d1)) best = min(best, d1);
                if (isfinite(d2)) best = min(best, d2);
            }
        }
    }

    return best;
}

static vector<int> route_region_expand_routes(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int ra,
    int rb
) {
    const Compressed &CG = *ev.CG;
    int R = (int)state.routes.size();

    vector<int> region;
    unordered_set<int> used;

    auto add_route = [&](int r) {
        if (r < 0 || r >= R) return;
        if (route_region_customer_count(state.routes[r], CG) == 0) return;
        if (used.insert(r).second) {
            region.push_back(r);
        }
    };

    add_route(ra);
    add_route(rb);

    while ((int)region.size() < max(2, cfg.route_region_lns_max_routes)) {
        vector<pair<double, int>> cand_routes;

        for (int r = 0; r < R; ++r) {
            if (used.count(r)) continue;
            if (route_region_customer_count(state.routes[r], CG) == 0) continue;

            double d = route_to_region_distance(
                state,
                CG,
                pm,
                r,
                region
            );

            if (!isfinite(d) || d >= INF_D / 2) continue;

            // Prefer nearby expensive routes.
            double pressure = 0.0;
            if (r < (int)state.route_metrics.size()) {
                pressure = state.route_metrics[r].weighted_cost;
            }

            double score = d - 0.00010 * pressure;
            cand_routes.push_back({score, r});
        }

        if (cand_routes.empty()) break;

        sort(cand_routes.begin(), cand_routes.end());
        add_route(cand_routes.front().second);
    }

    return region;
}

static void route_region_add_node_with_neighbors(
    vector<int> &pool,
    unordered_set<int> &seen,
    const vector<int> &route,
    const Compressed &CG,
    int node
) {
    int pos = -1;

    for (int i = 0; i < (int)route.size(); ++i) {
        if (route[i] == node) {
            pos = i;
            break;
        }
    }

    if (pos < 0) return;

    auto add_one = [&](int x) {
        if (x < 0 || x >= (int)CG.nodes.size()) return;
        if (CG.nodes[x].type != 2) return;

        if (seen.insert(x).second) {
            pool.push_back(x);
        }
    };

    add_one(route[pos]);

    int rad = max(0, cfg.route_region_lns_neighbor_radius);

    for (int d = 1; d <= rad; ++d) {
        if (pos - d >= 0) add_one(route[pos - d]);
        if (pos + d < (int)route.size()) add_one(route[pos + d]);
    }
}

static double route_region_local_removal_score(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int r,
    int pos,
    const vector<int> &region_routes
) {
    const Compressed &CG = *ev.CG;

    if (r < 0 || r >= (int)state.routes.size()) return -INF_D;

    const vector<int> &route = state.routes[r];

    if (pos <= 0 || pos + 1 >= (int)route.size()) return -INF_D;

    int node = route[pos];

    if (node < 0 || node >= (int)CG.nodes.size()) return -INF_D;
    if (CG.nodes[node].type != 2) return -INF_D;

    int prev = route[pos - 1];
    int next = route[pos + 1];

    double before =
        fast_pair_dist(prev, node, &pm) +
        fast_pair_dist(node, next, &pm);

    double after = fast_pair_dist(prev, next, &pm);

    if (!isfinite(before)) before = 1e12;
    if (!isfinite(after)) after = 1e12;

    double remove_gain = before - after;

    double cross_attraction = INF_D;

    for (int rr : region_routes) {
        if (rr == r) continue;
        if (rr < 0 || rr >= (int)state.routes.size()) continue;

        for (int y : state.routes[rr]) {
            if (y < 0 || y >= (int)CG.nodes.size()) continue;
            if (CG.nodes[y].type != 2) continue;

            double d1 = fast_pair_dist(node, y, &pm);
            double d2 = fast_pair_dist(y, node, &pm);

            if (isfinite(d1)) cross_attraction = min(cross_attraction, d1);
            if (isfinite(d2)) cross_attraction = min(cross_attraction, d2);
        }
    }

    if (!isfinite(cross_attraction) || cross_attraction >= INF_D / 2) {
        cross_attraction = 1e9;
    }

    double route_pressure = 0.0;

    if (r < (int)state.route_metrics.size()) {
        route_pressure = 0.00020 * state.route_metrics[r].weighted_cost;
    }

    double demand_pressure = 0.03 * CG.nodes[node].garbage_amount;

    // Higher score = better removal candidate.
    return
        remove_gain +
        route_pressure +
        demand_pressure -
        0.002 * cross_attraction;
}

static vector<int> route_region_build_remove_pool(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    const vector<int> &region_routes,
    int remove_target
) {
    const Compressed &CG = *ev.CG;

    vector<int> pool;
    unordered_set<int> seen;

    // 1) Boundary signal: customers that look closer to another region route.
    for (int ra : region_routes) {
        if (ra < 0 || ra >= (int)state.routes.size()) continue;

        for (int rb : region_routes) {
            if (ra == rb) continue;
            if (rb < 0 || rb >= (int)state.routes.size()) continue;

            vector<int> boundary_nodes = route_boundary_customers_against(
                state.routes[ra],
                state.routes[rb],
                CG,
                pm
            );

            for (int x : boundary_nodes) {
                route_region_add_node_with_neighbors(
                    pool,
                    seen,
                    state.routes[ra],
                    CG,
                    x
                );

                if ((int)pool.size() >= remove_target) break;
            }

            if ((int)pool.size() >= remove_target) break;
        }

        if ((int)pool.size() >= remove_target) break;
    }

    // 2) Fill with high-removal-gain / expensive / cross-attracted nodes.
    vector<pair<double, int>> scored;

    unordered_set<int> region_set(region_routes.begin(), region_routes.end());

    for (int r : region_routes) {
        if (r < 0 || r >= (int)state.routes.size()) continue;

        const vector<int> &route = state.routes[r];

        for (int pos = 1; pos + 1 < (int)route.size(); ++pos) {
            int node = route[pos];

            if (node < 0 || node >= (int)CG.nodes.size()) continue;
            if (CG.nodes[node].type != 2) continue;
            if (seen.count(node)) continue;

            double sc = route_region_local_removal_score(
                state,
                ev,
                pm,
                r,
                pos,
                region_routes
            );

            if (!isfinite(sc)) continue;

            scored.push_back({sc, node});
        }
    }

    sort(scored.begin(), scored.end(), [](const auto &a, const auto &b) {
        return a.first > b.first;
    });

    for (auto &p : scored) {
        if ((int)pool.size() >= remove_target) break;

        int node = p.second;

        if (seen.insert(node).second) {
            pool.push_back(node);
        }
    }

    // 3) If pool is too big, keep strongest nodes only.
    if ((int)pool.size() > remove_target) {
        unordered_map<int, double> score_map;

        for (auto &p : scored) {
            score_map[p.second] = p.first;
        }

        vector<pair<double, int>> keep;

        for (int x : pool) {
            double sc = 0.0;

            auto it = score_map.find(x);
            if (it != score_map.end()) {
                sc = it->second;
            } else {
                // Boundary nodes that were not in scored list should stay important.
                sc = 1e9;
            }

            keep.push_back({sc, x});
        }

        sort(keep.begin(), keep.end(), [](const auto &a, const auto &b) {
            return a.first > b.first;
        });

        pool.clear();

        for (int i = 0; i < min(remove_target, (int)keep.size()); ++i) {
            pool.push_back(keep[i].second);
        }
    }

    return pool;
}

static bool route_region_repair_order(
    const SolutionState &base_removed,
    const vector<int> &order,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    SolutionState &out
) {
    SolutionState cand = base_removed;

    for (int node : order) {
        bool ok = insert_customer_best_place_fast(cand, node, ev, pm);
        if (!ok) {
            return false;
        }
    }

    recompute_state_metrics_and_loads(cand, ev);

    if (!solution_hard_feasible(cand, *ev.CG, pm)) {
        return false;
    }

    // Cheap education after repair.
    local_polish_solution(cand, ev, pm);
    recompute_state_metrics_and_loads(cand, ev);

    if (!solution_hard_feasible(cand, *ev.CG, pm)) {
        return false;
    }

    out = std::move(cand);
    return true;
}

static bool route_region_lns_once(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    int ra,
    int rb,
    int round
) {
    const Compressed &CG = *ev.CG;
    int depot = find_depot_idx(CG);

    if (ra == rb) return false;
    if (ra < 0 || rb < 0) return false;
    if (ra >= (int)state.routes.size() || rb >= (int)state.routes.size()) return false;

    vector<int> region_routes = route_region_expand_routes(
        state,
        ev,
        pm,
        ra,
        rb
    );

    if ((int)region_routes.size() < 2) return false;

    int lo = max(2, cfg.route_region_lns_remove_min);
    int hi = max(lo, cfg.route_region_lns_remove_max);

    // Deterministic budget sweep instead of RNG.
    int remove_target = lo;
    if (hi > lo) {
        int span = hi - lo + 1;
        remove_target = lo + (round * 13 + ra * 7 + rb * 5) % span;
    }

    vector<int> pool = route_region_build_remove_pool(
        state,
        ev,
        pm,
        region_routes,
        remove_target
    );

    if ((int)pool.size() < lo) return false;

    unordered_set<int> rem(pool.begin(), pool.end());

    SolutionState base_removed = state;

    for (int r = 0; r < (int)base_removed.routes.size(); ++r) {
        base_removed.routes[r] = remove_nodes_from_route(
            base_removed.routes[r],
            rem
        );

        normalize_route(base_removed.routes[r], depot);
        enforce_trip_separators(base_removed.routes[r], CG, depot);
    }

    recompute_state_metrics_and_loads(base_removed, ev);

    vector<vector<int>> orders;

    // 1) Boundary/score order.
    orders.push_back(pool);

    // 2) Demand descending.
    vector<int> demand_order = pool;
    sort(demand_order.begin(), demand_order.end(), [&](int a, int b) {
        return CG.nodes[a].garbage_amount > CG.nodes[b].garbage_amount;
    });
    orders.push_back(demand_order);

    // 3) Demand ascending. Sometimes small customers repair route shape first.
    vector<int> demand_asc = pool;
    sort(demand_asc.begin(), demand_asc.end(), [&](int a, int b) {
        return CG.nodes[a].garbage_amount < CG.nodes[b].garbage_amount;
    });
    orders.push_back(demand_asc);

    // 4) Farthest-from-depot first.
    vector<int> far_depot = pool;
    sort(far_depot.begin(), far_depot.end(), [&](int a, int b) {
        double da = fast_pair_dist(depot, a, &pm);
        double db = fast_pair_dist(depot, b, &pm);

        if (!isfinite(da)) da = 1e15;
        if (!isfinite(db)) db = 1e15;

        return da > db;
    });
    orders.push_back(far_depot);

    // 5) Reverse boundary order.
    vector<int> rev = pool;
    reverse(rev.begin(), rev.end());
    orders.push_back(rev);

    SolutionState best_candidate = state;
    double best_obj = state.objective;
    bool improved = false;

    for (const auto &ord : orders) {
        SolutionState cand;

        bool ok = route_region_repair_order(
            base_removed,
            ord,
            ev,
            pm,
            cand
        );

        if (!ok) continue;

        if (cand.objective + 1e-9 < best_obj) {
            best_obj = cand.objective;
            best_candidate = std::move(cand);
            improved = true;
        }
    }

    if (!improved) return false;

    double old_obj = state.objective;

    state = std::move(best_candidate);
    recompute_state_metrics_and_loads(state, ev);

    if (cfg.route_region_lns_verbose) {
        cerr << "[RouteRegionLNS] accept"
            << " pair=(" << ra << "," << rb << ")"
            << " region_routes={";

        for (int r : region_routes) cerr << r << " ";

        cerr << "} removed=" << pool.size()
            << " old=" << old_obj
            << " new=" << state.objective
            << " gain=" << (old_obj - state.objective)
            << "\n";
    }

    return true;
}

static bool route_region_lns_descent(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!cfg.use_route_region_lns) return false;
    if (cfg.route_region_lns_rounds <= 0) return false;

    recompute_state_metrics_and_loads(state, ev);

    double start_obj = state.objective;
    int accepted = 0;

    auto t0 = Clock::now();

    for (int round = 0; round < cfg.route_region_lns_rounds; ++round) {
        if (solver_should_stop()) break;

        vector<pair<int, int>> pairs = route_region_rank_pairs(
            state,
            ev,
            pm
        );

        bool round_improved = false;

        for (auto [ra, rb] : pairs) {
            if (solver_should_stop()) break;

            bool ok = route_region_lns_once(
                state,
                ev,
                pm,
                ra,
                rb,
                round
            );

            if (ok) {
                accepted++;
                round_improved = true;

                // Rerank after each accepted region rebuild.
                break;
            }
        }

        if (!round_improved) {
            break;
        }
    }

    recompute_state_metrics_and_loads(state, ev);

    double elapsed = chrono::duration<double>(Clock::now() - t0).count();
    double gain = start_obj - state.objective;

    if (cfg.route_region_lns_verbose) {
        cerr << "[RouteRegionLNS]"
            << " start=" << start_obj
            << " end=" << state.objective
            << " gain=" << max(0.0, gain)
            << " accepted=" << accepted
            << " rounds=" << cfg.route_region_lns_rounds
            << " seed_pairs=" << cfg.route_region_lns_seed_pairs
            << " max_routes=" << cfg.route_region_lns_max_routes
            << " remove_min=" << cfg.route_region_lns_remove_min
            << " remove_max=" << cfg.route_region_lns_remove_max
            << " time=" << elapsed << "s\n";
    }

    return gain > 1e-9;
}


// -----------------------------------------------------------------------------
// V3.2: hard-feasible fleet-elimination LNS.
//
// The legacy FULL search mostly hopes that generic relocate/LNS moves eventually
// empty a route.  For fleet-first VRPTW that is an unnecessarily difficult basin
// transition.  This operator explicitly chooses a sparse active route, removes
// all of its customers, and uses regret-2 insertion into already-active routes.
// The source route is forbidden during repair, so a successful move really
// eliminates one vehicle.  Every insertion is capacity- and hard-TW-feasible;
// the entire move is transactional and accepted only if the final exact
// objective improves.
// -----------------------------------------------------------------------------
struct FleetElimInsertion {
    bool ok = false;
    int route = -1;
    int pos = -1;
    double best_delta = INF_D;
    double second_delta = INF_D;
};

static int route_customer_count_hard(const vector<int> &route, const Compressed &CG) {
    int c = 0;
    for (int node : route) if (node >= 0 && node < (int)CG.nodes.size() && CG.nodes[node].type == 2) c++;
    return c;
}

static FleetElimInsertion fleet_elim_best_insertion(
    const SolutionState &state,
    int node,
    int banned_route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    FleetElimInsertion ans;
    const int depot = depot_of(ev);

    const int elim_route_cap = (int)state.routes.size();
    vector<int> route_order = get_best_routes_for_node(
        state.routes, pm, node, elim_route_cap
    );

    for (int r : route_order) {
        if (solver_should_stop()) return ans;
        if (r == banned_route || r < 0 || r >= (int)state.routes.size()) continue;
        const auto &route = state.routes[r];
        // Do not create a replacement vehicle elsewhere.
        if (route_customer_count_hard(route, *ev.CG) == 0) continue;
        if ((int)route.size() < 2) continue;

        double old_cost = route_exact_cost(route, ev);
        if (!isfinite(old_cost) || old_cost >= INF_D / 2) continue;

        vector<pair<double,int>> ranked;
        int max_pos = min((int)route.size() - 1, max(1, cfg.insertion_pos_cap));
        ranked.reserve(max_pos);
        for (int pos = 1; pos <= max_pos; ++pos) {
            int prev = route[pos - 1];
            int next = route[pos];
            double old_edge = fast_pair_search_cost(prev, next, &pm);
            double new_edges = fast_pair_search_cost(prev, node, &pm) +
                               fast_pair_search_cost(node, next, &pm);
            if (!isfinite(old_edge) || !isfinite(new_edges)) continue;
            ranked.push_back({new_edges - old_edge, pos});
        }
        sort(ranked.begin(), ranked.end());
        int pos_cap = min((int)ranked.size(), max(12, min(36, cfg.insertion_topk_exact)));

        for (int k = 0; k < pos_cap; ++k) {
            if (solver_should_stop()) return ans;
            int pos = ranked[k].second;
            vector<int> cand_route = route;
            cand_route.insert(cand_route.begin() + pos, node);
            normalize_route(cand_route, depot);
            enforce_trip_separators(cand_route, *ev.CG, depot);
            if (!trips_feasible_for_route(cand_route, *ev.CG, depot)) continue;
            if (cfg.use_time_window && !route_hard_tw_feasible(cand_route, ev, pm)) continue;

            double delta = route_exact_cost(cand_route, ev) - old_cost;
            if (delta + 1e-12 < ans.best_delta) {
                ans.second_delta = ans.best_delta;
                ans.best_delta = delta;
                ans.route = r;
                ans.pos = pos;
                ans.ok = true;
            } else if (delta + 1e-12 < ans.second_delta) {
                ans.second_delta = delta;
            }
        }
    }
    return ans;
}


// V10 targeted ejection-chain step.  It is invoked only when one source
// customer has no direct hard-feasible insertion.  A candidate destination
// route temporarily ejects one of its customers, inserts the blocked source
// customer, then immediately reinserts the ejected customer into any active
// non-source route.  The state remains route-feasible after the completed
// chain; the overall source-route elimination stays transactional.
struct FleetEjectionStep {
    bool ok = false;
    SolutionState state;
    double score = INF_D;
    int target_route = -1;
    int ejected_node = -1;
};

static bool fleet_best_insert_into_specific_route(
    const vector<int> &base_route,
    int node,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    vector<int> &best_route,
    double &best_delta
) {
    const int depot = depot_of(ev);
    const double old_cost = route_exact_cost(base_route, ev);
    if (!isfinite(old_cost) || old_cost >= INF_D/2) return false;
    vector<pair<double,int>> ranked;
    const int max_pos = min((int)base_route.size()-1, max(1,cfg.insertion_pos_cap));
    for (int pos=1; pos<=max_pos; ++pos) {
        const int prev=base_route[pos-1], next=base_route[pos];
        const double oe=fast_pair_search_cost(prev,next,&pm);
        const double ne=fast_pair_search_cost(prev,node,&pm)+fast_pair_search_cost(node,next,&pm);
        if (isfinite(oe) && isfinite(ne)) ranked.push_back({ne-oe,pos});
    }
    sort(ranked.begin(),ranked.end());
    const int cap=min((int)ranked.size(), max(12,min(48,cfg.insertion_topk_exact)));
    best_delta=INF_D;
    bool ok=false;
    for (int k=0;k<cap;++k) {
        if (solver_should_stop()) break;
        vector<int> r=base_route;
        r.insert(r.begin()+ranked[k].second,node);
        normalize_route(r,depot);
        enforce_trip_separators(r,*ev.CG,depot);
        if (!trips_feasible_for_route(r,*ev.CG,depot)) continue;
        if (cfg.use_time_window && !route_hard_tw_feasible(r,ev,pm)) continue;
        const double d=route_exact_cost(r,ev)-old_cost;
        if (d+1e-12<best_delta) { best_delta=d; best_route=std::move(r); ok=true; }
    }
    return ok;
}

static bool fleet_ejection_chain_step(
    const SolutionState &cand,
    int blocked_node,
    int source_route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    SolutionState &out
) {
    if (!cfg.use_fleet_ejection_chain) return false;
    profile.fleet_ejection_chain_attempts.fetch_add(1,memory_order_relaxed);
    const int depot=depot_of(ev);
    vector<int> route_order=get_best_routes_for_node(cand.routes,pm,blocked_node,(int)cand.routes.size());
    if ((int)route_order.size()>cfg.fleet_ejection_route_scan_cap)
        route_order.resize(cfg.fleet_ejection_route_scan_cap);

    FleetEjectionStep best;
    for (int r:route_order) {
        if (solver_should_stop()) return false;
        if (r==source_route || r<0 || r>=(int)cand.routes.size()) continue;
        if (route_customer_count_hard(cand.routes[r],*ev.CG)<=1) continue;
        const vector<int> original=cand.routes[r];
        vector<int> eject_positions;
        for (int p=1;p+1<(int)original.size();++p) {
            int y=original[p];
            if (y>=0 && y<(int)ev.CG->nodes.size() && ev.CG->nodes[y].type==2) eject_positions.push_back(p);
        }
        // Capacity relief first, then deterministic node id: this is a bounded
        // heuristic ordering, not random related-customer removal.
        sort(eject_positions.begin(),eject_positions.end(),[&](int a,int b){
            int ya=original[a], yb=original[b];
            double da=ev.CG->nodes[ya].garbage_amount, db=ev.CG->nodes[yb].garbage_amount;
            if (fabs(da-db)>1e-9) return da>db;
            return ya<yb;
        });
        if ((int)eject_positions.size()>cfg.fleet_ejection_customer_scan_cap)
            eject_positions.resize(cfg.fleet_ejection_customer_scan_cap);

        for (int ep:eject_positions) {
            if (solver_should_stop()) return false;
            profile.fleet_ejection_chain_candidates.fetch_add(1,memory_order_relaxed);
            const int y=original[ep];
            vector<int> reduced=original;
            reduced.erase(reduced.begin()+ep);
            normalize_route(reduced,depot);
            enforce_trip_separators(reduced,*ev.CG,depot);
            if (!trips_feasible_for_route(reduced,*ev.CG,depot)) continue;
            if (cfg.use_time_window && !route_hard_tw_feasible(reduced,ev,pm)) continue;

            vector<int> with_blocked;
            double delta_blocked=INF_D;
            if (!fleet_best_insert_into_specific_route(reduced,blocked_node,ev,pm,with_blocked,delta_blocked)) continue;

            SolutionState temp=cand;
            temp.routes[r]=std::move(with_blocked);
            recompute_dirty_routes(temp,ev,{r});
            FleetElimInsertion rein=fleet_elim_best_insertion(temp,y,source_route,ev,pm);
            if (!rein.ok) continue;
            temp.routes[rein.route].insert(temp.routes[rein.route].begin()+rein.pos,y);
            normalize_route(temp.routes[rein.route],depot);
            enforce_trip_separators(temp.routes[rein.route],*ev.CG,depot);
            recompute_dirty_routes(temp,ev,{r,rein.route});

            // Full global coverage is intentionally not checked yet because
            // other source-route customers remain in the repair pool. Route
            // capacity/TW feasibility has already been checked for both edits.
            const double score=delta_blocked+rein.best_delta;
            if (!best.ok || score+1e-9<best.score) {
                best.ok=true; best.state=std::move(temp); best.score=score;
                best.target_route=r; best.ejected_node=y;
            }
        }
    }
    if (!best.ok) return false;
    out=std::move(best.state);
    profile.fleet_ejection_chain_successes.fetch_add(1,memory_order_relaxed);
    safe_log_line("[FleetEjectionChain] blocked=",blocked_node,
                  " target_route=",best.target_route,
                  " ejected=",best.ejected_node,
                  " score=",best.score,
                  " time_s=",solver_elapsed_seconds());
    return true;
}

static bool fleet_elimination_try_source(
    const SolutionState &base,
    SolutionState &out,
    int source_route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const int depot = depot_of(ev);
    if (source_route < 0 || source_route >= (int)base.routes.size()) return false;

    vector<int> pool;
    for (int node : base.routes[source_route]) {
        if (node >= 0 && node < (int)ev.CG->nodes.size() && ev.CG->nodes[node].type == 2) pool.push_back(node);
    }
    if (pool.empty()) return false;

    SolutionState cand = base;
    cand.routes[source_route] = {depot, depot};
    recompute_state_metrics_and_loads(cand, ev);

    vector<int> remaining = pool;
    while (!remaining.empty()) {
        if (solver_should_stop()) return false;

        int chosen_idx = -1;
        int blocked_idx = -1;
        FleetElimInsertion chosen;
        double chosen_regret = -INF_D;

        for (int i = 0; i < (int)remaining.size(); ++i) {
            FleetElimInsertion ins = fleet_elim_best_insertion(
                cand, remaining[i], source_route, ev, pm
            );
            if (!ins.ok) { blocked_idx = i; break; }
            double second = isfinite(ins.second_delta) && ins.second_delta < INF_D/2
                ? ins.second_delta : (ins.best_delta + 1e6);
            double regret = second - ins.best_delta;
            if (chosen_idx < 0 || regret > chosen_regret + 1e-9 ||
                (fabs(regret - chosen_regret) <= 1e-9 && ins.best_delta < chosen.best_delta)) {
                chosen_idx = i;
                chosen = ins;
                chosen_regret = regret;
            }
        }

        if (blocked_idx >= 0) {
            static thread_local int ejections_this_source = 0;
            // reset when the repair pool is still complete at source entry
            if ((int)remaining.size() == (int)pool.size()) ejections_this_source = 0;
            if (ejections_this_source >= cfg.fleet_ejection_max_per_source) return false;
            SolutionState chained;
            const int blocked = remaining[blocked_idx];
            if (!fleet_ejection_chain_step(cand, blocked, source_route, ev, pm, chained)) return false;
            cand = std::move(chained);
            remaining.erase(remaining.begin() + blocked_idx);
            ++ejections_this_source;
            continue;
        }

        if (chosen_idx < 0) return false;
        int node = remaining[chosen_idx];
        cand.routes[chosen.route].insert(cand.routes[chosen.route].begin() + chosen.pos, node);
        normalize_route(cand.routes[chosen.route], depot);
        enforce_trip_separators(cand.routes[chosen.route], *ev.CG, depot);
        recompute_dirty_routes(cand, ev, {chosen.route});
        remaining.erase(remaining.begin() + chosen_idx);
    }

    recompute_state_metrics_and_loads(cand, ev);
    if (!solution_hard_feasible(cand, *ev.CG, pm)) return false;
    if (!(cand.objective + 1e-9 < base.objective)) return false;
    out = std::move(cand);
    return true;
}

static bool fleet_elimination_lns(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    unsigned diversification_seed,
    int source_cap = 10
) {
    profile.fleet_elim_calls.fetch_add(1, memory_order_relaxed);
    if (cfg.solomon_vehicle_penalty <= 0.0) return false;
    recompute_state_metrics_and_loads(state, ev);
    if (!solution_hard_feasible(state, *ev.CG, pm)) return false;

    struct Src { int count; double load; int r; };
    vector<Src> srcs;
    for (int r = 0; r < (int)state.routes.size(); ++r) {
        int c = route_customer_count_hard(state.routes[r], *ev.CG);
        if (c <= 0) continue;
        double load = (r < (int)state.route_load.size()) ? state.route_load[r] : 0.0;
        srcs.push_back({c, load, r});
    }
    sort(srcs.begin(), srcs.end(), [](const Src &a, const Src &b) {
        if (a.count != b.count) return a.count < b.count;
        if (fabs(a.load - b.load) > 1e-9) return a.load < b.load;
        return a.r < b.r;
    });
    // Diversify the specialized worker across the ranked active routes while
    // still retaining the complete list. No source is hidden because this
    // designated worker is allowed to scan the full ranked set until deadline.
    if (!srcs.empty()) {
        size_t shift = (size_t)(diversification_seed % (unsigned)srcs.size());
        rotate(srcs.begin(), srcs.begin() + shift, srcs.end());
    }

    int attempts = 0;
    for (const auto &src : srcs) {
        if (attempts++ >= source_cap || solver_should_stop()) break;
        SolutionState cand;
        if (fleet_elimination_try_source(state, cand, src.r, ev, pm)) {
            double before = state.objective;
            state = std::move(cand);
            profile.fleet_elim_successes.fetch_add(1, memory_order_relaxed);
            update_global_best_checked(state, *ev.CG, pm);
            safe_log_line("[FleetElim] time_s=",solver_elapsed_seconds(),
                          " source=",src.r," customers=",src.count,
                          " before=",before," after=",state.objective,
                          " gain=",(before-state.objective));
            return true;
        }
    }
    return false;
}

static void final_refinement_pass(SolutionState &state, ObjectiveEvaluator &ev, PairwiseManager &pm) {
    recompute_state_metrics_and_loads(state, ev);

    // Final refinement is now strictly transactional. Exploration is allowed to
    // use soft TW states elsewhere, but this exploitation phase never replaces a
    // hard-feasible incumbent with an infeasible or non-improving candidate.
    if (!solution_hard_feasible(state, *ev.CG, pm)) return;

    SolutionState best = state;
    int rounds = max(1, cfg.final_refinement_rounds);

    auto accept_stage = [&](const char *name, auto &&fn) -> bool {
        if (solver_should_stop()) return false;
        SolutionState cand = best;
        fn(cand);
        recompute_state_metrics_and_loads(cand, ev);
        if (!solution_hard_feasible(cand, *ev.CG, pm)) return false;
        if (cand.objective + 1e-9 < best.objective) {
            double before = best.objective;
            best = std::move(cand);
            update_global_best_checked(best, *ev.CG, pm);
            cerr << "[RefineTxn] stage=" << name
                 << " before=" << before
                 << " after=" << best.objective
                 << " gain=" << (before - best.objective) << "\n";
            return true;
        }
        return false;
    };

    for (int round = 0; round < rounds && !solver_should_stop(); ++round) {
        bool changed = false;

        if (cfg.use_relocate_polish || cfg.use_oropt || cfg.use_2opt) {
            changed |= accept_stage("local", [&](SolutionState &cand) {
                local_polish_solution(cand, ev, pm);
            });
        }

        if (cfg.use_alns) {
            unsigned alns_seed = cfg.base_seed ^ 0xA5A5A5A5u ^
                                 (unsigned)(round * 1000003u);
            changed |= accept_stage("alns", [&](SolutionState &cand) {
                adaptive_lns_polish(cand, ev, pm, cfg.alns_rounds, alns_seed);
            });
        }

        if (cfg.use_interroute_polish) {
            changed |= accept_stage("interroute", [&](SolutionState &cand) {
                interroute_polish_solution(cand, ev, pm);
            });
        }

        if (cfg.use_guided_arc_penalty) {
            changed |= accept_stage("gls", [&](SolutionState &cand) {
                guided_arc_penalty_search(cand, ev, pm);
            });
        }

        if (cfg.use_fragment_lns) {
            changed |= accept_stage("fragment", [&](SolutionState &cand) {
                fragment_lns_search(cand, ev, pm);
            });
        }

        if (cfg.use_route_region_lns) {
            changed |= accept_stage("route_region", [&](SolutionState &cand) {
                route_region_lns_descent(cand, ev, pm);
            });
        }

        if (cfg.use_final_polish) {
            changed |= accept_stage("cleanup", [&](SolutionState &cand) {
                final_route_cleanup(cand, ev, pm);
            });
        }

        if (!changed) break;
    }

    state = std::move(best);
    recompute_state_metrics_and_loads(state, ev);
    update_global_best_checked(state, *ev.CG, pm);
}

static void elite_pool_update(vector<SolutionState> &pool, const SolutionState &cand, size_t maxK) {
    for (auto &x : pool) {
        if (x.routes == cand.routes) {
            if (cand.objective + 1e-9 < x.objective) x = cand;
            sort(pool.begin(), pool.end(), [](const SolutionState &a, const SolutionState &b){ return a.objective < b.objective; });
            return;
        }
    }
    pool.push_back(cand);
    sort(pool.begin(), pool.end(), [](const SolutionState &a, const SolutionState &b){ return a.objective < b.objective; });
    if (pool.size() > maxK) pool.resize(maxK);
}

static SolutionState path_relink_between(
    const SolutionState &a,
    const SolutionState &b,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    profile.path_relink_calls.fetch_add(1, memory_order_relaxed);

    const Compressed &CG = *ev.CG;
    const int depot = depot_of(ev);
    const int R = min((int)a.routes.size(), (int)b.routes.size());

    SolutionState cur = a;
    recompute_state_metrics_and_loads(cur, ev);
    if (!solution_hard_feasible(cur, CG, pm) || R <= 0) return a;

    SolutionState best = cur;

    // Route labels are arbitrary. Align guide routes to current route slots by
    // maximum customer overlap before defining a target assignment.
    vector<unordered_set<int>> a_sets(R), b_sets(R);
    for (int r = 0; r < R; ++r) {
        for (int x : a.routes[r]) if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) a_sets[r].insert(x);
        for (int x : b.routes[r]) if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) b_sets[r].insert(x);
    }

    vector<int> guide_to_slot(R, -1);
    vector<char> slot_used(R, 0), guide_used(R, 0);
    for (int match = 0; match < R; ++match) {
        int best_g = -1, best_s = -1, best_overlap = -1;
        for (int g = 0; g < R; ++g) if (!guide_used[g]) {
            for (int s = 0; s < R; ++s) if (!slot_used[s]) {
                int ov = 0;
                if (b_sets[g].size() < a_sets[s].size()) {
                    for (int x : b_sets[g]) ov += a_sets[s].count(x) ? 1 : 0;
                } else {
                    for (int x : a_sets[s]) ov += b_sets[g].count(x) ? 1 : 0;
                }
                if (ov > best_overlap) {
                    best_overlap = ov; best_g = g; best_s = s;
                }
            }
        }
        if (best_g < 0 || best_s < 0) break;
        guide_to_slot[best_g] = best_s;
        guide_used[best_g] = 1;
        slot_used[best_s] = 1;
    }

    vector<int> target_route(CG.nodes.size(), -1);
    for (int g = 0; g < R; ++g) {
        int slot = guide_to_slot[g];
        if (slot < 0) continue;
        for (int x : b.routes[g]) {
            if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) {
                target_route[x] = slot;
            }
        }
    }

    const int customer_count = (int)customer_nodes_global.size();
    const int max_steps = max(1, min(customer_count * 2, 512));

    for (int step = 0; step < max_steps; ++step) {
        if (solver_should_stop()) {
            profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed);
            break;
        }

        vector<int> owner(CG.nodes.size(), -1), pos(CG.nodes.size(), -1);
        vector<int> mismatched;
        for (int r = 0; r < R; ++r) {
            for (int p = 1; p + 1 < (int)cur.routes[r].size(); ++p) {
                int x = cur.routes[r][p];
                if (x < 0 || x >= (int)CG.nodes.size() || CG.nodes[x].type != 2) continue;
                owner[x] = r; pos[x] = p;
                if (target_route[x] >= 0 && target_route[x] != r) mismatched.push_back(x);
            }
        }
        if (mismatched.empty()) break;

        // Bound each relink step. Candidate order favors customers whose target
        // route is currently least loaded, which tends to preserve feasibility.
        stable_sort(mismatched.begin(), mismatched.end(), [&](int x, int y) {
            int tx = target_route[x], ty = target_route[y];
            double lx = (tx >= 0 && tx < (int)cur.route_max_trip_load.size()) ? cur.route_max_trip_load[tx] : INF_D;
            double ly = (ty >= 0 && ty < (int)cur.route_max_trip_load.size()) ? cur.route_max_trip_load[ty] : INF_D;
            return lx < ly;
        });
        if ((int)mismatched.size() > 96) mismatched.resize(96);

        bool found = false;
        SolutionState best_next;
        double best_next_obj = INF_D;
        int best_reduction = 0;

        // First try a direct move to the guide-assigned route. Every candidate
        // remains hard feasible; the path may temporarily worsen the objective.
        for (int x : mismatched) {
            int rf = owner[x];
            int rt = target_route[x];
            int pf = pos[x];
            if (rf < 0 || rt < 0 || rf == rt || rt >= R || pf <= 0) continue;

            const int pos_cap = min((int)cur.routes[rt].size() - 1, 80);
            for (int pt = 1; pt <= pos_cap; ++pt) {
                vector<int> from = cur.routes[rf];
                vector<int> to = cur.routes[rt];
                if (pf >= (int)from.size() - 1) continue;
                from.erase(from.begin() + pf);
                to.insert(to.begin() + pt, x);
                normalize_route(from, depot);
                normalize_route(to, depot);
                enforce_trip_separators(from, CG, depot);
                enforce_trip_separators(to, CG, depot);
                if (!trips_feasible_for_route(from, CG, depot) || !trips_feasible_for_route(to, CG, depot)) continue;
                if (cfg.use_time_window && (!route_hard_tw_feasible(from, ev, pm) || !route_hard_tw_feasible(to, ev, pm))) continue;

                SolutionState cand = cur;
                cand.routes[rf] = std::move(from);
                cand.routes[rt] = std::move(to);
                recompute_dirty_routes(cand, ev, {rf, rt});
                if (!solution_hard_feasible(cand, CG, pm)) continue;

                if (!found || cand.objective + 1e-9 < best_next_obj) {
                    found = true;
                    best_next_obj = cand.objective;
                    best_next = std::move(cand);
                    best_reduction = 1;
                }
            }
        }

        // If capacity/TW blocks all direct moves, try a reciprocal swap that
        // moves two customers toward their guide routes simultaneously.
        if (!found) {
            for (int x : mismatched) {
                int rx = owner[x], tx = target_route[x], px = pos[x];
                if (rx < 0 || tx < 0 || px <= 0) continue;
                for (int py = 1; py + 1 < (int)cur.routes[tx].size(); ++py) {
                    int y = cur.routes[tx][py];
                    if (y < 0 || y >= (int)CG.nodes.size() || CG.nodes[y].type != 2) continue;
                    if (target_route[y] != rx) continue;

                    vector<int> A = cur.routes[rx];
                    vector<int> B = cur.routes[tx];
                    if (px >= (int)A.size() - 1) continue;
                    A[px] = y;
                    B[py] = x;
                    normalize_route(A, depot);
                    normalize_route(B, depot);
                    enforce_trip_separators(A, CG, depot);
                    enforce_trip_separators(B, CG, depot);
                    if (!trips_feasible_for_route(A, CG, depot) || !trips_feasible_for_route(B, CG, depot)) continue;
                    if (cfg.use_time_window && (!route_hard_tw_feasible(A, ev, pm) || !route_hard_tw_feasible(B, ev, pm))) continue;

                    SolutionState cand = cur;
                    cand.routes[rx] = std::move(A);
                    cand.routes[tx] = std::move(B);
                    recompute_dirty_routes(cand, ev, {rx, tx});
                    if (!solution_hard_feasible(cand, CG, pm)) continue;
                    if (!found || cand.objective + 1e-9 < best_next_obj) {
                        found = true;
                        best_next_obj = cand.objective;
                        best_next = std::move(cand);
                        best_reduction = 2;
                    }
                }
            }
        }

        if (!found) break;
        cur = std::move(best_next);
        profile.path_relink_steps.fetch_add(1, memory_order_relaxed);
        profile.path_relink_feasible_progress.fetch_add(best_reduction, memory_order_relaxed);

        if (cur.objective + 1e-9 < best.objective) {
            best = cur;
            profile.path_relink_best_improvements.fetch_add(1, memory_order_relaxed);
        }
    }

    // Only polish the best hard-feasible state seen on the path, transactionally.
    SolutionState polished = best;
    for (auto &r : polished.routes) {
        if (solver_should_stop()) break;
        relocate_route_local_best(r, ev, pm, CG, depot);
        or_opt_k_route(r, 2, ev, pm, CG, depot);
        or_opt_k_route(r, 3, ev, pm, CG, depot);
        two_opt_multi_trip_route(r, ev, pm, CG, depot);
    }
    recompute_state_metrics_and_loads(polished, ev);
    if (solution_hard_feasible(polished, CG, pm) && polished.objective + 1e-9 < best.objective) {
        best = std::move(polished);
        profile.path_relink_best_improvements.fetch_add(1, memory_order_relaxed);
    }
    return best;
}


// -----------------------------------------------------------------------------
// Elite Evolution Lab 7: stronger route-label-invariant path relinking.
//
// Lab6 selected elites using adjacency diversity, but the legacy relinker mainly
// recombined route assignment.  Lab7 closes that mismatch:
//   1) exact maximum-overlap route alignment (Hungarian assignment),
//   2) assignment relinking that considers direct relocates and reciprocal swaps
//      in the same candidate set,
//   3) sequence relinking toward guide adjacencies after/alongside assignment,
//   4) transactional memetic education specialized for recombination boundaries.
// The production V61 path remains untouched; this is an opt-in laboratory path.
// -----------------------------------------------------------------------------

static vector<int> pr_max_overlap_alignment(
    const SolutionState &a,
    const SolutionState &b,
    const Compressed &CG,
    int R
) {
    if (R <= 0) return {};
    vector<vector<int>> aset(R), bset(R);
    vector<unordered_set<int>> ah(R), bh(R);
    for (int r = 0; r < R; ++r) {
        for (int x : a.routes[r]) if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) {
            aset[r].push_back(x); ah[r].insert(x);
        }
        for (int x : b.routes[r]) if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) {
            bset[r].push_back(x); bh[r].insert(x);
        }
    }

    // Rows are guide routes (b), columns are current route slots (a).
    // Large overlap dominates; size similarity only breaks otherwise-equal ties.
    vector<vector<long long>> w(R, vector<long long>(R, 0));
    for (int g = 0; g < R; ++g) {
        for (int slot = 0; slot < R; ++slot) {
            int ov = 0;
            if (bh[g].size() < ah[slot].size()) {
                for (int x : bh[g]) ov += ah[slot].count(x) ? 1 : 0;
            } else {
                for (int x : ah[slot]) ov += bh[g].count(x) ? 1 : 0;
            }
            const int size_gap = abs((int)bset[g].size() - (int)aset[slot].size());
            w[g][slot] = 1000000LL * ov - size_gap;
        }
    }

    // Hungarian algorithm for maximum-weight perfect assignment by minimizing -w.
    const long long INFLL = (1LL << 60);
    vector<long long> u(R + 1, 0), v(R + 1, 0);
    vector<int> p(R + 1, 0), way(R + 1, 0);
    for (int i = 1; i <= R; ++i) {
        p[0] = i;
        int j0 = 0;
        vector<long long> minv(R + 1, INFLL);
        vector<char> used(R + 1, false);
        do {
            used[j0] = true;
            const int i0 = p[j0];
            long long delta = INFLL;
            int j1 = 0;
            for (int j = 1; j <= R; ++j) if (!used[j]) {
                const long long cur = -w[i0 - 1][j - 1] - u[i0] - v[j];
                if (cur < minv[j]) { minv[j] = cur; way[j] = j0; }
                if (minv[j] < delta) { delta = minv[j]; j1 = j; }
            }
            for (int j = 0; j <= R; ++j) {
                if (used[j]) { u[p[j]] += delta; v[j] -= delta; }
                else minv[j] -= delta;
            }
            j0 = j1;
        } while (p[j0] != 0);
        do {
            const int j1 = way[j0];
            p[j0] = p[j1];
            j0 = j1;
        } while (j0 != 0);
    }

    vector<int> guide_to_slot(R, -1);
    for (int j = 1; j <= R; ++j) {
        if (p[j] > 0) guide_to_slot[p[j] - 1] = j - 1;
    }
    return guide_to_slot;
}

static double pr_assignment_distance_aligned(
    const SolutionState &a,
    const SolutionState &b,
    const Compressed &CG
) {
    const int R = min((int)a.routes.size(), (int)b.routes.size());
    if (R <= 0) return 0.0;
    const vector<int> map = pr_max_overlap_alignment(a, b, CG, R);
    vector<int> owner_a(CG.nodes.size(), -1);
    int total = 0, matched = 0;
    for (int r = 0; r < R; ++r) {
        for (int x : a.routes[r]) if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) owner_a[x] = r;
    }
    for (int g = 0; g < R; ++g) {
        const int slot = g < (int)map.size() ? map[g] : -1;
        for (int x : b.routes[g]) if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) {
            ++total;
            if (slot >= 0 && owner_a[x] == slot) ++matched;
        }
    }
    return total > 0 ? 1.0 - double(matched) / double(total) : 0.0;
}

static int pr_guide_edge_matches(
    const vector<int> &route,
    const vector<int> &guide_customers,
    const Compressed &CG,
    int depot
) {
    auto key = [](int x, int y) -> uint64_t {
        return (uint64_t(uint32_t(x)) << 32) | uint32_t(y);
    };
    unordered_set<uint64_t> guide;
    int prev = depot;
    for (int x : guide_customers) {
        guide.insert(key(prev, x));
        prev = x;
    }
    guide.insert(key(prev, depot));

    int score = 0;
    prev = depot;
    for (int x : route) {
        if (x < 0 || x >= (int)CG.nodes.size()) continue;
        if (CG.nodes[x].type == 2) {
            if (guide.count(key(prev, x))) ++score;
            prev = x;
        }
    }
    if (guide.count(key(prev, depot))) ++score;
    return score;
}

static SolutionState path_relink_between_strong(
    const SolutionState &a,
    const SolutionState &b,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    profile.path_relink_calls.fetch_add(1, memory_order_relaxed);
    const Compressed &CG = *ev.CG;
    const int depot = depot_of(ev);
    const int R = min((int)a.routes.size(), (int)b.routes.size());

    SolutionState cur = a;
    recompute_state_metrics_and_loads(cur, ev);
    if (R <= 0 || !solution_hard_feasible(cur, CG, pm)) return a;
    SolutionState best = cur;

    const vector<int> guide_to_slot = pr_max_overlap_alignment(a, b, CG, R);
    vector<int> target_route(CG.nodes.size(), -1);
    vector<vector<int>> guide_order(R);
    for (int g = 0; g < R; ++g) {
        const int slot = guide_to_slot[g];
        if (slot < 0 || slot >= R) continue;
        for (int x : b.routes[g]) {
            if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) {
                target_route[x] = slot;
                guide_order[slot].push_back(x);
            }
        }
    }

    const int customer_count = (int)customer_nodes_global.size();
    const int max_steps = max(1, min(customer_count * 2, 512));
    int assignment_steps = 0;

    for (int step = 0; step < max_steps; ++step) {
        if (solver_should_stop()) { profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed); break; }
        vector<int> owner(CG.nodes.size(), -1), pos(CG.nodes.size(), -1), mismatched;
        for (int r = 0; r < R; ++r) {
            for (int p0 = 1; p0 + 1 < (int)cur.routes[r].size(); ++p0) {
                const int x = cur.routes[r][p0];
                if (x < 0 || x >= (int)CG.nodes.size() || CG.nodes[x].type != 2) continue;
                owner[x] = r; pos[x] = p0;
                if (target_route[x] >= 0 && target_route[x] != r) mismatched.push_back(x);
            }
        }
        if (mismatched.empty()) break;

        // Put constrained target routes first, but do not hide the rest.
        stable_sort(mismatched.begin(), mismatched.end(), [&](int x, int y) {
            const int tx = target_route[x], ty = target_route[y];
            const double sx = (tx >= 0 && tx < (int)cur.route_max_trip_load.size())
                ? max(0.0, cfg.truck_capacity - cur.route_max_trip_load[tx]) : -INF_D;
            const double sy = (ty >= 0 && ty < (int)cur.route_max_trip_load.size())
                ? max(0.0, cfg.truck_capacity - cur.route_max_trip_load[ty]) : -INF_D;
            return sx < sy; // tight target first
        });
        if ((int)mismatched.size() > 128) mismatched.resize(128);

        bool found = false;
        SolutionState best_next;
        double best_next_obj = INF_D;
        int best_progress = 0;
        auto consider = [&](SolutionState &&cand, int progress) {
            // cand has already passed recompute_dirty_routes() for exactly the
            // modified route pair. That routine also rebuilds served_count and
            // the global objective, so a second full-state recompute here only
            // burns PR budget without adding correctness.
            if (!solution_hard_feasible(cand, CG, pm)) return;
            if (!found || cand.objective + 1e-9 < best_next_obj ||
                (fabs(cand.objective - best_next_obj) <= 1e-9 && progress > best_progress)) {
                found = true;
                best_next_obj = cand.objective;
                best_progress = progress;
                best_next = std::move(cand);
            }
        };

        // Direct guide-assignment relocates.
        for (int x : mismatched) {
            if (solver_should_stop()) break;
            const int rf = owner[x], rt = target_route[x], pf = pos[x];
            if (rf < 0 || rt < 0 || rf == rt || rt >= R || pf <= 0) continue;
            const int pos_cap = min((int)cur.routes[rt].size() - 1, 120);
            for (int pt = 1; pt <= pos_cap; ++pt) {
                if (solver_should_stop()) break;
                vector<int> from = cur.routes[rf], to = cur.routes[rt];
                if (pf >= (int)from.size() - 1) continue;
                from.erase(from.begin() + pf);
                to.insert(to.begin() + pt, x);
                normalize_route(from, depot); normalize_route(to, depot);
                enforce_trip_separators(from, CG, depot); enforce_trip_separators(to, CG, depot);
                if (!trips_feasible_for_route(from, CG, depot) || !trips_feasible_for_route(to, CG, depot)) continue;
                if (cfg.use_time_window && (!route_hard_tw_feasible(from, ev, pm) || !route_hard_tw_feasible(to, ev, pm))) continue;
                SolutionState cand = cur;
                cand.routes[rf] = std::move(from); cand.routes[rt] = std::move(to);
                recompute_dirty_routes(cand, ev, {rf, rt});
                consider(std::move(cand), 1);
            }
        }

        // Reciprocal swaps are evaluated even when direct moves exist.  The old
        // relinker only considered them as a feasibility fallback and therefore
        // missed many lower-cost two-customer guide steps.
        for (int x : mismatched) {
            if (solver_should_stop()) break;
            const int rx = owner[x], tx = target_route[x], px = pos[x];
            if (rx < 0 || tx < 0 || px <= 0 || tx >= R) continue;
            for (int py = 1; py + 1 < (int)cur.routes[tx].size(); ++py) {
                const int y = cur.routes[tx][py];
                if (y < 0 || y >= (int)CG.nodes.size() || CG.nodes[y].type != 2) continue;
                if (target_route[y] != rx) continue;
                vector<int> A = cur.routes[rx], B = cur.routes[tx];
                if (px >= (int)A.size() - 1) continue;
                A[px] = y; B[py] = x;
                normalize_route(A, depot); normalize_route(B, depot);
                enforce_trip_separators(A, CG, depot); enforce_trip_separators(B, CG, depot);
                if (!trips_feasible_for_route(A, CG, depot) || !trips_feasible_for_route(B, CG, depot)) continue;
                if (cfg.use_time_window && (!route_hard_tw_feasible(A, ev, pm) || !route_hard_tw_feasible(B, ev, pm))) continue;
                SolutionState cand = cur;
                cand.routes[rx] = std::move(A); cand.routes[tx] = std::move(B);
                recompute_dirty_routes(cand, ev, {rx, tx});
                consider(std::move(cand), 2);
            }
        }

        if (!found) break;
        cur = std::move(best_next);
        ++assignment_steps;
        profile.path_relink_steps.fetch_add(1, memory_order_relaxed);
        profile.path_relink_feasible_progress.fetch_add(best_progress, memory_order_relaxed);
        if (cur.objective + 1e-9 < best.objective) {
            best = cur;
            profile.path_relink_best_improvements.fetch_add(1, memory_order_relaxed);
        }
    }

    // Sequence relinking: the population is selected partly for adjacency
    // diversity, so explicitly recombine guide order too.  Multi-trip routes are
    // skipped for now because moving across depot separators changes trip identity.
    int sequence_steps = 0;
    if (!cfg.allow_multi_trip && !solver_should_stop()) {
        const int seq_cap = max(1, min(customer_count, 192));
        for (int step = 0; step < seq_cap && !solver_should_stop(); ++step) {
            bool found = false;
            SolutionState seq_best;
            int best_gain = 0;
            double best_obj = INF_D;

            for (int r = 0; r < R && !solver_should_stop(); ++r) {
                if (guide_order[r].size() < 2 || cur.routes[r].size() < 4) continue;
                const int old_score = pr_guide_edge_matches(cur.routes[r], guide_order[r], CG, depot);
                vector<int> guide_prev(CG.nodes.size(), -2), guide_next(CG.nodes.size(), -2);
                int gp = depot;
                for (int x : guide_order[r]) { guide_prev[x] = gp; gp = x; }
                int gn = depot;
                for (auto it = guide_order[r].rbegin(); it != guide_order[r].rend(); ++it) {
                    guide_next[*it] = gn; gn = *it;
                }

                vector<int> customers;
                for (int x : cur.routes[r]) if (x >= 0 && x < (int)CG.nodes.size() && CG.nodes[x].type == 2) customers.push_back(x);
                for (int x : customers) {
                    if (solver_should_stop()) break;
                    for (int mode = 0; mode < 2; ++mode) {
                        vector<int> nr = cur.routes[r];
                        auto ix = find(nr.begin(), nr.end(), x);
                        if (ix == nr.end()) continue;
                        nr.erase(ix);
                        int insert_pos = -1;
                        if (mode == 0) {
                            const int pred = guide_prev[x];
                            if (pred == -2) continue;
                            if (pred == depot) insert_pos = 1;
                            else {
                                auto ip = find(nr.begin(), nr.end(), pred);
                                if (ip == nr.end()) continue;
                                insert_pos = int(ip - nr.begin()) + 1;
                            }
                        } else {
                            const int succ = guide_next[x];
                            if (succ == -2) continue;
                            if (succ == depot) insert_pos = max(1, (int)nr.size() - 1);
                            else {
                                auto is = find(nr.begin(), nr.end(), succ);
                                if (is == nr.end()) continue;
                                insert_pos = int(is - nr.begin());
                            }
                        }
                        insert_pos = max(1, min(insert_pos, (int)nr.size() - 1));
                        nr.insert(nr.begin() + insert_pos, x);
                        normalize_route(nr, depot); enforce_trip_separators(nr, CG, depot);
                        if (!trips_feasible_for_route(nr, CG, depot)) continue;
                        if (cfg.use_time_window && !route_hard_tw_feasible(nr, ev, pm)) continue;
                        const int new_score = pr_guide_edge_matches(nr, guide_order[r], CG, depot);
                        const int gain = new_score - old_score;
                        if (gain <= 0) continue;
                        SolutionState cand = cur;
                        cand.routes[r] = std::move(nr);
                        recompute_dirty_routes(cand, ev, {r});
                        if (!solution_hard_feasible(cand, CG, pm)) continue;
                        if (!found || gain > best_gain ||
                            (gain == best_gain && cand.objective + 1e-9 < best_obj)) {
                            found = true; best_gain = gain; best_obj = cand.objective; seq_best = std::move(cand);
                        }
                    }
                }
            }

            if (!found) break;
            cur = std::move(seq_best);
            ++sequence_steps;
            profile.path_relink_steps.fetch_add(1, memory_order_relaxed);
            profile.path_relink_feasible_progress.fetch_add(best_gain, memory_order_relaxed);
            if (cur.objective + 1e-9 < best.objective) {
                best = cur;
                profile.path_relink_best_improvements.fetch_add(1, memory_order_relaxed);
            }
        }
    }

    // Cheap route-local education inside PR; deeper education is applied by the
    // memetic child pipeline outside this function.
    SolutionState polished = best;
    local_polish_solution(polished, ev, pm);
    recompute_state_metrics_and_loads(polished, ev);
    if (solution_hard_feasible(polished, CG, pm) && polished.objective + 1e-9 < best.objective) {
        best = std::move(polished);
        profile.path_relink_best_improvements.fetch_add(1, memory_order_relaxed);
    }
    safe_log_line("[StrongPR] assign_steps=", assignment_steps,
                  " sequence_steps=", sequence_steps,
                  " start=", a.objective, " guide=", b.objective,
                  " best=", best.objective,
                  " elapsed=", solver_elapsed_seconds());
    return best;
}

static SolutionState memetic_educate_child_strong(
    SolutionState child,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    double budget_s,
    unsigned child_seed
) {
    const Compressed &CG = *ev.CG;
    recompute_state_metrics_and_loads(child, ev);
    if (!solution_hard_feasible(child, CG, pm) || budget_s <= 1e-4) return child;
    SolutionState best = child;
    const auto t0 = Clock::now();
    const auto hard_end = t0 + chrono::duration_cast<Clock::duration>(chrono::duration<double>(budget_s));

    auto remaining = [&]() -> double {
        return max(0.0, chrono::duration<double>(hard_end - Clock::now()).count());
    };
    auto txn = [&](const char *name, double cap_s, auto &&fn) -> bool {
        const double rem = remaining();
        if (rem <= 1e-4 || solver_should_stop()) return false;
        SolutionState cand = best;
        {
            ScopedWorkerDeadline cap(min(rem, max(0.005, cap_s)));
            fn(cand);
        }
        recompute_state_metrics_and_loads(cand, ev);
        if (!solution_hard_feasible(cand, CG, pm)) return false;
        checkpoint_validated_global_best(cand, name);
        if (cand.objective + 1e-9 < best.objective) {
            const double before = best.objective;
            best = std::move(cand);
            safe_log_line("[StrongEducation] stage=", name,
                          " before=", before, " after=", best.objective,
                          " gain=", before - best.objective,
                          " remaining=", remaining());
            return true;
        }
        return false;
    };

    // Recombination tends to create poor route boundaries first, so educate in
    // that order: local sequencing -> boundary rebuild -> inter-route ownership
    // -> a small macro mutation -> granular tabu cleanup. Every stage is
    // transactional and the final granular phase receives all unused time.
    txn("elite_strong_local", 0.12 * budget_s, [&](SolutionState &c) {
        local_polish_solution(c, ev, pm);
    });
    txn("elite_strong_boundary", 0.18 * budget_s, [&](SolutionState &c) {
        boundary_pair_lns_descent(c, ev, pm);
    });
    txn("elite_strong_inter", 0.28 * budget_s, [&](SolutionState &c) {
        interroute_polish_solution(c, ev, pm);
    });
    if (cfg.use_route_region_lns && remaining() > 0.03) {
        txn("elite_strong_region", min(0.16 * budget_s, remaining()), [&](SolutionState &c) {
            route_region_lns_descent(c, ev, pm);
        });
    } else if (cfg.use_alns && remaining() > 0.03) {
        txn("elite_strong_alns", min(0.16 * budget_s, remaining()), [&](SolutionState &c) {
            adaptive_lns_polish(c, ev, pm, 1, child_seed ^ 0x51A7E11u);
        });
    }
    if (remaining() > 0.005) {
        txn("elite_strong_granular", remaining(), [&](SolutionState &c) {
            granular_tabu_repair(c, ev, pm);
        });
    }
    recompute_state_metrics_and_loads(best, ev);
    return best;
}


// Lab8 education: PR already performs route-local polish, while the micro-fill
// already carries macro LNS diversity.  Child education therefore concentrates
// compute on the three mechanisms that repeatedly earned accepted improvements
// in Lab7: boundary repair, inter-route ownership, and granular cleanup.  A
// second pass is conditional on the first pass actually changing the child.
static SolutionState memetic_educate_child_strong2(
    SolutionState child,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    double budget_s,
    unsigned child_seed
) {
    (void)child_seed;
    const Compressed &CG = *ev.CG;
    recompute_state_metrics_and_loads(child, ev);
    if (!solution_hard_feasible(child, CG, pm) || budget_s <= 1e-4) return child;
    SolutionState best = child;
    const auto hard_end = Clock::now() +
        chrono::duration_cast<Clock::duration>(chrono::duration<double>(budget_s));
    auto remaining = [&]() -> double {
        return max(0.0, chrono::duration<double>(hard_end - Clock::now()).count());
    };
    auto txn = [&](const char *name, double cap_s, auto &&fn) -> bool {
        const double rem = remaining();
        if (rem <= 1e-4 || solver_should_stop()) return false;
        SolutionState cand = best;
        {
            ScopedWorkerDeadline cap(min(rem, max(0.004, cap_s)));
            fn(cand);
        }
        recompute_state_metrics_and_loads(cand, ev);
        if (!solution_hard_feasible(cand, CG, pm)) return false;
        checkpoint_validated_global_best(cand, name);
        if (cand.objective + 1e-9 < best.objective) {
            const double before = best.objective;
            best = std::move(cand);
            safe_log_line("[StrongEducation2] stage=", name,
                          " before=", setprecision(15), before,
                          " after=", best.objective,
                          " gain=", before - best.objective,
                          " remaining=", remaining());
            return true;
        }
        return false;
    };

    bool changed = false;
    changed |= txn("elite_s2_boundary1", 0.22 * budget_s, [&](SolutionState &c) {
        boundary_pair_lns_descent(c, ev, pm);
    });
    changed |= txn("elite_s2_inter1", 0.28 * budget_s, [&](SolutionState &c) {
        interroute_polish_solution(c, ev, pm);
    });
    changed |= txn("elite_s2_gran1", 0.30 * budget_s, [&](SolutionState &c) {
        granular_tabu_repair(c, ev, pm);
    });

    // Recombination neighborhoods are complementary: a granular move can expose
    // a new cross-route boundary, and a boundary rebuild can expose another
    // granular descent. Spend the residual only when pass 1 proved productive.
    if (changed && remaining() > max(0.012, 0.08 * budget_s) && !solver_should_stop()) {
        txn("elite_s2_boundary2", min(0.08 * budget_s, remaining()), [&](SolutionState &c) {
            boundary_pair_lns_descent(c, ev, pm);
        });
        txn("elite_s2_inter2", min(0.10 * budget_s, remaining()), [&](SolutionState &c) {
            interroute_polish_solution(c, ev, pm);
        });
    }
    if (remaining() > 0.004 && !solver_should_stop()) {
        txn("elite_s2_gran_final", remaining(), [&](SolutionState &c) {
            granular_tabu_repair(c, ev, pm);
        });
    }
    recompute_state_metrics_and_loads(best, ev);
    return best;
}


// Balanced memetic education: preserve the three repeatedly productive stages
// but use a single pass. PR already performs route-local cleanup; micro-fill
// already supplies macro diversification. Boundary repair handles recombination
// seams, inter-route polish corrects ownership, and granular tabu consumes all
// remaining child budget. Every stage is transactional.
static SolutionState memetic_educate_child_balanced(
    SolutionState child,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    double budget_s,
    unsigned child_seed
) {
    (void)child_seed;
    const Compressed &CG = *ev.CG;
    recompute_state_metrics_and_loads(child, ev);
    if (!solution_hard_feasible(child, CG, pm) || budget_s <= 1e-4) return child;
    SolutionState best = child;
    const auto hard_end = Clock::now() +
        chrono::duration_cast<Clock::duration>(chrono::duration<double>(budget_s));
    auto remaining = [&]() -> double {
        return max(0.0, chrono::duration<double>(hard_end - Clock::now()).count());
    };
    auto txn = [&](const char *name, double cap_s, auto &&fn) -> bool {
        const double rem = remaining();
        if (rem <= 1e-4 || solver_should_stop()) return false;
        SolutionState cand = best;
        {
            ScopedWorkerDeadline cap(min(rem, max(0.004, cap_s)));
            fn(cand);
        }
        recompute_state_metrics_and_loads(cand, ev);
        if (!solution_hard_feasible(cand, CG, pm)) return false;
        checkpoint_validated_global_best(cand, name);
        if (cand.objective + 1e-9 < best.objective) {
            const double before = best.objective;
            best = std::move(cand);
            safe_log_line("[BalancedEducation] stage=", name,
                          " before=", setprecision(15), before,
                          " after=", best.objective,
                          " gain=", before - best.objective,
                          " remaining=", remaining());
            return true;
        }
        return false;
    };

    txn("elite_bal_boundary", 0.22 * budget_s, [&](SolutionState &c) {
        boundary_pair_lns_descent(c, ev, pm);
    });
    txn("elite_bal_inter", 0.28 * budget_s, [&](SolutionState &c) {
        interroute_polish_solution(c, ev, pm);
    });
    if (remaining() > 0.004 && !solver_should_stop()) {
        txn("elite_bal_granular", remaining(), [&](SolutionState &c) {
            granular_tabu_repair(c, ev, pm);
        });
    }
    recompute_state_metrics_and_loads(best, ev);
    return best;
}


/* ---------------- Safe assign helpers ---------------- */
static bool safe_assign_two_routes(SolutionState &state, int r1, vector<int> &candidate1, int r2, vector<int> &candidate2, ObjectiveEvaluator &ev) {
    int depot = find_depot_idx(*ev.CG);
    normalize_route(candidate1, depot);
    normalize_route(candidate2, depot);
    enforce_trip_separators(candidate1, *ev.CG, depot);
    enforce_trip_separators(candidate2, *ev.CG, depot);
    if (!cfg.allow_splitting && (route_has_duplicate_customers_strict(candidate1, *ev.CG) || route_has_duplicate_customers_strict(candidate2, *ev.CG))) return false;
    if (!trips_feasible_for_route(candidate1, *ev.CG, depot) || !trips_feasible_for_route(candidate2, *ev.CG, depot)) return false;
    state.routes[r1] = std::move(candidate1);
    state.routes[r2] = std::move(candidate2);
    if (r1 == r2) {
        recompute_dirty_routes(state, ev, {r1});
    } else {
        recompute_dirty_routes(state, ev, {r1, r2});
    }
    return true;
}

static bool safe_assign_one_route(SolutionState &state, int r, vector<int> &candidate, ObjectiveEvaluator &ev) {
    int depot = find_depot_idx(*ev.CG);
    normalize_route(candidate, depot);
    enforce_trip_separators(candidate, *ev.CG, depot);
    if (!cfg.allow_splitting && route_has_duplicate_customers_strict(candidate, *ev.CG)) return false;
    if (!trips_feasible_for_route(candidate, *ev.CG, depot)) return false;
    state.routes[r] = std::move(candidate);
    recompute_dirty_routes(state, ev, {r});
    return true;
}


/* ---------------- Clarke-Wright savings warm start ---------------- */
static inline double savings_pair_cost(int a, int b, PairwiseManager &pm) {
    if (a == b) return 0.0;

    if (cfg.objective_mode == "distance") {
        return fast_pair_dist(a, b, &pm);
    }
    if (cfg.objective_mode == "time") {
        return fast_pair_time(a, b, &pm);
    }

    double t = fast_pair_time(a, b, &pm);
    double d = fast_pair_dist(a, b, &pm);

    if (!isfinite(t)) t = INF_D;
    if (!isfinite(d)) d = INF_D;

    return d + cfg.w_time * t;
}

struct SavingsMergeMove {
    int i = -1;
    int j = -1;
    double score = 0.0;
};

struct SavingsRouteWork {
    vector<int> customers;
    double load = 0.0;
    bool active = true;
};

static vector<vector<int>> clarke_wright_savings_routes_once(
    Compressed &CG,
    int depot,
    const vector<int> &collections,
    int num_trucks,
    double capacity,
    PairwiseManager &pm,
    mt19937 &rng,
    double noise_strength,
    bool stop_at_fleet_ceiling = false
) {
    const int C = (int)collections.size();
    vector<vector<int>> fallback(num_trucks, vector<int>{depot, depot});
    if (C == 0 || num_trucks <= 0) return fallback;

    vector<SavingsRouteWork> works(C);
    unordered_map<int, int> owner;
    owner.reserve((size_t)C * 2 + 16);

    for (int idx = 0; idx < C; ++idx) {
        int c = collections[idx];
        works[idx].customers = {c};
        works[idx].load = (CG.nodes[c].type == 2) ? CG.nodes[c].garbage_amount : 0.0;
        works[idx].active = true;
        owner[c] = idx;
    }

    vector<SavingsMergeMove> moves;
    moves.reserve((size_t)C * (size_t)max(0, C - 1));

    uniform_real_distribution<double> noise(-noise_strength, noise_strength);

    for (int ia = 0; ia < C; ++ia) {
        int i = collections[ia];
        double dep_i = savings_pair_cost(depot, i, pm);
        if (!isfinite(dep_i) || dep_i >= INF_D / 2) continue;

        for (int jb = 0; jb < C; ++jb) {
            if (ia == jb) continue;
            int j = collections[jb];

            double j_dep = savings_pair_cost(j, depot, pm);
            double i_j = savings_pair_cost(i, j, pm);

            if (!isfinite(j_dep) || !isfinite(i_j) ||
                j_dep >= INF_D / 2 || i_j >= INF_D / 2) {
                continue;
            }

            double saving = dep_i + j_dep - i_j;
            double score = saving * (1.0 + noise(rng));
            moves.push_back({i, j, score});
        }
    }

    sort(moves.begin(), moves.end(), [](const SavingsMergeMove &a, const SavingsMergeMove &b) {
        if (fabs(a.score - b.score) > 1e-12) return a.score > b.score;
        if (a.i != b.i) return a.i < b.i;
        return a.j < b.j;
    });

    int active_count = C;

    auto try_merge = [&](int i, int j) -> bool {
        auto iti = owner.find(i);
        auto itj = owner.find(j);
        if (iti == owner.end() || itj == owner.end()) return false;

        int ri = iti->second;
        int rj = itj->second;
        if (ri == rj) return false;
        if (!works[ri].active || !works[rj].active) return false;
        if (works[ri].customers.empty() || works[rj].customers.empty()) return false;

        // Directed Clarke-Wright merge: route ending at i connects to route starting at j.
        if (works[ri].customers.back() != i) return false;
        if (works[rj].customers.front() != j) return false;

        if (cfg.capacity_mode == "strict" &&
            works[ri].load + works[rj].load > capacity + 1e-9 &&
            !cfg.allow_multi_trip) {
            return false;
        }

        works[ri].customers.insert(
            works[ri].customers.end(),
            works[rj].customers.begin(),
            works[rj].customers.end()
        );
        works[ri].load += works[rj].load;

        for (int c : works[rj].customers) owner[c] = ri;
        works[rj].active = false;
        works[rj].customers.clear();
        works[rj].load = 0.0;
        active_count--;
        return true;
    };

    // E21 dual construction semantics.  Production Savings treats num_trucks
    // as an availability ceiling and continues all beneficial merges.  The
    // optional truncated form deliberately stops at the ceiling and is used only
    // as a higher-entropy structural exploration seed.
    for (const auto &m : moves) {
        if (stop_at_fleet_ceiling) {
            if (active_count <= num_trucks) break;
        } else {
            if (m.score <= 1e-9) break;
        }
        try_merge(m.i, m.j);
    }

    // If capacity allowed more merges but the positive-saving list was exhausted,
    // continue with least-bad end-to-start merges until the fleet count is met.
    while (active_count > num_trucks) {
        double best_delta = INF_D;
        int best_a = -1;
        int best_b = -1;

        for (int a = 0; a < (int)works.size(); ++a) {
            if (!works[a].active || works[a].customers.empty()) continue;
            for (int b = 0; b < (int)works.size(); ++b) {
                if (a == b || !works[b].active || works[b].customers.empty()) continue;

                if (cfg.capacity_mode == "strict" &&
                    works[a].load + works[b].load > capacity + 1e-9 &&
                    !cfg.allow_multi_trip) {
                    continue;
                }

                int tail = works[a].customers.back();
                int head = works[b].customers.front();
                double delta = savings_pair_cost(tail, head, pm)
                            - savings_pair_cost(tail, depot, pm)
                            - savings_pair_cost(depot, head, pm);

                if (delta < best_delta) {
                    best_delta = delta;
                    best_a = a;
                    best_b = b;
                }
            }
        }

        if (best_a < 0 || best_b < 0) break;
        int tail = works[best_a].customers.back();
        int head = works[best_b].customers.front();
        if (!try_merge(tail, head)) break;
    }

    vector<vector<int>> built;
    built.reserve(works.size());

    for (const auto &w : works) {
        if (!w.active || w.customers.empty()) continue;
        vector<int> r;
        r.reserve(w.customers.size() + 2);
        r.push_back(depot);
        for (int c : w.customers) r.push_back(c);
        r.push_back(depot);
        normalize_route(r, depot);
        enforce_trip_separators(r, CG, depot);
        built.push_back(std::move(r));
    }

    sort(built.begin(), built.end(), [&](const vector<int> &a, const vector<int> &b) {
        double la = 0.0, lb = 0.0;
        for (int x : a) if (CG.nodes[x].type == 2) la += CG.nodes[x].garbage_amount;
        for (int x : b) if (CG.nodes[x].type == 2) lb += CG.nodes[x].garbage_amount;
        return la > lb;
    });

    vector<vector<int>> routes(num_trucks, vector<int>{depot, depot});

    int take = min(num_trucks, (int)built.size());
    for (int r = 0; r < take; ++r) routes[r] = std::move(built[r]);

    // If more active routes remain than trucks, append them to the currently lightest route.
    // This is rare when capacity/fleet are consistent, but prevents dropping customers.
    for (int idx = take; idx < (int)built.size(); ++idx) {
        int best_r = 0;
        double best_load = INF_D;
        for (int r = 0; r < num_trucks; ++r) {
            double load = 0.0;
            for (int x : routes[r]) if (CG.nodes[x].type == 2) load += CG.nodes[x].garbage_amount;
            if (load < best_load) {
                best_load = load;
                best_r = r;
            }
        }
        for (int x : built[idx]) {
            if (CG.nodes[x].type == 2) routes[best_r].insert(routes[best_r].end() - 1, x);
        }
        enforce_trip_separators(routes[best_r], CG, depot);
    }

    return routes;
}

static bool savings_light_relocate_pass(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    Clock::time_point deadline,
    int max_accepts
) {
    int accepted = 0;
    bool improved_any = false;
    const int accept_cap = max(1, max_accepts);
    while (accepted < accept_cap && Clock::now() < deadline) {
        int R = (int)state.routes.size();
        int depot = find_depot_idx(*ev.CG);
        bool found = false;
        for (int r_from = 0; r_from < R && !found; ++r_from) {
            for (int pos_from = 1; pos_from + 1 < (int)state.routes[r_from].size() && !found; ++pos_from) {
                if (Clock::now() >= deadline) break;
                int node = state.routes[r_from][pos_from];
                if (node < 0 || node >= (int)ev.CG->nodes.size() || ev.CG->nodes[node].type != 2) continue;
                double node_w = ev.CG->nodes[node].garbage_amount;
                for (int r_to = 0; r_to < R && !found; ++r_to) {
                    if (r_from == r_to) continue;
                    if (cfg.capacity_mode == "strict" && state.route_max_trip_load[r_to] + node_w > cfg.truck_capacity + 1e-9 && !cfg.allow_multi_trip) continue;
                    for (int pos_to = 1; pos_to < (int)state.routes[r_to].size(); ++pos_to) {
                        if (Clock::now() >= deadline) break;
                        vector<int> tmp_from = state.routes[r_from];
                        vector<int> tmp_to = state.routes[r_to];
                        tmp_from.erase(tmp_from.begin() + pos_from);
                        tmp_to.insert(tmp_to.begin() + pos_to, node);
                        enforce_trip_separators(tmp_from, *ev.CG, depot);
                        enforce_trip_separators(tmp_to, *ev.CG, depot);
                        if (!trips_feasible_for_route(tmp_from, *ev.CG, depot) || !trips_feasible_for_route(tmp_to, *ev.CG, depot)) continue;
                        if (!route_hard_tw_feasible(tmp_from, ev, pm) || !route_hard_tw_feasible(tmp_to, ev, pm)) continue;
                        RouteMetrics mf = ev.compute_route_metrics(tmp_from, 0.0);
                        RouteMetrics mt = ev.compute_route_metrics(tmp_to, 0.0);
                        double old_cost = state.route_metrics[r_from].weighted_cost + state.route_metrics[r_to].weighted_cost;
                        double new_cost = mf.weighted_cost + mt.weighted_cost;
                        if (new_cost + 1e-9 < old_cost) {
                            state.routes[r_from] = std::move(tmp_from);
                            state.routes[r_to] = std::move(tmp_to);
                            recompute_dirty_routes(state, ev, {r_from, r_to});
                            ++accepted;
                            improved_any = true;
                            found = true;
                            break;
                        }
                    }
                }
            }
        }
        if (!found) break;
    }
    return improved_any;
}

static bool build_savings_warm_start_solution(
    SolutionState &out,
    Compressed &CG,
    int depot,
    const vector<int> &collections,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    unsigned seed
) {
    // E12: caller owns the policy decision.  The phase engine may request a
    // cheap Savings candidate even when the archived legacy flag is false.
    if (collections.empty()) return false;

    auto t0 = Clock::now();
    double budget = max(0.0, cfg.savings_polish_time_s);
    Clock::time_point deadline = t0 + chrono::duration_cast<Clock::duration>(chrono::duration<double>(budget));

    SolutionState best(cfg.num_trucks, (int)CG.nodes.size());
    best.objective = INF_D;

    int variants = max(1, cfg.savings_variants);
    for (int v = 0; v < variants; ++v) {
        mt19937 rng(seed + 1000003u * (unsigned)(v + 1));
        double noise = (v == 0) ? 0.0 : cfg.savings_noise;

        SolutionState cand(cfg.num_trucks, (int)CG.nodes.size());
        cand.routes = clarke_wright_savings_routes_once(
            CG,
            depot,
            collections,
            cfg.num_trucks,
            cfg.truck_capacity,
            pm,
            rng,
            noise,
            false
        );
        recompute_state_metrics_and_loads(cand, ev);

        if (solution_hard_feasible(cand, CG, pm) &&
            cand.objective + 1e-9 < best.objective) {
            best = std::move(cand);
        }
    }

    if (best.routes.empty() || best.objective >= INF_D / 2) return false;

    // Tiny exact relocate education, time-capped. No global/local/interroute polish calls here.
    int rounds = max(0, cfg.savings_light_polish_rounds);
    for (int round = 0; round < rounds && Clock::now() < deadline; ++round) {
        bool changed = savings_light_relocate_pass(best, ev, pm, deadline, cfg.savings_relocate_accepts_per_round);
        if (!changed) break;
    }

    recompute_state_metrics_and_loads(best, ev);
    if (!solution_hard_feasible(best, CG, pm)) return false;

    out = std::move(best);

    int active_routes = 0;
    for (const auto &route : out.routes) {
        bool used = false;
        for (int node : route) {
            if (node >= 0 && node < (int)CG.nodes.size() && CG.nodes[node].type == 2) {
                used = true;
                break;
            }
        }
        if (used) active_routes++;
    }
    double elapsed = chrono::duration<double>(Clock::now() - t0).count();
    // Structured, always-on operational receipt. K is a ceiling, not a target.
    // This gives FleetRoute/IAAI evidence an explicit used-vs-available fleet fact
    // even when verbose search diagnostics are disabled.
    safe_log_line(
        "[SavingsWarmStart] obj=", out.objective,
        " active_trucks=", active_routes,
        " max_available_trucks=", cfg.num_trucks,
        " variants=", variants,
        " polish_budget_s=", budget,
        " elapsed_s=", elapsed
    );

    if (cfg.savings_verbose) {
        safe_log_line("[SavingsWarmStartDetail] objective=", out.objective,
            " active_trucks=", active_routes, " variants=", variants);
    }

    return true;
}

// E21 structural constructor: reproduce the useful fleet-ceiling-truncated
// Clarke-Wright geometry as an exploration seed, without confusing it with the
// incumbent.  It is independently hard-feasibility validated.
static bool build_truncated_savings_exploration_seed(
    SolutionState &out, Compressed &CG, int depot,
    const vector<int> &collections, ObjectiveEvaluator &ev,
    PairwiseManager &pm, unsigned seed
) {
    if (collections.empty()) return false;
    SolutionState best(cfg.num_trucks, (int)CG.nodes.size());
    best.objective = INF_D;
    const int variants = max(1, cfg.savings_variants);
    for (int v = 0; v < variants; ++v) {
        mt19937 rng(seed + 1000003u * (unsigned)(v + 1));
        const double noise = (v == 0) ? 0.0 : cfg.savings_noise;
        SolutionState cand(cfg.num_trucks, (int)CG.nodes.size());
        cand.routes = clarke_wright_savings_routes_once(
            CG, depot, collections, cfg.num_trucks, cfg.truck_capacity,
            pm, rng, noise, true);
        recompute_state_metrics_and_loads(cand, ev);
        if (solution_hard_feasible(cand, CG, pm) &&
            cand.objective + 1e-9 < best.objective)
            best = std::move(cand);
    }
    if (best.routes.empty() || best.objective >= INF_D/2) return false;
    // Keep this seed coarse; one bounded relocation pass removes obvious defects
    // without collapsing the route ownership structure into the quality seed.
    const double polish_s = min(0.35, max(0.0, cfg.savings_polish_time_s * 0.12));
    const auto deadline = Clock::now() + chrono::duration_cast<Clock::duration>(
        chrono::duration<double>(polish_s));
    if (polish_s > 0.0)
        savings_light_relocate_pass(best, ev, pm, deadline, 2);
    recompute_state_metrics_and_loads(best, ev);
    if (!solution_hard_feasible(best, CG, pm)) return false;
    out = std::move(best);
    return true;
}

/* ---------------- Greedy + two-opt + relocate ---------------- */
vector<vector<int>> greedy_initial_routes(Compressed &CG, int depot, const vector<int> &collections_in, int num_trucks, double capacity, PairwiseManager &pm) {
    vector<vector<int>> routes(num_trucks, vector<int>{depot});
    vector<double> loads(num_trucks, 0.0);
    vector<int> remaining = collections_in;
    vector<double> local_dem(CG.nodes.size(), 0.0);
    for (size_t i = 0; i < CG.nodes.size(); ++i) local_dem[i] = CG.nodes[i].garbage_amount;

    bool progress = true;
    int safety_counter = 0;
    while (!remaining.empty() && progress) {
        progress = false;
        if (++safety_counter > 200000) break;

        for (int t = 0; t < num_trucks && !remaining.empty(); ++t) {
            int cur = routes[t].back();
            double bestd = INF_D;
            int besti = -1;
            for (int i = 0; i < (int)remaining.size(); ++i) {
                int node = remaining[i];
                double d = fast_pair_search_cost(cur, node, &pm);
                if (d < bestd) {
                    bestd = d;
                    besti = i;
                }
            }
            if (besti == -1) continue;
            int node = remaining[besti];
            double gw = local_dem[node];

            if (loads[t] + gw > capacity + 1e-9) {
                if (loads[t] > 1e-9) {
                    if (routes[t].empty() || routes[t].back() != depot) routes[t].push_back(depot);
                    loads[t] = 0.0;
                    progress = true;
                    continue;
                }
            }

            if (loads[t] + gw > capacity + 1e-9) {
                if (cfg.allow_splitting) {
                    double can = capacity - loads[t];
                    if (can > 1e-9) {
                        local_dem[node] -= can;
                        loads[t] += can;
                        routes[t].push_back(node);
                        progress = true;
                        if (local_dem[node] <= 1e-6) remaining.erase(remaining.begin() + besti);
                    } else {
                        rotate(remaining.begin() + besti, remaining.begin() + besti + 1, remaining.end());
                        progress = true;
                    }
                } else {
                    rotate(remaining.begin() + besti, remaining.begin() + besti + 1, remaining.end());
                    progress = true;
                }
            } else {
                routes[t].push_back(node);
                loads[t] += gw;
                remaining.erase(remaining.begin() + besti);
                progress = true;
            }
        }
    }

    if (!remaining.empty()) {
        int idx = 0;
        for (int node : remaining) {
            if (routes[idx].empty() || routes[idx].back() != depot) routes[idx].push_back(depot);
            routes[idx].push_back(node);
            if (routes[idx].empty() || routes[idx].back() != depot) routes[idx].push_back(depot);
            idx = (idx + 1) % num_trucks;
        }
        remaining.clear();
    }

    for (int t = 0; t < num_trucks; ++t) {
        if (routes[t].empty() || routes[t].back() != depot) routes[t].push_back(depot);
        normalize_route(routes[t], depot);
        enforce_trip_separators(routes[t], CG, depot);
    }

    unordered_set<int> seen;
    for (auto &r : routes) for (int v : r) if (CG.nodes[v].type == 2) seen.insert(v);
    for (auto &n : CG.nodes) if (n.type == 2 && !seen.count(n.id)) {
        if (routes.empty()) routes.emplace_back(vector<int>{depot, n.id, depot});
        else {
            auto &r = routes[0];
            r.insert(r.end() - 1, n.id);
            normalize_route(r, depot);
            enforce_trip_separators(r, CG, depot);
        }
    }

    return routes;
}

// E19: compact-fill greedy retained as a construction candidate for road/single-trip
// search.  The newer round-robin greedy is still preserved as a diversity/probe seed.
// This version treats the fleet size as a ceiling and fills one route before opening
// another, which is the useful geometry used by the strong V31 construction lineage.
static vector<vector<int>> phase_compact_fill_greedy_routes(
    Compressed &CG, int depot, const vector<int> &collections_in,
    int num_trucks, double capacity, PairwiseManager &pm
) {
    vector<vector<int>> routes(num_trucks, vector<int>{depot});
    vector<double> loads(num_trucks, 0.0);
    vector<int> remaining = collections_in;
    vector<double> local_dem(CG.nodes.size(), 0.0);
    for (size_t i = 0; i < CG.nodes.size(); ++i) local_dem[i] = CG.nodes[i].garbage_amount;

    int truck = 0;
    int safety_counter = 0;
    while (!remaining.empty() && truck < num_trucks) {
        if (++safety_counter > 500000) break;
        int cur = routes[truck].back();
        double bestd = INF_D;
        int besti = -1;
        for (int i = 0; i < (int)remaining.size(); ++i) {
            int node = remaining[i];
            double demand = local_dem[node];
            if (!cfg.allow_splitting && loads[truck] + demand > capacity + 1e-9) continue;
            const double d = fast_pair_search_cost(cur, node, &pm);
            if (d < bestd) { bestd = d; besti = i; }
        }
        if (besti < 0) {
            if (routes[truck].back() != depot) routes[truck].push_back(depot);
            if (cfg.allow_multi_trip && !remaining.empty()) {
                loads[truck] = 0.0;
                continue;
            }
            ++truck;
            continue;
        }

        int node = remaining[besti];
        double demand = local_dem[node];
        if (loads[truck] + demand <= capacity + 1e-9) {
            routes[truck].push_back(node);
            loads[truck] += demand;
            remaining.erase(remaining.begin() + besti);
        } else if (cfg.allow_splitting) {
            double can = max(0.0, capacity - loads[truck]);
            if (can > 1e-9) {
                routes[truck].push_back(node);
                local_dem[node] -= can;
                loads[truck] += can;
                if (local_dem[node] <= 1e-6) remaining.erase(remaining.begin() + besti);
            } else {
                if (routes[truck].back() != depot) routes[truck].push_back(depot);
                loads[truck] = 0.0;
            }
        } else {
            if (routes[truck].back() != depot) routes[truck].push_back(depot);
            ++truck;
        }
    }

    if (!remaining.empty()) return {};
    for (auto &r : routes) {
        if (r.empty() || r.back() != depot) r.push_back(depot);
        normalize_route(r, depot);
        enforce_trip_separators(r, CG, depot);
    }
    return routes;
}

void two_opt_route(
    vector<int> &route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const int n = (int)route.size();
    if (n <= 3 || !cfg.use_2opt) return;
    const auto audit_t0 = Clock::now();
    profile.two_opt_route_calls.fetch_add(1, memory_order_relaxed);

    const Compressed &CG = *ev.CG;
    const int depot = find_depot_idx(CG);
    normalize_route(route, depot);
    enforce_trip_separators(route, CG, depot);

    double current_exact = route_exact_cost(route, ev);
    bool improved = true;
    int accepted_moves = 0;
    // Directed 2-opt can expose many valid reversals that the old symmetric
    // gate never considered.  Treat this as bounded education rather than an
    // unbounded pre-search descent: scale the cap with route length and retain
    // the existing insertion_pos_cap as the global safety ceiling.
    const int move_cap = min(max(1, cfg.insertion_pos_cap), max(4, 2 * max(1, n - 2)));

    while (improved && accepted_moves < move_cap) {
        if (solver_should_stop()) {
            profile.cooperative_stop_polls.fetch_add(1, memory_order_relaxed);
            return;
        }
        improved = false;

        // V21 closes the remaining directed-2opt hole.  V20 corrected the
        // multi-trip implementation, but this single-trip function still used
        // the symmetric two-boundary shortcut.  Reversing [i,k] on a directed
        // road metric also reverses every internal arc, so include that exact
        // distance contribution in O(1) via a prefix sum.
        vector<double> rev_prefix(route.size(), 0.0);
        if (!metric_is_symmetric()) {
            for (int e = 1; e + 1 < (int)route.size(); ++e) {
                const int x = route[e];
                const int y = route[e + 1];
                const double xy = fast_pair_search_cost(x, y, &pm);
                const double yx = fast_pair_search_cost(y, x, &pm);
                if (!isfinite(xy) || !isfinite(yx)) {
                    rev_prefix[e + 1] = INF_D;
                } else if (rev_prefix[e] >= INF_D / 2) {
                    rev_prefix[e + 1] = INF_D;
                } else {
                    rev_prefix[e + 1] = rev_prefix[e] + (yx - xy);
                }
            }
        }

        for (int i = 1; i < n - 2 && !improved; ++i) {
            for (int k = i + 1; k < n - 1; ++k) {
                const int a = route[i - 1];
                const int b = route[i];
                const int c = route[k];
                const int d = route[k + 1];

                const double before =
                    fast_pair_search_cost(a, b, &pm) +
                    fast_pair_search_cost(c, d, &pm);
                const double after =
                    fast_pair_search_cost(a, c, &pm) +
                    fast_pair_search_cost(b, d, &pm);
                if (!isfinite(before) || !isfinite(after)) continue;

                double edge_delta = after - before;
                if (!metric_is_symmetric()) {
                    profile.asymmetric_2opt_candidates.fetch_add(1, memory_order_relaxed);
                    const double hi = rev_prefix[k];
                    const double lo = rev_prefix[i];
                    if (!isfinite(hi) || !isfinite(lo) || hi >= INF_D / 2 || lo >= INF_D / 2) continue;
                    edge_delta += (hi - lo);
                }

                // Exact for route-distance contribution.  Full configured
                // objective and hard feasibility are checked after construction.
                if (!(edge_delta < -1e-9)) continue;

                vector<int> cand = route;
                reverse(cand.begin() + i, cand.begin() + k + 1);
                normalize_route(cand, depot);
                enforce_trip_separators(cand, CG, depot);
                if (!trips_feasible_for_route(cand, CG, depot)) continue;
                if (cfg.use_time_window && !route_hard_tw_feasible(cand, ev, pm)) continue;

                const double candidate_exact = route_exact_cost(cand, ev);
                if (candidate_exact + 1e-9 < current_exact) {
                    route.swap(cand);
                    current_exact = candidate_exact;
                    improved = true;
                    ++accepted_moves;
                    if (!metric_is_symmetric()) {
                        profile.asymmetric_2opt_improvements.fetch_add(1, memory_order_relaxed);
                    }
                    break;
                }
            }
        }
    }
    profile.two_opt_route_time_us.fetch_add(
        chrono::duration_cast<chrono::microseconds>(Clock::now() - audit_t0).count(),
        memory_order_relaxed
    );
}

void two_opt_all(
    vector<vector<int>> &routes,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    for (auto &r : routes) two_opt_route(r, ev, pm);
}

void relocate_improvement_pass(SolutionState &state, ObjectiveEvaluator &ev, PairwiseManager &pm) {
    (void)pm;
    int R = (int)state.routes.size();
    bool improved = true;
    int iter = 0;
    while (improved && iter < 2) {
        improved = false;
        iter++;
        for (int r_from = 0; r_from < R; ++r_from) {
            for (int pos_from = 1; pos_from + 1 < (int)state.routes[r_from].size(); ++pos_from) {
                int node = state.routes[r_from][pos_from];
                double node_w = (ev.CG->nodes[node].type == 2) ? ev.CG->nodes[node].garbage_amount : 0.0;
                for (int r_to = 0; r_to < R; ++r_to) {
                    if (r_from == r_to) continue;
                    for (int pos_to = 1; pos_to < (int)state.routes[r_to].size(); ++pos_to) {
                        if (state.route_load[r_to] + node_w > cfg.truck_capacity + 1e-9 && cfg.capacity_mode == "strict") continue;
                        if (!cfg.allow_splitting) {
                            bool found = false;
                            for (int x : state.routes[r_to]) if (ev.CG->nodes[x].type == 2 && x == node) { found = true; break; }
                            if (found) continue;
                        }
                        vector<int> tmp_from = state.routes[r_from];
                        vector<int> tmp_to = state.routes[r_to];
                        tmp_from.erase(tmp_from.begin() + pos_from);
                        tmp_to.insert(tmp_to.begin() + pos_to, node);
                        enforce_trip_separators(tmp_from, *ev.CG, find_depot_idx(*ev.CG));
                        enforce_trip_separators(tmp_to, *ev.CG, find_depot_idx(*ev.CG));
                        if (!trips_feasible_for_route(tmp_from, *ev.CG, find_depot_idx(*ev.CG))) continue;
                        if (!trips_feasible_for_route(tmp_to, *ev.CG, find_depot_idx(*ev.CG))) continue;
                        RouteMetrics new_from = ev.compute_route_metrics(tmp_from, 0.0);
                        RouteMetrics new_to = ev.compute_route_metrics(tmp_to, 0.0);
                        double delta = (new_from.weighted_cost + new_to.weighted_cost) - (state.route_metrics[r_from].weighted_cost + state.route_metrics[r_to].weighted_cost);
                        if (delta < -1e-9) {
                            state.routes[r_from].erase(state.routes[r_from].begin() + pos_from);
                            if (r_from == r_to && pos_to > pos_from) pos_to--;
                            state.routes[r_to].insert(state.routes[r_to].begin() + pos_to, node);
                            state.route_load[r_from] -= node_w;
                            state.route_load[r_to] += node_w;
                            state.route_metrics[r_from] = new_from;
                            state.route_metrics[r_to] = new_to;
                            state.objective += delta;
                            enforce_trip_separators(state.routes[r_from], *ev.CG, find_depot_idx(*ev.CG));
                            enforce_trip_separators(state.routes[r_to], *ev.CG, find_depot_idx(*ev.CG));
                            improved = true;
                            goto next_relocate;
                        }
                    }
                }
            }
        }
    next_relocate:;
    }
}

/* ---------------- Exact delta helpers ---------------- */
static double compute_weighted_swap_delta(const SolutionState &state, ObjectiveEvaluator &ev, int r1, int i, int r2, int j) {
    if (r1 == r2) {
        vector<int> r = state.routes[r1];
        if ((size_t)i >= r.size() || (size_t)j >= r.size()) return 0.0;
        if (abs(i - j) <= 1) return 0.0;
        swap(r[i], r[j]);
        double load = 0.0;
        for (int nid : r) if (ev.CG->nodes[nid].type == 2) load += ev.CG->nodes[nid].garbage_amount;
        RouteMetrics m = ev.compute_route_metrics(r, load);
        return m.weighted_cost - state.route_metrics[r1].weighted_cost;
    }

    vector<int> r1_new = state.routes[r1];
    vector<int> r2_new = state.routes[r2];
    if ((size_t)i >= r1_new.size() || (size_t)j >= r2_new.size()) return 0.0;

    int a = r1_new[i], b = r2_new[j];
    r1_new[i] = b;
    r2_new[j] = a;

    double load1 = 0.0, load2 = 0.0;
    for (int nid : r1_new) if (ev.CG->nodes[nid].type == 2) load1 += ev.CG->nodes[nid].garbage_amount;
    for (int nid : r2_new) if (ev.CG->nodes[nid].type == 2) load2 += ev.CG->nodes[nid].garbage_amount;

    RouteMetrics m1 = ev.compute_route_metrics(r1_new, load1);
    RouteMetrics m2 = ev.compute_route_metrics(r2_new, load2);
    double old_sum = state.route_metrics[r1].weighted_cost + state.route_metrics[r2].weighted_cost;
    double new_sum = m1.weighted_cost + m2.weighted_cost;
    return new_sum - old_sum;
}

static double compute_weighted_relocate_delta(const SolutionState &state, ObjectiveEvaluator &ev, int r_from, int pos_from, int r_to, int pos_to) {
    if ((size_t)pos_from >= state.routes[r_from].size() || (size_t)pos_to > state.routes[r_to].size()) return 0.0;

    if (r_from == r_to) {
        vector<int> r = state.routes[r_from];
        if (pos_from <= 0 || pos_from + 1 >= (int)r.size()) return 0.0;
        int node = r[pos_from];
        r.erase(r.begin() + pos_from);
        if (pos_to > pos_from) pos_to--;
        r.insert(r.begin() + pos_to, node);

        double load = 0.0;
        for (int nid : r) if (ev.CG->nodes[nid].type == 2) load += ev.CG->nodes[nid].garbage_amount;
        RouteMetrics m = ev.compute_route_metrics(r, load);
        return m.weighted_cost - state.route_metrics[r_from].weighted_cost;
    }

    vector<int> rfrom_new = state.routes[r_from];
    vector<int> rto_new = state.routes[r_to];
    int node = rfrom_new[pos_from];
    rfrom_new.erase(rfrom_new.begin() + pos_from);
    if (r_from == r_to && pos_to > pos_from) pos_to--;
    rto_new.insert(rto_new.begin() + pos_to, node);

    double load_from = 0.0, load_to = 0.0;
    for (int nid : rfrom_new) if (ev.CG->nodes[nid].type == 2) load_from += ev.CG->nodes[nid].garbage_amount;
    for (int nid : rto_new) if (ev.CG->nodes[nid].type == 2) load_to += ev.CG->nodes[nid].garbage_amount;
    RouteMetrics m_from = ev.compute_route_metrics(rfrom_new, load_from);
    RouteMetrics m_to = ev.compute_route_metrics(rto_new, load_to);
    double old_sum = state.route_metrics[r_from].weighted_cost + state.route_metrics[r_to].weighted_cost;
    double new_sum = m_from.weighted_cost + m_to.weighted_cost;
    return new_sum - old_sum;
}

static double compute_weighted_cross_delta(const SolutionState &state, ObjectiveEvaluator &ev, int r1, int i1, int r2, int i2) {
    if (r1 == r2) return 0.0;
    if ((size_t)i1 >= state.routes[r1].size() || (size_t)i2 >= state.routes[r2].size()) return 0.0;

    vector<int> tail1(state.routes[r1].begin() + i1, state.routes[r1].end());
    vector<int> tail2(state.routes[r2].begin() + i2, state.routes[r2].end());
    vector<int> new1(state.routes[r1].begin(), state.routes[r1].begin() + i1);
    vector<int> new2(state.routes[r2].begin(), state.routes[r2].begin() + i2);
    new1.insert(new1.end(), tail2.begin(), tail2.end());
    new2.insert(new2.end(), tail1.begin(), tail1.end());

    double load1 = 0.0, load2 = 0.0;
    for (int nid : new1) if (ev.CG->nodes[nid].type == 2) load1 += ev.CG->nodes[nid].garbage_amount;
    for (int nid : new2) if (ev.CG->nodes[nid].type == 2) load2 += ev.CG->nodes[nid].garbage_amount;

    RouteMetrics m1 = ev.compute_route_metrics(new1, load1);
    RouteMetrics m2 = ev.compute_route_metrics(new2, load2);
    double old_sum = state.route_metrics[r1].weighted_cost + state.route_metrics[r2].weighted_cost;
    double new_sum = m1.weighted_cost + m2.weighted_cost;
    return new_sum - old_sum;
}

/* ---------------- SA worker ---------------- */
struct ConvergenceLogRow {
    double time_s = 0.0;
    unsigned seed = 0;
    long long iter = 0;
    double current_obj = 0.0;
    double best_obj = 0.0;
    double temp = 0.0;
    long long accepted_moves = 0;
    long long attempted_moves = 0;
    long long stagnation = 0;
    string event = "periodic";
};

static void append_convergence_row(
    vector<ConvergenceLogRow> *log,
    mutex *log_mutex,
    const ConvergenceLogRow &row
) {
    if (!cfg.log_convergence || log == nullptr || log_mutex == nullptr) return;
    lock_guard<mutex> lk(*log_mutex);
    if (cfg.convergence_max_rows > 0 &&
        (long long)log->size() >= cfg.convergence_max_rows) return;
    log->push_back(row);
}

struct AlgoResult {
    SolutionState best_state;
    // Optional persistent exploration state.  Production callers that do not
    // understand it simply ignore it; the E2 phase scheduler uses it to keep a
    // macro-LNS lane in a nearby but structurally distinct basin.
    SolutionState alternate_state;
    bool has_alternate_state = false;
    // E2 archive handoff: phase-specialized search can pass its competitive
    // basin population into the final elite tail instead of rebuilding from
    // one incumbent.
    vector<SolutionState> elite_states;
    double runtime_sec = 0.0;
    double iterations = 0.0;
    long long accepted_moves = 0;
    long long attempted_moves = 0;
    long long drift_corrections = 0;
    long long capacity_violations = 0;
    double total_overload = 0.0;
    // E11: age of the most recent hard-feasible improvement when this worker
    // returned.  The scheduler uses this as a readiness signal: a cheap lane
    // that is still improving should not be pre-empted by heavy intensification.
    double last_improvement_age_s = INF_D;
    vector<pair<double, double>> convergence;
};

static uint64_t solution_route_hash(const SolutionState &s) {
    uint64_t h = 1469598103934665603ULL;
    auto mix = [&](uint64_t x) {
        h ^= x;
        h *= 1099511628211ULL;
    };
    mix((uint64_t)s.routes.size());
    for (size_t r = 0; r < s.routes.size(); ++r) {
        mix(0x9e3779b97f4a7c15ULL ^ (uint64_t)r);
        mix((uint64_t)s.routes[r].size());
        for (int node : s.routes[r]) {
            mix((uint64_t)(uint32_t)node + 0x100000001b3ULL);
        }
    }
    return h;
}

static void reset_repair_benchmark_counters() {
    repair_profile.calls.store(0, memory_order_relaxed);
    repair_profile.successful_calls.store(0, memory_order_relaxed);
    repair_profile.failed_calls.store(0, memory_order_relaxed);
    repair_profile.customers_requested.store(0, memory_order_relaxed);
    repair_profile.customers_inserted.store(0, memory_order_relaxed);
    repair_profile.candidate_routes_examined.store(0, memory_order_relaxed);
    repair_profile.positions_ranked.store(0, memory_order_relaxed);
    repair_profile.exact_route_evaluations.store(0, memory_order_relaxed);
    repair_profile.repair_time_us.store(0, memory_order_relaxed);
    repair_profile.improving_lns_moves.store(0, memory_order_relaxed);
    repair_profile.benchmark_iterations.store(0, memory_order_relaxed);
    repair_profile.benchmark_noop_iterations.store(0, memory_order_relaxed);
    repair_profile.benchmark_time_us.store(0, memory_order_relaxed);

    lock_guard<mutex> lk(repair_trace_mutex);
    repair_trace_rows.clear();
}

static AlgoResult run_lns_repair_benchmark(
    const SolutionState &seed_state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    double time_limit_s,
    unsigned seed,
    vector<ConvergenceLogRow> *shared_conv_log = nullptr,
    mutex *conv_mtx = nullptr
) {
    AlgoResult out;
    const auto t0 = Clock::now();
    const auto alns_t0 = Clock::now();

    mt19937 rng(seed);
    SolutionState best = seed_state;
    recompute_state_metrics_and_loads(best, ev);

    repair_benchmark_seed_objective = best.objective;
    repair_benchmark_effective_seed = seed;
    repair_benchmark_requested_time_s = max(0.0, time_limit_s);
    repair_benchmark_time_overshoot_s = 0.0;

    long long iterations = 0;
    long long accepted = 0;
    double next_sample_s = 0.0;

    append_convergence_row(shared_conv_log, conv_mtx, {
        0.0, seed, 0, best.objective, best.objective, 0.0,
        0, 0, 0, "search_start"
    });

    while (!solver_should_stop()) {
        const double elapsed = chrono::duration<double>(Clock::now() - t0).count();

        if (cfg.lns_benchmark_iterations > 0) {
            if (iterations >= cfg.lns_benchmark_iterations) break;
        }
        else if (time_limit_s > 0.0 && elapsed >= time_limit_s) {
            break;
        }

        // Controlled operator isolation is used by E2 to measure destroy
        // productivity directly.  -1 preserves a round-robin schedule.
        const int destroy_mode = cfg.lns_benchmark_destroy_mode >= 0
            ? cfg.lns_benchmark_destroy_mode
            : (int)(iterations % (cfg.phase_e2_destroy_policy ? 6 : 3));
        const long long calls_before =
            repair_profile.calls.load(memory_order_relaxed);

        SolutionState cand = alns_destroy_repair(
            best, ev, pm, rng, destroy_mode
        );

        if (repair_profile.calls.load(memory_order_relaxed) == calls_before) {
            repair_profile.benchmark_noop_iterations.fetch_add(
                1, memory_order_relaxed
            );
        }
        recompute_state_metrics_and_loads(cand, ev);

        bool improved = false;
        if (cand.objective + 1e-9 < best.objective &&
            solution_hard_feasible(cand, *ev.CG, pm)) {
            best = std::move(cand);
            accepted++;
            improved = true;
            repair_profile.improving_lns_moves.fetch_add(
                1, memory_order_relaxed
            );
            update_global_best_checked(best, *ev.CG, pm);
        }

        iterations++;
        repair_profile.benchmark_iterations.fetch_add(
            1, memory_order_relaxed
        );

        const double trace_t = chrono::duration<double>(Clock::now() - t0).count();
        if (improved) {
            append_convergence_row(shared_conv_log, conv_mtx, {
                trace_t, seed, iterations, best.objective, best.objective, 0.0,
                accepted, iterations, iterations - accepted, "improvement"
            });
        }
        if (trace_t + 1e-12 >= next_sample_s) {
            append_convergence_row(shared_conv_log, conv_mtx, {
                trace_t, seed, iterations, best.objective, best.objective, 0.0,
                accepted, iterations, iterations - accepted, "periodic"
            });
            next_sample_s = trace_t + cfg.convergence_sample_period_s;
        }
    }

    out.best_state = best;
    out.runtime_sec = chrono::duration<double>(Clock::now() - t0).count();
    if (cfg.lns_benchmark_iterations == 0 && time_limit_s > 0.0) {
        repair_benchmark_time_overshoot_s =
            max(0.0, out.runtime_sec - time_limit_s);
    }

    repair_profile.benchmark_time_us.store(
        (long long)llround(out.runtime_sec * 1'000'000.0),
        memory_order_relaxed
    );
    out.iterations = (double)iterations;
    out.accepted_moves = accepted;
    out.attempted_moves = iterations;

    profile.alns_calls.fetch_add(iterations, memory_order_relaxed);
    profile.alns_time_us.fetch_add(
        chrono::duration_cast<chrono::microseconds>(
            Clock::now() - alns_t0
        ).count(),
        memory_order_relaxed
    );

    append_convergence_row(shared_conv_log, conv_mtx, {
        out.runtime_sec, seed, iterations, best.objective, best.objective, 0.0,
        accepted, iterations, iterations - accepted, "search_final"
    });

    return out;
}

// V41 high-throughput strictly-feasible LNS portfolio worker. It deliberately
// uses the cheap greedy repair and omits post-repair polishing. It competes for
// one existing worker slot; it does not add cores or wall time.
static AlgoResult run_parallel_fast_worker_v41(
    const SolutionState &seed_state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    double time_limit_s,
    unsigned seed,
    vector<ConvergenceLogRow> *shared_conv_log = nullptr,
    mutex *conv_mtx = nullptr
) {
    AlgoResult out;
    const auto t0 = Clock::now();
    ScopedWorkerDeadline deadline_scope(time_limit_s);
    mt19937 rng(seed);
    SolutionState best = seed_state;
    recompute_state_metrics_and_loads(best, ev);
    long long iterations = 0, accepted = 0;

    const bool old_override = tls_repair_mode_override_enabled;
    const RepairMode old_mode = tls_repair_mode_override;
    const bool old_no_polish = tls_disable_post_repair_polish;
    tls_repair_mode_override_enabled = true;
    tls_repair_mode_override = RepairMode::GREEDY_FAST;
    tls_disable_post_repair_polish = true;

    while (!solver_should_stop()) {
        const double elapsed = chrono::duration<double>(Clock::now() - t0).count();
        if (time_limit_s > 0.0 && elapsed >= time_limit_s) break;
        const int destroy_mode = (int)(iterations % 3);
        SolutionState cand = alns_destroy_repair(best, ev, pm, rng, destroy_mode);
        recompute_state_metrics_and_loads(cand, ev);
        if (cand.objective + 1e-9 < best.objective &&
            solution_hard_feasible(cand, *ev.CG, pm)) {
            best = std::move(cand);
            ++accepted;
            update_global_best_checked(best, *ev.CG, pm);
            append_convergence_row(shared_conv_log, conv_mtx, {
                solver_elapsed_seconds(), seed, iterations, best.objective,
                best.objective, 0.0, accepted, iterations + 1,
                iterations + 1 - accepted, "parallel_fast_improvement_v41"
            });
        }
        ++iterations;
    }

    tls_repair_mode_override_enabled = old_override;
    tls_repair_mode_override = old_mode;
    tls_disable_post_repair_polish = old_no_polish;

    out.best_state = std::move(best);
    out.runtime_sec = chrono::duration<double>(Clock::now() - t0).count();
    out.iterations = iterations;
    out.accepted_moves = accepted;
    out.attempted_moves = iterations;
    return out;
}

double clamp_ratio(double ratio) {
    if (ratio < -50.0) return -50.0;
    if (ratio > 50.0) return 50.0;
    return ratio;
}

static void print_routes(const SolutionState &s) {
    for (int i = 0; i < (int)s.routes.size(); i++) {
        cout << "Truck " << i << ": ";
        for (int n : s.routes[i]) cout << n << " ";
        cout << "\n";
    }
}

AlgoResult sa_worker(Compressed &CG, PairwiseManager &pm, ObjectiveEvaluator &ev, int depot, const vector<int> &collections, unsigned seed, double time_limit, bool allow_cross2, const SolutionState *shared_start_state = nullptr, vector<ConvergenceLogRow> *shared_conv_log = nullptr, mutex *conv_mtx = nullptr, int explicit_worker_slot = -1, int phase_temperature_profile = -1) {
    AlgoResult out;
    auto tstart = Clock::now();
    ScopedWorkerDeadline worker_deadline_scope(time_limit);
    const double worker_search_budget = (time_limit > 0.0)
        ? time_limit * (1.0 - max(0.0, min(0.80, cfg.sa_refinement_reserve_fraction)))
        : time_limit;

    // Worker seeds are already deterministic functions of base_seed. Collapsing
    // all workers to base_seed under --deterministic destroyed portfolio diversity.
    unsigned rng_seed = seed;
    mt19937 rng(rng_seed);

    SolutionState state(cfg.num_trucks, (int)CG.nodes.size());

    bool used_shared_start = false;
    bool used_cluster_warm_start = false;

    // Paper-benchmark fairness and production efficiency:
    // every deep-search worker starts from the exact incumbent already built
    // by the outer pipeline (normally the Savings warm start).  Previously the
    // worker silently rebuilt a plain greedy solution and discarded Savings.
    if (shared_start_state != nullptr) {
        state = *shared_start_state;
        recompute_state_metrics_and_loads(state, ev);

        if (solution_hard_feasible(state, CG, pm)) {
            used_shared_start = true;
            safe_log_line("[SA-start] source=shared_incumbent objective=", state.objective, " seed=", seed);
        }
        else {
            safe_log_line("[SA-start] shared incumbent invalid; rebuilding fallback seed=", seed);
            state = SolutionState(cfg.num_trucks, (int)CG.nodes.size());
        }
    }

    if (!used_shared_start) {
        used_cluster_warm_start = build_cluster_warm_start_solution(
            state,
            collections,
            ev,
            pm
        );

        if (!used_cluster_warm_start) {
            auto routes = greedy_initial_routes(
                CG,
                depot,
                collections,
                cfg.num_trucks,
                cfg.truck_capacity,
                pm
            );

            if (cfg.use_2opt) {
                if (cfg.allow_multi_trip) {
                    for (auto &r : routes) {
                        two_opt_multi_trip_route(r, ev, pm, CG, depot);
                    }
                }
                else {
                    two_opt_all(routes, ev, pm);
                }
            }
            state.routes = routes;
        }
        else {
            if (cfg.use_2opt) {
                if (cfg.allow_multi_trip) {
                    for (auto &r : state.routes) {
                        two_opt_multi_trip_route(r, ev, pm, CG, depot);
                    }
                }
                else {
                    two_opt_all(state.routes, ev, pm);
                }
            }
            for (auto &r : state.routes) {
                normalize_route(r, depot);
                enforce_trip_separators(r, CG, depot);
            }
        }
    }

    int R = (int)state.routes.size();

    state.route_load.assign(R, 0.0);
    state.route_max_trip_load.assign(R, 0.0);
    state.route_metrics.assign(R, RouteMetrics());
    state.served_count.assign(CG.nodes.size(), 0);

    recompute_state_metrics_and_loads(state, ev);
    state.objective = ev.compute_objective_from_metrics(state.route_metrics);

    if (used_cluster_warm_start) {
        cerr << "[clusters] SA start after cleanup objective="
            << state.objective << "\n";
    }

    // V3 audit fix: keep the penalized search incumbent separate from the
    // best hard-feasible incumbent. Soft TW states may guide exploration,
    // but they must never shadow a later feasible improvement.
    SolutionState best = state;              // penalized/search incumbent
    SolutionState feasible_best = state;     // dispatchable incumbent
    bool feasible_best_valid = solution_hard_feasible(feasible_best, *ev.CG, pm);
    double last_feasible_best_improvement_local_s = 0.0;

    struct FeasibleUpdate { bool local_best=false; bool global_best=false; };
    auto consider_feasible = [&](const SolutionState &cand, const char *event) -> FeasibleUpdate {
        FeasibleUpdate u;
        SolutionState checked = cand;
        recompute_state_metrics_and_loads(checked, ev);
        if (!solution_hard_feasible(checked, *ev.CG, pm)) return u;
        if (!feasible_best_valid || checked.objective + 1e-9 < feasible_best.objective) {
            feasible_best = std::move(checked);
            feasible_best_valid = true;
            last_feasible_best_improvement_local_s = chrono::duration<double>(Clock::now() - tstart).count();
            u.local_best = true;
            u.global_best = update_global_best_checked(feasible_best, *ev.CG, pm);
            append_convergence_row(shared_conv_log, conv_mtx, {
                solver_elapsed_seconds(), seed, 0, feasible_best.objective,
                feasible_best.objective, 0.0, 0, 0, 0, event
            });
        }
        return u;
    };

    // V3.5: run the fleet-elimination attack only in the designated base-seed
    // worker, after the worker's normal start cleanup has been applied. This
    // captures the strong fleet-basin effect without multiplying the expensive
    // regret repair across all six workers.
    // V33: worker role is an explicit property, not a side effect of a seed
    // matching base_seed + i*10007. Filler/final workers use different seed
    // formulas and were previously misclassified.
    unsigned early_worker_slot = explicit_worker_slot >= 0 ? (unsigned)explicit_worker_slot :
        ((seed >= cfg.base_seed && ((seed - cfg.base_seed) % 10007u == 0u))
            ? (seed - cfg.base_seed) / 10007u : 0u);
    const bool fleet_specialist_worker = cfg.use_fleet_descent && early_worker_slot < 2u;
    if (fleet_specialist_worker && feasible_best_valid && !solver_should_stop()) {
        // V6: a fleet-first objective deserves a true descent, not a single
        // K->K-1 attempt. Re-run the transactional elimination operator from
        // each newly compressed feasible state. The two specialist workers use
        // different depth caps to preserve portfolio diversity.
        const int max_fleet_descent_steps = (early_worker_slot == 0u) ? 3 : 2;
        SolutionState squeezed = feasible_best;
        int fleet_steps = 0;
        while (fleet_steps < max_fleet_descent_steps && !solver_should_stop()) {
            SolutionState next = squeezed;
            const unsigned step_seed = seed ^ (0x9E3779B9u * (unsigned)(fleet_steps + 1));
            if (!fleet_elimination_lns(next, ev, pm, step_seed, (int)state.routes.size())) break;
            squeezed = std::move(next);
            ++fleet_steps;
        }
        if (fleet_steps > 0) {
            state = squeezed;
            best = squeezed;
            feasible_best = squeezed;
            feasible_best_valid = true;
            last_feasible_best_improvement_local_s = chrono::duration<double>(Clock::now() - tstart).count();
            safe_log_line("[FleetDescent] seed=", seed, " steps=", fleet_steps,
                          " objective=", feasible_best.objective);
        }
    }

    // Elite relinking is an exploitation mechanism: keep only hard-feasible
    // elites so a soft TW state cannot poison the elite archive.
    vector<SolutionState> elite_pool;
    if (feasible_best_valid) elite_pool_update(elite_pool, feasible_best, 8);

    double T = cfg.sa_T0;
    if (cfg.auto_T0) {
        // V18: calibrate temperature on the *actual penalized move objective*.
        // The legacy calibration sampled only a distance-like swap approximation,
        // while Metropolis decisions use weighted deltas that can include active
        // time-window penalties.  On Solomon/Homberger this scale mismatch made
        // the chain effectively frozen even at t ~= 0.
        mt19937 rng_sample(seed ^ 0x9e3779b9u);
        const int target_samples = 192;
        const int attempt_cap = 16 * target_samples;
        vector<int> active;
        active.reserve(R);
        for (int r = 0; r < R; ++r) {
            if (state.routes[r].size() >= 3) active.push_back(r);
        }

        vector<double> uphill;
        uphill.reserve(target_samples);
        vector<double> abs_all;
        abs_all.reserve(target_samples);
        int attempts = 0;
        int rejected = 0;
        while ((int)abs_all.size() < target_samples && attempts++ < attempt_cap && !active.empty()) {
            const int r1 = active[rng_sample() % active.size()];
            const int r2 = active[rng_sample() % active.size()];
            if (state.routes[r1].size() < 3 || state.routes[r2].size() < 3) continue;
            const int i = 1 + (int)(rng_sample() % (state.routes[r1].size() - 2));
            const int j = 1 + (int)(rng_sample() % (state.routes[r2].size() - 2));
            if (r1 == r2 && (i == j || abs(i - j) <= 1)) continue;

            const double d = compute_weighted_swap_delta(state, ev, r1, i, r2, j);
            if (!isfinite(d) || fabs(d) >= INF_D * 1e-6) { ++rejected; continue; }
            if (fabs(d) <= 1e-9) continue;
            abs_all.push_back(fabs(d));
            if (d > 1e-9) uphill.push_back(d);
        }

        const auto robust_median = [](vector<double> v, double fallback) {
            if (v.empty()) return fallback;
            sort(v.begin(), v.end());
            return v[(v.size() - 1) / 2];
        };
        const double scale_all = robust_median(abs_all, max(1e-3, cfg.sa_T0));
        const double uphill_med = robust_median(uphill, scale_all);
        // Choose T0 so a median uphill penalized move has 25% Metropolis
        // acceptance before feasibility guards.  This is scale calibration, not
        // instance-specific tuning.
        constexpr double initial_uphill_accept = 0.25;
        T = uphill_med / (-log(initial_uphill_accept));
        T = min(1e7, max(1e-3, T));

        safe_log_line("[AutoT0-V18] seed=", seed,
                      " active_routes=", active.size(),
                      " valid=", abs_all.size(),
                      " uphill=", uphill.size(),
                      " attempts=", attempts,
                      " rejected=", rejected,
                      " abs_median=", scale_all,
                      " uphill_median=", uphill_med,
                      " T0=", T);
    }

    auto active_fleet_count = [&](const SolutionState &ss) {
        int k = 0;
        for (const auto &r : ss.routes) if (route_customer_count_hard(r, *ev.CG) > 0) ++k;
        return k;
    };
    const unsigned worker_stride = 10007u;
    const unsigned worker_index = explicit_worker_slot >= 0 ? (unsigned)explicit_worker_slot :
        ((seed >= cfg.base_seed && ((seed - cfg.base_seed) % worker_stride == 0))
            ? (seed - cfg.base_seed) / worker_stride : 0u);
    const int total_workers = max(1, cfg.sa_instances);
    // Portfolio roles: workers 0-1 are structural fleet specialists and never
    // get overwritten by migration; the last N workers remain independent
    // explorers; only the middle workers are dominance-following exploiters.
    const bool migration_enabled_for_worker = !tls_defer_global_publish && cfg.use_global_fleet_migration &&
        worker_index >= 2u &&
        ((int)worker_index < max(2, total_workers - cfg.global_fleet_migration_preserve_explorers));
    const bool independent_explorer =
        ((int)worker_index >= max(2, total_workers - cfg.global_fleet_migration_preserve_explorers));
    const bool structural_worker = worker_index < 2u;
    if (structural_worker) profile.worker_role_structural.fetch_add(1, memory_order_relaxed);
    else if (independent_explorer) profile.worker_role_explorer.fetch_add(1, memory_order_relaxed);
    else profile.worker_role_exploiter.fetch_add(1, memory_order_relaxed);
    const bool alns_kick_specialist = cfg.use_time_stagnation_alns_kick &&
        worker_index >= 2u && worker_index < (unsigned)(2 + max(0, cfg.alns_kick_specialist_workers));
    long long alns_kick_sequence = 0;

    // V19: a heterogeneous portfolio should not force every worker to maintain
    // the same high acceptance ratio.  Structural workers already have explicit
    // K->K-1 machinery, dominance followers should exploit a migrated low-fleet
    // incumbent, and only preserved explorers should remain deliberately hot.
    // E1 can explicitly request a temperature personality without changing
    // the worker's neighborhood capabilities. Profiles:
    //   0 = cold exploiter, 1 = intentional quench, 2 = explorer.
    double role_temperature_scale = independent_explorer ? 1.0 :
        (structural_worker ? 0.30 : 0.10);
    if (phase_temperature_profile == 0) role_temperature_scale = 0.08;
    else if (phase_temperature_profile == 1) role_temperature_scale = 0.55;
    else if (phase_temperature_profile == 2) role_temperature_scale = 0.90;
    T *= role_temperature_scale;
    const double worker_initial_temperature = max(1e-6, T);
    safe_log_line("[TemperatureRole-E2] seed=", seed,
                  " worker_index=", worker_index,
                  " explicit_slot=", explicit_worker_slot,
                  " role=", (independent_explorer ? "explorer" :
                              (structural_worker ? "structural" : "exploiter")),
                  " phase_profile=", phase_temperature_profile,
                  " scale=", role_temperature_scale,
                  " T0_role=", worker_initial_temperature);

    uniform_real_distribution<double> unif(0.0, 1.0);
    long long iterations = 0, accepted = 0, attempted = 0, effective_proposals = 0, route_draw_failures = 0, drift_corrections = 0;
    long long cap_viol = 0;
    double total_overload = 0.0;
    int stagnation = 0;
    // V18: temperature is governed by elapsed budget and observed acceptance,
    // not multiplied once per proposal.  Proposal throughput can vary by orders
    // of magnitude across instances/versions, so proposal-count cooling is not a
    // stable fixed-time annealing schedule.
    const int adapt_window = 2048, recompute_period = 8000;
    int window_attempts = 0, window_accepted = 0;
    double thermostat_log_bias = 0.0;
    // V19 targets are role- and time-dependent.  Exploration is front-loaded;
    // the target acceptance decays toward exploitation as the worker consumes
    // its assigned wall-clock interval.
    double target_accept_start = independent_explorer ? 0.18 :
        (structural_worker ? 0.07 : 0.04);
    double target_accept_end = independent_explorer ? 0.035 : 0.008;
    double end_temperature_ratio = 0.02;
    if (phase_temperature_profile == 0) {
        target_accept_start = 0.030; target_accept_end = 0.004;
        end_temperature_ratio = 0.008;
    } else if (phase_temperature_profile == 1) {
        target_accept_start = 0.120; target_accept_end = 0.004;
        end_temperature_ratio = 0.002;
    } else if (phase_temperature_profile == 2) {
        target_accept_start = 0.160; target_accept_end = 0.025;
        end_temperature_ratio = 0.025;
    }
    constexpr double thermostat_gain = 1.60;
    constexpr double thermostat_bias_cap = 4.0;
    string sa_stop_reason = "local_time";
    double next_trace_sample_s = solver_elapsed_seconds();
    // V20 fixed-budget semantics: expensive meta-events are scheduled in wall
    // time, not raw iterations. V15+ changed proposal utilization by >6x, so
    // legacy iteration periods silently changed the amount of path relinking,
    // elite validation and ALNS per second.
    double next_migration_local_s = max(0.01, cfg.global_fleet_migration_period_s);
    double next_elite_local_s = max(0.01, cfg.elite_update_period_s);
    double next_relink_local_s = max(0.05, cfg.relink_period_s);
    double next_alns_local_s = 0.0;
    double next_string_slack_local_s = max(0.05, cfg.string_slack_kick_period_s);

    // V15: route-aware SA sampling. The legacy loop sampled route IDs uniformly
    // from all configured trucks, even when most routes were empty. With 20-23
    // active routes out of 50, the majority of iterations could become no-op
    // proposals. Draw from currently eligible routes instead. Rejection sampling
    // keeps the hot path cheap; the fallback scan guarantees a valid draw when
    // one exists. Singleton routes (depot-customer-depot, size 3) are eligible
    // for swap/relocate so ordinary SA can participate in K -> K-1 transitions.
    auto draw_route_min_size = [&](size_t min_size) -> int {
        for (int k = 0; k < 8; ++k) {
            int r = (int)(rng() % (unsigned)R);
            if (state.routes[r].size() >= min_size) return r;
        }
        vector<int> eligible;
        eligible.reserve(R);
        for (int r = 0; r < R; ++r) if (state.routes[r].size() >= min_size) eligible.push_back(r);
        if (eligible.empty()) { ++route_draw_failures; return -1; }
        return eligible[rng() % eligible.size()];
    };

    append_convergence_row(shared_conv_log, conv_mtx, {
        solver_elapsed_seconds(), seed, 0, state.objective, best.objective, T,
        0, 0, 0, "worker_start"
    });

    // V21: fixed-time runs must stop on time, not on a hidden iteration cap.
    // V19/V20 could hit exactly 2,000,001 loops/worker after the hot loop was
    // optimized, silently turning a time-budget experiment into a work-budget
    // experiment and forcing repeated filler-round startup costs.
    while (true) {
        const double local_elapsed = chrono::duration<double>(Clock::now() - tstart).count();
        if (worker_search_budget > 0.0 && local_elapsed >= worker_search_budget) {
            sa_stop_reason = "local_time";
            profile.sa_stop_local_time.fetch_add(1, memory_order_relaxed);
            break;
        }
        if (solver_should_stop()) {
            // If the thread-local deadline fired between clock samples, classify
            // it as local rather than incorrectly reporting a global deadline.
            if (tls_local_deadline_enabled && Clock::now() >= tls_local_deadline &&
                !(cfg.hard_time_limit_s > 0.0 && solver_deadline_passed())) {
                sa_stop_reason = "local_time";
                profile.sa_stop_local_time.fetch_add(1, memory_order_relaxed);
            } else {
                sa_stop_reason = "global_deadline";
                profile.sa_stop_global_deadline.fetch_add(1, memory_order_relaxed);
            }
            if (feasible_best_valid) update_global_best_checked(feasible_best, *ev.CG, pm);
            break;
        }
        if (cfg.sa_max_effective_proposals > 0 &&
            effective_proposals >= cfg.sa_max_effective_proposals) {
            sa_stop_reason = "proposal_cap";
            profile.sa_stop_proposal_cap.fetch_add(1, memory_order_relaxed);
            break;
        }

        iterations++;
        attempted++;
        bool proposal_made = false;

        if (iterations % recompute_period == 0) recompute_state_metrics_and_loads(state, ev);

        const double worker_elapsed_now = chrono::duration<double>(Clock::now() - tstart).count();
        if (migration_enabled_for_worker && cfg.solomon_vehicle_penalty > 0.0 &&
            cfg.global_fleet_migration_period_s > 0.0 &&
            worker_elapsed_now + 1e-12 >= next_migration_local_s && !solver_should_stop()) {
            next_migration_local_s = worker_elapsed_now + max(0.01, cfg.global_fleet_migration_period_s);
            profile.global_fleet_migration_checks.fetch_add(1, memory_order_relaxed);
            SolutionState migrant;
            bool have_migrant = false;
            {
                lock_guard<mutex> lock(global_best_mutex);
                if (!global_best_state.routes.empty()) { migrant = global_best_state; have_migrant = true; }
            }
            if (have_migrant) {
                const int km = active_fleet_count(migrant);
                const int kl = feasible_best_valid ? active_fleet_count(feasible_best) : INT_MAX;
                const double stagnated_for = worker_elapsed_now - last_feasible_best_improvement_local_s;
                const bool lower_fleet = km < kl;
                const bool same_fleet_better = cfg.use_same_fleet_migration && feasible_best_valid &&
                    km == kl && stagnated_for + 1e-12 >= cfg.same_fleet_migration_stagnation_s &&
                    migrant.objective + cfg.same_fleet_migration_min_gain < feasible_best.objective;
                if (lower_fleet || same_fleet_better) {
                    recompute_state_metrics_and_loads(migrant, ev);
                    state = migrant;
                    best = migrant;
                    feasible_best = migrant;
                    feasible_best_valid = true;
                    last_feasible_best_improvement_local_s = chrono::duration<double>(Clock::now() - tstart).count();
                    stagnation = 0;
                    T = max(T, worker_initial_temperature * cfg.global_fleet_migration_reheat);
                    elite_pool_update(elite_pool, feasible_best, 8);
                    profile.global_fleet_migration_adoptions.fetch_add(1, memory_order_relaxed);
                    append_convergence_row(shared_conv_log, conv_mtx, {
                        solver_elapsed_seconds(), seed, iterations, state.objective, feasible_best.objective, T,
                        accepted, attempted, 0, lower_fleet ? "global_fleet_migration" : "same_fleet_migration_v41"
                    });
                    safe_log_line("[FleetMigration-V41] time_s=",solver_elapsed_seconds(),
                                  " seed=",seed," from_K=",kl," to_K=",km,
                                  " kind=",(lower_fleet ? "fleet" : "geometry"),
                                  " objective=",state.objective);
                }
            }
        }

        double swap_prob = 0.48, rel_prob = 0.47;
        if (stagnation > 500) {
            swap_prob = 0.40;
            rel_prob = 0.45;
        }
        if (stagnation > 1500) {
            swap_prob = 0.35;
            rel_prob = 0.40;
        }

        double rsel = unif(rng);
        bool accepted_move = false;

        // SWAP
        if (rsel < swap_prob) {
            int r1 = draw_route_min_size(3), r2 = draw_route_min_size(3);
            if (r1 >= 0 && r2 >= 0) {
                int i = 1 + rng() % (state.routes[r1].size() - 2);
                int j = 1 + rng() % (state.routes[r2].size() - 2);
                if (!(r1 == r2 && (i == j || abs(i - j) <= 1))) {
                    ++effective_proposals;
                    proposal_made = true;
                    double approx = ev.delta_swap_approx(state, r1, i, r2, j);
                    double ratio = clamp_ratio(-approx / max(T, 1e-9));
                    double prob = exp(ratio);
                    if (approx < 0 || prob > unif(rng)) {
                        double weighted_delta = compute_weighted_swap_delta(state, ev, r1, i, r2, j);
                        double accept_prob = exp(clamp_ratio(-weighted_delta / max(T, 1e-9)));
                        if (weighted_delta < 0 || accept_prob > unif(rng)) {
                            if (r1 == r2) {
                                vector<int> candidate = state.routes[r1];
                                if ((size_t)i < candidate.size() && (size_t)j < candidate.size()) {
                                    swap(candidate[i], candidate[j]);
                                    enforce_trip_separators(candidate, CG, depot);
                                    double overload = compute_route_overload_max(candidate, CG, depot);
                                    if (overload > 0.0) {
                                        cap_viol++;
                                        total_overload += overload;
                                    } else {
                                        if (safe_assign_one_route(state, r1, candidate, ev)) accepted_move = true;
                                        else cap_viol++;
                                    }
                                }
                            } else {
                                if ((size_t)i < state.routes[r1].size() && (size_t)j < state.routes[r2].size()) {
                                    vector<int> new_r1 = state.routes[r1];
                                    vector<int> new_r2 = state.routes[r2];
                                    int a = new_r1[i], b = new_r2[j];
                                    new_r1[i] = b;
                                    new_r2[j] = a;
                                    enforce_trip_separators(new_r1, CG, depot);
                                    enforce_trip_separators(new_r2, CG, depot);
                                    double o1 = compute_route_overload_max(new_r1, CG, depot);
                                    double o2 = compute_route_overload_max(new_r2, CG, depot);
                                    if (o1 > 0.0 || o2 > 0.0) {
                                        cap_viol++;
                                        total_overload += (max(0.0, o1) + max(0.0, o2));
                                    } else {
                                        if (safe_assign_two_routes(state, r1, new_r1, r2, new_r2, ev)) accepted_move = true;
                                        else cap_viol++;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        // RELOCATE
        else if (rsel < swap_prob + rel_prob) {
            int from = draw_route_min_size(3), to = draw_route_min_size(3);
            if (from >= 0 && to >= 0) {
                int pos_from = 1 + rng() % (state.routes[from].size() - 2);
                int pos_to = 1 + rng() % (state.routes[to].size() - 1);
                if (!(from == to && (pos_to == pos_from || pos_to == pos_from + 1))) {
                    ++effective_proposals;
                    proposal_made = true;
                    double approx = ev.delta_relocate_approx(state, from, pos_from, to, pos_to);
                    double ratio = clamp_ratio(-approx / max(T, 1e-9));
                    double prob = exp(ratio);
                    if (approx < 0 || prob > unif(rng)) {
                        double weighted_delta = compute_weighted_relocate_delta(state, ev, from, pos_from, to, pos_to);
                        double accept_prob = exp(clamp_ratio(-weighted_delta / max(T, 1e-9)));
                        if (weighted_delta < 0 || accept_prob > unif(rng)) {
                            if (from == to) {
                                vector<int> cand = state.routes[from];
                                int node = cand[pos_from];
                                cand.erase(cand.begin() + pos_from);
                                if (pos_to > pos_from) pos_to--;
                                cand.insert(cand.begin() + pos_to, node);
                                enforce_trip_separators(cand, CG, depot);
                                double o = compute_route_overload_max(cand, CG, depot);
                                if (o > 0.0) {
                                    cap_viol++;
                                    total_overload += o;
                                } else {
                                    if (safe_assign_one_route(state, from, cand, ev)) accepted_move = true;
                                    else cap_viol++;
                                }
                            } else {
                                vector<int> new_from = state.routes[from];
                                vector<int> new_to = state.routes[to];
                                int node = new_from[pos_from];
                                new_from.erase(new_from.begin() + pos_from);
                                new_to.insert(new_to.begin() + pos_to, node);
                                enforce_trip_separators(new_from, CG, depot);
                                enforce_trip_separators(new_to, CG, depot);
                                double o_from = compute_route_overload_max(new_from, CG, depot);
                                double o_to = compute_route_overload_max(new_to, CG, depot);
                                if (o_from > 0.0 || o_to > 0.0) {
                                    cap_viol++;
                                    total_overload += (max(0.0, o_from) + max(0.0, o_to));
                                } else {
                                    if (safe_assign_two_routes(state, from, new_from, to, new_to, ev)) accepted_move = true;
                                    else cap_viol++;
                                }
                            }
                        }
                    }
                }
            }
        }
        // CROSS
        else {
            int r1 = draw_route_min_size(5), r2 = draw_route_min_size(5);
            if (r1 < 0 || r2 < 0) {
                // no eligible cross-route pair
            } else if (r1 == r2) {
                // skip same-route cross
            } else if (!allow_cross2) {
                // skip
            } else {
                int i1 = 1 + rng() % (state.routes[r1].size() - 3);
                int i2 = 1 + rng() % (state.routes[r2].size() - 3);
                ++effective_proposals;
                proposal_made = true;
                double approx = ev.delta_cross2_approx(state, r1, i1, r2, i2);
                double ratio = clamp_ratio(-approx / max(T, 1e-9));
                double prob = exp(ratio);
                if (approx < 0 || prob > unif(rng)) {
                    double weighted_delta = compute_weighted_cross_delta(state, ev, r1, i1, r2, i2);
                    double accept_prob = exp(clamp_ratio(-weighted_delta / max(T, 1e-9)));
                    if (weighted_delta < 0 || accept_prob > unif(rng)) {
                        vector<int> tail1(state.routes[r1].begin() + i1, state.routes[r1].end());
                        vector<int> tail2(state.routes[r2].begin() + i2, state.routes[r2].end());
                        vector<int> new1(state.routes[r1].begin(), state.routes[r1].begin() + i1);
                        vector<int> new2(state.routes[r2].begin(), state.routes[r2].begin() + i2);
                        new1.insert(new1.end(), tail2.begin(), tail2.end());
                        new2.insert(new2.end(), tail1.begin(), tail1.end());
                        enforce_trip_separators(new1, CG, depot);
                        enforce_trip_separators(new2, CG, depot);
                        double o1 = compute_route_overload_max(new1, CG, depot);
                        double o2 = compute_route_overload_max(new2, CG, depot);
                        if (o1 > 0.0 || o2 > 0.0) {
                            cap_viol++;
                            total_overload += (max(0.0, o1) + max(0.0, o2));
                        } else {
                            if (safe_assign_two_routes(state, r1, new1, r2, new2, ev)) accepted_move = true;
                            else cap_viol++;
                        }
                    }
                }
            }
        }

        if (accepted_move) {
            accepted++;
            window_accepted++;
            stagnation = 0;
            // A hard-feasible improvement can be valuable even when a lower
            // penalized infeasible search-best already exists.
            consider_feasible(state, "feasible_improvement");
            if (state.objective < best.objective - 1e-9) {
                best = state;
                append_convergence_row(shared_conv_log, conv_mtx, {
                    solver_elapsed_seconds(), seed, iterations, state.objective,
                    best.objective, T, accepted, attempted, stagnation,
                    "improvement"
                });
            }
        } else {
            stagnation++;
        }

        // V18 fixed-budget thermostat.  V16 still multiplied T by 0.9996 for
        // every evaluated proposal.  At millions of proposals per second this
        // drove T to ~1e-9 in a fraction of the wall-clock budget; even its 1.2x
        // "reheat" could not offset 0.9996^1000 ~= 0.67.  Here the base schedule
        // is a function of elapsed worker time and an acceptance-feedback bias.
        if (proposal_made) {
            ++window_attempts;
            if (window_attempts >= adapt_window) {
                const double acc_rate =
                    (double)window_accepted / max(1.0, (double)window_attempts);
                const double elapsed_worker =
                    chrono::duration<double>(Clock::now() - tstart).count();
                const double progress = min(1.0, max(0.0,
                    elapsed_worker / max(1e-9, time_limit)));
                // E1 quench deliberately recreates the old engine's useful
                // search *regime* without restoring its broken T0 calibration:
                // brief shake, rapid drop by ~32% of the epoch, then cold work.
                double schedule_progress = progress;
                if (phase_temperature_profile == 1) {
                    if (progress < 0.08)
                        schedule_progress = 0.10 * (progress / 0.08);
                    else if (progress < 0.32)
                        schedule_progress = 0.10 + 0.90 * ((progress - 0.08) / 0.24);
                    else
                        schedule_progress = 1.0;
                }
                const double base_T = worker_initial_temperature *
                    exp(log(end_temperature_ratio) * schedule_progress);

                const double target_acceptance = target_accept_end +
                    (target_accept_start - target_accept_end) *
                    (1.0 - schedule_progress) * (1.0 - schedule_progress);
                thermostat_log_bias +=
                    thermostat_gain * (target_acceptance - acc_rate);
                thermostat_log_bias = max(-thermostat_bias_cap,
                    min(thermostat_bias_cap, thermostat_log_bias));
                T = base_T * exp(thermostat_log_bias);
                T = min(1e8, max(1e-6, T));

                window_attempts = 0;
                window_accepted = 0;
            }
        }

        // Elite pool update and path relink. V20 uses wall-clock cadence so
        // these expensive mechanisms retain stable budget share when proposal
        // throughput changes.
        const double meta_elapsed = chrono::duration<double>(Clock::now() - tstart).count();
        if (cfg.use_elite_pool) {
            if (meta_elapsed + 1e-12 >= next_elite_local_s) {
                next_elite_local_s = meta_elapsed + max(0.01, cfg.elite_update_period_s);
                if (solution_hard_feasible(state, *ev.CG, pm)) {
                    elite_pool_update(elite_pool, state, 8);
                }
                if (feasible_best_valid) elite_pool_update(elite_pool, feasible_best, 8);
            }
            if (cfg.use_path_relink && elite_pool.size() >= 2 &&
                meta_elapsed + 1e-12 >= next_relink_local_s) {
                next_relink_local_s = meta_elapsed + max(0.05, cfg.relink_period_s);
                SolutionState relink = path_relink_between(elite_pool[0], elite_pool[1], ev, pm);
                recompute_state_metrics_and_loads(relink, ev);
                if (solution_hard_feasible(relink, *ev.CG, pm)) {
                    consider_feasible(relink, "feasible_path_relink");
                    if (relink.objective + 1e-9 < best.objective) {
                        best = std::move(relink);
                        append_convergence_row(shared_conv_log, conv_mtx, {
                            solver_elapsed_seconds(), seed, iterations, best.objective,
                            feasible_best_valid ? feasible_best.objective : best.objective,
                            T, accepted, attempted, stagnation,
                            "path_relink_improvement"
                        });
                    }
                }
            }
        }

        // V32 in-loop ALNS. Legacy `stagnation` is a consecutive-rejection
        // streak because any accepted SA move resets it; that is not a valid
        // measure of search stagnation. Use wall time since the last hard-feasible
        // best improvement and dedicate explicit workers to macro LNS moves.
        const bool alns_time_eligible = cfg.use_alns && alns_kick_specialist &&
            (meta_elapsed - last_feasible_best_improvement_local_s + 1e-12 >= cfg.alns_stagnation_s);
        if (alns_time_eligible && meta_elapsed + 1e-12 >= next_alns_local_s && !solver_should_stop()) {
            next_alns_local_s = meta_elapsed + max(0.05, cfg.alns_kick_cooldown_s);
            const int destroy_mode = (int)(alns_kick_sequence++ % 3LL);
            profile.alns_kick_calls.fetch_add(1, memory_order_relaxed);
            if (destroy_mode == 0) profile.alns_kick_destroy0_calls.fetch_add(1, memory_order_relaxed);
            if (destroy_mode == 1) profile.alns_kick_destroy1_calls.fetch_add(1, memory_order_relaxed);
            if (destroy_mode == 2) profile.alns_kick_destroy2_calls.fetch_add(1, memory_order_relaxed);
            const auto lns_t0 = Clock::now();
            SolutionState kicked = alns_destroy_repair(state, ev, pm, rng, destroy_mode);
            profile.alns_kick_time_us.fetch_add(
                chrono::duration_cast<chrono::microseconds>(Clock::now() - lns_t0).count(), memory_order_relaxed);
            recompute_state_metrics_and_loads(kicked, ev);
            FeasibleUpdate fu = consider_feasible(kicked, "feasible_alns_kick_v32");
            if (fu.local_best) profile.alns_kick_feasible_best_improvements.fetch_add(1, memory_order_relaxed);
            if (fu.global_best) profile.alns_kick_global_best_improvements.fetch_add(1, memory_order_relaxed);

            const double macro_delta = kicked.objective - state.objective;
            bool adopt_macro = macro_delta < -1e-9;
            bool metropolis_worse = false;
            if (!adopt_macro && cfg.lns_macro_metropolis && isfinite(macro_delta) && macro_delta > 1e-9) {
                const double p_macro = exp(clamp_ratio(-macro_delta / max(T, 1e-9)));
                metropolis_worse = p_macro > unif(rng);
                adopt_macro = metropolis_worse;
            }
            if (adopt_macro) {
                state = std::move(kicked);
                if (macro_delta < -1e-9) profile.alns_kick_state_improvements.fetch_add(1, memory_order_relaxed);
                if (metropolis_worse) profile.alns_kick_metropolis_worse_accepts.fetch_add(1, memory_order_relaxed);
                if (state.objective + 1e-9 < best.objective) {
                    best = state;
                    append_convergence_row(shared_conv_log, conv_mtx, {
                        solver_elapsed_seconds(), seed, (long long)iterations,
                        state.objective, best.objective, T, accepted, attempted,
                        stagnation, "alns_kick_improvement_v32"
                    });
                }
            }
        }

        // V31 structural string-LNS: does not dilute the legacy 3-way ALNS
        // distribution. It receives a separate, explicit wall-clock slice only
        // on structural workers after stagnation.
        if (cfg.use_string_slack_kick && structural_worker) {
            profile.string_slack_kick_trigger_checks.fetch_add(1, memory_order_relaxed);
        }
        const bool string_stagnation_eligible = cfg.use_string_slack_kick && structural_worker &&
            (meta_elapsed - last_feasible_best_improvement_local_s + 1e-12 >= cfg.string_slack_stagnation_s);
        if (string_stagnation_eligible) {
            profile.string_slack_kick_stagnation_eligible.fetch_add(1, memory_order_relaxed);
        }
        if (string_stagnation_eligible &&
            meta_elapsed + 1e-12 >= next_string_slack_local_s && !solver_should_stop()) {
            next_string_slack_local_s = meta_elapsed + max(0.05, cfg.string_slack_kick_period_s);
            profile.string_slack_kick_calls.fetch_add(1, memory_order_relaxed);
            const auto ss_t0 = Clock::now();
            SolutionState ss = alns_destroy_repair(state, ev, pm, rng, 3);
            profile.string_slack_kick_time_us.fetch_add(
                chrono::duration_cast<chrono::microseconds>(Clock::now()-ss_t0).count(), memory_order_relaxed);
            recompute_state_metrics_and_loads(ss, ev);
            FeasibleUpdate fu = consider_feasible(ss, "feasible_adjacent_string_kick");
            if (fu.local_best) profile.string_slack_kick_feasible_best_improvements.fetch_add(1, memory_order_relaxed);
            if (fu.global_best) profile.string_slack_kick_global_best_improvements.fetch_add(1, memory_order_relaxed);

            const double macro_delta = ss.objective - state.objective;
            bool adopt_macro = macro_delta < -1e-9;
            bool metropolis_worse = false;
            if (!adopt_macro && cfg.lns_macro_metropolis && isfinite(macro_delta) && macro_delta > 1e-9) {
                const double p_macro = exp(clamp_ratio(-macro_delta / max(T, 1e-9)));
                metropolis_worse = p_macro > unif(rng);
                adopt_macro = metropolis_worse;
            }
            if (adopt_macro) {
                state = std::move(ss);
                if (macro_delta < -1e-9) profile.string_slack_kick_improvements.fetch_add(1, memory_order_relaxed);
                if (metropolis_worse) profile.string_slack_kick_metropolis_worse_accepts.fetch_add(1, memory_order_relaxed);
                if (state.objective + 1e-9 < best.objective) {
                    best = state;
                    append_convergence_row(shared_conv_log, conv_mtx, {
                        solver_elapsed_seconds(), seed, (long long)iterations,
                        state.objective, best.objective, T, accepted, attempted,
                        stagnation, "adjacent_string_kick_improvement"
                    });
                }
            }
        }

        if (iterations % 500 == 0) {
            double full_check = ev.compute_objective_from_metrics(state.route_metrics);
            if (fabs(full_check - state.objective) > 1e-6) {
                drift_corrections++;
                state.objective = full_check;
            }
        }

        if (iterations % 10000 == 0) {
            vector<int> counts(CG.nodes.size(), 0);
            for (const auto &r : state.routes) {
                for (int nid : r) {
                    if (CG.nodes[nid].type == 2) counts[nid]++;
                }
            }

            bool mismatch = false;
            for (size_t i = 0; i < counts.size(); ++i) {
                if (counts[i] != state.served_count[i]) {
                    mismatch = true;
                    break;
                }
            }

            if (mismatch) {
                recompute_state_metrics_and_loads(state, ev);
                drift_corrections++;
            }
        }

        if (cfg.log_convergence) {
            const double tnow = solver_elapsed_seconds();
            if (tnow + 1e-12 >= next_trace_sample_s) {
                const double reported_best = feasible_best_valid ? feasible_best.objective : best.objective;
                out.convergence.push_back({tnow, reported_best});
                append_convergence_row(shared_conv_log, conv_mtx, {
                    tnow, seed, (long long)iterations, state.objective,
                    reported_best, T, accepted, attempted, stagnation, "periodic"
                });
                next_trace_sample_s = tnow + cfg.convergence_sample_period_s;
            }
        }
    }

    // Refine the hard-feasible incumbent independently. Also give the penalized
    // search incumbent one recovery attempt; only adopt it if it becomes hard feasible.
    if (feasible_best_valid) {
        // Transactional refinement: never destroy a valid incumbent.
        SolutionState refined_feasible = feasible_best;
        final_refinement_pass(refined_feasible, ev, pm);
        recompute_state_metrics_and_loads(refined_feasible, ev);
        if (solution_hard_feasible(refined_feasible, *ev.CG, pm) &&
            refined_feasible.objective + 1e-9 < feasible_best.objective) {
            feasible_best = std::move(refined_feasible);
        }
    }

    SolutionState recovered = best;
    final_refinement_pass(recovered, ev, pm);
    recompute_state_metrics_and_loads(recovered, ev);
    if (solution_hard_feasible(recovered, *ev.CG, pm)) {
        if (!feasible_best_valid || recovered.objective + 1e-9 < feasible_best.objective) {
            feasible_best = std::move(recovered);
            feasible_best_valid = true;
        }
    }

    if (feasible_best_valid) update_global_best_checked(feasible_best, *ev.CG, pm);

    out.best_state = feasible_best_valid ? feasible_best : best;
    out.runtime_sec = chrono::duration<double>(Clock::now() - tstart).count();
    out.iterations = iterations;
    out.accepted_moves = accepted;
    out.attempted_moves = attempted;
    out.drift_corrections = drift_corrections;
    out.capacity_violations = cap_viol;
    out.total_overload = total_overload;
    out.last_improvement_age_s = max(0.0, out.runtime_sec - last_feasible_best_improvement_local_s);

    // Aggregate once per completed worker, not inside the SA hot loop.
    profile.sa_iterations.fetch_add(iterations, memory_order_relaxed);
    profile.sa_accepted_moves.fetch_add(accepted, memory_order_relaxed);
    profile.sa_attempted_moves.fetch_add(attempted, memory_order_relaxed);
    profile.sa_effective_proposals.fetch_add(effective_proposals, memory_order_relaxed);
    profile.sa_route_draw_failures.fetch_add(route_draw_failures, memory_order_relaxed);
    profile.sa_drift_corrections.fetch_add(drift_corrections, memory_order_relaxed);
    profile.sa_capacity_violation_trials.fetch_add(cap_viol, memory_order_relaxed);
    profile.sa_total_overload_milli.fetch_add(
        static_cast<long long>(llround(total_overload * 1000.0)),
        memory_order_relaxed
    );
    profile.sa_time_us.fetch_add(
        static_cast<long long>(llround(out.runtime_sec * 1'000'000.0)),
        memory_order_relaxed
    );
    safe_log_line("[SA-stop-V34] seed=", seed,
                  " reason=", sa_stop_reason,
                  " runtime_s=", out.runtime_sec,
                  " loops=", iterations,
                  " effective_proposals=", effective_proposals);

    // Log the final best after final refinement.
    // This makes convergence.csv match the final printed solution.
    if (cfg.log_convergence) {
        double tnow = solver_elapsed_seconds();

        const double final_reported = out.best_state.objective;
        out.convergence.push_back({tnow, final_reported});
        append_convergence_row(shared_conv_log, conv_mtx, {
            tnow, seed, (long long)iterations, final_reported, final_reported,
            T, accepted, attempted, stagnation, "final_refinement"
        });
    }

    return out;
}


/* ============================================================
   E1 PHASE-SPECIALIZED PORTFOLIO ENGINE
   ------------------------------------------------------------
   The existing neighborhoods remain unchanged. This layer changes only
   temporal orchestration and state ownership:
     * size-adaptive multi-basin structure acquisition,
     * persistent worker identities across epochs,
     * diversity-aware elite archive,
     * explicit cold / quench / structure / macro / region / breeder roles,
     * barriered information exchange instead of winner-take-all restarts.
   ============================================================ */

static unordered_set<uint64_t> phase_edge_signature(const SolutionState &ss, const Compressed &CG) {
    unordered_set<uint64_t> sig;
    const int depot = find_depot_idx(CG);
    auto ek = [](int a, int b) -> uint64_t {
        return (uint64_t(uint32_t(a)) << 32) | uint32_t(b);
    };
    for (const auto &r : ss.routes) {
        int prev = depot;
        bool active = false;
        for (int x : r) {
            if (x < 0 || x >= (int)CG.nodes.size()) continue;
            if (CG.nodes[x].type == 2) {
                sig.insert(ek(prev, x));
                prev = x;
                active = true;
            } else if (CG.nodes[x].type == 1 && active && prev != depot) {
                sig.insert(ek(prev, depot));
                prev = depot;
                active = false;
            }
        }
        if (active && prev != depot) sig.insert(ek(prev, depot));
    }
    return sig;
}

static double phase_structural_distance(
    const SolutionState &a,
    const SolutionState &b,
    const Compressed &CG
) {
    auto A = phase_edge_signature(a, CG);
    auto B = phase_edge_signature(b, CG);
    double edge_d = 0.0;
    if (!(A.empty() && B.empty())) {
        const auto *S = &A, *L = &B;
        if (S->size() > L->size()) swap(S, L);
        size_t common = 0;
        for (uint64_t e : *S) if (L->count(e)) ++common;
        const size_t uni = A.size() + B.size() - common;
        edge_d = uni ? 1.0 - double(common) / double(uni) : 0.0;
    }
    const double assign_d = pr_assignment_distance_aligned(a, b, CG);
    return 0.62 * edge_d + 0.38 * assign_d;
}

static void phase_archive_rebuild(
    vector<SolutionState> &archive,
    vector<SolutionState> candidates,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const Compressed &CG = *ev.CG;
    for (auto &x : archive) candidates.push_back(x);

    vector<SolutionState> feasible;
    feasible.reserve(candidates.size());
    for (auto &c : candidates) {
        recompute_state_metrics_and_loads(c, ev);
        if (solution_hard_feasible(c, CG, pm)) feasible.push_back(std::move(c));
    }
    if (feasible.empty()) return;
    sort(feasible.begin(), feasible.end(), [](const SolutionState &a, const SolutionState &b) {
        return a.objective < b.objective;
    });

    // Diversity is useful only inside a competitive quality envelope.  E1
    // could retain a catastrophically weak warm start simply because it was far
    // from the good basins, then waste an entire persistent lane on it.
    const double archive_best_obj = feasible.front().objective;
    const double archive_cap_obj = archive_best_obj *
        (1.0 + max(0.0, cfg.phase_archive_max_quality_gap));
    vector<SolutionState> quality_feasible;
    quality_feasible.reserve(feasible.size());
    for (auto &c : feasible) {
        if (c.objective <= archive_cap_obj + 1e-9)
            quality_feasible.push_back(std::move(c));
    }
    feasible = std::move(quality_feasible);
    if (feasible.empty()) return;

    // Quality-ordered clone suppression. The first member of a structural
    // neighborhood is the best member because feasible[] is objective sorted.
    vector<SolutionState> unique;
    unique.reserve(feasible.size());
    for (auto &c : feasible) {
        bool clone = false;
        for (const auto &u : unique) {
            if (phase_structural_distance(c, u, CG) < cfg.phase_archive_clone_distance) {
                clone = true;
                break;
            }
        }
        if (!clone) unique.push_back(std::move(c));
    }
    if (unique.empty()) return;

    const int target = min(cfg.phase_archive_size, (int)unique.size());
    vector<SolutionState> selected;
    vector<char> used(unique.size(), 0);
    selected.push_back(unique[0]);
    used[0] = 1;
    const double qw = cfg.phase_archive_quality_weight;
    while ((int)selected.size() < target) {
        int pick = -1;
        double best_score = -1e100;
        for (int i = 0; i < (int)unique.size(); ++i) if (!used[i]) {
            double min_d = 1.0;
            for (const auto &e : selected)
                min_d = min(min_d, phase_structural_distance(unique[i], e, CG));
            const double q = unique.size() <= 1 ? 1.0 :
                1.0 - double(i) / double(unique.size() - 1);
            const double score = qw * q + (1.0 - qw) * min_d;
            if (score > best_score) {
                best_score = score;
                pick = i;
            }
        }
        if (pick < 0) break;
        used[pick] = 1;
        selected.push_back(unique[pick]);
    }
    sort(selected.begin(), selected.end(), [](const SolutionState &a, const SolutionState &b) {
        return a.objective < b.objective;
    });
    archive = std::move(selected);
}

static pair<int,int> phase_select_parent_pair(
    const vector<SolutionState> &archive,
    const Compressed &CG
) {
    if (archive.size() < 2) return {-1,-1};
    const double best = archive.front().objective;
    int bi = -1, bj = -1;
    double best_score = -1e100;
    double fallback_d = -1.0;
    pair<int,int> fallback{-1,-1};
    for (int i = 0; i < (int)archive.size(); ++i) {
        for (int j = i + 1; j < (int)archive.size(); ++j) {
            const double d = phase_structural_distance(archive[i], archive[j], CG);
            if (d > fallback_d) { fallback_d = d; fallback = {i,j}; }
            const double gap_i = (archive[i].objective - best) / max(1.0, fabs(best));
            const double gap_j = (archive[j].objective - best) / max(1.0, fabs(best));
            if (gap_i > cfg.phase_parent_quality_band || gap_j > cfg.phase_parent_quality_band) continue;
            if (d + 1e-12 < cfg.phase_parent_min_distance) continue;
            const double q = max(0.0, 1.0 - 0.5 * (gap_i + gap_j) /
                max(1e-9, cfg.phase_parent_quality_band));
            const double score = 0.56 * q + 0.44 * d;
            if (score > best_score) { best_score = score; bi = i; bj = j; }
        }
    }
    if (bi >= 0) return {bi,bj};
    return fallback;
}

static bool phase_has_strong_parent_pair(
    const vector<SolutionState> &archive,
    const Compressed &CG,
    double *best_distance_out = nullptr
) {
    if (best_distance_out) *best_distance_out = 0.0;
    if (archive.size() < 2) return false;
    const double best = archive.front().objective;
    double best_d = 0.0;
    bool found = false;
    for (int i = 0; i < (int)archive.size(); ++i) {
        const double gap_i = (archive[i].objective - best) / max(1.0, fabs(best));
        if (gap_i > cfg.phase_parent_quality_band + 1e-12) continue;
        for (int j = i + 1; j < (int)archive.size(); ++j) {
            const double gap_j = (archive[j].objective - best) / max(1.0, fabs(best));
            if (gap_j > cfg.phase_parent_quality_band + 1e-12) continue;
            const double d = phase_structural_distance(archive[i], archive[j], CG);
            best_d = max(best_d, d);
            if (d + 1e-12 >= cfg.phase_parent_min_distance) found = true;
        }
    }
    if (best_distance_out) *best_distance_out = best_d;
    return found;
}

static int phase_pick_diverse_archive_index(
    const vector<SolutionState> &archive,
    const SolutionState &reference,
    const Compressed &CG,
    double max_quality_gap = -1.0
) {
    if (archive.empty()) return -1;
    int pick = -1;
    double score_best = -1e100;
    const double best = archive.front().objective;
    for (int i = 0; i < (int)archive.size(); ++i) {
        const double gap = (archive[i].objective - best) / max(1.0, fabs(best));
        if (max_quality_gap >= 0.0 && gap > max_quality_gap + 1e-12) continue;
        const double d = phase_structural_distance(reference, archive[i], CG);
        const double q = 1.0 / (1.0 + 20.0 * max(0.0, gap));
        const double score = 0.35 * q + 0.65 * d;
        if (score > score_best) { score_best = score; pick = i; }
    }
    if (pick < 0) pick = 0;
    return pick;
}

static void phase_archive_log(
    const vector<SolutionState> &archive,
    const Compressed &CG,
    const char *stage,
    int epoch
) {
    double mean_d = 0.0, min_d = 1.0;
    int pairs = 0;
    for (int i = 0; i < (int)archive.size(); ++i)
        for (int j = i + 1; j < (int)archive.size(); ++j) {
            const double d = phase_structural_distance(archive[i], archive[j], CG);
            mean_d += d;
            min_d = min(min_d, d);
            ++pairs;
        }
    if (pairs) mean_d /= pairs; else min_d = 0.0;
    safe_log_line("[PhaseArchive-E32] stage=", stage,
                  " epoch=", epoch,
                  " size=", archive.size(),
                  " best=", archive.empty() ? INF_D : archive.front().objective,
                  " mean_div=", mean_d,
                  " min_div=", min_d,
                  " elapsed=", solver_elapsed_seconds());
}

struct PhaseLNSPolicyState {
    array<double,6> op_w = {1,1,1,1,1,1};
    array<double,3> intensity_w = {1,1,1};
    bool initialized = false;
    long long calls = 0;
};

static void phase_init_lns_policy_e3(
    PhaseLNSPolicyState &ps,
    bool macro_role,
    int n_customers,
    int profile_id
) {
    if (ps.initialized) return;
    if (macro_role) {
        ps.op_w = {1.20, 0.38, 0.42, 0.65, 1.45, 1.35};
        ps.intensity_w = {0.95, 1.20, 1.05};
    } else if (n_customers >= 400) {
        static const array<array<double,6>,4> P = {{
            {{3.20,0.05,0.07,0.20,3.20,0.12}},
            {{1.70,0.05,0.08,0.22,4.20,0.15}},
            {{3.50,0.08,0.10,0.28,2.60,0.30}},
            {{2.20,0.18,0.22,0.45,2.50,0.45}}
        }};
        ps.op_w = P[(profile_id % 4 + 4) % 4];
        // Coarse ownership changes are useful before the basin is repaired.
        ps.intensity_w = {0.72, 1.05, 1.55};
    } else {
        static const array<array<double,6>,4> P = {{
            {{2.50,0.08,0.12,0.65,2.80,1.60}},
            {{1.70,0.06,0.10,0.45,3.90,1.10}},
            {{1.60,0.06,0.10,0.55,1.80,3.80}},
            {{2.00,0.22,0.28,0.80,2.10,1.90}}
        }};
        ps.op_w = P[(profile_id % 4 + 4) % 4];
        ps.intensity_w = {1.15, 1.25, 0.90};
    }
    ps.initialized = true;
}

static AlgoResult run_phase_adaptive_lns_worker(
    const SolutionState &seed_state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    double budget_s,
    unsigned seed,
    bool macro_role,
    vector<ConvergenceLogRow> *shared_conv_log,
    mutex *conv_mtx,
    int profile_id = 0,
    PhaseLNSPolicyState *persistent_policy = nullptr
) {
    AlgoResult out;
    const auto t0 = Clock::now();
    ScopedWorkerDeadline deadline(budget_s);
    mt19937 rng(seed ^ (macro_role ? 0xBADC0DEu : 0x6A09E667u));
    SolutionState best = seed_state;
    SolutionState current = seed_state;
    recompute_state_metrics_and_loads(best, ev);
    recompute_state_metrics_and_loads(current, ev);
    const int n_customers = (int)collect_customers_from_state(seed_state, *ev.CG).size();

    PhaseLNSPolicyState local_policy;
    PhaseLNSPolicyState &policy = persistent_policy ? *persistent_policy : local_policy;
    if (!cfg.phase_persist_lns_policy || !policy.initialized)
        phase_init_lns_policy_e3(policy, macro_role, n_customers, profile_id);
    array<double,6> w = policy.op_w;
    array<double,3> iw = policy.intensity_w;

    const bool old_override = tls_repair_mode_override_enabled;
    const RepairMode old_mode = tls_repair_mode_override;
    const bool old_no_polish = tls_disable_post_repair_polish;
    tls_repair_mode_override_enabled = true;
    tls_repair_mode_override = RepairMode::GREEDY_FAST;
    tls_disable_post_repair_polish = true;

    constexpr int MAX_OPS = 6;
    constexpr int INTENSITIES = 3;
    const int operator_count = cfg.phase_e2_destroy_policy ? 6 : 4;
    array<long long,MAX_OPS> attempts = {0,0,0,0,0,0};
    array<long long,MAX_OPS> feasible = {0,0,0,0,0,0};
    array<long long,MAX_OPS> improvements = {0,0,0,0,0,0};
    array<double,MAX_OPS> time_ms = {0,0,0,0,0,0};
    array<double,MAX_OPS> gain_sum = {0,0,0,0,0,0};
    array<long long,INTENSITIES> intensity_attempts = {0,0,0};
    array<long long,INTENSITIES> intensity_improvements = {0,0,0};
    array<double,INTENSITIES> intensity_gain = {0,0,0};
    array<double,INTENSITIES> intensity_time_ms = {0,0,0};
    long long it = 0, accepted = 0, macro_worse_accepted = 0;
    auto last_gain = Clock::now();
    const double search_budget = macro_role
        ? max(0.20, budget_s * cfg.phase_macro_search_fraction)
        : budget_s;
    const double patience = max(1.0, min(cfg.phase_structure_no_improve_s,
                                        max(1.0, search_budget * 0.65)));
    const double dmin = macro_role ? cfg.phase_macro_destroy_min_ratio
                                   : cfg.phase_structure_destroy_min_ratio;
    const double dmax = macro_role ? cfg.phase_macro_destroy_max_ratio
                                   : cfg.phase_structure_destroy_max_ratio;
    uniform_real_distribution<double> U01(0.0, 1.0);

    auto weighted_pick = [&](const auto &weights, int count, double eps) -> int {
        if (count <= 1) return 0;
        if (U01(rng) < eps) return (int)(rng() % (unsigned)count);
        double total = 0.0;
        for (int k = 0; k < count; ++k) total += max(0.02, weights[k]);
        double ticket = U01(rng) * max(1e-9, total);
        for (int k = 0; k < count; ++k) {
            ticket -= max(0.02, weights[k]);
            if (ticket <= 0.0) return k;
        }
        return count - 1;
    };

    while (!solver_should_stop()) {
        const double elapsed = chrono::duration<double>(Clock::now() - t0).count();
        if (search_budget > 0.0 && elapsed >= search_budget) break;
        const double progress = (seed_state.objective > 1e-9)
            ? max(0.0, (seed_state.objective - best.objective) / seed_state.objective)
            : 0.0;

        // E3 keeps the E2 stage signal, but the policy is now persistent rather
        // than relearned from scratch in every epoch.
        if (!macro_role && n_customers >= 400 && progress >= 0.24) {
            w[5] = max(w[5], 1.35);
            w[4] = max(w[4], 1.85);
            iw[0] = max(iw[0], 1.25); // shrink ruins once structure is credible
            iw[2] *= 0.995;
        }

        int mode = 0;
        if (it < operator_count && policy.calls == 0) {
            // Bootstrap every family once so a new dataset can still surprise us.
            mode = (int)it;
        } else if (!macro_role && n_customers >= 250 && cfg.metric_mode == "road") {
            // E10 road evidence: expensive-related and Shaw-related repeatedly
            // collapse to the weight floor after bootstrap while random,
            // string-slack, multi-route blocks and seam-scatter dominate gain/s.
            // Keep the weak arms measurable at bootstrap, then stop paying the
            // full O(n log n) relatedness sort on every epsilon exploration.
            static const array<int,4> road_ops = {0,3,4,5};
            const double eps = 0.075;
            if (U01(rng) < eps) {
                mode = road_ops[rng() % road_ops.size()];
            } else {
                double total = 0.0;
                for (int op : road_ops) total += max(0.02, w[op]);
                double ticket = U01(rng) * max(1e-9, total);
                mode = road_ops.back();
                for (int op : road_ops) {
                    ticket -= max(0.02, w[op]);
                    if (ticket <= 0.0) { mode = op; break; }
                }
            }
        } else {
            mode = weighted_pick(w, operator_count, macro_role ? 0.13 : 0.09);
        }

        int intensity = 1;
        if (cfg.phase_adapt_destroy_intensity) {
            if (it < INTENSITIES && policy.calls == 0) intensity = (int)it;
            else intensity = weighted_pick(iw, INTENSITIES, 0.10);
        }
        static const array<double,INTENSITIES> scale = {0.64, 1.00, 1.38};
        double op_dmin = dmin * scale[intensity];
        double op_dmax = dmax * scale[intensity];
        if (mode == 4) {
            op_dmin *= 0.82;
            op_dmax *= 1.03;
        } else if (mode == 5) {
            op_dmin *= 0.62;
            op_dmax *= 0.88;
        }
        op_dmin = max(0.01, min(0.80, op_dmin));
        op_dmax = max(op_dmin, min(0.90, op_dmax));

        const auto rt0 = Clock::now();
        const SolutionState &source_state = macro_role ? current : best;
        SolutionState cand = alns_destroy_repair(
            source_state, ev, pm, rng, mode, op_dmin, op_dmax);
        const double ms = chrono::duration<double,milli>(Clock::now() - rt0).count();
        ++attempts[mode]; time_ms[mode] += ms;
        ++intensity_attempts[intensity]; intensity_time_ms[intensity] += ms;
        ++it;
        recompute_state_metrics_and_loads(cand, ev);
        const bool feas = solution_hard_feasible(cand, *ev.CG, pm);
        if (feas) ++feasible[mode];

        bool best_improved = false;
        bool current_accepted = false;
        if (feas && cand.objective + 1e-9 < best.objective) {
            const double before = best.objective;
            const double gain = before - cand.objective;
            const double meaningful = max(1.0, meaningful_gain_threshold(before));
            const double normalized_gain = gain / meaningful;
            const double gain_per_ms = normalized_gain / max(0.10, ms);
            const double reward = min(12.0,
                1.20 + min(6.0, normalized_gain) + min(4.2, 13.0 * gain_per_ms));
            w[mode] = min(12.0, max(0.08, 0.86 * w[mode] + 0.14 * reward));
            iw[intensity] = min(10.0, max(0.08,
                0.88 * iw[intensity] + 0.12 * min(10.0, reward)));
            ++improvements[mode]; gain_sum[mode] += gain;
            ++intensity_improvements[intensity]; intensity_gain[intensity] += gain;
            ++accepted;
            best = cand;
            if (macro_role) current = cand;
            last_gain = Clock::now();
            best_improved = true;
            current_accepted = true;
            append_convergence_row(shared_conv_log, conv_mtx, {
                solver_elapsed_seconds(), seed, it, best.objective, best.objective,
                0.0, accepted, it, it-accepted,
                macro_role ? "phase_macro_lns_improvement" : "phase_structure_lns_improvement"
            });
        } else if (macro_role && feas) {
            const double elapsed_now = chrono::duration<double>(Clock::now() - t0).count();
            const double p = search_budget > 1e-9
                ? min(1.0, max(0.0, elapsed_now / search_budget)) : 1.0;
            const double relative_cap = 0.028 - 0.012 * p; // 2.8% -> 1.6%
            const double cap_obj = best.objective * (1.0 + relative_cap);
            if (cand.objective <= cap_obj + 1e-9) {
                const double delta = cand.objective - current.objective;
                if (delta <= 1e-9) {
                    current_accepted = true;
                } else {
                    const double T = max(1.0,
                        best.objective * (0.0055 * (1.0 - p) + 0.0010));
                    const double prob = exp(-delta / T);
                    if (U01(rng) < prob) {
                        current_accepted = true;
                        ++macro_worse_accepted;
                    }
                }
            }
            if (current_accepted) {
                const double novelty = phase_structural_distance(cand, best, *ev.CG);
                current = std::move(cand);
                ++accepted;
                const double div_reward = min(1.0, 2.0 * novelty) /
                    sqrt(max(0.10, ms));
                w[mode] = max(0.08, min(12.0,
                    0.96 * w[mode] + 0.04 * (0.20 + div_reward)));
                iw[intensity] = max(0.08, min(10.0,
                    0.97 * iw[intensity] + 0.03 * (0.20 + div_reward)));
            }
        }

        if (!best_improved && !current_accepted) {
            const double speed_floor = min(0.40, 0.16 / sqrt(max(0.10, ms)));
            w[mode] = max(0.08, 0.93 * w[mode] + 0.07 * speed_floor);
            iw[intensity] = max(0.08, 0.95 * iw[intensity] + 0.05 * speed_floor);
        }
        const double no_gain = chrono::duration<double>(Clock::now() - last_gain).count();
        if (elapsed >= min(search_budget, max(1.0, search_budget * 0.35)) &&
            no_gain >= patience) break;
    }

    // Restore the production TLS policy before the recovery phase.  E2 could
    // hand a deliberately worse macro basin directly to the next epoch.  E3
    // first gives that basin a bounded local-search recovery window so we test
    // basin potential rather than raw ruin objective.
    tls_repair_mode_override_enabled = old_override;
    tls_repair_mode_override = old_mode;
    tls_disable_post_repair_polish = old_no_polish;

    if (macro_role && !solver_should_stop()) {
        const double used = chrono::duration<double>(Clock::now() - t0).count();
        const double recover_budget = max(0.0, budget_s - used);
        if (recover_budget >= 0.05 && solution_hard_feasible(current, *ev.CG, pm)) {
            SolutionState recovered = current;
            const double before_recover = recovered.objective;
            {
                ScopedWorkerDeadline cap(recover_budget);
                interroute_polish_solution(recovered, ev, pm);
            }
            recompute_state_metrics_and_loads(recovered, ev);
            if (solution_hard_feasible(recovered, *ev.CG, pm)) {
                if (recovered.objective + 1e-9 < current.objective)
                    current = recovered;
                if (recovered.objective + 1e-9 < best.objective) {
                    best = recovered;
                    last_gain = Clock::now();
                }
                safe_log_line("[PhaseMacroRecovery-E3] before=", before_recover,
                              " after=", recovered.objective,
                              " gain=", before_recover-recovered.objective,
                              " budget_s=", recover_budget);
            }
        }
    }

    recompute_state_metrics_and_loads(best, ev);
    recompute_state_metrics_and_loads(current, ev);
    out.best_state = best;
    if (macro_role &&
        solution_hard_feasible(current, *ev.CG, pm) &&
        current.objective <= best.objective *
            (1.0 + cfg.phase_macro_recovery_quality_gap) + 1e-9) {
        const double alt_d = phase_structural_distance(current, best, *ev.CG);
        if (alt_d >= max(0.010, cfg.phase_archive_clone_distance * 1.15)) {
            out.alternate_state = current;
            out.has_alternate_state = true;
        }
    }
    out.runtime_sec = chrono::duration<double>(Clock::now() - t0).count();
    out.last_improvement_age_s = chrono::duration<double>(Clock::now() - last_gain).count();
    out.iterations = it;
    out.accepted_moves = accepted;
    out.attempted_moves = it;

    if (persistent_policy && cfg.phase_persist_lns_policy) {
        persistent_policy->op_w = w;
        persistent_policy->intensity_w = iw;
        persistent_policy->initialized = true;
        ++persistent_policy->calls;
    }

    static const array<const char*,MAX_OPS> op_names = {
        "random", "expensive_related", "shaw_related", "string_slack",
        "multiroute_block", "seam_scatter"
    };
    safe_log_line("[PhaseLNS-E3] role=", macro_role ? "macro" : "structure",
                  " profile=", profile_id,
                  " seed=", seed, " start=", seed_state.objective,
                  " end=", best.objective, " wall=", out.runtime_sec,
                  " attempts=", it, " accepted=", accepted,
                  " worse_accepted=", macro_worse_accepted,
                  " alternate=", (out.has_alternate_state ? out.alternate_state.objective : -1.0),
                  " alt_distance=", (out.has_alternate_state
                      ? phase_structural_distance(out.alternate_state, best, *ev.CG) : 0.0));
    for (int k = 0; k < operator_count; ++k) {
        const double avg_ms = attempts[k] ? time_ms[k] / (double)attempts[k] : 0.0;
        const double gps = time_ms[k] > 1e-9 ? 1000.0 * gain_sum[k] / time_ms[k] : 0.0;
        safe_log_line("[PhaseLNSOp-E25] role=", macro_role ? "macro" : "structure",
                      " op=", k, " name=", op_names[k],
                      " attempts=", attempts[k],
                      " feasible=", feasible[k],
                      " improvements=", improvements[k],
                      " gain=", gain_sum[k],
                      " time_ms=", time_ms[k],
                      " avg_ms=", avg_ms,
                      " gain_per_s=", gps,
                      " persisted_weight=", w[k]);
    }
    for (int z = 0; z < INTENSITIES; ++z) {
        const double gps = intensity_time_ms[z] > 1e-9
            ? 1000.0 * intensity_gain[z] / intensity_time_ms[z] : 0.0;
        safe_log_line("[PhaseLNSIntensity-E25] role=", macro_role ? "macro" : "structure",
                      " band=", z,
                      " attempts=", intensity_attempts[z],
                      " improvements=", intensity_improvements[z],
                      " gain=", intensity_gain[z],
                      " gain_per_s=", gps,
                      " persisted_weight=", iw[z]);
    }
    return out;
}

struct PhaseRegionPolicyState {
    array<double,3> w = {1.15, 1.00, 1.20}; // region, granular, interroute
    bool initialized = false;
    long long calls = 0;
};

static AlgoResult run_phase_region_specialist(
    const SolutionState &seed_state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    double budget_s,
    unsigned seed,
    PhaseRegionPolicyState *persistent_policy = nullptr
) {
    (void)seed;
    AlgoResult out;
    const auto t0 = Clock::now();
    SolutionState best = seed_state;
    recompute_state_metrics_and_loads(best, ev);

    PhaseRegionPolicyState local;
    PhaseRegionPolicyState &policy = persistent_policy ? *persistent_policy : local;
    if (!policy.initialized) {
        policy.w = {1.15, 1.00, 1.20};
        policy.initialized = true;
    }

    static const array<const char*,3> names = {"route_region","granular","interroute"};
    array<long long,3> calls = {0,0,0};
    array<long long,3> wins = {0,0,0};
    array<double,3> gains = {0,0,0};
    array<double,3> time_s = {0,0,0};
    int version = 0;
    array<int,3> last_tried_version = {-1,-1,-1};

    auto run_op = [&](int op, double cap_s) -> bool {
        if (cap_s <= 1e-4 || solver_should_stop()) return false;
        SolutionState cand = best;
        const double before = best.objective;
        const auto s0 = Clock::now();
        {
            ScopedWorkerDeadline cap(cap_s);
            if (op == 0) {
                if (cfg.use_route_region_lns) route_region_lns_descent(cand, ev, pm);
                else interroute_polish_solution(cand, ev, pm);
            } else if (op == 1) {
                if (cfg.use_granular_tabu) granular_tabu_repair(cand, ev, pm);
                else local_polish_solution(cand, ev, pm);
            } else {
                interroute_polish_solution(cand, ev, pm);
            }
        }
        const double sec = chrono::duration<double>(Clock::now() - s0).count();
        recompute_state_metrics_and_loads(cand, ev);
        ++calls[op]; time_s[op] += sec;
        last_tried_version[op] = version;
        if (solution_hard_feasible(cand, *ev.CG, pm) && cand.objective + 1e-9 < best.objective) {
            const double gain = best.objective - cand.objective;
            gains[op] += gain; ++wins[op];
            const double scale = max(1.0, meaningful_gain_threshold(before));
            const double reward = min(10.0,
                1.0 + min(5.0, gain / scale) + min(4.0, (gain / scale) / max(0.05, sec)));
            policy.w[op] = min(10.0, 0.78 * policy.w[op] + 0.22 * reward);
            best = std::move(cand);
            ++version;
            safe_log_line("[PhaseRegion-E10] op=", names[op],
                          " before=", before,
                          " after=", best.objective,
                          " gain=", gain,
                          " slice_s=", sec,
                          " weight=", policy.w[op],
                          " version=", version);
            return true;
        }
        const double miss_reward = min(0.30, 0.08 / max(0.05, sec));
        policy.w[op] = max(0.06, 0.90 * policy.w[op] + 0.10 * miss_reward);
        return false;
    };

    if (!cfg.phase_adaptive_region_policy) {
        run_op(0, budget_s * 0.42);
        run_op(1, budget_s * 0.30);
        run_op(2, budget_s * 0.28);
    } else {
        // Deterministic neighborhoods should not be fired repeatedly at the
        // exact same local optimum. Each operator runs once per solution
        // version; an improvement re-enables the others. This retains adaptive
        // ordering without the E3-prototype's dozens of duplicate no-op calls.
        int guard = 0;
        while (!solver_should_stop() && guard++ < 8) {
            const double used = chrono::duration<double>(Clock::now() - t0).count();
            const double rem = budget_s - used;
            if (rem <= 0.05) break;
            vector<int> eligible;
            for (int op = 0; op < 3; ++op)
                if (last_tried_version[op] < version) eligible.push_back(op);
            if (eligible.empty()) break;
            sort(eligible.begin(), eligible.end(), [&](int a, int b) {
                if (policy.w[a] != policy.w[b]) return policy.w[a] > policy.w[b];
                return a < b;
            });
            const int op = eligible.front();
            double eligible_w = 0.0;
            for (int x : eligible) eligible_w += max(0.08, policy.w[x]);
            const double share = max(0.16,
                max(0.08, policy.w[op]) / max(0.08, eligible_w));
            const double cap_s = min(rem,
                max(0.18, min(2.75, budget_s * min(0.55, share))));
            run_op(op, cap_s);
        }
    }

    ++policy.calls;
    out.best_state = best;
    out.runtime_sec = chrono::duration<double>(Clock::now() - t0).count();
    for (int k = 0; k < 3; ++k) {
        safe_log_line("[PhaseRegionPolicy-E10] op=", names[k],
                      " calls=", calls[k], " wins=", wins[k],
                      " gain=", gains[k],
                      " gain_per_s=", time_s[k] > 1e-9 ? gains[k] / time_s[k] : 0.0,
                      " persisted_weight=", policy.w[k]);
    }
    return out;
}


static AlgoResult run_phase_ownership_pipeline_e32(
    const SolutionState &seed_state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    double budget_s,
    unsigned seed,
    PhaseRegionPolicyState *persistent_policy,
    int n_customers
) {
    AlgoResult out;
    const auto t0 = Clock::now();
    SolutionState best = seed_state;
    recompute_state_metrics_and_loads(best, ev);
    if (budget_s <= 0.02 || solver_should_stop()) {
        out.best_state = best;
        return out;
    }

    const double region_plan = min(budget_s,
        max(0.12, budget_s * max(0.10, min(0.90, cfg.phase_ownership_region_fraction))));
    AlgoResult region = run_phase_region_specialist(
        best, ev, pm, region_plan, seed ^ 0xE320001u, persistent_policy);
    recompute_state_metrics_and_loads(region.best_state, ev);
    if (solution_hard_feasible(region.best_state, *ev.CG, pm) &&
        region.best_state.objective + 1e-9 < best.objective)
        best = region.best_state;

    safe_log_line("[PhaseOwnership-E33] stage=region start=", seed_state.objective,
                  " end=", best.objective,
                  " used_s=", chrono::duration<double>(Clock::now()-t0).count(),
                  " plan_s=", region_plan);

    double remaining = max(0.0, budget_s -
        chrono::duration<double>(Clock::now() - t0).count());

    // Fragment LNS is especially complementary after ownership correction on
    // large road instances. E33 only launches it when the remaining local slice
    // is long enough for this instance size; otherwise donate the fragment to
    // later stages instead of starting work that cannot cooperatively finish.
    const double fragment_safe_floor = max(
        cfg.phase_ownership_fragment_min_s,
        cfg.phase_ownership_fragment_floor_per_customer_s * max(1, n_customers));
    if (n_customers >= 220 && cfg.use_fragment_lns &&
        remaining >= fragment_safe_floor && !solver_should_stop()) {
        const double reserve_for_refine = max(
            cfg.phase_ownership_refine_min_s,
            cfg.phase_ownership_refine_floor_per_customer_s * max(1, n_customers));
        double frag_cap = min(remaining, max(fragment_safe_floor, 0.72 * remaining));
        if (remaining > reserve_for_refine + fragment_safe_floor)
            frag_cap = min(frag_cap, remaining - reserve_for_refine);
        SolutionState cand = best;
        const double before = cand.objective;
        const auto f0 = Clock::now();
        {
            ScopedWorkerDeadline cap(frag_cap);
            fragment_lns_search(cand, ev, pm);
        }
        recompute_state_metrics_and_loads(cand, ev);
        if (solution_hard_feasible(cand, *ev.CG, pm) &&
            cand.objective + 1e-9 < best.objective)
            best = std::move(cand);
        safe_log_line("[PhaseOwnership-E33] stage=fragment before=", before,
                      " after=", best.objective,
                      " gain=", max(0.0, before-best.objective),
                      " wall_s=", chrono::duration<double>(Clock::now()-f0).count(),
                      " cap_s=", frag_cap,
                      " safe_floor_s=", fragment_safe_floor);
    } else if (n_customers >= 220 && cfg.use_fragment_lns && remaining > 0.02) {
        safe_log_line("[PhaseOwnership-E33] skip_fragment remaining_s=", remaining,
                      " safe_floor_s=", fragment_safe_floor);
    }

    remaining = max(0.0, budget_s -
        chrono::duration<double>(Clock::now() - t0).count());
    const double refine_safe_floor = max(
        cfg.phase_ownership_refine_min_s,
        cfg.phase_ownership_refine_floor_per_customer_s * max(1, n_customers));
    if (remaining >= refine_safe_floor && !solver_should_stop()) {
        SolutionState cand = best;
        const double before = cand.objective;
        const auto r0 = Clock::now();
        {
            ScopedWorkerDeadline cap(remaining);
            final_refinement_pass(cand, ev, pm);
        }
        recompute_state_metrics_and_loads(cand, ev);
        if (solution_hard_feasible(cand, *ev.CG, pm) &&
            cand.objective + 1e-9 < best.objective)
            best = std::move(cand);
        safe_log_line("[PhaseOwnership-E33] stage=refine before=", before,
                      " after=", best.objective,
                      " gain=", max(0.0, before-best.objective),
                      " wall_s=", chrono::duration<double>(Clock::now()-r0).count(),
                      " cap_s=", remaining,
                      " safe_floor_s=", refine_safe_floor);
    } else if (remaining > 0.02) {
        safe_log_line("[PhaseOwnership-E33] skip_refine remaining_s=", remaining,
                      " safe_floor_s=", refine_safe_floor);
    }

    out.best_state = best;
    out.runtime_sec = chrono::duration<double>(Clock::now() - t0).count();
    out.iterations = region.iterations;
    out.accepted_moves = region.accepted_moves;
    out.attempted_moves = region.attempted_moves;
    out.last_improvement_age_s = region.last_improvement_age_s;
    safe_log_line("[PhaseOwnership-E33] END start=", seed_state.objective,
                  " end=", best.objective,
                  " gain=", max(0.0, seed_state.objective-best.objective),
                  " wall_s=", out.runtime_sec,
                  " budget_s=", budget_s);
    return out;
}

static AlgoResult run_phase_breeder(
    const vector<SolutionState> &archive,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    double budget_s,
    unsigned seed
) {
    AlgoResult out;
    const auto t0 = Clock::now();
    if (archive.empty()) return out;
    const Compressed &CG = *ev.CG;
    auto parents = phase_select_parent_pair(archive, CG);
    if (parents.first < 0 || parents.second < 0) {
        out.best_state = archive.front();
        return out;
    }
    const SolutionState &pa = archive[parents.first];
    const SolutionState &pb = archive[parents.second];
    const double pr_budget = max(0.02, budget_s * (1.0 - cfg.phase_breeder_fraction));
    SolutionState child;
    { ScopedWorkerDeadline cap(pr_budget); child = path_relink_between_strong(pa, pb, ev, pm); }
    recompute_state_metrics_and_loads(child, ev);
    SolutionState best = solution_hard_feasible(child, CG, pm) ? child : pa;
    const double used = chrono::duration<double>(Clock::now() - t0).count();
    const double educate_budget = max(0.02, budget_s - used);
    if (educate_budget > 0.02 && !solver_should_stop()) {
        best = memetic_educate_child_balanced(
            best, ev, pm, educate_budget,
            seed ^ 0xE71ECAFEu
        );
        recompute_state_metrics_and_loads(best, ev);
        if (!solution_hard_feasible(best, CG, pm)) best = pa;
    }
    out.best_state = best;
    out.runtime_sec = chrono::duration<double>(Clock::now() - t0).count();
    safe_log_line("[PhaseBreeder-E32] parents=", parents.first, ",", parents.second,
                  " parentA=", pa.objective, " parentB=", pb.objective,
                  " distance=", phase_structural_distance(pa,pb,CG),
                  " child=", best.objective, " wall=", out.runtime_sec);
    return out;
}

static AlgoResult run_phase_specialized_engine_e23(
    const SolutionState &seed_state,
    const SolutionState *entry_probe_seed_override,
    const SolutionState *structure_seed_override,
    Compressed &CG,
    PairwiseManager &pm,
    ObjectiveEvaluator &ev,
    int depot_idx,
    const vector<int> &collections,
    vector<ConvergenceLogRow> *shared_conv_log,
    mutex *conv_mtx
) {
    AlgoResult out;
    const auto engine_t0 = Clock::now();
    const int n_customers = (int)collections.size();
    const int instances = max(1, cfg.sa_instances);
    const int hw_raw = (int)thread::hardware_concurrency();
    const int hw = hw_raw > 0 ? hw_raw : instances;

    // E18 deadline engineering: large road operators have cooperative polling
    // granularity and route-evaluation tails that can overrun a 0.1 s guard.
    // Reserve enough evidence margin so the best late candidate is admissible.
    if (cfg.hard_time_limit_s > 0.0) {
        if (n_customers >= 400)
            cfg.phase_tail_deadline_guard_s = max(cfg.phase_tail_deadline_guard_s, 0.65);
        else if (n_customers >= 250)
            cfg.phase_tail_deadline_guard_s = max(cfg.phase_tail_deadline_guard_s, 0.35);
        else
            cfg.phase_tail_deadline_guard_s = max(cfg.phase_tail_deadline_guard_s, 0.15);
    }

    if (cfg.hard_time_limit_s > 0.0) {
        double target_tail = cfg.final_intensification_reserve_s;
        if (n_customers >= 400)
            target_tail = max(target_tail, min(24.0, max(14.0, 0.060 * cfg.hard_time_limit_s)));
        else if (n_customers >= 250)
            target_tail = max(target_tail, min(15.0, max(9.0, 0.060 * cfg.hard_time_limit_s)));
        else if (n_customers >= 100)
            target_tail = max(target_tail, min(9.0, max(6.0, 0.050 * cfg.hard_time_limit_s)));
        cfg.final_intensification_reserve_s = min(target_tail, 0.20 * cfg.hard_time_limit_s);
    }

    vector<SolutionState> archive;
    phase_archive_rebuild(archive, {seed_state}, ev, pm);
    if (archive.empty()) {
        out.best_state = seed_state;
        return out;
    }

    vector<PhaseLNSPolicyState> lane_lns_policy(instances);
    PhaseRegionPolicyState region_policy;
    vector<double> role_credit(instances, 0.80);
    vector<int> idle_epochs(instances, 0);
    static const array<double,6> role_prior = {1.28, 1.02, 1.12, 0.54, 1.35, 1.08};
    for (int i = 0; i < instances; ++i)
        role_credit[i] = i < 6 ? role_prior[i] : 0.80;

    safe_log_line("[PhaseEngine-E32] START customers=", n_customers,
                  " logical_workers=", instances,
                  " hardware_concurrency=", hw,
                  " hard=", cfg.hard_time_limit_s,
                  " structure_fraction=", cfg.phase_structure_fraction,
                  " epoch_s=", cfg.phase_epoch_s,
                  " archive_cap=", cfg.phase_archive_size,
                  " tail_reserve=", cfg.final_intensification_reserve_s,
                  " start=", archive.front().objective);

    // -------- Phase 0: readiness-gated compact entry --------
    // A good compact instance does not need six expensive roles at t=0. Race
    // one cold exact lane against one FAST structure lane, keep both basins,
    // and extend only the family that is both best and still improving.
    if (cfg.phase_readiness_gate && cfg.hard_time_limit_s > 0.0 &&
        n_customers < cfg.phase_structure_min_customers && !solver_should_stop()) {
        const double pre_tail_end = cfg.hard_time_limit_s - cfg.final_intensification_reserve_s;
        const double requested = max(cfg.phase_entry_probe_min_s,
            min(cfg.phase_entry_probe_max_s,
                cfg.hard_time_limit_s * cfg.phase_entry_probe_fraction));
        const double granted = min(requested,
            max(0.0, pre_tail_end - solver_elapsed_seconds() - 0.50));
        if (granted >= 0.10) {
            const int probe_workers = min({instances, cfg.phase_entry_probe_workers,
                cfg.phase_respect_hardware_concurrency ? max(1, hw) : instances, 2});
            vector<AlgoResult> pr(max(1, probe_workers));
            PhaseLNSPolicyState compact_lns_policy;
            vector<thread> th;
            th.reserve(probe_workers);
            SolutionState entry_seed = archive.front();
            if (entry_probe_seed_override != nullptr) {
                SolutionState alt = *entry_probe_seed_override;
                recompute_state_metrics_and_loads(alt, ev);
                if (solution_hard_feasible(alt, CG, pm)) entry_seed = std::move(alt);
            }
            safe_log_line("[PhaseEntry-E25] START customers=", n_customers,
                          " workers=", probe_workers,
                          " budget_s=", granted,
                          " published_obj=", archive.front().objective,
                          " probe_seed_obj=", entry_seed.objective);
            if (probe_workers >= 1) {
                const unsigned ss = cfg.base_seed + 0xE110001u;
                th.emplace_back([&, ss, entry_seed]() mutable {
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    pr[0] = sa_worker(CG, pm, ev, depot_idx, collections, ss,
                        granted, cfg.use_cross2, &entry_seed,
                        shared_conv_log, conv_mtx, 2, 0);
                    tls_defer_global_publish = old_defer;
                });
            }
            if (probe_workers >= 2) {
                const unsigned ss = cfg.base_seed + 0xE110002u;
                th.emplace_back([&, ss, entry_seed]() mutable {
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    pr[1] = run_phase_adaptive_lns_worker(entry_seed, ev, pm,
                        granted, ss, false, shared_conv_log, conv_mtx,
                        0, &compact_lns_policy);
                    tls_defer_global_publish = old_defer;
                });
            }
            for (auto &t : th) if (t.joinable()) t.join();

            vector<SolutionState> cand;
            cand.push_back(entry_seed);
            for (int i = 0; i < probe_workers; ++i) {
                recompute_state_metrics_and_loads(pr[i].best_state, ev);
                if (solution_hard_feasible(pr[i].best_state, CG, pm))
                    cand.push_back(pr[i].best_state);
            }
            phase_archive_rebuild(archive, std::move(cand), ev, pm);
            if (!archive.empty()) update_global_best_checked(archive.front(), CG, pm);

            int winner = 0;
            if (probe_workers >= 2 &&
                pr[1].best_state.objective + 1e-9 < pr[0].best_state.objective)
                winner = 1;
            const double winner_age = pr[winner].last_improvement_age_s;
            const double hot_cut = max(0.08, granted * cfg.phase_entry_hot_age_fraction);
            const bool still_hot = isfinite(winner_age) && winner_age <= hot_cut;
            safe_log_line("[PhaseEntry-E25] END best=", archive.front().objective,
                          " cold=", pr[0].best_state.objective,
                          " lns=", (probe_workers >= 2 ? pr[1].best_state.objective : INF_D),
                          " winner=", (winner == 0 ? "cold_exact" : "fast_lns"),
                          " winner_age_s=", winner_age,
                          " hot_cut_s=", hot_cut,
                          " still_hot=", still_hot ? 1 : 0);

            if (still_hot && cfg.phase_entry_extension_max_s > 0.0 && !solver_should_stop()) {
                const double ext_plan = min(cfg.phase_entry_extension_max_s,
                    max(0.10, granted * cfg.phase_entry_extension_fraction));
                const double ext_budget = min(ext_plan,
                    max(0.0, pre_tail_end - solver_elapsed_seconds() - 0.35));
                if (ext_budget >= 0.10) {
                    const SolutionState ext_seed = archive.front();
                    AlgoResult ext;
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    if (winner == 0) {
                        ext = sa_worker(CG, pm, ev, depot_idx, collections,
                            cfg.base_seed + 0xE110101u, ext_budget,
                            cfg.use_cross2, &ext_seed, shared_conv_log, conv_mtx,
                            2, 0);
                    } else {
                        ext = run_phase_adaptive_lns_worker(ext_seed, ev, pm,
                            ext_budget, cfg.base_seed + 0xE110102u, false,
                            shared_conv_log, conv_mtx, 0, &compact_lns_policy);
                    }
                    tls_defer_global_publish = old_defer;
                    vector<SolutionState> ec{ext.best_state};
                    phase_archive_rebuild(archive, std::move(ec), ev, pm);
                    if (!archive.empty()) update_global_best_checked(archive.front(), CG, pm);
                    safe_log_line("[PhaseEntry-E25] EXTEND family=",
                                  (winner == 0 ? "cold_exact" : "fast_lns"),
                                  " budget_s=", ext_budget,
                                  " result=", ext.best_state.objective,
                                  " age_s=", ext.last_improvement_age_s,
                                  " archive_best=", archive.front().objective);
                }
            }
            phase_archive_log(archive, CG, "compact_entry_e11", -2);
        }
    }

    // -------- Phase A: multi-basin structure acquisition --------
    if (cfg.hard_time_limit_s > 0.0 &&
        n_customers >= cfg.phase_structure_min_customers &&
        cfg.phase_structure_fraction > 0.0) {
        const double requested = max(cfg.phase_structure_min_time_s,
            min(cfg.phase_structure_max_time_s,
                cfg.hard_time_limit_s * cfg.phase_structure_fraction));
        const double pre_tail_end = cfg.hard_time_limit_s - cfg.final_intensification_reserve_s;
        const double leave_epoch = min(cfg.phase_epoch_s, max(1.0, pre_tail_end * 0.10));
        const double granted = min(requested,
            max(0.0, pre_tail_end - solver_elapsed_seconds() - leave_epoch));
        if (granted >= 0.25) {
            int desired_sw = 2;
            if (n_customers >= 400) desired_sw = 4;
            else if (n_customers >= 250) desired_sw = 3;
            else if (n_customers >= cfg.phase_structure_parallel_min_customers) desired_sw = 3;
            const int compute_cap = cfg.phase_respect_hardware_concurrency
                ? max(cfg.phase_min_active_workers, min(instances, hw))
                : instances;
            const int sw = min(instances, min(desired_sw, compute_cap));
            vector<AlgoResult> rr(sw);
            vector<PhaseLNSPolicyState> prefix_policy(sw);
            vector<thread> th;
            th.reserve(sw);
            const bool have_structural_construct_seed =
                structure_seed_override != nullptr &&
                !structure_seed_override->routes.empty() &&
                solution_hard_feasible(*structure_seed_override, CG, pm);
            const bool have_raw_structure_seed =
                entry_probe_seed_override != nullptr &&
                !entry_probe_seed_override->routes.empty() &&
                solution_hard_feasible(*entry_probe_seed_override, CG, pm);
            const SolutionState *explore_seed = have_structural_construct_seed
                ? structure_seed_override
                : (have_raw_structure_seed ? entry_probe_seed_override : nullptr);
            safe_log_line("[PhaseStructure-E32] START workers=", sw,
                          " desired=", desired_sw,
                          " hardware_concurrency=", hw,
                          " budget_s=", granted,
                          " incumbent_start=", archive.front().objective,
                          " explore_seed=", (explore_seed ? explore_seed->objective : -1.0),
                          " explore_kind=", (have_structural_construct_seed ? "truncated_savings" :
                                             (have_raw_structure_seed ? "raw_round_robin" : "none")),
                          " policy=construction_ensemble");
            vector<double> structure_start_obj(sw, archive.front().objective);
            for (int i = 0; i < sw; ++i) {
                // E20: keep at least half the structural lanes on the rough/high-entropy
                // construction when available.  The other half refine the strong anytime
                // incumbent.  Objective quality is therefore not confused with launch
                // geometry quality.
                // E22: when a deliberate coarse structural constructor exists, all
                // structural profiles receive it.  The strong quality incumbent is
                // preserved separately in the archive and does not consume a scarce
                // structure-worker slot.
                const bool use_explore = explore_seed != nullptr;
                const SolutionState start_state = use_explore ? *explore_seed : archive.front();
                structure_start_obj[i] = start_state.objective;
                const unsigned ss = cfg.base_seed + 0x510000u + (unsigned)i * 10007u;
                safe_log_line("[PhaseStructure-E32] lane=", i,
                              " source=", (use_explore ? "coarse_exploration" : "competitive"),
                              " profile=", i, " start=", start_state.objective);
                th.emplace_back([&, i, start_state, ss]() mutable {
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    rr[i] = run_phase_adaptive_lns_worker(
                        start_state, ev, pm, granted, ss, false,
                        shared_conv_log, conv_mtx, i, &prefix_policy[i]);
                    tls_defer_global_publish = old_defer;
                });
            }
            for (auto &t : th) if (t.joinable()) t.join();

            // Preserve what the prefix learned.  Merge the independent policy
            // posteriors weighted by actual structural gain, then hand that
            // posterior to the persistent structure lane instead of relearning.
            if (instances > 2 && !prefix_policy.empty()) {
                PhaseLNSPolicyState merged;
                merged.op_w.fill(0.0);
                merged.intensity_w.fill(0.0);
                double denom = 0.0;
                for (int i = 0; i < sw; ++i) {
                    const double gain = max(1.0,
                        structure_start_obj[i] - rr[i].best_state.objective);
                    denom += gain;
                    for (int k = 0; k < 6; ++k) merged.op_w[k] += gain * prefix_policy[i].op_w[k];
                    for (int k = 0; k < 3; ++k) merged.intensity_w[k] += gain * prefix_policy[i].intensity_w[k];
                }
                if (denom > 0.0) {
                    for (double &x : merged.op_w) x /= denom;
                    for (double &x : merged.intensity_w) x /= denom;
                    merged.initialized = true;
                    merged.calls = 1;
                    lane_lns_policy[2] = merged;
                }
            }

            // E25: keep the endpoint<->policy relationship intact through the
            // readiness decision.  E23 rebuilt the archive first and then launched
            // generic extensions from archive[0]/archive[1] with a merged posterior.
            // That destroyed causal information: the worker that discovered the best
            // basin had already learned which ruin sizes/operators were productive on
            // that basin.  We retain all prefix endpoints and their own posteriors.
            vector<int> structure_rank(sw);
            iota(structure_rank.begin(), structure_rank.end(), 0);
            sort(structure_rank.begin(), structure_rank.end(), [&](int a, int b) {
                return rr[a].best_state.objective < rr[b].best_state.objective;
            });

            vector<SolutionState> cand;
            cand.reserve(sw + archive.size());
            // Preserve the validated anytime incumbent independently of the
            // exploratory structure trajectories.  Copy (do not move) the endpoints:
            // readiness continuation below may need the exact winning state.
            for (const auto &a : archive) cand.push_back(a);
            for (const auto &r : rr) cand.push_back(r.best_state);
            phase_archive_rebuild(archive, std::move(cand), ev, pm);
            if (!archive.empty()) update_global_best_checked(archive.front(), CG, pm);
            phase_archive_log(archive, CG, "structure_handoff_e25", -1);

            // E25 readiness gate: resume the actual productive trajectories rather
            // than starting a generic mini-search from the objective-sorted archive.
            // Lane 0 is always the winning endpoint + its own learned posterior; lane
            // 1 (when available) is the best distinct prefix endpoint + its posterior.
            if (cfg.phase_readiness_gate && cfg.phase_structure_extension_max_s > 0.0 &&
                !solver_should_stop() && !archive.empty() && !structure_rank.empty()) {
                const int best_worker = structure_rank.front();
                const double best_age = rr[best_worker].last_improvement_age_s;
                const double hot_cut = max(0.20,
                    granted * cfg.phase_structure_hot_age_fraction);
                const bool still_hot = isfinite(best_age) && best_age <= hot_cut;
                if (still_hot) {
                    const double ext_plan = min(cfg.phase_structure_extension_max_s,
                        max(0.25, granted * cfg.phase_structure_extension_fraction));
                    const double ext_budget = min(ext_plan,
                        max(0.0, pre_tail_end - solver_elapsed_seconds() - leave_epoch));
                    if (ext_budget >= 0.20) {
                        vector<int> ext_src;
                        ext_src.push_back(best_worker);
                        if (sw > 1) {
                            // Prefer a genuinely different second structural basin.  If
                            // all endpoints are clones, fall back to the runner-up so we
                            // still obtain an independent continuation trajectory.
                            int second = -1;
                            for (size_t r = 1; r < structure_rank.size(); ++r) {
                                const int j = structure_rank[r];
                                if (phase_structural_distance(rr[best_worker].best_state,
                                                              rr[j].best_state, CG) >=
                                    cfg.phase_archive_clone_distance) {
                                    second = j;
                                    break;
                                }
                            }
                            if (second < 0) second = structure_rank[1];
                            ext_src.push_back(second);
                        }
                        const int ew = (int)ext_src.size();
                        vector<AlgoResult> er(ew);
                        vector<PhaseLNSPolicyState> ep(ew);
                        vector<thread> eth;
                        eth.reserve(ew);
                        for (int i = 0; i < ew; ++i) {
                            const int src = ext_src[i];
                            const SolutionState ext_seed = rr[src].best_state;
                            ep[i] = prefix_policy[src];
                            // Use a continuation-specific RNG stream while preserving
                            // the learned operator posterior.  Reusing the exact original
                            // seed would replay early random choices from a new state.
                            const unsigned ss = cfg.base_seed + 0xE25E000u +
                                (unsigned)src * 10007u + (unsigned)i * 7919u;
                            safe_log_line("[PhaseStructure-E32] CONTINUE lane=", i,
                                          " src_profile=", src,
                                          " start=", ext_seed.objective,
                                          " policy_calls=", ep[i].calls,
                                          " budget_s=", ext_budget);
                            eth.emplace_back([&, i, ext_seed, ss]() mutable {
                                const bool old_defer = tls_defer_global_publish;
                                tls_defer_global_publish = true;
                                er[i] = run_phase_adaptive_lns_worker(ext_seed, ev, pm,
                                    ext_budget, ss, false, shared_conv_log, conv_mtx,
                                    i, &ep[i]);
                                tls_defer_global_publish = old_defer;
                            });
                        }
                        for (auto &t : eth) if (t.joinable()) t.join();
                        vector<SolutionState> ec;
                        ec.reserve(er.size());
                        int best_ext = 0;
                        for (int i = 0; i < ew; ++i) {
                            ec.push_back(er[i].best_state);
                            if (er[i].best_state.objective < er[best_ext].best_state.objective)
                                best_ext = i;
                        }
                        phase_archive_rebuild(archive, std::move(ec), ev, pm);
                        if (!archive.empty()) update_global_best_checked(archive.front(), CG, pm);
                        if (instances > 2 && !ep.empty()) lane_lns_policy[2] = ep[best_ext];
                        safe_log_line("[PhaseStructure-E32] READINESS_EXTEND budget_s=", ext_budget,
                                      " workers=", ew,
                                      " winner_profile=", best_worker,
                                      " previous_best_age_s=", best_age,
                                      " hot_cut_s=", hot_cut,
                                      " archive_best=", archive.front().objective);
                        phase_archive_log(archive, CG, "structure_readiness_extension_e25", -1);
                    }
                } else {
                    safe_log_line("[PhaseStructure-E32] READY_FOR_INTENSIFICATION best_profile=",
                                  best_worker,
                                  " best_age_s=", best_age,
                                  " hot_cut_s=", hot_cut,
                                  " best=", archive.front().objective);
                }
            }
        }
    }

    // -------- Phase B: persistent heterogeneous, hardware-aware epochs --------
    vector<SolutionState> worker_states(instances, archive.front());
    vector<int> stale(instances, 0);
    for (int i = 0; i < instances; ++i) {
        if (archive.size() > 1) worker_states[i] = archive[i % archive.size()];
    }
    int epoch = 0;
    bool final_mode = solver_phase_transition_requested.load(memory_order_relaxed);
    long long sum_iter = 0, sum_acc = 0, sum_att = 0;

    while (!solver_should_stop()) {
        const double nominal_epoch_s = (n_customers < cfg.phase_structure_min_customers)
            ? min(cfg.phase_epoch_s, (epoch == 0
                ? cfg.phase_compact_first_epoch_s : cfg.phase_compact_epoch_s))
            : cfg.phase_epoch_s;
        const double pre_tail_end = cfg.hard_time_limit_s > 0.0
            ? cfg.hard_time_limit_s - cfg.final_intensification_reserve_s
            : solver_elapsed_seconds() + nominal_epoch_s;
        const double remaining = pre_tail_end - solver_elapsed_seconds();
        if (remaining <= 0.05) break;
        // E10: a sub-second heterogeneous launch is mostly startup/cache churn and
        // steals time from deterministic final intensification. Donate that
        // fragment to the tail instead.
        if (cfg.hard_time_limit_s > 0.0 && remaining < cfg.phase_min_epoch_launch_s) {
            const double tail_available = max(0.0,
                cfg.hard_time_limit_s - solver_elapsed_seconds());
            cfg.final_intensification_reserve_s = max(
                cfg.final_intensification_reserve_s, tail_available);
            safe_log_line("[PhaseEngine-E32] donate_partial_epoch_to_tail remaining_s=", remaining,
                          " threshold_s=", cfg.phase_min_epoch_launch_s,
                          " donated_tail_s=", tail_available,
                          " best=", archive.front().objective);
            break;
        }
        const double eb = min(nominal_epoch_s, remaining);
        if (eb <= 0.05) break;

        double wave_b_planned = 0.0;
        double wave_a_budget = eb;
        if (cfg.phase_two_wave_epochs && eb >= 2.0 * cfg.phase_handoff_min_s) {
            wave_b_planned = max(cfg.phase_handoff_min_s, eb * cfg.phase_handoff_fraction);
            wave_b_planned = min(wave_b_planned, 0.48 * eb);
            wave_a_budget = max(cfg.phase_handoff_min_s, eb - wave_b_planned);
            wave_b_planned = max(0.0, eb - wave_a_budget);
        }

        vector<SolutionState> archive_snapshot = archive;
        vector<AlgoResult> rr(instances);
        vector<double> lane_start_obj(instances, INF_D);
        vector<char> active(instances, 0);
        vector<int> active_lanes;

        int active_cap = instances;
        if (cfg.phase_respect_hardware_concurrency) {
            active_cap = min(instances,
                max(1, min(instances, max(cfg.phase_min_active_workers, hw))));
        }
        // E10: once the first large-instance epoch has identified productive roles,
        // do not saturate memory bandwidth merely because another CPU is visible.
        // The idle-credit mechanism can still rotate excluded roles back in.
        if (cfg.phase_dynamic_active_cap && n_customers >= 250 && epoch >= 1) {
            active_cap = min(active_cap, max(cfg.phase_min_active_workers,
                cfg.phase_late_discovery_max_workers));
        }

        // Wave A is discovery.  When a second wave is available, reserve the
        // breeder for the *fresh* archive rather than letting it mate stale
        // parents for the entire epoch. Cold M1-style exact search stays the
        // anchor because the 100C traces show it is exceptionally productive
        // once a competitive basin exists.
        const int anchor_lane = (n_customers >= 220 && instances > 4) ? 4 : 0;
        if (instances > 0) { active[anchor_lane] = 1; active_lanes.push_back(anchor_lane); }
        struct LaneRank { double score; int lane; };
        vector<LaneRank> ranked;
        for (int lane = 0; lane < instances; ++lane) {
            if (lane == anchor_lane) continue;
            if (wave_b_planned > 0.05 && lane == 5) continue;
            double score = role_credit[lane] +
                cfg.phase_role_idle_bonus * (double)idle_epochs[lane];
            if (lane == 5 && archive_snapshot.size() < 2) score -= 1000.0;
            if (final_mode) {
                if (lane == 4) score += 0.40;
                if (lane == 2) score += 0.24;
                if (lane == 1) score += 0.16;
                if (lane == 3) score -= 0.15;
            } else {
                if (lane == 2 && n_customers >= 300 && epoch <= 1) score += 0.28;
                if (lane == 4) score += 0.15;
                if (lane == 1) score += 0.08;
            }
            ranked.push_back({score, lane});
        }
        sort(ranked.begin(), ranked.end(), [](const LaneRank &a, const LaneRank &b) {
            if (a.score != b.score) return a.score > b.score;
            return a.lane < b.lane;
        });
        for (auto x : ranked) {
            if ((int)active_lanes.size() >= active_cap) break;
            if (x.score < -100.0) continue;
            active[x.lane] = 1;
            active_lanes.push_back(x.lane);
        }

        string active_text;
        for (int lane : active_lanes) {
            if (!active_text.empty()) active_text += ",";
            active_text += to_string(lane);
        }
        safe_log_line("[PhaseSchedule-E10] epoch=", epoch,
                      " wave=A active=", active_text,
                      " active_cap=", active_cap,
                      " logical=", instances,
                      " hw=", hw,
                      " archive_best=", archive.front().objective,
                      " final_mode=", (final_mode ? 1 : 0));
        safe_log_line("[PhaseEpoch-E10] START epoch=", epoch,
                      " budget_s=", eb,
                      " wave_a_s=", wave_a_budget,
                      " wave_b_planned_s=", wave_b_planned,
                      " archive_best=", archive.front().objective,
                      " archive_size=", archive.size(),
                      " final_mode=", (final_mode ? 1 : 0),
                      " transition=", solver_phase_transition_requested.load());

        vector<thread> th;
        th.reserve(active_lanes.size());
        for (int lane : active_lanes) {
            SolutionState start_state = worker_states[lane];
            if (lane == 4 && n_customers >= cfg.phase_ownership_min_customers && cfg.phase_ownership_pipeline &&
                !archive_snapshot.empty()) {
                // Role semantics: lane 4 owns current-basin correction, while
                // lanes 2/3 own structural diversity.  Do not spend this core
                // repairing archive slot 4 merely because it is diverse.
                start_state = archive_snapshot.front();
                safe_log_line("[PhaseOwnership-E33] epoch=", epoch,
                              " start_from=archive_best objective=", start_state.objective);
            }
            if (lane != 0 && lane != 4 && !archive_snapshot.empty()) {
                const double archive_best = archive_snapshot.front().objective;
                const double worker_gap = (start_state.objective - archive_best) /
                    max(1.0, fabs(archive_best));
                const double lane_gap_cap = (lane == 3)
                    ? max(0.025, cfg.phase_parent_quality_band)
                    : cfg.phase_archive_max_quality_gap;
                const bool stale_migrate = stale[lane] >= cfg.phase_worker_stale_epochs;
                const bool quality_migrate = worker_gap > lane_gap_cap + 1e-12;
                if (stale_migrate || quality_migrate) {
                    if (lane == 4) {
                        start_state = archive_snapshot.front();
                    } else {
                        int pi = phase_pick_diverse_archive_index(
                            archive_snapshot, start_state, CG, lane_gap_cap);
                        if (pi >= 0) start_state = archive_snapshot[pi];
                    }
                    safe_log_line("[PhaseMigration-E10] epoch=", epoch,
                                  " lane=", lane,
                                  " stale=", stale[lane],
                                  " worker_gap=", worker_gap,
                                  " cap=", lane_gap_cap,
                                  " reason=", quality_migrate ? "quality" : "stale",
                                  " migrated_obj=", start_state.objective);
                }
            }
            lane_start_obj[lane] = start_state.objective;
            const unsigned ss = cfg.base_seed + 0xE500000u +
                (unsigned)epoch * 1000003u + (unsigned)lane * 10007u;
            th.emplace_back([&, lane, start_state, ss]() mutable {
                const bool old_defer = tls_defer_global_publish;
                tls_defer_global_publish = true;
                if (!final_mode) {
                    if (lane == 0) {
                        rr[lane] = sa_worker(CG, pm, ev, depot_idx, collections, ss,
                            wave_a_budget, cfg.use_cross2, &start_state,
                            shared_conv_log, conv_mtx, 2, 0);
                    } else if (lane == 1) {
                        rr[lane] = sa_worker(CG, pm, ev, depot_idx, collections, ss,
                            wave_a_budget, cfg.use_cross2, &start_state,
                            shared_conv_log, conv_mtx, 3, 1);
                    } else if (lane == 2) {
                        rr[lane] = run_phase_adaptive_lns_worker(start_state, ev, pm,
                            wave_a_budget, ss, false, shared_conv_log, conv_mtx,
                            (epoch + 1) % 4, &lane_lns_policy[lane]);
                    } else if (lane == 3) {
                        rr[lane] = run_phase_adaptive_lns_worker(start_state, ev, pm,
                            wave_a_budget, ss, true, shared_conv_log, conv_mtx,
                            3, &lane_lns_policy[lane]);
                    } else if (lane == 4) {
                        if (cfg.phase_ownership_pipeline && n_customers >= cfg.phase_ownership_min_customers)
                            rr[lane] = run_phase_ownership_pipeline_e32(start_state, ev, pm,
                                wave_a_budget, ss, &region_policy, n_customers);
                        else
                            rr[lane] = run_phase_region_specialist(start_state, ev, pm,
                                wave_a_budget, ss, &region_policy);
                    } else if (lane == 5 && archive_snapshot.size() >= 2) {
                        rr[lane] = run_phase_breeder(archive_snapshot, ev, pm,
                            wave_a_budget, ss);
                    } else {
                        rr[lane] = sa_worker(CG, pm, ev, depot_idx, collections, ss,
                            wave_a_budget, cfg.use_cross2, &start_state,
                            shared_conv_log, conv_mtx, max(0, instances-1), 2);
                    }
                } else {
                    // Final-mode Wave A becomes almost purely exact basin
                    // exploitation.  Macro exploration is no longer allowed to
                    // consume a full epoch after the anytime governor asks for
                    // intensification.
                    if (lane == 0 || lane == 4) {
                        rr[lane] = sa_worker(CG, pm, ev, depot_idx, collections, ss,
                            wave_a_budget, cfg.use_cross2, &start_state,
                            shared_conv_log, conv_mtx, lane == 0 ? 2 : 3, 0);
                    } else if (lane == 1) {
                        rr[lane] = sa_worker(CG, pm, ev, depot_idx, collections, ss,
                            wave_a_budget, cfg.use_cross2, &start_state,
                            shared_conv_log, conv_mtx, 3, 1);
                    } else if (lane == 2) {
                        rr[lane] = run_phase_region_specialist(start_state, ev, pm,
                            wave_a_budget, ss, &region_policy);
                    } else if (lane == 3) {
                        rr[lane] = run_phase_region_specialist(start_state, ev, pm,
                            wave_a_budget, ss, nullptr);
                    } else if (lane == 5 && archive_snapshot.size() >= 2) {
                        rr[lane] = run_phase_breeder(archive_snapshot, ev, pm,
                            wave_a_budget, ss);
                    } else {
                        rr[lane] = run_phase_region_specialist(start_state, ev, pm,
                            wave_a_budget, ss, nullptr);
                    }
                }
                tls_defer_global_publish = old_defer;
            });
        }
        for (auto &t : th) if (t.joinable()) t.join();

        const double before_wave_a = archive.front().objective;
        int wave_a_best_lane = -1;
        double wave_a_best_lane_obj = before_wave_a;
        vector<SolutionState> cand;
        cand.reserve(active_lanes.size() * 2 + 4);
        for (int lane = 0; lane < instances; ++lane) {
            if (!active[lane]) {
                ++idle_epochs[lane];
                continue;
            }
            idle_epochs[lane] = 0;
            recompute_state_metrics_and_loads(rr[lane].best_state, ev);
            if (solution_hard_feasible(rr[lane].best_state, CG, pm)) {
                if (rr[lane].best_state.objective + 1e-9 < wave_a_best_lane_obj) {
                    wave_a_best_lane_obj = rr[lane].best_state.objective;
                    wave_a_best_lane = lane;
                }
                const double before = lane_start_obj[lane];
                if (lane == 3 && rr[lane].has_alternate_state &&
                    solution_hard_feasible(rr[lane].alternate_state, CG, pm)) {
                    worker_states[lane] = rr[lane].alternate_state;
                    cand.push_back(rr[lane].alternate_state);
                } else {
                    worker_states[lane] = rr[lane].best_state;
                }
                if (rr[lane].best_state.objective + 1e-9 < before) stale[lane] = 0;
                else ++stale[lane];
                cand.push_back(rr[lane].best_state);

                const double gain = max(0.0, before - rr[lane].best_state.objective);
                const double norm_gain = gain /
                    max(1.0, meaningful_gain_threshold(max(1.0, before)));
                double novelty = 0.0;
                if (!archive_snapshot.empty()) {
                    novelty = 1.0;
                    for (const auto &a : archive_snapshot)
                        novelty = min(novelty,
                            phase_structural_distance(rr[lane].best_state, a, CG));
                }
                const double gap = archive_snapshot.empty() ? 0.0 :
                    (rr[lane].best_state.objective - archive_snapshot.front().objective) /
                    max(1.0, fabs(archive_snapshot.front().objective));
                const double novelty_credit = gap <= cfg.phase_archive_max_quality_gap + 1e-12
                    ? min(1.0, novelty / 0.20) : 0.0;
                const double throughput = min(4.0,
                    norm_gain / max(0.20, rr[lane].runtime_sec));
                const double observed = 0.32 + throughput + 0.38 * novelty_credit;
                const double decay = cfg.phase_role_credit_decay;
                role_credit[lane] = decay * role_credit[lane] +
                    (1.0 - decay) * observed;
                safe_log_line("[PhaseRoleCredit-E32] epoch=", epoch,
                              " wave=A lane=", lane,
                              " gain=", gain,
                              " novelty=", novelty,
                              " gap=", gap,
                              " runtime=", rr[lane].runtime_sec,
                              " observed=", observed,
                              " credit=", role_credit[lane]);
            } else {
                ++stale[lane];
                role_credit[lane] *= 0.90;
            }
            sum_iter += (long long)rr[lane].iterations;
            sum_acc += rr[lane].accepted_moves;
            sum_att += rr[lane].attempted_moves;
        }

        phase_archive_rebuild(archive, std::move(cand), ev, pm);
        const bool wave_a_improved = !archive.empty() &&
            archive.front().objective + 1e-9 < before_wave_a;
        const bool wave_a_ownership_executed = !final_mode &&
            n_customers >= cfg.phase_ownership_min_customers && cfg.phase_ownership_pipeline &&
            instances > 4 && active[4];
        if (!archive.empty()) {
            update_global_best_checked(archive.front(), CG, pm);
            if (wave_a_improved) {
                stale[0] = 0;
                worker_states[0] = archive.front();
            }
        }
        safe_log_line("[PhaseCausality-E34] epoch=", epoch,
                      " before=", before_wave_a,
                      " after=", archive.empty() ? INF_D : archive.front().objective,
                      " improved=", wave_a_improved ? 1 : 0,
                      " best_lane=", wave_a_best_lane,
                      " ownership_executed=", wave_a_ownership_executed ? 1 : 0);
        phase_archive_log(archive, CG, "wave_a_barrier_e33", epoch);

        // E12 compact diminishing-return gate.  Do not spend another handoff
        // window merely because time remains when a complete discovery wave has
        // failed to produce even a fraction of one meaningful improvement.
        if (cfg.phase_compact_stall_to_tail &&
            n_customers < cfg.phase_structure_min_customers && epoch >= 1 &&
            !archive.empty()) {
            const double wave_a_gain = max(0.0, before_wave_a - archive.front().objective);
            const double stall_threshold = cfg.phase_compact_stall_gain_multiplier *
                max(1.0, meaningful_gain_threshold(max(1.0, before_wave_a)));
            if (wave_a_gain + 1e-9 < stall_threshold) {
                const double tail_available = cfg.hard_time_limit_s > 0.0
                    ? max(0.0, cfg.hard_time_limit_s - solver_elapsed_seconds())
                    : cfg.final_intensification_reserve_s;
                cfg.final_intensification_reserve_s = max(
                    cfg.final_intensification_reserve_s, tail_available);
                safe_log_line("[PhaseEngine-E32] compact_stall_to_tail epoch=", epoch,
                              " wave_a_gain=", wave_a_gain,
                              " threshold=", stall_threshold,
                              " best=", archive.front().objective,
                              " donated_tail_s=", tail_available);
                break;
            }
        }

        // Wave B / E10 cascade: on large instances, first correct the freshly
        // discovered best with route-region/interroute search, publish that state,
        // then let the breeder see the corrected archive. Compact instances keep
        // the M1-style cold exact + breeder parallel handoff.
        const double wave_b_remaining = pre_tail_end - solver_elapsed_seconds();
        const double wave_b_budget = min(wave_b_planned, max(0.0, wave_b_remaining));
        if (wave_b_budget >= cfg.phase_handoff_min_s && !solver_should_stop()) {
            const double wave_b_start_best = archive.front().objective;

            auto assimilate_handoff = [&](AlgoResult &r, int lane, const char *stage) {
                recompute_state_metrics_and_loads(r.best_state, ev);
                if (!solution_hard_feasible(r.best_state, CG, pm)) return false;
                const double reference = archive.empty() ? r.best_state.objective : archive.front().objective;
                vector<SolutionState> one{r.best_state};
                phase_archive_rebuild(archive, std::move(one), ev, pm);
                if (!archive.empty()) update_global_best_checked(archive.front(), CG, pm);
                if (lane >= 0 && lane < instances) {
                    worker_states[lane] = r.best_state;
                    const double gain = max(0.0, reference - r.best_state.objective);
                    const double norm_gain = gain /
                        max(1.0, meaningful_gain_threshold(max(1.0, reference)));
                    const double throughput = min(4.0,
                        norm_gain / max(0.15, r.runtime_sec));
                    const double observed = 0.40 + throughput;
                    const double decay = cfg.phase_role_credit_decay;
                    role_credit[lane] = decay * role_credit[lane] +
                        (1.0 - decay) * observed;
                    safe_log_line("[PhaseRoleCredit-E32] epoch=", epoch,
                                  " wave=", stage,
                                  " lane=", lane,
                                  " gain=", gain,
                                  " runtime=", r.runtime_sec,
                                  " observed=", observed,
                                  " credit=", role_credit[lane]);
                }
                sum_iter += (long long)r.iterations;
                sum_acc += r.accepted_moves;
                sum_att += r.attempted_moves;
                return true;
            };

            if (cfg.phase_cascade_handoff && n_customers >= 220) {
                // E33 causal handoff: lane 4 already ran ownership correction on
                // the Wave-A incumbent. Re-run B1 only when some *other* lane
                // produced a fresh best that ownership has not yet seen.
                const bool ownership_already_covers_fresh_best =
                    cfg.phase_skip_duplicate_cascade_region &&
                    wave_a_ownership_executed &&
                    (!wave_a_improved || wave_a_best_lane == 4);
                bool b1_ran = false;
                bool b1_improved = false;
                double b1_used = 0.0;
                const double b1_planned = max(0.20,
                    wave_b_budget * cfg.phase_cascade_region_fraction);

                if (!ownership_already_covers_fresh_best) {
                    const double b1_budget = min(b1_planned,
                        max(0.0, pre_tail_end - solver_elapsed_seconds()));
                    if (b1_budget >= 0.18 && !solver_should_stop()) {
                        const unsigned ss = cfg.base_seed + 0xE8B1000u +
                            (unsigned)epoch * 1000003u;
                        SolutionState start_state = archive.front();
                        const double before_b1 = start_state.objective;
                        const double b1_t0 = solver_elapsed_seconds();
                        AlgoResult b1;
                        const bool old_defer = tls_defer_global_publish;
                        tls_defer_global_publish = true;
                        b1 = run_phase_region_specialist(start_state, ev, pm,
                            b1_budget, ss, &region_policy);
                        tls_defer_global_publish = old_defer;
                        assimilate_handoff(b1, min(instances - 1, 4), "B1-region");
                        b1_used = max(0.0, solver_elapsed_seconds() - b1_t0);
                        b1_ran = true;
                        b1_improved = !archive.empty() &&
                            archive.front().objective + 1e-9 < before_b1;
                        phase_archive_log(archive, CG, "cascade_region_barrier_e33", epoch);
                        safe_log_line("[PhaseCascade-E34] epoch=", epoch,
                                      " stage=region",
                                      " budget_s=", b1_budget,
                                      " before=", before_b1,
                                      " after=", archive.front().objective,
                                      " gain=", max(0.0, before_b1 - archive.front().objective),
                                      " elapsed=", solver_elapsed_seconds());
                    }
                } else {
                    safe_log_line("[PhaseCascade-E34] epoch=", epoch,
                                  " stage=region SKIP reason=ownership_already_covers_best",
                                  " wave_a_best_lane=", wave_a_best_lane,
                                  " wave_a_improved=", wave_a_improved ? 1 : 0,
                                  " best=", archive.front().objective);
                }

                // Breeding is now evidence-gated. A fallback far-diverse pair is
                // not enough: both parents must be inside the quality band and
                // satisfy the structural-distance threshold. If ownership already
                // produced the fresh best, defer recombination to the inherited
                // elite tail instead of spending Wave-B budget automatically.
                double parent_distance = 0.0;
                const bool strong_pair = phase_has_strong_parent_pair(
                    archive, CG, &parent_distance);
                const bool b2_causal = !wave_a_ownership_executed || b1_ran;
                const bool b2_signal = !cfg.phase_breed_requires_strong_pair || strong_pair;
                const double wave_b_left = min(
                    max(0.0, wave_b_budget - b1_used),
                    max(0.0, pre_tail_end - solver_elapsed_seconds()));
                if (b2_causal && b2_signal && wave_b_left >= 0.28 &&
                    archive.size() >= 2 && !solver_should_stop()) {
                    const vector<SolutionState> breed_archive = archive;
                    const unsigned ss = cfg.base_seed + 0xE8B2000u +
                        (unsigned)epoch * 1000003u;
                    const double before_b2 = archive.front().objective;
                    AlgoResult b2;
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    b2 = run_phase_breeder(breed_archive, ev, pm, wave_b_left, ss);
                    tls_defer_global_publish = old_defer;
                    assimilate_handoff(b2, min(instances - 1, 5), "B2-breed");
                    phase_archive_log(archive, CG, "cascade_breed_barrier_e33", epoch);
                    safe_log_line("[PhaseCascade-E34] epoch=", epoch,
                                  " stage=breed",
                                  " budget_s=", wave_b_left,
                                  " strong_pair=", strong_pair ? 1 : 0,
                                  " parent_distance=", parent_distance,
                                  " before=", before_b2,
                                  " after=", archive.front().objective,
                                  " gain=", max(0.0, before_b2 - archive.front().objective),
                                  " elapsed=", solver_elapsed_seconds());
                } else {
                    safe_log_line("[PhaseCascade-E34] epoch=", epoch,
                                  " stage=breed SKIP causal=", b2_causal ? 1 : 0,
                                  " strong_pair=", strong_pair ? 1 : 0,
                                  " parent_distance=", parent_distance,
                                  " budget_left=", wave_b_left,
                                  " b1_ran=", b1_ran ? 1 : 0,
                                  " b1_improved=", b1_improved ? 1 : 0);
                }
            } else {
                // Compact handoff: preserve M1's dense exact-search behavior.
                const vector<SolutionState> fresh_archive = archive;
                const int handoff_cap = min(
                    max(1, cfg.phase_handoff_max_workers),
                    max(1, min(active_cap, (int)fresh_archive.size() + 1)));
                vector<AlgoResult> wb(handoff_cap);
                vector<int> wb_role(handoff_cap, 0);
                vector<thread> wb_threads;
                wb_threads.reserve(handoff_cap);
                for (int j = 0; j < handoff_cap; ++j) {
                    const unsigned ss = cfg.base_seed + 0xE8BC000u +
                        (unsigned)epoch * 1000003u + (unsigned)j * 65537u;
                    if (j == 0) {
                        wb_role[j] = 0;
                        SolutionState start_state = fresh_archive.front();
                        wb_threads.emplace_back([&, j, ss, start_state]() mutable {
                            const bool old_defer = tls_defer_global_publish;
                            tls_defer_global_publish = true;
                            wb[j] = sa_worker(CG, pm, ev, depot_idx, collections, ss,
                                wave_b_budget, cfg.use_cross2, &start_state,
                                shared_conv_log, conv_mtx, 2, 0);
                            tls_defer_global_publish = old_defer;
                        });
                    } else if (fresh_archive.size() >= 2) {
                        wb_role[j] = 5;
                        wb_threads.emplace_back([&, j, ss]() {
                            const bool old_defer = tls_defer_global_publish;
                            tls_defer_global_publish = true;
                            wb[j] = run_phase_breeder(fresh_archive, ev, pm,
                                wave_b_budget, ss);
                            tls_defer_global_publish = old_defer;
                        });
                    }
                }
                for (auto &t : wb_threads) if (t.joinable()) t.join();
                for (int j = 0; j < handoff_cap; ++j)
                    assimilate_handoff(wb[j], min(instances - 1, wb_role[j]), "B-compact");
                phase_archive_log(archive, CG, "compact_handoff_e11", epoch);
            }

            safe_log_line("[PhaseWaveB-E25] epoch=", epoch,
                          " budget_s=", wave_b_budget,
                          " before=", wave_b_start_best,
                          " after=", archive.front().objective,
                          " gain=", max(0.0, wave_b_start_best - archive.front().objective),
                          " elapsed=", solver_elapsed_seconds());
        }

        if (solver_phase_transition_requested.load(memory_order_relaxed) && !final_mode) {
            final_mode = true;
            safe_log_line("[PhaseEngine-E32] transition_to_final_mode epoch=", epoch,
                          " best=", archive.front().objective,
                          " elapsed=", solver_elapsed_seconds(),
                          " action=cascade_region_then_recombine");
            fill(stale.begin(), stale.end(), cfg.phase_worker_stale_epochs);
            if (instances > 3) idle_epochs[3] = 0;
        }
        ++epoch;
    }

    if (!archive.empty()) {
        update_global_best_checked(archive.front(), CG, pm);
        out.best_state = archive.front();
        out.elite_states = archive;
    } else {
        out.best_state = seed_state;
    }
    out.runtime_sec = chrono::duration<double>(Clock::now() - engine_t0).count();
    out.iterations = (double)sum_iter;
    out.accepted_moves = sum_acc;
    out.attempted_moves = sum_att;
    safe_log_line("[PhaseEngine-E32] END epochs=", epoch,
                  " archive=", archive.size(),
                  " best=", out.best_state.objective,
                  " runtime_s=", out.runtime_sec,
                  " iterations=", sum_iter,
                  " accepted=", sum_acc,
                  " attempted=", sum_att,
                  " transition=", solver_phase_transition_requested.load());
    return out;
}

/* ---------------- run helper and main ---------------- */
struct RunSummary {
    string name = "";
    double objective = INF_D;
    double distance_m = 0.0;
    double co2_g = 0.0;
    double runtime = 0.0;
    double iterations = 0.0;
    long long accepted = 0;
    long long attempted = 0;
};

static bool valid_run_summary(const RunSummary &r) {
    return !r.name.empty() &&
        isfinite(r.objective) &&
        r.objective >= 0.0 &&
        r.objective < INF_D / 2;
}

RunSummary evaluate_state(const SolutionState &s, ObjectiveEvaluator &ev, const Compressed &CG) {
    (void)CG;
    RunSummary r;
    r.name = "state";
    double total_obj = 0, total_dist = 0, total_co2 = 0;
    for (size_t i = 0; i < s.routes.size(); ++i) {
        auto rm = ev.compute_route_metrics(s.routes[i], s.route_load[i]);
        total_obj += rm.weighted_cost;
        total_dist += rm.distance_m;
        total_co2 += rm.co2_g;
    }
    r.objective = total_obj;
    r.distance_m = total_dist;
    r.co2_g = total_co2;
    r.runtime = 0;
    r.iterations = 0;
    r.accepted = 0;
    r.attempted = 0;
    return r;
}

static string csv_escape(const string &s) {
    bool quote = false;

    for (char c : s) {
        if (c == ',' || c == '"' || c == '\n' || c == '\r') {
            quote = true;
            break;
        }
    }

    if (!quote) return s;

    string out = "\"";
    for (char c : s) {
        if (c == '"') out += "\"\"";
        else out += c;
    }
    out += "\"";
    return out;
}

static void write_repair_trace_csv() {
    if (cfg.repair_trace_csv.empty()) return;

    vector<RepairTraceRow> rows;
    {
        lock_guard<mutex> lk(repair_trace_mutex);
        rows = repair_trace_rows;
    }

    ofstream out(cfg.repair_trace_csv);
    if (!out) {
        cerr << "Warning: cannot write repair trace CSV: "
            << cfg.repair_trace_csv << "\n";
        return;
    }

    out << "call_id,repair_mode,destroy_mode,removed_count,inserted_count,"
        << "failed_count,success,repair_time_us,candidate_routes_examined,"
        << "positions_ranked,exact_route_evaluations,base_objective,"
        << "repaired_objective\n";

    out << fixed << setprecision(6);
    for (const auto &r : rows) {
        out << r.call_id << ","
            << csv_escape(r.mode) << ","
            << r.destroy_mode << ","
            << r.removed_count << ","
            << r.inserted_count << ","
            << r.failed_count << ","
            << r.success << ","
            << r.repair_time_us << ","
            << r.candidate_routes_examined << ","
            << r.positions_ranked << ","
            << r.exact_route_evaluations << ","
            << r.base_objective << ","
            << r.repaired_objective << "\n";
    }
}

struct FinalSummary {
    double objective = 0.0;
    double distance_m = 0.0;
    double travel_time_s = 0.0;
    double service_time_s = 0.0;
    double waiting_s = 0.0;
    double lateness_s = 0.0;
    double co2_g = 0.0;
    double total_load = 0.0;
    double max_trip_load = 0.0;
    double max_route_duration_s = 0.0;
    double min_route_duration_s = 0.0;
    int total_trips = 0;
    int max_trips_single_truck = 0;
    int used_trucks = 0;
};

static FinalSummary summarize_solution(const SolutionState &s) {
    FinalSummary fs;
    fs.objective = s.objective;

    bool first_route = true;

    for (int r = 0; r < (int)s.route_metrics.size(); ++r) {
        const RouteMetrics &m = s.route_metrics[r];

        fs.distance_m += m.distance_m;
        fs.travel_time_s += m.travel_seconds;
        fs.service_time_s += m.service;
        fs.waiting_s += m.waiting;
        fs.lateness_s += m.lateness;
        fs.co2_g += m.co2_g;
        fs.total_trips += m.trip_count;
        fs.max_trips_single_truck = max(fs.max_trips_single_truck, m.trip_count);
        fs.max_trip_load = max(fs.max_trip_load, m.max_trip_load);

        if (m.trip_count > 0) {
            fs.used_trucks++;

            double duration = m.travel_seconds + m.service + m.waiting;

            if (first_route) {
                fs.max_route_duration_s = duration;
                fs.min_route_duration_s = duration;
                first_route = false;
            }
            else {
                fs.max_route_duration_s = max(fs.max_route_duration_s, duration);
                fs.min_route_duration_s = min(fs.min_route_duration_s, duration);
            }
        }
    }

    for (double x : s.route_load) {
        fs.total_load += x;
    }

    return fs;
}

static void append_repair_summary_csv(
    const FinalSummary &fs,
    double pipeline_runtime_s,
    bool feasible
) {
    if (!cfg.lns_benchmark_mode || cfg.repair_summary_csv.empty()) return;

    const string expected_header =
        "benchmark_tag,metric_mode,objective_mode,use_time_window,tw_strict_insertion,tw_allow_soft_intermediate,graph_nodes,graph_edges,customers,num_trucks,capacity,seed_source,repair_mode,lns_benchmark_mode,base_seed,effective_benchmark_seed,budget_type,search_budget_s,fixed_iterations,post_repair_polish,full_scan_exact_repairs,destroy_min_ratio,destroy_max_ratio,candidate_k,candidate_route_probe_k,route_cap,position_cap,use_topk,topk_exact,use_simd,use_savings_warm_start,repair_calls,successful_calls,failed_calls,repair_time_s,repairs_per_s,customers_requested,customers_inserted,customers_inserted_per_s,candidate_routes_examined,positions_ranked,exact_route_evaluations,improving_lns_moves,benchmark_iterations,noop_iterations,benchmark_runtime_s,time_overshoot_s,iterations_per_s,seed_objective,final_objective,objective_gain,final_distance_m,pipeline_runtime_s,feasible";

    bool exists = false;
    {
        ifstream fin(cfg.repair_summary_csv);
        exists = fin.good() && fin.peek() != ifstream::traits_type::eof();
        if (exists) {
            string existing_header;
            getline(fin, existing_header);
            if (existing_header != expected_header) {
                cerr << "Repair summary schema mismatch; refusing to append: "
                    << cfg.repair_summary_csv << "\n";
                return;
            }
        }
    }

    ofstream out(cfg.repair_summary_csv, ios::app);
    if (!out) {
        cerr << "Warning: cannot write repair summary CSV: "
            << cfg.repair_summary_csv << "\n";
        return;
    }

    if (!exists) out << expected_header << "\n";

    const long long calls = repair_profile.calls.load(memory_order_relaxed);
    const long long success = repair_profile.successful_calls.load(memory_order_relaxed);
    const long long failed = repair_profile.failed_calls.load(memory_order_relaxed);
    const long long inserted = repair_profile.customers_inserted.load(memory_order_relaxed);
    const double repair_s = profile_seconds(repair_profile.repair_time_us);
    const double repairs_per_s = repair_s > 0.0 ? calls / repair_s : 0.0;
    const double inserted_per_s = repair_s > 0.0 ? inserted / repair_s : 0.0;
    const double benchmark_s = profile_seconds(repair_profile.benchmark_time_us);
    const long long benchmark_iters =
        repair_profile.benchmark_iterations.load(memory_order_relaxed);
    const double iterations_per_s =
        benchmark_s > 0.0 ? benchmark_iters / benchmark_s : 0.0;

    out << fixed << setprecision(6)
        << csv_escape(cfg.benchmark_tag) << ","
        << csv_escape(cfg.metric_mode) << ","
        << csv_escape(cfg.objective_mode) << ","
        << (cfg.use_time_window ? 1 : 0) << ","
        << (cfg.tw_strict_insertion ? 1 : 0) << ","
        << (cfg.tw_allow_soft_intermediate ? 1 : 0) << ","
        << repair_benchmark_graph_nodes << ","
        << repair_benchmark_graph_edges << ","
        << repair_benchmark_customer_count << ","
        << cfg.num_trucks << ","
        << cfg.truck_capacity << ","
        << csv_escape(repair_benchmark_seed_name) << ","
        << repair_mode_name(effective_repair_mode()) << ","
        << (cfg.lns_benchmark_mode ? 1 : 0) << ","
        << cfg.base_seed << ","
        << repair_benchmark_effective_seed << ","
        << (cfg.lns_benchmark_iterations > 0 ? "fixed_iterations" : "time") << ","
        << repair_benchmark_requested_time_s << ","
        << cfg.lns_benchmark_iterations << ","
        << (cfg.lns_benchmark_disable_post_repair_polish ? 0 : 1) << ","
        << (cfg.lns_benchmark_full_scan_exact_repairs ? 1 : 0) << ","
        << cfg.alns_destroy_min_ratio << ","
        << cfg.alns_destroy_max_ratio << ","
        << cfg.candidate_k << ","
        << cfg.candidate_route_probe_k << ","
        << cfg.insertion_route_cap << ","
        << cfg.insertion_pos_cap << ","
        << (cfg.use_topk_insertion ? 1 : 0) << ","
        << cfg.insertion_topk_exact << ","
        << (cfg.use_simd_insertion_rank ? 1 : 0) << ","
        << (cfg.use_savings_warm_start ? 1 : 0) << ","
        << calls << ","
        << success << ","
        << failed << ","
        << repair_s << ","
        << repairs_per_s << ","
        << repair_profile.customers_requested.load(memory_order_relaxed) << ","
        << inserted << ","
        << inserted_per_s << ","
        << repair_profile.candidate_routes_examined.load(memory_order_relaxed) << ","
        << repair_profile.positions_ranked.load(memory_order_relaxed) << ","
        << repair_profile.exact_route_evaluations.load(memory_order_relaxed) << ","
        << repair_profile.improving_lns_moves.load(memory_order_relaxed) << ","
        << benchmark_iters << ","
        << repair_profile.benchmark_noop_iterations.load(memory_order_relaxed) << ","
        << benchmark_s << ","
        << repair_benchmark_time_overshoot_s << ","
        << iterations_per_s << ","
        << repair_benchmark_seed_objective << ","
        << fs.objective << ","
        << (repair_benchmark_seed_objective - fs.objective) << ","
        << fs.distance_m << ","
        << pipeline_runtime_s << ","
        << (feasible ? 1 : 0)
        << "\n";
}

[[maybe_unused]] static bool final_solution_feasible(const SolutionState &s, const Compressed &CG) {
    for (int i = 0; i < (int)CG.nodes.size(); ++i) {
        if (CG.nodes[i].type == 2) {
            if (i >= (int)s.served_count.size()) return false;
            if (s.served_count[i] != 1) return false;
        }
    }

    for (double max_load : s.route_max_trip_load) {
        if (max_load > cfg.truck_capacity + 1e-9) return false;
    }

    if (cfg.max_trips_per_truck > 0) {
        for (const auto &m : s.route_metrics) {
            if (m.trip_count > cfg.max_trips_per_truck) return false;
        }
    }

    return true;
}

static void append_run_summary_csv(
    const string &algorithm_name,
    const SolutionState &best_state,
    const Compressed &CG,
    const FinalSummary &fs,
    double runtime_s,
    long long iterations,
    long long accepted_moves,
    long long attempted_moves,
    long long drift_corrections,
    long long capacity_violations,
    double total_overload,
    bool feasible
) {
    (void)best_state;
    (void)CG;
    bool exists = false;

    {
        ifstream fin(cfg.run_summary_csv);
        exists = fin.good() && fin.peek() != ifstream::traits_type::eof();
    }

    ofstream out(cfg.run_summary_csv, ios::app);

    if (!out) {
        cerr << "Warning: cannot write run summary CSV: " << cfg.run_summary_csv << "\n";
        return;
    }

    if (!exists) {
        out
            << "solver,algorithm,objective_mode,seed,deterministic_seed,"
            << "time_limit_s,instances,num_trucks,capacity,"
            << "allow_multi_trip,max_trips_per_truck,"
            << "use_sa,use_alns,use_elite_pool,use_path_relink,use_local_polish,use_final_polish,"
            << "use_regret_repair,use_cross2,"
            << "use_candidate_lists,candidate_k,candidate_route_probe_k,"
            << "use_fleet_descent,candidate_route_unbiased_scan,use_string_slack_kick,string_slack_kick_period_s,string_slack_stagnation_trigger,string_slack_stagnation_s,string_slack_max_string_length,string_slack_max_strings,string_slack_route_top_fraction,use_time_stagnation_alns_kick,alns_stagnation_s,alns_kick_specialist_workers,lns_macro_metropolis,savings_relocate_accepts_per_round,"
            << "objective,distance_m,travel_time_s,service_time_s,waiting_s,lateness_s,co2_g,"
            << "total_load,max_trip_load,total_trips,max_trips_single_truck,used_trucks,"
            << "fleet_balance_s,runtime_s,iterations,accepted_moves,attempted_moves,effective_proposals,proposal_utilization,acceptance_rate,"
            << "drift_corrections,capacity_violations,total_overload,"
            << "recompute_calls,alns_calls,polish_calls,pair_queries,"
            << "hard_time_limit_s,search_elapsed_s,deadline_overrun_s,sa_worker_seconds,"
            << "late_feasible_improvements_rejected,cooperative_stop_polls,sa_route_draw_failures,"
            << "fleet_elim_calls,fleet_elim_successes,fleet_ejection_chain_attempts,fleet_ejection_chain_successes,fleet_ejection_chain_candidates,global_fleet_migration_checks,global_fleet_migration_adoptions,budget_saturation_rounds,"
            << "path_relink_calls,path_relink_steps,path_relink_feasible_progress,path_relink_best_improvements,"
            << "boundary_pair_calls,granular_tabu_calls,"
            << "interroute_relocate_calls,interroute_swap_calls,interroute_twooptstar_calls,interroute_pairs_available,interroute_pairs_touched,interroute_candidate_scans,interroute_exact_evals,interroute_time_s,"
            << "asymmetric_2opt_candidates,asymmetric_2opt_improvements,two_opt_route_calls,two_opt_route_time_s,"
            << "hgs_split_calls,hgs_split_fast_segments,hgs_split_exact_segments,hgs_split_time_s,"
            << "candidate_route_affinity_calls,candidate_route_affinity_nodes_scanned,worker_role_structural,worker_role_exploiter,worker_role_explorer,string_slack_kick_calls,string_slack_kick_improvements,string_slack_kick_time_s,string_slack_kick_trigger_checks,string_slack_kick_stagnation_eligible,string_slack_kick_feasible_best_improvements,string_slack_kick_global_best_improvements,string_slack_kick_metropolis_worse_accepts,alns_kick_calls,alns_kick_state_improvements,alns_kick_feasible_best_improvements,alns_kick_global_best_improvements,alns_kick_metropolis_worse_accepts,alns_kick_time_s,alns_kick_destroy0_calls,alns_kick_destroy1_calls,alns_kick_destroy2_calls,"
            << "deadline_snapshot,feasible\n";
    }

    double acceptance_rate =
        attempted_moves > 0
            ? (double)accepted_moves / (double)attempted_moves
            : 0.0;

    double fleet_balance =
        fs.used_trucks > 1
            ? fs.max_route_duration_s - fs.min_route_duration_s
            : 0.0;

    out
        << "custom_cpp,"
        << csv_escape(algorithm_name) << ","
        << csv_escape(cfg.objective_mode) << ","
        << cfg.base_seed << ","
        << (cfg.deterministic_seed ? 1 : 0) << ","
        << cfg.sa_time_limit << ","
        << cfg.sa_instances << ","
        << cfg.num_trucks << ","
        << cfg.truck_capacity << ","
        << (cfg.allow_multi_trip ? 1 : 0) << ","
        << cfg.max_trips_per_truck << ","
        << (cfg.use_sa ? 1 : 0) << ","
        << (cfg.use_alns ? 1 : 0) << ","
        << (cfg.use_elite_pool ? 1 : 0) << ","
        << (cfg.use_path_relink ? 1 : 0) << ","
        << (cfg.use_local_polish ? 1 : 0) << ","
        << (cfg.use_final_polish ? 1 : 0) << ","
        << (cfg.use_regret_repair ? 1 : 0) << ","
        << (cfg.use_cross2 ? 1 : 0) << ","
        << (cfg.use_candidate_lists ? 1 : 0) << ","
        << cfg.candidate_k << ","
        << cfg.candidate_route_probe_k << ","
        << (cfg.use_fleet_descent ? 1 : 0) << ","
        << (cfg.candidate_route_unbiased_scan ? 1 : 0) << ","
        << (cfg.use_string_slack_kick ? 1 : 0) << ","
        << cfg.string_slack_kick_period_s << ","
        << cfg.string_slack_stagnation_trigger << ","
        << cfg.string_slack_stagnation_s << ","
        << cfg.string_slack_max_string_length << ","
        << cfg.string_slack_max_strings << ","
        << cfg.string_slack_route_top_fraction << ","
        << (cfg.use_time_stagnation_alns_kick ? 1 : 0) << ","
        << cfg.alns_stagnation_s << ","
        << cfg.alns_kick_specialist_workers << ","
        << (cfg.lns_macro_metropolis ? 1 : 0) << ","
        << cfg.savings_relocate_accepts_per_round << ","
        << fs.objective << ","
        << fs.distance_m << ","
        << fs.travel_time_s << ","
        << fs.service_time_s << ","
        << fs.waiting_s << ","
        << fs.lateness_s << ","
        << fs.co2_g << ","
        << fs.total_load << ","
        << fs.max_trip_load << ","
        << fs.total_trips << ","
        << fs.max_trips_single_truck << ","
        << fs.used_trucks << ","
        << fleet_balance << ","
        << runtime_s << ","
        << iterations << ","
        << accepted_moves << ","
        << attempted_moves << ","
        << profile.sa_effective_proposals.load(memory_order_relaxed) << ","
        << (attempted_moves > 0 ? (double)profile.sa_effective_proposals.load(memory_order_relaxed) / (double)attempted_moves : 0.0) << ","
        << acceptance_rate << ","
        << drift_corrections << ","
        << capacity_violations << ","
        << total_overload << ","
        << profile.recompute_calls.load(memory_order_relaxed) << ","
        << profile.alns_calls.load(memory_order_relaxed) << ","
        << profile.polish_calls.load(memory_order_relaxed) << ","
        << profile.pair_queries.load(memory_order_relaxed) << ","
        << cfg.hard_time_limit_s << ","
        << solver_elapsed_seconds() << ","
        << solver_deadline_overrun_seconds() << ","
        << profile_seconds(profile.sa_time_us) << ","
        << profile.late_feasible_improvements_rejected.load(memory_order_relaxed) << ","
        << profile.cooperative_stop_polls.load(memory_order_relaxed) << ","
        << profile.sa_route_draw_failures.load(memory_order_relaxed) << ","
        << profile.fleet_elim_calls.load(memory_order_relaxed) << ","
        << profile.fleet_elim_successes.load(memory_order_relaxed) << ","
        << profile.fleet_ejection_chain_attempts.load(memory_order_relaxed) << ","
        << profile.fleet_ejection_chain_successes.load(memory_order_relaxed) << ","
        << profile.fleet_ejection_chain_candidates.load(memory_order_relaxed) << ","
        << profile.global_fleet_migration_checks.load(memory_order_relaxed) << ","
        << profile.global_fleet_migration_adoptions.load(memory_order_relaxed) << ","
        << profile.budget_saturation_rounds.load(memory_order_relaxed) << ","
        << profile.path_relink_calls.load(memory_order_relaxed) << ","
        << profile.path_relink_steps.load(memory_order_relaxed) << ","
        << profile.path_relink_feasible_progress.load(memory_order_relaxed) << ","
        << profile.path_relink_best_improvements.load(memory_order_relaxed) << ","
        << profile.boundary_pair_calls.load(memory_order_relaxed) << ","
        << profile.granular_tabu_calls.load(memory_order_relaxed) << ","
        << profile.interroute_relocate_calls.load(memory_order_relaxed) << ","
        << profile.interroute_swap_calls.load(memory_order_relaxed) << ","
        << profile.interroute_twooptstar_calls.load(memory_order_relaxed) << ","
        << profile.interroute_pairs_available.load(memory_order_relaxed) << ","
        << profile.interroute_pairs_touched.load(memory_order_relaxed) << ","
        << profile.interroute_candidate_scans.load(memory_order_relaxed) << ","
        << profile.interroute_exact_evals.load(memory_order_relaxed) << ","
        << profile_seconds(profile.interroute_time_us) << ","
        << profile.asymmetric_2opt_candidates.load(memory_order_relaxed) << ","
        << profile.asymmetric_2opt_improvements.load(memory_order_relaxed) << ","
        << profile.two_opt_route_calls.load(memory_order_relaxed) << ","
        << profile_seconds(profile.two_opt_route_time_us) << ","
        << profile.hgs_split_calls.load(memory_order_relaxed) << ","
        << profile.hgs_split_fast_segments.load(memory_order_relaxed) << ","
        << profile.hgs_split_exact_segments.load(memory_order_relaxed) << ","
        << profile_seconds(profile.hgs_split_time_us) << ","
        << profile.candidate_route_affinity_calls.load(memory_order_relaxed) << ","
        << profile.candidate_route_affinity_nodes_scanned.load(memory_order_relaxed) << ","
        << profile.worker_role_structural.load(memory_order_relaxed) << ","
        << profile.worker_role_exploiter.load(memory_order_relaxed) << ","
        << profile.worker_role_explorer.load(memory_order_relaxed) << ","
        << profile.string_slack_kick_calls.load(memory_order_relaxed) << ","
        << profile.string_slack_kick_improvements.load(memory_order_relaxed) << ","
        << profile_seconds(profile.string_slack_kick_time_us) << ","
        << profile.string_slack_kick_trigger_checks.load(memory_order_relaxed) << ","
        << profile.string_slack_kick_stagnation_eligible.load(memory_order_relaxed) << ","
        << profile.string_slack_kick_feasible_best_improvements.load(memory_order_relaxed) << ","
        << profile.string_slack_kick_global_best_improvements.load(memory_order_relaxed) << ","
        << profile.string_slack_kick_metropolis_worse_accepts.load(memory_order_relaxed) << ","
        << profile.alns_kick_calls.load(memory_order_relaxed) << ","
        << profile.alns_kick_state_improvements.load(memory_order_relaxed) << ","
        << profile.alns_kick_feasible_best_improvements.load(memory_order_relaxed) << ","
        << profile.alns_kick_global_best_improvements.load(memory_order_relaxed) << ","
        << profile.alns_kick_metropolis_worse_accepts.load(memory_order_relaxed) << ","
        << profile_seconds(profile.alns_kick_time_us) << ","
        << profile.alns_kick_destroy0_calls.load(memory_order_relaxed) << ","
        << profile.alns_kick_destroy1_calls.load(memory_order_relaxed) << ","
        << profile.alns_kick_destroy2_calls.load(memory_order_relaxed) << ","
        << (cfg.hard_time_limit_s > 0.0 ? 1 : 0) << ","
        << (feasible ? 1 : 0)
        << "\n";
}

static bool parse_bool_arg(const string &s) {
    string x = s;
    transform(
        x.begin(), x.end(), x.begin(),
        [](unsigned char c) { return (char)tolower(c); }
    );

    if (x == "1" || x == "true" || x == "yes" ||
        x == "y" || x == "on") {
        return true;
    }
    if (x == "0" || x == "false" || x == "no" ||
        x == "n" || x == "off") {
        return false;
    }

    throw invalid_argument(
        "invalid boolean '" + s +
        "' (use true/false, 1/0, yes/no, or on/off)"
    );
}

int main(int argc, char **argv) {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    auto total_start_time = Clock::now();

    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    // V40: start the governed deadline explicitly according to --budget_scope.
    solver_governor_started = false;

    try {
    safe_log_line("[SolverBuild] production routing engine");
    for (int i = 1; i < argc; i++) {
        string s = argv[i];

        auto parse_bool_local = [](const string &v) {
            return parse_bool_arg(v);
        };

        if (s == "--seed" && i + 1 < argc) {
            cfg.base_seed = (unsigned)stoul(argv[++i]);
        }
        else if (s == "--time_limit" && i + 1 < argc) {
            cfg.sa_time_limit = stod(argv[++i]);
        }
        else if (s == "--hard_time_limit_s" && i + 1 < argc) {
            cfg.hard_time_limit_s = max(0.0, stod(argv[++i]));
        }
        else if (s == "--final_intensification_reserve_s" && i + 1 < argc) {
            cfg.final_intensification_reserve_s = max(0.0, stod(argv[++i]));
        }
        else if (s == "--budget_scope" && i + 1 < argc) {
            cfg.budget_scope = argv[++i];
        }
        else if (s == "--work_conserving_tail" && i + 1 < argc) {
            cfg.work_conserving_tail = parse_bool_local(argv[++i]);
        }
        else if (s == "--use_parallel_fast_worker" && i + 1 < argc) { cfg.use_parallel_fast_worker = parse_bool_local(argv[++i]); }
        else if (s == "--sa_refinement_reserve_fraction" && i + 1 < argc) { cfg.sa_refinement_reserve_fraction = stod(argv[++i]); }
        else if (s == "--use_same_fleet_migration" && i + 1 < argc) { cfg.use_same_fleet_migration = parse_bool_local(argv[++i]); }
        else if (s == "--same_fleet_migration_min_gain" && i + 1 < argc) { cfg.same_fleet_migration_min_gain = stod(argv[++i]); }
        else if (s == "--same_fleet_migration_stagnation_s" && i + 1 < argc) { cfg.same_fleet_migration_stagnation_s = stod(argv[++i]); }
        else if (s == "--parallel_intensification_tail" && i + 1 < argc) { cfg.parallel_intensification_tail = parse_bool_local(argv[++i]); }
        else if (s == "--diagnostic_probe_csv" && i + 1 < argc) { cfg.diagnostic_probe_csv = argv[++i]; }
        else if (s == "--diagnostic_probe_budget_s" && i + 1 < argc) { cfg.diagnostic_probe_budget_s = max(0.01, stod(argv[++i])); }
        else if (s == "--staged_portfolio_tail" && i + 1 < argc) { cfg.staged_portfolio_tail = parse_bool_local(argv[++i]); }
        else if (s == "--staged_portfolio_first_intensify_s" && i + 1 < argc) { cfg.staged_portfolio_first_intensify_s = max(0.05, stod(argv[++i])); }
        else if (s == "--staged_portfolio_final_intensify_s" && i + 1 < argc) { cfg.staged_portfolio_final_intensify_s = max(0.05, stod(argv[++i])); }
        else if (s == "--staged_portfolio_fast_lanes" && i + 1 < argc) { cfg.staged_portfolio_fast_lanes = max(1, stoi(argv[++i])); }
        else if (s == "--staged_portfolio_post_fraction" && i + 1 < argc) { cfg.staged_portfolio_post_fraction = max(0.05, min(0.60, stod(argv[++i]))); }
        else if (s == "--staged_portfolio_layout" && i + 1 < argc) {
            cfg.staged_portfolio_layout = argv[++i];
            if (cfg.staged_portfolio_layout != "v60" &&
                cfg.staged_portfolio_layout != "s1f3fragx" &&
                cfg.staged_portfolio_layout != "elite_evolution" &&
                cfg.staged_portfolio_layout != "elite_evolution_strong" &&
                cfg.staged_portfolio_layout != "elite_evolution_strong2" &&
                cfg.staged_portfolio_layout != "elite_evolution_balanced") {
                throw runtime_error("--staged_portfolio_layout must be v60, s1f3fragx, elite_evolution, elite_evolution_strong, elite_evolution_strong2, or elite_evolution_balanced");
            }
        }
        else if (s == "--sa_max_effective_proposals" && i + 1 < argc) {
            cfg.sa_max_effective_proposals = max(0LL, stoll(argv[++i]));
        }
        else if (s == "--no_improve_stop_s" && i + 1 < argc) {
            cfg.no_improve_stop_s = max(0.0, stod(argv[++i]));
        }
        else if (s == "--target_no_improve_stop_s" && i + 1 < argc) {
            cfg.target_no_improve_stop_s = max(0.0, stod(argv[++i]));
        }
        else if (s == "--target_objective" && i + 1 < argc) {
            cfg.target_objective = max(0.0, stod(argv[++i]));
        }
        else if (s == "--meaningful_gain_abs" && i + 1 < argc) {
            cfg.meaningful_gain_abs = max(0.0, stod(argv[++i]));
        }
        else if (s == "--meaningful_gain_rel" && i + 1 < argc) {
            cfg.meaningful_gain_rel = max(0.0, stod(argv[++i]));
        }
        else if (s == "--instances" && i + 1 < argc) {
            cfg.sa_instances = stoi(argv[++i]);
        }
        else if (s == "--stability" && i + 1 < argc) {
            cfg.stability_runs = stoi(argv[++i]);
        }
        else if (s == "--no_cross") {
            cfg.use_cross2 = false;
        }
        else if (s == "--allow_splitting") {
            cfg.allow_splitting = true;
        }
        else if (s == "--capacity_mode" && i + 1 < argc) {
            cfg.capacity_mode = argv[++i];
        }
        else if (s == "--log_convergence" && i + 1 < argc) {
            cfg.log_convergence = parse_bool_local(argv[++i]);
        }
        else if (s == "--convergence_csv" && i + 1 < argc) {
            cfg.convergence_csv = argv[++i];
        }
        else if (s == "--convergence_sample_period_s" && i + 1 < argc) {
            cfg.convergence_sample_period_s = max(0.01, stod(argv[++i]));
        }
        else if (s == "--convergence_max_rows" && i + 1 < argc) {
            cfg.convergence_max_rows = max(1000LL, stoll(argv[++i]));
        }
        else if (s == "--deterministic") {
            cfg.deterministic_seed = true;
        }
        else if (s == "--no_sa") {
            cfg.use_sa = false;
        }
        else if (s == "--no_alns") {
            cfg.use_alns = false;
        }
        else if (s == "--no_elite") {
            cfg.use_elite_pool = false;
        }
        else if (s == "--no_relink") {
            cfg.use_path_relink = false;
        }
        else if (s == "--no_local_polish") {
            cfg.use_local_polish = false;
            cfg.use_relocate_polish = false;
            cfg.use_oropt = false;
            cfg.use_2opt = false;
        }
        else if (s == "--no_final_polish") {
            cfg.use_final_polish = false;
        }
        else if (s == "--no_greedy") {
            cfg.use_greedy_baseline = false;
        }
        else if (s == "--alns_rounds" && i + 1 < argc) {
            cfg.alns_rounds = stoi(argv[++i]);
        }
        else if (s == "--relink_period" && i + 1 < argc) {
            cfg.relink_period = stoi(argv[++i]);
        }
        else if (s == "--relink_period_s" && i + 1 < argc) {
            cfg.relink_period_s = max(0.01, stod(argv[++i]));
        }
        else if (s == "--stagnation_trigger" && i + 1 < argc) {
            cfg.stagnation_alns_trigger = stoi(argv[++i]);
        }
        else if (s == "--use_time_stagnation_alns_kick" && i + 1 < argc) cfg.use_time_stagnation_alns_kick = parse_bool_arg(argv[++i]);
        else if (s == "--alns_stagnation_s" && i + 1 < argc) cfg.alns_stagnation_s = max(0.0, stod(argv[++i]));
        else if (s == "--alns_kick_specialist_workers" && i + 1 < argc) cfg.alns_kick_specialist_workers = max(0, stoi(argv[++i]));
        else if (s == "--lns_macro_metropolis" && i + 1 < argc) cfg.lns_macro_metropolis = parse_bool_arg(argv[++i]);
        else if (s == "--repair_mode" && i + 1 < argc) {
            string mode = argv[++i];
            transform(mode.begin(), mode.end(), mode.begin(), ::tolower);

            if (mode == "legacy") cfg.repair_mode = RepairMode::LEGACY;
            else if (mode == "greedy_fast") cfg.repair_mode = RepairMode::GREEDY_FAST;
            else if (mode == "greedy_exact") cfg.repair_mode = RepairMode::GREEDY_EXACT;
            else if (mode == "regret2" || mode == "regret_2") cfg.repair_mode = RepairMode::REGRET_2;
            else if (mode == "regret3" || mode == "regret_3") cfg.repair_mode = RepairMode::REGRET_3;
            else if (mode == "regret_k" || mode == "regretk") cfg.repair_mode = RepairMode::REGRET_K;
            else {
                cerr << "Invalid --repair_mode. Use legacy, greedy_fast, greedy_exact, regret2, regret3, or regret_k.\n";
                return 1;
            }
        }
        else if (s == "--lns_benchmark_mode" && i + 1 < argc) {
            cfg.lns_benchmark_mode = parse_bool_local(argv[++i]);
        }
        else if (s == "--lns_benchmark_iterations" && i + 1 < argc) {
            cfg.lns_benchmark_iterations = max(0LL, stoll(argv[++i]));
        }
        else if (s == "--hybrid_fast_phase_s" && i + 1 < argc) {
            cfg.hybrid_fast_phase_s = max(0.0, stod(argv[++i]));
        }
        else if (s == "--use_phase_specialized_engine" && i + 1 < argc) { cfg.use_phase_specialized_engine = parse_bool_local(argv[++i]); }
        else if (s == "--phase_structure_min_customers" && i + 1 < argc) { cfg.phase_structure_min_customers = max(1, stoi(argv[++i])); }
        else if (s == "--phase_structure_parallel_min_customers" && i + 1 < argc) { cfg.phase_structure_parallel_min_customers = max(1, stoi(argv[++i])); }
        else if (s == "--phase_structure_fraction" && i + 1 < argc) { cfg.phase_structure_fraction = max(0.0, min(0.50, stod(argv[++i]))); }
        else if (s == "--phase_structure_min_time_s" && i + 1 < argc) { cfg.phase_structure_min_time_s = max(0.0, stod(argv[++i])); }
        else if (s == "--phase_structure_max_time_s" && i + 1 < argc) { cfg.phase_structure_max_time_s = max(0.0, stod(argv[++i])); }
        else if (s == "--phase_structure_no_improve_s" && i + 1 < argc) { cfg.phase_structure_no_improve_s = max(0.0, stod(argv[++i])); }
        else if (s == "--phase_structure_destroy_min_ratio" && i + 1 < argc) { cfg.phase_structure_destroy_min_ratio = max(0.01, min(0.90, stod(argv[++i]))); }
        else if (s == "--phase_structure_destroy_max_ratio" && i + 1 < argc) { cfg.phase_structure_destroy_max_ratio = max(0.01, min(0.95, stod(argv[++i]))); }
        else if (s == "--phase_macro_destroy_min_ratio" && i + 1 < argc) { cfg.phase_macro_destroy_min_ratio = max(0.01, min(0.90, stod(argv[++i]))); }
        else if (s == "--phase_macro_destroy_max_ratio" && i + 1 < argc) { cfg.phase_macro_destroy_max_ratio = max(0.01, min(0.95, stod(argv[++i]))); }
        else if (s == "--phase_epoch_s" && i + 1 < argc) { cfg.phase_epoch_s = max(0.25, stod(argv[++i])); }
        else if (s == "--phase_archive_size" && i + 1 < argc) { cfg.phase_archive_size = max(2, min(32, stoi(argv[++i]))); }
        else if (s == "--phase_archive_clone_distance" && i + 1 < argc) { cfg.phase_archive_clone_distance = max(0.0, min(1.0, stod(argv[++i]))); }
        else if (s == "--phase_archive_quality_weight" && i + 1 < argc) { cfg.phase_archive_quality_weight = max(0.0, min(1.0, stod(argv[++i]))); }
        else if (s == "--phase_archive_max_quality_gap" && i + 1 < argc) { cfg.phase_archive_max_quality_gap = max(0.0, min(1.0, stod(argv[++i]))); }
        else if (s == "--phase_parent_quality_band" && i + 1 < argc) { cfg.phase_parent_quality_band = max(0.0, stod(argv[++i])); }
        else if (s == "--phase_parent_min_distance" && i + 1 < argc) { cfg.phase_parent_min_distance = max(0.0, min(1.0, stod(argv[++i]))); }
        else if (s == "--phase_worker_stale_epochs" && i + 1 < argc) { cfg.phase_worker_stale_epochs = max(1, stoi(argv[++i])); }
        else if (s == "--phase_breeder_fraction" && i + 1 < argc) { cfg.phase_breeder_fraction = max(0.20, min(0.95, stod(argv[++i]))); }
        else if (s == "--phase_respect_hardware_concurrency" && i + 1 < argc) { cfg.phase_respect_hardware_concurrency = parse_bool_local(argv[++i]); }
        else if (s == "--phase_min_active_workers" && i + 1 < argc) { cfg.phase_min_active_workers = max(1, stoi(argv[++i])); }
        else if (s == "--phase_role_credit_decay" && i + 1 < argc) { cfg.phase_role_credit_decay = max(0.0, min(0.99, stod(argv[++i]))); }
        else if (s == "--phase_role_idle_bonus" && i + 1 < argc) { cfg.phase_role_idle_bonus = max(0.0, stod(argv[++i])); }
        else if (s == "--phase_persist_lns_policy" && i + 1 < argc) { cfg.phase_persist_lns_policy = parse_bool_local(argv[++i]); }
        else if (s == "--phase_adapt_destroy_intensity" && i + 1 < argc) { cfg.phase_adapt_destroy_intensity = parse_bool_local(argv[++i]); }
        else if (s == "--phase_macro_search_fraction" && i + 1 < argc) { cfg.phase_macro_search_fraction = max(0.35, min(0.92, stod(argv[++i]))); }
        else if (s == "--phase_macro_recovery_quality_gap" && i + 1 < argc) { cfg.phase_macro_recovery_quality_gap = max(0.0, min(0.10, stod(argv[++i]))); }
        else if (s == "--phase_adaptive_region_policy" && i + 1 < argc) { cfg.phase_adaptive_region_policy = parse_bool_local(argv[++i]); }
        else if (s == "--phase_region_slice_fraction" && i + 1 < argc) { cfg.phase_region_slice_fraction = max(0.08, min(0.50, stod(argv[++i]))); }
        else if (s == "--phase_two_wave_epochs" && i + 1 < argc) { cfg.phase_two_wave_epochs = parse_bool_local(argv[++i]); }
        else if (s == "--phase_handoff_fraction" && i + 1 < argc) { cfg.phase_handoff_fraction = max(0.10, min(0.48, stod(argv[++i]))); }
        else if (s == "--phase_handoff_min_s" && i + 1 < argc) { cfg.phase_handoff_min_s = max(0.10, stod(argv[++i])); }
        else if (s == "--phase_handoff_max_workers" && i + 1 < argc) { cfg.phase_handoff_max_workers = max(1, min(4, stoi(argv[++i]))); }
        else if (s == "--phase_min_epoch_launch_s" && i + 1 < argc) { cfg.phase_min_epoch_launch_s = max(0.10, stod(argv[++i])); }
        else if (s == "--phase_cascade_handoff" && i + 1 < argc) { cfg.phase_cascade_handoff = parse_bool_local(argv[++i]); }
        else if (s == "--phase_cascade_region_fraction" && i + 1 < argc) { cfg.phase_cascade_region_fraction = max(0.30, min(0.82, stod(argv[++i]))); }
        else if (s == "--phase_dynamic_active_cap" && i + 1 < argc) { cfg.phase_dynamic_active_cap = parse_bool_local(argv[++i]); }
        else if (s == "--phase_late_discovery_max_workers" && i + 1 < argc) { cfg.phase_late_discovery_max_workers = max(2, min(6, stoi(argv[++i]))); }
        else if (s == "--phase_trace_csv" && i + 1 < argc) { cfg.phase_trace_csv = argv[++i]; }
        else if (s == "--phase_ownership_pipeline" && i + 1 < argc) { cfg.phase_ownership_pipeline = parse_bool_local(argv[++i]); }
        else if (s == "--phase_ownership_min_customers" && i + 1 < argc) { cfg.phase_ownership_min_customers = max(1, stoi(argv[++i])); }
        else if (s == "--phase_ownership_region_fraction" && i + 1 < argc) { cfg.phase_ownership_region_fraction = stod(argv[++i]); }
        else if (s == "--phase_readiness_gate" && i + 1 < argc) { cfg.phase_readiness_gate = parse_bool_local(argv[++i]); }
        else if (s == "--phase_entry_try_savings" && i + 1 < argc) { cfg.phase_entry_try_savings = parse_bool_local(argv[++i]); }
        else if (s == "--phase_entry_savings_max_customers" && i + 1 < argc) { cfg.phase_entry_savings_max_customers = max(1, stoi(argv[++i])); }
        else if (s == "--phase_entry_probe_fraction" && i + 1 < argc) { cfg.phase_entry_probe_fraction = max(0.0, min(0.10, stod(argv[++i]))); }
        else if (s == "--phase_entry_probe_min_s" && i + 1 < argc) { cfg.phase_entry_probe_min_s = max(0.05, stod(argv[++i])); }
        else if (s == "--phase_entry_probe_max_s" && i + 1 < argc) { cfg.phase_entry_probe_max_s = max(0.05, stod(argv[++i])); }
        else if (s == "--phase_entry_probe_workers" && i + 1 < argc) { cfg.phase_entry_probe_workers = max(1, min(3, stoi(argv[++i]))); }
        else if (s == "--phase_entry_hot_age_fraction" && i + 1 < argc) { cfg.phase_entry_hot_age_fraction = max(0.02, min(0.80, stod(argv[++i]))); }
        else if (s == "--phase_entry_extension_fraction" && i + 1 < argc) { cfg.phase_entry_extension_fraction = max(0.0, min(2.0, stod(argv[++i]))); }
        else if (s == "--phase_entry_extension_max_s" && i + 1 < argc) { cfg.phase_entry_extension_max_s = max(0.0, stod(argv[++i])); }
        else if (s == "--phase_structure_hot_age_fraction" && i + 1 < argc) { cfg.phase_structure_hot_age_fraction = max(0.02, min(0.80, stod(argv[++i]))); }
        else if (s == "--phase_structure_extension_fraction" && i + 1 < argc) { cfg.phase_structure_extension_fraction = max(0.0, min(1.0, stod(argv[++i]))); }
        else if (s == "--phase_structure_extension_max_s" && i + 1 < argc) { cfg.phase_structure_extension_max_s = max(0.0, stod(argv[++i])); }
        else if (s == "--phase_compact_epoch_s" && i + 1 < argc) { cfg.phase_compact_epoch_s = max(0.50, stod(argv[++i])); }
        else if (s == "--phase_compact_first_epoch_s" && i + 1 < argc) { cfg.phase_compact_first_epoch_s = max(0.50, stod(argv[++i])); }
        else if (s == "--phase_compact_stall_to_tail" && i + 1 < argc) { cfg.phase_compact_stall_to_tail = parse_bool_local(argv[++i]); }
        else if (s == "--phase_compact_stall_gain_multiplier" && i + 1 < argc) { cfg.phase_compact_stall_gain_multiplier = max(0.0, stod(argv[++i])); }
        else if (s == "--phase_compact_deadline_finish" && i + 1 < argc) { cfg.phase_compact_deadline_finish = parse_bool_local(argv[++i]); }
        else if (s == "--phase_compact_finish_workers" && i + 1 < argc) { cfg.phase_compact_finish_workers = max(1, min(3, stoi(argv[++i]))); }
        else if (s == "--phase_compact_finish_min_s" && i + 1 < argc) { cfg.phase_compact_finish_min_s = max(0.10, stod(argv[++i])); }
        else if (s == "--phase_adaptive_tail_probe" && i + 1 < argc) { cfg.phase_adaptive_tail_probe = parse_bool_local(argv[++i]); }
        else if (s == "--phase_tail_probe_fraction" && i + 1 < argc) { cfg.phase_tail_probe_fraction = max(0.01, min(0.40, stod(argv[++i]))); }
        else if (s == "--phase_tail_probe_min_s" && i + 1 < argc) { cfg.phase_tail_probe_min_s = max(0.05, stod(argv[++i])); }
        else if (s == "--phase_tail_probe_max_s" && i + 1 < argc) { cfg.phase_tail_probe_max_s = max(0.05, stod(argv[++i])); }
        else if (s == "--phase_tail_probe_max_workers" && i + 1 < argc) { cfg.phase_tail_probe_max_workers = max(1, min(5, stoi(argv[++i]))); }
        else if (s == "--phase_tail_probe_repeat_gain_multiplier" && i + 1 < argc) { cfg.phase_tail_probe_repeat_gain_multiplier = max(0.0, stod(argv[++i])); }
        else if (s == "--phase_tail_probe_repeat_max_s" && i + 1 < argc) { cfg.phase_tail_probe_repeat_max_s = max(0.0, stod(argv[++i])); }
        else if (s == "--phase_e2_destroy_policy" && i + 1 < argc) { cfg.phase_e2_destroy_policy = parse_bool_local(argv[++i]); }
        else if (s == "--lns_benchmark_destroy_mode" && i + 1 < argc) { cfg.lns_benchmark_destroy_mode = stoi(argv[++i]); }
        else if (s == "--lns_benchmark_disable_post_repair_polish" && i + 1 < argc) {
            cfg.lns_benchmark_disable_post_repair_polish = parse_bool_local(argv[++i]);
        }
        else if (s == "--lns_benchmark_full_scan_exact_repairs" && i + 1 < argc) {
            cfg.lns_benchmark_full_scan_exact_repairs = parse_bool_local(argv[++i]);
        }
        else if (s == "--benchmark_tag" && i + 1 < argc) {
            cfg.benchmark_tag = argv[++i];
        }
        else if (s == "--repair_summary_csv" && i + 1 < argc) {
            cfg.repair_summary_csv = argv[++i];
        }
        else if (s == "--repair_trace_csv" && i + 1 < argc) {
            cfg.repair_trace_csv = argv[++i];
        }
        else if (s == "--repair_trace_sample_every" && i + 1 < argc) {
            cfg.repair_trace_sample_every = max(1, stoi(argv[++i]));
        }
        else if (s == "--repair_trace_max_rows" && i + 1 < argc) {
            cfg.repair_trace_max_rows = stoll(argv[++i]);
            if (cfg.repair_trace_max_rows < 1 ||
                cfg.repair_trace_max_rows > 10000000LL) {
                throw invalid_argument(
                    "--repair_trace_max_rows must be in [1, 10000000]"
                );
            }
        }
        else if (s == "--no_regret") {
            cfg.use_regret_repair = false;
            if (cfg.repair_mode == RepairMode::LEGACY) {
                cfg.repair_mode = RepairMode::GREEDY_FAST;
            }
        }
        else if (s == "--regret_k" && i + 1 < argc) {
            cfg.regret_k = max(2, stoi(argv[++i]));
        }
        else if (s == "--insertion_route_cap" && i + 1 < argc) {
            cfg.insertion_route_cap = max(1, stoi(argv[++i]));
        }
        else if (s == "--insertion_pos_cap" && i + 1 < argc) {
            cfg.insertion_pos_cap = max(1, stoi(argv[++i]));
        }
        else if (s == "--use_topk_insertion" && i + 1 < argc) {
            cfg.use_topk_insertion = parse_bool_local(argv[++i]);
        }
        else if (s == "--insertion_topk_exact" && i + 1 < argc) {
            cfg.insertion_topk_exact = max(1, stoi(argv[++i]));
        }
        else if (s == "--use_simd_insertion_rank" && i + 1 < argc) {
            cfg.use_simd_insertion_rank = parse_bool_local(argv[++i]);
        }
        else if (s == "--simd_global_topk_multiplier" && i + 1 < argc) {
            cfg.simd_global_topk_multiplier = max(1, stoi(argv[++i]));
        }
        else if (s == "--use_savings_warm_start" && i + 1 < argc) {
            cfg.use_savings_warm_start = parse_bool_arg(argv[++i]);
        }
        else if (s == "--savings_variants" && i + 1 < argc) {
            cfg.savings_variants = stoi(argv[++i]);
        }
        else if (s == "--savings_noise" && i + 1 < argc) {
            cfg.savings_noise = stod(argv[++i]);
        }
        else if (s == "--savings_polish_time_s" && i + 1 < argc) {
            cfg.savings_polish_time_s = stod(argv[++i]);
        }
        else if (s == "--savings_light_polish_rounds" && i + 1 < argc) {
            cfg.savings_light_polish_rounds = stoi(argv[++i]);
        }
        else if (s == "--savings_relocate_accepts_per_round" && i + 1 < argc) {
            cfg.savings_relocate_accepts_per_round = max(1, stoi(argv[++i]));
        }
        else if (s == "--savings_verbose" && i + 1 < argc) {
            cfg.savings_verbose = parse_bool_arg(argv[++i]);
        }
        else if (s == "--use_alns" && i + 1 < argc) {
            cfg.use_alns = parse_bool_local(argv[++i]);
        }
        else if (s == "--use_elite_pool" && i + 1 < argc) {
            cfg.use_elite_pool = parse_bool_local(argv[++i]);
        }
        else if (s == "--use_path_relink" && i + 1 < argc) {
            cfg.use_path_relink = parse_bool_local(argv[++i]);
        }
        else if (s == "--use_final_polish" && i + 1 < argc) {
            cfg.use_final_polish = parse_bool_local(argv[++i]);
        }
        else if (s == "--use_oropt" && i + 1 < argc) {
            cfg.use_oropt = parse_bool_local(argv[++i]);
        }
        else if (s == "--use_2opt" && i + 1 < argc) {
            cfg.use_2opt = parse_bool_local(argv[++i]);
        }
        else if (s == "--use_relocate_polish" && i + 1 < argc) {
            cfg.use_relocate_polish = parse_bool_local(argv[++i]);
        }
        else if (s == "--alns_destroy_min_ratio" && i + 1 < argc) {
            cfg.alns_destroy_min_ratio = stod(argv[++i]);
        }
        else if (s == "--alns_destroy_max_ratio" && i + 1 < argc) {
            cfg.alns_destroy_max_ratio = stod(argv[++i]);
        }
        else if (s == "--elite_update_period" && i + 1 < argc) {
            cfg.elite_update_period = stoi(argv[++i]);
        }
        else if (s == "--elite_update_period_s" && i + 1 < argc) {
            cfg.elite_update_period_s = max(0.01, stod(argv[++i]));
        }
        else if (s == "--final_polish_rounds" && i + 1 < argc) {
            cfg.final_polish_rounds = stoi(argv[++i]);
        }
        else if (s == "--objective_mode" && i + 1 < argc) {
            cfg.objective_mode = argv[++i];

            if (cfg.objective_mode != "distance" &&
                cfg.objective_mode != "time" &&
                cfg.objective_mode != "hybrid") {
                cerr << "Invalid --objective_mode. Use distance, time, or hybrid.\n";
                return 1;
            }
        }
        else if (s == "--run_summary_csv" && i + 1 < argc) {
            cfg.run_summary_csv = argv[++i];
        }
        else if (s == "--allow_multi_trip" && i + 1 < argc) {
            cfg.allow_multi_trip = parse_bool_local(argv[++i]);
        }
        else if (s == "--max_trips_per_truck" && i + 1 < argc) {
            cfg.max_trips_per_truck = max(0, stoi(argv[++i]));
        }
        else if (s == "--w_trip_excess" && i + 1 < argc) {
            cfg.w_trip_excess = stod(argv[++i]);
        }
        else if (s == "--use_interroute_polish" && i + 1 < argc) {
            cfg.use_interroute_polish = parse_bool_local(argv[++i]);
        }
        else if (s == "--use_interroute_arc_delta_prune" && i + 1 < argc) {
            cfg.use_interroute_arc_delta_prune = parse_bool_local(argv[++i]);
        }
        else if (s == "--interroute_polish_rounds" && i + 1 < argc) {
            cfg.interroute_polish_rounds = max(0, stoi(argv[++i]));
        }
        else if (s == "--final_refinement_rounds" && i + 1 < argc) {
            cfg.final_refinement_rounds = max(1, stoi(argv[++i]));
        }
        else if (s == "--interroute_scan_cap" && i + 1 < argc) {
            cfg.interroute_scan_cap = max(1, stoi(argv[++i]));
        }
        else if (s == "--interroute_rank_pairs" && i + 1 < argc) {
            cfg.interroute_rank_pairs = parse_bool_local(argv[++i]);
        }
        else if (s == "--max_interroute_moves" && i + 1 < argc) {
            cfg.max_interroute_moves = max(1, stoi(argv[++i]));
        }
        else if (s == "--use_candidate_lists" && i + 1 < argc) {
            cfg.use_candidate_lists = parse_bool_local(argv[++i]);
        }
        else if (s == "--candidate_k" && i + 1 < argc) {
            cfg.candidate_k = max(1, stoi(argv[++i]));
        }
        else if (s == "--candidate_route_probe_k" && i + 1 < argc) {
            cfg.candidate_route_probe_k = max(1, stoi(argv[++i]));
        }
        else if (s == "--use_cluster_warm_start" && i + 1 < argc) {
            cfg.use_cluster_warm_start = parse_bool_local(argv[++i]);
        }
        else if (s == "--clusters_csv" && i + 1 < argc) {
            cfg.clusters_csv = argv[++i];
        }
        else if (s == "--use_guided_arc_penalty" && i + 1 < argc) {
            cfg.use_guided_arc_penalty = parse_bool_local(argv[++i]);
        }
        else if (s == "--gls_rounds" && i + 1 < argc) {
            cfg.gls_rounds = stoi(argv[++i]);
        }
        else if (s == "--gls_moves_per_round" && i + 1 < argc) {
            cfg.gls_moves_per_round = stoi(argv[++i]);
        }
        else if (s == "--gls_lambda" && i + 1 < argc) {
            cfg.gls_lambda = stod(argv[++i]);
        }
        else if (s == "--gls_penalty_top_k" && i + 1 < argc) {
            cfg.gls_penalty_top_k = stoi(argv[++i]);
        }
        else if (s == "--gls_source_route_cap" && i + 1 < argc) {
            cfg.gls_source_route_cap = stoi(argv[++i]);
        }
        else if (s == "--gls_source_customer_cap" && i + 1 < argc) {
            cfg.gls_source_customer_cap = stoi(argv[++i]);
        }
        else if (s == "--gls_target_route_cap" && i + 1 < argc) {
            cfg.gls_target_route_cap = stoi(argv[++i]);
        }
        else if (s == "--gls_pos_cap" && i + 1 < argc) {
            cfg.gls_pos_cap = stoi(argv[++i]);
        }
        else if (s == "--gls_max_exact_worsen_per_move" && i + 1 < argc) {
            cfg.gls_max_exact_worsen_per_move = stod(argv[++i]);
        }
        else if (s == "--gls_try_swaps" && i + 1 < argc) {
            cfg.gls_try_swaps = parse_bool_local(argv[++i]);
        }
        else if (s == "--gls_verbose" && i + 1 < argc) {
            cfg.gls_verbose = parse_bool_local(argv[++i]);
        }
        else if (s == "--gls_adaptive_lambda" && i + 1 < argc) {
            cfg.gls_adaptive_lambda = parse_bool_local(argv[++i]);
        }
        else if (s == "--gls_lambda_base" && i + 1 < argc) {
            cfg.gls_lambda_base = stod(argv[++i]);
        }
        else if (s == "--gls_lambda_growth" && i + 1 < argc) {
            cfg.gls_lambda_growth = stod(argv[++i]);
        }
        else if (s == "--gls_lambda_max" && i + 1 < argc) {
            cfg.gls_lambda_max = stod(argv[++i]);
        }
        else if (s == "--gls_adaptive_worsen_cap" && i + 1 < argc) {
            cfg.gls_adaptive_worsen_cap = parse_bool_local(argv[++i]);
        }
        else if (s == "--gls_worsen_growth" && i + 1 < argc) {
            cfg.gls_worsen_growth = stod(argv[++i]);
        }
        else if (s == "--gls_worsen_max" && i + 1 < argc) {
            cfg.gls_worsen_max = stod(argv[++i]);
        }
        else if (s == "--use_fragment_lns" && i + 1 < argc) {
            cfg.use_fragment_lns = parse_bool_arg(argv[++i]);
        }
        else if (s == "--fragment_lns_rounds" && i + 1 < argc) {
            cfg.fragment_lns_rounds = stoi(argv[++i]);
        }
        else if (s == "--use_fleet_descent" && i + 1 < argc) cfg.use_fleet_descent = parse_bool_arg(argv[++i]);
        else if (s == "--candidate_route_unbiased_scan" && i + 1 < argc) cfg.candidate_route_unbiased_scan = parse_bool_arg(argv[++i]);
        else if (s == "--use_fleet_ejection_chain" && i + 1 < argc) cfg.use_fleet_ejection_chain = parse_bool_arg(argv[++i]);
        else if (s == "--fleet_ejection_max_per_source" && i + 1 < argc) cfg.fleet_ejection_max_per_source = max(0, stoi(argv[++i]));
        else if (s == "--fleet_ejection_route_scan_cap" && i + 1 < argc) cfg.fleet_ejection_route_scan_cap = max(1, stoi(argv[++i]));
        else if (s == "--fleet_ejection_customer_scan_cap" && i + 1 < argc) cfg.fleet_ejection_customer_scan_cap = max(1, stoi(argv[++i]));
        else if (s == "--use_global_fleet_migration" && i + 1 < argc) cfg.use_global_fleet_migration = parse_bool_arg(argv[++i]);
        else if (s == "--global_fleet_migration_period" && i + 1 < argc) cfg.global_fleet_migration_period = max(1, stoi(argv[++i]));
        else if (s == "--global_fleet_migration_period_s" && i + 1 < argc) cfg.global_fleet_migration_period_s = max(0.01, stod(argv[++i]));
        else if (s == "--alns_kick_cooldown_s" && i + 1 < argc) cfg.alns_kick_cooldown_s = max(0.01, stod(argv[++i]));
        else if (s == "--use_string_slack_kick" && i + 1 < argc) cfg.use_string_slack_kick = parse_bool_arg(argv[++i]);
        else if (s == "--use_adjacent_string_kick" && i + 1 < argc) cfg.use_string_slack_kick = parse_bool_arg(argv[++i]);
        else if (s == "--string_slack_kick_period_s" && i + 1 < argc) cfg.string_slack_kick_period_s = max(0.05, stod(argv[++i]));
        else if (s == "--string_slack_stagnation_trigger" && i + 1 < argc) cfg.string_slack_stagnation_trigger = max(0, stoi(argv[++i]));
        else if (s == "--string_slack_stagnation_s" && i + 1 < argc) cfg.string_slack_stagnation_s = max(0.0, stod(argv[++i]));
        else if (s == "--string_slack_max_string_length" && i + 1 < argc) cfg.string_slack_max_string_length = max(1, stoi(argv[++i]));
        else if (s == "--string_slack_max_strings" && i + 1 < argc) cfg.string_slack_max_strings = max(1, stoi(argv[++i]));
        else if (s == "--string_slack_route_top_fraction" && i + 1 < argc) cfg.string_slack_route_top_fraction = min(1.0, max(0.05, stod(argv[++i])));
        else if (s == "--global_fleet_migration_reheat" && i + 1 < argc) cfg.global_fleet_migration_reheat = min(1.0, max(0.0, stod(argv[++i])));
        else if (s == "--global_fleet_migration_preserve_explorers" && i + 1 < argc) cfg.global_fleet_migration_preserve_explorers = max(0, stoi(argv[++i]));
        else if (s == "--fragment_lns_remove_min" && i + 1 < argc) {
            cfg.fragment_lns_remove_min = stoi(argv[++i]);
        }
        else if (s == "--fragment_lns_remove_max" && i + 1 < argc) {
            cfg.fragment_lns_remove_max = stoi(argv[++i]);
        }
        else if (s == "--fragment_lns_pos_cap" && i + 1 < argc) {
            cfg.fragment_lns_pos_cap = max(1, stoi(argv[++i]));
        }
        else if (s == "--fragment_lns_related_k" && i + 1 < argc) {
            cfg.fragment_lns_related_k = stoi(argv[++i]);
        }
        else if (s == "--fragment_lns_verbose" && i + 1 < argc) {
            cfg.fragment_lns_verbose = parse_bool_arg(argv[++i]);
        }
        else if (s == "--use_route_region_lns" && i + 1 < argc) {
            cfg.use_route_region_lns = parse_bool_arg(argv[++i]);
        }
        else if (s == "--route_region_lns_rounds" && i + 1 < argc) {
            cfg.route_region_lns_rounds = max(0, stoi(argv[++i]));
        }
        else if (s == "--route_region_lns_seed_pairs" && i + 1 < argc) {
            cfg.route_region_lns_seed_pairs = max(1, stoi(argv[++i]));
        }
        else if (s == "--route_region_lns_max_routes" && i + 1 < argc) {
            cfg.route_region_lns_max_routes = max(2, stoi(argv[++i]));
        }
        else if (s == "--route_region_lns_remove_min" && i + 1 < argc) {
            cfg.route_region_lns_remove_min = max(2, stoi(argv[++i]));
        }
        else if (s == "--route_region_lns_remove_max" && i + 1 < argc) {
            cfg.route_region_lns_remove_max = max(2, stoi(argv[++i]));
        }
        else if (s == "--route_region_lns_neighbor_radius" && i + 1 < argc) {
            cfg.route_region_lns_neighbor_radius = max(0, stoi(argv[++i]));
        }
        else if (s == "--route_region_lns_verbose" && i + 1 < argc) {
            cfg.route_region_lns_verbose = parse_bool_arg(argv[++i]);
        }
        else if (s == "--use_longest_route_ruin" && i + 1 < argc) {
            cfg.use_longest_route_ruin = parse_bool_arg(argv[++i]);
        }
        else if (s == "--longest_route_ruin_probability" && i + 1 < argc) {
            cfg.longest_route_ruin_probability = min(1.0, max(0.0, stod(argv[++i])));
        }
        else if (s == "--longest_route_ruin_top_routes" && i + 1 < argc) {
            cfg.longest_route_ruin_top_routes = max(1, stoi(argv[++i]));
        }
        else if (s == "--longest_route_ruin_block_radius" && i + 1 < argc) {
            cfg.longest_route_ruin_block_radius = max(0, stoi(argv[++i]));
        }
        else if (s == "--longest_route_ruin_extra_related" && i + 1 < argc) {
            cfg.longest_route_ruin_extra_related = max(0, stoi(argv[++i]));
        }
        else if (s == "--fragment_lns_euclidean_educate" && i + 1 < argc) {
            cfg.fragment_lns_euclidean_educate = parse_bool_arg(argv[++i]);
        }
        else if (s == "--fragment_lns_educate_swapstar_rounds" && i + 1 < argc) {
            cfg.fragment_lns_educate_swapstar_rounds = max(0, stoi(argv[++i]));
        }
        else if (s == "--fragment_lns_educate_two_opt_star_rounds" && i + 1 < argc) {
            cfg.fragment_lns_educate_two_opt_star_rounds = max(0, stoi(argv[++i]));
        }
        else if (s == "--fragment_lns_educate_deep_rounds" && i + 1 < argc) {
            cfg.fragment_lns_educate_deep_rounds = max(0, stoi(argv[++i]));
        }
        else if (s == "--fragment_lns_educate_swapstar_cap" && i + 1 < argc) {
            cfg.fragment_lns_educate_swapstar_cap = max(1000, stoi(argv[++i]));
        }
        else if (s == "--fragment_lns_educate_two_opt_star_cap" && i + 1 < argc) {
            cfg.fragment_lns_educate_two_opt_star_cap = max(1000, stoi(argv[++i]));
        }

        // ============================================================
        // Metric backend args
        // ============================================================
        else if ((s == "--metric_mode" || s == "--metric") && i + 1 < argc) {
            cfg.metric_mode = argv[++i];

            if (cfg.metric_mode != "road" &&
                cfg.metric_mode != "direct" &&
                cfg.metric_mode != "euclidean") {
                cerr << "Invalid --metric_mode: " << cfg.metric_mode
                    << " expected road/direct/euclidean\n";
                return 2;
            }

            // Important:
            // direct uses explicit arcs.
            // road and euclidean do NOT use direct arcs.
            cfg.use_direct_arc_costs = (cfg.metric_mode == "direct");
        }
        else if (s == "--coords_csv" && i + 1 < argc) {
            cfg.coords_csv = argv[++i];
        }
        else if (s == "--initial_routes_file" && i + 1 < argc) {
            cfg.initial_routes_file = argv[++i];
        }
        else if (s == "--external_depot_earliest" && i + 1 < argc) {
            cfg.external_depot_earliest = stod(argv[++i]);
        }
        else if (s == "--external_depot_latest" && i + 1 < argc) {
            cfg.external_depot_latest = stod(argv[++i]);
        }
        else if (s == "--euclidean_speed_kph" && i + 1 < argc) {
            cfg.euclidean_speed_kph = stod(argv[++i]);
        }
        else if (s == "--require_coords_for_euclidean" && i + 1 < argc) {
            cfg.require_coords_for_euclidean = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_round_distance" && i + 1 < argc) {
            cfg.euclidean_round_distance = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_truncate_1_decimal" && i + 1 < argc) {
            cfg.euclidean_truncate_1_decimal = parse_bool_arg(argv[++i]);
        }
        else if (s == "--solomon_vehicle_penalty" && i + 1 < argc) {
            cfg.solomon_vehicle_penalty = stod(argv[++i]);
        }
        else if (s == "--euclidean_branch_cuts" && i + 1 < argc) {
            cfg.euclidean_branch_cuts = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_candidate_2opt_cut" && i + 1 < argc) {
            cfg.euclidean_candidate_2opt_cut = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_uncross_routes" && i + 1 < argc) {
            cfg.euclidean_uncross_routes = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_uncross_passes" && i + 1 < argc) {
            cfg.euclidean_uncross_passes = max(0, stoi(argv[++i]));
        }
        else if (s == "--euclidean_ranked_insert_cut" && i + 1 < argc) {
            cfg.euclidean_ranked_insert_cut = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_insert_keep" && i + 1 < argc) {
            cfg.euclidean_insert_keep = max(1, stoi(argv[++i]));
        }
        else if (s == "--euclidean_gls_depot_arc_factor" && i + 1 < argc) {
            cfg.euclidean_gls_depot_arc_factor = stod(argv[++i]);
        }

        // Old compatibility flag.
        // Do NOT use this in euclidean runs.
        else if (s == "--use_direct_arc_costs" && i + 1 < argc) {
            bool v = parse_bool_arg(argv[++i]);
            cfg.use_direct_arc_costs = v;

            // Only change metric mode through this old flag if the user has not
            // explicitly requested euclidean before.
            if (v) {
                cfg.metric_mode = "direct";
            }
            else {
                if (cfg.metric_mode != "euclidean") {
                    cfg.metric_mode = "road";
                }
            }
        }
        else if (s == "--use_time_window" && i + 1 < argc) {
            cfg.use_time_window = parse_bool_arg(argv[++i]);
        }
        else if (s == "--use_dense_pair_matrix" && i + 1 < argc) {
            cfg.use_dense_pair_matrix = parse_bool_arg(argv[++i]);
        }
        else if (s == "--use_dirty_route_recompute" && i + 1 < argc) {
            cfg.use_dirty_route_recompute = parse_bool_arg(argv[++i]);
        }
        else if (s == "--gls_time_limit_s" && i + 1 < argc) {
            cfg.gls_time_limit_s = stod(argv[++i]);
        }
        else if (s == "--gls_max_total_moves" && i + 1 < argc) {
            cfg.gls_max_total_moves = stoi(argv[++i]);
        }
        else if (s == "--gls_max_stagnation" && i + 1 < argc) {
            cfg.gls_max_stagnation = stoi(argv[++i]);
        }
        else if (s == "--euclidean_deep_interroute" && i + 1 < argc) {
            cfg.euclidean_deep_interroute = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_deep_interroute_rounds" && i + 1 < argc) {
            cfg.euclidean_deep_interroute_rounds = max(0, stoi(argv[++i]));
        }
        else if (s == "--euclidean_deep_try_relocate" && i + 1 < argc) {
            cfg.euclidean_deep_try_relocate = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_deep_try_swap" && i + 1 < argc) {
            cfg.euclidean_deep_try_swap = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_swapstar" && i + 1 < argc) {
            cfg.euclidean_swapstar = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_swapstar_rounds" && i + 1 < argc) {
            cfg.euclidean_swapstar_rounds = max(0, stoi(argv[++i]));
        }
        else if (s == "--euclidean_swapstar_scan_cap" && i + 1 < argc) {
            cfg.euclidean_swapstar_scan_cap = max(1000, stoi(argv[++i]));
        }
        else if (s == "--euclidean_two_opt_star" && i + 1 < argc) {
            cfg.euclidean_two_opt_star = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_two_opt_star_rounds" && i + 1 < argc) {
            cfg.euclidean_two_opt_star_rounds = max(0, stoi(argv[++i]));
        }
        else if (s == "--euclidean_two_opt_star_scan_cap" && i + 1 < argc) {
            cfg.euclidean_two_opt_star_scan_cap = max(1000, stoi(argv[++i]));
        }
        else if (s == "--use_hgs_lite" && i + 1 < argc) {
            cfg.use_hgs_lite = parse_bool_arg(argv[++i]);
        }
        else if (s == "--hgs_population_size" && i + 1 < argc) {
            cfg.hgs_population_size = max(4, stoi(argv[++i]));
        }
        else if (s == "--hgs_generations" && i + 1 < argc) {
            cfg.hgs_generations = max(0, stoi(argv[++i]));
        }
        else if (s == "--hgs_elite_keep" && i + 1 < argc) {
            cfg.hgs_elite_keep = max(1, stoi(argv[++i]));
        }
        else if (s == "--hgs_mutation_rate" && i + 1 < argc) {
            cfg.hgs_mutation_rate = stod(argv[++i]);
        }
        else if (s == "--hgs_use_order_crossover" && i + 1 < argc) {
            cfg.hgs_use_order_crossover = parse_bool_arg(argv[++i]);
        }
        else if (s == "--hgs_educate_children" && i + 1 < argc) {
            cfg.hgs_educate_children = parse_bool_arg(argv[++i]);
        }
        else if (s == "--hgs_deep_every" && i + 1 < argc) {
            cfg.hgs_deep_every = max(1, stoi(argv[++i]));
        }
        else if (s == "--hgs_child_branch_passes" && i + 1 < argc) {
            cfg.hgs_child_branch_passes = max(0, stoi(argv[++i]));
        }
        else if (s == "--hgs_exact_fleet_split" && i + 1 < argc) {
            cfg.hgs_exact_fleet_split = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_hgs_only" && i + 1 < argc) {
            cfg.euclidean_hgs_only = parse_bool_arg(argv[++i]);
        }
        else if (s == "--use_route_pair_diag" && i + 1 < argc) {
            cfg.use_route_pair_diag = parse_bool_arg(argv[++i]);
        }
        else if (s == "--route_pair_diag_top" && i + 1 < argc) {
            cfg.route_pair_diag_top = max(0, stoi(argv[++i]));
        }
        else if (s == "--route_pair_diag_neighbor_k" && i + 1 < argc) {
            cfg.route_pair_diag_neighbor_k = max(1, stoi(argv[++i]));
        }
        else if (s == "--use_boundary_pair_lns" && i + 1 < argc) {
            cfg.use_boundary_pair_lns = parse_bool_arg(argv[++i]);
        }
        else if (s == "--boundary_pair_lns_rounds" && i + 1 < argc) {
            cfg.boundary_pair_lns_rounds = max(0, stoi(argv[++i]));
        }
        else if (s == "--boundary_pair_lns_top_pairs" && i + 1 < argc) {
            cfg.boundary_pair_lns_top_pairs = max(1, stoi(argv[++i]));
        }
        else if (s == "--boundary_pair_lns_max_remove" && i + 1 < argc) {
            cfg.boundary_pair_lns_max_remove = max(2, stoi(argv[++i]));
        }
        else if (s == "--boundary_pair_lns_add_neighbors" && i + 1 < argc) {
            cfg.boundary_pair_lns_add_neighbors = parse_bool_arg(argv[++i]);
        }
        else if (s == "--boundary_pair_lns_verbose" && i + 1 < argc) {
            cfg.boundary_pair_lns_verbose = parse_bool_arg(argv[++i]);
        }
        else if (s == "--use_boundary_prioritized_education" && i + 1 < argc) {
            cfg.use_boundary_prioritized_education = parse_bool_arg(argv[++i]);
        }
        else if (s == "--boundary_prioritized_top_pairs" && i + 1 < argc) {
            cfg.boundary_prioritized_top_pairs = max(1, stoi(argv[++i]));
        }
        else if (s == "--boundary_prioritized_verbose" && i + 1 < argc) {
            cfg.boundary_prioritized_verbose = parse_bool_arg(argv[++i]);
        }
        else if (s == "--boundary_prioritized_relax_candidate_filter" && i + 1 < argc) {
            cfg.boundary_prioritized_relax_candidate_filter = parse_bool_arg(argv[++i]);
        }
        else if (s == "--use_granular_tabu" && i + 1 < argc) {
            cfg.use_granular_tabu = parse_bool_arg(argv[++i]);
        }
        else if (s == "--granular_tabu_iters" && i + 1 < argc) {
            cfg.granular_tabu_iters = max(0, stoi(argv[++i]));
        }
        else if (s == "--granular_tabu_top_pairs" && i + 1 < argc) {
            cfg.granular_tabu_top_pairs = max(1, stoi(argv[++i]));
        }
        else if (s == "--granular_tabu_customer_radius" && i + 1 < argc) {
            cfg.granular_tabu_customer_radius = max(0, stoi(argv[++i]));
        }
        else if (s == "--granular_tabu_tenure_min" && i + 1 < argc) {
            cfg.granular_tabu_tenure_min = max(1, stoi(argv[++i]));
        }
        else if (s == "--granular_tabu_tenure_max" && i + 1 < argc) {
            cfg.granular_tabu_tenure_max = max(1, stoi(argv[++i]));
        }
        else if (s == "--granular_tabu_worsen_cap" && i + 1 < argc) {
            cfg.granular_tabu_worsen_cap = max(0.0, stod(argv[++i]));
        }
        else if (s == "--granular_tabu_allow_worsen" && i + 1 < argc) {
            cfg.granular_tabu_allow_worsen = parse_bool_arg(argv[++i]);
        }
        else if (s == "--granular_tabu_candidate_cap" && i + 1 < argc) {
            cfg.granular_tabu_candidate_cap = max(4, stoi(argv[++i]));
        }
        else if (s == "--granular_tabu_verbose" && i + 1 < argc) {
            cfg.granular_tabu_verbose = parse_bool_arg(argv[++i]);
        }
        else if (s == "--w_wait" && i + 1 < argc) {
            cfg.w_wait = stod(argv[++i]);
        }
        else if (s == "--tw_use_time_warp" && i + 1 < argc) {
            cfg.tw_use_time_warp = parse_bool_local(argv[++i]);
        }
        else if (s == "--tw_allow_soft_intermediate" && i + 1 < argc) {
            cfg.tw_allow_soft_intermediate = parse_bool_local(argv[++i]);
        }
        else if (s == "--tw_time_warp_penalty" && i + 1 < argc) {
            cfg.tw_time_warp_penalty = stod(argv[++i]);
        }
        else if (s == "--tw_time_warp_penalty_min" && i + 1 < argc) {
            cfg.tw_time_warp_penalty_min = stod(argv[++i]);
        }
        else if (s == "--tw_time_warp_penalty_max" && i + 1 < argc) {
            cfg.tw_time_warp_penalty_max = stod(argv[++i]);
        }
        else if (s == "--tw_time_warp_growth" && i + 1 < argc) {
            cfg.tw_time_warp_growth = stod(argv[++i]);
        }
        else if (s == "--tw_penalize_waiting_in_distance" && i + 1 < argc) {
            cfg.tw_penalize_waiting_in_distance = parse_bool_local(argv[++i]);
        }
        else if (s == "--tw_strict_insertion" && i + 1 < argc) {
            cfg.tw_strict_insertion = parse_bool_arg(argv[++i]);
        }
        else if (s == "--tw_sort_seed_by_window" && i + 1 < argc) {
            cfg.tw_sort_seed_by_window = parse_bool_arg(argv[++i]);
        }
        else if (s == "--tw_lateness_eps" && i + 1 < argc) {
            cfg.tw_lateness_eps = stod(argv[++i]);
        }
        else if (s == "--route_start_time_s" && i + 1 < argc) {
            cfg.route_start_time_s = stod(argv[++i]);
        }
        else if (s == "--route_start_hour" && i + 1 < argc) {
            cfg.route_start_time_s = stod(argv[++i]) * 3600.0;
        }
        else if (s == "--euclidean_time_equals_distance" && i + 1 < argc) {
            cfg.euclidean_time_equals_distance = parse_bool_arg(argv[++i]);
        }
        else {
            cerr << "Unknown or incomplete argument: " << s << "\n";
            return 2;
        }
    }
    }
    catch (const exception &e) {
        cerr << "Invalid command-line argument: " << e.what() << "\n";
        return 2;
    }

    if (cfg.sa_time_limit < 0.0) {
        cerr << "--time_limit must be non-negative\n";
        return 2;
    }
    if (cfg.budget_scope != "search" && cfg.budget_scope != "solve") {
        cerr << "--budget_scope must be search or solve\n";
        return 2;
    }
    if (cfg.alns_destroy_min_ratio < 0.0 ||
        cfg.alns_destroy_max_ratio > 1.0 ||
        cfg.alns_destroy_min_ratio > cfg.alns_destroy_max_ratio) {
        cerr << "ALNS destroy ratios must satisfy 0 <= min <= max <= 1\n";
        return 2;
    }
    if (cfg.lns_benchmark_mode &&
        cfg.lns_benchmark_iterations == 0 &&
        cfg.sa_time_limit <= 0.0) {
        cerr << "LNS benchmark requires --time_limit > 0 or --lns_benchmark_iterations > 0\n";
        return 2;
    }
    if (cfg.lns_benchmark_mode && cfg.hybrid_fast_phase_s > 0.0) {
        cerr << "--hybrid_fast_phase_s cannot be combined with --lns_benchmark_mode true\n";
        return 2;
    }
    if (cfg.hybrid_fast_phase_s > 0.0 && cfg.hard_time_limit_s <= 0.0) {
        cerr << "Hybrid mode requires --hard_time_limit_s > 0\n";
        return 2;
    }
    if (cfg.hybrid_fast_phase_s > 0.0 &&
        cfg.hybrid_fast_phase_s >= cfg.hard_time_limit_s) {
        cerr << "--hybrid_fast_phase_s must be smaller than --hard_time_limit_s\n";
        return 2;
    }
    if (cfg.use_phase_specialized_engine && cfg.lns_benchmark_mode) {
        cerr << "--use_phase_specialized_engine cannot be combined with --lns_benchmark_mode true\n";
        return 2;
    }
    if (cfg.use_phase_specialized_engine && cfg.hybrid_fast_phase_s > 0.0) {
        cerr << "--use_phase_specialized_engine owns structure acquisition; set --hybrid_fast_phase_s 0\n";
        return 2;
    }
    if (cfg.lns_benchmark_destroy_mode < -1 || cfg.lns_benchmark_destroy_mode > 5) {
        cerr << "--lns_benchmark_destroy_mode must be -1 or 0..5\n";
        return 2;
    }
    if (cfg.phase_structure_max_time_s < cfg.phase_structure_min_time_s)
        swap(cfg.phase_structure_max_time_s, cfg.phase_structure_min_time_s);
    if (cfg.phase_structure_destroy_max_ratio < cfg.phase_structure_destroy_min_ratio)
        swap(cfg.phase_structure_destroy_max_ratio, cfg.phase_structure_destroy_min_ratio);
    if (cfg.phase_macro_destroy_max_ratio < cfg.phase_macro_destroy_min_ratio)
        swap(cfg.phase_macro_destroy_max_ratio, cfg.phase_macro_destroy_min_ratio);

    vector<pair<string, string>> output_paths = {
        {"repair_summary_csv", cfg.repair_summary_csv},
        {"repair_trace_csv", cfg.repair_trace_csv},
        {"run_summary_csv", cfg.run_summary_csv},
        {"convergence_csv", cfg.log_convergence ? cfg.convergence_csv : ""}
    };
    for (size_t i = 0; i < output_paths.size(); ++i) {
        if (output_paths[i].second.empty()) continue;
        for (size_t j = i + 1; j < output_paths.size(); ++j) {
            if (!output_paths[j].second.empty() &&
                output_paths[i].second == output_paths[j].second) {
                cerr << "Output files must be distinct: "
                    << output_paths[i].first << " and "
                    << output_paths[j].first << " both use "
                    << output_paths[i].second << "\n";
                return 2;
            }
        }
    }

    if (cfg.lns_benchmark_mode) {
        // Controlled paper benchmark: preserve the production destroy/repair
        // functions, but remove unrelated search stages from the final result.
        cfg.use_alns = true;
        cfg.use_hgs_lite = false;
        cfg.euclidean_hgs_only = false;
        cfg.use_elite_pool = false;
        cfg.use_path_relink = false;
        cfg.use_guided_arc_penalty = false;
        cfg.use_fragment_lns = false;
        cfg.use_route_region_lns = false;
        cfg.use_boundary_pair_lns = false;
        cfg.use_granular_tabu = false;
        cfg.use_boundary_prioritized_education = false;
        cfg.use_interroute_polish = false;
        cfg.use_final_polish = false;
        cfg.use_route_pair_diag = false;

        // Critical isolation: these Euclidean intensification stages otherwise
        // run after the measured LNS loop and contaminate final_objective.
        cfg.euclidean_branch_cuts = false;
        cfg.euclidean_swapstar = false;
        cfg.euclidean_two_opt_star = false;
        cfg.euclidean_deep_interroute = false;

        cfg.hard_time_limit_s = 0.0;
        cfg.no_improve_stop_s = 0.0;
        cfg.target_no_improve_stop_s = 0.0;

        if (cfg.lns_benchmark_disable_post_repair_polish) {
            cfg.use_relocate_polish = false;
            cfg.use_oropt = false;
            cfg.use_2opt = false;
            cfg.use_local_polish = false;
        }
    }

    cerr << "[config] metric_mode=" << cfg.metric_mode
        << " coords_csv=" << cfg.coords_csv
        << " use_direct_arc_costs=" << cfg.use_direct_arc_costs
        << " repair_mode=" << repair_mode_name(effective_repair_mode())
        << " lns_benchmark_mode=" << (cfg.lns_benchmark_mode ? 1 : 0)
        << " hybrid_fast_phase_s=" << cfg.hybrid_fast_phase_s
        << " phase_engine=" << (cfg.use_phase_specialized_engine ? 1 : 0)
        << " phase_structure_fraction=" << cfg.phase_structure_fraction
        << " phase_epoch_s=" << cfg.phase_epoch_s
        << " phase_archive_size=" << cfg.phase_archive_size
        << "\n";

    const auto phase_after_args = Clock::now();
    double phase_input_s = 0.0;
    double phase_backend_s = 0.0;
    double phase_warm_start_s = 0.0;

    Compressed CG;
    int N = 0, M = 0, K = 0, depot_idx = 0;
    vector<int> collections;
    vector<pair<int, int>> virtual_alias_pairs;
    double capacity_input = cfg.truck_capacity;

    if (!(cin >> N >> M)) { cerr << "Bad input (N M)\n"; return 2; }
    if (!(cin >> K)) { cerr << "Bad input (K)\n"; return 2; }
    if (N <= 0 || M < 0 || K <= 0) {
        cerr << "Invalid N/M/K: require N>0, M>=0, K>0\n";
        return 2;
    }
    long long depot_orig;
    if (!(cin >> depot_orig)) { cerr << "Bad input (DEPOT)\n"; return 2; }

    for (int i = 0; i < N; i++) CG.add_node(i, 0, 0, 0);

    vector<tuple<long long, long long, double, double>> raw_edges;
    raw_edges.reserve(M);
    long long max_raw_id = -1;
    for (int i = 0; i < M; i++) {
        long long u, v;
        double d, s;
        if (!(cin >> u >> v >> d >> s)) { cerr << "Bad edge\n"; return 2; }
        if (!isfinite(d) || !isfinite(s) || d < 0.0 || s <= 0.0) {
            cerr << "Invalid edge length/speed at row " << i << "\n";
            return 2;
        }
        raw_edges.emplace_back(u, v, d, s);
        max_raw_id = max(max_raw_id, max(u, v));
    }

    int G;
    if (!(cin >> G)) { cerr << "Bad input (G)\n"; return 2; }
    if (G < 0) { cerr << "Customer count must be non-negative\n"; return 2; }

    struct CustRec {
        long long node;
        double garbage, service_time, earliest, latest;
    };

    vector<CustRec> raw_customers;
    raw_customers.reserve(G);
    long long max_cust_id = -1;
    for (int i = 0; i < G; i++) {
        long long node;
        double garbage, st, e, l;
        if (!(cin >> node >> garbage >> st >> e >> l)) { cerr << "Bad customer\n"; return 2; }
        if (!isfinite(garbage) || !isfinite(st) ||
            !isfinite(e) || !isfinite(l) ||
            garbage < 0.0 || st < 0.0 || e > l) {
            cerr << "Invalid customer data at row " << i << "\n";
            return 2;
        }
        raw_customers.push_back({node, garbage, st, e, l});
        max_cust_id = max(max_cust_id, node);
    }

    if (!(cin >> capacity_input)) { cerr << "Missing capacity\n"; return 2; }
    if (!isfinite(capacity_input) || capacity_input <= 0.0) {
        cerr << "Truck capacity must be positive and finite\n";
        return 2;
    }
    cfg.truck_capacity = capacity_input;
    cfg.num_trucks = K;

    bool assume_one_based = false;
    if (N > 0 && (max_raw_id == N || max_cust_id == N || depot_orig == N)) {
        assume_one_based = true;
    }

    for (auto &t : raw_edges) {
        long long u = get<0>(t), v = get<1>(t);
        double dist = get<2>(t), sp = get<3>(t);
        if (assume_one_based) {
            u--;
            v--;
        }
        if (u < 0 || v < 0 || u >= N || v >= N) {
            cerr << "Edge index outside declared node range [0, "
                << (N - 1) << "]\n";
            return 2;
        }
        CG.add_edge_directed((int)u, (int)v, dist, sp);
    }

    collections.clear();
    unordered_set<long long> normalized_customer_ids;
    for (auto &c : raw_customers) {
        long long node = c.node;
        if (assume_one_based) node--;
        if (node < 0 || node >= N) {
            cerr << "Customer index outside declared node range [0, "
                << (N - 1) << "]\n";
            return 2;
        }
        if (!normalized_customer_ids.insert(node).second) {
            cerr << "Duplicate customer node in input: " << node << "\n";
            return 2;
        }
        double remaining_qty = c.garbage;
        if (remaining_qty <= cfg.truck_capacity + 1e-9) {
            CG.nodes[(int)node].type = 2;
            CG.nodes[(int)node].garbage_amount = remaining_qty;
            CG.nodes[(int)node].service_time_s = c.service_time;
            CG.nodes[(int)node].earliest = c.earliest;
            CG.nodes[(int)node].latest = c.latest;
            collections.push_back((int)node);
        } else {
            if (!cfg.allow_splitting) {
                cerr << "Customer demand exceeds truck capacity and --allow_splitting is disabled: node="
                    << node
                    << " demand=" << remaining_qty
                    << " capacity=" << cfg.truck_capacity
                    << "\n";
                return 2;
            }

            if (cfg.truck_capacity <= 0.0) {
                cerr << "Truck capacity must be positive when splitting oversized customers\n";
                return 2;
            }

            int parts = (int)ceil(remaining_qty / cfg.truck_capacity);
            double left = remaining_qty;
            for (int p = 0; p < parts; p++) {
                double part_qty = min(cfg.truck_capacity, left);
                left -= part_qty;
                int new_idx = CG.add_node((long long)CG.nodes.size(), 0, 0, 0);
                virtual_alias_pairs.push_back({new_idx, (int)node});
                CG.nodes[new_idx].type = 2;
                CG.nodes[new_idx].garbage_amount = part_qty;
                CG.nodes[new_idx].service_time_s = c.service_time;
                CG.nodes[new_idx].earliest = c.earliest;
                CG.nodes[new_idx].latest = c.latest;
                collections.push_back(new_idx);
            }
        }
    }

    if (assume_one_based) depot_orig--;
    if (depot_orig < 0 || depot_orig >= N) {
        cerr << "Depot index outside declared node range [0, "
            << (N - 1) << "]\n";
        return 2;
    }
    depot_idx = (int)depot_orig;
    if (normalized_customer_ids.count(depot_orig)) {
        cerr << "Depot cannot also be listed as a customer\n";
        return 2;
    }
    CG.nodes[depot_idx].type = 1;
    if (cfg.external_depot_earliest >= 0.0) {
        CG.nodes[depot_idx].earliest = cfg.external_depot_earliest;
    }
    if (cfg.external_depot_latest >= 0.0) {
        CG.nodes[depot_idx].latest = cfg.external_depot_latest;
    }

    if (cfg.lns_benchmark_mode && collections.empty()) {
        cerr << "LNS benchmark requires at least one customer\n";
        return 2;
    }

    double total_customer_demand = 0.0;
    for (int node : collections) {
        total_customer_demand += CG.nodes[node].garbage_amount;
    }
    long long trips_per_truck_bound = 1;
    if (cfg.allow_multi_trip) {
        trips_per_truck_bound = cfg.max_trips_per_truck > 0
            ? cfg.max_trips_per_truck
            : numeric_limits<long long>::max();
    }
    if (cfg.capacity_mode == "strict" &&
        trips_per_truck_bound != numeric_limits<long long>::max()) {
        const long double fleet_capacity =
            (long double)cfg.num_trucks *
            (long double)trips_per_truck_bound *
            (long double)cfg.truck_capacity;
        if ((long double)total_customer_demand > fleet_capacity + 1e-9L) {
            cerr << "Aggregate demand exceeds strict fleet capacity: demand="
                << total_customer_demand
                << " fleet_capacity=" << (double)fleet_capacity << "\n";
            return 2;
        }
    }

    node_alias.assign(CG.nodes.size(), -1);
    for (int i = 0; i < (int)node_alias.size(); ++i) {
        node_alias[i] = i;
    }
    for (auto [virtual_node, physical_node] : virtual_alias_pairs) {
        if (virtual_node >= 0 &&
            virtual_node < (int)node_alias.size() &&
            physical_node >= 0 &&
            physical_node < (int)node_alias.size()) {
            node_alias[virtual_node] = physical_node;
        }
    }

    if (CG.nodes.empty()) {
        cerr << "Graph empty\n";
        return 2;
    }

    if (!cfg.coords_csv.empty()) {
        if (!load_coords_csv(CG, cfg.coords_csv)) {
            cerr << "[coords] failed to load coordinate file\n";
            return 2;
        }
    }

    if (!validate_euclidean_coordinates(CG, collections, depot_idx)) {
        return 2;
    }

    // FleetRoute production receipt: one stable, machine-readable line that
    // states the actual operational contract accepted by this binary.  This is
    // observational only; it does not alter search behavior.
    safe_log_line(
        "[SolverConfig] generation=production",
        " objective=", cfg.objective_mode,
        " metric=", cfg.metric_mode,
        " customers=", collections.size(),
        " max_available_trucks=", cfg.num_trucks,
        " capacity=", cfg.truck_capacity,
        " instances=", cfg.sa_instances,
        " hard_budget_s=", cfg.hard_time_limit_s,
        " no_improve_s=", cfg.no_improve_stop_s,
        " budget_scope=", cfg.budget_scope,
        " phase_engine=", (cfg.use_phase_specialized_engine ? 1 : 0),
        " time_windows=", (cfg.use_time_window ? 1 : 0),
        " multi_trip=", (cfg.allow_multi_trip ? 1 : 0),
        " max_trips=", cfg.max_trips_per_truck,
        " route_start_s=", cfg.route_start_time_s,
        " cluster_requested=", (cfg.use_cluster_warm_start ? 1 : 0),
        " convergence=", (cfg.log_convergence ? 1 : 0),
        " convergence_sample_s=", cfg.convergence_sample_period_s,
        " convergence_max_rows=", cfg.convergence_max_rows,
        " road_time_model=static_edge_speed",
        " hybrid_contract=distance_m_plus_0.25_route_duration_s"
    );

    // ------------------------------------------------------------
    // Metric backend setup.
    // For euclidean mode, coordinates must be loaded after all nodes
    // have been created and after depot/customers have been marked.
    // ------------------------------------------------------------

    const auto phase_input_done = Clock::now();
    phase_input_s = chrono::duration<double>(phase_input_done - phase_after_args).count();

    LineGraph LG;
    LG.build_from_compressed(CG);

    PairwiseManager pm(&CG, &LG, 200000);
    ObjectiveEvaluator ev(
        &pm,
        &CG,
        cfg.w_time,
        cfg.w_co2,
        cfg.w_late,
        cfg.w_capacity,
        cfg.co2_per_meter
    );

    if (!metric_is_euclidean()) {
        ValidationReport vr = validate_compressed(CG);
        if (!vr.valid) {
            cerr << "Validation failed: " << vr.message << "\n";
            if (!vr.unreachable_list.empty()) {
                cerr << "Unreachable:";
                for (int x : vr.unreachable_list) cerr << " " << x;
                cerr << "\n";
            }
            return 2;
        }

        // V40: do not precompute all sources twice. Road-mode dense construction
        // owns its single all-source precompute. Direct mode reads explicit arcs.
        if (metric_is_direct()) {
            cerr << "[direct] skipping TDijkstra all-source precompute; using explicit arcs\n";
        }
    } else {
        cerr << "[euclidean] skipping road reachability validation and TDijkstra precompute\n";
    }

    // Important order:
    // dense matrix first, because build_candidate_lists() calls fast_pair_dist().
    // In euclidean mode, fast_pair_dist() must read Euclidean dense_pairs,
    // not fall back to PairwiseManager / TDijkstra.
    build_dense_pair_matrix(CG, pm, find_depot_idx(CG));
    if (!metric_is_euclidean() && !validate_dense_pair_matrix_reachable()) {
        cerr << "Validation failed: required depot/customer pair is unreachable\n";
        return 2;
    }
    build_candidate_lists(CG, pm);

    const auto phase_backend_done = Clock::now();
    phase_backend_s = chrono::duration<double>(phase_backend_done - phase_input_done).count();

    if (cfg.budget_scope == "solve") {
        solver_governor_start();
        safe_log_line("[BudgetScope] solve clock started before warm start");
    }

    if (cfg.use_time_window && cfg.tw_sort_seed_by_window) {
        stable_sort(collections.begin(), collections.end(),
            [&](int a, int b) {
                const NodeC &A = CG.nodes[a];
                const NodeC &B = CG.nodes[b];

                if (fabs(A.latest - B.latest) > 1e-9) {
                    return A.latest < B.latest;
                }

                if (fabs(A.earliest - B.earliest) > 1e-9) {
                    return A.earliest < B.earliest;
                }

                return A.id < B.id;
            }
        );

        cerr << "[TW] collections sorted by latest/earliest windows\n";
    }

    route_metric_cache.mp.clear();
    route_metric_cache.order.clear();
    route_metric_cache.hits = 0;
    route_metric_cache.misses = 0;
    route_metric_cache.puts = 0;

    vector<ConvergenceLogRow> shared_conv_log;
    mutex conv_mtx;

    // Common feasible warm-start baseline. For controlled experiments, an
    // independently generated route file can replace all method-specific starts.
    SolutionState greedy_state(cfg.num_trucks, (int)CG.nodes.size());
    bool used_external_warm_start = false;

    if (!cfg.initial_routes_file.empty()) {
        ifstream rin(cfg.initial_routes_file);
        if (!rin) {
            cerr << "[warm-start] cannot open " << cfg.initial_routes_file << "\n";
            return 2;
        }

        vector<vector<int>> routes(cfg.num_trucks, vector<int>{depot_idx, depot_idx});
        unordered_map<long long, int> orig_to_internal;
        for (int nid = 0; nid < (int)CG.nodes.size(); ++nid) {
            orig_to_internal[CG.nodes[nid].orig_id] = nid;
        }

        vector<int> seen(CG.nodes.size(), 0);
        string line;
        int route_index = 0;
        while (getline(rin, line)) {
            if (line.empty()) continue;
            if (route_index >= cfg.num_trucks) {
                cerr << "[warm-start] route count exceeds fleet limit\n";
                return 2;
            }
            istringstream iss(line);
            long long orig = -1;
            vector<int> route{depot_idx};
            while (iss >> orig) {
                auto it = orig_to_internal.find(orig);
                if (it == orig_to_internal.end()) {
                    cerr << "[warm-start] unknown original node " << orig << "\n";
                    return 2;
                }
                int nid = it->second;
                if (CG.nodes[nid].type != 2 || ++seen[nid] != 1) {
                    cerr << "[warm-start] duplicate/non-customer node " << orig << "\n";
                    return 2;
                }
                route.push_back(nid);
            }
            route.push_back(depot_idx);
            routes[route_index++] = std::move(route);
        }

        for (int c : collections) {
            if (c < 0 || c >= (int)seen.size() || seen[c] != 1) {
                cerr << "[warm-start] customer coverage failure at internal node " << c << "\n";
                return 2;
            }
        }

        greedy_state.routes = std::move(routes);
        recompute_state_metrics_and_loads(greedy_state, ev);
        if (!solution_hard_feasible(greedy_state, CG, pm)) {
            cerr << "[warm-start] supplied routes are not hard feasible\n";
            return 2;
        }
        used_external_warm_start = true;
        cerr << "[warm-start] external feasible routes loaded=" << route_index
            << " objective=" << greedy_state.objective << "\n";
    }

    bool used_cluster_warm_start = false;
    if (!used_external_warm_start) {
        cerr << "[main] cluster warm start check...\n";
        used_cluster_warm_start = build_cluster_warm_start_solution(
            greedy_state,
            collections,
            ev,
            pm
        );
        cerr << "[main] cluster warm start used=" << (used_cluster_warm_start ? 1 : 0) << "\n";
    }

    string baseline_name = used_external_warm_start
        ? "HombergerI1WarmStart"
        : (used_cluster_warm_start ? "ClusterWarmStart" : "Greedy");

    if (!used_external_warm_start && !used_cluster_warm_start) {
        cerr << "[main] building greedy routes...\n";

    auto greedy_routes = greedy_initial_routes(
        CG,
        depot_idx,
        collections,
        cfg.num_trucks,
        cfg.truck_capacity,
        pm
    );

    cerr << "[main] greedy routes built\n";

    // Initial directed 2-opt can be unsafe/slow on asymmetric road graphs.
    // Later local_polish_solution / TripOrderSqueeze handles safer polishing.
    if (cfg.use_2opt && false) {
        cerr << "[main] initial two_opt_all start\n";
        two_opt_all(greedy_routes, ev, pm);
        cerr << "[main] initial two_opt_all done\n";
    }

    for (auto &r : greedy_routes) {
        enforce_trip_separators(r, CG, depot_idx);
    }

    cerr << "[main] greedy separators enforced\n";

    greedy_state.routes = greedy_routes;
    recompute_state_metrics_and_loads(greedy_state, ev);
    if (euclidean_cuts_enabled()) {
        cerr << "[euclidean] branch polish greedy start obj="
            << greedy_state.objective << "\n";

        euclidean_branch_polish_solution(greedy_state, ev, pm);

        cerr << "[euclidean] branch polish greedy end obj="
            << greedy_state.objective << "\n";
    }
    if (metric_is_euclidean() && cfg.use_hgs_lite && !cfg.euclidean_hgs_only) {
        cerr << "[HGS-lite] greedy seed start obj="
            << greedy_state.objective << "\n";

        SolutionState hgs_seed = hgs_lite_euclidean(
            greedy_state,
            CG,
            ev,
            pm,
            cfg.base_seed + 1234567
        );

        if (solution_hard_feasible(hgs_seed, CG, pm) &&
            hgs_seed.objective + 1e-9 < greedy_state.objective) {
            greedy_state = hgs_seed;
            baseline_name = "HGS-lite seed";
        }

        cerr << "[HGS-lite] greedy seed end obj="
            << greedy_state.objective << "\n";
    }

    } else if (!used_external_warm_start) {
        // Optional light cleanup after cluster start.
        for (auto &r : greedy_state.routes) {
            enforce_trip_separators(r, CG, depot_idx);
        }

        recompute_state_metrics_and_loads(greedy_state, ev);
    }

    // E19 construction ensemble: preserve the newer round-robin greedy as the
    // compact readiness probe seed, but allow a validated compact-fill candidate
    // to become the incumbent before Savings/structure acquisition.
    SolutionState phase_raw_greedy_seed = greedy_state;
    recompute_state_metrics_and_loads(phase_raw_greedy_seed, ev);
    const bool phase_raw_greedy_seed_valid = solution_hard_feasible(phase_raw_greedy_seed, CG, pm);
    // UI/evidence-only warm-start trace. This deliberately does NOT publish to
    // global_best_state or touch the anytime governor, so solver behavior and
    // no-improve timing remain unchanged. It exposes the first independently
    // validated construction objective to the live monitor instead of making
    // the curve appear to begin at a later search improvement.
    if (phase_raw_greedy_seed_valid) {
        safe_log_line(
            "[EvidenceWarmStart] time_s=", setprecision(15), solver_elapsed_seconds(),
            " objective=", setprecision(15), phase_raw_greedy_seed.objective,
            " event=", (used_external_warm_start ? "external_validated_start"
                       : used_cluster_warm_start ? "cluster_validated_start"
                       : "greedy_validated_start")
        );
    }
    SolutionState phase_structural_construct_seed;
    bool phase_structural_construct_seed_valid = false;

    if (!used_external_warm_start && cfg.use_phase_specialized_engine &&
        !metric_is_euclidean() && !cfg.allow_multi_trip) {
        auto compact_routes = phase_compact_fill_greedy_routes(
            CG, depot_idx, collections, cfg.num_trucks, cfg.truck_capacity, pm);
        if (!compact_routes.empty()) {
            SolutionState compact_state(cfg.num_trucks, (int)CG.nodes.size());
            compact_state.routes = std::move(compact_routes);
            recompute_state_metrics_and_loads(compact_state, ev);
            const bool ok = solution_hard_feasible(compact_state, CG, pm);
            safe_log_line("[PhaseConstruct-E25] kind=compact_fill objective=",
                          compact_state.objective, " feasible=", (ok?1:0),
                          " raw_round_robin=", greedy_state.objective);
            if (ok && compact_state.objective + 1e-9 < greedy_state.objective) {
                greedy_state = std::move(compact_state);
                baseline_name = "PhaseCompactFill";
                safe_log_line(
                    "[EvidenceWarmStart] time_s=", setprecision(15), solver_elapsed_seconds(),
                    " objective=", setprecision(15), greedy_state.objective,
                    " event=compact_fill_validated_improvement"
                );
            }
        }
    }

    SolutionState phase_entry_probe_seed;
    bool phase_entry_probe_seed_valid = false;
    if (cfg.use_phase_specialized_engine && !metric_is_euclidean() &&
        phase_raw_greedy_seed_valid) {
        phase_entry_probe_seed = phase_raw_greedy_seed;
        phase_entry_probe_seed_valid = true;
    }

    const bool phase_auto_savings =
        cfg.use_phase_specialized_engine && cfg.phase_readiness_gate &&
        cfg.phase_entry_try_savings && !metric_is_euclidean() &&
        (int)collections.size() <= cfg.phase_entry_savings_max_customers;

    if (!used_external_warm_start && (cfg.use_savings_warm_start || phase_auto_savings)) {
        if (phase_auto_savings && !phase_entry_probe_seed_valid) {
            phase_entry_probe_seed = greedy_state;
            recompute_state_metrics_and_loads(phase_entry_probe_seed, ev);
            phase_entry_probe_seed_valid = solution_hard_feasible(phase_entry_probe_seed, CG, pm);
        }
        cerr << "[main] savings warm start check..."
             << (phase_auto_savings && !cfg.use_savings_warm_start ? " [E25 auto-entry]" : "")
             << "\n";

        SolutionState savings_state(
            cfg.num_trucks,
            (int)CG.nodes.size()
        );

        bool savings_ok = build_savings_warm_start_solution(
            savings_state,
            CG,
            depot_idx,
            collections,
            ev,
            pm,
            cfg.base_seed + 424242u
        );

        cerr << "[main] savings warm start used="
            << (savings_ok ? 1 : 0);
        bool savings_status_line_closed = false;

        if (savings_ok) {
            int savings_active = 0;
            for (const auto &r : savings_state.routes)
                if (route_customer_count_hard(r, CG) > 0) ++savings_active;
            cerr << " obj=" << savings_state.objective
                 << " active_routes=" << savings_active;
            const double old_obj = greedy_state.objective;

            take_if_better_feasible(
                greedy_state,
                savings_state,
                ev,
                pm
            );

            if (greedy_state.objective + 1e-9 < old_obj) {
                baseline_name = "Savings";
                cerr << " improved_old=" << old_obj
                    << " new=" << greedy_state.objective << "\n";
                savings_status_line_closed = true;
                safe_log_line(
                    "[EvidenceWarmStart] time_s=", setprecision(15), solver_elapsed_seconds(),
                    " objective=", setprecision(15), greedy_state.objective,
                    " event=savings_validated_improvement"
                );
            }
        }

        if (!savings_status_line_closed) cerr << "\n";
    }

    if (!used_external_warm_start && cfg.use_phase_specialized_engine &&
        !metric_is_euclidean() && (int)collections.size() >= cfg.phase_structure_min_customers) {
        phase_structural_construct_seed_valid = build_truncated_savings_exploration_seed(
            phase_structural_construct_seed, CG, depot_idx, collections, ev, pm,
            515928u); // E25 fixed construction RNG: same structural launch geometry across solver seeds.
        if (phase_structural_construct_seed_valid) {
            int active = 0;
            for (const auto &r : phase_structural_construct_seed.routes)
                if (route_customer_count_hard(r, CG) > 0) ++active;
            safe_log_line("[PhaseConstruct-E25] kind=truncated_savings_explore objective=",
                          phase_structural_construct_seed.objective,
                          " active_routes=", active,
                          " incumbent=", greedy_state.objective);
        }
    }

    if (cfg.verbose_trip_order) {
        print_routes(greedy_state);
    }

    RunSummary greedy_summary;
    greedy_summary.name = baseline_name;
    greedy_summary.objective = greedy_state.objective;
    greedy_summary.distance_m = 0;
    greedy_summary.co2_g = 0;
    for (size_t r = 0; r < greedy_state.routes.size(); ++r) {
        auto rm = ev.compute_route_metrics(greedy_state.routes[r], greedy_state.route_max_trip_load[r]);
        greedy_summary.distance_m += rm.distance_m;
        greedy_summary.co2_g += rm.co2_g;
    }

    // E11 keeps Euclidean on its audited branch, but road instances of every
    // size may use the phase engine. Compact cases enter through the cheap
    // readiness probe rather than immediately launching the full portfolio.
    if (cfg.use_phase_specialized_engine && metric_is_euclidean()) {
        safe_log_line("[PhaseEngine-E32] BYPASS customers=", collections.size(),
                      " metric=", cfg.metric_mode,
                      " action=retain_euclidean_pipeline");
        cfg.use_phase_specialized_engine = false;
    }

    const auto phase_warm_done = Clock::now();
    phase_warm_start_s = chrono::duration<double>(phase_warm_done - phase_backend_done).count();

    // Search scope preserves the paper-compatible zero point. Solve scope was
    // already started before warm-start construction and is deliberately not reset.
    if (cfg.budget_scope == "search") {
        solver_governor_start();
        safe_log_line("[BudgetScope] search clock started after warm start");
    }
    update_global_best_checked(greedy_state, CG, pm);

    cerr << "[Anytime] hard_time_limit_s=" << cfg.hard_time_limit_s
        << " no_improve_stop_s=" << cfg.no_improve_stop_s
        << " target_objective=" << cfg.target_objective
        << " target_no_improve_stop_s=" << cfg.target_no_improve_stop_s
        << " meaningful_gain_abs=" << cfg.meaningful_gain_abs
        << " meaningful_gain_rel=" << cfg.meaningful_gain_rel
        << "\n";

    // V56 capability diagnostic.  This deliberately runs before the production
    // pipeline and exits, so no probe result can leak into a later benchmark.
    // Probes share only the exact supplied start state and equal wall time.
    if (!cfg.diagnostic_probe_csv.empty()) {
        if (!used_external_warm_start) {
            cerr << "[DiagnosticProbe] requires --initial_routes_file\n";
            return 2;
        }
        const SolutionState probe_base = greedy_state;
        const double probe_budget = max(0.01, cfg.diagnostic_probe_budget_s);
        const double saved_hard = cfg.hard_time_limit_s;
        const bool saved_stop = solver_stop_requested.load(memory_order_relaxed);
        cfg.hard_time_limit_s = 0.0;
        solver_stop_requested.store(false, memory_order_relaxed);

        ofstream dout(cfg.diagnostic_probe_csv);
        if (!dout) {
            cerr << "[DiagnosticProbe] cannot open " << cfg.diagnostic_probe_csv << "\n";
            return 2;
        }
        dout << "probe,start_objective,end_objective,gain,start_used_trucks,end_used_trucks,start_distance,end_distance,wall_s,feasible\n";

        auto used_count = [&](const SolutionState &s) {
            int k = 0;
            for (const auto &r : s.routes) if (route_customer_count_hard(r, CG) > 0) ++k;
            return k;
        };
        auto total_distance = [&](const SolutionState &s) {
            double d = 0.0;
            for (size_t rr = 0; rr < s.routes.size(); ++rr) {
                const double load = rr < s.route_max_trip_load.size() ? s.route_max_trip_load[rr] : 0.0;
                d += ev.compute_route_metrics(s.routes[rr], load).distance_m;
            }
            return d;
        };
        auto reset_probe_global = [&]() {
            lock_guard<mutex> lk(global_best_mutex);
            global_best_state = probe_base;
        };
        auto emit_probe = [&](const string &name, SolutionState cand, double wall) {
            recompute_state_metrics_and_loads(cand, ev);
            const bool feas = solution_hard_feasible(cand, CG, pm);
            const double sdist = total_distance(probe_base);
            const double edist = feas ? total_distance(cand) : INF_D;
            dout << name << "," << setprecision(15) << probe_base.objective << ","
                 << (feas ? cand.objective : INF_D) << ","
                 << (feas ? probe_base.objective - cand.objective : -INF_D) << ","
                 << used_count(probe_base) << "," << (feas ? used_count(cand) : -1) << ","
                 << sdist << "," << edist << "," << wall << "," << (feas ? 1 : 0) << "\n";
            if (feas) {
                ofstream rout(cfg.diagnostic_probe_csv + "." + name + ".routes");
                if (rout) {
                    for (const auto &route : cand.routes) {
                        bool wrote = false;
                        for (int node : route) {
                            if (node < 0 || node >= (int)CG.nodes.size()) continue;
                            if (CG.nodes[node].type != 2) continue;
                            if (wrote) rout << ' ';
                            rout << CG.nodes[node].orig_id;
                            wrote = true;
                        }
                        if (wrote) rout << "\n";
                    }
                }
            }
            cerr << "[DiagnosticProbe] " << name
                 << " gain=" << (feas ? probe_base.objective - cand.objective : -INF_D)
                 << " wall=" << wall << " feasible=" << (feas ? 1 : 0) << "\n";
        };
        auto probe = [&](const string &name, auto &&fn) {
            reset_probe_global();
            solver_stop_requested.store(false, memory_order_relaxed);
            SolutionState cand = probe_base;
            const auto t0p = Clock::now();
            { ScopedWorkerDeadline cap(probe_budget); fn(cand); }
            const double wall = chrono::duration<double>(Clock::now() - t0p).count();
            emit_probe(name, std::move(cand), wall);
        };

        probe("local_polish", [&](SolutionState &c) { local_polish_solution(c, ev, pm); });
        probe("interroute_polish", [&](SolutionState &c) { interroute_polish_solution(c, ev, pm); });
        probe("adaptive_lns", [&](SolutionState &c) { adaptive_lns_polish(c, ev, pm, max(1, cfg.alns_rounds), cfg.base_seed ^ 0xA11A5u); });
        probe("fragment_lns", [&](SolutionState &c) { fragment_lns_search(c, ev, pm); });
        probe("granular_tabu", [&](SolutionState &c) { granular_tabu_repair(c, ev, pm); });
        probe("route_region", [&](SolutionState &c) { route_region_lns_descent(c, ev, pm); });
        probe("boundary_pair", [&](SolutionState &c) { boundary_pair_lns_descent(c, ev, pm); });
        probe("final_refinement", [&](SolutionState &c) { final_refinement_pass(c, ev, pm); });

        auto probe_algo = [&](const string &name, auto &&fn) {
            reset_probe_global();
            solver_stop_requested.store(false, memory_order_relaxed);
            const auto t0p = Clock::now();
            AlgoResult r = fn();
            const double wall = chrono::duration<double>(Clock::now() - t0p).count();
            emit_probe(name, std::move(r.best_state), wall);
        };
        probe_algo("fast_lns", [&]() {
            return run_parallel_fast_worker_v41(probe_base, ev, pm, probe_budget, cfg.base_seed ^ 0xFA571u, nullptr, nullptr);
        });
        probe_algo("sa_structural", [&]() {
            return sa_worker(CG, pm, ev, depot_idx, collections, cfg.base_seed ^ 0x510001u, probe_budget, cfg.use_cross2, &probe_base, nullptr, nullptr, 0);
        });
        probe_algo("sa_exploiter", [&]() {
            return sa_worker(CG, pm, ev, depot_idx, collections, cfg.base_seed ^ 0x510003u, probe_budget, cfg.use_cross2, &probe_base, nullptr, nullptr, 3);
        });
        probe_algo("sa_explorer", [&]() {
            return sa_worker(CG, pm, ev, depot_idx, collections, cfg.base_seed ^ 0x510005u, probe_budget, cfg.use_cross2, &probe_base, nullptr, nullptr, max(0, cfg.sa_instances - 1));
        });

        cfg.hard_time_limit_s = saved_hard;
        solver_stop_requested.store(saved_stop, memory_order_relaxed);
        dout.close();
        cerr << "[DiagnosticProbe] complete csv=" << cfg.diagnostic_probe_csv << "\n";
        return 0;
    }

    // Optional phase-specialized handoff: run the proven high-throughput
    // greedy-fast LNS kernel first, then continue the unchanged deep engine
    // from the exact incumbent under one continuous global search clock.
    if (!cfg.lns_benchmark_mode && cfg.hybrid_fast_phase_s > 0.0) {
        const double phase_budget = min(
            cfg.hybrid_fast_phase_s,
            max(0.0, cfg.hard_time_limit_s - 1e-6)
        );

        cerr << "[HybridPhase] begin phase=fast_lns"
            << " budget_s=" << phase_budget
            << " start_objective=" << greedy_state.objective
            << " start_hash=" << solution_route_hash(greedy_state)
            << " elapsed=" << solver_elapsed_seconds() << "s\n";

        reset_repair_benchmark_counters();
        bool old_lns_benchmark_mode = cfg.lns_benchmark_mode;
        RepairMode old_repair_mode = cfg.repair_mode;
        bool old_full_scan = cfg.lns_benchmark_full_scan_exact_repairs;
        bool old_disable_post_polish = cfg.lns_benchmark_disable_post_repair_polish;
        double old_destroy_min = cfg.alns_destroy_min_ratio;
        double old_destroy_max = cfg.alns_destroy_max_ratio;

        // Make the hybrid prefix algorithmically identical to standalone FAST.
        // Standalone FAST runs with lns_benchmark_mode=true, which is also
        // what disables the per-repair local polish below.
        cfg.lns_benchmark_mode = true;
        cfg.repair_mode = RepairMode::GREEDY_FAST;
        cfg.lns_benchmark_full_scan_exact_repairs = true;
        cfg.lns_benchmark_disable_post_repair_polish = true;
        cfg.alns_destroy_min_ratio = 0.04;
        cfg.alns_destroy_max_ratio = 0.16;

        cerr << "[HybridFastConfig]"
            << " lns_benchmark_mode=" << (cfg.lns_benchmark_mode ? 1 : 0)
            << " post_repair_polish="
            << (cfg.lns_benchmark_disable_post_repair_polish ? 0 : 1)
            << " full_scan_exact_repairs="
            << (cfg.lns_benchmark_full_scan_exact_repairs ? 1 : 0)
            << " repair_mode=greedy_fast"
            << " destroy_min=" << setprecision(15) << cfg.alns_destroy_min_ratio
            << " destroy_max=" << setprecision(15) << cfg.alns_destroy_max_ratio
            << " candidate_k=" << cfg.candidate_k
            << " route_probe_k=" << cfg.candidate_route_probe_k
            << " route_cap=" << cfg.insertion_route_cap
            << " position_cap=" << cfg.insertion_pos_cap
            << " topk_exact=" << cfg.insertion_topk_exact
            << " simd=" << (cfg.use_simd_insertion_rank ? 1 : 0)
            << "\n";

        AlgoResult fast_phase = run_lns_repair_benchmark(
            greedy_state,
            ev,
            pm,
            phase_budget,
            cfg.base_seed + 909090u,
            &shared_conv_log,
            &conv_mtx
        );

        cfg.lns_benchmark_mode = old_lns_benchmark_mode;
        cfg.repair_mode = old_repair_mode;
        cfg.lns_benchmark_full_scan_exact_repairs = old_full_scan;
        cfg.lns_benchmark_disable_post_repair_polish = old_disable_post_polish;
        cfg.alns_destroy_min_ratio = old_destroy_min;
        cfg.alns_destroy_max_ratio = old_destroy_max;

        recompute_state_metrics_and_loads(fast_phase.best_state, ev);
        const bool handoff_feasible = solution_hard_feasible(
            fast_phase.best_state, CG, pm
        );
        if (!handoff_feasible) {
            cerr << "[HybridPhase] fast incumbent infeasible; retaining common warm start\n";
        }
        else {
            greedy_state = std::move(fast_phase.best_state);
            recompute_state_metrics_and_loads(greedy_state, ev);
            update_global_best_checked(greedy_state, CG, pm);
        }

        cerr << "[HybridHandoff] feasible="
            << (handoff_feasible ? "YES" : "NO")
            << " objective=" << setprecision(15) << greedy_state.objective
            << " route_hash=" << solution_route_hash(greedy_state)
            << " elapsed=" << setprecision(15) << solver_elapsed_seconds() << "s"
            << " destination=deep_engine\n";

        append_convergence_row(&shared_conv_log, &conv_mtx, {
            solver_elapsed_seconds(), cfg.base_seed + 909090u,
            (long long)fast_phase.iterations, greedy_state.objective,
            greedy_state.objective, 0.0, fast_phase.accepted_moves,
            fast_phase.attempted_moves,
            max(0LL, fast_phase.attempted_moves - fast_phase.accepted_moves),
            "hybrid_handoff"
        });
    }

    // V48: protect the reserved final intensification window against *all*
    // pre-tail search stages. V47 only subtracted the reserve from filler
    // saturation, so the two primary SA variants/final-SA could consume T
    // before the parallel tail started.
    auto pre_tail_stage_budget = [&](double requested) -> double {
        if (requested <= 0.0) return 0.0;
        if (cfg.hard_time_limit_s <= 0.0) return requested;
        const double reserve = max(0.0, min(cfg.final_intensification_reserve_s, cfg.hard_time_limit_s));
        const double available = cfg.hard_time_limit_s - reserve - solver_elapsed_seconds();
        return max(0.0, min(requested, available));
    };

    // SA variants
    auto run_sa_variant = [&](bool use_cross) -> RunSummary {
        int instances = max(1, cfg.sa_instances);
        vector<thread> threads;
        vector<AlgoResult> results(instances);
        mutex results_mtx;
        const double stage_budget = pre_tail_stage_budget(cfg.sa_time_limit);
        safe_log_line("[StageBudget-V51] name=", (use_cross ? "SA_full" : "SA_no_cross"),
                      " requested=", cfg.sa_time_limit, " granted=", stage_budget,
                      " elapsed=", solver_elapsed_seconds(),
                      " reserve=", cfg.final_intensification_reserve_s,
                      " fast_lane=", (cfg.use_parallel_fast_worker && instances >= 2 ? 1 : 0));

        if (solver_should_stop() || stage_budget <= 1e-4) {
            RunSummary stopped;
            stopped.name = use_cross ? "SA_full" : "SA_no_cross";
            stopped.objective = INF_D;
            stopped.distance_m = INF_D;
            stopped.co2_g = INF_D;
            stopped.runtime = 0.0;
            stopped.iterations = 0;
            stopped.accepted = 0;
            stopped.attempted = 0;
            return stopped;
        }

        for (int i = 0; i < instances; ++i) {
            if (solver_should_stop()) break;

            unsigned seed = cfg.base_seed + i * 10007;

            threads.emplace_back([&, i, seed]() {
                AlgoResult r;
                const bool stage_fast_lane = cfg.use_parallel_fast_worker &&
                    instances >= 2 && i == instances - 1;
                if (stage_fast_lane) {
                    // V49: keep one high-throughput feasible lane alive during the
                    // second primary stage instead of waiting until saturation/tail.
                    // This gives RC-like TW landscapes breadth without serially
                    // removing time from the other five deep workers.
                    r = run_parallel_fast_worker_v41(
                        greedy_state, ev, pm, stage_budget, seed + 0x51F17u,
                        &shared_conv_log, &conv_mtx
                    );
                } else {
                    r = sa_worker(
                        CG, pm, ev, depot_idx, collections,
                        seed, stage_budget, use_cross, &greedy_state,
                        &shared_conv_log, &conv_mtx, i
                    );
                }

                recompute_state_metrics_and_loads(r.best_state, ev);

                if (solution_hard_feasible(r.best_state, CG, pm)) {
                    update_global_best_checked(r.best_state, CG, pm);
                } else {
                    cerr << "[THREAD INVALID] "
                        << (use_cross ? "SA_full" : "SA_no_cross")
                        << " obj=" << r.best_state.objective
                        << " ignored before global best\n";
                }

                lock_guard<mutex> lk(results_mtx);
                results[i] = r;
            });
        }

        for (auto &th : threads) {
            if (th.joinable()) th.join();
        }

        bool first = true;
        AlgoResult best_r;

        for (auto &r : results) {
            recompute_state_metrics_and_loads(r.best_state, ev);

            if (!solution_hard_feasible(r.best_state, CG, pm)) {
                continue;
            }

            if (first || r.best_state.objective < best_r.best_state.objective) {
                best_r = r;
                first = false;
            }
        }

        RunSummary s;
        s.name = use_cross ? "SA_full" : "SA_no_cross";
        s.objective = INF_D;
        s.distance_m = INF_D;
        s.co2_g = INF_D;
        s.runtime = 0.0;
        s.iterations = 0;
        s.accepted = 0;
        s.attempted = 0;

        if (first) {
            cerr << "[RUN INVALID] " << s.name
                << " found no feasible candidate\n";
            return s;
        }

        // V37: no unbudgeted outer refinement here. Each sa_worker already
        // transactionally refines its hard-feasible incumbent under its own
        // ScopedWorkerDeadline. The previous second refinement occurred after
        // all worker joins with no stage-local deadline and could make a nominal
        // 1-2 s SA stage consume several extra seconds.
        recompute_state_metrics_and_loads(best_r.best_state, ev);

        update_global_best_checked(best_r.best_state, CG, pm);

        s.objective = best_r.best_state.objective;
        s.distance_m = 0.0;
        s.co2_g = 0.0;

        for (size_t rr = 0; rr < best_r.best_state.routes.size(); ++rr) {
            auto rm = ev.compute_route_metrics(
                best_r.best_state.routes[rr],
                best_r.best_state.route_max_trip_load[rr]
            );
            s.distance_m += rm.distance_m;
            s.co2_g += rm.co2_g;
        }

        s.runtime = best_r.runtime_sec;
        s.iterations = best_r.iterations;
        s.accepted = best_r.accepted_moves;
        s.attempted = best_r.attempted_moves;

        return s;
    };

    RunSummary sa_no_cross;
    RunSummary sa_full;
    RunSummary best_overall;
    AlgoResult final_sa;

    vector<double> stability_objs;
    double mean_obj = 0.0;
    double std_obj = 0.0;

    if (cfg.use_phase_specialized_engine && !cfg.lns_benchmark_mode) {
        final_sa = run_phase_specialized_engine_e23(
            greedy_state,
            phase_entry_probe_seed_valid ? &phase_entry_probe_seed : nullptr,
            phase_structural_construct_seed_valid ? &phase_structural_construct_seed : nullptr,
            CG, pm, ev, depot_idx, collections,
            &shared_conv_log, &conv_mtx
        );
        recompute_state_metrics_and_loads(final_sa.best_state, ev);
        if (!solution_hard_feasible(final_sa.best_state, CG, pm)) {
            safe_log_line("[PhaseEngine-E32] invalid final candidate; fallback warm start");
            final_sa.best_state = greedy_state;
            recompute_state_metrics_and_loads(final_sa.best_state, ev);
        }
        update_global_best_checked(final_sa.best_state, CG, pm);

        sa_no_cross = greedy_summary;
        sa_no_cross.name = "PhaseEngine_seed";
        sa_full = greedy_summary;
        sa_full.name = "PhaseEngine_seed_copy";
        best_overall = evaluate_state(final_sa.best_state, ev, CG);
        best_overall.name = "PhaseSpecialized_E25";
        best_overall.runtime = final_sa.runtime_sec;
        best_overall.iterations = final_sa.iterations;
        best_overall.accepted = final_sa.accepted_moves;
        best_overall.attempted = final_sa.attempted_moves;
    }
    else if (cfg.lns_benchmark_mode) {
        reset_repair_benchmark_counters();
        repair_benchmark_seed_name = baseline_name;
        repair_benchmark_graph_nodes = (int)CG.nodes.size();
        repair_benchmark_graph_edges = (int)CG.edges.size();
        repair_benchmark_customer_count = (int)collections.size();

        cerr << "[LNS-Benchmark] mode="
            << repair_mode_name(effective_repair_mode())
            << " budget_s=" << cfg.sa_time_limit
            << " fixed_iterations=" << cfg.lns_benchmark_iterations
            << " post_repair_polish="
            << (cfg.lns_benchmark_disable_post_repair_polish ? 0 : 1)
            << "\n";

        AlgoResult lns_result = run_lns_repair_benchmark(
            greedy_state,
            ev,
            pm,
            cfg.sa_time_limit,
            cfg.base_seed + 909090u,
            &shared_conv_log,
            &conv_mtx
        );

        recompute_state_metrics_and_loads(lns_result.best_state, ev);

        if (!solution_hard_feasible(lns_result.best_state, CG, pm)) {
            cerr << "[LNS-Benchmark] infeasible result; falling back to warm start\n";
            lns_result.best_state = greedy_state;
            recompute_state_metrics_and_loads(lns_result.best_state, ev);
        }

        update_global_best_checked(lns_result.best_state, CG, pm);

        sa_no_cross = greedy_summary;
        sa_no_cross.name = "LNS_seed";
        sa_full = greedy_summary;
        sa_full.name = "LNS_seed_copy";

        best_overall.name = string("LNS_") +
            repair_mode_name(effective_repair_mode());
        best_overall.objective = lns_result.best_state.objective;
        best_overall.distance_m = 0.0;
        best_overall.co2_g = 0.0;
        best_overall.runtime = lns_result.runtime_sec;
        best_overall.iterations = lns_result.iterations;
        best_overall.accepted = lns_result.accepted_moves;
        best_overall.attempted = lns_result.attempted_moves;

        for (size_t r = 0; r < lns_result.best_state.routes.size(); ++r) {
            const auto rm = ev.compute_route_metrics(
                lns_result.best_state.routes[r],
                lns_result.best_state.route_max_trip_load[r]
            );
            best_overall.distance_m += rm.distance_m;
            best_overall.co2_g += rm.co2_g;
        }

        final_sa = lns_result;
    }
    else if (metric_is_euclidean() && cfg.euclidean_hgs_only) {
        cerr << "[HGS-only] skipping SA/GLS/FragmentLNS pipeline\n";

        SolutionState hgs_only_state = greedy_state;
        recompute_state_metrics_and_loads(hgs_only_state, ev);

        if (cfg.use_hgs_lite) {
            hgs_only_state = hgs_lite_euclidean(
                greedy_state,
                CG,
                ev,
                pm,
                cfg.base_seed + 7654321
            );

            recompute_state_metrics_and_loads(hgs_only_state, ev);
        }

        if (cfg.euclidean_swapstar) {
            int old_rounds = cfg.euclidean_swapstar_rounds;
            int old_scan_cap = cfg.euclidean_swapstar_scan_cap;

            cfg.euclidean_swapstar_rounds = min(old_rounds, 10);
            cfg.euclidean_swapstar_scan_cap = min(old_scan_cap, 80000);

            euclidean_swapstar_descent(hgs_only_state, ev, pm);

            cfg.euclidean_swapstar_rounds = old_rounds;
            cfg.euclidean_swapstar_scan_cap = old_scan_cap;
            recompute_state_metrics_and_loads(hgs_only_state, ev);
            if (cfg.euclidean_two_opt_star) {
                int old_rounds = cfg.euclidean_two_opt_star_rounds;
                int old_scan_cap = cfg.euclidean_two_opt_star_scan_cap;

                cfg.euclidean_two_opt_star_rounds = min(old_rounds, 10);
                cfg.euclidean_two_opt_star_scan_cap = min(old_scan_cap, 120000);

                euclidean_two_opt_star_descent(hgs_only_state, ev, pm);

                cfg.euclidean_two_opt_star_rounds = old_rounds;
                cfg.euclidean_two_opt_star_scan_cap = old_scan_cap;

                recompute_state_metrics_and_loads(hgs_only_state, ev);
            }
        }

        if (cfg.euclidean_deep_interroute) {
            int old_rounds = cfg.euclidean_deep_interroute_rounds;
            cfg.euclidean_deep_interroute_rounds = min(old_rounds, 8);

            euclidean_deep_interroute_descent(hgs_only_state, ev, pm);

            cfg.euclidean_deep_interroute_rounds = old_rounds;
            recompute_state_metrics_and_loads(hgs_only_state, ev);
        }

        if (!solution_hard_feasible(hgs_only_state, CG, pm)) {
            cerr << "[HGS-only] infeasible result, falling back to greedy_state\n";

            hgs_only_state = greedy_state;
            recompute_state_metrics_and_loads(hgs_only_state, ev);
        }

        sa_no_cross = greedy_summary;
        sa_no_cross.name = "SA_no_cross";

        sa_full = greedy_summary;
        sa_full.name = "SA_full";

        best_overall.name = "HGS_only";
        best_overall.objective = hgs_only_state.objective;
        best_overall.distance_m = 0.0;
        best_overall.co2_g = 0.0;
        best_overall.runtime = 0.0;
        best_overall.iterations = 0;
        best_overall.accepted = 0;
        best_overall.attempted = 0;

        for (size_t r = 0; r < hgs_only_state.routes.size(); ++r) {
            auto rm = ev.compute_route_metrics(
                hgs_only_state.routes[r],
                hgs_only_state.route_max_trip_load[r]
            );

            best_overall.distance_m += rm.distance_m;
            best_overall.co2_g += rm.co2_g;
        }

        final_sa.best_state = hgs_only_state;
        final_sa.runtime_sec = 0.0;
        final_sa.iterations = 0;
        final_sa.accepted_moves = 0;
        final_sa.attempted_moves = 0;
        final_sa.drift_corrections = 0;
        final_sa.capacity_violations = 0;
        final_sa.total_overload = 0.0;
    }
    else {
        sa_no_cross = run_sa_variant(false);
        if (!solver_should_stop()) {
            sa_full = run_sa_variant(cfg.use_cross2);
        }

        for (int k = 0; k < cfg.stability_runs && !solver_should_stop(); k++) {
            unsigned seed = cfg.base_seed + 100000 + k * 7919;

            const double stability_budget = pre_tail_stage_budget(cfg.sa_time_limit);
            if (stability_budget <= 1e-4) break;
            AlgoResult r = sa_worker(
                CG,
                pm,
                ev,
                depot_idx,
                collections,
                seed,
                stability_budget,
                cfg.use_cross2,
                &greedy_state,
                &shared_conv_log,
                &conv_mtx,
                k % max(1, cfg.sa_instances)
            );

            // V37: sa_worker already performed transactional refinement under
            // its local deadline; do not run another unbudgeted pass here.
            recompute_state_metrics_and_loads(r.best_state, ev);

            if (solution_hard_feasible(r.best_state, CG, pm)) {
                update_global_best_checked(r.best_state, CG, pm);
                stability_objs.push_back(r.best_state.objective);
            }
            else {
                cerr << "[STABILITY INVALID] obj="
                    << r.best_state.objective
                    << " ignored because infeasible\n";
            }
        }

        if (!stability_objs.empty()) {
            for (double v : stability_objs) {
                mean_obj += v;
            }

            mean_obj /= (double)stability_objs.size();

            for (double v : stability_objs) {
                std_obj += (v - mean_obj) * (v - mean_obj);
            }

            std_obj = sqrt(std_obj / (double)stability_objs.size());
        }

        vector<RunSummary> all = {
            greedy_summary,
            sa_no_cross,
            sa_full
        };

        best_overall = RunSummary{};

        for (const auto &r : all) {
            if (!valid_run_summary(r)) {
                continue;
            }

            if (!valid_run_summary(best_overall) ||
                r.objective + 1e-9 < best_overall.objective) {
                best_overall = r;
            }
        }

        if (!valid_run_summary(best_overall)) {
            best_overall = greedy_summary;
        }

        // V51: under a hard fixed budget, do not spend the remaining pre-tail
        // window on a single final-SA worker. The following saturation stage can
        // use all configured workers (including structural/FAST roles) and is
        // strictly more work-conserving on multicore hardware. Keep final-SA only
        // for unlimited/offline runs.
        const double final_sa_budget = pre_tail_stage_budget(cfg.sa_time_limit);
        if (cfg.hard_time_limit_s <= 0.0 && !solver_should_stop() && final_sa_budget > 1e-4) {
            final_sa = sa_worker(
                CG,
                pm,
                ev,
                depot_idx,
                collections,
                cfg.base_seed + 99991,
                final_sa_budget,
                cfg.use_cross2,
                &greedy_state,
                &shared_conv_log,
                &conv_mtx,
                max(0, cfg.sa_instances - 1)
            );

            recompute_state_metrics_and_loads(final_sa.best_state, ev);
            if (solution_hard_feasible(final_sa.best_state, CG, pm)) {
                // V37: final_sa was already refined within sa_worker's local
                // budget. Avoid a second main-thread refinement outside it.
                update_global_best_checked(final_sa.best_state, CG, pm);
            }
            else {
                cerr << "[FINAL_SA INVALID] obj="
                    << final_sa.best_state.objective
                    << " ignored because infeasible\n";
            }
        }
    }

    // V17: budget saturation. A fixed-budget solver should not silently leave
    // search time unused merely because its finite internal pipeline completed.
    // If the deep pipeline returns before the global deadline, launch additional
    // six-worker rounds from the current hard-feasible global incumbent until T.
    // Each filler round uses fresh deterministic worker seeds and the same deep
    // SA kernel; the global deadline remains authoritative and censors late work.
    if (cfg.hard_time_limit_s > 0.0 && !solver_should_stop() &&
        !cfg.use_phase_specialized_engine) {
        int filler_round = 0;
        const double reserve_tail = min(cfg.final_intensification_reserve_s,
                                        max(0.0, cfg.hard_time_limit_s));
        while (!solver_should_stop() && filler_round < 64) {
            const double filler_remaining = cfg.hard_time_limit_s - reserve_tail - solver_elapsed_seconds();
            if (filler_remaining <= 1e-4) break;
            SolutionState filler_start = greedy_state;
            {
                lock_guard<mutex> lock(global_best_mutex);
                if (!global_best_state.routes.empty()) filler_start = global_best_state;
            }
            recompute_state_metrics_and_loads(filler_start, ev);
            if (!solution_hard_feasible(filler_start, CG, pm)) break;

            profile.budget_saturation_rounds.fetch_add(1, memory_order_relaxed);
            safe_log_line("[BudgetSaturation] round=", filler_round,
                          " elapsed=", solver_elapsed_seconds(),
                          " start_objective=", filler_start.objective);

            const double filler_budget = min(cfg.sa_time_limit, max(0.0,
                cfg.hard_time_limit_s - reserve_tail - solver_elapsed_seconds()));
            if (filler_budget <= 1e-4) break;
            const int instances = max(1, cfg.sa_instances);
            vector<thread> filler_threads;
            filler_threads.reserve(instances);
            for (int i = 0; i < instances && !solver_should_stop(); ++i) {
                const unsigned fseed = cfg.base_seed + 500003u +
                    (unsigned)filler_round * 1000003u + (unsigned)i * 10007u;
                filler_threads.emplace_back([&, fseed, i]() {
                    AlgoResult r;
                    if (cfg.use_parallel_fast_worker && instances >= 2 && i == instances - 1) {
                        r = run_parallel_fast_worker_v41(
                            filler_start, ev, pm, filler_budget, fseed + 0x51F17u,
                            &shared_conv_log, &conv_mtx
                        );
                    } else {
                        r = sa_worker(
                            CG, pm, ev, depot_idx, collections, fseed,
                            filler_budget, cfg.use_cross2, &filler_start,
                            &shared_conv_log, &conv_mtx, i
                        );
                    }
                    recompute_state_metrics_and_loads(r.best_state, ev);
                    if (solution_hard_feasible(r.best_state, CG, pm))
                        update_global_best_checked(r.best_state, CG, pm);
                });
            }
            for (auto &th : filler_threads) if (th.joinable()) th.join();
            ++filler_round;
        }
    }

    SolutionState best_state;

    // V40: under a hard deadline the validated, deadline-censored global ledger
    // is the *only* authoritative result. This also makes --budget_scope solve
    // correct when a method-specific initializer itself finishes after T.
    if (cfg.hard_time_limit_s > 0.0) {
        lock_guard<mutex> lock(global_best_mutex);
        if (!global_best_state.routes.empty()) best_state = global_best_state;
    } else {
        take_if_better_feasible(best_state, greedy_state, ev, pm);
        if (!global_best_state.routes.empty())
            take_if_better_feasible(best_state, global_best_state, ev, pm);
        take_if_better_feasible(best_state, final_sa.best_state, ev, pm);
    }

    if (best_state.routes.empty()) {
        cerr << "[FINAL_SELECT] no hard-feasible candidate completed within the governed budget\n";
        return 2;
    }

    recompute_state_metrics_and_loads(best_state, ev);

    // V35 explicit intensification tail. Previously these modules were located
    // after a saturation loop that intentionally consumed the entire deadline,
    // so configured Granular Tabu / Route-Region / Boundary-Pair could receive
    // zero compute. Reserve a tail, divide it among enabled modules, and enforce
    // each slice through the same thread-local cooperative deadline mechanism.
    int tail_modules = 0;
    if (cfg.use_granular_tabu) ++tail_modules;
    if (cfg.use_route_region_lns) ++tail_modules;
    if (cfg.use_boundary_pair_lns) ++tail_modules;
    const bool parallel_tail_available = (cfg.parallel_intensification_tail || cfg.staged_portfolio_tail) &&
        cfg.final_intensification_reserve_s > 0.0;
    const double tail_slice_s = parallel_tail_available
        ? cfg.final_intensification_reserve_s
        : ((cfg.final_intensification_reserve_s > 0.0 && tail_modules > 0)
            ? cfg.final_intensification_reserve_s / (double)tail_modules
            : 0.0);
    if (cfg.final_intensification_reserve_s > 0.0) {
        safe_log_line("[TailReserve-V35] enter elapsed=", solver_elapsed_seconds(),
                      " reserve_s=", cfg.final_intensification_reserve_s,
                      " modules=", tail_modules, " slice_s=", tail_slice_s,
                      " incumbent=", best_state.objective);
    }

    // E16: state-adaptive late-component audition.  Every candidate starts
    // from the exact same validated incumbent and receives the same short wall
    // budget.  The result is itself useful (improving candidates are retained),
    // while the telemetry tells us which late mechanism is alive in this basin.
    if (cfg.use_phase_specialized_engine && cfg.phase_adaptive_tail_probe &&
        cfg.hard_time_limit_s > 0.0 && !solver_should_stop()) {
        const double rem = max(0.0, cfg.hard_time_limit_s - solver_elapsed_seconds());
        double pb = min(cfg.phase_tail_probe_max_s,
            max(cfg.phase_tail_probe_min_s, rem * cfg.phase_tail_probe_fraction));
        pb = min(pb, max(0.0, rem - cfg.phase_tail_deadline_guard_s));
        if (pb >= cfg.phase_tail_probe_min_s) {
            enum class TailProbeKind { FRAGMENT, REGION, ADAPTIVE, REFINEMENT, FAST };
            vector<TailProbeKind> order;
            if ((int)collections.size() >= 400) {
                order = {TailProbeKind::FRAGMENT, TailProbeKind::REFINEMENT,
                         TailProbeKind::REGION, TailProbeKind::ADAPTIVE, TailProbeKind::FAST};
            } else if ((int)collections.size() >= 180) {
                order = {TailProbeKind::REGION, TailProbeKind::REFINEMENT,
                         TailProbeKind::ADAPTIVE, TailProbeKind::FAST, TailProbeKind::FRAGMENT};
            } else {
                order = {TailProbeKind::REFINEMENT, TailProbeKind::ADAPTIVE,
                         TailProbeKind::FAST, TailProbeKind::FRAGMENT, TailProbeKind::REGION};
            }
            const int hwp_raw = (int)thread::hardware_concurrency();
            const int hwp = hwp_raw > 0 ? hwp_raw : max(1, cfg.sa_instances);
            const int pc = min({(int)order.size(), cfg.phase_tail_probe_max_workers,
                                max(1, cfg.sa_instances), max(1, hwp)});
            struct ProbeResult { string name; SolutionState state; double wall=0.0; double gain=0.0; bool feasible=false; };
            vector<ProbeResult> pr(pc);
            vector<thread> pth;
            const SolutionState probe_seed = best_state;
            const double probe_start_obj = probe_seed.objective;
            for (int i = 0; i < pc; ++i) {
                const TailProbeKind kind = order[i];
                pth.emplace_back([&, i, kind]() {
                    const auto tp0 = Clock::now();
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    SolutionState c = probe_seed;
                    string name;
                    {
                        ScopedWorkerDeadline cap(pb);
                        if (kind == TailProbeKind::FRAGMENT) {
                            name = "fragment_lns";
                            fragment_lns_search(c, ev, pm);
                        } else if (kind == TailProbeKind::REGION) {
                            name = "route_region";
                            route_region_lns_descent(c, ev, pm);
                        } else if (kind == TailProbeKind::ADAPTIVE) {
                            name = "adaptive_lns";
                            adaptive_lns_polish(c, ev, pm, max(1, cfg.alns_rounds),
                                cfg.base_seed ^ (0xE160A11u + (unsigned)i));
                        } else if (kind == TailProbeKind::REFINEMENT) {
                            name = "final_refinement";
                            final_refinement_pass(c, ev, pm);
                        } else {
                            name = "fast_lns";
                            AlgoResult rr = run_parallel_fast_worker_v41(
                                probe_seed, ev, pm, pb,
                                cfg.base_seed + 0xE160F00u + (unsigned)i * 10007u,
                                &shared_conv_log, &conv_mtx);
                            c = std::move(rr.best_state);
                        }
                    }
                    tls_defer_global_publish = old_defer;
                    recompute_state_metrics_and_loads(c, ev);
                    pr[i].name = std::move(name);
                    pr[i].wall = chrono::duration<double>(Clock::now() - tp0).count();
                    pr[i].feasible = solution_hard_feasible(c, CG, pm);
                    if (pr[i].feasible) {
                        pr[i].state = std::move(c);
                        pr[i].gain = max(0.0, probe_start_obj - pr[i].state.objective);
                    }
                });
            }
            for (auto &t : pth) if (t.joinable()) t.join();
            int win = -1;
            double win_gain = 0.0;
            double win_rate = 0.0;
            for (int i = 0; i < pc; ++i) {
                const double rate = pr[i].wall > 1e-9 ? pr[i].gain / pr[i].wall : 0.0;
                safe_log_line("[PhaseTailProbe-E25] component=", pr[i].name,
                              " budget_s=", pb,
                              " wall_s=", pr[i].wall,
                              " gain=", pr[i].gain,
                              " gain_per_s=", rate,
                              " feasible=", pr[i].feasible ? 1 : 0);
                if (pr[i].feasible && (pr[i].gain > win_gain + 1e-9 ||
                    (fabs(pr[i].gain - win_gain) <= 1e-9 && rate > win_rate))) {
                    win = i; win_gain = pr[i].gain; win_rate = rate;
                }
            }
            if (win >= 0 && win_gain > 1e-9) {
                best_state = pr[win].state;
                update_global_best_checked(best_state, CG, pm);
                safe_log_line("[PhaseTailProbe-E25] winner=", pr[win].name,
                              " gain=", win_gain,
                              " objective=", best_state.objective,
                              " elapsed=", solver_elapsed_seconds());

                // E17: only a decisive probe earns a sequential repeat.  This
                // turns the audition into a tiny online allocation policy rather
                // than blindly rerunning every late component.
                const double repeat_trigger = cfg.phase_tail_probe_repeat_gain_multiplier *
                    max(1.0, meaningful_gain_threshold(max(1.0, probe_start_obj)));
                const double rem2 = max(0.0, cfg.hard_time_limit_s - solver_elapsed_seconds());
                const double rb = min({cfg.phase_tail_probe_repeat_max_s, pb,
                    max(0.0, rem2 - cfg.phase_tail_deadline_guard_s)});
                if (win_gain + 1e-9 >= repeat_trigger && rb >= 0.15 && !solver_should_stop()) {
                    const auto tr0 = Clock::now();
                    const double before_repeat = best_state.objective;
                    SolutionState c = best_state;
                    const TailProbeKind kind = order[win];
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    {
                        ScopedWorkerDeadline cap(rb);
                        if (kind == TailProbeKind::FRAGMENT) {
                            fragment_lns_search(c, ev, pm);
                        } else if (kind == TailProbeKind::REGION) {
                            route_region_lns_descent(c, ev, pm);
                        } else if (kind == TailProbeKind::ADAPTIVE) {
                            adaptive_lns_polish(c, ev, pm, max(1, cfg.alns_rounds),
                                cfg.base_seed ^ 0xE170A11u);
                        } else if (kind == TailProbeKind::REFINEMENT) {
                            final_refinement_pass(c, ev, pm);
                        } else {
                            AlgoResult rr = run_parallel_fast_worker_v41(
                                best_state, ev, pm, rb, cfg.base_seed + 0xE170F00u,
                                &shared_conv_log, &conv_mtx);
                            c = std::move(rr.best_state);
                        }
                    }
                    tls_defer_global_publish = old_defer;
                    recompute_state_metrics_and_loads(c, ev);
                    if (solution_hard_feasible(c, CG, pm) &&
                        c.objective + 1e-9 < best_state.objective) {
                        best_state = std::move(c);
                        update_global_best_checked(best_state, CG, pm);
                    }
                    safe_log_line("[PhaseTailProbe-E25] repeat=", pr[win].name,
                                  " trigger=", repeat_trigger,
                                  " budget_s=", rb,
                                  " wall_s=", chrono::duration<double>(Clock::now()-tr0).count(),
                                  " gain=", max(0.0, before_repeat-best_state.objective),
                                  " objective=", best_state.objective,
                                  " elapsed=", solver_elapsed_seconds());
                }
            } else {
                safe_log_line("[PhaseTailProbe-E25] winner=none objective=",
                              best_state.objective,
                              " elapsed=", solver_elapsed_seconds());
            }
        }
    }

    SolutionState pre_output_polish_state = best_state;

    if (cfg.staged_portfolio_tail && tail_slice_s > 0.0 && !solver_should_stop()) {
        // V56: barriered complementary search. Diagnostics showed that several
        // losing states were repairable by *existing* components only when they
        // were sequenced (intensify -> diversify -> intensify). Running all tail
        // components once from the same snapshot cannot realize that synergy.
        const double remaining0 = max(0.0, cfg.hard_time_limit_s - solver_elapsed_seconds());
        const double tail_guard = cfg.use_phase_specialized_engine
            ? min(max(0.0, cfg.phase_tail_deadline_guard_s), max(0.0, 0.18 * remaining0))
            : 0.0;
        const double total_budget = min(cfg.final_intensification_reserve_s,
            max(0.0, remaining0 - tail_guard));
        const double first_budget = min(cfg.staged_portfolio_first_intensify_s, max(0.0, total_budget * 0.30));
        const double final_budget = min(cfg.staged_portfolio_final_intensify_s, max(0.0, total_budget * 0.35));
        const double diversify_budget = max(0.0, total_budget - first_budget - final_budget);
        const int tail_hw_raw = (int)thread::hardware_concurrency();
        const int tail_hw = tail_hw_raw > 0 ? tail_hw_raw : max(1, cfg.sa_instances);
        const int tail_compute_cap = (cfg.use_phase_specialized_engine && cfg.phase_respect_hardware_concurrency)
            ? min(max(1, cfg.sa_instances), max(1, min(max(1, cfg.sa_instances), max(cfg.phase_min_active_workers, tail_hw))))
            : max(1, cfg.sa_instances);
        safe_log_line("[TailSchedule-E10] logical=", cfg.sa_instances,
                      " hw=", tail_hw, " active_cap=", tail_compute_cap,
                      " total_budget=", total_budget);
        auto tail_active_fleet_count = [&](const SolutionState &ss) {
            int k = 0;
            for (const auto &r : ss.routes) if (route_customer_count_hard(r, CG) > 0) ++k;
            return k;
        };
        const int elite_tail_entry_k = tail_active_fleet_count(best_state);
        vector<SolutionState> evolution_pool;
        mutex evolution_pool_mtx;
        if (cfg.use_phase_specialized_engine && !final_sa.elite_states.empty()) {
            const double phase_best = final_sa.elite_states.front().objective;
            for (auto c : final_sa.elite_states) {
                recompute_state_metrics_and_loads(c, ev);
                if (!solution_hard_feasible(c, CG, pm)) continue;
                const double gap = (c.objective - phase_best) /
                    max(1.0, fabs(phase_best));
                if (gap <= cfg.phase_archive_max_quality_gap + 1e-12)
                    evolution_pool.push_back(std::move(c));
            }
            safe_log_line("[PhaseTailHandoff-E10] inherited_elites=", evolution_pool.size(),
                          " best=", phase_best,
                          " elapsed=", solver_elapsed_seconds());
        }

        auto refresh_from_global = [&](SolutionState cur) {
            recompute_state_metrics_and_loads(cur, ev);
            lock_guard<mutex> lock(global_best_mutex);
            if (!global_best_state.routes.empty()) {
                SolutionState gb = global_best_state;
                recompute_state_metrics_and_loads(gb, ev);
                if (solution_hard_feasible(gb, CG, pm) && gb.objective + 1e-9 < cur.objective)
                    cur = std::move(gb);
            }
            return cur;
        };

        auto intensify_stage = [&](const SolutionState &seed_state, double budget, const char *tag) {
            if (budget <= 1e-4 || solver_should_stop()) return seed_state;
            vector<SolutionState> candidates;
            mutex cm;
            vector<thread> ths;
            auto submit_stage = [&](SolutionState c) {
                recompute_state_metrics_and_loads(c, ev);
                if (!solution_hard_feasible(c, CG, pm)) return;
                update_global_best_checked(c, CG, pm);
                lock_guard<mutex> lk(cm);
                candidates.push_back(std::move(c));
            };
            auto launch_state = [&](auto fn) {
                if ((int)ths.size() >= tail_compute_cap) return;
                ths.emplace_back([&, fn]() mutable {
                    SolutionState c = seed_state;
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    { ScopedWorkerDeadline cap(budget); fn(c); }
                    tls_defer_global_publish = old_defer;
                    submit_stage(std::move(c));
                });
            };
            if (cfg.use_phase_specialized_engine) {
                // E3 road evidence: ownership correction / region search should
                // get scarce tail cores before generic final-refinement work.
                if (cfg.use_interroute_polish) launch_state([&](SolutionState &c){ interroute_polish_solution(c, ev, pm); });
                if (cfg.use_route_region_lns) launch_state([&](SolutionState &c){ route_region_lns_descent(c, ev, pm); });
                if (cfg.use_granular_tabu) launch_state([&](SolutionState &c){ granular_tabu_repair(c, ev, pm); });
                if (cfg.use_boundary_pair_lns) launch_state([&](SolutionState &c){ boundary_pair_lns_descent(c, ev, pm); });
                if (cfg.use_final_polish) launch_state([&](SolutionState &c){ final_refinement_pass(c, ev, pm); });
            } else {
                if (cfg.use_interroute_polish) launch_state([&](SolutionState &c){ interroute_polish_solution(c, ev, pm); });
                if (cfg.use_granular_tabu) launch_state([&](SolutionState &c){ granular_tabu_repair(c, ev, pm); });
                if (cfg.use_final_polish) launch_state([&](SolutionState &c){ final_refinement_pass(c, ev, pm); });
                if (cfg.use_boundary_pair_lns) launch_state([&](SolutionState &c){ boundary_pair_lns_descent(c, ev, pm); });
                if (cfg.use_route_region_lns) launch_state([&](SolutionState &c){ route_region_lns_descent(c, ev, pm); });
            }
            // Keep the sixth core productive even when deterministic local
            // neighborhoods finish early: one cheap feasible LNS lane also tests
            // whether a structural escape is immediately available.
            if ((int)ths.size() < tail_compute_cap) {
                ths.emplace_back([&]() {
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    AlgoResult r = run_parallel_fast_worker_v41(
                        seed_state, ev, pm, budget, cfg.base_seed ^ 0x156A11u,
                        &shared_conv_log, &conv_mtx);
                    tls_defer_global_publish = old_defer;
                    submit_stage(std::move(r.best_state));
                });
            }
            for (auto &t : ths) if (t.joinable()) t.join();
            SolutionState out = seed_state;
            recompute_state_metrics_and_loads(out, ev);
            for (auto &c : candidates) if (c.objective + 1e-9 < out.objective) out = std::move(c);
            out = refresh_from_global(std::move(out));
            safe_log_line("[StagedPortfolio-V56] stage=", tag,
                          " budget_s=", budget, " candidates=", candidates.size(),
                          " objective=", out.objective, " elapsed=", solver_elapsed_seconds());
            return out;
        };

        auto diversify_stage = [&](const SolutionState &seed_state, double budget, bool harvest_elites = false) {
            if (budget <= 1e-4 || solver_should_stop()) return seed_state;
            const int instances = cfg.use_phase_specialized_engine
                ? tail_compute_cap : max(1, cfg.sa_instances);
            vector<SolutionState> candidates;
            mutex cm;
            vector<thread> ths;
            auto submit_stage = [&](SolutionState c) {
                recompute_state_metrics_and_loads(c, ev);
                if (!solution_hard_feasible(c, CG, pm)) return;
                // Only completed lane pipelines publish. This gives the stage a
                // deterministic barrier and prevents a temporarily good raw LNS
                // candidate from pulling other workers into its basin before its
                // downstream polish quality is known.
                update_global_best_checked(c, CG, pm);
                lock_guard<mutex> lk(cm);
                candidates.push_back(std::move(c));
            };
            const int fast_lanes = min(instances, max(1, cfg.staged_portfolio_fast_lanes));
            const double post_fraction = max(0.05, min(0.60, cfg.staged_portfolio_post_fraction));
            const double post_budget = max(0.05, budget * post_fraction);
            const double search_budget = max(0.05, budget - post_budget);

            for (int i = 0; i < instances; ++i) {
                const unsigned sseed = cfg.base_seed + 0xD157000u + (unsigned)i * 10007u;
                ths.emplace_back([&, sseed, i]() {
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    SolutionState lane_seed = seed_state;
                    if (cfg.use_phase_specialized_engine &&
                        final_sa.elite_states.size() > 1 && i > 0) {
                        const size_t idx = (size_t)(i - 1) % final_sa.elite_states.size();
                        const SolutionState &candidate_seed = final_sa.elite_states[idx];
                        const double gap = (candidate_seed.objective - seed_state.objective) /
                            max(1.0, fabs(seed_state.objective));
                        // Keep inherited starts competitive with the newly
                        // intensified incumbent; diversity is not a license to
                        // rewind the tail into a weak basin.
                        if (gap <= cfg.phase_archive_max_quality_gap + 1e-12)
                            lane_seed = candidate_seed;
                    }
                    SolutionState c = lane_seed;

                    // V60: roles are assigned explicitly by *search behavior*, not
                    // indirectly by the lane number left over after FAST lanes.
                    // Diagnostics showed the previous 3-FAST + Fragment layout left
                    // no structural SA lane in the final pipeline, exactly when a
                    // late K-changing transition could be most valuable.  For six
                    // workers use 2 structural SA + 2 FAST + 1 Fragment + 1 explorer.
                    // Every lane is subsequently polished before candidates are ranked.
                    if (instances >= 6 && cfg.staged_portfolio_layout == "s1f3fragx") {
                        // V61 B-layout: one structural lane is enough when the two
                        // V60 structural lanes repeatedly collapse to the same raw
                        // endpoint.  Spend the released core-second on an additional
                        // stochastic FAST basin; replace the short-tail explorer with
                        // a low-temperature exploiter (slot 2).
                        if (i == 0) {
                            AlgoResult r = sa_worker(
                                CG, pm, ev, depot_idx, collections, sseed, search_budget,
                                cfg.use_cross2, &lane_seed, &shared_conv_log, &conv_mtx, 0);
                            c = std::move(r.best_state);
                        } else if (i >= 1 && i <= 3) {
                            AlgoResult r = run_parallel_fast_worker_v41(
                                lane_seed, ev, pm, search_budget, sseed,
                                &shared_conv_log, &conv_mtx);
                            c = std::move(r.best_state);
                        } else if (i == 4 && cfg.use_fragment_lns) {
                            ScopedWorkerDeadline cap(search_budget);
                            fragment_lns_search(c, ev, pm);
                        } else {
                            AlgoResult r = sa_worker(
                                CG, pm, ev, depot_idx, collections, sseed, search_budget,
                                cfg.use_cross2, &lane_seed, &shared_conv_log, &conv_mtx, 2);
                            c = std::move(r.best_state);
                        }
                    } else if (instances >= 6 && i == 0) {
                        AlgoResult r = sa_worker(
                            CG, pm, ev, depot_idx, collections, sseed, search_budget,
                            cfg.use_cross2, &lane_seed, &shared_conv_log, &conv_mtx, 0);
                        c = std::move(r.best_state);
                    } else if (instances >= 6 && i == 1) {
                        AlgoResult r = sa_worker(
                            CG, pm, ev, depot_idx, collections, sseed, search_budget,
                            cfg.use_cross2, &lane_seed, &shared_conv_log, &conv_mtx, 1);
                        c = std::move(r.best_state);
                    } else if (instances >= 6 && (i == 2 || i == 3)) {
                        AlgoResult r = run_parallel_fast_worker_v41(
                            lane_seed, ev, pm, search_budget, sseed,
                            &shared_conv_log, &conv_mtx);
                        c = std::move(r.best_state);
                    } else if (instances >= 6 && i == 4 && cfg.use_fragment_lns) {
                        ScopedWorkerDeadline cap(search_budget);
                        fragment_lns_search(c, ev, pm);
                    } else if (instances >= 6 && i == 5) {
                        AlgoResult r = sa_worker(
                            CG, pm, ev, depot_idx, collections, sseed, search_budget,
                            cfg.use_cross2, &lane_seed, &shared_conv_log, &conv_mtx, 5);
                        c = std::move(r.best_state);
                    } else if (i < fast_lanes) {
                        // Fallback for non-six-worker experiments preserves the old
                        // configurable layout.
                        AlgoResult r = run_parallel_fast_worker_v41(
                            lane_seed, ev, pm, search_budget, sseed,
                            &shared_conv_log, &conv_mtx);
                        c = std::move(r.best_state);
                    } else if (i == fast_lanes && cfg.use_fragment_lns) {
                        ScopedWorkerDeadline cap(search_budget);
                        fragment_lns_search(c, ev, pm);
                    } else {
                        const int role_slot = (i == instances - 1) ? max(0, instances - 1) : i;
                        AlgoResult r = sa_worker(
                            CG, pm, ev, depot_idx, collections, sseed, search_budget,
                            cfg.use_cross2, &lane_seed, &shared_conv_log, &conv_mtx, role_slot);
                        c = std::move(r.best_state);
                    }

                    recompute_state_metrics_and_loads(c, ev);
                    const bool raw_hard_feasible = solution_hard_feasible(c, CG, pm);
                    if (raw_hard_feasible) {
                        // V61 correctness invariant: this raw state has completed
                        // hard-feasibility validation.  Record it immediately for
                        // objective-at-deadline even though the lane remains private
                        // for migration until downstream basin evaluation finishes.
                        checkpoint_validated_global_best(c, "staged_raw_validated");
                        if (harvest_elites) {
                            lock_guard<mutex> elk(evolution_pool_mtx);
                            evolution_pool.push_back(c);
                        }
                    }
                    if (raw_hard_feasible && !solver_should_stop()) {
                        // V57 key change: evaluate *basin potential*, not just the
                        // raw diversification objective. A slightly worse LNS
                        // endpoint can expose much larger inter-route gains.
                        ScopedWorkerDeadline cap(post_budget);
                        interroute_polish_solution(c, ev, pm);
                        if (!solver_should_stop()) granular_tabu_repair(c, ev, pm);
                    }
                    if (harvest_elites) {
                        recompute_state_metrics_and_loads(c, ev);
                        if (solution_hard_feasible(c, CG, pm)) {
                            lock_guard<mutex> elk(evolution_pool_mtx);
                            evolution_pool.push_back(c);
                        }
                    }
                    tls_defer_global_publish = old_defer;
                    submit_stage(std::move(c));
                });
            }
            for (auto &t : ths) if (t.joinable()) t.join();
            SolutionState out = seed_state;
            recompute_state_metrics_and_loads(out, ev);
            for (auto &c : candidates) if (c.objective + 1e-9 < out.objective) out = std::move(c);
            out = refresh_from_global(std::move(out));
            safe_log_line("[StagedPortfolio-V61] stage=diversify_polish",
                          " layout=", cfg.staged_portfolio_layout,
                          " budget_s=", budget, " search_s=", search_budget,
                          " post_s=", post_budget, " fast_lanes=", fast_lanes,
                          " candidates=", candidates.size(), " objective=", out.objective,
                          " elapsed=", solver_elapsed_seconds());
            return out;
        };

        bool elite_recombine_executed = false;
        auto elite_recombine_stage = [&](const SolutionState &seed_state, double budget) {
            if (budget <= 1e-4 || solver_should_stop()) return seed_state;
            if (cfg.use_phase_specialized_engine && cfg.hard_time_limit_s > 0.0) {
                const double entry_floor = max(
                    cfg.phase_elite_archive_min_entry_s,
                    cfg.phase_elite_archive_floor_per_customer_s *
                        max(1, (int)collections.size()));
                const double safe_remaining = max(0.0,
                    cfg.hard_time_limit_s - solver_elapsed_seconds() -
                    cfg.phase_tail_deadline_guard_s);
                const double usable = min(budget, safe_remaining);
                if (usable < entry_floor) {
                    safe_log_line("[EliteEvolution-E36] skip_stage usable_s=", usable,
                                  " entry_floor_s=", entry_floor,
                                  " requested_s=", budget,
                                  " incumbent=", seed_state.objective,
                                  " elapsed=", solver_elapsed_seconds());
                    return seed_state;
                }
            }
            const bool balanced_memetic = (cfg.staged_portfolio_layout == "elite_evolution_balanced");
            const bool strong_memetic = (cfg.staged_portfolio_layout == "elite_evolution_strong" || cfg.staged_portfolio_layout == "elite_evolution_strong2" || balanced_memetic);
            const bool strong_memetic2 = (cfg.staged_portfolio_layout == "elite_evolution_strong2");
            {
                lock_guard<mutex> lk(evolution_pool_mtx);
                evolution_pool.push_back(seed_state);
            }
            {
                lock_guard<mutex> glk(global_best_mutex);
                if (!global_best_state.routes.empty()) {
                    lock_guard<mutex> lk(evolution_pool_mtx);
                    evolution_pool.push_back(global_best_state);
                }
            }

            // Deliberately manufacture a small set of different, already-good basins
            // from the newly reached fleet layer.  These are all existing operators;
            // this phase tests population construction rather than new neighborhoods.
            const bool inherited_pool_ready = cfg.use_phase_specialized_engine &&
                cfg.phase_reuse_inherited_elites && evolution_pool.size() >= 6;
            const double fill_fraction = inherited_pool_ready ? 0.0 : 0.38;
            const double fill_budget = inherited_pool_ready ? 0.0 : max(0.04, budget * fill_fraction);
            const double breed_budget = max(0.0, budget - fill_budget);
            vector<thread> fill_threads;
            mutex fill_log_mtx;
            auto submit_fill = [&](SolutionState c, const char *kind, int lane) {
                recompute_state_metrics_and_loads(c, ev);
                if (!solution_hard_feasible(c, CG, pm)) return;
                checkpoint_validated_global_best(c, "elite_fill_validated");
                {
                    lock_guard<mutex> lk(evolution_pool_mtx);
                    evolution_pool.push_back(c);
                }
                safe_log_line("[EliteFill] lane=", lane, " kind=", kind,
                              " K=", tail_active_fleet_count(c),
                              " objective=", c.objective,
                              " elapsed=", solver_elapsed_seconds());
            };
            const int fill_count = inherited_pool_ready ? 0 : min(
                cfg.use_phase_specialized_engine ? tail_compute_cap : max(1, cfg.sa_instances), 6);
            for (int lane = 0; lane < fill_count; ++lane) {
                fill_threads.emplace_back([&, lane]() {
                    const bool old = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    SolutionState c = seed_state;
                    const unsigned ss = cfg.base_seed + 0xE11F111u + (unsigned)lane * 104729u;
                    if (lane == 0 || lane == 1) {
                        AlgoResult r = run_parallel_fast_worker_v41(
                            seed_state, ev, pm, fill_budget, ss,
                            &shared_conv_log, &conv_mtx);
                        c = std::move(r.best_state);
                        submit_fill(std::move(c), lane == 0 ? "FAST_A" : "FAST_B", lane);
                    } else if (lane == 2) {
                        AlgoResult r = sa_worker(
                            CG, pm, ev, depot_idx, collections, ss, fill_budget,
                            cfg.use_cross2, &seed_state, &shared_conv_log, &conv_mtx, 2);
                        c = std::move(r.best_state);
                        submit_fill(std::move(c), "SA_exploiter", lane);
                    } else if (lane == 3) {
                        AlgoResult r = sa_worker(
                            CG, pm, ev, depot_idx, collections, ss, fill_budget,
                            cfg.use_cross2, &seed_state, &shared_conv_log, &conv_mtx, 5);
                        c = std::move(r.best_state);
                        submit_fill(std::move(c), "SA_explorer", lane);
                    } else if (lane == 4 && cfg.use_fragment_lns) {
                        { ScopedWorkerDeadline cap(fill_budget); fragment_lns_search(c, ev, pm); }
                        submit_fill(std::move(c), "Fragment", lane);
                    } else if (cfg.use_route_region_lns) {
                        { ScopedWorkerDeadline cap(fill_budget); route_region_lns_descent(c, ev, pm); }
                        submit_fill(std::move(c), "RouteRegion", lane);
                    } else {
                        { ScopedWorkerDeadline cap(fill_budget); interroute_polish_solution(c, ev, pm); }
                        submit_fill(std::move(c), "InterRoute", lane);
                    }
                    tls_defer_global_publish = old;
                });
            }
            for (auto &t : fill_threads) if (t.joinable()) t.join();

            auto edge_signature = [&](const SolutionState &ss) {
                unordered_set<uint64_t> sig;
                auto ek = [](int a, int b) -> uint64_t {
                    return (uint64_t(uint32_t(a)) << 32) | uint32_t(b);
                };
                for (const auto &r : ss.routes) {
                    int prev = depot_idx;
                    bool active = false;
                    for (int x : r) {
                        if (x < 0 || x >= (int)CG.nodes.size()) continue;
                        if (CG.nodes[x].type == 2) {
                            sig.insert(ek(prev, x)); prev = x; active = true;
                        } else if (CG.nodes[x].type == 1 && active && prev != depot_idx) {
                            sig.insert(ek(prev, depot_idx)); prev = depot_idx; active = false;
                        }
                    }
                    if (active && prev != depot_idx) sig.insert(ek(prev, depot_idx));
                }
                return sig;
            };
            auto dist = [&](const SolutionState &a, const SolutionState &b) {
                auto A = edge_signature(a), B = edge_signature(b);
                double edge_d = 0.0;
                if (!(A.empty() && B.empty())) {
                    const auto *S = &A, *L = &B;
                    if (S->size() > L->size()) swap(S, L);
                    size_t common = 0;
                    for (uint64_t e : *S) if (L->count(e)) ++common;
                    const size_t uni = A.size() + B.size() - common;
                    edge_d = uni ? 1.0 - double(common) / double(uni) : 0.0;
                }
                if (!strong_memetic) return edge_d;
                const double assign_d = pr_assignment_distance_aligned(a, b, CG);
                return 0.62 * edge_d + 0.38 * assign_d;
            };

            vector<SolutionState> layer;
            int bestK = INT_MAX;
            for (auto &c : evolution_pool) {
                recompute_state_metrics_and_loads(c, ev);
                if (!solution_hard_feasible(c, CG, pm)) continue;
                if (cfg.solomon_vehicle_penalty > 0.0)
                    bestK = min(bestK, tail_active_fleet_count(c));
            }
            for (auto &c : evolution_pool) {
                if (!solution_hard_feasible(c, CG, pm)) continue;
                if (cfg.solomon_vehicle_penalty <= 0.0 || tail_active_fleet_count(c) == bestK)
                    layer.push_back(c);
            }
            sort(layer.begin(), layer.end(), [](const SolutionState &a, const SolutionState &b) {
                return a.objective < b.objective;
            });
            vector<SolutionState> unique;
            for (auto &c : layer) {
                bool clone = false;
                const double clone_threshold = 0.015;
                for (auto &u : unique) if (dist(c, u) < clone_threshold) { clone = true; break; }
                if (!clone) unique.push_back(c);
            }
            const int target = min(8, (int)unique.size());
            vector<SolutionState> elite;
            vector<char> used(unique.size(), 0);
            if (!unique.empty()) { elite.push_back(unique[0]); used[0] = 1; }
            while ((int)elite.size() < target) {
                int pick = -1; double best_score = -1e100;
                for (int i = 0; i < (int)unique.size(); ++i) if (!used[i]) {
                    double md = 1.0;
                    for (auto &e : elite) md = min(md, dist(unique[i], e));
                    const double q = unique.size() <= 1 ? 1.0 :
                        1.0 - double(i) / double(unique.size() - 1);
                    const double score = 0.58 * q + 0.42 * md;
                    if (score > best_score) { best_score = score; pick = i; }
                }
                if (pick < 0) break;
                used[pick] = 1; elite.push_back(unique[pick]);
            }
            double meanD = 0.0, minD = 1.0; int npair = 0;
            for (int i = 0; i < (int)elite.size(); ++i)
                for (int j = i + 1; j < (int)elite.size(); ++j) {
                    const double d = dist(elite[i], elite[j]);
                    meanD += d; minD = min(minD, d); ++npair;
                }
            if (npair) meanD /= npair; else minD = 0.0;
            safe_log_line("[EliteEvolution] phase=archive pool=", evolution_pool.size(),
                " bestK=", bestK == INT_MAX ? -1 : bestK,
                " layer=", layer.size(), " unique=", unique.size(), " elite=", elite.size(),
                " mean_div=", meanD, " min_div=", minD,
                " best=", elite.empty() ? seed_state.objective : elite[0].objective,
                " inherited_reuse=", (inherited_pool_ready ? 1 : 0),
                " fill_s=", fill_budget, " breed_s=", breed_budget,
                " elapsed=", solver_elapsed_seconds());
            if (elite.size() < 2) return seed_state;

            // E35: archive construction itself can consume a large fraction of
            // the tail. Recompute the safe breeding envelope now, not from the
            // stale budget that was passed into this stage. This prevents deep
            // children from being launched after their admissible evidence
            // window has effectively disappeared.
            double effective_breed_budget = breed_budget;
            if (cfg.use_phase_specialized_engine && cfg.hard_time_limit_s > 0.0) {
                const double hard_remaining = max(0.0,
                    cfg.hard_time_limit_s - solver_elapsed_seconds() -
                    cfg.phase_tail_deadline_guard_s);
                effective_breed_budget = min(effective_breed_budget, hard_remaining);
            }
            if (effective_breed_budget < cfg.phase_elite_recombine_min_safe_s) {
                SolutionState archive_best = elite.front();
                checkpoint_validated_global_best(archive_best, "elite_archive_best_validated");
                safe_log_line("[EliteEvolution-E35] skip_recombine remaining_safe_s=",
                              effective_breed_budget,
                              " min_safe_s=", cfg.phase_elite_recombine_min_safe_s,
                              " archive_best=", archive_best.objective,
                              " elapsed=", solver_elapsed_seconds());
                return refresh_from_global(std::move(archive_best));
            }
            elite_recombine_executed = true;

            vector<pair<int,int>> tasks;
            if (!strong_memetic) {
                vector<pair<double,int>> partners;
                for (int j = 1; j < (int)elite.size(); ++j)
                    partners.push_back({dist(elite[0], elite[j]), j});
                sort(partners.begin(), partners.end(), greater<pair<double,int>>());
                for (int z = 0; z < min(3, (int)partners.size()); ++z) {
                    const int j = partners[z].second;
                    tasks.push_back({0, j}); tasks.push_back({j, 0});
                }
            } else {
                // HGS-like mating pressure: select a few pairs jointly by parent
                // quality and structural complementarity, not only best x farthest.
                struct PairPick { double score; int i; int j; double d; };
                vector<PairPick> pp;
                const int nE = (int)elite.size();
                for (int i = 0; i < nE; ++i) for (int j = i + 1; j < nE; ++j) {
                    const double q = nE <= 1 ? 1.0 :
                        1.0 - double(i + j) / double(2 * (nE - 1));
                    const double d = dist(elite[i], elite[j]);
                    pp.push_back({0.56 * q + 0.44 * d, i, j, d});
                }
                sort(pp.begin(), pp.end(), [](const PairPick &x, const PairPick &y) {
                    if (fabs(x.score - y.score) > 1e-12) return x.score > y.score;
                    if (fabs(x.d - y.d) > 1e-12) return x.d > y.d;
                    return x.i + x.j < y.i + y.j;
                });
                if (balanced_memetic) {
                    // Middle ground: bidirectional search on the strongest pair,
                    // plus one forward child from the next complementary pair.
                    // This avoids spreading the ~0.66 s breeding window across
                    // four deep children while retaining more than one mating.
                    if (!pp.empty()) {
                        tasks.push_back({pp[0].i, pp[0].j});
                        tasks.push_back({pp[0].j, pp[0].i});
                    }
                    if (pp.size() >= 2) tasks.push_back({pp[1].i, pp[1].j});
                } else {
                    const int pair_count = min(2, (int)pp.size());
                    for (int z = 0; z < pair_count; ++z) {
                        tasks.push_back({pp[z].i, pp[z].j});
                        tasks.push_back({pp[z].j, pp[z].i});
                    }
                }
            }
            int nt_cap = cfg.use_phase_specialized_engine
                ? tail_compute_cap : max(1, cfg.sa_instances);
            if (cfg.use_phase_specialized_engine &&
                effective_breed_budget < cfg.phase_elite_recombine_full_tasks_s)
                nt_cap = min(nt_cap, 1);
            const int nt = min((int)tasks.size(), nt_cap);
            const double prb = max(0.02, effective_breed_budget *
                (balanced_memetic ? 0.30 : (strong_memetic2 ? 0.40 : (strong_memetic ? 0.30 : 0.35))));
            const double educate_b = max(0.02, effective_breed_budget - prb);
            const double ib = max(0.02, effective_breed_budget * 0.40);
            const double gb = max(0.02, effective_breed_budget - prb - ib);
            vector<SolutionState> kids; mutex km; vector<thread> ths;
            for (int z = 0; z < nt; ++z) {
                const int ia = tasks[z].first;
                const int ibp = tasks[z].second;
                ths.emplace_back([&, z, ia, ibp]() {
                    const bool old = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    SolutionState child;
                    const auto child_t0 = Clock::now();
                    {
                        ScopedWorkerDeadline cap(prb);
                        child = strong_memetic
                            ? path_relink_between_strong(elite[ia], elite[ibp], ev, pm)
                            : path_relink_between(elite[ia], elite[ibp], ev, pm);
                    }
                    recompute_state_metrics_and_loads(child, ev);
                    const double after_pr = child.objective;
                    bool child_valid = solution_hard_feasible(child, CG, pm);
                    SolutionState best_child = child_valid ? child : elite[ia];
                    recompute_state_metrics_and_loads(best_child, ev);
                    if (child_valid) checkpoint_validated_global_best(child,
                        strong_memetic ? "elite_strong_pr_validated" : "elite_pr_validated");

                    double after_inter = best_child.objective;
                    double after_gran = best_child.objective;
                    if (strong_memetic) {
                        if (!solver_should_stop()) {
                            double child_education_budget = educate_b;
                            if (balanced_memetic) {
                                const double used_pr = chrono::duration<double>(Clock::now() - child_t0).count();
                                child_education_budget = max(0.02, effective_breed_budget - used_pr);
                                best_child = memetic_educate_child_balanced(
                                    best_child, ev, pm, child_education_budget,
                                    cfg.base_seed ^ (unsigned)(0xE8A000u + z * 1009u));
                            } else if (strong_memetic2) {
                                const double used_pr = chrono::duration<double>(Clock::now() - child_t0).count();
                                // Reclaim every millisecond PR did not need. The total
                                // child envelope remains breed_budget.
                                child_education_budget = max(0.02, effective_breed_budget - used_pr);
                                best_child = memetic_educate_child_strong2(
                                    best_child, ev, pm, child_education_budget,
                                    cfg.base_seed ^ (unsigned)(0xE8A000u + z * 1009u));
                            } else {
                                best_child = memetic_educate_child_strong(
                                    best_child, ev, pm, child_education_budget,
                                    cfg.base_seed ^ (unsigned)(0xE8A000u + z * 1009u));
                            }
                            recompute_state_metrics_and_loads(best_child, ev);
                            after_inter = best_child.objective;
                            after_gran = best_child.objective;
                        }
                    } else {
                        if (!solver_should_stop()) {
                            SolutionState cand = best_child;
                            { ScopedWorkerDeadline cap(ib); interroute_polish_solution(cand, ev, pm); }
                            recompute_state_metrics_and_loads(cand, ev);
                            after_inter = cand.objective;
                            if (solution_hard_feasible(cand, CG, pm)) {
                                checkpoint_validated_global_best(cand, "elite_inter_validated");
                                if (cand.objective + 1e-9 < best_child.objective) best_child = std::move(cand);
                            }
                        }
                        if (!solver_should_stop()) {
                            SolutionState cand = best_child;
                            { ScopedWorkerDeadline cap(gb); granular_tabu_repair(cand, ev, pm); }
                            recompute_state_metrics_and_loads(cand, ev);
                            after_gran = cand.objective;
                            if (solution_hard_feasible(cand, CG, pm)) {
                                checkpoint_validated_global_best(cand, "elite_granular_validated");
                                if (cand.objective + 1e-9 < best_child.objective) best_child = std::move(cand);
                            }
                        }
                    }
                    recompute_state_metrics_and_loads(best_child, ev);
                    if (solution_hard_feasible(best_child, CG, pm)) {
                        checkpoint_validated_global_best(best_child,
                            strong_memetic ? "elite_strong_child_validated" : "elite_child_validated");
                        lock_guard<mutex> lk(km); kids.push_back(best_child);
                    }
                    safe_log_line(balanced_memetic ? "[BalancedEliteChild] task=" : (strong_memetic2 ? "[StrongEliteChild2] task=" : (strong_memetic ? "[StrongEliteChild] task=" : "[EliteEvolutionChild] task=")), z,
                        " from=", ia, " to=", ibp,
                        " pA=", elite[ia].objective, " pB=", elite[ibp].objective,
                        " pr=", after_pr, " educated=", best_child.objective,
                        " inter_trial=", after_inter, " gran_trial=", after_gran,
                        " elapsed=", solver_elapsed_seconds());
                    tls_defer_global_publish = old;
                });
            }
            for (auto &t : ths) if (t.joinable()) t.join();
            SolutionState out = seed_state;
            recompute_state_metrics_and_loads(out, ev);
            for (auto &k : kids) if (k.objective + 1e-9 < out.objective) out = k;
            out = refresh_from_global(std::move(out));
            safe_log_line("[EliteEvolution] phase=recombine tasks=", nt, " kids=", kids.size(),
                " objective=", out.objective, " elapsed=", solver_elapsed_seconds());
            return out;
        };

        SolutionState staged = best_state;
        staged = intensify_stage(staged, first_budget, "intensify_1");
        const int k_before_div = tail_active_fleet_count(staged);
        staged = diversify_stage(staged, diversify_budget,
                                 (cfg.staged_portfolio_layout == "elite_evolution" || cfg.staged_portfolio_layout == "elite_evolution_strong" || cfg.staged_portfolio_layout == "elite_evolution_strong2" || cfg.staged_portfolio_layout == "elite_evolution_balanced"));
        const int k_after_div = tail_active_fleet_count(staged);
        const bool elite_layout_active =
            (cfg.staged_portfolio_layout == "elite_evolution" ||
             cfg.staged_portfolio_layout == "elite_evolution_strong" ||
             cfg.staged_portfolio_layout == "elite_evolution_strong2" ||
             cfg.staged_portfolio_layout == "elite_evolution_balanced");
        const bool road_phase_recombine_gate = cfg.use_phase_specialized_engine &&
            cfg.solomon_vehicle_penalty <= 0.0;
        if (elite_layout_active &&
            (k_after_div < elite_tail_entry_k || road_phase_recombine_gate)) {
            safe_log_line("[EliteGate-E1] fleet_transition=",
                          (k_after_div < elite_tail_entry_k ? 1 : 0),
                          " road_phase_gate=", (road_phase_recombine_gate ? 1 : 0),
                          " K_before=", k_before_div, " K_after=", k_after_div);
            // Recombine after a fleet transition, or on road-distance E1 where
            // quality/diversity rather than K is the relevant basin criterion.
            // If that fleet layer has collapsed to one basin, immediately fall back
            // to V61's proven final diversify stage instead of wasting the window.
            SolutionState elite_seed = staged;
            staged = elite_recombine_stage(staged, final_budget);
            if (!elite_recombine_executed && !solver_should_stop()) {
                safe_log_line("[EliteEvolution] fallback=final_diversify reason=insufficient_diversity elapsed=",
                              solver_elapsed_seconds());
                staged = diversify_stage(elite_seed, final_budget, false);
            }
        } else {
            staged = diversify_stage(staged, final_budget, false);
        }
        best_state = refresh_from_global(std::move(staged));
        safe_log_line("[StagedPortfolio-V61] complete layout=", cfg.staged_portfolio_layout,
                      " total_budget_s=", total_budget,
                      " objective=", best_state.objective, " elapsed=", solver_elapsed_seconds());
    } else if (cfg.parallel_intensification_tail && tail_slice_s > 0.0 && !solver_should_stop()) {
        // V41: complementary intensifiers receive the same wall-clock window in
        // parallel, capped by the existing six-core budget. This avoids betting
        // the whole tail on a landscape-specific serial ordering.
        SolutionState tail_seed = best_state;
        vector<SolutionState> tail_candidates;
        mutex tail_candidates_mtx;
        vector<thread> tail_threads;
        const double remaining = max(0.0, cfg.hard_time_limit_s - solver_elapsed_seconds());
        const double tail_budget = min(cfg.final_intensification_reserve_s, remaining);
        auto submit = [&](SolutionState cand) {
            recompute_state_metrics_and_loads(cand, ev);
            if (!solution_hard_feasible(cand, CG, pm)) return;
            update_global_best_checked(cand, CG, pm);
            lock_guard<mutex> lk(tail_candidates_mtx);
            tail_candidates.push_back(std::move(cand));
        };

        if (cfg.use_granular_tabu) tail_threads.emplace_back([&]() {
            SolutionState cand = tail_seed;
            { ScopedWorkerDeadline cap(tail_budget); granular_tabu_repair(cand, ev, pm); }
            submit(std::move(cand));
        });
        if (cfg.use_time_window && cfg.metric_mode == "direct") tail_threads.emplace_back([&]() {
            AlgoResult r = sa_worker(
                CG, pm, ev, depot_idx, collections, cfg.base_seed + 0xC01D1u,
                tail_budget, cfg.use_cross2, &greedy_state,
                &shared_conv_log, &conv_mtx, 0);
            submit(std::move(r.best_state));
        });
        else if (cfg.use_route_region_lns) tail_threads.emplace_back([&]() {
            SolutionState cand = tail_seed;
            { ScopedWorkerDeadline cap(tail_budget); route_region_lns_descent(cand, ev, pm); }
            submit(std::move(cand));
        });
        if (cfg.use_time_window && cfg.metric_mode == "direct") tail_threads.emplace_back([&]() {
            // Cold structural restart: global incumbent remains monotone, but
            // this lane is free to rediscover a different low-fleet partition.
            AlgoResult r = sa_worker(
                CG, pm, ev, depot_idx, collections, cfg.base_seed + 0xC02D5u,
                tail_budget, cfg.use_cross2, &greedy_state,
                &shared_conv_log, &conv_mtx, 1);
            submit(std::move(r.best_state));
        });
        else if (cfg.use_boundary_pair_lns) tail_threads.emplace_back([&]() {
            SolutionState cand = tail_seed;
            { ScopedWorkerDeadline cap(tail_budget); boundary_pair_lns_descent(cand, ev, pm); }
            submit(std::move(cand));
        });
        // Legacy geometry refinement had real value on RC1; give it a genuine
        // concurrent lane rather than starving it behind the search deadline.
        tail_threads.emplace_back([&]() {
            SolutionState cand = tail_seed;
            { ScopedWorkerDeadline cap(tail_budget); final_refinement_pass(cand, ev, pm); }
            submit(std::move(cand));
        });
        // One high-throughput feasible LNS lane.
        tail_threads.emplace_back([&]() {
            AlgoResult r = run_parallel_fast_worker_v41(
                tail_seed, ev, pm, tail_budget, cfg.base_seed + 0xFA571u,
                &shared_conv_log, &conv_mtx);
            submit(std::move(r.best_state));
        });
        // One geometry-focused SA lane; slot 3 is an exploiter rather than a
        // fleet specialist or preserved explorer.
        if ((int)tail_threads.size() < max(1, cfg.sa_instances)) tail_threads.emplace_back([&]() {
            AlgoResult r = sa_worker(
                CG, pm, ev, depot_idx, collections, cfg.base_seed + 0x7A11u,
                tail_budget, cfg.use_cross2, &tail_seed,
                &shared_conv_log, &conv_mtx, 3);
            submit(std::move(r.best_state));
        });
        for (auto &th : tail_threads) if (th.joinable()) th.join();
        for (auto &cand : tail_candidates) {
            if (cand.objective + 1e-9 < best_state.objective) best_state = std::move(cand);
        }
        {
            lock_guard<mutex> lock(global_best_mutex);
            if (!global_best_state.routes.empty()) {
                SolutionState gb = global_best_state;
                recompute_state_metrics_and_loads(gb, ev);
                if (solution_hard_feasible(gb, CG, pm) &&
                    gb.objective + 1e-9 < best_state.objective) best_state = std::move(gb);
            }
        }
        safe_log_line("[ParallelTail-V41] threads=", tail_threads.size(),
                      " budget_s=", tail_budget,
                      " elapsed=", solver_elapsed_seconds(),
                      " incumbent=", best_state.objective);
    } else {
    if (cfg.use_granular_tabu && !solver_should_stop()) {
        recompute_state_metrics_and_loads(best_state, ev);

        double before_gt = best_state.objective;
        SolutionState before_gt_state = best_state;

        SolutionState gt_cand = best_state;
        {
            ScopedWorkerDeadline tail_cap(tail_slice_s);
            granular_tabu_repair(gt_cand, ev, pm);
        }

        accept_improving_hard_candidate(
            best_state,
            std::move(gt_cand),
            ev,
            pm,
            "GranularTabu-Final"
        );

        cerr << "[GranularTabu-Final]"
            << " before=" << before_gt
            << " after=" << best_state.objective
            << " gain=" << max(0.0, before_gt - best_state.objective)
            << "\n";
    }

    if (!global_best_state.routes.empty()) {
        SolutionState gb = global_best_state;
        recompute_state_metrics_and_loads(gb, ev);

        if (solution_hard_feasible(gb, CG, pm) &&
            gb.objective + 1e-9 < best_state.objective) {
            best_state = gb;
        }
    }

    if (cfg.use_route_pair_diag) {
        print_route_pair_diagnostics(best_state, ev, pm);
        print_route_pair_boundary_customers(best_state, ev, pm, 8);
    }

    if (cfg.use_route_region_lns && !solver_should_stop()) {
        SolutionState cand = best_state;
        {
            ScopedWorkerDeadline tail_cap(tail_slice_s);
            route_region_lns_descent(cand, ev, pm);
        }
        accept_improving_hard_candidate(
            best_state,
            std::move(cand),
            ev,
            pm,
            "RouteRegionLNS-Final"
        );

        if (cfg.use_route_pair_diag) {
            cerr << "[RouteRegionLNS] post-lns objective="
                << best_state.objective << "\n";
        }
    }

    if (cfg.use_boundary_pair_lns && !solver_should_stop()) {
        SolutionState cand = best_state;
        {
            ScopedWorkerDeadline tail_cap(tail_slice_s);
            boundary_pair_lns_descent(cand, ev, pm);
        }
        accept_improving_hard_candidate(best_state, std::move(cand), ev, pm, "BoundaryPairLNS-Final");

        if (cfg.use_route_pair_diag) {
            cerr << "[BoundaryPairLNS] post-lns objective="
                << best_state.objective << "\n";
        }
    }

    }

    // E14 compact deadline finish.  If the phase/tail machinery returns early,
    // use at most a couple of cold exact lanes from the best and one diverse
    // competitive elite.  This preserves M1's 100C late strength without
    // restarting the full six-role portfolio.
    if (cfg.use_phase_specialized_engine && cfg.phase_compact_deadline_finish &&
        (int)collections.size() < cfg.phase_structure_min_customers &&
        cfg.hard_time_limit_s > 0.0 && !solver_should_stop()) {
        const double remaining = cfg.hard_time_limit_s - solver_elapsed_seconds();
        const double finish_budget = max(0.0, remaining - cfg.phase_tail_deadline_guard_s);
        if (finish_budget >= cfg.phase_compact_finish_min_s) {
            const int hwf_raw = (int)thread::hardware_concurrency();
            const int hwf = hwf_raw > 0 ? hwf_raw : max(1, cfg.sa_instances);
            const int fw = min({cfg.phase_compact_finish_workers, max(1, cfg.sa_instances), max(1, hwf)});
            vector<SolutionState> finish_seeds;
            finish_seeds.push_back(best_state);
            for (const auto &e : final_sa.elite_states) {
                if ((int)finish_seeds.size() >= fw) break;
                if (phase_structural_distance(e, best_state, CG) >=
                    max(0.02, cfg.phase_archive_clone_distance * 1.5))
                    finish_seeds.push_back(e);
            }
            while ((int)finish_seeds.size() < fw) finish_seeds.push_back(best_state);
            vector<AlgoResult> fr(fw);
            vector<thread> fth;
            const double before_finish = best_state.objective;
            for (int i = 0; i < fw; ++i) {
                const unsigned ss = cfg.base_seed + 0xE14F000u + (unsigned)i * 65537u;
                const SolutionState start_state = finish_seeds[i];
                fth.emplace_back([&, i, ss, start_state]() mutable {
                    const bool old_defer = tls_defer_global_publish;
                    tls_defer_global_publish = true;
                    fr[i] = sa_worker(CG, pm, ev, depot_idx, collections, ss,
                        finish_budget, cfg.use_cross2, &start_state,
                        &shared_conv_log, &conv_mtx, 2 + (i % 2), 0);
                    tls_defer_global_publish = old_defer;
                });
            }
            for (auto &t : fth) if (t.joinable()) t.join();
            for (auto &r : fr) {
                recompute_state_metrics_and_loads(r.best_state, ev);
                if (solution_hard_feasible(r.best_state, CG, pm) &&
                    r.best_state.objective + 1e-9 < best_state.objective)
                    best_state = r.best_state;
                if (solution_hard_feasible(r.best_state, CG, pm))
                    update_global_best_checked(r.best_state, CG, pm);
            }
            {
                lock_guard<mutex> lock(global_best_mutex);
                if (!global_best_state.routes.empty()) {
                    SolutionState gb = global_best_state;
                    recompute_state_metrics_and_loads(gb, ev);
                    if (solution_hard_feasible(gb, CG, pm) &&
                        gb.objective + 1e-9 < best_state.objective) best_state = std::move(gb);
                }
            }
            safe_log_line("[PhaseCompactFinish-E25] workers=", fw,
                          " budget_s=", finish_budget,
                          " before=", before_finish,
                          " after=", best_state.objective,
                          " gain=", max(0.0, before_finish - best_state.objective),
                          " elapsed=", solver_elapsed_seconds());
        }
    }

    // V40 work-conserving tail: static reservations are upper bounds, not sunk
    // costs. If an intensifier returns early, immediately give the unused wall
    // time back to the productive SA portfolio rather than ending the search
    // below T. This preserves a real fixed-budget contract.
    if (cfg.hard_time_limit_s > 0.0 && cfg.work_conserving_tail && !solver_should_stop() &&
        !cfg.use_phase_specialized_engine) {
        int refill_round = 0;
        const double refill_begin = solver_elapsed_seconds();
        while (!solver_should_stop() && refill_round < 64) {
            const double remaining = cfg.hard_time_limit_s - solver_elapsed_seconds();
            if (remaining <= 1e-3) break;

            SolutionState refill_start = best_state;
            {
                lock_guard<mutex> lock(global_best_mutex);
                if (!global_best_state.routes.empty()) refill_start = global_best_state;
            }
            recompute_state_metrics_and_loads(refill_start, ev);
            if (!solution_hard_feasible(refill_start, CG, pm)) break;

            const double refill_budget = min(cfg.sa_time_limit, remaining);
            if (refill_budget <= 1e-4) break;
            const int instances = max(1, cfg.sa_instances);
            vector<thread> refill_threads;
            refill_threads.reserve(instances);
            for (int i = 0; i < instances && !solver_should_stop(); ++i) {
                const unsigned rseed = cfg.base_seed + 9000007u +
                    (unsigned)refill_round * 1000003u + (unsigned)i * 10007u;
                refill_threads.emplace_back([&, rseed, i]() {
                    AlgoResult r;
                    if (cfg.use_parallel_fast_worker && instances >= 2 && i == instances - 1) {
                        r = run_parallel_fast_worker_v41(
                            refill_start, ev, pm, refill_budget, rseed + 0x51F17u,
                            &shared_conv_log, &conv_mtx
                        );
                    } else {
                        r = sa_worker(
                            CG, pm, ev, depot_idx, collections, rseed,
                            refill_budget, cfg.use_cross2, &refill_start,
                            &shared_conv_log, &conv_mtx, i
                        );
                    }
                    recompute_state_metrics_and_loads(r.best_state, ev);
                    if (solution_hard_feasible(r.best_state, CG, pm))
                        update_global_best_checked(r.best_state, CG, pm);
                });
            }
            for (auto &th : refill_threads) if (th.joinable()) th.join();

            {
                lock_guard<mutex> lock(global_best_mutex);
                if (!global_best_state.routes.empty()) {
                    SolutionState gb = global_best_state;
                    recompute_state_metrics_and_loads(gb, ev);
                    if (solution_hard_feasible(gb, CG, pm) &&
                        gb.objective + 1e-9 < best_state.objective) best_state = std::move(gb);
                }
            }
            ++refill_round;
        }
        safe_log_line("[WorkConservingTail-V40] rounds=", refill_round,
                      " begin_elapsed=", refill_begin,
                      " end_elapsed=", solver_elapsed_seconds(),
                      " remaining=", max(0.0, cfg.hard_time_limit_s - solver_elapsed_seconds()));
    }
    if (cfg.hard_time_limit_s <= 0.0 && metric_is_euclidean() && cfg.euclidean_swapstar && !cfg.euclidean_hgs_only) {
        cerr << "[SWAP*] final pre-output start obj="
            << best_state.objective << "\n";

        euclidean_swapstar_descent(best_state, ev, pm);
        recompute_state_metrics_and_loads(best_state, ev);

        cerr << "[SWAP*] final pre-output end obj="
            << best_state.objective << "\n";
    }

    if (cfg.hard_time_limit_s <= 0.0 && metric_is_euclidean() && cfg.euclidean_two_opt_star && !cfg.euclidean_hgs_only) {
        cerr << "[2-opt*] final pre-output start obj="
            << best_state.objective << "\n";

        euclidean_two_opt_star_descent(best_state, ev, pm);
        recompute_state_metrics_and_loads(best_state, ev);

        cerr << "[2-opt*] final pre-output end obj="
            << best_state.objective << "\n";
    }

    if (cfg.hard_time_limit_s <= 0.0 && metric_is_euclidean() && cfg.euclidean_deep_interroute && !cfg.euclidean_hgs_only) {
        cerr << "[euclidean-deep] final pre-output polish start obj="
            << best_state.objective << "\n";

        euclidean_deep_interroute_descent(best_state, ev, pm);

        cerr << "[euclidean-deep] final pre-output polish end obj="
            << best_state.objective << "\n";
    }

    if (cfg.hard_time_limit_s <= 0.0 && metric_is_euclidean() && cfg.use_hgs_lite && !cfg.euclidean_hgs_only) {
        cerr << "[HGS-lite] final start obj="
            << best_state.objective << "\n";

        SolutionState hgs_final = hgs_lite_euclidean(
            best_state,
            CG,
            ev,
            pm,
            cfg.base_seed + 7654321
        );

        if (solution_hard_feasible(hgs_final, CG, pm) &&
            hgs_final.objective + 1e-9 < best_state.objective) {
            best_state = hgs_final;
            recompute_state_metrics_and_loads(best_state, ev);
        }

        cerr << "[HGS-lite] final end obj="
            << best_state.objective << "\n";
    }

    recompute_state_metrics_and_loads(best_state, ev);

    if (!solution_hard_feasible(best_state, CG, pm)) {
        cerr << "[FinalPolish] produced infeasible final candidate; rolling back\n";
        best_state = std::move(pre_output_polish_state);
        recompute_state_metrics_and_loads(best_state, ev);
    }

    // V5: final output under a hard budget is exactly the best hard-feasible
    // state whose validated completion timestamp was <= T. This prevents a
    // long operator that finishes after T from leaking into printed results.
    if (cfg.hard_time_limit_s > 0.0) {
        lock_guard<mutex> lock(global_best_mutex);
        if (!global_best_state.routes.empty()) best_state = global_best_state;
    }
    recompute_state_metrics_and_loads(best_state, ev);

    bool feasible_final = solution_hard_feasible(best_state, CG, pm);

    if (!feasible_final) {
        cerr << "[FINAL] no hard-feasible final solution available\n";
        return 2;
    }

    FinalSummary final_summary = summarize_solution(best_state);

    const double pipeline_runtime_s = chrono::duration<double>(
        Clock::now() - total_start_time
    ).count();
    const double phase_args_s = chrono::duration<double>(phase_after_args - total_start_time).count();
    const double governed_elapsed_s = solver_elapsed_seconds();
    safe_log_line("[PhaseLedger-V40] args_s=", phase_args_s,
                  " input_s=", phase_input_s,
                  " backend_s=", phase_backend_s,
                  " warm_start_s=", phase_warm_start_s,
                  " governed_elapsed_s=", governed_elapsed_s,
                  " pipeline_before_output_s=", pipeline_runtime_s,
                  " budget_scope=", cfg.budget_scope);

    const long long aggregate_sa_iterations =
        profile.sa_iterations.load(memory_order_relaxed);
    const long long aggregate_sa_accepted =
        profile.sa_accepted_moves.load(memory_order_relaxed);
    const long long aggregate_sa_attempted =
        profile.sa_attempted_moves.load(memory_order_relaxed);
    const long long aggregate_drift_corrections =
        profile.sa_drift_corrections.load(memory_order_relaxed);
    const long long aggregate_capacity_trials =
        profile.sa_capacity_violation_trials.load(memory_order_relaxed);
    const double aggregate_trial_overload =
        static_cast<double>(
            profile.sa_total_overload_milli.load(memory_order_relaxed)
        ) / 1000.0;

    append_run_summary_csv(
        "final_best",
        best_state,
        CG,
        final_summary,
        pipeline_runtime_s,
        aggregate_sa_iterations,
        aggregate_sa_accepted,
        aggregate_sa_attempted,
        aggregate_drift_corrections,
        aggregate_capacity_trials,
        aggregate_trial_overload,
        feasible_final
    );

    append_repair_summary_csv(
        final_summary,
        pipeline_runtime_s,
        feasible_final
    );
    write_repair_trace_csv();

    cout.setf(std::ios::fixed);

    recompute_state_metrics_and_loads(best_state, ev);

    auto missing = get_missing_customers(best_state, CG);
    auto dup = get_duplicate_customers(best_state, CG);

    if (!missing.empty() || !dup.empty()) {
        cerr << "[FINAL FEASIBILITY ERROR]\n";

        cerr << "Missing customers:";
        for (int x : missing) cerr << " " << x;
        cerr << "\n";

        cerr << "Duplicate customers:";
        for (int x : dup) cerr << " " << x;
        cerr << "\n";
    }

    cout << "============================================================\n";
    cout << "                 ALGORITHM COMPARISON\n";
    cout << "============================================================\n";
    cout << left
        << setw(20) << "Algorithm"
        << setw(16) << "Objective"
        << setw(14) << "Distance(m)"
        << setw(12) << "CO2(g)"
        << setw(12) << "Time(s)"
        << "\n";
    cout << "Objective mode   : " << cfg.objective_mode << "\n";
    cout << "Allow multi-trip : "
        << (cfg.allow_multi_trip ? "YES" : "NO") << "\n";
    cout << "Max trips/truck  : "
        << (cfg.max_trips_per_truck == 0
                ? string("unlimited")
                : to_string(cfg.max_trips_per_truck))
        << "\n";
    cout << "------------------------------------------------------------\n";

    auto print_row = [&](const RunSummary &r) {
        if (!valid_run_summary(r)) return;

        cout << left
            << setw(20) << r.name
            << setw(16) << setprecision(3) << r.objective
            << setw(14) << r.distance_m
            << setw(12) << r.co2_g
            << setw(12) << r.runtime
            << "\n";
    };

    print_row(greedy_summary);
    print_row(sa_no_cross);
    print_row(sa_full);

    RunSummary final_row;
    final_row.name = "Final";
    final_row.objective = best_state.objective;
    final_row.distance_m = final_summary.distance_m;
    final_row.co2_g = final_summary.co2_g;
    final_row.runtime = pipeline_runtime_s;
    final_row.iterations = static_cast<double>(aggregate_sa_iterations);
    final_row.accepted = aggregate_sa_accepted;
    final_row.attempted = aggregate_sa_attempted;

    print_row(final_row);

    if (!valid_run_summary(best_overall) ||
        final_row.objective + 1e-9 < best_overall.objective) {
        best_overall = final_row;
    }

    cout << "------------------------------------------------------------\n";
    cout << "Best algorithm      : " << best_overall.name << "\n";

    double improvement = 0.0;
    if (valid_run_summary(greedy_summary) &&
        valid_run_summary(best_overall) &&
        greedy_summary.objective > 1e-12) {
        improvement = 100.0 *
            (greedy_summary.objective - best_overall.objective) /
            greedy_summary.objective;
    }

    cout << "Improvement vs " << greedy_summary.name
        << " : " << setprecision(2) << improvement << " %\n";
    cout << setprecision(3);

    if (stability_objs.empty()) {
        cout << "Stability runs          : N/A (completed n=0)\n";
    }
    else {
        cout << "Stability runs (SA_full): mean=" << mean_obj
            << " std=" << std_obj
            << " (completed n=" << stability_objs.size() << ")\n";
    }

    cout << "Final solution feasible : "
        << (feasible_final ? "YES" : "NO") << "\n";
    cout << "Pipeline runtime        : " << pipeline_runtime_s << " s\n";
    cout << "Governed runtime        : " << governed_elapsed_s << " s\n";
    cout << "Budget scope            : " << cfg.budget_scope << "\n";
    cout << "Input parse wall        : " << phase_input_s << " s\n";
    cout << "Backend/precompute wall : " << phase_backend_s << " s\n";
    cout << "Warm-start wall         : " << phase_warm_start_s << " s\n";
    cout << "Hard deadline           : " << cfg.hard_time_limit_s << " s\n";
    cout << "Deadline overrun        : " << solver_deadline_overrun_seconds() << " s\n";
    cout << "Late improvements censored: "
        << profile.late_feasible_improvements_rejected.load(memory_order_relaxed) << "\n";
    cout << "Cooperative stop polls  : "
        << profile.cooperative_stop_polls.load(memory_order_relaxed) << "\n";
    cout << "SA effective proposals  : " << profile.sa_effective_proposals.load(memory_order_relaxed) << "\n";
    cout << "SA proposal utilization : "
        << (profile.sa_attempted_moves.load(memory_order_relaxed) > 0
            ? (double)profile.sa_effective_proposals.load(memory_order_relaxed) / (double)profile.sa_attempted_moves.load(memory_order_relaxed)
            : 0.0) << "\n";
    cout << "SA route-draw failures  : " << profile.sa_route_draw_failures.load(memory_order_relaxed) << "\n";
    cout << "Fleet elimination calls : "
        << profile.fleet_elim_calls.load(memory_order_relaxed) << "\n";
    cout << "Fleet elimination wins  : "
        << profile.fleet_elim_successes.load(memory_order_relaxed) << "\n";
    cout << "Fleet ejection attempts : " << profile.fleet_ejection_chain_attempts.load(memory_order_relaxed) << "\n";
    cout << "Fleet ejection wins     : " << profile.fleet_ejection_chain_successes.load(memory_order_relaxed) << "\n";
    cout << "Fleet ejection candidates: " << profile.fleet_ejection_chain_candidates.load(memory_order_relaxed) << "\n";
    cout << "Fleet migration checks   : " << profile.global_fleet_migration_checks.load(memory_order_relaxed) << "\n";
    cout << "Fleet migration adoptions: " << profile.global_fleet_migration_adoptions.load(memory_order_relaxed) << "\n";
    cout << "Worker local deadline     : cooperative nested-operator bound\n";
    cout << "Final intensify reserve   : " << cfg.final_intensification_reserve_s << " s\n";
    cout << "Work-conserving tail      : " << (cfg.work_conserving_tail ? "YES" : "NO") << "\n";
    cout << "Parallel fast worker     : " << (cfg.use_parallel_fast_worker ? "YES" : "NO") << "\n";
    cout << "SA refinement reserve    : " << cfg.sa_refinement_reserve_fraction << "\n";
    cout << "Same-fleet migration     : " << (cfg.use_same_fleet_migration ? "YES" : "NO") << "\n";
    cout << "Parallel tail            : " << (cfg.parallel_intensification_tail ? "YES" : "NO") << "\n";
    cout << "Staged portfolio tail     : " << (cfg.staged_portfolio_tail ? "YES" : "NO") << "\n";
    cout << "Staged portfolio layout   : " << cfg.staged_portfolio_layout << "\n";
    cout << "Budget saturation rounds : " << profile.budget_saturation_rounds.load(memory_order_relaxed) << "\n";
    cout << "Worker roles S/X/E        : " << profile.worker_role_structural.load(memory_order_relaxed) << "/"
         << profile.worker_role_exploiter.load(memory_order_relaxed) << "/"
         << profile.worker_role_explorer.load(memory_order_relaxed) << "\n";
    cout << "Candidate-route affinity  : calls=" << profile.candidate_route_affinity_calls.load(memory_order_relaxed)
         << " nodes=" << profile.candidate_route_affinity_nodes_scanned.load(memory_order_relaxed)
         << " unbiased=" << (cfg.candidate_route_unbiased_scan ? "YES" : "NO") << "\n";
    cout << "Interroute arc pruning    : pruned=" << profile.interroute_arc_delta_pruned.load(memory_order_relaxed)
         << " survivors=" << profile.interroute_arc_delta_survivors.load(memory_order_relaxed) << "\n";
    cout << "Path relink calls         : " << profile.path_relink_calls.load(memory_order_relaxed) << "\n";
    cout << "Path relink steps         : " << profile.path_relink_steps.load(memory_order_relaxed) << "\n";
    cout << "Path relink progress      : " << profile.path_relink_feasible_progress.load(memory_order_relaxed) << "\n";
    cout << "Path relink best gains    : " << profile.path_relink_best_improvements.load(memory_order_relaxed) << "\n";
    cout << "Asym 2-opt candidates     : " << profile.asymmetric_2opt_candidates.load(memory_order_relaxed) << "\n";
    cout << "Asym 2-opt improvements   : " << profile.asymmetric_2opt_improvements.load(memory_order_relaxed) << "\n";
    cout << "2-opt route calls         : " << profile.two_opt_route_calls.load(memory_order_relaxed) << "\n";
    cout << "2-opt route time (s)      : " << profile_seconds(profile.two_opt_route_time_us) << "\n";
    cout << "Boundary-pair calls       : " << profile.boundary_pair_calls.load(memory_order_relaxed) << "\n";
    cout << "Granular-tabu calls       : " << profile.granular_tabu_calls.load(memory_order_relaxed) << "\n";
    cout << "Granular candidate evals  : " << profile.granular_tabu_candidate_evals.load(memory_order_relaxed) << "\n";
    cout << "Granular accepted moves   : " << profile.granular_tabu_accepted_moves.load(memory_order_relaxed) << "\n";
    cout << "Granular worker time (s)  : " << profile_seconds(profile.granular_tabu_time_us) << "\n";
    cout << "SA stop local-time        : " << profile.sa_stop_local_time.load(memory_order_relaxed) << "\n";
    cout << "SA stop global-deadline   : " << profile.sa_stop_global_deadline.load(memory_order_relaxed) << "\n";
    cout << "SA stop proposal-cap      : " << profile.sa_stop_proposal_cap.load(memory_order_relaxed) << "\n";
    cout << "Interroute relocate calls : " << profile.interroute_relocate_calls.load(memory_order_relaxed) << "\n";
    cout << "Interroute swap calls     : " << profile.interroute_swap_calls.load(memory_order_relaxed) << "\n";
    cout << "Interroute 2opt* calls    : " << profile.interroute_twooptstar_calls.load(memory_order_relaxed) << "\n";
    cout << "Interroute pairs available: " << profile.interroute_pairs_available.load(memory_order_relaxed) << "\n";
    cout << "Interroute pairs touched  : " << profile.interroute_pairs_touched.load(memory_order_relaxed) << "\n";
    cout << "Interroute candidate scans: " << profile.interroute_candidate_scans.load(memory_order_relaxed) << "\n";
    cout << "Interroute exact evals    : " << profile.interroute_exact_evals.load(memory_order_relaxed) << "\n";
    cout << "Interroute time (s)       : " << profile_seconds(profile.interroute_time_us) << "\n";
    cout << "HGS Split calls           : " << profile.hgs_split_calls.load(memory_order_relaxed) << "\n";
    cout << "HGS Split fast segments   : " << profile.hgs_split_fast_segments.load(memory_order_relaxed) << "\n";
    cout << "HGS Split exact segments  : " << profile.hgs_split_exact_segments.load(memory_order_relaxed) << "\n";
    cout << "HGS Split time (s)        : " << profile_seconds(profile.hgs_split_time_us) << "\n";
    cout << "String-slack kick enabled : " << (cfg.use_string_slack_kick ? "YES" : "NO") << "\n";
    cout << "String-slack kick calls   : " << profile.string_slack_kick_calls.load(memory_order_relaxed) << "\n";
    cout << "String-slack kick wins    : " << profile.string_slack_kick_improvements.load(memory_order_relaxed) << "\n";
    cout << "String-slack kick time (s): " << profile_seconds(profile.string_slack_kick_time_us) << "\n";
    cout << "String stagnation threshold: " << cfg.string_slack_stagnation_s << " s\n";
    cout << "String trigger checks      : " << profile.string_slack_kick_trigger_checks.load(memory_order_relaxed) << "\n";
    cout << "String stagnation eligible : " << profile.string_slack_kick_stagnation_eligible.load(memory_order_relaxed) << "\n";
    cout << "String feasible-best gains : " << profile.string_slack_kick_feasible_best_improvements.load(memory_order_relaxed) << "\n";
    cout << "String global-best gains   : " << profile.string_slack_kick_global_best_improvements.load(memory_order_relaxed) << "\n";
    cout << "String worse macro accepts : " << profile.string_slack_kick_metropolis_worse_accepts.load(memory_order_relaxed) << "\n";
    cout << "In-loop ALNS enabled       : " << (cfg.use_time_stagnation_alns_kick ? "YES" : "NO") << "\n";
    cout << "In-loop ALNS calls         : " << profile.alns_kick_calls.load(memory_order_relaxed) << "\n";
    cout << "In-loop ALNS state gains   : " << profile.alns_kick_state_improvements.load(memory_order_relaxed) << "\n";
    cout << "In-loop ALNS feasible gains: " << profile.alns_kick_feasible_best_improvements.load(memory_order_relaxed) << "\n";
    cout << "In-loop ALNS global gains  : " << profile.alns_kick_global_best_improvements.load(memory_order_relaxed) << "\n";
    cout << "In-loop ALNS worse accepts : " << profile.alns_kick_metropolis_worse_accepts.load(memory_order_relaxed) << "\n";
    cout << "In-loop ALNS time (s)      : " << profile_seconds(profile.alns_kick_time_us) << "\n";
    cout << "In-loop ALNS destroy calls : " << profile.alns_kick_destroy0_calls.load(memory_order_relaxed) << "/" << profile.alns_kick_destroy1_calls.load(memory_order_relaxed) << "/" << profile.alns_kick_destroy2_calls.load(memory_order_relaxed) << "\n";
    cout << "============================================================\n\n";

    cout << "============================================================\n";
    cout << "               TRUCK ROUTE BREAKDOWN (USED TRUCKS)\n";
    cout << "============================================================\n\n";

    double global_distance = 0.0;
    double global_time = 0.0;
    double global_co2 = 0.0;
    double global_service = 0.0;
    double global_waiting = 0.0;
    double global_lateness = 0.0;
    double global_load = 0.0;
    int printed_used_trucks = 0;

    for (size_t t = 0; t < best_state.routes.size(); ++t) {
        const auto &route = best_state.routes[t];

        double total_load = 0.0;
        int customers = 0;
        for (int nid : route) {
            if (nid >= 0 &&
                nid < static_cast<int>(CG.nodes.size()) &&
                CG.nodes[nid].type == 2) {
                total_load += CG.nodes[nid].garbage_amount;
                customers++;
            }
        }

        if (customers == 0) continue;
        printed_used_trucks++;

        auto rm = ev.compute_route_metrics(
            route,
            best_state.route_max_trip_load[t]
        );

        const double max_trip_load = best_state.route_max_trip_load[t];
        const double route_duration =
            rm.travel_seconds + rm.waiting + rm.service;

        cout << "------------------------------------------------------------\n";
        cout << "Truck ID         : " << t << "\n";
        cout << "Customers Served : " << customers << "\n";
        {
            ostringstream pct;
            pct << fixed << setprecision(1)
                << (cfg.truck_capacity > 0.0
                        ? max_trip_load / cfg.truck_capacity * 100.0
                        : 0.0);
            cout << "Max trip load    : " << max_trip_load
                << " / " << cfg.truck_capacity
                << " (" << pct.str() << "%)\n";
        }
        cout << "Total Load       : " << total_load << "\n";
        cout << "Distance Driven  : " << rm.distance_m << " m\n";
        cout << "Travel Time      : " << rm.travel_seconds << " s\n";
        cout << "Service Time     : " << rm.service << " s\n";
        cout << "Waiting Time     : " << rm.waiting << " s\n";
        cout << "Lateness         : " << rm.lateness << " s\n";
        cout << "Route Duration   : " << route_duration << " s\n";
        cout << "CO2 Emitted      : " << rm.co2_g << " g\n";
        cout << "Efficiency Score : "
            << (route_duration > 0.0 ? total_load / route_duration : 0.0)
            << " kg/s\n";
        cout << "Path             : ";
        for (size_t i = 0; i < route.size(); ++i) {
            cout << route[i];
            if (i + 1 < route.size()) cout << " -> ";
        }
        cout << "\n";
        cout << "------------------------------------------------------------\n\n";

        global_distance += rm.distance_m;
        global_time += rm.travel_seconds;
        global_co2 += rm.co2_g;
        global_service += rm.service;
        global_waiting += rm.waiting;
        global_lateness += rm.lateness;
        global_load += total_load;
    }

    const double available_fleet_capacity =
        cfg.truck_capacity * max(1, cfg.num_trucks);
    const double used_fleet_capacity =
        cfg.truck_capacity * max(1, final_summary.used_trucks);
    const double available_fleet_utilization =
        available_fleet_capacity > 0.0
            ? 100.0 * global_load / available_fleet_capacity
            : 0.0;
    const double average_used_truck_load =
        used_fleet_capacity > 0.0
            ? 100.0 * global_load / used_fleet_capacity
            : 0.0;
    const double fleet_balance =
        final_summary.used_trucks > 1
            ? final_summary.max_route_duration_s -
            final_summary.min_route_duration_s
            : 0.0;

    cout << "============================================================\n";
    cout << "                 FLEET SUMMARY\n";
    cout << "============================================================\n";
    cout << "Used Trucks      : " << final_summary.used_trucks
        << " / " << cfg.num_trucks << "\n";
    cout << "Printed Trucks   : " << printed_used_trucks << "\n";
    cout << "Total Distance   : " << global_distance << " m\n";
    cout << "Total Travel Time: " << global_time << " s\n";
    cout << "Total Service    : " << global_service << " s\n";
    cout << "Total Waiting    : " << global_waiting << " s\n";
    cout << "Total Lateness   : " << global_lateness << " s\n";
    cout << "Total CO2        : " << global_co2 << " g\n";
    cout << "Total Load       : " << global_load << "\n";
    cout << "Total Trips      : " << final_summary.total_trips << "\n";
    cout << "Max Trips/Truck  : "
        << final_summary.max_trips_single_truck << "\n";
    cout << "Max Trip Load    : " << final_summary.max_trip_load
        << " / " << cfg.truck_capacity << "\n";
    cout << "Fleet Capacity % : " << setprecision(2)
        << available_fleet_utilization << " %\n";
    cout << "Used-Truck Load %: "
        << average_used_truck_load << " %\n";
    cout << "Fleet Balance    : " << fleet_balance << " s\n";
    cout << setprecision(3);
    cout << "============================================================\n\n";

    const double aggregate_acceptance_rate =
        aggregate_sa_attempted > 0
            ? 100.0 * static_cast<double>(aggregate_sa_accepted) /
            static_cast<double>(aggregate_sa_attempted)
            : 0.0;

    cout << "================ SEARCH STATISTICS =========================\n";
    cout << "SA iterations total       : " << aggregate_sa_iterations << "\n";
    cout << "SA attempted moves        : " << aggregate_sa_attempted << "\n";
    cout << "SA accepted moves         : " << aggregate_sa_accepted << "\n";
    cout << "SA acceptance rate        : " << setprecision(2)
        << aggregate_acceptance_rate << " %\n";
    cout << setprecision(3);
    cout << "SA drift corrections      : "
        << aggregate_drift_corrections << "\n";
    cout << "Infeasible capacity trials: "
        << aggregate_capacity_trials << "\n";
    cout << "Trial overload total      : "
        << aggregate_trial_overload << "\n";
    cout << "Aggregate SA worker time  : "
        << profile_seconds(profile.sa_time_us) << " s\n";
    cout << "============================================================\n\n";

    cout << "------------------ BACKEND PROFILING -----------------------\n";
    cout << "Metric mode               : " << cfg.metric_mode << "\n";
    cout << "Dense matrix ready        : "
        << (dense_pairs.ready ? "YES" : "NO") << "\n";
    cout << "Compact terminal count    : " << dense_pairs.C << "\n";
    cout << "Recompute calls           : "
        << profile.recompute_calls.load(memory_order_relaxed) << "\n";
    cout << "Adaptive ALNS calls       : "
        << profile.alns_calls.load(memory_order_relaxed) << "\n";
    cout << "Final-polish calls        : "
        << profile.polish_calls.load(memory_order_relaxed) << "\n";
    cout << "Pair fallback queries     : "
        << profile.pair_queries.load(memory_order_relaxed) << "\n";
    cout << "Adaptive ALNS worker time : "
        << profile_seconds(profile.alns_time_us) << " s\n";
    cout << "Final-polish worker time  : "
        << profile_seconds(profile.polish_time_us) << " s\n";
    cout << "Repair mode               : "
        << repair_mode_name(effective_repair_mode()) << "\n";
    cout << "Repair calls              : "
        << repair_profile.calls.load(memory_order_relaxed) << "\n";
    cout << "Successful repairs        : "
        << repair_profile.successful_calls.load(memory_order_relaxed) << "\n";
    cout << "Failed repairs            : "
        << repair_profile.failed_calls.load(memory_order_relaxed) << "\n";
    cout << "Repair worker time        : "
        << profile_seconds(repair_profile.repair_time_us) << " s\n";
    cout << "Exact route evaluations   : "
        << repair_profile.exact_route_evaluations.load(memory_order_relaxed) << "\n";
    cout << "Ranked insertion positions: "
        << repair_profile.positions_ranked.load(memory_order_relaxed) << "\n";
    cout << "Improving LNS moves       : "
        << repair_profile.improving_lns_moves.load(memory_order_relaxed) << "\n";
    cout << "LNS benchmark iterations  : "
        << repair_profile.benchmark_iterations.load(memory_order_relaxed) << "\n";
    cout << "LNS benchmark no-op iters : "
        << repair_profile.benchmark_noop_iterations.load(memory_order_relaxed) << "\n";
    cout << "LNS benchmark time        : "
        << profile_seconds(repair_profile.benchmark_time_us) << " s\n";
    cout << "Dense fallback time calls : "
        << dense_pairs.fallback_time_calls.load(memory_order_relaxed)
        << "\n";
    cout << "Dense fallback dist calls : "
        << dense_pairs.fallback_dist_calls.load(memory_order_relaxed)
        << "\n";
#if VRP_PROFILE_DENSE_HITS
    cout << "Dense time lookup hits    : "
        << dense_pairs.fast_time_hits.load(memory_order_relaxed) << "\n";
    cout << "Dense dist lookup hits    : "
        << dense_pairs.fast_dist_hits.load(memory_order_relaxed) << "\n";
#else
    cout << "Dense hit counters        : disabled at compile time\n";
#endif
    cout << "============================================================\n\n";

    if (dense_pairs.ready &&
        (dense_pairs.fallback_time_calls.load(memory_order_relaxed) > 0 ||
        dense_pairs.fallback_dist_calls.load(memory_order_relaxed) > 0)) {
        safe_log_line(
            "[RuntimeRisk] Dense matrix fallback occurred. ",
            "Some candidate pairs are not using O(1) dense lookup."
        );
    }

    if (cfg.log_convergence && !shared_conv_log.empty()) {
    ofstream out(cfg.convergence_csv);

        if (out.is_open()) {
            sort(shared_conv_log.begin(), shared_conv_log.end(),
                [](const ConvergenceLogRow &a, const ConvergenceLogRow &b) {
                    if (a.time_s != b.time_s) return a.time_s < b.time_s;
                    if (a.seed != b.seed) return a.seed < b.seed;
                    return a.iter < b.iter;
                });
            // Production telemetry contract: keep the worker-local trajectory,
            // but also write an explicit stream identity and a process-wide
            // monotone best after globally sorting the rows.  This removes any
            // need for the analyzer to infer a global incumbent from interleaved
            // worker-local best_obj values.  The seed is the stable stream id.
            out << "time_s,seed,stream_id,iter,current_obj,best_obj,global_best_obj,temp,"
                << "accepted_moves,attempted_moves,acceptance_rate,stagnation,event\n";

            double process_global_best = INF_D;
            for (const auto &r : shared_conv_log) {
                double acceptance_rate =
                r.attempted_moves > 0
                ? (double)r.accepted_moves / (double)r.attempted_moves
                : 0.0;
                if (isfinite(r.best_obj) && r.best_obj > 0.0)
                    process_global_best = min(process_global_best, r.best_obj);

                out << fixed << setprecision(12)
                    << r.time_s << ","
                    << r.seed << ","
                    << r.seed << ","
                    << r.iter << ","
                    << r.current_obj << ","
                    << r.best_obj << ","
                    << (process_global_best < INF_D / 2.0 ? process_global_best : r.best_obj) << ","
                    << r.temp << ","
                    << r.accepted_moves << ","
                    << r.attempted_moves << ","
                    << acceptance_rate << ","
                    << r.stagnation << ","
                    << r.event << "\n";
            }

            out.close();
        }
    }
    return 0;
}
