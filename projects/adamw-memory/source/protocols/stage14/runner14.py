"""Prospective stable-continuation and alternate-future confirmation."""
import gc,hashlib,json,math,os,platform,shutil,time
from contextlib import contextmanager,nullcontext
from pathlib import Path
from dataclasses import dataclass,asdict,replace
import numpy as np
import torch
from torch.nn import functional as F
from models import ResNet18GN
from horizon import flat,restore,slots,step,Trainer
from operators import Bank,rs_basis,trace_probe
from archive_io import Campaign,write_json,sha,check,pack,publish,verify
import data13
ROOT=Path(__file__).resolve().parent;VERSION='NEXUS-STAGE14-STABLE-CONTINUATION-R2'
@dataclass(frozen=True)
class Config:
    datasets:tuple=('CIFAR10','CIFAR100')
    seeds:tuple=tuple(range(14000,14008))
    width:int=32
    train_steps:int=8000
    train_batch:int=128
    donor_step:int=5600
    future_batch:int=128
    future_steps:int=64
    horizons:tuple=(0,1,4,16,64)
    fit_horizon:int=16
    fit_sizes:tuple=(256,)
    heldout_n:int=256
    first_n:int=128
    response_n:int=128
    ranks:tuple=(16,64)
    sketch_columns:int=128
    sketch_power:int=1
    quality_columns:int=192
    quality_seed_count:int=2
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
    future_lr:float=.00012
    hessian_microbatch:int=32
    hessian_cache_gib:float=12.0
    max_baseline_accuracy_drop:float=.02
    max_baseline_nll_increase:float=.10
    dataset_sign_alpha:float=.025
    transfer_margin:float=.05
    cut_floor_cifar10:float=.60
    cut_floor_cifar100:float=.25
class PauseRun(RuntimeError):pass
class SessionClock:
    """Soft session cap: finish atomic operator work before pausing."""
    def __init__(self,camp,hours,clock=None):
        check(math.isfinite(hours) and hours>0,'Session hours must be finite and positive')
        self.camp=camp;self.clock=clock or time.monotonic
        self.deadline=self.clock()+hours*3600;self.depth=0;self.announced=False
    def __call__(self):
        self.camp.pulse()
        if self.clock()>self.deadline:
            if self.depth:
                if not self.announced:
                    print('Session cap reached; finishing current operator transaction before checkpoint and pause.',flush=True)
                    self.announced=True
            else:raise PauseRun('Session cap reached. Rerun identical notebook/environment to resume.')
    @contextmanager
    def atomic(self):
        self();self.depth+=1
        try:yield
        finally:self.depth-=1
def atomic_work(pulse):
    return pulse.atomic() if hasattr(pulse,'atomic') else nullcontext()
def array(x):return x.detach().cpu().numpy()
def save(path,**values):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
    with open(tmp,'wb') as f:np.savez_compressed(f,**values);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def load(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k].copy(order='K') for k in z.files}
class OperatorJournal:
    """Writes a resumable working matrix when the durable interval is due."""
    def __init__(self,path,camp):self.path=Path(path);self.camp=camp
    def due(self):return self.camp.checkpoint_due()
    def load(self,key):
        if not self.path.exists():return None
        z=load(self.path);check(json.loads(str(z.pop('__key__')))==key,'Working operator identity mismatch')
        return json.loads(str(z.pop('__meta__'))),z
    def save(self,key,meta,arrays):
        # Keep growing columns adjacent in storage; live operator arithmetic is unchanged.
        stored={k:np.asfortranarray(v) if getattr(v,'ndim',0)==2 else v for k,v in arrays.items()}
        save(self.path,__key__=np.asarray(json.dumps(key,sort_keys=True)),__meta__=np.asarray(json.dumps(meta,sort_keys=True)),**stored)
        self.camp.checkpoint(True)
        print('DURABLE OPERATOR CHECKPOINT:',self.path.name,meta,flush=True)
    def discard(self):self.path.unlink(missing_ok=True)
def cached_basis(bank,H,n,columns,s,data,unit,c,camp,pulse):
    cached=unit/f'basis_h{H}_n{n}_l{columns}.resume.npz'
    if cached.exists():
        z=load(cached);U=torch.from_numpy(z.pop('U')).to(bank.device,bank.dtype)
        print('RESTORED COMPLETED BASIS:',cached.name,flush=True);return U,z
    journal=OperatorJournal(unit/f'operator_h{H}_n{n}_l{columns}.resume.npz',camp)
    U,info=rs_basis(bank,columns,max(c.ranks),data13.seed(VERSION,'sketch',data['name'],s,H,n),c.sketch_power,pulse,journal=journal)
    save(cached,U=array(U),**info);journal.discard();camp.checkpoint(True)
    return U,info

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
    check(f.exists() or not history.exists(),
          'Saved training history lacks its optimizer state; refusing silent retraining: '+str(unit))
    if f.exists():
        z=load(f);state={k:torch.tensor(z[k],device=data['X'].device) for k in ('theta','m','v')};state['clock']=int(z['clock'])
        check(0<=state['clock']<=c.train_steps,'Invalid restored training clock')
        md,opt=restore(md,state,c);donor=torch.tensor(z['donor_m'],device=data['X'].device) if 'donor_m' in z else None
        check(state['clock']<c.donor_step or donor is not None,'Saved training state lacks historical donor')
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
        if (i+1)%c.checkpoint_train_interval==0 or i+1 in (c.donor_step,c.train_steps) or camp.checkpoint_due():
            state=slots(md,opt);values={k:array(state[k]) for k in ('theta','m','v')};values['clock']=np.asarray(state['clock'])
            if donor is not None:values['donor_m']=array(donor)
            save(f,**values)
            if i+1 in (c.train_steps//2,c.train_steps):curve.append(dict(clock=i+1,**score(md,data)));write_json(history,curve)
            camp.checkpoint()
    check(donor is not None,'Historical donor was not saved');return md,slots(md,opt),donor
def qual(tr,md,state,donor,rx,bs,c,pulse):
    from audit13 import metrics
    u=norm(state['m']-donor);alpha=float(c.relative_displacement*state['m'].norm());x=rx
    b=Bank(tr,x,c.fit_horizon);prediction=array(b.jvp(alpha*u)).reshape(len(x),-1)
    Q=__import__('horizon').helmert(md.head.out_features,x.device,x.dtype);pred=prediction@array(Q).T*math.sqrt(len(x)*md.head.out_features)
    gen=torch.Generator().manual_seed(51377);r=torch.randn(b.outputs,generator=gen).to(x.device)
    lhs=float((b.jvp(u).double()*r.double()).sum());rhs=float((u.double()*b.vjp(r).double()).sum());dual=abs(lhs-rhs)/max(abs(lhs),abs(rhs),1e-12)
    out=dict(duality_relative_error=dual,finite_difference={})
    for scale in (1.,.5):
        results=[]
        for sign in (-1,1):
            m,o=restore(md,dict(state,m=state['m']+u*(alpha*scale*sign)),c)
            for x1,y1 in bs[:c.fit_horizon]:pulse();step(m,o,x1,y1)
            results.append(logits(m,x));del m,o
        actual=(results[1].astype(float)-results[0])/2;v=metrics(actual,pred*scale,c.resolution_floor)
        v['valid']=v['resolved'] and v['relative_prediction_error']<=c.derivative_error_max;out['finite_difference'][str(scale)]=v
    out['passes']=dual<.005 and all(v['valid'] for v in out['finite_difference'].values())
    b.close();return out
def make_controls(md,state,donor,tr,s,c):
    u=norm(state['m']-donor);g=tr.records[0][1];grad=norm(g/(torch.sqrt(state['v']/(1-c.beta2**state['clock']))+c.eps))
    gen=torch.Generator().manual_seed(data13.seed(VERSION,'random',s));r=torch.randn(len(u),generator=gen).to(u.device);a=0
    for p in md.parameters():
        n=p.numel();r[a:a+n]*=u[a:a+n].norm()/r[a:a+n].norm();a+=n
    return {'full':u,'gradient':grad,'random':r}
def fits(c):return [(H,n) for n in c.fit_sizes for H in (1,c.fit_horizon)]
def tag(H,n,r):return f'h{H}_n{n}_r{r}'
def capture_eval(md,state,data,s,role,Hfit,n,U,c,pulse,unit=None,camp=None):
    result={}
    for path in (0,1):
        tr=Trainer(md,state,list(data13.future(data,s,role,path,c))[:c.fit_horizon],c,pulse)
        for H in (1,c.fit_horizon):
            key=f'path{path}_h{H}'
            dest=unit/f'capture_fitH{Hfit}_n{n}_{key}.npz' if unit is not None else None
            if dest is not None and dest.exists():result[key]=load(dest);continue
            x=data['X'][torch.tensor(role['heldout_ids'],device=data['X'].device)];bank=Bank(tr,x,H)
            journal=OperatorJournal(unit/f'trace_fitH{Hfit}_n{n}_{key}.resume.npz',camp) if dest is not None else None
            result[key]=trace_probe(bank,U,c.trace_probes,data13.seed(VERSION,'trace',data['name'],s,path,H),pulse,journal=journal);bank.close()
            if dest is not None:
                save(dest,**result[key]);journal.discard();camp.checkpoint(True)
        tr.close();del tr;gc.collect()
    return result
def fit_phase(md,state,donor,data,s,role,unit,d,c,camp,pulse):
    device=data['X'].device;bs=list(data13.future(data,s,role,0,c));tr=Trainer(md,state,bs[:c.fit_horizon],c,pulse)
    rx=data['TX'][torch.tensor(role['response_ids'],device=device)]
    qfile=unit/'QUALIFICATION.json'
    if not qfile.exists():
        qualifications={'0':qual(tr,md,state,donor,rx,bs,c,pulse)}
        alternate=list(data13.future(data,s,role,1,c))
        other=Trainer(md,state,alternate[:c.fit_horizon],c,pulse)
        qualifications['1']=qual(other,md,state,donor,rx,alternate,c,pulse)
        other.close();del other
        write_json(qfile,dict(paths=qualifications,primary_valid=all(q['passes'] for q in qualifications.values())))
        camp.checkpoint(True)
    check(json.loads(qfile.read_text())['primary_valid'],
        'Full/half effects unresolved or derivative qualification failed on a future. Retain CHECKPOINT.zip; no expensive operator fit is started for this unit.')
    for H,n in fits(c):
        done=unit/f'fit_h{H}_n{n}.json'
        if done.exists():continue
        with atomic_work(pulse):
            captures=[unit/f'capture_fitH{H}_n{n}_path{p}_h{h}.npz' for p in (0,1) for h in (1,c.fit_horizon)]
            if not all(f.exists() for f in captures):
                x=data['X'][torch.tensor(role['fit_ids'][:n],device=device)];bank=Bank(tr,x,H)
                print(data['name'],s,'fit',H,n,flush=True)
                U,info=cached_basis(bank,H,n,c.sketch_columns,s,data,unit,c,camp,pulse)
                save(unit/f'fit_h{H}_n{n}.npz',**info)
                for r in c.ranks:d[tag(H,n,r)]=U[:,:r]@(U[:,:r].T@d['full'])
                save(unit/'directions.resume.npz',**{k:array(v) for k,v in d.items()})
                bank.close();tr.close();del tr;gc.collect()
                capture_eval(md,state,data,s,role,H,n,U,c,pulse,unit,camp)
                del U;(unit/f'basis_h{H}_n{n}_l{c.sketch_columns}.resume.npz').unlink(missing_ok=True)
                # The original basis is no longer needed once capture and projections are durable.
                camp.checkpoint(True)
                tr=Trainer(md,state,bs[:c.fit_horizon],c,pulse)
            (unit/f'basis_h{H}_n{n}_l{c.sketch_columns}.resume.npz').unlink(missing_ok=True)
            info=load(unit/f'fit_h{H}_n{n}.npz')
            if s in c.seeds[:c.quality_seed_count] and H==c.fit_horizon:
                quality=unit/f'quality_h{H}_n{n}.json'
                if not quality.exists():
                    x=data['X'][torch.tensor(role['fit_ids'][:n],device=device)];bank=Bank(tr,x,H)
                    V,ref=cached_basis(bank,H,n,c.quality_columns,s,data,unit,c,camp,pulse)
                    energy_rel={str(r):float(abs(info['ritz_spectrum'][:r].sum()-ref['ritz_spectrum'][:r].sum())/ref['ritz_spectrum'][:r].sum()) for r in c.ranks}
                    bresponse=Bank(tr,rx,H);effects={}
                    full=bresponse.jvp(d['full']);full_norm=float(full.norm())
                    for r in c.ranks:
                        a=d[tag(H,n,r)];v=V[:,:r]@(V[:,:r].T@d['full'])
                        effects[str(r)]=float((bresponse.jvp(a)-bresponse.jvp(v)).norm()/max(full_norm,1e-30))
                    bresponse.close();bank.close();del V
                    q=dict(energy_relative_change=energy_rel,projected_response_change_over_full=effects,primary_rank_valid=energy_rel[str(c.ranks[0])]<=c.quality_energy_tolerance and effects[str(c.ranks[0])]<=c.quality_response_tolerance)
                    write_json(quality,q)
                    (unit/f'basis_h{H}_n{n}_l{c.quality_columns}.resume.npz').unlink(missing_ok=True)
                    camp.checkpoint(True)
                check(json.loads(quality.read_text())['primary_rank_valid'],'Sketch convergence qualification failed. Retain the checkpoint/report; do not interpret primary effects until resolved.')
            write_json(done,dict(fit_horizon=H,fit_n=n,approximate=True,columns=int(info['columns']),power=int(info['power'])));camp.checkpoint(True)
    tr.close();del tr;gc.collect();return d

def expand(d,c):
    out=dict(d)
    for H,n in fits(c):
        for r in c.ranks:out['rem_'+tag(H,n,r)]=d['full']-d[tag(H,n,r)]
    return out
def plan(d):return [('baseline',None,0.,0)]+[(f'{k}_{sg}',k,1.,sign) for k in d for sg,sign in [('plus',1),('minus',-1)]]+[(f'full_half_{sg}','full',.5,sign) for sg,sign in [('plus',1),('minus',-1)]]
def predictions(md,state,data,s,role,d,c,pulse,unit=None,camp=None):
    work=unit/'prediction_work.resume.npz' if unit is not None else None
    out=load(work) if work is not None and work.exists() else {};rx=data['TX'][torch.tensor(role['response_ids'],device=data['X'].device)];alpha=float(c.relative_displacement*state['m'].norm())
    for path in (0,1):
        tr=Trainer(md,state,list(data13.future(data,s,role,path,c))[:c.fit_horizon],c,pulse)
        for H in (1,c.fit_horizon):
            bank=Bank(tr,rx,H)
            for name,v in d.items():
                key=f'path{path}_h{H}_{name}'
                if key in out:continue
                out[key]=array(bank.jvp(v*alpha))
                if camp is not None and camp.checkpoint_due():save(work,**out);camp.checkpoint(True)
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
    train_c=c;device=data['X'].device;md=model_for(data,s,c,device);role=data13.roles(data,s,c.fit_sizes,c.heldout_n,c.first_n);write_json(unit/'ROLES.json',role)
    md,state,donor=training(md,data,s,unit,train_c,camp,pulse)
    c=replace(train_c,lr=train_c.future_lr)
    check(state['clock']==c.train_steps and donor is not None,'Incomplete training state')
    check(bool((state['v']>0).all()),'Unresolved zero second-moment coordinates')
    initial=score(md,data);threshold={'CIFAR10':c.cut_floor_cifar10,'CIFAR100':c.cut_floor_cifar100}.get(data['name'],0.);quality=dict(accuracy_threshold=threshold,passes=initial['accuracy']>=threshold,action='Retain every seed; flag weakly trained cohorts, do not tune or exclude.')
    write_json(unit/'CUT.json',dict(training_quality=quality,clock=state['clock'],donor_clock=c.donor_step,parameters=len(state['m']),classes=data['classes'],model='CIFAR ResNet18-GN',width=c.width,
        state_hashes={k:hashlib.sha256(array(state[k]).tobytes()).hexdigest() for k in ('theta','m','v')},moment_norm=float(state['m'].norm()),
        displacement=float(c.relative_displacement*state['m'].norm()),initial_test=initial))
    df=unit/'directions.resume.npz'
    check(df.exists() or not any(unit.glob('fit_h*_n*.json')),
          'Saved fitted operators lack their directions; refusing inconsistent resume: '+str(unit))
    if df.exists():d={k:torch.tensor(v,device=device) for k,v in load(df).items()}
    else:
        tr=Trainer(md,state,list(data13.future(data,s,role,0,c))[:1],c,pulse);d=make_controls(md,state,donor,tr,s,c);tr.close()
    d=fit_phase(md,state,donor,data,s,role,unit,d,c,camp,pulse);d=expand(d,c)
    write_json(unit/'DIRECTIONS.json',{k:dict(norm=float(v.norm()),sha256=hashlib.sha256(array(v).tobytes()).hexdigest()) for k,v in d.items()})
    if not(unit/'predictions.npz').exists():
        with atomic_work(pulse):
            save(unit/'predictions.npz',**predictions(md,state,data,s,role,d,c,pulse,unit,camp))
            (unit/'prediction_work.resume.npz').unlink(missing_ok=True);camp.checkpoint(True)
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
def preflight(data,s,c,camp,pulse):
    unit=camp.local/'units'/f'{data["name"]}_{s}';unit.mkdir(parents=True,exist_ok=True)
    f=unit/'STABILITY14.json'
    if f.exists():return json.loads(f.read_text())
    md=model_for(data,s,c,data['X'].device);role=data13.roles(data,s,c.fit_sizes,c.heldout_n,c.first_n)
    write_json(unit/'ROLES.json',role);md,state,donor=training(md,data,s,unit,c,camp,pulse)
    fc=replace(c,lr=c.future_lr);cut=score(md,data);curves={};good=True
    floor={'CIFAR10':c.cut_floor_cifar10,'CIFAR100':c.cut_floor_cifar100}[data['name']]
    good=good and cut['accuracy']>=floor
    for path in (0,1):
        m,opt=restore(md,state,fc);curve=[]
        for H,(x,y) in enumerate(data13.future(data,s,role,path,c),1):
            pulse();step(m,opt,x,y)
            if H in (1,c.fit_horizon,c.future_steps):
                q=score(m,data);q.update(horizon=H,accuracy_drop=cut['accuracy']-q['accuracy'],nll_increase=q['nll']-cut['nll'])
                q['passes']=q['accuracy_drop']<=c.max_baseline_accuracy_drop and q['nll_increase']<=c.max_baseline_nll_increase
                good=good and q['passes'];curve.append(q)
        curves[str(path)]=curve;del m,opt
    report=dict(dataset=data['name'],seed=s,cut=cut,cut_floor=floor,paths=curves,passes=bool(good),train_lr=c.lr,future_lr=c.future_lr,
        rule='Every seed and both paths must pass at H1/H16/H64; no exclusion or retuning.')
    write_json(f,report);camp.checkpoint(True);del md,state,donor;gc.collect()
    if data['X'].device.type=='cuda':torch.cuda.empty_cache()
    print('STABILITY',data['name'],s,'PASS' if good else 'FAIL',flush=True);return report

def exact_sign_positive(x):
    x=np.asarray(x,float);check(np.isfinite(x).all(),'Nonfinite sign-test values')
    # Count exact ties as nonpositive. Dropping them can be anti-conservative
    # for a one-sided median null when measurements have a point mass at zero.
    n=len(x);k=int((x>0).sum());ties=int((x==0).sum())
    return dict(n=n,positive=k,ties=ties,tie_rule='ties count as nonpositive',
        p_one_sided=float(sum(math.comb(n,j) for j in range(k,n+1))/2**n) if n else 1.)

def registered_analysis(root,c,report=None):
    from audit13 import metrics
    results=[]
    qualification=report or json.loads((Path(root)/'analysis'/'REPORT.json').read_text())
    for ds in c.datasets:
        eligible=qualification['datasets'][ds]['scientific_valid']
        rows=[]
        for seed in c.seeds:
            unit=Path(root)/'units'/f'{ds}_{seed}';effects={}
            for path in (0,1):
                folder=unit/f'path{path}';full=(load(folder/'branch_full_plus.npz')[f'h{c.fit_horizon}'].astype(float)-load(folder/'branch_full_minus.npz')[f'h{c.fit_horizon}'].astype(float))/2
                errors={}
                for H in (1,c.fit_horizon):
                    name=tag(H,max(c.fit_sizes),c.ranks[0]);a=load(folder/f'branch_{name}_plus.npz')[f'h{c.fit_horizon}'].astype(float);b=load(folder/f'branch_{name}_minus.npz')[f'h{c.fit_horizon}'].astype(float)
                    errors[H]=metrics(full,(a-b)/2,c.resolution_floor)['relative_prediction_error']
                effects[path]=errors[1]-errors[c.fit_horizon]
            rows.append(dict(seed=seed,fitted_improvement=effects[0],alternate_improvement=effects[1],interaction=effects[0]-effects[1]))
        interaction=exact_sign_positive([r['interaction'] for r in rows])
        # This secondary margin test concerns the median, not a mean-equivalence claim.
        margin=exact_sign_positive([c.transfer_margin-r['alternate_improvement'] for r in rows])
        results.append(dict(dataset=ds,independent_histories=len(rows),per_seed=rows,primary_interaction_sign_test=interaction,
            numerically_eligible=eligible,primary_pass=eligible and interaction['p_one_sided']<=c.dataset_sign_alpha,secondary_median_transfer_below_margin=margin,
            transfer_margin=c.transfer_margin,interpretation='Primary is fitted-minus-alternate matching gain. Margin test is secondary; no pooled branches.'))
    return results

def main(drive,local='/content/nexus14_run',session_hours=6,device_name='cuda',c=None,data_map=None,
         require_checkpoint=False,resume_from='latest',required_paths=(),backend=None):
    c=c or Config();device=torch.device(device_name);check(device.type!='cuda' or torch.cuda.is_available(),'Select an A100 GPU runtime')
    configure(device);env=environment(device)
    sources={f.relative_to(ROOT).as_posix():sha(f) for f in ROOT.rglob('*') if f.is_file() and f.suffix in ('.py','.json') and '__pycache__' not in f.parts}
    ident=dict(version=VERSION,config=json.loads(json.dumps(asdict(c))),environment=env,source_sha256=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest())
    execution_hash=ident['source_sha256'];prior_identity=Path(drive)/'IDENTITY.json'
    old=None
    if backend is not None:
        ids=[m for m in backend.list(backend.run_id) if m['name']=='IDENTITY.json']
        check(len(ids)==1,'Saved Stage14 identity missing or ambiguous; no new campaign will be created')
        old=backend.read_json(ids[0]['id'])
    elif prior_identity.exists():old=json.loads(prior_identity.read_text())
    if old is not None:
        if old.get('source_sha256')=='9daa2fc0181d7f3e373e1de3be7c03bb2a251a22f4e1edcceecf2153ffc1964a':
            env_diff={k:dict(saved=old.get('environment',{}).get(k),current=ident['environment'].get(k))
                      for k in set(old.get('environment',{}))|set(ident['environment'])
                      if old.get('environment',{}).get(k)!=ident['environment'].get(k)}
            if env_diff:print('Resume runtime differs from saved runtime:',json.dumps(env_diff,sort_keys=True),flush=True)
            check(all(old.get(k)==ident[k] for k in ('version','config','environment')),
                'Legacy R2 config/environment mismatch; refusing changed campaign')
            ident=old
            print('RESUMING EXISTING R2 with the documented checkpoint-only compatibility patch.',flush=True)
    from checkpoint15 import IncrementalCampaign,CheckpointBlocked
    camp=IncrementalCampaign(drive,local,ident,backend) if backend is not None else Campaign(drive,local,ident)
    camp.require_checkpoint=require_checkpoint;camp.resume_from=resume_from;camp.required_paths=tuple(required_paths)
    status=camp.activate()
    pulse=SessionClock(camp,session_hours)
    try:
        if status=='FINISHED':print('Verified finished campaign already exists.');return
        from resume14 import report as resume_report
        receipt=resume_report(camp,c) if status=='CHECKPOINT' else None
        meta=camp.local/'metadata';meta.mkdir(exist_ok=True)
        for f in ROOT.glob('*'):
            if f.is_file() and f.suffix in ('.py','.json'):shutil.copy2(f,meta/f.name)
        write_json(meta/'CONFIG.json',asdict(c));write_json(meta/'ENVIRONMENT.json',env)
        if receipt is not None:write_json(meta/'RESUME_RECEIPT.json',receipt)
        write_json(meta/'CHECKPOINT_POLICY.json',dict(interval_seconds=camp.checkpoint_seconds,session_soft_limit_hours=session_hours,
            additional_commits='Completed basis, each capture block, wider-sketch check, training and unit completion',
            execution_source_sha256=execution_hash,archive_identity_source_sha256=ident['source_sha256'],
            compatibility='Only the exact pre-patch R2 source identity, same scientific config and runtime environment.',
            working_basis='Column-wise resumable; float32 matrices only in checkpoint ZIPs; deleted after fitting.',
            compact_fallback_max_bytes=600*1024**2))
        if backend is not None:
            camp.transport_preflight()
            write_json(meta/'INCREMENTAL_POLICY.json',dict(interval_seconds=900,checkpoint_limit_bytes=None,
                project_write_ceiling_bytes=None,project_limit_bytes=None,account_reserve_bytes=0,
                chunk_raw_bytes=64*1024**2,recovery_points=2,verification='Server checksums and commit read-back; SHA256 for restored chunks/arrays',
                storage='Owned NEXUS names/descendants, retained revisions, Trash, temporary uploads, account quota',
                protected='Frozen results and unrelated files are never garbage-collected'))
            # Preserve a fresh operational baseline before starting new GPU work.
            if camp.current is None:camp.checkpoint(True)
        for ds in c.datasets:
            print('DATASET',ds,'— restoring saved work before new tasks',flush=True)
            data=data_map[ds] if data_map else data13.load(ds,str(Path(local).parent/'nexus14_data'),device,response_n=c.response_n)
            write_json(meta/f'{ds}_DATA.json',{k:data[k].tolist() if isinstance(data[k],np.ndarray) else data[k] for k in ('fingerprints','train_ids','cal_ids','response_ids','test_ids')})
            screens=[];start=time.monotonic()
            for seed in c.seeds:
                saved_screen=(camp.local/'units'/f'{ds}_{seed}'/'STABILITY14.json').exists()
                screens.append(preflight(data,seed,c,camp,pulse))
                elapsed=(time.monotonic()-start)/60
                print(ds,seed,'stability screen reused' if saved_screen else 'stability screen computed',
                      'PASS' if screens[-1]['passes'] else 'FAIL',flush=True)
            write_json(camp.local/'analysis'/f'{ds}_STABILITY.json',screens)
            if not all(q['passes'] for q in screens):
                write_json(camp.local/'analysis'/'GATE_FAILED.json',dict(dataset=ds,reason='Predeclared stable-continuation qualification failed; no failed seeds discarded, no expensive operator fitting in this cohort.'))
                # Preserve states for investigation rather than publishing a false complete result.
                camp.checkpoint(True)
                print('STABILITY GATE FAILED. Retain the verified recovery records and report this outcome. Do not tune and rerun this identity.',flush=True)
                return
            for index,seed in enumerate(c.seeds):
                if (camp.local/'units'/f'{ds}_{seed}'/'COMPLETE.json').exists():
                    print('SKIP VERIFIED COMPLETED HISTORY',ds,seed,flush=True);continue
                started=time.monotonic();run_unit(data,seed,c,camp,pulse)
                print('UNIT COMPLETE',ds,seed,'minutes this session',round((time.monotonic()-started)/60,1),flush=True)
            from audit13 import audit_all
            cohort=audit_all(camp.local,replace(c,datasets=(ds,)))
            write_json(camp.local/'analysis'/f'REPORT_{ds}.json',cohort)
            write_json(camp.local/'analysis'/f'REGISTERED_{ds}.json',registered_analysis(camp.local,replace(c,datasets=(ds,)),cohort))
            if ds==c.datasets[0] and len(c.datasets)>1:
                selected=camp.files(final=True)
                selected=[p for p in selected if not str(p.relative_to(camp.local)).startswith('units/') or str(p.relative_to(camp.local)).startswith(f'units/{ds}_')]
                temporary=pack(camp.local,camp.local/'cohort-local.zip',camp.identity,'COHORT',selected)
                published=camp.publish_export(temporary,'NEXUS_STAGE14_PRIMARY_COHORT.zip','COHORT')
                print('PRIMARY COHORT VERIFIED:',published.get('webViewLink',published.get('name')) if isinstance(published,dict) else published,'; can analyze this while replication continues.',flush=True)
            del data;gc.collect()
            if device.type=='cuda':torch.cuda.empty_cache()
        from audit13 import audit_all
        report=audit_all(camp.local,c);write_json(camp.local/'analysis'/'REPORT.json',report)
        check(report['complete'],'Incomplete campaign cannot be marked finished')
        write_json(camp.local/'analysis'/'REGISTERED14.json',registered_analysis(camp.local,c))
        if not report['scientific_primary_valid']:print('Completed branches but unresolved/failed numerical validity; consult REPORT.json.',flush=True)
        dest=camp.finish()
        camp.discard_export('NEXUS_STAGE14_PRIMARY_COHORT.zip','COHORT')
        print('FINISHED AND VERIFIED:',getattr(camp,'finished_location',dest),
              f'{getattr(camp,"finished_bytes",dest.stat().st_size)/1e6:.1f} MB',flush=True)
    except CheckpointBlocked as e:print('PAUSED:',str(e),flush=True)
    except PauseRun as e:
        try:camp.checkpoint(True)
        except CheckpointBlocked as blocked:print('PAUSED:',str(blocked),flush=True)
        print(str(e),flush=True)
    except BaseException:
        # An upload failure is already inside the checkpoint transaction. Do not
        # blindly attempt the same failing migration/upload a second time.
        import sys
        exc=sys.exc_info()[1];tb=exc.__traceback__
        checkpoint_in_progress=False
        while tb is not None:
            if tb.tb_frame.f_globals.get('__name__')=='checkpoint15' and tb.tb_frame.f_code.co_name in ('checkpoint','transport_preflight','finish','publish_export'):
                checkpoint_in_progress=True;break
            tb=tb.tb_next
        if checkpoint_in_progress:
            print('Checkpoint/transport transaction stopped. Prior verified recovery points are retained; rerun after resolving the displayed cause.',flush=True)
        else:
            try:camp.checkpoint(True)
            except BaseException as e:print('Checkpoint failed:',type(e).__name__,str(e),flush=True)
        raise
    finally:camp.lease.release()
