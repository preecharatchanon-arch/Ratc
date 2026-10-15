# 01 · CaSR models and docking — code

[Experiment report and commands](../README.md) · [Saved results](../results/README.md) · [Shared inputs](../../../data/README.md)

Run the report’s commands **from the experiment folder**, with its pinned requirements installed. Scripts resolve input paths from their own location and write to `../runs/latest/` relative to this `code/` folder. The executed notebook, where supplied, retains its original embedded source and input layout.

| File | Purpose |
| --- | --- |
| [benchmark.py](benchmark.py) | Reconstruct the activity series and evaluate fixed chemical-prediction baselines. |
| [chemistry.py](chemistry.py) | Build explicit chemical graphs, linkages and stereochemistry; imported by analyses. |
| [docking.py](docking.py) | Prepare ligands and run the selected Vina panel; requires prepared receptor and benchmark outputs. |
| [native_search_sensitivity.py](native_search_sensitivity.py) | Run the larger native-reference search after docking. |
| [notebook_analysis.py](notebook_analysis.py) | Notebook-stage audit, figures, docking interpretation and decision exports; stage commands require their preceding outputs. |
| [prepare_receptor.py](prepare_receptor.py) | Prepare the retained receptor-domain input as PDBQT using Meeko. |
| [project_paths.py](project_paths.py) | Resolve shared input data and the ignored local run folder. |
| [protocol.py](protocol.py) | Fixed chemical-analysis protocol and paths used by the benchmark. |
| [run_config.json](run_config.json) | Retained docking configuration; do not silently change it when reproducing results. |
