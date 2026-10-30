# CaSR, kokumi and sensory enhancement

**Can measured calcium-sensing receptor (CaSR) activity help select peptides that increase human saltiness under defined conditions?**

Research by **Ratchanon Preecha** · Documentation updated **30 October 2026**

This project analyzes published peptide chemistry, receptor assays and human taste measurements. It contains five original computational analyses, additional tests completed on 27–29 October, and a source-by-source evidence review. **Useful CaSR-guided saltiness selection has not yet been established.** The biological measurements belong to the cited researchers; this project's contributions are data qualification and computational reanalysis.

## Start here

| If you want to… | Read |
| --- | --- |
| Understand the question, current conclusion and missing evidence | [Research status](docs/RESEARCH_STATUS.md) |
| See what was added after 20 October | [Dated research timeline](docs/RESEARCH_TIMELINE.md) |
| Inspect human measurements and their receptor links | [Evidence guide](evidence-review/README.md) |
| Assess whether the next test is ready | [Current test design](docs/NEXT_TEST_DESIGN.md) |
| Inspect or reproduce a completed analysis | [Five original analyses](experiments/README.md) and the [dated CaSR follow-ups](experiments/01-casr-models-and-docking/followups/README.md) |

## Research timeline

Dates below describe work performed in this project, not the publication dates of the underlying biological studies.

| Period | Work and status |
| --- | --- |
| **Before 20 October** | Five original analyses: CaSR prediction/docking, sensory source transfer, dose and endpoint dependence, TRPV1 access, and functional-assay controls. |
| **27 October** | Added training-mean comparison, family-bootstrap uncertainty, fixed positional/context models, an 11-pair Gly-effect prediction task and independent saved-pose verification. |
| **28–29 October** | Qualified additional primary receptor/sensory sources and wrote the matched-data test requirements. Separate liking evidence was reviewed on 28 October. |
| **29 October** | Executed a local bound-pose diagnostic and an exploratory WT/N102F ligand-response analysis. |
| **30 October** | Improved documentation, corrected an endpoint label and refreshed navigation/integrity metadata. No new scientific experiment. |

[Detailed milestones, results and source links](docs/RESEARCH_TIMELINE.md)

## Latest additions on 29 October 2026

- **Ligand-dependent response:** N102F shifts the reported EC50 values of γ-Glu-Val and γ-Glu-Val-Gly in opposite directions. The result is an exploratory functional comparison with small-sample and rounding assumptions, not a direct binding measurement. [Report and source table](experiments/05-functional-assay-controls/followups/2026-10-29/REPORT.md).
- **Docking diagnosis:** local optimization preserves a reference-like pose, but the displaced pose still receives the better Vina score. [Frozen design and outputs](experiments/01-casr-models-and-docking/followups/2026-10-29-local-relaxation/README.md).
- **Source qualification:** a recovered 16-peptide human sensory study does not provide the missing matched CaSR panel. Its numerical supplementary saltiness tables are electronic-tongue outputs and its cellular assay concerns TAS1R1. [Assessment](evidence-review/Followup_Source_Qualification_20261029.md).

## Completed results and what they mean

| Comparison | Saved result | Interpretation |
| --- | --- | --- |
| **Fixed receptor prediction**, 58 compounds / 26 families | Positional-model MAE **0.7653** versus **0.7989** for the existing nearest-three model; improvement **0.0337** pEC50 units, conditional family-bootstrap 95% interval **[-0.1104, 0.1553]**. | Point error decreases, but reliable improvement is not established. This predicts receptor response, not human saltiness. |
| **Predicting terminal-Gly effects**, 11 matched pairs | MAE **0.9151** versus **0.8851** for the training-mean effect; gain **-0.0300**, interval **[-0.2498, 0.1842]**. | The tested chemical representation does not reliably predict the observed context dependence. |
| **Independent check of ten original saved poses** | Symmetry-corrected top-pose RMSD **4.7803 Å**; closest pose **2.3158 Å**, ranked fifth. | Confirms the earlier placement/ranking limitation. This was a coordinate check, not new docking. |
| **Local relaxation from the known bound pose** | Reference-like RMSD **0.595 Å**, but the displaced pose still scores better. | The combined pose/ranking criterion failed; conditional global searches were not run. |
| **WT/N102F comparison** | Opposite γ-EV/γ-EVG EC50 shifts survive the stated summary-data and rounding analysis; complete potency-order reversal does not survive the conservative rounding analysis. | Useful exploratory functional contrast; expression and signaling remain competing explanations. |
| **Receptor–human evidence overlap** | Five linked identities; four have numerical saltiness observations and one has graphical observations. Twelve numerical formulation/dose conditions yield fourteen heterogeneous endpoint values. | Real overlap exists, but it is not a jointly tested candidate panel or a common regression target. |

[27 October protocol, code and predictions](experiments/01-casr-models-and-docking/followups/2026-10-27/README.md) · [29 October docking diagnostic](experiments/01-casr-models-and-docking/followups/2026-10-29-local-relaxation/README.md) · [29 October functional analysis](experiments/05-functional-assay-controls/followups/2026-10-29/README.md)

These analyses use previously inspected data and remain exploratory. Bootstrap intervals are conditional on fitted predictions; published concentration ranges are not confidence intervals. Repeated doses, assessors, cells and time windows do not create additional independent peptide candidates.

## Human evidence and the next decision

The source registry links **γ-Glu-Abu** (Abu = 2-aminobutyric acid), **γ-Glu-Val-Gly**, **γ-Glu-Ala**, **γ-Glu-Val** and **reduced glutathione (GSH)** to receptor and saltiness evidence. All five have numerical receptor records in the registry; γ-Glu-Val has graphical-only saltiness observations here.

The [evidence guide](evidence-review/README.md) separates human saltiness from kokumi/thickness, electronic-tongue values, extract responses and general cellular calcium signals. It preserves dose, matrix, sodium basis, pH, assay/species, source overlap, missing values and uncertainty. The 80-record indexed source screen describes bounded search coverage, not 80 experiments or a systematic review.

**Next decision:** obtain and qualify an actual shared peptide panel with measured functional human-CaSR activity and controlled, separately rated human saltiness. Then compare a fixed selection rule with and without CaSR information at the same follow-up budget. A useful-effect margin and independent evaluation material must be justified first. [Full test design](docs/NEXT_TEST_DESIGN.md).

A separate application question is whether a formulation improves **liking** without a significant increase in saltiness. Published MSG studies support that possibility; they do not establish a peptide-specific or frozen-food benefit. [Outcomes, primary example and sodium distinction](docs/SENSORY_OUTCOMES.md).

## Experiments

These five reports preserve the original work completed before 20 October. Later additions have their own dated folders and are not presented as new biological studies.

| Original analysis | Question and retained result | Inspect |
| --- | --- | --- |
| **01 · CaSR models and docking** | Can chemistry and docking prioritize analogues? Original best held-family MAE **0.799 pEC50**; native top-pose RMSD **4.78 Å**. | [Report](experiments/01-casr-models-and-docking/README.md) · [Later follow-ups](experiments/01-casr-models-and-docking/followups/README.md) |
| **02 · Sensory source transfer** | Do fixed sequence models transfer across sources? ExtraTrees AUC **0.686** under random splits versus **0.286** under reference-and-sequence holdouts; parsing sensitivity and other baselines are reported separately. | [Report](experiments/02-sensory-source-transfer/README.md) · [Results](experiments/02-sensory-source-transfer/results/) |
| **03 · Assay conditions and dose** | Are labels and rankings stable? Standalone taste differs from enhancement; published dose curves change the preferred peptide. | [Report](experiments/03-assay-dose-response/README.md) · [Results](experiments/03-assay-dose-response/results/) |
| **04 · TRPV1 membrane access** | Are proposed contacts positioned for rapid extracellular action? Reported contacts map to membrane/cytoplasmic regions in three experimental structures. Access and function remain untested. | [Report](experiments/04-trpv1-membrane-access/README.md) · [Results](experiments/04-trpv1-membrane-access/results/) |
| **05 · Functional assay controls** | Which response comparison measures enhancement? A 32-condition human taste-cell panel and separate knockdown/soy comparisons show why dose and component baselines matter. | [Report](experiments/05-functional-assay-controls/README.md) · [Later ligand contrast](experiments/05-functional-assay-controls/followups/README.md) |

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

