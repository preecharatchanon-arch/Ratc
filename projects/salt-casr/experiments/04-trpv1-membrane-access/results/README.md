# 04 · TRPV1 membrane access — results

[Experiment report](../README.md) · [Code](../code/README.md) · [Shared inputs](../../../data/README.md)

These files are the reviewed result snapshot. New local runs write to `../runs/latest/`, leaving this evidence intact. Read the report before interpreting a score or label.

## Key outputs

| File | What to inspect |
| --- | --- |
| [membrane_site_comparison.png](membrane_site_comparison.png) | Start here: contact-site membrane depth and the observed DkTx comparator. |
| [published_contact_depths.csv](published_contact_depths.csv) | Mapped reported contacts, coordinates, boundaries and depth classifications. |
| [canonical_alignment.csv](canonical_alignment.csv) | Species/construct mapping; do not transfer residue numbers directly. |
| [human_lipid_and_ligand_distances.csv](human_lipid_and_ligand_distances.csv) | Distances from the contacts to resolved lipid and other ligand atoms. |
| [independent_lipid_distance_check.csv](independent_lipid_distance_check.csv) | Separate original-coordinate calculation of the four human lipid distances. |
| [membrane_boundary_sensitivity.csv](membrane_boundary_sensitivity.csv) | Geometry under the declared centre/half-thickness perturbations. |
| [experimental_DkTx_contact_depths.csv](experimental_DkTx_contact_depths.csv) | Actual toxin–channel contact depths at the declared distance cutoff. |
| [hotspot_distance_to_DkTx.csv](hotspot_distance_to_DkTx.csv) | Distances from the mapped four hotspots to bound DkTx. |
| [source_peptide_descriptors.csv](source_peptide_descriptors.csv) | Free-form descriptors; not membrane-permeability predictions. |
| [coordinate_geometry_check.csv](coordinate_geometry_check.csv) | Rigid-alignment check between deposited and OPM coordinates. |
| [verification.json](verification.json) | Source/mapping and independent-distance checks. |
| [run_receipt.json](run_receipt.json) | Input versions, geometry summary and execution record. |

## Other retained files

Remaining JSON, CSV, structure and figure files support the calculations above. Original logs and full run payloads, where supplied, remain in the [archives](../../../archives/README.md). Sources, units and unresolved evidence are explained in the experiment report.
