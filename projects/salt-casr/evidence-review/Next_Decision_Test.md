# Earlier test-design snapshot

[Evidence guide](README.md) · [Current status](../docs/RESEARCH_STATUS.md) · [Current test design](../docs/NEXT_TEST_DESIGN.md)

**Historical record, 29 October 2026.** The single maintained plan is [docs/NEXT_TEST_DESIGN.md](../docs/NEXT_TEST_DESIGN.md). This file preserves the earlier design and diagnostic context; its retrieval priorities do not override the current plan.

The following content is retained for traceability, not as a second execution queue.

## Direction

Keep the question: does measured functional CaSR activity improve selection
of peptides that increase human saltiness under defined conditions?

The next empirical comparison must connect those two measurements on a common
candidate panel. More receptor-only models, an additional pose check or a new
literature citation would not answer it. The relevant deliverable is useful
selection performance with uncertainty, not a larger catalogue of proxy scores.

## Decisions already supported by completed tests

These results are carried forward, not rerun or presented as new evidence.

| Completed comparison | Saved result | Decision and limit |
|---|---|---|
| Fixed positional receptor model versus existing nearest3, family-held-out, journal assignment | MAE gain0.03365 log units; conditional group-bootstrap95% interval[-0.11043,0.15532];58 compounds,26 families | No reliable incremental gain established. Do not launch a model sweep. This predicts receptor activity, not saltiness. |
| Predicting Gly-extension effects |11 pairs; gain versus training-mean delta=-0.03004; interval[-0.24984,0.18417] | No reliable predictive gain. Do not repeat the same pair test as fresh confirmation. |
| Existing fixed-direction Vina activity ordering | AUC0.10714;14 measured positives,2 reported nonresponders | The selected panel does not justify advancing this scoring protocol. Two related negatives and one nonconverged starting geometry prevent a general screening claim. |
| Native top-pose check, independently recomputed previously | RMSD4.7803 Angstrom | Current top-pose placement remains inadequate for the intended pose claim. Broad screening/MD remains unsupported. |

The intervals above are not new independent validation: fitted models,
candidate choices and source records were previously inspected. No statistical
power or effect-size conclusion is inferred from the docking AUC alone.

Provenance: `casr_followup/output/summary.json`,
`casr_review/output/audit_results.json`, and
`casr_review/output/existing_docking_activity_panel.csv` in the existing work.
The completed analyses remain preserved in the earlier methods/further-tests
packages and repository; no repository files were changed in this continuation.

## One test card, with an explicit execution gate

**Hypothesis:** at the same follow-up budget, adding measured functional human-
CaSR information to a frozen context/chemistry selection rule increases the
yield of peptides meeting a practically useful human saltiness effect.

**Competing explanation:** exposure, sodium/counterions, pH, intrinsic taste,
matrix or another taste pathway explains the useful response. CaSR may predict
kokumi or combined taste intensity without improving separate saltiness selection.

**Eligible actual data:** a defined candidate panel with identified linkage,
stereochemistry and tested forms; measured functional hCaSR activity; controlled
human saltiness contrasts under a common application condition; unsuccessful,
uncertain and censored observations retained. Previously inspected data can
support development, not unseen confirmation. No current panel qualifies.

The receptor feature must specify its assay and response definition before
evaluation: species/construct, stable or transient expression, calcium, pH,
readout, EC50 and Emax where available. Do not average mixed assays or choose
the most favorable reported potency. Cross-assay calibration needs separate
justification; the recovered three-peptide overlap is not sufficient here.
Ohsu's thickness/intensity rating in NaCl remains related human evidence,
not a separately elicited saltiness target. Its GSH-referenced kokumi PSE is
not a NaCl-equivalent saltiness PSE.

Match the material and comparison, not just its name: extract G-versus-W
receptor measurements cannot substitute for G-versus-P human contrasts.
Different analytical processing and food cooking need an explicit transfer
argument. Unknown lots remain unknown; a same-name link does not establish
equivalent material, and exact lot identity is not invented as a universal
requirement for every descriptive purified-compound link.

For application to cooked food, define whether the receptor feature is measured
before or after the relevant processing and justify any transfer. Preserve
equal BCA-protein mass, fluorescent-peptide mass, dry-powder mass and molarity as
different exposure policies. Do not pool them without measured calibration.
Retain EC50 and maximum response separately. Keep process batch, assay cell/day,
well, assessor and session identifiers distinct. Published reanalyses retain the
original experiment identity and cannot create another independent sample.

Freeze exposure policy before evaluating: equal mass, equal molarity and
source-optimized application doses answer different questions. Preserve
counterion/pH-adjustment sodium. General cellular calcium and CaSR transcript
levels do not themselves constitute CaSR-specific functional activity. Define
any antagonist-sensitive response or species-proxy feature in its own assay
context; do not convert it into a common hCaSR EC50. No such alternate feature
test is ready with the currently recovered human outcomes.

**Independent unit:** peptide identity for selection, with chemical family and
source dependence retained. Assessors, sessions, material batches and receptor
biological replicates provide measurement uncertainty, not extra candidates.

**Primary comparison:** the same candidate set and follow-up budget, selected
by the frozen baseline rule versus that rule plus measured CaSR information.
Use peptide-minus-background saltiness. Do not substitute potency predictions,
kokumi, liking, intrinsic taste or combined umami/salty intensity. Select the
baseline, eligible domain and budget before confirmation; they are not chosen
from the current sparse outcomes.

A peptide-versus-free-amino-acid-mixture comparison is a separate secondary
contrast. It does not identify peptide-minus-background benefit unless the
amino-acid-mixture-minus-background effect is also measured. Preserve both
comparators, with dose and formulation matching, rather than substituting one
for the other. Generic database taste labels cannot supply the missing contrast.

**Practical success/failure criterion:** justify and freeze a minimum useful
saltiness effect and a minimum extra yield per budget. Their values remain
unset because the current evidence does not justify them. Success requires
uncertainty resolving useful improvement over baseline. If a sufficiently
informative interval's upper bound is below the required gain, stop that
selector; wide intervals remain inconclusive. A favorable point estimate is
insufficient. This is an explicit gate, not a runnable or preregistered test.

**Uncertainty:** retain paired assessor/session data or enough covariance
information, biological receptor replication, ranges, assay context, censoring
and source/family clusters. Missing measurements remain missing. A reported
nonresponse does not automatically imply a numerical EC50 lower bound.

**Consequences:** useful gain advances only the tested rule/domain to further
independent evaluation. Informative absence of useful gain stops that selector,
without refuting CaSR involvement in taste. Missing eligible data stops fitting
before execution. No number of surrogate-label fits fills this requirement.

## Smallest useful acquisition: a matched panel, not merely another paper

| Required resource | What must be provided | Why it changes the decision |
|---|---|---|
| Candidate roster and selection history | Every eligible tested peptide; exact chemical forms, source/lot links and exclusions | Establishes what selection performance would refer to and prevents counting only published successes |
| Functional receptor measurements | Per-peptide actual hCaSR response; assay/species/readout, calcium, pH, dose series, activity/censoring and replication | Supplies the feature whose incremental value is being tested |
| Human saltiness outcomes | Matched background contrasts, dose/basis, matrix, NaCl and total-sodium basis, pH, timing and paired uncertainty | Supplies the target without manufactured labels or cross-endpoint pooling |
| Application decision | Justified sensory margin and follow-up budget/yield margin | Makes both success and failure practically interpretable |
| Independent evaluation material | Candidate/source separation from already inspected development evidence | Distinguishes an exploratory fit from confirmation |

This table specifies the existing measurements needed for the comparison. A suitable candidate count depends on domain coverage, dependence, measurement precision and the justified decision margin.

## Latest assessment and next precise action

The sensory-first pass qualified seven cases without recovering a complete
eligible human peptide-dose/NaCl grid. Source failures, single-condition
human effects and wrong endpoints remain distinct. Full-text instrument,
vascular-cell and koku-only results do not replace saltiness measurements.
Do not copy the recent ESM-3 fungal pipeline as a way around missing human
data. Its methods and explicit future-human-panel statement were checked.

For a fixed peptide, a window comparison uses participants and paired ratings
as sampling units; this does not increase the peptide count for the main
selector test. A useful sensory increase, synergy, CaSR mediation, liking
and sodium reduction require different claims and comparisons. The new
window card preserves those distinctions, its missing practical delta and
its closed execution gate. It applies to a finite observed grid, not an
unjustified continuous concentration surface.

The original US8420144B2 Table8 adds three source-selected GSH/EVG saltiness
conditions. Its parent reproduces the same table. These are not new peptide
identities, a complete dose series, matched total-sodium controls or an unseen
candidate panel. No uncertainty-supported selector comparison is possible.
The same earlier six patent/paper assignments were verified against original
pages; the frozen sensitivity analyses already covered them. No re-fit ran.

The next concrete resource is a complete candidate-level joint table with:
exact compound, actual functional receptor result and assay conditions, human
saltiness-minus-background result and conditions, uncertainty, missingness and
candidate/source selection history. Qualify the denominator before selecting
success rows. Preserve nominal NaCl separately from measured total sodium,
including pH-adjustment sodium. A sensory-only source or receptor-only panel
is a lead, not an eligible selection benchmark.

Tu2023's known eight-peptide roster still lacks recovered individual sensory
measurements and a matched functional panel. Its RMIT/Figshare record contains
no manuscript file. Gong2025's mixture abstract supplies no established
individual functional/sensory match. Renewed Yi2025 and retronasal-paper leads
were already screened; docking and retronasal detection do not replace the two
required measurements. No currently available new source qualifies execution.

MSK remains a conditional ingredient-level lead if its actual methods and
control/formulation table become available through a new legitimate route.
It is not the only project dependency, and its acquisition would not guarantee
peptide-level selection data. Reumiller's candidate table, Wang's thesis and
Wu's methods remain unresolved leads, not queued repeated failed downloads.
The earlier fixed tests and no-go decisions stand. Do not restart closed
screens, fit proxy labels, or silently pivot to a liking/application question.

Once an actual qualified panel is recovered, justify the application margin,
budget, frozen baseline and precision requirement, then choose the analysis.
Until then there is no queued scientific experiment. This is a data/design
blocker, not evidence that CaSR cannot influence saltiness or that suitable
measurements do not exist elsewhere.
