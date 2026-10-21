# AIMO Interpretability — predicting robustness of mathematical reasoning

**Research in progress · updated 21 October 2026 · Ratchanon Preecha**

I am investigating whether inexpensive signals from a language model can predict when its mathematical performance will deteriorate under changes that preserve a problem's underlying reasoning. The project is being developed toward the **AIMO Interpretability Challenge, Small Models Track**. It is separate from my [neural-training intervention study](../neural-training/README.md): here the models are frozen and the target is robustness during inference.

**Current finding:** completed experiments have not demonstrated an incremental benefit from the tested numerical-intervention or activation-geometry signals over the stronger controls. A larger auxiliary-data study remains inconclusive. There is no verified competitive method or retained official leaderboard score in this project snapshot.

## Read this project in five minutes

1. This page explains the question, results and current direction.
2. [Results and interpretation](docs/RESULTS.md) distinguish completed measurements from incomplete experiments.
3. [Next experiment and questions for advice](docs/NEXT_EXPERIMENT.md) explain the hypothesis I want to test.
4. [Saved predictions](results/geometry/held_out_predictions.json), [summary](results/geometry/summary.json) and [source guide](source/geometry/README.md) provide inspectable evidence.

## What the challenge asks

For each supplied model and problem, the submission predicts whether that model answers the problem robustly. Robustness concerns performance under perturbations that leave the deductive chain unchanged; it is different from answering the original correctly once. A numerical perturbation can change the correct answer while preserving the required reasoning.

The official interface is:

```python
are_robust(model_id: str, reasoning_effort: str, problems: list[str]) -> list[bool]
```

Predictions must work offline. The entire prediction run, across all problems and models, has a shared **3,600-second limit**. The Small Models Track includes Qwen3.5-4B, Skywork-OR1-Math-7B, Olmo-3-7B-Think and DeepSeek-R1-0528-Qwen3-8B. Training and data collection are separate from this inference budget. The organizers do not publish the exact binary-label criterion, so an auxiliary accuracy-drop target must not be presented as their official label definition.

Official references: [challenge and current rules](https://aimo-interp.github.io/) · [submission interface and environment](https://github.com/aimo-interp/getting-started) · [baseline implementations](https://github.com/aimo-interp/baselines) · [public train-main-v2 data](https://huggingface.co/datasets/aimo-interp/train-main-v2).

## Completed evidence: a fixed geometry test

The most recent fully audited comparison contains **43 public development cases from 20 problem families**, across the four small models. There are 31 robust and 12 nonrobust cases. All cases from a family are withheld together across models. This public set has already informed earlier experiments; it is not an untouched confirmation set.

| Method | Correct / 43 | Accuracy | Nonrobust cases detected / 12 |
| --- | ---: | ---: | ---: |
| Always predict robust | 31 | 72.09% | 0 |
| Problem-structure control | 33 | 76.74% | 7 |
| Aggregate confidence | 33 | 76.74% | 7 |
| Aggregate confidence + temporal features | 33 | 76.74% | 7 |
| **Aggregate confidence + geometry — primary candidate** | **32** | **74.42%** | **6** |
| Aggregate confidence + temporal features + geometry | 32 | 74.42% | 6 |

Geometry corrected zero cases and lost one relative to aggregate confidence. Its paired, whole-family bootstrap interval for accuracy gain was **−7.69 to 0.00 percentage points**, conditional on the fitted held-out predictions. This closes the particular four-feature, one-layer, 128-token geometry design. It does not establish that all internal representations are uninformative.

The [results note](docs/RESULTS.md) gives the protocol, limits, earlier findings and provenance. These percentages are local development measurements, not private-test or leaderboard scores.

## Current direction: behavioural supervision with inexpensive inference

The hypothesis is that a small predictor trained to estimate measured sensitivity to verified problem variants might transfer better than a predictor trained only on correctness or a small set of binary robustness labels. A short original-problem trace would supply confidence statistics and selected hidden states; expensive repeated solving would occur during training-data collection.

This is a proposed experiment. Its first requirement is reliable measurement of the auxiliary target. It must then beat problem-text, confidence and original-correctness controls on withheld families and a different problem source. The existing integrated study has not established those results. An A100 Colab disconnection was reported during the recent workflow; the exact failure stage and VRAM cause have not been established from a retained diagnostic log.

## Verify the saved result counts

From the repository root, run:

```sh
python projects/aimo-interpretability/verify_results.py
```

Python 3.10+ and its standard library are sufficient. The script checks file hashes, verifies family isolation and prediction thresholds, and recomputes counts, accuracy, balanced accuracy, Brier loss and AUROC from the saved held-out predictions. It also verifies the primary comparison and the per-family counts. This is a CPU check of saved results; it does not rerun model inference or refit the readouts.

## Advice I am seeking

- Which experiment would best distinguish a robustness-specific signal from ordinary correctness or problem difficulty?
- How should I evaluate generalization with few labeled families and several different models?
- How should I structure GPU measurements, memory checks and checkpoints so that long experiments produce useful, reproducible intermediate results?

The concrete alternatives and decision criteria are in [Next experiment](docs/NEXT_EXPERIMENT.md). Advice on a smaller, more decisive experiment or a relevant paper would be particularly helpful.

## Rights and data scope

The repository's [rights statement](../../README.md#rights) applies to this project's original material. External papers, models, code and datasets retain their own terms. This snapshot includes derived scores, opaque case/family identifiers and selected analysis source; it does not redistribute model weights, the full problem corpus, generated reasoning traces or the historical raw feature caches. The original GPU campaign cannot be rerun from this snapshot alone.
