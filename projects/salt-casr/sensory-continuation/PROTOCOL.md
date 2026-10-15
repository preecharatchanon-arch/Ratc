# Saltiness evidence continuation — frozen analysis plan

Date: 2026-10-15. This plan is written after inspecting source schemas and evidence counts, before fitting or inspecting predictions.

Question: can simple sequence models generalize across literature sources in the newly obtained SaltyMeta dataset, and does its combined label answer a saltiness-enhancement question?

Inputs: Chen et al., arXiv:2609.16809v1, original Supplementary Data workbook. Retain all 580 labels as supplied. The quantitative CaSR series is a separate endpoint and is not merged with this dataset. Canonical one-letter sequences must not be interpreted as encoding gamma linkages, nonstandard residues, or stereochemical variants.

Analysis cohorts: (1) all 580 entries; (2) 138 positive records tagged Direct sensory evidence and 113 negative records graded A1 or B1. These are curator tags, not our independent confirmation of every source. A2 instrumental negatives and database negatives are excluded from cohort 2. Lack of standalone salty taste does not establish lack of enhancement in a NaCl background.

Models fixed in advance: length-only logistic regression; charge/length logistic regression; full composition/physicochemical logistic regression; ExtraTrees (512 trees, minimum leaf 2, square-root feature sampling). ExtraTrees is the designated main comparison, not selected by resulting scores. Logistic C=1, balanced class weights, train-fold scaling only. No tuning, embedding search or candidate-generation campaign.

Validation: five-fold stratified random splitting and five-fold similarity-grouped splitting for both cohorts; an additional reference-and-similarity-connected split for the sensory-tagged cohort. Repeated split seeds 777, 1777, 2777 measure partition sensitivity, not independent experimental replications. Sequence similarity = 1 minus Levenshtein edit distance divided by maximum sequence length; threshold 0.80, connected components. Reference groups connect records sharing any DOI-like token and then union sequence-similarity edges; this conservative reference connectivity is not proof that each token names an independent primary assay. No reference token may cross the corresponding train/test boundary.

Metrics: out-of-fold ROC-AUC, average precision (sklearn average_precision_score; not interpolated PR area), balanced accuracy at 0.5, Brier score as a descriptive score diagnostic, and within-reference AUC where both labels occur. Save every out-of-fold prediction and the exact folds. A source-cluster bootstrap of the averaged repeated OOF predictions is descriptive and conditional on these fits, not a retraining confidence interval. Report source-only and similarity-only grouping diagnostics. No interpretation of classifier scores as calibrated sensory probabilities.

Evidence audit: retain the source evidence fields; count explicit salt-enhancement wording separately from the combined positive label, without claiming that unmentioned enhancement was absent. Report sodium-salt/pH mentions as metadata flags, not proven confounders. Inspect primary-source examples when they affect our decision.

New October 2026 mushroom paper: check overlap with the September benchmark and extract the actual experimental context before any external comparison. Do not use news-reported percentages as receptor measurements, sodium-reduction percentages, or data that were verified from the primary manuscript. A tiny, success-selected set cannot establish external model performance.

Decision gate: do not screen new compounds using these scores until the endpoint, label strength and source-transfer performance support that use. Findings here concern the computational evidence, not newly measured receptor activation, taste, safety or a new chemical discovery.
