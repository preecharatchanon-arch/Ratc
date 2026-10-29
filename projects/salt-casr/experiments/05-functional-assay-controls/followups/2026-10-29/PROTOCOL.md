# Functional ligand contrast in CaSR

Written 29 October 2026 before the new numerical uncertainty calculation.
The source means and narrative were already inspected. This is exploratory
reanalysis of an existing primary paper, not preregistration, a new biological
experiment, independent replication or validation of a discovery method.

## Decision and hypothesis

The immediate decision is whether N102F responses provide a useful functional
control against a *uniform deterioration* interpretation of peptide responses.
The hypothesis is that N102F decreases gamma-EV EC50 but increases gamma-EVG
EC50, in the same published cellular assay. A simple uniform potency loss is
the comparator. Competing biological explanations include altered calcium
coupling, receptor expression/reserve, efficacy and ligand recognition.
These data cannot isolate direct binding from those explanations.

A secondary question is whether the relative peptide potency order itself
reverses with uncertainty accounted for. No docking run or fit is planned.

## Actual eligible data and unit

Yamaguchi et al. Scientific Reports 2025, DOI10.1038/s41598-025-87999-1,
original Supplementary Table S1: four mean/SEM EC50 cells for WT/N102F by
gamma-EV/gamma-EVG. Each is reported as three independent experiments. The
independent observational unit is an assay experiment, not a table cell,
ligand atom, receptor mutation or fitted concentration point. Raw experiment
values and cross-condition covariance are unavailable. The reported SEM is
accepted conditionally as SEM of three experiment-level EC50 estimates; if
that source description is inaccurate, the calculations cannot supply
confidence coverage. There is one source, two peptides and one mutation.

The entire S1/S2 numerical table is extracted for context, preserving NA as
not analyzed, units and missing uncertainty. S2 supplies no numerical SEM
despite its caption. Its Emax values remain descriptive. Surface expression
is a separate assay (n8); no exact expression SEM is available here.

Conditions: transient human CaSR in PEAKrapid cells; calcium mobilization;
146mM NaCl, 1mM MgSO4, 20mM HEPES, 1mM CaCl2, 2.5mM probenecid,
1.39mM glucose, pH7.4; Calcium5 fluorescent dye; peak response over180s.
The specified buffer calcium is a source condition, not proof that final
stimulus calcium was identical for every CaCl2 titration. Structural samples
used different preparations and cannot supply cellular assay conditions.

## Primary comparison and useful criterion

For EC50 lower means greater apparent functional potency. Require BOTH:
WT_EV lower confidence bound > N102F_EV upper confidence bound; and
N102F_EVG lower confidence bound > WT_EVG upper confidence bound.
This is a qualitative mechanistic discrimination criterion: a uniform
worsening of apparent potency cannot explain both directions. It is not a
human practical benefit margin. No eligible sensory margin/data exist, so
human candidate-selection success cannot be evaluated in this test.

Use four directed one-sided Student-t bounds with n3/df2 and Bonferroni
alpha .05/4 per bound. The union bound does not require known cross-cell
covariance. Conditional joint coverage is at least95% if the four marginal
Student-t models are valid. It assumes independent, approximately normal
experiment-level raw EC50 estimates; small n, fitted parameters, possible
skewness and absent raw curves prevent checking this. Do not log-transform
aggregate means and pretend these are log-scale sampling estimates.

Evaluate first the printed values literally, then conservatively include
rounding uncertainty: each printed mean/SEM may vary by half a unit of its
last displayed decimal. Use the mean endpoint and largest SEM that make
its directed bound least favorable. This is a sensitivity assumption, not
an assertion that the publisher used round-to-nearest. Do not truncate
negative raw-scale bounds at zero or call them plausible negative EC50s.
Record descriptive point fold shifts separately, without ratio CIs or
invented covariance. Means/SEMs are not treated as raw observations.

## Secondary comparison

Use the same four bounds (no additional inferential tails): WT_EV lower
> WT_EVG upper AND N102F_EV upper < N102F_EVG lower establishes complete
order reversal within the directed confidence region. Report any disagreement
between literal and rounding-sensitive conclusions. No switching the primary
criterion after execution. An inconclusive reversal is not evidence of no
ligand-dependent effect. No model sweeps, arbitrary bootstrap of table rows,
source pooling, threshold invention, p-value search or peptide screening.

## Controls, exclusions and uncertainty

Read CaCl2 EC50, normalized Emax and expression alongside peptides. Do not
normalize EC50 by expression or subtract calcium effects without an identified
biological model. WT CaCl2 0.19+/-0.4mM is unusual and uncorrected. The paper
says calcium EC50 was lower after mutations whereas the table shows higher;
it also prints N102F gamma-EVG in mM while S1 labels the whole row in uM.
Retain both conflicts and use table-labeled uM for this explicitly stated
analysis. NA is not zero, nonresponse, a fitted EC50 or a censoring bound.
No confirmatory or distribution-free significance claim is possible with
unreported experiment values. No saltiness, kokumi intensity or sodium-saving
labels are created.

## How outcomes change the next decision

If both primary directions survive literal and rounding-sensitive bounds,
retain these two peptides and N102F as an exploratory functional discrimination
control for a future genuinely mechanistic method. This does not establish
whether a docking score measures that distinction or isolate binding.
If the primary criterion fails, do not use this source to claim robust
opposing shifts; retain raw data and seek raw independent experiments.
If the secondary reversal fails only rounding sensitivity, require unrounded
experiment data before using reversal as an uncertainty-qualified benchmark.
Regardless, do not screen unknown peptides with the failed Vina protocol.
The main CaSR-to-human-saltiness question still requires matched controlled
human measurements across multiple chemical families and source-independent
validation. Absence of those observations is a real blocker.
