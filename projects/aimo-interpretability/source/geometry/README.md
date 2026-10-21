# Historical source: measuring the shape of internal model vectors

Here **geometry** means the arrangement of numerical vectors collected inside a model across generated text positions. We measured their spread across directions and changes between adjacent positions. It does not refer to geometry questions such as triangles. [What each measurement means](../../docs/METHODS.md) explains the terms, exact formulas and saved-result keys before the implementation details.

These four files are unchanged copies of the completed experiment's source. They are provided for inspection. The historical environment used NumPy 2.3.5 for numerical arrays and scikit-learn 1.8.0 for fitting predictors.

| File | What it does |
| --- | --- |
| `geometry_measures.py` | Computes four summaries of changing token uncertainty and four summaries of internal-vector shape. |
| `geometry_analysis.py` | Trains the fixed small predictor while excluding each evaluated problem family, calculates classification metrics and checks the preselected criteria for expanding the method. |
| `geometry_common.py` | Checks source identities, file hashes and stored measurement records, called caches. |
| `geometry_protocol.json` | Records the chosen settings, comparison methods and interpretation limits. |

Code names such as `temporal`, `readout`, `Gram`, `eigenvalue`, `AUROC` and `bootstrap` are explained in [Methods](../../docs/METHODS.md). The numerical source and machine-readable result keys retain their historical names to preserve identity with the audited experiment.

The original `cases.json`, `frozen_profiles.json`, GPU records and archive are not included. Regenerating the original LLM measurements requires those historical inputs. The small predictors can now be retrained from the separately published derived feature matrices using `../../reproduce_readouts.py`; see [reproduction scope](../../docs/REPRODUCIBILITY.md). This is not a complete GPU runner or competition submission. From the repository root, verify the published predictions using:

```sh
python projects/aimo-interpretability/verify_results.py
```

The copied-file hashes are recorded in [provenance.json](../../results/geometry/provenance.json). Hash agreement verifies byte identity; it does not repeat the neural-model calculations.
