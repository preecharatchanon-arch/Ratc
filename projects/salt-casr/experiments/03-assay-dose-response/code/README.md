# 03 · Assay conditions and dose — code

[Experiment report and commands](../README.md) · [Saved results](../results/README.md) · [Shared inputs](../../../data/README.md)

Run the report’s commands **from the experiment folder**, with its pinned requirements installed. Scripts resolve input paths from their own location and write to `../runs/latest/` relative to this `code/` folder. The executed notebook, where supplied, retains its original embedded source and input layout.

| File | Purpose |
| --- | --- |
| [analyse_conditions.py](analyse_conditions.py) | Run the fixed candidate-panel, dose-ranking and chemical mass analyses. |
| [baseline.py](baseline.py) | Shared peptide features and fixed model definitions; imported by the assay analysis. |
| [project_paths.py](project_paths.py) | Resolve shared input data and the ignored local run folder. |
