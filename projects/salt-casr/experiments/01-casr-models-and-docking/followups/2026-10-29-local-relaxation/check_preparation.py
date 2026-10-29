"""Post-hoc input integrity audit, not a new activity or docking test."""
from pathlib import Path
import hashlib
import json

import gemmi
import numpy as np

ROOT = Path(__file__).resolve().parent


def main():
    source = ROOT / "input" / "9J7I.cif"
    prepared = ROOT / "input" / "receptor.pdbqt"
    deposited = gemmi.read_structure(str(source))
    observed = {}
    for residue in deposited[0]["A"]:
        observed[residue.seqid.num] = {
            "name": residue.name,
            "atoms": {a.name.strip(): np.array([a.pos.x, a.pos.y, a.pos.z])
                      for a in residue if a.element.name not in ("H", "D")},
        }
    pdbqt_atoms = {}
    for line in prepared.read_text().splitlines():
        if line.startswith(("ATOM", "HETATM")):
            atom_type = line[77:].strip()
            if atom_type not in ("H", "HD"):
                key = int(line[22:26])
                pdbqt_atoms.setdefault(key, {})[line[12:16].strip()] = np.array(
                    [float(line[30:38]), float(line[38:46]), float(line[46:54])])
    rows = []
    for number in (39, 42, 66, 147, 170, 297):
        original = observed[number]
        actual = pdbqt_atoms.get(number, {})
        common = set(original["atoms"]) & set(actual)
        rows.append({
            "author_residue": number, "source_name": original["name"],
            "source_heavy_atoms": len(original["atoms"]),
            "prepared_heavy_atoms": len(actual),
            "missing_heavy_atom_names": sorted(set(original["atoms"]) - set(actual)),
            "max_matching_atom_displacement_A": max(
                float(np.linalg.norm(original["atoms"][name] - actual[name])) for name in common),
        })
    report = {
        "scope": "post-hoc source/input integrity; no new model or optimization",
        "source_PDB": "9J7I", "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "receptor_sha256": hashlib.sha256(prepared.read_bytes()).hexdigest(),
        "selected_contact_residues": rows,
        "limit": "Heavy-atom preservation does not validate protonation, atom types, complete receptor state or a functional model.",
    }
    output = ROOT / "output" / "posthoc_preparation_audit.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
