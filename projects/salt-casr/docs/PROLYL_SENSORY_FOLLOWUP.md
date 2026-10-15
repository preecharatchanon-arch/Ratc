# Sensory evidence changes the peptide comparison

[Project](../README.md) · [Functional controls](../experiments/05-functional-assay-controls/README.md) · [Inputs](../data/functional/README.md) · [Reproduction code](../experiments/05-functional-assay-controls/code/compare_published_sensory.py)

Research follow-up by **Ratchanon Preecha**, 15 October 2026. This is a recovery and analysis of published experimental evidence. We did not measure peptide activity or train a new predictor.

**The useful change:** Lys–Pro (KP) already has reported sensory salt-enhancement evidence. It remains unverified in the particular human taste-cell assay used for our Arg-to-Lys question. RP/KP is therefore a comparison of two reported sensory enhancers whose functional mechanisms can be compared, rather than a known enhancer versus an assumed inactive control.

## 1. The proposed comparator has prior sensory data

Table 4 of the primary patent US20210000152A1 [1] reports duo-trio dilution tests in model broth:

| Peptide | Reported salt-enhancement threshold in model broth |
| --- | ---: |
| Arg–Pro, RP | 0.5 mM |
| Lys–Pro, KP | 1.2 mM |
| Val–Pro, VP | 0.8 mM |
| Pro–Val, PV | 1.9 mM |

The KP/RP threshold ratio is **2.4**, and the PV/VP ratio is **2.375**, calculated within this table. These are ratios of reported point thresholds, without recovered confidence intervals or assessor-level data. They are not receptor potency ratios, confirmed statistically significant differences, or sodium-reduction percentages. VP/PV show why residue counts alone cannot describe this reported threshold difference.

The exact broth composition, NaCl concentration, pH and panel size were not verified for these Table 4 tests. Generic formulation claims elsewhere in a patent do not supply assay conditions. The official EPO family text reproduces the same table; it is not an independent replication. Salger et al. [2] provide related peer-reviewed work and an accessible supplement listing KP and PK analytical parameters, but that supplement does not supply the sensory thresholds. The numerical claims above are therefore attributed specifically to the patent.

The source also contains two conflicting Pro–Pro rows and several “<” concentrations paired with descriptions of no activity. The raw extraction preserves these entries and flags both Pro–Pro rows. They are excluded from the salt-threshold comparison; the inequality signs are not silently reversed or converted into quantitative negative labels.

## 2. A negative benchmark label does not answer the enhancement question

The existing 580-record benchmark labels **VP as negative**, with the phenotype “sour, sweet” and a database-compilation attribution. The patent reports enhancement in broth. This is a newly documented endpoint mismatch in our collection, not proof that the original standalone-taste annotation is false. A peptide can lack an intrinsic salty taste while modifying an existing salty mixture.

RP is already benchmark-positive; KP and PV are absent. The [overlap table](../experiments/05-functional-assay-controls/results/published_sensory_benchmark_overlap.csv) retains these distinctions. No existing label was overwritten and no new prediction accuracy is claimed.

## 3. Direct paper data provide non-arginyl sensory comparators

We recovered the complete author supplement of Jünger et al. [3], including Table S5 and sensory methods. It contains **15 peptide records**, 14 numerical modulation thresholds and one dash. Six records include a salty modulation descriptor:

| Sequence | Reported modulation threshold, μM | Modulation descriptors |
| --- | ---: | --- |
| LDYY | 42 | Umami, salty |
| LPPP | 105 | Umami, salty |
| ALDPLPT | 125 | Umami, salty |
| PPPP | 193 | Salty |
| DTDEPN | 210 | Umami, salty |
| EEL | 229 | Salty |

These thresholds were measured in a **partial basic taste recombinate, pRec, at pH 5.4**, using duo-trio dilution tests and geometric averaging of participating assessors’ thresholds. The supplement describes a general pool of 27 assessors; the number contributing to each threshold is not separately given. The exact pRec composition refers to the main paper’s Table 2, which was not recovered here. We do not fill its NaCl field from another paper or from the patent.

None of these six sequences contains Arg or Lys. Their reported effects therefore argue against either residue being universally necessary for sensory salt enhancement. They do not establish an ENaC mechanism. Five sequences are absent from our benchmark; ALDPLPT is already present and explicitly linked to the 2022 work. This collection must not be advertised as a wholly independent held-out test set.

Intrinsic taste and modulation are separate columns. For example, LDYY is described as astringent/bitter on its own and umami/salty in the recombinate. A dash for DGML is retained as unreported modulation, not a measured zero; the other non-salt descriptors are not used as verified salt-negative controls. Water and recombinate thresholds do not define a same-matrix off-taste window.

## What to investigate next

1. **Prioritize RP/KP for the mechanistic comparison.** Reproduce the RP reference effect, then test KP in the same functional system with matched molar exposure, sodium, pH and counterions. Keep peptide-only, NaCl-only and mixture comparisons. A difference would test functional specificity, not whether KP can ever enhance perceived saltiness. AR/AK and RA/KA remain secondary comparisons with unverified lysine-peptide activity in the sources reviewed.
2. **Use LDYY and LPPP as source-backed sensory comparator candidates.** Their reported low-concentration modulation makes them more informative than selecting a new sequence solely from a docking score. Recover the exact matrix and experimental materials before treating these thresholds as reproducible formulation targets. EEL provides an acidic sequence and PPPP a non-arginyl proline oligomer for contrasting chemistry; their mechanisms remain open.
3. **Keep the screening target conditional.** Store standalone taste, salt modulation, receptor activation and dose/matrix separately. Do not train a single unconditional salty/non-salty classifier on these records or score off-target descriptors as negatives. Further computation is useful when it tests transfer between specified conditions; it cannot replace the missing functional and sensory measurements.

No GPU is required for the completed extraction, overlap analysis or within-source comparisons. Reproduce locally from the experiment folder with `python code/compare_published_sensory.py` (Python standard library only). Outputs go to `runs/published_sensory/`; reviewed outputs are in `results/`. The earlier executed notebook remains a frozen reproduction of its original inputs; this later evidence is linked separately.

## Sources

[1] Hofmann T, Salger M, Stark T. *Flavor compositions and screening methods for identifying the same*. [US20210000152A1](https://patents.google.com/patent/US20210000152A1/en), 7 January 2021. Table 4, printed p23/PDF p37; paragraph 0270. Primary PDF visually inspected. [Official EPO family text, Table 4](https://data.epo.org/publication-server/rest/v1.2/patents/EP3768092NWB1/document.html). Patent-reported data, not independent confirmation or a legal assessment.

[2] Salger M, Stark TD, Hofmann T. *Taste Modulating Peptides from Overfermented Cocoa Beans*. JAFC 67(15), 4311–4320 (2019). [DOI](https://doi.org/10.1021/acs.jafc.9b00905); [author supplement](https://doi.org/10.1021/acs.jafc.9b00905.s001). Abstract and complete supplement inspected; main full text not obtained.

[3] Jünger M, et al. *Sensoproteomic Discovery of Taste-Modulating Peptides and Taste Re-engineering of Soy Sauce*. JAFC 70(21), 6503–6518 (2022). [DOI](https://doi.org/10.1021/acs.jafc.2c01688); [author supplement](https://doi.org/10.1021/acs.jafc.2c01688.s001). Full supplement inspected, Table S5 p16 visually checked; methods pp2–4. Source supplement CC BY-NC 4.0; facts transcribed with attribution, original PDF/figures not redistributed. [Source hashes and access record](../experiments/05-functional-assay-controls/verification/PROLYL_SOURCES.json).
