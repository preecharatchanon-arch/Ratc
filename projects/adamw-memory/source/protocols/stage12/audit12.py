"""Independent NumPy audit of all raw Stage12 branches."""
import json,math,hashlib
from pathlib import Path
import numpy as np
def load(f):
    with np.load(f,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
def js(f):return json.loads(Path(f).read_text())
def require(ok,msg):
    if not ok:raise ValueError(msg)
def center(x):x=np.asarray(x,dtype=np.float64);return x-x.mean(-1,keepdims=True)
def rms(x):return float(np.sqrt(np.mean(np.square(x))))
def metrics(full,proj,rem=None,floor=2e-5):
    f=center(full);v=center(proj);nf=float(np.linalg.norm(f));nv=float(np.linalg.norm(v));resolved=rms(f)>=floor
    m=dict(full_rms=rms(f),projected_rms=rms(v),resolved=resolved,
        relative_prediction_error=float(np.linalg.norm(f-v)/nf) if resolved else None,
        cosine=float(np.sum(f*v)/(nf*nv)) if resolved and nv>0 else None,retention=nv/nf if resolved else None)
    if rem is not None:
        r=center(rem);m.update(remainder_ratio=float(np.linalg.norm(r)/nf) if resolved else None,additivity_error=float(np.linalg.norm(f-v-r)/nf) if resolved else None)
    return m
def helmert(C):
    q=np.zeros((C,C-1))
    for k in range(1,C):q[:k,k-1]=1/math.sqrt(k*(k+1));q[k,k-1]=-k/math.sqrt(k*(k+1))
    return q
def audit_unit(folder,c):
    f=Path(folder);d=load(f/'directions.npz');cut=load(f/'cut_state.npz');geometry=js(f/'geometry.json');roles=js(f/'roles.json')
    expected=['full']+[n for r in (c.primary_rank,c.diagnostic_rank) for label in ('immediate','horizon') for n in (f'{label}{r}',f'remainder_{label}{r}')]+['gradient','random']
    require(set(d)==set(expected),'Directions are incomplete');require(abs(np.linalg.norm(d['full'])-1)<2e-5,'Full direction normalization')
    for r in (c.primary_rank,c.diagnostic_rank):
        for label in ('immediate','horizon'):
            a=d[f'{label}{r}'].astype(np.float64);b=d[f'remainder_{label}{r}'].astype(np.float64)
            require(np.linalg.norm(a+b-d['full'])<2e-5 and abs(a@b)<2e-5,'Projection decomposition or orthogonality failed')
    result=dict(seed=roles['seed'],paths={})
    all_branches={}
    for path in c.future_paths:
        out=f/f'path{path}';names=['baseline']+[f'{k}_{s}' for k in expected for s in ('plus','minus')]+['full_half_plus','full_half_minus']
        branches={n:load(out/f'branch_{n}.npz') for n in names};all_branches[path]=branches
        base=branches['baseline'];scores={n:js(out/f'branch_{n}.json')['endpoint'] for n in names};pred=load(out/'predictions.npz')
        for n,b in branches.items():
            require(all(np.isfinite(a).all() for a in b.values()),'Nonfinite branch data');require(np.array_equal(b['h0'],base['h0']),'Moment surgery changed cut logits')
            require(all(f'h{h}' in b for h in c.horizons),'Missing horizon')
            if n=='baseline':want=np.zeros_like(d['full'])
            else:
                key='full' if n.startswith('full_half') else n.rsplit('_',1)[0];scale=.5 if n.startswith('full_half') else 1.;sign=1 if n.endswith('plus') else -1
                want=d[key]*np.float32(geometry['displacement']*scale*sign)
            actual=(cut['m']+want)-cut['m'];digest=lambda a:hashlib.sha256(a.tobytes()).digest()
            require(b['requested_delta_sha256'].tobytes()==digest(want) and b['actual_delta_sha256'].tobytes()==digest(actual),'Intervention vector digest mismatch')
            rounding=float(np.linalg.norm(actual-want)/max(np.linalg.norm(want),1e-30));require(rounding<.003 and np.isclose(rounding,b['moment_rounding'],rtol=1e-4,atol=1e-9),'Intervention rounding failed')
        report=dict(branch_count=len(names),horizons={},finite_difference_controls={},capture={},endpoint_scores=scores,
            endpoint_effects={n:dict(accuracy_delta=scores[n]['accuracy']-scores['baseline']['accuracy'],nll_delta=scores[n]['nll']-scores['baseline']['nll']) for n in names})
        for h in c.horizons:
            central={k:(branches[k+'_plus'][f'h{h}'].astype(np.float64)-branches[k+'_minus'][f'h{h}'])/2 for k in expected};tab={}
            for k in expected:
                m=metrics(central['full'],central[k],central.get('remainder_'+k),c.resolution_floor)
                plus=branches[k+'_plus'][f'h{h}'].astype(np.float64)-base[f'h{h}'];minus=branches[k+'_minus'][f'h{h}'].astype(np.float64)-base[f'h{h}']
                m.update(plus_baseline_rms=rms(center(plus)),minus_baseline_rms=rms(center(minus)),even_rms=rms(center((plus+minus)/2)));tab[k]=m
            report['horizons'][str(h)]=tab
            if h in (1,c.fit_horizon):
                n,C=base[f'h{h}'].shape;Q=helmert(C);controls={}
                for k in expected:
                    predicted=pred[f'{k}_h{h}'].reshape(n,C-1)@Q.T*math.sqrt(n*C);m=metrics(central[k],predicted,floor=c.resolution_floor)
                    m['valid']=m['resolved'] and m['relative_prediction_error']<=c.derivative_error_max;controls[k]=m
                half=(branches['full_half_plus'][f'h{h}'].astype(np.float64)-branches['full_half_minus'][f'h{h}'])/2
                predicted=pred[f'full_h{h}'].reshape(n,C-1)@Q.T*math.sqrt(n*C)*.5;m=metrics(half,predicted,floor=c.resolution_floor)
                m['valid']=m['resolved'] and m['relative_prediction_error']<=c.derivative_error_max;controls['full_half']=m
                controls['amplitude_consistency']=metrics(central['full'],2*half,floor=c.resolution_floor);report['finite_difference_controls'][str(h)]=controls
                raw=load(out/f'capture_h{h}.npz');trace=raw['trace_squared_norms'];require(len(trace)==c.trace_probes,'Missing trace probes');mean=float(trace.mean());se=float(trace.std(ddof=1)/math.sqrt(len(trace)))
                capture=dict(trace=dict(estimate=mean,monte_carlo_se=se,probes=len(trace)))
                for r in (c.primary_rank,c.diagnostic_rank):
                    for label in ('immediate','horizon'):
                        energy=float(np.square(raw[label+'_action'][:,:r].astype(np.float64)).sum());capture[f'{label}{r}']=dict(energy=energy,capture_estimate=energy/mean,capture_mc_interval=[energy/(mean+1.96*se),energy/max(mean-1.96*se,np.finfo(float).tiny)])
                report['capture'][str(h)]=capture
        result['paths'][str(path)]=report
    if 0 in all_branches and 1 in all_branches:
        for name in all_branches[0]:require(np.array_equal(all_branches[0][name]['h1'],all_branches[1][name]['h1']),'Paths differ before first independent batch')
    primary=result['paths']['0']['horizons'][str(c.fit_horizon)];r=c.primary_rank
    result['primary_error_improvement']=None if not primary['full']['resolved'] else primary[f'immediate{r}']['relative_prediction_error']-primary[f'horizon{r}']['relative_prediction_error']
    checks=result['paths']['0']['finite_difference_controls'][str(c.fit_horizon)]
    result['primary_derivative_controls_valid']=all(checks[k]['valid'] for k in ('full','full_half',f'immediate{r}',f'horizon{r}'))
    return result
def summary(values):
    values=[v for v in values if v is not None]
    if not values:return dict(n=0,mean=None,values=[])
    a=np.asarray(values);g=np.random.default_rng(770012);means=a[g.integers(len(a),size=(5000,len(a)))].mean(1)
    return dict(n=len(a),mean=float(a.mean()),min=float(a.min()),max=float(a.max()),values=values,descriptive_seed_bootstrap_95_interval=np.quantile(means,[.025,.975]).tolist())
def audit_all(root,c):
    root=Path(root);units=[audit_unit(root/'units'/f'CIFAR10_{s}',c) for s in c.seeds]
    complete=all((root/'units'/f'CIFAR10_{s}'/'COMPLETE.json').exists() for s in c.seeds);primary=summary([u['primary_error_improvement'] for u in units]);valid=complete and all(u['primary_derivative_controls_valid'] for u in units)
    gain=bool(valid and primary['n']==len(c.seeds) and primary['mean']>=.10 and primary['min']>0 and primary['descriptive_seed_bootstrap_95_interval'][0]>0)
    contrasts={}
    for path in c.future_paths:
        for r in (c.primary_rank,c.diagnostic_rank):
            for h in c.horizons:
                vs=[]
                for u in units:
                    t=u['paths'][str(path)]['horizons'][str(h)];vs.append(None if not t['full']['resolved'] else t[f'immediate{r}']['relative_prediction_error']-t[f'horizon{r}']['relative_prediction_error'])
                contrasts[f'path{path}_rank{r}_h{h}']=summary(vs)
    return dict(complete=complete,primary=primary,all_primary_derivative_controls_valid=valid,predefined_oracle_gain_criterion_met=gain,
        exploratory_outcome='Consistent oracle gain on fitted future.' if gain else ('Inconclusive derivative controls.' if not valid else 'No predefined consistent primary oracle gain.'),
        paired_error_improvement_contrasts=contrasts,units=units,training_seeds_reused=len(units),new_training_seeds=0,
        claim_limits=['Exploratory follow-up after seeing earlier stages.','Two futures are nested within four reused seeds, not eight independent replicates.',
            'H16 basis is a known-future oracle; no online algorithm or global-spectrum claim.','Heldout capture denominator has Monte Carlo uncertainty.',
            'Response fidelity does not imply useful accuracy improvement or publication readiness.','Unresolved or failed derivative controls invalidate a positive mechanism interpretation.'])
if __name__=='__main__':
    import sys,types
    root=Path(sys.argv[1]);c=types.SimpleNamespace(**js(root/'metadata/CONFIG.json'));report=audit_all(root,c)
    print(json.dumps({k:v for k,v in report.items() if k!='units'},indent=2))
