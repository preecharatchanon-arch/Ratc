# Arginyl peptides: the starting question

[Project](../README.md) · [Functional evidence](../experiments/05-functional-assay-controls/README.md) · [Chemical control table](../experiments/05-functional-assay-controls/results/control_panel_chemistry.csv) · [Executed code](../experiments/05-functional-assay-controls/code/compare_control_panel.py)

Research note by **Ratchanon Preecha**, 15 October 2026. This note develops the completed functional-evidence analysis. It is a control-selection calculation and literature synthesis, not a sixth biological or prediction experiment.

**Starting question:** in the published AR/RA/RP cellular comparison, does an arginine side chain contribute beyond nominal positive charge? A matched Arg-to-Lys comparison can test that question. The present data do not answer it.

## What the existing comparison can distinguish

At the common condition of 50 μM peptide and reported 150 mM NaCl, Xu et al. [1] report increased responding-cell fractions over SUM for AR, RA and RP, but not RE, ER, DD or ED. Our calculation adds a simple chemical annotation:

| Published comparator | Nominal side-chain charge balance | Reported increase at 50 μM peptide / 150 mM NaCl |
| --- | ---: | --- |
| AR, RA, RP | +1 | Yes |
| RE, ER | 0 | No |
| DD, ED | −2 | No |

Here the nominal balance is **(number of Arg + Lys) − (number of Asp + Glu)**. It is a neutral-pH bookkeeping descriptor. It is not measured net charge, a pKa calculation or the formal charge of an RDKit graph; free-terminal and environment effects are omitted.

This selected comparison contains no positively charged, non-arginyl dipeptide. Consequently, it cannot determine whether arginine-specific chemistry is necessary for the response rather than a broader property shared by cationic peptides. This is a design gap, not evidence that charge causes enhancement.

The association does not explain the complete dose/NaCl panel. At 50 mM NaCl and 50 μM peptide, RP has the same nominal balance but no reported increase; at 100 μM none of the three has an increase reported. We export all four common-dose strata rather than presenting the favourable condition as a general rule. No classifier, p-value or out-of-sample accuracy is calculated.

## Chemical comparisons to prioritize

| Known cellular comparator | Proposed charge-matched control | What the comparison changes |
| --- | --- | --- |
| AR: Ala–Arg | AK: Ala–Lys | Replace guanidinium-bearing Arg with amine-bearing Lys at the C terminus |
| RA: Arg–Ala | KA: Lys–Ala | The corresponding substitution at the N terminus |
| RP: Arg–Pro | KP: Lys–Pro | Extend the comparison to a different partner residue |

Each pair retains two residues and nominal balance +1. It changes side-chain geometry, hydrogen bonding, hydration and pKa as well as molecular mass, so it is not a perfect isolation of charge. The free-form molecular-weight difference is 28.014 g/mol in each pair. Equal-mass dosing would therefore not give equal molar exposure.

For example, calculated free-form amounts for 50 μM are **12.264 mg/L AR** and **10.863 mg/L AK**. These are preparation equivalents under an anhydrous, free-peptide assumption—not observed active doses for AK. Actual salt form, counterion, water content and assay medium would need to be accounted for.

The three lysine dipeptides are absent from the retained 580-record benchmark and from the seven-peptide human taste-cell panel. Their absence is not evidence of novelty, inactivity, safety or a lack of prior research. A bounded literature search did not verify their activity in this specific assay. Their role here is **unmeasured mechanistic controls**, not predicted hits.

An independent rationale for including lysine exists: the primary Stähler et al. [2] abstract reports effects of free L-lysine on human salt perception and on currents through heterologously expressed human ENaC. That observation is not evidence for AK/KA/KP, and the full methods were not obtained here.

## The dose bridge is still missing

Xu et al. [1] quote earlier human sensory enhancement for AR/RA at **12 mM** in **50 mM NaCl**, while their own cellular enhancement comparison includes **50 μM** peptide. Those peptide concentrations differ by **240-fold**. This is not a potency ratio: the assays, endpoints and environments differ.

The original Schindler et al. [3] abstract and free supporting information were retrieved. The supplement contains MS/MS settings and hydrolysate composition, not the sensory dose-response data. We therefore retain the 12 mM statement explicitly as **Xu et al.’s citation of the earlier sensory study**, not independently recovered original methods. There is no verified continuous sensory-to-cellular dose curve in our collection. We cannot infer human taste at 50 μM from that evidence.

A useful sequence of work is to reproduce the AR response with its peptide-only/NaCl-only/SUM controls, then compare AR/AK and RA/KA across the reported dose range in the same functional system. Add RP/KP only if the first comparisons are informative. A human sensory comparison would remain a separate, professionally supervised study with explicit final concentrations and matched sodium, counterions and pH.

## Keep two counterexamples in view

A universal “positive peptide charge means salt enhancement” rule is already too broad. Kino et al. [4] report enhancement for the non-arginyl dipeptide **Met–Gly**, confirmed with a pure standard at 0.1% w/v in 0.6% w/v NaCl. Their 0.05% w/v sensory ranking places it between 0.60% and 0.65% NaCl intensity; their electronic-sensor estimate is a separate measurement. This supports keeping neutral sensory comparators separate from an ENaC-specific hypothesis. We do not label Met–Gly as a verified ENaC activator.

Also, Bigiani and Rhyu [5] used patch-clamp recording in rat sodium-taste cells. At 20 μM, GSH and γ-Glu-Val-Gly slightly reduced the ENaC-associated inward current rather than increasing it. This does not contradict an AR result measured in a different system or rule out human kokumi/saltiness effects. It does show why CaSR activity, calcium-response fractions and ENaC current must not become interchangeable screening labels. Species, preparation and channel state remain relevant.

## What would change our conclusion

- If the AR effect cannot be reproduced with the stated controls, broad analogue screening should stop while the assay discrepancy is resolved.
- If Arg and Lys pairs show comparable responses, an arginine-specific motif is not necessary for that tested response; a shared cationic property is one explanation, not a proven mechanism.
- If Arg pairs respond and matched Lys pairs do not, the result supports side-chain specificity beyond the nominal charge class. It still does not establish direct binding or a site.
- If a functional effect reproduces but sensory enhancement does not at the relevant formulation condition, the cellular endpoint is insufficient for the food-level goal.

The computational work completed here makes those comparisons concrete: 12 explicit chemical graphs, three matched pairs, molar-dose equivalents and four condition-specific charge strata. It does not predict their tastes or discover a new effective compound.

## Inspect or reproduce

The saved [chemical table](../experiments/05-functional-assay-controls/results/control_panel_chemistry.csv), [SDF structures](../experiments/05-functional-assay-controls/results/control_panel.sdf), [pair definitions](../experiments/05-functional-assay-controls/results/matched_control_pairs.csv), [condition strata](../experiments/05-functional-assay-controls/results/condition_charge_strata.csv) and [execution summary](../experiments/05-functional-assay-controls/results/control_selection_summary.json) are included with Experiment 05. See the separate [source/verification record](../experiments/05-functional-assay-controls/verification/CONTROL_SELECTION_REVIEW.json).

From that experiment folder, with Python 3.12:

```sh
python -m pip install -r requirements_control_selection.txt
python code/compare_control_panel.py
```

The calculation runs in seconds on CPU. It reads retained inputs and uses RDKit for chemical graphs and masses; no API, docking or ML model is involved. New outputs go to ignored `runs/control_selection/`. The three published Colab notebooks are unchanged.

## Sources and access

1. Xu JJ, et al. (2017). [Scientific Reports 7, 7483](https://doi.org/10.1038/s41598-017-07756-x). Primary full Results/Methods inspected; its citation of the 12 mM sensory dose remains a secondary attribution.
2. Stähler F, et al. (2008). *A Role of the Epithelial Sodium Channel in Human Salt Taste Transduction?* Chemosensory Perception 1, 78–90. [DOI](https://doi.org/10.1007/s12078-008-9006-4). Publisher abstract inspected; full experimental methods not obtained.
3. Schindler A, et al. (2011). *Discovery of Salt Taste Enhancing Arginyl Dipeptides in Protein Digests and Fermented Fish Sauces by Means of a Sensomics Approach.* JAFC 59, 12578–12588. [DOI](https://doi.org/10.1021/jf2041593); [author supplement](https://doi.org/10.1021/jf2041593.s001). Main abstract and supplement inspected; original main sensory methods not obtained. Full publisher files are not redistributed.
4. Kino H, et al. (2015). *Screening of Salt Taste Enhancing Dipeptides Based on a New Strategy Using L-Amino Acid Ligase.* Nippon Shokuhin Kagaku Kogaku Kaishi 62, 274–281. [DOI](https://doi.org/10.3136/nskkk.62.274). Primary Japanese full text, Methods §4 and Results §3 inspected. Reaction-mixture screening outcomes are not treated as pure-peptide labels.
5. Bigiani A, Rhyu MR (2023; online 2022). *Effect of kokumi taste-active γ-glutamyl peptides on amiloride-sensitive epithelial Na+ channels in rat fungiform taste cells.* Biochemistry and Biophysics Reports 33, 101400. [DOI](https://doi.org/10.1016/j.bbrep.2022.101400). Primary full paper inspected through the authors’ institutional copy. No raw cell data or source figures are reanalysed here.
