"""Verify the published fixed predictions and result tables; no GPU or refit."""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def close(actual, expected, label):
    if isinstance(expected, float):
        if not math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-11):
            raise ValueError(f"Metric mismatch: {label}: {actual} != {expected}")
    elif actual != expected:
        raise ValueError(f"Value mismatch: {label}: {actual} != {expected}")


def metrics(rows, arm):
    y = [int(r["label"]) for r in rows]
    s = [float(r["scores"][arm]) for r in rows]
    p = [v >= .5 for v in s]
    positives, negatives = sum(y), len(y) - sum(y)
    tp = sum(a and b for a, b in zip(p, y))
    tn = sum(not a and not b for a, b in zip(p, y))
    auc = None
    if positives and negatives:
        # Average ranks handle ties; Mann-Whitney AUROC, independent of sklearn.
        ordered = sorted(zip(s, y))
        rank_sum, i = 0., 0
        while i < len(ordered):
            j = i + 1
            while j < len(ordered) and ordered[j][0] == ordered[i][0]:
                j += 1
            rank_sum += ((i + 1 + j) / 2) * sum(v[1] for v in ordered[i:j])
            i = j
        auc = (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)
    nr = tn / negatives if negatives else None
    rr = tp / positives if positives else None
    return dict(n=len(y), correct=tp + tn, accuracy=(tp + tn) / len(y),
                balanced_accuracy=(nr + rr) / 2 if nr is not None and rr is not None else None,
                nonrobust_recall=nr, robust_recall=rr, auroc=auc,
                brier=sum((a - b) ** 2 for a, b in zip(s, y)) / len(y),
                true_robust=tp, true_nonrobust=tn,
                false_robust=negatives - tn, false_nonrobust=positives - tp)


def verify():
    provenance = read("results/geometry/provenance.json")
    for relative, expected in provenance["files"].items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("Manifest path escapes project")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        close(actual, expected, relative)
    summary = read("results/geometry/summary.json")
    rows = read("results/geometry/held_out_predictions.json")
    folds = read("results/geometry/family_folds.json")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate case")
    close(len(rows), 43, "cases")
    close(len({r["family"] for r in rows}), 20, "families")
    close(sum(r["label"] for r in rows), 31, "robust cases")
    arms = set(summary["metrics"])
    for r in rows:
        if type(r["label"]) is not bool or set(r["scores"]) != arms or set(r["predictions"]) != arms:
            raise ValueError("Invalid row schema")
        for arm, score in r["scores"].items():
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Invalid probability")
            if type(r["predictions"][arm]) is not bool:
                raise ValueError("Prediction is not bool")
            close(r["predictions"][arm], score >= .5, r["id"] + ":" + arm)
    for arm in sorted(arms):
        for key, expected in summary["metrics"][arm].items():
            close(metrics(rows, arm)[key], expected, arm + ":" + key)
        for model, table in summary["by_model"].items():
            subset = [r for r in rows if r["model"] == model]
            for key, expected in table[arm].items():
                close(metrics(subset, arm)[key], expected, model + ":" + arm + ":" + key)
    covered = Counter()
    for fold in folds:
        train, test = fold["train_indices"], fold["test_indices"]
        if len(set(train)) != len(train) or len(set(test)) != len(test):
            raise ValueError("Duplicate fold indices")
        if set(train) & set(test) or set(train) | set(test) != set(range(len(rows))):
            raise ValueError("Invalid partition")
        if {rows[i]["family"] for i in test} != {fold["family"]}:
            raise ValueError("Wrong held-out family")
        if fold["family"] in {rows[i]["family"] for i in train}:
            raise ValueError("Family leakage")
        covered.update(test)
    close(dict(covered), {i: 1 for i in range(len(rows))}, "fold coverage")
    for arm, expected in summary["comparisons"].items():
        gain = lost = 0
        by_family = defaultdict(int)
        sizes = Counter(r["family"] for r in rows)
        for r in rows:
            c = int(r["predictions"]["geometry"] == r["label"])
            b = int(r["predictions"][arm] == r["label"])
            gain += c and not b
            lost += b and not c
            by_family[r["family"]] += c - b
        values = dict(net_correct=gain - lost, accuracy_gain=(gain - lost) / len(rows),
                      candidate_only_correct=gain, reference_only_correct=lost,
                      benefiting_families=sum(v > 0 for v in by_family.values()),
                      harmed_families=sum(v < 0 for v in by_family.values()),
                      minimum_gain_after_removing_one_family=min(
                          (gain - lost - delta) / (len(rows) - sizes[f])
                          for f, delta in by_family.items()))
        for key, actual in values.items():
            close(actual, expected[key], arm + ":" + key)
    close(summary["status"], "NO_CLEAR_INCREMENTAL_GAIN", "status")
    close(summary["decision"]["passed"], False, "promotion decision")
    print("Verified hashes, 43 cases, 20 family-isolated folds, all arm/model metrics and paired counts.")
    print("Geometry: 32/43; aggregate confidence: 33/43; candidate-only gains: 0; losses: 1.")
    print("Saved-prediction verification only; no GPU forwards, refits or bootstrap rerun.")


if __name__ == "__main__":
    verify()
