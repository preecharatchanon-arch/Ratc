# Research status — 15 October 2026

[Project overview](../README.md)

The four published experiments are complete. Their outputs answer different questions and should not be merged into a single "saltiness score".

| Experiment | Supported conclusion | Limit that determines the next decision |
| --- | --- | --- |
| [01 · CaSR](../experiments/01-casr-models-and-docking/README.md) | Best observed held-family MAE 0.7989 pEC₅₀ units, equivalent to 6.2939-fold geometric absolute error. Reference top-pose RMSD 4.7803 Å; larger-search top pose 4.4356 Å, closest returned pose 2.4331 Å. | One compiled activity series and weak pose ranking do not support confident selection of new taste enhancers. CaSR activity does not establish increased saltiness. |
| [02 · Source transfer](../experiments/02-sensory-source-transfer/README.md) | Fixed Extra Trees mean AUC on the sensory-tagged subset is 0.686 under random partitions and 0.286 under reference+sequence holdouts. | This concerns one fixed baseline; composition logistic regression is about 0.484 under the same reference regime. Source metadata and endpoint mixtures limit interpretation. |
| [03 · Conditions and dose](../experiments/03-assay-dose-response/README.md) | Published enhancement evidence exists for benchmark-negative NGYDMR under different conditions; the preferred peptide changes with dose. All four frozen baselines retrieve one known enhancer among their top three in the six-candidate panel. | Preserve assay context and unresolved outcomes. The small selected panels do not establish population accuracy or verified sodium replacement. |
| [04 · Membrane access](../experiments/04-trpv1-membrane-access/README.md) | The reported TRPV1 contact set sits in the membrane/cytoplasmic region; lipid neighbours and actual DkTx contacts provide structural context. | Geometry raises an access question, not proof of absent binding or absent sensory activity. Rapid functional evidence is needed before screening at that site. |

The immediate research priority is to connect a reproducible enhancement window in a defined NaCl system with an appropriately controlled functional assay. Additional docking sweeps or a more complex model on the same mixed labels are not justified by these results alone. The reports describe possible follow-ups; **those follow-ups have not been performed**.

No synthesis, receptor-response measurement, sensory experiment, novel effective compound or food-safety determination is claimed as our own result. Computational reanalysis of published data is distinguished from the original authors' experiments.

## Reading order

Read the project overview and the report relevant to the question. Inspect `results/` for the completed evidence, `code/` for local reproduction, and the shared [data guide](../data/README.md) before interpreting a label or unit. The original executed notebooks carry their reviewed release code and inputs unchanged. Repository scripts have path-only updates for the organized layout and save new outputs under `runs/latest/`.

## Scope of this release

This index covers the four experiments present in this repository. Earlier ENaC stage notebooks discussed during the project are not included as additional numbered experiments here. Historical CaSR reference docking files and the two originally published run packages are listed in [archives](../archives/README.md).
