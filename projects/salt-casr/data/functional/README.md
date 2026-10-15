# Functional assay evidence — input data

[Experiment 05](../../experiments/05-functional-assay-controls/README.md) · [All data](../README.md)

Every row is attributed to a primary source and locator. Unknown is blank, reported non-significance is categorical, and no unreported effect is replaced by zero. This small comparator collection is not a general training dataset.

| Table | Unit of observation and role |
| --- | --- |
| [xu2017_condition_outcomes.csv](xu2017_condition_outcomes.csv) | 32 explicitly tested peptide-dose/NaCl combinations; main-text categorical outcomes relative to the authors’ SUM reference. No bar digitization. |
| [xu2017_peptide_response_EC50.csv](xu2017_peptide_response_EC50.csv) | Seven peptide-alone cellular EC50 values, in μM. Not binding or enhancement EC50. |
| [xu2017_knockdown_components.csv](xu2017_knockdown_components.csv) | Four Figure 7a–c conditions with peptide-only, NaCl-only and mixture response percentages and original counts. |
| [xu2017_knockdown_SUM_comparisons.csv](xu2017_knockdown_SUM_comparisons.csv) | Three separate Figure 7d–f comparisons. Different totals from 7a–c; never pool or interchange them. |
| [xu2017_amiloride_SUM_comparisons.csv](xu2017_amiloride_SUM_comparisons.csv) | Two pharmacological comparisons with reported SUM/mixture percentages. |
| [qi2025_soy_endpoint_comparison.csv](qi2025_soy_endpoint_comparison.csv) | Three soy sequences; publisher-abstract sensory and organoid outcomes. Organoid concentration, NaCl and species remain unverified. |

For Xu et al., `reported_NaCl_stimulus_mM` is the source’s stated stimulus concentration. It does not reconstruct total bath sodium from Ringer salts, sodium pyruvate or pH adjustment. `peptide_uM` is the stated peptide concentration. The stated pH is 7.0, application is 60 s, and response analysis uses the authors’ calcium-response criteria. Counterion identity and individual culture-level responses are not supplied in these tables. A cell count is not a biological-replicate count.

Sources and transformation details: [Experiment 05 source manifest](../../experiments/05-functional-assay-controls/SOURCE_MANIFEST.json). Xu et al. transcriptions/replots are attributed adaptations under CC BY 4.0. The soy comparison records attributed numeric facts from the publisher abstract; full ACS text, figures and supplementary files are not distributed.
