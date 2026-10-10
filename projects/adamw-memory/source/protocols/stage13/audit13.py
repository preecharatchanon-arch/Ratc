"""Independent NumPy arithmetic audit; no replay of deleted model states."""
import hashlib,json,math
from pathlib import Path
from dataclasses import asdict
import numpy as np

def read(p):return json.loads(Path(p).read_text())
def npz(p):
    with np.load(p,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
def require(x,msg):
    if not x:raise RuntimeError(msg)
def centered(x):
    x=np.asarray(x,dtype=np.float64);return x-x.mean(axis=-1,keepdims=True)
def metrics(actual,pred,floor=2e-5):
    a=centered(actual);p=centered(pred);n=float(np.linalg.norm(a));rms=float(np.sqrt(np.mean(a*a)))
    return dict(response_rms=rms,resolved=rms>=floor,relative_prediction_error=float(np.linalg.norm(a-p)/max(n,1e-30)),prediction_rms=float(np.sqrt(np.mean(p*p))))
def comparison(full,projection,remainder,floor):
    a=centered(full);b=centered(projection);r=centered(remainder);n=float(np.linalg.norm(a));rms=float(np.sqrt(np.mean(a*a)))
    return dict(full_rms=rms,resolved=rms>=floor,projection_error=float(np.linalg.norm(a-b)/max(n,1e-30)),remainder_fraction=float(np.linalg.norm(r)/max(n,1e-30)),additivity_error=float(np.linalg.norm(a-b-r)/max(n,1e-30)))
def decode(v,n,C):
    Q=np.zeros((C,C-1))
    for k in range(1,C):Q[:k,k-1]=1/math.sqrt(k*(k+1));Q[k,k-1]=-k/math.sqrt(k*(k+1))
    return np.asarray(v).reshape(n,C-1)@Q.T*math.sqrt(n*C)
def names(c):
    projections=[f'h{H}_n{n}_r{r}' for n in c.fit_sizes for H in (1,c.fit_horizon) for r in c.ranks]
    return ['full','gradient','random']+projections+['rem_'+x for x in projections]
def capture(p,r):
    z=npz(p);t=z['trace_squared_norms'];e=z['column_squared_norms'];require(np.isfinite(t).all() and (t>0).all() and np.isfinite(e).all(),'Invalid held-out energies')
    mean=float(t.mean());se=float(t.std(ddof=1)/math.sqrt(len(t))) if len(t)>1 else 0.;numerator=float(e[:r].sum())
    return dict(capture=numerator/mean,trace_mean=mean,trace_standard_error=se,trace_probes=len(t),numerator=numerator,
        approximate_trace_95_interval=[max(0.,mean-1.96*se),mean+1.96*se],capture_approximate_95_interval=[numerator/(mean+1.96*se),numerator/max(mean-1.96*se,1e-30)])
def audit_unit(unit,c):
    unit=Path(unit);cut=read(unit/'CUT.json');role=read(unit/'ROLES.json');C=cut['classes'];n=len(role['response_ids']);pred=npz(unit/'predictions.npz');directions=names(c)
    roles=[set(role[k]) for k in ('fit_ids','heldout_ids','first_ids')]
    require(all(not(a&b) for i,a in enumerate(roles) for b in roles[i+1:]),'Calibration roles overlap')
    require(not(set(role['response_ids'])&set(role['test_ids'])),'Response and endpoint tests overlap')
    out=dict(dataset=unit.name.rsplit('_',1)[0],seed=int(unit.name.rsplit('_',1)[1]),training=cut['initial_test'],training_quality=cut.get('training_quality'),paths={},qualification=read(unit/'QUALIFICATION.json'),replay_limitation='Final archive audits saved responses and metadata; completed full states and direction vectors are deliberately deleted. Full surgery replay requires deterministic retraining.')
    for path in (0,1):
        folder=unit/f'path{path}';base=npz(folder/'branch_baseline.npz');basej=read(folder/'branch_baseline.json');effects={};endpoints={};fd={};tests={};captures={}
        require(base['h0'].shape==(n,C),'Baseline response shape')
        digest=np.frombuffer(hashlib.sha256(base['h0'].tobytes()).digest(),dtype=np.uint8)
        allnames=['baseline']+[f'{d}_{sign}' for d in directions for sign in ('plus','minus')]+['full_half_plus','full_half_minus']
        for name in allnames:
            z=npz(folder/f'branch_{name}.npz');j=read(folder/f'branch_{name}.json')
            require(np.array_equal(z['cut_logits_sha256'],digest),'Current logits changed at surgery')
            require(float(z['moment_rounding'])<.003,'Moment displacement rounded too much')
            require(all(z[f'h{H}'].shape==(n,C) and np.isfinite(z[f'h{H}']).all() for H in c.horizons if H),'Nonfinite or missing branch outputs')
            require(z['requested_delta_sha256'].shape==(32,) and z['actual_delta_sha256'].shape==(32,),'Missing intervention hashes')
            ep=j['endpoint'];require(np.isfinite(ep['nll']) and 0<=ep['accuracy']<=1 and ep['n']==len(role['test_ids']),'Endpoint statistics invalid')
            endpoints[name]=dict(accuracy_change=ep['accuracy']-basej['endpoint']['accuracy'],nll_change=ep['nll']-basej['endpoint']['nll'])
        for d in directions+['full_half']:
            plus=npz(folder/f'branch_{d}_plus.npz');minus=npz(folder/f'branch_{d}_minus.npz')
            for H in c.horizons:
                if not H:continue
                effects[d,H]=(plus[f'h{H}'].astype(float)-minus[f'h{H}'].astype(float))/2
                if H in (1,c.fit_horizon):
                    p=decode(pred[f'path{path}_h{H}_{"full" if d=="full_half" else d}'],n,C)*(.5 if d=='full_half' else 1.)
                    v=metrics(effects[d,H],p,c.resolution_floor);v['valid']=v['resolved'] and v['relative_prediction_error']<=c.derivative_error_max;fd[f'{d}@{H}']=v
        for bank in c.fit_sizes:
            for Hfit in (1,c.fit_horizon):
                for r in c.ranks:
                    d=f'h{Hfit}_n{bank}_r{r}'
                    for H in c.horizons:
                        if H:tests[f'{d}@{H}']=comparison(effects['full',H],effects[d,H],effects['rem_'+d,H],c.resolution_floor)
                    for H in (1,c.fit_horizon):captures[f'{d}@{H}']=capture(unit/f'capture_fitH{Hfit}_n{bank}_path{path}_h{H}.npz',r)
        primary_fd=[fd[f'{d}@{c.fit_horizon}'] for d in ('full','full_half',f'h1_n{max(c.fit_sizes)}_r{min(c.ranks)}',f'h{c.fit_horizon}_n{max(c.fit_sizes)}_r{min(c.ranks)}')]
        out['paths'][str(path)]=dict(finite_difference=fd,comparisons=tests,capture=captures,endpoints=endpoints,primary_derivatives_valid=all(v['valid'] for v in primary_fd),branches=len(allnames))
    return out

def summarize(values):
    v=np.asarray(values,float);rng=np.random.default_rng(13013);boot=v[rng.integers(0,len(v),(5000,len(v)))].mean(1)
    k=int((v>0).sum());tail=sum(math.comb(len(v),j) for j in range(k,len(v)+1))/2**len(v)
    return dict(n=len(v),values=v.tolist(),mean=float(v.mean()),standard_deviation=float(v.std(ddof=1)) if len(v)>1 else None,
        descriptive_bootstrap_95_interval=np.quantile(boot,[.025,.975]).tolist(),positive_seeds=k,one_sided_sign_tail=tail)
def audit_all(root,c):
    root=Path(root);report=dict(complete=True,datasets={},config=asdict(c),interpretation='Horizon-dependent moment-response geometry. Approximate oracle subspaces; no deployable compression or accuracy-gain claim. Four independent seeds per dataset; paths, banks, ranks and branches are dependent comparisons. Bootstrap intervals are descriptive.')
    for dataset in c.datasets:
        rows=[]
        for s in c.seeds:
            unit=root/'units'/f'{dataset}_{s}';require((unit/'COMPLETE.json').exists(),'Missing completed unit');rows.append(audit_unit(unit,c))
        result=dict(primary_derivatives_valid=all(x['paths']['0']['primary_derivatives_valid'] for x in rows),training_quality_flags=[x['training_quality'] for x in rows],paths={})
        for path in (0,1):
            stats={};r=min(c.ranks);H=c.fit_horizon
            for n in c.fit_sizes:
                stats[f'horizon_matching_n{n}']=summarize([x['paths'][str(path)]['comparisons'][f'h1_n{n}_r{r}@{H}']['projection_error']-x['paths'][str(path)]['comparisons'][f'h{H}_n{n}_r{r}@{H}']['projection_error'] for x in rows])
            lo,hi=min(c.fit_sizes),max(c.fit_sizes)
            stats['bank_growth_matched']=summarize([x['paths'][str(path)]['comparisons'][f'h{H}_n{lo}_r{r}@{H}']['projection_error']-x['paths'][str(path)]['comparisons'][f'h{H}_n{hi}_r{r}@{H}']['projection_error'] for x in rows])
            stats['long_horizon_better_than_zero']=summarize([1-x['paths'][str(path)]['comparisons'][f'h{H}_n{hi}_r{r}@{c.future_steps}']['projection_error'] for x in rows])
            result['paths'][str(path)]=stats
        report['datasets'][dataset]=result
    report['primary_dataset']=c.datasets[0];report['replication_dataset']=c.datasets[1] if len(c.datasets)>1 else None
    report['scientific_primary_valid']=all(v['primary_derivatives_valid'] and all(q and q['passes'] for q in v['training_quality_flags']) for v in report['datasets'].values())
    return report
