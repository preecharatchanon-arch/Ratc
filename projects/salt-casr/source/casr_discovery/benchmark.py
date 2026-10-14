"""Fixed-model chemical-family evaluation and candidate ranking, exploratory."""
import json, math, time
from pathlib import Path
import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import Descriptors, rdFingerprintGenerator, rdDepictor
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import LeaveOneGroupOut, KFold
from sklearn.metrics import mean_absolute_error, r2_score
from scipy.stats import spearmanr
from chemistry import build, tokenize, identity, middle_group

ROOT=Path(__file__).resolve().parent; OUT=ROOT/'results'; OUT.mkdir(exist_ok=True)
GEN=rdFingerprintGenerator.GetMorganGenerator(radius=2,fpSize=2048,includeChirality=True)
ALT={
 'γ-Glu-Val-Glycolicacid':(.14,.14), 'γ-Glu-Tle-Glycolicacid':(.05,.05), 'γ-Glu-Abu-Glycolicacid':(.065,.079),
 'γ-Glu-Val-L-Lacticacid':(.057,.057), 'γ-Glu-Tle-L-Lacticacid':(.038,.038), 'γ-Glu-Abu-L-Lacticacid':(.102,.102)}

def features(mols):
    fp=np.asarray([GEN.GetFingerprintAsNumPy(m) for m in mols],dtype=float)
    desc=np.array([[Descriptors.MolWt(m),Descriptors.MolLogP(m),Descriptors.TPSA(m),Descriptors.NumHDonors(m),Descriptors.NumHAcceptors(m),Descriptors.NumRotatableBonds(m)] for m in mols])
    return fp,desc

def similarity(a,b):
    dot=a@b.T; return dot/np.maximum(a.sum(1)[:,None]+b.sum(1)[None,:]-dot,1)

def predictions(x,d,y,q,qd):
    k=similarity(q,x); nearest=np.argsort(-k,axis=1)[:,:3]
    weights=np.take_along_axis(k,nearest,axis=1)**2
    total=weights.sum(1)
    knn=np.full(len(q),np.median(y))
    np.divide((weights*y[nearest]).sum(1),total,out=knn,where=total>0)
    # Tanimoto kernel ridge; fixed regularization, without tuning on test folds.
    alpha=np.linalg.solve(similarity(x,x)+.1*np.eye(len(x)),y)
    kr=k@alpha
    scaler=StandardScaler().fit(d)
    ridge=Ridge(alpha=10).fit(scaler.transform(d),y).predict(scaler.transform(qd))
    et=ExtraTreesRegressor(n_estimators=256,min_samples_leaf=2,max_features=.5,random_state=777,n_jobs=2).fit(np.hstack([x,scaler.transform(d)]),y).predict(np.hstack([q,scaler.transform(qd)]))
    return {'median':np.full(len(q),np.median(y)), 'nearest3':knn, 'tanimoto_ridge':kr,'descriptor_ridge':ridge,'extra_trees':et}

def main():
    started=time.monotonic()
    source=pd.read_csv(ROOT.parent/'toolkit_pilot/results/casr_compounds_for_datawarrior.csv')
    rows=[]; exclusions=[]; mols={}
    for rec in source.to_dict('records'):
        try: mol=build(rec['compound'])
        except ValueError as e: exclusions.append({'compound':rec['compound'],'reason':str(e)});continue
        name=''.join(rec['compound'].split()); mols[name]=mol
        rec['name']=name;rec['SMILES'],rec['formula']=identity(mol)
        _,parts=tokenize(name);rec['middle_family'],rec['middle_group_key']=middle_group(name)
        rec['terminal_family']='dipeptide' if len(parts)==2 else parts[-1].replace('D-','')
        rows.append(rec)
    allrows=pd.DataFrame(rows);allrows.to_csv(OUT/'chemical_activity_dataset.csv',index=False)
    pd.DataFrame(exclusions).to_csv(OUT/'structure_exclusions.csv',index=False)
    data=allrows[allrows.hek293_status.isin(['numeric','range'])].reset_index(drop=True)
    x,d=features([mols[n] for n in data.name]); group=data.middle_group_key.to_numpy()
    family_labels=data.middle_family.to_numpy()
    candidates=[]
    for middle in ['Ala','Abu','Nva','Val','Ser','Ser(Me)','Algly','Tle','Aib','Cle','Hse','Ile','Leu','Cys']:
        for cap in ['Gly','Glycolicacid','L-Lacticacid']:
            name=f'γ-Glu-{middle}-{cap}'
            if name in mols:continue
            mol=build(name);s,f=identity(mol);label,key=middle_group(name)
            candidates.append({'name':name,'SMILES':s,'formula':f,'middle_family':label,'middle_group_key':key,'terminal_family':cap,'MW':Descriptors.MolWt(mol)})
            mols[name]=mol
    candidate=pd.DataFrame(candidates);cx,cd=features([mols[n] for n in candidate.name])
    metrics=[]; oof=[]; candidate_preds=[]; inactive_predictions=[]
    for version in ['journal','patent_assignment_sensitivity']:
        low=data.hek293_low_uM.to_numpy().copy();high=data.hek293_high_uM.to_numpy().copy()
        if version!='journal':
            for i,n in enumerate(data.name):
                if n in ALT:low[i],high[i]=ALT[n]
        y=6-np.log10(np.sqrt(low*high))
        for split,iterator in [('leave_middle_family_out',LeaveOneGroupOut().split(x,y,group)),('random_5fold',KFold(5,shuffle=True,random_state=777).split(x))]:
            fitted={m:np.full(len(y),np.nan) for m in ['median','nearest3','tanimoto_ridge','descriptor_ridge','extra_trees']}
            for fold,(train,test) in enumerate(iterator):
                pred=predictions(x[train],d[train],y[train],x[test],d[test])
                for model,p in pred.items():
                    fitted[model][test]=p
                    oof.extend({'version':version,'split':split,'fold':fold,'model':model,'name':data.name.iloc[i],'held_out_middle_family':family_labels[i],'middle_group_key':group[i],'observed_pEC50':y[i],'predicted_pEC50':v} for i,v in zip(test,p))
            for model,p in fitted.items():
                metrics.append({'version':version,'split':split,'model':model,'n':len(y),'MAE_log10':mean_absolute_error(y,p),'R2':r2_score(y,p),'spearman':float(spearmanr(y,p).statistic),'within_3fold':float((np.abs(y-p)<=np.log10(3)).mean())})
        pred=predictions(x,d,y,cx,cd)
        for model,p in pred.items():
            if model=='median':continue
            candidate_preds.extend({'version':version,'model':model,'name':n,'predicted_pEC50':v,'implied_EC50_uM':10**(6-v)} for n,v in zip(candidate.name,p))
        # Sensitivity to leaving out all examples of the candidate's middle residue.
        for family in sorted(candidate.middle_group_key.unique()):
            test=np.where(candidate.middle_group_key==family)[0];train=np.where(group!=family)[0]
            if len(train)==len(y):continue
            pred=predictions(x[train],d[train],y[train],cx[test],cd[test])
            for model,p in pred.items():
                if model=='median':continue
                candidate_preds.extend({'version':version,'model':model+'_middle_excluded','name':candidate.name.iloc[i],'predicted_pEC50':v,'implied_EC50_uM':10**(6-v)} for i,v in zip(test,p))
        inactive=allrows[allrows.hek293_status.isin(['reported_inactive','lower_bound'])]
        ix,id_=features([mols[n] for n in inactive.name]);pred=predictions(x,d,y,ix,id_)
        inactive_predictions.extend({'version':version,'model':m,'name':n,'reported_status':s,'predicted_pEC50':v,'implied_EC50_uM':10**(6-v)} for m,p in pred.items() if m!='median' for n,s,v in zip(inactive.name,inactive.hek293_status,p))
    pd.DataFrame(metrics).to_csv(OUT/'model_metrics.csv',index=False);pd.DataFrame(oof).to_csv(OUT/'held_out_predictions.csv',index=False)
    cp=pd.DataFrame(candidate_preds);cp.to_csv(OUT/'candidate_predictions.csv',index=False)
    pd.DataFrame(inactive_predictions).to_csv(OUT/'inactive_and_censored_diagnostic.csv',index=False)
    # Report agreement and extrapolation shift, not a falsely calibrated confidence interval.
    full=cp[~cp.model.str.endswith('_middle_excluded')].groupby('name').predicted_pEC50.agg(['median','min','max'])
    excluded=cp[cp.model.str.endswith('_middle_excluded')].groupby('name').predicted_pEC50.median()
    candidate=candidate.join(full,on='name').rename(columns={'median':'ensemble_median_pEC50','min':'lowest_prediction_pEC50','max':'highest_prediction_pEC50'})
    candidate['middle_excluded_median_pEC50']=candidate.name.map(excluded)
    candidate['model_spread_log10']=candidate.highest_prediction_pEC50-candidate.lowest_prediction_pEC50
    sim=similarity(cx,x);nearest=sim.argmax(1)
    candidate['nearest_measured_compound']=data.name.to_numpy()[nearest];candidate['nearest_similarity']=sim.max(1)
    candidate['novelty_status']='Absent from this extracted series; external novelty requires checking'
    candidate=candidate.sort_values('ensemble_median_pEC50',ascending=False);candidate.to_csv(OUT/'candidate_shortlist.csv',index=False)
    with Chem.SDWriter(str(OUT/'candidate_library.sdf')) as w:
        for rec in candidate.to_dict('records'):
            m=mols[rec['name']];rdDepictor.Compute2DCoords(m);m.SetProp('_Name',rec['name']);m.SetProp('novelty_status',rec['novelty_status']);w.write(m)
    pairs=[]
    for middle in ['Ala','Cys','Nva','Abu','Tle','Nle']:
        names=[f'γ-Glu-{middle}',f'γ-Glu-{middle}-Gly'];sub=data[data.name.isin(names)].set_index('name')
        if len(sub)==2:
            a,b=sub.loc[names[0]],sub.loc[names[1]]
            pairs.append({'middle':middle,'dipeptide_EC50_low_uM':a.hek293_low_uM,'dipeptide_EC50_high_uM':a.hek293_high_uM,'glycine_appended_EC50_low_uM':b.hek293_low_uM,'glycine_appended_EC50_high_uM':b.hek293_high_uM,'glycine_potency_gain_low':a.hek293_low_uM/b.hek293_high_uM,'glycine_potency_gain_high':a.hek293_high_uM/b.hek293_low_uM})
    pd.DataFrame(pairs).to_csv(OUT/'matched_glycine_extension_effects.csv',index=False)
    summary={'numerical_compounds':len(data),'middle_families':len(set(group)),'grouping_rule':'Canonical non-stereochemical SMILES of isolated middle monomer; L/D and allo variants held out together.','explicit_graphs':len(allrows),'untested_in_series_candidates':len(candidate),'versions':2,'runtime_s':time.monotonic()-started,'scope':'Exploratory within-series chemical generalization; not independent sensory validation or calibrated efficacy prediction.'}
    (OUT/'run_summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
    print(pd.DataFrame(metrics).query('version=="journal" and split=="leave_middle_family_out"').to_string(index=False))
    print(candidate[['name','ensemble_median_pEC50','model_spread_log10','middle_excluded_median_pEC50','nearest_similarity']].head(12).to_string(index=False))

if __name__=='__main__':main()
