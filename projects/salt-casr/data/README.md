# Shared research data

[Project overview](../README.md) · [Experiments](../experiments/README.md)

This folder contains reusable **inputs**. Reviewed predictions, metrics, figures and chemical proposals stay under the experiment that produced them. No values or labels were changed during reorganization.

## CaSR chemistry

[casr/](casr/) supports [Experiment 01](../experiments/01-casr-models-and-docking/README.md).

| File | Role and limits |
| --- | --- |
| [casr_compounds_for_datawarrior.csv](casr/casr_compounds_for_datawarrior.csv) | Curated table-compound labels, structures where supported and reported HEK-293 activity categories; Amino et al. 2016 plus its erratum. The name is retained for provenance. |
| [narrative_inactive_annotations.csv](casr/narrative_inactive_annotations.csv) | Eighteen additional prose-only inactive annotations; assay identity/detection limit not established by those sentences. Not added as quantitative training labels. |
| [native_gamma_EVG.sdf](casr/native_gamma_EVG.sdf) | Reference ligand with experimentally observed coordinates and explicit linkage/stereochemistry. |
| [9J7I.cif](casr/9J7I.cif) | Deposited CaSR complex used for reference preparation. [PDB](https://www.rcsb.org/structure/9J7I). |
| [casr_binding_domain.pdb](casr/casr_binding_domain.pdb) | Retained prepared receptor-domain reference derived from the deposited structure; not an additional experiment. |
| [source_table_audit.json](casr/source_table_audit.json) | Comparison with 103 original article table rows and 102 unique labels. |
| [source_notes.json](casr/source_notes.json) | Source and chemical interpretation notes. |

The 94 reconstructed structures and 58 supported numerical/range observations are **derived outputs**, available in [Experiment 01 results](../experiments/01-casr-models-and-docking/results/). EC₅₀ is in μM where named as such; pEC₅₀ uses mol/L. Missing, reported inactive and censored values are distinct. Standard one-letter peptide strings cannot encode every γ linkage or non-standard monomer here.

Source: [Amino et al. 2016](https://doi.org/10.1248/cpb.c16-00293), [2017 erratum](https://doi.org/10.1248/cpb.c17-e6506); [Yamaguchi et al. 2025](https://doi.org/10.1038/s41598-025-87999-1). Source publications retain their terms; repository code licensing does not relicense them.

## Saltiness and assay conditions

[saltiness/](saltiness/) supports [Experiment 02](../experiments/02-sensory-source-transfer/README.md) and [Experiment 03](../experiments/03-assay-dose-response/README.md).

| File | Role and limits |
| --- | --- |
| [saltymeta_supplement.xlsx](saltiness/saltymeta_supplement.xlsx) | Unchanged SaltyMeta v1 source workbook: 580 peptides, 280 positive and 300 negative author labels. |
| [benchmark_records.csv](saltiness/benchmark_records.csv) | The 580-record curation used as an input to Experiment 03. It is byte-identical to Experiment 02's retained `results/curated_records.csv`, whose role is the output of curation. |
| [fixed_assay_panels.csv](saltiness/fixed_assay_panels.csv) | Eleven synthesized candidates in two published NaCl-enhancement panels; retains unresolved/non-significant outcomes separately. |
| [dose_response.csv](saltiness/dose_response.csv) | Eighteen published group means, including three zero-dose rows, from three peptides. Nominal mM doses, reported SD and the stock/final mixing ambiguity remain explicit. |
| [caption_mz.csv](saltiness/caption_mz.csv) | Eight published Figure S1 caption m/z values for a chemical-consistency check. Not raw mass-spectrometry measurements. |

SaltyMeta labels combine standalone saltiness and enhancement evidence. They are not receptor EC₅₀, and a negative does not establish absence of enhancement under every condition. Raw sensory scores from differently calibrated studies are not pooled.

Benchmark attribution: Chen W, Li W, He Y, Yang Y, [SaltyMeta v1](https://arxiv.org/abs/2609.16809v1), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). New experimental-table transcriptions are attributed to the sources in [Experiment 03](../experiments/03-assay-dose-response/SOURCE_MANIFEST.json) under their CC BY 4.0 terms. Full publisher papers/figures are not bundled.

## TRPV1 structure inputs

[trpv1/](trpv1/) supports [Experiment 04](../experiments/04-trpv1-membrane-access/README.md).

| File | Role |
| --- | --- |
| [trpv1_human.json](trpv1/trpv1_human.json), [trpv1_rat.json](trpv1/trpv1_rat.json), [trpv1_squirrel.json](trpv1/trpv1_squirrel.json) | Exact canonical-sequence snapshots for residue mapping; UniProtKB Q8NER1, O35433 and I3LZN5. [UniProt CC BY 4.0 terms](https://www.uniprot.org/help/license). |
| [INPUT_MANIFEST.json](trpv1/INPUT_MANIFEST.json) | SHA-256-verified original PDB/OPM input URLs and current cache destinations, with original execution paths retained for provenance. |
| [posthoc_alternative_evidence.csv](trpv1/posthoc_alternative_evidence.csv) | Separate hours-long cellular inhibitory-response evidence; not a sensory negative set or an acute gating measurement. |

Coordinate downloads go to `trpv1/cache/`, which is ignored by Git. Those coordinates were used in the completed analysis and are retrieved by Experiment 04's downloader. A changed upstream file produces an explicit version error. OPM planes are estimated hydrophobic-core boundaries; they are not measurements of peptide transport.

## Browse outputs

[CaSR results](../experiments/01-casr-models-and-docking/results/) · [Sensory benchmark results](../experiments/02-sensory-source-transfer/results/) · [Assay/dose results](../experiments/03-assay-dose-response/results/) · [Membrane-access results](../experiments/04-trpv1-membrane-access/results/)
