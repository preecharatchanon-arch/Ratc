# Receptor and human sensory evidence

[Project](../README.md) · [Current direction](../docs/RESEARCH_STATUS.md) · [Next test design](../docs/NEXT_TEST_DESIGN.md)

Updated29 October2026. This folder qualifies published measurements; it contains
no receptor or human experiment performed by this project and no fitted human
saltiness selector. The source files preserve missing measurements, source
relationships, exposure conditions and endpoint distinctions.

## Current findings and entry points

| Read | Purpose |
|---|---|
| [Latest source qualification](Followup_Source_Qualification_20261029.md) | Full16-peptide sensory source and three additional primary cases; human versus electronic-tongue values, TAS1R1 versus CaSR, feline versus human assays |
| [Follow-up source records](followup_source_records.json) and [panel inventory](cao2026_panel_inventory.csv) | Source hashes, access depth,16 sequence identities and explicit missing numerical human/CaSR fields |
| [Registry](evidence.json) | Attributed receptor/sensory observations and chemical-identity links, with dose, matrix, sodium, pH, assay and uncertainty qualifications |
| [Source assessment and design](Source_Assessment_and_Design.md) | Working question, source/control eligibility and the written selection-test requirements |
| [Sensory window assessment](Sensory_Window_Assessment_and_Design.md) | Why the bounded seven-case pass did not qualify a human peptide-dose/NaCl grid |
| [Primary assay qualification](Primary_Assays_and_Endpoint_Decision.md) | Source-specific EC50, normalized maximum response and sensory endpoint distinctions |
| [Detailed source ledger](source_qualification.json) | Source-level qualifications, including original methods and unresolved fields |
| [Bounded indexed screen](search_screen.json) | Historical80-record search coverage; new case reviews are recorded separately |

The registry links five named peptide identities: gamma-Glu-Abu, gamma-EVG,
gamma-Glu-Ala, gamma-Glu-Val and reduced glutathione. Four have numerical
saltiness observations here; one is graphical. Twelve numerical formulation/
dose conditions yield fourteen heterogeneous endpoint values. This is not a
jointly tested candidate panel or common regression target. Repeated doses,
participants and time windows do not become extra independent compounds.

`null` and empty inventory numeric fields mean unestablished or unreported,
never zero, inactivity or a negative sensory result. Non-significance is not
equivalence; published concentration ranges are not confidence intervals.
Instrument outputs, kokumi, liking, intrinsic taste, receptor activity and
human saltiness are distinct outcomes. All inspected material is development
evidence rather than unseen confirmation.

## Reproduce the registry only

From this folder, run `python build_registry.py` with Python3.12. This rebuilds
the attributed registry and consistency summary; it performs no model fitting,
biological experiment or new statistical efficacy test. Source-qualification
JSON and prose are reviewed records, not automatically inferred labels.

The earlier [ASSESSMENT.md](ASSESSMENT.md) remains a historical original-method
assessment; the current files above supersede its acquisition queue. Other
dated reports in this folder preserve endpoint and identity decisions. A lack
of qualified data is an execution blocker rather than a negative finding about
CaSR or every peptide in a source.

Primary citations and exact locators are retained in the JSON records. Original
publisher articles, supplements, figures and private correspondence are not
redistributed. Third-party rights remain with their sources.
