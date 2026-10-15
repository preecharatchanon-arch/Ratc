# 04 · TRPV1 membrane access — code

[Experiment report and commands](../README.md) · [Saved results](../results/README.md) · [Shared inputs](../../../data/README.md)

Run the report’s commands **from the experiment folder**, with its pinned requirements installed. Scripts resolve input paths from their own location and write to `../runs/latest/` relative to this `code/` folder. The executed notebook, where supplied, retains its original embedded source and input layout.

| File | Purpose |
| --- | --- |
| [analyse_access.py](analyse_access.py) | Align structures, map contacts and calculate membrane depths and ligand distances. |
| [download_inputs.py](download_inputs.py) | Retrieve versioned coordinates and copy sequence snapshots; verify input SHA-256 hashes. |
| [project_paths.py](project_paths.py) | Resolve shared input data and the ignored local run folder. |
| [verify_sources.py](verify_sources.py) | Independently check deposited-coordinate lipid distances; inspect the source paragraph when its optional local text is available. |
