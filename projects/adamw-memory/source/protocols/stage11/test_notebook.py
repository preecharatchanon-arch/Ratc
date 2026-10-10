"""Execute both delivered code cells with GPU/mount/run seams mocked, inspect payload."""
import hashlib,json,sys,tempfile,types,zipfile,io,unittest
from pathlib import Path
from unittest.mock import patch
import torch,torchvision

def main():
    root=Path(__file__).parent;nb=json.loads((root/'NEXUS_III_STAGE11_FUNCTIONAL_CONTROL_REALDATA_R1.ipynb').read_text())
    setup,run=[''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code'];real_path=Path;real_sys_path=sys.path.copy();calls=[]
    with tempfile.TemporaryDirectory() as tmp:
        code=Path(tmp)/'code'
        def path_map(s):return code if str(s)=='/content/nexus_stage11_code_r1' else real_path(s)
        google=types.ModuleType('google');colab=types.ModuleType('google.colab');colab.drive=types.SimpleNamespace(mount=lambda s:calls.append(('mount',s)))
        env={}
        with patch.dict(sys.modules,{'google':google,'google.colab':colab}),patch('pathlib.Path',path_map),patch.object(torch.cuda,'is_available',return_value=True),patch.object(torch.cuda,'get_device_properties',return_value=types.SimpleNamespace(name='A100 MOCK',total_memory=40*1024**3)):
            exec(compile(setup,'<setup>','exec'),env)
        manifest=json.loads(zipfile.ZipFile(io.BytesIO(env['_payload'])).read('PAYLOAD_MANIFEST.json'))
        for n,h in manifest.items():assert hashlib.sha256((code/n).read_bytes()).hexdigest()==h
        # Import hook intercepts only the pipeline call; delivered module reload loop still executes.
        fake=types.ModuleType('runner')
        def fake_run(drive,local,data):
            calls.append(('run',drive,local,data));return {'independent_models':16,'completed_cases':32,'planned_cases':32,'panels':{}},Path(tmp)/'NEXUS_STAGE11_FINISHED.zip'
        fake.run=fake_run;import builtins;original_import=builtins.__import__
        def hook(name,*a,**kw):return fake if name=='runner' else original_import(name,*a,**kw)
        with patch.object(builtins,'__import__',hook):exec(compile(run,'<run>','exec'),env)
        assert calls[0]==('mount','/content/drive')
        assert calls[1]==('run','/content/drive/MyDrive/NEXUS_III_STAGE11_FUNCTIONAL_CONTROL_R1','/content/nexus_stage11_runtime_r1','/content/nexus_stage10_dataset_cache')
    sys.path[:]=real_sys_path
    return {'passed':True,'embedded_file_sha256_checks':len(manifest),'both_code_cells_executed_with_mocked_gpu_mount_pipeline':True,
            'scope':'Wiring/payload test only; does not execute GPU training.'}
if __name__=='__main__':print(json.dumps(main(),indent=2))
