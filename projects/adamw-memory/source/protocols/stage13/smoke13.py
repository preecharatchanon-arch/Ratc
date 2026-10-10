"""Tiny two-cohort end-to-end interruption test, never research data."""
import dataclasses,tempfile,json,hashlib
from pathlib import Path
import numpy as np
import torch
import runner13 as R
from archive_io import verify

def synthetic(name,C,device):
    rng=np.random.default_rng(C);y=np.arange(80)%C;ty=np.arange(20)%C
    return dict(name=name,classes=C,X=torch.tensor(rng.normal(size=(80,3,32,32)),dtype=torch.float32,device=device),Y=torch.tensor(y,device=device),TX=torch.tensor(rng.normal(size=(20,3,32,32)),dtype=torch.float32,device=device),TY=torch.tensor(ty,device=device),labels=y,test_labels=ty,train_ids=np.arange(40),cal_ids=np.arange(40,80),response_ids=np.arange(6),test_ids=np.arange(6,20),fingerprints={'fixture':'synthetic-engineering-only'})
def main():
    c=dataclasses.replace(R.Config(),datasets=('SyntheticA','SyntheticB'),seeds=(13000,),width=2,train_steps=10,donor_step=7,train_batch=2,future_batch=2,future_steps=4,horizons=(0,1,2,3,4),fit_horizon=3,fit_sizes=(4,8),heldout_n=4,first_n=4,response_n=6,ranks=(2,4),sketch_columns=8,quality_columns=12,quality_energy_tolerance=2.,quality_response_tolerance=2.,trace_probes=4,checkpoint_train_interval=5,resolution_floor=1e-12,derivative_error_max=2.)
    # Looser thresholds are for exercising plumbing only. Default protocol is unchanged.
    data={n:synthetic(n,C,'cpu') for n,C in zip(c.datasets,(3,5))}
    with tempfile.TemporaryDirectory() as t:
        drive=Path(t)/'drive';local=Path(t)/'local';native=R.branch;counter=[0]
        def interrupt(*a,**kw):
            if counter[0]==3:raise R.PauseRun('Injected engineering interruption')
            counter[0]+=1;return native(*a,**kw)
        R.branch=interrupt;R.main(str(drive),str(local),device_name='cpu',c=c,data_map=data)
        before={p.relative_to(local).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (local/'units').rglob('branch*.npz')};assert len(before)==3
        R.branch=native;R.main(str(drive),str(local),device_name='cpu',c=c,data_map=data)
        for p,h in before.items():assert hashlib.sha256((local/p).read_bytes()).hexdigest()==h,'Completed branch recomputed'
        ident=json.loads((drive/'IDENTITY.json').read_text());manifest=verify(drive/'NEXUS_STAGE13_FINISHED.zip',ident,'FINISHED');report=json.loads((local/'analysis/REPORT.json').read_text())
        assert report['complete'];assert len(list((local/'units').rglob('branch*.npz')))==164
        assert not any(e['path'].endswith('.resume.npz') for e in manifest['files']);assert not list(drive.glob('CHECKPOINT*.zip'))
        result={'synthetic_only':True,'branches':164,'datasets':2,'resume_preserved_branch_hashes':len(before),'final_manifest_verified':True,'active_state_excluded':True,'checkpoint_cleanup_verified':True}
        print('SMOKE_TEST_RESULT',json.dumps(result));return result
if __name__=='__main__':main()
