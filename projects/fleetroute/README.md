# FleetRoute: Bounded-Authority Route Optimization for Auditable Real-Road Fleet Operations

**Author:** Ratchanon Preecha  
**Status:** Submitted to the Innovative Applications of Artificial Intelligence Conference (IAAI-27); acceptance is not claimed.

FleetRoute develops a routing algorithm into an inspectable application. Real road networks are represented as directed graphs, and candidate routes pass explicit validation before the system reports a result. Bounded execution, progress telemetry, and structured receipts make the optimization process auditable.

## Project and source

- [Read the paper (PDF)](paper.pdf)
- [Complete submission supplement and restoration instructions](supplement/README.md)
- [Application notebook](FleetRoute_App.ipynb)
- [Current solver](../../solvers/current/README.md)
- [Versioned solver sources](../../solvers/README.md)
- [Submission evidence](evidence/submission.png)
- [Third-party data notice](THIRD_PARTY_DATA_NOTICE.md)

The work extends the NSC 2026 finalist project **ระบบเพิ่มประสิทธิภาพเส้นทางรถเก็บขยะหลายคัน บนโครงข่ายถนนจริงด้วยอัลกอริทึมไฮบริดเมตาฮิวริสติก**. Its [NSC reports and finalist presentation](../nsc-2026/README.md) document Legacy at the regional stage and V31 at the finalist stage. Planner and driver workflows already existed in the finalist application. The subsequent IAAI work expands the Thailand-only PBF workflow to international region selection and strengthens road-data handling, spatial indexing, backend execution, validation, lifecycle management and inspectable evidence around the optimization core.

## Run and inspect

- [Open the application in Google Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/fleetroute/FleetRoute_App.ipynb). Run its two code cells in order and keep the second cell running while using the printed workspace link.
- [Read the complete application source](source/README.md), [architecture](source/ARCHITECTURE.md), [backend](source/app/engine.py), [directed-road preparation](source/app/offline_osm.py), [spatial graph store](source/app/graph_store.py) and [frontend](source/app/static).

The submitted supplement preserves the frozen application snapshot. The public source and application notebook include a subsequent map-provider correction (v8.2): origin-only referrers, canonical OSM tile URLs, linked attribution, and the existing terrain host in the image security allowlist. The optimizer source is unchanged. Launch requires internet access for setup and the temporary tunnel; road-data download is a separate job.

To check the frozen package, run from the cloned repository root:

```sh
python restore_supplements.py
python -m zipfile -e projects/fleetroute/supplement.zip build/fleetroute-evidence
cd build/fleetroute-evidence
python tools/verify_package.py
python tools/verify_app_notebook.py
python tools/verify_parent_benchmark.py
python tools/recompute_all_common_objectives.py
```

These checks passed on 10 October 2026: 213 package files verified, application payload/source identity verified, 198 parent command rows checked, and 180 parent-valid routes independently re-scored. This verifies retained evidence; it does not launch a new benchmark or certify current external services.

## Application and control architecture

![FleetRoute planned-fleet playback and truck schedule roster](figures/planned-fleet-playback.png)

A single application panel from Figure 5 in the submitted paper, showing the committed fleet plan and schedule-aware playback. This is a controlled prototype scenario.

![FleetRoute committed-plan application surfaces](figures/fleetroute_committed_plan.jpeg)

Per-truck route cards, schedule-aware playback, driver route geometry, and navigation handoff from the controlled scenario in the submitted paper (Figure 5). These are application surfaces, rather than evidence of a field deployment.

![FleetRoute bounded-authority control architecture](figures/fleetroute_architecture.jpeg)

Figure 1 from the submitted paper. The solver proposes a private candidate; independent replay and the commit gate determine whether it becomes the public plan. Road incidents stay pending until operator action creates an approved revision.

## Read the results with their contracts

| Evidence | Interpretation |
| --- | --- |
| [Public reference gaps](tables/current_public_reference_gaps.csv) | Frozen Current results against public reference solutions |
| [Original paired comparisons](tables/paired_comparison_strict_parent_original.csv) | Complete triples from the original parent experiment |
| [Recovery-augmented comparisons](tables/paired_comparison_recovery_augmented_descriptive.csv) | Descriptive comparisons after targeted recovery |
| [Directed-road comparison](tables/osm_four_way_common_metric.csv) | Four-way comparison under the common metric |
| [Claim receipt](tables/PAPER_CLAIMS_RECEIPT.json) | Machine-readable scope and claim provenance |

The frozen package reports a mean best-of-three reference gap of **2.02% over 18 public instances**. In the directed-road comparisons, Current's mean common-evaluator route distance was 0%, 1.10%, 2.73%, and 1.51% lower than OR-Tools for the 50-, 100-, 300-, and 450-customer cases respectively. These are solution-quality comparisons under the retained protocol, not matched end-to-end runtime comparisons.

The parent batch used six software workers on two runtime-visible logical CPUs. The original and recovery-augmented results must remain distinct: 180 parent-valid runs became 197 valid outcomes after 17 successful targeted recoveries. One Legacy case remained unresolved.

## Reproduction scope

The complete submission supplement includes the frozen inputs, retained source snapshots, raw results, an independent common-objective evaluator, table reconstruction tools, and the application notebook. The application is a predeployment research system; the package does not establish measured field savings.

## Benchmark figures

![Reference gap for each of the 18 public instances](figures/public_reference_gaps.png)

Best and mean distances use three seeds for each instance. All Current rows shown are original parent results. Reference costs and scoring conventions are those retained in the package; the figure does not certify a new best-known solution.

![Directed-road route distances for Legacy, V31, and Current relative to OR-Tools](figures/directed_road_quality.png)

Dots show the three-seed mean; whiskers show the observed minimum and maximum, not confidence intervals. The OR-Tools baseline is the best of twelve configurations. The comparison covers solution distance under a common evaluator, with different aggregation and configured budgets.

Rebuild both figures with `python make_figures.py` from this directory (requires NumPy and Matplotlib). The [script](make_figures.py) reads the public CSVs and performs no solver runs. SVG copies are included for export.

## Map-provider correction — 16 October 2026

A reported OSM 403 tile block exposed a conflict: application pages suppressed all referrers, although OSM requires browser tile requests to send a Referer. The updated source/notebook sends only the site origin and keeps login/token redirects at `no-referrer`. Tokens remain in HttpOnly cookies after the redirect. The driver and simulation also use the canonical tile endpoint; terrain images are permitted by CSP.

The screenshot identifies a background-tile block, not a PBF download or optimizer failure. The specific provider-side blocking reason is not observable from the screenshot. The correction does not guarantee availability or remove an existing provider/network block. Do not retry aggressively or rotate proxies/identities.

For an existing Colab runtime, stop cell 2, reopen the updated notebook, run cell 1 and then cell 2, and reload the workspace. Running servers do not update automatically. Runtime road data and plans are retained by the installer.

Run `python projects/fleetroute/tools/verify_map_policy.py` with the application dependencies installed to check authentication, response policies, notebook integrity, source/payload identity and unchanged optimizer identity. These checks do not certify external services or replace an interactive end-to-end test.
