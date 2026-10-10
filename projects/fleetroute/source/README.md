# FleetRoute Routing Workspace

FleetRoute is a real-road fleet planning and decision-support workspace for **delivery, pickup, collection, distribution, and field operations**. It turns a depot, work points, fleet constraints, time windows, road closures, and a directed OpenStreetMap road graph into independently validated multi-vehicle plans, driver-ready outputs, and reproducible operational evidence.

## Production contract

- Fleet size means **maximum available vehicles**, not a required number of active routes.
- FleetRoute owns operational semantics: objective, runtime, worker ceiling, time-window and multi-trip settings, materialization, warm-start validation, independent route validation, transactional publication, and evidence.
- The native routing optimizer owns its internal search schedule, neighborhoods, operator selection, and incumbent evolution. Production mode intentionally does not expose or inject low-level research tuning.
- Distance uses directed-road metres. Time uses static edge-speed travel time plus waiting and service. Hybrid is `distance_m + 0.25 × route_duration_s`.
- A deterministic prepared route is explicitly labeled **INITIAL PLAN**. Optimization is complete only after the native optimizer returns and FleetRoute independently validates the candidate.
- A valid but worse completed candidate is retained as execution evidence but cannot degrade the protected published route.
- Cancellation, timeout, launch failure, invalid output, or incomplete evidence cannot erase the last complete valid route/evidence bundle.
- FleetRoute does not claim mathematical optimality, live GPS tracking, or vehicle-specific legal clearance simply because a route passes operational validation.

## Map-first operating-region setup

A fresh workspace opens with the operating-region selector rather than a country dropdown. Operators can hover or search the world map, select a country or smaller regional extract, and then choose the recommended verified road source or reuse a previously verified source from the runtime-local cache. The default Colab cache lasts only for the current runtime unless `VRP_OSM_DATA_DIR` points to persistent mounted storage.

FleetRoute uses the selected regional source as part of graph and evidence identity. Changing region immediately invalidates the active operating graph so a previous region cannot be reused accidentally, while checksum-keyed prepared caches remain available for fast safe reuse when returning to a previously verified region.

Navigation maps use keyless OpenStreetMap tiles with a neutral local fallback. Terrain uses Esri World Topographic tiles and falls back tile-by-tile to the matching OpenStreetMap street tile, so a temporary topographic-provider error does not collapse the operational map into a diagnostic grid. The searchable region browser remains available as a resilient fallback if live boundary geometry is unavailable.

## Optimizer controls

The everyday Optimizer surface is intentionally small: maximum trucks, capacity per truck, fleet departure time, maximum runtime, maximum parallel workers, objective, time-window enforcement, and multi-trip policy. Warm-start clustering, random seed/reproducibility, convergence-report generation, and expert/native overrides stay under **Advanced · research & reproducibility**.

FleetRoute manages the operating contract while the routing optimizer manages its internal search. Expert research overrides require an explicit deployment-level research switch. Managed lifecycle, I/O, validation, and evidence flags cannot be overridden by raw extras.

## Independent validation and publication

Every optimization attempt runs in an isolated private attempt directory before any published artifact can change. The commit gate requires process success, parseable routes, exact independent feasibility validation, and comparison against the protected published route. Shortest-path validation contexts are objective-specific: changing Distance/Time/Hybrid may reuse the same materialized road graph, but it can never reuse a predecessor forest built for another objective. The objective is rechecked again inside the final route-publication transaction.

Validation checks include:

- work-point coverage and duplication;
- directed-road reachability;
- vehicle capacity;
- time-window arrival, waiting, service, and depot return;
- trip-count rules;
- distance, duration, and hybrid objective semantics;
- maximum available fleet usage.

A failed, cancelled, invalid, or worse attempt cannot silently replace the current verified plan.

## Evidence and observability

A complete solve retains the materialized problem, source hashes, frozen settings, native invocation receipt, stdout, stderr, convergence telemetry, run summary, route evidence, and relevant clustering receipts. Exact native-source lineage and source hashes are recorded in `solver_provenance.json`; normal product screens intentionally use operator-facing terminology rather than internal development labels.

Convergence reports include the raw telemetry identity. An existing report is reused only when its `SourceManifest` matches the current telemetry SHA-256; changed telemetry forces a genuine rebuild. The live monitor keeps the true validated construction objective in its receipt; when that first value is a large outlier, only the compact popup may zoom to the subsequent validated search range and marks the original start as off-scale rather than inventing or rescaling objective values.

Native road-cost preparation and governed search use separate clocks. Directed pair-cost construction is protected by its own hang guard, while the user-selected optimization budget begins at the native `[BudgetScope]` marker. Evidence records total process wall time, road-preparation time, governed search time, and independent validation time separately.

## Road incidents and stale-state handling

Approved closures modify the exact directed operating edge, plus at most one geometry-matched reverse edge when a two-way closure is requested. Graph, source, input, fleet, or closure changes mark dependent routes/evidence historical rather than silently relabeling them current.

Regional PBF files are trusted only after source verification. FleetRoute follows Geofabrik’s current `*-latest` redirect contract, pins the resolved dated PBF to the matching dated checksum, and never resumes partial bytes across snapshot versions. A file modified after verification loses its ready state. Downloads are staged and verified before atomic publication, so a failed refresh cannot replace a known-good source.

## Security and deployment boundary

The Colab launcher binds the application to loopback and exposes it through a temporary HTTPS tunnel. A one-time launch credential is verified server-side, moved into an HttpOnly SameSite cookie, and removed from the URL. The browser does not persist that credential in local storage or append it to driver/simulation links.

Security headers include content-security, anti-framing, MIME-sniffing, and referrer protections. The fallback tunnel binary is version-pinned and checksum-verified. FleetRoute remains a single authenticated operations workspace; it should not be represented as a hardened multi-tenant SaaS without additional identity, authorization, secrets-management, backup, and infrastructure controls.

## Colab launch

Run the generated two-cell notebook from top to bottom.

Cell 1 verifies the embedded application, reuses an intact existing release when possible, installs only missing/incompatible Python dependencies, and prepares runtime directories. It then prepares both the clustering engine and routing optimizer using the exact production flags `-O3 -DNDEBUG -std=c++17 -pthread`. The first build can take several minutes; progress and elapsed time stay visible. Matching source/compiler/flags reuse the cached binaries. Build errors stop setup before any launch link is shown.

Cell 2 first verifies the lightweight native-readiness receipt written by Cell 1. When the source files, executable hashes, and build markers still match, it starts the server without importing the heavy routing backend or probing the compiler again; any mismatch falls back to the normal preparation path. It then verifies the local app, checks the public HTTPS health response against this launch's unique instance ID, and requests the authenticated entry page and main script. It prints a launch link only after these checks pass, with at most three bounded tunnel attempts. Keep cell 2 running; stopping it closes the link. Restart cell 2 and use the newest link after a runtime/tunnel interruption. Startup checks from the notebook cannot guarantee another device's DNS or future Cloudflare availability.

Quick Tunnel links use job polling because Cloudflare Quick Tunnels do not support Server-Sent Events. Polling includes live logs, optimizer trace, final results, and scenario-to-optimizer handoff. The live Optimization Monitor is driven only by the native solver's validated process-wide incumbent events; the backend folds those events into the normal job heartbeat, so no extra convergence-file polling or hot-loop writer is introduced. Other hosts may use SSE with a stalled-stream polling watchdog. Road-viewport requests are cancellable and generation-checked so an older pan/zoom response cannot overwrite a newer viewport or survive an operating-graph change.

Road-extraction tooling is still installed lazily when an uncached regional extract requires it. Regional downloads, graph preparation, clustering execution, and optimizer search remain real jobs with their own progress; ready engines do not mean road data or routes have already been computed.
