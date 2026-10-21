# AIMO Interpretability — predicting when mathematical performance survives problem changes

**Research in progress · updated 21 October 2026 · Ratchanon Preecha**

I am investigating whether measurements taken while a language model begins an answer can predict how much its mathematical performance will fall when a problem changes in ways that preserve the required reasoning. This project is being developed toward the **AIMO Interpretability Challenge, Small Models Track**. The language models' trained weights—the numerical parameters learned during their training—remain fixed; I train only small predictors from measurements of those models.

**What we have learned:** the tested changes to internal number representations and the tested measurements of internal-vector shape have not improved predictions over the stronger comparison methods. A study collecting additional model answers is incomplete. This snapshot contains no verified competitive method or retained official leaderboard score.

## Start here

- This page explains the challenge, measurements and latest completed result.
- [What each measurement means](docs/METHODS.md) explains internal vectors, probability measurements, comparison methods and the exact four shape calculations.
- [Results and their limits](docs/RESULTS.md) separates completed experiments from incomplete runs.
- [Next experiment and questions for advice](docs/NEXT_EXPERIMENT.md) explains the proposed research decision.

This differs from my [neural-training intervention study](../neural-training/README.md), which changes a neural network's state during training.

## What the challenge asks

For a given model and mathematical problem, our program returns **robust** or **nonrobust**. Robust means that the model's accuracy remains reliable when details change while the underlying reasoning stays the same. Nonrobust means that at least one such change clearly damages performance. Changing numbers can change the correct answer even when the solution method stays the same.

For example, a model might solve an original problem often but fail on versions with different numbers. We want to predict that vulnerability without repeatedly solving every possible version during competition evaluation. Correctly answering the original once is insufficient evidence.

The submission exposes this Python function:

```python
are_robust(model_id: str, reasoning_effort: str, problems: list[str]) -> list[bool]
```

It receives a model identifier, its reasoning-effort setting and problem texts, and returns one true/false prediction per problem. It runs without internet access. All models and problems together share a **3,600-second prediction limit**; training and data collection happen separately. The Small Models Track evaluates Qwen3.5-4B, Skywork-OR1-Math-7B, Olmo-3-7B-Think and DeepSeek-R1-0528-Qwen3-8B. The organizers do not publish the exact rule that converts their measurements into robust/nonrobust labels.

Official references: [challenge and current rules](https://aimo-interp.github.io/) · [submission interface and environment](https://github.com/aimo-interp/getting-started) · [example methods](https://github.com/aimo-interp/baselines) · [public training data](https://huggingface.co/datasets/aimo-interp/train-main-v2).

## What does “geometry” mean in this experiment?

As a model processes text, it represents each position internally as a **vector: a list of numbers**. A vector taken from an intermediate processing layer is called a **hidden state** or **activation**. A **token** is one text unit used by the model; it can be a word, part of a word, a number fragment or punctuation.

We collected one internal vector for each of the first **128 generated tokens**, from one fixed processing layer about three quarters of the way through the model. We then calculated four summaries of how those vectors were arranged:

1. Whether their variation was spread across many directions or concentrated in a few.
2. How much of that variation lay along the single strongest direction.
3. A regularized measure of how much variation remained across all directions. Regularization adds a small constant so that nearly zero values can be handled numerically.
4. How much vector direction changed between consecutive tokens.

These measurements are what this project calls **internal-vector geometry**. The term describes relationships among numerical vectors, not whether the mathematical question is about triangles or circles. It does not by itself identify reasoning steps or prove that an answer is correct.

We added these four numbers to a simpler predictor and asked whether its robustness classifications improved. [The methods note](docs/METHODS.md#the-four-internal-vector-shape-measurements) gives the exact calculations and names used in code.

## What were the simpler comparison methods?

A **baseline** is a reference method used to judge whether a new idea helps. A **control** tests whether an apparent benefit could come from simpler or less specific information.

| Reader-facing name | Information used | Saved-result key |
| --- | --- | --- |
| Always predict robust | The same prediction for every case | `always_robust` |
| Text and bookkeeping measurements | Text length, number/symbol counts, model identity, response length and information about which positions could be measured | `structure` |
| Add overall token-probability summaries | The preceding measurements plus summaries of the probabilities the model assigned while generating the short answer | `aggregate` |
| Add changes in uncertainty over the answer | The overall-probability method plus whether next-token uncertainty rises, falls or fluctuates across those 128 tokens | `temporal` |
| **Add internal-vector shape — main proposed improvement** | The overall-probability method plus the four vector-shape measurements above | **`geometry`** |
| Add both uncertainty changes and vector shape | Both additions together | `combined` |

Token probability is a model prediction about text, not a calibrated probability that its mathematical answer is correct. A further word-position disturbance control, saved as `prose_control`, tests sensitivity to changing ordinary-word input vectors; it is explained in [Methods](docs/METHODS.md#the-number-position-and-word-position-disturbance-experiment).

## Latest completed comparison

A **case** is one problem–model pair. A **problem family** groups related versions of a mathematical problem. Our latest fully checked comparison contains **43 public development cases from 20 families**, with 31 robust and 12 nonrobust reference labels.

For each family, we trained the small predictor on the other families and evaluated it on that family. Related versions and their model-specific rows stayed together. This prevents direct training/test overlap within a family, although these public families have already influenced earlier research choices.

| Predictor | Correct robustness classifications / 43 | Accuracy | Nonrobust cases correctly identified / 12 |
| --- | ---: | ---: | ---: |
| Always predict robust | 31 | 72.09% | 0 |
| Text and bookkeeping measurements | 33 | 76.74% | 7 |
| Add overall token-probability summaries | 33 | 76.74% | 7 |
| Add changes in uncertainty | 33 | 76.74% | 7 |
| **Add internal-vector shape — main test** | **32** | **74.42%** | **6** |
| Add uncertainty changes and internal-vector shape | 32 | 74.42% | 6 |

Adding vector shape fixed zero errors and introduced one compared with the overall-probability method. It did not improve this experiment. We have stopped expanding this particular four-measurement design. This result does not establish that every possible use of internal model vectors will fail.

These are local development results, not private-test or leaderboard scores. [Results](docs/RESULTS.md) explains the uncertainty calculation, older experiments and limits.

## Proposed next step

The next hypothesis is to train a small predictor from **measured changes in model behaviour**. During training-data collection, repeatedly solve an original problem and verified variants, estimate the accuracy difference, and ask whether measurements from a short original answer can predict that difference on new families. This is called **behavioural supervision**: observed behaviour supplies the training target.

We must first show that the accuracy difference can be measured reliably. The predictor must then improve on simpler references, including predictions of original-question correctness, and work on another problem source. The current larger study has not established those results. A recent A100 Colab disconnection also needs a retained log/checkpoint review to determine its cause.

## Verify the saved result counts

From the repository root:

```sh
python projects/aimo-interpretability/verify_results.py
```

Python 3.10+ and its standard library are sufficient. The script checks file hashes, which detect changed bytes, and checks that each family was excluded from training when evaluated. It recalculates the classification counts and other reported scores from saved predictions. Definitions of balanced accuracy, Brier loss and AUROC are in [Methods](docs/METHODS.md#how-the-predictions-are-evaluated).

This verifies saved results on CPU. It does not regenerate model outputs or retrain predictors. [Saved predictions](results/geometry/held_out_predictions.json) · [saved summary](results/geometry/summary.json) · [analysis source guide](source/geometry/README.md).

## Advice I am seeking

- Which experiment best separates sensitivity to problem changes from ordinary answer correctness or problem difficulty?
- How should I evaluate performance on new problems with few labeled families and several different models?
- How should GPU memory measurements and saved progress be organized so long experiments provide reproducible intermediate results?

The [next-experiment note](docs/NEXT_EXPERIMENT.md) gives the proposed tests and decision criteria.

## Rights and data scope

The repository's [rights statement](../../README.md#rights) applies to original material. External papers, models, code and datasets retain their own terms. This snapshot includes derived scores, case/family identifiers and selected analysis source. It does not include model weights, the full problem corpus, generated reasoning text or historical raw measurement files. The original GPU experiment cannot be rerun from this snapshot alone.
