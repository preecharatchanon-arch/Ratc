"""Reproduce the larger-search reference-ligand follow-up."""
from project_paths import DATA, RUN
import json,time
from pathlib import Path
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem,rdMolAlign
from meeko import MoleculePreparation,PDBQTWriterLegacy,PDBQTMolecule,RDKitMolCreate
from vina import Vina
from docking import state
from chemistry import build
from protocol import load_protocol

def main():
    root=Path(__file__).resolve().parent;out=RUN/'docking';out.mkdir(parents=True,exist_ok=True);cfg=load_protocol()
    native=next(m for m in Chem.SDMolSupplier(str(DATA/'native_gamma_EVG.sdf')) if m is not None)
    ref=state(native);xyz=np.array(ref.GetConformer().GetPositions());centre=xyz.mean(0);box=np.ptp(xyz,axis=0)+12
    v=Vina(sf_name='vina',cpu=cfg['cpu_threads'],seed=cfg['docking_seed'],verbosity=0);v.set_receptor(str(RUN/'casr.pdbqt'));v.compute_vina_maps(center=centre.tolist(),box_size=box.tolist())
    prep=MoleculePreparation();text,ok,e=PDBQTWriterLegacy.write_string(prep.prepare(Chem.AddHs(ref,addCoords=True))[0]);assert ok,e
    v.set_ligand_from_string(text);observed_score=float(v.score()[0])
    m=Chem.AddHs(state(build('γ-Glu-Val-Gly')));p=AllChem.ETKDGv3();p.randomSeed=cfg['docking_seed'];assert AllChem.EmbedMolecule(m,p)==0;mmff_status=AllChem.MMFFOptimizeMolecule(m,maxIters=500)
    if mmff_status<0:raise RuntimeError('Missing MMFF parameters')
    text,ok,e=PDBQTWriterLegacy.write_string(prep.prepare(m)[0]);assert ok,e;v.set_ligand_from_string(text)
    t=time.monotonic();v.dock(exhaustiveness=cfg['native_exhaustiveness'],n_poses=cfg['native_poses']);v.write_poses(str(out/'native_exhaustiveness16.pdbqt'),n_poses=cfg['native_poses'],overwrite=True)
    pose=RDKitMolCreate.from_pdbqt_mol(PDBQTMolecule((out/'native_exhaustiveness16.pdbqt').read_text(),skip_typing=True))[0];pose=Chem.RemoveHs(pose)
    rmsds=[float(rdMolAlign.CalcRMS(pose,ref,prbId=i)) for i in range(pose.GetNumConformers())]
    s={'exhaustiveness':cfg['native_exhaustiveness'],'seed':cfg['docking_seed'],'poses_requested':cfg['native_poses'],'poses_returned':len(rmsds),'protocol':cfg,'mmff_initial_geometry_converged':mmff_status==0,'runtime_s':time.monotonic()-t,'observed_native_score_kcal_mol':observed_score,'best_scoring_pose_score':float(v.energies(n_poses=cfg['native_poses'])[0,0]),'top_pose_rmsd_A':rmsds[0],'best_rmsd_A':min(rmsds),'all_pose_rmsds_A':rmsds}
    (out/'native_search_sensitivity.json').write_text(json.dumps(s,indent=2));print(json.dumps(s,indent=2))

if __name__=='__main__':main()
