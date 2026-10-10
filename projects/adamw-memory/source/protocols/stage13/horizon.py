"""Exact finite-bank full-state AdamW tangents and adjoints."""
import copy,math,time
import numpy as np
import torch
from torch.nn import functional as F
from torch.func import functional_call

def flat(model):return torch.cat([p.detach().reshape(-1) for p in model.parameters()])
def call(model,w,x):
    d={};a=0
    for n,p in model.named_parameters():d[n]=w[a:a+p.numel()].view_as(p);a+=p.numel()
    assert a==len(w)
    return functional_call(model,d,(x,),strict=True)
def restore(model,state,c):
    md=copy.deepcopy(model);a=0
    with torch.no_grad():
        for p in md.parameters():p.copy_(state['theta'][a:a+p.numel()].view_as(p));a+=p.numel()
    op=torch.optim.AdamW(md.parameters(),lr=c.lr,betas=(c.beta1,c.beta2),eps=c.eps,weight_decay=c.weight_decay,foreach=False,fused=False);a=0
    for p in md.parameters():
        n=p.numel();op.state[p]={'step':torch.tensor(float(state['clock'])),
            'exp_avg':state['m'][a:a+n].view_as(p).clone(),'exp_avg_sq':state['v'][a:a+n].view_as(p).clone()};a+=n
    return md,op
def slots(md,op):
    clocks=[int(op.state[p]['step']) for p in md.parameters()];assert len(set(clocks))==1
    return dict(theta=flat(md),m=torch.cat([op.state[p]['exp_avg'].detach().flatten() for p in md.parameters()]),
        v=torch.cat([op.state[p]['exp_avg_sq'].detach().flatten() for p in md.parameters()]),clock=clocks[0])
def step(md,op,x,y):
    op.zero_grad(set_to_none=True);F.cross_entropy(md(x),y).backward()
    g=torch.cat([p.grad.detach().flatten() for p in md.parameters()]);assert torch.isfinite(g).all();op.step();return g
def helmert(C,device,dtype):
    q=torch.zeros(C,C-1,device=device,dtype=dtype)
    for k in range(1,C):q[:k,k-1]=1/math.sqrt(k*(k+1));q[k,k-1]=-k/math.sqrt(k*(k+1))
    return q

class Trainer:
    def __init__(self,model,state,batches,c,pulse=lambda:None):
        self.model=model;self.c=c;self.pulse=pulse;self.records=[];self.graphs=[];self.agreement=[]
        md,op=restore(model,state,c)
        for i,(x,y) in enumerate(batches):
            pulse();before=slots(md,op);g=step(md,op,x,y);after=slots(md,op)
            root=torch.sqrt(after['v']/(1-c.beta2**after['clock']));assert (root>0).all();den=root+c.eps
            B=-c.lr/((1-c.beta1**after['clock'])*den)
            C=c.lr*after['m']/(2*(1-c.beta1**after['clock'])*(1-c.beta2**after['clock'])*root*den.square())
            self.records.append((before['theta'],g,B,C))
            if i==0:self.graphs.append(None)
            else:
                w=before['theta'].requires_grad_(True);gg=torch.autograd.grad(F.cross_entropy(call(model,w,x),y),w,create_graph=True)[0]
                rel=float((gg.detach()-g).norm()/g.norm().clamp_min(1e-12));ab=float((gg.detach()-g).abs().max())
                assert rel<2e-5 and ab<2e-5*max(1.,float(g.abs().max())),('Functional/native disagreement',rel,ab)
                self.agreement.append(dict(step=i+1,relative_l2=rel,max_abs=ab));self.graphs.append((w,gg))
        self.final=slots(md,op);del md,op
    def hvp(self,i,v):
        self.pulse();w,g=self.graphs[i]
        if v.ndim==2:return torch.stack([self.hvp(i,r) for r in v])
        return torch.autograd.grad(g,w,v,retain_graph=True)[0].detach()
    def forward(self,u,H):
        dw=torch.zeros_like(u);dm=u.clone();dv=torch.zeros_like(u);c=self.c
        for i in range(H):
            _,g,B,C=self.records[i];dg=torch.zeros_like(u) if i==0 else self.hvp(i,dw)
            dm=c.beta1*dm+(1-c.beta1)*dg;dv=c.beta2*dv+2*(1-c.beta2)*g*dg
            dw=(1-c.lr*c.weight_decay)*dw+B*dm+C*dv
        return dw
    def reverse(self,lw,H):
        lm=torch.zeros_like(lw);lv=torch.zeros_like(lw);c=self.c
        for i in range(H-1,-1,-1):
            _,g,B,C=self.records[i];um=lm+B*lw;uv=lv+C*lw
            port=(1-c.beta1)*um+2*(1-c.beta2)*g*uv
            lw=(1-c.lr*c.weight_decay)*lw+(self.hvp(i,port) if i>0 else 0)
            lm=c.beta1*um;lv=c.beta2*uv
        return lm.detach()
    def observer(self,x,H):return Observer(self,x,H)
    def close(self):self.graphs.clear()

class Observer:
    def __init__(self,tr,x,H):
        self.tr=tr;self.H=H;self.x=x
        self.w=(tr.records[H][0] if H<len(tr.records) else tr.final['theta']).detach().requires_grad_(True)
        z=call(tr.model,self.w,x);self.q=helmert(z.shape[1],z.device,z.dtype);self.norm=math.sqrt(len(x)*z.shape[1])
        self.y=(z@self.q).flatten()/self.norm
    def vjp(self,r):
        if r.ndim==2:return torch.stack([self.vjp(row) for row in r])
        w=torch.autograd.grad(self.y,self.w,r,retain_graph=True)[0].detach();return self.tr.reverse(w,self.H)
    def jvp(self,u):
        du=self.tr.forward(u,self.H);r=torch.zeros_like(self.y,requires_grad=True)
        wt=torch.autograd.grad(self.y,self.w,r,retain_graph=True,create_graph=True)[0]
        return torch.autograd.grad(wt,r,du,retain_graph=True)[0].detach()
    def close(self):del self.y

def exact_rows(tr,x,H,pulse=lambda:None):
    parts=[];count=0;total=len(x)*9;start=time.monotonic()
    for a in range(0,len(x),8):
        ob=tr.observer(x[a:a+8],H)
        for b in range(0,len(ob.y),4):
            pulse();n=min(4,len(ob.y)-b);r=torch.zeros(n,len(ob.y),device=x.device,dtype=x.dtype)
            r[torch.arange(n,device=x.device),torch.arange(b,b+n,device=x.device)]=1
            parts.append(ob.vjp(r)*math.sqrt(len(ob.x)/len(x)));count+=n
            if count==4 or count%72==0 or count==total:
                elapsed=time.monotonic()-start;print(f'Exact H{H}: {count}/{total} rows, {elapsed:.1f}s, estimated remaining {elapsed*(total-count)/count:.1f}s',flush=True)
        ob.close()
    A=torch.cat(parts);assert torch.isfinite(A).all();return A
def basis(A,rank=64):
    G=(A.double()@A.double().T).cpu().numpy();G=(G+G.T)/2
    w,E=np.linalg.eigh(G);w=w[::-1].copy();E=E[:,::-1].copy()
    assert w[0]>0 and w[-1]>=-1e-8*w[0];w=np.maximum(w,0)
    assert (w>w[0]*1e-8).sum()>=rank,'Declared rank is not numerically resolved'
    C=E[:,:rank]/np.sqrt(w[:rank])[None,:]
    U=(A.double().T@torch.tensor(C,device=A.device)).to(A.dtype)
    orth=float((U.double().T@U.double()-torch.eye(rank,device=A.device,dtype=torch.float64)).abs().max());assert orth<2e-5
    return U,dict(gram=G,spectrum=w,coefficients=C,orthogonality_max_error=np.asarray(orth))
