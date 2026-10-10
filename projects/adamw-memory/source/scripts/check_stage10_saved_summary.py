#!/usr/bin/env python3
"""Check Stage 10 saved per-seed summaries and the quoted horizon-decay values."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "evidence" / "stage10" / "original_compact"


def check_stat(stat: dict, label: str) -> None:
    values = np.asarray(stat["per_seed"], dtype=float)
    if len(values) != stat["n_seeds"] or abs(float(values.mean()) - stat["mean"]) > 1e-12:
        raise SystemExit(f"Stage 10 internal summary mismatch: {label}")


def main() -> None:
    report = json.loads((BASE / "analysis" / "SUMMARY.json").read_text(encoding="utf-8"))
    if not report["complete"] or report["completed_models"] != 8:
        raise SystemExit("Stage 10 archive is not the complete eight-model result")
    for dataset, panel in report["panels"].items():
        for rank, signs in panel["causal"].items():
            for sign, horizons in signs.items():
                for horizon, metrics in horizons.items():
                    for metric, stat in metrics.items():
                        check_stat(stat, f"{dataset}/rank{rank}/{sign}/h{horizon}/{metric}")
        for rank, metrics in panel["rank_curve"].items():
            for metric, stat in metrics.items():
                if stat is not None:
                    check_stat(stat, f"{dataset}/rank_curve/{rank}/{metric}")

    c10 = report["panels"]["CIFAR10"]
    observed = {
        "rank16_cosine_h1": c10["causal"]["16"]["paired"]["1"]["cosine"]["mean"],
        "rank16_cosine_h16": c10["causal"]["16"]["paired"]["16"]["cosine"]["mean"],
        "rank16_cosine_h64": c10["causal"]["16"]["paired"]["64"]["cosine"]["mean"],
        "rank64_cosine_h1": c10["causal"]["64"]["paired"]["1"]["cosine"]["mean"],
        "rank64_cosine_h16": c10["causal"]["64"]["paired"]["16"]["cosine"]["mean"],
        "rank64_cosine_h64": c10["causal"]["64"]["paired"]["64"]["cosine"]["mean"],
        "rank16_transfer_capture": c10["rank_curve"]["16"]["transfer_capture"]["mean"],
    }
    expected = {
        "rank16_cosine_h1": 0.9369814791632161,
        "rank16_cosine_h16": 0.3054325834672906,
        "rank16_cosine_h64": 0.18539713954574358,
        "rank64_cosine_h1": 0.9721797974839911,
        "rank64_cosine_h16": 0.4248002887888298,
        "rank64_cosine_h64": 0.1961626091929799,
        "rank16_transfer_capture": 0.4412013582347101,
    }
    for key, target in expected.items():
        if abs(observed[key] - target) > 1e-12:
            raise SystemExit(f"Stage 10 quoted value mismatch: {key}")

    unit_results = sorted(BASE.glob("units/*/result.json"))
    unit_operators = sorted(BASE.glob("units/*/operator.json"))
    if len(unit_results) != 8 or len(unit_operators) != 8:
        raise SystemExit("Stage 10 compact evidence should contain eight result/operator pairs")
    print(json.dumps({"complete_models": 8, "cifar10": observed, "unit_result_files": 8}, indent=2))


if __name__ == "__main__":
    main()
