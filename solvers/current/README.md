# Current solver

A **21,196-line C++17 solver** integrated into FleetRoute for constrained fleet routing on real directed road networks.

- [Source](solver.cpp)
- [Integration provenance](solver_provenance.json)
- [Frozen benchmark Current](../benchmark-current/solver.cpp)
- [Version comparison](../README.md)

## Search architecture

The implementation combines simulated annealing, adaptive large neighborhood search (ALNS), Fragment LNS, and phase-specialized parallel search. Search phases allocate work among different operators and reserve refinement time. Worker-local repair controls and stopping conditions support concurrent search without giving every nested operator the same process-wide interruption behavior.

The AVX2 kernel accelerates a specific hot path: distance-based insertion-delta evaluation. It gathers distance-matrix entries into 256-bit vectors, processes four double-precision lanes, and computes insertion costs in batches. A runtime CPU capability check selects the vectorized path; a scalar fallback remains available. This is an implementation feature, not a separately measured end-to-end speedup claim.

FleetRoute integration adds directed edge-speed travel semantics, a distance-and-route-duration objective, hard-feasible cluster warm starts, structured receipts, bounded telemetry, cached reverse incidence, and a progress clock separate from governed search time. These adaptations explain why this production source differs from the retained benchmark snapshot.

## Version identity

Production SHA-256:

```text
89619e5ed68f00e70f78d1633795db23becd02c158319d80dcc910b31c772e48
```

Retained benchmark Current SHA-256:

```text
2615c80d7dc53f5b666f353671521e7d825cd10a1eebb22009f68f96ab1ef584
```

The benchmark tables document the retained benchmark source. They should not be interpreted as a fresh evaluation of this later application integration.
