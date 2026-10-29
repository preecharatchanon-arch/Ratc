# Modified-GSH identity and panel coverage

28 October 2026. The version11 checkpoint was read before this work. This is
source assessment, not a new experiment or a test of predictive usefulness.

## Decision

Keep the proposed Amino2016 compound58 / Givaudan sample3 link **provisional**.
The patent's cited DCE-GSH paper supports the intended connectivity, but does
not establish the identity of the material used for the receptor measurement.
The specific conflict is not resolved by another synonym or supplier listing.
Close this identity-retrieval branch unless a compound-specific structural
record, correction or material description becomes available.

This is an important limit on the dataset, but it does not advance empirical
validation of a CaSR selector. No linked-compound or saltiness count increases.

## What the original sources establish

| Source inspected | Established fact | What it cannot establish |
|---|---|---|
| Amino2016, DOI10.1248/cpb.c16-00293, original PDF Table2 p1183 and full methods | Row58 is named gamma-Glu-Cys(1,2-Dicarboxyethyl)-Gly, with HEK EC50 printed as5–10uM. Its abbreviation footnote instead prints S-(2,3-dicarboxymethyl)-cysteine. Both readings were checked visually. | Which description defines the assayed material; added stereocenter; compound-specific lot or spectrum |
| Same article's publisher landing page and experimental section | Supplementary material count is0. Detailed synthesis/characterization entries concern other numbered compounds; general methods state a purity criterion of at least95% for CaSR samples. | A compound58-specific synthesis, measured purity or stereoisomer composition. General characterization statements are not its disclosed spectrum. |
| US20090155440A1, Example1a sample3 and Example8 | Reports S-(alpha,beta-dicarboxyethyl)-gamma-L-glutamyl-L-cysteinyl-glycine. The general synthesis describes thiol addition to unsaturated carbonyl compounds, followed by purification and stated identity/purity checks. | A disclosed stereochemical analysis or spectrum tied to this sensory lot; a CaSR measurement |
| Tsuboi1999, DOI10.1248/bpb.22.21, complete five-page original scan; Figure1 and reagent subsection visually checked | Figure1 explicitly shows GSH-S-CH(COOH)-CH2-COOH. The DCE-GS standard was supplied by Senjyu Pharmaceutical. This is the paper cited by the patent. | No stereochemical assignment is drawn at the added carbon. It does not identify Amino's or the patent's tested lot. It contains no human saltiness or functional CaSR outcome used here. |

**Inference, not a source correction:** the patent's alpha,beta wording and
Tsuboi's1,2 wording are consistent with a succinate thioether connectivity.
That strengthens the *intended-name* interpretation; it does not authorize
silently changing the conflicting receptor footnote. No exact-material match
or stereoisomer mixture ratio is inferred from the synthetic route.

The source range5–10uM remains a printed range, not a confidence interval or
an invented7.5uM measurement. The published Amino erratum was already assessed
and does not resolve this compound. The manufacturer's indexed DCE-GSH entry
was also located, but no supplier or catalog number is tied to compound58 in
the paper. It cannot repair that provenance gap.

## Whole-panel coverage before considering a test

The patent panel has **eight additives, five containing a peptide backbone**,
plus one background reference. It is not an eight-peptide matched dataset.
The existing saltiness observations are retained below; this is a source
crosswalk, not another statistical analysis. All additives are reported at
10mM in nominal30mM NaCl, pH6.5. Total sodium, exact Example1a panel size,
paired dispersion and material salt forms remain unresolved as before.

| Patent sample | Reported additive, abbreviated only for readability | Peptide backbone? | NaCl isointensity, mM | Functional CaSR match established in inspected sources? |
|---:|---|:---:|---:|---|
| 2 | Dicarboxyethyl-L-cysteine | No | 40 | No; missing, not inactive |
| 3 | Dicarboxyethyl-GSH | Yes | 48 | Compound58 proposed; provisional, not confirmed |
| 4 | Dicarboxyethyl-gamma-Glu-Cys | Yes | 60 | No; unmodified gamma-Glu-Cys is a different compound |
| 5 | Dicarboxypropyl-GSH | Yes | 48 | No; missing, not inactive |
| 6 | Dicarboxyethyl-gamma-Glu-Cys ethyl ester | Yes | 48 | No; ester/backbone substitutions cannot borrow another potency |
| 7 | Dicarboxyethyl-cysteine ethyl ester | No | 42 | No; missing, not inactive |
| 8 | Carboxyethyl-GSH | Yes | 38 | No; Amino's carboxymethyl-gamma-Glu-Cys is not this material |
| 9 | Dicarboxyethyl-cysteine methyl ester | No | 38 | No; missing, not inactive |

The reference is30mM NaCl. Isointensity is a human saltiness endpoint, not a
measurement of sodium reduction. General pH adjustment/synthesis details do
not quantify the sodium in each sensory sample. Names above abbreviate the
patent; `evidence.json` retains the fuller source names.

Targeted CaSR searches for dicarboxyethyl, dicarboxypropyl and carboxyethyl
aliases did not establish additional matched receptor records. This is a
bounded search result, not proof that none exist anywhere. Patent citations
or broad claims are not functional measurements. The neighboring kokumi
diethyl-ester patent family is not interchangeable with these free-acid forms.

Even if sample3's identity were resolved favorably, one receptor-linked
candidate would not establish whether receptor measurements improve selection
among the five peptide-containing candidates. The panel's candidate-selection
history is also undocumented here; all eight additives are reported to enhance
saltiness. It cannot establish a general screening false-positive rate.

## Complementary acquisition check: a panel with non-significant findings

Wu2022, DOI10.1021/acs.jafc.2c03501, remains relevant because its primary
abstract reports four individual gamma-Glu-repeat/Arg peptides under a shared
study, including non-significant saltiness conditions. Those descriptions
were already retained. No new effect sizes were recovered in this pass.

The new access check found only DOI/PubMed locations in current OpenAlex
metadata. Targeted institutional/title searches found an official author
profile but no main manuscript. Its listed application202110379878.0 resolves
to the previously excluded CN113080426 patent, not a new gamma-Glu/Arg data
source. The publisher labels the main article available to purchase; the
previously read public supplement contains MS/MS spectra. No purchase or
request was made. This does not establish absence of a receptor assay from
the inaccessible main text. Existing missing CaSR fields stay missing.

## Consequence for the written test design

The previous hypothesis and primary comparison remain: measured functional
human-CaSR information must add practically useful selection yield beyond
the same frozen context/chemistry rule at a fixed follow-up budget. The
competing explanation remains dose, sodium/pH, intrinsic flavor, matrix or
other taste pathways, together with source-selection effects.

No eligible joint candidate panel has emerged. Candidate identity is the
selection unit; assessors, doses, wells and repeated reports do not increase
the number of independent candidates. Practical sensory and incremental-yield
margins remain unjustified, and paired/source-aware uncertainty is still
missing. Neither a favorable point estimate nor a significance difference
would satisfy the design. Thus no model, numerical hypothesis test, power
calculation or new notebook is executed.

A precise useful gain on independent eligible data would justify evaluating
that selector further; informative absence of useful gain would stop it;
wide uncertainty would remain inconclusive. The current outcome is an
unmet data prerequisite, not a negative biological or predictive result.
All inspected material remains development evidence. These source checks
must not be described as validation progress.

## Next precise action and stopping condition

The next useful action is **acquisition of a primary main-text/results copy
for the existing Wu2022 four-peptide panel, with a new legitimate location**.
On acquisition, inspect its individual-peptide saltiness comparisons, NaCl
recipe, pH/counterions, concentration basis, assay inventory and paired-error
reporting. First determine whether any actual functional CaSR measurements
exist; recovering a sensory recipe alone cannot qualify a joint selector test.
Do not rerun the known ACS/SI, abstract or author-profile searches as new work.

This action is currently access-blocked: no untried public location was found
in the bounded check. If none becomes available, remain at that prerequisite
rather than starting a surrogate fit or continuing generic retrieval queues.
The modified-GSH branch reopens only with a compound-specific primary record.
No outreach, payment, repository publication or wet-lab activity is authorized.

## Primary-source locators

- Amino2016 main text: https://www.jstage.jst.go.jp/article/cpb/64/8/64_c16-00293/_html/-char/en
- Publisher landing page with supplement count: https://www.jstage.jst.go.jp/article/cpb/64/8/64_c16-00293/_article/-char/en
- Givaudan patent: https://patents.google.com/patent/US20090155440A1/en
- Tsuboi1999: https://doi.org/10.1248/bpb.22.21
- Original scan: https://www.jstage.jst.go.jp/article/bpb1993/22/1/22_1_21/_pdf
- Wu2022 primary abstract: https://pubs.acs.org/doi/abs/10.1021/acs.jafc.2c03501
- Official Wu author profile: https://www.qztc.edu.cn/hyyspxy/_t5/2025/0929/c6100a287991/page.htm
- Listed application identity: https://patents.google.com/patent/CN113080426A/zh

Tsuboi1999 PDF:811516bytes; SHA-256
`60922a2fd143ab4e1545fc9b62454885a887dabcccbf15bfd6bb9d122106929b`.
OCR located passages; Figure1 and the reagent subsection were checked against
the original pages. Source scans and images are not redistributed.
