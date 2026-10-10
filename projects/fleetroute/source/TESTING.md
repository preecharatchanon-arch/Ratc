# FleetRoute Routing Workspace — Release Validation

The release gate checks product semantics, native execution, evidence truth, performance-sensitive behavior, and UI contracts—not only syntax.

## High-risk contracts

- Bundled native sources pass standard C++17 syntax checks and the integrated routing optimizer executes through the real application wrapper.
- Every emitted optimizer CLI flag is recognized; FleetRoute-managed lifecycle/I/O flags cannot be duplicated or overridden by research extras.
- Distance, time, and hybrid semantics match the independent application evaluator, including directed parallel edges and tight time windows. Objective-specific routing contexts reject cross-objective reuse, and the final publication transaction rejects a candidate if the live objective changed during the run.
- Fleet size remains a maximum ceiling; warm-start and final evidence report active routes separately from maximum available vehicles.
- App-provided clustering must pass independent assignment checks and a native hard-feasibility receipt.
- Plan → scenario → clustering → optimization → independent validation → route publication → evidence → Convergence Lab passes end-to-end with a frozen settings snapshot.
- A cancelled rerun preserves the previous route/evidence bundle.
- A completed valid-but-worse rerun cannot degrade the protected published route.
- Convergence reports are accepted only when their source manifest matches raw telemetry; unchanged reports may be reused and changed telemetry must rebuild.
- Live optimization monitoring accepts only validated construction/process-wide incumbent events, rejects objective regressions, persists the final curve through success/failure/cancellation, bounds heartbeat payload size, and never infers global best from worker-local search values. The compact search zoom must preserve and label the true off-scale start without synthetic points.
- Routing watchdog tests prove that road-cost preparation may exceed the post-search grace without stealing search budget, while a real post-marker overrun is still terminated. Process/preparation/search/validation timings remain separately auditable and are surfaced in the terminal Evidence & Logs view.
- Route-state wording distinguishes prepared, running, optimized, reviewed, and stale states across Control Center, Driver, Simulation, and exports.
- Launch credentials move into an HttpOnly cookie, leave the URL, and are never persisted by the frontend.
- International map setup preserves per-region verification receipts, invalidates the active graph on source changes, and safely reuses matching regional caches.
- Geofabrik `*-latest.osm.pbf` redirects are accepted only when they resolve to the same extract family; the dated PBF and dated MD5 sidecar must identify the same snapshot. Resume is permitted only for that exact snapshot/checksum identity, cancellation propagates immediately, and checksum corruption triggers one clean re-resolution/retry.
- The catalog audits every exposed PBF URL and keeps parent countries navigable when only state/province/subregion extracts are downloadable.
- Navigation map surfaces use OpenStreetMap plus a local neutral fallback; Terrain uses keyless-access topographic tiles with per-tile OpenStreetMap fallback so provider errors still render a real street map.
- Performance contracts guard against full-road spatial-index construction on ordinary map clicks, duplicate native builds, redundant compiler probes/UI polling, repeated Geofabrik catalog transforms, stale road-viewport responses, and repeated heavy convergence analysis.
- System-hardening regression tests cover exact accelerated road snapping against exhaustive projected geometry, 450-stop access/materialization scaling, streamed/resumed PBF integrity, visible native/Osmium lock waiting, cold FastAPI startup, and a controlled fresh-state → independently validated → atomically published native-solver route.
- Responsive/accessibility contracts include unique IDs, keyboard focus, search/listbox semantics, live regions, reduced-motion handling, mobile breakpoints, explicit button types, and visible failure/retry states.

## Release checks

The internal regression suite covers:

- runtime/API contracts;
- directed-road speed and map behavior;
- feasibility-safe scenario generation;
- actual native optimizer handoff;
- maximum-fleet semantics;
- guided workflow and runtime inspector;
- performance/system behavior;
- optimizer/convergence state;
- user-facing startup/log presentation;
- command and evidence contracts;
- full solver/evidence handoff;
- clustering safety;
- transactional rerun protection;
- objective semantic alignment;
- route-state truth across application surfaces;
- responsive map-first overview.

Integration tests may use exact-source precompiled test binaries to avoid repeatedly spending minutes optimizing the very large native translation unit. This changes only test compilation cost. Production continues to use the fingerprinted `-O3 -DNDEBUG -std=c++17 -pthread` build.

## Production hardening release gates

The polished notebook release adds several checks that should remain true in future edits:

- **Single operational mutation slot:** the idle check and job creation are protected by one process lock. Concurrent tabs or a double-click may create at most one road-source, graph, scenario, clustering, or solver job.
- **Diff-safe settings writes:** partial fleet and solver updates are serialized and merged with the latest saved contract, so concurrent partial edits cannot silently reset an unrelated field.
- **Fail-closed source coverage:** after a depot or work point exists, a downloaded PBF is not operational merely because its checksum is valid. The exact selected region boundary must be known and cover every active plan point.
- **Finite numeric contract:** both API validation and direct engine entry points reject NaN/infinite coordinates or operating values; edited coordinates are range-checked before road access is invalidated.
- **Solver commit isolation:** a completed candidate is applied only if the click-time input/settings/source contract still matches the active plan. Otherwise the previous published route remains intact and the stale candidate is rejected with evidence.
- **Accessible destructive/expensive confirmations:** large operating-span approval uses the application dialog (including Escape/backdrop cancellation) rather than a browser-native confirm, and dynamic place controls expose accessible names.

For a release candidate, run Python compilation, JavaScript syntax validation, the native C++ production builds, a fresh authenticated API launch, and a decode/re-extract manifest audit from the final `.ipynb` rather than only from the loose source tree.
