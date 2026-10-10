#!/usr/bin/env python3
"""Check the exact Stage06 precursor values quoted by the manuscript.

This validates the canonical saved-output transcription included with the
source bundle. It does not re-fit the archived scalar predictor or replay the
neural experiment.
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "evidence" / "stage06_precursor_claims.json"


def close(actual, expected, tol=5e-12):
    if abs(float(actual) - expected) > tol:
        raise AssertionError(f"{actual!r} != {expected!r}")


data = json.loads(RECORD.read_text())
assert data["protocol_hash"] == "89d065fb5d81d316667742c587edd1cdcf0b69c80a1e3a0a5adf9e4dafe434e1"
assert data["claims"] == {
    "H6_B_between_task_predictive_phenotype": False,
    "H6_W_within_task_causal_state": False,
    "H6_A_optimizer_anisotropy": True,
}

anisotropy = data["H6_A"]
assert anisotropy["n"] == 30
assert anisotropy["median_ratio"]["statistic"] == "median"
close(anisotropy["median_ratio"]["estimate"], 90.92669839201187)
close(anisotropy["median_ratio"]["mean"], 86.2407346072064)
for actual, expected in zip(
    anisotropy["median_ratio"]["ci95"],
    [75.95081345371219, 94.57075139228826],
):
    close(actual, expected)
close(anisotropy["best_random_ratio"]["estimate"], 70.78910630476736)

prediction = data["H6_W"]["P_centered_future_prediction"]
for view, rich, zero in (
    ("A", 0.1574102493935951, -0.021774953217337988),
    ("B", 0.1568302744907795, -0.02255047352485532),
):
    close(prediction["vs_rich"][view]["improvement"]["mean"], rich)
    close(prediction["vs_zero"][view]["improvement"]["mean"], zero)

print("Stage06 precursor summary check passed: n=30; registered median=90.9267.")
