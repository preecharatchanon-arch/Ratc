"""Independent saved-data estimands; no neural backend imports."""
import numpy as np

RANKS=(1,2,4,8,16,32,64)

def center(z):
    z=np.asarray(z,dtype=np.float64);return z-z.mean(-1,keepdims=True)

def effects(base,full,parallel,remainder,floor=2e-5):
    b=center(base);f=center(full)-b;p=center(parallel)-b;r=center(remainder)-b
    nf=float(np.linalg.norm(f));pn=float(np.linalg.norm(p));rms=float(np.sqrt(np.mean(f*f)))
    # Keep raw effects below the resolution floor; do not manufacture resolved ratios.
    resolved=rms>=floor
    return {'full_rmse':rms,'resolved':resolved,
       'retention':float(pn/nf) if resolved else None,
       'cosine':float(np.sum(f*p)/(nf*pn)) if resolved and pn>0 else None,
       'remainder_ratio':float(np.linalg.norm(r)/nf) if resolved else None,
       'additivity_error':float(np.linalg.norm(f-p-r)/nf) if resolved else None,
       'projection_prediction_error_ratio_vs_zero':float(np.linalg.norm(f-p)/nf) if resolved else None}

def capture(raw_norms,raw_coefficients,ranks=RANKS):
    n=np.asarray(raw_norms,dtype=np.float64);c=np.asarray(raw_coefficients,dtype=np.float64)
    if not np.isfinite(n).all() or not np.isfinite(c).all() or n.mean()<=0:raise ValueError('Invalid independent trace probes')
    out=[]
    for k in ranks:
        actual=min(k,c.shape[1]);projected=np.square(c[:,:actual]).sum(1)
        out.append({'k':k,'actual_rank':actual,'paired_hutchinson_capture':float(projected.mean()/n.mean()),
                    'trace_estimate':float(n.mean()),'captured_trace_estimate':float(projected.mean()),
                    'trace_mc_standard_error':float(n.std(ddof=1)/np.sqrt(len(n)))})
    return out

def causal_curves(arrays,horizons,ranks,floor=2e-5):
    out={}
    for k in ranks:
        out[str(k)]={}
        for sign in ('plus','minus'):
            out[str(k)][sign]={str(h):effects(arrays[f'baseline_h{h}'],arrays[f'full_{sign}_h{h}'],
                arrays[f'parallel{k}_{sign}_h{h}'],arrays[f'remainder{k}_{sign}_h{h}'],floor) for h in horizons}
        out[str(k)]['paired']={}
        for h in horizons:
            def delta(name):return (center(arrays[f'{name}_plus_h{h}'])-center(arrays[f'{name}_minus_h{h}']))/2
            f,p,r=delta('full'),delta(f'parallel{k}'),delta(f'remainder{k}')
            out[str(k)]['paired'][str(h)]=effects(np.zeros_like(f),f,p,r,floor)
    return out

def bootstrap(values,rng,draws=10000):
    if any(v is None or not np.isfinite(v) for v in values):
        return {'n_planned_seeds':len(values),'unresolved_seed_count':sum(v is None or not np.isfinite(v) for v in values),'per_seed':values,'claim_supported':False}
    x=np.asarray(values,dtype=np.float64);means=x[rng.integers(0,len(x),size=(draws,len(x)))].mean(1)
    return {'n_seeds':len(x),'mean':float(x.mean()),'median':float(np.median(x)),
       'ci95_descriptive':np.quantile(means,[.025,.975]).tolist(),'per_seed':x.tolist()}
