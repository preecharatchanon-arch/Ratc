# FleetRoute and Neural Training Research

Research and engineering by **Ratchanon Preecha**. This repository brings together a real-road fleet-routing system, the C++17 solver behind it, and two studies of hidden optimizer state in neural-network training.

**Chemistry research:** [CaSR peptide workbench and method review](projects/salt-casr/README.md) · [Executed notebook](projects/salt-casr/CaSR_Research_Workbench.ipynb)

**Additional signal-processing project:** [Two-File Audio Fault Analyzer](projects/audio-fft/README.md) · [FFT and STFT evidence](projects/audio-fft/figures)

**Start with:** [Current solver](solvers/current/README.md) · [FleetRoute paper](projects/fleetroute/paper.pdf) · [Benchmark data](projects/fleetroute/tables) · [Neural training paper](projects/neural-training/paper.pdf) · [AdamW manuscript](projects/adamw-memory/paper.pdf)

## Review the code and run examples

| Work | Code you can read here | Run or verify |
| --- | --- | --- |
| C++17 solver | [Current source](solvers/current/solver.cpp), [V31](solvers/v31/solver.cpp), [Legacy](solvers/legacy/solver.cpp) | [Compile and run a small directed-road example](solvers/current/README.md#build-and-run) |
| FleetRoute | [Application source](projects/fleetroute/source), [routing backend](projects/fleetroute/source/app/engine.py), [road-data processing](projects/fleetroute/source/app/offline_osm.py), [interface](projects/fleetroute/source/app/static) | [Two-cell Colab launch and frozen-result checks](projects/fleetroute/README.md#run-and-inspect) |
| Neural training | [Final confirmation notebook](projects/neural-training/source/evidence/02_final_confirmation_notebook.ipynb), [final claims](projects/neural-training/source/evidence/01_final_confirmation_claims.json) | [Execution requirements and evidence scope](projects/neural-training/README.md#code-and-execution-scope) |
| AdamW memory | [Original protocols](projects/adamw-memory/source/protocols), [CPU analysis scripts](projects/adamw-memory/source/scripts) | [Recompute retained results on CPU](projects/adamw-memory/README.md#code-and-cpu-verification) |
| Audio FFT | [One-cell notebook](projects/audio-fft/audio_fft_analysis.ipynb), [analysis functions](projects/audio-fft/original_prototype.py), [local runner](projects/audio-fft/run_analysis.py) | [Upload any two recordings; display and save all 15 plots](projects/audio-fft/README.md#run-the-project) |
| CaSR chemistry | [Chemical reconstruction and model benchmark](projects/salt-casr/source/casr_discovery), [executed notebook](projects/salt-casr/CaSR_Research_Workbench.ipynb) | [CPU/Colab execution and reviewed evidence scope](projects/salt-casr/README.md#run-and-inspect) |

The earlier source snapshots are extracted unchanged from their supplied research packages. The CaSR project includes reviewed analysis code and an executed notebook. The original archives remain available for the data and frozen experiment context. Each project page states what can be run independently and what requires historical inputs or a GPU.

## Explore the work

| Project | Focus | Evidence |
| --- | --- | --- |
| [NSC 2026 project](projects/nsc-2026/README.md) | Multi-truck waste-collection routing on real roads; Legacy to V31 development | Regional and finalist reports, finalist presentation video |
| [FleetRoute](projects/fleetroute/README.md) | Auditable route optimization on directed road networks | IAAI-27 submission, application notebook, benchmark tables |
| [Current solver](solvers/current/README.md) | Hybrid metaheuristics, AVX2 insertion evaluation, and parallel search | Production source and integration provenance |
| [Solver versions](solvers/README.md) | Current, V31, and Legacy | Frozen source snapshots and SHA-256 identities |
| [Neural training](projects/neural-training/README.md) | Testing whether reproducible low-dimensional structure is causally adequate | AAAI-27 Student Abstract and Poster Program submission |
| [AdamW memory](projects/adamw-memory/README.md) | Testing whether low-rank optimizer-memory representations preserve intervention effects | Research manuscript; not submitted to AISTATS |
| [Audio FFT analysis](projects/audio-fft/README.md) | FFT spectra, STFT and recording comparison; exploratory engine-sound project | Restored Colab notebook, rerun results, graphs and measurement audit |
| [CaSR peptide modelling](projects/salt-casr/README.md) | Receptor-activity modelling and reference-pose validation for salt research | Reviewed exploratory notebook, measured-data benchmark and method limitations; no validated new enhancer |
| [Targeted recovery audit](benchmarks/README.md) | Recovering deadline-censored benchmark rows | Self-contained notebook with embedded Legacy and V31 sources |

The routing work grew from the NSC 2026 project **ระบบเพิ่มประสิทธิภาพเส้นทางรถเก็บขยะหลายคัน บนโครงข่ายถนนจริงด้วยอัลกอริทึมไฮบริดเมตาฮิวริสติก** into FleetRoute. The application adds road-network semantics, validation, bounded execution, and inspectable evidence around the solver.

![FleetRoute route cards, fleet playback, driver map, and navigation handoff](projects/fleetroute/figures/fleetroute_committed_plan.jpeg)

Application evidence extracted from Figure 5 of the submitted FleetRoute paper: a controlled scenario showing the committed-plan surfaces.

## Research status

FleetRoute was submitted to the **Innovative Applications of Artificial Intelligence Conference (IAAI-27)**. *Reproducible Low-Dimensional Structure Can Fail a Causal-State Test in Neural Training* was submitted to the **AAAI-27 Student Abstract and Poster Program**. These are submissions; neither is presented here as an accepted publication.

*Testing Low-Rank Causal Control in AdamW Memory* is a research manuscript intended for a possible AISTATS submission. It has **not been submitted to AISTATS**.

## Benchmark evidence

The frozen benchmark Current source reaches a **2.02% mean best-of-three reference gap over 18 public instances**. Every instance and the mean-of-three result are shown, including the harder cases.

![Current solver reference gaps on all 18 public instances](projects/fleetroute/figures/public_reference_gaps.png)

[Explore the directed-road comparison and evaluation contracts](projects/fleetroute/README.md#benchmark-figures). These figures are rebuilt from retained CSVs; they do not represent new benchmark runs.

## Source identity and historical development

[SOURCE_MANIFEST.json](SOURCE_MANIFEST.json) records the exact archive member and SHA-256 of each extracted solver. The production Current solver and the frozen benchmark Current solver are different snapshots. Reported benchmark results belong to the frozen experimental package.

The [original notebook-cell exports](solvers/history/README.md) preserve the development notes with their original names and unchanged blob identities. The solver index identifies Current, V31, Legacy and the frozen benchmark source separately.

## Obtain the complete supplements

The AAAI Student Abstract supplement is a [single ZIP](projects/neural-training/supplement.zip). The two larger supplements are preserved in checksum-verified parts. Download this repository as a ZIP or clone it, then run:

```sh
python restore_supplements.py
```

This restores the exact original FleetRoute and AdamW ZIP archives locally. It checks each part, the complete SHA-256, and ZIP integrity without executing research code. See the [FleetRoute package](projects/fleetroute/supplement/README.md) and [AdamW package](projects/adamw-memory/supplement/README.md).

## Rights

This code remains proprietary. Reviewers may download it and run the documented commands for academic evaluation. Other copying, modification, redistribution or commercial use requires the author's permission.

Third-party datasets and map data retain their own rights and attribution requirements; see the [data notice](projects/fleetroute/THIRD_PARTY_DATA_NOTICE.md). Hosting an artifact here does not grant a new license to its code or data.


