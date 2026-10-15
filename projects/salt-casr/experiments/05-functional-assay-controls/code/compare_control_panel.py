"""Select interpretable chemical controls; no prediction of taste or activity."""
from pathlib import Path
import csv,json,hashlib,sys
from rdkit import Chem,rdBase
from rdkit.Chem import Descriptors,rdMolDescriptors
E=Path(__file__).resolve().parents[1];P=E.parent.parent;D=P/'data/functional';O=E/'runs/control_selection'

def read(p):
    with p.open() as f:return list(csv.DictReader(f))
def save(name,rows):
    with (O/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
def balance(s):
    # Nominal side-chain balance at neutral pH. Free termini are not modeled.
    # This integer is not a measured net charge or a pKa calculation.
    return sum(s.count(x) for x in 'RK')-sum(s.count(x) for x in 'DE')
def main():
    O.mkdir(parents=True,exist_ok=True)
    c=read(D/'xu2017_condition_outcomes.csv');existing={r['sequence'] for r in c}
    seqs=['AR','RA','RP','RE','ER','DD','ED','AK','KA','KP','MG','LS']
    benchmark={r['sequence']:r for r in read(P/'data/saltiness/benchmark_records.csv')}
    rows=[];mols={}
    for s in seqs:
        m=Chem.MolFromSequence(s)
        if m is None:raise ValueError(s)
        if sum(a.GetSymbol()=='N' for a in m.GetAtoms())!=sum({'A':1,'R':4,'P':1,'E':1,'D':1,'K':2,'M':1,'G':1,'L':1,'S':1}[a] for a in s):raise ValueError('Nitrogen count')
        mols[s]=m
        role='published_HBO_comparator' if s in existing else ('proposed_charge_matched_control' if s in ['AK','KA','KP'] else 'separate_published_sensory_comparator')
        b=benchmark.get(s)
        rows.append(dict(sequence=s,role=role,isomeric_SMILES=Chem.MolToSmiles(m,isomericSmiles=True),formula=rdMolDescriptors.CalcMolFormula(m),
            free_form_average_MW_g_mol=Descriptors.MolWt(m),free_form_monoisotopic_mass_Da=rdMolDescriptors.CalcExactMolWt(m),
            nominal_sidechain_balance=balance(s),calculated_free_form_mg_L_at_50_uM=Descriptors.MolWt(m)*.05,
            original_HBO_panel=s in existing,benchmark_record_present=b is not None,benchmark_label_if_present=b['label'] if b else '',
            activity_interpretation='No new activity prediction; benchmark presence/absence is not experimental validation.'))
    save('control_panel_chemistry.csv',rows)
    strata=[]
    for dose in [50,100]:
        for salt in [50,150]:
            z=[r for r in c if int(r['peptide_uM'])==dose and int(r['reported_NaCl_stimulus_mM'])==salt]
            positive=[r for r in z if balance(r['sequence'])>0];other=[r for r in z if balance(r['sequence'])<=0]
            strata.append(dict(peptide_uM=dose,reported_NaCl_stimulus_mM=salt,positive_balance_tested=len(positive),
                positive_balance_with_reported_increase=sum(r['reported_outcome']=='significant_increase_over_SUM' for r in positive),
                nonpositive_balance_tested=len(other),nonpositive_balance_with_reported_increase=sum(r['reported_outcome']=='significant_increase_over_SUM' for r in other),
                interpretation='Selected comparison; no causal charge effect or general classifier is inferred.'))
    save('condition_charge_strata.csv',strata)
    pairs=[]
    for a,b in [('AR','AK'),('RA','KA'),('RP','KP')]:
        pairs.append(dict(reference=a,proposed_control=b,sequence_edit='R_to_K',same_length=len(a)==len(b),
            reference_sidechain_balance=balance(a),control_sidechain_balance=balance(b),
            free_form_MW_difference_g_mol=Descriptors.MolWt(mols[a])-Descriptors.MolWt(mols[b]),
            reference_HBO_result_at_50uM_150mM='reported_increase_over_SUM',control_HBO_result='unverified_in_sources_reviewed',
            confounds_remaining='Side-chain geometry; H-bonding; pKa; hydration and transport can change. No taste prediction.'))
    save('matched_control_pairs.csv',pairs)
    with Chem.SDWriter(str(O/'control_panel.sdf')) as w:
        for row in rows:
            m=mols[row['sequence']];m.SetProp('_Name',row['sequence']);m.SetProp('role',row['role']);m.SetProp('activity','Not predicted');w.write(m)
    summary=dict(question='Does an arginine side chain contribute beyond nominal positive side-chain balance in the selected cellular assay?',
        original_panel=7,charge_matched_lysine_dipeptides_in_original_panel=0,proposed_pairs=[['AR','AK'],['RA','KA'],['RP','KP']],
        sensory_to_cellular_dose_ratio_if_using_Xu2017_citation=12.0/.05,
        dose_ratio_limit='12 mM sensory dose is quoted by Xu2017 from Schindler2011; the original sensory methods were not recovered. This is not a potency ratio.',
        no_new_activity_prediction=True,novelty_of_control_activity_not_established=True,
        chemical_scope='Ordinary alpha-linked L-dipeptides, neutral connectivity graphs with free termini. No counterions, hydrates or pH-specific microspecies.',
        charge_scope='Nominal (R+K)-(D+E) side-chain balance, not formal graph charge or measured net charge.',
        rdkit=rdBase.rdkitVersion,python=sys.version,
        input_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [D/'xu2017_condition_outcomes.csv',P/'data/saltiness/benchmark_records.csv']})
    (O/'control_selection_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
