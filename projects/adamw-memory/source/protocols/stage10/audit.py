"""Independent saved-data auditor: NumPy only, no runner or PyTorch import."""
import hashlib,json
from pathlib import Path
import numpy as np
from control_math import spectrum,energy_curves,causal_curves,center,response_metrics

def ensure(ok,message):
    if not ok:raise ValueError(message)

def compare(actual,expected,path='record',tol=2e-5):
    if isinstance(expected,dict):
        for k,v in expected.items():compare(actual[k],v,path+'.'+k,tol)
    elif isinstance(expected,list):
        ensure(len(actual)==len(expected),path+' length differs')
        for i,(a,e) in enumerate(zip(actual,expected)):compare(a,e,path+f'[{i}]',tol)
    elif expected is None:ensure(actual is None,path+' unresolved differs')
    elif isinstance(expected,(float,int,np.number)) and not isinstance(expected,bool):
        ensure(np.isfinite(float(actual)) and abs(float(actual)-float(expected))<=tol*max(1,abs(float(expected))),path+' value differs')
    else:ensure(actual==expected,path+' differs')

def file_sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def test_metrics(z,y):
    z=np.asarray(z,dtype=np.float64);y=np.asarray(y,dtype=int);q=z-z.max(1,keepdims=True)
    return {'accuracy':float((z.argmax(1)==y).mean()),'loss':float(np.mean(np.log(np.exp(q).sum(1))-q[np.arange(len(y)),y]))}

def audit_unit(folder,horizons=(0,1,4,16,64),ranks=(16,64)):
    folder=Path(folder);result=json.loads((folder/'result.json').read_text());op=result['operator']
    ensure(result['unit']==folder.name,'Unit identity mismatch')
    with np.load(folder/'operator_raw.npz',allow_pickle=False) as data:raw={k:data[k] for k in data.files}
    G,H,K,C,Cs=[raw[k] for k in ('G','H','K','C','Cs')]
    ensure(np.isfinite(G).all() and np.isfinite(H).all() and np.isfinite(K).all(),'Nonfinite Gram')
    w,_,valid=spectrum(G)
    ensure(np.allclose(C.T@G@C,np.eye(C.shape[1]),atol=1e-5),'Exact basis not orthonormal in parameter metric')
    ensure(np.linalg.norm(G@C-C*w[valid][None,:])/max(np.linalg.norm(G@C),1e-30)<1e-5,'Not an eigenbasis')
    ensure(np.allclose(Cs.T@G@Cs,np.eye(Cs.shape[1]),atol=1e-5),'Sketch metric orthogonality failed')
    curve,spec=energy_curves(G,H,K,C,Cs);compare(op['rank_curve'],curve);compare(op['spectral_diagnostics'],spec)
    for r in curve:
        ensure(-1e-7<=r['transfer_capture']<=1+1e-5,'Impossible transferred energy fraction')
        if r['sketch_transfer_capture'] is not None:ensure(-1e-7<=r['sketch_transfer_capture']<=1+1e-5,'Impossible sketch fraction')
    h=raw['history'];ensure(abs(np.linalg.norm(h)-1)<1e-6,'Historical direction not unit norm')
    ensure(not set(op['fit_anchor_ids'])&set(op['heldout_anchor_ids']),'Anchor overlap')
    ensure(not set(op['first_batch_ids'])&(set(op['fit_anchor_ids'])|set(op['heldout_anchor_ids'])),'Probe/anchor overlap')
    for k in ranks:
        ensure(np.linalg.norm(raw['linear_full']-raw[f'linear_parallel{k}']-raw[f'linear_remainder{k}'])/max(np.linalg.norm(raw['linear_full']),1e-30)<1e-5,'Linear projection decomposition fails')
    for name,rec in op['controls'].items():
        z=raw[f'control_{name}'];power=float(np.linalg.norm(z));hp=float(np.linalg.norm(raw['linear_full']))
        compare(rec,{'heldout_potency':power,'history_potency_ratio':hp/max(power,1e-30)})
    for factor in (.5,1.):
        scale=op['displacement']*factor
        actual=(center(raw[f'factor{factor}_sign1.0'])-center(raw[f'factor{factor}_sign-1.0']))/(2*scale)
        pred=raw['predicted_history_derivative']
        error=float(np.linalg.norm(actual-pred)/max(np.linalg.norm(pred),1e-30))
        compare(op['one_step_fd'][str(factor)],{'relative_central_derivative_error':error})
    with np.load(folder/'cut_state.npz',allow_pickle=False) as z:
        ensure(np.isfinite(z['theta']).all() and np.isfinite(z['m']).all() and (z['v']>=0).all(),'Bad true checkpoint state')
        ensure(not set(z['response_ids'])&set(z['test_ids']),'Response/evaluation overlap')
        labels=z['test_labels'].copy();m=z['m'].astype('float64')
        direction=m-z['donor_m'].astype('float64')
        ensure(np.linalg.norm(h-direction/max(np.linalg.norm(direction),1e-30))<2e-6,'History does not match saved donor/cut')
    with np.load(folder/'initial.npz',allow_pickle=False) as z:compare(result['initial_test'],test_metrics(z['test_logits'],labels))
    arrays={};deltas={};names=['baseline']+[f'{name}_{sign}' for name in ['full']+[f'{part}{k}' for k in ranks for part in ('parallel','remainder')] for sign in ('plus','minus')]
    for name in names:
        p=folder/f'future_{name}.npz';rec=json.loads((folder/f'future_{name}.json').read_text())
        ensure(rec['label']==name and rec['payload_sha256']==file_sha(p),'Branch payload digest/label mismatch')
        with np.load(p,allow_pickle=False) as z:
            deltas[name]=z['actual_delta_m'].copy()
            compare(rec['surgery_relative_m_displacement'],float(np.linalg.norm(deltas[name])/max(np.linalg.norm(m),1e-30)))
            ensure(rec['initial_weights_second_moments_clock_unchanged'],'State surgery invariants failed')
            for horizon in horizons:arrays[f'{name}_h{horizon}']=z[f'h{horizon}'].copy()
            compare(rec['final_test'],test_metrics(z['test_logits'],labels))
    ensure(np.array_equal(deltas['baseline'],np.zeros_like(m)),'Baseline first moments changed')
    for sign in ('plus','minus'):
        delta=deltas[f'full_{sign}'];expected=(1 if sign=='plus' else -1)*op['displacement']*h
        ensure(np.linalg.norm(delta-expected)/max(np.linalg.norm(expected),1e-30)<1e-3,'Full intervention displacement wrong')
        for k in ranks:
            gap=delta-deltas[f'parallel{k}_{sign}']-deltas[f'remainder{k}_{sign}']
            ensure(np.linalg.norm(gap)/max(np.linalg.norm(delta),1e-30)<1e-3,'Rounded moment interventions do not decompose')
    for name in names:ensure(np.array_equal(arrays[f'{name}_h0'],arrays['baseline_h0']),'Nonzero present-function change')
    curves=causal_curves(arrays,horizons,ranks)
    for k in curves:
        curves[k]['paired']={}
        for h in horizons:
            def delta(name):return (center(arrays[f'{name}_plus_h{h}'])-center(arrays[f'{name}_minus_h{h}']))/2
            f=delta('full');p=delta(f'parallel{k}');r=delta(f'remainder{k}')
            curves[k]['paired'][str(h)]=response_metrics(np.zeros_like(f),f,p,r)
    compare(result['causal_curves'],curves)
    return {'passed':True,'unit':folder.name,'recomputed_gram_spectrum_and_capture':True,
      'recomputed_raw_finite_future_and_accuracy':True,
      'scope':'independent saved-data arithmetic; does not independently regenerate neural Jacobians or natural training histories'}
