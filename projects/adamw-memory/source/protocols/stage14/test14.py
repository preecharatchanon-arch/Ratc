"""Engineering tests. Synthetic inputs are never research observations."""
import tempfile,unittest,math,json,inspect
from unittest.mock import patch
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
        from runner14 import Config
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
class MicrobatchTests(unittest.TestCase):
    def test_microbatch_matches_native_hessian_and_full_unroll(self):
        torch.manual_seed(73);c=config();c.hessian_microbatch=2
        md=nn.Sequential(nn.Linear(3,5),nn.Tanh(),nn.Linear(5,3)).double();p=len(flat(md))
        state=dict(theta=flat(md),m=torch.randn(p,dtype=torch.double)*.02,v=torch.rand(p,dtype=torch.double)+.1,clock=30)
        bs=[(torch.randn(7,3,dtype=torch.double),torch.randint(3,(7,))) for _ in range(3)]
        tr=Trainer(md,state,bs,c);u=torch.randn(p,dtype=torch.double)
        w=tr.records[1][0].detach().requires_grad_(True);x,y=bs[1]
        g=torch.autograd.grad(F.cross_entropy(call(md,w,x),y),w,create_graph=True)[0]
        h=torch.autograd.grad(g,w,u)[0]
        self.assertTrue(torch.allclose(h,tr.hvp(1,u),rtol=1e-10,atol=1e-12))
        self.assertFalse(hasattr(tr,'graphs'));tr.close()
    def test_production_batch128_resnet_hessian_microbatch32(self):
        from models import ResNet18GN
        from runner14 import Config
        from dataclasses import replace
        c=replace(Config(),lr=Config().future_lr);torch.manual_seed(831)
        md=ResNet18GN(100,c.width);p=len(flat(md));state=dict(theta=flat(md),m=torch.randn(p)*.01,v=torch.rand(p)*.01+.01,clock=8000)
        bs=[(torch.randn(128,3,32,32),torch.arange(128)%100) for _ in range(2)]
        tr=Trainer(md,state,bs,c);u=torch.randn(p);u/=u.norm();w=tr.records[1][0].detach().requires_grad_(True);x,y=bs[1]
        g=torch.autograd.grad(F.cross_entropy(call(md,w,x),y),w,create_graph=True)[0]
        h=torch.autograd.grad(g,w,u)[0].detach();mh=tr.hvp(1,u)
        self.assertLess(float((h-mh).norm()/h.norm()),2e-5)
        tr.close()
    def test_cached_hessian_equals_recomputed_and_close_releases(self):
        torch.manual_seed(85);c=config();c.hessian_microbatch=2;c.hessian_cache_cpu=True;c.hessian_cache_gib=.01
        md=nn.Sequential(nn.Linear(3,4),nn.Tanh(),nn.Linear(4,3)).double();p=len(flat(md))
        state=dict(theta=flat(md),m=torch.randn(p,dtype=torch.double)*.02,v=torch.rand(p,dtype=torch.double)+.1,clock=30)
        bs=[(torch.randn(5,3,dtype=torch.double),torch.randint(3,(5,))) for _ in range(2)]
        tr=Trainer(md,state,bs,c);u=torch.randn(p,dtype=torch.double);first=tr.hvp(1,u);second=tr.hvp(1,u)
        self.assertTrue(torch.equal(first,second));self.assertEqual(len(tr.cache),3)
        tr.cache_limit=0;tr.cache.clear();third=tr.hvp(1,u)
        self.assertTrue(torch.equal(first,third));tr.close();self.assertFalse(tr.cache)
    def test_stable_config_and_sign_test(self):
        from runner14 import Config,exact_sign_positive
        c=Config();self.assertEqual(len(c.seeds),8);self.assertEqual(c.future_batch,c.train_batch)
        self.assertEqual(c.fit_sizes,(256,));self.assertLess(c.future_lr,c.lr)
        self.assertEqual(exact_sign_positive([1]*8)['p_one_sided'],1/256)
        self.assertEqual(exact_sign_positive([0]*8)['p_one_sided'],1.)
class AuditAndPauseTests(unittest.TestCase):
    def test_one_sided_sign_test_counts_ties_conservatively(self):
        from runner14 import exact_sign_positive
        q=exact_sign_positive([1]*7+[0])
        self.assertEqual(q['n'],8);self.assertEqual(q['ties'],1)
        self.assertEqual(q['p_one_sided'],9/256)
        self.assertGreater(q['p_one_sided'],.025)
        self.assertRaises(RuntimeError,exact_sign_positive,[float('nan')])
    def test_six_hour_cap_defers_inside_operator_and_pauses_after(self):
        from runner14 import SessionClock,PauseRun,main
        clock=[0.];camp=SimpleNamespace(pulse=lambda:None)
        self.assertEqual(inspect.signature(main).parameters['session_hours'].default,6)
        timer=SessionClock(camp,6,clock=lambda:clock[0])
        with timer.atomic():
            clock[0]=6*3600+1;timer()
            self.assertEqual(timer.depth,1)
        self.assertEqual(timer.depth,0)
        self.assertRaises(PauseRun,timer)
        self.assertRaises(RuntimeError,SessionClock,camp,0)
    def test_unresolved_full_effect_stops_before_any_operator_fit(self):
        import runner14 as r
        from smoke14 import data
        from dataclasses import replace
        c=replace(r.Config(),fit_sizes=(8,),fit_horizon=2,future_steps=3,future_batch=4,ranks=(1,2))
        dm=data('CIFAR10');role=r.data13.roles(dm,14000,c.fit_sizes,4,4)
        class Dummy:
            def __init__(self,*a,**k):pass
            def close(self):pass
        calls=[];camp=SimpleNamespace(checkpoint=lambda force:calls.append(force))
        with tempfile.TemporaryDirectory() as td,patch.object(r,'Trainer',Dummy),patch.object(r,'qual',return_value={'passes':False}),patch.object(r,'rs_basis') as fit:
            unit=Path(td);self.assertRaises(RuntimeError,r.fit_phase,None,{},None,dm,14000,role,unit,{},c,camp,lambda:None)
            fit.assert_not_called();self.assertEqual(calls,[True])
            q=json.loads((unit/'QUALIFICATION.json').read_text());self.assertFalse(q['primary_valid']);self.assertEqual(set(q['paths']),{'0','1'})
    def test_alternate_validity_and_dataset_eligibility_are_separate(self):
        import audit13 as a,runner14 as r
        c=r.Config()
        def fake_unit(unit,c):
            ds=unit.name.rsplit('_',1)[0];valid=ds=='CIFAR10'
            keys={f'h{H}_n256_r16@{h}':{'projection_error':.4} for H in (1,16) for h in (16,64)}
            return {'training_quality':{'passes':True},'qualification':{'primary_valid':True},
                'paths':{'0':{'primary_derivatives_valid':True,'comparisons':keys},'1':{'primary_derivatives_valid':valid,'comparisons':keys}}}
        def fake_read(path):
            return {'primary_rank_valid':True} if str(path.name).startswith('quality_') else {'passes':True}
        with tempfile.TemporaryDirectory() as td:
            for ds in c.datasets:
                for seed in c.seeds:
                    u=Path(td)/'units'/f'{ds}_{seed}';u.mkdir(parents=True);(u/'COMPLETE.json').write_text('{}')
            with patch.object(a,'audit_unit',side_effect=fake_unit),patch.object(a,'read',side_effect=fake_read):
                report=a.audit_all(td,c)
            self.assertTrue(report['datasets']['CIFAR10']['scientific_valid'])
            self.assertFalse(report['datasets']['CIFAR100']['scientific_valid'])
            self.assertFalse(report['scientific_primary_valid'])
            self.assertNotIn('bank_growth_matched',report['datasets']['CIFAR10']['paths']['0'])
            self.assertIn('8 independent histories',report['interpretation'])
            def fake_load(path):
                name=path.name;sign=1 if '_plus' in name else -1
                path_id=int(path.parent.name[-1]);scale=1.
                if name.startswith('branch_h1_'):scale=.4
                elif name.startswith('branch_h16_'):scale=.9 if path_id==0 else .3
                return {'h16':sign*scale*np.array([[1.,-1.,0.],[0.,1.,-1.]])}
            with patch.object(r,'load',side_effect=fake_load):q=r.registered_analysis(td,c,report)
            self.assertTrue(q[0]['primary_pass']);self.assertFalse(q[1]['primary_pass'])
            self.assertTrue(q[0]['numerically_eligible']);self.assertFalse(q[1]['numerically_eligible'])
class OperatorResumeTests(unittest.TestCase):
    def test_column_resume_matches_uninterrupted_all_four_passes(self):
        from operators import rs_basis
        torch.manual_seed(97);A=torch.randn(10,14,dtype=torch.double)
        class Matrix:
            outputs=10;parameters=14;device=torch.device('cpu');dtype=torch.double;H=2
            def jvp(self,u):return A@u
            def vjp(self,r):return A.T@r
        baseline,info=rs_basis(Matrix(),8,3,719,1)
        class Interruption(RuntimeError):pass
        class Journal:
            def __init__(self,target):self.target=target;self.saved=None;self.count=0;self.stopped=False
            def load(self,key):
                if self.saved:
                    k,m,a=self.saved;assert k==key;return m,a
            def due(self):self.count+=1;return self.count==self.target and not self.stopped
            def save(self,key,meta,arrays):
                self.saved=(key.copy(),meta.copy(),{k:v.copy(order='K') for k,v in arrays.items()});self.stopped=True;raise Interruption()
        for position in (3,11,19,27,32):
            with self.subTest(position=position):
                j=Journal(position)
                self.assertRaises(Interruption,rs_basis,Matrix(),8,3,719,1,journal=j)
                result,other=rs_basis(Matrix(),8,3,719,1,journal=j)
                self.assertTrue(torch.equal(result,baseline))
                self.assertTrue(np.array_equal(other['ritz_gram'],info['ritz_gram']))
                self.assertTrue(np.array_equal(other['ritz_spectrum'],info['ritz_spectrum']))
    def test_trace_resume_reuses_probes_and_generator_sequence(self):
        from operators import trace_probe
        torch.manual_seed(811);A=torch.randn(9,12,dtype=torch.double);U=torch.linalg.qr(torch.randn(12,3,dtype=torch.double)).Q
        class Matrix:
            outputs=9;parameters=12;device=torch.device('cpu');dtype=torch.double;H=2
            def jvp(self,u):return A@u
            def vjp(self,r):return A.T@r
        expected=trace_probe(Matrix(),U,7,832)
        class Interrupted(RuntimeError):pass
        class Journal:
            saved=None;count=0
            def load(self,key):return self.saved
            def due(self):self.count+=1;return self.count==4
            def save(self,key,meta,arrays):self.saved=(meta,arrays);raise Interrupted()
        j=Journal();self.assertRaises(Interrupted,trace_probe,Matrix(),U,7,832,journal=j)
        got=trace_probe(Matrix(),U,7,832,journal=j)
        for k in expected:self.assertTrue(np.array_equal(got[k],expected[k]))
    def test_real_operator_journal_survives_archive_restore(self):
        from runner14 import OperatorJournal
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);camp=Campaign(root/'drive',root/'local',{'resume_test':1});camp.activate()
            j=OperatorJournal(root/'local'/'units'/'U'/'working.resume.npz',camp)
            self.assertEqual(camp.checkpoint_seconds,7200);self.assertFalse(j.due())
            camp.last_checkpoint-=7201;self.assertTrue(j.due())
            q=np.asfortranarray(np.arange(24,dtype=np.float32).reshape(6,4));key={'matrix':1};meta={'at':3}
            j.save(key,meta,{'Q':q});camp.lease.release()
            restored=Campaign(root/'drive',root/'other',{'resume_test':1});self.assertEqual(restored.activate(),'CHECKPOINT')
            j2=OperatorJournal(root/'other'/'units'/'U'/'working.resume.npz',restored);m,a=j2.load(key)
            self.assertEqual(m,meta);self.assertTrue(np.array_equal(a['Q'],q));self.assertTrue(a['Q'].flags.f_contiguous)
            self.assertRaises(RuntimeError,j2.load,{'matrix':2});restored.lease.release()
class CompatibilityTests(unittest.TestCase):
    def test_only_exact_legacy_r2_config_and_environment_are_accepted(self):
        import runner14 as r
        from dataclasses import asdict
        captured=[]
        class Finished:
            def __init__(self,drive,local,identity):
                captured.append(identity);self.lease=SimpleNamespace(release=lambda:None)
            def activate(self):return 'FINISHED'
            def pulse(self):pass
        with tempfile.TemporaryDirectory() as td,patch.object(r,'Campaign',Finished):
            p=Path(td)/'IDENTITY.json'
            old=dict(version=r.VERSION,config=json.loads(json.dumps(asdict(r.Config()))),environment=r.environment(torch.device('cpu')),
                source_sha256='9daa2fc0181d7f3e373e1de3be7c03bb2a251a22f4e1edcceecf2153ffc1964a')
            p.write_text(json.dumps(old));r.main(td,device_name='cpu')
            self.assertEqual(captured[-1],old)
            old['config']['lr']=.002;p.write_text(json.dumps(old))
            self.assertRaises(RuntimeError,r.main,td,device_name='cpu')
            old['config']['lr']=.001;old['environment']['torch']='different';p.write_text(json.dumps(old))
            self.assertRaises(RuntimeError,r.main,td,device_name='cpu')
    def test_large_working_checkpoint_keeps_compact_predecessor(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);camp=Campaign(root/'drive',root/'local',{'test':1});camp.activate()
            f=root/'local'/'units'/'U'/'value.json';f.parent.mkdir(parents=True)
            for n in (1,2):f.write_text(json.dumps({'n':n}));camp.checkpoint(True)
            previous=root/'drive'/'CHECKPOINT_PREVIOUS.zip';digest=__import__('hashlib').sha256(previous.read_bytes()).hexdigest()
            camp.fallback_max_bytes=1;f.write_text(json.dumps({'n':3}));camp.checkpoint(True)
            self.assertEqual(__import__('hashlib').sha256(previous.read_bytes()).hexdigest(),digest)
            with zipfile.ZipFile(root/'drive'/'CHECKPOINT.zip') as z:self.assertEqual(json.loads(z.read('units/U/value.json'))['n'],3)
            camp.lease.release()
if __name__=='__main__':unittest.main()
