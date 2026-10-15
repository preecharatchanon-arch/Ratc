"""Check the transcribed contact set and recompute lipid distances independently."""
from project_paths import DATA, RUN
from pathlib import Path
import json, re
import gemmi, numpy as np, pandas as pd
from analyse_access import HOTSPOTS, KEY, AA3
ROOT=Path(__file__).resolve().parent

def main():
    # Source paragraph inspection is independent of coordinate-based conclusions.
    p=DATA/'cache/tilapia.txt'
    source_check=None
    if p.exists():
        source=p.read_text().split('major AA residues being ',1)[1].split(', with Arg491',1)[0]
        parsed={int(pos):AA3[aa.upper()] for aa,pos in re.findall(r'([A-Za-z]{3})(\d+)',source)}
        assert parsed==HOTSPOTS
        source_check=dict(matched_major_residues=11,method='Source Results paragraph vs declared contact identities')
    structure=gemmi.read_structure(str(DATA/'cache/8gfa.cif'))[0]
    lipids=[];target={}
    for chain in structure:
        for residue in chain:
            coords=np.array([[a.pos.x,a.pos.y,a.pos.z] for a in residue if a.element.name not in ['H','D']])
            if residue.name=='POV':lipids.extend(coords)
            if chain.name=='A' and residue.seqid.num in KEY and residue.name in AA3:
                target[residue.seqid.num]=coords
    lipids=np.array(lipids)
    table=pd.read_csv(RUN/'human_lipid_and_ligand_distances.csv');rows=[]
    for pos,coords in target.items():
        original=float(np.linalg.norm(coords[:,None,:]-lipids[None,:,:],axis=-1).min())
        oriented=float(table[(table.chain=='A')&(table.human_position==pos)&(table.ligand_type=='resolved_phospholipid')].minimum_heavy_atom_distance_A.iloc[0])
        assert abs(original-oriented)<.003
        rows.append(dict(human_position=pos,original_deposit_minimum_phospholipid_distance_A=original,
            OPM_minimum_distance_A=oriented,difference_A=original-oriented))
    pd.DataFrame(rows).to_csv(RUN/'independent_lipid_distance_check.csv',index=False)
    geometry=pd.read_csv(RUN/'coordinate_geometry_check.csv')
    assert geometry.orientation_only_RMSD_A.max()<.01
    result=dict(source_contact_set=source_check,independent_original_coordinate_distance_checks=len(rows),
                maximum_lipid_distance_difference_A=max(abs(r['difference_A']) for r in rows),
                all_coordinate_superposition_RMSD_under_point01_A=True,
                interpretation='Checks source identity and coordinate arithmetic, not experimental peptide binding or membrane transport.')
    (RUN/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
