# Solver versions and development history

C++17 routing-engine sources, original Colab development cells, and dated Git history for the solver behind FleetRoute.

**Start here:** [Current solver and run instructions](current/README.md) · [Original development files](history/README.md) · [Benchmark evidence](../projects/fleetroute/README.md#read-the-results-with-their-contracts) · [Full live commit history](https://github.com/preecharatchanon-arch/Ratc/commits/main/)

## Versioned source snapshots

These are exact snapshots extracted from the FleetRoute submission supplement without editing the C++ source. Dates below are verified **first-publication commit timestamps in this repository**, not inferred code-creation dates. All dates use **Asia/Bangkok (UTC+07:00)** and the Gregorian year.

| Version / source | Lines | First published (UTC+07:00) | SHA-256 prefix | Role |
| --- | ---: | --- | --- | --- |
| [Current solver](current/solver.cpp) | 21,196 | 2026-10-10 00:03:15 | `89619e5ed68f` | Solver integrated into FleetRoute |
| [Benchmark Current](benchmark-current/solver.cpp) | 20,931 | 2026-10-10 00:03:15 | `2615c80d7dc5` | Frozen source used for the retained benchmark |
| [V31](v31/solver.cpp) | 14,627 | 2026-10-10 00:03:15 | `2508570e5174` | Generation used at the NSC finalist stage |
| [V31 STRICT_FAIR](v31/solver_strict_fair.cpp) | 14,645 | 2026-10-10 00:03:15 | `845014863fe6` | Targeted-recovery benchmark variant |
| [Legacy](legacy/solver.cpp) | 13,104 | 2026-10-10 00:03:15 | `1f5822cfc49c` | Generation used at the NSC regional stage |
| [Legacy STRICT_FAIR](legacy/solver_strict_fair.cpp) | 13,122 | 2026-10-10 00:03:15 | `6225684b27bd` | Targeted-recovery benchmark variant |

All six snapshots were published in [`978e80b`](https://github.com/preecharatchanon-arch/Ratc/commit/978e80bf5030dbdfbe5f15f7d758e3b768c5749a). Their source files have not changed since that import. Line counts describe complete files, not a measure of performance. STRICT_FAIR variants are listed separately so that similar sources are not treated as identical.

<details>
<summary>Full SHA-256 source identities</summary>

| Source | SHA-256 |
| --- | --- |
| [Current solver](current/solver.cpp) | `89619e5ed68f00e70f78d1633795db23becd02c158319d80dcc910b31c772e48` |
| [Benchmark Current](benchmark-current/solver.cpp) | `2615c80d7dc53f5b666f353671521e7d825cd10a1eebb22009f68f96ab1ef584` |
| [V31](v31/solver.cpp) | `2508570e517419860a9b278e3692065316503a0f67efeb2d9ad16ded16de19de` |
| [V31 STRICT_FAIR](v31/solver_strict_fair.cpp) | `845014863fe646f96969f775f68851411f0ff0ab4586d487a3ade0098a2e8a22` |
| [Legacy](legacy/solver.cpp) | `1f5822cfc49c108616e63e6bc833a854b39eab36079ccb33bcb1ce388690dee7` |
| [Legacy STRICT_FAIR](legacy/solver_strict_fair.cpp) | `6225684b27bdc8c1c484d1576e21f069c5dc2229aaaea7ff7223c7f2e84684cc` |

[SOURCE_MANIFEST.json](../SOURCE_MANIFEST.json) also records the original archive and member path for each snapshot.

</details>

## Original development commits: May 2026

Six original notebook-cell exports were committed before the October release. Their Git blob identities match the files now preserved in `solvers/history/`, so moving them did not change their contents. The dates here are the **original May commits**, not the October reorganization date.

| Original commit date (UTC+07:00) | Development file | Lines | Original commit |
| --- | --- | ---: | --- |
| 2026-05-09 13:27:42 | [Original solver cell](history/original-solv.colab.txt) | 9,862 | [`6882e21`](https://github.com/preecharatchanon-arch/Ratc/commit/6882e215248c163494d2eded3ae2364901da8c7f) |
| 2026-05-09 15:28:38 | [Operator-pruning experiment](history/operator-pruning.colab.txt) | 5,752 | [`c3db7a6`](https://github.com/preecharatchanon-arch/Ratc/commit/c3db7a6e24f9a2a1ea29c759120443542481b4fb) |
| 2026-05-12 13:59:03 | [Euclidean experiment](history/euclidean-experiment.colab.txt) | 6,626 | [`44ed403`](https://github.com/preecharatchanon-arch/Ratc/commit/44ed4033f7f9771d8a6b4e1ba6311cb1304b942a) |
| 2026-05-18 17:38:33 | [HGS experiment](history/hgs-experiment.colab.txt) | 7,255 | [`57c7c03`](https://github.com/preecharatchanon-arch/Ratc/commit/57c7c0310a7c47d6668ef937557b8189021b8664) |
| 2026-05-18 19:34:39 | [A-n60-k9 tuning](history/a-n60-k9-tuning.colab.txt) | 7,583 | [`f075c46`](https://github.com/preecharatchanon-arch/Ratc/commit/f075c466de62ee7123fbe104f94942a9978bc402) |
| 2026-05-27 20:42:35 | [Fragment LNS experiment](history/fragment-lns-experiment.colab.txt) | 8,251 | [`8217a0f`](https://github.com/preecharatchanon-arch/Ratc/commit/8217a0f2a3e133f582013c76ab1796906d766ba0) |

See the [historical source index](history/README.md) for original filenames, exact blob hashes, and preservation details. These are Colab cells containing directives such as `%%writefile solver.cpp`, rather than standalone `.cpp` translation units. The original filenames retain informal experimental observations; those observations are separate from the audited benchmark results.

## Competition and application history

The author identifies Legacy with the NSC regional round and V31 with the finalist round. The [NSC evidence page](../projects/nsc-2026/README.md) provides the July and August reports and the finalist presentation. V31's early throughput policy separates low-cost LNS from deeper intensification; the later Current solver and FleetRoute integration refine search scheduling, correctness and the application backend further.

Round labels describe development generations. The archived files remain exact submission-supplement snapshots; no byte-identical competition-stage executable is inferred from the generation name alone.

## All repository commits

The table below contains **all 22 commits reachable on `main` through [`50eaf45`](https://github.com/preecharatchanon-arch/Ratc/commit/50eaf455cae3eb37b95d39468cd4cfbadf8a269c)**, in chronological order. It includes other project updates because this repository also hosts the research and audio work. The documentation revision that adds this table, and subsequent updates, appear in the [live GitHub history](https://github.com/preecharatchanon-arch/Ratc/commits/main/). Dates are Git **committer timestamps**, displayed in UTC+07:00.

<details>
<summary>Expand the complete dated commit table (22 commits)</summary>

| Date and time (UTC+07:00) | Commit | Recorded commit message |
| --- | --- | --- |
| 2026-05-09 13:27:42 | [`6882e21`](https://github.com/preecharatchanon-arch/Ratc/commit/6882e215248c163494d2eded3ae2364901da8c7f) | Create solv |
| 2026-05-09 13:29:33 | [`5c3de54`](https://github.com/preecharatchanon-arch/Ratc/commit/5c3de549106f80b9da466743b56b3cad70ec98c8) | Create README.md |
| 2026-05-09 15:28:38 | [`c3db7a6`](https://github.com/preecharatchanon-arch/Ratc/commit/c3db7a6e24f9a2a1ea29c759120443542481b4fb) | Create del sm unused algos |
| 2026-05-12 13:59:03 | [`44ed403`](https://github.com/preecharatchanon-arch/Ratc/commit/44ed4033f7f9771d8a6b4e1ba6311cb1304b942a) | Create euclidean, bads algos, wastes time |
| 2026-05-18 17:38:33 | [`57c7c03`](https://github.com/preecharatchanon-arch/Ratc/commit/57c7c0310a7c47d6668ef937557b8189021b8664) | Create add hgs |
| 2026-05-18 19:34:39 | [`f075c46`](https://github.com/preecharatchanon-arch/Ratc/commit/f075c466de62ee7123fbe104f94942a9978bc402) | Create good, got 1.11% gap from a-n60-k9 consistenly from bks after tuning config |
| 2026-05-27 20:42:35 | [`8217a0f`](https://github.com/preecharatchanon-arch/Ratc/commit/8217a0f2a3e133f582013c76ab1796906d766ba0) | Create from 1380-ish - 1360(rng) to 1365- 1358 bks 1354, after i addd long route target in fragment lns |
| 2026-10-10 00:03:15 | [`978e80b`](https://github.com/preecharatchanon-arch/Ratc/commit/978e80bf5030dbdfbe5f15f7d758e3b768c5749a) | Publish versioned solvers, research papers and audited benchmark evidence |
| 2026-10-10 07:38:52 | [`3aa1023`](https://github.com/preecharatchanon-arch/Ratc/commit/3aa1023d1d313177a1c2b0528e41f537a6a8bb4e) | Add NSC reports and finalist presentation; document Legacy–V31–FleetRoute progression and paper figures |
| 2026-10-10 07:50:44 | [`3629887`](https://github.com/preecharatchanon-arch/Ratc/commit/3629887014d78fa493e7573c77006feb1bb1bcfb) | Organize original notebook-cell exports under solver history with unchanged source identities |
| 2026-10-10 15:50:45 | [`e885161`](https://github.com/preecharatchanon-arch/Ratc/commit/e88516107c85fe46bb6933863b224fd9a2c85e71) | Add FFT audio-analysis project with reproduced evidence and explicit measurement scope |
| 2026-10-10 19:57:47 | [`7a89eb3`](https://github.com/preecharatchanon-arch/Ratc/commit/7a89eb3aef92c6ad145ced6e441c8600f6e33c9c) | Generalize audio runner roles and isolate new analysis outputs |
| 2026-10-10 19:57:49 | [`9b9d4ed`](https://github.com/preecharatchanon-arch/Ratc/commit/9b9d4ed513d9d4b465ae35f941ffebdd01d754ab) | Document arbitrary audio inputs and archived example evidence |
| 2026-10-10 19:57:51 | [`898cd2e`](https://github.com/preecharatchanon-arch/Ratc/commit/898cd2e50bf313df79f17eb548b62586c91c7492) | Clarify audio input selection and versioned run outputs |
| 2026-10-10 19:57:52 | [`bb94423`](https://github.com/preecharatchanon-arch/Ratc/commit/bb944236d7b11d8de67b7e7f1f59dfd51121b197) | Fix Colab audio selection to accept arbitrary uploaded recordings |
| 2026-10-10 20:12:32 | [`a9dfb19`](https://github.com/preecharatchanon-arch/Ratc/commit/a9dfb19b6930c244346f92f7dda11701511475d1) | Restore original audio summaries and every plot with PNG/text saving |
| 2026-10-10 20:12:33 | [`614f2d6`](https://github.com/preecharatchanon-arch/Ratc/commit/614f2d6e87c1dc47ce4d4c96f55f77a9a2d2fc89) | Document restored one-cell audio workflow and original outputs |
| 2026-10-10 20:12:34 | [`66a8a52`](https://github.com/preecharatchanon-arch/Ratc/commit/66a8a52d4013e5b91d24244a6e810f4504bec526) | Document restored one-cell audio workflow and original outputs |
| 2026-10-10 20:12:35 | [`b0820f8`](https://github.com/preecharatchanon-arch/Ratc/commit/b0820f8d1043adbed211b844400e344ecb6c076f) | Restore one-cell Colab workflow with all 15 original audio plots |
| 2026-10-10 20:30:27 | [`5555553`](https://github.com/preecharatchanon-arch/Ratc/commit/5555553bde856909bdf61a598f64bf2ddd86d846) | Expose original project code and add verified reviewer run instructions |
| 2026-10-10 21:58:34 | [`78979f0`](https://github.com/preecharatchanon-arch/Ratc/commit/78979f05463e30525c6229eec185de304e8b7d97) | Show original FFT/STFT portfolio figures and complete 15-plot run |
| 2026-10-10 23:42:12 | [`50eaf45`](https://github.com/preecharatchanon-arch/Ratc/commit/50eaf455cae3eb37b95d39468cd4cfbadf8a269c) | Correct AdamW manuscript headers to reflect unsubmitted status |

</details>

## Compilation

The retained build contract uses C++17, optimization, and pthread support:

```sh
g++ -O3 -DNDEBUG -std=c++17 -pthread solvers/benchmark-current/solver.cpp -o solver
```

Consult the FleetRoute supplement for the instance formats, exact commands, seeds, objective definitions, and independent evaluation. A successful compilation alone does not reproduce the paper's experiment.

## Benchmark boundaries

The parent experiment configured 198 runs. It retained 180 valid parent outcomes; targeted recovery added 17 valid outcomes from 18 attempts. The resulting 197/198 figure is a recovery-augmented descriptive result. Original complete three-generation comparisons and recovery-augmented comparisons are separate tables.

The targeted recovery notebook reruns Legacy and V31 only. It contains no embedded Current source and does not rerun OR-Tools. Its extended wrapper grace allows deadline-censored runs to finish serializing their ledger; recovery wall-clock time is not comparable with the parent batch.
