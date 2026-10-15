# 01 · CaSR models and docking — results

[Experiment report](../README.md) · [Code](../code/README.md) · [Shared inputs](../../../data/README.md)

These files are the reviewed result snapshot. New local runs write to `../runs/latest/`, leaving this evidence intact. Read the report before interpreting a score or label.

## Key outputs

| File | What to inspect |
| --- | --- |
| [notebook/main_metrics.csv](notebook/main_metrics.csv) | Start here: all five models, evaluated splits, errors and within-threefold fractions. |
| [notebook/prediction_validation.png](notebook/prediction_validation.png) | Prediction/error figure; the held-family evaluation is the primary comparison. |
| [notebook/reconstructed_structures.csv](notebook/reconstructed_structures.csv) | 94 reconstructed chemical graphs; audit of the representation used. |
| [chemical_activity_dataset.csv](chemical_activity_dataset.csv) | Assembled chemical/activity table; numerical, missing and inactive labels are distinct. |
| [notebook/matched_glycine_effects.csv](notebook/matched_glycine_effects.csv) | Measured matched chemical comparisons; not model forecasts. |
| [notebook/docking_validation.png](notebook/docking_validation.png) | Docking validation figure, including the native-pose discrepancy. |
| [docking/docking_results.csv](docking/docking_results.csv) | 20 selected compound docking jobs; scores do not establish receptor activation. |
| [docking/native_search_sensitivity.json](docking/native_search_sensitivity.json) | Reference-pose search comparison and RMSD values. |
| [notebook/docking_with_assay_labels.csv](notebook/docking_with_assay_labels.csv) | Docking joined to reported activity, including controls. |
| [candidate_predictions.csv](candidate_predictions.csv) | Exploratory forecasts for 22 unmeasured combinations; not validated hits. |
| [candidate_library.sdf](candidate_library.sdf) | Chemical structures corresponding to those proposals. |
| [notebook/research_decisions.md](notebook/research_decisions.md) | Retained interpretation from the executed notebook. |

## Other retained files

Remaining JSON, CSV, structure and figure files support the calculations above. Original logs and full run payloads, where supplied, remain in the [archives](../../../archives/README.md). Sources, units and unresolved evidence are explained in the experiment report.
