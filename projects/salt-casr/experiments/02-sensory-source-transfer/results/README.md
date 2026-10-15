# 02 · Sensory source transfer — results

[Experiment report](../README.md) · [Code](../code/README.md) · [Shared inputs](../../../data/README.md)

These files are the reviewed result snapshot. New local runs write to `../runs/latest/`, leaving this evidence intact. Read the report before interpreting a score or label.

## Key outputs

| File | What to inspect |
| --- | --- |
| [evidence_and_transfer.png](evidence_and_transfer.png) | Start here: evidence audit, split comparison and matched controls. |
| [metric_summary.csv](metric_summary.csv) | Metrics summarized across partition seeds. |
| [metrics.csv](metrics.csv) | Every primary model/cohort/split/seed metric. |
| [out_of_fold_predictions.csv](out_of_fold_predictions.csv) | 22,956 retained primary out-of-fold predictions. |
| [curated_records.csv](curated_records.csv) | 580 curated source records; the shared benchmark input has identical bytes. |
| [evidence_audit.json](evidence_audit.json) | Counts and limits of supplied evidence categories. |
| [split_diagnostics.json](split_diagnostics.json) | Group sizes, fold class balance and split diagnostics. |
| [posthoc_matched_fold_control.csv](posthoc_matched_fold_control.csv) | Random controls matched to the reference-fold sizes and class counts. |
| [posthoc_reference_parse_sensitivity.csv](posthoc_reference_parse_sensitivity.csv) | Sensitivity to a more restrictive reference parse; post-hoc. |
| [literature_panel_scores.csv](literature_panel_scores.csv) | Scores for the later selected literature panel, not an external accuracy estimate. |
| [arginyl_cellular_controls.csv](arginyl_cellular_controls.csv) | Separate human taste-cell evidence; not interchangeable with sensory labels. |
| [verification.json](verification.json) | Recalculated metric counts and prediction/split consistency checks. |

## Other retained files

Remaining JSON, CSV, structure and figure files support the calculations above. Original logs and full run payloads, where supplied, remain in the [archives](../../../archives/README.md). Sources, units and unresolved evidence are explained in the experiment report.
