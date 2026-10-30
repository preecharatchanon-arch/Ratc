# Research timeline and contribution record

[Project](../README.md) · [Current status](RESEARCH_STATUS.md) · [Current test design](NEXT_TEST_DESIGN.md)

Updated 30 October 2026. Dates identify this project's analysis or review work. The underlying receptor and human measurements were published by the cited authors; none is a new biological experiment performed here.

## Before 20 October 2026 — original analyses

| Work already completed | Retained evidence |
| --- | --- |
| Chemical reconstruction, CaSR prediction and docking | 94 reconstructed table-compound graphs; 58 numerical/range compounds and 26 constitutional families in the prediction comparison. Original best held-family MAE 0.7989 pEC50; native top-pose RMSD 4.7803 Å. [Experiment 01](../experiments/01-casr-models-and-docking/README.md). |
| Sensory-source transfer | Fixed sequence baselines on 251 sensory-tagged records; ExtraTrees random AUC 0.686 versus reference/sequence-held-out 0.286, with post-hoc parsing sensitivity around 0.415. [Experiment 02](../experiments/02-sensory-source-transfer/README.md). |
| Endpoint and dose dependence | NGYDMR's context-dependent benchmark label, published dose-ranking changes and small complete-panel checks. [Experiment 03](../experiments/03-assay-dose-response/README.md). |
| TRPV1 structural access | Proposed contacts lie in membrane/cytoplasmic regions across three chosen structures; this is not proof of inaccessible binding or absent taste effects. [Experiment 04](../experiments/04-trpv1-membrane-access/README.md). |
| Functional-assay controls | Seven peptides across 32 tested dose/NaCl conditions, distinct knockdown cohorts and the separate soy sensory/organoid comparison. [Experiment 05](../experiments/05-functional-assay-controls/README.md). |

These results should not be described as discoveries made after 20 October merely because a README or repository commit was updated later.

## 27 October 2026 — fixed models and diagnostics

- **Baseline completion:** training-mean held-family MAE 0.8971 versus existing nearest-three 0.7989. Their conditional family-bootstrap gain interval crosses zero.
- **Fixed positional comparison:** primary MAE 0.7653; improvement over nearest-three 0.0337, conditional 95% interval [-0.1104, 0.1553]. Context-interaction and range-aware secondary comparisons also have gain intervals crossing zero. Scaling is fitted within training folds; no subsequent parameter sweep.
- **Matched-pair extension:** the earlier Gly observation was expanded to 11 complete pairs and 55 overlapping four-compound contrasts. For Nva/Val, the interaction range is [-1.1969, -0.7746] pEC50 units. This range propagates source bounds; it is not a confidence interval, and overlapping contrasts are not independent experiments.
- **Gly-effect prediction:** leave-one-pair-out MAE 0.9151 versus training-mean effect 0.8851; gain interval [-0.2498, 0.1842].
- **Saved-pose cross-check:** independent symmetry-aware spyrmsd confirms top-pose RMSD 4.7803 Å; closest of the ten original poses is 2.3158 Å, ranked fifth. This is not the distinct higher-search run or new docking.
- **Selected-panel activity diagnostic:** fixed-direction Vina ordering gives AUC 0.1071 for 14 numerical/range positives and two reported nonresponders. Both negatives belong to one family, one input has an initial-geometry convergence issue, and property-matched decoys are absent. This is a restricted diagnostic, not a validated screening benchmark.

[Protocol, code and outputs](../experiments/01-casr-models-and-docking/followups/2026-10-27/README.md) · [Model summary](../experiments/01-casr-models-and-docking/followups/2026-10-27/output/summary.json) · [Earlier dated planning record with the selected-panel diagnostic](../evidence-review/Next_Decision_Test.md)

Some observations predated this extension. The newly fitted models and audits use previously inspected data and remain exploratory.

## 28–29 October 2026 — primary-source qualification

The review traced named chemical identities to actual receptor and sensory methods. It separated saltiness from kokumi, umami, liking, instrument outputs and extract-level effects. Source dependence and missing fields were retained rather than turned into new labels.

The registry contains five linked identities, all with numerical receptor records. Four have numerical human saltiness observations; γ-Glu-Val has graphical-only saltiness observations here. Twelve numerical formulation/dose conditions yield fourteen values on heterogeneous endpoint scales. They do not form one candidate-selection benchmark.

Examples of what the source qualification changed:

- Ohsu's quantitative panel concerns kokumi/thickness; Broadhead provides receptor EC50/uncertainty without human saltiness. [Primary-assay assessment](../evidence-review/Primary_Assays_and_Endpoint_Decision.md).
- AMPC extract assays and human patty profiling use different material processing and contrasts. Deng's equimolar supplement concerns umami and murine STC-1 responses. [Source assessment](../evidence-review/ASSESSMENT.md).
- The recovered Cao 16-peptide study has human sensory work, but supplementary numerical saltiness tables are electronic-tongue outputs and the cellular assay concerns TAS1R1. Feline-CaSR patent results remain a different species/outcome. [29 October assessment](../evidence-review/Followup_Source_Qualification_20261029.md).
- Liking was reviewed on 28 October as a separate application question. Published MSG solution results support the possibility of increased palatability without a significant saltiness increase; they do not establish peptide efficacy, unchanged total sodium or a frozen-food benefit. [Sensory outcomes](SENSORY_OUTCOMES.md).

The [evidence guide](../evidence-review/README.md) identifies current data and dated historical notes. The source search is bounded, not a systematic review.

## 29 October 2026 — local pose diagnostic

Starting from the known bound coordinates, local optimization gives RMSD 0.5948 Å. Under a common unbound reference, the relaxed pose scores -7.021 versus -7.828 for the frozen displaced pose. The displaced pose remains preferred by this scoring model.

The combined pose/ranking criterion failed, so the conditional new global searches were not run. This is method diagnosis, not de novo pose prediction or validation of an unknown-peptide screen.

[Design, inputs, output and reproduction instructions](../experiments/01-casr-models-and-docking/followups/2026-10-29-local-relaxation/README.md)

## 29 October 2026 — ligand-dependent functional contrast

Published N102F measurements show lower EC50 for γ-Glu-Val and higher EC50 for γ-Glu-Val-Gly. Opposite directions survive the stated conditional summary-data and rounding checks; complete potency-order reversal does not survive the conservative rounding analysis.

Only three experiments per cell are summarized. Raw experiment-level curves are unavailable and receptor expression changes. The result does not isolate direct binding or predict human saltiness.

[Report, original-table transcription, design and calculation](../experiments/05-functional-assay-controls/followups/2026-10-29/REPORT.md)

## Current next step

The [current test design](NEXT_TEST_DESIGN.md) is the single maintained plan. It requires actual matched functional hCaSR and controlled human saltiness measurements, a justified practical margin and an independent evaluation comparison. The present data do not satisfy those requirements. More docking, model sweeps or surrogate-label fits do not supply the missing measurements.

Documentation history and current file checks are recorded in the [verification guide](../verification/README.md).
