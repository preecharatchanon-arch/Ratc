# Expanded source search and qualification of the actual comparisons

> **Historical assessment.** This dated record preserves source qualifications and earlier decisions. For subsequent work, use the [current research status](../docs/RESEARCH_STATUS.md) and the [current test design](../docs/NEXT_TEST_DESIGN.md).

28 October 2026. This public assessment summarizes the 28 October evidence review.
This is an evidence assessment and written design amendment. No new scientific
numerical test, predictor, docking/MD run, notebook, or human/biological
experiment was performed. Published measurements below belong to their authors.

## Decision

Measured CaSR activity remains a plausible candidate-selection feature, but
its **incremental usefulness for human saltiness has not been established**.
The strongest newly recovered application report connects receptor and food
sensory work at the extract level. Its actual materials and comparisons do
not support the proposed peptide-level selector test. The newer cellular
papers do not fill that gap through calcium fluorescence alone.

The five previously indexed named saltiness/receptor links remain unchanged.
They are heterogeneous descriptive links, not five observations from a common
candidate experiment. New contextual records are kept in
`source_qualification.json`; they are not appended as saltiness training rows.

## Bounded search, with its denominator and limits

Two Europe PMC MEDLINE-source title/abstract searches were retrieved on
28 October 2026, using `resultType=core`, `pageSize=100`, first-date cutoff
28 October 2026. The exact queries and metadata are in `search_screen.json`.

| Search | Hits returned / reported hits | Overlap and use |
|---|---:|---|
| CaSR/calcium-sensing receptor + kokumi/saltiness/salty/taste + peptide(s) |48/48|Direct receptor/peptide screen;9 records tagged Review|
| Kokumi + receptor/activation/cells/cellular |65/65|Complementary screen;33 overlap with the first search,32 additional records|
| Combined unique MEDLINE records |80|Titles and available indexed abstracts assessed; methods depth recorded separately|

This is not a systematic review or proof that qualified data do not exist.
The database, title/abstract vocabulary, indexing delays and publication bias
limit coverage. Important known sources lack these terms in their abstracts.
Compound-name searches, patents, institutional documents and primary citation
routes supplemented the screen. The earlier broad 706-hit search returned
only 100 records and is **not** counted as an exhaustively screened collection.

Review claims were not used as primary measurements. An abstract-only screen
can establish what evidence was recovered, but cannot rule out every result in
an unseen full paper. The ledger distinguishes an endpoint mismatch verified
in original methods from unresolved acquisition. Missing tests remain missing.

## Closest new application evidence: AMPC2024-1087

Primary report: *Kokumi flavour peptide production from beef offal co-products*,
25 June2024. Sections4.1,4.5–4.6, Table1, Figures5–6; PDF pages7,11–12,18,20.

| Domain | Actual materials / comparison |
|---|---|
| Receptor |Liver-W, Lung-W, Liver-G, Lung-G; W=water extract, G=protease+glutaminase|
| Human patties |Control, Liver-P, Lung-P, Liver-G, Lung-G; P=protease hydrolysate|
| Nominal identity overlap |Liver-G and Lung-G only; W controls are not P controls|
| Processing |Analytical preparations: PC2 laboratory,10kDa ultrafiltration. Sensory preparations: separate food-grade laboratory, straining/60°C drying, then cooking in patties. Exact lots not established.|

Stable human-CaSR CHO-K1/Gα15 cells, receptor-negative controls,0.5mM calcium
and ΔRFU readout were used. Approximate source EC50 values are121µg/mL
protein for Lung-G and181 for Liver-G; Figure5 reports mean±SE,n3, with
biological/batch independence unresolved. These are extract potencies.

Flash profiling used7 experienced assessors, free-choice attributes and ranks
of five coded patties. Lung-G associated with salty/juicy descriptors in the
multivariate representation. No paired saltiness effect or raw-rank table was
recovered. Recipe masses are1350g beef,150g water,15g salt; supplemented patties
replace15g water with15g extract. Nominal1% additions do not establish measured
total sodium or sodium reduction. Sensory pH/free calcium remain unresolved.

**Assessment:** a real receptor/food-sensory connection, but not individual
peptide outcomes or an aligned receptor-versus-saltiness contrast. The common
extract names do not establish identical tested material. A two-extract
ordering, inferred PCA saltiness score, or G-versus-W/G-versus-P difference
would not validate selection. This mismatch cannot be repaired statistically.

Source: https://ampc.com.au/media/zq3lipxu/ampc-2024-1087-final-report-kokumi-agr.pdf

## A two-sided candidate search that did not yield human compound labels

Zhang2023, DOI10.3390/foods12030674, was investigated because anserine/carnosine
addition results appeared to offer complementary sensory evidence. Original
Sections2.3,2.5–2.6 and Figure5 distinguish the measurements:

- A10-person trained human panel rated four whole chicken soups.
- Component-addition experiments used an SA402B **electronic tongue**.
- The carnosine addition changes0.52,0.26,0.57 at0.23,0.12,0.17g/L are
  instrumental salt-sensor outputs, not human saltiness effects.
- Anserine addition statements likewise do not supply a purified-compound
  human outcome; whole-soup QDA cannot be allocated to its components.

No anserine or carnosine human label was created. Akiyama2023
(10.1016/j.physbeh.2022.114063) documents a human-CaSR HEK assay and mouse
trigeminal work, but no matched human saltiness outcome. Actual anserine
nonresponse limits were not recovered; no zero activity or EC50 bound is
invented. Failure of this documentary bridge is not a negative sensory result.

Primary chicken article: https://doi.org/10.3390/foods12030674

## Dose matching and receptor attribution: what the recovered supplement adds

Deng2026, DOI10.1021/acs.jafc.6c11250, original supporting information,
FigureS8/pageS10, was recovered and visually checked. Its identity was verified
against the parent DOI and publisher-hosted supplement metadata.

FigureS8A compares **umami intensity** for2mM MSG plus2mM GSH, gamma-EV or
gamma-E-gamma-EV. It has three peptide-mixture groups; a MSG-only sensory bar
is not present in that figure. S8B/C measure STC-1 calcium responses and CCK
with/without NPS-2143. The inhibitor manipulation is cellular, not a human
tasting manipulation. The supplement caption does not establish sensory n,
paired covariance or the meaning of its error bars here.

Equal molarity is useful against mass-dose confounding. These outcomes still
do not become saltiness or hCaSR EC50 measurements. An inhibitor-sensitive
component in murine enteroendocrine cells supports CaSR-related signaling;
it does not identify all response as CaSR-specific or demonstrate oral
saltiness selection. The associated2022 article
(10.1021/acs.jafc.2c04919) is related-source umami/gut-hormone evidence, not
independent confirmation of the present target.

SI DOI: https://doi.org/10.1021/acs.jafc.6c11250.s001

## A measured alternative pathway, with the construct limitation retained

Cornut2025, DOI10.1016/j.fochms.2025.100319, original full text, Sections2.3–2.4,
3.1–3.3/Figures1–6: GSH activates **human-TAS1R1/rat-TAS1R3**, with mock-cell
subtraction, mutagenesis and four independent experiments/duplicate wells.
The mixed-species umami construct must not be called a fully human receptor.
Human/human sweet-receptor responses were also tested; the reported
sucralose potentiation depended on rat TAS1R3 and did not transfer unchanged
to human/human TAS1R2/TAS1R3.

This is functional evidence that GSH need not act solely through CaSR in
these assay systems. It supplies neither a new CaSR measurement nor human
saltiness data. The article's0.71µM CaSR citation comes from Ohsu and is not
an independent assay. Cross-receptor EC50 ratios cannot establish which
pathway dominates a food response. Competing pathways belong in the design;
they do not justify launching a new mechanistic experiment on current data.

Primary: https://doi.org/10.1016/j.fochms.2025.100319

## Other concrete leads: decision and remaining uncertainty

| Primary source | Inspected evidence | Qualification for this question |
|---|---|---|
| Reumiller2026,10.1016/j.foodchem.2026.150843 |Primary abstract reports measured CaSR activation including Tyr-Phe-Tyr; online18Aug2026 despite30Oct issue date|Worth retaining as a receptor-panel acquisition lead. Full assay/species, candidate roster, values and separate human saltiness results remain unrecovered; absence is not inferred.|
| Wang2026 HKBU master's thesis, awarded28Sep2026 |Official record lists full thesis and abstract/TOC PDFs|Both listed downloads returned403. Actual methods, peptide table and outcomes unknown. No labels or claim of CaSR coverage; this is a newly grounded access blocker.|
| Cao2026 soybean,10.1016/j.fochx.2026.104238 |Indexed original methods identify TAS1R1-transfected HEK293; CaSR structure used as a modeling template|Calcium fluorescence here does not supply measured functional CaSR activity.|
| Wang2026 clam,10.3390/molecules31122193 |Original cellular methods/results: STC-1 calcium response and receptor transcripts|CaSR mRNA elevation is not CaSR-specific functional potency. Multiple receptor pathways remain possible.|
| Motoyama2020,10.1080/09168451.2020.1743169 |Primary abstract: hCaSR study of poly-Glu-Tyr series|Cannot transfer measurements to Wu's chemically different poly-Glu-Arg series.|
| CN120584963A |Feline-CaSR peptide responses and cat feeding work|Different species/outcome; not human saltiness. A species-proxy hypothesis would need its own justified matched-data design.|
| KR20180132007A |Human-CaSR agonist-dependent modulation by mannosylated dipeptides|No controlled human sensory example recovered; glycosylated forms are not unmodified dipeptides.|
| CN119708149B |Docking-selected peptides; actual follow-up electronic tongue|Neither docking score nor instrumental richness/salt signal supplies the required pair of measurements.|
| US20240180221A1 |Broad peptide/assay language; inspected examples concern stevia/mineral mixtures|Claims of possible use are not measured peptide CaSR/saltiness data.|
| CN114982861A |Original wheat-hydrolysate sensory protocol, ten assessors, mixture-level tests|No functional CaSR assay established; not Wu2022's arginyl series or the new HKBU thesis.|
| Kitajima2023 aldehydes,10.3390/molecules28124585 |Original full methods: transient hCaSR, nose clips, NaCl+MSG two-choice taste task|Useful endpoint/odor-control context; non-peptides and a combined umami/salty choice, not separate peptide saltiness labels.|

Reumiller's exact-title Figshare search returned no entries. A DOI-text search
returned an unrelated artwork, excluded after identity checking. Those bounded
checks do not prove that its supplements do not exist. No public manuscript
was recovered from the inspected publisher/metadata/institutional routes;
data-on-request language did not authorize outreach.

HKBU record: https://scholars.hkbu.edu.hk/en/studentTheses/synthesis-of-taste-active-%CE%B3-glutamyl-peptides-with-wheat-gluten-h/

## Written design amendment before any later execution

[Next test design](../docs/NEXT_TEST_DESIGN.md) remains the full test card, including hypothesis,
competing explanation, eligible data, independent unit, fixed-budget primary
comparison, meaningful gain criterion, uncertainty and decision consequences.
This continuation adds three operational requirements:

1. **Match the comparison as well as the name.** Record the material and
   transformation represented by each receptor and human observation. A
   purified-peptide contrast cannot be substituted with a hydrolysate contrast;
   G-versus-W cannot stand in for G-versus-P. Unknown lots qualify the strength
   of a named-identity link; different processing requires explicit evidence
   before treating the materials as equivalent. Analytical batch and cooked
   food exposure remain separate domains.
2. **Freeze exposure policy and attributable receptor feature.** Equal mass,
   equal molarity and source-optimized application doses answer different
   questions. Choose one justified policy before comparison, retaining peptide
   sodium/counterions and pH-adjustment sodium. Retain EC50/Emax and actual
   assay context. Bulk calcium or transcription alone is not a CaSR-specific
   feature. Antagonist-sensitive fractions and different species/constructs
   require explicit definitions, not conversion into a common EC50.
3. **Compare selection performance without requiring exclusive mediation.**
   A useful predictive feature need not be the only taste pathway. Nevertheless,
   dose, matrix, intrinsic taste and other receptors are plausible competitors.
   No causal dominance follows from a potency ratio or two extract rankings.
   Keep human saltiness separate from umami, kokumi, choice of combined
   intensity and liking.

The practical sensory and extra-yield margins remain unjustified, so they are
not assigned arbitrary numbers. Missing observations are not failures;
uncertain/censored measurements remain in the acquisition denominator.
Assessors, wells, time windows and batches do not multiply peptide identities.
All newly inspected observations are development evidence. No scientific
execution gate was passed.

## Next precise action and stopping condition

The next useful acquisition is an **actual candidate-by-candidate table**,
not another molecular model. Two newly identified source opportunities remain
specific: Reumiller's actual functional peptide panel and Wang's official2026
thesis results/TOC. Qualify any newly accessible original copy first: do its
named peptides have separately measured human saltiness under documented
conditions, and do actual functional CaSR records overlap? Full receptor data
alone or a full sensory-only thesis would still not unblock the selector test.

The old pea-EVV and fish-thesis leads remain unresolved, not newly verified;
the same failed routes are not requeued. Additional metadata queries do not
turn those gaps into measurements. If no new legitimate primary route or
qualified table becomes available, retain the blocker rather than fit proxy
labels, digitize unrelated endpoints or repeat completed no-gain analyses.

Human evidence and actual transfer determine test readiness; no universal
noise floor is assumed. Material, endpoint, dose and sampling frame must be
matched. Existing no-gain computational conclusions and closed docking/MD
decisions stand;9J7I was already used in the original project.

Reusable metadata and factual extractions are included. Third-party papers,
abstract corpora and page images are not redistributed. Any integrity checks
only verify record bookkeeping and packaging; they are not efficacy tests.
