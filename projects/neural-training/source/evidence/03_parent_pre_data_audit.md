# NEXUS-II Stage 06 RC13B r2 — Final Pre-Data Rigor / Integrity Audit

Date: 2026-09-26

## Release decision

**Approved for first research-data exposure on A100/Colab, with the limitations stated below.**

RC13A is superseded and should not be used. The audit found a real preregistration/implementation mismatch before any RC13 research data were observed: the within-task “zero-change” comparator was numerical zero after target standardization, which represents the discovery target mean rather than physical ΔY=0. RC13B corrects this and strengthens several related validity/provenance contracts. The scientific Stage-06 protocol is now frozen.

No RC13A/RC13B research cohort data have been used to choose RC13B outcomes or thresholds.

## Frozen research identity

- Project: `NEXUS-II`
- Version: `1.9.1`
- Protocol revision: `NEXUS-II-v1.9.1-stage06-predictive-susceptibility-RC13B-FINAL-20260926`
- Research protocol SHA-256: `e5568991066d679c1663fc3e5e3bbdd22e51e2cb7cea71a645c112e9526f66cb`
- Implementation revision: `NEXUS-II-v1.9.1-stage06-selfcontained-RC13B-r2-FULL-PRELAUNCH-FINGERPRINT-20260926`
- Implementation revision SHA-256: `67db03b9b6e7d3a0fa6ce49f9ce9fef20bcc5858b379b912cd8b8912921883bc`
- Research scientific-code fingerprint: `89976fcc13988d5cbdb90769a39352189eaf71fe186abd2e2654ac48da5669b5`
- Exact notebook SHA-256: `679f808a393bb86fddc90859a9d42673a78eb59f260c2f66fa666ecea06eee77`

The research scientific-code fingerprint is profile-specific because the frozen research schema differs from smoke QA. Smoke production fingerprint for the exact same notebook is `c5565aff887741c5fee5bac1cd8a63df8c3dedbb8612ac2a673be99b1f555fab`.

## Frozen scientific scope

Stage 06 reports three independent claims. There is no master majority vote.

1. **H6-B — between-task predictive susceptibility phenotype.** A discovery-frozen one-dimensional matched-query representation of untouched baseline learning states must be query-reproducible, predict held-out Q_T future responses beyond the rich observational/microscopic challenger, and be sufficient relative to full matched Q.
2. **H6-W — within-task causal state.** All short-horizon Q_A/Q_B and future Q_T responses are first expressed as exact branch-minus-that-task's-untreated-baseline effects. A one-dimensional discovery-frozen representation must then be query-invariant, predict centered future effects from both matched Q views, transport to confirmation-only random_b, predict familywise ±1 caused contrasts for history/random_a/random_b, and satisfy full-context / residual-information sufficiency gates.
3. **H6-A — optimizer anisotropy.** On untouched confirmation tasks only, the historical AdamW exp_avg direction must require substantially less relative first-moment displacement than eight deterministic random axes orthogonal to history and to each other to create the same prospective one-step functional effect.

All claim language is restricted to the frozen controlled clean-learning synthetic ResNet18-GN / AdamW population and the Stage-06 physical intervention/query family.

## Fresh cohorts / firewall

- Discovery tasks: `3000..3019` (20 independent task/replicate units)
- Confirmation tasks: `3100..3129` (30 independent task/replicate units)
- Independent inferential unit: task / replicate only.
- Branches, doses, query atoms, positions, signs, and horizons never increase n.
- `random_b` is not constructed in discovery. Code constructs it only when `cohort == 'confirmation'`.
- Discovery atlas, fitted models, dimension curves, and model pickle are SHA-locked before confirmation opens.
- Confirmation firewall records the discovery model/atlas identity and the invariant that random_b was absent from discovery.

## Main RC13B corrections / hardening

### 1. Physical zero is now actually physical ΔY = 0

Within-task target differences are standardized using the discovery target scaler. Numerical zero in standardized coordinates is generally the discovery target mean, not physical zero. RC13B explicitly transforms a raw all-zero effect through the frozen target scaler and compares the frozen predictor against that location.

A zero-hour regression test asserts that this distinction exists and exercises the real zero-change gate.

### 2. True nested task-grouped discovery CV

The dimension curve now uses:

- outer task-grouped CV for estimated future Q_T error by dimension;
- inner task-grouped CV within each outer-training fold to select rCCA regularization;
- a separate full-discovery grouped CV to select the regularization used in the frozen model.

Research settings: 5 outer folds, 4 inner folds, 5 folds for final regularization selection. Candidate dimensions are 1, 2, 4, 8. Confirmation never selects a dimension or regularization.

### 3. Matched Q_A/Q_B/Q_T directions are physically independence-audited

The three deterministic Gaussian noise directions are generated independently at each target and their pairwise absolute cosine is checked directly. Research maximum allowed |cosine| is 0.15. Seed separation alone is not treated as proof of independence.

All signed Q probes must also satisfy the inherited central-secant local-response qualification.

### 4. Hidden exp_avg interventions receive their own locality qualification

History, random_a, random_b and anisotropy random axes are not accepted merely because ± effects are symmetric. Each calibrated hidden-state axis is prospectively evaluated after one frozen training update using central logit secants at 0.5×, 0.75× and 1.0× dose.

Required:
- minimum secant cosine ≥ 0.98;
- maximum relative secant-norm drift ≤ 0.25.

These are validity gates, not headline evidence.

### 5. No silent loss of confirmation tasks

Dimension noninferiority, matched-query identity, prediction, sufficiency, familywise causal contrasts and anisotropy now carry explicit expected-task coverage checks. A degenerate/missing replicate cannot silently disappear and leave a smaller passing sample.

### 6. Finite Monte-Carlo p-values cannot equal zero

For n above the exact-sign-flip range, the Monte-Carlo estimate uses a plus-one correction `(count + 1)/(draws + 1)`.

Research sign-flip Monte-Carlo draws: 100,000. Bootstrap replicates: 10,000.

### 7. Scientific-stop semantics

A preregistered upstream support failure before complete claim evaluation is recorded as `claims_evaluated: false` and individual claims `null`, rather than incorrectly converting unobserved claims into false findings. Genuine software/infrastructure failures remain separate and raise.

### 8. Full pre-launch provenance fingerprint

RC13B r2 moves fingerprint/integrity initialization to the final pre-launch cell. Every user-defined function/class loaded before campaign execution—including workload and launch/error-handling helpers—is semantically hashed before any paid run starts.

Semantic hashing excludes ephemeral filename/line-table metadata but includes bytecode, constants, names, defaults, nested code, exception tables, classes/methods and frozen schemas. Protocol hash, implementation identity and environment compatibility are separately bound.

### 9. Resume / stage integrity

- Replicate commits bind protocol, implementation, environment compatibility, scientific-code fingerprint, canonical table size and SHA-256.
- Stage markers bind output artifact paths, sizes and SHA-256 hashes.
- Discovery lock rechecks upstream atlas/dimension/model hashes before confirmation.
- Zero-hour regressions deliberately corrupt a stage artifact and a replicate provenance fingerprint; both are rejected.

### 10. Final bundle integrity

The final result ZIP is CRC-tested with `ZipFile.testzip()`. An adjacent receipt records ZIP bytes/SHA-256, protocol/implementation/code identity and artifact-manifest SHA-256. A QA export was generated and independently re-hashed successfully.

## Frozen research workload

- Discovery replicates: 20
- Confirmation replicates: 30
- Discovery branches per replicate: 7
- Confirmation branches per replicate: 7
- Q continuations per branch: 44
- Rows per branch: 264
- Q signed calibrations per replicate: 40
- Anisotropy random calibrations per confirmation replicate: 8
- Expected discovery rows: **36,960**
- Expected confirmation rows: **55,440**
- Expected response rows total: **92,400**
- Base training optimizer updates excluding calibration: **50,000**
- Q continuation updates excluding calibration: **252,000**
- Counted optimizer updates total excluding calibration: **302,000**

Hidden-instrument, Q-functional and anisotropy functional-calibration forward/one-step qualification work is intentionally excluded from that optimizer-update count and is separately recorded in artifacts.

## Executed validation evidence

### Static / format

- `nbformat.validate`: PASS
- 22 cells / 15 code cells
- every code cell compiles
- zero saved code-cell outputs
- no stale RC13A / v1.9.0 identifiers in the final notebook
- fresh RC13B cohorts only

### Research-profile initialization

Executed locally with A100 requirement disabled and a **QA-only pyarrow import stub** (no scientific campaign run): PASS.

Resolved research identity:
- protocol: `e5568991066d679c1663fc3e5e3bbdd22e51e2cb7cea71a645c112e9526f66cb`
- scientific code: `89976fcc13988d5cbdb90769a39352189eaf71fe186abd2e2654ac48da5669b5`
- discovery 20 / confirmation 30
- nested CV 5/4/5
- Q noise |cos| cap 0.15
- hidden secant cosine floor 0.98
- hidden relative norm-drift cap 0.25
- 10,000 bootstraps / 100,000 MC sign flips
- workload exactly 36,960 + 55,440 rows and 302,000 counted updates.

The **production notebook itself was separately tested without pyarrow** and correctly stopped before scientific work with the explicit “research requires pyarrow/Parquet” failure. The production file was not changed to use the QA stub.

### Exact-production-fingerprint physical lane

The exact r2 production fingerprint was computed first; only the slow synthetic suite call was replaced at runtime after fingerprinting. All physical/integrity machinery passed:

- function-preserving hidden-state surgery: PASS
- optimizer-field isolation: PASS
- history hidden-state locality: minimum cosine `1.0`, maximum norm drift `4.706445172128543e-06`
- random hidden-state locality: minimum cosine `0.9999999403953552`, maximum norm drift `0.000157943194913002`
- real branch writer: 44 rows × 145 columns
- Q calibration pass fraction: 1.0
- matched Q counts: A=12, B=12, T=12
- maximum observed Q_A/Q_T/Q_B direction |cosine|: `0.05411098524928093` (< 0.15)
- durable fresh write/readback: PASS
- resume without recomputation: PASS
- mismatched code provenance rejected: PASS
- deliberately corrupted stage artifact rejected: PASS

Smoke production fingerprint for this exact lane: `c5565aff887741c5fee5bac1cd8a63df8c3dedbb8612ac2a673be99b1f555fab`.

### Exact-production-fingerprint synthetic discrimination

The seven synthetic worlds were run independently under the exact r2 production fingerprint to avoid CPU thread-oversubscription hiding individual failures:

1. known shared 1-D between+within world → H6-B=true, H6-W=true, H6-A=true: PASS
2. pure between-task world → H6-B=true, H6-W=false: PASS
3. pure within-task world → H6-B=false, H6-W=true: PASS
4. genuine 2-D within-task world → H6-W=false: PASS
5. mismatched physical-query world → H6-W=false: PASS
6. discovery-visible dose proxy with broken confirmation-only random_b transport → H6-W=false: PASS
7. null optimizer-anisotropy world → H6-A=false: PASS

Each dimension curve checked during these tests reported `selection_method = nested_task_grouped_cv`.

### Campaign-controller integration

The real Stage-06 controller was run unchanged while only expensive neural data generation was replaced with known-positive synthetic tables. PASS:

- 06A discovery competency
- 06B discovery atlas
- 06C discovery decomposition lock
- cryptographic discovery reload
- confirmation firewall
- 06D confirmation competency
- 06E confirmation atlas
- 06F confirmation analysis
- all six stage markers verified
- random_b absent from discovery / present only after firewall
- final ZIP CRC and receipt SHA verification

### Final-export isolated QA

The exact final-export function successfully produced a test ZIP and receipt; CRC verification and independent SHA recomputation matched the receipt.

## What is and is not guaranteed

This audit establishes that there is **no known methodological, statistical-contract, zero-hour implementation, stage-orchestration, persistence, resume, or packaging defect** in the frozen RC13B r2 notebook.

It cannot honestly guarantee that an external multi-hour A100/Colab run can never fail. This environment does not provide an A100 and does not have a real local pyarrow installation, so the full 302,000-update production campaign has not been executed here. External failures such as Colab disconnection, CUDA/library failure, Drive outage/quota, or an unseen hardware-specific deterministic-operation issue remain possible.

The notebook is designed so that those conditions are either detected before paid work where possible, raised as software/infrastructure failures, or recoverable from cryptographically verified durable replicate commits.

## Freeze recommendation

**Run this exact RC13B r2 notebook unchanged.**

Do not change thresholds, cohorts, query definitions, CCA regularization grid, dimension candidates, branch schema, anisotropy rules, inference logic, claim language, or confirmation handling after any 3000–3019 / 3100–3129 research response is observed. Any such scientific change requires a new protocol revision and new fresh cohorts.
