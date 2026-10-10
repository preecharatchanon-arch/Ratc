"""Tiny end-to-end engineering integration, not research observations."""
import tempfile,json,hashlib
from pathlib import Path
from dataclasses import replace
import numpy as np,torch
import runner14 as r

def data(name):
    torch.manual_seed(715);N=28;T=10;x=torch.randn(N,3,32,32);y=torch.arange(N)%3;tx=torch.randn(T,3,32,32);ty=torch.arange(T)%3
    return dict(name=name,X=x,Y=y,TX=tx,TY=ty,labels=y.numpy(),test_labels=ty.numpy(),train_ids=np.arange(8),cal_ids=np.arange(8,N),
        response_ids=np.arange(3),test_ids=np.arange(3,T),classes=3,fingerprints={'synthetic':'engineering'})
if __name__=='__main__':
    c=replace(r.Config(),datasets=('CIFAR10','CIFAR100'),seeds=(14000,14001),width=2,train_steps=6,donor_step=4,train_batch=4,
        future_batch=4,future_steps=3,horizons=(0,1,2,3),fit_horizon=2,fit_sizes=(8,),heldout_n=4,first_n=4,response_n=3,
        ranks=(1,2),sketch_columns=4,quality_columns=5,quality_energy_tolerance=1.,quality_response_tolerance=2.,
        trace_probes=3,checkpoint_train_interval=3,resolution_floor=0.,derivative_error_max=1.,cut_floor_cifar10=0.,cut_floor_cifar100=0.,
        max_baseline_accuracy_drop=1.,max_baseline_nll_increase=100.,hessian_microbatch=2)
    dm={name:data(name) for name in c.datasets}
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);original_basis=r.rs_basis;original_save=r.OperatorJournal.save;once=[False]
        def forced_due(*args,**kwargs):
            journal=kwargs['journal']
            if not once[0]:journal.camp.last_checkpoint-=7201
            return original_basis(*args,**kwargs)
        def disconnect_after_save(self,*args,**kwargs):
            original_save(self,*args,**kwargs)
            if not once[0]:once[0]=True;raise r.PauseRun('Injected disconnect after durable column save')
        r.rs_basis=forced_due;r.OperatorJournal.save=disconnect_after_save
        r.main(root/'drive',root/'local',device_name='cpu',session_hours=6,c=c,data_map=dm)
        first_unit=root/'local'/'units'/'CIFAR10_14000'
        assert (first_unit/'operator_h1_n8_l4.resume.npz').exists()
        assert not (first_unit/'fit_h1_n8.json').exists()
        r.OperatorJournal.save=original_save;expired=[False]
        def expire_during_fit(*args,**kwargs):
            pulse=kwargs.get('pulse',args[-1])
            if not expired[0]:
                assert isinstance(pulse,r.SessionClock) and pulse.depth>0
                pulse.deadline=-1.;expired[0]=True
            return original_basis(*args,**kwargs)
        r.rs_basis=expire_during_fit
        r.main(root/'drive',root/'local',device_name='cpu',session_hours=6,c=c,data_map=dm,require_checkpoint=True)
        r.rs_basis=original_basis
        first_unit=root/'local'/'units'/'CIFAR10_14000'
        assert (first_unit/'fit_h1_n8.json').exists()
        assert not (first_unit/'fit_h2_n8.json').exists()
        first_fit_hash=hashlib.sha256((first_unit/'fit_h1_n8.npz').read_bytes()).hexdigest()
        original=r.branch;count=[0]
        def interrupted(*args,**kwargs):
            count[0]+=1
            if count[0]==4:raise r.PauseRun('Injected engineering interruption')
            return original(*args,**kwargs)
        r.branch=interrupted;r.main(root/'drive',root/'local',device_name='cpu',session_hours=1,c=c,data_map=dm,require_checkpoint=True)
        assert hashlib.sha256((first_unit/'fit_h1_n8.npz').read_bytes()).hexdigest()==first_fit_hash
        assert(root/'drive'/'CHECKPOINT.zip').exists()
        retained={p.relative_to(root/'local').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'local'/'units').rglob('branch_*.npz')}
        assert len(retained)==3
        r.branch=original;r.main(root/'drive',root/'local',device_name='cpu',session_hours=1,c=c,data_map=dm,require_checkpoint=True)
        for name,digest in retained.items():assert hashlib.sha256((root/'local'/name).read_bytes()).hexdigest()==digest
        from archive_io import verify
        finished=root/'drive'/'NEXUS_STAGE14_FINISHED.zip';assert finished.exists();assert not(root/'drive'/'CHECKPOINT.zip').exists()
        import zipfile
        with zipfile.ZipFile(finished) as z:
            registered=json.loads(z.read('analysis/REGISTERED14.json'));assert len(registered)==2
            assert all(q['independent_histories']==2 for q in registered)
            assert not any(n.endswith('.resume.npz') for n in z.namelist())
            assert sum(n.endswith('STABILITY14.json') for n in z.namelist())==4
        before=hashlib.sha256(finished.read_bytes()).hexdigest();r.main(root/'drive',root/'local',device_name='cpu',session_hours=1,c=c,data_map=dm,require_checkpoint=True)
        assert before==hashlib.sha256(finished.read_bytes()).hexdigest()
        print('SMOKE14 COMPLETE: four tiny units, two-hour column save and disconnect/resume, timer expiry during an operator fit, committed-fit hash preserved on resume, branch interruption, stability screen, both-future qualification, all branches, final archive, analysis and completed-run resume.')
