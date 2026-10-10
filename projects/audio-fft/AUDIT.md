# Reproduction and measurement audit

## Provenance

The author supplied analysis code and a printed run, identifying the project as work from 23 March 2026. On 10 October 2026, the analysis functions were restored into an importable module and rerun against the supplied MP3 files. The calculations were retained; repeated list storage was consolidated and Colab upload/printing/display operations moved to a runner. This is not a byte-identical recovered notebook. No March timestamp or prior competition claim is inferred from the files.

## What the rerun checks

- The engine and drum dominant bins, centroid, flatness, entropy, flagged-frame fractions, onset densities and severity agree with the supplied rounded log.
- Both baseline/test orientations are exported. Choosing the first uploaded file reversed the author's intended roles in the supplied run.
- Numerical sanity checks cover known-frequency sinusoids and the expected power ratio of a two-tone signal. These verify measurement mechanics, not fault-detection performance.
- SHA-256 hashes, sample rates, durations, CSVs and package versions are retained. Raw stock MP3s are linked rather than rehosted.

## Input selection and new runs

The Colab upload cell lists the actual uploaded filenames and asks the user to choose reference and comparison by number. Neither role is tied to an example filename or upload order, and the two selections must be different files. The local runner accepts explicit `--reference` and `--comparison` paths; `--engine` is retained as an alias.

New runs export schema version 2 with generic reference/comparison labels, per-role input hashes and both selected and reversed orientations. Figures live inside each run's output directory. The archived `results/` and `figures/` evidence remains unchanged, and the runner rejects those directories as new output destinations. `check_evidence.py` checks that historical example and measurement sanity, not the validity of an arbitrary user's recording against the example numbers.

## Definitions that matter

1. **Magnitude is not power.** The original `band_energy` sums `abs(FFT)`, so its retained values are labelled magnitude shares. The additional Welch audit integrates estimated power on equal-duration recordings at a common sample rate, with identical window settings.
2. **The original filter runs twice.** `analyze_file` and `extract_global_features` both high-pass. This is preserved for numerical reproduction. The separately labelled matched-support analysis filters once. The implementation is not a new March result.
3. **Global spectra have different supports.** Full files differ in length and sample rate. Raw FFT amplitudes, the number of bins and unnormalised entropy depend on these choices. The original comparison does not by itself establish a change in engine condition. The published FFT display normalises amplitudes by the Hann-window sum; STFT and Welch comparisons additionally use a shared rate and duration.
4. **Anomaly is relative to each recording.** MAD scores are calculated separately inside each file. A flagged frame is unusual relative to that recording, not a known mechanical fault, and the fraction is not calibrated between engine operating conditions.
5. **Clipping is measured after filtering.** Filter overshoot can create peaks above one. The original threshold count cannot establish clipping in the source recorder or MP3 decoder.
6. **The decay estimator is not a fitted decay envelope.** It finds the first absolute sample below a fraction of the maximum in a later window. Ordinary zero crossings can produce nearly zero values. These outputs are retained in the text reproduction but are not used as evidence of mechanical decay.
7. **Verdicts are hand-built heuristics.** Both inputs are classified as percussive by the original rules. The severity and wear/roughness hints have no labelled engine validation, calibrated threshold or measured diagnostic accuracy. No health status, worn component or engine RPM is inferred.

## Documentary scope

`original_prototype.py` retains the supplied analysis definitions. `run_analysis.py` restores the printing/export path and creates October figures with explicit roles and labels. `audio_fft_analysis.ipynb` embeds both modules for use in Colab. The audited power plot is an additional October calculation, not a replacement silently relabelled as a March result.

Primary technical references:

- NumPy FFT documentation: https://numpy.org/doc/stable/reference/routines.fft.html — amplitude `abs(A)` versus power `abs(A)**2`.
- SciPy STFT: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.stft.html
- SciPy Welch: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html

This is a signal-processing demonstration with transparent evidence, not a validated condition-monitoring product.
