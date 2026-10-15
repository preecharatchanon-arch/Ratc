# Research and Engineering — Ratchanon Preecha

I build computational systems and test how well their results support the decisions they are meant to inform. This repository brings together my work on waste-collection routing, neural-network training, audio signals, and taste-receptor modelling, with the code and evidence behind each project.

## Where the work began

I noticed irregular waste collection in my area before and after the November 2025 floods in southern Thailand (พฤศจิกายน 2568). That observation led me to ask how several collection trucks could serve the same neighbourhoods more effectively while respecting road directions, vehicle capacity, and service schedules. It brought me into the vehicle routing problem (VRP) field.

The question became my **NSC 2026 national-finalist project**, *A Hybrid Metaheuristic Optimization System for Multi-Truck Waste Collection Routing on Real Road Networks*. I built a C++17 routing solver and a road-data workflow using OpenStreetMap, then developed planner and driver interfaces around them. The [NSC reports and finalist presentation](projects/nsc-2026/README.md) document that development.

The project continued as **FleetRoute**, an application for planning and inspecting fleet routes on real directed road networks. It adds international map-region selection, progress and convergence views, route validation, and workflows for handling road incidents. The original observation motivated the work; the retained results come from computational benchmarks and prototype scenarios.

![FleetRoute route cards, fleet playback, driver map, and navigation handoff](projects/fleetroute/figures/fleetroute_committed_plan.jpeg)

Application views from a controlled scenario in Figure 5 of the submitted FleetRoute paper. [Read the paper](projects/fleetroute/paper.pdf) · [Explore the application and benchmark evidence](projects/fleetroute/README.md).

## Explore the questions and results

| Work | Question and result | Open the evidence |
| --- | --- | --- |
| **Waste-collection routing → FleetRoute** | How can a multi-truck plan respect real-road constraints and remain inspectable? The work combines a hybrid search solver, independently checked routes, and an application for planners and drivers. | [NSC project story, reports and video](projects/nsc-2026/README.md) · [FleetRoute paper, application and benchmarks](projects/fleetroute/README.md) |
| **Neural-training interventions** | Does a reproducible low-dimensional description predict what happens when training state is changed? A one-dimensional coordinate reproduced across tasks, but its frozen decoder performed worse than predicting zero displacement on held-out intervention tests. | [Study, findings and submitted paper](projects/neural-training/README.md) |
| **AdamW optimizer memory** | Can a low-rank representation preserve the effects of changing optimizer memory? Short-horizon reconstruction improved descriptively in an eight-history follow-up, but the declared interaction test failed and longer-horizon prediction failed across those histories. | [Manuscript, saved evidence and CPU reconstruction](projects/adamw-memory/README.md) |
| **Saltiness and taste-receptor research** | Five connected analyses examine CaSR activity prediction, sensory-data transfer, dose-dependent enhancement, receptor-site access and functional assay controls, with explicit limits on what computation can establish. | [Experiments, data and findings](projects/salt-casr/README.md) · [Experiment index](projects/salt-casr/experiments/README.md) |
| **Audio signal analysis** | What changes can be measured between two recordings? A Python notebook compares spectra and time-varying features using the fast Fourier transform (FFT) and short-time Fourier transform (STFT). The demonstration establishes the analysis workflow; engine-fault detection remains unvalidated. | [Project, notebook and signal plots](projects/audio-fft/README.md) |

The neural studies test the difference between observing a repeatable pattern and predicting the effect of an intervention. The chemistry work asks a related practical question: when are a model's predictions reliable enough to guide the next experiment? Each project page explains the measurements, the result, and the remaining limits.

**For molecular-modelling and ML readers:** start with the [five saltiness and taste-receptor analyses](projects/salt-casr/README.md), then choose the relevant report, executed notebook or source. The [shared data guide](projects/salt-casr/data/README.md) explains the endpoints and source limits. The [neural-training study](projects/neural-training/README.md) provides further context on how I evaluate prediction and intervention claims.

## Routing benchmark evidence

The retained fleet-routing benchmark reports a **2.02% mean best-of-three reference gap across 18 public instances**. The figure shows every instance, including the harder cases, and distinguishes the best result from the three-seed mean.

![Frozen routing benchmark: reference gaps on all 18 public instances](projects/fleetroute/figures/public_reference_gaps.png)

[Inspect the benchmark tables and evaluation contracts](projects/fleetroute/README.md#read-the-results-with-their-contracts). These figures are reconstructed from retained CSVs. The reported results belong to the frozen benchmark source, which differs from the later application integration. Computational route-quality comparisons do not establish municipal deployment savings or matched end-to-end runtime advantages.

## Read the code or run a project

| Work | Read the implementation | Execution and evidence scope |
| --- | --- | --- |
| Routing solver | [C++17 source](solvers/current/solver.cpp) | [Compile and run a small directed-road example](solvers/current/README.md#build-and-run) |
| FleetRoute | [Application source](projects/fleetroute/source), [routing backend](projects/fleetroute/source/app/engine.py), [road-data processing](projects/fleetroute/source/app/offline_osm.py), [interface](projects/fleetroute/source/app/static) | [Two-cell Colab launch and frozen-result checks](projects/fleetroute/README.md#run-and-inspect) |
| Neural training | [Final confirmation notebook](projects/neural-training/source/evidence/02_final_confirmation_notebook.ipynb), [final claims](projects/neural-training/source/evidence/01_final_confirmation_claims.json) | [Historical inputs and execution requirements](projects/neural-training/README.md#code-and-execution-scope) |
| AdamW memory | [Experiment protocols](projects/adamw-memory/source/protocols), [analysis scripts](projects/adamw-memory/source/scripts) | [Recompute retained results on CPU](projects/adamw-memory/README.md#code-and-cpu-verification) |
| Saltiness and taste receptors | [Five analysis reports](projects/salt-casr/experiments/README.md), [shared inputs](projects/salt-casr/data/README.md) | [CPU/Colab entry points and verification](projects/salt-casr/README.md#run-an-experiment) |
| Audio analysis | [One-cell notebook](projects/audio-fft/audio_fft_analysis.ipynb), [analysis functions](projects/audio-fft/original_prototype.py), [local runner](projects/audio-fft/run_analysis.py) | [Compare two recordings and save all 15 plots](projects/audio-fft/README.md#run-the-project) |

The routing and neural-research source snapshots retain their supplied archive identities. The saltiness project includes five completed computational analyses, shared data and three executed notebooks. Each project page states whether execution is self-contained, requires historical inputs, or needs GPU training; inspecting saved evidence does not imply that every original experiment can be rerun from scratch.

## Research status

| Work | Status |
| --- | --- |
| NSC waste-collection project | National finalist, NSC 2026; reports and presentation retained |
| FleetRoute | Submitted to the **Innovative Applications of Artificial Intelligence Conference (IAAI-27)** |
| *Reproducible Low-Dimensional Structure Can Fail a Causal-State Test in Neural Training* | Submitted to the **AAAI-27 Student Abstract and Poster Program** |
| *Testing Low-Rank Causal Control in AdamW Memory* | Research manuscript; **not submitted to AISTATS** |
| Saltiness and taste-receptor research | Five completed computational analyses; no validated new saltiness enhancer |
| Audio analysis | Personal signal-processing project; no validated engine-fault classifier |

The conference entries record submissions, not accepted publications.

## Source identity and development history

For readers comparing implementations, the [solver index](solvers/README.md) distinguishes the archived **Legacy**, **V31**, and **Current** generations, as well as the separate frozen benchmark source. These labels describe development snapshots; a benchmark result belongs to its recorded source and protocol.

[SOURCE_MANIFEST.json](SOURCE_MANIFEST.json) records the archive origin and SHA-256 of each extracted solver. The [original notebook-cell exports](solvers/history/README.md) preserve development notes and unchanged source identities. [ARTIFACT_CHECKSUMS.json](ARTIFACT_CHECKSUMS.json) lists artifact sizes and hashes, excluding the checksum index itself.

The [targeted recovery audit](benchmarks/README.md) documents deadline-censored benchmark rows separately from the original experiment, including its retained sources and unresolved case.

## Obtain the complete supplements

The AAAI Student Abstract supplement is a [single ZIP](projects/neural-training/supplement.zip). The two larger supplements are preserved in checksum-verified parts. Download this repository as a ZIP or clone it, then run:

```sh
python restore_supplements.py
```

This restores the original FleetRoute and AdamW ZIP archives locally. It checks each part, the complete SHA-256, and ZIP integrity without executing research code. See the [FleetRoute package](projects/fleetroute/supplement/README.md) and [AdamW package](projects/adamw-memory/supplement/README.md). The CaSR [complete run package](projects/salt-casr/archives/CaSR_Notebook_Run.zip) is available directly.

## Rights

This code remains proprietary. Reviewers may download it and run the documented commands for academic evaluation. Other copying, modification, redistribution or commercial use requires the author's permission.

Third-party datasets and map data retain their own rights and attribution requirements; see the [data notice](projects/fleetroute/THIRD_PARTY_DATA_NOTICE.md). Hosting an artifact here does not grant a new license to its code or data.
