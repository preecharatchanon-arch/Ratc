"""Chunked finite-horizon operator and validated randomized right subspaces.

Subspaces are approximate. Derivatives are full-state native AdamW derivatives.
"""
import math,time
import numpy as np
import torch
from horizon import Trainer

class Bank:
    def __init__(self,tr,x,H,chunk=32):
        self.tr=tr;self.H=H;self.observers=[tr.observer(x[a:a+chunk],H) for a in range(0,len(x),chunk)]
        self.scales=[math.sqrt(len(o.x)/len(x)) for o in self.observers]
        self.outputs=sum(len(o.y) for o in self.observers);self.device=x.device;self.dtype=x.dtype
        self.parameters=len(tr.records[0][0])
    def vjp(self,r):
        at=0;w=None
        for ob,scale in zip(self.observers,self.scales):
            n=len(ob.y);g=torch.autograd.grad(ob.y,ob.w,r[at:at+n]*scale,retain_graph=True)[0].detach();at+=n
            w=g if w is None else w+g
        return self.tr.reverse(w,self.H)
    def jvp(self,u):
        dw=self.tr.forward(u,self.H);parts=[]
        for ob,scale in zip(self.observers,self.scales):
            r=torch.zeros_like(ob.y,requires_grad=True)
            wt=torch.autograd.grad(ob.y,ob.w,r,create_graph=True,retain_graph=True)[0]
            parts.append(torch.autograd.grad(wt,r,dw,retain_graph=True)[0].detach()*scale)
        return torch.cat(parts)
    def close(self):
        for ob in self.observers:ob.close()
        self.observers.clear()

def gram_columns(Q):
    G=torch.zeros(Q.shape[1],Q.shape[1],dtype=torch.float64,device=Q.device)
    for a in range(0,len(Q),65536):
        q=Q[a:a+65536].double();G+=q.T@q
    return G
def ortho(Y):
    Q,R=torch.linalg.qr(Y,mode='reduced')
    err=float((gram_columns(Q)-torch.eye(Q.shape[1],device=Q.device,dtype=torch.float64)).abs().max())
    if err>2e-4:raise RuntimeError('Randomized range orthogonality failed')
    return Q,err
def rs_basis(bank,columns,rank,rng_seed,power=1,pulse=lambda:None):
    """Range of A^T, stabilized power iteration, Ritz SVD inside that range."""
    l=min(columns,bank.outputs,bank.parameters);gen=torch.Generator().manual_seed(rng_seed)
    Omega=torch.randn(bank.outputs,l,generator=gen).to(bank.device,bank.dtype)
    Y=None;start=time.monotonic()
    def report(label,j):
        if (j+1)%16==0 or j+1==l:
            elapsed=time.monotonic()-start;print(f'{label} {j+1}/{l}; elapsed {elapsed/60:.1f} min',flush=True)
    for j in range(l):
        pulse();v=bank.vjp(Omega[:,j])
        if Y is None:Y=torch.empty(len(v),l,device=bank.device,dtype=bank.dtype)
        Y[:,j]=v;report('range VJP',j)
    del Omega;Q,err=ortho(Y);del Y
    def apply_jvp(Q,label):
        out=[]
        for j in range(l):pulse();out.append(bank.jvp(Q[:,j]));report(label,j)
        return torch.stack(out,1)
    for k in range(power):
        Z=apply_jvp(Q,f'power{k+1} JVP');Z,_=ortho(Z)
        for j in range(l):
            pulse();Q[:,j]=bank.vjp(Z[:,j]);report(f'power{k+1} VJP',j)
        Q,e=ortho(Q);err=max(err,e);del Z
    B=apply_jvp(Q,'Ritz JVP')
    G=(B.double().T@B.double()).cpu().numpy();G=(G+G.T)/2
    vals,V=np.linalg.eigh(G);vals=vals[::-1].copy();V=V[:,::-1].copy();vals=np.maximum(vals,0)
    if vals[0]<=0 or (vals>vals[0]*1e-8).sum()<rank:raise RuntimeError('Requested rank not numerically resolved')
    U=Q@torch.tensor(V[:,:rank],device=bank.device,dtype=bank.dtype);del Q
    err=max(err,float((gram_columns(U)-torch.eye(rank,device=U.device,dtype=torch.float64)).abs().max()))
    if err>2e-4:raise RuntimeError('Randomized right basis orthogonality failed')
    return U,dict(ritz_gram=G,ritz_spectrum=vals,ritz_vectors=V,columns=np.asarray(l),power=np.asarray(power),
        rng_seed=np.asarray(rng_seed,dtype=np.int64),orthogonality_max_error=np.asarray(err),seconds=np.asarray(time.monotonic()-start))

def trace_probe(bank,U,probes,rng_seed,pulse=lambda:None):
    """Exact numerator by column JVP norms, independent Hutchinson trace denominator."""
    gen=torch.Generator().manual_seed(rng_seed);values=[]
    for j in range(probes):
        pulse();r=(torch.randint(0,2,(bank.outputs,),generator=gen)*2-1).to(bank.device,bank.dtype)
        v=bank.vjp(r);values.append(float(v.double().square().sum()))
        if (j+1)%32==0:print('held-out trace',j+1,'/',probes,flush=True)
    energy=[]
    for j in range(U.shape[1]):
        pulse();z=bank.jvp(U[:,j]);energy.append(float(z.double().square().sum()))
        if (j+1)%16==0:print('held-out basis actions',j+1,'/',U.shape[1],flush=True)
    return dict(trace_squared_norms=np.asarray(values),column_squared_norms=np.asarray(energy))
