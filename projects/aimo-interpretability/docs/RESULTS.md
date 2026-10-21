# Results and evidence scope

Updated 21 October 2026. The status of an experiment is separate from whether its implementation passed engineering checks.

## What has been learned

| Experiment | Supported conclusion | Current status |
| --- | --- | --- |
| Earlier prompt/layer probes | The retained evaluations did not establish an improvement over their constant baseline. | No positive transfer claim. Their data and readout differ from the comparison below. |
| Numerical-intervention benchmark | On 43 public cases, the candidate scored 33/43, versus 32/43 for aggregate confidence and 34/43 for a prose control. | No incremental benefit over the stronger control; branch frozen. |
| Fixed early-trace geometry | On the common refitted-control protocol, geometry scored 32/43, versus 33/43 for structure, aggregate confidence and prose controls. | Audited negative result for this fixed design. |
| Verified auxiliary-generation pilot | Only 27 responses were collected; 19 were parseable and correct, but no complete problem family was measured. | No supported robustness or predictive conclusion. Truncation and missing responses prevent interpretation. |
| Integrated auxiliary-data study | A notebook and source bundle were prepared for 96 families and two models. Local engineering checks were completed. | No completed scientific outcome is claimed. The recently reported A100 disconnection needs a retained log/checkpoint audit. |

Scores from different protocols must not be compared as a learning curve. In particular, the geometry comparison refits all controls using a new fixed unweighted classifier. The numerical-intervention counts belong to the older frozen protocol.

## Geometry protocol

- Four frozen checkpoints: Qwen3.5-4B, Skywork-OR1-Math-7B, Olmo-3-7B-Think and DeepSeek-R1-0528-Qwen3-8B.
- 43 labeled development cases, 20 grouped mathematical families, 31 robust and 12 nonrobust targets. Six small-track cases without a binary target were excluded from this binary experiment; exclusion does not imply they lack useful continuous measurements.
- 128 continuation tokens per case, with one decoder block at 75% of model depth. The block output is taken before final normalization. No layer search was performed in this test.
- Four geometry features: normalized spectral entropy, largest-eigenvalue share, mean log regularized eigenvalue and mean adjacent cosine distance.
- Temporal features summarize entropy slope, linear-fit R², the difference between late and early quarters, and the largest local-window excess over the mean.
- Fixed logistic regression: C = 0.1, liblinear, no class weighting, training-fold-only standardization and threshold 0.5. All variants/models belonging to a family are held out together.
- Geometry is the primary candidate. The combined arm is descriptive and cannot replace a failed primary result.

The machine-readable [protocol](../source/geometry/geometry_protocol.json), [feature code](../source/geometry/geometry_measures.py) and [historical analysis](../source/geometry/geometry_analysis.py) are retained unchanged. The analysis source requires the original feature caches to refit; this publication contains a lighter saved-prediction verification path instead.

## Outcome and audit

The geometry candidate corrected zero aggregate-confidence errors and introduced one error. The saved primary outcome is `NO_CLEAR_INCREMENTAL_GAIN`. The paired family-bootstrap 95% interval was −7.69 to 0.00 percentage points against aggregate confidence. There were zero benefiting families and one harmed family.

The original audit independently reconstructed the four geometry scores with PyTorch float64 eigendecomposition, with maximum difference 1.43e−13, and reconstructed held-out readout scores using a separate sklearn pipeline, with maximum difference 2.48e−14. All 43 measurements completed and each model recorded a native hidden-state reference check. These are historical audit findings, not newly repeated GPU measurements.

The original returned ZIP passed CRC and source-identity checks. Its SHA-256 was `55b9547ecdd9c330c8e7a4cf4d1f4f5fad8f7393771d1487e9d6b52fa83bda0e`. The ZIP is not included in this lightweight publication. [Provenance](../results/geometry/provenance.json) identifies the derived files retained here.

## Limits

The 20 public families have been inspected across previous experiments. Family withholding prevents direct within-fold leakage but does not erase adaptive choices informed by earlier results. The bootstrap intervals condition on fixed predictions and omit refitting, earlier hypothesis selection and simultaneous testing uncertainty. A 128-token prefix may contain restatement or boilerplate. No private competition score or general mechanistic explanation follows from these results.

The new verification script checks the internal numerical consistency of the published tables and saved predictions. It does not independently verify the biological or mathematical semantics of a label, regenerate neural activations, validate a new A100 memory bound, or establish performance on new families.

## Data reference

The public-case source was [aimo-interp/train-main-v2](https://huggingface.co/datasets/aimo-interp/train-main-v2), revision `fa8af758c6519fc97a9d0bd9017feb6f12232b52`. The input parquet SHA-256 was `e18eb44207e7987781ec2ff214793196038442bdc1466fdf5498f3e87ec58285`. The original source contained 94 rows across both tracks, 49 small-track rows and 43 labeled small-track rows; these are overlapping public development data, not 94 new independent training examples for the small track.
