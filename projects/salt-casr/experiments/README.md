# Completed analyses

[Project overview](../README.md) · [Research timeline](../docs/RESEARCH_TIMELINE.md) · [Shared data](../data/README.md) · [Current evidence](../evidence-review/README.md)

## Original work completed before 20 October

| Analysis | Main question |
| --- | --- |
| [01 · CaSR models and docking](01-casr-models-and-docking/README.md) | Can receptor-activity prediction and docking prioritize analogues? |
| [02 · Sensory source transfer](02-sensory-source-transfer/README.md) | Do fixed sequence models transfer between literature sources? |
| [03 · Assay conditions and dose](03-assay-dose-response/README.md) | Do labels and candidate rankings change with endpoint and dose? |
| [04 · TRPV1 membrane access](04-trpv1-membrane-access/README.md) | Where are the proposed peptide contacts relative to the membrane? |
| [05 · Functional assay controls](05-functional-assay-controls/README.md) | Which component and perturbation controls are required to measure enhancement? |

## Additions on 27–29 October

- [27 October fixed models, Gly-effect prediction and independent saved-pose check](01-casr-models-and-docking/followups/2026-10-27/README.md).
- [29 October bound-pose local-relaxation diagnostic](01-casr-models-and-docking/followups/2026-10-29-local-relaxation/README.md).
- [29 October WT/N102F ligand-response analysis](05-functional-assay-controls/followups/2026-10-29/README.md).
- [Primary-source qualification and compound/condition registry](../evidence-review/README.md).

These are computational analyses of published observations. They do not constitute additional biological studies or independent confirmation.

## Inspect or reproduce

Within each original experiment, `code/` holds readable scripts, `results/` holds reviewed outputs and `verification/` contains supplied execution records. Dated follow-ups document their own file layout. New local outputs go to ignored `runs/latest/` folders where supported.

Experiments 01, 02, 03 and 05 include self-contained executed notebooks with embedded inputs and code. The three previously shared notebook URLs remain byte-identical aliases. See [execution entry points](../README.md#run-an-experiment).

The [current research status](../docs/RESEARCH_STATUS.md) and [current test design](../docs/NEXT_TEST_DESIGN.md) govern new work; reproducing an old analysis does not create new independent evidence.
