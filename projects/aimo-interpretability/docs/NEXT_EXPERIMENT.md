# Next experiment and questions for advice

**Status: proposed; no positive outcome claimed.** This note describes the research decision before another notebook is treated as ready for a full GPU campaign.

## Hypothesis

Can selected hidden states from a short original-problem trace predict measured sensitivity to mathematically verified variants, beyond confidence, original correctness and problem-text cues?

One possible auxiliary target is original-problem accuracy minus mean variant accuracy under a declared sampling budget. This is an operational measurement. It is not the organizers' unpublished binary robustness criterion, and a budget-induced failure is not automatically a reasoning failure.

The training strategy is inspired by [Semantic Entropy Probes: Robust and Cheap Hallucination Detection in LLMs](https://arxiv.org/abs/2406.15927): estimate an expensive behavioural property from a cheap representation at deployment. That paper studies hallucination detection, so its transfer to mathematical robustness is a hypothesis. [Tracing Uncertainty in Language Model “Reasoning”](https://arxiv.org/abs/2605.07776) motivates short-trace confidence controls, but predicts correctness rather than perturbation robustness.

## Three decisions

| Stage | Measurement | Decision |
| --- | --- | --- |
| Target reliability | Repeat independent response batches on complete original/variant families; track censoring, parse failures, target variation and agreement between repeats. | Expand only when fragility can be measured repeatably under a feasible declared budget. Otherwise revise the task or measurement. |
| Incremental signal | Compare fixed simple readouts of short-trace hidden states with constant, text, confidence and original-correctness controls. | Continue only if whole-family held-out error improves with uncertainty and multiple contributing families. |
| Transfer | Freeze the readout, then evaluate a different problem source; inspect official-label development performance separately. | A result confined to the training source is insufficient to justify a deployment claim. |

## Evaluation design

Use all appropriate official continuous measurements as training targets only within training partitions, including binary-unlabeled cases when their continuous target is usable. Keep related problems, source variants and their model-specific rows together in each partition. Fit preprocessing, regularization and thresholds using training/development data only. Never supply `max_drop`, labels or variant correctness measurements to the deployed feature extractor.

If new auxiliary data is collected, feature samples and target-scoring samples must be disjoint. References and transformations need independent checks. A numerical variant may have a different answer, so raw answer agreement across variants is not a robustness measure. Measure original correctness separately: uniformly failing on every view can produce a small accuracy drop without demonstrating successful reasoning.

Report results by source and model, the main metric and its family-level uncertainty, benefiting/harmed families, missingness, censoring and measured compute. A short-trace predictor must first predict its auxiliary target on withheld data; that result alone still does not establish official-label accuracy. Previously inspected official cases remain development evidence.

## GPU execution requirements

Begin with one model and one sequence at a time. Record free/allocated/reserved/peak VRAM and CPU RAM, and exercise the longest intended context before a campaign is released. Avoid retaining all layers, full-vocabulary score histories or live GPU tensors across cases. Use inference mode and transfer selected small records to CPU promptly.

Checkpoint completed records atomically, with model/config/source identity and explicit error records. Record an OOM distinctly from a censored answer or wrong answer. Confirm a resumed run uses the same measurement and sampling policy. A successful CPU test or short GPU run does not certify long-context memory safety; checkpointing preserves work but does not bound memory consumption.

The existing integrated notebook allows 24,576 generated tokens and was not validated end-to-end on the user's A100 before delivery. It should be treated as historical experimental code pending revision and real hardware checks, rather than a validated campaign entry point.

## Questions for an adviser

1. Would this design isolate robustness-specific information, or would a different control or target expose a correctness/difficulty shortcut more decisively?
2. With few official families, should the first priority be better auxiliary-data coverage, a simpler readout, or a different generalization test?
3. Which GPU execution design, profiling method or relevant research group/paper would help make repeated measurements efficient and reproducible?

No external adviser is associated with or endorses this project by being asked these questions.
