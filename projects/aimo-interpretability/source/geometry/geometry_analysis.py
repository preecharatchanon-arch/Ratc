"""Frozen unweighted readout; one primary candidate, no selection of best arm."""
import csv
from pathlib import Path
import numpy as np
from geometry_common import ROOT,load,save
from geometry_measures import temporal_features
P=load(ROOT/'geometry_protocol.json');SEED=P['readout']['seed']

def fit(x,y):
    from sklearn.linear_model import LogisticRegression
    x=np.asarray(x,float);y=np.asarray(y,int)
    if not np.isfinite(x).all():raise ValueError('Invalid classifier features')
    if len(set(y))<2:return {'constant':float((y.sum()+.5)/(len(y)+1)),'dimension':x.shape[1]}
    mean=x.mean(0);scale=np.sqrt(((x-mean)**2).mean(0));scale[scale<1e-12]=1.
    clf=LogisticRegression(C=.1,solver='liblinear',max_iter=5000,random_state=SEED).fit((x-mean)/scale,y)
    return {'mean':mean.tolist(),'scale':scale.tolist(),'coef':clf.coef_[0].tolist(),'intercept':float(clf.intercept_[0]),'dimension':x.shape[1]}
def predict(fitted,x):
    x=np.atleast_2d(np.asarray(x,float))
    if x.shape[1]!=fitted['dimension'] or not np.isfinite(x).all():raise ValueError('Invalid prediction features')
    if 'constant'in fitted:return np.full(len(x),fitted['constant'])
    z=((x-fitted['mean'])/np.array(fitted['scale']))@np.array(fitted['coef'])+fitted['intercept']
    return 1/(1+np.exp(-np.clip(z,-700,700)))
def folds(groups):
    groups=np.array(groups)
    for family in sorted(set(groups)):
        train=np.flatnonzero(groups!=family);test=np.flatnonzero(groups==family)
        if not len(train) or not len(test):raise ValueError('Multiple families required')
        yield family,train,test
def oof(matrices,y,groups):
    predictions={a:np.full(len(y),np.nan) for a in matrices};receipts=[]
    for family,train,test in folds(groups):
        for arm,x in matrices.items():
            predictions[arm][test]=1. if arm=='always_robust' else predict(fit(np.asarray(x)[train],np.asarray(y)[train]),np.asarray(x)[test])
        receipts.append({'family':family,'train_indices':train.tolist(),'test_indices':test.tolist()})
    if not all(np.isfinite(v).all() for v in predictions.values()):raise ValueError('Missing OOF prediction')
    return predictions,receipts
def metrics(y,scores):
    from sklearn.metrics import roc_auc_score
    y=np.array(y,int);s=np.array(scores,float);p=s>=.5
    nr=float(np.mean(~p[y==0])) if np.any(y==0) else None
    rr=float(np.mean(p[y==1])) if np.any(y==1) else None
    return {'n':len(y),'correct':int(np.sum(p==y)),'accuracy':float(np.mean(p==y)),
        'balanced_accuracy':(nr+rr)/2 if nr is not None and rr is not None else None,
        'nonrobust_recall':nr,'robust_recall':rr,'auroc':float(roc_auc_score(y,s)) if len(set(y))==2 else None,
        'brier':float(np.mean((s-y)**2)),'true_robust':int(sum(p&(y==1))),'true_nonrobust':int(sum(~p&(y==0))),
        'false_robust':int(sum(p&(y==0))),'false_nonrobust':int(sum(~p&(y==1)))}
def compare(y,candidate,reference,groups):
    y=np.array(y);c=np.array(candidate)>=.5;r=np.array(reference)>=.5;group_array=np.array(groups)
    ix=[np.flatnonzero(group_array==g) for g in sorted(set(groups))]
    delta=np.array([int(sum((c[k]==y[k]).astype(int)-(r[k]==y[k]).astype(int))) for k in ix]);sizes=np.array([len(k) for k in ix])
    draws=np.random.default_rng(SEED).integers(len(ix),size=(P['readout']['bootstrap'],len(ix)))
    boot=delta[draws].sum(1)/sizes[draws].sum(1);total=int(delta.sum())
    return {'net_correct':total,'accuracy_gain':total/len(y),'family_bootstrap95':np.quantile(boot,[.025,.975]).tolist(),
        'candidate_only_correct':int(sum((c==y)&(r!=y))),'reference_only_correct':int(sum((c!=y)&(r==y))),
        'benefiting_families':int(sum(delta>0)),'harmed_families':int(sum(delta<0)),
        'minimum_gain_after_removing_one_family':min(float((total-d)/(len(y)-n)) for d,n in zip(delta,sizes))}
def decision(results,comparisons,reference_valid):
    references=P['references'];best=max(results[a]['correct'] for a in references)
    strongest=[a for a in references if results[a]['correct']==best];candidate=results['geometry']
    checks={'all_43_measurements_reference_validated':bool(reference_valid),
        'three_more_correct_than_strongest_reference':candidate['correct']-best>=3,
        'positive_family_bootstrap_lower_vs_each_reference':all(comparisons[a]['family_bootstrap95'][0]>0 for a in references),
        'benefit_in_three_families_vs_each_strongest_reference':all(comparisons[a]['benefiting_families']>=3 for a in strongest),
        'no_single_family_reversal_vs_each_strongest_reference':all(comparisons[a]['minimum_gain_after_removing_one_family']>=0 for a in strongest),
        'nonrobust_recall_preserved_vs_each_strongest_reference':all(candidate['nonrobust_recall']>=results[a]['nonrobust_recall'] for a in strongest)}
    return {'passed':all(checks.values()),'checks':checks,'failed_checks':[k for k,v in checks.items() if not v],
        'strongest_references':strongest,'net_gain_vs_strongest':candidate['correct']-best}
def matrices_for(cases,profiles,geometry=None):
    models=sorted({c['model'] for c in cases});matrices={a:[] for a in ('always_robust','model','structure','aggregate','prose_control','temporal')}
    if geometry is not None:matrices.update(geometry=[],combined=[])
    for c in cases:
        p=profiles[c['id']];base=p['vectors']['aggregate'];temporal=temporal_features(p['trace'])
        matrices['always_robust'].append([1.]);matrices['model'].append([float(c['model']==m) for m in models])
        for arm in ('structure','aggregate','prose_control'):matrices[arm].append(p['vectors'][arm])
        matrices['temporal'].append(base+temporal)
        if geometry is not None:
            g=geometry[c['id']]['features'];matrices['geometry'].append(base+g);matrices['combined'].append(base+temporal+g)
    return {a:np.asarray(v,float) for a,v in matrices.items()}
def evaluate(cases,profiles,labels,out,geometry=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);groups=[c['family'] for c in cases];y=np.array([labels[c['id']] for c in cases],int)
    matrices=matrices_for(cases,profiles,geometry);scores,split=oof(matrices,y,groups);results={a:metrics(y,s) for a,s in scores.items()}
    by_model={m:{a:metrics(y[ix],s[ix]) for a,s in scores.items()} for m in sorted({c['model'] for c in cases}) for ix in [np.array([c['model']==m for c in cases])]}
    rows=[{'id':c['id'],'model':c['model'],'family':c['family'],'label':bool(y[i]),
        'scores':{a:float(s[i]) for a,s in scores.items()},'predictions':{a:bool(s[i]>=.5) for a,s in scores.items()}} for i,c in enumerate(cases)]
    summary={'version':P['version'],'n':len(y),'families':len(set(groups)),'metrics':results,'by_model':by_model,
        'status':'TEMPORAL_DEVELOPMENT_ONLY','primary_evaluated':False,'interpretation':P['interpretation'],
        'old_scores_not_comparable':'All controls are refitted under the new fixed unweighted rule. The old balanced readout remains frozen separately.',
        'secondary_scope':P['secondary'],'bootstrap_scope':P['bootstrap_scope']}
    if geometry is not None:
        if set(geometry)!={c['id'] for c in cases}:raise ValueError('Primary evaluation requires all 43 cases')
        checks=all(any(geometry[c['id']]['reference_checked'] for c in cases if c['model']==m) for m in by_model)
        comparisons={a:compare(y,scores['geometry'],scores[a],groups) for a in P['references']}
        d=decision(results,comparisons,checks)
        summary.update(primary_evaluated=True,decision=d,comparisons=comparisons,status='PROMISING_DEVELOPMENT_SIGNAL' if d['passed'] else 'NO_CLEAR_INCREMENTAL_GAIN')
    save(out/'summary.json',summary);save(out/'held_out_predictions.json',rows);save(out/'family_folds.json',split)
    save(out/'fitted_readouts.json',{a:fit(x,y) for a,x in matrices.items() if a!='always_robust'})
    family_rows=[]
    for family in sorted(set(groups)):
        ix=np.array(groups)==family;row={'family':family,'cases':int(sum(ix)),'nonrobust':int(sum(y[ix]==0))}
        row.update({a:int(sum((s[ix]>=.5)==y[ix])) for a,s in scores.items()});family_rows.append(row)
    with (out/'family_results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(family_rows[0]));writer.writeheader();writer.writerows(family_rows)
    lines=[summary['status']+': 43 public development cases / 20 held-out families.',P['interpretation'],'']
    for a,m in results.items():lines.append(f"{a}: {m['correct']}/43; accuracy={m['accuracy']:.4f}; balanced accuracy={m['balanced_accuracy']:.4f}; nonrobust recall={m['nonrobust_recall']:.4f}")
    if geometry is not None:lines+=['','Primary only: geometry. Strongest references: '+', '.join(summary['decision']['strongest_references']),
        'Net correct gain vs strongest: '+str(summary['decision']['net_gain_vs_strongest']),
        'Failed gates: '+', '.join(summary['decision']['failed_checks']),
        'Next: external validation on genuinely new families.' if d['passed'] else 'Stop this geometry branch. Do not search layers/thresholds or substitute a secondary arm on these results.']
    else:lines+=['','Geometry not collected: no primary verdict or submission export.']
    (out/'decision_report.txt').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True)
    return summary
