"""Fixed exploratory CaSR representation and interval tests; CPU only."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from rdkit import Chem,rdBase
from rdkit.Chem import Descriptors
from chemistry import build,monomer,tokenize

ROOT=Path(__file__).resolve().parent
INPUT=ROOT/'input'
OUTPUT=ROOT/'output'
ALPHA=10.
DESC=['MW','MolLogP','TPSA','HBD','HBA','RotatableBonds']

def descriptors(m):
    return np.array([Descriptors.MolWt(m),Descriptors.MolLogP(m),Descriptors.TPSA(m),Descriptors.NumHDonors(m),Descriptors.NumHAcceptors(m),Descriptors.NumRotatableBonds(m)],float)

def represent(row):
    link,parts=tokenize(row['name']);m=build(row['name'])
    assert Chem.MolToSmiles(m,isomericSmiles=True)==Chem.MolToSmiles(Chem.MolFromSmiles(row['SMILES']),isomericSmiles=True)
    middle=descriptors(monomer(parts[1])[0]);tail=parts[2:]
    tail_desc=sum((descriptors(monomer(p)[0]) for p in tail),start=np.zeros(6))
    hydroxy=int(bool(tail) and monomer(tail[0])[0].GetAtomWithIdx(monomer(tail[0])[1]).GetAtomicNum()==8)
    gly=int(tail==['Gly'])
    base=np.r_[middle,int(parts[1].startswith('D-')),int('allo-' in parts[1]),tail_desc,len(tail),hydroxy,gly,
        sum(p.startswith('D-') for p in tail),sum('allo-' in p for p in tail)]
    inter=np.r_[base,middle*gly,middle*hydroxy]
    return base,inter,middle,'|'.join(tail) or '<none>'

def interval_fit(x,lo,hi,alpha=ALPHA):
    initial=Ridge(alpha=alpha).fit(x,(lo+hi)/2)
    start=np.r_[initial.coef_,initial.intercept_]
    def objective(z):
        prediction=x@z[:-1]+z[-1];residual=prediction-np.clip(prediction,lo,hi)
        value=.5*(residual@residual+alpha*(z[:-1]@z[:-1]))
        grad=np.r_[x.T@residual+alpha*z[:-1],residual.sum()]
        return value,grad
    fit=minimize(objective,start,method='L-BFGS-B',jac=True,options={'maxiter':1000,'ftol':1e-13,'gtol':1e-8})
    if not fit.success:raise RuntimeError('Interval optimization failed: '+str(fit.message))
    return fit.x[:-1],fit.x[-1],int(fit.nit)

def paired_gain(a,b,groups):
    delta=np.asarray(a)-np.asarray(b);groups=np.asarray(groups);keys=sorted(set(groups))
    sums=np.array([delta[groups==g].sum() for g in keys]);counts=np.array([(groups==g).sum() for g in keys])
    rng=np.random.default_rng(2701026);ix=rng.integers(len(keys),size=(10000,len(keys)))
    boot=sums[ix].sum(1)/counts[ix].sum(1)
    return float(delta.mean()),float(np.quantile(boot,.025)),float(np.quantile(boot,.975))

def main():
    global INPUT,OUTPUT
    ap=argparse.ArgumentParser();ap.add_argument('--input-dir',type=Path,default=ROOT/'input');ap.add_argument('--output-dir',type=Path,default=ROOT/'output');a=ap.parse_args()
    INPUT=a.input_dir;OUTPUT=a.output_dir
    start=time.monotonic();OUTPUT.mkdir(exist_ok=True)
    # Independent convex-loss check: exact point labels must reproduce Ridge.
    rng=np.random.default_rng(51);xx=rng.normal(size=(15,4));yy=rng.normal(size=15)
    coef,inter,_=interval_fit(xx,yy,yy);rr=Ridge(alpha=ALPHA).fit(xx,yy)
    np.testing.assert_allclose(xx@coef+inter,rr.predict(xx),atol=1e-7,rtol=0)
    data=pd.read_csv(INPUT/'chemical_activity_dataset.csv');data=data[data.hek293_status.isin(['numeric','range'])].copy().set_index('name',verify_integrity=True)
    prior=pd.read_csv(INPUT/'held_out_predictions.csv');all_predictions=[];summaries=[];domains=[]
    for version in sorted(prior.version.unique()):
        # Family/random folds share the identical endpoint assignments.
        labels=prior[(prior.version==version)&(prior.split=='leave_middle_family_out')&(prior.model=='median')].copy().sort_values('name').reset_index(drop=True)
        names=labels.name.tolist();d=data.loc[names].reset_index();assert len(d)==58
        rep=[represent(r) for r in d.to_dict('records')];base=np.array([r[0] for r in rep]);interaction=np.array([r[1] for r in rep]);middle=np.array([r[2] for r in rep]);tail=np.array([r[3] for r in rep])
        y=labels.observed_pEC50.to_numpy();lo=6-np.log10(d.hek293_high_uM.to_numpy());hi=6-np.log10(d.hek293_low_uM.to_numpy())
        # Reuse the six explicit alternate assignments from the old benchmark.
        # Their range widths also differ, so do not infer them from midpoints.
        if version!='journal':
            alt={'γ-Glu-Val-Glycolicacid':(.14,.14),'γ-Glu-Tle-Glycolicacid':(.05,.05),'γ-Glu-Abu-Glycolicacid':(.065,.079),
                'γ-Glu-Val-L-Lacticacid':(.057,.057),'γ-Glu-Tle-L-Lacticacid':(.038,.038),'γ-Glu-Abu-L-Lacticacid':(.102,.102)}
            for i,n in enumerate(names):
                if n in alt:a,b=alt[n];lo[i]=6-np.log10(b);hi[i]=6-np.log10(a)
        np.testing.assert_allclose((lo+hi)/2,y,atol=1e-12,rtol=0)
        for split in ['leave_middle_family_out','random_5fold']:
            old=prior[(prior.version==version)&(prior.split==split)]
            fold=old[old.model=='median'].set_index('name').loc[names].fold.to_numpy()
            models={m:np.full(58,np.nan) for m in ['mean','median','existing_nearest3','positional_ridge','context_interaction_ridge','interval_context_ridge']}
            models['existing_nearest3']=old[old.model=='nearest3'].set_index('name').loc[names].predicted_pEC50.to_numpy()
            outside=np.zeros(58,bool);unknown_tail=np.zeros(58,bool);mindistance=np.zeros(58);iterations=[]
            for f in sorted(set(fold)):
                test=fold==f;train=~test
                if split=='leave_middle_family_out':assert not set(labels.loc[test,'middle_group_key'])&set(labels.loc[train,'middle_group_key'])
                models['mean'][test]=y[train].mean();models['median'][test]=np.median(y[train])
                for m,x in [('positional_ridge',base),('context_interaction_ridge',interaction)]:
                    scaler=StandardScaler().fit(x[train]);xt=scaler.transform(x[train]);xq=scaler.transform(x[test])
                    models[m][test]=Ridge(alpha=ALPHA).fit(xt,y[train]).predict(xq)
                    if m=='context_interaction_ridge':
                        w,b,it=interval_fit(xt,lo[train],hi[train]);models['interval_context_ridge'][test]=xq@w+b;iterations.append(it)
                outside[test]=((middle[test]<middle[train].min(0)-1e-12)|(middle[test]>middle[train].max(0)+1e-12)).any(1)
                unknown_tail[test]=np.array([t not in set(tail[train]) for t in tail[test]])
                sc=StandardScaler().fit(middle[train]);q=sc.transform(middle[test]);tr=sc.transform(middle[train])
                mindistance[test]=np.sqrt(((q[:,None,:]-tr[None,:,:])**2).sum(2)).min(1)
            oldmed=old[old.model=='median'].set_index('name').loc[names].predicted_pEC50.to_numpy()
            np.testing.assert_allclose(models['median'],oldmed,atol=1e-12,rtol=0)
            referror=abs(y-models['existing_nearest3']);groups=labels.middle_group_key.to_numpy()
            for m,pred in models.items():
                assert np.isfinite(pred).all()
                err=abs(y-pred);distance=abs(pred-np.clip(pred,lo,hi));gain,low,high=paired_gain(referror,err,groups)
                summaries.append({'version':version,'split':split,'model':m,'n':58,'groups':len(set(groups)),
                    'midpoint_MAE':float(err.mean()),'interval_distance_MAE':float(distance.mean()),'within_3fold':float((err<=np.log10(3)).mean()),
                    'MAE_gain_over_existing_nearest3':gain,'gain_95pct_low':low,'gain_95pct_high':high,
                    'outside_middle_training_box':int(outside.sum()),'unseen_tail_context':int(unknown_tail.sum()),
                    'MAE_in_middle_training_box':float(err[~outside].mean()) if (~outside).any() else None,
                    'MAE_outside_middle_training_box':float(err[outside].mean()) if outside.any() else None})
                all_predictions.extend({'version':version,'split':split,'model':m,'name':n,'group':groups[i],'fold':int(fold[i]),'observed_midpoint':float(y[i]),
                    'observed_low':float(lo[i]),'observed_high':float(hi[i]),'prediction':float(pred[i]),'outside_middle_training_box':bool(outside[i]),
                    'unseen_tail_context':bool(unknown_tail[i]),'nearest_training_middle_distance':float(mindistance[i])} for i,n in enumerate(names))
            domains.append({'version':version,'split':split,'n':58,'base_features':base.shape[1],'interaction_features':interaction.shape[1],
                'outside_middle_training_box':int(outside.sum()),'unseen_tail_context':int(unknown_tail.sum()),'maximum_interval_optimizer_iterations':max(iterations)})
    pd.DataFrame(summaries).to_csv(OUTPUT/'model_comparison.csv',index=False);pd.DataFrame(all_predictions).to_csv(OUTPUT/'fold_predictions.csv',index=False)
    pd.DataFrame(domains).to_csv(OUTPUT/'domain_coverage.csv',index=False)
    # Separate task: predicting the change from a measured core to its Gly
    # analogue. This is not a claim of predicting an unseen core's full potency.
    pairs=pd.read_csv(INPUT/'glycine_extension_bounds.csv');z=np.array([descriptors(monomer(s)[0]) for s in pairs.middle]);delta=(pairs.delta_pEC50_low+pairs.delta_pEC50_high).to_numpy()/2
    predmean=np.empty(len(pairs));predridge=np.empty(len(pairs));pairrows=[]
    for i in range(len(pairs)):
        train=np.arange(len(pairs))!=i;sc=StandardScaler().fit(z[train]);predmean[i]=delta[train].mean();predridge[i]=Ridge(alpha=ALPHA).fit(sc.transform(z[train]),delta[train]).predict(sc.transform(z[[i]]))[0]
        pairrows.append({'middle':pairs.middle.iloc[i],'observed_low':pairs.delta_pEC50_low.iloc[i],'observed_high':pairs.delta_pEC50_high.iloc[i],
            'observed_midpoint':delta[i],'training_mean_delta':predmean[i],'residue_ridge_delta':predridge[i]})
    pd.DataFrame(pairrows).to_csv(OUTPUT/'glycine_effect_predictions.csv',index=False)
    gain,low,high=paired_gain(abs(delta-predmean),abs(delta-predridge),pairs.middle.to_numpy())
    pairsummary={'pairs':len(pairs),'training_mean_delta_MAE':float(abs(delta-predmean).mean()),'residue_ridge_delta_MAE':float(abs(delta-predridge).mean()),
        'gain':gain,'gain_95pct_low':low,'gain_95pct_high':high,'interpretation':'Eleven same-source pairs, one fixed model; no independent-study confirmation.'}
    primary=[r for r in summaries if r['split']=='leave_middle_family_out' and r['model']=='positional_ridge']
    result={'protocol_sha256':hashlib.sha256((ROOT/'protocol.json').read_bytes()).hexdigest(),'runtime_seconds':time.monotonic()-start,'rdkit':rdBase.rdkitVersion,
        'verified_exact_stereochemical_graphs':58,'fixed_alpha':ALPHA,'primary_passed_exploratory_gain_gate':all(r['gain_95pct_low']>0 for r in primary),
        'primary':primary,'glycine_effect_prediction':pairsummary,'domain_definition':'Training-only middle-fragment descriptor min/max box and exact tail-context presence, descriptive not a calibrated chemical applicability domain.',
        'limits':['New models on previously inspected data; frozen settings before this run do not create independent confirmation.','Reported source ranges are not confidence intervals.','Bootstrap intervals are conditional on fitted models; secondary comparisons do not justify selecting a winner.','No sensory prediction, sodium-reduction result or proposed-compound potency is established.']}
    (OUTPUT/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(pd.DataFrame(summaries).query('split=="leave_middle_family_out"')[['version','model','midpoint_MAE','interval_distance_MAE','gain_95pct_low','gain_95pct_high']].to_string(index=False),flush=True)
    print(json.dumps(result,indent=2,allow_nan=False),flush=True)
if __name__=='__main__':main()
