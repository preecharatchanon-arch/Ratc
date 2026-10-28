# CaSR, kokumi and sensory enhancement

**Current question:** can measured calcium-sensing receptor (CaSR) activity improve selection of peptides that increase human saltiness under defined conditions? The current evidence does not yet establish useful selection performance.

Research by **Ratchanon Preecha** · Updated 28 October 2026

This project connects published peptide chemistry, receptor assays and human sensory evidence. It contains **five completed computational analyses**, a later fixed CaSR-model/pose follow-up, and an ongoing assessment of whether the actual measurements overlap by compound and conditions. No new human or biological measurements are claimed.

**Start here:** [Current direction and blockers](docs/RESEARCH_STATUS.md) · [Sensory outcomes and the liking opportunity](docs/SENSORY_OUTCOMES.md) · [Evidence review](evidence-review/README.md) · [Next test design](docs/NEXT_TEST_DESIGN.md)

## What the evidence currently supports

- Fixed follow-up comparisons use 58 numerical/range compounds and 26 chemical families. Their gain intervals cross zero; reliable incremental receptor-prediction benefit has not been established. [Protocol, code and saved results](experiments/01-casr-models-and-docking/followups/README.md).
- The source registry contains five named receptor/saltiness links across different doses, matrices and endpoints. They do not form a jointly tested peptide-selection benchmark. The bounded 80-record indexed source screen and original-method qualifications are in the [evidence review](evidence-review/README.md).
- A food could be more enjoyable without becoming significantly saltier. Published MSG studies support that possibility; a peptide-specific benefit in a defined food still needs actual liking data. This [application opportunity](docs/SENSORY_OUTCOMES.md) is separate from the saltiness question.

**Next decision:** qualify actual matched receptor/saltiness measurements before fitting a selector. Material processing, dose policy, receptor specificity and human outcome must align. A meaningful success criterion and independent evaluation data are still missing. [Full test card](docs/NEXT_TEST_DESIGN.md).

The earlier [arginyl-control](docs/ARGINYL_STARTING_POINT.md) and [RP/KP sensory](docs/PROLYL_SENSORY_FOLLOWUP.md) notes remain historical branches. They do not supersede the current CaSR question or establish that a new laboratory experiment is ready.

## Latest completed tests: actual results

These are our computational reanalyses of existing published measurements and saved poses, completed before this README update. They are exploratory, not independent biological confirmation.

| Test | Actual result | What it changes |
| --- | --- | --- |
| **Fixed receptor-prediction comparison** | 58 compounds, 26 chemical families. Positional-model MAE **0.7653** versus **0.7989** for the existing nearest-three model; error reduction **0.0337** log units, conditional family-bootstrap 95% interval **[-0.1104, 0.1553]**. | The point error improves, but the interval crosses zero. Reliable incremental gain is not established. |
| **Predicting the effect of adding terminal Gly** | 11 matched core/Gly peptide pairs. Prediction MAE **0.9151** versus **0.8851** for the training-mean effect; gain **-0.0300**, interval **[-0.2498, 0.1842]**. | The tested chemistry-based rule does not reliably improve prediction of the Gly-extension effect. |
| **Independent native-pose verification** | Symmetry-corrected spyrmsd top-pose RMSD **4.7803 Å**. The closest of the ten saved poses is **2.3158 Å**, ranked fifth; no rigid alignment. | Confirms the pose-ranking limitation. This checks saved coordinates; it is not new docking. |

[Protocol and reproduction guide](experiments/01-casr-models-and-docking/followups/2026-10-27/README.md) · [Model summary](experiments/01-casr-models-and-docking/followups/2026-10-27/output/summary.json) · [Fold predictions](experiments/01-casr-models-and-docking/followups/2026-10-27/output/fold_predictions.csv) · [Independent pose result](experiments/01-casr-models-and-docking/followups/2026-10-27/output/independent_RMSD_check.json)

The gain intervals are conditional on the fitted models and previously inspected data. Published concentration ranges are not confidence intervals. Receptor-prediction error is not human saltiness performance.

## Meaningful published data recovered

These measurements belong to the original authors. Our contribution here is recovering, attributing and checking their endpoints and conditions, not discovering new effective compounds.

| Evidence recovered | What is actually available | Interpretation |
| --- | --- | --- |
| **Five named receptor/saltiness links** | Gamma-Glu-Abu (Abu = 2-aminobutyric acid), gamma-Glu-Val-Gly, gamma-Glu-Ala, gamma-Glu-Val and reduced glutathione (GSH). Four have numerical saltiness observations here; gamma-Glu-Val is graphical only. Nine numerical formulation/dose conditions yield eleven heterogeneous endpoint values. | Real compound-level overlap exists, including non-significant GSH conditions. It is not a jointly tested candidate panel; repeated doses/time windows are not independent compounds, and the values cannot be pooled into one score. |
| **Original Ohsu and Broadhead receptor papers** | Ohsu supplies a six-identity receptor/kokumi panel. Broadhead supplies four peptide EC50 estimates with SE and experiment counts. | Useful receptor and kokumi documentation, but neither supplies the required separate human saltiness panel. The apparent Ohsu table/caption potency discrepancy remains unresolved. |
| **AMPC beef-offal application report** | Human-CaSR responses to extracts and human flash profiling of patties containing extracts. Liver-G and Lung-G names overlap, but processing and receptor/human control contrasts differ. | A relevant preparation-level receptor/food-sensory connection; no individual peptide saltiness effects or valid two-extract predictor test. |
| **Deng2026 original supplement** | Equal-molar GSH, gamma-Glu-Val and gamma-Glu-gamma-Glu-Val comparisons in an MSG background, alongside STC-1 calcium/CCK measurements. | A useful dose-controlled **umami** comparison. Cellular inhibitor responses are not human saltiness scores or human-CaSR EC50 values. |
| **Palatability without a significant saltiness difference** | Hayabuchi2020, 584 participants: at 0.9% NaCl, adding 0.3% MSG raises palatability VAS **40.7 → 51.6**; saltiness **73.8 → 72.3**, reported **P=0.3013**. | Supports the separate liking opportunity. These are published simple-solution results, not our peptide or frozen-food results; equal NaCl is not equal total sodium. Non-significance is not equivalence. |

[Compound/condition registry and source locators](evidence-review/evidence.json) · [Original-method assessment](evidence-review/ASSESSMENT.md) · [Detailed source qualifications](evidence-review/source_qualification.json) · [Palatability study, conditions and uncertainty](docs/SENSORY_OUTCOMES.md)

The **80-record indexed screen** documents search coverage and source decisions, not 80 experiments or newly measured peptides. Missing outcomes remain missing. These findings narrow the next decision: actual matched measurements and a justified useful-effect criterion are needed before fitting a CaSR-to-saltiness selector.

## Experiments

| Experiment | Question and completed result | Open |
| --- | --- | --- |
| **01 · CaSR models and docking** | Original best observed MAE **0.799 pEC₅₀ units**; later fixed positional-model MAE **0.7653**, with gain interval crossing zero. Native top-pose RMSD remains **4.78 Å**. | [Original report](experiments/01-casr-models-and-docking/README.md) · [Executed notebook](experiments/01-casr-models-and-docking/CaSR_Research_Workbench.ipynb) · [Later follow-up](experiments/01-casr-models-and-docking/followups/README.md) |
| **02 · Sensory source transfer** | On 251 sensory-tagged peptides, fixed Extra Trees mean ROC-AUC falls from **0.686** with random splits to **0.286** with reference-and-sequence holdouts. Other baselines and post-hoc controls are reported separately. | [Report](experiments/02-sensory-source-transfer/README.md) · [Executed notebook](experiments/02-sensory-source-transfer/Saltiness_Sensory_Validation.ipynb) · [Results](experiments/02-sensory-source-transfer/results/) |
| **03 · Assay conditions and dose** | NGYDMR's benchmark negative conflicts with enhancement evidence under a different assay. Published dose curves reverse the preferred peptide. Four fixed baselines retrieve only **one of three reported enhancers** in their top three for the six-candidate Pleurotus panel. | [Report](experiments/03-assay-dose-response/README.md) · [Executed notebook](experiments/03-assay-dose-response/Saltiness_Assay_Conditions.ipynb) · [Results](experiments/03-assay-dose-response/results/) |
| **04 · TRPV1 membrane access** | Three cited peptide-contact residues lie in the membrane core and one on the cytoplasmic side. The result holds across three experimental structures; actual bound DkTx contacts provide a distinct comparator. | [Report](experiments/04-trpv1-membrane-access/README.md) · [Code](experiments/04-trpv1-membrane-access/code/) · [Results](experiments/04-trpv1-membrane-access/results/) |
| **05 · Functional assay controls** | A 32-condition human taste-cell panel and separate knockdown comparisons show why dose, peptide-only controls and NaCl baselines matter. Soy sensory and organoid outcomes remain separate. | [Report](experiments/05-functional-assay-controls/README.md) · [Executed notebook](experiments/05-functional-assay-controls/Arginyl_Functional_Controls.ipynb) · [Code](experiments/05-functional-assay-controls/code/README.md) · [Results](experiments/05-functional-assay-controls/results/README.md) |

These endpoints are kept separate: **CaSR activity, channel structure, standalone saltiness and enhancement in NaCl are different measurements**. The project has not established a new effective or food-suitable salt enhancer. None of these computational outputs is a receptor-response or sensory experiment performed by us.

## Run an experiment

These entry points reproduce completed analyses. They are not the next scientific action; the current matched-data gate is described above.

| Experiment | Execution | Verified status |
| --- | --- | --- |
| 01 | [Open in Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/salt-casr/experiments/01-casr-models-and-docking/CaSR_Research_Workbench.ipynb), choose CPU, Run all | Reviewed local execution and source checks; full docking optional through the notebook configuration |
| 02 | [Open in Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/salt-casr/experiments/02-sensory-source-transfer/Saltiness_Sensory_Validation.ipynb), CPU | Every code cell executed locally; Colab browser not directly tested |
| 03 | [Open in Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/salt-casr/experiments/03-assay-dose-response/Saltiness_Assay_Conditions.ipynb), CPU | Local execution plus a [verified user-supplied Colab export](experiments/03-assay-dose-response/verification/COLAB_RUN_VERIFICATION.json) |
| 04 | Follow the [local commands](experiments/04-trpv1-membrane-access/README.md#reproduce-and-inspect), CPU | Fresh isolated Python 3.12 execution; no Colab execution claimed |
| 05 | [Open in Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/salt-casr/experiments/05-functional-assay-controls/Arginyl_Functional_Controls.ipynb), CPU | Every notebook code cell executed locally with an isolated worker; soy source-access limits remain explicit |

The four canonical notebooks are self-contained: inputs and reviewed source are embedded, and no API key or upload is required. Repository scripts use shared `data/` inputs and write fresh outputs to an ignored `runs/latest/` folder inside their experiment. The committed `results/` folders retain the reviewed results. Local commands must be run from the relevant experiment folder; each has pinned requirements.

## Folder guide

| Folder | Contents |
| --- | --- |
| [experiments/](experiments/README.md) | Five numbered reports with code, results, protocols and verification |
| [data/](data/README.md) | CaSR chemistry inputs, sensory benchmark and assay tables, TRPV1 sequence snapshots and coordinate download manifest, functional comparator tables |
| [evidence-review/](evidence-review/README.md) | Current attributed receptor/sensory registry, source screen, original-method qualifications and explicit missing information |
| [archives/](archives/README.md) | Original run ZIPs and separately labelled earlier CaSR docking reference files |
| [docs/](docs/RESEARCH_STATUS.md) | Current decisions, next-test requirements, sensory endpoint definitions and dated historical research branches |
| [verification/](verification/README.md) | Organization review, file-move map and artifact integrity checks |

## Previously shared links

The project URL stays the same. Previously shared notebook URLs are retained as **byte-identical runnable aliases**; the table above gives their canonical locations. Earlier experiment-folder URLs open a short page linking the numbered report. Original ZIP contents keep their original execution layout and are explained in [archives](archives/README.md).

## Reading the measurements

**MAE** is mean absolute prediction error; pEC₅₀ is a logarithmic receptor-response concentration, not a sensory score. **RMSD** measures pose-coordinate displacement in ångströms. **ROC-AUC** measures binary ranking performance, with 0.5 as chance ranking. The analyses measure different endpoints, so these numbers cannot be compared as a common performance score.

## Data and attribution

See the [data guide](data/README.md) for source citations, units, evidence labels and licence boundaries. SaltyMeta's author-curated labels are not independently verified for every peptide. Source-table transcriptions and computational results have different evidential status. Full publisher articles are not redistributed.

The [15 October organization review](verification/ORGANIZATION_REVIEW.json) records the original layout checks; the [verification guide](verification/README.md) describes the current integrity check. Original execution records remain with their experiments. The repository [checksum index](../../ARTIFACT_CHECKSUMS.json) identifies the actual current files, including compatibility notebook aliases.
