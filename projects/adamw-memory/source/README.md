# Anonymous supplementary code and saved-output evidence

This supplement accompanies **Testing Low-Rank Causal Control in AdamW Memory**. The paper PDF contains Appendices A–G; they are not replaced by a competing manuscript here. This archive provides frozen code, seven figure exports, all figure-input tables, manifest-authenticated primary response arrays for the central matching experiments, and the instructions below. Historical stage numbers match Appendix G. Internal editorial reviews and author correspondence are excluded.

## What can be reproduced from this archive

Run commands from the extracted archive root. These checks require only Python, NumPy and Matplotlib; a GPU and a Drive account are unnecessary. If needed, install `requirements-cpu.txt` in a fresh environment. Run in a working copy because some scripts regenerate tables and figures.

```bash
python scripts/verify_package.py
python scripts/verify_source_subsets.py
python scripts/verify_stage06_archive.py
python scripts/check_stage10_saved_summary.py
python scripts/recompute_compact_matching.py --out regenerated_compact_matching
python scripts/plot.py --data evidence --out regenerated_figures
python scripts/recompute_stage14.py
python scripts/audit_stage14.py
python scripts/audit_amplitude_stage14.py
python scripts/audit_stage07.py --root evidence/stage07/raw --out regenerated_stage07
python scripts/check_stage06_precursor_summary.py
```

| Command/evidence | Reproduces | Does not establish |
|---|---|---|
| `verify_source_subsets.py` | Every included Stage 10, 12 and 13 evidence file against the SHA-256 and byte count stored in its original immutable archive manifest | Correctness of the experiment design |
| `verify_stage06_archive.py` | All 202 payloads in the complete original Stage 06 result archive against its internal artifact manifest | Neural replay, because the original runner source is not embedded in that results archive |
| `recompute_compact_matching.py` | The Stage 12/13 primary rank-16 and rank-64 response errors across all saved horizons; independent capture arithmetic at evaluation horizons 1 and 16; exact agreement with archived Stage 13 values | Neural retraining, operator refitting, or quantities requiring omitted checkpoints |
| `check_stage10_saved_summary.py` | Internal per-seed aggregation and the quoted rank-16/rank-64 immediate-to-future cosine decay from the complete eight-model saved result | Recalculation of the exact operator from the omitted model states |
| `plot.py` | Figures 01–05 from the supplied stage 12/13 response, capture and continuation tables | Neural reruns |
| `recompute_stage14.py` | All 256 central projection errors from the eight included CIFAR10 histories; geometry, baseline aggregate differences, primary sign test and figures 06–07 | Fresh neural training or full-test prediction replay |
| `audit_stage14.py` and `audit_amplitude_stage14.py` | Signed errors, capture arithmetic, additivity, even responses, archived qualification, full/half-amplitude checks and endpoint differences | Unrun half-amplitude projected branches |
| `audit_stage07.py` | Controlled confirmation cosine, norm retention, remainder and additivity from 30 raw task endpoint files | Re-fitting the operator or retraining those tasks |
| Stage 06 summary check | Consistency of the quoted precursor statistic with its saved summary | Neural replay, a re-fit scalar predictor, or independent bootstrap reconstruction |
| `protocols/` | Original implementations and frozen experiment settings for stages 07, 10–14 | A verified turnkey reconstruction of every original campaign |

`evidence/stage06/original` exposes the precursor summary, per-task anisotropy table and protocol/configuration records directly; `evidence/stage06/source_archive` retains the complete original 30-task result archive, including replicate blocks and its immutable scientific-code fingerprint. The original Stage 06 neural runner source is not embedded in that results archive. `evidence/stage07/raw/confirmation` includes original endpoint arrays, geometry/temporal tables and saved analysis. `evidence/stage10/original_compact` includes the complete saved eight-model analysis and each unit's operator/result record. `evidence/stage11` retains saved architecture-extension summaries. `evidence/stage12/original_compact` and `evidence/stage13/original_compact` contain the branch arrays and independent-trace arrays needed for the central immediate-versus-matched comparisons. `evidence/stage14/raw` includes branch logits, trace/capture arrays, qualification and stability records for all eight reported CIFAR10 histories.

`evidence/SOURCE_ARCHIVES.json` records the immutable source archive size, SHA-256, manifest identity and selection size. Each compact directory also contains `ORIGINAL_SELECTION_MANIFEST.json`, which authenticates every included payload against the original archive manifest. See `STUDY_CROSSWALK.md` for the claim-to-evidence map and explicit scope decisions.

## Full matching archive recomputation

The compact command above reproduces the paper's central Stage 12/13 matching comparisons from included arrays. The following stronger audit requires the two complete original archives, which are not included because together they exceed the submission-size budget:

```bash
python scripts/recompute.py --stage12 PATH_TO_NEXUS_STAGE12_FINISHED.zip --stage13 PATH_TO_NEXUS_STAGE13_FINISHED.zip --out recomputed_matching
```

It verifies every payload in both original archives, source identity, training-quality records, finite-difference controls, endpoint changes and all secondary configurations before recomputing the matching results. The included compact selection is sufficient for the headline saved-array calculations but cannot substitute for the omitted trained states and full campaign payloads. This release therefore does not change the paper's conservative **No** answer to the checklist question asking whether everything needed to reproduce all main experimental results is supplied.

## Native neural execution

Frozen notebooks for discovery/confirmation and the exact/architecture diagnostics are included without cell outputs or personal metadata. Stages 07A and 07B run in sequence; discovery freezes the rank lock before confirmation. `protocols/stage10` and `protocols/stage11` contain their corresponding notebook and imported modules.

The fresh and stable runners expose `runner13.main(...)` and `runner14.main(...)`; their Config dataclasses and PROTOCOL/CONFIG files specify the experiments. Run them from their respective protocol directories on the recorded compatible GPU stack, using new output directories for any rerun. They download official CIFAR splits. The stable analysis reported in the paper is the complete eight-history CIFAR10 cohort under the frozen .025 continuation-loss threshold. The archived prospective configuration also names CIFAR100, but this supplement makes no stable-CIFAR100 observation or claim. Changing the reported cohort or threshold creates a different analysis, not a reproduction of the frozen result. Runtime/source/environment checks are preserved.

Stage 12 reuses four stage 10 CIFAR10 states. Its expected `parent/units/CIFAR10_SEED/cut_state.npz` files and corresponding basis arrays are not included. Native stage 12 execution requires regeneration or provision of the original parent states in the expected layout. Compact large-model results likewise omit trained weights and moments. Native surgery needs retraining; the supplied array checks do not constitute independent neural-execution replication. No new GPU rerun was performed for this release.

See `DEPENDENCIES.md` and per-campaign environment records for dependencies, asset sources and license information. Dataset images, credentials, personal Drive links and internal author reviews are absent. `PACKAGE_MANIFEST.json` authenticates the released file membership and bytes; it is independent of the immutable original result-archive manifests and does not certify experimental correctness.
