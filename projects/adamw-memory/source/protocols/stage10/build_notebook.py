import base64,hashlib,io,json,pathlib,zipfile

ROOT=pathlib.Path(__file__).parent
NAMES=['runner.py','archive_io.py','control_math.py','audit.py','test_math.py','PROTOCOL.json','PARENT_EVIDENCE.json','README.md',
       'test_cpu.py','test_storage.py','CPU_INTEGRATION_VALIDATION.json','CONVGN_VALIDATION.json','VALIDATION.json']
buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    manifest={}
    for name in NAMES:
        data=(ROOT/name).read_bytes();z.writestr(name,data);manifest[name]=hashlib.sha256(data).hexdigest()
    z.writestr('PAYLOAD_MANIFEST.json',json.dumps(manifest,sort_keys=True))
payload=buffer.getvalue();encoded=base64.b64encode(payload).decode();digest=hashlib.sha256(payload).hexdigest()
cell1=f'''# Setup: mount Drive and unpack frozen code locally. No file upload required.
import os,sys,base64,hashlib,io,json,zipfile
from pathlib import Path
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
os.environ["OMP_NUM_THREADS"]="2"
os.environ["OPENBLAS_NUM_THREADS"]="2"
import torch,torchvision
if not torch.cuda.is_available():
    raise RuntimeError("Select a GPU runtime in Colab first. A100 is recommended.")
print("GPU:",torch.cuda.get_device_name(0),"| torch:",torch.__version__,"| torchvision:",torchvision.__version__)
from google.colab import drive
drive.mount("/content/drive")
_payload=base64.b64decode("{encoded}")
assert hashlib.sha256(_payload).hexdigest()=="{digest}", "Notebook payload corrupted"
CODE=Path("/content/nexus_stage10_code_r1");CODE.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(io.BytesIO(_payload)) as _z:
    _manifest=json.loads(_z.read("PAYLOAD_MANIFEST.json"))
    assert set(_z.namelist())==set(_manifest)|{{"PAYLOAD_MANIFEST.json"}}
    for _name,_sha in _manifest.items():
        assert Path(_name).name==_name
        _bytes=_z.read(_name)
        assert hashlib.sha256(_bytes).hexdigest()==_sha
        (CODE/_name).write_bytes(_bytes)
if str(CODE) not in sys.path:sys.path.insert(0,str(CODE))
print("Ready: 8 models, exact-spectrum audit, 11 futures/model.")
print("Drive storage: cumulative checkpoint ZIP + predecessor; one finished ZIP on completion.")
'''
cell2='''# Run or resume the frozen study. Leave all settings unchanged.
import importlib,json
for _module in ("runner","archive_io","control_math","audit","test_math"):
    sys.modules.pop(_module,None)
import runner
DRIVE_ROOT="/content/drive/MyDrive/NEXUS_III_STAGE10_CONTROL_SPECTRUM_R1"
LOCAL_ROOT="/content/nexus_stage10_runtime_r1"
summary,finished=runner.run(DRIVE_ROOT,LOCAL_ROOT)
print("\\nFINISHED:",finished)
print("Completed models:",summary["completed_models"],"/",summary["planned_models"])
for dataset,panel in summary["panels"].items():
    print("\\n",dataset,"— descriptive results from",panel["n"],"training seeds")
    for rank in (16,64):
        energy=panel["rank_curve"][str(rank)]["transfer_capture"]
        print(" rank",rank,"independent-anchor energy capture:",round(energy["mean"],4),"CI",energy["ci95_descriptive"])
        for sign in ("plus","minus"):
            row=panel["causal"][str(rank)][sign]["16"]
            print("  h16",sign,{key:round(value["mean"],4) if "mean" in value else value for key,value in row.items()})
    print("Quality diagnostics:",panel["quality_per_seed"])
    print("Instrument diagnostics:",panel["instrument_per_seed"])
print("\\nSend back NEXUS_STAGE10_FINISHED.zip from the Drive folder above.")
print("Separate new evidence: frozen Stage07 flags are unchanged. No positive/publication claim is automatic.")
'''
markdown='''# NEXUS Stage10 — Control Spectrum and Real-Data Causal Sufficiency

This follows the saved AISTATS draft **Testing Low-Rank Causal Control in AdamW Memory**.

Stage07 found rank-16 capture of about 38% and substantial future effects outside that subspace. This study asks whether subspace estimation missed control directions, and whether low-rank energy capture preserves actual future effects on real-data models. Stage07 remains frozen.

**Run both code cells in order on an A100 Colab GPU. No upload needed.**

- **8 trained models:** four fixed MNIST/MLP seeds and four CIFAR-10/ConvGN seeds.
- Explicit local operator on 64 fitting images and 64 independent images; compare exact finite-anchor spectra against the earlier 24-probe estimation method.
- Fixed rank-16 primary and rank-64 diagnostic projections; full, projected, remainder and unchanged continuations; both signs; horizons 0, 1, 4, 16, 64.
- 12,000 reference updates and 5,632 future updates. Planning allowance approximately **1–4 A100 hours**, unbenchmarked; actual timings print during execution.
- CPU PyTorch integration, raw-data audit, interruption/resume, ConvGN Jacobian and archive-failure tests passed. Full real-data GPU execution remains untested here. The installed GPU backend is qualified before training.

**Drive receives no loose per-step/per-branch data.** Work and dataset caches stay under `/content`. Only cumulative `CHECKPOINT.zip` and `CHECKPOINT_PREVIOUS.zip` are retained during execution, plus tiny identity/lease metadata. Checkpoints occur at the trained cut, completed operator and completed model; intermediate publication is throttled to at most every 15 minutes. After verification, **NEXUS_STAGE10_FINISHED.zip** replaces the checkpoints.

Expected final size about **150–300 MB**; allow **1 GB** free for publication overlap. Estimates are not measured. The ZIP preserves meaningful states and raw evidence needed to audit conclusions.

If disconnected, run this same notebook again with the same software/GPU identity. An unfinished operator phase may repeat. A six-hour per-session limit stops the session without deleting the prior checkpoint. Send back the finished ZIP; if there is an error, send the traceback and keep the checkpoint files.

All seeds and failed learning/instrument diagnostics remain visible. Four seeds per regime give descriptive uncertainty. Rank-64 results do not rescue the old rank hypothesis, finite-anchor rank is not global rank, and moment surgery does not establish natural-history reachability. This is a focused research test, not a guarantee of a positive result or acceptance.
'''
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
 'language_info':{'name':'python','version':'3'},'accelerator':'GPU','colab':{'name':'NEXUS_III_STAGE10_CONTROL_SPECTRUM_REALDATA_R1.ipynb'}},
 'cells':[{'cell_type':'markdown','id':'stage10-overview','metadata':{},'source':markdown.splitlines(True)},
   *[{'cell_type':'code','id':name,'metadata':{},'execution_count':None,'outputs':[],'source':s.splitlines(True)} for name,s in [('setup',cell1),('run',cell2)]]]}
notebook=ROOT/'NEXUS_III_STAGE10_CONTROL_SPECTRUM_REALDATA_R1.ipynb'
notebook.write_text(json.dumps(nb,indent=1))
for cell in nb['cells']:
    if cell['cell_type']=='code':compile(''.join(cell['source']),'<notebook>','exec')
bundle=ROOT/'NEXUS_STAGE10_PROTOCOL_CODE_VALIDATION.zip'
members=NAMES+['build_notebook.py',notebook.name]
manifest={name:{'bytes':(ROOT/name).stat().st_size,'sha256':hashlib.sha256((ROOT/name).read_bytes()).hexdigest()} for name in members}
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in members:z.write(ROOT/name,name)
    z.writestr('DELIVERY_MANIFEST.json',json.dumps(manifest,indent=2,sort_keys=True))
with zipfile.ZipFile(bundle) as z:
    assert z.testzip() is None
    for name,record in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==record['sha256']
print(json.dumps({'notebook':str(notebook),'notebook_bytes':notebook.stat().st_size,'bundle':str(bundle),'bundle_bytes':bundle.stat().st_size,
                 'embedded_files_verified':len(NAMES),'notebook_code_cells_compiled':2},indent=2))
