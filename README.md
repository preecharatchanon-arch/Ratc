# FleetRoute and Neural Training Research

Research and engineering by **Ratchanon Preecha**. This repository brings together a real-road fleet-routing system, the C++17 solver behind it, and two studies of hidden optimizer state in neural-network training.

**Start with:** [Current solver](solvers/current/README.md) · [FleetRoute paper](projects/fleetroute/paper.pdf) · [Benchmark data](projects/fleetroute/tables) · [Neural training paper](projects/neural-training/paper.pdf) · [AdamW manuscript](projects/adamw-memory/paper.pdf)

## Explore the work

| Project | Focus | Evidence |
| --- | --- | --- |
| [FleetRoute](projects/fleetroute/README.md) | Auditable route optimization on directed road networks | IAAI-27 submission, application notebook, benchmark tables |
| [Current solver](solvers/current/README.md) | Hybrid metaheuristics, AVX2 insertion evaluation, and parallel search | Production source and integration provenance |
| [Solver versions](solvers/README.md) | Current, V31, and Legacy | Frozen source snapshots and SHA-256 identities |
| [Neural training](projects/neural-training/README.md) | Testing whether reproducible low-dimensional structure is causally adequate | AAAI-27 Student Abstract and Poster Program submission |
| [AdamW memory](projects/adamw-memory/README.md) | Testing whether low-rank optimizer-memory representations preserve intervention effects | Research manuscript; not submitted to AISTATS |
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

The older files at the repository root preserve the original development history. They are earlier experiments, rather than substitutes for the explicitly identified versions under `solvers/`.

## Obtain the complete supplements

The AAAI Student Abstract supplement is a [single ZIP](projects/neural-training/supplement.zip). The two larger supplements are preserved in checksum-verified parts. Download this repository as a ZIP or clone it, then run:

```sh
python restore_supplements.py
```

This restores the exact original FleetRoute and AdamW ZIP archives locally. It checks each part, the complete SHA-256, and ZIP integrity without executing research code. See the [FleetRoute package](projects/fleetroute/supplement/README.md) and [AdamW package](projects/adamw-memory/supplement/README.md).

## Rights

This code is PROPRIETARY. You may view the source code for educational purposes, but you are NOT authorized to copy, modify, or distribute it without explicit permission.

Third-party datasets and map data retain their own rights and attribution requirements; see the [data notice](projects/fleetroute/THIRD_PARTY_DATA_NOTICE.md). Hosting an artifact here does not grant a new license to its code or data.
