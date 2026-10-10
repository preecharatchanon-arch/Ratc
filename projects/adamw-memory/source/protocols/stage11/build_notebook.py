"""Build a self-contained notebook and hash-verified delivery archive."""
import base64,hashlib,io,json,pathlib,zipfile
ROOT=pathlib.Path(__file__).parent
NAMES=['runner.py','models.py','operators.py','archive_io.py','control_math.py','audit.py','PROTOCOL.json','PARENT_EVIDENCE.json',
       'RELATED_WORK.md','README.md','test_validation.py','test_storage.py','CPU_VALIDATION.json','REAL_BACKBONE_ESTIMATOR_VALIDATION.json','VALIDATION.json']
buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    manifest={}
    for name in NAMES:
        b=(ROOT/name).read_bytes();z.writestr(name,b);manifest[name]=hashlib.sha256(b).hexdigest()
    z.writestr('PAYLOAD_MANIFEST.json',json.dumps(manifest,sort_keys=True))
payload=buffer.getvalue();encoded=base64.b64encode(payload).decode();digest=hashlib.sha256(payload).hexdigest()
setup=f'''# Run first: verify GPU, mount Drive and unpack the frozen protocol locally.
import os,sys,base64,hashlib,io,json,zipfile
from pathlib import Path
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
os.environ["OMP_NUM_THREADS"]="2"
os.environ["OPENBLAS_NUM_THREADS"]="2"
import torch,torchvision
if not torch.cuda.is_available():
    raise RuntimeError("Select an A100 GPU runtime in Colab before running this notebook.")
_gpu=torch.cuda.get_device_properties(0)
if _gpu.total_memory < 35*1024**3:
    raise RuntimeError("This fixed protocol needs at least 35 GiB GPU memory. Select an A100 runtime; training has not started.")
print("GPU:",_gpu.name,"| GiB:",round(_gpu.total_memory/1024**3,1),"| torch:",torch.__version__,"| torchvision:",torchvision.__version__)
from google.colab import drive
drive.mount("/content/drive")
_payload=base64.b64decode("{encoded}")
assert hashlib.sha256(_payload).hexdigest()=="{digest}","Notebook payload corrupted"
CODE=Path("/content/nexus_stage11_code_r1");CODE.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(io.BytesIO(_payload)) as _z:
    _manifest=json.loads(_z.read("PAYLOAD_MANIFEST.json"))
    assert set(_z.namelist())==set(_manifest)|{{"PAYLOAD_MANIFEST.json"}}
    for _name,_sha in _manifest.items():
        assert Path(_name).name==_name
        _b=_z.read(_name);assert hashlib.sha256(_b).hexdigest()==_sha
        (CODE/_name).write_bytes(_b)
if str(CODE) not in sys.path:sys.path.insert(0,str(CODE))
print("Frozen study ready: 16 reference models, 32 checkpoint cases, 2 future streams/case.")
print("No source upload required. Dataset and working files stay in /content.")
print("Drive retains two rolling checkpoint ZIPs, then one verified finished ZIP.")
'''
run='''# Run or resume. Keep these fixed settings unchanged between sessions.
for _module in ("runner","models","operators","archive_io","control_math","audit"):
    sys.modules.pop(_module,None)
import runner
DRIVE_ROOT="/content/drive/MyDrive/NEXUS_III_STAGE11_FUNCTIONAL_CONTROL_R1"
LOCAL_ROOT="/content/nexus_stage11_runtime_r1"
DATASET_ROOT="/content/nexus_stage10_dataset_cache"  # Reuse Stage10 CIFAR files if still present.
print("315,648 optimizer updates plus matrix-free operator estimation; GPU runtime is unbenchmarked.")
print("Actual model-block timings and an ETA will print during the run.")
print("An eight-hour session limit saves progress and stops; rerun this identical notebook to continue.")
summary,finished=runner.run(DRIVE_ROOT,LOCAL_ROOT,DATASET_ROOT)
print("\\nFINISHED:",finished)
print("Independent reference models:",summary["independent_models"])
print("Completed checkpoint cases:",summary["completed_cases"],"/",summary["planned_cases"])
for _name,_panel in summary["panels"].items():
    print("\\n",_name,"—",_panel["independent_models"],"independent training seeds")
    _capture=_panel["capture"]["16"]
    print("rank16 independent functional capture:",_capture)
    print("primary paired h16 causal effects:",_panel["primary"]["paired"])
    print("reference learning:",_panel["reference_learning_per_seed"])
    print("instrument diagnostics:",_panel["instrument_per_seed"])
print("\\nSend back NEXUS_STAGE11_FINISHED.zip from the Drive folder above.")
print("All failed/unresolved diagnostics remain visible; frozen Stage07 conclusions are unchanged.")
'''
overview='''# NEXUS Stage11 — Functional Control and Future Learning

**Question:** Does a subspace that captures immediate AdamW-memory influence preserve its effects after further training?

This extends the saved AISTATS topic *Testing Low-Rank Causal Control in AdamW Memory*. The frozen Stage07 confirmation had about38% rank16 capture and substantial future effects in the remainder. Those negative conclusions remain unchanged. Stage11 tests external validity and estimation adequacy with a fixed design; it does not assume a positive result.

**Run both code cells in order on an A100 Colab GPU. No source upload is needed.**

| Component | Fixed scope |
|---|---|
| Data | CIFAR10 and CIFAR100; calibration excluded from sampled training |
| Architecture | ResNet18 with GroupNorm and a six-block small vision transformer, crossed with both datasets |
| Independent models | Four seeds per dataset/architecture cell:16 total |
| Trained checkpoints | Halfway and final:32 nested cases |
| Estimation |128/512 fitting images;64/128 probes; independent512-image trace anchor |
| Intervention | Full memory direction; projected/remainder at ranks8,16,64; gradient and tensor-matched random controls; both signs |
| Continuation |19 branches ×2 future streams per case; horizons0,1,4,16,64,128 |
| Primary report | Late checkpoint, rank16, horizon16; descriptive across independent training seeds |

Projected and remainder directions retain their size; weights, second moments and clocks are held fixed. The largest estimator is always used. Smaller budgets test stability and are never selected by the outcomes. Both signed baseline-relative and paired effects are saved. Low learning quality, unstable estimators and unresolved effects remain in the report.

**Runtime:**160,000 reference plus155,648 future optimizer updates, with additional matrix-free operator work. Full A100 timing is **not benchmarked**. The run prints measured model-block time and a rough ETA. An eight-hour session limit stops with a verified checkpoint; resume using this same notebook. The early blocks include compilation/kernel/cache warmup and any resumed block may be shorter, so the ETA is approximate. This is a substantial study, but GPU time is not a measure of scientific merit.

**Storage:** datasets and working tensors stay in `/content`. The existing Stage10 dataset cache is reused when available. Drive gets a cumulative checkpoint ZIP and one predecessor, plus tiny identity/lease JSON; no loose per-step/per-branch `.pt` files or full basis matrices. Publication is throttled to15minutes plus the first trained cut and completed models. On completion, **NEXUS_STAGE11_FINISHED.zip** replaces the verified checkpoints. Allow roughly1.5GB free for publication overlap; actual size prints. Previous stage folders are not altered.

The finished ZIP keeps raw response logits, trace probes/projections, finite-surgery outputs, Gram matrices, per-example evaluation predictions/NLL, source, seeds and provenance. It excludes full model/optimizer tensors. Statistical audit can recompute those saved estimands; full neural reproduction requires rerunning the frozen code.

**Development verification:** actual CPU checks of both full backbones, JVP/VJP agreement, exact serialized continuation, analytic AdamW derivative, a known-spectrum operator, an interrupted two-cut/two-stream pipeline, saved-data tampering and archive failures. The synthetic engineering fixture validates code and is not research evidence. Full real-data GPU execution remains untested here; the installed GPU backend is qualified before training.

Read `PROTOCOL.json`, `PARENT_EVIDENCE.json` and `RELATED_WORK.md` in the accompanying code ZIP for the interpretation boundaries. Four seeds per cell give descriptive uncertainty; branches, streams and checkpoints do not increase that seed count. CIFAR evidence does not establish generality to LLMs or production-scale training. No breakthrough, novelty priority or publication outcome is assumed.

If disconnected, run this unchanged notebook again. A recent session lease expires after15minutes. An unfinished operator fit may repeat and up to15minutes of work can be lost between Drive publications. If an error occurs, keep the checkpoint ZIPs and send the traceback. Send back the finished ZIP for analysis.
'''
overview=overview.replace('about38%','about 38%').replace('ranks8,16,64','ranks 8,16,64').replace('to15minutes','to 15 minutes').replace('after15minutes','after 15 minutes').replace('to15minutes','to 15 minutes')
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
    'language_info':{'name':'python','version':'3'},'accelerator':'GPU','colab':{'name':'NEXUS_III_STAGE11_FUNCTIONAL_CONTROL_REALDATA_R1.ipynb'}},
    'cells':[{'cell_type':'markdown','id':'overview','metadata':{},'source':overview.splitlines(True)},
      *[{'cell_type':'code','id':n,'metadata':{},'execution_count':None,'outputs':[],'source':s.splitlines(True)} for n,s in [('setup',setup),('run',run)]]]}
notebook=ROOT/'NEXUS_III_STAGE11_FUNCTIONAL_CONTROL_REALDATA_R1.ipynb';notebook.write_text(json.dumps(nb,indent=1))
for cell in nb['cells']:
    if cell['cell_type']=='code':compile(''.join(cell['source']),'<notebook>','exec')
members=NAMES+['build_notebook.py','test_notebook.py',notebook.name]
delivery={n:{'bytes':(ROOT/n).stat().st_size,'sha256':hashlib.sha256((ROOT/n).read_bytes()).hexdigest()} for n in members}
bundle=ROOT/'NEXUS_STAGE11_PROTOCOL_CODE_VALIDATION.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in members:z.write(ROOT/name,name)
    z.writestr('DELIVERY_MANIFEST.json',json.dumps(delivery,sort_keys=True,indent=2))
with zipfile.ZipFile(bundle) as z:
    assert z.testzip() is None
    for n,r in delivery.items():assert hashlib.sha256(z.read(n)).hexdigest()==r['sha256']
print(json.dumps({'notebook':str(notebook),'notebook_bytes':notebook.stat().st_size,'bundle':str(bundle),
                 'bundle_bytes':bundle.stat().st_size,'verified_embedded_files':len(NAMES),'compiled_code_cells':2},indent=2))
