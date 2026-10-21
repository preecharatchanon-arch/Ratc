# Historical geometry analysis source

The four files here are unchanged copies of the completed geometry campaign's feature calculations, grouped readout, cache helpers and fixed protocol. They are published for inspection. They depend on NumPy; fitting also uses scikit-learn. The historical environment used NumPy 2.3.5 and scikit-learn 1.8.0.

- `geometry_measures.py`: four temporal and four geometry features.
- `geometry_analysis.py`: family withholding, fold-only standardization, fixed classifier, metrics and promotion gates.
- `geometry_common.py`: historical provenance and cache checks.
- `geometry_protocol.json`: frozen parameters and interpretation.

The original `cases.json`, `frozen_profiles.json`, GPU records and archive are not included. Importing some analysis modules requires the local protocol, and refitting requires those historical inputs. This is not a self-contained GPU runner or a submission bundle. To verify the published predictions and table without those inputs, use `../../verify_results.py` from this directory or the repository-root command in the project README.

The hashes of these copied files are in `../../results/geometry/provenance.json`. These checks establish byte identity to the retained source snapshot, not an independent rerun of the model forwards.
