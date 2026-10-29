"""Execute the frozen single-complex diagnostic; no unknown-peptide screen."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
import time

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMolAlign
from meeko import MoleculePreparation, PDBQTWriterLegacy, PDBQTMolecule, RDKitMolCreate
from spyrmsd import molecule as symm_molecule, rmsd as symm_rmsd
from vina import Vina

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input"
OUT = ROOT / "output"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    path = OUT / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def charge_state(mol):
    """Reuse the original fixed-charge hypothesis, not a measured pKa."""
    mol = Chem.Mol(mol)
    for _, _, oxygen in mol.GetSubstructMatches(Chem.MolFromSmarts("[CX3](=[OX1])[OX2H]")):
        atom = mol.GetAtomWithIdx(oxygen)
        atom.SetFormalCharge(-1)
        atom.SetNumExplicitHs(0)
        atom.SetNoImplicit(True)
    for (nitrogen,) in mol.GetSubstructMatches(Chem.MolFromSmarts("[NX3;H2;!$(NC=O)]")):
        atom = mol.GetAtomWithIdx(nitrogen)
        atom.SetFormalCharge(1)
        atom.SetNumExplicitHs(3)
        atom.SetNoImplicit(True)
    Chem.SanitizeMol(mol)
    return mol


def identity(mol):
    return Chem.MolToSmiles(Chem.RemoveHs(mol), canonical=True, isomericSmiles=True)


def decode(pdbqt):
    mols = RDKitMolCreate.from_pdbqt_mol(PDBQTMolecule(pdbqt, skip_typing=True))
    if len(mols) != 1 or mols[0] is None:
        raise ValueError("Expected one reconstructed molecular graph")
    return Chem.RemoveHs(mols[0])


def first_model(pdbqt):
    if not any(line.startswith("MODEL") for line in pdbqt.splitlines()):
        return pdbqt
    block = []
    inside = False
    for line in pdbqt.splitlines():
        if line.startswith("MODEL"):
            inside = True
            continue
        if inside and line.startswith("ENDMDL"):
            return "\n".join(block) + "\n"
        if inside:
            block.append(line)
    raise ValueError("Incomplete first MODEL")


def torsdof(text):
    match = re.search(r"^TORSDOF\s+(\d+)\s*$", text, re.M)
    if not match:
        raise ValueError("Missing ligand torsion count")
    return int(match.group(1))


def main():
    start = time.monotonic()
    OUT.mkdir(exist_ok=True)
    if (OUT / "results.json").exists():
        raise RuntimeError("Completed results exist; do not silently rerun or overwrite")
    protocol = json.loads((ROOT / "protocol.json").read_text())
    cfg = protocol["settings"]
    if digest(ROOT / "PROTOCOL.md") != protocol["protocol_sha256"]:
        raise ValueError("Frozen protocol changed")
    for row in protocol["inputs"]:
        if digest(INPUT / row["file"]) != row["sha256"]:
            raise ValueError("Frozen input changed: " + row["file"])
    expected_versions = {
        "vina": "1.2.7", "meeko": "0.8.0", "rdkit": "2025.9.3",
        "numpy": "2.2.6", "scipy": "1.15.3", "gemmi": "0.7.5", "spyrmsd": "0.9.0",
    }
    versions = {name: importlib.metadata.version(name) for name in expected_versions}
    if versions != expected_versions:
        raise RuntimeError("Environment differs from the frozen method versions")
    ref = next(m for m in Chem.SDMolSupplier(str(INPUT / "native_gamma_EVG.sdf")) if m is not None)
    ref = charge_state(Chem.RemoveHs(ref))
    xyz = np.array(ref.GetConformer().GetPositions())
    center = xyz.mean(0).tolist()
    box = (np.ptp(xyz, axis=0) + 12).tolist()
    setup = MoleculePreparation().prepare(Chem.AddHs(ref, addCoords=True))[0]
    native_text, ok, error = PDBQTWriterLegacy.write_string(setup)
    if not ok:
        raise RuntimeError(error)
    (OUT / "native_prepared.pdbqt").write_text(native_text)
    frozen_text = first_model((INPUT / "frozen_high_search.pdbqt").read_text())
    independent_text = (INPUT / "independent_start.pdbqt").read_text()
    graphs = {key: identity(decode(text)) for key, text in {
        "native_prepared": native_text, "frozen_top": frozen_text, "independent_start": independent_text,
    }.items()}
    if set(graphs.values()) != {identity(ref)}:
        raise ValueError("Input isomeric molecular graphs differ")
    torsions = {key: torsdof(text) for key, text in {
        "native_prepared": native_text, "frozen_top": frozen_text, "independent_start": independent_text,
    }.items()}
    if len(set(torsions.values())) != 1:
        raise ValueError("Input torsion counts differ")
    reference_symm = symm_molecule.Molecule.from_rdkit(ref)

    def rmsds(mol):
        values = []
        for conf in mol.GetConformers():
            temp = Chem.Mol(mol)
            temp.RemoveAllConformers()
            temp.AddConformer(Chem.Conformer(conf), assignId=True)
            match = symm_molecule.Molecule.from_rdkit(temp)
            a = float(symm_rmsd.symmrmsd(
                reference_symm.coordinates, match.coordinates,
                reference_symm.atomicnums, match.atomicnums,
                reference_symm.adjacency_matrix, match.adjacency_matrix,
                center=False, minimize=False,
            ))
            b = float(rdMolAlign.CalcRMS(temp, ref))
            if abs(a - b) > 1e-6:
                raise ValueError("Independent RMSD calculations disagree")
            values.append(a)
        return values

    def engine(text, seed):
        v = Vina(sf_name="vina", cpu=cfg["cpu"], seed=seed, verbosity=0)
        v.set_receptor(str(INPUT / "receptor.pdbqt"))
        v.compute_vina_maps(center=center, box_size=box)
        v.set_ligand_from_string(text)
        return v

    result = {
        "status": "running_stage1", "scope": protocol["scope"],
        "protocol_sha256": protocol["protocol_sha256"],
        "script_sha256": digest(Path(__file__)),
        "python": platform.python_version(), "versions": versions,
        "environment_distributions": {x.metadata["Name"]: x.version for x in importlib.metadata.distributions(path=[str(ROOT / "deps")])},
        "center_A": center, "box_size_A": box,
        "input_graphs": graphs, "torsion_counts": torsions,
        "net_formal_charge": Chem.GetFormalCharge(ref), "heavy_atoms": ref.GetNumAtoms(),
        "statistical_CI": None, "independent_complexes": 1,
        "no_human_or_functional_assay_result": True,
        "unknown_peptides_screened": 0,
    }
    save("progress.json", result)
    frozen_engine = engine(frozen_text, cfg["seed"])
    frozen_default = frozen_engine.score().tolist()
    frozen_common = frozen_engine.score(unbound_energy=cfg["common_unbound_energy"]).tolist()
    native_engine = engine(native_text, cfg["seed"])
    native_default = native_engine.score().tolist()
    native_common = native_engine.score(unbound_energy=cfg["common_unbound_energy"]).tolist()
    archived = json.loads((INPUT / "frozen_high_search_summary.json").read_text())
    compatibility = {
        "native_default_delta_from_archive": native_default[0] - archived["observed_native_score_kcal_mol"],
        "top_default_delta_from_archive": frozen_default[0] - archived["best_scoring_pose_score"],
    }
    # Record these diagnostics even if the archived output used another implicit
    # intramolecular reference; the primary comparison explicitly rescored both.
    relaxed_default = native_engine.optimize(max_steps=cfg["local_max_steps"]).tolist()
    relaxed_common = native_engine.score(unbound_energy=cfg["common_unbound_energy"]).tolist()
    pose_path = OUT / "native_locally_relaxed.pdbqt"
    native_engine.write_pose(str(pose_path), overwrite=False)
    relaxed = decode(pose_path.read_text())
    if identity(relaxed) != identity(ref):
        raise ValueError("Local optimization changed molecular identity")
    relaxed_rmsd = rmsds(relaxed)[0]
    score_advantage = frozen_common[0] - relaxed_common[0]
    stage1_pass = relaxed_rmsd <= cfg["RMSD_max_A"] and score_advantage > cfg["score_precision_tolerance"]
    with Chem.SDWriter(str(OUT / "native_locally_relaxed.sdf")) as writer:
        writer.write(relaxed)
    result["stage1"] = {
        "native_before_default_energy_vector": native_default,
        "native_before_common_reference_energy_vector": native_common,
        "frozen_wrong_top_default_energy_vector": frozen_default,
        "frozen_wrong_top_common_reference_energy_vector": frozen_common,
        "locally_relaxed_default_energy_vector": relaxed_default,
        "locally_relaxed_common_reference_energy_vector": relaxed_common,
        "common_unbound_reference": cfg["common_unbound_energy"],
        "locally_relaxed_RMSD_A": relaxed_rmsd,
        "frozen_wrong_top_RMSD_A": rmsds(decode(frozen_text))[0],
        "relaxed_score_advantage_over_wrong_pose": score_advantage,
        "coordinate_RMSD_crosscheck": "spyrmsd and RDKit agree <=1e-6A; no centering/alignment",
        "archived_default_score_comparison": compatibility,
        "support_for_competitive_local_reference_basin": bool(stage1_pass),
        "verified_optimization_convergence": None,
    }
    result["status"] = "stage1_complete"
    save("progress.json", result)
    print(json.dumps({"stage1": result["stage1"]}), flush=True)
    stage2 = []
    if stage1_pass:
        for seed in cfg["stage2_seeds"]:
            job_start = time.monotonic()
            v = engine(independent_text, seed)
            v.dock(exhaustiveness=cfg["stage2_exhaustiveness"], n_poses=cfg["stage2_poses"])
            output = OUT / f"new_seed_{seed}.pdbqt"
            v.write_poses(str(output), n_poses=cfg["stage2_poses"], overwrite=False)
            mol = decode(output.read_text())
            if identity(mol) != identity(ref):
                raise ValueError("New search returned a different molecular identity")
            errors = rmsds(mol)
            energies = v.energies(n_poses=cfg["stage2_poses"]).tolist()
            if len(errors) != len(energies):
                raise ValueError("Energy and pose counts differ")
            row = {
                "seed": seed, "top_RMSD_A": errors[0], "best_RMSD_A": min(errors),
                "top_meets_RMSD_criterion": errors[0] <= cfg["RMSD_max_A"],
                "all_pose_RMSD_A": errors, "all_energy_vectors": energies,
                "runtime_seconds": time.monotonic() - job_start,
            }
            stage2.append(row)
            result["stage2"] = stage2
            result["status"] = "running_stage2"
            save("progress.json", result)
            print(json.dumps({"stage2_seed": seed, "top_RMSD_A": errors[0]}), flush=True)
    result["stage2"] = stage2
    result["stage2_executed"] = bool(stage2)
    result["stage2_pass"] = bool(len(stage2) == 3 and all(x["top_meets_RMSD_criterion"] for x in stage2))
    result["status"] = "complete"
    result["runtime_seconds"] = time.monotonic() - start
    result["decision"] = (
        "Only this reference search prerequisite passed; activity ranking and human selection remain unvalidated. No unknown screen."
        if result["stage2_pass"] else
        "Stop docking expansion: a competitive local-reference basin or reproducible top-pose recovery prerequisite remains unmet. No unknown screen."
    )
    save("results.json", result)
    save("progress.json", result)
    print(json.dumps({"complete": True, "decision": result["decision"], "runtime_seconds": result["runtime_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
