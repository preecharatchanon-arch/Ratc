# 05 · Functional assay controls — code

[Experiment and commands](../README.md) · [Results](../results/README.md) · [Input tables](../../../data/functional/README.md)

[analyse_functional.py](analyse_functional.py) reads the six attributed input tables, retains separate experimental cohorts, calculates descriptive contrasts, checks count/percentage rounding and draws the summary figure. It performs no model fitting or new statistical test. Run it from the experiment folder after installing the requirements; output goes to `../runs/latest/` relative to this folder.

[compare_control_panel.py](compare_control_panel.py) is a separate RDKit calculation for the [arginyl follow-up](../../../docs/ARGINYL_STARTING_POINT.md). It uses `../requirements_control_selection.txt` and writes to `../runs/control_selection/`. It proposes interpretable chemical controls without predicting activity.

The [self-contained notebook](../Arginyl_Functional_Controls.ipynb) orchestrates both scripts in an isolated CPU worker using `../requirements_notebook.txt`. It adds reference-table checks, chemical-identity checks, structure drawings, a unit calculator and a run ZIP export.
