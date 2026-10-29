# Primary saltiness recovery and test-readiness decision

29 October 2026, Asia/Bangkok. Checkpoint version20 was read first. This is
published-evidence assessment and a written design, not a new efficacy study.
The question remains whether measured CaSR activity improves peptide selection
for human saltiness under defined conditions. No scientific numerical test ran.

## What this pass actually adds

US8420144B2 Example24/Table8 reports relative saltiness enhancement in aqueous
0.7 g/dL NaCl. The original PDF methods and table were visually inspected.

| Peptide | Dose, g/dL | Reported relative score |
|---|---:|---:|
| Reduced glutathione, GSH | 0.10 | 0.2 |
| gamma-Glu-Val-Gly, EVG | 0.005 | 0.5 |
| EVG | 0.01 | 1.0 |

The source gives n=12 and anchors control=0, moderately strong enhancement=1,
strong enhancement=2. It reports selected example doses, not a complete curve.
Paired data, variance, significance, absolute pH, calcium and measured total
sodium are unavailable. NaOH pH adjustment can change sodium. The table's
literal control header is “Distilled water”; the methods describe the relevant
taste standard without peptide. Its zero is a relative anchor, not an extra
absolute-saltiness observation. Other taste endpoints stay separate.

The parent US8173605B2 Example16/Table7 repeats all twelve basic-taste values,
conditions and n. Count this once. The child reports EVG functional human-CaSR
EC50 of 0.023–0.055 micromolar in HEK293 cells; that range is not a CI. Its GSH
oocyte experiment uses 50 micromolar as a test dose, not an EC50. Shared lots
and independence from journal experiments remain unknown.

Primary sources: [US8420144B2](https://patents.google.com/patent/US8420144B2/en),
[original PDF](https://patentimages.storage.googleapis.com/71/46/5c/03bf28255622e1/US8420144.pdf),
[parent](https://patents.google.com/patent/US8173605B2/en).
Exact transcriptions and assay qualifications are in `evidence.json` under
`patent_basic_*`, `patent_Table3_*` and `patent_nonEC50_functional_observations`.

## Novelty and dependence audit

These are three newly extracted published conditions, not new compounds or our
own measurements. The registry now has twelve numerical formulation/dose
conditions and fourteen heterogeneous endpoint values, still only four linked
identities with numerical saltiness and one with graphical-only observations.
Time windows, doses and repeated publications are not independent candidates.
The numerical total includes PSE concentrations and distinct relative scales;
it must never become a pooled fourteen-row regression target.

Six original patent-versus-Amino2016 compound-to-value assignments were visually
rechecked. They match the six alternate assignments already used in the frozen
benchmark. Thus this is source verification, not a new conflict or an excuse
to re-fit. Both reports are retained separately. The comparison does not
adjudicate different experiments versus reporting error. The 2017 erratum
corrects another citation, not these assignments. Amino's relevant table is
Table3, printed p1184/PDF p4: [DOI10.1248/cpb.c16-00293](https://doi.org/10.1248/cpb.c16-00293).

The lineage audit improves qualification, not selector performance. Earlier
58-compound/26-family and eleven-pair gain intervals still cross zero. The
completed pose and activity-ordering results are unchanged. No broad docking,
MD or receptor-only model sweep is justified by these observations.

## The question the new observations cannot answer

Two source-selected known activators at unequal exposures cannot identify the
incremental value of CaSR over a practical selection rule. Repeating EVG at
two doses does not add a third candidate. Positive relative means without
uncertainty do not establish significance or a useful effect. A higher score
at a lower mass dose does not establish a potency ratio, mediation by CaSR,
or general performance on unseen peptides. A receptor response and a human
effect on the same named compound establish descriptive overlap only.

The useful blocker is therefore a common candidate panel and an interpretable
decision threshold. It is not simply access to one favored paper. Ingredient
mixture results may answer an application question without resolving peptide
selection. Saltiness enhancement is also not equivalent to human preference,
kokumi, intrinsic taste, safety or sodium reduction.

## Decision-bearing test card — execution remains closed

**Hypothesis.** With a fixed candidate domain, exposure policy and follow-up
budget, adding measured functional human-CaSR information increases the yield
of peptides meeting a practically useful separately measured human saltiness
effect, beyond a frozen non-CaSR selection rule.

**Plausible competitor.** Exposure, counterion/NaOH sodium, pH, matrix effects,
intrinsic flavor or another taste pathway accounts for the observed advantage.
CaSR might track kokumi while adding no saltiness-selection value. A selected
positive-only publication panel can also create an apparent association.

**Eligible actual data.** Recover a defined tested candidate roster, exact
forms/linkages/stereochemistry, functional receptor measurements and peptide-
minus-matched-background human saltiness under a common condition. Retain
unsuccessful, uncertain and censored measurements and the selection history.
Specify assay construct/species, calcium, pH, dose basis, processing, matrix,
nominal NaCl versus total sodium, replication and material provenance. Do not
pool unlike assay potencies, borrow missing controls or fill missing outcomes.
Same-name cross-source links can support descriptive overlap; they need an
explicit comparability argument for a selector comparison.

**Independent sampling unit.** Peptide identity for candidate selection,
with constitutional-family and source clustering retained. Assessors,
sessions, dose points, wells and assay days quantify measurement error, not
additional peptides. All currently inspected candidates are development data.

**Primary comparison.** Same panel and budget: baseline selection versus that
baseline plus a prespecified measured CaSR feature. Freeze baseline, budget,
feature definition and exposure policy before independent evaluation. Use
separately rated peptide-minus-background saltiness as the target. An amino-
acid-mixture comparator is a distinct secondary contrast. Do not substitute
kokumi, docking, liking, combined intensity or sensory recognition thresholds.

**Meaningful success/failure.** Justify a useful saltiness margin and minimum
extra yield per budget from the intended application and measurement scale.
Neither number is justified by the present records, so neither is invented.
Success requires uncertainty resolving useful extra yield. An adequately
informative upper bound below the useful-gain margin stops that selector;
a wide interval is inconclusive. This is not a runnable preregistration.

**Uncertainty.** Preserve participant/session pairing, covariance, receptor
biological replication, censored results and material/source/family dependence.
Do not treat source ranges as CIs, NS as equivalence or missing tests as
negative. Once qualified data and margins exist, choose the analysis and
precision requirement before seeing confirmation outcomes.

**Outcome-dependent decision.** Useful gain advances only that rule and domain
to independent evaluation. Informative lack of useful gain stops that rule,
without refuting CaSR involvement. Missing eligible data stops fitting. This
last outcome applies now. No dose curve, correlation or model fit was executed.

## Targeted acquisition ledger and next precise action

`targeted_primary_followup.json` separates new recovery, new access checks and
previously closed branches. Tu2023's eight-peptide sensory roster was already
known. Its newly checked RMIT/Figshare record has no manuscript attachment;
repository metadata is not recovered methods. Group threshold ranges cannot
be assigned to individual peptides. Gong2025's morel-stipe ingredient abstract
does not establish per-peptide human/receptor overlap. Yi2025 and the 2026
retronasal-detection paper were previously qualified; their renewed appearance
is not a new matched panel. The exact eight Tu names had no match in the saved
numeric/range receptor table; that bounded check is not proof of inactivity.

**Next precise action:** qualify the first legitimately recovered complete
candidate-level source against a single joint table: exact peptide, measured
functional receptor result and conditions, human saltiness-minus-background
result and conditions, uncertainty, candidate/source dependence, missingness
and selection history. Inspect the complete denominator before extracting
favorable rows. A study supplying only one side stays an evidence lead. Current
public copies do not supply this table; repeated blocked downloads add nothing.
MSK remains a conditional ingredient-level lead, not the sole project gateway.

No outreach, new human/cell work, publication, purchases, automation or paid/GPU
jobs are authorized by this design. No preference-study pivot is made. Prior methodological guidance
advice to begin with actual sensory evidence remains useful guidance; proposed
noise floors or transferred activity bounds still require assay-specific proof.
