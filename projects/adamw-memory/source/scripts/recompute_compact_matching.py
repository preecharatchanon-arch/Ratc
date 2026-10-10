#!/usr/bin/env python3
"""Recompute the Stage 12/13 matching results from included primary response arrays."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
HORIZONS = (1, 4, 16, 64)


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as payload:
        return {key: payload[key].copy() for key in payload.files}


def centered(value: np.ndarray) -> np.ndarray:
    value = np.asarray(value, dtype=np.float64)
    return value - value.mean(axis=1, keepdims=True)


def effect(folder: Path, stem: str, horizon: int) -> np.ndarray:
    plus = load_npz(folder / f"branch_{stem}_plus.npz")[f"h{horizon}"]
    minus = load_npz(folder / f"branch_{stem}_minus.npz")[f"h{horizon}"]
    return centered((plus.astype(np.float64) - minus.astype(np.float64)) / 2.0)


def rel_error(full: np.ndarray, projected: np.ndarray) -> float:
    return float(np.linalg.norm(full - projected) / np.linalg.norm(full))


def cosine(full: np.ndarray, projected: np.ndarray) -> float:
    denominator = np.linalg.norm(full) * np.linalg.norm(projected)
    return float(np.vdot(full, projected).real / denominator) if denominator else float("nan")


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def recompute_stage12(base: Path) -> tuple[list[dict], list[dict]]:
    responses, captures = [], []
    for unit in sorted((base / "units").iterdir()):
        if not unit.is_dir():
            continue
        dataset, seed = unit.name.rsplit("_", 1)
        saved = json.loads((unit / "RESULT.json").read_text(encoding="utf-8"))
        for path_index in (0, 1):
            folder = unit / f"path{path_index}"
            for rank in (16, 64):
                for fit_horizon, stem in ((1, f"immediate{rank}"), (16, f"horizon{rank}")):
                    for horizon in HORIZONS:
                        full = effect(folder, "full", horizon)
                        projected = effect(folder, stem, horizon)
                        responses.append(
                            {
                                "stage": 12,
                                "dataset": dataset,
                                "seed": int(seed),
                                "path": path_index,
                                "fit_horizon": fit_horizon,
                                "fit_n": 64,
                                "rank": rank,
                                "evaluation_horizon": horizon,
                                "relative_error": rel_error(full, projected),
                                "cosine": cosine(full, projected),
                                "full_rms": float(np.linalg.norm(full) / math.sqrt(full.size)),
                            }
                        )
                for evaluation_horizon in (1, 16):
                    payload = load_npz(folder / f"capture_h{evaluation_horizon}.npz")
                    trace = float(payload["trace_squared_norms"].mean())
                    for fit_horizon, action_name, stem in (
                        (1, "immediate_action", f"immediate{rank}"),
                        (16, "horizon_action", f"horizon{rank}"),
                    ):
                        numerator = float(np.square(payload[action_name][:, :rank].astype(np.float64)).sum())
                        estimate = numerator / trace
                        archived = saved["paths"][str(path_index)]["capture"][str(evaluation_horizon)][stem]["capture_estimate"]
                        if abs(estimate - archived) > 2e-7:
                            raise SystemExit(f"Stage 12 capture mismatch: {unit.name} path{path_index} {stem}@{evaluation_horizon}")
                        captures.append(
                            {
                                "stage": 12,
                                "dataset": dataset,
                                "seed": int(seed),
                                "path": path_index,
                                "fit_horizon": fit_horizon,
                                "fit_n": 64,
                                "rank": rank,
                                "evaluation_horizon": evaluation_horizon,
                                "capture": estimate,
                            }
                        )
    return responses, captures


def recompute_stage13(base: Path) -> tuple[list[dict], list[dict]]:
    responses, captures = [], []
    for unit in sorted((base / "units").iterdir()):
        if not unit.is_dir():
            continue
        dataset, seed = unit.name.rsplit("_", 1)
        saved = json.loads((unit / "RESULT.json").read_text(encoding="utf-8"))
        for path_index in (0, 1):
            folder = unit / f"path{path_index}"
            for rank in (16, 64):
                for fit_horizon in (1, 16):
                    stem = f"h{fit_horizon}_n256_r{rank}"
                    for horizon in HORIZONS:
                        full = effect(folder, "full", horizon)
                        projected = effect(folder, stem, horizon)
                        error = rel_error(full, projected)
                        archived = saved["paths"][str(path_index)]["comparisons"][f"{stem}@{horizon}"]["projection_error"]
                        if abs(error - archived) > 1e-10:
                            raise SystemExit(f"Stage 13 response mismatch: {unit.name} path{path_index} {stem}@{horizon}")
                        responses.append(
                            {
                                "stage": 13,
                                "dataset": dataset,
                                "seed": int(seed),
                                "path": path_index,
                                "fit_horizon": fit_horizon,
                                "fit_n": 256,
                                "rank": rank,
                                "evaluation_horizon": horizon,
                                "relative_error": error,
                                "cosine": cosine(full, projected),
                                "full_rms": float(np.linalg.norm(full) / math.sqrt(full.size)),
                            }
                        )
                    for evaluation_horizon in (1, 16):
                        payload = load_npz(
                            unit / f"capture_fitH{fit_horizon}_n256_path{path_index}_h{evaluation_horizon}.npz"
                        )
                        numerator = float(payload["column_squared_norms"][:rank].sum())
                        estimate = numerator / float(payload["trace_squared_norms"].mean())
                        archived = saved["paths"][str(path_index)]["capture"][f"{stem}@{evaluation_horizon}"]["capture"]
                        if abs(estimate - archived) > 1e-10:
                            raise SystemExit(f"Stage 13 capture mismatch: {unit.name} path{path_index} {stem}@{evaluation_horizon}")
                        captures.append(
                            {
                                "stage": 13,
                                "dataset": dataset,
                                "seed": int(seed),
                                "path": path_index,
                                "fit_horizon": fit_horizon,
                                "fit_n": 256,
                                "rank": rank,
                                "evaluation_horizon": evaluation_horizon,
                                "capture": estimate,
                            }
                        )
    return responses, captures


def aggregate(responses: list[dict], captures: list[dict]) -> dict:
    headline = {}
    for stage, dataset in ((12, "CIFAR10"), (13, "CIFAR10"), (13, "CIFAR100")):
        headline[f"stage{stage}_{dataset}"] = {}
        for path_index in (0, 1):
            rows = [
                r for r in responses
                if r["stage"] == stage and r["dataset"] == dataset and r["path"] == path_index
                and r["rank"] == 16 and r["evaluation_horizon"] == 16
            ]
            headline[f"stage{stage}_{dataset}"][f"path{path_index}"] = {
                "immediate_mean_error": float(np.mean([r["relative_error"] for r in rows if r["fit_horizon"] == 1])),
                "matched_mean_error": float(np.mean([r["relative_error"] for r in rows if r["fit_horizon"] == 16])),
                "independent_histories": len({r["seed"] for r in rows}),
            }
    for dataset in ("CIFAR10", "CIFAR100"):
        key = f"stage13_{dataset}"
        for path_index in (0, 1):
            rows = [
                r for r in captures
                if r["stage"] == 13 and r["dataset"] == dataset and r["path"] == path_index
                and r["fit_horizon"] == 16 and r["rank"] == 16 and r["evaluation_horizon"] == 16
            ]
            headline[key][f"path{path_index}"]["matched_rank16_capture_mean"] = float(np.mean([r["capture"] for r in rows]))
    return headline


def assert_headline(summary: dict) -> None:
    expected = {
        ("stage12_CIFAR10", "path0", "immediate_mean_error"): 1.3517466752649232,
        ("stage12_CIFAR10", "path0", "matched_mean_error"): 0.8161364168605018,
        ("stage12_CIFAR10", "path1", "immediate_mean_error"): 1.34826959481306,
        ("stage12_CIFAR10", "path1", "matched_mean_error"): 0.9086758074305816,
        ("stage13_CIFAR10", "path0", "immediate_mean_error"): 1.0486871596623848,
        ("stage13_CIFAR10", "path0", "matched_mean_error"): 0.5939929000313525,
        ("stage13_CIFAR10", "path1", "immediate_mean_error"): 0.9370727703010159,
        ("stage13_CIFAR10", "path1", "matched_mean_error"): 0.99324094400212,
        ("stage13_CIFAR100", "path0", "immediate_mean_error"): 0.9651444625695911,
        ("stage13_CIFAR100", "path0", "matched_mean_error"): 0.7973910814782694,
        ("stage13_CIFAR100", "path1", "immediate_mean_error"): 0.9881362493591902,
        ("stage13_CIFAR100", "path1", "matched_mean_error"): 0.995286608696827,
    }
    for keys, target in expected.items():
        actual = summary[keys[0]][keys[1]][keys[2]]
        if abs(actual - target) > 5e-10:
            raise SystemExit(f"Headline mismatch for {keys}: {actual} != {target}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("regenerated_compact_matching"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    stage12 = ROOT / "evidence" / "stage12" / "original_compact"
    stage13 = ROOT / "evidence" / "stage13" / "original_compact"
    responses12, captures12 = recompute_stage12(stage12)
    responses13, captures13 = recompute_stage13(stage13)
    responses = responses12 + responses13
    captures = captures12 + captures13
    summary = aggregate(responses, captures)
    assert_headline(summary)
    write_csv(args.out / "responses.csv", responses)
    write_csv(args.out / "captures.csv", captures)
    (args.out / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
