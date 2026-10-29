# Bound-pose local optimization diagnostic

Frozen before execution, 29 October 2026, Asia/Bangkok. Exploratory method
diagnosis on a previously inspected reference; not independent confirmation,
a candidate screen, measured receptor activity or a human sensory experiment.

The latest checkpoint version23 was read. The user invited continued testing
and conditional docking/unknown-peptide work. The completed docking protocol
does not justify screening unmeasured candidates. This bounded diagnostic
addresses one specific unresolved failure before considering any such step.

## Evidence motivating the test

The saved higher-search run has observed-pose Vina score-3.193 and top returned
score-6.998 kcal/mol, at top RMSD4.4356Angstrom in the receptor frame. Increasing
search effort to16 did not recover a top reference-like pose. The original
panel top RMSD4.7803 was independently checked earlier; it is not rerun here
as a new result. The PDB9J7I model is a3.55Angstrom cryo-EM reconstruction:
its ligand coordinates are an experimental model, not exact ground truth.

## Stage1 test card

**Hypothesis:** the unrelaxed deposited ligand starts at an unfavorable local
geometry under the fixed preparation/scoring model. Local relaxation can
produce a competitive score while retaining a reference-like pose.

**Competing explanation:** the rigid receptor/ligand-state/scoring model
prefers a displaced pose, even after the deposited pose is locally relaxed.
Insufficient global search alone would then not explain the whole problem.
Missing receptor flexibility, ligand-state uncertainty and uncertain deposited
coordinates are not adjudicated by this test.

**Eligible actual data:** exactly the archived9J7I receptor PDBQT, deposited
gamma-EVG SDF, higher-search pose file and its summary from the original
CaSR_Notebook_Run.zip. Preserve archived bytes and hashes. Use the original
charge convention: carboxylates negative and free primary amine positive.
No ligand or receptor reparameterization, cofactor insertion, box change,
alternative forcefield, training or new peptide is permitted in this test.

**Independent unit:** one deposited receptor/peptide complex. Optimization
steps and algorithm seeds are not independent biological samples. Results
cannot estimate an across-target or across-peptide success rate.

**Primary comparison:** the locally optimized deposited pose versus the frozen
higher-search top pose, rescored with the same Vina1.2.7 model and an explicit
common unbound-energy reference of0.0. Record ordinary default scores too, but
do not mix them into the common-reference comparison. Require identical
isomeric molecular graphs and rotatable-bond counts. Use the frozen receptor,
box and ligand chemistry. Locally optimize only the deposited pose once,
max_steps5000, seed777, two CPU threads. Do not globally redock at Stage1.

**Meaningful diagnostic criterion:** support the local-geometry explanation
only if the locally relaxed ligand stays at symmetry-corrected heavy-atom
RMSD<=2.0Angstrom without alignment AND scores more favorably than the
rescored frozen displaced pose by more than0.001 score units. The score
tolerance reflects output precision and determines a ranking decision; it is
not a thermodynamic or sensory-effect margin. A tie is unresolved. The2Angstrom
criterion is conventional pose-validation practice, not a confidence radius
for this cryo-EM ligand. Report the continuous RMSD and score differences.

**Uncertainty:** no biological CI or p-value is warranted for this single-case
calculation. Record input coordinates, versions, charge state, receptor/box,
energy vectors, optimization limit and no-alignment RMSD. Independently check
RMSD using graph-symmetry matching; preserve possible nonconvergence. The API
does not supply a verified optimization-convergence flag, so reaching the
criterion does not prove an exact local minimum. Do not call this a validated
binding affinity or infer calcium-dependent functional activation from it.

**Decision:** if Stage1 fails, stop before any new search or unknown-peptide
screen and document the specific failure. If Stage1 passes, execute only the
Stage2 card below. Either result leaves human saltiness and functional-ranking
validation unresolved. No broad screen or MD follows automatically.

## Stage2 conditional card — execute only after Stage1 passes

**Hypothesis:** an independently embedded gamma-EVG starting geometry can
recover the competitive reference-like basin reproducibly under the same
unchanged preparation/model. **Competitor:** supplying near-native coordinates
is necessary; unseeded global search still misses or misranks the basin.

**Actual data:** the same fixed receptor, reference and original independently
generated ligand input from the archive. If its graph or torsion count differs,
stop rather than silently changing the ligand. **Unit:** the same single
complex, with three algorithmic repetitions; not three peptide experiments.

**Primary comparison:** three new search seeds104729,130363,155921, each
exhaustiveness16, requested20 poses, two CPU threads, unchanged box. Evaluate
the top-ranked pose by no-alignment symmetry-corrected heavy-atom RMSD and
report all returned RMSDs/energies. Do not select the best seed or report only
the closest pose as top-pose success.

**Criterion:** all three top poses must have RMSD<=2.0Angstrom. Any failure
leaves a reproducible-search prerequisite unmet. **Uncertainty:** report the
three outcomes descriptively, without treating seeds as biological replication
or inventing a population CI. **Next decision:** a pass qualifies only this
reference recovery under these settings. It does not validate activity ranking,
unknown-peptide binding, sensory benefit, novelty, safety or food use. A fail
stops additional docking in this continuation. No tuning/sweep follows.

## Primary methodological references

- Trott/Olson, original Vina paper, DOI10.1002/jcc.21334: conventional2Angstrom
  pose criterion; it is not a sensory threshold.
- Official Vina Python tutorial:
  https://autodock-vina.readthedocs.io/en/latest/docking_python.html
- Yamaguchi etal., DOI10.1038/s41598-025-87999-1 and PDB9J7I: deposited
  gamma-EVG recognition structure and its experimental limitations.
