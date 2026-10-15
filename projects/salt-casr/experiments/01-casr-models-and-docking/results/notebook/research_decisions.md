# Executed CaSR notebook: research decisions

Best observed chemical-family model MAE: 0.799 log10; geometric mean absolute fold error: 6.29.
The descriptive bootstrap does not establish a reliable advantage over the median comparator. Random folds are secondary; they do not establish external generalization.

Docking source: reused_verified_outputs. 20 compound results, 14 numeric assay comparisons; score/activity Spearman 0.240.
Top native RMSD 4.78 Å, larger-search top 4.44 Å, closest returned pose 2.43 Å. The top-ranked reference pose remains displaced; this protocol is weak support for structural prioritization.

What can be used: explicit structures, assay labels, matched chemical effects, failure examples and reproducible comparison conditions.
What remains unknown: activity of the proposed compounds, taste effects, food stability and suitability.

The Nva ester is an unmeasured combination within an explicitly described patent scaffold. PubChem absence does not establish novelty. Keep it as a secondary chemical comparison rather than promoting it as a hit.

The regression is not an active/inactive classifier. The table-only inactive set is narrow. Additional narrative-only inactive annotations have no assay-system assignment in their sentences and are exported separately. Review assay compatibility before combining labels. Do not convert missingness, inactivity or censored EC50 into arbitrary numeric targets.

Next meaningful evidence: independent matched receptor responses for the proposed analogue and known comparators, followed by separate direct saltiness evidence at matched sodium, dose and food matrix. More docking jobs alone do not supply that evidence.
