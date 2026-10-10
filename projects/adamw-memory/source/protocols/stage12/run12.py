"""Stage12 known-future oracle comparison. Does not change earlier frozen evidence."""
import gc,hashlib,json,math,shutil,time
from pathlib import Path
from dataclasses import dataclass,asdict
import numpy as np
import torch
import parent10 as p
from horizon import *
from archive_io import Campaign,write_json,sha,check
ROOT=Path(__file__).resolve().parent
VERSION='NEXUS-STAGE12-HORIZON-ORACLE-R2'
@dataclass(frozen=True)
class Config(p.Config):
    fit_horizon:int=16
    trace_probes:int=128
    resolution_floor:float=2e-5
    derivative_error_max:float=.15
    future_paths:tuple=(0,1)
class PauseRun(RuntimeError):pass
def array(x):return x.detach().cpu().numpy()
def save(path,**d):p.npz(path,d)
def load(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
def norm(v):check(float(v.norm())>0,'Zero control direction');return v/v.norm()
def branch_names(d):return [('baseline',None,0.,0)]+[(f'{k}_{sign}',k,1.,v) for k in d for sign,v in [('plus',1),('minus',-1)]]+[(f'full_half_{sign}','full',.5,v) for sign,v in [('plus',1),('minus',-1)]]
def case(s,device):
    f=ROOT/'parent/units'/f'CIFAR10_{s}';r=json.loads((f/'result.json').read_text());o=r['operator'];z=load(f/'cut_state.npz')
    state={k:torch.tensor(z[k],device=device) for k in ('theta','m','v')};state['clock']=o['clock'];return o,state,z
def future(data,s,path,o,c):
    ids=torch.tensor(o['first_batch_ids'],device=data['X'].device);yield data['X'][ids],data['Y'][ids]
    for i in range(1,c.future_steps):yield p.batch(data,s,p.seed(VERSION,'path',path,i),c)
def directions(md,st,z,U1,U16,c,s):
    u=norm(st['m']-torch.tensor(z['donor_m'],device=st['m'].device));d={'full':u}
    for r in (c.primary_rank,c.diagnostic_rank):
        for name,U in [('immediate',U1),('horizon',U16)]:
            proj=U[:,:r]@(U[:,:r].T@u);d[f'{name}{r}']=proj;d[f'remainder_{name}{r}']=u-proj
    g=torch.tensor(z['first_gradient'],device=u.device);d['gradient']=norm(g/(torch.sqrt(st['v']/(1-c.beta2**st['clock']))+c.eps))
    gen=torch.Generator().manual_seed(p.seed(VERSION,'random',s));v=torch.randn(len(u),generator=gen).to(u.device);a=0
    for param in md.parameters():
        n=param.numel();v[a:a+n]*=u[a:a+n].norm()/v[a:a+n].norm();a+=n
    d['random']=v;return d
@torch.no_grad()
def observe_logits(md,x):return array(md.eval()(x))
@torch.no_grad()
def endpoint(md,data,ids):
    correct=0;nll=0.;n=len(ids)
    for a in range(0,n,256):
        ix=torch.tensor(ids[a:a+256],device=data['TX'].device);z=md.eval()(data['TX'][ix]);y=data['TY'][ix]
        correct+=int((z.argmax(1)==y).sum());nll+=float(F.cross_entropy(z,y,reduction='sum'))
    return dict(accuracy=correct/n,nll=nll/n,n=n)
def native_branch(md,st,d,scale,sign,data,s,path,o,z,c,pulse):
    alpha=float(c.relative_displacement*st['m'].norm());delta=torch.zeros_like(st['m']) if d is None else d*(alpha*scale*sign)
    alt=dict(st,m=st['m']+delta);model,opt=restore(md,alt,c);actual=array(alt['m']-st['m']);wanted=array(delta)
    digest=lambda a:np.frombuffer(hashlib.sha256(a.tobytes()).digest(),dtype=np.uint8)
    rx=data['TX'][torch.tensor(z['response_ids'],device=st['m'].device)]
    out=dict(requested_delta_sha256=digest(wanted),actual_delta_sha256=digest(actual),moment_rounding=np.asarray(np.linalg.norm(actual-wanted)/max(np.linalg.norm(wanted),1e-30)),h0=observe_logits(model,rx))
    for h,(x,y) in enumerate(future(data,s,path,o,c),1):
        pulse();step(model,opt,x,y)
        if h in c.horizons:out[f'h{h}']=observe_logits(model,rx)
    return out,endpoint(model,data,z['test_ids'])
def capture(tr,x,H,U1,U16,c,s,path,pulse):
    ob=tr.observer(x,H);g=torch.Generator().manual_seed(p.seed(VERSION,'trace',s,path,H));trace=[];out={}
    for i in range(c.trace_probes):
        pulse();r=(2*torch.randint(0,2,(len(ob.y),),generator=g)-1).to(x.device,x.dtype);v=ob.vjp(r);trace.append(float(v.double().square().sum()))
        if (i+1)%32==0:print(f'Independent capture H{H} path{path} trace {i+1}/{c.trace_probes}',flush=True)
    out['trace_squared_norms']=np.asarray(trace)
    for name,U in [('immediate',U1),('horizon',U16)]:
        out[f'{name}_action']=array(torch.stack([ob.jvp(U[:,j]) for j in range(U.shape[1])],1))
    ob.close();return out
def qualify(tr,md,st,z,rx,bs,c,pulse):
    from audit12 import metrics
    u=norm(st['m']-torch.tensor(z['donor_m'],device=st['m'].device));alpha=float(c.relative_displacement*st['m'].norm())
    x=rx[torch.linspace(0,len(rx)-1,min(16,len(rx)),device=rx.device).long()];ob=tr.observer(x,c.fit_horizon)
    pred=array(ob.jvp(alpha*u)).reshape(len(x),-1)@array(ob.q).T*ob.norm
    gen=torch.Generator().manual_seed(62116);r=torch.randn(len(ob.y),generator=gen).to(x.device)
    lhs=float((ob.jvp(u).double()*r.double()).sum());rhs=float((u.double()*ob.vjp(r).double()).sum())
    dual=abs(lhs-rhs)/max(abs(lhs),abs(rhs),1e-12);check(dual<.003,'Backend tangent/adjoint duality failed')
    report=dict(duality_relative_error=dual,horizon=c.fit_horizon,finite_differences={})
    for scale in (1.,.5):
        ys=[]
        for sign in (-1,1):
            pulse();m,op=restore(md,dict(st,m=st['m']+u*(alpha*scale*sign)),c)
            for bx,by in bs[:c.fit_horizon]:pulse();step(m,op,bx,by)
            ys.append(observe_logits(m,x));del m,op
        effect=(ys[1].astype(np.float64)-ys[0])/2;score=metrics(effect,pred*scale,floor=c.resolution_floor)
        score['valid']=score['resolved'] and score['relative_prediction_error']<=c.derivative_error_max
        report['finite_differences'][str(scale)]=score
        check(not score['resolved'] or score['valid'],'Backend finite-difference control failed; stopping before costly fitting')
    ob.close();return report
def unit(s,data,camp,c,device,pulse):
    folder=camp.local/'units'/f'CIFAR10_{s}';folder.mkdir(parents=True,exist_ok=True)
    if (folder/'COMPLETE.json').exists():print('Already complete',s,flush=True);return
    o,st,z=case(s,device);md=p.ConvGN().to(device)
    layout=[dict(name=n,shape=list(v.shape),size=v.numel()) for n,v in md.named_parameters()];check(layout==o['layout'],'Imported layout differs')
    check(st['clock']==2000 and bool((st['v']>0).all()) and all(bool(torch.isfinite(st[k]).all()) for k in ('theta','m','v')),'Invalid imported state')
    a,b,g=[set(o[k]) for k in ('fit_anchor_ids','heldout_anchor_ids','first_batch_ids')]
    check(not(a&b or a&g or b&g) and not (a|b|g)&set(data['train_ids']) and (a|b|g)<=set(data['cal_ids']),'Role leakage')
    check(not set(z['response_ids'])&set(z['test_ids']),'Response/test overlap')
    save(folder/'cut_state.npz',**z);write_json(folder/'roles.json',dict(seed=s,**{k:o[k] for k in ('clock','layout','fit_anchor_ids','heldout_anchor_ids','first_batch_ids')}))
    fx=data['X'][torch.tensor(o['fit_anchor_ids'],device=device)];hx=data['X'][torch.tensor(o['heldout_anchor_ids'],device=device)];rx=data['TX'][torch.tensor(z['response_ids'],device=device)]
    bs=list(future(data,s,0,o,c));tr=Trainer(md,st,bs[:c.fit_horizon],c,pulse)
    original=torch.tensor(z['first_gradient'],device=device);cur=tr.records[0][1];rel=float((cur-original).norm()/original.norm());ab=float((cur-original).abs().max())
    check(rel<2e-5 and ab<2e-5*max(1.,float(original.abs().max())),'Imported first gradient mismatch');write_json(folder/'imported_gradient_check.json',dict(relative_l2=rel,max_abs=ab))
    if not(folder/'BACKEND_QUALIFICATION.json').exists():
        write_json(folder/'BACKEND_QUALIFICATION.json',qualify(tr,md,st,z,rx,bs,c,pulse));print('Actual-state backend derivative checks passed',s,flush=True)
    bases={}
    for H in (1,c.fit_horizon):
        f=folder/f'basis_h{H}.resume.npz'
        if f.exists():bases[H]=torch.tensor(load(f)['U'],device=device);print('Restored basis H',H,flush=True)
        else:
            A=exact_rows(tr,fx,H,pulse);U,info=basis(A,c.diagnostic_rank);del A;save(f,U=array(U));save(folder/f'fit_h{H}.npz',**info);bases[H]=U;camp.checkpoint(True)
    d=directions(md,st,z,bases[1],bases[c.fit_horizon],c,s);save(folder/'directions.npz',**{k:array(v) for k,v in d.items()})
    write_json(folder/'geometry.json',dict(displacement=float(c.relative_displacement*st['m'].norm()),
        principal_cosines_rank16=array(torch.linalg.svdvals(bases[1][:,:c.primary_rank].T@bases[c.fit_horizon][:,:c.primary_rank])).tolist(),
        direction_norms={k:float(v.norm()) for k,v in d.items()}))
    for path in c.future_paths:
        if path!=0:tr.close();del tr;gc.collect();tr=Trainer(md,st,list(future(data,s,path,o,c))[:c.fit_horizon],c,pulse)
        out=folder/f'path{path}';out.mkdir(exist_ok=True);write_json(out/'trajectory_numerics.json',tr.agreement)
        for H in (1,c.fit_horizon):
            if not (out/f'capture_h{H}.npz').exists():save(out/f'capture_h{H}.npz',**capture(tr,hx,H,bases[1],bases[c.fit_horizon],c,s,path,pulse));camp.checkpoint()
        if not(out/'predictions.npz').exists():
            pred={};alpha=float(c.relative_displacement*st['m'].norm())
            for H in (1,c.fit_horizon):
                ob=tr.observer(rx,H)
                for k,v in d.items():pred[f'{k}_h{H}']=array(ob.jvp(alpha*v))
                ob.close()
            save(out/'predictions.npz',**pred);camp.checkpoint()
    tr.close();del tr,bs;gc.collect()
    for path in c.future_paths:
        out=folder/f'path{path}'
        for name,key,scale,sign in branch_names(d):
            f=out/f'branch_{name}.npz';j=out/f'branch_{name}.json'
            if f.exists() and j.exists():continue
            values,scores=native_branch(md,st,None if key is None else d[key],scale,sign,data,s,path,o,z,c,pulse)
            save(f,**values);write_json(j,dict(name=name,direction=key,scale=scale,sign=sign,endpoint=scores));print(f'{s} path{path}: {name} complete',flush=True);camp.checkpoint()
    from audit12 import audit_unit
    write_json(folder/'RESULT.json',audit_unit(folder,c));write_json(folder/'COMPLETE.json',dict(seed=s,branches_per_path=len(branch_names(d))))
    for f in folder.glob('*.resume.npz'):f.unlink()
    camp.checkpoint(True)
def main(drive,local='/content/nexus12_run',session_hours=10,device_name='cuda',c=None,data=None):
    c=c or Config();device=torch.device(device_name);check(device.type!='cuda' or torch.cuda.is_available(),'Select a GPU runtime')
    torch.set_default_dtype(torch.float32);p.configure(device);env=p.environment(device)
    files={f.relative_to(ROOT).as_posix():sha(f) for f in ROOT.rglob('*') if f.is_file() and f.suffix in ('.py','.json','.npz') and '__pycache__' not in f.parts}
    ident=dict(version=VERSION,config=json.loads(p.canon(asdict(c))),environment=env,source_sha256=hashlib.sha256(p.canon(files).encode()).hexdigest())
    camp=Campaign(drive,local,ident);deadline=time.monotonic()+session_hours*3600
    def pulse():
        camp.pulse()
        if time.monotonic()>deadline:raise PauseRun('Session limit reached. Rerun the same notebook to resume.')
    status=camp.activate()
    try:
        if status=='FINISHED':print('Verified finished archive already exists.',flush=True);return
        meta=camp.local/'metadata';meta.mkdir(exist_ok=True)
        for f in ROOT.glob('*'):
            if f.is_file() and f.suffix in ('.py','.json'):shutil.copy2(f,meta/f.name)
        shutil.copytree(ROOT/'parent',meta/'parent',dirs_exist_ok=True);write_json(meta/'CONFIG.json',asdict(c));write_json(meta/'ENVIRONMENT.json',env)
        data=data or p.dataset_load('CIFAR10',str(Path(local).parent/'nexus12_data'),device,c)
        expected=json.loads((ROOT/'parent/metadata/CIFAR10_DATA.json').read_text());check(data['fingerprints']==expected['fingerprints'],'Dataset fingerprint differs')
        for i,s in enumerate(c.seeds):
            done=(camp.local/'units'/f'CIFAR10_{s}'/'COMPLETE.json').exists();resumed=bool(list((camp.local/'units'/f'CIFAR10_{s}').glob('*.resume.npz')));start=time.monotonic();unit(s,data,camp,c,device,pulse)
            if not done and not resumed:print(f'Observed seed pace: {(time.monotonic()-start)/60:.1f} min; estimated remaining {(time.monotonic()-start)*(len(c.seeds)-i-1)/3600:.2f} hours.',flush=True)
        from audit12 import audit_all
        report=audit_all(camp.local,c);write_json(camp.local/'analysis/REPORT.json',report);check(report['complete'],'Incomplete run cannot publish as finished')
        dest=camp.finish();print('FINISHED AND VERIFIED:',dest,f'{dest.stat().st_size/1e6:.1f} MB',flush=True)
    except PauseRun as e:camp.checkpoint(True);print(str(e),flush=True)
    except BaseException:
        try:camp.checkpoint(True)
        except BaseException as e:print('Checkpoint attempt failed:',type(e).__name__,str(e),flush=True)
        raise
    finally:camp.lease.release()
