import tempfile,unittest,json,zipfile
from pathlib import Path
from types import SimpleNamespace
import torch,numpy as np
from torch import nn
from horizon import *
from archive_io import Campaign,verify,write_json
def cfg():return SimpleNamespace(lr=.003,beta1=.9,beta2=.999,eps=1e-8,weight_decay=.01)
def fixture():
    torch.manual_seed(43);m=nn.Sequential(nn.Linear(3,5),nn.Tanh(),nn.Linear(5,3)).double();w=flat(m)
    st=dict(theta=w,m=torch.randn_like(w)*.02,v=torch.rand_like(w)*.005+.001,clock=11)
    bs=[(torch.randn(6,3,dtype=w.dtype),torch.arange(6)%3) for i in range(4)];x=torch.randn(5,3,dtype=w.dtype);return m,st,bs,x
def unroll(md,st,bs,c,m):
    w=st['theta'];v=st['v'];t=st['clock']
    for x,y in bs:
        w=w.requires_grad_(True);g=torch.autograd.grad(F.cross_entropy(call(md,w,x),y),w,create_graph=True)[0]
        m=c.beta1*m+(1-c.beta1)*g;v=c.beta2*v+(1-c.beta2)*g*g;t+=1
        w=w*(1-c.lr*c.weight_decay)-c.lr*(m/(1-c.beta1**t))/(torch.sqrt(v/(1-c.beta2**t))+c.eps)
    return w
class MathTests(unittest.TestCase):
    def setUp(self):torch.set_num_threads(2)
    def test_full_unroll_and_adjoint(self):
        md,st,bs,x=fixture();c=cfg();tr=Trainer(md,st,bs,c);q=helmert(3,'cpu',x.dtype)
        for H in (1,2,4):
            fn=lambda m:(call(md,unroll(md,st,bs[:H],c,m),x)@q).flatten()/math.sqrt(len(x)*3)
            A=torch.autograd.functional.jacobian(fn,st['m']);ob=tr.observer(x,H);u=torch.randn_like(st['m']);r=torch.randn_like(ob.y)
            self.assertLess(float((ob.jvp(u)-A@u).norm()/(A@u).norm()),1e-9)
            self.assertLess(float((ob.vjp(r)-A.T@r).norm()/(A.T@r).norm()),1e-9)
            self.assertLess(abs(float((ob.jvp(u)*r).sum()-(u*ob.vjp(r)).sum())),1e-10);ob.close()
        self.assertTrue(torch.allclose(tr.final['theta'],unroll(md,st,bs,c,st['m']),atol=2e-15,rtol=1e-12));tr.close()
    def test_finite_interventions(self):
        md,st,bs,x=fixture();c=cfg();tr=Trainer(md,st,bs,c);u=torch.randn_like(st['m']);u/=u.norm();eps=1e-6;out=[]
        for sign in (-1,1):
            m,op=restore(md,dict(st,m=st['m']+sign*eps*u),c)
            for bx,by in bs:step(m,op,bx,by)
            out.append(m(x).detach())
        ob=tr.observer(x,4);fd=((out[1]-out[0])@ob.q).flatten()/(2*eps*ob.norm)
        self.assertLess(float((fd-ob.jvp(u)).norm()/ob.jvp(u).norm()),1e-6);tr.close()
    def test_known_spectrum_and_center_chart(self):
        q=helmert(10,'cpu',torch.float64);self.assertTrue(torch.allclose(q.T@q,torch.eye(9,dtype=q.dtype),atol=1e-14))
        torch.manual_seed(45);U=torch.linalg.qr(torch.randn(12,5,dtype=q.dtype)).Q;V=torch.linalg.qr(torch.randn(9,5,dtype=q.dtype)).Q
        A=U@torch.diag(torch.tensor([5.,4.,3.,2.,1.],dtype=q.dtype))@V.T;B,raw=basis(A,3)
        self.assertLess(float((B@B.T-V[:,:3]@V[:,:3].T).norm()),1e-10);self.assertAlmostEqual(raw['spectrum'][:3].sum()/raw['spectrum'].sum(),50/55)
    def test_groupnorm_actual_architecture(self):
        from parent10 import ConvGN
        torch.manual_seed(3);md=ConvGN();w=flat(md);st=dict(theta=w,m=torch.randn_like(w)*1e-4,v=torch.ones_like(w)*.001,clock=2000)
        bs=[(torch.randn(2,3,32,32),torch.tensor([1,3])) for _ in range(3)];tr=Trainer(md,st,bs,cfg());ob=tr.observer(bs[0][0],3)
        u=torch.randn_like(w);u/=u.norm();r=torch.randn_like(ob.y);lhs=float((ob.jvp(u).double()*r.double()).sum());rhs=float((u.double()*ob.vjp(r).double()).sum())
        self.assertLess(abs(lhs-rhs)/max(abs(lhs),abs(rhs)),.003)
        R=torch.stack([r,-r]);self.assertTrue(torch.allclose(ob.vjp(R)[0],ob.vjp(r)));tr.close()
class StorageTests(unittest.TestCase):
    def test_resume_predecessor_and_final(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ident={'frozen':1};c=Campaign(root/'drive',root/'local',ident);c.activate()
            write_json(c.local/'units/x.json',{'n':1});c.checkpoint(True);write_json(c.local/'units/x.json',{'n':2});c.checkpoint(True);c.lease.release()
            (c.drive/'CHECKPOINT.zip').write_bytes(b'bad');c=Campaign(root/'drive',root/'local',ident);self.assertEqual(c.activate(),'CHECKPOINT')
            self.assertEqual(json.loads((c.local/'units/x.json').read_text())['n'],1)
            (c.local/'units/basis.resume.npz').write_bytes(b'temporary');f=c.finish();manifest=verify(f,ident,'FINISHED')
            self.assertNotIn('units/basis.resume.npz',[e['path'] for e in manifest['files']]);self.assertFalse((c.drive/'CHECKPOINT.zip').exists());c.lease.release()
    def test_identity_and_lease(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);c=Campaign(root/'d',root/'l',{'x':1});c.activate()
            with self.assertRaises(RuntimeError):Campaign(root/'d',root/'other',{'x':1}).activate()
            c.lease.release()
            with self.assertRaises(RuntimeError):Campaign(root/'d',root/'l',{'x':2}).activate()
    def test_unsafe_zip_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            f=Path(temp)/'bad.zip'
            with zipfile.ZipFile(f,'w') as z:z.writestr('../bad','x')
            with self.assertRaises(RuntimeError):verify(f,{'x':1})
if __name__=='__main__':unittest.main()
