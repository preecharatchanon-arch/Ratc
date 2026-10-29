# CaSR functional contrast

Read REPORT.md for the conclusion and limitations; PROTOCOL.md contains the
written design frozen before numerical analysis. Source means were already
inspected, so this is exploratory reanalysis, not preregistered confirmation.

- functional_data.csv: all56 source-table entries, including missing NA values.
- analyze.py: one prespecified summary-data uncertainty calculation.
- results.json: actual outputs; no simulated biological measurements.
- design_freeze.json: original protocol/input hashes and freeze time.
- SOURCE_MANIFEST.json: original-source provenance and hashes.

Run `python analyze.py` with Python3.12 and scipy1.15.3. No docking or model
training is included. Main outcome: opposing mutation effects survive the
conditional rounding-sensitive bounds; complete potency reversal does not.
This is not evidence of a human saltiness-selection advantage.
