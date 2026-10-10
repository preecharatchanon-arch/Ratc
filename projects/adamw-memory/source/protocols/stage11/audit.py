"""Backend-independent saved-data audit. Does not claim to replay neural training."""
import hashlib,json,math
from pathlib import Path
import numpy as np
from control_math import capture,causal_curves,center,bootstrap

def check(ok,msg):
    if not ok:raise RuntimeError('Audit: '+msg)
def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):
    with np.load(path,allow_pickle=False) as z:
        a={k:z[k] for k in z.files}
    check(all(np.isfinite(v).all() for v in a.values()),'Non-finite saved arrays: '+str(path))
    return a
def close(a,b,where):
    if isinstance(a,dict):
        check(set(a)==set(b),where+' keys differ')
        for k in a:close(a[k],b[k],where+'.'+str(k))
    elif isinstance(a,list):
        check(len(a)==len(b),where+' lengths differ')
        for i,(x,y) in enumerate(zip(a,b)):close(x,y,where+str(i))
    elif isinstance(a,(float,int)) and not isinstance(a,bool):check(np.isclose(a,b,rtol=2e-7,atol=2e-10),where+' differs')
    else:check(a==b,where+' differs')
def learning(a):
    check(a['test_prediction'].shape==a['test_labels'].shape==a['test_nll'].shape,'Learning payload shape')
    check(np.all(a['test_nll']>=0),'Negative per-example NLL')
    return {'accuracy':float(np.mean(a['test_prediction']==a['test_labels'])),'loss':float(np.mean(a['test_nll']))}
def labels(cfg):
    out=['baseline','full_plus','full_minus']
    for k in cfg['intervention_ranks']:
        for component in ('parallel','remainder'):out.extend(f'{component}{k}_{s}' for s in ('plus','minus'))
    return out+[f'{n}_{s}' for n in ('gradient','tensor_random') for s in ('plus','minus')]

def audit_case(folder,cfg):
    folder=Path(folder);g=read(folder/'geometry.json');a=load(folder/'geometry_raw.npz');ranks=cfg['intervention_ranks'];k0=cfg['primary_rank']
    check(g['unit']==folder.name and g['basis_uses_history_or_future'] is False,'Geometry identity/design')
    check(g['natural_history_reachability_claimed'] is False,'Unsupported reachability claim')
    captures={}
    for name,rec in g['fitted_candidates'].items():
        captures[name]=capture(a['trace_norms'],a[name+'_trace_coefficients']);close(captures[name],g['capture_curves'][name],'capture '+name)
        c=a[name+'_trace_coefficients'];check(np.all(np.square(c).sum(1)<=a['trace_norms']*(1+2e-4)),'Projection trace exceeds full trace')
        w=np.linalg.eigvalsh((a[name+'_fit_projected_gram']+a[name+'_fit_projected_gram'].T)/2)[::-1]
        check(np.allclose(w,a[name+'_ritz_values'],rtol=2e-7,atol=max(abs(w[0]),1e-30)*1e-10),'Ritz spectrum inconsistent')
        check(rec['actual_rank']==c.shape[1] and rec['orthogonality_max_error']<=5e-5,'Fitted rank/orthogonality record')
    fd={}
    for factor in (.5,1.):
        minus=a[f'fd_factor{factor}_sign-1.0'];plus=a[f'fd_factor{factor}_sign1.0']
        d=(center(plus)-center(minus)).reshape(-1)/(2*factor*g['displacement']*math.sqrt(plus.size))
        fd[str(factor)]={'relative_error':float(np.linalg.norm(d-a['fd_prediction'])/max(np.linalg.norm(a['fd_prediction']),1e-30))}
    close(fd,g['finite_difference'],'finite difference')
    distances={};anchor_distances={};budget_difference={};anchor_difference={};alignment={}
    for k in ranks:
        overlap=a[f'budget_overlap_k{k}'];n=overlap.shape[0]
        distances[str(k)]={'requested_rank':k,'actual_rank':n,'normalized_chordal_distance':float(np.sqrt(max(0,n-np.square(overlap).sum())/max(n,1))),
                           'smallest_principal_cosine':float(np.linalg.svd(overlap,compute_uv=False).min())}
        overlap=a[f'anchor_overlap_k{k}'];n=overlap.shape[0]
        anchor_distances[str(k)]={'requested_rank':k,'actual_rank':n,'normalized_chordal_distance':float(np.sqrt(max(0,n-np.square(overlap).sum())/max(n,1))),
                                 'smallest_principal_cosine':float(np.linalg.svd(overlap,compute_uv=False).min())}
        budget_difference[str(k)]=abs(next(x['paired_hutchinson_capture'] for x in captures['anchor512_q128'] if x['k']==k)-next(x['paired_hutchinson_capture'] for x in captures['anchor512_q64'] if x['k']==k))
        anchor_difference[str(k)]=abs(next(x['paired_hutchinson_capture'] for x in captures['anchor128_q64'] if x['k']==k)-next(x['paired_hutchinson_capture'] for x in captures['anchor512_q64'] if x['k']==k))
        co=a[f'history_coefficients_k{k}'];alignment[str(k)]=float(np.square(co).sum())
        check(np.isclose(alignment[str(k)],g['history_alignment'][str(k)]['history_alignment'],rtol=1e-6,atol=1e-9),'History projection energy differs')
        f=a['linear_full'];err=np.linalg.norm(f-a[f'linear_parallel{k}']-a[f'linear_remainder{k}'])/max(np.linalg.norm(f),1e-30)
        check(err<5e-4,'Linear operator additivity failed')
    close(distances,g['budget_distances'],'subspace distance');close(budget_difference,g['capture_budget_difference'],'budget capture')
    close(anchor_distances,g['anchor_distances'],'anchor subspace distance')
    controls={}
    for name in g['matched_controls']:
        z=a['control_'+name];controls[name]={'normalized_logit_gain':float(np.linalg.norm(z)),
          'history_gain_ratio':float(np.linalg.norm(a['linear_full'])/max(np.linalg.norm(z),1e-30))}
    close(controls,g['matched_controls'],'control gains')
    check(not set(g['fit_large_ids'])&set(g['independent_ids']),'Independent anchor overlaps fit')
    check(set(g['fit_small_ids']).issubset(g['fit_large_ids']),'Small anchor not nested')
    check(not set(g['first_ids'])&(set(g['fit_large_ids'])|set(g['independent_ids'])),'First batch role overlap')
    curves={};quality={};rounding={};raw_hashes={};paths={};future_controls={}
    for path in cfg['future_paths']:
        arrays={};quality[str(path)]={}
        for label in labels(cfg):
            tag=f'path{path}_{label}';rec=read(folder/(tag+'.json'));raw=folder/(tag+'.npz')
            check(rec['label']==label and rec['path']==path and rec['unit']==folder.name,'Future identity mismatch')
            check(rec['recipient_digest']==g['snapshot_digest'],'Branches have different recipient states')
            check(rec['weights_variance_clock_unchanged'] is True and rec['reference_clock']==g['clock'],'Surgery invariants')
            check(rec['future_steps']==cfg['future_steps'] and rec['horizons']==list(cfg['horizons']),'Future horizon mismatch')
            check(sha(raw)==rec['raw_sha256'],'Future raw data digest mismatch');b=load(raw);raw_hashes[tag]=rec['raw_sha256']
            for h in cfg['horizons']:arrays[f'{label}_h{h}']=b[f'h{h}']
            check(np.array_equal(b['h0'],arrays['baseline_h0']),'Initial logits changed by moment-only surgery')
            if label=='baseline':check(rec['actual_delta_norm']==0,'Baseline moment displacement')
            quality[str(path)][label]=learning(b);close(quality[str(path)][label],rec['learning'],'future learning')
            rounding[tag]=rec['rounding_relative_error']
        curves[str(path)]=causal_curves(arrays,cfg['horizons'],ranks,cfg['future_effect_floor']);paths[path]=arrays
        future_controls[str(path)]={}
        for sign in ('plus','minus','paired'):
            future_controls[str(path)][sign]={}
            for h in cfg['horizons']:
                def delta(name):
                    if sign=='paired':return (center(arrays[f'{name}_plus_h{h}'])-center(arrays[f'{name}_minus_h{h}']))/2
                    return center(arrays[f'{name}_{sign}_h{h}'])-center(arrays[f'baseline_h{h}'])
                full=delta('full');gain=float(np.sqrt(np.mean(full*full)));control_rows={}
                for name in ('gradient','tensor_random'):
                    z=delta(name);rms=float(np.sqrt(np.mean(z*z)))
                    control_rows[name]={'centered_logit_rmse':rms,'gain_relative_to_history':rms/gain if gain>=cfg['future_effect_floor'] else None}
                future_controls[str(path)][sign][str(h)]=control_rows
    if len(paths)>1:
        for label in labels(cfg):check(all(np.array_equal(paths[p][f'{label}_h1'],paths[cfg['future_paths'][0]][f'{label}_h1']) for p in paths),'Identical first update differs across future streams')
    reference=learning(load(folder/'reference_learning.npz'))
    instrument={'adjoint_ok':g['adjoint_error']<2e-5,'finite_difference_ok':all(x['relative_error']<=cfg['fd_error_max'] for x in fd.values()),
       'capture_budget_stable_primary':budget_difference[str(k0)]<=cfg['capture_budget_difference_max'],
       'subspace_budget_stable_primary':distances[str(k0)]['normalized_chordal_distance']<=cfg['angle_budget_difference_max'],
       'capture_anchor_stable_primary':anchor_difference[str(k0)]<=cfg['capture_budget_difference_max'],
       'subspace_anchor_stable_primary':anchor_distances[str(k0)]['normalized_chordal_distance']<=cfg['angle_budget_difference_max'],
       'max_surgery_rounding_relative_error':max(rounding.values()),'stable_basis_is_not_assumed':True}
    result={'unit':folder.name,'captures':captures,'history_alignment':alignment,'controls':controls,'causal_curves':curves,
            'reference_learning':reference,'future_learning':quality,'future_controls':future_controls,'instrument':instrument,
            'geometry_raw_sha256':sha(folder/'geometry_raw.npz'),'future_raw_sha256':raw_hashes,
            'audit_scope':'Recomputed saved trace/response/learning statistics and recorded surgery provenance; neural actions and training are not replayed from these summaries.'}
    if (folder/'result.json').exists():
        old=read(folder/'result.json')
        close(result,{k:old[k] for k in result},'saved result')
    return result

def summarize(root,cfg):
    root=Path(root);identity=read(root/'metadata'/'IDENTITY.json')
    for n,h in identity['source'].items():check(sha(root/'metadata'/n)==h,'Frozen source differs: '+n)
    cases=[]
    for d in cfg['datasets']:
        meta=read(root/'metadata'/(d+'_DATA.json'))
        check(not set(meta['train_ids'])&set(meta['calibration_ids']),'Training/calibration overlap')
        check(not set(meta['response_test_ids'])&set(meta['evaluation_test_ids']),'Response/evaluation test overlap')
        for arch in cfg['architectures']:
            for i in range(cfg['models_per_cell']):
                s=11000+1000*(d=='CIFAR100')+100*(arch=='ViTSmall')+i
                total=cfg['total_steps_cifar10'] if d=='CIFAR10' else cfg['total_steps_cifar100'];initials=[]
                for fraction in cfg['cut_fractions']:
                    t=int(total*fraction);folder=root/'units'/f'{d}_{arch}_{s}_t{t}';check((folder/'result.json').exists(),'Missing planned case: '+folder.name)
                    r=audit_case(folder,cfg);rec=read(folder/'result.json');key=rec['identity'];check(key=={'dataset':d,'architecture':arch,'model_seed':s,'cut':t,'late':t==total},'Case identity differs')
                    g=read(folder/'geometry.json');check(g['clock']==t,'Cut clock differs')
                    for role in ('fit_large_ids','independent_ids','first_ids'):check(set(g[role]).issubset(meta['calibration_ids']),'Operator role outside withheld calibration')
                    initials.append(g['initial_model_digest']);cases.append((key,r))
                check(len(set(initials))==1,'Repeated checkpoints are not the same reference model')
    panels={};rng=np.random.default_rng(7112026);h0=str(cfg['primary_horizon']);k0=str(cfg['primary_rank'])
    for d in cfg['datasets']:
        for arch in cfg['architectures']:
            for late in (False,True):
                rows=[r for key,r in cases if key['dataset']==d and key['architecture']==arch and key['late']==late]
                if not rows:continue
                key=f'{d}/{arch}/{"late" if late else "early"}';captures={};causal={}
                for k in cfg['intervention_ranks']:
                    captures[str(k)]=bootstrap([next(v['paired_hutchinson_capture'] for v in r['captures']['anchor512_q128'] if v['k']==k) for r in rows],rng,cfg['bootstrap_draws'])
                    causal[str(k)]={}
                    for sign in ('plus','minus','paired'):
                        causal[str(k)][sign]={}
                        for h in cfg['horizons']:
                            values={}
                            for metric in ('full_rmse','retention','cosine','remainder_ratio','additivity_error','projection_prediction_error_ratio_vs_zero'):
                                per_seed=[]
                                for r in rows:
                                    path_values=[r['causal_curves'][str(p)][str(k)][sign][str(h)][metric] for p in cfg['future_paths']]
                                    per_seed.append(None if any(v is None for v in path_values) else float(np.mean(path_values)))
                                values[metric]=bootstrap(per_seed,rng,cfg['bootstrap_draws'])
                            causal[str(k)][sign][str(h)]=values
                floor=.6 if d=='CIFAR10' else .3
                control_report={}
                for name in ('gradient','tensor_random'):
                    vals=[]
                    for r in rows:
                        v=[r['future_controls'][str(p)]['paired'][h0][name]['gain_relative_to_history'] for p in cfg['future_paths']]
                        vals.append(None if any(x is None for x in v) else float(np.mean(v)))
                    control_report[name]=bootstrap(vals,rng,cfg['bootstrap_draws'])
                panels[key]={'independent_models':len(rows),'capture':captures,'causal':causal,
                   'estimator_capture_per_seed':[{name:r['captures'][name] for name in r['captures']} for r in rows],
                   'primary_future_control_gain_relative_to_history':control_report,
                   'reference_learning_per_seed':[r['reference_learning'] for r in rows],
                   'learning_quality_floor':floor,'reference_below_quality_floor':[r['reference_learning']['accuracy']<floor for r in rows],
                   'instrument_per_seed':[r['instrument'] for r in rows],
                   'primary':{'rank':int(k0),'horizon':int(h0),'paired':causal[k0]['paired'][h0]}}
    return {'version':identity['version'],'completed_cases':len(cases),'planned_cases':len(cfg['datasets'])*len(cfg['architectures'])*cfg['models_per_cell']*len(cfg['cut_fractions']),
            'independent_models':len(cfg['datasets'])*len(cfg['architectures'])*cfg['models_per_cell'],
            'panels':panels,'inference':'Four independent training seeds per cell in the default protocol. Checkpoints, signs, branches and future streams are nested observations; intervals are descriptive, not powered confirmation.',
            'parent_confirmation_unchanged':True,'positive_or_publication_claim_automatic':False}
