"""Reanalyse attributed functional evidence; no fitting or source downloads."""
import os
os.environ['MPLBACKEND']='Agg'
from pathlib import Path
import csv,hashlib,json,platform,sys,time

EXPERIMENT=Path(__file__).resolve().parents[1]
PROJECT=EXPERIMENT.parent.parent
DATA=PROJECT/'data/functional'
OUT=EXPERIMENT/'runs/latest'

def read(name):
    with (DATA/name).open() as f:return list(csv.DictReader(f))

def write(name,rows):
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)

def main():
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True)
    conditions=read('xu2017_condition_outcomes.csv')
    peptides=read('xu2017_peptide_response_EC50.csv')
    components=read('xu2017_knockdown_components.csv')
    sums=read('xu2017_knockdown_SUM_comparisons.csv')
    drug=read('xu2017_amiloride_SUM_comparisons.csv')
    soy=read('qi2025_soy_endpoint_comparison.csv')
    keys=[(r['sequence'],int(r['peptide_uM']),int(r['reported_NaCl_stimulus_mM'])) for r in conditions]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate condition key')
    positive=[r for r in conditions if r['reported_outcome']=='significant_increase_over_SUM']
    seqs=[r['sequence'] for r in peptides]
    counts=[]
    for seq in seqs:
        z=[r for r in conditions if r['sequence']==seq]
        yes=sum(r['reported_outcome']=='significant_increase_over_SUM' for r in z)
        counts.append(dict(sequence=seq,tested_conditions=len(z),reported_increases=yes,
                           other_tested_conditions=len(z)-yes,interpretation='Selected reported conditions; not prevalence or effect-size estimate'))
    write('condition_summary.csv',counts)
    # Check supplied counts against rounded source percentages, without pooling cells.
    contrasts=[];max_rounding=0.
    for r in components:
        for endpoint in ['NaCl','AR','mixture']:
            delta=abs(100*int(r[endpoint+'_responders'])/int(r['cells_examined'])-float(r[endpoint+'_response_pct']))
            max_rounding=max(max_rounding,delta)
            if delta>0.051:raise ValueError(('Count/percent inconsistency',r['treatment'],endpoint,delta))
        S=float(r['NaCl_response_pct'])+float(r['AR_response_pct']);M=float(r['mixture_response_pct'])
        contrasts.append(dict(treatment=r['treatment'],cohort=r['cohort'],NaCl_response_pct=r['NaCl_response_pct'],
                              AR_response_pct=r['AR_response_pct'],SUM_from_rounded_components_pct=S,
                              mixture_pct=M,mixture_minus_SUM_pp=M-S,
                              mixture_decline_vs_untransfected_pct=100*(1-M/float(components[0]['mixture_response_pct'])),
                              new_significance_test='none'))
    write('component_contrasts.csv',contrasts)
    exact=[]
    for r in sums:
        N=int(r['cells_examined']);M=float(r['mixture_pct']);S=float(r['SUM_pct'])
        exact.append(dict(treatment=r['treatment'],cohort=r['cohort'],SUM_pct=S,mixture_pct=M,
                          excess_over_SUM_pp=M-S,
                          count_based_excess_pp=100*(int(r['mixture_responders'])-int(r['SUM_responder_count_as_reported']))/N,
                          reported_outcome=r['reported_outcome'],new_significance_test='none'))
    write('separate_SUM_contrasts.csv',exact)
    so=[]
    core=next(r['sequence'] for r in soy if r['name']=='9AA')
    for r in soy:
        x=r.copy();v=x['sensory_equivalent_NaCl_mM']
        x['increase_in_equivalent_intensity_pct']=100*(float(v)/float(x['sensory_NaCl_mM'])-1) if v else ''
        x['sequence_relation_to_9AA']='N-terminal E addition' if r['sequence']=='E'+core else ('C-terminal P addition' if r['sequence']==core+'P' else 'shared 9-residue core')
        so.append(x)
    write('soy_endpoint_comparison.csv',so)
    write('amiloride_contrasts.csv',[dict(condition=r['condition'],SUM_pct=r['SUM_pct'],mixture_pct=r['mixture_pct'],
        excess_over_SUM_pp=float(r['mixture_pct'])-float(r['SUM_pct']),reported_outcome=r['reported_outcome']) for r in drug])
    # A short, independently readable record rather than an automated biological verdict.
    result=dict(analysis='retrospective functional-assay evidence reanalysis',
        condition_records=len(conditions),unique_peptides=len(seqs),reported_increase_conditions=len(positive),
        peptides_with_any_reported_increase=sorted({r['sequence'] for r in positive}),
        at_100_uM=dict(tested_records=sum(int(r['peptide_uM'])==100 for r in conditions),
                       reported_increases=sum(int(r['peptide_uM'])==100 for r in positive)),
        peptide_alone_EC50_count=len(peptides),separate_knockdown_SUM_cohorts=len(sums),
        max_component_count_percent_rounding_pp=max_rounding,
        soy_sensory_enhancers=[r['name'] for r in soy if r['sensory_enhancement_reported']=='yes'],
        soy_organoid_enhancers=[r['name'] for r in soy if r['organoid_enhancement_reported']=='yes'],
        limits=['Published outcomes, not independently measured biology.',
                'Reported non-significance is neither numerical zero nor an established between-dose interaction.',
                'No new significance test from pooled cell counts; different Figure 7 cohorts remain separate.',
                'Soy organoid dose, salt background and species were not verified from the accessible abstract.',
                'Cellular response, receptor binding, sensory enhancement and sodium replacement are distinct.'])
    (OUT/'analysis_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    plot(conditions,contrasts,exact,so)
    import matplotlib
    receipt=dict(python=sys.version,platform=platform.platform(),matplotlib=matplotlib.__version__,
        elapsed_s=time.monotonic()-started,input_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DATA.glob('*.csv'))},
        output_directory=str(OUT),scope='Executed calculations and plotting; no wet-lab experiment or model training')
    (OUT/'run_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(result,indent=2))

def plot(conditions,components,sums,soy):
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    seqs=['AR','RA','RP','RE','ER','DD','ED'];cols=[(s,d) for s in [50,150] for d in [10,50,100]]
    matrix=np.full((len(seqs),len(cols)),np.nan)
    for r in conditions:matrix[seqs.index(r['sequence']),cols.index((int(r['reported_NaCl_stimulus_mM']),int(r['peptide_uM'])))]=r['reported_outcome']=='significant_increase_over_SUM'
    a=axes[0,0];cmap=ListedColormap(['#e3e8ea','#187f82']);cmap.set_bad('#f4f4f4')
    a.imshow(np.ma.masked_invalid(matrix),cmap=cmap,vmin=0,vmax=1,aspect='auto')
    for i in range(len(seqs)):
        for j in range(len(cols)):a.text(j,i,'NT' if np.isnan(matrix[i,j]) else ('+' if matrix[i,j] else 'NS'),ha='center',va='center',color='white' if matrix[i,j]==1 else '#324956',fontsize=9)
    a.set(xticks=range(6),xticklabels=['10','50','100','10','50','100'],yticks=range(7),yticklabels=seqs,
          xlabel='Peptide dose (µM): left 50 mM NaCl; right 150 mM NaCl',title='A. Human taste-cell outcomes relative to SUM')
    a.axvline(2.5,color='white',lw=3)
    a=axes[0,1];x=np.arange(4)
    a.bar(x-.17,[r['mixture_pct'] for r in components],.34,label='Mixture',color='#173d56')
    a.bar(x+.17,[r['SUM_from_rounded_components_pct'] for r in components],.34,label='NaCl alone + AR alone',color='#88bec1')
    a.set(xticks=x,xticklabels=['Untreated','ENaCα siRNA','ENaCδ siRNA','NHE1 siRNA'],ylabel='Responding cells (%)',title='B. Raw mixture drops in every knockdown (7a–c)');a.legend(frameon=False,fontsize=8)
    a=axes[1,0];x=np.arange(3)
    a.bar(x,[r['excess_over_SUM_pp'] for r in sums],color=['#a5b6bc','#a5b6bc','#187f82'])
    for i,r in enumerate(sums):a.text(i,r['excess_over_SUM_pp']+.13,'Reported NS' if r['reported_outcome'].startswith('no_') else 'Reported increase',ha='center',fontsize=8)
    a.set(xticks=x,xticklabels=['ENaCα siRNA','ENaCδ siRNA','NHE1 siRNA'],ylim=(-.3,5.2),ylabel='Mixture minus SUM (percentage points)',title='C. Separate direct SUM comparisons (7d–f)');a.axhline(0,color='.5',lw=.8)
    a=axes[1,1];a.axis('off')
    text=('D. Soy endpoint comparison (publisher abstract)\n\n'
          'E    EDEGEQPRPF    Sensory +     Organoid +\n'
          'DG   DEGEQPRPFP    Sensory +     Organoid NS\n'
          '9AA  DEGEQPRPF     Sensory NS    Organoid NS\n\n'
          'Sensory: 0.4 mg/mL peptide + 50 mM NaCl.\n'
          'Organoid dose, NaCl and species remain unverified.\n'
          'No cross-assay accuracy estimate is justified.\n\n'
          '+ = reported increase; NS = no increase reported.\n'
          'NT = dose not tested in the reconstructed panel.\n'
          'NS is not a measured zero effect.\n\n'
          'Sources: Xu et al. (2017); Qi et al. (2025).')
    a.text(0,1,text,va='top',linespacing=1.5,fontfamily='DejaVu Sans',fontsize=9.5)
    fig.suptitle('Functional evidence: assay conditions and appropriate controls',fontweight='bold',fontsize=15)
    fig.savefig(OUT/'functional_controls.png',dpi=160);fig.savefig(OUT/'functional_controls.svg');plt.close(fig)

if __name__=='__main__':main()
