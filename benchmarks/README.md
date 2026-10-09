# Targeted recovery audit

[Open the AUDIT4 notebook](Targeted_Recovery_AUDIT4.ipynb).

This notebook reruns only **18 parent benchmark rows** terminated by the wrapper's post-deadline watchdog. It embeds a compact ZIP payload with data, provenance receipts, and the exact Legacy and V31 STRICT_FAIR sources. It does **not** contain a third, Current solver despite the historical notebook filename.

The embedded sources match the extracted FleetRoute supplement byte for byte:

| Embedded source | SHA-256 |
| --- | --- |
| Legacy STRICT_FAIR | `6225684b27bdc8c1c484d1576e21f069c5dc2229aaaea7ff7223c7f2e84684cc` |
| V31 STRICT_FAIR | `845014863fe646f96969f775f68851411f0ff0ab4586d487a3ade0098a2e8a22` |

The recovery fixes six public instances, the original seeds, six software workers, hard algorithmic budgets, and semantic commands. It independently validates reference routes and scores distance; route count is diagnostic. A longer wrapper grace permits serialization and exit after the algorithmic deadline.

The notebook is evidence for targeted recovery, rather than a full rerun of the parent benchmark or an OR-Tools comparison. Recovery runtime is explicitly non-comparable to parent runtime. Saved outcomes in the submission supplement report 17 valid recoveries and one unresolved Legacy case.
