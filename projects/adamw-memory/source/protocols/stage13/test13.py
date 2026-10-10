"""Engineering tests. Synthetic inputs are never research observations."""
import tempfile,unittest,math,json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from horizon import Trainer,flat,helmert,restore,slots,step,call
from operators import Bank,rs_basis
from archive_io import Campaign,verify
from audit13 import decode,metrics

def config():return SimpleNamespace(lr=.003,beta1=.9,beta2=.99,eps=1e-6,weight_decay=.01)
class NumericalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):torch.set_num_threads(2)
    def test_full_state_tangent_against_differentiable_unroll(self):
        torch.manual_seed(44);c=config();md=nn.Sequential(nn.Linear(3,4),nn.Tanh(),nn.Linear(4,3)).double();P=len(flat(md));state=dict(theta=flat(md),m=torch.randn(P,dtype=torch.double)*.02,v=torch.rand(P,dtype=torch.double)*.03+.01,clock=50)
        bs=[(torch.randn(4,3,dtype=torch.double),torch.randint(3,(4,))) for _ in range(3)];rx=torch.randn(5,3,dtype=torch.double)
        tr=Trainer(md,state,bs,c);b=Bank(tr,rx,3,chunk=2);u=torch.randn(P,dtype=torch.double);r=torch.randn(b.outputs,dtype=torch.double)
        def unroll(m0):
            w=state['theta'].clone().requires_grad_(True);m=m0;v=state['v'];t=state['clock']
            for x,y in bs:
                g=torch.autograd.grad(F.cross_entropy(call(md,w,x),y),w,create_graph=True)[0];t+=1;m=c.beta1*m+(1-c.beta1)*g;v=c.beta2*v+(1-c.beta2)*g*g
                w=(1-c.lr*c.weight_decay)*w-c.lr*(m/(1-c.beta1**t))/(torch.sqrt(v/(1-c.beta2**t))+c.eps)
            return (call(md,w,rx)@helmert(3,rx.device,rx.dtype)).flatten()/math.sqrt(len(rx)*3)
        _,j=torch.autograd.functional.jvp(unroll,state['m'].clone().requires_grad_(True),u)
        self.assertLess(float((j-b.jvp(u)).norm()/j.norm()),1e-9)
        m0=state['m'].clone().requires_grad_(True);v=torch.autograd.grad(unroll(m0),m0,r)[0]
        self.assertLess(float((v-b.vjp(r)).norm()/v.norm()),1e-9)
        self.assertLess(abs(float(j@r-u@v)),1e-10)
        ob=tr.observer(rx,3);self.assertTrue(torch.allclose(b.jvp(u),ob.jvp(u),atol=1e-12,rtol=1e-10));ob.close();b.close();tr.close()
    def test_randomized_basis_exact_finite_matrix(self):
        torch.manual_seed(7);A=torch.randn(20,30,dtype=torch.double)
        class Matrix:
            outputs=20;parameters=30;device=torch.device('cpu');dtype=torch.double
            def jvp(self,u):return A@u
            def vjp(self,r):return A.T@r
        U,info=rs_basis(Matrix(),20,8,13,1)
        V=torch.linalg.svd(A,full_matrices=False).Vh[:8].T
        self.assertLess(float((U@U.T-V@V.T).norm()),1e-9)
        self.assertTrue(np.allclose(info['ritz_spectrum'][:8],torch.linalg.svdvals(A)[:8].numpy()**2,rtol=1e-10))
    def test_100_class_chart(self):
        Q=helmert(100,'cpu',torch.double).numpy();self.assertTrue(np.allclose(Q.T@Q,np.eye(99),atol=1e-13));self.assertLess(abs(Q.sum(0)).max(),1e-13)
        rng=np.random.default_rng(1);z=rng.normal(size=(7,100));phi=(z@Q).ravel()/math.sqrt(700);self.assertTrue(np.allclose(decode(phi,7,100),z-z.mean(1,keepdims=True)))
        self.assertAlmostEqual(metrics(z,z)['relative_prediction_error'],0.)
    def test_resnet_native_finite_difference(self):
        from models import ResNet18GN
        torch.manual_seed(81);c=config();md=ResNet18GN(3,2).double();P=len(flat(md));state=dict(theta=flat(md),m=torch.randn(P,dtype=torch.double)*.01,v=torch.rand(P,dtype=torch.double)*.01+.01,clock=50)
        bs=[(torch.randn(2,3,16,16,dtype=torch.double),torch.tensor([0,2])) for _ in range(3)];rx=torch.randn(2,3,16,16,dtype=torch.double);u=torch.randn(P,dtype=torch.double);u/=u.norm();alpha=1e-5
        tr=Trainer(md,state,bs,c);b=Bank(tr,rx,3,chunk=1);prediction=b.jvp(alpha*u);vals=[]
        for sign in (-1,1):
            m,o=restore(md,dict(state,m=state['m']+sign*alpha*u),c)
            for x,y in bs:step(m,o,x,y)
            vals.append((m(rx)@helmert(3,'cpu',torch.double)).detach().flatten()/math.sqrt(6))
        actual=(vals[1]-vals[0])/2;self.assertLess(float((prediction-actual).norm()/actual.norm()),1e-5);b.close();tr.close()
    def test_release_width32_float32_native_duality_and_fd(self):
        from models import ResNet18GN
        from runner13 import Config
        c=Config();torch.manual_seed(913);md=ResNet18GN(100,c.width);P=len(flat(md))
        state=dict(theta=flat(md),m=torch.randn(P)*.01,v=torch.rand(P)*.01+.01,clock=c.train_steps)
        bs=[(torch.randn(2,3,32,32),torch.tensor([0,99])) for _ in range(3)];rx=torch.randn(3,3,32,32);u=torch.randn(P);u/=u.norm();alpha=c.relative_displacement*state['m'].norm()
        tr=Trainer(md,state,bs,c);b=Bank(tr,rx,3,chunk=2);prediction=b.jvp(alpha*u);r=torch.randn(b.outputs)
        lhs=float(b.jvp(u).double()@r.double());rhs=float(u.double()@b.vjp(r).double())
        self.assertLess(abs(lhs-rhs)/max(abs(lhs),abs(rhs),1e-12),.005)
        vals=[]
        for sign in (-1,1):
            m,o=restore(md,dict(state,m=state['m']+sign*alpha*u),c)
            for x,y in bs:step(m,o,x,y)
            vals.append((m(rx)@helmert(100,'cpu',torch.float32)).detach().flatten()/math.sqrt(300))
        actual=(vals[1].double()-vals[0].double())/2
        self.assertLess(float((prediction.double()-actual).norm()/actual.norm()),c.derivative_error_max);b.close();tr.close()
    def test_checkpoint_fallback_identity_and_final_filter(self):
        with tempfile.TemporaryDirectory() as t:
            drive=Path(t)/'drive';local=Path(t)/'local';ident={'id':13};camp=Campaign(drive,local,ident);camp.activate();u=local/'units'/'test';u.mkdir(parents=True);(u/'value.json').write_text('{"n":1}');(u/'state.resume.npz').write_bytes(b'x');camp.checkpoint(True)
            (u/'value.json').write_text('{"n":2}');camp.checkpoint(True);camp.lease.release();(drive/'CHECKPOINT.zip').write_bytes(b'bad')
            c2=Campaign(drive,local,ident);self.assertEqual(c2.activate(),'CHECKPOINT');self.assertEqual(json.loads((u/'value.json').read_text())['n'],1)
            dest=c2.finish();m=verify(dest,ident,'FINISHED');self.assertFalse(any(x['path'].endswith('.resume.npz') for x in m['files']));c2.lease.release()
            bad=Campaign(drive,local,{'id':14});self.assertRaises(RuntimeError,bad.activate)
if __name__=='__main__':unittest.main()
