# 02 · Sensory source transfer — code

[Experiment report and commands](../README.md) · [Saved results](../results/README.md) · [Shared inputs](../../../data/README.md)

Run the report’s commands **from the experiment folder**, with its pinned requirements installed. Scripts resolve input paths from their own location and write to `../runs/latest/` relative to this `code/` folder. The executed notebook, where supplied, retains its original embedded source and input layout.

| File | Purpose |
| --- | --- |
| [analyse.py](analyse.py) | Curate the workbook, construct fixed splits and fit the four primary baselines. |
| [diagnose.py](diagnose.py) | Run the separately declared post-hoc matched-fold and reference-parsing controls. |
| [project_paths.py](project_paths.py) | Resolve shared input data and the ignored local run folder. |
| [report.py](report.py) | Recompute saved metrics, verify split/prediction consistency and draw the results figure. |
