"""NEXUS Stage11: cross-architecture natural-data causal-control replication."""
import copy,gc,hashlib,io,json,math,os,platform,sys,time,shutil
from dataclasses import dataclass,asdict
from pathlib import Path
import numpy as np
import torch,torchvision
from torch import nn
from torch.nn import functional as F
from torchvision.datasets import CIFAR10,CIFAR100
from models import build
from operators import Operator,estimate,independent_trace,subspace_distance,flat,functional_logits,rademacher
from archive_io import Campaign,write_json,sha,check
from control_math import RANKS,capture,causal_curves,bootstrap,center
VERSION='NEXUS-STAGE11-CAUSAL-CONTROL-REPLICATION-R1'

@dataclass(frozen=True)
class Config:
    datasets:tuple=('CIFAR10','CIFAR100')
    architectures:tuple=('ResNet18GN','ViTSmall')
    models_per_cell:int=4
    total_steps_cifar10:int=8000
    total_steps_cifar100:int=12000
    cut_fractions:tuple=(.5,1.)
    donor_fraction:float=.7
    batch_size:int=128
    calibration_n:int=8192
    first_batch_n:int=256
    fit_small_n:int=128
    fit_large_n:int=512
    independent_anchor_n:int=512
    response_n:int=128
    fit_small_probes:int=64
    fit_large_probes:int=128
    trace_probes:int=128
    max_rank:int=64
    intervention_ranks:tuple=(8,16,64)
    primary_rank:int=16
    primary_horizon:int=16
    future_paths:tuple=(0,1)
    future_steps:int=128
    horizons:tuple=(0,1,4,16,64,128)
    relative_displacement:float=.002
    lr:float=.0012
    min_lr_fraction:float=.1
    warmup_steps:int=500
    beta1:float=.9
    beta2:float=.999
    eps:float=1e-8
    weight_decay:float=.01
    gradient_clip:float=1.
    future_effect_floor:float=2e-5
    session_hours:float=8.
    bootstrap_draws:int=10000
    capture_budget_difference_max:float=.05
    angle_budget_difference_max:float=.25
    fd_error_max:float=.10

def seed(*parts):return int(hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:8],16)


def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)


def save_pt(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
    with open(tmp,'wb') as f:torch.save(payload,f);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)


def load_pt(path):return torch.load(path,map_location='cpu',weights_only=True)


def cpu(x):
    if isinstance(x,torch.Tensor):return x.detach().cpu().clone()
    if isinstance(x,dict):return {k:cpu(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return type(x)(cpu(v) for v in x)
    return x


def npz(path,arrays):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
    with open(tmp,'wb') as f:np.savez_compressed(f,**arrays);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)


def configure(device):
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True);torch.set_float32_matmul_precision('highest')
    if device.type=='cuda':
        torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
        torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False


def environment(device):
    return {'python':sys.version,'torch':str(torch.__version__),'torchvision':str(torchvision.__version__),
            'numpy':str(np.__version__),'device':str(device),'gpu':torch.cuda.get_device_name(device) if device.type=='cuda' else None,
            'cuda':torch.version.cuda,'cudnn':torch.backends.cudnn.version(),'cpu_threads':torch.get_num_threads(),
            'deterministic':torch.are_deterministic_algorithms_enabled(),'tf32':False}


def optimizer(model,cfg):return torch.optim.AdamW(model.parameters(),lr=cfg.lr,betas=(cfg.beta1,cfg.beta2),eps=cfg.eps,weight_decay=cfg.weight_decay,foreach=False,fused=False)


def snapshot(model,opt):return {'model':cpu(model.state_dict()),'optimizer':cpu(opt.state_dict())}


def vectors(model,opt):
    theta=[];m=[];v=[];clocks=[];layout=[]
    for name,p in model.named_parameters():
        state=opt.state[p];theta.append(p.detach().cpu().reshape(-1).numpy());m.append(state['exp_avg'].cpu().reshape(-1).numpy());v.append(state['exp_avg_sq'].cpu().reshape(-1).numpy())
        clocks.append(int(state['step'].item()));layout.append({'name':name,'shape':list(p.shape),'size':p.numel()})
    check(len(set(clocks))==1,'Mixed optimizer clocks are unsupported')
    return np.concatenate(theta).copy(),np.concatenate(m).copy(),np.concatenate(v).copy(),clocks[0],layout


def install(model,opt,m,v,t):
    at=0
    for p in model.parameters():
        n=p.numel();s=opt.state[p]
        s['exp_avg'].copy_(torch.as_tensor(m[at:at+n],device=p.device,dtype=p.dtype).reshape_as(p))
        s['exp_avg_sq'].copy_(torch.as_tensor(v[at:at+n],device=p.device,dtype=p.dtype).reshape_as(p))
        s['step'].fill_(t);at+=n
    check(at==len(m)==len(v),'Parameter layout differs')


@torch.no_grad()
def logits(model,data,ids):
    model.eval();return torch.cat([model(data['TX'][torch.as_tensor(ids[i:i+256],device=data['X'].device)]).cpu() for i in range(0,len(ids),256)]).numpy()


def metrics(z,y):
    z=torch.from_numpy(z).double();y=torch.as_tensor(y)
    return {'accuracy':float((z.argmax(1)==y).double().mean()),'loss':float(F.cross_entropy(z,y))}

def binding():
    root=Path(__file__).parent
    return {n:sha(root/n) for n in ('runner.py','models.py','operators.py','archive_io.py','control_math.py','audit.py','PROTOCOL.json','PARENT_EVIDENCE.json','RELATED_WORK.md','README.md')}

def total_steps(dataset,cfg):return cfg.total_steps_cifar10 if dataset=='CIFAR10' else cfg.total_steps_cifar100
def classes(dataset):return 10 if dataset=='CIFAR10' else 100
def model_seed(dataset,architecture,index):return 11000+1000*(dataset=='CIFAR100')+100*(architecture=='ViTSmall')+index
def model_id(dataset,architecture,index):return f'{dataset}_{architecture}_{model_seed(dataset,architecture,index)}'
def case_id(dataset,architecture,index,cut):return f'{model_id(dataset,architecture,index)}_t{cut}'
def cuts(dataset,cfg):return tuple(int(total_steps(dataset,cfg)*f) for f in cfg.cut_fractions)
def planned(cfg):return [case_id(d,a,i,t) for d in cfg.datasets for a in cfg.architectures for i in range(cfg.models_per_cell) for t in cuts(d,cfg)]

def model_for(dataset,architecture,s,device):
    with torch.random.fork_rng(devices=[]):torch.manual_seed(seed('model',dataset,architecture,s));m=build(architecture,classes(dataset))
    return m.to(device)
def restore(dataset,architecture,s,device,cfg,state):
    m=model_for(dataset,architecture,s,device);m.load_state_dict(copy.deepcopy(state['model']));o=optimizer(m,cfg);o.load_state_dict(copy.deepcopy(state['optimizer']));return m,o
def lr_at(step,total,cfg):
    if step<cfg.warmup_steps:return cfg.lr*(step+1)/cfg.warmup_steps
    u=min(1.,max(0.,(step-cfg.warmup_steps)/max(total-cfg.warmup_steps,1)))
    return cfg.lr*(cfg.min_lr_fraction+(1-cfg.min_lr_fraction)*.5*(1+math.cos(math.pi*u)))
def set_lr(opt,rate):
    for group in opt.param_groups:group['lr']=rate

def train_step(model,opt,x,y,cfg):
    model.train();opt.zero_grad(set_to_none=True);loss=F.cross_entropy(model(x),y);loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(),cfg.gradient_clip,error_if_nonfinite=True)
    opt.step();return loss.detach()
def gradient(model,x,y,cfg):
    model.train();model.zero_grad(set_to_none=True);F.cross_entropy(model(x),y).backward()
    norm=torch.nn.utils.clip_grad_norm_(model.parameters(),cfg.gradient_clip,error_if_nonfinite=True)
    return np.concatenate([p.grad.detach().cpu().reshape(-1).numpy() for p in model.parameters()]).copy(),float(norm)

def balanced(labels,ids,n,rng,counts):
    out=[];labels=np.asarray(labels);ids=np.asarray(ids)
    for c in range(counts):
        eligible=ids[labels[ids]==c];need=n//counts+(c<n%counts)
        check(len(eligible)>=need,'Insufficient anchor class coverage');out.extend(rng.permutation(eligible)[:need].tolist())
    # Shuffle so a prefix does not accidentally contain only the first classes.
    return rng.permutation(np.asarray(out,dtype=np.int64))

def dataset_load(name,root,device,cfg):
    cls=CIFAR10 if name=='CIFAR10' else CIFAR100
    ds=cls(root,train=True,download=True);test=cls(root,train=False,download=True)
    raw=np.asarray(ds.data);traw=np.asarray(test.data);y=np.asarray(ds.targets,dtype=np.int64);ty=np.asarray(test.targets,dtype=np.int64)
    fingerprints={k:hashlib.sha256(a.tobytes()).hexdigest() for k,a in {'train_images':raw,'train_labels':y,'test_images':traw,'test_labels':ty}.items()}
    def convert(a):
        x=torch.as_tensor(a.copy(),device=device,dtype=torch.float32).permute(0,3,1,2).contiguous()/255.
        mean=[.4914,.4822,.4465] if name=='CIFAR10' else [.5071,.4867,.4408]
        std=[.247,.243,.261] if name=='CIFAR10' else [.2675,.2565,.2761]
        return (x-torch.tensor(mean,device=device)[None,:,None,None])/torch.tensor(std,device=device)[None,:,None,None]
    rng=np.random.default_rng(seed('roles',name));cal_ids=balanced(y,np.arange(len(y)),cfg.calibration_n,rng,classes(name))
    train_ids=np.setdiff1d(np.arange(len(y)),cal_ids);response_ids=balanced(ty,np.arange(len(ty)),cfg.response_n,rng,classes(name))
    test_ids=np.setdiff1d(np.arange(len(ty)),response_ids)
    return {'name':name,'X':convert(raw),'Y':torch.tensor(y,device=device),'TX':convert(traw),'TY':torch.tensor(ty,device=device),
       'train_ids':train_ids,'cal_ids':cal_ids,'response_ids':response_ids,'test_ids':test_ids,'fingerprints':fingerprints}

def batch(data,s,step,cfg,path=-1):
    g=torch.Generator().manual_seed(seed('batch',data['name'],s,path,step));ix=torch.randint(len(data['train_ids']),(cfg.batch_size,),generator=g).numpy()
    ids=torch.tensor(data['train_ids'][ix],device=data['X'].device);x=data['X'][ids];y=data['Y'][ids]
    offsets=torch.randint(0,9,(len(x),2),generator=g).to(x.device);flip=(torch.rand(len(x),generator=g)>.5).to(x.device)
    padded=F.pad(x,(4,4,4,4),mode='reflect').permute(0,2,3,1)
    rows=torch.arange(len(x),device=x.device)[:,None,None]
    h=torch.arange(32,device=x.device)[None,:,None]+offsets[:,0,None,None];w=torch.arange(32,device=x.device)[None,None,:]+offsets[:,1,None,None]
    x=padded[rows,h,w].permute(0,3,1,2).contiguous();return torch.where(flip[:,None,None,None],x.flip(-1),x),y

def state_digest(state):
    # Scientific identity of tensor bytes, independent of torch.save container bytes.
    h=hashlib.sha256()
    def visit(x):
        if isinstance(x,torch.Tensor):
            y=x.detach().cpu().contiguous();h.update(str((str(y.dtype),tuple(y.shape))).encode());h.update(y.numpy().tobytes())
        elif isinstance(x,dict):
            for k in sorted(x,key=str):h.update(str(k).encode());visit(x[k])
        elif isinstance(x,(list,tuple)):
            for y in x:visit(y)
        else:h.update(str(x).encode())
    visit(state);return h.hexdigest()

def reference_to(store,data,architecture,index,target,cfg,device,guard):
    s=model_seed(data['name'],architecture,index);mid=model_id(data['name'],architecture,index);p=store.local/'active'/'reference.pt'
    if p.exists():
        saved=load_pt(p)
        if saved['model_id']!=mid:saved=None
    else:saved=None
    if saved is None:
        model=model_for(data['name'],architecture,s,device);opt=optimizer(model,cfg);done=0;donor=None
        initial=state_digest(model.state_dict())
    else:
        model,opt=restore(data['name'],architecture,s,device,cfg,saved['snapshot']);done=saved['completed'];donor=saved['donor'];initial=saved['initial_model_digest']
    check(done<=target,'Reference state advanced past an unfinished checkpoint')
    donor_at=int(target*cfg.donor_fraction);total=total_steps(data['name'],cfg)
    for step in range(done,target):
        guard();set_lr(opt,lr_at(step,total,cfg));x,y=batch(data,s,step,cfg);loss=train_step(model,opt,x,y,cfg)
        if step+1==donor_at:donor=torch.cat([opt.state[q]['exp_avg'].detach().cpu().reshape(-1) for q in model.parameters()]).clone()
        if (step+1)%500==0 or step+1==target:
            saved={'model_id':mid,'snapshot':snapshot(model,opt),'completed':step+1,'donor':donor,'initial_model_digest':initial,'donor_at':donor_at}
            save_pt(p,saved);store.checkpoint()
            print(mid,'reference',step+1,'/',total,'loss',round(float(loss),4),flush=True)
    if done==target:
        saved={'model_id':mid,'snapshot':snapshot(model,opt),'completed':target,'donor':donor,'initial_model_digest':initial,'donor_at':donor_at}
    check(donor is not None,'Historical donor checkpoint missing')
    if not (store.drive/'CHECKPOINT.zip').exists():store.checkpoint(force=True)
    del model,opt;return saved

def readonly_roles(data,s,cfg):
    rng=np.random.default_rng(seed('operator_roles',data['name'],s));labels=data['Y'].cpu().numpy();count=classes(data['name'])
    large=balanced(labels,data['cal_ids'],cfg.fit_large_n,rng,count)
    small=balanced(labels,large,cfg.fit_small_n,rng,count)
    remain=np.setdiff1d(data['cal_ids'],large);independent=balanced(labels,remain,cfg.independent_anchor_n,rng,count)
    first=rng.permutation(np.setdiff1d(remain,independent))[:cfg.first_batch_n]
    check(not set(large)&set(independent) and not set(first)&(set(large)|set(independent)),'Calibration role overlap')
    return small,large,independent,first

def geometry(store,folder,data,architecture,index,saved,cfg,device,guard):
    jp=folder/'geometry.json';dp=folder/'directions.pt'
    if jp.exists() and dp.exists():return json.loads(jp.read_text()),load_pt(dp)
    s=model_seed(data['name'],architecture,index);model,opt=restore(data['name'],architecture,s,device,cfg,saved['snapshot'])
    theta,m,v,t,layout=vectors(model,opt);h=torch.from_numpy(m).to(device)-saved['donor'].to(device);hn=torch.linalg.vector_norm(h)
    check(float(hn)>0,'Zero historical memory direction');h=(h/hn).detach();mnorm=float(np.linalg.norm(m.astype('float64')))
    small_ids,large_ids,ind_ids,first_ids=readonly_roles(data,s+saved['completed'],cfg)
    gx=data['X'][torch.tensor(first_ids,device=device)];gy=data['Y'][torch.tensor(first_ids,device=device)]
    g,unclipped_norm=gradient(model,gx,gy,cfg);rate=lr_at(t,total_steps(data['name'],cfg),cfg);set_lr(opt,rate);train_step(model,opt,gx,gy,cfg)
    nxt=flat(model);den=np.sqrt((cfg.beta2*v.astype('float64')+(1-cfg.beta2)*g.astype('float64')**2)/(1-cfg.beta2**(t+1)))+cfg.eps
    D=torch.tensor(-rate*cfg.beta1/((1-cfg.beta1**(t+1))*den),device=device,dtype=torch.float32)
    candidates={};fit_records={};arrays={}
    specs=[('anchor128_q64',small_ids,cfg.fit_small_probes,1),('anchor512_q64',large_ids,cfg.fit_small_probes,1),('anchor512_q128',large_ids,cfg.fit_large_probes,2)]
    for name,ids,q,power in specs:
        print(folder.name,'fitting',name,flush=True);op=Operator(model,nxt,D,data['X'][torch.tensor(ids,device=device)],guard)
        U,rec=estimate(op,q,power,seed('sketch',data['name'],architecture,s,t,name),cfg.max_rank);op.close();del op
        candidates[name]=U;fit_records[name]={k:v for k,v in rec.items() if not isinstance(v,np.ndarray)}
        for key,value in rec.items():
            if isinstance(value,np.ndarray):arrays[f'{name}_{key}']=value
    main=candidates['anchor512_q128'];dirs={'full':h};alignment={}
    for k in cfg.intervention_ranks:
        n=min(k,main.shape[1]);coef=main[:,:n].double().T@h.double();p=(main[:,:n].double()@coef).float()
        dirs[f'parallel{k}']=p;alignment[str(k)]={'actual_rank':n,'history_alignment':float(torch.dot(coef,coef)),'parallel_norm':float(torch.linalg.vector_norm(p))}
        arrays[f'history_coefficients_k{k}']=coef.cpu().numpy()
    rng=np.random.default_rng(seed('controls',data['name'],architecture,s,t));hc=h.cpu().numpy().astype('float64');at=0;segments=[]
    for item in layout:segments.append((at,at+item['size']));at+=item['size']
    controls={}
    for j in range(8):
        z=np.empty_like(hc)
        for a,b in segments:
            r=rng.normal(size=b-a);z[a:b]=r/max(np.linalg.norm(r),1e-30)*np.linalg.norm(hc[a:b])
        controls[f'tensor_random{j}']=torch.tensor(z,device=device,dtype=torch.float32)
    z=hc*rng.choice([-1.,1.],len(hc));controls['sign_shuffle']=torch.tensor(z,device=device,dtype=torch.float32)
    z=hc.copy()
    for a,b in segments:z[a:b]=rng.permutation(z[a:b])
    controls['within_tensor_permutation']=torch.tensor(z,device=device,dtype=torch.float32)
    gg=torch.from_numpy(g).to(device);controls['current_gradient']=gg/torch.linalg.vector_norm(gg)
    pg=g.astype('float64')/(np.sqrt(v.astype('float64')/(1-cfg.beta2**t))+cfg.eps);pg/=max(np.linalg.norm(pg),1e-30)
    controls['preconditioned_gradient']=torch.tensor(pg,device=device,dtype=torch.float32)
    dirs['tensor_random']=controls['tensor_random0'];dirs['gradient']=controls['current_gradient']
    op=Operator(model,nxt,D,data['X'][torch.tensor(ind_ids,device=device)],guard)
    trace,coeff=independent_trace(op,candidates,cfg.trace_probes,seed('independent_trace',data['name'],architecture,s,t))
    arrays['trace_norms']=trace;curves={}
    for name,c in coeff.items():arrays[f'{name}_trace_coefficients']=c;curves[name]=capture(trace,c)
    linear={}
    for name,d in dirs.items():linear[name]=op.jvp(d).cpu().numpy();arrays[f'linear_{name}']=linear[name]
    for k in cfg.intervention_ranks:arrays[f'linear_remainder{k}']=op.jvp(h-dirs[f'parallel{k}']).cpu().numpy()
    potency={}
    for name,d in controls.items():
        z=op.jvp(d).cpu().numpy();arrays[f'control_{name}']=z
        potency[name]={'normalized_logit_gain':float(np.linalg.norm(z)),'history_gain_ratio':float(np.linalg.norm(linear['full'])/max(np.linalg.norm(z),1e-30))}
    # Parameter-energy partition: an explanatory diagnostic chosen from v, never responses.
    variance_cut=np.quantile(v,.25);mask=torch.tensor(v<=variance_cut,device=device)
    low=h*mask;arrays['linear_history_low_variance_quartile']=op.jvp(low).cpu().numpy()
    arrays['linear_history_other_variance']=op.jvp(h-low).cpu().numpy()
    # Actual backend adjoint agreement, scaled against norm bounds to avoid cancellation.
    r=rademacher(op.outputs,seed('adjoint',s,t),device);u=controls['tensor_random0'];ju=op.jvp(u);jr=op.vjp(r)
    left=float(torch.dot(ju.double(),r.double()));right=float(torch.dot(u.double(),jr.double()))
    denom_check=float(torch.linalg.vector_norm(ju.double())*torch.linalg.vector_norm(r.double())+torch.linalg.vector_norm(jr.double())*torch.linalg.vector_norm(u.double()))
    adjoint=abs(left-right)/max(denom_check,1e-30);op.close();del op
    distances={str(k):subspace_distance(candidates['anchor512_q64'],main,k) for k in cfg.intervention_ranks}
    anchor_distances={str(k):subspace_distance(candidates['anchor128_q64'],candidates['anchor512_q64'],k) for k in cfg.intervention_ranks}
    for k in cfg.intervention_ranks:
        arrays[f'budget_overlap_k{k}']=(candidates['anchor512_q64'][:,:min(k,candidates['anchor512_q64'].shape[1],main.shape[1])].double().T@main[:,:min(k,candidates['anchor512_q64'].shape[1],main.shape[1])].double()).cpu().numpy()
        n=min(k,candidates['anchor128_q64'].shape[1],candidates['anchor512_q64'].shape[1])
        arrays[f'anchor_overlap_k{k}']=(candidates['anchor128_q64'][:,:n].double().T@candidates['anchor512_q64'][:,:n].double()).cpu().numpy()
    scale=cfg.relative_displacement*mnorm
    # Two predetermined central finite-surgery checks against actual torch.optim.AdamW.
    fd_ids=data['response_ids'][np.linspace(0,len(data['response_ids'])-1,min(16,len(data['response_ids'])),dtype=int)]
    xfd=data['TX'][torch.tensor(fd_ids,device=device)];fdop=Operator(model,nxt,D,xfd,guard);prediction=fdop.jvp(h).cpu().numpy();fdop.close()
    arrays['fd_prediction']=prediction;fd={}
    for factor in (.5,1.):
        responses=[]
        for sign in (-1.,1.):
            md,oo=restore(data['name'],architecture,s,device,cfg,saved['snapshot']);install(md,oo,(m.astype('float64')+sign*factor*scale*hc).astype('float32'),v,t)
            set_lr(oo,rate);train_step(md,oo,gx,gy,cfg)
            with torch.no_grad():z=md(xfd).cpu().numpy()
            arrays[f'fd_factor{factor}_sign{sign}']=z;responses.append(z);del md,oo
        actual=(center(responses[1])-center(responses[0])).reshape(-1)/(2*factor*scale*math.sqrt(responses[0].size))
        fd[str(factor)]={'relative_error':float(np.linalg.norm(actual-prediction)/max(np.linalg.norm(prediction),1e-30))}
    capture_difference={str(k):abs(next(r['paired_hutchinson_capture'] for r in curves['anchor512_q128'] if r['k']==k)-next(r['paired_hutchinson_capture'] for r in curves['anchor512_q64'] if r['k']==k)) for k in cfg.intervention_ranks}
    variance_summary={'low_variance_coordinate_fraction':float(np.mean(v<=variance_cut)),'variance_quartile':float(variance_cut)}
    rec={'unit':folder.name,'clock':t,'parameter_count':len(m),'snapshot_digest':state_digest(saved['snapshot']),
      'historical_donor_digest':state_digest(saved['donor']),'initial_model_digest':saved['initial_model_digest'],
      'fitted_candidates':fit_records,'capture_curves':curves,'budget_distances':distances,'anchor_distances':anchor_distances,'capture_budget_difference':capture_difference,
      'history_alignment':alignment,'matched_controls':potency,'variance_diagnostic':variance_summary,'adjoint_error':adjoint,
      'finite_difference':fd,'displacement':scale,'recipient_m_norm':mnorm,'donor_history_norm':float(hn),
      'first_gradient_unclipped_norm':unclipped_norm,'first_lr':rate,'first_ids':first_ids.tolist(),
      'fit_small_ids':small_ids.tolist(),'fit_large_ids':large_ids.tolist(),'independent_ids':ind_ids.tolist(),
      'basis_uses_history_or_future':False,'natural_history_reachability_claimed':False}
    npz(folder/'geometry_raw.npz',arrays);write_json(jp,rec)
    directions={'vectors':{name:d.detach().cpu().clone() for name,d in dirs.items()},'first_ids':torch.from_numpy(first_ids),'scale':scale}
    save_pt(dp,directions);del candidates,main,model,opt;gc.collect()
    if device.type=='cuda':torch.cuda.empty_cache()
    store.checkpoint();return rec,directions

def branch_labels(cfg):
    out=['baseline','full_plus','full_minus']
    for k in cfg.intervention_ranks:
        for component in ('parallel','remainder'):
            out.extend(f'{component}{k}_{sign}' for sign in ('plus','minus'))
    out.extend(f'{name}_{sign}' for name in ('gradient','tensor_random') for sign in ('plus','minus'))
    return out

def branch_direction(label,directions):
    if label=='baseline':return None,0
    name,sign=label.rsplit('_',1)
    if name.startswith('remainder'):
        k=int(name[len('remainder'):]);d=directions['vectors']['full']-directions['vectors'][f'parallel{k}']
    else:d=directions['vectors'][name]
    return d.numpy().astype('float64'),1 if sign=='plus' else -1

def evaluate_test(model,data):
    z=logits(model,data,data['test_ids']);y=data['TY'][torch.as_tensor(data['test_ids'],device=data['X'].device)].cpu().numpy()
    zt=torch.from_numpy(z).double()
    return {'test_prediction':z.argmax(1).astype('int16'),'test_nll':F.cross_entropy(zt,torch.from_numpy(y),reduction='none').numpy(),
            'test_labels':y.astype('int16')}

def response(model,data):return logits(model,data,data['response_ids'])

def continue_branch(store,folder,data,architecture,index,saved,directions,label,path,cfg,device,guard):
    tag=f'path{path}_{label}';jp=folder/(tag+'.json');rp=folder/(tag+'.npz');progress=folder/'branch.pt'
    if jp.exists():
        record=json.loads(jp.read_text());check(rp.exists() and sha(rp)==record['raw_sha256'],'Committed future payload corrupted')
        return record
    s=model_seed(data['name'],architecture,index);t=saved['completed'];done=0;arrays={};record=None
    if progress.exists():
        p=load_pt(progress)
        if p['tag']==tag:
            model,opt=restore(data['name'],architecture,s,device,cfg,p['snapshot']);done=p['completed'];record=p['record']
            arrays={k:v.numpy() for k,v in p['arrays'].items()}
        else:model=None
    else:model=None
    if model is None:
        model,opt=restore(data['name'],architecture,s,device,cfg,saved['snapshot']);theta,m,v,clock,_=vectors(model,opt)
        d,sign=branch_direction(label,directions);desired=np.zeros_like(m,dtype='float64') if d is None else sign*directions['scale']*d
        install(model,opt,(m.astype('float64')+desired).astype('float32'),v,clock)
        theta2,m2,v2,t2,_=vectors(model,opt);actual=m2.astype('float64')-m.astype('float64')
        fixed=bool(np.array_equal(theta,theta2) and np.array_equal(v,v2) and clock==t2)
        check(fixed,'Moment surgery changed weights, variance or clock')
        record={'label':label,'path':path,'unit':folder.name,'recipient_digest':state_digest(saved['snapshot']),
                'weights_variance_clock_unchanged':fixed,'post_surgery_snapshot_digest':state_digest(snapshot(model,opt)),
                'requested_delta_norm':float(np.linalg.norm(desired)),'actual_delta_norm':float(np.linalg.norm(actual)),
                'rounding_relative_error':float(np.linalg.norm(actual-desired)/max(np.linalg.norm(desired),1e-30)),
                'reference_clock':t,'future_steps':cfg.future_steps,'horizons':list(cfg.horizons)}
        arrays['h0']=response(model,data)
    def commit_progress():
        save_pt(progress,{'tag':tag,'completed':done,'snapshot':snapshot(model,opt),'record':record,
                          'arrays':{k:torch.from_numpy(np.asarray(v)) for k,v in arrays.items()}})
        store.checkpoint()
    if done==0:commit_progress()
    for h in range(done+1,cfg.future_steps+1):
        guard();set_lr(opt,lr_at(t+h-1,total_steps(data['name'],cfg),cfg))
        if h==1:
            ids=directions['first_ids'].to(device);x,y=data['X'][ids],data['Y'][ids]
        else:x,y=batch(data,s,t+h-2,cfg,path=path)
        train_step(model,opt,x,y,cfg);done=h
        if h in cfg.horizons:arrays[f'h{h}']=response(model,data)
        if h%16==0 or h==cfg.future_steps:commit_progress()
    arrays.update(evaluate_test(model,data));npz(rp,arrays);record['raw_sha256']=sha(rp)
    record['learning']={'accuracy':float(np.mean(arrays['test_prediction']==arrays['test_labels'])),
                        'loss':float(np.mean(arrays['test_nll']))}
    write_json(jp,record)
    if progress.exists():progress.unlink()
    del model,opt;gc.collect()
    print(folder.name,tag,'completed',flush=True);return record

def run_case(store,data,architecture,index,saved,cfg,device,guard):
    import audit
    folder=store.local/'units'/case_id(data['name'],architecture,index,saved['completed']);folder.mkdir(parents=True,exist_ok=True)
    if (folder/'result.json').exists():return audit.audit_case(folder,asdict(cfg))
    start=time.monotonic();g,dirs=geometry(store,folder,data,architecture,index,saved,cfg,device,guard)
    if not (folder/'reference_learning.npz').exists():
        model,opt=restore(data['name'],architecture,model_seed(data['name'],architecture,index),device,cfg,saved['snapshot'])
        npz(folder/'reference_learning.npz',evaluate_test(model,data));del model,opt
    for path in cfg.future_paths:
        for label in branch_labels(cfg):continue_branch(store,folder,data,architecture,index,saved,dirs,label,path,cfg,device,guard)
    result=audit.audit_case(folder,asdict(cfg));result['identity']={'dataset':data['name'],'architecture':architecture,
       'model_seed':model_seed(data['name'],architecture,index),'cut':saved['completed'],'late':saved['completed']==total_steps(data['name'],cfg)}
    result['seconds_case_this_session']=time.monotonic()-start;write_json(folder/'result.json',result)
    audit.audit_case(folder,asdict(cfg))
    for p in folder.glob('*.pt'):p.unlink()
    del dirs;gc.collect()
    print('CASE COMPLETE',folder.name,'seconds this session',round(result['seconds_case_this_session'],1),flush=True)
    return result

def qualify(device,cfg):
    # Qualify the installed backend, including forward-mode AD on both real backbones.
    records={}
    for arch in cfg.architectures:
        md=model_for('CIFAR10',arch,99001,device);oo=optimizer(md,cfg)
        generator=torch.Generator().manual_seed(987);x=torch.randn(2,3,32,32,generator=generator).to(device);y=torch.tensor([1,2],device=device)
        train_step(md,oo,x,y,cfg);saved=snapshot(md,oo);theta,m,v,t,_=vectors(md,oo)
        g,_=gradient(md,x,y,cfg);rate=cfg.lr;set_lr(oo,rate);train_step(md,oo,x,y,cfg);nxt=flat(md)
        denom=np.sqrt((cfg.beta2*v.astype('float64')+(1-cfg.beta2)*g.astype('float64')**2)/(1-cfg.beta2**(t+1)))+cfg.eps
        D=torch.tensor(-rate*cfg.beta1/((1-cfg.beta1**(t+1))*denom),device=device,dtype=torch.float32)
        op=Operator(md,nxt,D,x,lambda:None);u=rademacher(len(theta),456,device);u/=torch.linalg.vector_norm(u);r=rademacher(op.outputs,457,device)
        ju=op.jvp(u);jr=op.vjp(r);left=float(torch.dot(ju.double(),r.double()));right=float(torch.dot(u.double(),jr.double()))
        err=abs(left-right)/max(float(torch.linalg.vector_norm(ju.double())*torch.linalg.vector_norm(r.double())+torch.linalg.vector_norm(jr.double())),1e-30)
        check(np.isfinite(err) and err<2e-5,'Installed backend adjoint check failed: '+arch);op.close()
        md2,oo2=restore('CIFAR10',arch,99001,device,cfg,saved);set_lr(oo2,rate);train_step(md2,oo2,x,y,cfg)
        check(state_digest(snapshot(md,oo))==state_digest(snapshot(md2,oo2)),'Serialized optimizer continuation differs')
        records[arch]={'parameters':len(theta),'adjoint_relative_error':err,'serialized_continuation_exact':True}
        del md,oo,md2,oo2,op;gc.collect()
        if device.type=='cuda':torch.cuda.empty_cache()
    return records

def run(drive_root,local_root,dataset_root='/content/nexus_stage10_dataset_cache',cfg=None,device=None,loader=None,qualification=True):
    import audit
    cfg=cfg or Config();device=torch.device(device or 'cuda');configure(device)
    check(cfg.primary_horizon in cfg.horizons and max(cfg.horizons)==cfg.future_steps and 0 in cfg.horizons,'Invalid planned horizons')
    check(cfg.primary_rank in cfg.intervention_ranks,'Primary rank missing')
    if device.type=='cuda':
        check(torch.cuda.is_available(),'Select a GPU runtime')
        check(torch.cuda.get_device_properties(device).total_memory>=35*1024**3,'This fixed protocol requires an A100-class GPU with at least 35 GiB; stopping before training')
    identity={'version':VERSION,'config':json.loads(canon(asdict(cfg))),'source':binding(),'environment':environment(device)}
    store=Campaign(drive_root,local_root,identity);status=store.activate();start=time.monotonic()
    def guard():
        store.pulse()
        if time.monotonic()-start>cfg.session_hours*3600:raise TimeoutError('Session budget reached; resume this same notebook to continue the frozen campaign')
    try:
        if status=='FINISHED':
            summary=audit.summarize(store.local,asdict(cfg));return summary,Path(drive_root)/'NEXUS_STAGE11_FINISHED.zip'
        meta=store.local/'metadata';meta.mkdir(parents=True,exist_ok=True)
        for name in binding():shutil.copyfile(Path(__file__).parent/name,meta/name)
        for name in ('VALIDATION.json','CPU_VALIDATION.json','REAL_BACKBONE_ESTIMATOR_VALIDATION.json','test_validation.py','test_storage.py'):
            if (Path(__file__).parent/name).exists():shutil.copyfile(Path(__file__).parent/name,meta/name)
        write_json(meta/'IDENTITY.json',identity)
        if qualification:
            q=qualify(device,cfg);write_json(meta/'BACKEND_QUALIFICATION.json',q);print('Backend qualified:',q,flush=True)
        loader=loader or dataset_load;timings=[]
        for dataset in cfg.datasets:
            data=loader(dataset,dataset_root,device,cfg);data_identity={'fingerprints':data['fingerprints'],
              'train_ids':data['train_ids'].tolist(),'calibration_ids':data['cal_ids'].tolist(),'response_test_ids':data['response_ids'].tolist(),
              'evaluation_test_ids':data['test_ids'].tolist()}
            data_path=meta/(dataset+'_DATA.json')
            if data_path.exists():check(json.loads(data_path.read_text())==data_identity,'Dataset bytes or role assignments changed across sessions')
            else:write_json(data_path,data_identity)
            for architecture in cfg.architectures:
                for index in range(cfg.models_per_cell):
                    names=[case_id(dataset,architecture,index,t) for t in cuts(dataset,cfg)]
                    if all((store.local/'units'/name/'result.json').exists() for name in names):
                        for name in names:audit.audit_case(store.local/'units'/name,asdict(cfg))
                        continue
                    model_start=time.monotonic()
                    for t in cuts(dataset,cfg):
                        folder=store.local/'units'/case_id(dataset,architecture,index,t)
                        if (folder/'result.json').exists():audit.audit_case(folder,asdict(cfg));continue
                        saved=reference_to(store,data,architecture,index,t,cfg,device,guard)
                        run_case(store,data,architecture,index,saved,cfg,device,guard);del saved
                    store.checkpoint(force=True);elapsed=time.monotonic()-model_start;timings.append(elapsed)
                    completed=sum((store.local/'units'/name/'result.json').exists() for name in planned(cfg));remaining=(len(planned(cfg))-completed)/len(cfg.cut_fractions)
                    print('Measured model block seconds:',round(elapsed,1),'| rough remaining hours from this session:',round(np.median(timings)*remaining/3600,2),
                          '| includes archive time; resumed blocks underestimate a full block',flush=True)
            del data;gc.collect()
            if device.type=='cuda':torch.cuda.empty_cache()
        summary=audit.summarize(store.local,asdict(cfg));write_json(store.local/'analysis'/'SUMMARY.json',summary)
        finished=store.finish();return summary,finished
    except BaseException:
        # Publish the latest complete local progress; partially fitted operators are repeated.
        store.checkpoint(force=True);raise
    finally:store.lease.release()
