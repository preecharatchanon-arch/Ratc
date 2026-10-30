# The next decision-bearing test

[Project](../README.md) · [Current status](RESEARCH_STATUS.md) · [Timeline](RESEARCH_TIMELINE.md)

**Current maintained test design.** Dated evidence-review notes preserve earlier decisions; this page governs subsequent work.

29 October 2026. This written execution gate uses the current source assessment.
It is a test-readiness decision, not a newly executed scientific test. No new
model, docking/MD or human/receptor experiment ran during the source review.

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
| Native top-pose check, independently recomputed previously | RMSD4.7803 Angstrom | Current top-pose placement remains inadequate for the intended pose claim. Broad screening/MD remains unsupported. |

The intervals above are not new independent validation: fitted models,
candidate choices and source records were previously inspected. No statistical
power or general effect-size conclusion follows from these selected panels.

Provenance: [original Experiment01](../experiments/01-casr-models-and-docking/README.md)
and the [dated follow-up protocol, code and outputs](../experiments/01-casr-models-and-docking/followups/README.md).
The results belong to their original executions and are not new confirmation.

## Follow-up evidence does not unlock the selector

The [local-relaxation diagnostic](../experiments/01-casr-models-and-docking/followups/2026-10-29-local-relaxation/README.md)
failed its combined pose/ranking gate. The [functional ligand contrast](../experiments/05-functional-assay-controls/followups/2026-10-29/README.md)
provides a conditional exploratory response control, without human saltiness.
The [new source audit](../evidence-review/Followup_Source_Qualification_20261029.md)
adds a human sensory lead but no qualified matched hCaSR panel. None changes
the primary test card below or supplies the unset practical margins.

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

This is a request specification for existing measurements, not authorization
to conduct a new human or biological experiment. There is no universal minimum
compound count asserted; adequacy depends on domain coverage, dependence,
measurement precision and the justified decision margin.

## Current execution decision

No currently recovered panel qualifies, and practical sensory/yield margins
remain unjustified. See [research status](RESEARCH_STATUS.md) for the exact
missing original tables and access limits, and [the evidence review](../evidence-review/README.md)
for the source ledger. All inspected observations are development material.

An umami/liking application is a separate question described in
[Sensory outcomes](SENSORY_OUTCOMES.md). It does not change this saltiness
endpoint after inspecting results. A future liking experiment requires its
own complete design and actual eligible data before execution.

