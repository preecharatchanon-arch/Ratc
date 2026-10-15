# Project organization and integrity review

[Project overview](../README.md)

[ORGANIZATION_REVIEW.json](ORGANIZATION_REVIEW.json) records the completed review. [PATH_MAP.csv](PATH_MAP.csv) maps every pre-organization project file to its current canonical location and records content hashes. [FILE_INDEX.csv](FILE_INDEX.csv) lists the current files by experiment and role. The repository-wide [checksum index](../../../ARTIFACT_CHECKSUMS.json) covers the organized release.

Review scope: file preservation; notebook code/output preservation and embedded payload hashes; local Markdown, image and Colab paths; script compilation and relocated input paths; archived ZIP integrity; independent recomputation from retained results; and selected short local execution checks. A folder reorganization is not a new biological experiment or a blanket guarantee of scientific validity.

The three previously shared notebook URLs remain byte-identical runnable aliases. Experiment 05 adds a fourth canonical notebook with its own execution and artifact records. Canonical notebooks are listed under numbered experiment folders. Original execution records remain with their experiments; their old internal filenames refer to the self-contained notebook or archived run, not a claim that the old repository layout still exists.

Current scientific status is in [RESEARCH_STATUS.md](../docs/RESEARCH_STATUS.md). Existing uncertainties about data provenance, endpoint mismatch, external validation, peptide access and food suitability are retained in the experiment reports.

From the project folder, run `python verification/verify_layout.py` to check navigation, notebook payloads, archive integrity and current file checksums. This uses only the Python standard library.
