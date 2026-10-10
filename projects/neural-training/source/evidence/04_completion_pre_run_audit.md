# NEXUS-II Stage 06 RC13C r3 — Full Pre-Run Release Audit

Date: 2026-09-27

## Release identity

- Project: NEXUS-II
- Version: 1.9.2
- Protocol: `NEXUS-II-v1.9.2-stage06-confirmation-completion-RC13C-FINAL-20260927`
- Scientific protocol hash (unchanged from RC13C r2): `89d065fb5d81d316667742c587edd1cdcf0b69c80a1e3a0a5adf9e4dafe434e1`
- Implementation revision: `NEXUS-II-v1.9.2-stage06-RC13C-r3-FULL-PARENT-EQUIVALENCE-NONZERO-Q-QA-MERGED-PROVENANCE-AND-REPORTING-HARDENED-20260927`
- Implementation-revision SHA-256: `27cbbd1f97f8a418336c80808913cfbd6fbbdb2e020b6eb9fcccd94fc15cdcdd`
- Exact notebook SHA-256: `c3e07f2ba27b94d92dbff8b902c2420fc582d1272090b3dd1e592fcbd495296d`
- Code-cell source-bundle SHA-256: `678db12ad1edf860a273012cbee2be3672a3f159cbbb5cce3ee1e61a33793de7`
- Canonical RC13B parent ZIP SHA-256: `ce32e9d26899ddcb9b32669e9fe67bb730cc1972f243a0490562edc54b39c947`

## Notebook integrity

- `nbformat.validate`: PASS
- Cells: 22 total / 15 code
- Saved outputs: 0
- Every code cell compiles: PASS
- Protocol-bearing AST is identical to RC13C r2 for `CoreConfig`, discovery/confirmation/cohort IDs, Q rejection rule, parent evidence, preregistration, and `PROTOCOL_PAYLOAD`.
- Therefore r2 -> r3 is implementation-only; no scientific threshold, estimator, cohort, claim, intervention, or estimand changed.

## Parent RC13B evidence verification

The canonical aborted RC13B bundle was independently checked:

- 166 manifest-bound payloads
- ZIP/member manifest SHA and size mismatches: 0
- Discovery model SHA: `3eb7b969a54b0004222c5b81f4344a8d91ce02b06fdf8f04dced20017222ab0b`
- Discovery atlas SHA: `7603aeeb62e9c453bb0c095aac2902202d1489033035cd3a5b8ca9bcfd78ad0f`
- Discovery dimension curves SHA: `a4b467f763ac2947d9ce6801c44879e78f020cefdb5a23d714269e0dc9ad0d26`
- Discovery lock SHA: `113eed25783b3ed0331fb92d5e02a3c017fe6a82a12705a0d556c8c3c31ee9d0`
- Parent stop: pre-claim scientific stop; H6-B/W/A are null/not evaluated.
- Parent environment records Python 3.13.15, torch 2.11.0+cu128, CUDA 12.8, A100-SXM4-40GB, numpy 2.1.3, pandas 2.2.3, scipy 1.16.3, sklearn 1.6.1, pyarrow 23.0.1, driver 580.82.07.
- RC13C refuses deterministic completion if that environment-compatibility record does not replay exactly.

## Sealed-parent firewall

Before the RC13C Q-plan lock:

- parent confirmation Parquet payloads 3100-3126 are treated as opaque bytes only;
- outcome-bearing replicate metadata is not deserialized;
- only manifests, commits, discovery lock, code/config/environment manifests, and the documented stop record are decoded;
- table/meta bytes are hash/size checked against the parent commits.

Only after the full 3100-3129 geometry plan is frozen may parent response/replicate evidence be opened.

## Q-plan / conditional-law amendment

The scientific amendment remains exactly the frozen RC13C rule:

- candidate 0 = exact RC13B Q-direction seed recipe;
- candidates >0 use a domain-separated deterministic rejection namespace;
- accept first whole Q bank with max pairwise |cos(Q_A,Q_T,Q_B)| <= 0.15 at every target;
- acceptance uses Q geometry only, before response outcomes are opened;
- 3100-3126 must replay as candidate 0;
- 3127 candidate 0 must replay the documented ~0.201394 failure;
- candidate plan for all 30 tasks is frozen before completion training.

r3 makes the Q-plan content hash reproducible by excluding wall-clock `locked_unix` from the scientific Q-plan SHA while retaining the timestamp as audit metadata.

## Nonzero-candidate path

A missing zero-hour test in r2 was identified: candidate-0 writer mechanics were tested, but the actual nonzero rejection-sampled `build_q_bank(..., q_plan_entry=...)` path was not.

r3 adds a release-blocking real ResNet QA for that path.

Independent local execution result:

- nonzero candidate index: 1
- max noise cosine: 0.0756199658
- direction-ID replay: PASS
- candidate-index replay: PASS
- Q-bank hash construction: PASS
- post-QA runtime-integrity restoration: PASS

This is QA-only; the A100 zero-hour run will independently execute the same software path before paid 3127-3129 work.

## Parent scientific equivalence

Static RC13B-r8 -> RC13C-r3 AST comparison found only seven shared parent functions changed:

- `_assert_runtime_integrity`
- `_current_protocol_payload`
- `build_q_bank`
- `measure_branch`
- `run_s6_replicate`
- `freeze_discovery_lock`
- `run_stage06_campaign`

The last two intentionally disable obsolete discovery/full-rerun paths. `build_q_bank`, `measure_branch`, and `run_s6_replicate` differ only by the frozen Q-candidate plumbing/provenance. Runtime/protocol helpers differ because this is a new protocol revision.

All common scientific classes are AST-identical to RC13B r8.

r3 strengthens the runtime parent guard to require:

- every parent scientific helper still present except the two obsolete launch/workload wrappers;
- semantic hash equality for every unchanged parent function;
- semantic hash equality for all shared parent scientific classes;
- exact parent analysis schema equality;
- exact parent `CoreConfig` equality.

The analysis schema was independently compared and is identical: role names, signed kinds, state columns, query base, observational columns, target microscopic columns, primary metrics, and master seed.

## Task/training continuation integrity

The RC13C task/training machinery is source-identical to RC13B for task generation, model initialization, schedule generation, AdamW configuration, step RNG, checkpointing, hidden axes, hidden calibration, continuation, observables, and analysis.

Task generation uses `stable_seed('S6_suite', rep)` and model/training streams do not depend on the new RC13C protocol hash. Completion therefore regenerates the original 3127-3129 tasks/training streams.

After each missing replicate is rerun, its final and recipient pre-intervention competency values must match the already-recorded parent competency artifact to 1e-8; mismatch is a hard stop.

## Seed-collision audit

Exhaustive deterministic seed audit for RC13C's expanded Q rejection namespace:

- potential rejection-candidate noise-direction seeds: 23,040
- unique: 23,040
- collisions: 0

Including all fixed Stage-06 discovery/confirmation measurement-direction seeds:

- total checked: 23,880
- unique: 23,880
- collisions: 0

Thus the 32-bit `stable_seed` truncation causes no collision in the actual RC13C measurement-direction namespace.

## Merged-atlas provenance hardening

r2 would have created `NaN` in the newly introduced `q_candidate_index` column for the 27 parent rows because RC13B predates that column. This did not feed the frozen estimator, but it was ambiguous evidence provenance.

r3 explicitly assigns parent rows candidate index 0 in both `q_candidate_index` and `rc13c_q_candidate_index`, and hard-fails unless:

- neither column has missing values;
- both columns agree row-for-row;
- each task's candidate index exactly equals the frozen Q-plan entry.

The provenance columns remain excluded from the unchanged H6 feature selectors.

## No provenance leakage into H6

The frozen estimator uses explicit `OBS_COLS`, `MICRO_TARGET_COLS`, matched-Q columns, and fixed treatment metadata. It does not dynamically absorb arbitrary numeric columns.

Therefore `q_candidate_index`, `rc13c_q_candidate_index`, and `rc13c_evidence_origin` cannot enter the rich baseline, rCCA state, target, residual model, or causal-contrast predictor.

## Final reporting

The unchanged `confirm_stage06` estimator is preserved byte-for-byte. After it returns, r3 only updates the final report's claim-boundary text to the already-hashed RC13C preregistered boundary and records explicitly that the measurement estimand is conditional on valid-Q support geometry. No gate/result is altered by this reporting step.

## Workload

New paid work remains exactly:

- completion tasks: 3127, 3128, 3129
- 7 branches/task
- 264 rows/branch
- new response rows: 5,544
- final confirmation rows: 55,440
- new base training updates: 1,500
- new Q continuation updates: 15,120
- new counted optimizer updates: 16,620

Calibration forward passes remain excluded from the update count.

## Remaining irreducible checks

The exact accepted candidate indices cannot be certified on this CPU environment because RC13C deliberately requires replay in the canonical parent A100/CUDA/Python software environment. The A100 zero-hour run must therefore still prove, before paid completion:

1. exact environment compatibility;
2. all 3100-3126 replay candidate 0;
3. 3127 candidate 0 reproduces the parent ~0.201394 support failure;
4. a later valid 3127 candidate is selected;
5. a valid plan is frozen for 3128-3129;
6. the new nonzero-candidate real-writer QA passes;
7. runtime protocol/code/determinism restoration passes.

These are intentional fail-closed checks, not untested assumptions.

## Release conclusion

No known controllable scientific, statistical, parent-evidence, task-generation, Q-rejection, feature-leakage, merged-provenance, resume, or final-reporting defect remains in RC13C r3 after this audit. RC13C r3 should replace r2 for the completion run.
