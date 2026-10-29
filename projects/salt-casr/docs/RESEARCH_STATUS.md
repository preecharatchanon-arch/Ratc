# Research status — 29 October 2026

[Project](../README.md) · [Evidence review](../evidence-review/README.md) · [Test design](NEXT_TEST_DESIGN.md) · [Sensory outcomes](SENSORY_OUTCOMES.md)

## Current direction

Can **measured functional CaSR activity** improve selection of peptides that
increase **human saltiness under defined conditions**? This remains the main
selection question. Available observations do not yet qualify an independent
comparison of a frozen baseline selector with/without CaSR data.

Improving consumer liking without increasing saltiness is a separate,
potentially useful application goal. Published MSG studies make it plausible;
they do not demonstrate that our peptides achieve it, that CaSR predicts it,
or that the benefit transfers to frozen food. The [sensory guide](SENSORY_OUTCOMES.md)
defines the outcomes and the required distinction.

## Completed computational findings

| Work | Retained finding | Current implication |
| --- | --- | --- |
| [01: original CaSR models/docking](../experiments/01-casr-models-and-docking/README.md) | Original best held-family MAE 0.7989 pEC50; native top-pose RMSD 4.7803 Å | Receptor prediction and pose placement do not validate human saltiness selection. |
| [01: 27 Oct follow-up](../experiments/01-casr-models-and-docking/followups/README.md) | 58 compounds/26 families; positional-model gain 0.0337, conditional 95% interval [-0.1104,0.1553]; 11-pair Gly-effect gain interval [-0.2498,0.1842] | No reliable incremental gain; previously inspected data remain exploratory. Independent spyrmsd confirms top-pose 4.7803 Å. |
| [01: local-relaxation diagnostic](../experiments/01-casr-models-and-docking/followups/2026-10-29-local-relaxation/README.md) | Relaxed reference RMSD0.595 Å; common-reference score−7.021 versus−7.828 for the displaced pose | Reference-like geometry is locally accessible, but the combined ranking gate fails. Conditional new global searches were not run. |
| [05: functional ligand contrast](../experiments/05-functional-assay-controls/followups/2026-10-29/README.md) | N102F has opposing γ-EV/γ-EVG EC50 shifts under conditional rounding-sensitive summary bounds; full ordering reversal is inconclusive | An exploratory functional control, not a direct-binding mechanism or human selector validation. Raw n3 sampling assumptions remain unchecked. |
| [02: sensory source transfer](../experiments/02-sensory-source-transfer/README.md) | Fixed Extra Trees mean AUC 0.686 under random partitions versus 0.286 under reference+sequence holdouts | Source/endpoint dependence limits transfer; other baselines reported separately. |
| [03: conditions and dose](../experiments/03-assay-dose-response/README.md) | Context-dependent benchmark negatives and dose-ranking reversals; four baselines each retrieve one known enhancer in their top three of six candidates | Preserve dose, matrix and unresolved results; no population screening or sodium-replacement claim. |
| [04: TRPV1 access](../experiments/04-trpv1-membrane-access/README.md) | Proposed contacts lie in membrane/cytoplasmic regions | Structural access question, not proof of absent binding or human efficacy. |
| [05: functional controls](../experiments/05-functional-assay-controls/README.md) | 32 condition-specific human taste-cell records and distinct knockdown/soy comparisons | Attributed reanalysis; neither new wet-lab work nor a matched CaSR/saltiness candidate panel. |

The original five analyses and their executed notebooks remain preserved.
The later follow-up analyzes existing observations; it is not a sixth
independent biological study. Broad docking, MD and model sweeps remain
unsupported. The 9J7I structure was already used.

## New source qualification on 29 October

A full 16-peptide human sensory source, Cao2026 (Food Chemistry:X104238), was
recovered with its original supplement. Separate saltiness is assessed, but
human paired numerical ratings were not recovered. Its precise supplementary
saltiness numbers belong to an electronic tongue, and the functional cellular
readout concerns TAS1R1 rather than CaSR. Three additional primary leads retain
explicit access, species and endpoint limits. See the [full qualification](../evidence-review/Followup_Source_Qualification_20261029.md)
and [16-identity inventory](../evidence-review/cao2026_panel_inventory.csv).
No numerical human labels were reconstructed or new selector fitted.

The registry now records twelve numerical formulation/dose conditions and
fourteen heterogeneous endpoint values for five linked identities. The same
source's repeated measurements are not independent compounds or studies.

## Earlier source work retained

The [registry](../evidence-review/evidence.json) links five named peptide
identities to receptor and saltiness evidence, with heterogeneous conditions
and uncertainty. Four have numerical saltiness observations here and one has
graphical observations. Neither count is a common candidate denominator.
Missing tests are not negative labels; non-significance is not equivalence.

Two title/abstract searches returned 48 and 65 records, with 33 shared records:
80 unique indexed records. This is a bounded screen, not a systematic review.
Original-source qualifications identify specific limitations:

- AMPC2024-1087 measures human-CaSR extract responses and human patty profiles,
  but analytical/food preparations and receptor/human control contrasts differ.
- Chicken-soup component-addition scores are electronic-tongue outputs;
  its human panel evaluated whole soups.
- Deng2026's recovered equimolar supplement measures umami and murine STC-1
  cellular responses, not separate saltiness or hCaSR EC50.
- Cornut2025 supplies functional evidence for alternative GSH taste-receptor
  pathways in specified constructs, including a human/rat umami receptor.
- Ohsu's quantitative panel measures kokumi/thickness; Broadhead supplies
  receptor EC50/SE/n without human saltiness. Kim2021 liking and Kim2022 extract
  assays do not become a compound-level saltiness benchmark.

Read the [assessment](../evidence-review/ASSESSMENT.md) and
[source qualifications](../evidence-review/source_qualification.json) for
locators, conditions, unresolved discrepancies and limits. No new numerical
scientific experiment ran during that assessment or this repository update.
Integrity checks establish file consistency only.

## Next precise action

The [test card](NEXT_TEST_DESIGN.md) remains gated on actual matched measurements.
The new 16-peptide lead needs the human mixture-minus-NaCl comparison, paired
assessor/session uncertainty, exact dose/chemical form and sodium/pH metadata.
It could support a CaSR-selector comparison only with measured functional
hCaSR data for exact matching identities and an adequate independent candidate
panel. Neither a precise instrument value nor a general cellular calcium
response supplies a missing field.

The WT/N102F ligand contrast also lacks raw experiment-level response curves,
unrounded EC50 values and numerical Emax uncertainty. Its conditional summary
analysis is already completed; do not rerun it as confirmation or infer a
binding mechanism from the mutation alone.

There is no qualified common panel or justified useful-gain margin yet.
New original data can reopen qualification; the failed download routes remain
closed without a new legitimate source. Current evidence supports neither a
broad unknown-peptide docking screen nor more proxy-label fitting. Earlier
acquisition queues do not supersede these prerequisites.

## Historical branches and claim boundaries

The [arginyl-control note](ARGINYL_STARTING_POINT.md) and
[RP/KP sensory follow-up](PROLYL_SENSORY_FOLLOWUP.md) remain dated records of a
different functional-comparison branch; they are not the current execution
queue. The three-compound potency/threshold audit rejects only an exact
proportional-scale assumption, not positive association or CaSR involvement.

No synthesis, receptor assay, human sensory experiment, novel effective food
compound, food-use approval or proven sodium reduction is claimed as our own.
Umami, kokumi, overall liking, intrinsic taste, receptor activity and saltiness
remain separate outcomes. AIMO remains a separate project.

