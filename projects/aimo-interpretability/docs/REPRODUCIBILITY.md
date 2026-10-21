# What can be reproduced from this repository?

The project publishes both its result tables and the derived numerical inputs used to train the small predictors. Reproducing a predictor is distinct from repeating a language model's GPU calculations.

| Stage | Available here? | What the check establishes |
| --- | --- | --- |
| Recalculate metrics from stored predictions | Yes: `verify_results.py`, predictions, labels and family partitions | Arithmetic consistency of the reported counts and metrics; family separation and file integrity. |
| Refit every small predictor | Yes: `reproduce_readouts.py` and `feature_matrices.json` | Whether training-fold-only scaling and the declared fixed classifier reproduce the stored probabilities and classifications. |
| Regenerate the text, token probabilities and internal vectors | No: the full original problem/trace/measurement files are omitted | This publication alone cannot independently repeat the LLM measurement stage. |
| Verify generalization to new families or private competition cases | No new measurements claimed | Public development performance does not establish private-test performance. |

## Quick arithmetic check

From the repository root, Python 3.10+ with its standard library is enough:

```sh
python projects/aimo-interpretability/verify_results.py
```

This checks hashes, row identities, stored family partitions, decision thresholds, overall/per-model classification metrics and paired gains/losses. It does not fit a model.

## Refit the predictors on CPU

Use Python 3.11+ and install the two recorded dependencies in your chosen environment:

```sh
python -m pip install -r projects/aimo-interpretability/requirements-replay.txt
python projects/aimo-interpretability/reproduce_readouts.py
```

The script uses NumPy 2.3.5 and scikit-learn 1.8.0. It independently implements the historical predictor fit with `StandardScaler` and `LogisticRegression` in a pipeline. For each of 20 families, it fits scaling and the classifier only on the other families. The constant reference always predicts robust. No model inference, network access or GPU is used by the reproduction script; installing dependencies is a separate setup action.

On 21 October 2026 this CPU reproduction matched all eight methods' classifications and all 43 saved probability scores per method within a maximum difference of **1.11e−16**. The script permits absolute probability differences up to 1e−8 for numerical-library variation while requiring identical classifications. It checks accuracy, balanced accuracy, AUROC and Brier loss against the saved summary. These terms are defined in [Methods](METHODS.md#how-the-predictions-are-evaluated).

## What is in the feature file?

`results/geometry/feature_matrices.json` contains 43 rows. Each has an opaque case identifier, model identifier, family identifier and numerical input vectors for all eight methods. The file includes the ordered column names and dimensions: constant 1, model identity 4, text/bookkeeping 24, overall probabilities 39, word-disturbance control 45, uncertainty changes 43, internal-vector shape 43, and combined additions 47.

These are derived measurements, not regenerated model outputs. They contain no original problem text, generated reasoning text, token IDs or full activation arrays. Labels are taken from the already published saved-prediction file. The fitting script checks that its row order and case/model/family identities match those records.

The matrices were exported from the original feature-building function after verifying the historical input archive, profile identities and all 43 geometry cache records. The cache checks include recomputation of shape features from the saved numerical matrices. Hashes are recorded in [provenance.json](../results/geometry/provenance.json).

## Historical environment and limits

[measurement_environment.json](../results/geometry/measurement_environment.json) preserves the original run's recorded Python, PyTorch, Transformers, NumPy, sklearn and A100 environment, plus the current CPU-replay versions. It is a record of the completed run, not a new hardware test.

Refitting the predictors cannot detect every possible upstream measurement error or establish that a robustness label is semantically correct. The original extraction source and native-reference checks were audited earlier; the large raw records are not included here. Neither reproduction command reruns the family bootstrap, corrects for earlier hypothesis selection, or turns previously inspected public development families into a new confirmation set.
