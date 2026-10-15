# TRPV1 receptor-site accessibility test

15 October 2026. Exploratory follow-up to the completed ENaC and sensory work.
The published contact identities and preliminary human membrane depths were
inspected before this protocol. This is not a preregistered discovery experiment.

## Question

Do the TRPV1 residues repeatedly nominated for salty-peptide docking describe
an extracellular peptide-binding site, or a site requiring additional membrane
partitioning/access evidence? A binding score does not answer this question.

## Inputs chosen by experimental relevance

- Ren et al., DOI 10.3389/fnut.2023.1343209: preserve the four explicitly named
  key residues and all eleven major contact residues in the Results, without
  expanding the set from unrelated papers or counting citations as replication.
- Human 8GFA: experimental antagonist-bound TRPV1; directly match published
  human residue names to Q8NER1, not an unverified residue-number offset.
- Squirrel 7LQY: the template actually used by the peptide paper. Align its
  canonical sequence to human before transferring residue labels.
- Rat 5IRX: experimentally bound DkTx peptide agonist and RTX in nanodiscs.
  Use actual toxin contacts as the peptide-site comparator. This is a different
  species, construct and activated state, not an interchangeable replicate.
- Use OPM-oriented coordinates and their dummy-atom boundary planes. OPM
  boundaries are calculated hydrophobic-core boundaries, not directly measured
  outer headgroup surfaces. Confirm OPM coordinates preserve deposited geometry.

## Analyses

1. Map every source residue to canonical human sequence and homologous structures.
   Export mapping identity and resolved/missing status. Compare global alignments
   under match/mismatch/gap settings (2,-1,-2) and (3,-2,-3); do not retain a
   species-transferred conclusion if hotspot mappings differ.
2. Use all four receptor chains per structure. Report CA and heavy-atom depth
   ranges, radial distance to the channel axis, and distance from the positive-z
   extracellular boundary. Determine the extracellular sign from known N-terminal
   cytoplasmic versus outer-pore regions and verify the DkTx location.
3. Boundary sensitivity: shift the membrane centre by -3, 0, +3 A and vary the
   hydrophobic half-thickness by -3, 0, +3 A. Do not interpret a point's z-category
   as a calculated permeability or physical proof that no access route exists.
4. In human 8GFA, calculate nearest distances to resolved phospholipids (POV),
   bound antagonist (ZEI), detergent (DU0) and water separately. Contacts within
   3.5, 4.0 and 5.0 A are descriptive. Lipid neighbours do not establish an
   overlap with an unavailable published docking pose.
5. In rat 5IRX, identify actual receptor-DkTx heavy-atom contacts at the same
   cutoffs, then compare their depth distribution with mapped peptide-paper
   residues. Four chains are structural copies, not four biological replicates.
6. Calculate standard physicochemical descriptors for the four source peptides
   under explicit free-terminus/unmodified-L-peptide assumptions. Approximate
   charge across pH 5-8 is descriptive; do not infer passive permeability from
   one descriptor or apply a small-molecule rule as a peptide exclusion rule.

## Interpretation and stopping rule

No new docking, MD trajectory, model fitting or peptide ranking. The intended
decision is whether to use this literature docking site for an oral-peptide
screen. A positive structural concern changes that decision, while preserving
the authors' sensory findings. DkTx demonstrates that peptides can interact
with membrane-associated TRPV1 sites; it is a venom-derived mechanistic
comparator, not a food candidate. A membrane access concern does not establish
that a peptide cannot act on TRPV1, cannot enhance saltiness, or acts via ENaC.

TMC4 is not assigned an access category in this experiment: its sequence
topology annotations and newer structural models require a separate topology
validation, and the original peptide poses are not available here.
