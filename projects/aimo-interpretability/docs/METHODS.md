# What each measurement means

This note maps the explanations in the [project overview](../README.md) to names used in saved results and code. It describes measurements, not proof that a model follows a particular reasoning mechanism.

## Text units, internal vectors and small predictors

A **token** is a text unit processed by a model. A **prompt** is its input text, including formatting instructions. A **continuation** or **trace** is text generated after that prompt. A **prefix** here means the beginning of generated text: the first 128 tokens in the completed shape experiment. It may contain restatement or introductory text rather than a complete solution.

The model first maps input tokens into vectors, lists of numbers called **input embeddings**. It then applies successive processing blocks, also called layers or decoder blocks. A vector after one of those blocks is a **hidden state**, also called an activation here. It differs from the input embedding. The four tested models have vector widths of 2,560, 3,584 or 4,096 at the selected block.

A **feature** is one number supplied to our predictor, such as mean token uncertainty. A **probe** or **readout** is a small learned predictor mapping measurements to a target. The completed comparison uses logistic regression: a weighted sum of standardized measurements is converted into a probability, and scores at least 0.5 are classified as robust. The language model itself is not retrained.

**Standardization** subtracts each measurement's training-set mean and divides by its training-set standard deviation. **Regularization** penalizes large fitted coefficients to reduce fitting to noise. Here scikit-learn's `C=0.1` controls the strength of that penalty, and `liblinear` names the numerical fitting algorithm. Class weighting would give one label group more influence during fitting; this experiment uses no class weighting. These choices were fixed for the reported comparison.

## The four internal-vector shape measurements

“Geometry” in the result files means the arrangement of internal vectors across generated text positions. A mathematical geometry problem is a separate use of the word.

We replay the same 128-token continuation and collect the output vector of block `ceil(0.75 × number_of_blocks) − 1`, with zero-based indexing, before the model's final normalization. The vectors for those positions form the rows of a matrix `H`.

The calculation in [geometry_measures.py](../source/geometry/geometry_measures.py) is:

1. Divide each row by its length, so every vector has unit length. This removes magnitude differences: `[1, 0]` and `[2, 0]` become the same direction. These two vectors are illustrative, not measured data.
2. Subtract the average row vector. This **centering** removes the direction shared by the collection and retains variation around it.
3. Multiply the centered matrix by its transpose. The resulting **Gram matrix** contains pairwise dot products, describing how centered vectors align.
4. Divide that matrix by the sum of its diagonal entries, its **trace**. This expresses relative shape rather than total variation size.
5. Calculate its **eigenvalues**, nonnegative numbers describing how variation is distributed along mutually perpendicular principal directions. Their sum is one after normalization.

For `n=128` eigenvalues `λ₁,…,λₙ`, the four measurements are:

| Code name | Calculation | Meaning |
| --- | --- | --- |
| `normalized_spectral_entropy` | `−sum(λ × log λ) / log(n)`, omitting zero terms | How evenly variation is distributed across directions; larger values mean a more even spread. |
| `largest_eigenvalue_share` | `max(λ)` | Fraction of total variation along the strongest direction. |
| `mean_log_regularized_eigenvalue` | `mean(log(λ + 0.000001))` | A spectrum summary sensitive to directions with little variation. The added constant prevents taking the logarithm of zero. It is not a physical volume or a count of concepts. |
| `mean_adjacent_cosine_distance` | Mean of `1 − dot(uₜ, uₜ₊₁)` for consecutive unit vectors before centering | Average directional change from one text position to the next. Identical directions have distance zero. |

The first three describe overall shape and ignore token order. The fourth uses the order. Larger values do not inherently mean better reasoning. The experiment asks whether a learned combination improves robustness prediction beyond simpler measurements.

## Token probabilities and changes in uncertainty

At each generation step, the model assigns a probability to every possible next token. Our **overall token-probability summaries**, saved under `aggregate`, summarize selected-token probabilities and the distribution over alternatives. They include means, extremes, variation, the gap between the two most probable alternatives, and the fraction of very high/low selected-token probabilities.

**Entropy** measures how spread out a probability distribution is. Concentration on one next token gives low entropy; many similarly probable alternatives give higher entropy. A model can nevertheless be confidently wrong. Token probabilities do not directly measure mathematical truth.

**Negative log probability** is a surprise score: a less probable selected token has a larger score. **Perplexity** is the exponential of its mean, another summary of how surprising the generated text is under the model.

The `temporal` method adds four measurements of entropy changes across the 128 positions: overall slope, how well a straight line describes that change (`R²`), mean entropy in the last 32 positions minus the first 32, and the highest mean over 16 consecutive positions minus the overall mean. “Temporal” refers to text-position order, not elapsed time.

The `structure` reference includes text lengths, fractions of digits and mathematical symbols, line/capital-letter/LaTeX-command counts, model identity, prompt/response lengths, whether generation ended normally, and bookkeeping about measurable positions. It is not purely a question-text predictor. The `aggregate`, `temporal`, `geometry` and `combined` methods include these common inputs too.

## The number-position and word-position disturbance experiment

The older result called a **numerical intervention** changes internal input vectors at positions containing digits or number words. The written problem stays unchanged.

For selected number positions, each input vector's direction is replaced by the average direction of the problem's input vectors, preserving the vector's original length. The experiment then calculates how surprising the **same previously generated continuation** becomes. It scores fixed text under a modified internal input; it does not generate a newly solved answer after the disturbance.

As a control, the same number of ordinary-word positions is disturbed, with positions matched as closely as possible. Similar predictive value from word disturbances would weaken a number-specific interpretation.

The saved key `prose_control` means overall token-probability summaries plus six summaries of the surprise change after the ordinary-word disturbance. The number-position candidate adds summaries comparing number and word disturbances. The later vector-shape experiment reuses those saved probability and word-disturbance measurements and fits its own fixed predictor.

This differs from the proposed next experiment, which would actually solve original and mathematically verified altered problem texts repeatedly.

## How the predictions are evaluated

A **case** is a problem paired with a model. A **family** groups related versions of a problem. A **label** is the reference target: robust or nonrobust. **Out-of-family evaluation** means training without a whole family and then predicting its cases, including cases from different models. A **fold** is one such train/test partition. **Out-of-fold (OOF) predictions** are predictions obtained only when the case was excluded from that predictor's training.

| Term | Meaning here |
| --- | --- |
| Accuracy | Fraction of robust/nonrobust classifications matching reference labels. This differs from how often the language model solves mathematical questions. |
| Nonrobust recall | Fraction of the 12 genuinely nonrobust cases correctly identified as nonrobust. |
| Balanced accuracy | Average of recall for robust and nonrobust cases, giving the two groups equal weight. |
| Brier loss | Mean squared difference between a robustness probability and its true zero/one label; lower is better. |
| AUROC | How well scores rank robust above nonrobust cases across possible thresholds; 0.5 is chance ranking and 1 is perfect. It differs from accuracy at the chosen 0.5 threshold. |
| Paired comparison | Compare methods on the same cases, counting errors fixed and errors introduced. |
| Family bootstrap interval | Repeatedly resample whole families with replacement, keeping each family's cases together, and calculate the accuracy difference. The reported interval covers the central 95% of those differences. |
| Primary candidate / promotion gate | The improvement selected in advance and the criteria required before expanding it. Secondary comparisons cannot replace it after seeing results. |

The bootstrap uses fixed predictions. It does not retrain predictors or account for research choices informed by earlier experiments. **Data leakage** means information from a test case or its relatives influences training or selection. Family separation reduces one form of leakage; repeatedly inspected public data still does not become independent confirmation evidence.

## Terms used in the proposed next experiment

**Behavioural supervision** means training against measured model behaviour. An **auxiliary target** is a training measurement, such as accuracy loss across verified problem variants, separate from the official robust/nonrobust label. **Fragility** is shorthand for such measured loss, not a claim about an underlying mental process. **Transfer** means a learned relationship also works on another problem source or model.

**Censoring** means an answer was not observed before a time/token limit. A **parse failure** means the program could not extract a final answer. Neither should silently become evidence about mathematical reasoning. **Checkpointing** saves completed work for resumption. **VRAM** is GPU memory, **RAM** is main computer memory, and **OOM** means an out-of-memory error. A **cache** stores computed measurements to avoid repeating them.
