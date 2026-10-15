# 03 · Assay conditions and dose — results

[Experiment report](../README.md) · [Code](../code/README.md) · [Shared inputs](../../../data/README.md)

These files are the reviewed result snapshot. New local runs write to `../runs/latest/`, leaving this evidence intact. Read the report before interpreting a score or label.

## Key outputs

| File | What to inspect |
| --- | --- |
| [dose_rank_reversal.png](dose_rank_reversal.png) | Start here: published dose-series means and reported SD, replotted. |
| [dose_rankings.csv](dose_rankings.csv) | Ranking of the three peptides at each reported nominal dose. |
| [dose_summary.csv](dose_summary.csv) | Within-peptide peaks and observed declines; descriptive group-mean comparisons. |
| [heldout_panel_scores.csv](heldout_panel_scores.csv) | Every fixed model score and tie flag for both complete candidate panels. |
| [panel_retrieval.csv](panel_retrieval.csv) | Reported enhancers retrieved in each model’s top three. |
| [training_eligibility.csv](training_eligibility.csv) | Included and excluded benchmark training records, with exclusion reasons. |
| [NGYDMR_original_benchmark_record.csv](NGYDMR_original_benchmark_record.csv) | Original negative record retained with its original endpoint context. |
| [nominal_molar_doses.csv](nominal_molar_doses.csv) | Free-peptide molar equivalents under explicit neutral-form assumptions. |
| [caption_mass_check.csv](caption_mass_check.csv) | Sequence masses versus published caption m/z; does not re-identify a peptide. |
| [run_receipt.json](run_receipt.json) | Completed execution summary and interpretation limits. |

## Other retained files

Remaining JSON, CSV, structure and figure files support the calculations above. Original logs and full run payloads, where supplied, remain in the [archives](../../../archives/README.md). Sources, units and unresolved evidence are explained in the experiment report.
