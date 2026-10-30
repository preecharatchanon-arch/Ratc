# Research status — 30 October 2026

[Project](../README.md) · [Timeline](RESEARCH_TIMELINE.md) · [Evidence](../evidence-review/README.md) · [Current test design](NEXT_TEST_DESIGN.md) · [Sensory outcomes](SENSORY_OUTCOMES.md)

## Question and conclusion

Can **measured functional human-CaSR activity** improve selection of peptides that increase **human saltiness under defined conditions**?

The existing analyses have not established that selection benefit. Some named compounds have both receptor and human saltiness evidence, but the measurements do not yet form a common candidate panel suitable for the proposed comparison. The [timeline](RESEARCH_TIMELINE.md) separates the five original analyses from the work added on 27–29 October.

## What the completed analyses show

| Analysis | Retained result | Consequence |
| --- | --- | --- |
| [Original CaSR models/docking](../experiments/01-casr-models-and-docking/README.md) | Best original held-family MAE **0.7989 pEC50**; native top-pose RMSD **4.7803 Å**. | The original predictor and pose-ranking results provide limited support for prioritizing unmeasured analogues. |
| [27 October fixed-model follow-up](../experiments/01-casr-models-and-docking/followups/2026-10-27/README.md) | Positional-model gain **0.0337**, conditional 95% interval **[-0.1104, 0.1553]**; the 11-pair Gly-effect gain interval also crosses zero. | Reliable improvement is not established. These are exploratory comparisons on previously inspected data. |
| [Local pose relaxation](../experiments/01-casr-models-and-docking/followups/2026-10-29-local-relaxation/README.md) | Relaxed reference RMSD **0.595 Å**; common-reference Vina score **−7.021**, versus **−7.828** for the displaced pose. | A reference-like local minimum is accessible, but the displaced pose still ranks better. Conditional new global searches were not run. |
| [WT/N102F functional comparison](../experiments/05-functional-assay-controls/followups/2026-10-29/REPORT.md) | Opposite γ-EV/γ-EVG EC50 shifts survive the stated conditional summary-data and rounding checks; complete ordering reversal is inconclusive. | A useful ligand-dependent response comparison. Small n, expression and signaling limit mechanistic interpretation. |
| [Sensory source transfer](../experiments/02-sensory-source-transfer/README.md) | Fixed ExtraTrees AUC **0.686** under random splits versus **0.286** under reference/sequence holdouts; parsing sensitivity is reported separately. | Performance depends strongly on the evaluation domain and source grouping. |
| [Dose and endpoint analysis](../experiments/03-assay-dose-response/README.md) | Context-dependent benchmark labels, dose-ranking changes and limited retrieval in a small complete panel. | Preserve the actual endpoint, dose, matrix and unsuccessful or uncertain observations. |
| [TRPV1 access](../experiments/04-trpv1-membrane-access/README.md) | Proposed contacts map to membrane/cytoplasmic regions in three selected structures. | Access route and rapid extracellular function need evidence beyond site geometry. |
| [Functional-assay controls](../experiments/05-functional-assay-controls/README.md) | Seven peptides across **32 tested conditions**, with distinct component and knockdown comparisons. | Peptide-only, NaCl-only and mixture responses answer different questions; general calcium responses cannot substitute for a salt-enhancement comparison. |

These are reanalyses of published observations and saved structures. Receptor activity, binding, human perception and actual sodium reduction are separate endpoints.

## Human evidence currently available

The [registry](../evidence-review/evidence.json) links **five peptide identities** to receptor and saltiness evidence. All five have numerical receptor records; **four have numerical saltiness observations and one is graphical only**. Twelve numerical formulation/dose conditions yield fourteen heterogeneous endpoint values. They cannot be pooled into one sensory score or counted as fourteen independent candidates.

Original-method checks preserve several important distinctions:

- Ohsu's quantitative panel measures kokumi/thickness; Broadhead provides receptor EC50 estimates and uncertainty without human saltiness measurements.
- AMPC extract assays and human patty profiles differ in material processing and control contrasts. Kim2021 overall liking and Kim2022 extract responses also remain separate from purified-compound saltiness effects.
- Deng's equimolar supplement concerns umami and murine STC-1 responses. Cornut reports alternative GSH taste-receptor activity in specified constructs, including a human/rat umami receptor.
- The recovered Cao2026 16-peptide study contains human sensory work, but its numerical supplementary saltiness tables are electronic-tongue results and its cellular assay concerns TAS1R1.

[Evidence guide and source records](../evidence-review/README.md) · [29 October source qualification](../evidence-review/Followup_Source_Qualification_20261029.md)

The 80-record indexed source screen is bounded search coverage, not a systematic review. Missing measurements remain missing; non-significance does not establish equivalence.

## Next decision

The [current test design](NEXT_TEST_DESIGN.md) specifies a comparison of selection with and without measured CaSR information at the same follow-up budget. It requires:

1. A defined candidate panel with measured functional human-CaSR activity for the exact chemical identities.
2. Controlled human mixture-minus-background saltiness measurements, with interpretable dose, matrix, sodium/pH and paired uncertainty.
3. A justified minimum useful sensory effect, a useful selection-gain margin and independent evaluation material.

No recovered panel currently satisfies those requirements. The Cao source needs the numerical human mixture/control comparisons and matched receptor records. The N102F analysis needs experiment-level response data to strengthen its functional interpretation; it does not supply the missing human outcome.

Further fitting or broad docking on the existing proxies would not resolve this data gap. New matched measurements could reopen the comparison.

## Related questions

Improving **consumer liking** is a separate application goal supported by published MSG examples. A peptide-specific benefit, transfer to frozen food and actual sodium reduction each require their own measurements. [Sensory outcomes](SENSORY_OUTCOMES.md).

The [arginyl-control note](ARGINYL_STARTING_POINT.md) and [RP/KP sensory follow-up](PROLYL_SENSORY_FOLLOWUP.md) preserve an earlier functional-comparison branch. The three-compound potency/threshold audit rejects only an exact proportional conversion; it does not refute a positive association or CaSR involvement.
