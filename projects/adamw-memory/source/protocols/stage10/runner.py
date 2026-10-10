"""NEXUS Stage10: exact finite-anchor control-spectrum audit and real-data replication."""
import copy,gc,hashlib,io,json,math,os,platform,sys,time
from dataclasses import dataclass,asdict
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torch.func import functional_call,jacrev
import torchvision
from torchvision.datasets import MNIST,CIFAR10
from archive_io import Campaign,write_json,sha,check
from control_math import RANKS,coefficients,sketch_coefficients,energy_curves,causal_curves,bootstrap,center
VERSION='NEXUS-STAGE10-CONTROL-SPECTRUM-R1'

@dataclass(frozen=True)
class Config:
    datasets:tuple=('MNIST','CIFAR10')
    seeds:tuple=(10100,10101,10102,10103)
    train_steps_mnist:int=1000
    train_steps_cifar:int=2000
    donor_fraction:float=.7
    batch_size:int=128
    first_probe_batch:int=256
    calibration_n:int=4096
    fit_anchor_n:int=64
    heldout_anchor_n:int=64
    response_n:int=128
    primary_rank:int=16
    diagnostic_rank:int=64
    jac_image_chunk:int=4
    jac_output_chunk:int=4
    future_steps:int=64
    horizons:tuple=(0,1,4,16,64)
    relative_displacement:float=.002
    lr:float=.0012
    beta1:float=.9
    beta2:float=.999
    eps:float=1e-8
    weight_decay:float=1e-4
    session_hours:float=6.0
    bootstrap_draws:int=5000
    accuracy_floor_mnist:float=.85
    accuracy_floor_cifar:float=.40
    jac_fd_error_max:float=.10
    clone_tolerance:float=0.0
    manual_step_abs_tolerance:float=2e-6

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


class MLP(nn.Module):
    def __init__(self):
        super().__init__();self.net=nn.Sequential(nn.Flatten(),nn.Linear(784,128),nn.Tanh(),nn.Linear(128,64),nn.Tanh(),nn.Linear(64,10))
    def forward(self,x):return self.net(x)


class ConvGN(nn.Module):
    def __init__(self):
        super().__init__();layers=[];channels=3
        for width in (16,32,64):
            layers += [nn.Conv2d(channels,width,3,padding=1,bias=False),nn.GroupNorm(8,width),nn.SiLU(),
                       nn.Conv2d(width,width,3,padding=1,bias=False),nn.GroupNorm(8,width),nn.SiLU(),nn.AvgPool2d(2)]
            channels=width
        self.features=nn.Sequential(*layers);self.head=nn.Linear(64,10)
    def forward(self,x):return self.head(self.features(x).mean((2,3)))


def model_for(dataset,unit_seed,device):
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed('model',dataset,unit_seed));m=MLP() if dataset=='MNIST' else ConvGN()
    return m.to(device)


def optimizer(model,cfg):return torch.optim.AdamW(model.parameters(),lr=cfg.lr,betas=(cfg.beta1,cfg.beta2),eps=cfg.eps,weight_decay=cfg.weight_decay,foreach=False,fused=False)


def snapshot(model,opt):return {'model':cpu(model.state_dict()),'optimizer':cpu(opt.state_dict())}


def restore(dataset,unit_seed,device,cfg,state):
    m=model_for(dataset,unit_seed,device);m.load_state_dict(copy.deepcopy(state['model']));o=optimizer(m,cfg);o.load_state_dict(copy.deepcopy(state['optimizer']));return m,o


def vectors(model,opt):
    theta=[];m=[];v=[];clocks=[];layout=[]
    for name,p in model.named_parameters():
        state=opt.state[p];theta.append(p.detach().cpu().reshape(-1).numpy());m.append(state['exp_avg'].cpu().reshape(-1).numpy());v.append(state['exp_avg_sq'].cpu().reshape(-1).numpy())
        clocks.append(int(state['step'].item()));layout.append({'name':name,'shape':list(p.shape),'size':p.numel()})
    check(len(set(clocks))==1,'Mixed clocks are outside the identification theorem')
    return np.concatenate(theta).copy(),np.concatenate(m).copy(),np.concatenate(v).copy(),clocks[0],layout


def install(model,opt,m,v,t):
    at=0
    for p in model.parameters():
        n=p.numel();s=opt.state[p]
        s['exp_avg'].copy_(torch.as_tensor(m[at:at+n],device=p.device,dtype=p.dtype).reshape_as(p))
        s['exp_avg_sq'].copy_(torch.as_tensor(v[at:at+n],device=p.device,dtype=p.dtype).reshape_as(p))
        s['step'].fill_(t);at+=n
    check(at==len(m)==len(v),'Parameter layout differs')


def dataset_load(name,root,device,cfg):
    ds=MNIST(root,train=True,download=True) if name=='MNIST' else CIFAR10(root,train=True,download=True)
    test=MNIST(root,train=False,download=True) if name=='MNIST' else CIFAR10(root,train=False,download=True)
    raw=np.asarray(ds.data);raw_test=np.asarray(test.data);y=np.asarray(ds.targets,dtype=np.int64);ty=np.asarray(test.targets,dtype=np.int64)
    fingerprints={k:hashlib.sha256(a.tobytes()).hexdigest() for k,a in {'train_images':raw,'train_labels':y,'test_images':raw_test,'test_labels':ty}.items()}
    def convert(a):
        x=torch.as_tensor(a.copy(),device=device,dtype=torch.float32)
        if name=='MNIST':return (x[:,None]/255.-.1307)/.3081
        x=x.permute(0,3,1,2).contiguous()/255.
        mean=torch.tensor([.4914,.4822,.4465],device=device)[None,:,None,None];std=torch.tensor([.247,.243,.261],device=device)[None,:,None,None]
        return (x-mean)/std
    X=convert(raw);TX=convert(raw_test);Y=torch.as_tensor(y,device=device);TY=torch.as_tensor(ty,device=device)
    order=np.random.default_rng(790012).permutation(len(y));train_ids=order[:-cfg.calibration_n];cal_ids=order[-cfg.calibration_n:]
    resp=[];rng=np.random.default_rng(790013)
    for label in range(10):resp.extend(rng.permutation(np.flatnonzero(ty==label))[:cfg.response_n//10+(label<cfg.response_n%10)].tolist())
    resp=np.asarray(resp);test_ids=np.setdiff1d(np.arange(len(ty)),resp)
    check(not set(train_ids)&set(cal_ids) and not set(resp)&set(test_ids),'Dataset role leakage')
    return {'X':X,'Y':Y,'TX':TX,'TY':TY,'train_ids':train_ids,'cal_ids':cal_ids,'response_ids':resp,'test_ids':test_ids,
            'fingerprints':fingerprints,'name':name}


def batch(data,unit_seed,step,cfg):
    g=torch.Generator().manual_seed(seed('batch',data['name'],unit_seed,step))
    ix=torch.randint(len(data['train_ids']),(cfg.batch_size,),generator=g).numpy()
    ids=torch.as_tensor(data['train_ids'][ix],device=data['X'].device);x=data['X'][ids];y=data['Y'][ids]
    if data['name']=='CIFAR10':
        # Deterministic per-step augmentation, common to all future branches.
        offsets=torch.randint(0,9,(len(x),2),generator=g).to(x.device);flip=(torch.rand(len(x),generator=g)>.5).to(x.device)
        padded=F.pad(x,(4,4,4,4),mode='reflect').permute(0,2,3,1)
        rows=torch.arange(len(x),device=x.device)[:,None,None]
        h=torch.arange(32,device=x.device)[None,:,None]+offsets[:,0,None,None]
        w=torch.arange(32,device=x.device)[None,None,:]+offsets[:,1,None,None]
        x=padded[rows,h,w].permute(0,3,1,2).contiguous();x=torch.where(flip[:,None,None,None],x.flip(-1),x)
    return x,y


def train_step(model,opt,x,y):
    model.train();opt.zero_grad(set_to_none=True);loss=F.cross_entropy(model(x),y);loss.backward()
    check(all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()),'Nonfinite or absent gradient')
    opt.step();return float(loss.detach())


def gradient(model,x,y):
    model.train();model.zero_grad(set_to_none=True);F.cross_entropy(model(x),y).backward()
    return np.concatenate([p.grad.detach().cpu().reshape(-1).numpy() for p in model.parameters()]).copy()


@torch.no_grad()
def logits(model,data,ids):
    model.eval();return torch.cat([model(data['TX'][torch.as_tensor(ids[i:i+256],device=data['X'].device)]).cpu() for i in range(0,len(ids),256)]).numpy()


def metrics(z,y):
    z=torch.from_numpy(z).double();y=torch.as_tensor(y)
    return {'accuracy':float((z.argmax(1)==y).double().mean()),'loss':float(F.cross_entropy(z,y))}

def binding():
    root=Path(__file__).parent
    return {n:sha(root/n) for n in ('runner.py','archive_io.py','control_math.py','audit.py','test_math.py','PROTOCOL.json','PARENT_EVIDENCE.json','README.md')}

def layout_of(model):
    return [(n,p.shape,p.numel()) for n,p in model.named_parameters()]

def flat_parameters(model):return torch.cat([p.detach().reshape(-1) for p in model.parameters()])

def assign_parameters(model,theta):
    at=0
    with torch.no_grad():
        for p in model.parameters():p.copy_(theta[at:at+p.numel()].view_as(p));at+=p.numel()

def flatten_m(model,opt):return torch.cat([opt.state[p]['exp_avg'].reshape(-1) for p in model.parameters()])

def functional_logits(model,theta,x):
    at=0;params={}
    for name,shape,n in layout_of(model):params[name]=theta[at:at+n].view(shape);at+=n
    return functional_call(model,params,(x,),strict=True)

def centered_flat(model,theta,x):
    z=functional_logits(model,theta,x);return (z-z.mean(-1,keepdim=True)).reshape(-1)

def exact_rows(model,theta,D,x,cfg,pulse):
    blocks=[];model.eval()
    for start in range(0,len(x),cfg.jac_image_chunk):
        pulse();xb=x[start:start+cfg.jac_image_chunk]
        J=jacrev(lambda p:centered_flat(model,p,xb),chunk_size=cfg.jac_output_chunk)(theta)
        check(torch.isfinite(J).all(),'Nonfinite exact Jacobian')
        blocks.append((J*D[None,:]).detach());del J
        print('  exact operator rows',min(start+len(xb),len(x)),'/',len(x),'images',flush=True)
    return torch.cat(blocks)/math.sqrt(len(x))

def unit_ids(cfg):return [f'{d}_{s}' for d in cfg.datasets for s in cfg.seeds]

def qualification(cfg,device):
    # Ordinary AdamW formula, actual serialised continuation, known-spectrum recovery.
    torch.manual_seed(87012);model=nn.Sequential(nn.Linear(4,6),nn.Tanh(),nn.Linear(6,3)).to(device)
    opt=optimizer(model,cfg);x=torch.arange(32,device=device).float().view(8,4)/32;y=torch.arange(8,device=device)%3
    for _ in range(4):train_step(model,opt,x,y)
    buffer=io.BytesIO();torch.save(snapshot(model,opt),buffer);buffer.seek(0)
    snap=torch.load(buffer,map_location='cpu',weights_only=True)
    clone=copy.deepcopy(model);clone.load_state_dict(snap['model']);co=optimizer(clone,cfg);co.load_state_dict(copy.deepcopy(snap['optimizer']))
    for _ in range(3):train_step(model,opt,x,y);train_step(clone,co,x,y)
    check(all(torch.equal(a,b) for a,b in zip(model.parameters(),clone.parameters())),'Clone parameter continuation differs')
    check(all(torch.equal(opt.state[p][k],co.state[q][k]) for p,q in zip(model.parameters(),clone.parameters()) for k in ('step','exp_avg','exp_avg_sq')),'Clone moment continuation differs')
    theta,m,v,t,_=vectors(model,opt);g=gradient(model,x,y)
    M=cfg.beta1*m+(1-cfg.beta1)*g;V=cfg.beta2*v+(1-cfg.beta2)*g*g
    manual=theta*(1-cfg.lr*cfg.weight_decay)-cfg.lr*(M/(1-cfg.beta1**(t+1)))/(np.sqrt(V/(1-cfg.beta2**(t+1)))+cfg.eps)
    train_step(model,opt,x,y);err=float(np.max(abs(flat_parameters(model).cpu().numpy()-manual)))
    check(err<cfg.manual_step_abs_tolerance,'AdamW formula qualification failed')
    # Independent direct derivative of the one-step m->logits map on a smooth tiny model.
    model.double();layout=layout_of(model);th=torch.tensor(theta,device=device,dtype=torch.float64)
    mm=torch.tensor(m,device=device,dtype=torch.float64);vv=torch.tensor(v,device=device,dtype=torch.float64);gg=torch.tensor(g,device=device,dtype=torch.float64)
    den=torch.sqrt((cfg.beta2*vv+(1-cfg.beta2)*gg*gg)/(1-cfg.beta2**(t+1)))+cfg.eps
    D=-cfg.lr*cfg.beta1/((1-cfg.beta1**(t+1))*den)
    nxt=th*(1-cfg.lr*cfg.weight_decay)-cfg.lr*(cfg.beta1*mm+(1-cfg.beta1)*gg)/((1-cfg.beta1**(t+1))*den)
    J=jacrev(lambda p:centered_flat(model,p,x.double()))(nxt)
    actual=jacrev(lambda a:centered_flat(model,th*(1-cfg.lr*cfg.weight_decay)-cfg.lr*(cfg.beta1*a+(1-cfg.beta1)*gg)/((1-cfg.beta1**(t+1))*den),x.double()))(mm)
    derr=float(torch.linalg.vector_norm(actual-J*D)/torch.linalg.vector_norm(actual))
    check(derr<1e-10,'Control operator derivative is wrong')
    # Exercise actual ConvGN batched Jacobian backend before any research training.
    conv=ConvGN().to(device);ct=flat_parameters(conv).clone().requires_grad_(True)
    cx=torch.sin(torch.arange(3*32*32,device=device,dtype=torch.float32)).view(1,3,32,32)
    cd=torch.linspace(.01,.02,len(ct),device=device);alpha=torch.linspace(-1,1,10,device=device)
    rows=exact_rows(conv,ct,cd,cx,cfg,lambda:None)
    y=centered_flat(conv,ct,cx);adj=torch.autograd.grad((y*alpha).sum(),ct)[0]*cd
    predicted=rows.T@alpha
    conv_err=float(torch.linalg.vector_norm(predicted-adj)/torch.linalg.vector_norm(adj))
    check(conv_err<2e-4,'ConvGN batched Jacobian backend qualification failed')
    from test_math import verify_math
    known=verify_math()
    return {'passed':True,'adamw_parameter_max_abs_error':err,'one_step_m_derivative_relative_error':derr,'convgn_jacrev_adjoint_relative_error':conv_err,
            'serialized_clone_continuation_bitwise_exact':True,'known_spectrum':known}

def train_reference(folder,data,s,cfg,device,store,guard):
    cut=folder/'cut.pt';progress=folder/'training.pt'
    total=cfg.train_steps_mnist if data['name']=='MNIST' else cfg.train_steps_cifar
    donor_at=int(total*cfg.donor_fraction)
    if cut.exists():return load_pt(cut)
    if progress.exists():
        saved=load_pt(progress);model,opt=restore(data['name'],s,device,cfg,saved['snapshot']);done=saved['completed'];donor=saved['donor']
    else:model=model_for(data['name'],s,device);opt=optimizer(model,cfg);done=0;donor=None
    for step in range(done,total):
        guard();x,y=batch(data,s,step,cfg);loss=train_step(model,opt,x,y)
        if step+1==donor_at:donor=flatten_m(model,opt).detach().cpu().clone()
        if (step+1)%500==0:
            save_pt(progress,{'snapshot':snapshot(model,opt),'completed':step+1,'donor':donor})
            store.checkpoint();print(data['name'],s,'training',step+1,'/',total,'loss',round(loss,4),flush=True)
    check(donor is not None,'Missing historical donor moment')
    saved={'snapshot':snapshot(model,opt),'donor':donor,'completed':total,'donor_at':donor_at}
    save_pt(cut,saved)
    if progress.exists():progress.unlink()
    store.checkpoint(force=True);return saved

def balanced_ids(labels,ids,n,rng):
    labels=np.asarray(labels);out=[]
    for c in range(10):
        eligible=np.asarray(ids)[labels[np.asarray(ids)]==c];need=n//10+(c<n%10)
        check(len(eligible)>=need,'Not enough class-balanced anchor items');out.extend(rng.permutation(eligible)[:need].tolist())
    return np.asarray(out,dtype=np.int64)

def operator_phase(folder,data,s,cfg,device,saved,store,guard):
    if (folder/'operator.json').exists() and (folder/'directions.pt').exists():
        return json.loads((folder/'operator.json').read_text()),load_pt(folder/'directions.pt')
    model,opt=restore(data['name'],s,device,cfg,saved['snapshot'])
    theta,m,v,t,layout=vectors(model,opt);h=torch.from_numpy(m).to(device)-saved['donor'].to(device)
    hn=float(torch.linalg.vector_norm(h));mn=float(np.linalg.norm(m.astype('float64')))
    check(hn>0 and mn>0,'Historical direction has zero norm');h=h/hn
    rng=np.random.default_rng(seed('roles',data['name'],s));cy=data['Y'].cpu().numpy()
    aid=balanced_ids(cy,data['cal_ids'],cfg.fit_anchor_n,rng)
    remain=np.setdiff1d(data['cal_ids'],aid);bid=balanced_ids(cy,remain,cfg.heldout_anchor_n,rng)
    remain=np.setdiff1d(remain,bid);gids=rng.permutation(remain)[:cfg.first_probe_batch]
    check(not set(aid)&set(bid) and not set(gids)&(set(aid)|set(bid)),'Anchor/probe overlap')
    gx=data['X'][torch.as_tensor(gids,device=device)];gy=data['Y'][torch.as_tensor(gids,device=device)]
    g=gradient(model,gx,gy);train_step(model,opt,gx,gy);next_theta=flat_parameters(model)
    den=np.sqrt((cfg.beta2*v.astype('float64')+(1-cfg.beta2)*g.astype('float64')**2)/(1-cfg.beta2**(t+1)))+cfg.eps
    D=torch.tensor(-cfg.lr*cfg.beta1/((1-cfg.beta1**(t+1))*den),device=device,dtype=torch.float32)
    A=exact_rows(model,next_theta,D,data['X'][torch.as_tensor(aid,device=device)],cfg,guard)
    B=exact_rows(model,next_theta,D,data['X'][torch.as_tensor(bid,device=device)],cfg,guard)
    guard();Ad=A.double();Bd=B.double()
    G=(Ad@Ad.T).cpu().numpy();H=(Bd@Bd.T).cpu().numpy();K=(Bd@Ad.T).cpu().numpy()
    C,w=coefficients(G);Cs,sw=sketch_coefficients(G,np.random.default_rng(seed('sketch',data['name'],s)))
    curve,spec=energy_curves(G,H,K,C,Cs)
    # Build only frozen ranks. Neither h nor future responses influenced the fitted subspace.
    U=Ad.T@torch.from_numpy(C[:,:cfg.diagnostic_rank]).to(device)
    orth=float(torch.max(abs(U.T@U-torch.eye(U.shape[1],device=device,dtype=torch.float64))))
    check(orth<1e-5,'Right-subspace orthogonality qualification failed')
    h=h.double();dirs={'full':h};projection={}
    for k in (cfg.primary_rank,cfg.diagnostic_rank):
        p=U[:,:k]@(U[:,:k].T@h);r=h-p
        dirs[f'parallel{k}']=p;dirs[f'remainder{k}']=r
        projection[str(k)]={'actual_rank':min(k,U.shape[1]),'history_alignment':float(torch.dot(p,p)),
          'parallel_norm':float(torch.linalg.vector_norm(p)),'remainder_norm':float(torch.linalg.vector_norm(r)),
          'direction_additivity_error':float(torch.linalg.vector_norm(h-p-r))}
    # Raw linear effects of each history component on the independent anchor.
    linear={name:(Bd@d).cpu().numpy() for name,d in dirs.items()}
    controls={};control_vectors={};rr=np.random.default_rng(seed('matched_controls',data['name'],s))
    hcpu=h.cpu().numpy();at=0;tensor_slices=[]
    for item in layout:tensor_slices.append((at,at+item['size']));at+=item['size']
    for j in range(8):
        z=np.empty_like(hcpu)
        for a,b in tensor_slices:
            q=rr.normal(size=b-a);z[a:b]=q/max(np.linalg.norm(q),1e-30)*np.linalg.norm(hcpu[a:b])
        control_vectors[f'random{j}']=z
    control_vectors['sign_shuffle']=hcpu*rr.choice([-1.,1.],size=len(hcpu))
    z=hcpu.copy()
    for a,b in tensor_slices:z[a:b]=rr.permutation(z[a:b])
    control_vectors['within_tensor_permutation']=z
    control_vectors['current_gradient']=g.astype('float64')/max(np.linalg.norm(g.astype('float64')),1e-30)
    pg=g.astype('float64')/(np.sqrt(v.astype('float64')/(1-cfg.beta2**t))+cfg.eps)
    control_vectors['preconditioned_gradient']=pg/max(np.linalg.norm(pg),1e-30)
    control_linear={name:(Bd@torch.from_numpy(d).to(device)).cpu().numpy() for name,d in control_vectors.items()}
    history_energy=float(np.square(linear['full']).sum())
    for name,z in control_linear.items():controls[name]={'heldout_potency':float(np.linalg.norm(z)),
         'history_potency_ratio':float(math.sqrt(history_energy/max(float(np.square(z).sum()),1e-60)))}
    scale=cfg.relative_displacement*mn
    # Independent finite-surgery first-step check at two scales; no threshold/amplitude rescue.
    finite={};fds={};fdids=data['response_ids'][np.linspace(0,len(data['response_ids'])-1,16,dtype=int)]
    x_eval=data['TX'][torch.as_tensor(fdids,device=device)]
    with torch.no_grad():baseline=functional_logits(model,next_theta,x_eval).cpu().numpy()
    J_eval=exact_rows(model,next_theta,D,x_eval,cfg,guard)
    pred=(J_eval.double()@h).cpu().numpy()*math.sqrt(len(x_eval));pred=pred.reshape(len(x_eval),10)
    for factor in (.5,1.):
        responses=[]
        for sign in (-1.,1.):
            md,op=restore(data['name'],s,device,cfg,saved['snapshot'])
            install(md,op,(m.astype('float64')+sign*scale*factor*hcpu).astype('float32'),v,t)
            train_step(md,op,gx,gy)
            with torch.no_grad():z=md(x_eval).cpu().numpy()
            responses.append(z);fds[f'factor{factor}_sign{sign}']=z
        actual=(center(responses[1])-center(responses[0]))/(2*scale*factor)
        finite[str(factor)]={'relative_central_derivative_error':float(np.linalg.norm(actual-pred)/max(np.linalg.norm(pred),1e-30))}
    result={'unit':f'{data["name"]}_{s}','clock':t,'parameter_count':len(m),'layout':layout,
      'fit_anchor_ids':aid.tolist(),'heldout_anchor_ids':bid.tolist(),'first_batch_ids':gids.tolist(),
      'rank_curve':curve,'spectral_diagnostics':spec,'projection':projection,'controls':controls,
      'orthogonality_max_error':orth,'one_step_fd':finite,'displacement':scale,'relative_displacement':cfg.relative_displacement,
      'exact_scope':'explicit FP32-autodiff Jacobian of this finite-anchor local operator; no global spectrum claim',
      'no_history_or_future_in_subspace_fit':True}
    npz(folder/'operator_raw.npz',{'G':G,'H':H,'K':K,'C':C,'Cs':Cs,'spectrum':w,
      'history':hcpu,'baseline_first':baseline,'predicted_history_derivative':pred,
      **{f'linear_{k}':z for k,z in linear.items()},**{f'control_{k}':z for k,z in control_linear.items()},**fds})
    npz(folder/'cut_state.npz',{'theta':theta,'m':m,'v':v,'donor_m':saved['donor'].numpy(),'first_gradient':g,
      'response_ids':data['response_ids'],'test_ids':data['test_ids'],
      'response_labels':data['TY'][torch.as_tensor(data['response_ids'],device=device)].cpu().numpy(),
      'test_labels':data['TY'][torch.as_tensor(data['test_ids'],device=device)].cpu().numpy()})
    directions={'vectors':{k:d.detach().cpu().float() for k,d in dirs.items()},'gids':torch.from_numpy(gids),'scale':scale}
    save_pt(folder/'directions.pt',directions);write_json(folder/'operator.json',result)
    del A,B,Ad,Bd,U,J_eval,model,opt;gc.collect()
    if device.type=='cuda':torch.cuda.empty_cache()
    store.checkpoint(force=True);return result,directions

def future_phase(folder,data,s,cfg,device,saved,directions,store,guard):
    base_model,base_opt=restore(data['name'],s,device,cfg,saved['snapshot'])
    theta,m,v,t,_=vectors(base_model,base_opt);gids=directions['gids'].numpy()
    if not (folder/'initial.npz').exists():
        rz=logits(base_model,data,data['response_ids']);tz=logits(base_model,data,data['test_ids'])
        npz(folder/'initial.npz',{'response_logits':rz,'test_logits':tz})
    labels=['baseline']+[f'{name}_{sign}' for name in directions['vectors'] for sign in ('plus','minus')]
    for label in labels:
        guard();jp=folder/f'future_{label}.json';zp=folder/f'future_{label}.npz';progress=folder/'branch.pt'
        if jp.exists():
            rec=json.loads(jp.read_text());check(zp.exists() and sha(zp)==rec['payload_sha256'],'Committed branch data changed')
            if progress.exists() and load_pt(progress)['label']==label:progress.unlink()
            continue
        if progress.exists():
            record=load_pt(progress);check(record['label']==label,'Branch order changed')
            md,op=restore(data['name'],s,device,cfg,record['snapshot']);done=record['completed'];arrays={k:z.numpy() for k,z in record['arrays'].items()}
        else:
            md,op=restore(data['name'],s,device,cfg,saved['snapshot']);done=0
            if label!='baseline':
                name,sgn=label.rsplit('_',1);d=directions['vectors'][name].numpy().astype('float64')
                proposed=(m.astype('float64')+(1 if sgn=='plus' else -1)*directions['scale']*d).astype('float32')
                install(md,op,proposed,v,t)
            check(torch.equal(flat_parameters(md).cpu(),torch.from_numpy(theta)),'Surgery changed initial weights')
            # Actual modified first-moment bytes are retained in the local progress only.
            arrays={'h0':logits(md,data,data['response_ids']),
                    'actual_delta_m':flatten_m(md,op).detach().cpu().numpy().astype('float64')-m.astype('float64')}
            check(torch.equal(torch.cat([op.state[p]['exp_avg_sq'].cpu().reshape(-1) for p in md.parameters()]),torch.from_numpy(v)),'Surgery changed second moments')
            check(all(int(op.state[p]['step'].item())==t for p in md.parameters()),'Surgery changed clock')
        for h in range(done+1,cfg.future_steps+1):
            guard()
            if h==1:x=data['X'][torch.as_tensor(gids,device=device)];y=data['Y'][torch.as_tensor(gids,device=device)]
            else:x,y=batch(data,s,saved['completed']+h-2,cfg)
            train_step(md,op,x,y)
            if h in cfg.horizons:arrays[f'h{h}']=logits(md,data,data['response_ids'])
            if h%16==0:
                save_pt(progress,{'label':label,'completed':h,'snapshot':snapshot(md,op),'arrays':{k:torch.from_numpy(z.copy()) for k,z in arrays.items()}})
                store.checkpoint()
        arrays['test_logits']=logits(md,data,data['test_ids']);npz(zp,arrays)
        rec={'label':label,'payload_sha256':sha(zp),'surgery_relative_m_displacement':float(np.linalg.norm(arrays['actual_delta_m'])/max(np.linalg.norm(m.astype('float64')),1e-30)),
             'initial_weights_second_moments_clock_unchanged':True,
             'final_test':metrics(arrays['test_logits'],data['TY'][torch.as_tensor(data['test_ids'],device=device)].cpu().numpy())}
        write_json(jp,rec)
        if progress.exists():progress.unlink()
        store.checkpoint();del md,op;gc.collect()
        print(data['name'],s,'future completed:',label,flush=True)
    all_arrays={}
    for label in labels:
        with np.load(folder/f'future_{label}.npz',allow_pickle=False) as z:
            for h in cfg.horizons:all_arrays[f'{label}_h{h}']=z[f'h{h}'].copy()
    curves=causal_curves(all_arrays,cfg.horizons,(cfg.primary_rank,cfg.diagnostic_rank))
    # Zero-horizon effects must be exactly zero. Paired and both signed effects stay separate.
    for label in labels:check(np.array_equal(all_arrays[f'{label}_h0'],all_arrays['baseline_h0']),'Present-function invariance failed')
    for k in curves:
        curves[k]['paired']={}
        for h in cfg.horizons:
            def contrast(name):return (center(all_arrays[f'{name}_plus_h{h}'])-center(all_arrays[f'{name}_minus_h{h}']))/2
            from control_math import response_metrics
            f=contrast('full');p=contrast(f'parallel{k}');r=contrast(f'remainder{k}')
            curves[k]['paired'][str(h)]=response_metrics(np.zeros_like(f),f,p,r)
    return curves

def run_unit(store,data,s,cfg,device,guard):
    unit=f'{data["name"]}_{s}';folder=store.local/'units'/unit;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'result.json').exists():
        from audit import audit_unit
        audit_unit(folder,cfg.horizons,(cfg.primary_rank,cfg.diagnostic_rank));print('Verified completed unit; skipping:',unit,flush=True);return
    start=time.monotonic();saved=train_reference(folder,data,s,cfg,device,store,guard)
    operator_record,directions=operator_phase(folder,data,s,cfg,device,saved,store,guard)
    curves=future_phase(folder,data,s,cfg,device,saved,directions,store,guard)
    with np.load(folder/'initial.npz') as z:initial=metrics(z['test_logits'],data['TY'][torch.as_tensor(data['test_ids'],device=device)].cpu().numpy())
    threshold=cfg.accuracy_floor_mnist if data['name']=='MNIST' else cfg.accuracy_floor_cifar
    result={'unit':unit,'dataset':data['name'],'seed':s,'operator':operator_record,'causal_curves':curves,
      'initial_test':initial,'learning_quality_diagnostic':{'accuracy_floor':threshold,'passed':initial['accuracy']>=threshold,'seed_excluded':False},
      'instrument_fd_diagnostic':{'max_relative_error':max(r['relative_central_derivative_error'] for r in operator_record['one_step_fd'].values()),
        'threshold':cfg.jac_fd_error_max,'passed':all(r['relative_central_derivative_error']<cfg.jac_fd_error_max for r in operator_record['one_step_fd'].values())},
      'active_seconds_this_session':time.monotonic()-start,'claims':'descriptive prospective extension, not a rescue of Stage07 confirmation',
      'natural_training_history_reachability_claimed':False}
    write_json(folder/'result.json',result)
    from audit import audit_unit
    audit_unit(folder,cfg.horizons,(cfg.primary_rank,cfg.diagnostic_rank))
    for p in folder.glob('*.pt'):p.unlink()
    store.checkpoint(force=True)
    print('UNIT COMPLETE',unit,'seconds this session',round(result['active_seconds_this_session'],1),flush=True)

def summarize(local,cfg):
    from audit import audit_unit
    results=[]
    for unit in unit_ids(cfg):
        folder=Path(local)/'units'/unit
        if (folder/'result.json').exists():audit_unit(folder,cfg.horizons,(cfg.primary_rank,cfg.diagnostic_rank));results.append(json.loads((folder/'result.json').read_text()))
    out={'version':VERSION,'complete':len(results)==len(unit_ids(cfg)),'completed_models':len(results),'planned_models':len(unit_ids(cfg)),
       'primary_rank':cfg.primary_rank,'diagnostic_rank':cfg.diagnostic_rank,'panels':{},
       'inference':'descriptive per-training-seed bootstrap; no coordinate or image pseudoreplication; no multiplicity-adjusted confirmation',
       'contribution_boundary':'exact finite-anchor spectrum diagnosis plus two real-data regimes; historical Stage07 flags remain unchanged'}
    for dataset in cfg.datasets:
        rs=[r for r in results if r['dataset']==dataset]
        if not rs:continue
        rng=np.random.default_rng(seed('summary',dataset));panel={'n':len(rs),'rank_curve':{},'causal':{},
           'quality_per_seed':[r['learning_quality_diagnostic'] for r in rs],
           'instrument_per_seed':[r['instrument_fd_diagnostic'] for r in rs]}
        for k in RANKS:
            panel['rank_curve'][str(k)]={}
            for key in ('fit_capture','transfer_capture','heldout_self_oracle_capture','sketch_transfer_capture'):
                vals=[next(q[key] for q in r['operator']['rank_curve'] if q['k']==k) for r in rs]
                panel['rank_curve'][str(k)][key]=bootstrap(vals,rng,cfg.bootstrap_draws) if all(v is not None for v in vals) else None
        for k in (cfg.primary_rank,cfg.diagnostic_rank):
            panel['causal'][str(k)]={}
            for sign in ('plus','minus','paired'):
                panel['causal'][str(k)][sign]={}
                for h in (1,4,16,64):
                    panel['causal'][str(k)][sign][str(h)]={}
                    for key in ('full_rmse','retention','cosine','remainder_ratio','additivity_error'):
                        vals=[r['causal_curves'][str(k)][sign][str(h)][key] for r in rs]
                        panel['causal'][str(k)][sign][str(h)][key]=bootstrap(vals,rng,cfg.bootstrap_draws) if all(v is not None for v in vals) else {'unresolved_seed_count':sum(v is None for v in vals),'per_seed':vals}
        out['panels'][dataset]=panel
    write_json(Path(local)/'analysis'/'SUMMARY.json',out);return out

def run(drive_root,local_root,device='cuda',cfg=None,data_loader=None):
    cfg=cfg or Config();device=torch.device(device);configure(device)
    check(device.type=='cuda' or data_loader is not None,'Research notebook requires a GPU; CPU allowed only for injected engineering fixtures')
    identity=json.loads(canon({'version':VERSION,'config':asdict(cfg),'sources':binding(),'runtime':environment(device)}))
    store=Campaign(drive_root,local_root,identity);status=store.activate();started=time.monotonic()
    def guard():
        store.pulse();check(time.monotonic()-started<cfg.session_hours*3600,'Session time limit reached; rerun same notebook to resume')
    try:
        if status=='FINISHED':return summarize(store.local,cfg),store.drive/'NEXUS_STAGE10_FINISHED.zip'
        metadata=store.local/'metadata';metadata.mkdir(parents=True,exist_ok=True)
        for name in binding():
            import shutil
            shutil.copy2(Path(__file__).parent/name,metadata/name)
        write_json(metadata/'BACKEND_QUALIFICATION.json',qualification(cfg,device))
        loader=data_loader or dataset_load
        for dataset in cfg.datasets:
            required=[f'{dataset}_{s}' for s in cfg.seeds]
            if all((store.local/'units'/u/'result.json').exists() for u in required):continue
            data=loader(dataset,str(Path(local_root).parent/'nexus_stage10_dataset_cache'),device,cfg)
            manifest={'fingerprints':data['fingerprints'],'train_ids':data['train_ids'].tolist(),'cal_ids':data['cal_ids'].tolist(),
               'response_ids':data['response_ids'].tolist(),'test_ids':data['test_ids'].tolist()}
            mp=metadata/f'{dataset}_DATA.json'
            if mp.exists():check(json.loads(mp.read_text())==manifest,'Dataset content/roles changed across resume')
            else:write_json(mp,manifest)
            for s in cfg.seeds:run_unit(store,data,s,cfg,device,guard)
            del data;gc.collect()
            if device.type=='cuda':torch.cuda.empty_cache()
        summary=summarize(store.local,cfg);check(summary['complete'],'Missing planned models')
        return summary,store.finish()
    except BaseException as e:
        # Preserve partial progress on controlled errors, but never overwrite a previous
        # checkpoint with an invalid scientific record or a lost session lease.
        print('STOPPED:',repr(e),'\nThe latest verified checkpoint remains. Rerun unchanged notebook or send the error.',flush=True)
        raise
    finally:store.lease.release()
