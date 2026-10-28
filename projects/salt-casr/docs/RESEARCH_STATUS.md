# Research status — 28 October 2026

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
| [02: sensory source transfer](../experiments/02-sensory-source-transfer/README.md) | Fixed Extra Trees mean AUC 0.686 under random partitions versus 0.286 under reference+sequence holdouts | Source/endpoint dependence limits transfer; other baselines reported separately. |
| [03: conditions and dose](../experiments/03-assay-dose-response/README.md) | Context-dependent benchmark negatives and dose-ranking reversals; four baselines each retrieve one known enhancer in their top three of six candidates | Preserve dose, matrix and unresolved results; no population screening or sodium-replacement claim. |
| [04: TRPV1 access](../experiments/04-trpv1-membrane-access/README.md) | Proposed contacts lie in membrane/cytoplasmic regions | Structural access question, not proof of absent binding or human efficacy. |
| [05: functional controls](../experiments/05-functional-assay-controls/README.md) | 32 condition-specific human taste-cell records and distinct knockdown/soy comparisons | Attributed reanalysis; neither new wet-lab work nor a matched CaSR/saltiness candidate panel. |

The original five analyses and their executed notebooks remain preserved.
The later follow-up analyzes existing observations; it is not a sixth
independent biological study. Broad docking, MD and model sweeps remain
unsupported. The 9J7I structure was already used.

## What the latest source work adds

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

Qualify an actual candidate-by-candidate primary table against the
[test card](NEXT_TEST_DESIGN.md). Newly grounded acquisition leads are:

| Original source | What is known | Actual blocker |
| --- | --- | --- |
| Reumiller2026, 10.1016/j.foodchem.2026.150843 | Primary abstract reports functional CaSR including Tyr-Phe-Tyr; online 18 Aug 2026 | Actual assay panel/species/values and separate human saltiness results not recovered; abstract silence is not proof no tests occurred. |
| Shiqin Wang2026 HKBU wheat-gluten thesis, awarded 28 Sep 2026 | Official record lists full text and abstract/TOC | Both official PDF downloads returned403; actual peptide identities and methods/results unknown. |

First establish whether separate human saltiness outcomes overlap actual
functional CaSR measurements for the same identified peptides and relevant
conditions. Retain selection history, chemical forms, dose/basis, matrix,
sodium, pH, calcium, species/readout, source overlap, censoring and uncertainty.
Receptor-only or sensory-only data alone would not qualify the selector test.

No practical sensory/yield margin is established and no experiment is queued.
A new legitimate original copy or qualified dataset is needed before execution.
Repeated inaccessible routes, proxy labels or another model fit do not fill
this prerequisite. All inspected material is development evidence.

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
