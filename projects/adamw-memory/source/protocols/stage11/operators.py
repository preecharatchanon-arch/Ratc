"""Matrix-free one-update moment operator. Fitting never sees historical/future effects."""
import math,numpy as np,torch
from torch.func import functional_call,jvp

def flat(model):return torch.cat([p.detach().reshape(-1) for p in model.parameters()])

def functional_logits(model,theta,x):
    params={};at=0
    for name,p in model.named_parameters():
        params[name]=theta[at:at+p.numel()].view_as(p);at+=p.numel()
    return functional_call(model,params,(x,),strict=True)

class Operator:
    def __init__(self,model,theta,D,x,pulse):
        self.model=model.eval();self.theta=theta.detach().requires_grad_(True);self.D=D.detach();self.x=x;self.pulse=pulse
        self.y=self.phi(self.theta);self.outputs=self.y.numel();self.parameters=theta.numel()
    def phi(self,theta):
        # GN/LN have no batch coupling; chunking does not change the declared operator.
        out=[]
        for i in range(0,len(self.x),64):
            z=functional_logits(self.model,theta,self.x[i:i+64]);out.append(z-z.mean(-1,keepdim=True))
        return torch.cat(out).reshape(-1)/math.sqrt(len(self.x)*out[0].shape[-1])
    def vjp(self,r):
        self.pulse();return (torch.autograd.grad(self.y,self.theta,r,retain_graph=True)[0]*self.D).detach()
    def jvp(self,v):
        self.pulse();return jvp(self.phi,(self.theta,),(self.D*v,))[1].detach()
    def close(self):del self.y

def rademacher(n,seed,device):
    g=torch.Generator(device='cpu').manual_seed(int(seed))
    return (torch.randint(0,2,(n,),generator=g,dtype=torch.int64)*2-1).to(device=device,dtype=torch.float32)

def orthonormal(Y):
    norms=torch.linalg.vector_norm(Y,dim=0)
    good=norms>norms.max()*1e-8
    if not good.any():raise RuntimeError('Zero/invalid fitted operator')
    Q=torch.linalg.qr(Y[:,good]/norms[good],mode='reduced')[0]
    eye=torch.eye(Q.shape[1],device=Q.device,dtype=torch.float64)
    gram=Q.double().T@Q.double()
    # Tall FP32 Householder QR can accumulate norm error on million-row matrices.
    # Recondition its already near-orthogonal Q, never the ill-conditioned original
    # sketch Gram matrix. This preserves the fitted span and checks the result anew.
    initial_error=float(torch.max(abs(gram-eye)))
    if initial_error>5e-5:
        if initial_error>.05:raise RuntimeError('Grossly inaccurate QR basis')
        L=torch.linalg.cholesky((gram+gram.T)/2)
        correction=torch.linalg.solve_triangular(L,eye,upper=False).T.to(Q.dtype)
        Q=Q@correction;gram=Q.double().T@Q.double()
    error=float(torch.max(abs(gram-eye)))
    if error>5e-5:raise RuntimeError('Subspace QR failed orthogonality check')
    return Q,error

def estimate(op,probes,powers,base_seed,max_rank=64):
    Y=torch.empty(op.parameters,probes,device=op.theta.device)
    initial_norms=[]
    for j in range(probes):
        z=op.vjp(rademacher(op.outputs,base_seed+j,op.theta.device));Y[:,j]=z;initial_norms.append(float(torch.dot(z.double(),z.double())))
        if (j+1)%32==0:print('  fitted VJP probes',j+1,'/',probes,flush=True)
    Q,error=orthonormal(Y);del Y
    for power in range(powers):
        Z=torch.empty_like(Q)
        for j in range(Q.shape[1]):Z[:,j]=op.vjp(op.jvp(Q[:,j]))
        Q,new_error=orthonormal(Z);error=max(error,new_error);del Z
        print('  subspace iteration',power+1,'/',powers,flush=True)
    F=torch.stack([op.jvp(Q[:,j]) for j in range(Q.shape[1])],1)
    gram=(F.double().T@F.double()).cpu().numpy();del F
    w,E=np.linalg.eigh((gram+gram.T)/2);w=w[::-1].copy();E=E[:,::-1].copy();valid=w>max(w[0],1e-30)*1e-8
    n=min(max_rank,int(valid.sum()))
    if n==0:raise RuntimeError('No numerically resolved right-subspace directions')
    U=(Q@torch.tensor(E[:,:n],device=Q.device,dtype=Q.dtype)).detach();del Q
    return U,{'ritz_values':w,'fit_projected_gram':gram,'initial_fit_trace_samples':np.asarray(initial_norms),
       'orthogonality_max_error':error,'actual_rank':n,'probes':probes,'power_iterations':powers,
       'scope':'finite-anchor randomized right subspace; Ritz values are not a complete/global spectrum'}

def independent_trace(op,bases,probes,base_seed):
    norms=[];coeff={name:[] for name in bases}
    for j in range(probes):
        g=op.vjp(rademacher(op.outputs,base_seed+j,op.theta.device));gd=g.double();norms.append(float(torch.dot(gd,gd)))
        for name,U in bases.items():coeff[name].append((U.double().T@gd).cpu().numpy())
    return np.asarray(norms),{name:np.stack(rows) for name,rows in coeff.items()}

def subspace_distance(A,B,k):
    n=min(k,A.shape[1],B.shape[1]);cross=(A[:,:n].double().T@B[:,:n].double()).cpu().numpy()
    return {'requested_rank':k,'actual_rank':n,'normalized_chordal_distance':float(np.sqrt(max(0,n-np.square(cross).sum())/max(n,1))),
            'smallest_principal_cosine':float(np.linalg.svd(cross,compute_uv=False).min())}
