# Testing Low-Rank Causal Control in AdamW Memory

**Research by:** Ratchanon Preecha  
**Status:** Research manuscript. A possible submission to the International Conference on Artificial Intelligence and Statistics (AISTATS) is planned; this manuscript has **not been submitted**.

This follow-up asks whether low-rank projections of AdamW first-moment memory preserve the functional effects of interventions derived from training history.

## What is tested

The evaluation distinguishes three requirements: influence capture on independent images, reconstruction of signed intervention responses, and robustness to alternate future batches and longer continuation horizons. Model weights, second moments, and the optimizer clock stay fixed when the first-moment intervention is applied.

A frozen thirty-task confirmation fails its declared causal-sufficiency conjunction. Subsequent diagnostics examine when fitting the response operator to the desired future yields a short-horizon benefit, and whether that benefit transfers.

## Results and limits

In an eight-history, accuracy-stable CIFAR10 follow-up, rank-16 sixteen-update reconstruction error decreases from **0.965 to 0.838** on the fitted future and from **0.924 to 0.850** on an alternate future. The declared interaction test fails (**p = .145**), so these improvements remain descriptive.

At sixty-four updates, rank-16 error exceeds zero-response prediction in every history on both futures. Substantial retained response magnitude can coexist with weak directional alignment. Short-horizon improvement therefore does not, by itself, establish causal sufficiency.

## Manuscript and reconstruction evidence

- [Read the research manuscript (PDF)](paper.pdf)
- [Frozen supplementary package and restoration instructions](supplement/README.md)

The supplement preserves saved arrays, experiment receipts, CPU verification utilities, and reconstruction procedures. It supports checking retained results; it does not include every original full training checkpoint or provide a fresh rerun of every neural experiment.

The public manuscript copy corrects the stale conference-template footer that said it was under AISTATS review. The scientific text and results are preserved. The supplied anonymous supplement remains a frozen archive; historical internal filenames do not change the displayed research title.
