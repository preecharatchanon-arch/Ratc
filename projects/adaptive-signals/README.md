# Adaptive Signals · SUMO Stage 2

This October 2026 prototype tests adaptive traffic signals on a synthetic nine-intersection grid. It preserves the original dark-blue viewer that opens inside the Colab notebook. The viewer draws vehicle positions, signal phases, and queue estimates from a live SUMO simulation. The notebook includes the C++17 control code, Python runner, web viewer, tests, and archived benchmark summaries.

**[Open the original notebook in Google Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/adaptive-signals/AdaptiveSignals_Stage2_Live_Colab.ipynb)** · [View the notebook on GitHub](AdaptiveSignals_Stage2_Live_Colab.ipynb)

## Run the viewer

1. Open the notebook in a Colab CPU runtime and run the first two code cells in order.
2. In the second cell's output, click **Start / reset run**. Keep the runtime connected while using the viewer.
3. Use the same demand pattern, load, and seed to compare controllers. The viewer also supports pausing, stepping one second at a time, and adjusting simulated detector errors.

The first cell installs the pinned SUMO 1.25.0 packages and compiles the controller with `g++`. The optional third cell displays the archived summary and can reproduce or export the benchmark.

## Experiment scope

The archived campaign contains 48 development runs and 284 evaluation runs. It compares fixed timing, native SUMO actuation, and adaptive C++ heuristics using finite-horizon mean system time per requested vehicle, including unfinished trips. The experiment uses simulated demand and detectors on a synthetic grid.
