"""Independent NumPy calculations. No training/torch imports."""
import numpy as np

RANKS=(1,2,4,8,16,32,64,128)

def spectrum(G):
    G=np.asarray(G,dtype=np.float64);G=(G+G.T)/2
    w,E=np.linalg.eigh(G);w=w[::-1];E=E[:,::-1]
    if not np.isfinite(G).all() or w[0]<=0:raise ValueError('Invalid/zero operator')
    if w[-1]<-1e-8*max(float(np.trace(G)),w[0]):raise ValueError('Non-PSD Gram')
    w=np.maximum(w,0);valid=w>w[0]*1e-8
    return w,E,valid

def coefficients(G):
    w,E,valid=spectrum(G)
    return E[:,valid]/np.sqrt(w[valid])[None,:],w

def metric_qr(C,G):
    w,E,valid=spectrum(C.T@G@C)
    return C@E[:,valid]/np.sqrt(w[valid])[None,:]

def sketch_coefficients(G,rng,probes=24):
    # The parameter-space columns are A.T @ C. No historical direction enters.
    C=metric_qr(rng.normal(size=(len(G),probes)),G)
    C=metric_qr(G@C,G)  # one J.T J subspace iteration
    w,E,_=spectrum(C.T@G@G@C)
    return C@E,w

def energy_curves(G,H,K,C,sketch):
    w,_,_=spectrum(G);wh,_,_=spectrum(H)
    trace=float(np.trace(H));fit=float(np.trace(G))
    if trace<=0:raise ValueError('Zero held-out operator')
    records=[]
    for k in RANKS:
        n=min(k,C.shape[1]);ns=min(k,sketch.shape[1])
        records.append({'k':k,'actual_fit_rank':n,
          'fit_capture':float(w[:n].sum()/fit),
          'transfer_capture':float(np.square(K@C[:,:n]).sum()/trace),
          'heldout_self_oracle_capture':float(wh[:min(k,len(wh))].sum()/trace),
          'sketch_actual_rank':ns,
          'sketch_transfer_capture':float(np.square(K@sketch[:,:ns]).sum()/trace) if k<=sketch.shape[1] else None})
    p=w[w>0]/w.sum()
    return records,{'stable_rank':float(w.sum()/w[0]),
                    'participation_rank':float(w.sum()**2/np.square(w).sum()),
                    'entropy_rank':float(np.exp(-np.sum(p*np.log(p)))),
                    'full_fit_rowspace_transfer_capture':float(np.square(K@C).sum()/trace),
                    'fit_numerical_rank':int(C.shape[1]),
                    'relative_eigenvalue_resolution_cutoff':1e-8,
                    'rank80_fit':int(np.searchsorted(np.cumsum(w),.8*w.sum())+1),
                    'rank80_heldout_self_oracle':int(np.searchsorted(np.cumsum(wh),.8*wh.sum())+1)}

def response_metrics(base,full,parallel,remainder):
    b=np.asarray(base,dtype=np.float64);f=np.asarray(full,dtype=np.float64)-b
    p=np.asarray(parallel,dtype=np.float64)-b;r=np.asarray(remainder,dtype=np.float64)-b
    # All logits are centered per example before calling this function.
    nf=float(np.linalg.norm(f));np_=float(np.linalg.norm(p))
    return {'full_rmse':float(np.sqrt(np.mean(f*f))),
            'retention':float(np_/nf) if nf>0 else None,
            'cosine':float(np.sum(f*p)/(nf*np_)) if nf>0 and np_>0 else None,
            'remainder_ratio':float(np.linalg.norm(r)/nf) if nf>0 else None,
            'additivity_error':float(np.linalg.norm(f-p-r)/nf) if nf>0 else None}

def center(z):
    z=np.asarray(z,dtype=np.float64);return z-z.mean(axis=-1,keepdims=True)

def causal_curves(arrays,horizons=(0,1,4,16,64),ranks=(16,64)):
    out={}
    for k in ranks:
        out[str(k)]={}
        for sign in ('plus','minus'):
            out[str(k)][sign]={}
            for h in horizons:
                names=['baseline',f'full_{sign}',f'parallel{k}_{sign}',f'remainder{k}_{sign}']
                out[str(k)][sign][str(h)]=response_metrics(*(center(arrays[f'{n}_h{h}']) for n in names))
    return out

def bootstrap(values,rng,draws=5000):
    v=np.asarray(values,dtype=np.float64)
    if not np.isfinite(v).all() or not len(v):raise ValueError('Missing/nonfinite seed estimand')
    means=v[rng.integers(0,len(v),size=(draws,len(v)))].mean(1)
    return {'n_seeds':len(v),'mean':float(v.mean()),'median':float(np.median(v)),
            'ci95_descriptive':np.quantile(means,[.025,.975]).tolist(),'per_seed':v.tolist()}
