# Solver versions

These are exact snapshots from the FleetRoute submission supplement, extracted without editing the C++ source. The SHA-256 values in [SOURCE_MANIFEST.json](../SOURCE_MANIFEST.json) identify the complete files.

| Version | Source | Lines | Role |
| --- | --- | ---: | --- |
| Current solver | [Production source](current/solver.cpp) | 21,196 | Solver integrated into the FleetRoute application |
| Benchmark Current | [Frozen source](benchmark-current/solver.cpp) | 20,931 | Current snapshot used in the retained benchmark |
| V31 | [Retained source](v31/solver.cpp) | 14,627 | Generation used at the NSC finalist stage |
| V31 STRICT_FAIR | [Benchmark source](v31/solver_strict_fair.cpp) | 14,645 | Source embedded in the targeted recovery notebook |
| Legacy | [Retained source](legacy/solver.cpp) | 13,104 | Generation used at the NSC regional stage |
| Legacy STRICT_FAIR | [Benchmark source](legacy/solver_strict_fair.cpp) | 13,122 | Source embedded in the targeted recovery notebook |

Line counts describe these snapshots, not a measure of performance. The STRICT_FAIR variants are recorded separately so that benchmark provenance does not depend on treating similar files as identical.

## Competition and application history

The author identifies Legacy with the NSC regional round and V31 with the finalist round. The [NSC evidence page](../projects/nsc-2026/README.md) provides the July and August reports and the finalist presentation. V31's early throughput policy separates low-cost LNS from deeper intensification; the later Current solver and FleetRoute integration refine search scheduling, correctness and the application backend further.

Round labels describe development generations. The archived files remain exact submission-supplement snapshots; no byte-identical competition-stage executable is inferred from the generation name alone.

## Compilation

The retained build contract uses C++17, optimization, and pthread support:

```sh
g++ -O3 -DNDEBUG -std=c++17 -pthread solvers/benchmark-current/solver.cpp -o solver
```

Consult the FleetRoute supplement for the instance formats, exact commands, seeds, objective definitions, and independent evaluation. A successful compilation alone does not reproduce the paper's experiment.

## Benchmark boundaries

The parent experiment configured 198 runs. It retained 180 valid parent outcomes; targeted recovery added 17 valid outcomes from 18 attempts. The resulting 197/198 figure is a recovery-augmented descriptive result. Original complete three-generation comparisons and recovery-augmented comparisons are separate tables.

The targeted recovery notebook reruns Legacy and V31 only. It contains no embedded Current source and does not rerun OR-Tools. Its extended wrapper grace allows deadline-censored runs to finish serializing their ledger; recovery wall-clock time is not comparable with the parent batch.
