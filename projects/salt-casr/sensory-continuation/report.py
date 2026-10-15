"""Recalculate saved metrics and draw a compact scientific results figure."""
import os
os.environ['MPLBACKEND']='Agg'
import json
import numpy as np,pandas as pd
from sklearn.metrics import roc_auc_score
from analyse import ROOT,OUT,SEEDS,curate,groups
import matplotlib.pyplot as plt

def main():
    d=curate();p=pd.read_csv(OUT/'out_of_fold_predictions.csv');m=pd.read_csv(OUT/'metrics.csv')
    checked=0
    for key,v in p.groupby(['cohort','regime','seed','model']):
        expected=580 if key[0]=='all' else 251
        assert len(v)==expected and v.sequence.nunique()==expected
        row=m[(m.cohort==key[0])&(m.regime==key[1])&(m.seed==key[2])&(m.model==key[3])].iloc[0]
        assert np.isclose(roc_auc_score(v.label,v.probability),row.roc_auc)
        checked+=1
    s=d[d.sensory_tagged].reset_index(drop=True);g,_=groups(s,True);assignment=dict(zip(s.sequence,g))
    for seed,z in p.query('cohort=="sensory_tagged" and regime=="reference_similarity" and model=="extra_trees"').groupby('seed'):
        z=z.copy();z['group']=z.sequence.map(assignment)
        assert z.groupby('group').fold.nunique().eq(1).all()
        for _,v in z.groupby('fold'):
            train=s[~s.sequence.isin(v.sequence)];test=s[s.sequence.isin(v.sequence)]
            assert not {t for ts in train.doi_tokens for t in ts.split(';')}&{t for ts in test.doi_tokens for t in ts.split(';')}
    panel=pd.read_csv(OUT/'october_mushroom_evidence.csv')
    assert not panel.benchmark_exact_match.any()
    assert panel.query('sequence in ["GDDWT","LDDGF"]').standalone_salty_descriptor_listed.eq(False).all()
    receipt={'checks_passed':True,'metric_rows_recomputed':checked,'expected_oof_rows':len(p),
             'exactly_one_prediction_per_record_per_model_split_seed':True,'reference_crossing_folds':0,
             'standalone_taste_and_enhancement_columns_kept_separate':True,
             'limitations':'Metadata tags and reference connectivity do not independently verify every primary assay. No external model accuracy estimate from the selected mushroom panel.'}
    (OUT/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':140})
    fig,axes=plt.subplots(2,2,figsize=(12.5,8.5),layout='constrained')
    a=axes[0,0];configs=[('all','random','All: random'),('all','similarity','All: sequence groups'),('sensory_tagged','random','Sensory tags: random'),('sensory_tagged','similarity','Sensory tags: sequence groups'),('sensory_tagged','reference_similarity','Sensory tags: reference + sequence')]
    for i,(cohort,regime,label) in enumerate(configs):
        values=m.query('model=="extra_trees" and cohort==@cohort and regime==@regime').roc_auc
        a.plot([values.min(),values.max()],[i,i],color='#177e89',lw=3);a.scatter(values.mean(),i,color='#123952',s=45,zorder=3)
    a.set(yticks=range(len(configs)),yticklabels=[c[2] for c in configs],xlim=(0,1),xlabel='Out-of-fold ROC-AUC',title='A. Fixed ExtraTrees; 3 partition seeds');a.invert_yaxis();a.axvline(.5,color='.6',ls='--');a.grid(axis='x',alpha=.15)
    a=axes[0,1];f=pd.read_csv(OUT/'posthoc_matched_fold_control.csv')
    for _,r in f.iterrows():a.plot([0,1],[r.matched_random_auc,r.reference_auc],color='#87aab0',alpha=.55,lw=1)
    a.scatter([0,1],[f.matched_random_auc.mean(),f.reference_auc.mean()],s=70,color='#123952',zorder=3)
    a.set(xticks=[0,1],xticklabels=['Matched random\nsize and class counts','Reference + sequence\nheld out'],ylim=(0,1),ylabel='AUC within held-out fold',title='B. Post-hoc matched control; 15 folds');a.axhline(.5,color='.6',ls='--')
    a=axes[1,0];z=m.query('cohort=="sensory_tagged"').groupby(['model','regime']).roc_auc.mean().unstack()
    order=['length_only','charge_length','composition_logistic','extra_trees'];loc=np.arange(4)
    for offset,(regime,label,color) in zip([-.24,0,.24],[('random','Random','#9ac3c7'),('similarity','Sequence groups','#177e89'),('reference_similarity','Reference + sequence','#123952')]):
        a.bar(loc+offset,z.loc[order,regime],width=.23,label=label,color=color)
    a.set(xticks=loc,xticklabels=['Length\nonly','Charge +\nlength','Composition\nlogistic','ExtraTrees'],ylim=(0,1),ylabel='Mean OOF ROC-AUC',title='C. No model selected from these results');a.axhline(.5,color='.6',ls='--');a.legend(frameon=False,fontsize=8)
    a=axes[1,1];a.axis('off')
    text=('D. Experimental endpoint check\n\n'
          'GDDWT: umami + sourness when tested alone\n'
          'LDDGF: umami + sourness + sweetness alone\n\n'
          'Both increased saltiness in the October 2026 study:\n'
          '1 mg/mL peptide + 3 mg/mL NaCl.\n\n'
          'Standalone salty taste and saltiness enhancement\n'
          'must remain separate labels.\n\n'
          'Five published candidates; no exact benchmark overlap.\n'
          'LDDGF has an 80% edit-similarity neighbour.\n'
          'No external AUC or new-compound claim.\n\n'
          'Primary source: doi:10.1038/s41538-026-01088-9')
    a.text(0,1,text,va='top',fontsize=10.5,linespacing=1.45)
    fig.suptitle('Saltiness peptide models: source transfer and endpoint validity',fontsize=16,fontweight='bold')
    fig.savefig(OUT/'evidence_and_transfer.png',dpi=180);fig.savefig(OUT/'evidence_and_transfer.svg');plt.close(fig)
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
