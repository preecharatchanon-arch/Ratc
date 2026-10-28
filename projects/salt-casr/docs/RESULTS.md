# Findings and figures

[Project overview](../README.md) · [Research status](RESEARCH_STATUS.md) · [Shared data](../data/README.md)

Five completed computational analyses follow one research question: what evidence is needed before using a model to select a saltiness enhancer? The figures below show the retained findings; each links to the complete report and underlying result tables.

## Latest follow-up and evidence qualification

The [27 October fixed comparison](../experiments/01-casr-models-and-docking/followups/README.md)
uses 58 compounds and 26 chemical families. The primary MAE-gain interval
crosses zero; the 11-pair Gly-effect comparison also fails to establish gain.
An independent saved-pose check confirms the native top-pose RMSD of 4.7803 Å.
These are exploratory reanalyses, not fresh biological confirmation.

The [current source review](../evidence-review/README.md) records five named
receptor/saltiness links and a bounded 80-record indexed screen. It does not
supply a common candidate panel for fitting a selector. Read the
[current status](RESEARCH_STATUS.md) and [test design](NEXT_TEST_DESIGN.md)
before treating any completed analysis as the next action.

## 01 · CaSR models and docking

Model transfer remains inaccurate and reference-pose ranking is weak.

[Report](../experiments/01-casr-models-and-docking/README.md) · [Tables and figure guide](../experiments/01-casr-models-and-docking/results/README.md)

![Held-family prediction errors](../experiments/01-casr-models-and-docking/results/notebook/prediction_validation.png)

## 02 · Sensory source transfer

Reference-held-out performance is unstable; random splits overstate the tested pipeline’s usefulness.

[Report](../experiments/02-sensory-source-transfer/README.md) · [Tables and figure guide](../experiments/02-sensory-source-transfer/results/README.md)

![Source transfer and endpoint audit](../experiments/02-sensory-source-transfer/results/evidence_and_transfer.png)

## 03 · Assay conditions and dose

Standalone taste and enhancement differ, and published rankings reverse with dose.

[Report](../experiments/03-assay-dose-response/README.md) · [Tables and figure guide](../experiments/03-assay-dose-response/results/README.md)

![Dose-dependent ranking reversal](../experiments/03-assay-dose-response/results/dose_rank_reversal.png)

## 04 · TRPV1 membrane access

The contacts lie in a membrane/cytoplasmic region; access and function remain untested.

[Report](../experiments/04-trpv1-membrane-access/README.md) · [Tables and figure guide](../experiments/04-trpv1-membrane-access/results/README.md)

![Membrane depths and the observed DkTx comparator](../experiments/04-trpv1-membrane-access/results/membrane_site_comparison.png)

## 05 · Functional assay controls

A 32-condition human taste-cell panel, separate knockdown comparisons and soy endpoint contrasts determine useful controls for the next experiment.

[Report](../experiments/05-functional-assay-controls/README.md) · [Tables and figure guide](../experiments/05-functional-assay-controls/results/README.md)

![Functional assay conditions and control comparisons](../experiments/05-functional-assay-controls/results/functional_controls.png)

## What follows

The current evidence does not validate a new salt enhancer. The next research task is to identify condition-matched sensory and functional evidence that distinguishes direct receptor modulation from other explanations. A literature finding remains attributed to its authors; any new calculation must state what it adds.
