"""Actual PyTorch engineering integration; synthetic pixels, not research outcomes."""
import copy,json,tempfile,time
from pathlib import Path
from dataclasses import replace
import numpy as np
import torch
import runner
from archive_io import Campaign,verify,sha
from audit import audit_unit

def toy_data(name,root,device,cfg):
    g=torch.Generator().manual_seed(700)
    X=torch.randn(300,1,28,28,generator=g).to(device);Y=(torch.arange(300)%10).to(device)
    TX=torch.randn(100,1,28,28,generator=g).to(device);TY=(torch.arange(100)%10).to(device)
    return {'name':name,'X':X,'Y':Y,'TX':TX,'TY':TY,'train_ids':np.arange(100),'cal_ids':np.arange(100,300),
            'response_ids':np.arange(20),'test_ids':np.arange(20,100),'fingerprints':{'engineering':'synthetic_fixture_v1'}}

def main():
    torch.set_num_threads(2);runner.MLP=lambda:torch.nn.Sequential(torch.nn.Flatten(),torch.nn.Linear(784,12),torch.nn.Tanh(),torch.nn.Linear(12,10))
    cfg=replace(runner.Config(),datasets=('MNIST',),seeds=(10100,),train_steps_mnist=8,batch_size=16,
      first_probe_batch=10,fit_anchor_n=2,heldout_anchor_n=2,response_n=20,calibration_n=200,
      jac_image_chunk=2,jac_output_chunk=4,bootstrap_draws=100,session_hours=.25)
    started=time.monotonic();tests={}
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);drive=root/'drive';local=root/'local';real_phase=runner.future_phase
        # Interrupt after the completed operator checkpoint, then resume all futures.
        def interrupt(*args,**kwargs):raise RuntimeError('injected_disconnect_after_operator')
        runner.future_phase=interrupt
        try:runner.run(drive,local,'cpu',cfg,toy_data)
        except RuntimeError as e:assert 'injected_disconnect' in str(e)
        else:raise AssertionError('Interruption was not exercised')
        assert (drive/'CHECKPOINT.zip').exists() and not list(drive.glob('*.pt'))
        identity=json.loads((drive/'IDENTITY.json').read_text());verify(drive/'CHECKPOINT.zip',identity,'CHECKPOINT')
        # Rerun must load verified operator state without computing new Jacobians.
        runner.future_phase=real_phase;old=runner.exact_rows
        def fail_if_recomputed(*args,**kwargs):
            # The one-image ConvGN backend fixture reruns on every session.
            if len(args[3])==1:return old(*args,**kwargs)
            raise AssertionError('Committed research operator recomputed')
        runner.exact_rows=fail_if_recomputed
        summary,path=runner.run(drive,local,'cpu',cfg,toy_data);runner.exact_rows=old
        assert summary['complete'] and summary['completed_models']==1
        assert not (drive/'CHECKPOINT.zip').exists() and not (drive/'CHECKPOINT_PREVIOUS.zip').exists()
        m=verify(path,identity,'FINISHED');assert not any(e['path'].endswith('.pt') for e in m['files'])
        tests['actual_training_operator_11_futures_independent_audit']=True
        tests['disconnect_after_operator_resume_without_jacobian_replay']=True
        tests['low_numerical_rank_retained_instead_of_aborted']=True
        tests['final_no_pt_and_checkpoint_pruned_after_verification']=True
        summary2,path2=runner.run(drive,local,'cpu',cfg,toy_data);assert summary2==summary and sha(path2)==sha(path)
        tests['completed_campaign_resume_skips_training']=True
        # Raw-data auditor catches outcome tampering independently of archive integrity.
        result_file=local/'units'/'MNIST_10100'/'result.json';record=json.loads(result_file.read_text());original=result_file.read_text()
        record['operator']['rank_curve'][0]['transfer_capture']+=.1;result_file.write_text(json.dumps(record))
        try:audit_unit(result_file.parent)
        except ValueError:pass
        else:raise AssertionError('Auditor accepted altered energy')
        result_file.write_text(original);tests['independent_audit_rejects_tampering']=True
        # Changed protocol cannot enter the same campaign.
        changed=copy.deepcopy(identity);changed['version']='changed'
        try:Campaign(drive,root/'other',changed).activate()
        except RuntimeError:pass
        else:raise AssertionError('Identity mismatch accepted')
        tests['changed_campaign_identity_rejected']=True
    return {'passed':True,'torch':str(torch.__version__),'torchvision':str(runner.torchvision.__version__),
        'backend':'CPU','scope':'synthetic engineering fixture only; no real MNIST/CIFAR outcomes',
        'seconds':time.monotonic()-started,'checks':tests}

if __name__=='__main__':
    result=main();print(json.dumps(result,indent=2));Path('CPU_INTEGRATION_VALIDATION.json').write_text(json.dumps(result,indent=2))
