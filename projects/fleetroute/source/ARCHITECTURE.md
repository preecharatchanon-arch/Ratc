# FleetRoute Routing Workspace — Architecture

## 1. Separation of responsibility

**Application/control plane** owns operational truth: fleet and plan settings, regional road-source identity, directed-road materialization, objective semantics, time windows, multi-trip policy, clustering validation, native-process supervision, independent route validation, transactional publication, evidence retention, incidents, driver exports, and UI state.

**Native routing optimizer** owns internal search: parallel trajectories, neighborhood selection, incumbent evolution, archive/intensification behavior, and search scheduling. Production mode does not expose those internals as everyday operator controls.

This separation lets the optimizer evolve without changing what the product's distance, time, capacity, fleet, validation, or publication semantics mean.

## 2. Map-first regional source model

The first-run workspace is geographic rather than form-first:

1. Load any previously verified regional sources immediately from the runtime-local cache (or from persistent mounted storage when `VRP_OSM_DATA_DIR` is configured accordingly).
2. Load the external region catalog and boundary geometry when available.
3. Hover/search/select a country or smaller extract on the world map.
4. Choose a recommended verified PBF, a smaller extract, or an existing local cached source.
5. Record the exact region/source identity in graph and evidence provenance.

Changing the selected region invalidates the active operating graph immediately. Verified regional files and prepared graph caches remain isolated by source/checksum identity and may be safely reused when switching back.

## 3. Data and route-truth pipeline

1. Depot/work points, fleet settings, regional road source, and active closure revision define the source contract.
2. FleetRoute atomically materializes `input.txt`, `dataset.json`, and `dataset_summary.json`.
3. Materialized files are independently cross-checked and hashed.
4. A deterministic feasible baseline may be published only as an explicitly labeled initial plan.
5. The native optimizer runs in a private attempt directory using a frozen settings/materialization snapshot.
6. Returned routes are parsed and independently recomputed against the application road model using an objective-matched routing context.
7. Capacity, time windows, depot return, trip rules, work-point coverage, distance, duration, and objective are validated independently. Distance/hybrid certification can reuse exact terminal-pair metrics from that same selected-path context; publication still reconstructs real road geometry.
8. The candidate is compared with the protected published route.
9. Only a complete valid commit promotes public solver artifacts. A valid-but-worse attempt can retain execution evidence while preserving the better route.

## 4. Fleet semantics

Fleet size is a **maximum available fleet**. Empty vehicles are permitted and omitted from the published route plan. Optional clustering may choose fewer active clusters for construction while the optimizer still receives the full available-fleet ceiling.

## 5. Operational objective semantics

- **Distance:** directed-road metres.
- **Time:** static edge-speed travel time plus waiting/service under the route schedule.
- **Hybrid:** `distance_m + 0.25 × route_duration_s`.

The application validator and native optimizer are regression-tested against the same public contract, including directed parallel edges and tight time-window cases.

## 6. Native build and process supervision

Production compilation uses a source/compiler/flag fingerprint, a cross-process build lock, temporary output, executable validation, and atomic publication. The public UI can start before the optimized build finishes; an early optimization request converges on the same locked build rather than spawning a competing compiler.

Every native process has explicit START/EXIT/TIMEOUT/CANCEL/LAUNCH-ERROR lifecycle evidence. For routing, the outer supervisor separates native road-cost preparation from governed search: preprocessing has a graph-scaled hang guard, and the search watchdog begins only after the solver emits its budget-start receipt. stdout, stderr, merged native stream, and FleetRoute audit information remain separately inspectable.

## 7. Transactional artifacts and rollback

Every attempt writes privately under its own attempt directory. Public route/evidence artifacts are promoted only through the commit gate. Cancellation, timeout, invalid output, launch failure, and incomplete evidence preserve the previous verified route. A completed valid-but-worse result cannot degrade the protected published plan.

Evidence archives are built to temporary files and atomically published. Path containment and symlink checks prevent exports from escaping the intended runtime tree.

## 8. Convergence evidence

Native telemetry includes worker-local values and a process-wide best-so-far signal. The interactive live curve consumes only validated construction/incumbent events; it never promotes a worker-local best or an unvalidated search state. These native stderr events are folded into the normal 0.5 s job heartbeat, avoiding incremental convergence-file writes or a second solver-side global-best mechanism. The true construction start remains part of the numeric receipt; the compact monitor may use a clearly labeled search zoom when that start would flatten later improvements. Sampling is wall-clock bounded so logging does not dominate optimization. Analysis stores a source manifest containing the raw telemetry SHA-256. A matching report may be reused; a changed hash requires a true rebuild.

## 9. Regional road-source integrity

Regional PBF downloads are staged, validated against trusted source metadata, and only then atomically replace the active copy. Verification receipts are stored per region. Local size/mtime identity is checked before reporting a source ready, so a modified file cannot silently remain trusted.

External region sources are restricted to expected HTTPS provider paths and sanitized region IDs. Road-extraction tooling is installed lazily under a lock only when an uncached extract needs it.

## 10. Performance model

- The runtime-local source cache renders before remote region geometry finishes loading, and the processed Geofabrik catalog is reused in-process until the source file changes or an explicit refresh is requested.
- Normal map clicks use a lightweight local candidate search before falling back to the global projected spatial index.
- Road-viewport fetches cancel superseded requests and reject stale generations; graph identity changes clear the previous road overlay immediately.
- Prepared regional graph caches use hard-link-or-copy semantics where possible.
- Road-access snapping uses a conservative geographic edge grid plus exact projected geometry. Nearest-node distance supplies a valid upper bound, grid/bounds pruning removes impossible edges, and the final edge is still chosen by exact Shapely distance; pathological far-away queries fall back to the exact global spatial index.
- PBF integrity is accumulated during transfer and verified before atomic publication; same-filesystem runtime staging uses hard links where possible.
- Uncached graph construction filters directly to OSM XML when supported, avoiding an intermediate roads-PBF pass; the compatible PBF-to-XML path remains as a correctness fallback.
- Cell 2 verifies a source/binary/build-marker readiness receipt instead of repeating the heavy native preparation path after Cell 1; any mismatch falls back safely to full verification.
- Browser live state uses SSE where the host supports it and bounded polling for Quick Tunnels; a single view-aware heartbeat handles local presentation refreshes instead of multiple permanent polling loops.
- Optimizer log parsing and compiler identity checks are cached when their underlying inputs have not changed.
- In-memory road routing contexts are keyed by both materialized graph identity and objective mode; objective changes cannot reuse incompatible shortest-path predecessors.
- Process wall time, directed-road preparation time, governed search time, and independent validation time are measured separately so preprocessing cannot consume or misreport the user's search budget.

## 11. Security boundary

The application listens on loopback in Colab. Authentication is established by a one-time launch credential and moved into an HttpOnly SameSite cookie. The public URL is immediately cleaned, browser credential persistence is prohibited, and static/API caching is controlled. Security headers apply to authenticated and login responses.

The temporary tunnel fallback is pinned and checksum-verified. FleetRoute is designed as a single authenticated operations workspace, not as a multi-tenant SaaS security boundary.

## 12. Provenance

Exact native source lineage, source SHA-256, production compilation flags, and narrow compatibility adaptations are recorded in `solver_provenance.json`. Those details are retained for reproducibility and auditing; the normal user experience deliberately presents product-level concepts instead of development-generation labels.
