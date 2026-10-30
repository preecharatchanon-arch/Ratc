# Human saltiness window: source assessment and written design

> **Historical assessment.** This dated record preserves source qualifications and earlier decisions. For subsequent work, use the [current research status](../docs/RESEARCH_STATUS.md) and the [current test design](../docs/NEXT_TEST_DESIGN.md).

29 October 2026, Asia/Bangkok. No new scientific numerical test or biological experiment was run. This
continuation implements the sensory-first acquisition/design priority without
replacing the main question: can measured functional CaSR improve peptide
selection for human saltiness under defined conditions?

## Result of the bounded acquisition

Seven primary-source cases were qualified. No complete eligible human peptide-
dose/NaCl series with usable uncertainty was recovered. Access failures and
wrong endpoints are different reasons for ineligibility. Neither means the
compound is inactive. All source records and their limits are retained in
`sensory_window_qualification.json`. The existing receptor/saltiness counts
remain five named identities, four numerical, twelve numerical conditions and
fourteen heterogeneous endpoint values. No new training labels were created.

### Two priority dose-series leads remain incomplete

**Zhao2025, DOI10.1016/j.foodres.2024.115622.** The original abstract reports
ADWPR and WPEMDAL changing their saltiness effects with salt concentration.
OpenAlex's green-OA entry resolves to the same SSRN preprint, not another
recovered dataset. The newly checked public delivery link returned403.
The advertised publisher XML endpoint returned a195-byte HTML “Site
Unavailable” page despite status200, not article XML. Full doses, control
formulations, paired responses and uncertainty remain unrecovered. The paper
is a lead, not a completed operating-window comparison. Do not retry these
routes without a genuine new source.

**Fu2026** is now identified exactly as DOI10.1016/j.foodres.2026.119270,
PII S0963996926009476, online24April2026, issue31July2026. The six-peptide
psychophysics/processing report remains abstract-level here. OpenAlex lists
no repository full text; its advertised XML route also supplied the same HTML
failure. A stated optimum in an abstract does not recover the underlying
surface, candidate denominator or sampling uncertainty. No numerical window
or CaSR observation is assigned from it.

### Full primary examples that do not answer the window question

**Bu2023 preprint / Bu2024 journal**, DOI10.21203/rs.3.rs-3306601/v1 and
10.1007/s11947-023-03278-9, are one study lineage. The19-page original
preprint was recovered. Figure3/PDFp18 was visually checked against the
publisher's figure. Its human sensory bars and electronic-tongue line use
different axes. The often quoted2.62/2.86/3.01 values are instrumental, not
human ratings. Methods describe ten assessors, four synthesized peptides,
0.03% m/v peptide in0.4% m/v NaCl and a0–10 human scale. Only the control and
two reported enhancers appear in that figure; do not invent numerical values
for the other two. It supplies no dose/NaCl grid or functional CaSR assay.
Minor printed sequence variants remain unresolved. No bar digitization,
significance recalculation, human-effect ratio or activity label was produced.

**Foods2026, DOI10.3390/foods15101826**, supplies original full-text XML,
Table1 and detailed randomized methods. Its GSH condition is1.5g/L;
0.75g/L is warm-up, not a second tested dose. The model background contains
5g/L NaCl plus5g/L MSG, with a separate mushroom broth. The20-person koku
assessment measures body thickness, mouthcoating, continuity, astringency
and aftertaste. It does not separately rate saltiness in that matrix task.
Its six-dose umami experiment and seventeen-compound QDA are different tasks;
they cannot fill a GSH saltiness curve. Discussion about possible saltiness
modulation is not an observed saltiness endpoint. This source is useful
methodological guidance, not two new GSH saltiness conditions. No CaSR
functional measurements or liking outcomes are established by these methods.

### Supporting information recovered, with its actual scope

**Shan2022, DOI10.1021/acs.jafc.2c06237.** The complete official supplement
was recovered from ACS's Figshare record21485215. FigureS2/PDFp3 was
visually inspected: it is a probability-by-salt-concentration graphic, not a
peptide-dose/NaCl response grid. The supplement also contains extract-
processing optimization, spectra and docking. The main abstract reports
peptide recognition and mixture thresholds, but full main methods remain
unrecovered. No participant counts, denominators, individual dose responses
or paired uncertainty are reconstructed from rounded percentages. A missing
per-peptide table is not replaced by an extract-optimization score.

**Pu2023, DOI10.1021/acs.jafc.2c06293.** Its official three-page supplement
was recovered from ACS's Figshare record21751164. FigureS1/PDFp1 was visually
checked: salt-preference frequencies. FigureS2 concerns food gels, and
TableS1 zeta potentials. The main abstract concerns MSG, free alanine/glycine
and gum Arabic; it does not provide the required peptide panel. Its forced-
choice and temporal methods are design leads only. Neither preferred salt
levels nor non-significance in a discrimination task establishes our practical
margin or sensory equivalence. The sodium-versus-NaCl concentration basis
must be resolved from original methods before transferring any formulation.

### A recent AI paper is not a human validation shortcut

**Zhang2026, DOI10.1038/s41538-026-01209-4**, published20October2026:
the17-page accepted primary PDF and six-page supplement were recovered;
the candidate-assay methods page was visually inspected. Taste measurements
use an electronic tongue at0.25mg/mL peptide; enhancer candidates are tested
in0.1%NaCl. Three retained cycles are technical replicates. HUVEC assays
measure vascular-cell outcomes, not human taste or functional CaSR. The
discussion explicitly leaves human panels for future work. Its negative
training classes are other taste modalities; those annotations do not establish
absence of enhancement. Thus its ESM-3/FT-Transformer/docking/MD pipeline
does not resolve our target-data problem. No new benchmark, model reproduction
or cellular experiment was run. Electronic-tongue positives remain separate
from human sensory positives and from food-use/sodium-reduction claims.

## Decision: define the human comparison before another predictor

A usable saltiness increase and a mechanistic explanation are different
questions. Increased mixture saltiness over the matched background can be
useful even if intrinsic peptide taste contributes. Calling the effect
“synergy” additionally requires a justified interaction null on the sensory
scale. Adding subjective intensity scores is not automatically that null.
CaSR mediation requires separate functional/perturbation evidence. A fixed-
salt enhancement result is also not proof of sodium reduction or greater
consumer liking. Do not make a more demanding mechanism claim a prerequisite
for simply describing a controlled sensory effect, or claim mechanism from it.

### Written test card: a known-peptide enhancement window

**Status and scope.** Design only; not runnable or preregistered. Gamma-EVG
is a defensible reference candidate because identified functional receptor
and human evidence already exist, with source limitations preserved. This
does not establish it as a new ingredient or authorize its use. An actual
eligible published series is still needed; do not force another peptide's
responses into this card or treat reference calibration as discovery success.

**Hypothesis.** For one exact peptide/material, a prespecified dose/NaCl range
in one matrix produces a human peptide-minus-background saltiness gain above
an application-relevant minimum. The range and time endpoint must be frozen
before confirmation. Do not select only the observed peak after inspection.
The tested window is a finite set of observed cells; continuous interpolation
and transfer to untested concentrations would require additional justification.

**Plausible competitors.** Added sodium from counterions or pH adjustment,
intrinsic taste, sourness/umami interactions, order/carryover, scale use or
material differences account for the apparent effect. These explanations do
not all negate a useful sensory result, but they change the mechanistic and
sodium-reduction interpretation.

**Eligible actual data.** Original controlled human ratings for background
and background-plus-peptide across the specified final-dose/salt cells;
chemical form, purity/counterion, pH, total-sodium basis, matrix, timing,
participant/session pairing and uncertainty. Peptide-only samples support
intrinsic-taste interpretation; water controls and randomized presentation
support measurement quality. Unmeasured calcium and lot identity stay missing.
Nominal-NaCl-only sources may support a qualified descriptive contrast, but
cannot identify an equal-total-sodium benefit. Single-dose papers, warm-up
samples, electronic-tongue cycles and kokumi-only tasks do not supply the grid.

**Independent unit.** For a fixed material's human contrast, participants are
the population sampling units; repeated ratings/sessions remain paired, with
material/preparation batches retained where available. This does not make
participants independent peptide candidates. In the later selection test,
peptide identity with family/source dependence is the candidate unit.

**Primary comparison.** At each prespecified cell, separately rated saltiness
of background-plus-peptide minus the matched background, at the same defined
time endpoint. Distinguish fixed-NaCl and matched-total-sodium estimands.
Retain secondary intrinsic-taste and other basic-taste contrasts separately.
Do not pool scales across studies or substitute recognition thresholds.

**Practical success/failure.** A minimum useful gain, delta, must be justified
from the target application and calibrated sensory scale before execution.
No such number is currently justified. A useful window would require
simultaneous uncertainty bounds above delta throughout its frozen cells.
An informative upper bound below delta at a required cell rejects that whole
window; a smaller observed region remains exploratory. Wide uncertainty is
inconclusive, not failure or equivalence. A significant p-value alone does
not satisfy a practical criterion. No universal ten-percent threshold is
invented from an unrelated reference formulation.

**Uncertainty analysis.** Use actual participant/session pairing and repeated-
measure structure; preserve batch/preparation dependence. Obtain raw ratings
or adequate contrast covariance. Before analysis, choose an approach suited
to the scale and repeated design, including multiplicity across the frozen
window. Do not reconstruct independent replicates from means, repeated
sensor cycles or rounded probabilities. Report censoring and missing cells.

**Outcome-dependent decision.** An informative useful window justifies a
further independent check only in that domain. An informative lack of gain
stops that material/condition proposal. Inconclusive precision calls for
measurement improvement, not selecting a favorable subset. Missing qualified
data stops numerical execution now. A successful reference window alone
would still not validate a novel-peptide selector or CaSR's incremental value.

## What happens next

The source-assessment pass ends here; these seven cases are not a new broad
retrieval queue. The next required resource is an actual original participant-
paired human grid, with final formulations and an interpretable margin, or
a legitimate new full source providing it. The written specification above
is review-ready but authorizes no human or biological experiment or outreach.
On receipt, qualify all tested cells and candidates before calculating effects.

Keep the main CaSR selector gate separate: it additionally requires a common
candidate panel with measured functional receptor information, a frozen
non-CaSR comparison and independent evaluation. Neither a reference window
nor a modern embedding model fills that requirement. No new model fit,
notebook, docking/MD, publication, message, purchase, automation or paid/GPU
job was performed.

## Primary source locators

- Zhao: [journal DOI](https://doi.org/10.1016/j.foodres.2024.115622),
  [preprint](https://doi.org/10.2139/ssrn.4901320).
- Fu: [journal DOI](https://doi.org/10.1016/j.foodres.2026.119270).
- Bu: [original preprint](https://doi.org/10.21203/rs.3.rs-3306601/v1),
  [journal](https://link.springer.com/article/10.1007/s11947-023-03278-9).
- Foods2026: [journal](https://doi.org/10.3390/foods15101826),
  [original XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13205270/fullTextXML).
- Shan: [journal](https://doi.org/10.1021/acs.jafc.2c06237),
  [official supplement record](https://acs.figshare.com/articles/journal_contribution/21485215).
- Pu: [journal](https://doi.org/10.1021/acs.jafc.2c06293),
  [official supplement record](https://acs.figshare.com/articles/journal_contribution/21751164).
- Zhang: [journal](https://link.springer.com/article/10.1038/s41538-026-01209-4),
  [accepted primary PDF](https://link.springer.com/content/pdf/10.1038/s41538-026-01209-4_reference.pdf).

Original third-party PDFs, page images and article XML are not redistributed
in this package. These are our source qualifications and design, not new
biological measurements or independent confirmation of the original studies.
