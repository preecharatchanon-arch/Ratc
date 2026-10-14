"""Reproduce the receptor preparation used for this exploratory docking run."""
import sys, subprocess
from pathlib import Path
import gemmi

root=Path(__file__).resolve().parent
structure=gemmi.read_structure(str(root.parent/'toolkit_pilot/sources/9J7I.cif'))
for chain in list(structure[0]):
    if chain.name!='A': del structure[0][chain.name]
output=root/'sources/casr_binding_domain.pdb';output.parent.mkdir(exist_ok=True)
structure.write_pdb(str(output))
subprocess.run([sys.executable,'-m','meeko.cli.mk_prepare_receptor','--read_pdb',str(output),'-o',str(root/'results/casr'),'-p','-j','--box_enveloping',str(root.parent/'toolkit_pilot/results/native_gamma_EVG.sdf'),'--padding','6','--delete_bad_res_from_box_radius','6'],check=True)
