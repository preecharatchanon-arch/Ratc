# CaSR functional contrast assessment

29 October 2026. New work: original source-table recovery, assay qualification
and one exploratory summary-data uncertainty calculation. This is a useful
functional control, not a validated peptide-discovery or saltiness-selection
method. Original biological measurements belong to Yamaguchi and colleagues.

## Result that changes the immediate decision

N102F has opposing effects on the apparent functional potency of two related
peptides. Those directions survive the prespecified, rounding-sensitive
summary-data bounds under the model assumptions. Retain this contrast as an
exploratory ligand-discrimination control. Do not label all mutation-associated
response changes as direct peptide-binding effects.

| Peptide | Wild-type EC50, µM | N102F EC50, µM | Descriptive interpretation |
|---|---:|---:|---|
| γ-Glu-Val | 10.71 ± 0.1 | 4.48 ± 0.2 | Lower EC50 after mutation; approximately 2.39 times greater apparent potency |
| γ-Glu-Val-Gly | 0.18 ± 0.1 | 6.52 ± 0.1 | Higher EC50 after mutation; approximately 36.2 times lower apparent potency |

Values are the source's mean ± SEM, n3 independent experiments, not newly
measured activities or confidence intervals. Fold changes are descriptive,
with no ratio CI. The four cells are not four independent biological samples.

## Written design and actual calculation

The design and extracted data were hashed before calculation. Source means
had already been read, so this is explicitly exploratory. The primary criterion
was opposing EC50 shifts, not a complete ranking reversal. Four directed
Student-t bounds use df2 and Bonferroni .05/4, critical value6.2053468.
They do not require assuming independent table cells or inventing their
covariance. Conditional joint95% coverage requires valid normal experiment-level
EC50 sampling and correctly reported SEMs. Those requirements cannot be
verified from the summaries. No unconditional95% reliability claim is made.

| Directed bound, µM | Printed values taken literally | Conservative rounding sensitivity |
|---|---:|---:|
| WT γ-EV lower | 10.0895 | 9.7742 |
| N102F γ-EV upper | 5.7211 | 6.0363 |
| WT γ-EVG upper | 0.8005 | 1.1158 |
| N102F γ-EVG lower | 5.8995 | 5.5842 |

The conservative separation for γ-EV's improvement is3.7379µM and for γ-EVG's
worsening is4.4684µM. Both retain the stipulated direction. These gaps are
separations of conservative marginal bounds, not effect estimates with paired
confidence intervals or useful sensory-effect margins.

Complete potency-order reversal passes with literal summaries, but fails the
rounding-sensitive secondary criterion: N102F separation changes from+0.1784
to−0.4521µM. Do not claim an uncertainty-qualified complete reversal. Rounding
sensitivity allows each printed mean/SEM half its last displayed unit; it is
a deliberately conservative scenario, not knowledge of the original rounding.
Failure here does not erase the primary opposing-shift result.

There are only three experiments per cell, with no raw per-experiment EC50,
curve fits, covariance or distribution diagnostics. EC50 is a nonlinear fitted
positive parameter and may be skewed. A raw-scale normal model cannot be
verified. No bootstrap of table cells, invented replicates, log-scale SEM
conversion, p-value claim, fit or independent-validation claim was made.
Results are suitable for an exploratory assay-control assessment only.

## Biological controls and source problems

The assay is transient human CaSR in PEAKrapid cells with Calcium5 mobilization,
peak response over180s. Published buffer:146mM NaCl,1mM MgSO4,20mM HEPES,
1mM CaCl2,2.5mM probenecid,1.39mM glucose,pH7.4. Structural purification
conditions are different and are not substituted for these assay conditions.

- N102F surface expression is65.2% of WT in the article's prose; the separate
  expression assay has n8 (SI Figure5). Expression and receptor reserve remain
  potential contributors. No numerical expression SEM was recovered and no
  fluorescence-dot digitization was performed.
- CaCl2 EC50 for WT is printed0.19±0.4mM and N102F2.75±0.21mM. WT's unusual
  SEM is preserved. All six mutants have higher tabulated CaCl2 EC50 than WT,
  conflicting with the article's word 'lower'. Do not silently repair it.
- A nominal1mM buffer calcium and the CaCl2 titration EC50 cannot be used to
  calculate receptor fractional activation: final versus added titration
  calcium, Hill slope, baseline and mutant coupling are not established here.
  In particular, do not assert that WT was saturated while N102F was not.
- Table S1 labels the entire γ-EVG row µM. The body calls N102F6.52mM but
  supplies a36.2-fold ratio to WT0.18µM; use the table-labeled units explicitly
  and preserve the conflict. No arbitrary1000-fold conversion is made.
- Table S2 supplies normalized Emax point values without numerical SEM,
  despite its caption. N102F Emax is194.8%WT for γ-EV and95.7%WT for γ-EVG;
  calcium87.8%WT. These remain descriptive, ligand-specific normalizations.
  They are not comparable absolute signal amplitudes across ligands, and
  cannot support a new uncertainty-qualified efficacy test.
- S1/S2 NA means 'not analyzed'. Fourteen EC50 cells and fourteen Emax cells
  are NA. They are retained as missing, not fitted negatives, censoring limits
  or zero activities. S147A was excluded for very low expression and must not
  be repurposed as a binding-negative control.

A uniform loss of apparent functional potency does not explain the two primary
directions. This narrow observation does not exclude ligand-dependent calcium
coupling, receptor reserve, efficacy effects or structural binding changes.
The assay does not directly measure binding affinity. It does not isolate a
contact mechanism, provide a sensory label or establish a beneficial food dose.

## What this does and does not add

The newly recovered56 table cells comprise28 EC50 and28 Emax source entries,
including NA. There are14 numerical entries per endpoint, not56 new compounds
or independent datapoints. The four primary cells concern two known peptides
and one mutation. This is a new extraction/uncertainty audit of a known source,
not newly discovered compounds or independent confirmation.

The failed Vina ranking remains failed. No new docking, MD, unknown-peptide
screen, predictive model, notebook, biological experiment or human test ran.
Five earlier project analyses and subsequent held-family comparisons remain
unchanged. This analysis supplies no new compound-level controlled human
saltiness outcomes. Kokumi, liking, intrinsic taste and sodium saving were not
inferred from receptor response.

## Bounded additional evidence assessment

A targeted search for an additional calcium-context or structural control was
screened against existing work before proposing more calculations.

- Kitajima2023, DOI10.3390/molecules28124585, is already assessed in the main
  evidence package. Its γ-EVG potentiation of a calcium titration supports PAM
  context, but is not a second-peptide dose-by-calcium grid. Its nonpeptide
  human combined umami/salty choice must not become a peptide saltiness label.
  Shared Ajinomoto source provenance also prevents treating all related papers
  as source-independent confirmation. No repeat quantitative fit was run.
- The newly indexed primary structural paper, DOI10.1631/jzus.B2500788,
  PMID42928019, PMCIDPMC13696094, first published2026-10-01, concerns upacicalcet
  and neomycin according to its indexed abstract. Metadata was confirmed by
  Europe PMC. Full text did not recover (publisher503, PMC challenge, XML500).
  No additional γ-glutamyl peptide reference was established. Drug structures
  are not automatically transfer validation for a peptide screen or food hits.
- Laffitte2021 and Yamaguchi2025 cannot be used as a controlled two-calcium
  intervention merely because their assay calcium differs: species, assay and
  source differences remain. No cross-paper calcium-effect estimate was fitted.

## Next precise action and stop conditions

Two questions require different evidence, and neither is resolved by another
large calculation:

1. For a mechanistic functional benchmark, obtain published experiment-level
   WT/N102F γ-EV/γ-EVG curves or unrounded EC50s, the exact calcium titration
   definition and numerical Emax uncertainty. Independently sourced human-WT
   peptide data at specified calcium levels would be needed before testing
   transport of functional rankings. If these records are unavailable, stop
   at this exploratory contrast; do not replace missing measurements with
   docking energies or digitized pseudo-replicates. No author contact is
   authorized in this run.
2. For the main peptide-selection question, qualify an actual multi-peptide
   panel with measured hCaSR function and controlled separately rated human
   saltiness in matching compound identities and defined dose/matrix/sodium/
   pH conditions. Apply the already written source/family-held-out and practical
   selection-margin design. Current recovered sources do not supply it.
   Existing blocked article routes remain closed without a genuinely new
   legitimate source. No reopening of model sweeps or the failed docking engine
   is justified by this remaining gap.

Immediate feasible deliverable is this source-qualified control and design.
The main external-measurement gap is an actual blocker, not a reason to declare
an unknown peptide promising. Endpoint, uncertainty and measured-evidence
principles are followed as guidance; the advice is not independent validation.

## Reproduction and provenance

Run `python analyze.py` in Python3.12 with scipy1.15.3. The actual run used
Python3.12.3/scipy1.15.3. It reads only the frozen numerical source extraction,
checks the design/input hashes and writes results.json. No internet/GPU needed.
The extraction was checked against a render of the original SI page9; expression
Figure5 page7 was visually inspected. Reproduce from original source via URLs
and SHA256 in SOURCE_MANIFEST.json. No original full article/SI is redistributed.

Source: Yamaguchi H et al., Scientific Reports15,3894(2025),
https://doi.org/10.1038/s41598-025-87999-1 ;
https://pmc.ncbi.nlm.nih.gov/articles/PMC11785791/ ; Supplementary TablesS1/S2
and FigureS5. Numerical transcription and our calculations are explicitly
separated. Source license CC BY4.0: https://creativecommons.org/licenses/by/4.0/.
