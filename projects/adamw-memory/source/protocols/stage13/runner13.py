"""Fresh-seed, two-dataset horizon/bank-size confirmation."""
import gc,hashlib,json,math,os,platform,shutil,time
from pathlib import Path
from dataclasses import dataclass,asdict
import numpy as np
import torch
from torch.nn import functional as F
from models import ResNet18GN
from horizon import flat,restore,slots,step,Trainer
from operators import Bank,rs_basis,trace_probe
from archive_io import Campaign,write_json,sha,check
import data13
ROOT=Path(__file__).resolve().parent;VERSION='NEXUS-STAGE13-SCALE-BANK-R1'
@dataclass(frozen=True)
class Config:
    datasets:tuple=('CIFAR10','CIFAR100')
    seeds:tuple=(13000,13001,13002,13003)
    width:int=32
    train_steps:int=8000
    train_batch:int=128
    donor_step:int=5600
    future_batch:int=32
    future_steps:int=64
    horizons:tuple=(0,1,4,16,64)
    fit_horizon:int=16
    fit_sizes:tuple=(64,256)
    heldout_n:int=256
    first_n:int=128
    response_n:int=128
    ranks:tuple=(16,64)
    sketch_columns:int=128
    sketch_power:int=1
    quality_columns:int=192
    quality_energy_tolerance:float=.10
    quality_response_tolerance:float=.15
    trace_probes:int=128
    relative_displacement:float=.002
    resolution_floor:float=2e-5
    derivative_error_max:float=.15
    lr:float=.001
    beta1:float=.9
    beta2:float=.999
    eps:float=1e-8
    weight_decay:float=5e-4
    checkpoint_train_interval:int=1000
class PauseRun(RuntimeError):pass
def array(x):return x.detach().cpu().numpy()
def save(path,**values):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
    with open(tmp,'wb') as f:np.savez_compressed(f,**values);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def load(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
def norm(x):check(float(x.norm())>0,'Zero intervention direction');return x/x.norm()
def configure(device):
    torch.set_default_dtype(torch.float32);torch.set_num_threads(2);torch.use_deterministic_algorithms(True);torch.set_float32_matmul_precision('highest')
    if device.type=='cuda':
        torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
        torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
def environment(device):return dict(python=platform.python_version(),torch=str(torch.__version__),numpy=np.__version__,cuda=torch.version.cuda,cudnn=torch.backends.cudnn.version(),
    device=str(device),gpu=torch.cuda.get_device_name(device) if device.type=='cuda' else None,tf32=False,deterministic=True)
@torch.no_grad()
def logits(md,x):return array(md.eval()(x))
@torch.no_grad()
def score(md,data):
    ids=data['test_ids'];correct=0;nll=0.
    for a in range(0,len(ids),256):
        ix=torch.tensor(ids[a:a+256],device=data['TX'].device);z=md.eval()(data['TX'][ix]);y=data['TY'][ix]
        correct+=int((z.argmax(1)==y).sum());nll+=float(F.cross_entropy(z,y,reduction='sum'))
    return dict(accuracy=correct/len(ids),nll=nll/len(ids),n=len(ids))
def model_for(data,s,c,device):
    with torch.random.fork_rng(devices=[]):torch.manual_seed(data13.seed(VERSION,'model',data['name'],s));md=ResNet18GN(data['classes'],c.width)
    return md.to(device)
def training(md,data,s,unit,c,camp,pulse):
    f=unit/'state.resume.npz';history=unit/'TRAINING.json'
    if f.exists():
        z=load(f);state={k:torch.tensor(z[k],device=data['X'].device) for k in ('theta','m','v')};state['clock']=int(z['clock'])
        md,opt=restore(md,state,c);donor=torch.tensor(z['donor_m'],device=data['X'].device) if 'donor_m' in z else None
        curve=json.loads(history.read_text()) if history.exists() else []
    else:
        opt=torch.optim.AdamW(md.parameters(),lr=c.lr,betas=(c.beta1,c.beta2),eps=c.eps,weight_decay=c.weight_decay,foreach=False,fused=False)
        state={'clock':0};donor=None;curve=[]
    if state['clock']==c.train_steps:return md,state,donor
    train_start=time.monotonic();train_start_clock=state['clock']
    for i in range(state['clock'],c.train_steps):
        pulse();md.train();bx,by=data13.batch(data,s,i,c.train_batch);step(md,opt,bx,by)
        if i+1==c.donor_step:donor=slots(md,opt)['m'].clone()
        if (i+1)%500==0:print(data['name'],s,'training',i+1,'/',c.train_steps,'estimated training minutes remaining',round((time.monotonic()-train_start)/(i+1-train_start_clock)*(c.train_steps-i-1)/60,1),flush=True)
        if (i+1)%c.checkpoint_train_interval==0 or i+1 in (c.donor_step,c.train_steps):
            state=slots(md,opt);values={k:array(state[k]) for k in ('theta','m','v')};values['clock']=np.asarray(state['clock'])
            if donor is not None:values['donor_m']=array(donor)
            save(f,**values)
            if i+1 in (c.train_steps//2,c.train_steps):curve.append(dict(clock=i+1,**score(md,data)));write_json(history,curve)
            camp.checkpoint(True)
    check(donor is not None,'Historical donor was not saved');return md,slots(md,opt),donor
def qual(tr,md,state,donor,rx,bs,c,pulse):
    from audit13 import metrics
    u=norm(state['m']-donor);alpha=float(c.relative_displacement*state['m'].norm());x=rx[:min(16,len(rx))]
    b=Bank(tr,x,c.fit_horizon);prediction=array(b.jvp(alpha*u)).reshape(len(x),-1)
    Q=__import__('horizon').helmert(md.head.out_features,x.device,x.dtype);pred=prediction@array(Q).T*math.sqrt(len(x)*md.head.out_features)
    gen=torch.Generator().manual_seed(51377);r=torch.randn(b.outputs,generator=gen).to(x.device)
    lhs=float((b.jvp(u).double()*r.double()).sum());rhs=float((u.double()*b.vjp(r).double()).sum());dual=abs(lhs-rhs)/max(abs(lhs),abs(rhs),1e-12)
    check(dual<.005,'Large-model tangent/adjoint duality failed');out=dict(duality_relative_error=dual,finite_difference={})
    for scale in (1.,.5):
        results=[]
        for sign in (-1,1):
            m,o=restore(md,dict(state,m=state['m']+u*(alpha*scale*sign)),c)
            for x1,y1 in bs[:c.fit_horizon]:pulse();step(m,o,x1,y1)
            results.append(logits(m,x));del m,o
        actual=(results[1].astype(float)-results[0])/2;v=metrics(actual,pred*scale,c.resolution_floor)
        v['valid']=v['resolved'] and v['relative_prediction_error']<=c.derivative_error_max;out['finite_difference'][str(scale)]=v
        check(not v['resolved'] or v['valid'],'Resolved native finite-difference qualification failed')
    b.close();return out
def make_controls(md,state,donor,tr,s,c):
    u=norm(state['m']-donor);g=tr.records[0][1];grad=norm(g/(torch.sqrt(state['v']/(1-c.beta2**state['clock']))+c.eps))
    gen=torch.Generator().manual_seed(data13.seed(VERSION,'random',s));r=torch.randn(len(u),generator=gen).to(u.device);a=0
    for p in md.parameters():
        n=p.numel();r[a:a+n]*=u[a:a+n].norm()/r[a:a+n].norm();a+=n
    return {'full':u,'gradient':grad,'random':r}
def fits(c):return [(H,n) for n in c.fit_sizes for H in (1,c.fit_horizon)]
def tag(H,n,r):return f'h{H}_n{n}_r{r}'
def capture_eval(md,state,data,s,role,Hfit,n,U,c,pulse):
    result={}
    for path in (0,1):
        tr=Trainer(md,state,list(data13.future(data,s,role,path,c))[:c.fit_horizon],c,pulse)
        for H in (1,c.fit_horizon):
            x=data['X'][torch.tensor(role['heldout_ids'],device=data['X'].device)];bank=Bank(tr,x,H)
            result[f'path{path}_h{H}']=trace_probe(bank,U,c.trace_probes,data13.seed(VERSION,'trace',data['name'],s,path,H),pulse);bank.close()
        tr.close();del tr;gc.collect()
    return result
def fit_phase(md,state,donor,data,s,role,unit,d,c,camp,pulse):
    device=data['X'].device;bs=list(data13.future(data,s,role,0,c));tr=Trainer(md,state,bs[:c.fit_horizon],c,pulse)
    rx=data['TX'][torch.tensor(role['response_ids'],device=device)]
    if not(unit/'QUALIFICATION.json').exists():write_json(unit/'QUALIFICATION.json',qual(tr,md,state,donor,rx,bs,c,pulse))
    for H,n in fits(c):
        done=unit/f'fit_h{H}_n{n}.json'
        if done.exists():continue
        x=data['X'][torch.tensor(role['fit_ids'][:n],device=device)];bank=Bank(tr,x,H)
        print(data['name'],s,'fit',H,n,flush=True);U,info=rs_basis(bank,c.sketch_columns,max(c.ranks),data13.seed(VERSION,'sketch',data['name'],s,H,n),c.sketch_power,pulse)
        save(unit/f'fit_h{H}_n{n}.npz',**info)
        if s==c.seeds[0] and H==c.fit_horizon:
            # Fixed wider-sketch comparison on each dataset's first fresh seed.
            V,ref=rs_basis(bank,c.quality_columns,max(c.ranks),data13.seed(VERSION,'sketch',data['name'],s,H,n),c.sketch_power,pulse)
            energy_rel={str(r):float(abs(info['ritz_spectrum'][:r].sum()-ref['ritz_spectrum'][:r].sum())/ref['ritz_spectrum'][:r].sum()) for r in c.ranks}
            bresponse=Bank(tr,rx,H);effects={}
            full=bresponse.jvp(d['full']);full_norm=float(full.norm())
            for r in c.ranks:
                a=U[:,:r]@(U[:,:r].T@d['full']);v=V[:,:r]@(V[:,:r].T@d['full'])
                effects[str(r)]=float((bresponse.jvp(a)-bresponse.jvp(v)).norm()/max(full_norm,1e-30))
            bresponse.close();del V
            q=dict(energy_relative_change=energy_rel,projected_response_change_over_full=effects,primary_rank_valid=energy_rel[str(c.ranks[0])]<=c.quality_energy_tolerance and effects[str(c.ranks[0])]<=c.quality_response_tolerance)
            write_json(unit/f'quality_h{H}_n{n}.json',q)
            check(q['primary_rank_valid'],'Sketch convergence qualification failed. Retain the checkpoint/report; do not interpret primary effects until resolved.')
        for r in c.ranks:d[tag(H,n,r)]=U[:,:r]@(U[:,:r].T@d['full'])
        save(unit/'directions.resume.npz',**{k:array(v) for k,v in d.items()})
        bank.close();tr.close();del tr;gc.collect()
        captures=capture_eval(md,state,data,s,role,H,n,U,c,pulse)
        for k,values in captures.items():save(unit/f'capture_fitH{H}_n{n}_{k}.npz',**values)
        del U;write_json(done,dict(fit_horizon=H,fit_n=n,approximate=True,columns=int(info['columns']),power=int(info['power'])));camp.checkpoint(True)
        tr=Trainer(md,state,bs[:c.fit_horizon],c,pulse)
    tr.close();del tr;gc.collect();return d
def expand(d,c):
    out=dict(d)
    for H,n in fits(c):
        for r in c.ranks:out['rem_'+tag(H,n,r)]=d['full']-d[tag(H,n,r)]
    return out
def plan(d):return [('baseline',None,0.,0)]+[(f'{k}_{sg}',k,1.,sign) for k in d for sg,sign in [('plus',1),('minus',-1)]]+[(f'full_half_{sg}','full',.5,sign) for sg,sign in [('plus',1),('minus',-1)]]
def predictions(md,state,data,s,role,d,c,pulse):
    out={};rx=data['TX'][torch.tensor(role['response_ids'],device=data['X'].device)];alpha=float(c.relative_displacement*state['m'].norm())
    for path in (0,1):
        tr=Trainer(md,state,list(data13.future(data,s,role,path,c))[:c.fit_horizon],c,pulse)
        for H in (1,c.fit_horizon):
            bank=Bank(tr,rx,H)
            for name,v in d.items():out[f'path{path}_h{H}_{name}']=array(bank.jvp(v*alpha))
            bank.close()
        tr.close();del tr;gc.collect()
    return out
def branch(md,state,data,s,role,path,vector,scale,sign,c,pulse):
    alpha=float(c.relative_displacement*state['m'].norm());delta=torch.zeros_like(state['m']) if vector is None else vector*(alpha*scale*sign)
    alt=dict(state,m=state['m']+delta);actual=alt['m']-state['m'];requested=array(delta);actual_cpu=array(actual)
    m,o=restore(md,alt,c);rx=data['TX'][torch.tensor(role['response_ids'],device=data['X'].device)]
    # Verify cut invariance at execution, avoid duplicating h0 logits 656 times.
    before=logits(m,rx);reference=logits(md,rx);check(np.array_equal(before,reference),'Surgery changed current logits')
    out=dict(requested_delta_sha256=np.frombuffer(hashlib.sha256(requested.tobytes()).digest(),dtype=np.uint8),
        actual_delta_sha256=np.frombuffer(hashlib.sha256(actual_cpu.tobytes()).digest(),dtype=np.uint8),
        moment_rounding=np.asarray(float((actual-delta).norm()/delta.norm().clamp_min(1e-30))),cut_logits_sha256=np.frombuffer(hashlib.sha256(before.tobytes()).digest(),dtype=np.uint8))
    if vector is None:out['h0']=before
    for H,(x,y) in enumerate(data13.future(data,s,role,path,c),1):
        pulse();step(m,o,x,y)
        if H in c.horizons:out[f'h{H}']=logits(m,rx)
    return out,score(m,data)
def run_unit(data,s,c,camp,pulse):
    unit=camp.local/'units'/f'{data["name"]}_{s}';unit.mkdir(parents=True,exist_ok=True)
    if (unit/'COMPLETE.json').exists():print('Already completed',unit.name,flush=True);return
    device=data['X'].device;md=model_for(data,s,c,device);role=data13.roles(data,s,c.fit_sizes,c.heldout_n,c.first_n);write_json(unit/'ROLES.json',role)
    md,state,donor=training(md,data,s,unit,c,camp,pulse)
    check(state['clock']==c.train_steps and donor is not None,'Incomplete training state')
    check(bool((state['v']>0).all()),'Unresolved zero second-moment coordinates')
    initial=score(md,data);threshold={'CIFAR10':.60,'CIFAR100':.25}.get(data['name'],0.);quality=dict(accuracy_threshold=threshold,passes=initial['accuracy']>=threshold,action='Retain every seed; flag weakly trained cohorts, do not tune or exclude.')
    write_json(unit/'CUT.json',dict(training_quality=quality,clock=state['clock'],donor_clock=c.donor_step,parameters=len(state['m']),classes=data['classes'],model='CIFAR ResNet18-GN',width=c.width,
        state_hashes={k:hashlib.sha256(array(state[k]).tobytes()).hexdigest() for k in ('theta','m','v')},moment_norm=float(state['m'].norm()),
        displacement=float(c.relative_displacement*state['m'].norm()),initial_test=initial))
    df=unit/'directions.resume.npz'
    if df.exists():d={k:torch.tensor(v,device=device) for k,v in load(df).items()}
    else:
        tr=Trainer(md,state,list(data13.future(data,s,role,0,c))[:1],c,pulse);d=make_controls(md,state,donor,tr,s,c);tr.close()
    d=fit_phase(md,state,donor,data,s,role,unit,d,c,camp,pulse);d=expand(d,c)
    write_json(unit/'DIRECTIONS.json',{k:dict(norm=float(v.norm()),sha256=hashlib.sha256(array(v).tobytes()).hexdigest()) for k,v in d.items()})
    if not(unit/'predictions.npz').exists():save(unit/'predictions.npz',**predictions(md,state,data,s,role,d,c,pulse));camp.checkpoint()
    for path in (0,1):
        folder=unit/f'path{path}';folder.mkdir(exist_ok=True)
        for name,key,scale,sign in plan(d):
            f=folder/f'branch_{name}.npz';j=folder/f'branch_{name}.json'
            if f.exists() and j.exists():continue
            out,endpoint=branch(md,state,data,s,role,path,None if key is None else d[key],scale,sign,c,pulse)
            save(f,**out);write_json(j,dict(name=name,key=key,scale=scale,sign=sign,endpoint=endpoint));print(unit.name,path,name,'complete',flush=True);camp.checkpoint()
    from audit13 import audit_unit
    write_json(unit/'RESULT.json',audit_unit(unit,c));write_json(unit/'COMPLETE.json',dict(dataset=data['name'],seed=s,branches_per_path=len(plan(d))))
    for f in unit.glob('*.resume.npz'):f.unlink()
    camp.checkpoint(True)
def main(drive,local='/content/nexus13_run',session_hours=10,device_name='cuda',c=None,data_map=None):
    c=c or Config();device=torch.device(device_name);check(device.type!='cuda' or torch.cuda.is_available(),'Select an A100 GPU runtime')
    configure(device);env=environment(device);source={f.relative_to(ROOT).as_posix():sha(f) for f in ROOT.rglob('*') if f.is_file() and f.suffix in ('.py','.json') and '__pycache__' not in f.parts}
    ident=dict(version=VERSION,config=json.loads(json.dumps(asdict(c))),environment=env,source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest())
    camp=Campaign(drive,local,ident);deadline=time.monotonic()+session_hours*3600
    def pulse():
        camp.pulse()
        if time.monotonic()>deadline:raise PauseRun('Session cap reached. Rerun the same notebook/environment to continue.')
    status=camp.activate();unit_times=[]
    try:
        if status=='FINISHED':print('Verified finished campaign already exists.');return
        meta=camp.local/'metadata';meta.mkdir(exist_ok=True)
        for f in ROOT.glob('*'):
            if f.is_file() and f.suffix in ('.py','.json'):shutil.copy2(f,meta/f.name)
        write_json(meta/'CONFIG.json',asdict(c));write_json(meta/'ENVIRONMENT.json',env)
        for name in c.datasets:
            data=data_map[name] if data_map else data13.load(name,str(Path(local).parent/'nexus13_data'),device,response_n=c.response_n)
            write_json(meta/f'{name}_DATA.json',{k:data[k].tolist() if isinstance(data[k],np.ndarray) else data[k] for k in ('fingerprints','train_ids','cal_ids','response_ids','test_ids')})
            for s in c.seeds:
                was_done=(camp.local/'units'/f'{name}_{s}'/'COMPLETE.json').exists();start=time.monotonic();run_unit(data,s,c,camp,pulse)
                if not was_done:
                    unit_times.append(time.monotonic()-start);completed=len(list((camp.local/'units').glob('*/COMPLETE.json')));remaining=len(c.datasets)*len(c.seeds)-completed
                    print('UNIT COMPLETE',name,s,'minutes this session',round(unit_times[-1]/60,1),'rough remaining campaign hours',round(np.mean(unit_times)*remaining/3600,1),'(partial resumes and dataset differences can bias this estimate)',flush=True)
            del data;gc.collect()
            if device.type=='cuda':torch.cuda.empty_cache()
        from audit13 import audit_all
        report=audit_all(camp.local,c);write_json(camp.local/'analysis/REPORT.json',report);check(report['complete'],'Incomplete campaign cannot be marked finished')
        if not report['scientific_primary_valid']:print('WARNING: completed campaign has failed or unresolved primary validity checks. Consult REPORT.json before making scientific claims.',flush=True)
        dest=camp.finish();print('FINISHED AND VERIFIED:',dest,f'{dest.stat().st_size/1e6:.1f} MB',flush=True)
    except PauseRun as e:camp.checkpoint(True);print(str(e),flush=True)
    except BaseException:
        try:camp.checkpoint(True)
        except BaseException as e:print('Checkpoint attempt failed:',type(e).__name__,str(e),flush=True)
        raise
    finally:camp.lease.release()
