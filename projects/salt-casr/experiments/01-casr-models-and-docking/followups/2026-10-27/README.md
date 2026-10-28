# CaSR focused follow-up — executed 27 October 2026

Read `CaSR_Further_Research_and_Tests.md` first. This package contains new fixed
model tests, independent saved-pose verification and an attributed evidence
registry. It does not contain a new effective compound or new sensory data.

## Reproduce the model comparison

Use an isolated Python 3.12 environment:

```sh
python -m pip install -r requirements.txt
python prepare_public_inputs.py
python run_tests.py --input-dir input --output-dir replay
```

The downloader verifies immutable Git blob hashes for the public chemical table,
old folds/predictions and chemical assembler. It does not rely on the changing
main branch. Public API access/rate limits apply. The verified-cache path was
exercised here; new HTTP downloads were supplied by the connected GitHub tool.
Existing repository files are referenced rather than duplicated in this bundle.

The included `input/glycine_extension_bounds.csv` is our previously computed
eleven-pair table. It is explicitly derived from published measurements, not
eleven new experimental observations. The current tests preserve its ranges.

`protocol.json` was written before fitting these particular models. Earlier
data/results had already been inspected, so this is exploratory work, not a
registered independent confirmation. No hyperparameter search followed the
reported fits. The shared alpha is 10; preprocessing is fitted within each
fold. The main task and the eleven-pair effect task are separate.

`summary.json` includes actual execution time and the primary decision. Most
numerical outputs are deterministic; execution time itself will vary. The
range-aware fit is squared distance to reported ranges plus Ridge penalty,
not a fitted censored-regression likelihood. Nine qualitative non-activators
and one explicitly bounded record are not assigned invented regression labels.

## Reproduce the independent pose check

Use the original `CaSR_Notebook_Run.zip` dated 14 October 2026:

```sh
python check_saved_poses.py --archive /path/to/CaSR_Notebook_Run.zip \
  --output replay/independent_RMSD_check.json
```

Its input SHA-256 is recorded in `output/independent_RMSD_check.json`. This reads
the original saved SDFs without extracting or executing archive source. It
does not run Vina. It checks all ten poses, graph symmetry, no centering and no
rigid alignment; separate translation and oxygen-swap checks catch wrong RMSD
semantics. The original archive is not duplicated in this package.

## Literature registry

`output/condition_evidence_registry.csv` contains 15 condition/evidence entries
across five publications. These are not 15 independent measured compounds or a
new training set. `output/source_access_notes.json` records endpoint and access
limits. Exact missing conditions stay missing. Only a set-level threshold range
was recovered for the eight Tu2023 sequences; it is not copied into each row.
The Yi2025 supplement was inspected and contains a scoring card and peptide
purity figures, not the complete sensory matrix methods. Third-party papers
and supplements are not redistributed.

`output/verification.json` records the actual checks and hashes. The GitHub
repository and original results were not modified. Every numerical improvement
remains conditional on previously observed within-series data; no external
prediction or sodium-replacement success is claimed.
