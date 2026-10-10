from pathlib import Path
import json,numpy as np
package=Path(__file__).resolve().parents[1];root=package/'evidence/stage14/raw';out={};captures={};stats=[];quality=[];endpoint=[];deriv=[]
for unit in sorted(root.glob('CIFAR10_*')):
 seed=int(unit.name.split('_')[1]);result=json.loads((unit/'RESULT.json').read_text());q=json.loads((unit/'QUALIFICATION.json').read_text());assert q['primary_valid']
 for path in (0,1):
  base=unit/f'path{path}'
  def logits(name,h):return np.load(base/f'branch_{name}.npz')[f'h{h}'].astype(float)
  def center(x):return x-x.mean(axis=1,keepdims=True)
  def effect(name,h):return center((logits(name+'_plus',h)-logits(name+'_minus',h))/2)
  for h in (16,64):
   f=effect('full',h);norm=np.linalg.norm(f);rms=float(norm/np.sqrt(f.size));assert rms>2e-5
   b=logits('baseline',h)
   even=center((logits('full_plus',h)+logits('full_minus',h))/2-b)
   for rank in (16,64):
    key=f'h16_n256_r{rank}';p=effect(key,h);rem=effect('rem_'+key,h)
    err=float(np.linalg.norm(f-p)/norm);signed=[]
    for sign in ('plus','minus'):
     fs=center(logits('full_'+sign,h)-b);ps=center(logits(key+'_'+sign,h)-b);signed.append(float(np.linalg.norm(fs-ps)/np.linalg.norm(fs)))
    stats.append(dict(seed=seed,path=path,horizon=h,rank=rank,error=err,full_rms=rms,plus_error=signed[0],minus_error=signed[1],even_over_odd=float(np.linalg.norm(even)/norm),additivity=float(np.linalg.norm(f-p-rem)/norm)))
  for a in q['paths'][str(path)]['finite_difference'].values():deriv.append(a['relative_prediction_error'])
  bj=json.loads((base/'branch_baseline.json').read_text())['endpoint']
  for p in base.glob('branch_*.json'):
   j=json.loads(p.read_text())['endpoint'];endpoint.append(dict(accuracy_change_pp=100*(j['accuracy']-bj['accuracy']),nll_change=j['nll']-bj['nll']))
  for fit in (1,16):
   z=np.load(unit/f'capture_fitH{fit}_n256_path{path}_h16.npz');den=float(np.mean(z['trace_squared_norms']))
   for rank in (16,64):
    val=float(np.sum(z['column_squared_norms'][:rank])/den);captures.setdefault(f'path{path}_fit{fit}_r{rank}',[]).append(val)
 for p in unit.glob('quality_h16_n256.json'):quality.append(json.loads(p.read_text()))
for path in (0,1):
 for rank in (16,64):
  for h in (16,64):
   x=[s for s in stats if (s['path'],s['rank'],s['horizon'])==(path,rank,h)]
   out[f'path{path}_rank{rank}_H{h}']={'mean_error':float(np.mean([a['error'] for a in x])),'error_range':[min(a['error'] for a in x),max(a['error'] for a in x)],'above_zero_predictor':sum(a['error']>1 for a in x),'signed_error_max_difference_from_central':max(abs(a[k]-a['error']) for a in x for k in ('plus_error','minus_error'))}
out.update(capture_means={k:float(np.mean(v)) for k,v in captures.items()},max_derivative_error=max(deriv),min_full_response_rms=min(x['full_rms'] for x in stats),max_even_over_odd=max(x['even_over_odd'] for x in stats),max_additivity=max(x['additivity'] for x in stats),max_endpoint_accuracy_change_pp=max(abs(x['accuracy_change_pp']) for x in endpoint),max_endpoint_nll_change=max(abs(x['nll_change']) for x in endpoint),quality_histories=len(quality))
(package/'evidence/stage14/EXTENDED_AUDIT.json').write_text(json.dumps({'summary':out,'per_history':stats},indent=2));print(json.dumps(out,indent=2))
