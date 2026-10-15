# Condition-aware follow-up, 15 October 2026

This is a **post-hoc follow-up** to the source-transfer experiment. The papers,
their outcomes, the NGYDMR discrepancy and the dose curves were inspected before
this protocol. The four model definitions were fixed in the preceding experiment;
no claim of prospective discovery or a blind external benchmark is made.

## Questions and stopping rules

1. Can the earlier fixed sequence baselines retrieve reported NaCl enhancers in
   two complete, author-selected synthesis panels? Fit each of the same four
   models once, seed 777, on the sensory-tagged benchmark subset. Remove exact
   matches, entire >=0.8 normalized-Levenshtein connected components touching
   either panel, and records citing the panel papers or NGYDMR's older source.
   Export all exclusions and all scores. Report known-positive retrieval among
   the top three per panel. Do not select a winner, tune, calculate a pooled AUC,
   or interpret scores as calibrated probabilities of enhancement.
2. Is a concentration-independent ranking compatible with the straw-mushroom
   Table S4 means? Preserve all 18 published means (including three shared-dose
   zero rows); describe ranking changes and peak-to-last changes without
   inferential tests, EC50 fitting or treating dose points as independent peptides.
3. Does NGYDMR's benchmark negative mean the same thing as absence of enhancement
   in NaCl? Export its original record alongside the new assay evidence. Do not
   globally relabel it without preserving endpoint and conditions.
4. Check all eight Figure S1 caption m/z values against unmodified linear
   peptides, free termini, protonated charge states 1 through 6. This is a caption
   consistency check, not MS/MS re-identification. Report unresolved mismatches;
   do not infer fraud or a wrong synthesized compound.

## Source interpretation

- Pleurotus (DOI 10.1038/s41538-025-00681-8): six candidates at 1 mg/mL peptide
  with 3 mg/mL NaCl. Figure 1A gives three candidates a letter shared with CK;
  record "not significant in this assay", not "biologically inactive". Do not
  digitize bar heights. Table S2 time-intensity Imax is a different measurement.
- October mushroom (DOI 10.1038/s41538-026-01088-9): five candidates, same stated
  concentrations. Three significant enhancers; two "less pronounced" outcomes
  remain unresolved. Training metadata may not contain every source citation.
- Straw mushroom (DOI 10.3390/foods13070995): use exact Table S4 numbers, not
  visually approximated Figure 8 values. Flag the VP10 final-point disagreement.
  Keep nominal doses; Methods 2.11 leaves stock/final concentrations ambiguous
  after 1:1 mixing. The separate threshold assay uses 0.5% NaCl and must not be
  merged with this nominal 0.5 g/L dose-response assay.
- Saltiness scales differ: Pleurotus 3/5/7 mg/mL and October 3/6/9 mg/mL NaCl
  map to scores 5/10/15. Do not pool raw intensity, percent change or convert it
  to measured sodium replacement.

Stop after the four fits and descriptive source checks. Next experiments should
resolve a biological or formulation question; additional docking parameter
sweeps and model tuning on these panels are not justified by this analysis.
