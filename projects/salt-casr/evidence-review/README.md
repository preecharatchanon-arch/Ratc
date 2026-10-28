# Receptor and human sensory evidence

[Project](../README.md) · [Current direction](../docs/RESEARCH_STATUS.md) · [Next test design](../docs/NEXT_TEST_DESIGN.md)

Updated 28 October 2026. This folder assesses published measurements and whether
they can answer the current selection question. It is a literature/data
qualification layer, separate from the five completed computational analyses.
No receptor or human sensory measurements were performed by this project.

| File | Read it for |
| --- | --- |
| [ASSESSMENT.md](ASSESSMENT.md) | Original-source methods, material/control mismatches, rejected uses and unresolved tables |
| [evidence.json](evidence.json) | Named compounds, receptor assays, sensory contexts, observations and attributed identity links; column arrays describe row arrays |
| [source_qualification.json](source_qualification.json) | Detailed AMPC, chicken-soup, Deng supplement, Cornut receptor, plant-peptide and thesis qualifications |
| [search_screen.json](search_screen.json) | Exact bounded search queries and manual assessments of 80 unique indexed records; assessment depth is explicit |

The registry includes five named peptide identities with receptor/saltiness
links: gamma-Glu-Abu, gamma-EVG, gamma-Glu-Ala, gamma-Glu-Val and GSH. Four have
numerical saltiness observations here and one has graphical observations.
They are not a jointly tested candidate panel. Repeated conditions, dose
levels and time windows do not increase the number of independent compounds.
Kokumi and combined-intensity observations are indexed separately.

`null` means unresolved or unreported in the inspected source, never zero or
inactive. Non-significant differences are not equivalence. Reported source
ranges are not confidence intervals. Dose, matrix, sodium basis, pH, calcium,
assay species/construct, material linkage and source dependence constrain any
comparison. Unknown exact lots stay unknown.

The title/abstract queries returned 48 and 65 records with 33 in common: 80
unique indexed records. This bounded screen is not a systematic review or
proof that no qualifying dataset exists. Abstract-only assessment is distinct
from original-method verification. A record marked as supplying no newly
qualified panel is not a biological negative label.

Current result: no recovered common panel justifies fitting a human saltiness
selector using measured CaSR activity. No predictor was fitted to these
records. A successful metadata/integrity check would establish record
consistency only, not an effective peptide or validated discovery method.

Primary URLs and source locators are retained in the JSON records. Third-party
papers, supplements, figures, raw abstract corpora and private correspondence
are not included. Source publications retain their own rights; repository
licensing does not relicense them. All inspected evidence is development
material, not unseen confirmation.
