"""Actual CPU engineering tests; fixture outputs are not research evidence."""
import copy,json,tempfile,time,unittest
from dataclasses import replace,asdict
from pathlib import Path
import numpy as np
import torch
from torch import nn
import runner,audit,operators
from archive_io import Campaign,verify,sha

class Tiny(nn.Module):
    def __init__(self,c=10):
        super().__init__();self.conv=nn.Conv2d(3,4,1);self.gn=nn.GroupNorm(2,4);self.head=nn.Linear(4,c)
    def forward(self,x):return self.head(torch.tanh(self.gn(self.conv(x))).mean((2,3)))

def fixture_data(name,root,device,cfg):
    g=torch.Generator().manual_seed(703)
    X=torch.randn(240,3,32,32,generator=g).to(device);TX=torch.randn(100,3,32,32,generator=g).to(device)
    return {'name':name,'X':X,'Y':(torch.arange(240)%10).to(device),'TX':TX,'TY':(torch.arange(100)%10).to(device),
      'train_ids':np.arange(120),'cal_ids':np.arange(120,240),'response_ids':np.arange(20),'test_ids':np.arange(20,100),
      'fingerprints':{'engineering_fixture':'RGB32_fixed_seed703_v1'}}

def known_spectrum():
    g=torch.Generator().manual_seed(140);L=torch.linalg.qr(torch.randn(30,10,generator=g))[0];R=torch.linalg.qr(torch.randn(70,10,generator=g))[0]
    values=torch.tensor([10.,8.,5.,2.,1.,.5,.3,.2,.1,.05]);A=(L*values)@R.T
    class Known:
        theta=torch.zeros(70);outputs=30;parameters=70
        def jvp(self,v):return A@v
        def vjp(self,r):return A.T@r
    U,rec=operators.estimate(Known(),20,2,91,10)
    principal=torch.linalg.svdvals(U[:,:3].double().T@R[:,:3].double()).numpy()
    assert principal.min()>.99999
    assert np.allclose(rec['ritz_values'][:10],values.numpy()**2,rtol=2e-4,atol=1e-5)
    norms,co=operators.independent_trace(Known(),{'main':U},128,554)
    curves=audit.capture(norms,co['main']);assert np.isclose(curves[-1]['paired_hutchinson_capture'],1.,rtol=1e-5)
    return {'known_right_subspace_minimum_principal_cosine':float(principal.min()),'full_capture':curves[-1]['paired_hutchinson_capture'],
            'ritz_spectrum_matches_prescribed':True}

def adamw_formula():
    cfg=replace(runner.Config(),gradient_clip=.3);torch.manual_seed(330)
    md=nn.Linear(5,3).double();opt=runner.optimizer(md,cfg);x=torch.randn(7,5,dtype=torch.float64);y=torch.arange(7)%3
    for _ in range(3):runner.train_step(md,opt,x,y,cfg)
    theta,m,v,t,_=runner.vectors(md,opt);snap=runner.snapshot(md,opt);g,_=runner.gradient(md,x,y,cfg)
    D=-cfg.lr*cfg.beta1/((1-cfg.beta1**(t+1))*(np.sqrt((cfg.beta2*v+(1-cfg.beta2)*g*g)/(1-cfg.beta2**(t+1)))+cfg.eps))
    h=np.random.default_rng(441).normal(size=len(m));h/=np.linalg.norm(h);delta=1e-5*np.linalg.norm(m);out=[]
    for sign in (-1,1):
        clone=copy.deepcopy(md);oo=runner.optimizer(clone,cfg);oo.load_state_dict(copy.deepcopy(snap['optimizer']))
        runner.install(clone,oo,m+sign*delta*h,v,t);th,m2,v2,t2,_=runner.vectors(clone,oo)
        assert np.array_equal(theta,th) and np.array_equal(v,v2) and t2==t
        runner.train_step(clone,oo,x,y,cfg);out.append(np.concatenate([p.detach().numpy().reshape(-1) for p in clone.parameters()]))
    fd=(out[1]-out[0])/(2*delta);error=float(np.linalg.norm(fd-D*h)/np.linalg.norm(D*h));assert error<1e-7
    return {'double_precision_first_moment_derivative_relative_error':error,'clipped_gradient_and_weight_decay_included':True}

def integration():
    cfg=replace(runner.Config(),datasets=('CIFAR10',),architectures=('ResNet18GN',),models_per_cell=1,
      total_steps_cifar10=8,batch_size=8,calibration_n=120,first_batch_n=20,fit_small_n=20,fit_large_n=40,
      independent_anchor_n=40,response_n=20,fit_small_probes=6,fit_large_probes=10,trace_probes=12,max_rank=4,
      future_steps=20,horizons=(0,1,4,16,20),warmup_steps=2,bootstrap_draws=100,session_hours=.5)
    original_build=runner.build;original_branch=runner.continue_branch;original_geometry=runner.geometry
    runner.build=lambda arch,c:Tiny(c)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);drive=root/'drive';local=root/'local';attempt=[False]
            def injected(*args,**kwargs):
                label=args[7];path=args[8]
                if label=='full_plus' and path==0 and not attempt[0]:
                    attempt[0]=True;real_guard=args[-1];calls=[0]
                    def interrupt():
                        real_guard();calls[0]+=1
                        if calls[0]==18:raise RuntimeError('injected_mid_future_disconnect')
                    args=list(args);args[-1]=interrupt
                return original_branch(*args,**kwargs)
            runner.continue_branch=injected
            try:runner.run(drive,local,'unused',cfg,'cpu',fixture_data,qualification=False)
            except RuntimeError as e:assert 'injected_mid_future' in str(e)
            else:raise AssertionError('Interruption was not exercised')
            unit=local/'units'/'CIFAR10_ResNet18GN_11000_t4';assert runner.load_pt(unit/'branch.pt')['completed']==16
            identity=json.loads((drive/'IDENTITY.json').read_text());verify(drive/'CHECKPOINT.zip',identity,'CHECKPOINT')
            assert not list(drive.glob('*.pt'))
            geom_hash=sha(unit/'geometry_raw.npz');runner.continue_branch=original_branch
            def changed_data(*args,**kwargs):
                d=fixture_data(*args,**kwargs);d['fingerprints']={'engineering_fixture':'changed_data'};return d
            try:runner.run(drive,local,'unused',cfg,'cpu',changed_data,qualification=False)
            except RuntimeError as e:assert 'Dataset bytes or role assignments changed' in str(e)
            else:raise AssertionError('Dataset identity changed across sessions')
            def ensure_not_refit(*args,**kwargs):
                if args[1].name.endswith('_t4'):
                    assert (args[1]/'directions.pt').exists();assert sha(args[1]/'geometry_raw.npz')==geom_hash
                return original_geometry(*args,**kwargs)
            runner.geometry=ensure_not_refit
            summary,finished=runner.run(drive,local,'unused',cfg,'cpu',fixture_data,qualification=False);runner.geometry=original_geometry
            assert summary['completed_cases']==2 and summary['independent_models']==1
            manifest=verify(finished,identity,'FINISHED');assert not any(e['path'].endswith('.pt') for e in manifest['files'])
            assert len(list(drive.glob('*.zip')))==1
            summary2,p2=runner.run(drive,local,'unused',cfg,'cpu',fixture_data,qualification=False)
            assert summary2==summary and sha(p2)==sha(finished)
            # A second uninterrupted campaign must produce exactly the same scientific raw arrays.
            other=root/'other';_,f2=runner.run(other/'drive',other/'local','unused',cfg,'cpu',fixture_data,qualification=False)
            for p in (local/'units').rglob('*.npz'):
                otherfile=other/'local'/p.relative_to(local)
                a,b=audit.load(p),audit.load(otherfile);assert set(a)==set(b)
                assert all(np.array_equal(a[k],b[k]) for k in a)
            # A stored result cannot change the reported estimand unnoticed.
            p=unit/'result.json';old=p.read_text();record=json.loads(old);record['captures']['anchor512_q128'][0]['paired_hutchinson_capture']+=.1;p.write_text(json.dumps(record))
            try:audit.audit_case(unit,asdict(cfg))
            except RuntimeError:pass
            else:raise AssertionError('Saved-data auditor accepted altered capture')
            p.write_text(old)
            changed=copy.deepcopy(identity);changed['version']='changed'
            try:Campaign(drive,root/'wrong',changed).activate()
            except RuntimeError:pass
            else:raise AssertionError('Changed campaign identity accepted')
            return {'actual_training_geometry_19_branches_two_paths_two_cuts':True,'mid_branch_resume_exactly_matches_uninterrupted':True,
               'committed_geometry_resumed_without_refit':True,'completed_campaign_no_training_replay':True,'saved_data_tampering_rejected':True,
               'changed_identity_rejected':True,'changed_dataset_rejected_before_training':True,'final_excludes_pt_and_prunes_verified_checkpoints':True,
               'scope':'Small synthetic RGB engineering fixture with an injected tiny network; not real CIFAR evidence.'}
    finally:runner.build=original_build;runner.continue_branch=original_branch;runner.geometry=original_geometry

def main():
    started=time.monotonic();runner.configure(torch.device('cpu'))
    result={'passed':True,'backend':'CPU','torch':str(torch.__version__),'torchvision':str(runner.torchvision.__version__),
      'real_backbones':runner.qualify(torch.device('cpu'),runner.Config()),'known_operator':known_spectrum(),
      'adamw_derivative':adamw_formula(),'integration':integration()}
    result['seconds']=time.monotonic()-started;return result

if __name__=='__main__':
    r=main();Path(__file__).with_name('CPU_VALIDATION.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
