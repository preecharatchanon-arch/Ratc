# Further CaSR research and executed tests

27 October 2026. **The focused models modestly improve point errors, but do not
establish a reliable predictive gain. Independent RMSD verification confirms
the docking pose-ranking limitation.** The most useful continuation is a
condition-specific receptor/sensory evidence study with measured comparators.

## What was actually run

The configuration was fixed before fitting these new models. It was informed
by previously inspected results, so it remains exploratory. All 58 original
numerical/range compounds were reconstructed with matching stereochemical
graphs using RDKit 2025.09.3. The original 26 constitutional-family folds and
random five-fold partitions were reused, along with both label scenarios.

Three fixed candidates were fitted: positional neutral-fragment descriptors;
the same representation with middle-residue interactions with exact single-Gly
and hydroxy-tail context; and a range-aware loss on those interaction features.
Each uses alpha 10. Scaling was fitted on the training fold only. No model or
hyperparameter search was added after reviewing the output.

The fragment representation has 19 additive features and 31 with interactions.
Tail monomers are parsed explicitly: a Gly–Gly tail is not mislabeled as a single
Gly. These are neutral bookkeeping graph descriptors, not predicted solution
microstates or measurements of receptor exposure. All nine qualitative
non-activators and the explicit lower-bound record remain outside this regression
comparison; no numerical potency was invented for them.

## Prediction results

MAE is in pEC50 log units; lower is better. These are held-middle-family results:

| Method | Journal labels | Alternate patent assignments |
|---|---:|---:|
| Training mean | 0.8971 | 0.8971 |
| Existing nearest-three model | 0.7989 | 0.7967 |
| Positional Ridge, primary candidate | 0.7653 | 0.7680 |
| Context-interaction Ridge, secondary | 0.7516 | 0.7653 |
| Range-aware context Ridge, secondary | 0.7481 | 0.7611 |

The primary candidate's journal-label gain over nearest-three is 0.0337, with
10,000-resample whole-family bootstrap interval **[-0.1104, 0.1553]**. For the
alternate assignments the interval is **[-0.1122, 0.1502]**. Both cross zero, so
the prespecified exploratory gain criterion fails. Secondary candidates also
have gain intervals crossing zero. Selecting the best point error would not
turn these results into independent confirmation.

Range-aware fitting reduced its journal-label distance-to-range MAE to 0.7239,
versus 0.7765 for nearest-three. This objective permits any value inside a
published range; the ranges are not confidence intervals. It is a useful
sensitivity analysis, not a measurement-noise model or a full censored likelihood.

Six of 58 held-family queries lie outside at least one training-only middle
descriptor min/max range; seven have tail contexts absent from training. The
primary candidate's error is 1.796 outside that middle box and 0.646 inside it.
No cases were dropped from the primary metric. This box is a descriptive
extrapolation flag, not a calibrated applicability domain or a new guarantee of
accuracy inside it.

## Can chemistry predict the Gly-extension effect?

All eleven complete core/Gly pairs were tested by leaving one pair out. A fixed
middle-fragment Ridge model gave effect MAE **0.9151**, versus **0.8851** for
predicting the training mean effect. Its gain interval is **[-0.2498, 0.1842]**.
Thus the observed context dependence is not yet a successfully predicted rule.

This task asks about a change from an already measured core to its analogue.
It does not predict an unseen core's full potency, and the eleven pairs are
from the same compiled source. It should not be described as external validation.

## Independent RMSD check: completed

The original archived ten native-ligand poses were checked with spyrmsd, using
symmetry correction, no centering and no rigid alignment. Its values agree
with RDKit to **8.9e-16 Å** on the saved coordinates:

- Top-scored pose: **4.7803 Å**.
- Closest returned pose: **2.3158 Å**, ranked fifth in this ten-pose run.
- A reference translated by 5 Å correctly returns 5 Å, while swapping
  symmetry-equivalent carboxylate oxygens returns zero after correction.

The last two checks ensure that an alignment operation did not hide displacement
and that atom symmetry was considered. Differences of about 1e-6 Å from the
earlier in-memory numbers are consistent with saved SDF coordinate rounding.
These ten poses are the original panel run, not the distinct higher-search run.
Their successful reanalysis provides no reason to reinterpret the top pose as
near native. No new docking or MD was performed.

## Literature findings that change the next comparison

**Amino2016 provides a particularly useful existing reference pair.** In its
NaCl/MSG/IMP mixture, reported recognition thresholds for gamma-Glu-Val-Gly,
gamma-Glu-Nva-Gly and gamma-Glu-Nva are 0.47, 0.028 and 0.077 ppm. Five assessors
participated over three sessions. Val-Gly's reported point threshold is therefore
16.8 times Nva-Gly's, while their reported CaSR EC50 intervals overlap.
This is kokumi mixture recognition, not isolated saltiness or sodium reduction.
It is already published and belongs to the same source as our receptor table;
it cannot be repackaged as an independent test or a new biological discovery.

**Yi2025 adds two source-reported sensory comparators:** gamma-Glu-Gly-Pro-Phe
and gamma-Glu-Ala-Phe-Phe. Their abstract reports salt-enhancement thresholds
of 0.76±0.22 and 0.58±0.21 mM. We recovered the public supplement, which contains
a sensory scoring card and purity figures. Exact threshold-test matrix, panel
and uncertainty statistic remain unverified from the accessible material.
Computational CaSR docking/MD is not a measured receptor EC50 for these peptides.

**Tu2023 reports eight gamma-glutamyl tripeptides with enhancement.** Its primary
abstract provides only a set-level salt-threshold range, 1.65±0.19 to
2.23±0.20 mM. Individual assignments and full conditions were not recovered.
The sequence records are kept, but that aggregate range is not assigned to
each compound. These are evidence leads rather than assay-matched training labels.

**Ahmad2025 is a useful boundary case.** It measures CaSR responses to GSH-sugar
Maillard mixtures and explicitly lacks sensory validation. It should not be
added as confirmed human salt enhancement or as a pure-compound regression row.

An independent 2024 GSH-derived-probe study also shows that its CaSR binding and
functional readouts depend on extracellular calcium and assay controls. This
supports retaining conditions; it does not provide a new food-taste candidate.

The registry contains 15 evidence entries across five publications, including
the earlier chicken-consommé comparison. It is not an unbiased sensory benchmark:
missing conditions, pooled thresholds, same-source overlap and different
endpoints remain explicit.

## Direction justified by these results

Prioritize **gamma-Glu-Nva-Gly versus gamma-Glu-Val-Gly as a reference comparison**
for studying why receptor potency and a defined sensory endpoint diverge. Their
existing reports help design the question; independent matched measurements
would still be required to test an explanation. Keep the Nva/Val core comparison
as a terminal-context control, and keep the arginyl/ENaC branch separate.

The next computational investment should recover and harmonize external
compound-by-condition measurements, with separate CaSR activity, kokumi and
salt-specific fields. The new studies supply concrete retrieval targets, but
their unresolved matrix fields must be recovered before quantitative transfer
testing. Fit a new-source evaluation only after that evidence exists. The
current results do not support another unconstrained model sweep or a broad
screen of unmeasured compounds.

No new receptor activity, human taste experiment, sodium-reduction percentage,
food-use status or effective compound is claimed. The original repository and
result archives remain unchanged.

## Primary sources

- Amino et al., 2016, [10.1248/cpb.c16-00293](https://doi.org/10.1248/cpb.c16-00293),
  sensory results and methods; measured receptor series.
- Miyaki et al., 2015, [10.1186/2044-7248-4-17](https://doi.org/10.1186/2044-7248-4-17),
  matrix-specific sensory comparison.
- Yi et al., 2025, [10.1007/s11947-025-03894-7](https://doi.org/10.1007/s11947-025-03894-7),
  primary abstract and author supplement, DOI-linked MOESM1 file.
- Tu et al., 2023, [10.1021/acs.jafc.3c01467](https://doi.org/10.1021/acs.jafc.3c01467),
  [primary PubMed abstract](https://pubmed.ncbi.nlm.nih.gov/37170549/).
- Ahmad et al., 2025, [10.1016/j.fochx.2025.102616](https://doi.org/10.1016/j.fochx.2025.102616).
- GSH-based probe study, 2024, [10.1021/acschembio.4c00335](https://doi.org/10.1021/acschembio.4c00335).
- [spyrmsd API](https://spyrmsd.readthedocs.io/en/develop/api/spyrmsd.rmsd.html)
  and [RDKit RMSD API](https://www.rdkit.org/docs/source/rdkit.Chem.rdMolAlign.html).

Reproduction code, all fold predictions, source-access notes, protocol and
verification receipts accompany this report. Third-party papers and supplements
are not redistributed. CPU execution covers the tests above; it does not
constitute biological validation.
