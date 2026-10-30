# Project files and integrity checks

[Project](../README.md) · [Timeline](../docs/RESEARCH_TIMELINE.md)

## Current files

| Record | Purpose |
| --- | --- |
| [FILE_INDEX.csv](FILE_INDEX.csv) | Complete current project-file inventory, including later follow-ups and source reviews. |
| [PATH_MAP.csv](PATH_MAP.csv) | Original file moves. `old_sha256` preserves the source identity; `new_sha256` records the current destination bytes. Later additions are listed in the file index rather than invented as old moves. |
| [Repository checksum index](../../../ARTIFACT_CHECKSUMS.json) | Current file sizes and SHA-256 values; excludes the checksum index itself. |
| [30 October documentation review](REPOSITORY_REVIEW_2026-10-30.json) | Scope of the documentation repair and checks actually performed. |

## Run the layout check

From this project folder:

```sh
python verification/verify_layout.py
```

The checker uses only the Python standard library. It checks complete file-index coverage, local Markdown/Colab targets, Python compilation, notebook execution metadata and embedded payload hashes, ZIP CRCs, current file checksums, and destination hashes in the move map.

The three previously shared notebook URLs are byte-identical aliases. Four canonical notebooks retain their original execution records and embedded inputs. Original scientific scripts, inputs, protocols, result tables and run ZIPs are unchanged by the documentation repair.

## What was corrected on 30 October

- Refreshed the complete file index to include the additional evidence and dated follow-up files.
- Refreshed move-map destination hashes after documentation edits, while preserving the original source hashes.
- Corrected the distinction between numerical receptor records and numerical human-saltiness observations.
- Added a dated research timeline and one clearly identified current test plan.
- Updated documentation manifests and the repository checksum index.

The initial audit found a stale README destination hash and an incomplete file index. Both were corrected. The checker now also rejects missing or duplicate inventory entries, so an incomplete index cannot silently pass.

**Latest verification, 30 October:** the documented Python command passed. It checked the current file inventory, four notebook payloads, three notebook aliases, three run-archive CRCs, navigation and current hashes. A temporary copy with an intentionally omitted index entry was correctly rejected. The [review record](REPOSITORY_REVIEW_2026-10-30.json) records the scope and results. These checks inspect saved artifacts; they do not execute the notebooks or rerun the scientific analyses.

## Historical execution and organization records

[ORGANIZATION_REVIEW.json](ORGANIZATION_REVIEW.json) is the dated original organization review, not a receipt for later scientific validation. Individual experiment folders retain execution and source-verification records. Old internal filenames in those records refer to the self-contained notebook or archived execution layout.

These integrity checks establish file consistency and traceability. They do not validate receptor function, human saltiness prediction, a new ingredient or food suitability.
