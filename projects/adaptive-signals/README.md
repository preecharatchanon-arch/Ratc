# Adaptive Signals · SUMO Stage 2

**Archived prototype · October 2026**

I built this Stage 2 prototype to test how signal controllers respond when demand changes across neighbouring intersections. The original dark-blue Colab viewer shows vehicles, signal phases and approach queues from a running SUMO simulation on a synthetic nine-intersection grid.

**[Open the original notebook in Google Colab](https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/projects/adaptive-signals/AdaptiveSignals_Stage2_Live_Colab.ipynb)** · [View the notebook on GitHub](AdaptiveSignals_Stage2_Live_Colab.ipynb)

## Demo video

**[Watch the 19-second SUMO recording](sumo-stage2-comparison.mp4)**

I reran the notebook's directional-switch demonstration on Eclipse SUMO 1.25.0. All three controllers received the same **443 vehicle requests** on the same synthetic nine-intersection grid. The seed was **22777**, the demand multiplier was **×1.0**, and the observation cutoff was **600 simulated seconds**. The recording shows the resulting vehicle trajectories and signal states with accelerated playback.

| Signal controller | Mean system time per request | Trips completed by 600 s |
| --- | ---: | ---: |
| Fixed timing tuned on development runs | 344.7 s | 228 / 443 |
| Stage 1 coordinated controller | 304.2 s | 303 / 443 |
| Discharge lookahead | 273.1 s | 340 / 443 |

Mean system time includes entry wait and the elapsed time of unfinished trips at the cutoff. The demo uses one synthetic demand trace and perfect simulated detector counts. All three reruns passed the notebook's vehicle accounting, signal-transition and metric checks. All 10 bundled tests passed.

To reproduce the comparison, run the first notebook cell and then run `python make_demo.py` in the extracted project directory. The script runs all three controllers and writes a replay GIF under `runs/demo/`.

## Run the viewer

1. Open the notebook in a Colab CPU runtime and run the first two code cells in order.
2. In the second cell's output, click **Start / reset run**. Keep the runtime connected while using the viewer.
3. Use the same demand pattern, load, and seed to compare controllers. The viewer also supports pausing, stepping one second at a time, and adjusting simulated detector errors.

The notebook bundles the C++17 controllers, Python runner, viewer and tests. The first cell installs SUMO 1.25.0 and compiles the controllers with `g++`. The optional third cell displays the saved summary and can rerun or export the benchmark.

## Experiment scope

The archived campaign contains 48 development runs and 284 evaluation runs. It compares fixed timing, native SUMO actuation and adaptive C++ heuristics using mean system time per requested vehicle within a fixed simulation horizon. The metric counts unfinished trips and requests still waiting to enter.

For example, on the archived balanced-demand case at ×0.6 load, the saved means were **442.1 s/request** for tuned fixed timing, **361.7** for native actuation and **241.7** for the C++ discharge controller. These values describe a synthetic scenario and its recorded seeds. The notebook contains the other cases and the checks for trip accounting and signal clearance.
