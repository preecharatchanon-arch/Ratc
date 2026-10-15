# Saltiness and taste-receptor research

Research by **Ratchanon Preecha** · Updated 15 October 2026

Can published chemical, receptor and sensory measurements support useful selection of compounds for lower-sodium foods? This project follows that question through **five completed computational analyses**. It began with CaSR peptide modelling and now includes sensory-label evaluation, dose-dependent effects, a structural check of proposed TRPV1 binding sites, and functional-assay controls.

**Start here:** [Findings and figures](docs/RESULTS.md) · [Experiments](experiments/README.md) · [Data](data/README.md) · [Research status](docs/RESEARCH_STATUS.md)

**The experiment table is the main index.** Each report links its code, saved results, protocol and verification. [Research status](docs/RESEARCH_STATUS.md) explains what the combined results support; [data](data/README.md) lists the shared inputs, sources and limits.

## Experiments

| Experiment | Question and completed result | Open |
| --- | --- | --- |
| **01 · CaSR models and docking** | Predicting an unseen chemical family remains inaccurate: best observed MAE **0.799 pEC₅₀ units**, about **6.29-fold** error. Native-ligand top-pose RMSD is **4.78 Å**. | [Report](experiments/01-casr-models-and-docking/README.md) · [Executed notebook](experiments/01-casr-models-and-docking/CaSR_Research_Workbench.ipynb) · [Results](experiments/01-casr-models-and-docking/results/) |
| **02 · Sensory source transfer** | On 251 sensory-tagged peptides, fixed Extra Trees mean ROC-AUC falls from **0.686** with random splits to **0.286** with reference-and-sequence holdouts. Other baselines and post-hoc controls are reported separately. | [Report](experiments/02-sensory-source-transfer/README.md) · [Executed notebook](experiments/02-sensory-source-transfer/Saltiness_Sensory_Validation.ipynb) · [Results](experiments/02-sensory-source-transfer/results/) |
| **03 · Assay conditions and dose** | NGYDMR's benchmark negative conflicts with enhancement evidence under a different assay. Published dose curves reverse the preferred peptide. Four fixed baselines retrieve only **one of three reported enhancers** in their top three for the six-candidate Pleurotus panel. | [Report](experiments/03-assay-dose-response/README.md) · [Executed notebook](experiments/03-assay-dose-response/Saltiness_Assay_Conditions.ipynb) · [Results](experiments/03-assay-dose-response/results/) |
| **04 · TRPV1 membrane access** | Three cited peptide-contact residues lie in the membrane core and one on the cytoplasmic side. The result holds across three experimental structures; actual bound DkTx contacts provide a distinct comparator. | [Report](experiments/04-trpv1-membrane-access/README.md) · [Code](experiments/04-trpv1-membrane-access/code/) · [Results](experiments/04-trpv1-membrane-access/results/) |
| **05 · Functional assay controls** | A 32-condition human taste-cell panel and separate knockdown comparisons show why dose, peptide-only controls and NaCl baselines matter. Soy sensory and organoid outcomes remain separate. | [Report](experiments/05-functional-assay-controls/README.md) · [Code](experiments/05-functional-assay-controls/code/README.md) · [Results](experiments/05-functional-assay-controls/results/README.md) |

These endpoints are kept separate: **CaSR activity, channel structure, standalone saltiness and enhancement in NaCl are different measurements**. The project has not established a new effective or food-suitable salt enhancer. None of these computational outputs is a receptor-response or sensory experiment performed by us.

## Run an experiment

| Experiment | Execution | Verified status |
| --- | --- | --- |
| 01 | [Open in Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/salt-casr/experiments/01-casr-models-and-docking/CaSR_Research_Workbench.ipynb), choose CPU, Run all | Reviewed local execution and source checks; full docking optional through the notebook configuration |
| 02 | [Open in Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/salt-casr/experiments/02-sensory-source-transfer/Saltiness_Sensory_Validation.ipynb), CPU | Every code cell executed locally; Colab browser not directly tested |
| 03 | [Open in Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/salt-casr/experiments/03-assay-dose-response/Saltiness_Assay_Conditions.ipynb), CPU | Local execution plus a [verified user-supplied Colab export](experiments/03-assay-dose-response/verification/COLAB_RUN_VERIFICATION.json) |
| 04 | Follow the [local commands](experiments/04-trpv1-membrane-access/README.md#reproduce-and-inspect), CPU | Fresh isolated Python 3.12 execution; no Colab execution claimed |
| 05 | Follow the [local commands](experiments/05-functional-assay-controls/README.md#reproduce-and-inspect), CPU | Executed numeric reanalysis and inspected figure; soy comparison limited to accessible abstract |

The three notebooks are self-contained: inputs and reviewed source are embedded, and no API key or upload is required. Repository scripts use shared `data/` inputs and write fresh outputs to an ignored `runs/latest/` folder inside their experiment. The committed `results/` folders retain the reviewed results. Local commands must be run from the relevant experiment folder; each has pinned requirements.

## Folder guide

| Folder | Contents |
| --- | --- |
| [experiments/](experiments/README.md) | Five numbered reports with code, results, protocols and verification |
| [data/](data/README.md) | CaSR chemistry inputs, sensory benchmark and assay tables, TRPV1 sequence snapshots and coordinate download manifest, functional comparator tables |
| [archives/](archives/README.md) | Original run ZIPs and separately labelled earlier CaSR docking reference files |
| [docs/](docs/RESEARCH_STATUS.md) | Project-level conclusions and interpretation limits |
| [verification/](verification/README.md) | Organization review, file-move map and artifact integrity checks |

## Previously shared links

The project URL stays the same. Previously shared notebook URLs are retained as **byte-identical runnable aliases**; the table above gives their canonical locations. Earlier experiment-folder URLs open a short page linking the numbered report. Original ZIP contents keep their original execution layout and are explained in [archives](archives/README.md).

## Reading the measurements

**MAE** is mean absolute prediction error; pEC₅₀ is a logarithmic receptor-response concentration, not a sensory score. **RMSD** measures pose-coordinate displacement in ångströms. **ROC-AUC** measures binary ranking performance, with 0.5 as chance ranking. The analyses measure different endpoints, so these numbers cannot be compared as a common performance score.

## Data and attribution

See the [data guide](data/README.md) for source citations, units, evidence labels and licence boundaries. SaltyMeta's author-curated labels are not independently verified for every peptide. Source-table transcriptions and computational results have different evidential status. Full publisher articles are not redistributed.

The [organization review](verification/ORGANIZATION_REVIEW.json) records what was checked in this layout update. Original execution records remain with their experiments. The repository [checksum index](../../ARTIFACT_CHECKSUMS.json) identifies the actual current files, including compatibility notebook aliases.
