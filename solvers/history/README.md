# Original solver development history

Six original notebook-cell exports are preserved unchanged, with dates verified against their original GitHub commits. All timestamps below use **Asia/Bangkok (UTC+07:00)** and the Gregorian year.

**Browse:** [Solver versions](../README.md) · [Current source and run instructions](../current/README.md) · [Live repository history](https://github.com/preecharatchanon-arch/Ratc/commits/main/)

## Original commits and preserved files

| Original commit date (UTC+07:00) | Preserved file | Lines | Original commit | Unchanged Git blob SHA |
| --- | --- | ---: | --- | --- |
| 2026-05-09 13:27:42 | [original-solv.colab.txt](original-solv.colab.txt) | 9,862 | [`6882e21`](https://github.com/preecharatchanon-arch/Ratc/commit/6882e215248c163494d2eded3ae2364901da8c7f) | `8cdb6024816fc4847370431b8578a276cec9ed5b` |
| 2026-05-09 15:28:38 | [operator-pruning.colab.txt](operator-pruning.colab.txt) | 5,752 | [`c3db7a6`](https://github.com/preecharatchanon-arch/Ratc/commit/c3db7a6e24f9a2a1ea29c759120443542481b4fb) | `8b354b988fdb12d9492ee21bba640df1816c1c58` |
| 2026-05-12 13:59:03 | [euclidean-experiment.colab.txt](euclidean-experiment.colab.txt) | 6,626 | [`44ed403`](https://github.com/preecharatchanon-arch/Ratc/commit/44ed4033f7f9771d8a6b4e1ba6311cb1304b942a) | `0ae78306b9ab3b3b932389dd8f3cc81aa13436d1` |
| 2026-05-18 17:38:33 | [hgs-experiment.colab.txt](hgs-experiment.colab.txt) | 7,255 | [`57c7c03`](https://github.com/preecharatchanon-arch/Ratc/commit/57c7c0310a7c47d6668ef937557b8189021b8664) | `b0cfc4142748f809f07d12e36491ccaa569400b1` |
| 2026-05-18 19:34:39 | [a-n60-k9-tuning.colab.txt](a-n60-k9-tuning.colab.txt) | 7,583 | [`f075c46`](https://github.com/preecharatchanon-arch/Ratc/commit/f075c466de62ee7123fbe104f94942a9978bc402) | `57efc2bbda983d679144ee287baadcf8d23d9299` |
| 2026-05-27 20:42:35 | [fragment-lns-experiment.colab.txt](fragment-lns-experiment.colab.txt) | 8,251 | [`8217a0f`](https://github.com/preecharatchanon-arch/Ratc/commit/8217a0f2a3e133f582013c76ab1796906d766ba0) | `887cb9cbfad1384c5ae2e2a9734c11c8e496cf04` |

The file-content identities in this table were checked against both the original commit entries and the current repository tree. These are **Git blob SHA-1 identities**, not commit hashes or SHA-256 checksums. Original commit dates record publication of these particular files; they do not establish when each experiment began.

## Original filename mapping

The original filenames are retained here verbatim for traceability.

| Preserved file | Original repository filename |
| --- | --- |
| [original-solv.colab.txt](original-solv.colab.txt) | `solv` |
| [operator-pruning.colab.txt](operator-pruning.colab.txt) | `del sm unused algos` |
| [euclidean-experiment.colab.txt](euclidean-experiment.colab.txt) | `euclidean, bads algos, wastes time` |
| [hgs-experiment.colab.txt](hgs-experiment.colab.txt) | `add hgs` |
| [a-n60-k9-tuning.colab.txt](a-n60-k9-tuning.colab.txt) | `good, got 1.11% gap from a-n60-k9 consistenly from bks after tuning config` |
| [fragment-lns-experiment.colab.txt](fragment-lns-experiment.colab.txt) | `from 1380-ish - 1360(rng) to 1365- 1358 bks 1354, after i addd long route target in fragment lns` |

## October reorganization

The files were moved under `solvers/history/` on **2026-10-10 07:50:44 UTC+07:00** in [`3629887`](https://github.com/preecharatchanon-arch/Ratc/commit/3629887014d78fa493e7573c77006feb1bb1bcfb). Their original May blob hashes are unchanged. This organization date is separate from the original publication dates above.

These exports contain Colab cell directives such as `%%writefile solver.cpp` followed by C++ source. They are historical notebook cells, not standalone `.cpp` translation units. For identified Current, V31, Legacy and benchmark sources, start with the [solver index](../README.md).

The original filenames contain informal experiment notes. Their performance figures are historical observations, not a replacement for the frozen benchmark tables. The chronological order here is the verified Git commit order, not an inferred order of experiment execution.
