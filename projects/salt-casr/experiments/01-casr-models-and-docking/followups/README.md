# CaSR follow-up analyses

[Original experiment](../README.md) · [Current project status](../../../docs/RESEARCH_STATUS.md)

The [27 October 2026 package](2026-10-27/README.md) preserves completed CPU
comparisons on the previously inspected 58-compound, 26-family receptor series,
an 11-pair Gly-effect task and an independent check of saved docking poses.
It includes the fixed exploratory protocol, code, fold predictions and
execution records. These are follow-ups to Experiment 01, not independent
biological confirmation or an additional successful discovery experiment.

The positional-model MAE gain over the existing nearest-three model is 0.0337
log units, with conditional family-bootstrap 95% interval [-0.1104,0.1553].
The interval crosses zero. The 11-pair gain interval also crosses zero.
Independent spyrmsd confirms the native top-pose RMSD of 4.7803 Å. These findings
do not justify a model sweep, broad docking screen or MD escalation.

The dated package's literature priorities are historical. The current
[evidence guide](../../../evidence-review/README.md),
[research status](../../../docs/RESEARCH_STATUS.md) and
[test design](../../../docs/NEXT_TEST_DESIGN.md) control subsequent work.
No scientific experiment was rerun while publishing and organizing this copy.


## 29 October local relaxation diagnostic

The [new dated diagnostic](2026-10-29-local-relaxation/README.md) starts from
the experimental bound pose and preserves a near-reference local minimum,
but the displaced pose still scores better. Its combined gate failed and
conditional Stage2 was not executed. Frozen design, minimal source inputs,
actual outputs and reproduction instructions are included. This is a separate
exploratory method diagnosis, not a repaired or validated screening workflow.
