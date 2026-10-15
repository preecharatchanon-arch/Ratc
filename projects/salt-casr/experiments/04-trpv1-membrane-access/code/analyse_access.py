"""Locate literature TRPV1 contacts relative to membranes and bound comparators.

No docking score, binding-energy prediction or permeability prediction is made.
See PROTOCOL.md. Source coordinates are downloaded unchanged from OPM and PDB.
"""
from project_paths import DATA, RUN
from pathlib import Path
import csv, hashlib, json, re, time, importlib.metadata
import numpy as np
import pandas as pd
import gemmi
from scipy.spatial import cKDTree
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

ROOT = Path(__file__).resolve().parent
SRC = DATA/'cache'
OUT = RUN
AA3 = dict(zip(['ALA','CYS','ASP','GLU','PHE','GLY','HIS','ILE','LYS','LEU',
               'MET','ASN','PRO','GLN','ARG','SER','THR','VAL','TRP','TYR'],
              'ACDEFGHIKLMNPQRSTVWY'))
HOTSPOTS = {410:'R',441:'V',445:'Y',487:'Y',488:'F',491:'R',
            499:'R',500:'R',509:'D',557:'R',708:'D'}
KEY = {441,487,491,708}

def atoms(path):
    rows=[]
    for l in path.read_text().splitlines():
        if l[:6].strip() not in ['ATOM','HETATM']:continue
        # Accept only the first conformer. The included OPM structures use blank
        # or A for retained atoms; hydrogen and membrane dummy atoms are separate.
        if l[16] not in [' ','A']:continue
        el=l[76:78].strip() or l[12:16].strip()[0]
        rows.append(dict(record=l[:6].strip(),chain=l[21],resnum=int(l[22:26]),
            insertion=l[26].strip(),resname=l[17:20].strip(),atom=l[12:16].strip(),
            element=el,x=float(l[30:38]),y=float(l[38:46]),z=float(l[46:54])))
    return pd.DataFrame(rows)

def xyz(d):return d[['x','y','z']].to_numpy(dtype=float)

def global_map(a,b,match=2,mismatch=-1,gap=-2):
    """Global linear-gap alignment; diagonal-first tie breaking; 1-based map."""
    n,m=len(a),len(b);s=np.zeros((n+1,m+1),dtype=np.int32)
    s[:,0]=np.arange(n+1)*gap;s[0,:]=np.arange(m+1)*gap
    for i in range(1,n+1):
        for j in range(1,m+1):
            s[i,j]=max(s[i-1,j-1]+(match if a[i-1]==b[j-1] else mismatch),
                       s[i-1,j]+gap,s[i,j-1]+gap)
    mapping={};i=n;j=m
    while i or j:
        if i and j and s[i,j]==s[i-1,j-1]+(match if a[i-1]==b[j-1] else mismatch):
            mapping[i]=j;i-=1;j-=1
        elif i and s[i,j]==s[i-1,j]+gap:i-=1
        else:j-=1
    return mapping,int(s[n,m])

def compartment(z,centre,half):
    return 'extracellular_side' if z>centre+half else 'cytoplasmic_side' if z<centre-half else 'hydrophobic_core_slab'

def main():
    start=time.monotonic();OUT.mkdir(exist_ok=True)
    seqs={k:json.loads((SRC/f'trpv1_{k}.json').read_text())['sequence']['value'] for k in ['human','rat','squirrel']}
    for pos,aa in HOTSPOTS.items():assert seqs['human'][pos-1]==aa
    structures=[('8gfa','human'),('7lqy','squirrel'),('5irx','rat')]
    mappings={'human':{i:i for i in range(1,len(seqs['human'])+1)}}
    alignments=[];mapping_records=[]
    for species in ['rat','squirrel']:
        a,score=global_map(seqs['human'],seqs[species])
        alternative,_=global_map(seqs['human'],seqs[species],3,-2,-3)
        assert all(a.get(p)==alternative.get(p) for p in HOTSPOTS)
        mappings[species]=a
        alignments.append(dict(species=species,score=score,all_hotspot_mappings_stable=True,
            mapped_positions=len(a),human_length=len(seqs['human']),target_length=len(seqs[species])))
        for hp,tp in sorted(a.items()):
            mapping_records.append(dict(species=species,human_position=hp,human_aa=seqs['human'][hp-1],
                target_position=tp,target_aa=seqs[species][tp-1]))
    pd.DataFrame(mapping_records).to_csv(OUT/'canonical_alignment.csv',index=False)
    all_res=[];geometry=[];sensitivity=[];contact_rows=[];dk_contacts=[];summaries=[]
    structure_data={}
    for name,species in structures:
        d=atoms(SRC/f'opm_{name}.pdb');dummy=d[d.resname.eq('DUM')]
        planes=sorted(dummy.z.unique());assert len(planes)==2 and np.isclose(planes[0],-planes[1])
        half=planes[1]
        protein=d[d.record.eq('ATOM')&~d.element.isin(['H','D'])&d.chain.isin(list('ABCD'))]
        ca=protein[protein.atom.eq('CA')]
        assert set(ca.chain)==set('ABCD')
        # Sign is anchored by experimentally established channel topology, not
        # chosen to place the source hotspots on one side.
        cyt=ca[ca.resnum.between(199,350)].z.median()
        outer=ca[ca.resnum.between(630,660)].z.median()
        assert cyt<planes[0] and outer>0
        axis=ca[ca.z.between(-half,half)][['x','y']].mean().to_numpy()
        # Rigid-body superposition checks that OPM changed orientation rather
        # than the experimental conformation. Use chain A CAs and author IDs.
        original=gemmi.read_structure(str(SRC/f'{name}.cif'))[0]
        orig={}
        for r in original['A']:
            cas=[a for a in r if a.name=='CA']
            if cas:
                p=cas[0].pos;orig[r.seqid.num]=(r.name,np.array([p.x,p.y,p.z]))
        ca_a=ca[ca.chain.eq('A')]
        pairs=[(orig[int(r.resnum)][1],np.array([r.x,r.y,r.z])) for r in ca_a.itertuples()
               if int(r.resnum) in orig and orig[int(r.resnum)][0]==r.resname]
        x=np.stack([p[0] for p in pairs]);y=np.stack([p[1] for p in pairs])
        xc=x-x.mean(0);yc=y-y.mean(0);u,sv,vt=np.linalg.svd(xc.T@yc)
        correction=np.diag([1,1,np.linalg.det(u@vt)]);rot=u@correction@vt
        errors=np.linalg.norm(xc@rot-yc,axis=1)
        assert np.sqrt(np.mean(errors**2))<.01
        geometry.append(dict(pdb=name.upper(),species=species,CA_pairs=len(pairs),
            orientation_only_RMSD_A=float(np.sqrt(np.mean(errors**2))),max_deviation_A=float(errors.max()),
            membrane_half_thickness_A=float(half),N_terminal_domain_median_z_A=float(cyt),outer_pore_median_z_A=float(outer)))
        for hp,haa in HOTSPOTS.items():
            tp=mappings[species].get(hp);taa=seqs[species][tp-1] if tp else None
            for chain in 'ABCD':
                r=protein[protein.chain.eq(chain)&protein.resnum.eq(tp)]
                a=r[r.atom.eq('CA')]
                assert len(a)==1 and AA3.get(a.iloc[0].resname)==taa
                q=a.iloc[0]
                row=dict(pdb=name.upper(),species=species,chain=chain,human_position=hp,human_aa=haa,
                    key_hotspot=hp in KEY,structure_position=tp,structure_aa=taa,conserved_identity=taa==haa,
                    CA_z_A=q.z,heavy_atom_min_z_A=r.z.min(),heavy_atom_max_z_A=r.z.max(),
                    extracellular_boundary_z_A=half,CA_to_extracellular_boundary_A=half-q.z,
                    CA_radial_distance_A=float(np.linalg.norm(np.array([q.x,q.y])-axis)),
                    baseline_category=compartment(q.z,0,half))
                all_res.append(row)
                for shift in [-3,0,3]:
                    for delta in [-3,0,3]:
                        sensitivity.append(dict(pdb=name.upper(),chain=chain,human_position=hp,key_hotspot=hp in KEY,
                            centre_shift_A=shift,half_thickness_change_A=delta,
                            CA_category=compartment(q.z,shift,half+delta),
                            any_residue_atom_above_external_boundary=bool((r.z>shift+half+delta).any())))
                if name=='8gfa':
                    for code,label in [('POV','resolved_phospholipid'),('ZEI','bound_antagonist'),('DU0','detergent'),('HOH','resolved_water')]:
                        other=d[d.resname.eq(code)&~d.element.isin(['H','D'])]
                        min_distance=float(cKDTree(xyz(other)).query(xyz(r))[0].min()) if len(other) else None
                        for cutoff in [3.5,4.,5.]:
                            contact_rows.append(dict(pdb='8GFA',chain=chain,human_position=hp,ligand_type=label,
                                minimum_heavy_atom_distance_A=min_distance,cutoff_A=cutoff,contact=min_distance<=cutoff if min_distance else False))
        structure_data[name]=dict(atoms=d,protein=protein,ca=ca,half=half)
        summaries.append(dict(pdb=name.upper(),species=species,membrane_half_thickness_A=half))
    res=pd.DataFrame(all_res);res.to_csv(OUT/'published_contact_depths.csv',index=False)
    pd.DataFrame(geometry).to_csv(OUT/'coordinate_geometry_check.csv',index=False)
    pd.DataFrame(sensitivity).to_csv(OUT/'membrane_boundary_sensitivity.csv',index=False)
    pd.DataFrame(contact_rows).to_csv(OUT/'human_lipid_and_ligand_distances.csv',index=False)
    rat=structure_data['5irx'];d=rat['atoms'];prot=rat['protein']
    toxin=d[d.record.eq('ATOM')&d.chain.isin(['E','F'])&~d.element.isin(['H','D'])]
    assert len(toxin)>500 and toxin.z.median()>rat['half']
    # Receptor contact sets retain every resolved subunit and both actual toxins.
    near=cKDTree(xyz(toxin)).query(xyz(prot))[0]
    for cutoff in [3.5,4.,5.]:
        for (chain,num),r in prot.loc[near<=cutoff].groupby(['chain','resnum']):
            a=rat['ca'][rat['ca'].chain.eq(chain)&rat['ca'].resnum.eq(num)].iloc[0]
            dk_contacts.append(dict(cutoff_A=cutoff,chain=chain,rat_position=num,rat_aa=AA3[r.resname.iloc[0]],
                CA_z_A=a.z,category=compartment(a.z,0,rat['half'])))
    dk=pd.DataFrame(dk_contacts);dk.to_csv(OUT/'experimental_DkTx_contact_depths.csv',index=False)
    dist=[]
    for hp in sorted(KEY):
        r=prot[prot.resnum.eq(mappings['rat'][hp])]
        dist.append(dict(human_position=hp,rat_position=mappings['rat'][hp],
            minimum_distance_to_bound_DkTx_A=float(cKDTree(xyz(toxin)).query(xyz(r))[0].min())))
    pd.DataFrame(dist).to_csv(OUT/'hotspot_distance_to_DkTx.csv',index=False)
    # Explicit free-form descriptors; logP is neutral graph logP, never logD.
    peptides=[]
    for sequence in ['HLDDALR','VIEPLDIGDDKVR','FPGIPDHL','DFKSPDDPSRH']:
        mol=Chem.MolFromFASTA(sequence);assert mol is not None
        row=dict(sequence=sequence,MW_Da=Descriptors.MolWt(mol),tPSA_A2=rdMolDescriptors.CalcTPSA(mol),
            neutral_graph_logP=Descriptors.MolLogP(mol),H_bond_donors=rdMolDescriptors.CalcNumHBD(mol),
            H_bond_acceptors=rdMolDescriptors.CalcNumHBA(mol),rotatable_bonds=rdMolDescriptors.CalcNumRotatableBonds(mol))
        for ph in [5,6,7,8]:
            charge=1/(1+10**(ph-9.69))-1/(1+10**(2.34-ph))
            for aa,pka in [('H',6),('K',10.5),('R',12.5)]:charge+=sequence.count(aa)/(1+10**(ph-pka))
            for aa,pka in [('D',3.9),('E',4.1),('C',8.3),('Y',10.1)]:charge-=sequence.count(aa)/(1+10**(pka-ph))
            row[f'approximate_net_charge_pH{ph}']=charge
        peptides.append(row)
    pd.DataFrame(peptides).to_csv(OUT/'source_peptide_descriptors.csv',index=False)
    # Display a geometrical comparison, not a new docking visualization.
    import os
    os.environ['MPLBACKEND']='Agg'
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,3,figsize=(12,4.8),layout='constrained',sharey=True)
    for ax,(name,species) in zip(axs,structures):
        dat=structure_data[name];ca=dat['ca'];half=dat['half']
        ax.axhspan(-half,half,color='#f0dfb1',alpha=.7)
        ax.scatter(np.hypot(ca.x,ca.y),ca.z,s=2,color='#c6d0d8',alpha=.35,rasterized=True)
        q=res[res.pdb.eq(name.upper())&res.chain.eq('A')]
        for r in q[q.key_hotspot].itertuples():
            ax.scatter(r.CA_radial_distance_A,r.CA_z_A,s=45,color='#bb4b3b',zorder=3)
            offset={441:(-38,8),487:(6,10),491:(6,-3),708:(6,-2)}[r.human_position]
            ax.annotate(f'{r.human_aa}{r.human_position}',(r.CA_radial_distance_A,r.CA_z_A),
                        xytext=offset,textcoords='offset points',fontsize=8,
                        arrowprops=dict(arrowstyle='-',lw=.6,color='#bb4b3b'))
        if name=='5irx':
            bound=dk[dk.cutoff_A.eq(4.)&dk.chain.eq('A')]
            p=ca[ca.chain.eq('A')&ca.resnum.isin(bound.rat_position)]
            ax.scatter(np.hypot(p.x,p.y),p.z,s=25,color='#168575',label='DkTx contacts, 4 Å',zorder=3)
            ax.legend(loc='upper left',fontsize=8,frameon=False)
        ax.axhline(half,color='#ad8d43',lw=1);ax.axhline(-half,color='#ad8d43',lw=1)
        ax.set(title=f'{name.upper()}: {species}',xlabel='Distance from pore axis (Å)',ylim=(-42,36),xlim=(0,65))
    axs[0].set_ylabel('Membrane-normal coordinate z (Å)\nextracellular ↑ / cytoplasmic ↓')
    fig.suptitle('Published key contacts lie below the extracellular face\nRed: four literature hotspots; shaded: OPM hydrophobic core',fontsize=12)
    fig.savefig(OUT/'membrane_site_comparison.png',dpi=180);plt.close(fig)
    receipt=dict(runtime_s=time.monotonic()-start,experimental_structures=3,source_major_positions=11,
        source_key_positions=4,structural_chains_per_entry=4,independent_biological_replicates=0,
        alignment_checks=alignments,
        human_key_CA_z_A={str(int(r.human_position)):float(r.CA_z_A) for r in res[res.pdb.eq('8GFA')&res.chain.eq('A')&res.key_hotspot].itertuples()},
        key_CA_extracellular_under_any_boundary_scenario=bool(pd.DataFrame(sensitivity).query('key_hotspot').CA_category.eq('extracellular_side').any()),
        DkTx_unique_rat_positions_at_4A=int(dk[dk.cutoff_A.eq(4)].rat_position.nunique()),
        packages={n:importlib.metadata.version(n) for n in ['numpy','pandas','scipy','gemmi','rdkit','matplotlib']},
        interpretation='Site geometry/access concern; no permeability, binding, activation, sensory or food-safety prediction.')
    (OUT/'run_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
    print(res[res.chain.eq('A')][['pdb','human_position','structure_position','structure_aa','CA_z_A','CA_to_extracellular_boundary_A','baseline_category']].to_string(index=False))
    print('DkTx 4A contact depth:',dk[dk.cutoff_A.eq(4)].CA_z_A.describe().to_dict())
    print(pd.DataFrame(dist).to_string(index=False))

if __name__=='__main__':main()
