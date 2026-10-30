# Receptor and human sensory evidence

[Project](../README.md) · [Timeline](../docs/RESEARCH_TIMELINE.md) · [Current status](../docs/RESEARCH_STATUS.md) · [Current test design](../docs/NEXT_TEST_DESIGN.md)

Updated 30 October 2026. This folder records which published measurements can be connected by exact compound identity and relevant conditions. It contains no receptor or human experiment performed by this project and no fitted human-saltiness selector.

## Read the current evidence

| Resource | What it provides |
| --- | --- |
| [Registry](evidence.json) | Attributed receptor and sensory records, chemical links, dose/matrix/sodium/pH, assay context and uncertainty. |
| [29 October source qualification](Followup_Source_Qualification_20261029.md) | The recovered 16-peptide human source and three further cases; separates human versus electronic-tongue outputs, TAS1R1 versus CaSR, and feline versus human assays. |
| [Follow-up source records](followup_source_records.json) · [16-peptide inventory](cao2026_panel_inventory.csv) | Source identifiers, access depth, exact identities and explicit missing human/CaSR values. |
| [Source ledger](source_qualification.json) | Original-method qualifications and unresolved fields for the reviewed sources. |
| [Current test design](../docs/NEXT_TEST_DESIGN.md) | The single maintained comparison, eligibility requirements, uncertainty, practical margins and stopping conditions. |

### What the counts mean

The five linked peptide identities are **γ-Glu-Abu, γ-Glu-Val-Gly, γ-Glu-Ala, γ-Glu-Val and reduced glutathione**. All five have numerical receptor records. **Four have numerical saltiness observations; γ-Glu-Val has graphical-only saltiness observations here.**

Twelve numerical formulation/dose conditions yield fourteen heterogeneous endpoint values. These are not fourteen independent peptides, one common sensory scale or a jointly tested candidate panel. Assessors, repeated doses and time windows do not increase the candidate count.

Missing fields (`null` or blank numeric inventory entries) remain unestablished, not zero or inactivity. Non-significance is not equivalence. Published concentration ranges are not confidence intervals. Human saltiness, kokumi, liking, instrument values and receptor activity remain separate outcomes.

## Dated assessments and earlier decisions

These records explain how the evidence was qualified. Their acquisition queues and proposed next actions are **historical**; use the [current status](../docs/RESEARCH_STATUS.md) and [current test design](../docs/NEXT_TEST_DESIGN.md) for subsequent work.

| Historical record | Purpose |
| --- | --- |
| [Primary receptor assays](Primary_Assays_and_Endpoint_Decision.md) | Ohsu/Broadhead methods, EC50/Emax context and sensory endpoint distinctions. |
| [Expanded source assessment](ASSESSMENT.md) | Extract processing, human versus instrument outcomes and alternative receptor pathways. |
| [Sensory contrast and provenance](Sensory_Contrast_and_Compound_Provenance.md) | Preserves the actual material, background and comparator. |
| [Patent saltiness recovery](Patent_Saltiness_and_Test_Readiness.md) | Original patent examples and the additional numerical conditions. |
| [Sensory-window assessment](Sensory_Window_Assessment_and_Design.md) | Why the bounded seven-case review did not qualify a usable peptide-dose/NaCl grid. |
| [Earlier acquisition/design record](Source_Assessment_and_Design.md) · [Earlier test-card snapshot](Next_Decision_Test.md) | Preserved development history; not competing current plans. |
| [Bounded indexed screen](search_screen.json) | Historical coverage of 80 unique indexed records, not a systematic review or 80 experiments. |

Other dated files retain specific chemical-identity and source decisions. All inspected observations are development evidence, not unseen confirmation.

## Rebuild the registry

From this folder, with Python 3.12:

```sh
python build_registry.py
```

This rebuilds the attributed registry and consistency summary. It does not fit a predictor or perform a new biological or statistical efficacy test. Source-qualification JSON and prose are reviewed records, not inferred sensory labels.

## Sources and rights

Primary citations and exact source locators are retained in the records. Original publisher papers, supplements and figures are linked rather than redistributed. A missing qualified panel is a data limitation, not a negative result about every peptide in a source.
