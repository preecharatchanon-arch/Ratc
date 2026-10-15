"""CPU Vina experiment at the observed CaSR pocket, with fixed ligand states."""
from project_paths import DATA, RUN
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign
from meeko import MoleculePreparation, PDBQTWriterLegacy, PDBQTMolecule, RDKitMolCreate
from vina import Vina
from chemistry import build
from protocol import load_protocol

ROOT=Path(__file__).resolve().parent;OUT=RUN/'docking';OUT.mkdir(parents=True,exist_ok=True)
NAMES=['γ-Glu-Val-Gly','γ-Glu-Nva-Gly','γ-Glu-Ala-Gly','γ-Glu-Cys-Gly','γ-Glu-Abu-Gly','γ-Glu-Tle-Gly','γ-Glu-Algly-Gly','γ-Glu-Hse-Gly','γ-Glu-Val','γ-Glu-Ala','γ-Glu-Cys','γ-Glu-Nva','γ-Glu-Val-Gln','γ-Glu-Val-Cys','γ-Glu-D-Val-Gly','γ-D-Glu-Val-Gly','α-Glu-Val-Gly','γ-Glu-Nva-Glycolicacid','γ-Glu-Nva-L-Lacticacid','γ-Glu-Ala-Glycolicacid']

def state(mol):
    m=Chem.Mol(mol)
    for c,o,oh in m.GetSubstructMatches(Chem.MolFromSmarts('[CX3](=[OX1])[OX2H]')):
        a=m.GetAtomWithIdx(oh);a.SetFormalCharge(-1);a.SetNumExplicitHs(0);a.SetNoImplicit(True)
    for match in m.GetSubstructMatches(Chem.MolFromSmarts('[NX3;H2;!$(NC=O)]')):
        a=m.GetAtomWithIdx(match[0]);a.SetFormalCharge(1);a.SetNumExplicitHs(3);a.SetNoImplicit(True)
    Chem.SanitizeMol(m);return m

def main():
    start=time.monotonic()
    cfg=load_protocol()
    native=next(m for m in Chem.SDMolSupplier(str(DATA/'native_gamma_EVG.sdf'),removeHs=False) if m is not None)
    ref=state(Chem.RemoveHs(native));xyz=np.array(ref.GetConformer().GetPositions());centre=xyz.mean(0);box=np.ptp(xyz,axis=0)+12
    np.savetxt(OUT/'box.csv',np.vstack([centre,box]),delimiter=',',header='x,y,z')
    v=Vina(sf_name='vina',cpu=cfg['cpu_threads'],seed=cfg['docking_seed'],verbosity=0)
    v.set_receptor(str(RUN/'casr.pdbqt'))
    v.compute_vina_maps(center=centre.tolist(),box_size=box.tolist())
    prep=MoleculePreparation();rows=[]
    for idx,name in enumerate(NAMES):
        t=time.monotonic();m=Chem.AddHs(state(build(name)))
        params=AllChem.ETKDGv3();params.randomSeed=cfg['docking_seed']
        if AllChem.EmbedMolecule(m,params)!=0:raise RuntimeError('Embedding failed: '+name)
        mmff_status=AllChem.MMFFOptimizeMolecule(m,maxIters=500)
        if mmff_status<0:raise RuntimeError('Missing MMFF parameters: '+name)
        pdbqt,ok,error=PDBQTWriterLegacy.write_string(prep.prepare(m)[0])
        if not ok:raise RuntimeError(error)
        prefix=OUT/f'{idx:02d}';prefix.with_suffix('.input.pdbqt').write_text(pdbqt)
        v.set_ligand_from_string(pdbqt);v.dock(exhaustiveness=cfg['panel_exhaustiveness'],n_poses=cfg['panel_poses'])
        energies=v.energies(n_poses=cfg['panel_poses']);v.write_poses(str(prefix.with_suffix('.poses.pdbqt')),n_poses=cfg['panel_poses'],overwrite=True)
        pose=RDKitMolCreate.from_pdbqt_mol(PDBQTMolecule(prefix.with_suffix('.poses.pdbqt').read_text(),skip_typing=True))[0]
        if pose is None:raise RuntimeError('Pose reconstruction failed')
        with Chem.SDWriter(str(prefix.with_suffix('.poses.sdf'))) as w:
            pose.SetProp('_Name',name)
            for ci in range(pose.GetNumConformers()):w.write(pose,confId=ci)
        rmsds=[]
        if name=='γ-Glu-Val-Gly':
            p=Chem.RemoveHs(pose)
            rmsds=[float(rdMolAlign.CalcRMS(p,ref,prbId=ci,refId=0)) for ci in range(p.GetNumConformers())]
        rec={'name':name,'vina_top_score_kcal_mol':float(energies[0,0]),'seconds':time.monotonic()-t,'poses':len(energies),'mmff_initial_geometry_converged':mmff_status==0,'native_top_rmsd_A':rmsds[0] if rmsds else None,'native_best_rmsd_A':min(rmsds) if rmsds else None}
        rows.append(rec);pd.DataFrame(rows).to_csv(OUT/'docking_results.csv',index=False)
        print(json.dumps(rec),flush=True)
    (OUT/'run_summary.json').write_text(json.dumps({'jobs':len(rows),'runtime_s':time.monotonic()-start,'protocol':cfg,'ligand_state':'Carboxylate groups negative, free primary amine positive; fixed charge hypothesis, not measured pKa.','receptor':'Rigid observed VFT domain; no modeled calcium ions in deposited pocket.','interpretation':'Binding-pose/scoring experiment; not receptor activation or saltiness proof.'},indent=2))

if __name__=='__main__':main()
