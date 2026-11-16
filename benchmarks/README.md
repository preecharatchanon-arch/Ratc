# Targeted recovery audit

This audit recovered **17 of 18** benchmark rows stopped by the wrapper watchdog after the algorithmic deadline. One Legacy case remains unresolved. The notebook bundles the data, provenance receipts and exact Legacy and V31 STRICT_FAIR sources. [Inspect the AUDIT4 notebook](Targeted_Recovery_AUDIT4.ipynb).

The embedded sources match the extracted FleetRoute supplement byte for byte:

| Embedded source | SHA-256 |
| --- | --- |
| Legacy STRICT_FAIR | `6225684b27bdc8c1c484d1576e21f069c5dc2229aaaea7ff7223c7f2e84684cc` |
| V31 STRICT_FAIR | `845014863fe646f96969f775f68851411f0ff0ab4586d487a3ade0098a2e8a22` |

The recovery fixes six public instances, the original seeds, six software workers, hard algorithmic budgets, and semantic commands. It independently validates reference routes and scores distance; route count is diagnostic. A longer wrapper grace permits serialization and exit after the algorithmic deadline.

Use these rows for the targeted route-quality recovery under the retained evaluator. The recovery gave the wrapper more time to serialize results after the fixed search deadline. See the [original paired comparison](../projects/fleetroute/README.md#read-the-results-with-their-contracts) for the original run conditions.
