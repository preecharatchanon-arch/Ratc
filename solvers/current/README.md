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

## Build and run

Use Linux with an x86-64 C++17 GCC toolchain. From the repository root:

```sh
mkdir -p build/review-run
g++ -std=c++17 -O2 -pthread solvers/current/solver.cpp -o build/solver
cd build/review-run
../solver --objective_mode distance --metric road --use_time_window true \
  --route_start_time_s 0 --allow_multi_trip false --instances 1 \
  --time_limit 0.2 --hard_time_limit_s 5 --no_improve_stop_s 1 --seed 777 \
  < ../../solvers/current/examples/tiny-road.txt \
  > solver_output.txt 2> solver_stderr.txt
```

The [small example](examples/tiny-road.txt) has five nodes, twenty directed edges, four customers, capacity two and at most two trucks. The checked run reports `Final solution feasible : YES` and a distance of **80 metres**. This is an integration example, separate from the research benchmarks. Inspect `solver_output.txt` for routes and metrics and `solver_stderr.txt` for execution logs; runtime details can vary by machine.

Input comes from standard input. Its order is `N M`, maximum trucks `K`, depot ID, `M` directed edges (`u v length_m speed_kph`), customer count, each customer's `node demand service_s earliest_s latest_s`, then capacity. Time values are seconds. The command sets departure to zero to match this example's windows. Do not add `-mavx2` globally: the source dispatches its AVX2 kernel after checking CPU support and retains a scalar fallback.
