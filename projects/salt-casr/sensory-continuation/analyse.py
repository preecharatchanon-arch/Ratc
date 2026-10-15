"""Evidence-aware evaluation of the public SaltyMeta v1 workbook.

This is an independent fixed-baseline analysis, not a reproduction of SaltyMeta's
released ESM2 model. Run with the existing reviewed scientific Python environment.
"""
from pathlib import Path
import csv, hashlib, json, re, time, zipfile, xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold, StratifiedGroupKFold
from sklearn.metrics import roc_auc_score, average_precision_score, balanced_accuracy_score, brier_score_loss

ROOT = Path(__file__).resolve().parent
INPUT = ROOT/'private_sources/saltymeta_supplement.xlsx'
OUT = ROOT/'results'
AA = 'ACDEFGHIKLMNPQRSTVWY'
KD = dict(zip(AA, [1.8,2.5,-3.5,-3.5,2.8,-.4,-3.2,4.5,-3.9,3.8,1.9,-3.5,-1.6,-3.5,-4.5,-.8,-.7,4.2,-.9,-1.3]))
SEEDS = [777,1777,2777]

def workbook_rows(path):
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(t.itertext()) for t in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',ns)]
        book=ET.fromstring(z.read('xl/workbook.xml'))
        relations=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        rel={r.get('Id'):r.get('Target').lstrip('/') for r in relations}
        for sh in book.find('s:sheets',ns):
            rid=sh.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            member=rel[rid]
            if not member.startswith('xl/'): member='xl/'+member
            rows=[]
            for row in ET.fromstring(z.read(member)).findall('.//s:row',ns):
                d={}
                for c in row:
                    v=c.find('s:v',ns)
                    value=v.text if v is not None else ''.join(c.itertext())
                    if c.get('t')=='s': value=strings[int(value)]
                    d[re.sub(r'\d','',c.get('r'))]=value or ''
                rows.append(d)
            yield sh.get('name'),rows

def curate():
    records=[]
    for sheet,rows in workbook_rows(INPUT):
        if not sheet.startswith(('Table S1','Table S2')): continue
        positive=sheet.startswith('Table S1')
        for r in rows:
            seq=r.get('B','')
            if not re.fullmatch('['+AA+']{2,15}',seq): continue
            refs=sorted(set(x.rstrip('.,)') for x in re.findall(r'10\.\d{4,9}/[^;\s]+',r['H'].lower())))
            evidence=r['E'] if positive else r['F']
            context=r['F'] if positive else r['G']
            text='; '.join([r.get(c,'') for c in 'EFGH']).lower()
            records.append(dict(sequence=seq,label=int(r['D']),source_sheet=sheet,
                source_row=int(r['A'])+3,evidence=evidence,
                phenotype=r['F'] if positive else r['E'],assay_context=context,
                material=r['G'] if positive else '',references=r['H'],doi_tokens=';'.join(refs),
                sensory_tagged=evidence.startswith('Direct sensory') if positive else evidence.startswith(('A1','B1')),
                explicit_enhancement_wording=('salt-enhanc' in context.lower() or 'saltiness-enhanc' in context.lower()) if positive else False,
                sodium_salt_mention=('sodium salt' in text),nacl_context_mention=('nacl' in text),
                ph_context_mention=bool(re.search(r'\bph\s*[0-9]',text))))
    d=pd.DataFrame(records)
    assert len(d)==580 and d.label.value_counts().to_dict()=={0:300,1:280}
    assert d.sequence.nunique()==580
    assert d.sensory_tagged.sum()==251
    return d

def distance(a,b):
    prior=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        cur=[i]
        for j,y in enumerate(b,1):cur.append(min(cur[-1]+1,prior[j]+1,prior[j-1]+(x!=y)))
        prior=cur
    return prior[-1]

def groups(d,refs=False):
    parent=list(range(len(d)))
    def find(i):
        while parent[i]!=i: parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(a,b): parent[find(a)]=find(b)
    sequences=d.sequence.tolist();edges=[]
    for i,a in enumerate(sequences):
        for j in range(i):
            b=sequences[j]
            if abs(len(a)-len(b))>.2*max(len(a),len(b))+1e-9: continue
            sim=1-distance(a,b)/max(len(a),len(b))
            if sim>=.8-1e-12:union(i,j);edges.append((i,j))
    if refs:
        seen={}
        for i,tokens in enumerate(d.doi_tokens):
            assert tokens,'Reference-blocked cohort contains no-DOI record'
            for token in tokens.split(';'):
                if token in seen:union(i,seen[token])
                else:seen[token]=i
    roots=[find(i) for i in range(len(d))]
    labels={g:k for k,g in enumerate(sorted(set(roots)))}
    return np.array([labels[g] for g in roots]),edges

def features(seqs):
    rows=[]
    for s in seqs:
        n=len(s)
        charge=1/(1+10**(7-9.69))-1/(1+10**(2.34-7))
        for a,pka in [('H',6),('K',10.5),('R',12.5)]:charge+=s.count(a)/(1+10**(7-pka))
        for a,pka in [('D',3.9),('E',4.1),('C',8.3),('Y',10.1)]:charge-=s.count(a)/(1+10**(pka-7))
        rows.append([n,charge,charge/n,*[s.count(a)/n for a in AA],
            np.mean([KD[a] for a in s]),int(s[0] in 'DE'),int(s[-1] in 'DE'),
            int(s[0] in 'KRH'),int(s[-1] in 'KRH')])
    return np.array(rows,dtype=float)

def fit_predict(name,x,y,train,test):
    if name=='extra_trees':
        model=ExtraTreesClassifier(n_estimators=512,min_samples_leaf=2,max_features='sqrt',class_weight='balanced',random_state=777,n_jobs=2)
        cols=np.arange(x.shape[1])
    else:
        model=make_pipeline(StandardScaler(),LogisticRegression(C=1,class_weight='balanced',max_iter=2000,random_state=777))
        cols=np.array([0]) if name=='length_only' else np.array([0,1,2]) if name=='charge_length' else np.arange(x.shape[1])
    model.fit(x[train][:,cols],y[train])
    return model.predict_proba(x[test][:,cols])[:,1]

def metrics(y,p):
    return {'roc_auc':float(roc_auc_score(y,p)),'average_precision':float(average_precision_score(y,p)),
        'balanced_accuracy':float(balanced_accuracy_score(y,p>=.5)),'brier_score':float(brier_score_loss(y,p))}

def main():
    start=time.monotonic();OUT.mkdir(exist_ok=True);d=curate()
    d.to_csv(OUT/'curated_records.csv',index=False)
    audit={'n':len(d),'labels':{str(k):int(v) for k,v in d.label.value_counts().items()},
        'sensory_tagged':{str(k):int(v) for k,v in d[d.sensory_tagged].label.value_counts().items()},
        'explicit_enhancement_wording_positive_records':int(d.explicit_enhancement_wording.sum()),
        'explicit_enhancement_wording_sensory_positive_records':int((d.explicit_enhancement_wording&d.sensory_tagged).sum()),
        'metadata_flags':{c:{str(k):int(v) for k,v in d.groupby('label')[c].sum().items()} for c in ['sodium_salt_mention','nacl_context_mention','ph_context_mention']},
        'note':'Evidence and endpoint wording are curator metadata; lack of a wording flag is not negative experimental evidence.'}
    all_metrics=[];oof=[];diagnostics=[]
    for cohort,subset in [('all',d),('sensory_tagged',d[d.sensory_tagged])]:
        subset=subset.reset_index(drop=True);x=features(subset.sequence);y=subset.label.to_numpy()
        sim,edges=groups(subset);reference,_=groups(subset,True) if cohort=='sensory_tagged' else (None,None)
        regimes=['random','similarity']+(['reference_similarity'] if cohort=='sensory_tagged' else [])
        for regime in regimes:
            g=sim if regime=='similarity' else reference if regime=='reference_similarity' else None
            for seed in SEEDS:
                split=StratifiedKFold(5,shuffle=True,random_state=seed).split(x,y) if g is None else StratifiedGroupKFold(5,shuffle=True,random_state=seed).split(x,y,g)
                folds=list(split);pred={m:np.full(len(y),np.nan) for m in ['length_only','charge_length','composition_logistic','extra_trees']}
                fold_ids=np.full(len(y),-1)
                for fold,(train,test) in enumerate(folds):
                    assert len(set(y[train]))==2
                    fold_ids[test]=fold
                    if g is not None:assert not set(g[train])&set(g[test])
                    if regime=='reference_similarity':
                        trainrefs={v for ts in subset.doi_tokens.iloc[train] for v in ts.split(';')}
                        testrefs={v for ts in subset.doi_tokens.iloc[test] for v in ts.split(';')}
                        assert not trainrefs&testrefs
                    for model in pred:pred[model][test]=fit_predict(model,x,y,train,test)
                crossed=sum(fold_ids[i]!=fold_ids[j] for i,j in edges)
                diagnostics.append(dict(cohort=cohort,regime=regime,seed=seed,n=len(y),groups=None if g is None else len(set(g)),
                    largest_group=None if g is None else int(pd.Series(g).value_counts().max()),similarity_edges=len(edges),similarity_edges_crossing_folds=crossed,
                    test_class_counts=[{int(k):int(v) for k,v in zip(*np.unique(y[t],return_counts=True))} for _,t in folds]))
                for model,p in pred.items():
                    assert np.isfinite(p).all()
                    all_metrics.append(dict(cohort=cohort,regime=regime,seed=seed,model=model,n=len(y),**metrics(y,p)))
                    for i in range(len(y)):
                        oof.append(dict(cohort=cohort,regime=regime,seed=seed,model=model,sequence=subset.sequence[i],label=int(y[i]),fold=int(fold_ids[i]),
                            reference_group=int(reference[i]) if reference is not None else -1,probability=float(p[i])))
                print(cohort,regime,seed,'ExtraTrees',round(all_metrics[-1]['roc_auc'],3),flush=True)
    m=pd.DataFrame(all_metrics);predictions=pd.DataFrame(oof)
    m.to_csv(OUT/'metrics.csv',index=False);predictions.to_csv(OUT/'out_of_fold_predictions.csv',index=False)
    m.groupby(['cohort','regime','model']).agg(auc_mean=('roc_auc','mean'),auc_min=('roc_auc','min'),auc_max=('roc_auc','max'),ap_mean=('average_precision','mean'),balanced_accuracy_mean=('balanced_accuracy','mean')).reset_index().to_csv(OUT/'metric_summary.csv',index=False)
    # Source-cluster descriptive uncertainty for our designated model, paired across regimes.
    p=predictions.query('cohort=="sensory_tagged" and model=="extra_trees"').groupby(['sequence','label','reference_group','regime']).probability.mean().unstack('regime').reset_index()
    rng=np.random.default_rng(777);keys=p.reference_group.unique();draws=[]
    for _ in range(3000):
        sample=np.concatenate([np.flatnonzero(p.reference_group.to_numpy()==g) for g in rng.choice(keys,len(keys),replace=True)])
        z=p.iloc[sample]
        if z.label.nunique()<2:continue
        draws.append([roc_auc_score(z.label,z[r]) for r in ['random','similarity','reference_similarity']])
    b=np.asarray(draws);bounds=np.quantile(b,[.025,.975],axis=0)
    bootstrap={'resamples':len(b),'groups':len(keys),'interpretation':'Descriptive source-cluster resampling of averaged repeated OOF predictions, conditional on fixed fits; not a retraining or external-validation confidence interval.',
        'regimes':{r:{'auc':float(roc_auc_score(p.label,p[r])),'interval_95':[float(bounds[0,i]),float(bounds[1,i])]} for i,r in enumerate(['random','similarity','reference_similarity'])},
        'random_minus_reference_auc_interval_95':np.quantile(b[:,0]-b[:,2],[.025,.975]).tolist()}
    within=[]
    for group,z in p.groupby('reference_group'):
        if z.label.nunique()==2:
            within.append(dict(reference_group=int(group),n=len(z),positives=int(z.label.sum()),**{r+'_auc':float(roc_auc_score(z.label,z[r])) for r in ['random','similarity','reference_similarity']}))
    pd.DataFrame(within).to_csv(OUT/'within_reference_metrics.csv',index=False)
    for name,value in [('evidence_audit.json',audit),('split_diagnostics.json',diagnostics),('bootstrap.json',bootstrap)]:
        (OUT/name).write_text(json.dumps(value,indent=2,default=lambda v:int(v) if isinstance(v,np.integer) else str(v))+'\n')
    (OUT/'run_receipt.json').write_text(json.dumps({'input_sha256':hashlib.sha256(INPUT.read_bytes()).hexdigest(),'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256((ROOT/'PROTOCOL.md').read_bytes()).hexdigest(),'seconds':time.monotonic()-start,'models_fitted':len(all_metrics)*5,'feature_count':features(['AG']).shape[1],'seeds':SEEDS},indent=2)+'\n')
    print(m.groupby(['cohort','regime','model']).roc_auc.mean().to_string(),flush=True)
    print(json.dumps(bootstrap,indent=2),flush=True)

if __name__=='__main__': main()
