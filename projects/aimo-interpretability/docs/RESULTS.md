# Results and what they establish

Updated 21 October 2026. Passing engineering checks means code behaved as expected in those checks; it does not establish a useful scientific prediction.

A **case** is one problem paired with a model. A **family** groups related problem versions. The score reported here counts correct robust/nonrobust classifications, rather than correct mathematical answers. A **reference method**, also called a baseline or control, provides the comparison needed to judge a proposed improvement.

[Methods](METHODS.md) explains the measurements, their code names and all evaluation terms used below.

## What each experiment actually did

| Experiment | Operation and question | Supported result |
| --- | --- | --- |
| Earlier small predictors from internal vectors, called prompt/layer probes | Learn a simple predictor from the model's numerical representation after reading the question, at selected processing layers. Can it predict robustness? | The retained evaluations did not establish an improvement over a constant prediction. These data and fitting rules differ from the later comparison. |
| Disturb internal vectors at number positions, called numerical intervention | Replace directions of input vectors at number positions, then score the same previously generated text. Compare with disturbing ordinary-word positions. Does number sensitivity add useful information? | On 43 cases, the number-position candidate scored 33/43, versus 32/43 for overall token-probability summaries and 34/43 for the word-position disturbance control. No gain over the stronger control. |
| Measure internal-vector shape, called geometry | Replay the first 128 generated text units, measure spread and direction changes in one processing layer, and add four summaries to the overall-probability predictor. | The proposed addition scored 32/43, versus 33/43 for the text/bookkeeping, overall-probability and word-disturbance references. No gain from this fixed design. |
| Collect additional solved examples, called the auxiliary-generation pilot | Repeatedly solve original and verified altered problems to measure accuracy differences. | Only 27 responses were collected; 19 had extractable final answers and were correct, but no family had all required responses. No robustness or predictive conclusion follows. |
| Larger proposed data-collection and prediction study, called the integrated study | Prepare a comparison using 96 families and two models. | Notebook and source were prepared and local engineering checks completed. There is no completed scientific outcome. A reported A100 disconnection still needs a retained log/checkpoint review. |

The number-position disturbance is an internal-vector edit, not a test of newly solved problems with changed numbers. The [methods note](METHODS.md#the-number-position-and-word-position-disturbance-experiment) describes that distinction and the word-position control.

Scores from different experiments are not a learning curve: the later vector-shape test refits every comparison method using a new fixed fitting rule. The older counts remain attached to their original rule.

## How the completed vector-shape test was specified

- Four fixed language models: Qwen3.5-4B, Skywork-OR1-Math-7B, Olmo-3-7B-Think and DeepSeek-R1-0528-Qwen3-8B.
- 43 labeled cases in 20 families: 31 robust and 12 nonrobust. Six small-track cases lacking a binary label were excluded from this robust/nonrobust comparison. They may still have useful continuous accuracy-drop measurements.
- First 128 generated **tokens**, the model's text units. Internal vectors were taken from one processing block at 75% of model depth, before final normalization. The block choice was fixed rather than searched using the result.
- Four vector-shape measurements: distribution of variation across directions, share along the strongest direction, mean log of the regularized spectrum, and mean directional change between adjacent positions. [Methods](METHODS.md#the-four-internal-vector-shape-measurements) defines the exact formulas and code names.
- Four measurements of uncertainty changing across token positions: slope, straight-line fit, late-minus-early mean and the largest local mean above the overall mean. These are the `temporal` features in code.
- A fixed logistic-regression predictor converts a weighted combination of measurements into a robustness probability. The implementation uses `C=0.1`, `liblinear`, no class weighting and threshold 0.5. Measurements are standardized using only the training partition. These fitting terms are explained in [Methods](METHODS.md#text-units-internal-vectors-and-small-predictors).
- Each family and its model-specific cases are excluded from training together when evaluated. The internal-vector-shape addition is the main proposed improvement, called the **primary candidate**. Combining it with uncertainty changes is a secondary description, not a replacement candidate selected after seeing results.

The machine-readable [protocol](../source/geometry/geometry_protocol.json), [feature calculations](../source/geometry/geometry_measures.py) and [historical analysis](../source/geometry/geometry_analysis.py) remain unchanged. Retraining the predictors requires original measurement files not included in this publication. A lighter saved-prediction check is provided instead.

## Outcome and numerical verification

Adding vector shape fixed zero errors and introduced one relative to overall token-probability summaries. The saved outcome code is `NO_CLEAR_INCREMENTAL_GAIN`, meaning no demonstrated benefit from the added measurements.

To describe uncertainty, the analysis repeatedly resampled whole families and compared accuracy on the same resampled cases. Its central 95% interval for the accuracy difference was −7.69 to 0.00 percentage points. No family gained correct predictions and one family lost one. This **family bootstrap** uses the already fitted predictions; it omits uncertainty from retraining and earlier research choices.

The historical audit independently recalculated the four shape scores with PyTorch using 64-bit floating-point arithmetic; the largest difference was 1.43e−13. A separate sklearn calculation reconstructed the trained-predictor scores with largest difference 2.48e−14. All 43 measurements completed. Each model recorded a check that the chosen internal-vector extraction agreed with the model's standard output interface. These are saved audit findings, not newly repeated GPU calculations.

The original returned ZIP passed checks for archive corruption and source-file identity. Its SHA-256 file fingerprint was `55b9547ecdd9c330c8e7a4cf4d1f4f5fad8f7393771d1487e9d6b52fa83bda0e`. The archive is not included here. [Provenance](../results/geometry/provenance.json) records the origins and hashes of the retained files.

## Limits and reproducibility

These 20 public families have been inspected across earlier experiments. Keeping families separate within each training/test partition does not undo research choices informed by previous results. The 128-token beginnings may contain restatement or boilerplate. No private competition score or general explanation of the model's reasoning follows from this result.

The [verification script](../verify_results.py) recalculates classification metrics from saved predictions and checks hashes and family separation. It does not regenerate internal vectors, retrain predictors, rerun the bootstrap or establish performance on new families. Definitions of its reported accuracy, balanced accuracy, Brier loss and AUROC are in [Methods](METHODS.md#how-the-predictions-are-evaluated).

## Data origin

The public cases came from [aimo-interp/train-main-v2](https://huggingface.co/datasets/aimo-interp/train-main-v2), revision `fa8af758c6519fc97a9d0bd9017feb6f12232b52`. The original parquet data-file SHA-256 was `e18eb44207e7987781ec2ff214793196038442bdc1466fdf5498f3e87ec58285`. It contained 94 rows across both tracks, including 49 small-track rows and 43 labeled small-track rows. These overlap across problems/models and are not 94 independent new small-track examples.
