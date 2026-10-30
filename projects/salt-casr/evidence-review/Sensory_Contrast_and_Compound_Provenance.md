# Human sensory evidence: preserve the actual comparison

> **Historical assessment.** This dated record preserves source qualifications and earlier decisions. For subsequent work, use the [current research status](../docs/RESEARCH_STATUS.md) and the [current test design](../docs/NEXT_TEST_DESIGN.md).

28 October 2026, Asia/Bangkok. This is
source qualification and a written design amendment, not a newly run scientific
test. Previously inspected database sequences remain development material.

## What was recovered

[Feng et al.2019, DOI10.3390/foods8020043](https://doi.org/10.3390/foods8020043):
original full-text XML and12-page PDF; Figures5–6/Table3 visually inspected.
Twenty trained assessors are described. The synthetic-peptide concentration
series is0.05–0.50% w/w, but the exact dose for those figures is unspecified.
Figures5–6 compare GLPD and GHGD with their mass-equivalent free-amino-acid
mixtures in commercial chicken-consomme broth; they do not plot blank broth.
Saltiness is separately rated, but numerical bars were not digitized and
error-bar definitions/paired covariance remain unknown. Figure6's legend and
body identify GHGD; its caption instead says Gly-His-Pro-Asp. Preserve that
conflict. Fraction-testing pH6.5 is specified; its applicability to synthetic-
peptide figures is unclear. Broth sodium, calcium and exact formulation are
unresolved. No functional CaSR assay is reported.

Separately, Section3.3 reports that1% F5 fraction in1% NaCl changes saltiness
intensity from1.9 to2.6. That is a fraction-level result, not either isolated
peptide's effect. Uncertainty/final sodium matching are unavailable. The
paper's sodium-reduction conclusion exceeds these recovered comparisons.

## What is new here, and what is already old

The existing `curated_records.csv` and `training_eligibility.csv` already
contain GLPD/GHGD. They carry positive compilation annotations attributed to
TastePeptidesDB, material described as yeast, no DOI token, and no source-
tagged sensory eligibility in that extraction. This primary mushroom report
improves provenance. It does not discover two new peptides, establish that
yeast occurrence is false, or make our earlier model evaluation independent.
Keep the compilation annotation and primary experiment as separate claims.
No frozen repository file or label was changed.

Exact-name checks of the two saved receptor tables found no GLPD/GHGD entry.
A bounded public search did not recover their measured functional CaSR
response. That is an acquisition result, not evidence that they are inactive.
The recovered human comparisons therefore do not increase the five confirmed
receptor/saltiness identity links or qualify a selector benchmark.

The exact YFY sensory-name search and Reumiller journal DOI were already in
`source_qualification.json` from the earlier assessment. Renewed checks do not
count as new findings. Version18's description of the journal route as newly
identified overstated novelty; this continuation corrects that classification.
Full Reumiller and MSK methods remain unrecovered through the checked routes.

## Why the comparator changes the question

Let B denote background broth, P the peptide at a defined dose, and A its
specified free-amino-acid mixture. The desired application contrast is

`D_background = saltiness(B + P) - saltiness(B)`.

The figures instead provide evidence about

`D_amino_acids = saltiness(B + P) - saltiness(B + A)`.

They are distinct. Without measuring A versus B, the second contrast does not
identify the first. A peptide may differ from its components while offering no
useful gain over the starting food; conversely, an amino-acid mixture could
already improve that food. This is a design distinction, not a new statistical
test or a numerical estimate from the figures.

A free-amino-acid arm is useful for a **secondary compositional explanation**.
It does not isolate CaSR involvement: sequence, exposure, other taste pathways,
acidity, sodium and matrix effects can still contribute. Mass equivalence also
does not automatically establish equal constituent molar exposure. Preserve
the source policy instead of silently redefining its comparator.

## Amendment to the future test design

The main hypothesis remains incremental usefulness of measured functional
CaSR for selecting human saltiness enhancers. Keep its existing execution gate
in `Next_Decision_Test.md`; margins and eligible matched data remain unresolved.

| Design item | Requirement before execution |
|---|---|
| Primary outcome | Peptide-minus-background saltiness at the frozen application dose/time, with uncertainty |
| Optional explanatory comparison | Peptide versus an explicitly defined free-amino-acid mixture; retain it separately from the primary outcome |
| Competitor | Basic-taste/component, exposure, sodium, pH, processing or matrix effects account for apparent benefit |
| Eligible data | Actual candidate-level receptor measurements and the required human contrast; a generic positive taste annotation is insufficient |
| Independent unit | Peptide for selection; preserve participant/session pairing and material/assay replication; repeated database entries are not new units |
| Success/failure | Existing justified sensory and incremental-yield margins are required; a significant peptide-versus-mixture contrast alone cannot pass |
| Uncertainty | Raw paired ratings or adequate covariance, assessor contribution, dose, error-bar definition, source/family dependence and censoring |
| Next decision | A useful primary gain can advance only the specified selector/domain; incomplete comparisons block fitting; secondary mechanistic contrasts remain explanatory |

If all three arms exist in a later eligible source, extract them before
analysis. If only the peptide-versus-mixture arm exists, record that contrast
faithfully and leave the primary background effect missing. This specification
concerns the assessment of existing measurements.

## Next precise action

The acquisition target remains the MSK original formulation/control and sensory
tables on a new legitimate public route. Its ingredient effect would need the
same contrast check. For a peptide selector, an actual common candidate panel
with functional CaSR and peptide-minus-background saltiness is still needed.
Do not repeat YFY/name searches or Reumiller access attempts without new source
information. GLPD/GHGD are now qualified sensory-only source records; no further
model or receptor-negative label follows from them.
