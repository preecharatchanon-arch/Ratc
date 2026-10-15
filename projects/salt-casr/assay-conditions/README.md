# Saltiness enhancement depends on assay and dose

Research and analysis by **Ratchanon Preecha**, 15 October 2026.

**[Executed notebook](Saltiness_Assay_Conditions.ipynb)** · **[Run in Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/salt-casr/assay-conditions/Saltiness_Assay_Conditions.ipynb)** · [Protocol](PROTOCOL.md) · [Data](data) · [Every model score](results/heldout_panel_scores.csv)

The preceding [source-transfer experiment](../sensory-continuation) found that
sequence models did not transfer reliably between reference groups. This follow-up
asks a more specific question: **are the labels and rankings stable when the
endpoint, NaCl background and peptide dose are made explicit?**

This is retrospective analysis of published experiments. The experimental
discoveries belong to the cited authors. Our contributions are the cross-source
label check, reproducible transcription, condition-aware comparison and fixed
baseline diagnostic. We have not discovered or experimentally validated a new molecule.

## A benchmark negative has published enhancement evidence

The SaltyMeta v1 workbook labels **NGYDMR negative**, with phenotype "umami,
sweetness" and evidence "B1 - excluded as salty in the same sensory study".
Its cited source is the 2025 Pleurotus ostreatus umami-peptide study [2].

A different primary study [1] reports NGYDMR significantly increasing saltiness
at **1 mg/mL peptide + 3 mg/mL NaCl**. Figure 1A gives it significance group b,
while the NaCl control is a. The separate time-intensity experiment reports
Imax 7.25 ± 0.27 versus control 5.50 ± 0.32. Those Imax values are not the
heights of Figure 1A's QDA bars.

This is an **endpoint/context conflict for a combined saltiness benchmark**.
The older sensory observation need not be wrong: absence of a standalone salty
descriptor does not establish absence of enhancement in NaCl. We retain both
contexts and the [original record](results/NGYDMR_original_benchmark_record.csv),
rather than silently changing its label. The older full text was not obtained;
its detailed assay conditions therefore remain unverified here.

## Dose changes the preferred peptide

Exact means transcribed from the straw-mushroom study's supplementary Table S4 [3]:

| Reported nominal peptide dose | DF8: DFNALPFK | YN9: YNEDNGIVK | VP10: VPGGQEIKDR |
| --- | ---: | ---: | ---: |
| 0.2 mM | 7.5 | 1.5 | 2.0 |
| 0.8 mM | 8.5 | 5.0 | 6.5 |
| 3.2 mM | 2.5 | 1.2 | 8.0 |

The nominal NaCl background is 0.5 g/L. DF8 ranks highest at the lower doses;
VP10 ranks highest at 1.6 and 3.2 mM. DF8 falls 6.0 score units from its observed
peak; YN9 falls 5.3. These are differences between published group means, not
new significance tests or independent observations from 18 different molecules.
This is evidence against using a single concentration-independent ranking for
these three peptides under this assay. It does not identify the cause of the decline.

![Published Table S4 means, replotted with reported SD](results/dose_rank_reversal.png)

Three unresolved source issues matter before translating this into a formulation:

1. Methods 2.11 describes 1:1 mixing with 0.5 g/L NaCl, without resolving whether
   the listed concentrations are stocks or final mixtures. All doses are retained
   **as reported nominal values**. The separate threshold assay's 0.5% NaCl is a
   different assay and is not merged with these measurements.
2. Figure 8 places VP10's last mean around 9, while Table S4 gives **8.0 ± 0.2**.
   We use the table. Both versions preserve the ranking reversal, but we do not
   repeat the claimed equivalence to 0.15% NaCl as a verified reduction result.
3. Figure S1's DFNALPFK caption gives m/z **574.25**. The unmodified sequence
   predicts **476.2504 for [M+2H]²⁺**; none of charge states 1–6 matches 574.25.
   The main text also assigns neutral mass **875.04**, versus calculated
   monoisotopic **950.4862 Da**. The spectrum is annotated with DFNALPFK and
   matching-looking fragment labels; this check cannot re-identify the peptide.
   Caption/transcription or modification explanations remain unresolved. Two
   other captions differ by about 0.01 Da, far smaller than the DF8 mismatch.

## Does the previous model retrieve experimentally reported enhancers?

We retain all six candidates in [1] and all five in the October mushroom study
[4], including less successful candidates. Both studies use 1 mg/mL peptide
with 3 mg/mL NaCl; their saltiness-scale calibration differs, so raw intensities
are not pooled. In [1], three candidates share the control's significance letter;
this is assay-specific non-significance, not universal biological inactivity.
The two "less pronounced" candidates in [4] remain unresolved rather than negative.

We fit the **same four fixed baselines** from the earlier analysis once each.
These are our independent baselines, not SaltyMeta's released ESM2 predictor.
After excluding matching/near-matching sequence components and known test-source
citations, training contains **244 sensory-tagged records: 138 positive, 106
negative**. The largest direct training-to-panel edit similarity is 0.667.
The benchmark labels still combine standalone saltiness and enhancement; this
limitation is deliberately preserved to test the earlier model's usefulness.

| Fixed model | Reported enhancers in top 3: Pleurotus, 6 candidates | October, 5 candidates |
| --- | ---: | ---: |
| Length only | 1 | 2 |
| Charge and length | 1 | 2 |
| Composition logistic regression | 1 | 1 |
| Extra Trees | 1 | 2 |

Each panel has three reported significant enhancers. Uniform random selection
would retrieve 1.5 and 1.8 respectively **in expectation**. These tiny selected
panels do not establish a population success rate, a significant difference from
chance or a reliable model ranking. Ties are flagged in the exported scores;
alphabetical tie-breaking has no biological meaning. No thresholds were tuned.

**Decision:** these results do not justify a new virtual screen or increasingly
complex ML on the same mixed labels. Nor do they establish that sequence-based
prediction is impossible. They identify the missing target: an assay observation,
including dose and matrix, rather than a universal peptide-level binary label.

## What this changes in the research

The strongest immediate experimental comparison is the **complete six-candidate
Pleurotus panel**, with its three positive comparators and three candidates that
did not differ significantly from control at the stated dose. It offers a more
informative test than taking only reported hits into docking. Any follow-up
should compare dose curves at explicitly final NaCl concentrations, retain
peptide-only and NaCl-only controls, and match pH/counterion/sodium contributions.
Mass-matched and molar-matched comparisons answer different questions; our
[nominal molar-dose table](results/nominal_molar_doses.csv) states its neutral
free-peptide assumptions rather than treating unknown counterions as measured.

The important question is whether an enhancement window survives those controls
and a different NaCl background. A blinded replication can establish that window;
receptor perturbation would then be needed to distinguish an ENaC-related effect
from other taste mechanisms. Docking alone cannot settle that question. These
published peptides are comparators, not proposed safe food ingredients.

For computation, collect condition-matched tested comparators and dose series
before fitting a concentration-dependent model. Three dose curves are sufficient
to expose a ranking problem, but insufficient to train or validate a general
sequence-to-dose-response predictor. No new API, GPU, AlphaFold run or molecular
dynamics trajectory is required to reproduce the present analysis.

## Run and provenance

Choose **CPU** in Colab and Run all. Embedded inputs need no upload or API key.
An isolated Python 3.12 worker reuses the earlier pinned scientific stack and adds
RDKit 2025.9.3 for the chemical mass checks; `MPLBACKEND=Agg` is set before any plotting import. Readable scripts and
data are embedded and are also provided beside the notebook. Local scientific
analysis takes a few seconds; fresh dependency installation dominates runtime.
Allow approximately 2–5 minutes on a fresh runtime, depending on downloads.

All notebook code cells were executed sequentially with IPython display capture.
The Colab browser itself was not directly tested by the author. A user-supplied Colab export was subsequently checked: every scientific CSV matches the reviewed results within numerical rounding (largest score difference 2.22 × 10⁻¹⁶). See [Colab run verification](COLAB_RUN_VERIFICATION.json). [Execution record](NOTEBOOK_EXECUTION.json)
and [source manifest](SOURCE_MANIFEST.json) distinguish executed calculations from
unverified source details. Publisher articles/figures are linked and were inspected
locally; they are not bundled into the notebook.

Local command, after installing `requirements_locked.txt` into Python 3.12:

```sh
python analyse_conditions.py
```

New experimental-table transcriptions are attributed to their sources under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); the benchmark input and
derivatives retain SaltyMeta's [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
attribution to Chen W, Li W, He Y and Yang Y. Source code retains the repository's
academic-review terms. The earlier source workbook and curation code are available
in [sensory-continuation](../sensory-continuation).

## Sources

1. Yang M, Wang W, Zhu B, et al. (2026). *Characterization of saltiness-enhancing peptides from Pleurotus eryngii: identification, sensory evaluations, and mechanism of saltiness-enhancing.* npj Science of Food 10, 39. [DOI](https://doi.org/10.1038/s41538-025-00681-8). Figure 1A, Table 1, supplement Tables S1–S2.
2. Wang W, Yang M, Zhou S, et al. (2025). *Identification of novel umami peptides from Pleurotus ostreatus and their umami-enhancing effects through virtual screening, sensory evaluation, and molecular simulation.* Food Chemistry 492, 145575. [DOI](https://doi.org/10.1016/j.foodchem.2025.145575). Benchmark citation; abstract/metadata inspected.
3. *Taste-Active Peptides from Triple-Enzymatically Hydrolyzed Straw Mushroom Proteins Enhance Salty Taste: An Elucidation of Their Effect on the T1R1/T1R3 Taste Receptor via Molecular Docking.* Foods (2024) 13, 995. [DOI](https://doi.org/10.3390/foods13070995). Methods 2.11, Results 3.6, Figure 8, supplement Table S4 and Figure S1.
4. Kong W, Lin L, Lai L, et al. (2026). [October mushroom peptide study](https://doi.org/10.1038/s41538-026-01088-9). Experimental synthesis panel and sensory calibration; see the preceding source manifest for inspected copies.
5. Chen W, Li W, He Y, Yang Y (2026). *SaltyMeta*, [arXiv:2609.16809v1](https://arxiv.org/abs/2609.16809v1). Original supplementary workbook, submitted 15 September 2026; author-curated labels are not independently verified for all 580 records here.

