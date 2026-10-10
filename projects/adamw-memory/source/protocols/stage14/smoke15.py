"""Four-unit CPU integration of incremental saves; synthetic engineering data only."""
import hashlib,json,tempfile,zipfile
from pathlib import Path
from dataclasses import replace,asdict
import torch
import runner14 as r
from smoke14 import data
from test_incremental15 import LocalBackend
from archive_io import pack,write_json,verify

def main():
    c=replace(r.Config(),datasets=('CIFAR10','CIFAR100'),seeds=(14000,14001),width=2,train_steps=6,donor_step=4,train_batch=4,
        future_batch=4,future_steps=3,horizons=(0,1,2,3),fit_horizon=2,fit_sizes=(8,),heldout_n=4,first_n=4,response_n=3,
        ranks=(1,2),sketch_columns=4,quality_columns=5,quality_energy_tolerance=1.,quality_response_tolerance=2.,
        trace_probes=3,checkpoint_train_interval=3,resolution_floor=0.,derivative_error_max=1.,cut_floor_cifar10=0.,cut_floor_cifar100=0.,
        max_baseline_accuracy_drop=1.,max_baseline_nll_increase=100.,hessian_microbatch=2)
    dm={name:data(name) for name in c.datasets};r.configure(torch.device('cpu'))
    identity=dict(version=r.VERSION,config=json.loads(json.dumps(asdict(c))),environment=r.environment(torch.device('cpu')),
        source_sha256='9daa2fc0181d7f3e373e1de3be7c03bb2a251a22f4e1edcceecf2153ffc1964a')
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);b=LocalBackend(root/'server');f=root/'seed/metadata/ENGINEERING.json';write_json(f,{'synthetic':True})
        z=pack(root/'seed',root/'seed.zip',identity,'CHECKPOINT',[f]);ip=root/'identity.json';write_json(ip,identity)
        b.put('run','IDENTITY.json',ip);b.put('run','CHECKPOINT.zip',z);b.put('run','CHECKPOINT_PREVIOUS.zip',z)
        def run():
            return r.main(root/'mounted',root/'local',device_name='cpu',session_hours=6,c=c,data_map=dm,
                require_checkpoint=True,backend=LocalBackend(root/'server'))
        original_basis=r.rs_basis;original_save=r.OperatorJournal.save;once=[False]
        def forced_due(*args,**kwargs):
            if not once[0]:kwargs['journal'].camp.last_checkpoint-=901
            return original_basis(*args,**kwargs)
        def interrupt(self,*args,**kwargs):
            original_save(self,*args,**kwargs)
            if not once[0]:once[0]=True;raise r.PauseRun('Engineering interruption after a durable column')
        r.rs_basis=forced_due;r.OperatorJournal.save=interrupt;run()
        unit=root/'local/units/CIFAR10_14000';assert (unit/'operator_h1_n8_l4.resume.npz').exists()
        assert not (unit/'fit_h1_n8.json').exists()
        r.OperatorJournal.save=original_save;expired=[False]
        def expire_during_fit(*args,**kwargs):
            pulse=kwargs.get('pulse',args[-1])
            if not expired[0]:assert pulse.depth>0;pulse.deadline=-1.;expired[0]=True
            return original_basis(*args,**kwargs)
        r.rs_basis=expire_during_fit;run();r.rs_basis=original_basis
        assert (unit/'fit_h1_n8.json').exists();assert not (unit/'fit_h2_n8.json').exists()
        fit_hash=hashlib.sha256((unit/'fit_h1_n8.npz').read_bytes()).hexdigest();original_branch=r.branch;count=[0]
        def interrupted_branch(*args,**kwargs):
            count[0]+=1
            if count[0]==4:raise r.PauseRun('Engineering interruption after three branches')
            return original_branch(*args,**kwargs)
        r.branch=interrupted_branch;run()
        retained={p.relative_to(root/'local').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'local/units').rglob('branch_*.npz')}
        assert len(retained)==3;assert hashlib.sha256((unit/'fit_h1_n8.npz').read_bytes()).hexdigest()==fit_hash
        r.branch=original_branch;run()
        for name,digest in retained.items():assert hashlib.sha256((root/'local'/name).read_bytes()).hexdigest()==digest
        b=LocalBackend(root/'server');finals=[m for m in b.list('run') if m['name']=='NEXUS_STAGE14_FINISHED.zip'];assert len(finals)==1
        final=b.root/finals[0]['id'];verify(final,identity,'FINISHED')
        with zipfile.ZipFile(final) as zz:
            assert not any(n.endswith('.resume.npz') for n in zz.namelist())
            assert sum(n.endswith('STABILITY14.json') for n in zz.namelist())==4
            registered=json.loads(zz.read('analysis/REGISTERED14.json'));assert len(registered)==2
            assert all(q['independent_histories']==2 for q in registered)
        stores=[m for m in b.list('run') if m['name']=='CHECKPOINTS_15MIN'];assert len(stores)==1;assert not b.list(stores[0]['id'])
        before=hashlib.sha256(final.read_bytes()).hexdigest();run();assert before==hashlib.sha256(final.read_bytes()).hexdigest()
        print('SMOKE15 COMPLETE: four synthetic CPU units; legacy import; column, timer and branch interruptions; exact retained fits/branches; final export verified; resume chunks removed only after final publication; finished run skips computation.')

if __name__=='__main__':main()
