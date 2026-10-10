"""Recompute evidence from immutable stage ZIPs; requires numpy/matplotlib only."""
from pathlib import Path
import csv,hashlib,io,json,math,zipfile,argparse
import numpy as np
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--stage12',type=Path,default=ROOT.parent/'upload/NEXUS_STAGE12_FINISHED.zip');parser.add_argument('--stage13',type=Path,default=ROOT.parent/'upload/NEXUS_STAGE13_FINISHED.zip');parser.add_argument('--out',type=Path,default=ROOT/'package');args=parser.parse_args()
OUT=args.out;OUT.mkdir(parents=True,exist_ok=True)
INPUTS={12:args.stage12,13:args.stage13}

def write_csv(name,rows):
 with open(OUT/name,'w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def center(v):
 v=np.asarray(v,dtype=float);return v-v.mean(1,keepdims=True)
def norm(v):return float(np.linalg.norm(v))
def summarize(v):
 v=np.asarray(v);rng=np.random.default_rng(20261003);boot=v[rng.integers(0,len(v),(10000,len(v)))].mean(1);k=int((v>0).sum())
 return dict(n=len(v),mean=float(v.mean()),sd=float(v.std(ddof=1)),minimum=float(v.min()),maximum=float(v.max()),bootstrap_descriptive_95_low=float(np.quantile(boot,.025)),bootstrap_descriptive_95_high=float(np.quantile(boot,.975)),positive_seeds=k,one_sided_sign_tail=sum(math.comb(len(v),j) for j in range(k,len(v)+1))/2**len(v))
rows=[];caprows=[];fdrows=[];endrows=[];controlrows=[];checks={};sketch=[];baselines=[]
for stage,path in INPUTS.items():
 with zipfile.ZipFile(path) as z:
  def j(n):return json.loads(z.read(n))
  def load(n):
   with np.load(io.BytesIO(z.read(n)),allow_pickle=False) as p:return {k:p[k].copy() for k in p.files}
  manifest=j('MANIFEST.json');names=z.namelist();assert len(names)==len(set(names));assert set(names)=={'MANIFEST.json'}|{e['path'] for e in manifest['files']}
  for e in manifest['files']:
   p=Path(e['path']);assert not p.is_absolute() and '..' not in p.parts and '\\' not in str(p)
   b=z.read(e['path']);assert len(b)==e['bytes'] and hashlib.sha256(b).hexdigest()==e['sha256']
  assert manifest['kind']=='FINISHED';cfg=j('metadata/CONFIG.json');assert manifest['identity']['config']==cfg
  source={n[len('metadata/'):]:hashlib.sha256(z.read(n)).hexdigest() for n in names if n.startswith('metadata/') and (n.endswith('.py') or n.endswith('.json') or (stage==12 and n.endswith('.npz'))) and n!='metadata/CONFIG.json' and n!='metadata/ENVIRONMENT.json' and not(stage==13 and n.endswith('_DATA.json'))}
  # Source identity hashes scientific input JSON and Python, not generated config/env/role data.
  source_identity=hashlib.sha256(json.dumps(source,sort_keys=True,**({'separators':(',',':')} if stage==12 else {})).encode()).hexdigest();assert source_identity==manifest['identity']['source_sha256'],(stage,'source identity differs',source.keys())
  units=sorted(n.rsplit('/',1)[0] for n in names if n.endswith('/COMPLETE.json'))
  branch_count=0;max_saved_disagreement=0.;cut_quality=[]
  for u in units:
   dataset,seed=u.split('/')[1].rsplit('_',1);seed=int(seed);result=j(u+'/RESULT.json');cut=j(u+'/CUT.json') if stage==13 else None
   if stage==13:
    role=j(u+'/ROLES.json');assert not(set(role['response_ids'])&set(role['test_ids']));sets=[set(role[k]) for k in ('fit_ids','heldout_ids','first_ids')];assert all(not(a&b) for i,a in enumerate(sets) for b in sets[i+1:]);cut_quality.append(cut['training_quality']['passes'])
    for n in (64,256):
     f=f'{u}/quality_h16_n{n}.json'
     if f in names:
      q=j(f);assert q['primary_rank_valid'];sketch.append(dict(stage=stage,dataset=dataset,seed=seed,fit_n=n,rank16_energy_change=q['energy_relative_change']['16'],rank16_response_change=q['projected_response_change_over_full']['16'],rank64_energy_change=q['energy_relative_change']['64'],rank64_response_change=q['projected_response_change_over_full']['64']))
   for p in (0,1):
    pp=result['paths'][str(p)];folder=f'{u}/path{p}'
    branchfiles=[n for n in names if n.startswith(folder+'/branch_') and n.endswith('.npz')];branch_count+=len(branchfiles)
    branches={Path(n).stem[len('branch_'):]:load(n) for n in branchfiles};basej=j(folder+'/branch_baseline.json');base=branches['baseline']
    for name,arr in branches.items():
     assert all(np.isfinite(arr[f'h{H}']).all() for H in cfg['horizons'] if H)
     if stage==13:
      digest=np.frombuffer(hashlib.sha256(base['h0'].tobytes()).digest(),dtype=np.uint8);assert np.array_equal(arr['cut_logits_sha256'],digest);assert float(arr['moment_rounding'])<.003
     bj=j(folder+'/branch_'+name+'.json');ep=bj['endpoint'];assert ep['n']==9872
     endrows.append(dict(stage=stage,dataset=dataset,seed=seed,path=p,branch=name,accuracy_change_pp=100*(ep['accuracy']-basej['endpoint']['accuracy']),nll_change=ep['nll']-basej['endpoint']['nll'],endpoint_accuracy=ep['accuracy'],endpoint_nll=ep['nll']))
    if cut:baselines.append(dict(stage=stage,dataset=dataset,seed=seed,path=p,cut_accuracy=cut['initial_test']['accuracy'],endpoint_accuracy=basej['endpoint']['accuracy'],accuracy_change_pp=100*(basej['endpoint']['accuracy']-cut['initial_test']['accuracy']),cut_nll=cut['initial_test']['nll'],endpoint_nll=basej['endpoint']['nll']))
    effects={}
    for name in branches:
     if name.endswith('_plus'):
      d=name[:-5]
      for H in cfg['horizons']:
       if H:effects[d,H]=center((branches[name][f'h{H}'].astype(float)-branches[d+'_minus'][f'h{H}'])/2)
    specifications=[(Hfit,n,r,f'h{Hfit}_n{n}_r{r}') for n in (64,256) for Hfit in (1,16) for r in (16,64)] if stage==13 else [(Hfit,64,r,('immediate' if Hfit==1 else 'horizon')+str(r)) for Hfit in (1,16) for r in (16,64)]
    for Hfit,n,r,d in specifications:
     rem='rem_'+d if stage==13 else ('immediate_rem' if Hfit==1 else 'horizon_rem')+str(r)
     # Stage12 uses remainder names in archived source; choose by presence.
     if stage==12 and rem not in {k[0] for k in effects}:rem=('immediate_remainder' if Hfit==1 else 'horizon_remainder')+str(r)
     for H in cfg['horizons']:
      if not H:continue
      f=effects['full',H];v=effects[d,H];den=norm(f);error=norm(f-v)/den
      # Find stage12 remainder naming robustly after frozen branch inspection.
      candidates=[k[0] for k in effects if k[1]==H and ('immediate' if Hfit==1 else 'horizon') in k[0] and str(r) in k[0] and 'rem' in k[0]]
      rn=rem if (rem,H) in effects else (candidates[0] if candidates else None)
      add=norm(f-v-effects[rn,H])/den if rn else None
      plus_full=center(branches['full_plus'][f'h{H}'].astype(float)-base[f'h{H}']);minus_full=center(branches['full_minus'][f'h{H}'].astype(float)-base[f'h{H}']);plus_proj=center(branches[d+'_plus'][f'h{H}'].astype(float)-base[f'h{H}']);minus_proj=center(branches[d+'_minus'][f'h{H}'].astype(float)-base[f'h{H}']);even=center((branches['full_plus'][f'h{H}'].astype(float)+branches['full_minus'][f'h{H}'])/2-base[f'h{H}']);plus_error=norm(plus_full-plus_proj)/max(norm(plus_full),1e-30);minus_error=norm(minus_full-minus_proj)/max(norm(minus_full),1e-30)
      cosine=float((f*v).sum()/max(norm(f)*norm(v),1e-30));rms=den/math.sqrt(f.size)
      row=dict(stage=stage,dataset=dataset,seed=seed,path=p,fit_horizon=Hfit,fit_n=n,rank=r,horizon=H,error=error,plus_baseline_error=plus_error,minus_baseline_error=minus_error,full_even_over_odd=norm(even)/den,cosine=cosine,full_rms=rms,projection_rms=norm(v)/math.sqrt(v.size),additivity_error=add,resolved=rms>=cfg['resolution_floor'])
      rows.append(row)
      if stage==13:
       saved=pp['comparisons'][f'{d}@{H}']['projection_error'];max_saved_disagreement=max(max_saved_disagreement,abs(error-saved));assert abs(error-saved)<1e-10
     for H in (1,16):
      if stage==13:
       payload=load(f'{u}/capture_fitH{Hfit}_n{n}_path{p}_h{H}.npz');t=payload['trace_squared_norms'];ener=payload['column_squared_norms'][:r].sum();estimate=float(ener/t.mean());saved=pp['capture'][f'{d}@{H}']['capture'];se=float(t.std(ddof=1)/math.sqrt(len(t)));low=ener/(t.mean()+1.96*se);high=ener/max(t.mean()-1.96*se,1e-30)
      else:
       stats=pp['capture'][str(H)][d];estimate=stats['capture_estimate'];saved=estimate;low,high=stats['capture_mc_interval']
      assert abs(estimate-saved)<1e-10
      caprows.append(dict(stage=stage,dataset=dataset,seed=seed,path=p,fit_horizon=Hfit,fit_n=n,rank=r,evaluation_horizon=H,capture=estimate,trace_mc_low=float(low),trace_mc_high=float(high),independent_recomputed=stage==13))
    for H in cfg['horizons']:
     if H:
      for d in ('full','gradient','random'):
       e=effects[d,H];controlrows.append(dict(stage=stage,dataset=dataset,seed=seed,path=p,horizon=H,direction=d,response_rms=norm(e)/math.sqrt(e.size),relative_to_full=norm(e)/norm(effects['full',H])))
    fd=pp.get('finite_difference',pp.get('finite_difference_controls',{}))
    pred=load(folder+'/predictions.npz') if stage==12 else load(u+'/predictions.npz')
    C=base['h1'].shape[1];N=base['h1'].shape[0];Q=np.zeros((C,C-1))
    for k in range(1,C):Q[:k,k-1]=1/math.sqrt(k*(k+1));Q[k,k-1]=-k/math.sqrt(k*(k+1))
    fitems=[(str(H)+'@'+d,v) for H,ds in fd.items() for d,v in ds.items()] if stage==12 else list(fd.items())
    for key,v in fitems:
     if stage==12:H,d=key.split('@',1);H=int(H)
     else:d,H=key.split('@',1);H=int(H)
     raw_error=None
     if d!='amplitude_consistency':
      pk=(f'{d if d!="full_half" else "full"}_h{H}' if stage==12 else f'path{p}_h{H}_{d if d!="full_half" else "full"}')
      pr=pred[pk].reshape(N,C-1)@Q.T*math.sqrt(N*C)*(.5 if d=='full_half' else 1.)
      actual=effects[d,H];raw_error=norm(actual-center(pr))/max(norm(actual),1e-30);assert v['relative_prediction_error'] is None or abs(raw_error-v['relative_prediction_error'])<1e-10
     fdrows.append(dict(stage=stage,dataset=dataset,seed=seed,path=p,test=key,resolved=v.get('resolved'),valid=v.get('valid'),relative_error=v.get('relative_prediction_error',v.get('relative_error')),raw_recomputed=raw_error is not None))
  checks[str(stage)]=dict(archive=str(path.name),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size,payloads=len(manifest['files']),source_identity_verified=True,completed_units=len(units),branches=branch_count,max_raw_vs_saved_error_difference=max_saved_disagreement,training_quality_passes=cut_quality,config=cfg,environment=j('metadata/ENVIRONMENT.json'))
for name,values in [('response_by_seed.csv',rows),('operator_capture_by_seed.csv',caprows),('finite_difference_checks.csv',fdrows),('endpoint_changes.csv',endrows),('control_responses.csv',controlrows),('sketch_quality_checks.csv',sketch),('baseline_training_drift.csv',baselines)]:
 if values:write_csv(name,values)
# Paired differences within histories; no pooling datasets or dependent paths.
deltas=[]
for stage,dataset in sorted(set((r['stage'],r['dataset']) for r in rows)):
 for p in (0,1):
  for n in sorted(set(r['fit_n'] for r in rows if r['stage']==stage)):
   for rnk in (16,64):
    for H in (1,4,16,64):
     subset=[r for r in rows if (r['stage'],r['dataset'],r['path'],r['fit_n'],r['rank'],r['horizon'])==(stage,dataset,p,n,rnk,H)]
     for seed in sorted(set(r['seed'] for r in subset)):
      a=next(r for r in subset if r['seed']==seed and r['fit_horizon']==1);b=next(r for r in subset if r['seed']==seed and r['fit_horizon']==16)
      deltas.append(dict(stage=stage,dataset=dataset,path=p,fit_n=n,rank=rnk,horizon=H,seed=seed,immediate_error=a['error'],matched_error=b['error'],improvement=a['error']-b['error']))
write_csv('paired_horizon_matching.csv',deltas)
summary=[]
for key in sorted(set((r['stage'],r['dataset'],r['path'],r['fit_n'],r['rank'],r['horizon']) for r in deltas)):
 rs=[r for r in deltas if (r['stage'],r['dataset'],r['path'],r['fit_n'],r['rank'],r['horizon'])==key]
 summary.append(dict(zip(('stage','dataset','path','fit_n','rank','horizon'),key))|dict(immediate_mean=float(np.mean([r['immediate_error'] for r in rs])),matched_mean=float(np.mean([r['matched_error'] for r in rs])))|summarize([r['improvement'] for r in rs]))
write_csv('horizon_matching_summary.csv',summary)
(OUT/'AUDIT.json').write_text(json.dumps(checks,indent=2));(OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2))
print('ARCHIVE CHECKS',[(s,v['completed_units'],v['branches']) for s,v in checks.items()])
print('BASELINE DRIFT',[(ds,min(r['accuracy_change_pp'] for r in baselines if r['dataset']==ds),max(r['accuracy_change_pp'] for r in baselines if r['dataset']==ds)) for ds in ('CIFAR10','CIFAR100')])
print('FULL RESPONSE RMS H16',[(ds,min(r['full_rms'] for r in rows if r['stage']==13 and r['dataset']==ds and r['horizon']==16),max(r['full_rms'] for r in rows if r['stage']==13 and r['dataset']==ds and r['horizon']==16)) for ds in ('CIFAR10','CIFAR100')])
