"""Post-hoc robustness checks and endpoint-separated literature comparisons."""
import hashlib,json,time
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from analyse import ROOT,OUT,SEEDS,curate,groups,features,fit_predict,distance

EXCLUDED={'10.1016/j.meatsci.2023.109261','10.1016/j.fufo.2026.100930','10.1080/10408398.2025.2547284',
          '10.1002/fsh3.12055','10.1271/bbb.59','10.1016/j.tifs.2022.11','10.1007/s13197--04836-1'}

def relaxed_groups(d):
    # Reuse the original edit-similarity grouping; retain singleton/no-reference records.
    sim,_=groups(d);parent=list(range(len(d)))
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(a,b):parent[find(a)]=find(b)
    seen_sim={};seen_ref={};missing=0
    for i,r in d.iterrows():
        if sim[i] in seen_sim:union(i,seen_sim[sim[i]])
        else:seen_sim[sim[i]]=i
        refs=set(r.doi_tokens.split(';'))-EXCLUDED
        if not refs:missing+=1
        for token in refs:
            if token in seen_ref:union(i,seen_ref[token])
            else:seen_ref[token]=i
    return np.array([find(i) for i in range(len(d))]),missing

def main():
    start=time.monotonic();d=curate();s=d[d.sensory_tagged].reset_index(drop=True)
    oof=pd.read_csv(OUT/'out_of_fold_predictions.csv')
    fixed=oof.query('cohort=="sensory_tagged" and model=="extra_trees" and regime=="reference_similarity"')
    x=features(s.sequence);y=s.label.to_numpy();byseq={seq:i for i,seq in enumerate(s.sequence)}
    fold_metrics=[];control_predictions=[]
    for seed,z in fixed.groupby('seed'):
        for fold,v in z.groupby('fold'):
            rng=np.random.default_rng(40000+int(seed)+int(fold));test=[]
            for label,n in v.label.value_counts().items():
                test.extend(rng.choice(np.flatnonzero(y==label),n,replace=False).tolist())
            test=np.array(sorted(test));train=np.setdiff1d(np.arange(len(y)),test)
            p=fit_predict('extra_trees',x,y,train,test)
            fold_metrics.append(dict(seed=int(seed),fold=int(fold),n=len(v),positive=int(v.label.sum()),
                reference_auc=float(roc_auc_score(v.label,v.probability)),matched_random_auc=float(roc_auc_score(y[test],p))))
            control_predictions.extend(dict(seed=int(seed),fold=int(fold),sequence=s.sequence.iloc[i],label=int(y[i]),probability=float(q)) for i,q in zip(test,p))
    pd.DataFrame(fold_metrics).to_csv(OUT/'posthoc_matched_fold_control.csv',index=False)
    pd.DataFrame(control_predictions).to_csv(OUT/'posthoc_matched_fold_predictions.csv',index=False)
    g,missing=relaxed_groups(s);sensitivity=[];sp=[]
    for seed in SEEDS:
        p=np.full(len(s),np.nan);folds=np.full(len(s),-1)
        for f,(train,test) in enumerate(StratifiedGroupKFold(5,shuffle=True,random_state=seed).split(x,y,g)):
            assert not set(g[train])&set(g[test]);p[test]=fit_predict('extra_trees',x,y,train,test);folds[test]=f
        sensitivity.append(dict(seed=seed,roc_auc=float(roc_auc_score(y,p)),groups=len(set(g)),largest_group=int(pd.Series(g).value_counts().max()),records_without_remaining_reference=missing))
        sp.extend(dict(seed=seed,sequence=s.sequence.iloc[i],label=int(y[i]),fold=int(folds[i]),group=int(g[i]),probability=float(p[i])) for i in range(len(s)))
    pd.DataFrame(sensitivity).to_csv(OUT/'posthoc_reference_parse_sensitivity.csv',index=False)
    pd.DataFrame(sp).to_csv(OUT/'posthoc_reference_parse_predictions.csv',index=False)
    panel=pd.DataFrame([
        dict(sequence='FGDDP',standalone_descriptors='umami; sourness',taste_threshold_mM=.11,NaCl_sensory_enhancement='effect described as less pronounced; not assigned negative here'),
        dict(sequence='GDDWT',standalone_descriptors='umami; sourness',taste_threshold_mM=.11,NaCl_sensory_enhancement='significant increase reported'),
        dict(sequence='ASHGEGF',standalone_descriptors='umami; sourness; saltiness',taste_threshold_mM=.13,NaCl_sensory_enhancement='significant increase reported'),
        dict(sequence='DDPRLP',standalone_descriptors='umami; sourness; bitterness',taste_threshold_mM=.09,NaCl_sensory_enhancement='effect described as less pronounced; not assigned negative here'),
        dict(sequence='LDDGF',standalone_descriptors='umami; sourness; sweetness',taste_threshold_mM=.06,NaCl_sensory_enhancement='significant increase reported')])
    panel['doi']='10.1038/s41538-026-01088-9';panel['publication_date']='2026-10-02'
    panel['NaCl_mg_mL']=3;panel['peptide_mg_mL']=1
    panel['standalone_salty_descriptor_listed']=panel.standalone_descriptors.str.contains('saltiness')
    panel['benchmark_exact_match']=panel.sequence.isin(d.sequence)
    sims=[]
    for seq in panel.sequence:
        ss=[1-distance(seq,b)/max(len(seq),len(b)) for b in d.sequence]
        best=int(np.argmax(ss));sims.append(dict(sequence=seq,nearest_benchmark_sequence=d.sequence.iloc[best],edit_similarity=float(ss[best])))
    panel=panel.merge(pd.DataFrame(sims),on='sequence')
    panel.to_csv(OUT/'october_mushroom_evidence.csv',index=False)
    # Separate functional controls; do not relabel the combined sensory benchmark.
    controls=pd.DataFrame([dict(sequence=a,cellular_NaCl_response_increase=b,doi='10.1038/s41598-017-07756-x') for a,b in [('AR',True),('RA',True),('RP',True),('RE',False),('ER',False),('DD',False),('ED',False)]])
    controls=controls.merge(d[['sequence','label','references']],on='sequence',how='left').rename(columns={'label':'combined_benchmark_label','references':'benchmark_references'})
    controls.to_csv(OUT/'arginyl_cellular_controls.csv',index=False)
    scores=[]
    for cohort,train_data in [('all',d),('sensory_tagged',s)]:
        candidates=pd.concat([panel[['sequence']],controls[['sequence']]]).drop_duplicates().reset_index(drop=True)
        xx=np.vstack([features(train_data.sequence),features(candidates.sequence)]);yy=np.r_[train_data.label.to_numpy(),np.zeros(len(candidates),dtype=int)]
        train=np.arange(len(train_data));test=np.arange(len(train_data),len(xx))
        for model in ['length_only','charge_length','composition_logistic','extra_trees']:
            p=fit_predict(model,xx,yy,train,test)
            scores.extend(dict(cohort=cohort,model=model,sequence=seq,score=float(v),in_training=seq in set(train_data.sequence)) for seq,v in zip(candidates.sequence,p))
    pd.DataFrame(scores).to_csv(OUT/'literature_panel_scores.csv',index=False)
    fm=pd.DataFrame(fold_metrics);result={'posthoc':True,'matched_fold_control':{'folds':len(fm),'reference_macro_auc':float(fm.reference_auc.mean()),'matched_random_macro_auc':float(fm.matched_random_auc.mean()),'reference_wins':int((fm.reference_auc>fm.matched_random_auc).sum())},
        'reference_parse_sensitivity':sensitivity,'note':'Matched random draws are sensitivity controls, not independent trials or a p-value. External mushroom panel is five author-selected candidates; neither external AUC nor success rate is estimated.',
        'mushroom_panel_exact_overlap':int(panel.benchmark_exact_match.sum()),'mushroom_panel_similarity_ge_0_8':int((panel.edit_similarity>=.8).sum()),'seconds':time.monotonic()-start}
    (OUT/'posthoc_summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
