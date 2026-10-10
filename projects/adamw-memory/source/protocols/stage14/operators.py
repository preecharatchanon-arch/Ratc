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
def rs_basis(bank,columns,rank,rng_seed,power=1,pulse=lambda:None,journal=None):
    """Same randomized operator arithmetic, with resumable column passes."""
    l=min(columns,bank.outputs,bank.parameters);gen=torch.Generator().manual_seed(rng_seed)
    Omega=torch.randn(bank.outputs,l,generator=gen).to(bank.device,bank.dtype)
    key=dict(outputs=bank.outputs,parameters=bank.parameters,columns=l,rank=rank,seed=rng_seed,power=power,dtype=str(bank.dtype))
    saved=journal.load(key) if journal else None
    start=time.monotonic();prior=0.;err=0.;phase='range';iteration=0;at=0;Q=None;Z=None;B=None;Y=None
    def tensor(x):return torch.from_numpy(x).to(device=bank.device,dtype=bank.dtype)
    if saved:
        meta,arr=saved;phase=meta['phase'];iteration=meta['iteration'];at=meta['at'];err=meta['err'];prior=meta['seconds']
        if phase=='range':
            Y=torch.empty(bank.parameters,l,device=bank.device,dtype=bank.dtype);Y[:,:at]=tensor(arr['Y'])
        elif phase=='power_vjp':
            Q=torch.empty_strided((bank.parameters,l),(1,bank.parameters),device=bank.device,dtype=bank.dtype);Q[:,:at]=tensor(arr['Q'])
            Z=tensor(arr['Z'])
        else:
            Q=tensor(arr['Q']);B=torch.empty(bank.outputs,l,device=bank.device,dtype=bank.dtype);B[:,:at]=tensor(arr['B'])
        print('RESUMING OPERATOR:',phase,'iteration',iteration,'completed columns',at,'/',l,flush=True)
    def report(label,j):
        if (j+1)%16==0 or j+1==l:
            elapsed=prior+time.monotonic()-start;print(f'{label} {j+1}/{l}; elapsed {elapsed/60:.1f} min',flush=True)
    def snapshot():
        if not journal or not journal.due():return
        meta=dict(phase=phase,iteration=iteration,at=at,err=err,seconds=prior+time.monotonic()-start)
        if phase=='range':arrays={'Y':Y[:,:at]}
        elif phase=='power_vjp':arrays={'Q':Q[:,:at],'Z':Z}
        else:arrays={'Q':Q,'B':B[:,:at]}
        journal.save(key,meta,{k:v.detach().cpu().numpy() for k,v in arrays.items()})
    if phase=='range':
        for j in range(at,l):
            pulse();v=bank.vjp(Omega[:,j])
            if Y is None:Y=torch.empty(len(v),l,device=bank.device,dtype=bank.dtype)
            Y[:,j]=v;at=j+1;report('range VJP',j);snapshot()
        Q,err=ortho(Y);del Y;Y=None;phase='power_jvp' if power else 'ritz';at=0
    del Omega
    while iteration<power:
        if phase=='power_jvp':
            if B is None:B=torch.empty(bank.outputs,l,device=bank.device,dtype=bank.dtype)
            for j in range(at,l):
                pulse();B[:,j]=bank.jvp(Q[:,j]);at=j+1;report(f'power{iteration+1} JVP',j);snapshot()
            Z,_=ortho(B);B=None;phase='power_vjp';at=0
        if phase=='power_vjp':
            for j in range(at,l):
                pulse();Q[:,j]=bank.vjp(Z[:,j]);at=j+1;report(f'power{iteration+1} VJP',j);snapshot()
            Q,e=ortho(Q);err=max(err,e);Z=None;iteration+=1;phase='power_jvp' if iteration<power else 'ritz';at=0
    if B is None:B=torch.empty(bank.outputs,l,device=bank.device,dtype=bank.dtype)
    for j in range(at,l):
        pulse();B[:,j]=bank.jvp(Q[:,j]);at=j+1;report('Ritz JVP',j);snapshot()
    G=(B.double().T@B.double()).cpu().numpy();G=(G+G.T)/2
    vals,V=np.linalg.eigh(G);vals=vals[::-1].copy();V=V[:,::-1].copy();vals=np.maximum(vals,0)
    if vals[0]<=0 or (vals>vals[0]*1e-8).sum()<rank:raise RuntimeError('Requested rank not numerically resolved')
    U=Q@torch.tensor(V[:,:rank],device=bank.device,dtype=bank.dtype);del Q
    err=max(err,float((gram_columns(U)-torch.eye(rank,device=U.device,dtype=torch.float64)).abs().max()))
    if err>2e-4:raise RuntimeError('Randomized right basis orthogonality failed')
    return U,dict(ritz_gram=G,ritz_spectrum=vals,ritz_vectors=V,columns=np.asarray(l),power=np.asarray(power),
        rng_seed=np.asarray(rng_seed,dtype=np.int64),orthogonality_max_error=np.asarray(err),seconds=np.asarray(prior+time.monotonic()-start))

def trace_probe(bank,U,probes,rng_seed,pulse=lambda:None,journal=None):
    """Exact numerator by column JVP norms, independent Hutchinson trace denominator."""
    gen=torch.Generator().manual_seed(rng_seed);values=[];energy=[]
    key=dict(kind='trace',H=bank.H,outputs=bank.outputs,parameters=bank.parameters,probes=probes,seed=rng_seed,rank=U.shape[1])
    restored=journal.load(key) if journal else None
    if restored:
        _,arr=restored;values=arr['trace_squared_norms'].tolist();energy=arr['column_squared_norms'].tolist()
        print('RESTORED TRACE:',len(values),'probes and',len(energy),'basis actions',flush=True)
    def snapshot():
        if journal and journal.due():journal.save(key,{},dict(trace_squared_norms=np.asarray(values),column_squared_norms=np.asarray(energy)))
    for j in range(probes):
        r=(torch.randint(0,2,(bank.outputs,),generator=gen)*2-1).to(bank.device,bank.dtype)
        if j<len(values):continue
        pulse();v=bank.vjp(r);values.append(float(v.double().square().sum()));snapshot()
        if (j+1)%32==0:print('held-out trace',j+1,'/',probes,flush=True)
    for j in range(U.shape[1]):
        if j<len(energy):continue
        pulse();z=bank.jvp(U[:,j]);energy.append(float(z.double().square().sum()));snapshot()
        if (j+1)%16==0:print('held-out basis actions',j+1,'/',U.shape[1],flush=True)
    return dict(trace_squared_norms=np.asarray(values),column_squared_norms=np.asarray(energy))
