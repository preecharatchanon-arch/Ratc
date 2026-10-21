# Next experiment and questions for advice

**Proposed work; no positive outcome claimed.** The completed experiments are described in [Results](RESULTS.md). This note explains what another experiment should decide before a large GPU run.

## The question in plain language

Can measurements from the beginning of an original answer predict how much the model's accuracy will fall on altered versions of the problem, beyond what we can predict from text, token probabilities and ordinary answer correctness?

Here a **token** is the model's text unit. An **internal vector**, also called a hidden state, is a list of numbers produced at an intermediate model layer. A **predictor** is a small learned model that converts selected measurements into a predicted outcome. [Methods](METHODS.md) defines these terms and explains the earlier measurements.

## What supplies the training target?

Repeatedly solve an original problem and mathematically verified variants, then estimate:

`accuracy drop = original accuracy − mean accuracy on variants`

For illustration only, 8 correct answers out of 10 attempts on the original and 5 out of 10 on a variant gives an estimated drop of 0.30. Ten attempts can be noisy; this example is not a measurement or an approved sample-size choice.

Using observed behaviour as the target is called **behavioural supervision**. The drop is an **auxiliary target**: an experimental training measurement, separate from the organizers' unpublished rule for assigning robust/nonrobust labels. The word **fragility** is only shorthand for such measured deterioration.

The motivation comes from [Semantic Entropy Probes: Robust and Cheap Hallucination Detection in LLMs](https://arxiv.org/abs/2406.15927), which trains inexpensive predictors from costly behavioural measurements. That paper studies hallucinations, so applying its training strategy to mathematical robustness remains a hypothesis. [Tracing Uncertainty in Language Model “Reasoning”](https://arxiv.org/abs/2605.07776) motivates comparison with changes in next-token uncertainty during early generated text; its published target is correctness.

## Three decisions the experiment must support

| Stage | What to do | What would justify continuing? |
| --- | --- | --- |
| Can we measure the drop reliably? | Collect independent repeated-answer batches for complete original/variant families. Check whether the estimated drop varies across families and agrees between repeats. Count answers lost to limits or extraction failures. | The measurement is repeatable under a feasible declared budget. |
| Do internal measurements add information? | Compare small predictors using short-answer internal vectors with references using constant predictions, text, token probabilities and original-correctness predictions. Exclude whole related families from training when testing them. | Lower prediction error with uncertainty reported, and improvement contributed by several families rather than one example. |
| Does it work beyond the training source? | Fix the trained predictor and its settings, then evaluate another problem source. Inspect official-label development results separately. | The improvement survives the change of source. This is **transfer**, or generalization to different data. |

## Preventing misleading results

Use appropriate official continuous measurements, such as `max_drop` (the supplied measured accuracy-drop field), only as training targets within training partitions. A case lacking a binary label may still have a usable continuous measurement. Related problem versions and their model-specific rows must remain together. Fit scaling, model settings and the robust/nonrobust decision threshold using training/development data only. The deployed measurement code must never receive labels, `max_drop` or variant correctness outcomes.

For new data, use separate generated answers to obtain predictor inputs and to estimate the target. Independently check answer references and transformations. Numerical variants can have different correct answers, so matching literal answers across variants is not a robustness measure. Also measure original correctness: a model that fails every version can have a small accuracy drop without demonstrating successful reasoning.

A **censored answer** is one whose final outcome was not observed before a token/time limit. A **parse failure** means the program could not extract its final answer. Keep both visible rather than silently treating them as pure reasoning failures. The declared bounded-budget score can count them as incorrect, but its interpretation must retain those operational limitations.

Report performance by problem source and model, uncertainty across families, errors fixed/introduced, missing records and compute cost. Predicting the auxiliary drop successfully does not by itself establish good official robust/nonrobust classifications. Previously inspected official cases remain development evidence.

## GPU execution requirements

Begin with one model and one sequence at a time. Measure GPU memory (**VRAM**) and main memory (**RAM**), including their peaks. Exercise the longest intended context before launching the full experiment. Copy only the chosen small measurements to CPU and release temporary GPU tensors; avoid retaining every layer or every token's full probability distribution.

**Checkpointing** saves completed work for resumption. Save each completed record atomically, so interruption cannot leave a half-written record treated as complete, and record model/source/settings identity. Keep an **OOM**, or out-of-memory error, distinct from a censored or incorrect answer. A resumed run must preserve the same measurement and sampling policy.

The existing larger notebook permits 24,576 generated tokens and was not verified end-to-end on the user's A100 before delivery. It remains historical experimental code pending revision and hardware checks. CPU checks and checkpoints alone do not establish long-context memory safety.

## Questions for an adviser

The request is for ideas about where to go next, given the completed negative results. The experiment above is one current hypothesis, not a conclusion that it is the best direction.

1. What alternative signal, mechanism or formulation would be worth investigating for robustness of mathematical reasoning?
2. Does learning measured accuracy drop seem a useful next direction, or does another hypothesis have a stronger rationale?
3. Which paper or research group's work would help challenge the assumptions of the methods already tried?

No external adviser is associated with or endorses the project merely by being asked these questions.
