"""Refit every family-excluded predictor from published derived measurements."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def reproduce():
    import numpy as np
    import sklearn
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, brier_score_loss, roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    provenance = load("results/geometry/provenance.json")
    for path, expected in provenance["files"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise ValueError("Published measurement/source bytes changed: " + path)
    data = load("results/geometry/feature_matrices.json")
    reference = load("results/geometry/held_out_predictions.json")
    summary = load("results/geometry/summary.json")
    protocol = load("source/geometry/geometry_protocol.json")
    folds = load("results/geometry/family_folds.json")
    rows = data["rows"]
    if len(rows) != 43 or [r["id"] for r in rows] != [r["id"] for r in reference]:
        raise ValueError("Case ordering or coverage mismatch")
    if set(data["feature_dimensions"]) != set(summary["metrics"]):
        raise ValueError("Missing method")
    for row, ref in zip(rows, reference):
        if any(row[k] != ref[k] for k in ("id", "model", "family")):
            raise ValueError("Case metadata mismatch")
    y = np.array([r["label"] for r in reference], dtype=int)
    groups = np.array([r["family"] for r in rows])
    if len(set(groups)) != 20:
        raise ValueError("Family coverage mismatch")
    for fold in folds:
        expected_train = np.flatnonzero(groups != fold["family"]).tolist()
        expected_test = np.flatnonzero(groups == fold["family"]).tolist()
        if fold["train_indices"] != expected_train or fold["test_indices"] != expected_test:
            raise ValueError("Stored fold differs from whole-family exclusion")
    settings = protocol["readout"]
    if settings["class_weight"] is not None or settings["threshold"] != .5:
        raise ValueError("Unsupported historical fitting policy")
    max_error = 0.
    for arm, dimension in data["feature_dimensions"].items():
        x = np.array([r["features"][arm] for r in rows], dtype=float)
        if x.shape != (43, dimension) or not np.isfinite(x).all():
            raise ValueError("Invalid derived measurements: " + arm)
        predicted = np.full(len(y), np.nan)
        for family in sorted(set(groups)):
            train, test = groups != family, groups == family
            if arm == "always_robust":
                predicted[test] = 1.
            elif len(set(y[train])) == 1:
                predicted[test] = (y[train].sum() + .5) / (train.sum() + 1)
            else:
                # Separate implementation from the historical manual scaler.
                # Fit every transform inside this family's training partition.
                pipe = make_pipeline(StandardScaler(), LogisticRegression(
                    C=settings["C"], solver=settings["solver"], max_iter=5000,
                    random_state=settings["seed"], class_weight=None))
                pipe.fit(x[train], y[train])
                predicted[test] = pipe.predict_proba(x[test])[:, 1]
        if not np.isfinite(predicted).all():
            raise ValueError("Incomplete predictions")
        saved = np.array([r["scores"][arm] for r in reference])
        error = float(np.max(np.abs(predicted - saved)))
        max_error = max(max_error, error)
        np.testing.assert_allclose(predicted, saved, atol=1e-8, rtol=0,
                                   err_msg="Refitted probabilities differ: " + arm)
        classified = predicted >= .5
        if not np.array_equal(classified, np.array([r["predictions"][arm] for r in reference])):
            raise ValueError("Refitted classifications differ: " + arm)
        observed = {"accuracy": accuracy_score(y, classified),
                    "balanced_accuracy": balanced_accuracy_score(y, classified),
                    "brier": brier_score_loss(y, predicted),
                    "auroc": roc_auc_score(y, predicted)}
        for key, value in observed.items():
            np.testing.assert_allclose(value, summary["metrics"][arm][key], atol=1e-8, rtol=0)
        print(f"{arm}: {int(sum(classified == y))}/43; max probability difference {error:.3g}")
    print(f"Reproduced all 8 methods across 20 excluded families; largest score difference {max_error:.3g}.")
    print(f"CPU environment: NumPy {np.__version__}; scikit-learn {sklearn.__version__}.")
    print("This refits the small predictors; it does not regenerate LLM measurements or rerun the bootstrap.")


if __name__ == "__main__":
    reproduce()
