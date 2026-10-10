from pathlib import Path
import numpy as np,json,csv
package=Path(__file__).resolve().parents[1];root=package/'evidence/stage14/raw';rows=[]
for unit in sorted(root.glob('CIFAR10_*')):
 for path in (0,1):
  def effect(name,h):
   a=np.load(unit/f'path{path}/branch_{name}_plus.npz')[f'h{h}'].astype(float);b=np.load(unit/f'path{path}/branch_{name}_minus.npz')[f'h{h}'].astype(float);x=(a-b)/2;return x-x.mean(axis=1,keepdims=True)
  for h in (16,64):
   f=effect('full',h);half=effect('full_half',h)
   rows.append(dict(seed=int(unit.name.split('_')[1]),path=path,horizon=h,full_half_discrepancy=float(np.linalg.norm(f-2*half)/np.linalg.norm(f)),half_rms=float(np.sqrt(np.mean(half*half)))))
summary={str(h):{'maximum_full_half_discrepancy':max(x['full_half_discrepancy'] for x in rows if x['horizon']==h),'minimum_half_rms':min(x['half_rms'] for x in rows if x['horizon']==h)} for h in (16,64)}
(package/'evidence/stage14/AMPLITUDE_AUDIT.json').write_text(json.dumps(dict(summary=summary,per_history=rows),indent=2));print(summary)
