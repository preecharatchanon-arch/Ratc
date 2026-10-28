"""Independent RMSD check of the original archive, without new docking."""
import argparse,ast,hashlib,io,json,zipfile
from pathlib import Path
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMolAlign
from spyrmsd import rmsd,molecule

def charge_state(mol):
    m=Chem.Mol(mol)
    for c,o,oh in m.GetSubstructMatches(Chem.MolFromSmarts('[CX3](=[OX1])[OX2H]')):
        a=m.GetAtomWithIdx(oh);a.SetFormalCharge(-1);a.SetNumExplicitHs(0);a.SetNoImplicit(True)
    for match in m.GetSubstructMatches(Chem.MolFromSmarts('[NX3;H2;!$(NC=O)]')):
        a=m.GetAtomWithIdx(match[0]);a.SetFormalCharge(1);a.SetNumExplicitHs(3);a.SetNoImplicit(True)
    Chem.SanitizeMol(m);return m

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    with zipfile.ZipFile(a.archive) as z:
        if z.testzip() is not None:raise ValueError('Input archive CRC failure')
        native=z.read('work/toolkit_pilot/results/native_gamma_EVG.sdf');poses=z.read('work/casr_discovery/results/docking/00.poses.sdf')
    ref=next(m for m in Chem.ForwardSDMolSupplier(io.BytesIO(native),removeHs=False) if m is not None)
    ref=charge_state(Chem.RemoveHs(ref));poses=[Chem.RemoveHs(m) for m in Chem.ForwardSDMolSupplier(io.BytesIO(poses),removeHs=False) if m is not None]
    assert len(poses)==10 and ref.GetNumAtoms()==21
    sr=molecule.Molecule.from_rdkit(ref);mols=[molecule.Molecule.from_rdkit(p) for p in poses]
    new=np.array(rmsd.rmsdwrapper(sr,mols,symmetry=True,center=False,minimize=False));old=np.array([rdMolAlign.CalcRMS(p,ref) for p in poses])
    np.testing.assert_allclose(new,old,atol=1e-8,rtol=0)
    shift=rmsd.symmrmsd(sr.coordinates,sr.coordinates+[5,0,0],sr.atomicnums,sr.atomicnums,sr.adjacency_matrix,sr.adjacency_matrix,center=False,minimize=False)
    assert abs(shift-5)<1e-10
    pairs=ref.GetSubstructMatches(Chem.MolFromSmarts('[CX3](=[OX1])[O-]'))
    assert pairs;c,o,ox=pairs[0];swap=sr.coordinates.copy();swap[[o,ox]]=swap[[ox,o]]
    symmetry_test=rmsd.symmrmsd(sr.coordinates,swap,sr.atomicnums,sr.atomicnums,sr.adjacency_matrix,sr.adjacency_matrix,center=False,minimize=False)
    assert abs(symmetry_test)<1e-10
    result={'input_archive_sha256':hashlib.sha256(a.archive.read_bytes()).hexdigest(),'poses':10,'heavy_atoms':21,
        'spyrmsd_top_pose_RMSD_A':float(new[0]),'spyrmsd_closest_pose_RMSD_A':float(new.min()),
        'maximum_difference_from_RDKit_A':float(abs(new-old).max()),'translated_reference_by_5A_RMSD_A':float(shift),
        'carboxylate_oxygen_swap_corrected_RMSD_A':float(symmetry_test),'center':False,'minimize':False,'all_pose_RMSD_A':new.tolist(),
        'scope':'Independent saved-coordinate validation; no new docking. SDF coordinate rounding can cause ~1e-6 A differences from the original in-memory result.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
