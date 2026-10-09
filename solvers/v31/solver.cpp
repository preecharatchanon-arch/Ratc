// Final reporting/instrumentation cleanup. Search operators and hot-path
// objective logic are intentionally unchanged.
//  - initialized summaries and robust comparison selection
//  - correct Greedy/Cluster/Savings baseline attribution
//  - full-pipeline runtime and aggregate SA statistics
//  - active-truck fleet statistics; depot-only routes hidden
//  - thread-safe coarse profiling; noisy diagnostics disabled by default
//  - HGS-lite disabled by default, retained only for compatibility
// VRP solver — v8 patched: record/per-route max single-trip load and print it.
// Seed behavior fixed: --seed sets base seed; add --deterministic to force same seed for all SA instances.
// Extra fixes in this version:
//  - same-route swap / relocate handled correctly
//  - cross-exchange skips same-route cases
//  - route rec omputation is more consistent
//  - quieter recompute loop (no repeated stderr spam)
//  - output formatting rstored after percentage prints
//
// Build:
//   g++ -std=c++17 -O2 -pthread router_full_improved_final_fixed_v8_with_maxtrip_seedfix.cpp -o router_fixed

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
    bool require_coords_for_euclidean = true;

    // Euclidean benchmark / branch-cut controls.
    // These are ignored in road/direct mode.
    bool euclidean_round_distance = true;          // CVRPLIB-style rounded EUC_2D
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
    // Public hybrid contract: distance_m + 0.25 * route_duration_s.
    // Time-only mode always uses unscaled route duration.
    double w_time = 0.25;
    double w_co2 = 0.001;
    double w_late = 10.0;
    double w_capacity = 1000.0;
    double w_trip_excess = 10000.0;
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
    double no_improve_stop_s = 0.0;
    double target_no_improve_stop_s = 0.0;
    // When enabled, hard_time_limit_s is treated as an actual search budget:
    // after the normal finite pipeline completes, launch deterministic multistart
    // SA slices until only a small finalization reserve remains.
    bool fill_time_budget = false;
    double target_objective = 0.0;
    double meaningful_gain_abs = 500.0;
    double meaningful_gain_rel = 0.0015;

    /* ============================================================
    SA core
    ============================================================ */
    bool use_sa = true;
    double sa_T0 = 1000.0;
    // Historical cooling factor, now normalized over 10,000 reference steps.
    // Applying it once per CPU iteration made the temperature depend on machine
    // speed and underflow almost immediately on fast Colab runtimes.
    double sa_alpha = 0.9996;
    bool auto_T0 = true;

    // Portfolio warm start.  Early LNS and earlier SA phases must hand their
    // incumbent to later workers instead of making every worker rediscover it
    // from the same greedy construction.  A minority of cold workers retains
    // diversification.
    bool use_incumbent_sa_warm_start = true;
    double sa_incumbent_portfolio_fraction = 0.75;

    bool use_cross2 = true;

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
    bool savings_verbose = false;

    // Fixed-budget throughput prefix. This is deliberately a separate policy
    // from the later deep FragmentLNS/SA pipeline: cheap approximate-ranked
    // repairs, no post-repair education, strict feasibility, and one monotone
    // best incumbent. Native default is off; FleetRoute's customer tiers decide
    // when the measured hybrid schedule is appropriate.
    bool use_early_throughput_lns = false;
    double early_lns_fraction = 0.176;
    double early_lns_min_time_s = 0.75;
    double early_lns_max_time_s = 45.0;
    // 0 = automatic: 4% of the global budget, clamped to [2, 8] seconds.
    double early_lns_no_improve_s = 0.0;
    double early_lns_destroy_min_ratio = 0.04;
    double early_lns_destroy_max_ratio = 0.16;
    // Parallel prefix search is evidence-backed for the heavy road tier but
    // can reduce per-worker depth on medium instances. Keep the threshold
    // explicit and user-overridable instead of treating one benchmark as a
    // universal law.
    int early_lns_parallel_min_customers = 400;
    bool early_lns_verbose = true;

    bool use_alns = true;
    bool use_elite_pool = true;
    bool use_path_relink = true;

    bool use_local_polish = true;
    bool use_final_polish = true;

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

    /* ============================================================
    Candidate lists / insertion limits
    ============================================================ */
    bool use_candidate_lists = true;
    int candidate_k = 32;
    int candidate_route_probe_k = 4;

    bool use_regret_repair = true;
    int regret_k = 4;

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
    int interroute_polish_rounds = 4;
    int interroute_scan_cap = 30000;
    int max_interroute_moves = 60;

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
    int stagnation_alns_trigger = 800;

    /* ============================================================
    Elite pool / path relinking
    ============================================================ */
    // Elite intensification is deliberately sparse.  At the old 5,000-step
    // cadence it consumed nearly half the worker budget with repeated polishing.
    int relink_period = 250000;
    int elite_update_period = 5000;

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
} profile;

static double profile_seconds(const atomic<long long> &microseconds) {
    return static_cast<double>(microseconds.load(memory_order_relaxed)) /
        1'000'000.0;
}

// SA accepts hundreds of thousands of moves per worker. A shared atomic
// profiling increment on every dirty-route refresh made all workers contend on
// one cache line. Batch this diagnostic counter per worker thread; optimization
// state and correctness are unchanged.
static thread_local bool batch_recompute_profile = false;
static thread_local long long batched_recompute_calls = 0;

static inline void record_recompute_profile_call() {
    if (batch_recompute_profile) {
        batched_recompute_calls++;
    } else {
        profile.recompute_calls.fetch_add(1, memory_order_relaxed);
    }
}

static inline void begin_recompute_profile_batch() {
    batch_recompute_profile = true;
    batched_recompute_calls = 0;
}

static inline void flush_recompute_profile_batch() {
    if (batched_recompute_calls > 0) {
        profile.recompute_calls.fetch_add(
            batched_recompute_calls,
            memory_order_relaxed
        );
    }
    batched_recompute_calls = 0;
    batch_recompute_profile = false;
}

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
        // input.txt is a static directed-road snapshot.  A hidden synthetic
        // peak multiplier made native feasibility disagree with the Python
        // certificate and with the serialized edge travel time.  Live/forecast
        // traffic must be materialized explicitly into edge speeds instead.
        double speed_ms = max(0.1, speed_kph * 1000.0 / 3600.0);
        return length_m / speed_ms;
    }
    double co2() const { return length_m * cfg.co2_per_meter; }
};

static inline double routing_arc_score(double distance_m, double travel_time_s) {
    if (cfg.objective_mode == "time") return travel_time_s;
    if (cfg.objective_mode == "hybrid") return distance_m + cfg.w_time * travel_time_s;
    return distance_m;
}

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
        vector<double> best_score(E, INF);
        vector<double> best_arr(E, INF);
        vector<double> best_dist(E, INF);
        vector<int> prev(E, -1);
        using P = tuple<double, double, double, int>;
        priority_queue<P, vector<P>, greater<P>> pq;

        for (int e : starts) {
            if (e < 0 || e >= E) continue;
            double t = G->edges[e].travel_time(start_time);
            double arr = start_time + t;
            double dist = G->edges[e].length_m;
            double score = routing_arc_score(dist, t);
            if (score + 1e-9 < best_score[e] ||
                (fabs(score - best_score[e]) <= 1e-9 &&
                 make_pair(arr, dist) < make_pair(best_arr[e], best_dist[e]))) {
                best_score[e] = score;
                best_arr[e] = arr;
                best_dist[e] = dist;
                prev[e] = -1;
                pq.push({score, arr, dist, e});
            }
        }

        unordered_set<int> target_set(targets.begin(), targets.end());
        int found = -1;
        while (!pq.empty()) {
            auto [score, arr, dist, e] = pq.top();
            pq.pop();
            if (score > best_score[e] + 1e-9) continue;
            if (fabs(score - best_score[e]) <= 1e-9 &&
                make_pair(arr, dist) > make_pair(best_arr[e], best_dist[e])) continue;
            if (target_set.count(e)) {
                found = e;
                break;
            }
            for (auto &pr : LG->adj[e]) {
                int e2 = pr.first;
                double pen = pr.second;
                double t2 = G->edges[e2].travel_time(arr);
                double arr2 = arr + pen + t2;
                double dist2 = dist + G->edges[e2].length_m;
                double score2 = score + routing_arc_score(G->edges[e2].length_m, pen + t2);
                if (score2 + 1e-9 < best_score[e2] ||
                    (fabs(score2 - best_score[e2]) <= 1e-9 &&
                     make_pair(arr2, dist2) < make_pair(best_arr[e2], best_dist[e2]))) {
                    best_score[e2] = score2;
                    best_arr[e2] = arr2;
                    best_dist[e2] = dist2;
                    prev[e2] = e;
                    pq.push({score2, arr2, dist2, e2});
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
        double cost = best_arr[found] - start_time;
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

    PairwiseManager(
        Compressed *g,
        LineGraph *lg,
        size_t cap = 200000
    ) : G(g), LG(lg), path_cache(cap) {}

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

    // One-source line-graph Dijkstra.
    // This fills scalar time/dist only. No path vectors.
    void precompute_from_source(int src, const vector<int> &targets) {
        int src_c = canonical_node(src);

        if (src_c < 0 || src_c >= (int)G->out_edges.size()) {
            return;
        }

        const int E = (int)G->edges.size();
        const int N = (int)G->nodes.size();

        vector<vector<int>> incoming(N);

        for (int eid = 0; eid < E; ++eid) {
            int v = G->edges[eid].v;
            if (v >= 0 && v < N) {
                incoming[v].push_back(eid);
            }
        }

        vector<double> best_score(E, INF_D);
        vector<double> best_arr(E, INF_D);
        vector<double> best_dist(E, INF_D);

        using Q = tuple<double, double, double, int>;
        priority_queue<Q, vector<Q>, greater<Q>> pq;

        for (int eid : G->out_edges[src_c]) {
            if (eid < 0 || eid >= E) continue;

            const EdgeC &e = G->edges[eid];

            double arr =
                cfg.route_start_time_s +
                e.travel_time(cfg.route_start_time_s);

            double dist = e.length_m;
            double score = routing_arc_score(dist, arr - cfg.route_start_time_s);

            if (score + 1e-9 < best_score[eid] ||
                (fabs(score - best_score[eid]) <= 1e-9 &&
                 make_pair(arr, dist) < make_pair(best_arr[eid], best_dist[eid]))) {
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
                make_pair(arr, dist) > make_pair(best_arr[eid], best_dist[eid])) continue;

            for (auto &pr : LG->adj[eid]) {
                int e2 = pr.first;
                double pen = pr.second;

                if (e2 < 0 || e2 >= E) continue;

                const EdgeC &edge2 = G->edges[e2];

                double arr2 = arr + pen + edge2.travel_time(arr);
                double dist2 = dist + edge2.length_m;
                double score2 = score + routing_arc_score(
                    edge2.length_m,
                    pen + edge2.travel_time(arr)
                );

                if (score2 + 1e-9 < best_score[e2] ||
                    (fabs(score2 - best_score[e2]) <= 1e-9 &&
                     make_pair(arr2, dist2) < make_pair(best_arr[e2], best_dist[e2]))) {
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

            if (t_c < 0 || t_c >= N) {
                continue;
            }

            double best_c = INF_D;
            double best_t = INF_D;
            double best_d = INF_D;

            for (int eid : incoming[t_c]) {
                double score = best_score[eid];
                double arr = best_arr[eid];
                double dist = best_dist[eid];

                if (score + 1e-9 < best_c ||
                    (fabs(score - best_c) <= 1e-9 &&
                     make_pair(arr, dist) < make_pair(best_t, best_d))) {
                    best_c = score;
                    best_t = arr;
                    best_d = dist;
                }
            }

            if (best_t >= INF_D / 2 || best_d >= INF_D / 2) {
                continue;
            }

            store_metric(src, t, best_t - cfg.route_start_time_s, best_d);
        }
    }

    PairMetric get_pair_metric(int a, int b) {
        int a_c = canonical_node(a);
        int b_c = canonical_node(b);

        if (a_c == b_c) {
            return {0.0, 0.0};
        }

        PairMetric cached;
        if (get_metric_cached(a, b, cached)) {
            return cached;
        }

        TDijkstra td(G, LG);
        auto res = td.shortest_from_node_to_node(
            a_c,
            b_c,
            cfg.route_start_time_s
        );

        double time_s = res.first;
        double dist_m = res.second.empty() ? INF_D : 0.0;

        for (int eid : res.second) {
            dist_m += G->edges[eid].length_m;
        }

        store_metric(a, b, time_s, dist_m);
        return {time_s, dist_m};
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

        TDijkstra td(G, LG);
        auto res = td.shortest_from_node_to_node(
            a_c,
            b_c,
            cfg.route_start_time_s
        );

        double time_s = res.first;
        double dist_m = res.second.empty() ? INF_D : 0.0;

        auto path_ptr = make_shared<vector<int>>();

        for (int eid : res.second) {
            path_ptr->push_back(G->edges[eid].u);
            dist_m += G->edges[eid].length_m;
        }

        if (!res.second.empty()) {
            path_ptr->push_back(G->edges[res.second.back()].v);
        }

        path_cache.put(k, {time_s, path_ptr});
        store_metric(a, b, time_s, dist_m);

        return {time_s, *path_ptr};
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

    // CVRPLIB EUC_2D usually uses nearest integer distance.
    // This makes your objective comparable to PyVRP/CVRPLIB rounded runs.
    if (metric_is_euclidean() && cfg.euclidean_round_distance) {
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

    if (metric_is_road()) {
        for (int i = 0; i < C; ++i) {
            int a = dense_pairs.compact_to_node[i];
            pm.precompute_from_source(a, dense_pairs.compact_to_node);
        }
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

    return pm->get_pair(a, b).first;
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
    static bool initialized = false;
    static bool ok = false;

    if (!initialized) {
        __builtin_cpu_init();
        ok = __builtin_cpu_supports("avx2");
        initialized = true;
    }

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
static std::atomic<long long> solver_last_live_telemetry_ms{-1000000};
static string solver_stop_reason = "";

static double solver_elapsed_seconds() {
    if (!solver_governor_started) return 0.0;
    return chrono::duration<double>(Clock::now() - solver_start_time).count();
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
    solver_last_live_telemetry_ms.store(-1000000, memory_order_relaxed);
    solver_stop_reason.clear();
}

// Low-overhead live diagnostics for FleetRoute. stdout is deliberately reserved
// for the final machine-readable solution, so progress belongs on cerr/stderr.
// Multiple SA workers may call this; one atomic timestamp limits the entire
// process to roughly one line per second.
static void solver_live_telemetry(const char *phase, double local_best = INF_D, long long iterations = -1) {
    if (!solver_governor_started) return;
    const double elapsed = solver_elapsed_seconds();
    const long long now_ms = (long long)llround(elapsed * 1000.0);
    long long prev = solver_last_live_telemetry_ms.load(memory_order_relaxed);
    if (now_ms - prev < 1000) return;
    if (!solver_last_live_telemetry_ms.compare_exchange_strong(prev, now_ms, memory_order_relaxed)) return;

    double global_snapshot = INF_D;
    {
        lock_guard<mutex> lk(solver_governor_mutex);
        global_snapshot = solver_last_meaningful_objective;
    }
    const double remaining = cfg.hard_time_limit_s > 0.0
        ? max(0.0, cfg.hard_time_limit_s - elapsed)
        : -1.0;
    safe_log_line(
        "[SolverLive] phase=", phase,
        " elapsed_s=", elapsed,
        " remaining_s=", remaining,
        " local_best=", (isfinite(local_best) && local_best < INF_D / 2 ? local_best : -1.0),
        " global_best=", (isfinite(global_snapshot) && global_snapshot < INF_D / 2 ? global_snapshot : -1.0),
        " iterations=", iterations
    );
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

        if (!isfinite(solver_last_meaningful_objective) ||
            solver_last_meaningful_objective >= INF_D / 2) {
            solver_last_meaningful_objective = obj;
            solver_last_meaningful_improve_time = Clock::now();
            return;
        }

        need = meaningful_gain_threshold(solver_last_meaningful_objective);
        if (obj + need < solver_last_meaningful_objective) {
            old = solver_last_meaningful_objective;
            solver_last_meaningful_objective = obj;
            solver_last_meaningful_improve_time = Clock::now();
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

    if (!solver_governor_started) return false;

    double elapsed = solver_elapsed_seconds();

    if (cfg.hard_time_limit_s > 0.0 && elapsed >= cfg.hard_time_limit_s) {
        solver_request_stop("hard time limit reached");
        return true;
    }

    double patience = cfg.no_improve_stop_s;
    double best_snapshot = INF_D;
    Clock::time_point last_improve_snapshot;
    {
        // Every worker calls this function. Snapshot the governor state under
        // its owning mutex so concurrent best updates cannot create a C++ data
        // race or an inconsistent objective/timestamp pair.
        lock_guard<mutex> lk(solver_governor_mutex);
        best_snapshot = solver_last_meaningful_objective;
        last_improve_snapshot = solver_last_meaningful_improve_time;
    }
    const bool has_recorded_best =
        isfinite(best_snapshot) && best_snapshot < INF_D / 2;

    if (cfg.target_objective > 0.0 &&
        has_recorded_best &&
        best_snapshot <= cfg.target_objective &&
        cfg.target_no_improve_stop_s > 0.0) {
        patience = cfg.target_no_improve_stop_s;
    }

    if (patience > 0.0 && has_recorded_best) {
        const double no_gain_time = chrono::duration<double>(
            Clock::now() - last_improve_snapshot
        ).count();

        if (no_gain_time >= patience) {
            solver_request_stop("no meaningful improvement timeout");
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

static void update_global_best(const SolutionState &s) {
    std::lock_guard<std::mutex> lock(global_best_mutex);
    if (!state_basic_feasible_for_global_best(s)) return;
    if (global_best_state.routes.empty() ||
        s.objective + 1e-9 < global_best_state.objective) {
        global_best_state = s;
        solver_note_global_best(s.objective);
    }
}

static bool snapshot_global_best(SolutionState &out) {
    std::lock_guard<std::mutex> lock(global_best_mutex);
    if (!state_basic_feasible_for_global_best(global_best_state)) return false;
    out = global_best_state;
    return true;
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

        if (cfg.objective_mode == "distance") {
            m.weighted_cost =
                m.distance_m +
                tw_penalty_cost +
                overload_penalty +
                m.trip_excess_penalty;
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
        if (r1 == r2) return INF_D;
        if (i1 <= 0 || i2 <= 0) return INF_D;
        if (i1 + 2 >= (int)state.routes[r1].size() || i2 + 2 >= (int)state.routes[r2].size()) return INF_D;

        int a_prev = state.routes[r1][i1 - 1];
        int a1 = state.routes[r1][i1];
        int a2 = state.routes[r1][i1 + 1];
        int a_next = state.routes[r1][i1 + 2];

        int b_prev = state.routes[r2][i2 - 1];
        int b1 = state.routes[r2][i2];
        int b2 = state.routes[r2][i2 + 1];
        int b_next = state.routes[r2][i2 + 2];

        double ap_a1 = fast_pair_search_cost(a_prev, a1, pm);
        double a1_a2 = fast_pair_search_cost(a1, a2, pm);
        double a2_an = fast_pair_search_cost(a2, a_next, pm);

        double bp_b1 = fast_pair_search_cost(b_prev, b1, pm);
        double b1_b2 = fast_pair_search_cost(b1, b2, pm);
        double b2_bn = fast_pair_search_cost(b2, b_next, pm);

        double ap_b1 = fast_pair_search_cost(a_prev, b1, pm);
        double b1_b2_new = fast_pair_search_cost(b1, b2, pm);
        double b2_an = fast_pair_search_cost(b2, a_next, pm);

        double bp_a1 = fast_pair_search_cost(b_prev, a1, pm);
        double a1_a2_new = fast_pair_search_cost(a1, a2, pm);
        double a2_bn = fast_pair_search_cost(a2, b_next, pm);

        double cur_local = ap_a1 + a1_a2 + a2_an + bp_b1 + b1_b2 + b2_bn;
        double new_local = ap_b1 + b1_b2_new + b2_an + bp_a1 + a1_a2_new + a2_bn;

        return new_local - cur_local;
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
    record_recompute_profile_call();
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

    record_recompute_profile_call();
}

static bool dirty_recompute_matches_full(
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

static void update_global_best_checked(
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

static bool adapt_time_warp_penalty_after_phase(
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
    int depot = find_depot_idx(CG);
    int n = (int)tour.size();
    int K = cfg.num_trucks;

    const double INF = INF_D;

    SolutionState empty(cfg.num_trucks, (int)CG.nodes.size());
    empty.routes.assign(cfg.num_trucks, vector<int>{depot, depot});

    if (n == 0) {
        recompute_state_metrics_and_loads(empty, ev);
        return empty;
    }

    // ------------------------------------------------------------
    // Precompute feasible segment route costs.
    // seg_cost[i][j] = cost of route depot, tour[i..j-1], depot.
    // j is exclusive.
    // ------------------------------------------------------------
    vector<vector<double>> seg_cost(n + 1, vector<double>(n + 1, INF));

    for (int i = 0; i < n; ++i) {
        double load = 0.0;
        vector<int> route;
        route.reserve(n - i + 2);
        route.push_back(depot);

        for (int j = i; j < n; ++j) {
            int node = tour[j];

            if (node < 0 || node >= (int)CG.nodes.size()) {
                break;
            }

            if (CG.nodes[node].type != 2) {
                break;
            }

            load += CG.nodes[node].garbage_amount;

            if (load > cfg.truck_capacity + 1e-9) {
                break;
            }

            route.push_back(node);

            vector<int> closed = route;
            closed.push_back(depot);

            // Exact route cost through current evaluator.
            if (cfg.use_time_window &&
                cfg.tw_strict_insertion &&
                !cfg.tw_allow_soft_intermediate &&
                !route_hard_tw_feasible(closed, ev, pm)) {
                continue;
            }
            seg_cost[i][j + 1] = route_exact_cost(closed, ev);
        }
    }

    // ------------------------------------------------------------
    // Fleet-constrained split:
    // dp[k][i] = best cost to serve first i customers using exactly k routes.
    // Empty routes are allowed after reconstruction if k < K.
    // ------------------------------------------------------------
    vector<vector<double>> dp(K + 1, vector<double>(n + 1, INF));
    vector<vector<int>> parent(K + 1, vector<int>(n + 1, -1));

    dp[0][0] = 0.0;

    for (int k = 1; k <= K; ++k) {
        for (int j = 1; j <= n; ++j) {
            double best = INF;
            int best_i = -1;

            for (int i = 0; i < j; ++i) {
                if (dp[k - 1][i] >= INF / 2) continue;
                if (seg_cost[i][j] >= INF / 2) continue;

                double cand = dp[k - 1][i] + seg_cost[i][j];

                if (cand + 1e-9 < best) {
                    best = cand;
                    best_i = i;
                }
            }

            dp[k][j] = best;
            parent[k][j] = best_i;
        }
    }

    // Use at most K routes: choose best k <= K.
    int best_k = -1;
    double best_obj = INF;

    for (int k = 1; k <= K; ++k) {
        if (dp[k][n] + 1e-9 < best_obj) {
            best_obj = dp[k][n];
            best_k = k;
        }
    }

    if (best_k < 0 || best_obj >= INF / 2) {
        // Fallback: return empty infeasible-ish structure; caller will reject.
        recompute_state_metrics_and_loads(empty, ev);
        return empty;
    }

    // ------------------------------------------------------------
    // Recover routes.
    // ------------------------------------------------------------
    vector<vector<int>> recovered;
    int cur = n;
    int k = best_k;

    while (k > 0 && cur > 0) {
        int p = parent[k][cur];

        if (p < 0) {
            break;
        }

        vector<int> r;
        r.reserve(cur - p + 2);
        r.push_back(depot);

        for (int i = p; i < cur; ++i) {
            r.push_back(tour[i]);
        }

        r.push_back(depot);
        recovered.push_back(r);

        cur = p;
        k--;
    }

    reverse(recovered.begin(), recovered.end());

    SolutionState s(cfg.num_trucks, (int)CG.nodes.size());
    s.routes.assign(cfg.num_trucks, vector<int>{depot, depot});

    for (int r = 0; r < (int)recovered.size() && r < cfg.num_trucks; ++r) {
        s.routes[r] = recovered[r];
        enforce_trip_separators(s.routes[r], CG, depot);
    }

    recompute_state_metrics_and_loads(s, ev);
    return s;
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

    for (int sidx = 0; sidx < sweep_count; ++sidx) {
        double off = (2.0 * M_PI * sidx) / max(1, sweep_count);
        vector<int> t = euclidean_sweep_tour(CG, off);

        if (!t.empty()) {
            Individual ind = make_individual(t, sidx % 3 == 0);

            if (feasible_individual(ind)) {
                pop.push_back(std::move(ind));
            }
        }
    }

    while ((int)pop.size() < cfg.hgs_population_size) {
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
    for (int gen = 0; gen < cfg.hgs_generations; ++gen) {
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
    PairwiseManager &pm
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
    PairwiseManager &pm,
    const Compressed &CG,
    int depot
);

static int depot_of(const ObjectiveEvaluator &ev) {
    return find_depot_idx(*ev.CG);
}

static void update_global_best_checked(
    const SolutionState &s,
    const Compressed &CG,
    PairwiseManager &pm
) {
    if (s.routes.empty()) return;
    if (!solution_hard_feasible(s, CG, pm)) return;

    update_global_best(s);
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

            best = min(best, fast_pair_dist(node, x, &pm));
            checked++;

            if (checked >= cfg.candidate_route_probe_k) break;
        }

        // 2) Fallback: sample actual internal route nodes.
        // Do this even if depot distance exists, because depot endpoints are weak in multi-trip.
        if (!isfinite(best) || best >= INF_D / 2) {
            int internal_count = max(0, (int)route.size() - 2);
            int step = max(1, internal_count / max(1, cfg.candidate_route_probe_k));

            for (int i = 1; i + 1 < (int)route.size(); i += step) {
                if (route[i] == node) continue;
                best = min(best, fast_pair_dist(route[i], node, &pm));
            }
        }

        // 3) Empty route fallback: depot distance only.
        if (!isfinite(best) || best >= INF_D / 2) {
            if (!route.empty()) {
                best = min(best, fast_pair_dist(route.front(), node, &pm));
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
    PairwiseManager &pm
) {
    if (!cfg.use_topk_insertion || !cfg.use_simd_insertion_rank) {
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

        double old_cost = route_exact_cost(route, ev);
        if (!isfinite(old_cost) || old_cost >= INF_D / 2) {
            continue;
        }

        int max_try = min((int)route.size(), cfg.insertion_pos_cap);

        for (int pos = 1; pos < max_try; ++pos) {
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
    PairwiseManager &pm
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
            pm
        )) {
        return true;
    }

    for (int r : candidate_routes) {
        if (r < 0 || r >= (int)state.routes.size()) continue;

        const auto &route = state.routes[r];

        if ((int)route.size() < 2) continue;

        double old_cost = route_exact_cost(route, ev);

        int max_try = min((int)route.size(), cfg.insertion_pos_cap);

        vector<int> positions;
        positions.reserve(max_try);

        if (cfg.use_topk_insertion) {
            vector<pair<double, int>> ranked_pos;
            ranked_pos.reserve(max_try);

            for (int pos = 1; pos < max_try; ++pos) {
                int prev = route[pos - 1];
                int next = route[pos];

                double old_edge = fast_pair_dist(prev, next, &pm);
                double new_edges =
                    fast_pair_dist(prev, node, &pm) +
                    fast_pair_dist(node, next, &pm);

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
            for (int pos = 1; pos < max_try; ++pos) {
                positions.push_back(pos);
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
    if (cfg.boundary_pair_lns_rounds <= 0) return;

    double start_obj = state.objective;
    int accepted = 0;

    for (int round = 0; round < cfg.boundary_pair_lns_rounds; ++round) {
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

    SolutionState cand;
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

static bool granular_candidate_feasible(
    const SolutionState &cand,
    const Compressed &CG
) {
    if (!solution_serves_all_customers_once(cand, CG)) return false;
    if (!solution_capacity_feasible(cand, CG)) return false;
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
    GranularTabuMove &out
) {
    if (r_from == r_to) return false;

    const Compressed &CG = *ev.CG;
    int depot = find_depot_idx(CG);

    if (r_from < 0 || r_to < 0) return false;
    if (r_from >= (int)state.routes.size()) return false;
    if (r_to >= (int)state.routes.size()) return false;

    const vector<int> &A = state.routes[r_from];
    const vector<int> &B = state.routes[r_to];

    if (pos_from <= 0 || pos_from + 1 >= (int)A.size()) return false;
    if (insert_pos <= 0 || insert_pos >= (int)B.size()) return false;

    int node = A[pos_from];

    if (node < 0 || node >= (int)CG.nodes.size()) return false;
    if (CG.nodes[node].type != 2) return false;

    SolutionState cand = state;

    cand.routes[r_from].erase(cand.routes[r_from].begin() + pos_from);
    cand.routes[r_to].insert(cand.routes[r_to].begin() + insert_pos, node);

    normalize_route(cand.routes[r_from], depot);
    normalize_route(cand.routes[r_to], depot);

    if (!granular_route_basic_ok(cand.routes[r_from], CG, depot)) return false;
    if (!granular_route_basic_ok(cand.routes[r_to], CG, depot)) return false;

    recompute_dirty_routes(cand, ev, {r_from, r_to});

    if (!granular_candidate_feasible(cand, CG)) return false;

    out.type = GranularTabuMove::RELOCATE;
    out.r1 = r_from;
    out.p1 = pos_from;
    out.r2 = r_to;
    out.p2 = insert_pos;
    out.a = node;
    out.b = -1;
    out.new_obj = cand.objective;
    out.delta = cand.objective - state.objective;
    out.cand = std::move(cand);

    return true;
}

static bool try_build_granular_swap(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    int r1,
    int p1,
    int r2,
    int p2,
    GranularTabuMove &out
) {
    if (r1 == r2) return false;

    const Compressed &CG = *ev.CG;
    int depot = find_depot_idx(CG);

    if (r1 < 0 || r2 < 0) return false;
    if (r1 >= (int)state.routes.size()) return false;
    if (r2 >= (int)state.routes.size()) return false;

    const vector<int> &A = state.routes[r1];
    const vector<int> &B = state.routes[r2];

    if (p1 <= 0 || p1 + 1 >= (int)A.size()) return false;
    if (p2 <= 0 || p2 + 1 >= (int)B.size()) return false;

    int a = A[p1];
    int b = B[p2];

    if (a < 0 || a >= (int)CG.nodes.size()) return false;
    if (b < 0 || b >= (int)CG.nodes.size()) return false;
    if (CG.nodes[a].type != 2) return false;
    if (CG.nodes[b].type != 2) return false;

    SolutionState cand = state;

    cand.routes[r1][p1] = b;
    cand.routes[r2][p2] = a;

    normalize_route(cand.routes[r1], depot);
    normalize_route(cand.routes[r2], depot);

    if (!granular_route_basic_ok(cand.routes[r1], CG, depot)) return false;
    if (!granular_route_basic_ok(cand.routes[r2], CG, depot)) return false;

    recompute_dirty_routes(cand, ev, {r1, r2});

    if (!granular_candidate_feasible(cand, CG)) return false;

    out.type = GranularTabuMove::SWAP;
    out.r1 = r1;
    out.p1 = p1;
    out.r2 = r2;
    out.p2 = p2;
    out.a = a;
    out.b = b;
    out.new_obj = cand.objective;
    out.delta = cand.objective - state.objective;
    out.cand = std::move(cand);

    return true;
}

static bool granular_tabu_repair(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    if (!cfg.use_granular_tabu) return false;
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

        for (const auto &sig : signals) {
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
                    GranularTabuMove mv;

                    if (try_build_granular_relocate(
                            state,
                            ev,
                            ra,
                            pa,
                            rb,
                            ins,
                            mv
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
                    GranularTabuMove mv;

                    if (try_build_granular_relocate(
                            state,
                            ev,
                            rb,
                            pb,
                            ra,
                            ins,
                            mv
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
                            mv
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

        state = std::move(best_move.cand);
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

static void two_opt_trip_segment(
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

                // Reverse only when the exact edge delta improves. Geometric
                // crossing detection is handled by the dedicated Euclidean
                // uncross pass; it must never force a non-improving move here.
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

static void two_opt_multi_trip_route(vector<int> &route, PairwiseManager &pm, const Compressed &CG, int depot) {
    normalize_route(route, depot);
    enforce_trip_separators(route, CG, depot);
    vector<int> dep;
    for (int i = 0; i < (int)route.size(); ++i) if (route[i] == depot) dep.push_back(i);
    if (dep.size() < 2) return;
    // Only perform two-opt if enabled; limit to first improvement on each trip segment
    if (!cfg.use_2opt) return;
    for (int i = 0; i + 1 < (int)dep.size(); ++i) {
        if (solver_should_stop()) return;
        int L = dep[i], R = dep[i + 1];
        if (R - L < 2) continue;
        bool improved = true;
        int moves = 0;
        while (improved && moves < cfg.insertion_pos_cap) {
            if (solver_should_stop()) return;
            improved = false;
            for (int a = L + 1; a < R - 1 && moves < cfg.insertion_pos_cap; ++a) {
                for (int b = a + 1; b < R && moves < cfg.insertion_pos_cap; ++b) {
                    // check local cost delta
                    int u1 = route[a - 1], v1 = route[a];
                    int u2 = route[b], v2 = route[b + 1];
                    double before = fast_pair_time(u1, v1, &pm) + fast_pair_time(u2, v2, &pm);
                    double after  = fast_pair_time(u1, u2, &pm) + fast_pair_time(v1, v2, &pm);
                    if (after + 1e-9 < before) {
                        vector<int> cand = route;
                        reverse(cand.begin() + a, cand.begin() + b + 1);

                        double old_cost = 0.0;
                        double new_cost = 0.0;

                        for (int p = L; p < R; ++p) {
                            old_cost += fast_pair_time(route[p], route[p + 1], &pm);
                            new_cost += fast_pair_time(cand[p], cand[p + 1], &pm);
                        }

                        if (new_cost + 1e-9 < old_cost) {
                            route.swap(cand);
                            improved = true;
                            moves++;
                            break;
                        }
                    }
                }
                if (improved) break;
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
        if (solver_should_stop()) return;
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
        if (solver_should_stop()) return;
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

static vector<int> customers_in_route_set(
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

static bool remove_customer_set_from_state(
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
        if (solver_should_stop()) break;
        normalize_route(r, depot);
        enforce_trip_separators(r, *ev.CG, depot);
        relocate_route_local_best(r, ev, pm, *ev.CG, depot);
        if (solver_should_stop()) break;
        or_opt_k_route(r, 2, ev, pm, *ev.CG, depot);
        if (solver_should_stop()) break;
        or_opt_k_route(r, 3, ev, pm, *ev.CG, depot);
        if (solver_should_stop()) break;
        two_opt_multi_trip_route(r, pm, *ev.CG, depot);
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
    PairwiseManager &pm
) {
    vector<InsertionOption> opts;
    int depot = depot_of(ev);

    vector<int> route_ids = get_best_routes_for_node(
        state.routes, pm, node, max(1, cfg.insertion_route_cap)
    );

    for (int r : route_ids) {
        if (r < 0 || r >= (int)state.routes.size()) continue;
        const auto &route = state.routes[r];
        if (route.size() < 2) continue;
        double old_cost = route_exact_cost(route, ev);
        if (!isfinite(old_cost)) continue;

        int max_pos = min((int)route.size() - 1, max(1, cfg.insertion_pos_cap));
        for (int pos = 1; pos <= max_pos; ++pos) {
            vector<int> cand = route;
            cand.insert(cand.begin() + pos, node);
            normalize_route(cand, depot);
            enforce_trip_separators(cand, *ev.CG, depot);
            if (!trips_feasible_for_route(cand, *ev.CG, depot)) continue;

            bool hard_filter_insert =
                cfg.use_time_window &&
                cfg.tw_strict_insertion &&
                !cfg.tw_allow_soft_intermediate;

            if (hard_filter_insert) {
                if (!route_hard_tw_feasible(cand, ev, pm)) continue;
            }

            double new_cost = route_exact_cost(cand, ev);
            if (!isfinite(new_cost)) continue;

            double delta = new_cost - old_cost;
            opts.push_back({r, pos, delta});
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

static void regret_repair_remaining_nodes(
    SolutionState &cur,
    vector<int> &remaining,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    vector<int> unplaced = remaining;
    remaining.clear();

    while (!unplaced.empty()) {
        if (solver_should_stop()) break;
        int pick_idx = -1;
        InsertionOption pick_choice;
        double best_regret = -INF_D;
        double best_best_cost = INF_D;

        for (int i = 0; i < (int)unplaced.size(); ++i) {
            if ((i & 7) == 0 && solver_should_stop()) break;
            int node = unplaced[i];
            auto opts = collect_insertion_options(cur, node, ev, pm);
            if (opts.empty()) continue;

            int kk = min((int)opts.size(), max(2, cfg.regret_k));
            double regret = 0.0;
            if ((int)opts.size() == 1) {
                regret = 1e12;
            } else {
                regret = opts[kk - 1].cost - opts[0].cost;
            }

            if (regret > best_regret + 1e-9 ||
                (fabs(regret - best_regret) <= 1e-9 && opts[0].cost < best_best_cost)) {
                best_regret = regret;
                best_best_cost = opts[0].cost;
                pick_idx = i;
                pick_choice = opts[0];
            }
        }

        if (pick_idx == -1) break;

        int node = unplaced[pick_idx];
        if (!apply_insertion_option(cur, node, pick_choice, ev)) break;
        unplaced.erase(unplaced.begin() + pick_idx);
    }
    remaining = unplaced;
    recompute_state_metrics_and_loads(cur, ev);
    remaining = std::move(unplaced);
}

// Worst-String Related Ruin (WSRR)
//
// Random and Shaw-style ruin are good at diversification, but they often miss
// a structurally bad route seam.  WSRR ranks customers by their directed local
// removal saving, removes a compact string around one high-cost seam, then
// adds geographically related customers from other routes.  Greedy repair can
// therefore repartition the seam instead of merely restoring the same route.
// The operator is O(customers log customers), uses the dense pair cache, and
// never changes feasibility rules.
static void build_worst_string_related_ruin(
    const SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    mt19937 &rng,
    const vector<int> &all_customers,
    int remove_cnt,
    unordered_set<int> &removed
) {
    struct SeamCandidate {
        double saving = -INF_D;
        int route = -1;
        int pos = -1;
        int node = -1;
    };

    vector<SeamCandidate> seams;
    vector<int> route_of(ev.CG->nodes.size(), -1);
    seams.reserve(all_customers.size());

    for (int r = 0; r < (int)state.routes.size(); ++r) {
        const auto &route = state.routes[r];
        for (int pos = 1; pos + 1 < (int)route.size(); ++pos) {
            const int node = route[pos];
            if (node < 0 || node >= (int)ev.CG->nodes.size()) continue;
            if (ev.CG->nodes[node].type != 2) continue;
            route_of[node] = r;

            const int prev = route[pos - 1];
            const int next = route[pos + 1];
            const double before =
                fast_pair_dist(prev, node, &pm) +
                fast_pair_dist(node, next, &pm);
            const double after = fast_pair_dist(prev, next, &pm);
            if (!isfinite(before) || !isfinite(after)) continue;
            seams.push_back({before - after, r, pos, node});
        }
    }

    if (seams.empty()) {
        if (!all_customers.empty()) {
            removed.insert(all_customers[rng() % all_customers.size()]);
        }
        return;
    }

    const int elite_count = min(
        (int)seams.size(),
        max(4, min(20, (int)seams.size() / 5))
    );
    if ((int)seams.size() > elite_count) {
        nth_element(
            seams.begin(),
            seams.begin() + elite_count,
            seams.end(),
            [](const SeamCandidate &a, const SeamCandidate &b) {
                return a.saving > b.saving;
            }
        );
        seams.resize(elite_count);
    }
    sort(
        seams.begin(),
        seams.end(),
        [](const SeamCandidate &a, const SeamCandidate &b) {
            return a.saving > b.saving;
        }
    );

    // Bias toward the worst seam without making every attempt identical.
    const int rank_window = max(1, min(elite_count, 8));
    const int pick_rank = min(
        rank_window - 1,
        (int)floor(pow(uniform_real_distribution<double>(0.0, 1.0)(rng), 2.0)
            * rank_window)
    );
    const SeamCandidate seed = seams[pick_rank];
    const auto &seed_route = state.routes[seed.route];

    const int string_target = min(
        remove_cnt,
        max(2, (int)ceil((double)remove_cnt * 0.60))
    );
    for (int radius = 0;
         (int)removed.size() < string_target && radius < (int)seed_route.size();
         ++radius) {
        const int positions[2] = {seed.pos + radius, seed.pos - radius};
        for (int k = 0; k < 2 && (int)removed.size() < string_target; ++k) {
            const int pos = positions[k];
            if (pos <= 0 || pos + 1 >= (int)seed_route.size()) continue;
            const int node = seed_route[pos];
            if (node >= 0 && node < (int)ev.CG->nodes.size() &&
                ev.CG->nodes[node].type == 2) {
                removed.insert(node);
            }
        }
    }

    vector<int> related;
    related.reserve(all_customers.size());
    for (int node : all_customers) {
        if (!removed.count(node)) related.push_back(node);
    }
    sort(related.begin(), related.end(), [&](int a, int b) {
        const double ra = relatedness_score(seed.node, a, pm, *ev.CG);
        const double rb = relatedness_score(seed.node, b, pm, *ev.CG);
        if (ra != rb) return ra < rb;
        return a < b;
    });

    // Guarantee some cross-route material when available; this is what lets
    // greedy repair change ownership across the bad seam.
    const int cross_target = max(1, remove_cnt / 4);
    int cross_added = 0;
    for (int node : related) {
        if ((int)removed.size() >= remove_cnt || cross_added >= cross_target) break;
        if (node >= 0 && node < (int)route_of.size() &&
            route_of[node] >= 0 && route_of[node] != seed.route) {
            if (removed.insert(node).second) ++cross_added;
        }
    }
    for (int node : related) {
        if ((int)removed.size() >= remove_cnt) break;
        removed.insert(node);
    }
}

static SolutionState alns_destroy_repair(
    const SolutionState &base,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    mt19937 &rng,
    int destroy_mode,
    bool throughput_repair = false
) {
    SolutionState cur = base;
    int depot = depot_of(ev);
    vector<int> all_customers = collect_customers_from_state(cur, *ev.CG);
    if (all_customers.empty()) return cur;

    uniform_real_distribution<double> ur(0.0, 1.0);
    // Sample removal ratio from configurable bounds
    const double destroy_min_ratio = throughput_repair
        ? cfg.early_lns_destroy_min_ratio
        : cfg.alns_destroy_min_ratio;
    const double destroy_max_ratio = throughput_repair
        ? cfg.early_lns_destroy_max_ratio
        : cfg.alns_destroy_max_ratio;
    double remove_ratio = destroy_min_ratio
                        + (destroy_max_ratio - destroy_min_ratio) * ur(rng);
    int remove_cnt = max(2, (int)round(remove_ratio * (double)all_customers.size()));
    unordered_set<int> removed;

    if (destroy_mode == 0) {
        shuffle(all_customers.begin(), all_customers.end(), rng);
        for (int i = 0; i < remove_cnt && i < (int)all_customers.size(); ++i) removed.insert(all_customers[i]);
    } else if (destroy_mode == 1) {
        vector<pair<double,int>> route_scores;
        for (int r = 0; r < (int)cur.routes.size(); ++r) route_scores.push_back({route_exact_cost(cur.routes[r], ev), r});
        sort(route_scores.begin(), route_scores.end(), greater<>());
        // Cost-oriented destruction: the old code sorted the routes and then
        // sampled the entire array, accidentally making the sort meaningless.
        // Restrict the seed to the expensive leading third while retaining
        // stochastic diversity among those routes.
        int expensive_route_count = max(
            1,
            min(
                (int)route_scores.size(),
                (int)ceil((double)route_scores.size() / 3.0)
            )
        );
        int seed_route = route_scores[rng() % expensive_route_count].second;
        vector<int> seed_customers = collect_customers_from_route(cur.routes[seed_route], *ev.CG);
        if (seed_customers.empty()) return cur;
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
    } else {
        build_worst_string_related_ruin(
            cur,
            ev,
            pm,
            rng,
            all_customers,
            remove_cnt,
            removed
        );
    }

    for (auto &r : cur.routes) {
        r = remove_nodes_from_route(r, removed);
        normalize_route(r, depot);
        enforce_trip_separators(r, *ev.CG, depot);
    }

vector<int> rem_list(removed.begin(), removed.end());

    bool repair_ok = true;

    if (cfg.use_regret_repair && !throughput_repair) {
        // regret_repair_remaining_nodes should erase successfully inserted nodes
        // and leave failed nodes in rem_list.
        regret_repair_remaining_nodes(cur, rem_list, ev, pm);

        if (!rem_list.empty()) {
            repair_ok = false;
        }
    } else {
        sort(rem_list.begin(), rem_list.end(), [&](int a, int b) {
            return ev.CG->nodes[a].garbage_amount > ev.CG->nodes[b].garbage_amount;
        });

        vector<int> failed;

        for (int node : rem_list) {
            bool ok = insert_customer_best_place_fast(cur, node, ev, pm);

            if (!ok) {
                failed.push_back(node);
            }
        }

        rem_list.swap(failed);

        if (!rem_list.empty()) {
            repair_ok = false;
        }
    }

    if (!repair_ok) {
        return base;
    }

    // The early throughput regime intentionally omits post-repair polishing.
    // Its insertion engine still ranks cheaply and validates the final shortlist
    // exactly; deep local education remains available in the unchanged later
    // pipeline. Normal ALNS calls retain their historical light polish.
    if (!throughput_repair) {
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
                two_opt_multi_trip_route(r, pm, *ev.CG, depot);
            }
        }
    }

    recompute_state_metrics_and_loads(cur, ev);

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
    array<double,4> destroy_w = {1.0, 1.0, 1.0, 1.0};
    for (int t = 0; t < rounds; ++t) {
        if (solver_should_stop()) break;
        double sum = accumulate(destroy_w.begin(), destroy_w.end(), 0.0);
        uniform_real_distribution<double> ur(0.0, max(1e-9, sum));
        double x = ur(rng);
        int op = 0;
        double cumulative = destroy_w[0];
        while (op + 1 < (int)destroy_w.size() && x >= cumulative) {
            ++op;
            cumulative += destroy_w[op];
        }
        SolutionState cand = alns_destroy_repair(best, ev, pm, rng, op);
        recompute_state_metrics_and_loads(cand, ev);
        if (cand.objective + 1e-9 < best_obj) {
            best = std::move(cand);
            best_obj = best.objective;
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
        if (solver_should_stop()) break;
        for (auto &r : state.routes) {
            if (solver_should_stop()) break;
            normalize_route(r, depot);
            enforce_trip_separators(r, *ev.CG, depot);
            if (cfg.use_relocate_polish) relocate_route_local_best(r, ev, pm, *ev.CG, depot);
            if (solver_should_stop()) break;
            if (cfg.use_oropt) or_opt_k_route(r, 2, ev, pm, *ev.CG, depot);
            if (solver_should_stop()) break;
            if (cfg.use_2opt) two_opt_multi_trip_route(r, pm, *ev.CG, depot);
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

static bool inter_route_relocate_best_pass(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    (void)pm;

    int depot = depot_of(ev);
    int R = (int)state.routes.size();

    recompute_state_metrics_and_loads(state, ev);

    double best_delta = -1e-9;
    int best_from = -1, best_to = -1;
    vector<int> best_route_from, best_route_to;

    int scans = 0;

    for (int from = 0; from < R; ++from) {
        for (int to = 0; to < R; ++to) {
            if (from == to) continue;

            const auto &rf = state.routes[from];
            const auto &rt = state.routes[to];

            if ((int)rf.size() <= 2) continue;

            for (int pos_from = 1; pos_from + 1 < (int)rf.size(); ++pos_from) {
                int node = rf[pos_from];
                if (ev.CG->nodes[node].type != 2) continue;

                for (int pos_to = 1; pos_to < (int)rt.size(); ++pos_to) {
                    ++scans;
                    if ((scans & 255) == 0 && solver_should_stop()) {
                        goto finish_scan;
                    }
                    if (cfg.interroute_scan_cap > 0 && scans > cfg.interroute_scan_cap) {
                        goto finish_scan;
                    }

                    vector<int> cand_from = rf;
                    vector<int> cand_to = rt;

                    cand_from.erase(cand_from.begin() + pos_from);

                    int insert_pos = max(1, min(pos_to, (int)cand_to.size() - 1));
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

finish_scan:

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
    (void)pm;

    int depot = depot_of(ev);
    int R = (int)state.routes.size();

    recompute_state_metrics_and_loads(state, ev);

    double best_delta = -1e-9;
    int best_r1 = -1, best_r2 = -1;
    vector<int> best_route_1, best_route_2;

    int scans = 0;

    for (int r1 = 0; r1 < R; ++r1) {
        for (int r2 = r1 + 1; r2 < R; ++r2) {
            const auto &a = state.routes[r1];
            const auto &b = state.routes[r2];

            if ((int)a.size() <= 2 || (int)b.size() <= 2) continue;

            for (int i = 1; i + 1 < (int)a.size(); ++i) {
                if (ev.CG->nodes[a[i]].type != 2) continue;

                for (int j = 1; j + 1 < (int)b.size(); ++j) {
                    if (ev.CG->nodes[b[j]].type != 2) continue;

                    ++scans;
                    if ((scans & 255) == 0 && solver_should_stop()) {
                        goto finish_scan;
                    }
                    if (cfg.interroute_scan_cap > 0 && scans > cfg.interroute_scan_cap) {
                        goto finish_scan;
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
    }

finish_scan:

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
    (void)pm;

    int depot = depot_of(ev);
    int R = (int)state.routes.size();

    recompute_state_metrics_and_loads(state, ev);

    double best_delta = -1e-9;
    int best_r1 = -1, best_r2 = -1;
    vector<int> best_route_1, best_route_2;

    int scans = 0;

    for (int r1 = 0; r1 < R; ++r1) {
        for (int r2 = r1 + 1; r2 < R; ++r2) {
            const auto &a = state.routes[r1];
            const auto &b = state.routes[r2];

            if ((int)a.size() <= 3 || (int)b.size() <= 3) continue;

            for (int cut1 = 0; cut1 + 1 < (int)a.size(); ++cut1) {
                for (int cut2 = 0; cut2 + 1 < (int)b.size(); ++cut2) {
                    ++scans;
                    if ((scans & 255) == 0 && solver_should_stop()) {
                        goto finish_scan;
                    }
                    if (cfg.interroute_scan_cap > 0 && scans > cfg.interroute_scan_cap) {
                        goto finish_scan;
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
    }

finish_scan:

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
        if (solver_should_stop()) break;
        bool improved = false;

        if (moves < cfg.max_interroute_moves && !solver_should_stop()) {
            if (inter_route_relocate_best_pass(state, ev, pm)) {
                improved = true;
                moves++;
            }
        }

        if (moves < cfg.max_interroute_moves && !solver_should_stop()) {
            if (inter_route_swap_best_pass(state, ev, pm)) {
                improved = true;
                moves++;
            }
        }

        if (moves < cfg.max_interroute_moves && !solver_should_stop()) {
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

    if (!solver_should_stop()) {
        local_polish_solution(state, ev, pm);
    }
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

    if (cfg.use_longest_route_ruin) {
        uniform_real_distribution<double> prob_dist(0.0, 1.0);

        if (prob_dist(rng) < cfg.longest_route_ruin_probability) {
            pool = longest_route_ruin_pool(base, remove_target, ev, pm, rng);
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

static void final_refinement_pass(SolutionState &state, ObjectiveEvaluator &ev, PairwiseManager &pm) {
    recompute_state_metrics_and_loads(state, ev);

    SolutionState best = state;
    double best_obj = state.objective;

    int rounds = max(1, cfg.final_refinement_rounds);

    for (int round = 0; round < rounds; ++round) {
        if (solver_should_stop()) break;

        SolutionState cand = best;
        recompute_state_metrics_and_loads(cand, ev);

        if ((cfg.use_relocate_polish || cfg.use_oropt || cfg.use_2opt) &&
            !solver_should_stop()) {
            local_polish_solution(cand, ev, pm);
            recompute_state_metrics_and_loads(cand, ev);
        }

        if (cfg.use_alns && !solver_should_stop()) {
            unsigned alns_seed =
                cfg.base_seed ^
                0xA5A5A5A5u ^
                (unsigned)(round * 1000003u);

            adaptive_lns_polish(cand, ev, pm, cfg.alns_rounds, alns_seed);
            recompute_state_metrics_and_loads(cand, ev);
        }

        if (cfg.use_interroute_polish && !solver_should_stop()) {
            interroute_polish_solution(cand, ev, pm);
            recompute_state_metrics_and_loads(cand, ev);
        }

        // GLS-lite: penalize stuck arcs, explore penalized moves,
        // then keep only exact objective improvements.
        if (cfg.use_guided_arc_penalty && !solver_should_stop()) {
            guided_arc_penalty_search(cand, ev, pm);
            recompute_state_metrics_and_loads(cand, ev);
        }

        if (cfg.use_fragment_lns && !solver_should_stop()) {
            fragment_lns_search(cand, ev, pm);
            recompute_state_metrics_and_loads(cand, ev);
        }

        if (cfg.use_route_region_lns && !solver_should_stop()) {
            route_region_lns_descent(cand, ev, pm);
            recompute_state_metrics_and_loads(cand, ev);
        }

        if (cfg.use_final_polish && !solver_should_stop()) {
            final_route_cleanup(cand, ev, pm);
            recompute_state_metrics_and_loads(cand, ev);
        }

        if (cand.objective + 1e-9 < best_obj) {
            best = std::move(cand);
            best_obj = best.objective;
            update_global_best_checked(best, *ev.CG, pm);
        } else {
            // Reliable rollback: stop if the full chain cannot improve.
            break;
        }
    }

    state = std::move(best);
    recompute_state_metrics_and_loads(state, ev);
    update_global_best_checked(state, *ev.CG, pm);
}

static void elite_pool_update(vector<SolutionState> &pool, const SolutionState &cand, size_t maxK) {
    pool.push_back(cand);
    sort(pool.begin(), pool.end(), [](const SolutionState &a, const SolutionState &b){ return a.objective < b.objective; });
    if (pool.size() > maxK) pool.resize(maxK);
}

static SolutionState path_relink_between(const SolutionState &a, const SolutionState &b, ObjectiveEvaluator &ev, PairwiseManager &pm) {
    SolutionState cur = a;
    int depot = depot_of(ev);
    for (int r = 0; r < (int)cur.routes.size(); ++r) {
        if (cur.routes[r] != b.routes[r]) {
            cur.routes[r] = b.routes[r];
            normalize_route(cur.routes[r], depot);
            enforce_trip_separators(cur.routes[r], *ev.CG, depot);
        }
    }
    recompute_state_metrics_and_loads(cur, ev);
    for (auto &r : cur.routes) {
        relocate_route_local_best(r, ev, pm, *ev.CG, depot);
        or_opt_k_route(r, 2, ev, pm, *ev.CG, depot);
        or_opt_k_route(r, 3, ev, pm, *ev.CG, depot);
        two_opt_multi_trip_route(r, pm, *ev.CG, depot);
    }
    recompute_state_metrics_and_loads(cur, ev);
    return cur;
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
    state.routes[r1] = move(candidate1);
    state.routes[r2] = move(candidate2);
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
    state.routes[r] = move(candidate);
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
    double noise_strength
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

    // K is an availability ceiling, not a target route count.  The previous
    // loop stopped as soon as active_count reached K, which silently made a
    // 40-truck ceiling behave like a request to use 40 trucks.  Continue all
    // strictly beneficial, capacity-feasible Clarke-Wright merges; only the
    // fallback below is concerned with forcing an over-cap solution down to K.
    for (const auto &m : moves) {
        if (m.score <= 1e-9) break;
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
    Clock::time_point deadline
) {
    int R = (int)state.routes.size();
    int depot = find_depot_idx(*ev.CG);
    bool improved_any = false;

    for (int r_from = 0; r_from < R; ++r_from) {
        for (int pos_from = 1; pos_from + 1 < (int)state.routes[r_from].size(); ++pos_from) {
            if (Clock::now() >= deadline) return improved_any;
            int node = state.routes[r_from][pos_from];
            if (node < 0 || node >= (int)ev.CG->nodes.size() || ev.CG->nodes[node].type != 2) continue;
            double node_w = ev.CG->nodes[node].garbage_amount;

            for (int r_to = 0; r_to < R; ++r_to) {
                if (r_from == r_to) continue;
                if (cfg.capacity_mode == "strict" &&
                    state.route_max_trip_load[r_to] + node_w > cfg.truck_capacity + 1e-9 &&
                    !cfg.allow_multi_trip) {
                    continue;
                }

                for (int pos_to = 1; pos_to < (int)state.routes[r_to].size(); ++pos_to) {
                    if (Clock::now() >= deadline) return improved_any;

                    vector<int> tmp_from = state.routes[r_from];
                    vector<int> tmp_to = state.routes[r_to];
                    tmp_from.erase(tmp_from.begin() + pos_from);
                    tmp_to.insert(tmp_to.begin() + pos_to, node);
                    enforce_trip_separators(tmp_from, *ev.CG, depot);
                    enforce_trip_separators(tmp_to, *ev.CG, depot);

                    if (!trips_feasible_for_route(tmp_from, *ev.CG, depot)) continue;
                    if (!trips_feasible_for_route(tmp_to, *ev.CG, depot)) continue;
                    if (!route_hard_tw_feasible(tmp_from, ev, pm)) continue;
                    if (!route_hard_tw_feasible(tmp_to, ev, pm)) continue;

                    RouteMetrics mf = ev.compute_route_metrics(tmp_from, 0.0);
                    RouteMetrics mt = ev.compute_route_metrics(tmp_to, 0.0);
                    double old_cost = state.route_metrics[r_from].weighted_cost +
                                    state.route_metrics[r_to].weighted_cost;
                    double new_cost = mf.weighted_cost + mt.weighted_cost;

                    if (new_cost + 1e-9 < old_cost) {
                        state.routes[r_from] = std::move(tmp_from);
                        state.routes[r_to] = std::move(tmp_to);
                        recompute_dirty_routes(state, ev, {r_from, r_to});

                        // Important safety rule:
                        // after changing route vectors, all outer loop indices/sizes
                        // from the old routes may be stale. Return immediately and let
                        // the caller start the next light-polish pass from fresh routes.
                        return true;
                    }
                }
            }
        }
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
    if (!cfg.use_savings_warm_start) return false;
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
            noise
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
        bool changed = savings_light_relocate_pass(best, ev, pm, deadline);
        if (!changed) break;
    }

    recompute_state_metrics_and_loads(best, ev);
    if (!solution_hard_feasible(best, CG, pm)) return false;

    out = std::move(best);

    // This compact receipt is correctness evidence, not optional debug noise.
    // Keep it on stderr for every successful Savings construction.
    double elapsed = chrono::duration<double>(Clock::now() - t0).count();
    int active_routes = 0;
    for (const auto &route : out.routes) {
        bool has_customer = false;
        for (int node : route) {
            if (node >= 0 && node < (int)CG.nodes.size() &&
                CG.nodes[node].type == 2) {
                has_customer = true;
                break;
            }
        }
        if (has_customer) active_routes++;
    }
    cerr << "[SavingsWarmStart] obj=" << out.objective
        << " active_trucks=" << active_routes
        << " max_available_trucks=" << cfg.num_trucks
        << " variants=" << variants
        << " polish_budget_s=" << budget
        << " elapsed_s=" << elapsed
        << " verbose=" << (cfg.savings_verbose ? "true" : "false")
        << "\n";

    return true;
}

/* ---------------- Greedy + two-opt + relocate ---------------- */
vector<vector<int>> greedy_initial_routes(Compressed &CG, int depot, const vector<int> &collections_in, int num_trucks, double capacity, PairwiseManager &pm) {
    // num_trucks is a maximum available fleet, not a requirement to activate
    // every route. Fill the current vehicle before opening the next one.
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
            double d = fast_pair_time(cur, node, &pm);
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
            continue;
        }
        if (cfg.allow_splitting) {
            double can = capacity - loads[truck];
            if (can > 1e-9) {
                routes[truck].push_back(node);
                local_dem[node] -= can;
                loads[truck] += can;
                if (local_dem[node] <= 1e-6) remaining.erase(remaining.begin() + besti);
            }
            if (routes[truck].back() != depot) routes[truck].push_back(depot);
            if (cfg.allow_multi_trip) loads[truck] = 0.0; else ++truck;
        }
    }

    // Preserve correctness if the compact greedy could not place every node.
    // Remaining customers are added to available routes for later feasibility
    // validation/rescue; this is not a forced-all-trucks round robin.
    for (int node : remaining) {
        int best_truck = 0;
        for (int t = 1; t < num_trucks; ++t) {
            if (routes[t].size() < routes[best_truck].size()) best_truck = t;
        }
        if (routes[best_truck].back() != depot) routes[best_truck].push_back(depot);
        routes[best_truck].insert(routes[best_truck].end() - 1, node);
    }

    for (int t = 0; t < num_trucks; ++t) {
        if (routes[t].empty() || routes[t].back() != depot) routes[t].push_back(depot);
        normalize_route(routes[t], depot);
        enforce_trip_separators(routes[t], CG, depot);
    }
    return routes;
}
void two_opt_route(
    vector<int> &route,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    const int n = (int)route.size();
    if (n <= 3) return;

    // Road travel is directed: the classic four-boundary-edge 2-opt delta is
    // valid only for symmetric costs because reversing [i,k] also reverses all
    // of its internal arcs.  The previous test could accept A->B and then B->A
    // forever on asymmetric graphs.  Evaluate the complete route objective,
    // retain only hard-feasible strict improvements, and cap accepted moves.
    double current_cost = route_exact_cost(route, ev);
    if (!isfinite(current_cost)) return;

    const int move_cap = max(1, cfg.insertion_pos_cap);
    int accepted_moves = 0;
    while (accepted_moves < move_cap && !solver_should_stop()) {
        bool improved = false;
        for (int i = 1; i < n - 2 && !improved; ++i) {
            for (int k = i + 1; k < n - 1; ++k) {
                if (((i * n + k) & 63) == 0 && solver_should_stop()) return;

                vector<int> candidate = route;
                reverse(candidate.begin() + i, candidate.begin() + k + 1);
                if (!trips_feasible_for_route(
                        candidate,
                        *ev.CG,
                        find_depot_idx(*ev.CG)
                    )) {
                    continue;
                }
                if (cfg.use_time_window && cfg.tw_strict_insertion &&
                    !cfg.tw_allow_soft_intermediate &&
                    !route_hard_tw_feasible(candidate, ev, pm)) {
                    continue;
                }

                const double candidate_cost = route_exact_cost(candidate, ev);
                if (isfinite(candidate_cost) &&
                    candidate_cost + 1e-9 < current_cost) {
                    route.swap(candidate);
                    current_cost = candidate_cost;
                    ++accepted_moves;
                    improved = true;
                    break;
                }
            }
        }
        if (!improved) break;
    }
}

void two_opt_all(
    vector<vector<int>> &routes,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm
) {
    for (auto &route : routes) {
        if (solver_should_stop()) break;
        two_opt_route(route, ev, pm);
    }
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
    unsigned long long stream_id = 0;
    long long iter = 0;
    double current_obj = 0.0;
    double best_obj = 0.0;
    double temp = 0.0;
    long long accepted_moves = 0;
    long long attempted_moves = 0;
    long long stagnation = 0;
    string event = "periodic";
};

struct EarlyThroughputLnsResult {
    bool ran = false;
    bool improved = false;
    bool handoff_feasible = false;
    double requested_budget_s = 0.0;
    double granted_budget_s = 0.0;
    double elapsed_s = 0.0;
    double productive_patience_s = 0.0;
    double start_objective = INF_D;
    double final_objective = INF_D;
    long long attempted_repairs = 0;
    long long feasible_repairs = 0;
    long long improving_repairs = 0;
    long long censored_late_repairs = 0;
    string stop_reason = "not_started";
};

static EarlyThroughputLnsResult run_early_throughput_lns(
    SolutionState &state,
    ObjectiveEvaluator &ev,
    PairwiseManager &pm,
    unsigned worker_seed,
    unsigned long long worker_stream_id,
    vector<ConvergenceLogRow> *shared_conv_log,
    mutex *conv_mtx
) {
    EarlyThroughputLnsResult result;
    result.start_objective = state.objective;
    result.final_objective = state.objective;

    if (!cfg.use_early_throughput_lns || cfg.hard_time_limit_s <= 0.0) {
        return result;
    }

    recompute_state_metrics_and_loads(state, ev);
    if (!solution_hard_feasible(state, *ev.CG, pm)) {
        safe_log_line(
            "[EarlyLNS] skipped worker=", worker_stream_id,
            " reason=infeasible_start objective=",
            state.objective
        );
        return result;
    }

    const double hard_budget_s = cfg.hard_time_limit_s;
    const double requested = max(
        cfg.early_lns_min_time_s,
        min(
            cfg.early_lns_max_time_s,
            hard_budget_s * cfg.early_lns_fraction
        )
    );
    const double finalization_reserve_s = min(
        1.5,
        max(0.35, hard_budget_s * 0.005)
    );
    // Even if preprocessing consumed an unexpectedly large share, do not let
    // the prefix crowd out the deep regime entirely.
    const double deep_reserve_s = max(
        0.50,
        min(cfg.sa_time_limit, hard_budget_s * 0.20)
    );
    const double available = max(
        0.0,
        hard_budget_s
        - solver_elapsed_seconds()
        - finalization_reserve_s
        - deep_reserve_s
    );
    const double granted = min(requested, available);

    result.requested_budget_s = requested;
    result.granted_budget_s = granted;
    result.productive_patience_s = cfg.early_lns_no_improve_s > 0.0
        ? cfg.early_lns_no_improve_s
        : max(2.0, min(8.0, hard_budget_s * 0.04));

    if (granted < 0.10) {
        safe_log_line(
            "[EarlyLNS] skipped worker=", worker_stream_id,
            " reason=insufficient_remaining_budget",
            " requested_s=", requested,
            " available_s=", available,
            " elapsed_s=", solver_elapsed_seconds(),
            " deep_reserve_s=", deep_reserve_s
        );
        return result;
    }

    result.ran = true;
    result.stop_reason = "phase_budget";
    const auto phase_start = Clock::now();
    const auto phase_deadline = phase_start + chrono::duration_cast<Clock::duration>(
        chrono::duration<double>(granted)
    );
    SolutionState best = state;
    mt19937 rng(worker_seed ^ 0x6a09e667u);
    long long attempts_since_improvement = 0;
    constexpr int early_operator_count = 4;
    array<double, early_operator_count> operator_weights = {1.0, 1.0, 1.0, 1.0};
    array<long long, early_operator_count> operator_attempts = {0, 0, 0, 0};
    array<long long, early_operator_count> operator_improvements = {0, 0, 0, 0};
    array<double, early_operator_count> operator_time_ms = {0.0, 0.0, 0.0, 0.0};
    auto last_productive_time = phase_start;
    const double initial_grace_s = min(
        granted,
        max(
            result.productive_patience_s,
            min(5.0, granted * 0.35)
        )
    );

    safe_log_line(
        "[EarlyLNS] START worker=", worker_stream_id,
        " seed=", worker_seed,
        " policy=throughput_before_intensification",
        " fraction=", cfg.early_lns_fraction,
        " requested_s=", requested,
        " granted_s=", granted,
        " productive_patience_s=", result.productive_patience_s,
        " initial_grace_s=", initial_grace_s,
        " destroy_ratio=", cfg.early_lns_destroy_min_ratio,
        "..", cfg.early_lns_destroy_max_ratio,
        " start_objective=", best.objective,
        " repair=approx_rank_exact_shortlist",
        " post_repair_polish=false"
    );

    while (!solver_should_stop() && Clock::now() < phase_deadline) {
        int destroy_mode = 0;
        if (result.attempted_repairs < early_operator_count) {
            // Give every operator one observation before adapting.
            destroy_mode = (int)result.attempted_repairs;
        } else {
            const double total_weight = accumulate(
                operator_weights.begin(),
                operator_weights.end(),
                0.0
            );
            double ticket = uniform_real_distribution<double>(
                0.0,
                max(1e-9, total_weight)
            )(rng);
            double cumulative = operator_weights[0];
            while (destroy_mode + 1 < early_operator_count && ticket >= cumulative) {
                ++destroy_mode;
                cumulative += operator_weights[destroy_mode];
            }
        }

        const auto repair_start = Clock::now();
        SolutionState candidate = alns_destroy_repair(
            best,
            ev,
            pm,
            rng,
            destroy_mode,
            true
        );
        const double repair_ms = chrono::duration<double, milli>(
            Clock::now() - repair_start
        ).count();
        ++result.attempted_repairs;
        ++operator_attempts[destroy_mode];
        operator_time_ms[destroy_mode] += repair_ms;

        // A repair finishing after the phase deadline is diagnostic evidence,
        // not a legal prefix improvement. This prevents deadline overshoot from
        // being credited to the early policy.
        if (Clock::now() > phase_deadline) {
            ++result.censored_late_repairs;
            break;
        }

        if (!solution_hard_feasible(candidate, *ev.CG, pm)) {
            operator_weights[destroy_mode] = max(
                0.15,
                0.90 * operator_weights[destroy_mode] + 0.10 * 0.15
            );
            ++attempts_since_improvement;
            continue;
        }
        ++result.feasible_repairs;

        if (candidate.objective + 1e-9 < best.objective) {
            const double before = best.objective;
            const double gain = before - candidate.objective;
            const double scale = max(1.0, meaningful_gain_threshold(before));
            const double speed_factor = 1.0 / sqrt(max(0.10, repair_ms));
            const double reward = min(
                10.0,
                (4.0 + min(4.0, gain / scale)) * speed_factor
            );
            operator_weights[destroy_mode] = min(
                10.0,
                max(
                    0.15,
                    0.90 * operator_weights[destroy_mode] + 0.10 * reward
                )
            );
            ++operator_improvements[destroy_mode];
            best = std::move(candidate);
            ++result.improving_repairs;
            attempts_since_improvement = 0;
            last_productive_time = Clock::now();
            update_global_best_checked(best, *ev.CG, pm);

            if (cfg.log_convergence && shared_conv_log && conv_mtx) {
                lock_guard<mutex> lk(*conv_mtx);
                shared_conv_log->push_back({
                    solver_elapsed_seconds(),
                    worker_seed,
                    worker_stream_id,
                    result.attempted_repairs,
                    best.objective,
                    best.objective,
                    0.0,
                    result.improving_repairs,
                    result.attempted_repairs,
                    attempts_since_improvement,
                    "early_lns_improvement"
                });
            }

            if (cfg.early_lns_verbose) {
                safe_log_line(
                    "[EarlyLNS] improve worker=", worker_stream_id,
                    " attempt=", result.attempted_repairs,
                    " before=", before,
                    " after=", best.objective,
                    " gain=", (before - best.objective),
                    " elapsed_s=", solver_elapsed_seconds()
                );
            }
        }
        else {
            const double speed_reward = min(
                0.60,
                0.30 / sqrt(max(0.10, repair_ms))
            );
            operator_weights[destroy_mode] = max(
                0.15,
                0.90 * operator_weights[destroy_mode] + 0.10 * speed_reward
            );
            ++attempts_since_improvement;
        }

        solver_live_telemetry(
            "early-throughput-lns",
            best.objective,
            result.attempted_repairs
        );

        const double phase_elapsed_s = chrono::duration<double>(
            Clock::now() - phase_start
        ).count();
        const double no_productive_s = chrono::duration<double>(
            Clock::now() - last_productive_time
        ).count();
        if (phase_elapsed_s >= initial_grace_s
            && no_productive_s >= result.productive_patience_s) {
            result.stop_reason = "productive_stagnation";
            break;
        }
    }

    recompute_state_metrics_and_loads(best, ev);
    result.handoff_feasible = solution_hard_feasible(best, *ev.CG, pm);
    if (result.handoff_feasible) {
        state = best;
        update_global_best_checked(state, *ev.CG, pm);
    }
    result.elapsed_s = chrono::duration<double>(Clock::now() - phase_start).count();
    result.final_objective = result.handoff_feasible
        ? state.objective
        : result.start_objective;
    result.improved = result.handoff_feasible
        && result.final_objective + 1e-9 < result.start_objective;

    if (cfg.log_convergence && shared_conv_log && conv_mtx && result.handoff_feasible) {
        lock_guard<mutex> lk(*conv_mtx);
        shared_conv_log->push_back({
            solver_elapsed_seconds(),
            worker_seed,
            worker_stream_id,
            result.attempted_repairs,
            state.objective,
            state.objective,
            0.0,
            result.improving_repairs,
            result.attempted_repairs,
            attempts_since_improvement,
            "early_lns_handoff"
        });
    }

    const double repairs_per_s = result.elapsed_s > 1e-9
        ? (double)result.attempted_repairs / result.elapsed_s
        : 0.0;
    const double improving_per_s = result.elapsed_s > 1e-9
        ? (double)result.improving_repairs / result.elapsed_s
        : 0.0;
    safe_log_line(
        "[EarlyLNS] END worker=", worker_stream_id,
        " seed=", worker_seed,
        " handoff_feasible=", (result.handoff_feasible ? "true" : "false"),
        " improved=", (result.improved ? "true" : "false"),
        " start_objective=", result.start_objective,
        " final_objective=", result.final_objective,
        " elapsed_s=", result.elapsed_s,
        " attempted=", result.attempted_repairs,
        " feasible=", result.feasible_repairs,
        " improving=", result.improving_repairs,
        " censored_late=", result.censored_late_repairs,
        " stop_reason=", result.stop_reason,
        " productive_patience_s=", result.productive_patience_s,
        " repairs_per_s=", repairs_per_s,
        " improving_per_s=", improving_per_s
    );
    static const array<const char *, early_operator_count> operator_names = {
        "random",
        "expensive_related",
        "shaw_related",
        "worst_string_related"
    };
    for (int op = 0; op < early_operator_count; ++op) {
        safe_log_line(
            "[EarlyLNSOperator] worker=", worker_stream_id,
            " name=", operator_names[op],
            " attempts=", operator_attempts[op],
            " improvements=", operator_improvements[op],
            " final_weight=", operator_weights[op],
            " total_time_ms=", operator_time_ms[op],
            " avg_time_ms=", (operator_attempts[op] > 0
                ? operator_time_ms[op] / (double)operator_attempts[op]
                : 0.0)
        );
    }

    return result;
}

// A seed is intentionally reused by several SA phases/restarts.  It therefore
// cannot identify one continuous trajectory.  Every sa_worker invocation gets
// a process-unique stream id so analysis never connects unrelated temperature,
// acceptance, or stagnation sequences into needle-like lines.
static atomic<unsigned long long> convergence_stream_counter{1};

struct AlgoResult {
    SolutionState best_state;
    double runtime_sec = 0.0;
    double iterations = 0.0;
    long long accepted_moves = 0;
    long long attempted_moves = 0;
    long long drift_corrections = 0;
    long long capacity_violations = 0;
    double total_overload = 0.0;
    vector<pair<double, double>> convergence;
};

static inline double annealing_worsening_budget(double temperature, double u) {
    // One exponential-race threshold is shared by the cheap screen and exact
    // objective check.  The former code drew twice, so an exactly estimated
    // worsening move was accepted with exp(-2*delta/T) instead of exp(-delta/T).
    // This form also replaces two exp calls with one log call.
    const double safe_u = min(1.0 - 1e-15, max(1e-15, u));
    return -max(1e-9, temperature) * log(safe_u);
}

static void print_routes(const SolutionState &s) {
    for (int i = 0; i < (int)s.routes.size(); i++) {
        cout << "Truck " << i << ": ";
        for (int n : s.routes[i]) cout << n << " ";
        cout << "\n";
    }
}

AlgoResult sa_worker(
    Compressed &CG,
    PairwiseManager &pm,
    ObjectiveEvaluator &ev,
    int depot,
    const vector<int> &collections,
    unsigned seed,
    double time_limit,
    bool allow_cross2,
    const SolutionState *warm_start = nullptr,
    vector<ConvergenceLogRow> *shared_conv_log = nullptr,
    mutex *conv_mtx = nullptr
) {
    AlgoResult out;
    begin_recompute_profile_batch();
    const unsigned long long stream_id = convergence_stream_counter.fetch_add(1, memory_order_relaxed);
    auto tstart = Clock::now();
    // Convergence telemetry is sampled by wall-clock time, not iteration count.
    // Fast instances can execute millions of iterations per second; logging every
    // 100 iterations produced hundreds of thousands of CSV rows and contended on
    // the shared log mutex. Four samples/second/worker is enough for diagnostics
    // without turning evidence collection into part of the optimization cost.
    double next_convergence_sample_s = 0.0;
    constexpr double convergence_sample_interval_s = 0.25;

    unsigned rng_seed = cfg.deterministic_seed ? cfg.base_seed : seed;
    mt19937 rng(rng_seed);

    SolutionState state(cfg.num_trucks, (int)CG.nodes.size());
    bool used_incumbent_warm_start = false;
    bool used_cluster_warm_start = false;

    if (warm_start && !warm_start->routes.empty()) {
        state = *warm_start;
        recompute_state_metrics_and_loads(state, ev);
        used_incumbent_warm_start =
            (int)state.routes.size() == cfg.num_trucks &&
            solution_hard_feasible(state, CG, pm);
        if (!used_incumbent_warm_start) {
            safe_log_line(
                "[SAStart] stream_id=", stream_id,
                " source=incumbent rejected=true reason=incompatible_or_infeasible"
            );
            state = SolutionState(cfg.num_trucks, (int)CG.nodes.size());
        }
    }

    if (!used_incumbent_warm_start) {
        used_cluster_warm_start = build_cluster_warm_start_solution(
            state,
            collections,
            ev,
            pm
        );
    }

    if (!used_incumbent_warm_start && !used_cluster_warm_start) {
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
                    two_opt_multi_trip_route(r, pm, CG, depot);
                }
            }
            else {
                two_opt_all(routes, ev, pm);
            }
        }
        state.routes = routes;
    } else if (!used_incumbent_warm_start) {
        if (cfg.use_2opt) {
            if (cfg.allow_multi_trip) {
                for (auto &r : state.routes) {
                    two_opt_multi_trip_route(r, pm, CG, depot);
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

    safe_log_line(
        "[SAStart] stream_id=", stream_id,
        " source=", (used_incumbent_warm_start
            ? "incumbent"
            : (used_cluster_warm_start ? "cluster" : "greedy")),
        " objective=", state.objective,
        " time_limit_s=", time_limit,
        " cross2=", (allow_cross2 ? "true" : "false")
    );

    SolutionState best = state;
    solver_live_telemetry("sa-start", best.objective, 0);
    vector<SolutionState> elite_pool;
    elite_pool_update(elite_pool, state, 8);
    elite_pool_update(elite_pool, best, 8);

    double T = max(1e-9, cfg.sa_T0);
    double sampled_median_delta = 0.0;
    int usable_temperature_samples = 0;
    int rejected_temperature_samples = 0;
    if (cfg.auto_T0) {
        mt19937 rng_sample(seed ^ 0x9e3779b9);
        int samples = 200;
        vector<double> finite_abs_deltas;
        finite_abs_deltas.reserve(samples);
        for (int s = 0; s < samples; ++s) {
            int r1 = rng_sample() % R, r2 = rng_sample() % R;
            if (state.routes[r1].size() <= 3 || state.routes[r2].size() <= 3) continue;
            int i = 1 + rng_sample() % (state.routes[r1].size() - 2);
            int j = 1 + rng_sample() % (state.routes[r2].size() - 2);
            if (r1 == r2 && i == j) continue;
            double approx = ev.delta_swap_approx(state, r1, i, r2, j);
            const double magnitude = fabs(approx);
            // INF_D is a sentinel for invalid/overlapping/unreachable moves.
            // Letting even one sentinel enter the mean produced T0 around 1e16.
            if (!isfinite(magnitude) || magnitude <= 1e-9 || magnitude >= INF_D / 8.0) {
                rejected_temperature_samples++;
                continue;
            }
            finite_abs_deltas.push_back(magnitude);
        }
        usable_temperature_samples = (int)finite_abs_deltas.size();
        if (!finite_abs_deltas.empty()) {
            const size_t middle = finite_abs_deltas.size() / 2;
            nth_element(
                finite_abs_deltas.begin(),
                finite_abs_deltas.begin() + middle,
                finite_abs_deltas.end()
            );
            sampled_median_delta = finite_abs_deltas[middle];
            if (finite_abs_deltas.size() % 2 == 0 && middle > 0) {
                const double lower = *max_element(
                    finite_abs_deltas.begin(),
                    finite_abs_deltas.begin() + middle
                );
                sampled_median_delta = 0.5 * (lower + sampled_median_delta);
            }

            // At T0, a representative worsening move has an 80% chance of
            // acceptance. Clamp against the incumbent scale so corrupt/sentinel
            // costs can never dominate even if they slip through a data source.
            constexpr double initial_acceptance_target = 0.80;
            const double calibrated = sampled_median_delta / -log(initial_acceptance_target);
            const double objective_cap = max(1.0, fabs(state.objective) * 0.25);
            T = min(objective_cap, max(1.0, calibrated));
        } else {
            T = max(1.0, cfg.sa_T0);
        }
    }

    const double initial_temperature = max(1e-9, T);
    constexpr double sa_reference_cooling_steps = 10000.0;
    double final_temperature_ratio = 1.0;
    if (cfg.sa_alpha > 0.0 && cfg.sa_alpha < 1.0) {
        final_temperature_ratio = pow(cfg.sa_alpha, sa_reference_cooling_steps);
    }
    final_temperature_ratio = min(1.0, max(1e-4, final_temperature_ratio));
    const double log_final_temperature_ratio = log(final_temperature_ratio);
    const double cooling_horizon_s = max(0.10, time_limit);

    safe_log_line(
        "[SAConfig] stream_id=", stream_id,
        " cooling=time_normalized",
        " initial_temperature=", initial_temperature,
        " auto_t0=", (cfg.auto_T0 ? "true" : "false"),
        " usable_samples=", usable_temperature_samples,
        " rejected_samples=", rejected_temperature_samples,
        " median_delta=", sampled_median_delta,
        " alpha=", cfg.sa_alpha,
        " reference_steps=", (long long)sa_reference_cooling_steps,
        " final_temperature_ratio=", final_temperature_ratio,
        " horizon_s=", cooling_horizon_s,
        " relink_period=", cfg.relink_period
    );

    uniform_real_distribution<double> unif(0.0, 1.0);
    long long iterations = 0, accepted = 0, attempted = 0, drift_corrections = 0;
    long long cap_viol = 0;
    double total_overload = 0.0;
    int stagnation = 0;
    const int recompute_period = 8000;
    int window_attempts = 0, window_accepted = 0;
    double adaptive_temperature_multiplier = 1.0;
    double next_temperature_adaptation_s = 0.25;
    // Clock/governor checks used to run on every proposal and a fixed two-
    // million-iteration ceiling could end a fast worker before its time slice.
    // Check the wall clock in small batches instead: deadline error is bounded
    // to 255 cheap proposals, while machine speed no longer changes the budget.
    constexpr long long sa_clock_check_mask = 255LL;

    while (true) {
        if ((iterations & sa_clock_check_mask) == 0) {
            const double elapsed_check_s = chrono::duration<double>(
                Clock::now() - tstart
            ).count();
            if (elapsed_check_s >= time_limit) break;
            if (solver_should_stop()) {
                update_global_best_checked(best, *ev.CG, pm);
                break;
            }
        }

        iterations++;
        if ((iterations & 255LL) == 0) {
            solver_live_telemetry("sa-search", best.objective, iterations);
        }

        // Cooling and feedback advance by elapsed search time, not by raw CPU
        // throughput. Recompute only every 256 iterations so exp() is not a hot-
        // loop cost. This yields the same schedule on slow and fast machines.
        if ((iterations & 255LL) == 0) {
            const double elapsed_s = chrono::duration<double>(Clock::now() - tstart).count();
            if (elapsed_s + 1e-12 >= next_temperature_adaptation_s) {
                if (window_attempts > 0) {
                    const double acc_rate =
                        (double)window_accepted / (double)window_attempts;
                    if (acc_rate < 0.08) adaptive_temperature_multiplier *= 1.15;
                    else if (acc_rate > 0.55) adaptive_temperature_multiplier *= 0.85;
                    else adaptive_temperature_multiplier =
                        1.0 + 0.90 * (adaptive_temperature_multiplier - 1.0);
                    adaptive_temperature_multiplier = min(
                        2.0,
                        max(0.5, adaptive_temperature_multiplier)
                    );
                }
                window_attempts = 0;
                window_accepted = 0;
                next_temperature_adaptation_s = elapsed_s + 0.25;
            }
            const double progress = min(1.0, max(0.0, elapsed_s / cooling_horizon_s));
            const double scheduled_temperature = initial_temperature * exp(
                log_final_temperature_ratio * progress
            );
            T = max(1e-9, scheduled_temperature * adaptive_temperature_multiplier);
        }
        if (iterations % recompute_period == 0) recompute_state_metrics_and_loads(state, ev);

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
        bool attempted_move = false;

        // SWAP
        if (rsel < swap_prob) {
            int r1 = rng() % R, r2 = rng() % R;
            if (state.routes[r1].size() > 3 && state.routes[r2].size() > 3) {
                int i = 1 + rng() % (state.routes[r1].size() - 2);
                int j = 1 + rng() % (state.routes[r2].size() - 2);
                if (!(r1 == r2 && i == j)) {
                    attempted_move = true;
                    bool capacity_possible = true;
                    if (r1 != r2 && !cfg.allow_multi_trip) {
                        const int a = state.routes[r1][i];
                        const int b = state.routes[r2][j];
                        const double da = CG.nodes[a].garbage_amount;
                        const double db = CG.nodes[b].garbage_amount;
                        const double overload1 = max(
                            0.0,
                            state.route_load[r1] - da + db - cfg.truck_capacity
                        );
                        const double overload2 = max(
                            0.0,
                            state.route_load[r2] - db + da - cfg.truck_capacity
                        );
                        if (overload1 > 1e-9 || overload2 > 1e-9) {
                            capacity_possible = false;
                            cap_viol++;
                            total_overload += overload1 + overload2;
                        }
                    }
                    const double worsening_budget = annealing_worsening_budget(
                        T,
                        unif(rng)
                    );
                    double approx = capacity_possible
                        ? ev.delta_swap_approx(state, r1, i, r2, j)
                        : INF_D;
                    if (isfinite(approx) && approx < INF_D / 8.0 &&
                        approx <= worsening_budget) {
                        double weighted_delta = compute_weighted_swap_delta(state, ev, r1, i, r2, j);
                        if (isfinite(weighted_delta) && weighted_delta < INF_D / 8.0 &&
                            weighted_delta <= worsening_budget) {
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
                                        if (safe_assign_one_route(state, r1, candidate, ev)) {
                                            accepted_move = true;
                                        }
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
                                        if (safe_assign_two_routes(state, r1, new_r1, r2, new_r2, ev)) {
                                            accepted_move = true;
                                        }
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
            int from = rng() % R, to = rng() % R;
            if (state.routes[from].size() > 3 && state.routes[to].size() > 2) {
                int pos_from = 1 + rng() % (state.routes[from].size() - 2);
                int pos_to = 1 + rng() % (state.routes[to].size() - 1);
                if (!(from == to && (pos_to == pos_from || pos_to == pos_from + 1))) {
                    attempted_move = true;
                    bool capacity_possible = true;
                    if (from != to && !cfg.allow_multi_trip) {
                        const int node = state.routes[from][pos_from];
                        const double overload = max(
                            0.0,
                            state.route_load[to] + CG.nodes[node].garbage_amount
                                - cfg.truck_capacity
                        );
                        if (overload > 1e-9) {
                            capacity_possible = false;
                            cap_viol++;
                            total_overload += overload;
                        }
                    }
                    const double worsening_budget = annealing_worsening_budget(
                        T,
                        unif(rng)
                    );
                    double approx = capacity_possible
                        ? ev.delta_relocate_approx(state, from, pos_from, to, pos_to)
                        : INF_D;
                    if (isfinite(approx) && approx < INF_D / 8.0 &&
                        approx <= worsening_budget) {
                        double weighted_delta = compute_weighted_relocate_delta(state, ev, from, pos_from, to, pos_to);
                        if (isfinite(weighted_delta) && weighted_delta < INF_D / 8.0 &&
                            weighted_delta <= worsening_budget) {
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
                                    if (safe_assign_one_route(state, from, cand, ev)) {
                                        accepted_move = true;
                                    }
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
                                    if (safe_assign_two_routes(state, from, new_from, to, new_to, ev)) {
                                        accepted_move = true;
                                    }
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
            int r1 = rng() % R, r2 = rng() % R;
            if (r1 != r2 && allow_cross2 &&
                state.routes[r1].size() > 4 && state.routes[r2].size() > 4) {
                int i1 = 1 + rng() % (state.routes[r1].size() - 3);
                int i2 = 1 + rng() % (state.routes[r2].size() - 3);
                attempted_move = true;
                double approx = ev.delta_cross2_approx(state, r1, i1, r2, i2);
                const double worsening_budget = annealing_worsening_budget(
                    T,
                    unif(rng)
                );
                if (isfinite(approx) && approx < INF_D / 8.0 &&
                    approx <= worsening_budget) {
                    double weighted_delta = compute_weighted_cross_delta(state, ev, r1, i1, r2, i2);
                    if (isfinite(weighted_delta) && weighted_delta < INF_D / 8.0 &&
                        weighted_delta <= worsening_budget) {
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
                            if (safe_assign_two_routes(state, r1, new1, r2, new2, ev)) {
                                accepted_move = true;
                            }
                            else cap_viol++;
                        }
                    }
                }
            }
        }

        if (attempted_move) {
            attempted++;
            window_attempts++;
        }
        if (accepted_move) {
            accepted++;
            window_accepted++;
            stagnation = 0;
            if (state.objective < best.objective - 1e-9) {
                best = state;
                update_global_best_checked(best, *ev.CG, pm);
            }
        } else {
            stagnation++;
        }

        // Elite pool update and path relink
        if (cfg.use_elite_pool) {
            if (iterations % max(1, cfg.elite_update_period) == 0) {
                elite_pool_update(elite_pool, state, 8);
                elite_pool_update(elite_pool, best, 8);
            }
            if (cfg.use_path_relink && elite_pool.size() >= 2 && iterations % max(1, cfg.relink_period) == 0) {
                SolutionState relink = path_relink_between(elite_pool[0], elite_pool[1], ev, pm);
                recompute_state_metrics_and_loads(relink, ev);
                if (relink.objective + 1e-9 < best.objective &&
                    solution_hard_feasible(relink, *ev.CG, pm)) {
                    best = std::move(relink);
                    update_global_best_checked(best, *ev.CG, pm);
                }
            }
        }

        // ALNS kick when stagnation persists.
        if (cfg.use_alns && stagnation > cfg.stagnation_alns_trigger && iterations % 500 == 0) {
            SolutionState kicked = alns_destroy_repair(state, ev, pm, rng, stagnation % 4);

            if (kicked.objective + 1e-9 < state.objective) {
                state = std::move(kicked);

                if (state.objective + 1e-9 < best.objective) {
                    best = state;
                    update_global_best_checked(best, *ev.CG, pm);
                    stagnation = 0;

                    if (cfg.log_convergence && shared_conv_log && conv_mtx) {
                        lock_guard<mutex> lk(*conv_mtx);

                        shared_conv_log->push_back({
                            solver_elapsed_seconds(),
                            seed,
                            stream_id,
                            (long long)iterations,
                            state.objective,
                            best.objective,
                            T,
                            accepted,
                            attempted,
                            stagnation,
                            "improvement"
                        });
                    }
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
            double tnow = chrono::duration<double>(Clock::now() - tstart).count();
            if (tnow + 1e-12 >= next_convergence_sample_s) {
                next_convergence_sample_s = tnow + convergence_sample_interval_s;
                out.convergence.push_back({tnow, best.objective});

                if (shared_conv_log && conv_mtx) {
                    lock_guard<mutex> lk(*conv_mtx);
                    shared_conv_log->push_back({
                        solver_elapsed_seconds(), // process-relative time_s
                        seed,                   // seed
                        stream_id,              // unique SA invocation
                        (long long)iterations,  // iter
                        state.objective,        // current_obj
                        best.objective,         // best_obj
                        T,                      // temp
                        accepted,               // accepted_moves
                        attempted,              // attempted_moves
                        stagnation,             // stagnation
                        "periodic"              // event
                    });
                }
            }
        }
    }

    // Keep worker finalization cheap.  A worker is one member of a parallel
    // portfolio; running the full deterministic refinement chain here made all
    // workers repeat the same expensive work concurrently, and the winning
    // candidate was refined yet again by the coordinator.  The coordinator
    // refines only the selected feasible winner once.
    recompute_state_metrics_and_loads(best, ev);
    update_global_best_checked(best, *ev.CG, pm);

    out.best_state = best;
    out.runtime_sec = chrono::duration<double>(Clock::now() - tstart).count();
    out.iterations = iterations;
    out.accepted_moves = accepted;
    out.attempted_moves = attempted;
    out.drift_corrections = drift_corrections;
    out.capacity_violations = cap_viol;
    out.total_overload = total_overload;

    // Aggregate once per completed worker, not inside the SA hot loop.
    profile.sa_iterations.fetch_add(iterations, memory_order_relaxed);
    profile.sa_accepted_moves.fetch_add(accepted, memory_order_relaxed);
    profile.sa_attempted_moves.fetch_add(attempted, memory_order_relaxed);
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

    // Log the final best after final refinement.
    // This makes convergence.csv match the final printed solution.
    if (cfg.log_convergence) {
        double tnow = chrono::duration<double>(Clock::now() - tstart).count();

        out.convergence.push_back({tnow, best.objective});

        if (shared_conv_log && conv_mtx) {
            lock_guard<mutex> lk(*conv_mtx);

            shared_conv_log->push_back({
                solver_elapsed_seconds(), // process-relative time_s
                seed,                   // seed
                stream_id,              // unique SA invocation
                (long long)iterations,  // iter
                best.objective,         // current_obj
                best.objective,         // best_obj
                T,                      // temp
                accepted,               // accepted_moves
                attempted,              // attempted_moves
                stagnation,             // stagnation
                "worker_final"          // event
            });
        }
    }

    flush_recompute_profile_batch();
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

static bool final_solution_feasible(const SolutionState &s, const Compressed &CG) {
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
            << "objective,distance_m,travel_time_s,service_time_s,waiting_s,lateness_s,co2_g,"
            << "total_load,max_trip_load,total_trips,max_trips_single_truck,used_trucks,"
            << "fleet_balance_s,runtime_s,iterations,accepted_moves,attempted_moves,acceptance_rate,"
            << "drift_corrections,capacity_violations,total_overload,"
            << "recompute_calls,alns_calls,polish_calls,pair_queries,"
            << "feasible\n";
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
        << acceptance_rate << ","
        << drift_corrections << ","
        << capacity_violations << ","
        << total_overload << ","
        << profile.recompute_calls.load(memory_order_relaxed) << ","
        << profile.alns_calls.load(memory_order_relaxed) << ","
        << profile.polish_calls.load(memory_order_relaxed) << ","
        << profile.pair_queries.load(memory_order_relaxed) << ","
        << (feasible ? 1 : 0)
        << "\n";
}

static bool parse_bool_arg(const string &s) {
    string x = s;
    transform(x.begin(), x.end(), x.begin(), ::tolower);

    return (
        x == "1" ||
        x == "true" ||
        x == "yes" ||
        x == "y" ||
        x == "on"
    );
}

int main(int argc, char **argv) {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    auto total_start_time = Clock::now();

    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    solver_governor_start();

    for (int i = 1; i < argc; i++) {
        string s = argv[i];

        auto parse_bool_local = [](const string &v) {
            return v == "true" || v == "1" || v == "yes" || v == "on";
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
        else if (s == "--no_improve_stop_s" && i + 1 < argc) {
            cfg.no_improve_stop_s = max(0.0, stod(argv[++i]));
        }
        else if (s == "--fill_time_budget" && i + 1 < argc) {
            cfg.fill_time_budget = parse_bool_local(argv[++i]);
        }
        else if (s == "--use_early_throughput_lns" && i + 1 < argc) {
            cfg.use_early_throughput_lns = parse_bool_local(argv[++i]);
        }
        else if (s == "--early_lns_fraction" && i + 1 < argc) {
            cfg.early_lns_fraction = max(0.0, min(0.50, stod(argv[++i])));
        }
        else if (s == "--early_lns_min_time_s" && i + 1 < argc) {
            cfg.early_lns_min_time_s = max(0.0, stod(argv[++i]));
        }
        else if (s == "--early_lns_max_time_s" && i + 1 < argc) {
            cfg.early_lns_max_time_s = max(0.0, stod(argv[++i]));
        }
        else if (s == "--early_lns_no_improve_s" && i + 1 < argc) {
            cfg.early_lns_no_improve_s = max(0.0, stod(argv[++i]));
        }
        else if (s == "--early_lns_destroy_min_ratio" && i + 1 < argc) {
            cfg.early_lns_destroy_min_ratio = max(0.01, min(0.90, stod(argv[++i])));
        }
        else if (s == "--early_lns_destroy_max_ratio" && i + 1 < argc) {
            cfg.early_lns_destroy_max_ratio = max(0.01, min(0.95, stod(argv[++i])));
        }
        else if (s == "--early_lns_parallel_min_customers" && i + 1 < argc) {
            cfg.early_lns_parallel_min_customers = max(1, stoi(argv[++i]));
        }
        else if (s == "--early_lns_verbose" && i + 1 < argc) {
            cfg.early_lns_verbose = parse_bool_local(argv[++i]);
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
        else if (s == "--stagnation_trigger" && i + 1 < argc) {
            cfg.stagnation_alns_trigger = stoi(argv[++i]);
        }
        else if (s == "--no_regret") {
            cfg.use_regret_repair = false;
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
        else if (s == "--interroute_polish_rounds" && i + 1 < argc) {
            cfg.interroute_polish_rounds = max(0, stoi(argv[++i]));
        }
        else if (s == "--final_refinement_rounds" && i + 1 < argc) {
            cfg.final_refinement_rounds = max(1, stoi(argv[++i]));
        }
        else if (s == "--interroute_scan_cap" && i + 1 < argc) {
            cfg.interroute_scan_cap = max(1, stoi(argv[++i]));
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
        else if (s == "--fragment_lns_pos_cap" && i + 1 < argc) {
            cfg.fragment_lns_pos_cap = max(1, stoi(argv[++i]));
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
        else if (s == "--use_topk_insertion" && i + 1 < argc) {
            cfg.use_topk_insertion = parse_bool_arg(argv[++i]);
        }
        else if (s == "--insertion_topk_exact" && i + 1 < argc) {
            cfg.insertion_topk_exact = atoi(argv[++i]);
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
        else if (s == "--euclidean_speed_kph" && i + 1 < argc) {
            cfg.euclidean_speed_kph = stod(argv[++i]);
        }
        else if (s == "--require_coords_for_euclidean" && i + 1 < argc) {
            cfg.require_coords_for_euclidean = parse_bool_arg(argv[++i]);
        }
        else if (s == "--euclidean_round_distance" && i + 1 < argc) {
            cfg.euclidean_round_distance = parse_bool_arg(argv[++i]);
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
            cerr << "[warn] unknown or incomplete argument ignored: " << s << "\n";
        }
    }

    if (cfg.early_lns_max_time_s < cfg.early_lns_min_time_s) {
        cfg.early_lns_max_time_s = cfg.early_lns_min_time_s;
    }
    if (cfg.early_lns_destroy_max_ratio < cfg.early_lns_destroy_min_ratio) {
        swap(cfg.early_lns_destroy_min_ratio, cfg.early_lns_destroy_max_ratio);
    }

    cerr << "[config] metric_mode=" << cfg.metric_mode
        << " coords_csv=" << cfg.coords_csv
        << " use_direct_arc_costs=" << cfg.use_direct_arc_costs
        << "\n";

    Compressed CG;
    int N = 0, M = 0, K = 0, depot_idx = 0;
    vector<int> collections;
    vector<pair<int, int>> virtual_alias_pairs;
    double capacity_input = cfg.truck_capacity;

    if (!(cin >> N >> M)) { cerr << "Bad input (N M)\n"; return 2; }
    if (!(cin >> K)) { cerr << "Bad input (K)\n"; return 2; }
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
        raw_edges.emplace_back(u, v, d, s);
        max_raw_id = max(max_raw_id, max(u, v));
    }

    int G;
    if (!(cin >> G)) { cerr << "Bad input (G)\n"; return 2; }

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
        raw_customers.push_back({node, garbage, st, e, l});
        max_cust_id = max(max_cust_id, node);
    }

    if (!(cin >> capacity_input)) { cerr << "Missing capacity\n"; return 2; }
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
        if (u < 0 || v < 0) {
            cerr << "Invalid edge indices\n";
            return 2;
        }
        long long maxid = max(u, v);
        if (maxid >= (long long)CG.nodes.size()) {
            while (maxid >= (long long)CG.nodes.size()) CG.add_node((long long)CG.nodes.size(), 0, 0, 0);
        }
        CG.add_edge_directed((int)u, (int)v, dist, sp);
    }

    collections.clear();
    for (auto &c : raw_customers) {
        long long node = c.node;
        if (assume_one_based) node--;
        if (node < 0) {
            cerr << "Invalid customer index\n";
            return 2;
        }
        while (node >= (long long)CG.nodes.size()) CG.add_node((long long)CG.nodes.size(), 0, 0, 0);

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
    if (depot_orig < 0) {
        cerr << "Invalid depot\n";
        return 2;
    }
    while (depot_orig >= (long long)CG.nodes.size()) CG.add_node((long long)CG.nodes.size(), 0, 0, 0);
    depot_idx = (int)depot_orig;
    CG.nodes[depot_idx].type = 1;

    double input_total_demand = 0.0;
    for (int customer : collections) {
        if (customer >= 0 && customer < (int)CG.nodes.size()) {
            input_total_demand += max(0.0, CG.nodes[customer].garbage_amount);
        }
    }
    const int capacity_trip_lower_bound = cfg.truck_capacity > 0.0
        ? max(1, (int)ceil(input_total_demand / cfg.truck_capacity - 1e-12))
        : 0;
    const int capacity_truck_lower_bound = !cfg.allow_multi_trip
        ? capacity_trip_lower_bound
        : (cfg.max_trips_per_truck > 0
            ? max(1, (capacity_trip_lower_bound + cfg.max_trips_per_truck - 1) /
                     cfg.max_trips_per_truck)
            : 1);
    const int early_lns_effective_workers =
        (int)collections.size() >= cfg.early_lns_parallel_min_customers
            ? max(1, cfg.sa_instances)
            : 1;

    // One canonical native receipt for the values that were actually parsed.
    // FleetRoute mirrors stderr verbatim, so this line proves the Python argv,
    // stdin fleet contract, and C++ configuration agree for every launch.
    cerr << "[SolverConfig]"
        << " input_nodes=" << N
        << " input_edges=" << M
        << " customer_records=" << G
        << " active_customer_nodes=" << collections.size()
        << " max_vehicles=" << cfg.num_trucks
        << " fleet_semantics=maximum_available_not_target"
        << " capacity=" << cfg.truck_capacity
        << " total_demand=" << input_total_demand
        << " capacity_lower_bound_trucks=" << capacity_truck_lower_bound
        << " instances=" << cfg.sa_instances
        << " stage_time_limit_s=" << cfg.sa_time_limit
        << " hard_time_limit_s=" << cfg.hard_time_limit_s
        << " no_improve_stop_s=" << cfg.no_improve_stop_s
        << " fill_time_budget=" << (cfg.fill_time_budget ? "true" : "false")
        << " use_early_throughput_lns=" << (cfg.use_early_throughput_lns ? "true" : "false")
        << " early_lns_fraction=" << cfg.early_lns_fraction
        << " early_lns_min_time_s=" << cfg.early_lns_min_time_s
        << " early_lns_max_time_s=" << cfg.early_lns_max_time_s
        << " early_lns_no_improve_s=" << cfg.early_lns_no_improve_s
        << " early_lns_destroy_ratio=" << cfg.early_lns_destroy_min_ratio
        << ".." << cfg.early_lns_destroy_max_ratio
        << " early_lns_parallel_min_customers="
        << cfg.early_lns_parallel_min_customers
        << " early_lns_effective_workers=" << early_lns_effective_workers
        << " use_time_window=" << (cfg.use_time_window ? "true" : "false")
        << " objective_mode=" << cfg.objective_mode
        << " metric=" << cfg.metric_mode
        << " sa_cooling=time_normalized"
        << " sa_alpha=" << cfg.sa_alpha
        << " sa_reference_steps=10000"
        << " sa_incumbent_warm_start="
        << (cfg.use_incumbent_sa_warm_start ? "true" : "false")
        << " sa_incumbent_portfolio_fraction="
        << cfg.sa_incumbent_portfolio_fraction
        << " relink_period=" << cfg.relink_period
        << " alns_destroy_operators=4"
        << " log_convergence=" << (cfg.log_convergence ? "true" : "false")
        << " convergence_csv=" << cfg.convergence_csv
        << " run_summary_csv=" << cfg.run_summary_csv
        << "\n";

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

    // ------------------------------------------------------------
    // Metric backend setup.
    // For euclidean mode, coordinates must be loaded after all nodes
    // have been created and after depot/customers have been marked.
    // ------------------------------------------------------------

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

        pm.precompute_from_source(depot_idx, collections);
        if (collections.size() <= 2000) {
            for (int s : collections) {
                pm.precompute_from_source(s, collections);
            }
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

    // Greedy baseline
    // Greedy / cluster warm-start baseline
    SolutionState greedy_state(cfg.num_trucks, (int)CG.nodes.size());

    cerr << "[main] cluster warm start check...\n";

    bool used_cluster_warm_start = build_cluster_warm_start_solution(
        greedy_state,
        collections,
        ev,
        pm
    );

    cerr << "[main] cluster warm start used=" << (used_cluster_warm_start ? 1 : 0) << "\n";

    string baseline_name = used_cluster_warm_start
        ? "ClusterWarmStart"
        : "Greedy";

    if (!used_cluster_warm_start) {
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

    } else {
        // Optional light cleanup after cluster start.
        for (auto &r : greedy_state.routes) {
            enforce_trip_separators(r, CG, depot_idx);
        }

        recompute_state_metrics_and_loads(greedy_state, ev);
    }

    if (cfg.use_savings_warm_start) {
        cerr << "[main] savings warm start check...\n";

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

        if (savings_ok) {
            cerr << " obj=" << savings_state.objective;
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
                    << " new=" << greedy_state.objective;
            }
        }

        cerr << "\n";
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

    update_global_best_checked(greedy_state, CG, pm);
    if (cfg.log_convergence) {
        lock_guard<mutex> lk(conv_mtx);
        shared_conv_log.push_back({
            solver_elapsed_seconds(), cfg.base_seed, 0, 0,
            greedy_state.objective, greedy_state.objective, 0.0,
            0, 0, 0, "baseline"
        });
    }

    cerr << "[Anytime] hard_time_limit_s=" << cfg.hard_time_limit_s
        << " no_improve_stop_s=" << cfg.no_improve_stop_s
        << " fill_time_budget=" << (cfg.fill_time_budget ? "true" : "false")
        << " target_objective=" << cfg.target_objective
        << " target_no_improve_stop_s=" << cfg.target_no_improve_stop_s
        << " meaningful_gain_abs=" << cfg.meaningful_gain_abs
        << " meaningful_gain_rel=" << cfg.meaningful_gain_rel
        << "\n";

    EarlyThroughputLnsResult early_lns_result;
    RunSummary early_lns_summary;
    SolutionState early_lns_state = greedy_state;
    vector<SolutionState> early_elite_states;

    if (!cfg.euclidean_hgs_only && cfg.use_early_throughput_lns) {
        // The prefix previously used one core regardless of --instances. Run
        // independent destroy/repair trajectories in parallel, then hand the
        // best hard-feasible result to the deep engine. Each trajectory has a
        // distinct seed and convergence stream; wall-clock budget is unchanged.
        const int early_workers = early_lns_effective_workers;
        vector<SolutionState> early_states(early_workers, greedy_state);
        vector<EarlyThroughputLnsResult> early_results(early_workers);
        vector<thread> early_threads;
        early_threads.reserve(early_workers);
        const auto early_portfolio_start = Clock::now();

        safe_log_line(
            "[EarlyLNSPortfolio] START workers=", early_workers,
            " instances=", cfg.sa_instances,
            " start_objective=", greedy_state.objective
        );

        if (early_workers == 1) {
            const unsigned long long worker_stream_id =
                convergence_stream_counter.fetch_add(1, memory_order_relaxed);
            // Preserve the original single-worker execution shape for medium
            // instances: no scheduler handoff, no coordination overhead.
            early_results[0] = run_early_throughput_lns(
                    early_states[0],
                    ev,
                    pm,
                    cfg.base_seed,
                    worker_stream_id,
                    &shared_conv_log,
                    &conv_mtx
            );
        } else {
            for (int worker = 0; worker < early_workers; ++worker) {
                const unsigned worker_seed = cfg.base_seed
                    + (unsigned)worker * 10007u;
                const unsigned long long worker_stream_id =
                    convergence_stream_counter.fetch_add(1, memory_order_relaxed);
                early_threads.emplace_back([&, worker, worker_seed, worker_stream_id]() {
                    early_results[worker] = run_early_throughput_lns(
                        early_states[worker],
                        ev,
                        pm,
                        worker_seed,
                        worker_stream_id,
                        &shared_conv_log,
                        &conv_mtx
                    );
                });
            }
            for (auto &worker_thread : early_threads) {
                if (worker_thread.joinable()) worker_thread.join();
            }
        }

        early_lns_result.start_objective = greedy_state.objective;
        early_lns_result.final_objective = greedy_state.objective;
        early_lns_result.stop_reason = "portfolio_complete";
        early_lns_result.elapsed_s = chrono::duration<double>(
            Clock::now() - early_portfolio_start
        ).count();
        bool found_early_handoff = false;
        for (int worker = 0; worker < early_workers; ++worker) {
            const auto &worker_result = early_results[worker];
            early_lns_result.ran = early_lns_result.ran || worker_result.ran;
            early_lns_result.requested_budget_s = max(
                early_lns_result.requested_budget_s,
                worker_result.requested_budget_s
            );
            early_lns_result.granted_budget_s = max(
                early_lns_result.granted_budget_s,
                worker_result.granted_budget_s
            );
            early_lns_result.productive_patience_s = max(
                early_lns_result.productive_patience_s,
                worker_result.productive_patience_s
            );
            early_lns_result.attempted_repairs += worker_result.attempted_repairs;
            early_lns_result.feasible_repairs += worker_result.feasible_repairs;
            early_lns_result.improving_repairs += worker_result.improving_repairs;
            early_lns_result.censored_late_repairs += worker_result.censored_late_repairs;

            if (!worker_result.handoff_feasible) continue;
            recompute_state_metrics_and_loads(early_states[worker], ev);
            if (!solution_hard_feasible(early_states[worker], CG, pm)) continue;
            const bool duplicate_routes = any_of(
                early_elite_states.begin(),
                early_elite_states.end(),
                [&](const SolutionState &elite) {
                    return elite.routes == early_states[worker].routes;
                }
            );
            if (!duplicate_routes) {
                early_elite_states.push_back(early_states[worker]);
            }
            if (!found_early_handoff ||
                early_states[worker].objective + 1e-9 < early_lns_state.objective) {
                early_lns_state = early_states[worker];
                found_early_handoff = true;
            }
        }
        early_lns_result.handoff_feasible = found_early_handoff;
        if (found_early_handoff) {
            sort(
                early_elite_states.begin(),
                early_elite_states.end(),
                [](const SolutionState &a, const SolutionState &b) {
                    return a.objective < b.objective;
                }
            );
            early_lns_result.final_objective = early_lns_state.objective;
            early_lns_result.improved =
                early_lns_state.objective + 1e-9 < greedy_state.objective;
            update_global_best_checked(early_lns_state, CG, pm);
        }

        safe_log_line(
            "[EarlyLNSPortfolio] END workers=", early_workers,
            " handoff_feasible=", (found_early_handoff ? "true" : "false"),
            " start_objective=", early_lns_result.start_objective,
            " final_objective=", early_lns_result.final_objective,
            " elapsed_s=", early_lns_result.elapsed_s,
            " attempted=", early_lns_result.attempted_repairs,
            " feasible=", early_lns_result.feasible_repairs,
            " improving=", early_lns_result.improving_repairs,
            " censored_late=", early_lns_result.censored_late_repairs
        );

        if (early_lns_result.ran && early_lns_result.handoff_feasible) {
            early_lns_summary = evaluate_state(early_lns_state, ev, CG);
            early_lns_summary.name = "EarlyThroughputLNS";
            early_lns_summary.runtime = early_lns_result.elapsed_s;
            early_lns_summary.iterations = (double)early_lns_result.attempted_repairs;
            early_lns_summary.accepted = early_lns_result.improving_repairs;
            early_lns_summary.attempted = early_lns_result.attempted_repairs;
        }
    }

    // SA variants
    auto run_sa_variant = [&](bool use_cross) -> RunSummary {
        int instances = max(1, cfg.sa_instances);
        vector<thread> threads;
        vector<AlgoResult> results(instances);
        mutex results_mtx;
        SolutionState launch_incumbent;
        const bool has_global_launch_incumbent =
            cfg.use_incumbent_sa_warm_start &&
            snapshot_global_best(launch_incumbent);
        vector<SolutionState> launch_pool;
        if (has_global_launch_incumbent) {
            launch_pool.push_back(launch_incumbent);
        }
        if (cfg.use_incumbent_sa_warm_start) {
            for (const auto &elite : early_elite_states) {
                if (!solution_hard_feasible(elite, CG, pm)) continue;
                const bool duplicate_routes = any_of(
                    launch_pool.begin(),
                    launch_pool.end(),
                    [&](const SolutionState &candidate) {
                        return candidate.routes == elite.routes;
                    }
                );
                if (!duplicate_routes) launch_pool.push_back(elite);
            }
        }
        const bool has_launch_incumbent = !launch_pool.empty();
        int warm_workers = 0;
        if (has_launch_incumbent) {
            warm_workers = max(
                1,
                (int)llround(
                    cfg.sa_incumbent_portfolio_fraction * (double)instances
                )
            );
            warm_workers = min(instances, warm_workers);
            // Keep one independent construction when there is enough parallel
            // capacity; the other workers exploit the incumbent.
            if (instances > 1) warm_workers = min(instances - 1, warm_workers);
        }

        safe_log_line(
            "[SAPortfolio] phase=", (use_cross ? "full" : "no_cross"),
            " workers=", instances,
            " incumbent_workers=", warm_workers,
            " cold_workers=", (instances - warm_workers),
            " incumbent_pool=", launch_pool.size(),
            " incumbent_objective=",
            (has_launch_incumbent ? launch_pool.front().objective : -1.0)
        );

        if (solver_should_stop()) {
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
            const bool use_warm =
                has_launch_incumbent && i >= instances - warm_workers;
            const int warm_slot = use_warm
                ? (i - (instances - warm_workers)) % (int)launch_pool.size()
                : -1;

            threads.emplace_back([&, i, seed, use_warm, warm_slot]() {
                AlgoResult r = sa_worker(
                    CG, pm, ev, depot_idx, collections,
                    seed,
                    cfg.sa_time_limit,
                    use_cross,
                    use_warm ? &launch_pool[warm_slot] : nullptr,
                    &shared_conv_log,
                    &conv_mtx
                );

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

        // Polish best feasible candidate from this variant.
        recompute_state_metrics_and_loads(best_r.best_state, ev);
        final_refinement_pass(best_r.best_state, ev, pm);
        recompute_state_metrics_and_loads(best_r.best_state, ev);

        if (!solution_hard_feasible(best_r.best_state, CG, pm)) {
            cerr << "[RUN INVALID] " << s.name
                << " obj=" << best_r.best_state.objective
                << " became infeasible after refinement\n";
            return s;
        }

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

    if (metric_is_euclidean() && cfg.euclidean_hgs_only) {
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
            int old_swapstar_rounds = cfg.euclidean_swapstar_rounds;
            int old_swapstar_scan_cap = cfg.euclidean_swapstar_scan_cap;

            cfg.euclidean_swapstar_rounds = min(old_swapstar_rounds, 10);
            cfg.euclidean_swapstar_scan_cap = min(old_swapstar_scan_cap, 80000);

            euclidean_swapstar_descent(hgs_only_state, ev, pm);

            cfg.euclidean_swapstar_rounds = old_swapstar_rounds;
            cfg.euclidean_swapstar_scan_cap = old_swapstar_scan_cap;
            recompute_state_metrics_and_loads(hgs_only_state, ev);
            if (cfg.euclidean_two_opt_star) {
                int old_two_opt_star_rounds = cfg.euclidean_two_opt_star_rounds;
                int old_two_opt_star_scan_cap = cfg.euclidean_two_opt_star_scan_cap;

                cfg.euclidean_two_opt_star_rounds = min(old_two_opt_star_rounds, 10);
                cfg.euclidean_two_opt_star_scan_cap = min(old_two_opt_star_scan_cap, 120000);

                euclidean_two_opt_star_descent(hgs_only_state, ev, pm);

                cfg.euclidean_two_opt_star_rounds = old_two_opt_star_rounds;
                cfg.euclidean_two_opt_star_scan_cap = old_two_opt_star_scan_cap;

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
            SolutionState stability_incumbent;
            const bool has_stability_incumbent =
                cfg.use_incumbent_sa_warm_start &&
                snapshot_global_best(stability_incumbent);

            AlgoResult r = sa_worker(
                CG,
                pm,
                ev,
                depot_idx,
                collections,
                seed,
                cfg.sa_time_limit,
                cfg.use_cross2,
                has_stability_incumbent ? &stability_incumbent : nullptr,
                &shared_conv_log,
                &conv_mtx
            );

            recompute_state_metrics_and_loads(r.best_state, ev);
            final_refinement_pass(r.best_state, ev, pm);
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
            early_lns_summary,
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

        if (!solver_should_stop()) {
            SolutionState final_incumbent;
            const bool has_final_incumbent =
                cfg.use_incumbent_sa_warm_start &&
                snapshot_global_best(final_incumbent);
            final_sa = sa_worker(
                CG,
                pm,
                ev,
                depot_idx,
                collections,
                cfg.base_seed + 99991,
                cfg.sa_time_limit,
                cfg.use_cross2,
                has_final_incumbent ? &final_incumbent : nullptr,
                &shared_conv_log,
                &conv_mtx
            );

            recompute_state_metrics_and_loads(final_sa.best_state, ev);
            final_refinement_pass(final_sa.best_state, ev, pm);
            recompute_state_metrics_and_loads(final_sa.best_state, ev);

            if (solution_hard_feasible(final_sa.best_state, CG, pm)) {
                update_global_best_checked(final_sa.best_state, CG, pm);
            }
            else {
                cerr << "[FINAL_SA INVALID] obj="
                    << final_sa.best_state.objective
                    << " ignored because infeasible\n";
            }
        }
    }

    // The historical pipeline is finite: with parallel workers it can naturally
    // finish far before a large hard_time_limit_s. FleetRoute exposes that value
    // as a real search budget, so use the otherwise idle tail for additional
    // deterministic multistart SA. This does not weaken feasibility checks and
    // does not fabricate progress; every slice performs actual solver work.
    if (cfg.fill_time_budget && cfg.hard_time_limit_s > 0.0 && !solver_should_stop()) {
        const double reserve_s = min(1.5, max(0.35, cfg.hard_time_limit_s * 0.005));
        int budget_restarts = 0;
        safe_log_line(
            "[BudgetFill] enabled budget_s=", cfg.hard_time_limit_s,
            " elapsed_s=", solver_elapsed_seconds(),
            " finalization_reserve_s=", reserve_s
        );

        while (!solver_should_stop()) {
            const double elapsed_now = solver_elapsed_seconds();
            const double usable = cfg.hard_time_limit_s - elapsed_now - reserve_s;
            if (usable <= 0.20) break;

            const double slice_s = max(0.20, min(cfg.sa_time_limit, usable));
            const int budget_workers = max(1, cfg.sa_instances);
            safe_log_line(
                "[BudgetFill] batch=", (budget_restarts + 1),
                " workers=", budget_workers,
                " slice_s=", slice_s,
                " remaining_s=", max(0.0, cfg.hard_time_limit_s - elapsed_now)
            );

            // Preserve the solver's normal parallel-search semantics while using
            // the remaining wall-clock budget. A 6-instance profile therefore
            // keeps six independent multistarts active instead of idling five
            // cores during the budget-fill tail.
            vector<thread> budget_threads;
            budget_threads.reserve(budget_workers);
            SolutionState budget_incumbent;
            const bool has_global_budget_incumbent =
                cfg.use_incumbent_sa_warm_start &&
                snapshot_global_best(budget_incumbent);
            vector<SolutionState> budget_launch_pool;
            if (has_global_budget_incumbent) {
                budget_launch_pool.push_back(budget_incumbent);
            }
            if (cfg.use_incumbent_sa_warm_start) {
                for (const auto &elite : early_elite_states) {
                    if (!solution_hard_feasible(elite, CG, pm)) continue;
                    const bool duplicate_routes = any_of(
                        budget_launch_pool.begin(),
                        budget_launch_pool.end(),
                        [&](const SolutionState &candidate) {
                            return candidate.routes == elite.routes;
                        }
                    );
                    if (!duplicate_routes) budget_launch_pool.push_back(elite);
                }
            }
            int budget_warm_workers = 0;
            if (!budget_launch_pool.empty()) {
                budget_warm_workers = max(
                    1,
                    (int)llround(
                        cfg.sa_incumbent_portfolio_fraction *
                        (double)budget_workers
                    )
                );
                budget_warm_workers = min(budget_workers, budget_warm_workers);
                if (budget_workers > 1) {
                    budget_warm_workers = min(
                        budget_workers - 1,
                        budget_warm_workers
                    );
                }
            }
            safe_log_line(
                "[BudgetFillPortfolio] batch=", (budget_restarts + 1),
                " workers=", budget_workers,
                " incumbent_workers=", budget_warm_workers,
                " cold_workers=", (budget_workers - budget_warm_workers),
                " incumbent_pool=", budget_launch_pool.size()
            );
            for (int worker = 0; worker < budget_workers && !solver_should_stop(); ++worker) {
                const unsigned restart_seed = cfg.base_seed + 2000003u
                    + (unsigned)budget_restarts * 104729u
                    + (unsigned)worker * 10007u;
                const bool use_warm =
                    !budget_launch_pool.empty() &&
                    worker >= budget_workers - budget_warm_workers;
                const int warm_slot = use_warm
                    ? (worker - (budget_workers - budget_warm_workers)) %
                        (int)budget_launch_pool.size()
                    : -1;
                budget_threads.emplace_back([
                    &, worker, restart_seed, slice_s, use_warm, warm_slot
                ]() {
                    AlgoResult extra = sa_worker(
                        CG, pm, ev, depot_idx, collections, restart_seed, slice_s,
                        cfg.use_cross2,
                        use_warm ? &budget_launch_pool[warm_slot] : nullptr,
                        &shared_conv_log, &conv_mtx
                    );
                    recompute_state_metrics_and_loads(extra.best_state, ev);
                    if (solution_hard_feasible(extra.best_state, CG, pm)) {
                        update_global_best_checked(extra.best_state, CG, pm);
                    } else {
                        safe_log_line(
                            "[BudgetFill] batch=", (budget_restarts + 1),
                            " worker=", worker,
                            " discarded_infeasible objective=", extra.best_state.objective
                        );
                    }
                });
            }
            for (auto &th : budget_threads) {
                if (th.joinable()) th.join();
            }
            ++budget_restarts;
            solver_live_telemetry("budget-fill", INF_D, -1);
        }

        safe_log_line(
            "[BudgetFill] complete restarts=", budget_restarts,
            " elapsed_s=", solver_elapsed_seconds(),
            " budget_s=", cfg.hard_time_limit_s
        );
    }

    SolutionState best_state;

    take_if_better_feasible(best_state, greedy_state, ev, pm);

    if (!global_best_state.routes.empty()) {
        take_if_better_feasible(best_state, global_best_state, ev, pm);
    }

    take_if_better_feasible(best_state, final_sa.best_state, ev, pm);

    if (best_state.routes.empty()) {
        cerr << "[FINAL_SELECT] no hard-feasible candidate exists\n";
        return 2;
    }

    recompute_state_metrics_and_loads(best_state, ev);

    if (cfg.use_granular_tabu && !solver_should_stop()) {
        recompute_state_metrics_and_loads(best_state, ev);

        double before_gt = best_state.objective;
        SolutionState before_gt_state = best_state;

        SolutionState gt_cand = best_state;
        granular_tabu_repair(gt_cand, ev, pm);

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

    SolutionState pre_output_polish_state = best_state;

    if (cfg.use_route_pair_diag) {
        print_route_pair_diagnostics(best_state, ev, pm);
        print_route_pair_boundary_customers(best_state, ev, pm, 8);
    }

    if (cfg.use_route_region_lns && !solver_should_stop()) {
        SolutionState cand = best_state;
        route_region_lns_descent(cand, ev, pm);
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
        boundary_pair_lns_descent(cand, ev, pm);
        accept_improving_hard_candidate(best_state, std::move(cand), ev, pm, "BoundaryPairLNS-Final");

        if (cfg.use_route_pair_diag) {
            cerr << "[BoundaryPairLNS] post-lns objective="
                << best_state.objective << "\n";
        }
    }
    if (metric_is_euclidean() && cfg.euclidean_swapstar && !cfg.euclidean_hgs_only) {
        cerr << "[SWAP*] final pre-output start obj="
            << best_state.objective << "\n";

        euclidean_swapstar_descent(best_state, ev, pm);
        recompute_state_metrics_and_loads(best_state, ev);

        cerr << "[SWAP*] final pre-output end obj="
            << best_state.objective << "\n";
    }

    if (metric_is_euclidean() && cfg.euclidean_two_opt_star && !cfg.euclidean_hgs_only) {
        cerr << "[2-opt*] final pre-output start obj="
            << best_state.objective << "\n";

        euclidean_two_opt_star_descent(best_state, ev, pm);
        recompute_state_metrics_and_loads(best_state, ev);

        cerr << "[2-opt*] final pre-output end obj="
            << best_state.objective << "\n";
    }

    if (metric_is_euclidean() && cfg.euclidean_deep_interroute && !cfg.euclidean_hgs_only) {
        cerr << "[euclidean-deep] final pre-output polish start obj="
            << best_state.objective << "\n";

        euclidean_deep_interroute_descent(best_state, ev, pm);

        cerr << "[euclidean-deep] final pre-output polish end obj="
            << best_state.objective << "\n";
    }

    if (metric_is_euclidean() && cfg.use_hgs_lite && !cfg.euclidean_hgs_only) {
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

    if (cfg.log_convergence) {
        {
            lock_guard<mutex> lk(conv_mtx);
            shared_conv_log.push_back({
                solver_elapsed_seconds(), cfg.base_seed, 0, 0,
                best_state.objective, best_state.objective, 0.0,
                0, 0, 0, "final_selected"
            });
            stable_sort(shared_conv_log.begin(), shared_conv_log.end(),
                [](const ConvergenceLogRow &a, const ConvergenceLogRow &b) {
                    return a.time_s < b.time_s;
                });
        }
        ofstream out(cfg.convergence_csv);

        if (out.is_open()) {
            // best_obj is the worker-local best for diagnostics. global_best_obj
            // is the actual monotone process-wide best-so-far used by the primary
            // convergence plot. Never connect current_obj across worker streams.
            out << "time_s,seed,stream_id,iter,current_obj,best_obj,global_best_obj,temp,"
                << "accepted_moves,attempted_moves,acceptance_rate,stagnation,event\n";

            double running_global_best = INF_D;
            for (const auto &r : shared_conv_log) {
                if (isfinite(r.best_obj)) running_global_best = min(running_global_best, r.best_obj);
                double acceptance_rate =
                    r.attempted_moves > 0
                    ? (double)r.accepted_moves / (double)r.attempted_moves
                    : 0.0;

                out << fixed << setprecision(6)
                    << r.time_s << ","
                    << r.seed << ","
                    << r.stream_id << ","
                    << r.iter << ","
                    << r.current_obj << ","
                    << r.best_obj << ","
                    << running_global_best << ","
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
