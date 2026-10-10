#include <bits/stdc++.h>
 using namespace std;

 /*
 ================================================================================
 cluster.cpp v4 — paper-faithful road-aware clustering warm-start generator
 ================================================================================

 Purpose:
     External clustering warm-start generator.
     Reads solver input.txt and optional dataset.json.
     Writes clusters.csv for solver.cpp.

 Input format:
     N M
     K
     depot
     M lines: u v length_m speed_kph
     Gcust
     customer lines: node demand service earliest latest
     capacity

 Outputs:
     clusters.csv:
         node,cluster

     cluster_summary.csv:
         per-cluster load/centroid plus requested/effective method and timings

     cluster_timing.csv:
         one row with preprocessing, method, repair, polish, write, and total time

 Modes:
     round_robin
         Demand-balanced fallback.

     sweep
         Angular sweep around depot using coordinates.

     balanced_kmeans / kmeans
         Capacity-aware coordinate K-means.

     kd_split
         Recursive spatial KD split.

     spatial_grid
         Grid-bucket spatial clustering.

     spectral_lite
         Coordinate spectral-lite using dense Jacobi eigen decomposition.

     road_savings
         Paper-faithful directed parallel Clarke-Wright Savings: singleton
         routes, directed end-to-start savings, hard capacity/TW checks,
         perturbed variants, best-feasible selection, and light relocate polish.

     network_kmedoids
         Road-cost K-medoids using shortest path travel-time/distance matrix.

     route_split
         Road-nearest giant tour, then capacity split.

     road_spectral_lite
         Existing dense road-cost KNN + dense normalized Laplacian + Jacobi mode.

     road_spectral_sparse / sparse_road_spectral
         Paper-faithful Sparse Road-aware Spectral Clustering:
         projected-coordinate KD-tree k-NN candidates, symmetric road
         dissimilarity, self-tuning sparse affinity, sparse normalized
         Laplacian, iterative Lanczos eigensolver, row-normalized embedding,
         capacity-aware k-means, overload repair, and road assignment polish.

     auto
         road_savings if road matrix works, else sweep if coords exist, else round_robin.

 Road cost:
     --road_cost time
     --road_cost distance

 Example:
     g++ -O2 -std=c++17 cluster.cpp -o cluster

     ./cluster \
     --mode road_savings \
     --road_cost time \
     --input input.txt \
     --dataset dataset.json \
     --out clusters.csv \
     --summary cluster_summary.csv \
     --timing cluster_timing.csv \
     --seed 42 \
     --iters 100 \
     --spectral_neighbors 8 \
     --spectral_sigma_rank 8 \
     --spectral_lanczos_dim 0 \
     --spectral_eig_tol 1e-8 \
     --savings_variants 8 \
     --savings_noise 0.025 \
     --savings_light_polish_rounds 2 \
     --savings_polish_time_s 0.50
 ================================================================================
 */

 static const double INF_D = 1e100;
 static const double PI = acos(-1.0);

 struct Edge {
     int u = 0;
     int v = 0;
     double length_m = 0.0;
     double speed_kph = 0.0;
 };

 struct Customer {
     int node = -1;
     double demand = 0.0;
     double service = 0.0;
     double earliest = 0.0;
     double latest = 0.0;

     double lon = 0.0;
     double lat = 0.0;
     bool has_xy = false;
 };

 struct InputData {
     int N = 0;
     int M = 0;
     int K = 0;
     int depot = 0;
     double capacity = 0.0;

     vector<Edge> edges;
     vector<Customer> customers;
 };

 struct RoadMatrix {
     bool built = false;
     string cost_mode = "time";

     vector<double> depot_to;
     vector<double> customer_to_depot;
     vector<vector<double>> cc;
 };

 struct SpectralDiagnostics {
     int k_eff = 0;
     int candidate_arcs = 0;
     int sparse_edges = 0;
     int lanczos_dimension = 0;
     int lanczos_steps = 0;
     bool eig_converged = false;
     bool fallback_used = false;
     double eig_max_residual = 0.0;
     double median_local_scale = 0.0;
 };

 struct TimingReport {
     string requested_mode;
     string effective_mode;
     string road_cost_mode;

     double parse_s = 0.0;
     double coordinate_s = 0.0;
     double road_matrix_s = 0.0;
     double method_s = 0.0;
     double repair_s = 0.0;
     double polish_s = 0.0;
     double write_s = 0.0;
     double total_s = 0.0;
 };

 /* ---------------- Basic utils ---------------- */

 static double sqr(double x) {
     return x * x;
 }

 static string read_file(const string &path) {
     ifstream in(path);
     if (!in.good()) return "";

     stringstream ss;
     ss << in.rdbuf();

     return ss.str();
 }

 static string lower_copy(string s) {
     for (char &c : s) {
         c = (char)tolower((unsigned char)c);
     }
     return s;
 }

 static string get_arg(int argc, char **argv, const string &key, const string &def) {
     for (int i = 1; i + 1 < argc; ++i) {
         if (string(argv[i]) == key) {
             return argv[i + 1];
         }
     }

     return def;
 }

 static double edge_time_s(const Edge &e) {
     double speed_ms = max(0.1, e.speed_kph * 1000.0 / 3600.0);
     return e.length_m / speed_ms;
 }

 static double edge_cost(const Edge &e, const string &mode) {
     if (mode == "distance") return e.length_m;
     return edge_time_s(e);
 }

 using SteadyClock = chrono::steady_clock;

 static double seconds_between(
     const SteadyClock::time_point &a,
     const SteadyClock::time_point &b
 ) {
     return chrono::duration<double>(b - a).count();
 }

 static uint64_t undirected_pair_key(int a, int b) {
     if (a > b) swap(a, b);
     return (uint64_t)(uint32_t)a << 32 | (uint32_t)b;
 }

 /* ---------------- input.txt parsing ---------------- */

 static InputData parse_input_txt(const string &path) {
     ifstream in(path);

     if (!in.good()) {
         throw runtime_error("Could not open input file: " + path);
     }

     InputData d;

     in >> d.N >> d.M;
     in >> d.K;
     in >> d.depot;

     if (!in.good()) {
         throw runtime_error("Failed reading N M K depot");
     }

     d.edges.reserve(d.M);

     for (int i = 0; i < d.M; ++i) {
         Edge e;
         in >> e.u >> e.v >> e.length_m >> e.speed_kph;

         if (!in.good()) {
             throw runtime_error("Failed reading edge line " + to_string(i));
         }

         if (e.u < 0 || e.u >= d.N || e.v < 0 || e.v >= d.N) {
             throw runtime_error("Bad edge endpoint at line " + to_string(i));
         }

         if (e.length_m <= 0.0 || e.speed_kph <= 0.0) {
             throw runtime_error("Bad edge length/speed at line " + to_string(i));
         }

         d.edges.push_back(e);
     }

     int Gcust = 0;
     in >> Gcust;

     if (!in.good()) {
         throw runtime_error("Failed reading customer count");
     }

     d.customers.reserve(Gcust);

     for (int i = 0; i < Gcust; ++i) {
         Customer c;
         in >> c.node >> c.demand >> c.service >> c.earliest >> c.latest;

         if (!in.good()) {
             throw runtime_error("Failed reading customer line " + to_string(i));
         }

         if (c.node < 0 || c.node >= d.N) {
             throw runtime_error("Bad customer node at line " + to_string(i));
         }

         if (c.demand <= 0.0) {
             throw runtime_error("Bad customer demand at line " + to_string(i));
         }

         d.customers.push_back(c);
     }

     in >> d.capacity;

     if (!in.good()) {
         throw runtime_error("Failed reading capacity");
     }

     if (d.K <= 0) {
         throw runtime_error("K must be positive");
     }

     if (d.capacity <= 0.0) {
         throw runtime_error("capacity must be positive");
     }

     return d;
 }

 /* ---------------- dataset.json coordinate parsing ---------------- */

 static unordered_map<int, pair<double,double>> parse_dataset_coords(const string &path) {
     unordered_map<int, pair<double,double>> coords;

     string s = read_file(path);
     if (s.empty()) return coords;

     regex node_re(
         R"("id"\s*:\s*([0-9]+)\s*,\s*"osm_id"\s*:\s*-?[0-9]+\s*,\s*"lon"\s*:\s*([-+0-9.eE]+)\s*,\s*"lat"\s*:\s*([-+0-9.eE]+))"
     );

     auto begin = sregex_iterator(s.begin(), s.end(), node_re);
     auto end = sregex_iterator();

     for (auto it = begin; it != end; ++it) {
         int id = stoi((*it)[1].str());
         double lon = stod((*it)[2].str());
         double lat = stod((*it)[3].str());

         coords[id] = {lon, lat};
     }

     return coords;
 }

 static void attach_coords(
     InputData &d,
     const unordered_map<int, pair<double,double>> &coords
 ) {
     for (auto &c : d.customers) {
         auto it = coords.find(c.node);

         if (it != coords.end()) {
             c.lon = it->second.first;
             c.lat = it->second.second;
             c.has_xy = true;
         }
     }
 }

 static bool all_customers_have_coords(
     const InputData &d,
     const unordered_map<int, pair<double,double>> &coords
 ) {
     if (!coords.count(d.depot)) return false;

     for (const auto &c : d.customers) {
         if (!coords.count(c.node)) return false;
     }

     return true;
 }

 static pair<double,double> get_depot_xy(
     const InputData &d,
     const unordered_map<int, pair<double,double>> &coords
 ) {
     auto it = coords.find(d.depot);

     if (it == coords.end()) {
         return {0.0, 0.0};
     }

     return it->second;
 }

 /* ---------------- Road shortest-path matrix ---------------- */

 static vector<double> dijkstra_all(
     int source,
     const InputData &d,
     const vector<vector<pair<int,double>>> &adj
 ) {
     vector<double> dist(d.N, INF_D);

     priority_queue<
         pair<double,int>,
         vector<pair<double,int>>,
         greater<pair<double,int>>
     > pq;

     dist[source] = 0.0;
     pq.push({0.0, source});

     while (!pq.empty()) {
         auto [du, u] = pq.top();
         pq.pop();

         if (du > dist[u] + 1e-12) continue;

         for (auto [v, w] : adj[u]) {
             double nd = du + w;

             if (nd + 1e-12 < dist[v]) {
                 dist[v] = nd;
                 pq.push({nd, v});
             }
         }
     }

     return dist;
 }

 static RoadMatrix build_road_matrix(
     const InputData &d,
     const string &cost_mode
 ) {
     RoadMatrix rm;
     rm.cost_mode = cost_mode;

     int C = (int)d.customers.size();

     rm.depot_to.assign(C, INF_D);
     rm.customer_to_depot.assign(C, INF_D);
     rm.cc.assign(C, vector<double>(C, INF_D));

     vector<vector<pair<int,double>>> adj(d.N);

     for (const auto &e : d.edges) {
         adj[e.u].push_back({e.v, edge_cost(e, cost_mode)});
     }

     vector<int> sources;
     sources.reserve(C + 1);
     sources.push_back(d.depot);

     for (const auto &c : d.customers) {
         sources.push_back(c.node);
     }

     vector<vector<double>> all_dist;
     all_dist.reserve(C + 1);

     for (int s : sources) {
         all_dist.push_back(dijkstra_all(s, d, adj));
     }

     for (int i = 0; i < C; ++i) {
         int node_i = d.customers[i].node;
         rm.depot_to[i] = all_dist[0][node_i];
     }

     for (int i = 0; i < C; ++i) {
         int src_row = i + 1;

         rm.customer_to_depot[i] = all_dist[src_row][d.depot];

         for (int j = 0; j < C; ++j) {
             int node_j = d.customers[j].node;
             rm.cc[i][j] = all_dist[src_row][node_j];
         }
     }

     bool ok = true;

     for (int i = 0; i < C; ++i) {
         if (!isfinite(rm.depot_to[i]) || rm.depot_to[i] >= INF_D / 2) ok = false;
         if (!isfinite(rm.customer_to_depot[i]) || rm.customer_to_depot[i] >= INF_D / 2) ok = false;

         for (int j = 0; j < C; ++j) {
             if (!isfinite(rm.cc[i][j]) || rm.cc[i][j] >= INF_D / 2) {
                 ok = false;
             }
         }
     }

     rm.built = ok;

     return rm;
 }

 static double sym_road_cost(const RoadMatrix &rm, int i, int j) {
     if (i == j) return 0.0;

     double a = rm.cc[i][j];
     double b = rm.cc[j][i];

     if (a >= INF_D / 2 && b >= INF_D / 2) return INF_D;
     if (a >= INF_D / 2) return b;
     if (b >= INF_D / 2) return a;

     return 0.5 * (a + b);
 }

 /* ---------------- Assignment utilities ---------------- */

 static void ensure_valid_assignments(const InputData &d, vector<int> &assign) {
     int C = (int)d.customers.size();

     if ((int)assign.size() != C) {
         assign.assign(C, 0);
     }

     for (int &x : assign) {
         if (x < 0 || x >= d.K) {
             x = 0;
         }
     }
 }

 static vector<double> cluster_loads(const InputData &d, const vector<int> &assign) {
     vector<double> load(d.K, 0.0);

     for (int i = 0; i < (int)d.customers.size(); ++i) {
         int k = assign[i];

         if (0 <= k && k < d.K) {
             load[k] += d.customers[i].demand;
         }
     }

     return load;
 }

 static vector<vector<int>> cluster_members(
     const InputData &d,
     const vector<int> &assign
 ) {
     vector<vector<int>> members(d.K);

     for (int i = 0; i < (int)d.customers.size(); ++i) {
         int k = assign[i];

         if (0 <= k && k < d.K) {
             members[k].push_back(i);
         }
     }

     return members;
 }

 static double cluster_medoid_cost(
     const InputData &d,
     const RoadMatrix &rm,
     const vector<int> &members,
     int cand
 ) {
     (void)d;

     if (members.empty()) return 0.0;

     double cost = 0.0;

     for (int x : members) {
         if (x == cand) continue;
         cost += sym_road_cost(rm, cand, x);
     }

     return cost;
 }

 static vector<int> compute_cluster_medoids(
     const InputData &d,
     const RoadMatrix &rm,
     const vector<int> &assign
 ) {
     vector<vector<int>> members = cluster_members(d, assign);
     vector<int> medoid(d.K, -1);

     for (int k = 0; k < d.K; ++k) {
         if (members[k].empty()) continue;

         int best = members[k][0];
         double best_cost = INF_D;

         for (int cand : members[k]) {
             double cost = cluster_medoid_cost(d, rm, members[k], cand);

             if (cost < best_cost) {
                 best_cost = cost;
                 best = cand;
             }
         }

         medoid[k] = best;
     }

     return medoid;
 }

 static void repair_overloaded_clusters(
     const InputData &d,
     const RoadMatrix &rm,
     vector<int> &assign
 ) {
     ensure_valid_assignments(d, assign);

     vector<double> load = cluster_loads(d, assign);

     bool changed = true;
     int guard = 0;

     while (changed && guard++ < 10000) {
         changed = false;

         int over_k = -1;
         double over_amt = 0.0;

         for (int k = 0; k < d.K; ++k) {
             double ov = load[k] - d.capacity;

             if (ov > over_amt) {
                 over_amt = ov;
                 over_k = k;
             }
         }

         if (over_k == -1 || over_amt <= 1e-9) break;

         vector<int> medoids;
         if (rm.built) {
             medoids = compute_cluster_medoids(d, rm, assign);
         }

         int best_node = -1;
         int best_to = -1;
         double best_penalty = INF_D;

         for (int i = 0; i < (int)d.customers.size(); ++i) {
             if (assign[i] != over_k) continue;

             for (int k = 0; k < d.K; ++k) {
                 if (k == over_k) continue;

                 if (load[k] + d.customers[i].demand > d.capacity + 1e-9) {
                     continue;
                 }

                 double penalty = load[k];

                 if (rm.built) {
                     if (medoids[k] != -1) {
                         penalty = sym_road_cost(rm, i, medoids[k]);
                     } else {
                         penalty = min(rm.depot_to[i], rm.customer_to_depot[i]);
                     }
                 }

                 if (penalty < best_penalty) {
                     best_penalty = penalty;
                     best_node = i;
                     best_to = k;
                 }
             }
         }

         if (best_node == -1) {
             break;
         }

         int old = assign[best_node];

         assign[best_node] = best_to;

         load[old] -= d.customers[best_node].demand;
         load[best_to] += d.customers[best_node].demand;

         changed = true;
     }
 }

 static void road_assignment_polish(
     const InputData &d,
     const RoadMatrix &rm,
     vector<int> &assign,
     int rounds = 3
 ) {
     if (!rm.built) return;

     ensure_valid_assignments(d, assign);

     int C = (int)d.customers.size();
     if (C == 0) return;

     for (int round = 0; round < rounds; ++round) {
         bool changed = false;

         vector<double> load = cluster_loads(d, assign);
         vector<int> medoid = compute_cluster_medoids(d, rm, assign);

         vector<int> order(C);
         iota(order.begin(), order.end(), 0);

         sort(order.begin(), order.end(), [&](int a, int b) {
             if (fabs(d.customers[a].demand - d.customers[b].demand) > 1e-12) {
                 return d.customers[a].demand > d.customers[b].demand;
             }
             return d.customers[a].node < d.customers[b].node;
         });

         for (int idx : order) {
             int old_k = assign[idx];

             if (old_k < 0 || old_k >= d.K) continue;

             double old_score = INF_D;

             if (medoid[old_k] != -1) {
                 old_score = sym_road_cost(rm, idx, medoid[old_k]);
             }

             int best_k = old_k;
             double best_score = old_score;

             for (int k = 0; k < d.K; ++k) {
                 if (k == old_k) continue;

                 if (load[k] + d.customers[idx].demand > d.capacity + 1e-9) {
                     continue;
                 }

                 double score;

                 if (medoid[k] == -1) {
                     score = min(rm.depot_to[idx], rm.customer_to_depot[idx]);
                 } else {
                     score = sym_road_cost(rm, idx, medoid[k]);
                 }

                 double load_pressure = load[k] / max(1e-9, d.capacity);
                 score *= (1.0 + 0.10 * load_pressure);

                 if (score + 1e-9 < best_score * 0.97) {
                     best_score = score;
                     best_k = k;
                 }
             }

             if (best_k != old_k) {
                 load[old_k] -= d.customers[idx].demand;
                 load[best_k] += d.customers[idx].demand;
                 assign[idx] = best_k;
                 changed = true;
             }
         }

         if (!changed) break;
     }
 }

 /* ---------------- Mode 1: round_robin ---------------- */

 static vector<int> round_robin_cluster(const InputData &d) {
     int C = (int)d.customers.size();

     vector<int> assign(C, 0);
     vector<int> order(C);

     iota(order.begin(), order.end(), 0);

     sort(order.begin(), order.end(), [&](int a, int b) {
         if (fabs(d.customers[a].demand - d.customers[b].demand) > 1e-12) {
             return d.customers[a].demand > d.customers[b].demand;
         }

         return d.customers[a].node < d.customers[b].node;
     });

     vector<double> load(d.K, 0.0);

     for (int idx : order) {
         int best = 0;

         for (int k = 1; k < d.K; ++k) {
             if (load[k] < load[best]) {
                 best = k;
             }
         }

         assign[idx] = best;
         load[best] += d.customers[idx].demand;
     }

     return assign;
 }

 /* ---------------- Mode 2: sweep ---------------- */

 static vector<int> sweep_cluster(
     const InputData &d,
     const unordered_map<int, pair<double,double>> &coords
 ) {
     int C = (int)d.customers.size();

     vector<int> assign(C, 0);

     auto depot_xy = get_depot_xy(d, coords);
     double depot_lon = depot_xy.first;
     double depot_lat = depot_xy.second;

     struct Item {
         int idx = 0;
         double angle = 0.0;
         double dist2 = 0.0;
         double demand = 0.0;
     };

     vector<Item> items;
     items.reserve(C);

     for (int i = 0; i < C; ++i) {
         const auto &c = d.customers[i];

         double dx = c.lon - depot_lon;
         double dy = c.lat - depot_lat;

         double angle = atan2(dy, dx);
         if (angle < 0) angle += 2.0 * PI;

         items.push_back({
             i,
             angle,
             dx * dx + dy * dy,
             c.demand
         });
     }

     sort(items.begin(), items.end(), [](const Item &a, const Item &b) {
         if (fabs(a.angle - b.angle) > 1e-12) return a.angle < b.angle;
         return a.dist2 < b.dist2;
     });

     double total_demand = 0.0;
     for (const auto &c : d.customers) total_demand += c.demand;

     double target_load = total_demand / max(1, d.K);
     double soft_limit = min(d.capacity, target_load * 1.15);

     int cluster = 0;
     double load = 0.0;

     for (const auto &it : items) {
         bool advance =
             cluster < d.K - 1 &&
             load > 0.0 &&
             (
                 load + it.demand > d.capacity + 1e-9 ||
                 load + it.demand > soft_limit + 1e-9
             );

         if (advance) {
             cluster++;
             load = 0.0;
         }

         assign[it.idx] = cluster;
         load += it.demand;
     }

     return assign;
 }

 /* ---------------- Geometry K-means helpers ---------------- */

 static void recompute_xy_centers(
     const InputData &d,
     const vector<int> &assign,
     vector<double> &cx,
     vector<double> &cy
 ) {
     int C = (int)d.customers.size();

     cx.assign(d.K, 0.0);
     cy.assign(d.K, 0.0);

     vector<double> cnt(d.K, 0.0);

     for (int i = 0; i < C; ++i) {
         int k = max(0, min(d.K - 1, assign[i]));

         cx[k] += d.customers[i].lon;
         cy[k] += d.customers[i].lat;
         cnt[k] += 1.0;
     }

     for (int k = 0; k < d.K; ++k) {
         if (cnt[k] > 0.0) {
             cx[k] /= cnt[k];
             cy[k] /= cnt[k];
         } else if (C > 0) {
             int idx = k % C;
             cx[k] = d.customers[idx].lon;
             cy[k] = d.customers[idx].lat;
         }
     }
 }

 /* ---------------- Mode 3: balanced_kmeans ---------------- */

 static vector<int> balanced_kmeans_cluster(
     const InputData &d,
     const unordered_map<int, pair<double,double>> &coords,
     int iters,
     unsigned seed
 ) {
     (void)seed;

     int C = (int)d.customers.size();

     vector<int> assign(C, 0);
     if (C == 0) return assign;

     assign = sweep_cluster(d, coords);

     vector<double> cx, cy;
     recompute_xy_centers(d, assign, cx, cy);

     for (int iter = 0; iter < iters; ++iter) {
         vector<int> order(C);
         iota(order.begin(), order.end(), 0);

         sort(order.begin(), order.end(), [&](int a, int b) {
             if (fabs(d.customers[a].demand - d.customers[b].demand) > 1e-12) {
                 return d.customers[a].demand > d.customers[b].demand;
             }

             return d.customers[a].node < d.customers[b].node;
         });

         vector<int> next_assign(C, 0);
         vector<double> load(d.K, 0.0);

         for (int idx : order) {
             vector<pair<double,int>> pref;

             for (int k = 0; k < d.K; ++k) {
                 double dd = sqr(d.customers[idx].lon - cx[k])
                         + sqr(d.customers[idx].lat - cy[k]);

                 double load_pressure = load[k] / max(1e-9, d.capacity);
                 double score = dd * (1.0 + 0.35 * load_pressure);

                 pref.push_back({score, k});
             }

             sort(pref.begin(), pref.end());

             int chosen = pref[0].second;

             for (auto [score, k] : pref) {
                 if (load[k] + d.customers[idx].demand <= d.capacity + 1e-9) {
                     chosen = k;
                     break;
                 }
             }

             next_assign[idx] = chosen;
             load[chosen] += d.customers[idx].demand;
         }

         bool changed = (next_assign != assign);
         assign.swap(next_assign);
         recompute_xy_centers(d, assign, cx, cy);

         if (!changed) break;
     }

     return assign;
 }

 /* ---------------- Mode 4: kd_split ---------------- */

 static vector<int> kd_split_cluster(
     const InputData &d,
     const unordered_map<int, pair<double,double>> &coords
 ) {
     (void)coords;

     int C = (int)d.customers.size();

     vector<int> assign(C, 0);
     if (C == 0) return assign;

     vector<vector<int>> groups(1);

     for (int i = 0; i < C; ++i) {
         groups[0].push_back(i);
     }

     auto group_load = [&](const vector<int> &g) {
         double load = 0.0;
         for (int idx : g) load += d.customers[idx].demand;
         return load;
     };

     auto group_score = [&](const vector<int> &g) {
         if ((int)g.size() <= 1) return -1.0;

         double min_lon = 1e100, max_lon = -1e100;
         double min_lat = 1e100, max_lat = -1e100;
         double load = 0.0;

         for (int idx : g) {
             const auto &c = d.customers[idx];

             min_lon = min(min_lon, c.lon);
             max_lon = max(max_lon, c.lon);
             min_lat = min(min_lat, c.lat);
             max_lat = max(max_lat, c.lat);
             load += c.demand;
         }

         double spread = max(max_lon - min_lon, max_lat - min_lat);

         return spread * (1.0 + load / max(1.0, d.capacity));
     };

     while ((int)groups.size() < d.K) {
         int best_g = -1;
         double best_score = -1.0;

         for (int i = 0; i < (int)groups.size(); ++i) {
             double sc = group_score(groups[i]);

             if (sc > best_score) {
                 best_score = sc;
                 best_g = i;
             }
         }

         if (best_g == -1 || best_score <= 0.0) break;

         vector<int> g = groups[best_g];

         double min_lon = 1e100, max_lon = -1e100;
         double min_lat = 1e100, max_lat = -1e100;

         for (int idx : g) {
             const auto &c = d.customers[idx];

             min_lon = min(min_lon, c.lon);
             max_lon = max(max_lon, c.lon);
             min_lat = min(min_lat, c.lat);
             max_lat = max(max_lat, c.lat);
         }

         bool split_lon = (max_lon - min_lon) >= (max_lat - min_lat);

         sort(g.begin(), g.end(), [&](int a, int b) {
             if (split_lon) {
                 if (fabs(d.customers[a].lon - d.customers[b].lon) > 1e-12) {
                     return d.customers[a].lon < d.customers[b].lon;
                 }

                 return d.customers[a].lat < d.customers[b].lat;
             } else {
                 if (fabs(d.customers[a].lat - d.customers[b].lat) > 1e-12) {
                     return d.customers[a].lat < d.customers[b].lat;
                 }

                 return d.customers[a].lon < d.customers[b].lon;
             }
         });

         double total_load = group_load(g);
         double half = total_load * 0.5;

         double acc = 0.0;
         int cut = 1;

         for (int i = 0; i + 1 < (int)g.size(); ++i) {
             acc += d.customers[g[i]].demand;

             if (acc >= half) {
                 cut = i + 1;
                 break;
             }
         }

         cut = max(1, min(cut, (int)g.size() - 1));

         vector<int> left(g.begin(), g.begin() + cut);
         vector<int> right(g.begin() + cut, g.end());

         groups[best_g] = left;
         groups.push_back(right);
     }

     for (int k = 0; k < (int)groups.size(); ++k) {
         for (int idx : groups[k]) {
             assign[idx] = min(k, d.K - 1);
         }
     }

     return assign;
 }

 /* ---------------- Mode 5: spatial_grid ---------------- */

 static vector<int> spatial_grid_cluster(
     const InputData &d,
     const unordered_map<int, pair<double,double>> &coords
 ) {
     (void)coords;

     int C = (int)d.customers.size();
     vector<int> assign(C, 0);

     if (C == 0) return assign;

     double min_lon = 1e100, max_lon = -1e100;
     double min_lat = 1e100, max_lat = -1e100;

     for (const auto &c : d.customers) {
         min_lon = min(min_lon, c.lon);
         max_lon = max(max_lon, c.lon);
         min_lat = min(min_lat, c.lat);
         max_lat = max(max_lat, c.lat);
     }

     int grid_side = max(1, (int)ceil(sqrt((double)d.K * 2.0)));
     double lon_span = max(1e-12, max_lon - min_lon);
     double lat_span = max(1e-12, max_lat - min_lat);

     map<pair<int,int>, vector<int>> buckets;

     for (int i = 0; i < C; ++i) {
         const auto &c = d.customers[i];

         int gx = (int)floor((c.lon - min_lon) / lon_span * grid_side);
         int gy = (int)floor((c.lat - min_lat) / lat_span * grid_side);

         gx = max(0, min(grid_side - 1, gx));
         gy = max(0, min(grid_side - 1, gy));

         buckets[{gx, gy}].push_back(i);
     }

     struct Cell {
         vector<int> items;
         double load = 0.0;
         double cx = 0.0;
         double cy = 0.0;
     };

     vector<Cell> cells;

     for (auto &kv : buckets) {
         Cell cell;
         cell.items = kv.second;

         for (int idx : cell.items) {
             cell.load += d.customers[idx].demand;
             cell.cx += d.customers[idx].lon;
             cell.cy += d.customers[idx].lat;
         }

         if (!cell.items.empty()) {
             cell.cx /= cell.items.size();
             cell.cy /= cell.items.size();
         }

         cells.push_back(cell);
     }

     auto depot_xy = get_depot_xy(d, coords);

     sort(cells.begin(), cells.end(), [&](const Cell &a, const Cell &b) {
         double aa = atan2(a.cy - depot_xy.second, a.cx - depot_xy.first);
         double bb = atan2(b.cy - depot_xy.second, b.cx - depot_xy.first);

         if (aa < 0) aa += 2.0 * PI;
         if (bb < 0) bb += 2.0 * PI;

         if (fabs(aa - bb) > 1e-12) return aa < bb;

         return sqr(a.cx - depot_xy.first) + sqr(a.cy - depot_xy.second)
             < sqr(b.cx - depot_xy.first) + sqr(b.cy - depot_xy.second);
     });

     double total_demand = 0.0;
     for (const auto &c : d.customers) total_demand += c.demand;

     double target_load = total_demand / max(1, d.K);
     double soft_limit = min(d.capacity, target_load * 1.20);

     int cluster = 0;
     double load = 0.0;

     for (const auto &cell : cells) {
         bool advance =
             cluster < d.K - 1 &&
             load > 0.0 &&
             (
                 load + cell.load > d.capacity + 1e-9 ||
                 load + cell.load > soft_limit + 1e-9
             );

         if (advance) {
             cluster++;
             load = 0.0;
         }

         for (int idx : cell.items) {
             assign[idx] = cluster;
         }

         load += cell.load;
     }

     return assign;
 }

 /* ---------------- Jacobi eigen decomposition ---------------- */

 static void jacobi_eigen_symmetric(
     vector<vector<double>> A,
     vector<double> &evals,
     vector<vector<double>> &evecs,
     int max_iter = 300
 ) {
     int n = (int)A.size();

     evecs.assign(n, vector<double>(n, 0.0));
     for (int i = 0; i < n; ++i) {
         evecs[i][i] = 1.0;
     }

     if (n == 0) {
         evals.clear();
         return;
     }

     if (n == 1) {
         evals = {A[0][0]};
         return;
     }

     for (int iter = 0; iter < max_iter; ++iter) {
         int p = 0;
         int q = 1;
         double best = 0.0;

         for (int i = 0; i < n; ++i) {
             for (int j = i + 1; j < n; ++j) {
                 double v = fabs(A[i][j]);

                 if (v > best) {
                     best = v;
                     p = i;
                     q = j;
                 }
             }
         }

         if (best < 1e-12) break;

         double app = A[p][p];
         double aqq = A[q][q];
         double apq = A[p][q];

         double phi = 0.5 * atan2(2.0 * apq, aqq - app);
         double c = cos(phi);
         double s = sin(phi);

         for (int k = 0; k < n; ++k) {
             if (k == p || k == q) continue;

             double akp = A[k][p];
             double akq = A[k][q];

             A[k][p] = A[p][k] = c * akp - s * akq;
             A[k][q] = A[q][k] = s * akp + c * akq;
         }

         A[p][p] = c*c*app - 2.0*s*c*apq + s*s*aqq;
         A[q][q] = s*s*app + 2.0*s*c*apq + c*c*aqq;
         A[p][q] = A[q][p] = 0.0;

         for (int k = 0; k < n; ++k) {
             double vip = evecs[k][p];
             double viq = evecs[k][q];

             evecs[k][p] = c * vip - s * viq;
             evecs[k][q] = s * vip + c * viq;
         }
     }

     evals.assign(n, 0.0);
     for (int i = 0; i < n; ++i) {
         evals[i] = A[i][i];
     }
 }

 static vector<int> balanced_kmeans_on_features(
     const InputData &d,
     const vector<vector<double>> &features,
     int iters
 ) {
     int C = (int)features.size();

     vector<int> assign(C, 0);
     if (C == 0) return assign;

     int dim = (int)features[0].size();

     vector<int> order(C);
     iota(order.begin(), order.end(), 0);

     sort(order.begin(), order.end(), [&](int a, int b) {
         if (features[a][0] != features[b][0]) return features[a][0] < features[b][0];
         return d.customers[a].node < d.customers[b].node;
     });

     vector<double> load(d.K, 0.0);
     int cluster = 0;

     double total = 0.0;
     for (auto &c : d.customers) total += c.demand;

     double target = total / max(1, d.K);
     double soft = min(d.capacity, target * 1.15);

     for (int idx : order) {
         if (
             cluster < d.K - 1 &&
             load[cluster] > 0.0 &&
             load[cluster] + d.customers[idx].demand > soft + 1e-9
         ) {
             cluster++;
         }

         assign[idx] = cluster;
         load[cluster] += d.customers[idx].demand;
     }

     vector<vector<double>> centers(d.K, vector<double>(dim, 0.0));

     auto recompute = [&]() {
         centers.assign(d.K, vector<double>(dim, 0.0));
         vector<double> cnt(d.K, 0.0);

         for (int i = 0; i < C; ++i) {
             int k = assign[i];

             for (int z = 0; z < dim; ++z) {
                 centers[k][z] += features[i][z];
             }

             cnt[k] += 1.0;
         }

         for (int k = 0; k < d.K; ++k) {
             if (cnt[k] > 0.0) {
                 for (int z = 0; z < dim; ++z) {
                     centers[k][z] /= cnt[k];
                 }
             } else {
                 centers[k] = features[k % C];
             }
         }
     };

     recompute();

     for (int iter = 0; iter < iters; ++iter) {
         vector<int> demand_order(C);
         iota(demand_order.begin(), demand_order.end(), 0);

         sort(demand_order.begin(), demand_order.end(), [&](int a, int b) {
             if (fabs(d.customers[a].demand - d.customers[b].demand) > 1e-12) {
                 return d.customers[a].demand > d.customers[b].demand;
             }

             return d.customers[a].node < d.customers[b].node;
         });

         vector<double> next_load(d.K, 0.0);
         vector<int> next_assign(C, 0);

         for (int idx : demand_order) {
             vector<pair<double,int>> pref;

             for (int k = 0; k < d.K; ++k) {
                 double dd = 0.0;

                 for (int z = 0; z < dim; ++z) {
                     dd += sqr(features[idx][z] - centers[k][z]);
                 }

                 double pressure = next_load[k] / max(1e-9, d.capacity);
                 double score = dd * (1.0 + 0.35 * pressure);

                 pref.push_back({score, k});
             }

             sort(pref.begin(), pref.end());

             int chosen = pref[0].second;

             for (auto [score, k] : pref) {
                 if (next_load[k] + d.customers[idx].demand <= d.capacity + 1e-9) {
                     chosen = k;
                     break;
                 }
             }

             next_assign[idx] = chosen;
             next_load[chosen] += d.customers[idx].demand;
         }

         bool changed = next_assign != assign;
         assign.swap(next_assign);
         recompute();

         if (!changed) break;
     }

     return assign;
 }

 /* ---------------- Mode 6: spectral_lite coordinate ---------------- */

 static vector<int> spectral_lite_cluster(
     const InputData &d,
     const unordered_map<int, pair<double,double>> &coords,
     int neighbors,
     int iters,
     unsigned seed
 ) {
     (void)coords;
     (void)seed;

     int C = (int)d.customers.size();

     if (C == 0) return {};
     if (C <= d.K) {
         vector<int> a(C);
         for (int i = 0; i < C; ++i) a[i] = min(i, d.K - 1);
         return a;
     }

     if (C > 120) {
         cerr << "[cluster] spectral_lite C=" << C
             << " too large for dense Jacobi; fallback balanced_kmeans\n";

         return balanced_kmeans_cluster(d, coords, iters, seed);
     }

     neighbors = max(1, min(neighbors, C - 1));

     vector<vector<double>> W(C, vector<double>(C, 0.0));
     vector<double> near_dist;
     near_dist.reserve(C * neighbors);

     for (int i = 0; i < C; ++i) {
         vector<pair<double,int>> ds;

         for (int j = 0; j < C; ++j) {
             if (i == j) continue;

             double dd = sqr(d.customers[i].lon - d.customers[j].lon)
                     + sqr(d.customers[i].lat - d.customers[j].lat);

             ds.push_back({dd, j});
         }

         sort(ds.begin(), ds.end());

         for (int t = 0; t < neighbors && t < (int)ds.size(); ++t) {
             near_dist.push_back(max(1e-18, ds[t].first));
         }
     }

     double sigma2 = 1e-12;

     if (!near_dist.empty()) {
         sort(near_dist.begin(), near_dist.end());
         sigma2 = max(near_dist[near_dist.size() / 2], 1e-12);
     }

     for (int i = 0; i < C; ++i) {
         vector<pair<double,int>> ds;

         for (int j = 0; j < C; ++j) {
             if (i == j) continue;

             double dd = sqr(d.customers[i].lon - d.customers[j].lon)
                     + sqr(d.customers[i].lat - d.customers[j].lat);

             ds.push_back({dd, j});
         }

         sort(ds.begin(), ds.end());

         for (int t = 0; t < neighbors && t < (int)ds.size(); ++t) {
             int j = ds[t].second;
             double dd = ds[t].first;

             double sim = exp(-dd / (2.0 * sigma2));

             W[i][j] = max(W[i][j], sim);
             W[j][i] = max(W[j][i], sim);
         }
     }

     vector<double> deg(C, 0.0);

     for (int i = 0; i < C; ++i) {
         for (int j = 0; j < C; ++j) {
             deg[i] += W[i][j];
         }
     }

     vector<vector<double>> L(C, vector<double>(C, 0.0));

     for (int i = 0; i < C; ++i) {
         L[i][i] = 1.0;
     }

     for (int i = 0; i < C; ++i) {
         if (deg[i] <= 1e-12) continue;

         for (int j = 0; j < C; ++j) {
             if (W[i][j] <= 0.0 || deg[j] <= 1e-12) continue;

             L[i][j] -= W[i][j] / sqrt(deg[i] * deg[j]);
         }
     }

     vector<double> evals;
     vector<vector<double>> evecs;

     jacobi_eigen_symmetric(L, evals, evecs, 300);

     vector<int> eig_idx(C);
     iota(eig_idx.begin(), eig_idx.end(), 0);

     sort(eig_idx.begin(), eig_idx.end(), [&](int a, int b) {
         return evals[a] < evals[b];
     });

     int dim = min(d.K, C);
     dim = max(1, dim);

     vector<vector<double>> features(C, vector<double>(dim, 0.0));

     int start_col = (C > 1 && dim + 1 <= C) ? 1 : 0;

     for (int i = 0; i < C; ++i) {
         for (int z = 0; z < dim; ++z) {
             int col = eig_idx[min(start_col + z, C - 1)];
             features[i][z] = evecs[i][col];
         }

         double norm = 0.0;
         for (double v : features[i]) norm += v * v;
         norm = sqrt(max(norm, 1e-18));

         for (double &v : features[i]) v /= norm;
     }

     return balanced_kmeans_on_features(d, features, iters);
 }

 /* ---------------- Mode 7: road_savings ---------------- */

 /*
 Paper-faithful directed parallel Clarke-Wright Savings.

 For ordered customer pair i -> j:
     s_ij = c_0i + c_j0 - c_ij

 The implementation follows the report protocol:
 1) start from singleton routes 0 -> i -> 0;
 2) sort directed end-to-start merge savings;
 3) accept only duplicate-free, capacity-feasible, trip-count-feasible,
     and hard time-window-feasible merges;
 4) create several slightly perturbed variants and keep the best feasible one;
 5) apply a small time-capped exact relocate polish;
 6) export each final route as one cluster label.
 */
 struct SavingsDiagnostics {
     int variants_requested = 0;
     int variants_feasible = 0;
     int best_variant = -1;
     int target_routes = 0;
     int final_routes = 0;
     int accepted_relocates = 0;
     bool hard_feasible = false;
     double best_route_cost = 0.0;
 };

 struct SavingsRouteGroup {
     vector<int> seq;
     double load = 0.0;
     bool active = true;
 };

 struct SavingsVariantResult {
     vector<vector<int>> routes;
     double objective = INF_D;
     bool feasible = false;
 };

 static double directed_saving(const RoadMatrix &rm, int i, int j) {
     if (i == j) return -INF_D;

     const double a = rm.depot_to[i];
     const double b = rm.customer_to_depot[j];
     const double c = rm.cc[i][j];

     if (!isfinite(a) || !isfinite(b) || !isfinite(c)) return -INF_D;
     if (a >= INF_D / 2 || b >= INF_D / 2 || c >= INF_D / 2) return -INF_D;

     return a + b - c;
 }

 static double savings_route_load(
     const InputData &d,
     const vector<int> &seq
 ) {
     double load = 0.0;
     for (int x : seq) load += d.customers[x].demand;
     return load;
 }

 static double savings_route_cost(
     const RoadMatrix &rm,
     const vector<int> &seq
 ) {
     if (seq.empty()) return 0.0;

     double cost = rm.depot_to[seq.front()];

     if (!isfinite(cost) || cost >= INF_D / 2) return INF_D;

     for (int p = 0; p + 1 < (int)seq.size(); ++p) {
         const double c = rm.cc[seq[p]][seq[p + 1]];
         if (!isfinite(c) || c >= INF_D / 2) return INF_D;
         cost += c;
     }

     const double back = rm.customer_to_depot[seq.back()];
     if (!isfinite(back) || back >= INF_D / 2) return INF_D;

     return cost + back;
 }

 static bool savings_route_tw_feasible(
     const InputData &d,
     const RoadMatrix &time_rm,
     const vector<int> &seq,
     bool check_time_windows
 ) {
     if (!check_time_windows || seq.empty()) return true;
     if (!time_rm.built) return false;

     double t = 0.0;
     int prev = -1;

     for (int idx : seq) {
         const double travel =
             prev < 0 ? time_rm.depot_to[idx] : time_rm.cc[prev][idx];

         if (!isfinite(travel) || travel >= INF_D / 2) return false;

         t += travel;
         t = max(t, d.customers[idx].earliest);

         if (t > d.customers[idx].latest + 1e-9) return false;

         t += d.customers[idx].service;
         prev = idx;
     }

     const double back = time_rm.customer_to_depot[seq.back()];
     return isfinite(back) && back < INF_D / 2;
 }

 static bool savings_route_hard_feasible(
     const InputData &d,
     const RoadMatrix &time_rm,
     const vector<int> &seq,
     bool check_time_windows
 ) {
     if (savings_route_load(d, seq) > d.capacity + 1e-9) return false;
     return savings_route_tw_feasible(
         d,
         time_rm,
         seq,
         check_time_windows
     );
 }

 static bool savings_solution_hard_feasible(
     const InputData &d,
     const RoadMatrix &time_rm,
     const vector<vector<int>> &routes,
     bool check_time_windows
 ) {
     if ((int)routes.size() > d.K) return false;

     vector<int> seen(d.customers.size(), 0);

     for (const auto &route : routes) {
         if (!savings_route_hard_feasible(
                 d,
                 time_rm,
                 route,
                 check_time_windows
             )) {
             return false;
         }

         for (int x : route) {
             if (x < 0 || x >= (int)d.customers.size()) return false;
             if (++seen[x] != 1) return false;
         }
     }

     for (int v : seen) {
         if (v != 1) return false;
     }

     return true;
 }

 static double savings_solution_cost(
     const RoadMatrix &rm,
     const vector<vector<int>> &routes
 ) {
     double total = 0.0;

     for (const auto &route : routes) {
         const double c = savings_route_cost(rm, route);
         if (!isfinite(c) || c >= INF_D / 2) return INF_D;
         total += c;
     }

     return total;
 }

 static SavingsVariantResult road_savings_variant_once(
     const InputData &d,
     const RoadMatrix &rm,
     const RoadMatrix &time_rm,
     int target_routes,
     double noise_strength,
     bool check_time_windows,
     mt19937 &rng
 ) {
     const int C = (int)d.customers.size();
     SavingsVariantResult result;

     if (C == 0) {
         result.feasible = true;
         result.objective = 0.0;
         return result;
     }

     struct SavingMove {
         int tail = -1;
         int head = -1;
         double saving = -INF_D;
         double score = -INF_D;
     };

     vector<SavingMove> moves;
     moves.reserve((size_t)C * (size_t)max(0, C - 1));

     uniform_real_distribution<double> noise(-noise_strength, noise_strength);

     for (int i = 0; i < C; ++i) {
         for (int j = 0; j < C; ++j) {
             if (i == j) continue;

             const double saving = directed_saving(rm, i, j);
             if (!isfinite(saving) || saving <= -INF_D / 2) continue;

             const double score = saving * (1.0 + noise(rng));
             moves.push_back({i, j, saving, score});
         }
     }

     sort(moves.begin(), moves.end(), [](const SavingMove &a, const SavingMove &b) {
         if (fabs(a.score - b.score) > 1e-12) return a.score > b.score;
         if (fabs(a.saving - b.saving) > 1e-12) return a.saving > b.saving;
         if (a.tail != b.tail) return a.tail < b.tail;
         return a.head < b.head;
     });

     vector<SavingsRouteGroup> work(C);
     vector<int> owner(C, -1);

     for (int i = 0; i < C; ++i) {
         work[i].seq = {i};
         work[i].load = d.customers[i].demand;
         owner[i] = i;
     }

     int active_count = C;

     auto try_merge = [&](int tail, int head) -> bool {
         if (tail < 0 || tail >= C || head < 0 || head >= C) return false;

         const int ra = owner[tail];
         const int rb = owner[head];

         if (ra < 0 || rb < 0 || ra == rb) return false;
         if (!work[ra].active || !work[rb].active) return false;
         if (work[ra].seq.empty() || work[rb].seq.empty()) return false;

         // Directed parallel Clarke-Wright endpoint condition.
         if (work[ra].seq.back() != tail) return false;
         if (work[rb].seq.front() != head) return false;

         if (work[ra].load + work[rb].load > d.capacity + 1e-9) {
             return false;
         }

         vector<int> merged;
         merged.reserve(work[ra].seq.size() + work[rb].seq.size());
         merged.insert(merged.end(), work[ra].seq.begin(), work[ra].seq.end());
         merged.insert(merged.end(), work[rb].seq.begin(), work[rb].seq.end());

         if (!savings_route_tw_feasible(
                 d,
                 time_rm,
                 merged,
                 check_time_windows
             )) {
             return false;
         }

         work[ra].seq.swap(merged);
         work[ra].load += work[rb].load;

         for (int x : work[rb].seq) owner[x] = ra;

         work[rb].seq.clear();
         work[rb].load = 0.0;
         work[rb].active = false;
         active_count--;
         return true;
     };

     // Savings-ordered endpoint merges. This includes the least-bad merges
     // when necessary to satisfy the fleet/trip-count target.
     for (const auto &move : moves) {
         if (active_count <= target_routes) break;
         try_merge(move.tail, move.head);
     }

     // Defensive completion: search every remaining end-to-start pair if the
     // sorted move pass could not reach the target because prior merges changed
     // route endpoints.
     while (active_count > target_routes) {
         int best_tail = -1;
         int best_head = -1;
         double best_delta = INF_D;

         for (int a = 0; a < C; ++a) {
             if (!work[a].active || work[a].seq.empty()) continue;

             for (int b = 0; b < C; ++b) {
                 if (a == b || !work[b].active || work[b].seq.empty()) continue;
                 if (work[a].load + work[b].load > d.capacity + 1e-9) continue;

                 vector<int> merged;
                 merged.reserve(work[a].seq.size() + work[b].seq.size());
                 merged.insert(merged.end(), work[a].seq.begin(), work[a].seq.end());
                 merged.insert(merged.end(), work[b].seq.begin(), work[b].seq.end());

                 if (!savings_route_tw_feasible(
                         d,
                         time_rm,
                         merged,
                         check_time_windows
                     )) {
                     continue;
                 }

                 const int tail = work[a].seq.back();
                 const int head = work[b].seq.front();

                 const double delta =
                     rm.cc[tail][head] -
                     rm.customer_to_depot[tail] -
                     rm.depot_to[head];

                 if (delta < best_delta) {
                     best_delta = delta;
                     best_tail = tail;
                     best_head = head;
                 }
             }
         }

         if (best_tail < 0 || best_head < 0) break;
         if (!try_merge(best_tail, best_head)) break;
     }

     for (const auto &r : work) {
         if (r.active && !r.seq.empty()) result.routes.push_back(r.seq);
     }

     sort(result.routes.begin(), result.routes.end(), [&](const auto &a, const auto &b) {
         const double la = savings_route_load(d, a);
         const double lb = savings_route_load(d, b);
         if (fabs(la - lb) > 1e-12) return la > lb;
         return a.front() < b.front();
     });

     result.feasible = savings_solution_hard_feasible(
         d,
         time_rm,
         result.routes,
         check_time_windows
     );

     if (result.feasible) {
         result.objective = savings_solution_cost(rm, result.routes);
     }

     return result;
 }

 static int savings_light_relocate_polish(
     const InputData &d,
     const RoadMatrix &rm,
     const RoadMatrix &time_rm,
     vector<vector<int>> &routes,
     int rounds,
     double time_limit_s,
     bool check_time_windows
 ) {
     if (rounds <= 0 || routes.empty()) return 0;

     const auto start = SteadyClock::now();
     int accepted = 0;

     auto time_expired = [&]() {
         if (time_limit_s <= 0.0) return false;
         return seconds_between(start, SteadyClock::now()) >= time_limit_s;
     };

     for (int round = 0; round < rounds && !time_expired(); ++round) {
         bool improved = false;

         for (int ra = 0; ra < (int)routes.size() && !improved; ++ra) {
             for (int pa = 0; pa < (int)routes[ra].size() && !improved; ++pa) {
                 const int node = routes[ra][pa];

                 for (int rb = 0; rb < (int)routes.size() && !improved; ++rb) {
                     if (ra == rb) continue;

                     for (int pb = 0; pb <= (int)routes[rb].size(); ++pb) {
                         if (time_expired()) return accepted;

                         vector<int> from = routes[ra];
                         vector<int> to = routes[rb];

                         from.erase(from.begin() + pa);
                         to.insert(to.begin() + pb, node);

                         if (!savings_route_hard_feasible(
                                 d,
                                 time_rm,
                                 from,
                                 check_time_windows
                             )) {
                             continue;
                         }

                         if (!savings_route_hard_feasible(
                                 d,
                                 time_rm,
                                 to,
                                 check_time_windows
                             )) {
                             continue;
                         }

                         const double old_cost =
                             savings_route_cost(rm, routes[ra]) +
                             savings_route_cost(rm, routes[rb]);

                         const double new_cost =
                             savings_route_cost(rm, from) +
                             savings_route_cost(rm, to);

                         if (new_cost + 1e-9 < old_cost) {
                             routes[ra].swap(from);
                             routes[rb].swap(to);

                             routes.erase(
                                 remove_if(
                                     routes.begin(),
                                     routes.end(),
                                     [](const vector<int> &r) { return r.empty(); }
                                 ),
                                 routes.end()
                             );

                             accepted++;
                             improved = true;
                             break;
                         }
                     }
                 }
             }
         }

         if (!improved) break;
     }

     return accepted;
 }

 static vector<int> road_savings_cluster(
     const InputData &d,
     const RoadMatrix &rm,
     const RoadMatrix &time_rm,
     int variants,
     double noise_strength,
     int target_routes_override,
     int target_extra_routes,
     int polish_rounds,
     double polish_time_s,
     bool check_time_windows,
     unsigned seed,
     SavingsDiagnostics &diag
 ) {
     const int C = (int)d.customers.size();
     vector<int> assign(C, 0);

     if (C == 0) return assign;
     if (!rm.built || !time_rm.built) {
         throw runtime_error("road_savings requires objective and time road matrices");
     }

     double total_demand = 0.0;
     for (const auto &c : d.customers) total_demand += c.demand;

     int target_routes = target_routes_override;

     if (target_routes <= 0) {
         target_routes =
             (int)ceil(total_demand / max(1e-9, d.capacity)) +
             max(0, target_extra_routes);
     }

     target_routes = max(1, min({target_routes, d.K, C}));

     variants = max(1, variants);
     noise_strength = max(0.0, noise_strength);

     diag.variants_requested = variants;
     diag.target_routes = target_routes;

     SavingsVariantResult best;

     for (int v = 0; v < variants; ++v) {
         mt19937 rng(seed + 1000003u * (unsigned)(v + 1));
         const double variant_noise = v == 0 ? 0.0 : noise_strength;

         SavingsVariantResult cand = road_savings_variant_once(
             d,
             rm,
             time_rm,
             target_routes,
             variant_noise,
             check_time_windows,
             rng
         );

         if (!cand.feasible) continue;

         diag.variants_feasible++;

         if (cand.objective + 1e-9 < best.objective) {
             best = std::move(cand);
             diag.best_variant = v;
         }
     }

     if (!best.feasible || best.routes.empty()) {
         throw runtime_error(
             "paper-faithful road_savings could not construct a hard-feasible "
             "solution with at most K routes"
         );
     }

     diag.accepted_relocates = savings_light_relocate_polish(
         d,
         rm,
         time_rm,
         best.routes,
         polish_rounds,
         polish_time_s,
         check_time_windows
     );

     best.objective = savings_solution_cost(rm, best.routes);
     best.feasible = savings_solution_hard_feasible(
         d,
         time_rm,
         best.routes,
         check_time_windows
     );

     if (!best.feasible) {
         throw runtime_error(
             "road_savings light polish failed hard-feasibility validation"
         );
     }

     diag.final_routes = (int)best.routes.size();
     diag.best_route_cost = best.objective;
     diag.hard_feasible = true;

     for (int k = 0; k < (int)best.routes.size(); ++k) {
         for (int x : best.routes[k]) assign[x] = k;
     }

     cerr << "[road_savings] directed_parallel_clarke_wright=1"
         << " variants=" << diag.variants_requested
         << " feasible_variants=" << diag.variants_feasible
         << " best_variant=" << diag.best_variant
         << " target_routes=" << diag.target_routes
         << " final_routes=" << diag.final_routes
         << " light_relocates=" << diag.accepted_relocates
         << " route_cost=" << diag.best_route_cost
         << " hard_feasible=" << (diag.hard_feasible ? 1 : 0)
         << "\n";

     return assign;
 }


 /* ---------------- Mode 8: network_kmedoids ---------------- */

 static vector<int> network_kmedoids_cluster(
     const InputData &d,
     const RoadMatrix &rm,
     int iters,
     unsigned seed
 ) {
     int C = (int)d.customers.size();

     vector<int> assign(C, 0);
     if (C == 0) return assign;
     if (!rm.built) return round_robin_cluster(d);

     int K = min(d.K, C);
     mt19937 rng(seed);

     vector<int> medoids;
     medoids.reserve(d.K);

     int first = 0;
     double far_from_depot = -1.0;

     for (int i = 0; i < C; ++i) {
         double v = min(rm.depot_to[i], rm.customer_to_depot[i]);

         if (v > far_from_depot) {
             far_from_depot = v;
             first = i;
         }
     }

     medoids.push_back(first);

     while ((int)medoids.size() < K) {
         int best = -1;
         double best_dist = -1.0;

         for (int i = 0; i < C; ++i) {
             bool used = false;

             for (int m : medoids) {
                 if (m == i) {
                     used = true;
                     break;
                 }
             }

             if (used) continue;

             double nearest = INF_D;

             for (int m : medoids) {
                 nearest = min(nearest, sym_road_cost(rm, i, m));
             }

             if (nearest > best_dist) {
                 best_dist = nearest;
                 best = i;
             }
         }

         if (best == -1) break;

         medoids.push_back(best);
     }

     while ((int)medoids.size() < d.K) {
         medoids.push_back(medoids.back());
     }

     for (int iter = 0; iter < iters; ++iter) {
         vector<int> order(C);
         iota(order.begin(), order.end(), 0);

         sort(order.begin(), order.end(), [&](int a, int b) {
             if (fabs(d.customers[a].demand - d.customers[b].demand) > 1e-12) {
                 return d.customers[a].demand > d.customers[b].demand;
             }

             return d.customers[a].node < d.customers[b].node;
         });

         vector<double> load(d.K, 0.0);
         vector<int> next_assign(C, 0);

         for (int idx : order) {
             vector<pair<double,int>> pref;

             for (int k = 0; k < d.K; ++k) {
                 int m = medoids[k];

                 double dist = sym_road_cost(rm, idx, m);
                 double pressure = load[k] / max(1e-9, d.capacity);
                 double score = dist * (1.0 + 0.35 * pressure);

                 pref.push_back({score, k});
             }

             sort(pref.begin(), pref.end());

             int chosen = pref[0].second;

             for (auto [score, k] : pref) {
                 if (load[k] + d.customers[idx].demand <= d.capacity + 1e-9) {
                     chosen = k;
                     break;
                 }
             }

             next_assign[idx] = chosen;
             load[chosen] += d.customers[idx].demand;
         }

         assign.swap(next_assign);

         vector<int> new_medoids = medoids;

         for (int k = 0; k < d.K; ++k) {
             vector<int> members;

             for (int i = 0; i < C; ++i) {
                 if (assign[i] == k) {
                     members.push_back(i);
                 }
             }

             if (members.empty()) continue;

             int best_medoid = members[0];
             double best_sum = INF_D;

             for (int cand : members) {
                 double sum = 0.0;

                 for (int x : members) {
                     sum += sym_road_cost(rm, cand, x);
                 }

                 if (sum < best_sum) {
                     best_sum = sum;
                     best_medoid = cand;
                 }
             }

             new_medoids[k] = best_medoid;
         }

         bool changed = (new_medoids != medoids);
         medoids.swap(new_medoids);

         if (!changed && iter > 0) break;
     }

     return assign;
 }

 /* ---------------- Mode 9: route_split ---------------- */

 static vector<int> route_split_cluster(
     const InputData &d,
     const RoadMatrix &rm
 ) {
     int C = (int)d.customers.size();

     vector<int> assign(C, 0);
     if (C == 0) return assign;
     if (!rm.built) return round_robin_cluster(d);

     vector<char> used(C, 0);
     vector<int> tour;
     tour.reserve(C);

     int cur = -1;

     for (int step = 0; step < C; ++step) {
         int best = -1;
         double best_cost = INF_D;

         for (int j = 0; j < C; ++j) {
             if (used[j]) continue;

             double cost = 0.0;

             if (cur == -1) {
                 cost = rm.depot_to[j];
             } else {
                 cost = rm.cc[cur][j];
             }

             cost += 0.05 * rm.customer_to_depot[j];

             if (cost < best_cost) {
                 best_cost = cost;
                 best = j;
             }
         }

         if (best == -1) break;

         used[best] = 1;
         tour.push_back(best);
         cur = best;
     }

     double total_demand = 0.0;
     for (const auto &c : d.customers) total_demand += c.demand;

     double target_load = total_demand / max(1, d.K);
     double soft_limit = min(d.capacity, target_load * 1.10);

     int cluster = 0;
     double load = 0.0;

     for (int idx : tour) {
         double dem = d.customers[idx].demand;

         bool advance =
             cluster < d.K - 1 &&
             load > 0.0 &&
             (
                 load + dem > d.capacity + 1e-9 ||
                 load + dem > soft_limit + 1e-9
             );

         if (advance) {
             cluster++;
             load = 0.0;
         }

         assign[idx] = cluster;
         load += dem;
     }

     return assign;
 }

 /* ---------------- Mode 10: road_spectral_lite ---------------- */

 static vector<int> road_spectral_lite_cluster(
     const InputData &d,
     const RoadMatrix &rm,
     int neighbors,
     int iters,
     unsigned seed
 ) {
     (void)seed;

     int C = (int)d.customers.size();

     if (C == 0) return {};
     if (!rm.built) return round_robin_cluster(d);

     if (C > 120) {
         cerr << "[cluster] road_spectral_lite C=" << C
             << " too large for dense spectral; fallback network_kmedoids\n";

         return network_kmedoids_cluster(d, rm, iters, seed);
     }

     neighbors = max(1, min(neighbors, C - 1));

     vector<vector<double>> W(C, vector<double>(C, 0.0));
     vector<double> near_costs;
     near_costs.reserve(C * neighbors);

     for (int i = 0; i < C; ++i) {
         vector<pair<double,int>> ds;

         for (int j = 0; j < C; ++j) {
             if (i == j) continue;

             double c = sym_road_cost(rm, i, j);
             ds.push_back({c, j});
         }

         sort(ds.begin(), ds.end());

         for (int t = 0; t < neighbors && t < (int)ds.size(); ++t) {
             near_costs.push_back(max(1e-9, ds[t].first));
         }
     }

     double sigma = 1.0;

     if (!near_costs.empty()) {
         sort(near_costs.begin(), near_costs.end());
         sigma = max(1e-9, near_costs[near_costs.size() / 2]);
     }

     for (int i = 0; i < C; ++i) {
         vector<pair<double,int>> ds;

         for (int j = 0; j < C; ++j) {
             if (i == j) continue;

             double c = sym_road_cost(rm, i, j);
             ds.push_back({c, j});
         }

         sort(ds.begin(), ds.end());

         for (int t = 0; t < neighbors && t < (int)ds.size(); ++t) {
             int j = ds[t].second;
             double c = ds[t].first;

             double sim = exp(-c / max(1e-9, sigma));

             W[i][j] = max(W[i][j], sim);
             W[j][i] = max(W[j][i], sim);
         }
     }

     vector<double> deg(C, 0.0);

     for (int i = 0; i < C; ++i) {
         for (int j = 0; j < C; ++j) {
             deg[i] += W[i][j];
         }
     }

     vector<vector<double>> L(C, vector<double>(C, 0.0));

     for (int i = 0; i < C; ++i) {
         L[i][i] = 1.0;
     }

     for (int i = 0; i < C; ++i) {
         if (deg[i] <= 1e-12) continue;

         for (int j = 0; j < C; ++j) {
             if (W[i][j] <= 0.0 || deg[j] <= 1e-12) continue;

             L[i][j] -= W[i][j] / sqrt(deg[i] * deg[j]);
         }
     }

     vector<double> evals;
     vector<vector<double>> evecs;

     jacobi_eigen_symmetric(L, evals, evecs, 300);

     vector<int> eig_idx(C);
     iota(eig_idx.begin(), eig_idx.end(), 0);

     sort(eig_idx.begin(), eig_idx.end(), [&](int a, int b) {
         return evals[a] < evals[b];
     });

     int dim = min(d.K, C);
     dim = max(1, dim);

     vector<vector<double>> features(C, vector<double>(dim, 0.0));

     int start_col = (C > 1 && dim + 1 <= C) ? 1 : 0;

     for (int i = 0; i < C; ++i) {
         for (int z = 0; z < dim; ++z) {
             int col = eig_idx[min(start_col + z, C - 1)];
             features[i][z] = evecs[i][col];
         }

         double norm = 0.0;
         for (double v : features[i]) norm += v * v;
         norm = sqrt(max(norm, 1e-18));

         for (double &v : features[i]) v /= norm;
     }

     vector<int> assign = balanced_kmeans_on_features(d, features, iters);

     // Shared main-stage pipeline performs overload repair and exactly one
     // road-assignment polish so its timing is recorded separately.
     return assign;
 }


 /* ---------------- Mode 11: paper-faithful sparse road spectral ---------------- */

 struct ProjectedPoint {
     double x = 0.0;
     double y = 0.0;
     int idx = -1;
 };

 static vector<ProjectedPoint> project_customer_coordinates_m(
     const InputData &d
 ) {
     const double EARTH_R = 6371000.0;
     double mean_lat_rad = 0.0;

     for (const auto &c : d.customers) {
         mean_lat_rad += c.lat * PI / 180.0;
     }

     if (!d.customers.empty()) {
         mean_lat_rad /= (double)d.customers.size();
     }

     vector<ProjectedPoint> pts;
     pts.reserve(d.customers.size());

     for (int i = 0; i < (int)d.customers.size(); ++i) {
         const double lon_rad = d.customers[i].lon * PI / 180.0;
         const double lat_rad = d.customers[i].lat * PI / 180.0;

         pts.push_back({
             EARTH_R * lon_rad * cos(mean_lat_rad),
             EARTH_R * lat_rad,
             i
         });
     }

     return pts;
 }

 class KDTree2D {
 private:
     struct Node {
         int point_pos = -1;
         int left = -1;
         int right = -1;
         int axis = 0;
     };

     vector<ProjectedPoint> points_;
     vector<Node> nodes_;
     int root_ = -1;

     int build_rec(vector<int> &ids, int l, int r, int depth) {
         if (l >= r) return -1;

         const int axis = depth & 1;
         const int m = l + (r - l) / 2;

         nth_element(
             ids.begin() + l,
             ids.begin() + m,
             ids.begin() + r,
             [&](int a, int b) {
                 const double va = axis == 0 ? points_[a].x : points_[a].y;
                 const double vb = axis == 0 ? points_[b].x : points_[b].y;
                 if (fabs(va - vb) > 1e-12) return va < vb;
                 return points_[a].idx < points_[b].idx;
             }
         );

         const int node_id = (int)nodes_.size();
         nodes_.push_back(Node{});
         nodes_[node_id].point_pos = ids[m];
         nodes_[node_id].axis = axis;
         nodes_[node_id].left = build_rec(ids, l, m, depth + 1);
         nodes_[node_id].right = build_rec(ids, m + 1, r, depth + 1);

         return node_id;
     }

     static double point_dist2(
         const ProjectedPoint &p,
         double qx,
         double qy
     ) {
         return sqr(p.x - qx) + sqr(p.y - qy);
     }

     void query_rec(
         int node_id,
         double qx,
         double qy,
         int self_idx,
         int k,
         priority_queue<pair<double,int>> &best
     ) const {
         if (node_id < 0) return;

         const Node &node = nodes_[node_id];
         const ProjectedPoint &p = points_[node.point_pos];

         const double d2 = point_dist2(p, qx, qy);

         if (p.idx != self_idx) {
             if ((int)best.size() < k) {
                 best.push({d2, p.idx});
             } else if (
                 d2 + 1e-12 < best.top().first ||
                 (
                     fabs(d2 - best.top().first) <= 1e-12 &&
                     p.idx < best.top().second
                 )
             ) {
                 best.pop();
                 best.push({d2, p.idx});
             }
         }

         const double qv = node.axis == 0 ? qx : qy;
         const double pv = node.axis == 0 ? p.x : p.y;

         const int near_child = qv < pv ? node.left : node.right;
         const int far_child = qv < pv ? node.right : node.left;

         query_rec(near_child, qx, qy, self_idx, k, best);

         const double plane_d2 = sqr(qv - pv);
         const double worst =
             (int)best.size() < k ? INF_D : best.top().first;

         if (plane_d2 <= worst + 1e-12) {
             query_rec(far_child, qx, qy, self_idx, k, best);
         }
     }

 public:
     explicit KDTree2D(vector<ProjectedPoint> points)
         : points_(std::move(points)) {
         vector<int> ids(points_.size());
         iota(ids.begin(), ids.end(), 0);
         nodes_.reserve(points_.size());
         root_ = build_rec(ids, 0, (int)ids.size(), 0);
     }

     vector<int> query_knn(int point_index, int k) const {
         if (point_index < 0 || point_index >= (int)points_.size()) {
             return {};
         }

         k = max(0, min(k, (int)points_.size() - 1));
         if (k == 0) return {};

         priority_queue<pair<double,int>> best;

         query_rec(
             root_,
             points_[point_index].x,
             points_[point_index].y,
             point_index,
             k,
             best
         );

         vector<pair<double,int>> ordered;
         ordered.reserve(best.size());

         while (!best.empty()) {
             ordered.push_back(best.top());
             best.pop();
         }

         sort(ordered.begin(), ordered.end(), [](const auto &a, const auto &b) {
             if (fabs(a.first - b.first) > 1e-12) return a.first < b.first;
             return a.second < b.second;
         });

         vector<int> out;
         out.reserve(ordered.size());

         for (const auto &x : ordered) {
             out.push_back(x.second);
         }

         return out;
     }
 };

 struct SparseAffinityGraph {
     vector<vector<pair<int,double>>> w;
     vector<double> degree;
     vector<double> local_scale;
     int directed_candidate_arcs = 0;
     int undirected_edges = 0;
 };

 static SparseAffinityGraph build_sparse_road_affinity(
     const InputData &d,
     const RoadMatrix &rm,
     int neighbors,
     int sigma_rank
 ) {
     const int C = (int)d.customers.size();

     SparseAffinityGraph g;
     g.w.assign(C, {});
     g.degree.assign(C, 0.0);
     g.local_scale.assign(C, 1.0);

     if (C <= 1) return g;

     neighbors = max(1, min(neighbors, C - 1));
     sigma_rank = max(1, min(sigma_rank, neighbors));

     vector<ProjectedPoint> projected = project_customer_coordinates_m(d);
     KDTree2D tree(projected);

     vector<vector<int>> candidates(C);
     vector<double> all_candidate_delta;
     all_candidate_delta.reserve((size_t)C * neighbors);

     for (int i = 0; i < C; ++i) {
         candidates[i] = tree.query_knn(i, neighbors);
         g.directed_candidate_arcs += (int)candidates[i].size();

         vector<double> local_delta;
         local_delta.reserve(candidates[i].size());

         for (int j : candidates[i]) {
             const double delta = sym_road_cost(rm, i, j);

             if (isfinite(delta) && delta > 1e-12 && delta < INF_D / 2) {
                 local_delta.push_back(delta);
                 all_candidate_delta.push_back(delta);
             }
         }

         sort(local_delta.begin(), local_delta.end());

         if (!local_delta.empty()) {
             const int pos = min((int)local_delta.size() - 1, sigma_rank - 1);
             g.local_scale[i] = max(1e-12, local_delta[pos]);
         }
     }

     double global_scale = 1.0;

     if (!all_candidate_delta.empty()) {
         nth_element(
             all_candidate_delta.begin(),
             all_candidate_delta.begin() + all_candidate_delta.size() / 2,
             all_candidate_delta.end()
         );
         global_scale = max(
             1e-12,
             all_candidate_delta[all_candidate_delta.size() / 2]
         );
     }

     for (double &s : g.local_scale) {
         if (!isfinite(s) || s <= 1e-12) {
             s = global_scale;
         }
     }

     unordered_set<uint64_t> seen;
     seen.reserve((size_t)C * neighbors * 2 + 1);

     for (int i = 0; i < C; ++i) {
         for (int j : candidates[i]) {
             if (i == j) continue;

             const uint64_t key = undirected_pair_key(i, j);
             if (!seen.insert(key).second) continue;

             const double delta = sym_road_cost(rm, i, j);

             if (!isfinite(delta) || delta <= 0.0 || delta >= INF_D / 2) {
                 continue;
             }

             // Self-tuning affinity:
             // w_ij = exp(-delta_ij^2 / (sigma_i sigma_j)).
             const double denom = max(
                 1e-18,
                 g.local_scale[i] * g.local_scale[j]
             );

             double weight = exp(-(delta * delta) / denom);

             // Preserve graph connectivity numerically without densifying it.
             weight = max(weight, 1e-15);

             g.w[i].push_back({j, weight});
             g.w[j].push_back({i, weight});
             g.degree[i] += weight;
             g.degree[j] += weight;
             g.undirected_edges++;
         }
     }

     // Defensive isolated-node repair. This still keeps O(nk) edges.
     for (int i = 0; i < C; ++i) {
         if (g.degree[i] > 1e-18) continue;
         if (candidates[i].empty()) continue;

         int j = candidates[i][0];
         if (i == j) continue;

         const uint64_t key = undirected_pair_key(i, j);

         if (seen.insert(key).second) {
             const double weight = 1e-12;
             g.w[i].push_back({j, weight});
             g.w[j].push_back({i, weight});
             g.degree[i] += weight;
             g.degree[j] += weight;
             g.undirected_edges++;
         }
     }

     return g;
 }

 static vector<double> apply_sparse_lsym(
     const SparseAffinityGraph &g,
     const vector<double> &x
 ) {
     const int n = (int)g.w.size();
     vector<double> y = x;

     for (int i = 0; i < n; ++i) {
         if (g.degree[i] <= 1e-30) continue;

         const double inv_sqrt_di = 1.0 / sqrt(g.degree[i]);

         for (const auto &[j, wij] : g.w[i]) {
             if (g.degree[j] <= 1e-30) continue;

             y[i] -=
                 wij *
                 inv_sqrt_di *
                 (1.0 / sqrt(g.degree[j])) *
                 x[j];
         }
     }

     return y;
 }

 static double dot_vec(
     const vector<double> &a,
     const vector<double> &b
 ) {
     double s = 0.0;

     for (int i = 0; i < (int)a.size(); ++i) {
         s += a[i] * b[i];
     }

     return s;
 }

 static double norm_vec(const vector<double> &a) {
     return sqrt(max(0.0, dot_vec(a, a)));
 }

 static void axpy_inplace(
     vector<double> &y,
     double alpha,
     const vector<double> &x
 ) {
     for (int i = 0; i < (int)y.size(); ++i) {
         y[i] += alpha * x[i];
     }
 }

 /*
 Implicit QL for a real symmetric tridiagonal matrix.

 d: diagonal
 e: e[0]=0, e[i]=subdiagonal between i-1 and i
 z: receives eigenvectors in columns
 */
 static void tridiagonal_ql(
     vector<double> &d,
     vector<double> &e,
     vector<vector<double>> &z
 ) {
     const int n = (int)d.size();

     z.assign(n, vector<double>(n, 0.0));
     for (int i = 0; i < n; ++i) z[i][i] = 1.0;

     if (n <= 1) return;

     for (int i = 1; i < n; ++i) {
         e[i - 1] = e[i];
     }
     e[n - 1] = 0.0;

     for (int l = 0; l < n; ++l) {
         int iter = 0;

         while (true) {
             int m = l;

             for (; m < n - 1; ++m) {
                 const double dd = fabs(d[m]) + fabs(d[m + 1]);

                 if (fabs(e[m]) <=
                     numeric_limits<double>::epsilon() * max(1.0, dd)) {
                     break;
                 }
             }

             if (m == l) break;

             if (++iter > 1000) {
                 throw runtime_error(
                     "Sparse spectral tridiagonal QL failed to converge"
                 );
             }

             double g = (d[l + 1] - d[l]) / (2.0 * e[l]);
             double r = hypot(g, 1.0);
             g = d[m] - d[l] +
                 e[l] / (g + copysign(r, g));

             double s = 1.0;
             double c = 1.0;
             double p = 0.0;
             int i = m - 1;

             for (; i >= l; --i) {
                 const double f = s * e[i];
                 const double b = c * e[i];

                 r = hypot(f, g);
                 e[i + 1] = r;

                 if (r <= 1e-300) {
                     d[i + 1] -= p;
                     e[m] = 0.0;
                     break;
                 }

                 s = f / r;
                 c = g / r;

                 g = d[i + 1] - p;
                 r = (d[i] - g) * s + 2.0 * c * b;
                 p = s * r;
                 d[i + 1] = g + p;
                 g = c * r - b;

                 for (int k = 0; k < n; ++k) {
                     const double zik1 = z[k][i + 1];
                     const double zik = z[k][i];

                     z[k][i + 1] = s * zik + c * zik1;
                     z[k][i] = c * zik - s * zik1;
                 }
             }

             if (r <= 1e-300 && i >= l) {
                 continue;
             }

             d[l] -= p;
             e[l] = g;
             e[m] = 0.0;
         }
     }
 }

 struct SparseEigenResult {
     vector<double> eigenvalues;
     vector<vector<double>> eigenvectors; // rows = customers, columns = eigenvectors
     int lanczos_steps = 0;
     int lanczos_dimension = 0;
     double max_residual = INF_D;
     bool converged = false;
 };

 static SparseEigenResult smallest_sparse_lsym_eigenvectors(
     const SparseAffinityGraph &g,
     int wanted,
     int max_lanczos_dim,
     double tolerance,
     unsigned seed
 ) {
     const int n = (int)g.w.size();

     SparseEigenResult result;

     if (n == 0 || wanted <= 0) return result;

     wanted = min(wanted, n);

     int m_limit = max_lanczos_dim;

     if (m_limit <= 0) {
         m_limit = min(n, max(wanted + 32, 3 * wanted));
     }

     m_limit = max(wanted, min(m_limit, n));
     result.lanczos_dimension = m_limit;

     mt19937 rng(seed);
     normal_distribution<double> normal01(0.0, 1.0);

     vector<double> q(n, 0.0);

     for (double &x : q) {
         x = normal01(rng);
     }

     // Avoid an accidental start vector orthogonal to the null-space vector.
     for (int i = 0; i < n; ++i) {
         q[i] += 1e-3 * sqrt(max(0.0, g.degree[i]));
     }

     double qnorm = norm_vec(q);

     if (qnorm <= 1e-30) {
         q.assign(n, 0.0);
         q[0] = 1.0;
         qnorm = 1.0;
     }

     for (double &x : q) x /= qnorm;

     vector<double> q_prev(n, 0.0);
     double beta_prev = 0.0;
     double beta_tail = 0.0;

     vector<vector<double>> basis;
     basis.reserve(m_limit);

     vector<double> alpha;
     vector<double> beta;
     alpha.reserve(m_limit);
     beta.reserve(max(0, m_limit - 1));

     for (int step = 0; step < m_limit; ++step) {
         basis.push_back(q);

         vector<double> w = apply_sparse_lsym(g, q);

         const double a = dot_vec(q, w);
         alpha.push_back(a);

         axpy_inplace(w, -a, q);

         if (step > 0) {
             axpy_inplace(w, -beta_prev, q_prev);
         }

         // Full reorthogonalization twice for numerical reliability.
         for (int pass = 0; pass < 2; ++pass) {
             for (const auto &v : basis) {
                 const double coeff = dot_vec(v, w);
                 axpy_inplace(w, -coeff, v);
             }
         }

         const double b = norm_vec(w);
         beta_tail = b;

         if (step + 1 >= m_limit || b <= 1e-13) {
             break;
         }

         beta.push_back(b);
         q_prev = q;
         q = w;

         for (double &x : q) x /= b;

         beta_prev = b;
     }

     const int m = (int)alpha.size();
     result.lanczos_steps = m;

     if (m == 0) return result;

     vector<double> diag = alpha;
     vector<double> off(m, 0.0);

     for (int i = 1; i < m; ++i) {
         off[i] = beta[i - 1];
     }

     vector<vector<double>> z;
     tridiagonal_ql(diag, off, z);

     vector<int> order(m);
     iota(order.begin(), order.end(), 0);

     sort(order.begin(), order.end(), [&](int a, int b) {
         if (fabs(diag[a] - diag[b]) > 1e-12) return diag[a] < diag[b];
         return a < b;
     });

     const int take = min(wanted, m);

     result.eigenvalues.resize(take);
     result.eigenvectors.assign(n, vector<double>(take, 0.0));
     result.max_residual = 0.0;

     for (int c = 0; c < take; ++c) {
         const int col = order[c];
         result.eigenvalues[c] = diag[col];

         for (int j = 0; j < m; ++j) {
             const double coeff = z[j][col];

             for (int i = 0; i < n; ++i) {
                 result.eigenvectors[i][c] += basis[j][i] * coeff;
             }
         }

         double cnorm = 0.0;

         for (int i = 0; i < n; ++i) {
             cnorm +=
                 result.eigenvectors[i][c] *
                 result.eigenvectors[i][c];
         }

         cnorm = sqrt(max(cnorm, 1e-30));

         for (int i = 0; i < n; ++i) {
             result.eigenvectors[i][c] /= cnorm;
         }

         const double residual =
             fabs(beta_tail * z[m - 1][col]);

         result.max_residual = max(result.max_residual, residual);
     }

     result.converged =
         take == wanted &&
         result.max_residual <= max(1e-12, tolerance);

     return result;
 }

 static vector<int> capacity_aware_kmeans_embedding(
     const InputData &d,
     const vector<vector<double>> &features,
     int k_eff,
     int iters,
     unsigned seed
 ) {
     const int C = (int)features.size();

     if (C == 0) return {};

     const int dim = (int)features[0].size();
     k_eff = max(1, min({k_eff, C, d.K}));

     vector<vector<double>> centers;
     centers.reserve(k_eff);

     mt19937 rng(seed);
     uniform_int_distribution<int> first_pick(0, C - 1);

     int first = first_pick(rng);
     centers.push_back(features[first]);

     vector<double> nearest_d2(C, INF_D);

     while ((int)centers.size() < k_eff) {
         int chosen = -1;
         double farthest = -1.0;

         for (int i = 0; i < C; ++i) {
             double best = nearest_d2[i];

             double dd = 0.0;
             for (int z = 0; z < dim; ++z) {
                 dd += sqr(features[i][z] - centers.back()[z]);
             }

             best = min(best, dd);
             nearest_d2[i] = best;

             if (
                 best > farthest + 1e-15 ||
                 (
                     fabs(best - farthest) <= 1e-15 &&
                     (
                         chosen < 0 ||
                         d.customers[i].node < d.customers[chosen].node
                     )
                 )
             ) {
                 farthest = best;
                 chosen = i;
             }
         }

         if (chosen < 0) chosen = (int)centers.size() % C;
         centers.push_back(features[chosen]);
     }

     vector<int> assign(C, 0);

     for (int iter = 0; iter < max(1, iters); ++iter) {
         vector<int> order(C);
         iota(order.begin(), order.end(), 0);

         sort(order.begin(), order.end(), [&](int a, int b) {
             if (fabs(d.customers[a].demand - d.customers[b].demand) > 1e-12) {
                 return d.customers[a].demand > d.customers[b].demand;
             }
             return d.customers[a].node < d.customers[b].node;
         });

         vector<int> next_assign(C, 0);
         vector<double> load(k_eff, 0.0);
         vector<int> count(k_eff, 0);

         for (int idx : order) {
             vector<pair<double,int>> pref;
             pref.reserve(k_eff);

             for (int k = 0; k < k_eff; ++k) {
                 double dd = 0.0;

                 for (int z = 0; z < dim; ++z) {
                     dd += sqr(features[idx][z] - centers[k][z]);
                 }

                 const double pressure =
                     load[k] / max(1e-12, d.capacity);

                 // Capacity-aware score from the report: embedding distance
                 // multiplied by a load-pressure term.
                 const double score =
                     dd * (1.0 + 0.35 * pressure);

                 pref.push_back({score, k});
             }

             sort(pref.begin(), pref.end());

             int chosen = -1;

             for (const auto &[score, k] : pref) {
                 (void)score;

                 if (
                     load[k] + d.customers[idx].demand
                     <= d.capacity + 1e-9
                 ) {
                     chosen = k;
                     break;
                 }
             }

             if (chosen < 0) {
                 double best_penalized = INF_D;

                 for (const auto &[score, k] : pref) {
                     const double overload = max(
                         0.0,
                         load[k] + d.customers[idx].demand - d.capacity
                     );

                     const double penalized =
                         score +
                         1e6 * overload * overload;

                     if (penalized < best_penalized) {
                         best_penalized = penalized;
                         chosen = k;
                     }
                 }
             }

             if (chosen < 0) chosen = 0;

             next_assign[idx] = chosen;
             load[chosen] += d.customers[idx].demand;
             count[chosen]++;
         }

         vector<vector<double>> next_centers(
             k_eff,
             vector<double>(dim, 0.0)
         );

         for (int i = 0; i < C; ++i) {
             const int k = next_assign[i];

             for (int z = 0; z < dim; ++z) {
                 next_centers[k][z] += features[i][z];
             }
         }

         for (int k = 0; k < k_eff; ++k) {
             if (count[k] > 0) {
                 for (int z = 0; z < dim; ++z) {
                     next_centers[k][z] /= (double)count[k];
                 }
             } else {
                 int farthest_idx = 0;
                 double farthest_d2 = -1.0;

                 for (int i = 0; i < C; ++i) {
                     const int old_k = next_assign[i];
                     double dd = 0.0;

                     for (int z = 0; z < dim; ++z) {
                         dd += sqr(
                             features[i][z] -
                             next_centers[old_k][z]
                         );
                     }

                     if (dd > farthest_d2) {
                         farthest_d2 = dd;
                         farthest_idx = i;
                     }
                 }

                 next_centers[k] = features[farthest_idx];
             }
         }

         const bool changed = next_assign != assign;
         assign.swap(next_assign);
         centers.swap(next_centers);

         if (!changed && iter > 0) break;
     }

     return assign;
 }

 static vector<int> road_spectral_sparse_cluster(
     const InputData &d,
     const RoadMatrix &rm,
     int neighbors,
     int sigma_rank,
     int kmeans_iters,
     int lanczos_dim,
     double eig_tol,
     unsigned seed,
     SpectralDiagnostics &diag
 ) {
     const int C = (int)d.customers.size();

     if (C == 0) return {};
     if (!rm.built) return round_robin_cluster(d);

     const int k_eff = max(1, min(d.K, C));
     diag.k_eff = k_eff;

     SparseAffinityGraph graph = build_sparse_road_affinity(
         d,
         rm,
         neighbors,
         sigma_rank
     );

     diag.candidate_arcs = graph.directed_candidate_arcs;
     diag.sparse_edges = graph.undirected_edges;

     if (!graph.local_scale.empty()) {
         vector<double> tmp = graph.local_scale;
         nth_element(
             tmp.begin(),
             tmp.begin() + tmp.size() / 2,
             tmp.end()
         );
         diag.median_local_scale = tmp[tmp.size() / 2];
     }

     if (graph.undirected_edges <= 0) {
         throw runtime_error(
             "Sparse road spectral produced an empty affinity graph"
         );
     }

     SparseEigenResult eig = smallest_sparse_lsym_eigenvectors(
         graph,
         k_eff,
         lanczos_dim,
         eig_tol,
         seed
     );

     diag.lanczos_dimension = eig.lanczos_dimension;
     diag.lanczos_steps = eig.lanczos_steps;
     diag.eig_converged = eig.converged;
     diag.eig_max_residual = eig.max_residual;

     if (
         (int)eig.eigenvectors.size() != C ||
         eig.eigenvectors.empty() ||
         (int)eig.eigenvectors[0].size() < k_eff
     ) {
         throw runtime_error(
             "Sparse eigensolver returned fewer than K_eff eigenvectors"
         );
     }

     vector<vector<double>> embedding = eig.eigenvectors;

     // Row normalization U -> Y, exactly as specified in the report.
     for (int i = 0; i < C; ++i) {
         double row_norm = 0.0;

         for (double v : embedding[i]) {
             row_norm += v * v;
         }

         row_norm = sqrt(max(row_norm, 1e-30));

         for (double &v : embedding[i]) {
             v /= row_norm;
         }
     }

     vector<int> assign = capacity_aware_kmeans_embedding(
         d,
         embedding,
         k_eff,
         kmeans_iters,
         seed
     );

     cerr << "[road_spectral_sparse]"
         << " candidate_arcs=" << diag.candidate_arcs
         << " sparse_edges=" << diag.sparse_edges
         << " k_eff=" << diag.k_eff
         << " lanczos_dim=" << diag.lanczos_dimension
         << " lanczos_steps=" << diag.lanczos_steps
         << " eig_residual=" << diag.eig_max_residual
         << " eig_converged=" << (diag.eig_converged ? 1 : 0)
         << "\n";

     return assign;
 }

 /* ---------------- Writers ---------------- */

 static double total_assignment_overload(
     const InputData &d,
     const vector<int> &assign
 ) {
     vector<double> load = cluster_loads(d, assign);
     double total = 0.0;

     for (double x : load) {
         total += max(0.0, x - d.capacity);
     }

     return total;
 }

 static void write_clusters_csv(
     const string &path,
     const InputData &d,
     const vector<int> &assign
 ) {
     ofstream out(path);

     if (!out.good()) {
         throw runtime_error("Could not write " + path);
     }

     // Keep this exact two-column contract for solver.cpp compatibility.
     out << "node,cluster\n";

     for (int i = 0; i < (int)d.customers.size(); ++i) {
         out << d.customers[i].node << "," << assign[i] << "\n";
     }
 }

 static void write_summary_csv(
     const string &path,
     const InputData &d,
     const vector<int> &assign,
     const TimingReport &timing,
     const SpectralDiagnostics &diag,
     const SavingsDiagnostics &savings
 ) {
     vector<int> count(d.K, 0);
     vector<double> load(d.K, 0.0);
     vector<double> cx(d.K, 0.0);
     vector<double> cy(d.K, 0.0);

     for (int i = 0; i < (int)d.customers.size(); ++i) {
         int k = assign[i];

         if (k < 0 || k >= d.K) continue;

         count[k]++;
         load[k] += d.customers[i].demand;

         if (d.customers[i].has_xy) {
             cx[k] += d.customers[i].lon;
             cy[k] += d.customers[i].lat;
         }
     }

     ofstream out(path);

     if (!out.good()) {
         throw runtime_error("Could not write " + path);
     }

     out
         << "requested_mode,effective_mode,road_cost_mode,"
         << "cluster,count,load,capacity,utilization,overload,"
         << "centroid_lon,centroid_lat,"
         << "parse_s,coordinate_s,road_matrix_s,method_s,"
         << "repair_s,polish_s,write_s,total_s,"
         << "k_eff,candidate_arcs,sparse_edges,"
         << "lanczos_dimension,lanczos_steps,"
         << "eig_converged,eig_max_residual,median_local_scale,"
         << "savings_variants_requested,savings_variants_feasible,"
         << "savings_best_variant,savings_target_routes,"
         << "savings_final_routes,savings_light_relocates,"
         << "savings_hard_feasible,savings_route_cost\n";

     out << fixed << setprecision(9);

     for (int k = 0; k < d.K; ++k) {
         double util = d.capacity > 0.0 ? load[k] / d.capacity : 0.0;
         double overload = max(0.0, load[k] - d.capacity);

         double lon = count[k] > 0 ? cx[k] / count[k] : 0.0;
         double lat = count[k] > 0 ? cy[k] / count[k] : 0.0;

         out
             << timing.requested_mode << ","
             << timing.effective_mode << ","
             << timing.road_cost_mode << ","
             << k << ","
             << count[k] << ","
             << load[k] << ","
             << d.capacity << ","
             << util << ","
             << overload << ","
             << lon << ","
             << lat << ","
             << timing.parse_s << ","
             << timing.coordinate_s << ","
             << timing.road_matrix_s << ","
             << timing.method_s << ","
             << timing.repair_s << ","
             << timing.polish_s << ","
             << timing.write_s << ","
             << timing.total_s << ","
             << diag.k_eff << ","
             << diag.candidate_arcs << ","
             << diag.sparse_edges << ","
             << diag.lanczos_dimension << ","
             << diag.lanczos_steps << ","
             << (diag.eig_converged ? 1 : 0) << ","
             << diag.eig_max_residual << ","
             << diag.median_local_scale << ","
             << savings.variants_requested << ","
             << savings.variants_feasible << ","
             << savings.best_variant << ","
             << savings.target_routes << ","
             << savings.final_routes << ","
             << savings.accepted_relocates << ","
             << (savings.hard_feasible ? 1 : 0) << ","
             << savings.best_route_cost
             << "\n";
     }
 }

 static void write_timing_csv(
     const string &path,
     const InputData &d,
     const TimingReport &timing,
     const SpectralDiagnostics &diag,
     const SavingsDiagnostics &savings
 ) {
     ofstream out(path);

     if (!out.good()) {
         throw runtime_error("Could not write " + path);
     }

     out
         << "requested_mode,effective_mode,road_cost_mode,"
         << "customers,K,capacity,"
         << "parse_s,coordinate_s,road_matrix_s,method_s,"
         << "repair_s,polish_s,write_s,total_s,"
         << "k_eff,candidate_arcs,sparse_edges,"
         << "lanczos_dimension,lanczos_steps,"
         << "eig_converged,eig_max_residual,median_local_scale,"
         << "fallback_used,"
         << "savings_variants_requested,savings_variants_feasible,"
         << "savings_best_variant,savings_target_routes,"
         << "savings_final_routes,savings_light_relocates,"
         << "savings_hard_feasible,savings_route_cost\n";

     out << fixed << setprecision(9)
         << timing.requested_mode << ","
         << timing.effective_mode << ","
         << timing.road_cost_mode << ","
         << d.customers.size() << ","
         << d.K << ","
         << d.capacity << ","
         << timing.parse_s << ","
         << timing.coordinate_s << ","
         << timing.road_matrix_s << ","
         << timing.method_s << ","
         << timing.repair_s << ","
         << timing.polish_s << ","
         << timing.write_s << ","
         << timing.total_s << ","
         << diag.k_eff << ","
         << diag.candidate_arcs << ","
         << diag.sparse_edges << ","
         << diag.lanczos_dimension << ","
         << diag.lanczos_steps << ","
         << (diag.eig_converged ? 1 : 0) << ","
         << diag.eig_max_residual << ","
         << diag.median_local_scale << ","
         << (diag.fallback_used ? 1 : 0) << ","
         << savings.variants_requested << ","
         << savings.variants_feasible << ","
         << savings.best_variant << ","
         << savings.target_routes << ","
         << savings.final_routes << ","
         << savings.accepted_relocates << ","
         << (savings.hard_feasible ? 1 : 0) << ","
         << savings.best_route_cost
         << "\n";
 }

 static void print_cluster_report(
     const InputData &d,
     const vector<int> &assign,
     const string &mode
 ) {
     vector<int> count(d.K, 0);
     vector<double> load(d.K, 0.0);

     for (int i = 0; i < (int)d.customers.size(); ++i) {
         int k = assign[i];

         if (0 <= k && k < d.K) {
             count[k]++;
             load[k] += d.customers[i].demand;
         }
     }

     double total_load = 0.0;
     double total_overload = 0.0;
     int empty = 0;

     for (int k = 0; k < d.K; ++k) {
         total_load += load[k];
         total_overload += max(0.0, load[k] - d.capacity);

         if (count[k] == 0) {
             empty++;
         }
     }

     cerr << "[cluster] mode=" << mode << "\n";
     cerr << "[cluster] total_load=" << total_load
         << " fleet_capacity=" << d.K * d.capacity
         << " total_overload=" << total_overload
         << " empty_clusters=" << empty
         << "\n";

     for (int k = 0; k < d.K; ++k) {
         cerr << "  cluster " << k
             << " count=" << count[k]
             << " load=" << load[k]
             << " util=" << (d.capacity > 0.0 ? load[k] / d.capacity : 0.0)
             << " overload=" << max(0.0, load[k] - d.capacity)
             << "\n";
     }
 }

 /* ---------------- Main ---------------- */

 int main(int argc, char **argv) {
     ios::sync_with_stdio(false);
     cin.tie(nullptr);

     const auto total_start = SteadyClock::now();

     try {
         string input_path = get_arg(argc, argv, "--input", "input.txt");
         string dataset_path = get_arg(argc, argv, "--dataset", "dataset.json");
         string out_path = get_arg(argc, argv, "--out", "clusters.csv");
         string summary_path = get_arg(
             argc,
             argv,
             "--summary",
             "cluster_summary.csv"
         );
         string timing_path = get_arg(
             argc,
             argv,
             "--timing",
             "cluster_timing.csv"
         );

         string requested_mode = lower_copy(
             get_arg(argc, argv, "--mode", "auto")
         );
         string mode = requested_mode;

         if (mode == "sparse_road_spectral") {
             mode = "road_spectral_sparse";
         }

         string road_cost_mode = lower_copy(
             get_arg(argc, argv, "--road_cost", "time")
         );

         int iters = stoi(get_arg(argc, argv, "--iters", "80"));
         int spectral_neighbors = stoi(
             get_arg(argc, argv, "--spectral_neighbors", "8")
         );
         int spectral_sigma_rank = stoi(
             get_arg(
                 argc,
                 argv,
                 "--spectral_sigma_rank",
                 to_string(spectral_neighbors)
             )
         );

         string lanczos_default = get_arg(
             argc,
             argv,
             "--spectral_eig_iters",
             "0"
         );
         int spectral_lanczos_dim = stoi(
             get_arg(
                 argc,
                 argv,
                 "--spectral_lanczos_dim",
                 lanczos_default
             )
         );

         double spectral_eig_tol = stod(
             get_arg(argc, argv, "--spectral_eig_tol", "1e-8")
         );

         int savings_variants = stoi(
             get_arg(argc, argv, "--savings_variants", "8")
         );
         double savings_noise = stod(
             get_arg(argc, argv, "--savings_noise", "0.025")
         );
         int savings_target_routes = stoi(
             get_arg(argc, argv, "--savings_target_routes", "0")
         );
         int savings_target_extra_routes = stoi(
             get_arg(argc, argv, "--savings_target_extra_routes", "1")
         );
         int savings_light_polish_rounds = stoi(
             get_arg(argc, argv, "--savings_light_polish_rounds", "2")
         );
         double savings_polish_time_s = stod(
             get_arg(argc, argv, "--savings_polish_time_s", "0.50")
         );
         const string savings_tw_raw = lower_copy(
             get_arg(argc, argv, "--savings_check_tw", "true")
         );
         const bool savings_check_tw =
             savings_tw_raw != "0" &&
             savings_tw_raw != "false" &&
             savings_tw_raw != "no" &&
             savings_tw_raw != "off";

         unsigned seed = (unsigned)stoul(
             get_arg(argc, argv, "--seed", "42")
         );

         if (road_cost_mode != "time" && road_cost_mode != "distance") {
             throw runtime_error("--road_cost must be time or distance");
         }

         if (spectral_neighbors <= 0) {
             throw runtime_error("--spectral_neighbors must be positive");
         }

         if (spectral_sigma_rank <= 0) {
             throw runtime_error("--spectral_sigma_rank must be positive");
         }

         if (spectral_eig_tol <= 0.0) {
             throw runtime_error("--spectral_eig_tol must be positive");
         }

         if (savings_variants <= 0) {
             throw runtime_error("--savings_variants must be positive");
         }
         if (savings_noise < 0.0) {
             throw runtime_error("--savings_noise must be non-negative");
         }
         if (savings_target_routes < 0) {
             throw runtime_error("--savings_target_routes must be non-negative");
         }
         if (savings_target_extra_routes < 0) {
             throw runtime_error("--savings_target_extra_routes must be non-negative");
         }
         if (savings_light_polish_rounds < 0) {
             throw runtime_error("--savings_light_polish_rounds must be non-negative");
         }
         if (savings_polish_time_s < 0.0) {
             throw runtime_error("--savings_polish_time_s must be non-negative");
         }

         TimingReport timing;
         timing.requested_mode = requested_mode;
         timing.effective_mode = mode;
         timing.road_cost_mode = road_cost_mode;

         SpectralDiagnostics spectral_diag;
         SavingsDiagnostics savings_diag;

         auto t0 = SteadyClock::now();
         InputData d = parse_input_txt(input_path);
         auto t1 = SteadyClock::now();
         timing.parse_s = seconds_between(t0, t1);

         t0 = SteadyClock::now();
         auto coords = parse_dataset_coords(dataset_path);
         attach_coords(d, coords);
         bool has_coords = all_customers_have_coords(d, coords);
         t1 = SteadyClock::now();
         timing.coordinate_s = seconds_between(t0, t1);

         cerr << "[cluster] input=" << input_path << "\n";
         cerr << "[cluster] dataset=" << dataset_path << "\n";
         cerr << "[cluster] requested_mode=" << requested_mode << "\n";
         cerr << "[cluster] N=" << d.N
             << " M=" << d.M
             << " K=" << d.K
             << " depot=" << d.depot
             << " customers=" << d.customers.size()
             << " capacity=" << d.capacity
             << "\n";
         cerr << "[cluster] coords_loaded=" << coords.size()
             << " all_customer_coords=" << (has_coords ? 1 : 0)
             << "\n";

         bool wants_road =
             mode == "auto" ||
             mode == "road_savings" ||
             mode == "network_kmedoids" ||
             mode == "route_split" ||
             mode == "road_spectral_lite" ||
             mode == "road_spectral_sparse";

         RoadMatrix rm;
         RoadMatrix time_rm;

         if (wants_road) {
             cerr << "[cluster] building road matrix cost="
                 << road_cost_mode << "\n";

             t0 = SteadyClock::now();
             rm = build_road_matrix(d, road_cost_mode);
             t1 = SteadyClock::now();

             timing.road_matrix_s = seconds_between(t0, t1);

             cerr << "[cluster] road_matrix_built="
                 << (rm.built ? 1 : 0)
                 << " road_matrix_s=" << timing.road_matrix_s
                 << "\n";

             const bool may_run_savings =
                 mode == "road_savings" || mode == "auto";

             if (may_run_savings && road_cost_mode != "time") {
                 cerr << "[cluster] building separate time matrix for "
                     << "Savings hard-TW validation\n";

                 t0 = SteadyClock::now();
                 time_rm = build_road_matrix(d, "time");
                 t1 = SteadyClock::now();

                 const double time_matrix_s = seconds_between(t0, t1);
                 timing.road_matrix_s += time_matrix_s;

                 cerr << "[cluster] savings_time_matrix_built="
                     << (time_rm.built ? 1 : 0)
                     << " savings_time_matrix_s=" << time_matrix_s
                     << "\n";
             }
         }

         if (mode == "auto") {
             if (rm.built) {
                 mode = "road_savings";
             } else if (has_coords) {
                 mode = "sweep";
             } else {
                 mode = "round_robin";
             }
         }

         vector<int> assign;

         t0 = SteadyClock::now();

         if (mode == "round_robin") {
             assign = round_robin_cluster(d);

         } else if (mode == "sweep") {
             if (!has_coords) {
                 cerr << "[cluster] sweep needs coordinates;"
                     << " fallback round_robin\n";
                 spectral_diag.fallback_used = true;
                 mode = "round_robin";
                 assign = round_robin_cluster(d);
             } else {
                 assign = sweep_cluster(d, coords);
             }

         } else if (mode == "balanced_kmeans" || mode == "kmeans") {
             if (!has_coords) {
                 cerr << "[cluster] balanced_kmeans needs coordinates;"
                     << " fallback round_robin\n";
                 spectral_diag.fallback_used = true;
                 mode = "round_robin";
                 assign = round_robin_cluster(d);
             } else {
                 mode = "balanced_kmeans";
                 assign = balanced_kmeans_cluster(d, coords, iters, seed);
             }

         } else if (mode == "kd_split") {
             if (!has_coords) {
                 cerr << "[cluster] kd_split needs coordinates;"
                     << " fallback round_robin\n";
                 spectral_diag.fallback_used = true;
                 mode = "round_robin";
                 assign = round_robin_cluster(d);
             } else {
                 assign = kd_split_cluster(d, coords);
             }

         } else if (mode == "spatial_grid") {
             if (!has_coords) {
                 cerr << "[cluster] spatial_grid needs coordinates;"
                     << " fallback round_robin\n";
                 spectral_diag.fallback_used = true;
                 mode = "round_robin";
                 assign = round_robin_cluster(d);
             } else {
                 assign = spatial_grid_cluster(d, coords);
             }

         } else if (mode == "spectral_lite") {
             if (!has_coords) {
                 cerr << "[cluster] spectral_lite needs coordinates;"
                     << " fallback round_robin\n";
                 spectral_diag.fallback_used = true;
                 mode = "round_robin";
                 assign = round_robin_cluster(d);
             } else if ((int)d.customers.size() > 120) {
                 cerr << "[cluster] spectral_lite C="
                     << d.customers.size()
                     << " exceeds dense limit;"
                     << " effective_mode=balanced_kmeans\n";
                 spectral_diag.fallback_used = true;
                 mode = "balanced_kmeans";
                 assign = balanced_kmeans_cluster(
                     d,
                     coords,
                     iters,
                     seed
                 );
             } else {
                 assign = spectral_lite_cluster(
                     d,
                     coords,
                     spectral_neighbors,
                     iters,
                     seed
                 );
             }

         } else if (mode == "road_savings") {
             if (!rm.built) {
                 cerr << "[cluster] road_savings needs road matrix;"
                     << " fallback round_robin\n";
                 spectral_diag.fallback_used = true;
                 mode = "round_robin";
                 assign = round_robin_cluster(d);
             } else {
                 const RoadMatrix &savings_time_rm =
                     road_cost_mode == "time" ? rm : time_rm;

                 assign = road_savings_cluster(
                     d,
                     rm,
                     savings_time_rm,
                     savings_variants,
                     savings_noise,
                     savings_target_routes,
                     savings_target_extra_routes,
                     savings_light_polish_rounds,
                     savings_polish_time_s,
                     savings_check_tw,
                     seed,
                     savings_diag
                 );
             }

         } else if (mode == "network_kmedoids") {
             if (!rm.built) {
                 cerr << "[cluster] network_kmedoids needs road matrix;"
                     << " fallback round_robin\n";
                 spectral_diag.fallback_used = true;
                 mode = "round_robin";
                 assign = round_robin_cluster(d);
             } else {
                 assign = network_kmedoids_cluster(
                     d,
                     rm,
                     iters,
                     seed
                 );
             }

         } else if (mode == "route_split") {
             if (!rm.built) {
                 cerr << "[cluster] route_split needs road matrix;"
                     << " fallback round_robin\n";
                 spectral_diag.fallback_used = true;
                 mode = "round_robin";
                 assign = round_robin_cluster(d);
             } else {
                 assign = route_split_cluster(d, rm);
             }

         } else if (mode == "road_spectral_lite") {
             if (!rm.built) {
                 cerr << "[cluster] road_spectral_lite needs road matrix;"
                     << " fallback round_robin\n";
                 spectral_diag.fallback_used = true;
                 mode = "round_robin";
                 assign = round_robin_cluster(d);
             } else if ((int)d.customers.size() > 120) {
                 cerr << "[cluster] road_spectral_lite C="
                     << d.customers.size()
                     << " exceeds dense Jacobi limit;"
                     << " effective_mode=network_kmedoids\n";
                 spectral_diag.fallback_used = true;
                 mode = "network_kmedoids";
                 assign = network_kmedoids_cluster(
                     d,
                     rm,
                     iters,
                     seed
                 );
             } else {
                 assign = road_spectral_lite_cluster(
                     d,
                     rm,
                     spectral_neighbors,
                     iters,
                     seed
                 );
             }

         } else if (mode == "road_spectral_sparse") {
             if (!rm.built) {
                 throw runtime_error(
                     "road_spectral_sparse requires a complete road matrix"
                 );
             }

             if (!has_coords) {
                 throw runtime_error(
                     "road_spectral_sparse requires dataset.json coordinates "
                     "for the projected-coordinate KD-tree candidate graph"
                 );
             }

             assign = road_spectral_sparse_cluster(
                 d,
                 rm,
                 spectral_neighbors,
                 spectral_sigma_rank,
                 iters,
                 spectral_lanczos_dim,
                 spectral_eig_tol,
                 seed,
                 spectral_diag
             );

         } else {
             cerr << "Unknown mode: " << mode << "\n";
             cerr
                 << "Use --mode auto | round_robin | sweep | "
                 << "balanced_kmeans | kmeans | kd_split | spatial_grid | "
                 << "spectral_lite | road_savings | network_kmedoids | "
                 << "route_split | road_spectral_lite | "
                 << "road_spectral_sparse | sparse_road_spectral\n";
             return 1;
         }

         t1 = SteadyClock::now();
         timing.method_s = seconds_between(t0, t1);
         timing.effective_mode = mode;

         ensure_valid_assignments(d, assign);

         if (rm.built) {
             // Both paper methods use overload repair. The spectral method
             // additionally performs road-cost assignment polish, while
             // directed Clarke-Wright Savings remains Savings + repair.
             t0 = SteadyClock::now();
             repair_overloaded_clusters(d, rm, assign);
             t1 = SteadyClock::now();
             timing.repair_s += seconds_between(t0, t1);

             const bool paper_spectral_polish =
                 mode == "road_spectral_sparse" ||
                 mode == "road_spectral_lite";

             if (paper_spectral_polish) {
                 t0 = SteadyClock::now();
                 road_assignment_polish(d, rm, assign, 3);
                 t1 = SteadyClock::now();
                 timing.polish_s += seconds_between(t0, t1);

                 t0 = SteadyClock::now();
                 repair_overloaded_clusters(d, rm, assign);
                 t1 = SteadyClock::now();
                 timing.repair_s += seconds_between(t0, t1);
             }
         }

         ensure_valid_assignments(d, assign);

         const double final_overload =
             total_assignment_overload(d, assign);

         if (rm.built && final_overload > 1e-7) {
             throw runtime_error(
                 "Hard-feasibility check failed: clustering overload remains " +
                 to_string(final_overload)
             );
         }

         const auto write_start = SteadyClock::now();

         write_clusters_csv(out_path, d, assign);

         timing.write_s = seconds_between(
             write_start,
             SteadyClock::now()
         );
         timing.total_s = seconds_between(
             total_start,
             SteadyClock::now()
         );

         // First write with measured values.
         write_summary_csv(
             summary_path,
             d,
             assign,
             timing,
             spectral_diag,
             savings_diag
         );
         write_timing_csv(
             timing_path,
             d,
             timing,
             spectral_diag,
             savings_diag
         );

         // Refresh final write/total timings and rewrite the evidence files.
         timing.write_s = seconds_between(
             write_start,
             SteadyClock::now()
         );
         timing.total_s = seconds_between(
             total_start,
             SteadyClock::now()
         );

         write_summary_csv(
             summary_path,
             d,
             assign,
             timing,
             spectral_diag,
             savings_diag
         );
         write_timing_csv(
             timing_path,
             d,
             timing,
             spectral_diag,
             savings_diag
         );

         cerr << "[cluster] effective_mode="
             << timing.effective_mode << "\n";
         cerr << "[cluster] wrote " << out_path << "\n";
         cerr << "[cluster] wrote " << summary_path << "\n";
         cerr << "[cluster] wrote " << timing_path << "\n";

         cerr << fixed << setprecision(6)
             << "[cluster-timing]"
             << " requested_mode=" << timing.requested_mode
             << " effective_mode=" << timing.effective_mode
             << " parse_s=" << timing.parse_s
             << " coordinate_s=" << timing.coordinate_s
             << " road_matrix_s=" << timing.road_matrix_s
             << " method_s=" << timing.method_s
             << " repair_s=" << timing.repair_s
             << " polish_s=" << timing.polish_s
             << " write_s=" << timing.write_s
             << " total_s=" << timing.total_s
             << "\n";

         print_cluster_report(
             d,
             assign,
             timing.effective_mode
         );

         return 0;

     } catch (const exception &e) {
         cerr << "[cluster] ERROR: " << e.what() << "\n";
         return 1;
     }
 }
