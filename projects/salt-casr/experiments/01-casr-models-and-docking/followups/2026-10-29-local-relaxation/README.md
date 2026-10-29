# CaSR bound-pose diagnostic: local relaxation helps, ranking remains unresolved

29 October 2026, Asia/Bangkok. One new exploratory computational diagnostic
was executed after writing and freezing `PROTOCOL.md` and `protocol.json`.
The prior written research plan was read before deciding on work.

The question was whether local relaxation of the deposited gamma-EVG pose
could explain its previously poor Vina score without displacing it far from
the experimental model. This was a method-repair test, not a peptide screen,
a new receptor experiment or a human taste result.

## Actual result

Lower score is more favorable within this scoring model. These are program
outputs, not measured affinities or uncertainty-supported binding energies.

| Pose | Heavy-atom RMSD to deposited reference, Angstrom | Default Vina score | Score using common unbound reference0 |
|---|---:|---:|---:|
| Deposited reference before local relaxation | Reference | -3.193 | -3.329 |
| Reference after local relaxation | 0.594806 | -6.643 | -7.021 |
| Frozen higher-search top pose | 4.435575 | -6.998 | -7.828 |

The first and third default scores exactly reproduce the archived values.
The local calculation took4.26seconds including validation/maps/scoring.
Symmetry-corrected RMSD from spyrmsd and RDKit agreed within1e-6Angstrom,
without alignment or centering. All three inputs had the same isomeric graph,
21 heavy atoms,10 active torsions and the fixed net formal charge-1.

**The combined Stage1 criterion failed.** Local relaxation stayed within the
frozen2Angstrom criterion, but the displaced pose remained better ranked.
The locally relaxed pose trails by0.807 score units with the common reference,
and by0.355 under ordinary default scoring. The ranking direction agrees under
both conventions. These small uncalibrated score differences do not establish
physical affinity differences.

This is a partial diagnosis: much of the original apparent score deficit came
from comparing an unrelaxed reference with optimized search poses. The
reference neighborhood can support a locally relaxed pose. It has not been
shown to win the ranking. This does not prove that no other reference-like
minimum could score better, or that global search alone can never help.

**Stage2 was not executed**, as required by the frozen conditional rule.
No new global docking, three-seed search, unknown-peptide screen, model sweep
or MD followed. Starting local optimization from known bound coordinates is
not successful de novo pose prediction or independent screening validation.

## Supporting preparation audit

The later `check_preparation.py` audit is explicitly post-hoc input integrity,
not another scientific test. Deposited heavy atoms for Pro39, Phe42, Arg66,
Ser147, Ser170 and Glu297 are present in the archived prepared receptor with
zero coordinate change at stored precision. This rules out deletion of those
selected atoms as the immediate explanation; it does not validate protonation,
atom types, missing parts of the receptor, cofactors, flexibility or state.
Its full output is `output/posthoc_preparation_audit.json`.

## Decision for unknown peptides

Do not use this preparation/scoring protocol for a broad unknown-peptide screen.
This single-case test leaves a pose-ranking prerequisite unresolved, and the
previous restricted functional-ordering comparison also remains unfavorable.
Passing one native-pose test would still not establish prediction of CaSR
activation, human saltiness or novelty.

Do not solve this by changing forcefields, boxes, charge states or restraints
until the same inspected reference passes, then calling that confirmation.
A future method change needs a specific rationale, a frozen comparison and
additional suitable evaluation cases or actual measured functional controls.
One score-selected unmeasured analogue is a proposal, not an effective compound.
The22 previously generated combinations remain prior proposals; they were not
rediscovered or promoted by this test.

The main human-saltiness project still lacks a qualified matched candidate
panel and practical effect margin. This structural diagnostic neither supplies
those measurements nor makes missing tests negative. Receptor response,
saltiness, kokumi, liking and actual sodium reduction remain separate.

## Reproduce deliberately

Python3.12 and pinned binary packages are required. The full resolved package
versions from the executed environment are in `requirements_resolved.txt`.
No external article download, API key, GPU or archive upload is required.
The small archived input subset is included with original member paths/hashes
in `protocol.json`. The deposited9J7I coordinates are included for the separate
preparation audit; no publisher article or figure is redistributed.

To reproduce in a new copy of this folder:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python --only-binary :all: -r requirements_resolved.txt
mv output reviewed_output
.venv/bin/python run_diagnostic.py
.venv/bin/python check_preparation.py
```

The script refuses to overwrite completed results. Moving the reviewed output
keeps the actual original run; a rerun does not become independent confirmation.
In a fresh virtual environment, `environment_distributions` may be empty because
the original run used a target dependency directory; named method versions are
still checked explicitly. Stage2 is conditional, so total runtime is outcome-
dependent. Its three searches were not run in this saved result.

## Files and provenance

- `PROTOCOL.md`, `protocol.json`: pre-execution design/settings/input hashes.
- `run_diagnostic.py`: Stage1 plus the frozen conditional Stage2.
- `input/`: archived receptor, reference, independent start and old higher-search
  poses/summary; deposited9J7I CIF for post-hoc integrity only.
- `output/results.json`: actual new result, energy vectors, no-alignment RMSD,
  versions, input graph/torsion checks and the stop decision.
- `output/native_locally_relaxed.*`: actual generated local pose.
- `check_preparation.py`: post-hoc selected-heavy-atom preservation check.

The source archive SHA256 is
`51b265c5d3acc3e0b07183160ce03a69929ad479ed186ef337cf44f7b3378129`.
It is the previously inspected run, not newly acquired experimental data.

Primary sources:
[9J7I deposition](https://www.rcsb.org/structure/9J7I),
[Yamaguchi2025](https://doi.org/10.1038/s41598-025-87999-1),
[Vina original paper](https://doi.org/10.1002/jcc.21334),
[official local-optimization documentation](https://autodock-vina.readthedocs.io/en/latest/docking_python.html).
The2Angstrom rule is conventional pose validation, not a coordinate confidence
radius for the3.55Angstrom cryo-EM model or a meaningful human taste effect.

No new biological activity, effective food compound, human benefit, food-use
approval or sodium reduction is claimed. This is a public copy of the saved diagnostic.
