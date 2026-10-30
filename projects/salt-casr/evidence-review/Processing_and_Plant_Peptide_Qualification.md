# Processing, mushroom ingredient and plant-peptide evidence

> **Historical assessment.** This dated record preserves source qualifications and earlier decisions. For subsequent work, use the [current research status](../docs/RESEARCH_STATUS.md) and the [current test design](../docs/NEXT_TEST_DESIGN.md).

28 October 2026, Asia/Bangkok. This assessment supersedes older acquisition priorities. No
scientific numerical experiment, model, notebook, docking or MD was run.
This file evaluates published evidence; none of it is our wet-lab result.

## Decision

Retain the peptide-selection question: can measured functional CaSR activity
improve selection of human saltiness enhancers under defined conditions?

A new mushroom preprint provides a credible **lead for ingredient-level
receptor/human overlap**, which is more relevant than another receptor-only
screen. Its actual paired measurements and control composition are still
unrecovered. A newly identified journal article gives another legitimate
route to the previously blocked plant-peptide work, but accessible text does
not establish human saltiness outcomes. Neither supplies a usable new panel.

The gain from this continuation is a better acquisition target and a stricter
design for processing and source dependence. It is not validated prediction,
proof of CaSR-mediated saltiness, or evidence that an ingredient reduces sodium.

## Four source qualifications

### Mushroom-stalk MSK preprint: direct human endpoint lead, methods unresolved

[Ahmad et al., DOI10.2139/ssrn.7173378](https://doi.org/10.2139/ssrn.7173378)
is a32-page preprint posted24July2026. Its primary abstract reports enzymatic
conversion of *Agaricus bisporus* stalks into MSK powder, detection of gamma-EVG
after conversion, dose-dependent CaSR responses, and consumer rate-all-that-
apply (RATA) evaluation in chicken stock. Reported increases include saltiness
and savouriness as well as kokumi descriptors. RATA attributes are not liking.
The abstract reports no significant receptor difference after100C heating,
and reduced activity at150C; the former does not establish equivalence.

The full methods/results were not recovered. Dose/basis, sodium, control,
panel size, paired uncertainty, pH/calcium, receptor species/construct and
receptor/sensory material matching remain unknown. Detection after conversion
does not assign mixture activity to EVG or turn earlier nondetection into
absence. No numerical saltiness label or peptide potency was added.

The [BPA project23234 summary](https://bioresourceprocessing.co.nz/executive-summary/flavour-enhancer-from-mushroom-stalk-a-proof-of-concept/),
16July2026, supplies a grounded institutional route, not the missing methods
or an independent replication. Its public page has no project-report download;
the linked general impact report did not supply the study data. SSRN delivery
was denied; author-hosted listing offers a request button, not a public copy.
Crossref/OpenAlex disclose no alternate full-text copy. No request was sent.

### Kim2024: distinguish potency from maximum response

[DOI10.1111/ijfs.17293](https://doi.org/10.1111/ijfs.17293), original text and
captions: four preparations (beef, mutton, lamb, venison), stable human-CaSR
CHO-K1, negative CHO-Galpha15 cells,10kDa ultrafiltrate, BCA protein basis,
maximum-minus-minimum fluorescence. Three cartons per meat class were
processed independently; technical triplicates are not extra material units.
Assay free calcium, pH and NaCl are not established in the inspected methods.

Figure2 reports EC50 values with an unclear printed unit description and a
qualified venison value; no common molar potency is inferred. Beef heating
methods say100/120/150C for3h, whereas abstract/results/Figure3 say80/120/150C.
That discrepancy remains unresolved. Results report no significant EC50 change
and a nonsignificant decline in maximum response. No human sensory experiment
is reported. A source's assertion that receptor screening is reliable does
not itself validate prediction of human saltiness.

### Kim2026: processing matters, but no human outcome or independent baseline

[DOI10.1093/ijfood/vvag112](https://doi.org/10.1093/ijfood/vvag112), primary
indexed methods/captions: new lamb hydrolysate plus glucose or xylose;5% powder,
1.6% sugar, pH7, sealed aqueous heating for3h. Methods/Table1 include100C;
reported receptor figures use25/80/120/150C. Human-CaSR CHO-K1 activity uses
fluorescent-peptide concentration,0.0062–0.8mg/mL, unlike2024's BCA basis.
No human sensory evaluation was performed.

Figure1 explicitly reanalyses/reproduces Kim2024 bovine heating data. It is
not independent confirmation or a newly manufactured matched lamb control.
The later significance claim cannot be reconciled with the earlier
nonsignificance by comparing p-values alone. Methods describe separate cell
grow-ups; captions/statistics also describe three independent hydrolysate
preparations and technical-well averaging. Their batch/day mapping is unknown;
nine plotted wells are not nine independent process runs. Separate sugar
panels have different unheated responses; no cross-panel ratio is calculated.
No active molecular entity was isolated. No peptide-level saltiness label results.

### Reumiller2026 journal article: functional lead, panel not recovered

[DOI10.1016/j.foodchem.2026.150843](https://doi.org/10.1016/j.foodchem.2026.150843),
available online18August2026, provides a journal route distinct from the blocked
thesis PDF. Publisher abstract/highlights report black-gram processing,
peptidomics, docking and functional CaSR assays, including Tyr-Phe-Tyr.
Over8900 identified peptides do not mean8900 individually tested receptor
ligands or human outcomes. The accessible text supplies neither the actual
tested-candidate denominator nor human saltiness measurements, assay conditions
or uncertainty. This is unresolved coverage, not a negative human result.

Publisher access was denied; the metadata-advertised public XML route returned
a short unavailable-page HTML response, not article XML. OpenAlex gives no
alternate full text, and the author listing has no public manuscript. The
publisher states that data are available on request. EC50, nonresponder status and sensory scores remain unestablished.

## What changes in the design

**Processing is part of the material definition.** For a food application,
pair receptor and sensory measurements on the relevant processed material,
or explicitly justify transfer. A pre-cooking response cannot silently become
the feature for cooked food. Preserve precursor identity and the resulting
mixture separately; an ingredient is not an isolated peptide.

**Do not pool exposure policies.** Equal protein mass, equal fluorescent-
peptide mass, equal dry powder, equal molarity and equal application dose are
different comparisons. Record which was used. Cross-method conversion requires
measured calibration; no conversion was manufactured here. A larger maximum
response is not automatically lower EC50 or greater human enhancement.

**Match both sides of a contrast.** Record each receptor test and comparator,
each sensory test and comparator, recipe sodium and measured total sodium
separately. Enzyme treatment may change free glutamate, other peptides, aroma,
counterions, acidity and texture. These are plausible alternative contributors
to a preparation-level result; they are not evidence against CaSR involvement.

**Track reuse and replication layers.** Retain material batch, process run,
assay day/cell grow-up, well, participant and session as distinct fields.
Repeated publications and wells must not inflate the candidate denominator.
Preserve reporting conflicts rather than choosing the more favorable version.

## Conditional extraction card before any later test

These are data requirements for a future comparison. The [current test design](../docs/NEXT_TEST_DESIGN.md) sets out the main selector question; the sources reviewed here do not establish its success margin.

| Required item | Decision specified now | Unresolved execution requirement |
|---|---|---|
| Hypothesis | Measured functional CaSR adds useful saltiness-selection yield to the same frozen baseline and budget | Actual common peptide panel and application domain |
| Competing explanation | Dose, sodium, other tastes, processing or matrix accounts for apparent benefit | Matched controls and recorded composition/exposure |
| Eligible data | Identified peptides with measured functional receptor and controlled human saltiness outcomes, retaining failures/censoring | No new recovered panel meets this gate |
| Independent unit | Peptide identity, retaining family/source dependence | Actual roster and tested denominator; preparation results remain separate |
| Primary comparison | Baseline selection versus baseline plus CaSR on the same candidates; paired saltiness contrast | Frozen rule, budget, receptor feature and sensory endpoint |
| Practical success/failure | Interval resolves a justified useful gain; informative upper bound below that gain stops this selector | Justified sensory-effect and selection-yield margins remain unset |
| Uncertainty | Assessor pairing, batch/day effects, family/source clustering and censoring | Raw observations or adequate covariance/replication summaries |
| Next decision | Useful gain advances the tested domain; informative no gain stops it; insufficient data prevents execution | Current outcome is the data prerequisite, not empirical failure |

For MSK, first extract an **ingredient contrast map**, not a peptide training
row: every formulation, control, dose/basis, stock composition, sodium/pH,
processing, lot/source link, receptor readout, RATA scale/zero handling,
assessor/session pairing and uncertainty. Determine whether control and test
are shared across the receptor and human comparisons. If the original supplies
only one enriched powder, it may support a specific ingredient effect but not
incremental peptide-selection performance. Increased saltiness does not become
CaSR causality merely because that powder activates CaSR in cells.

## Next precise action and stopping rule

The next useful document is the **actual MSK methods/results and formulation
table**, obtainable only if a new legitimate public copy becomes available.
Extract the contrast map above first. In parallel only when an actual new
public route exists, recover Reumiller's tested synthetic-peptide table and
functional assay conditions; verify whether human outcomes are present before
considering any join. Neither repeated blocked URL requests nor another
abstract summary changes this gate.

If no new full source is available, the current task is blocked at acquisition.
Do not expand a receptor-only model, digitize curves to manufacture precision,
relabel RATA sensory attributes as liking, or start a cooking experiment to make output.
The liking question remains a separate application option requiring its own
data/design and explicit scope decision. Previously completed computational
no-go results and the five named saltiness/receptor identity links are unchanged.
