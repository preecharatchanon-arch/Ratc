import hashlib
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
from torchvision.datasets import CIFAR10,CIFAR100
def seed(*items):return int(hashlib.sha256('|'.join(map(str,items)).encode()).hexdigest()[:8],16)
def balanced(labels,pool,n,rng):
    pools={int(c):list(rng.permutation(np.asarray(pool)[labels[pool]==c])) for c in np.unique(labels[pool])};out=[]
    while len(out)<n:
        available=[c for c,v in pools.items() if v]
        if not available:raise ValueError('Insufficient independent role images')
        for c in rng.permutation(available):
            out.append(int(pools[int(c)].pop()))
            if len(out)==n:break
    return np.asarray(out,dtype=np.int64)
def load(name,root,device,cal_n=4096,response_n=128):
    cls={'CIFAR10':CIFAR10,'CIFAR100':CIFAR100}[name];tr=cls(root,train=True,download=True);te=cls(root,train=False,download=True)
    raw=np.asarray(tr.data);rt=np.asarray(te.data);y=np.asarray(tr.targets,dtype=np.int64);ty=np.asarray(te.targets,dtype=np.int64)
    order=np.random.default_rng(seed('stage13','partition',name)).permutation(len(y));train=order[:-cal_n];cal=order[-cal_n:]
    resp=balanced(ty,np.arange(len(ty)),response_n,np.random.default_rng(seed('stage13','response',name)));test=np.setdiff1d(np.arange(len(ty)),resp)
    def convert(a):return (torch.tensor(a,device=device,dtype=torch.float32).permute(0,3,1,2).contiguous()/255.-.5)/.25
    return dict(name=name,X=convert(raw),Y=torch.tensor(y,device=device),TX=convert(rt),TY=torch.tensor(ty,device=device),labels=y,test_labels=ty,
        train_ids=train,cal_ids=cal,response_ids=resp,test_ids=test,classes=len(np.unique(y)),
        fingerprints={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in {'train_images':raw,'train_labels':y,'test_images':rt,'test_labels':ty}.items()})
def roles(data,s,fit_sizes,held_n=256,first_n=128):
    rng=np.random.default_rng(seed('stage13','roles',data['name'],s));pool=data['cal_ids']
    fit=balanced(data['labels'],pool,max(fit_sizes),rng);remaining=np.setdiff1d(pool,fit)
    held=balanced(data['labels'],remaining,held_n,rng);remaining=np.setdiff1d(remaining,held)
    first=balanced(data['labels'],remaining,first_n,rng)
    return dict(fit_ids=fit.tolist(),heldout_ids=held.tolist(),first_ids=first.tolist(),fit_sizes=list(fit_sizes),
        response_ids=data['response_ids'].tolist(),test_ids=data['test_ids'].tolist())
def batch(data,s,index,batch_n,phase='train',path=0):
    g=torch.Generator().manual_seed(seed('stage13',phase,data['name'],s,path,index));ix=torch.randint(len(data['train_ids']),(batch_n,),generator=g).numpy()
    ids=torch.tensor(data['train_ids'][ix],device=data['X'].device);x=data['X'][ids];y=data['Y'][ids]
    offsets=torch.randint(0,9,(len(x),2),generator=g).to(x.device);flip=(torch.rand(len(x),generator=g)>.5).to(x.device)
    padded=F.pad(x,(4,4,4,4),mode='reflect').permute(0,2,3,1);rows=torch.arange(len(x),device=x.device)[:,None,None]
    h=torch.arange(32,device=x.device)[None,:,None]+offsets[:,0,None,None];w=torch.arange(32,device=x.device)[None,None,:]+offsets[:,1,None,None]
    x=padded[rows,h,w].permute(0,3,1,2).contiguous();return torch.where(flip[:,None,None,None],x.flip(-1),x),y
def future(data,s,role,path,c):
    ix=torch.tensor(role['first_ids'],device=data['X'].device);yield data['X'][ix],data['Y'][ix]
    for i in range(1,c.future_steps):yield batch(data,s,i,c.future_batch,'future',path)
