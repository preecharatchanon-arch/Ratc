from pathlib import Path
import numpy as np,json,csv,argparse
parser=argparse.ArgumentParser(description='Audit an extracted Stage07 confirmation archive; raw endpoints required.');parser.add_argument('--root',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();root=args.root;saved=json.loads((root/'confirmation/stage07_confirmation_analysis.json').read_text());rows=[]
for p in sorted((root/'confirmation').glob('*causal_endpoints.npz')):
 with np.load(p,allow_pickle=False) as z:
  for H in (1,4,16):
   f=(z[f'history_plus_h{H}'].astype(float)-z[f'history_minus_h{H}'].astype(float))/2
   v=(z[f'parallel_plus_h{H}'].astype(float)-z[f'parallel_minus_h{H}'].astype(float))/2
   r=(z[f'perp_plus_h{H}'].astype(float)-z[f'perp_minus_h{H}'].astype(float))/2
   n=np.linalg.norm(f)
   rows.append(dict(seed=int(z['replicate_id']),horizon=H,cosine=float(f@v/(n*np.linalg.norm(v))),retention=float(np.linalg.norm(v)/n),remainder=float(np.linalg.norm(r)/n),additivity=float(np.linalg.norm(f-v-r)/n),error=float(np.linalg.norm(f-v)/n)))
checks={}
for col,key in [('cosine','parallel_cosine'),('retention','parallel_retention'),('remainder','perp_ratio'),('additivity','additivity_error')]:
 actual=float(np.mean([r[col] for r in rows if r['horizon']==16]));stored=saved['H7_C'][key]['mean'];checks[col]=dict(recomputed=actual,archived=stored,difference=actual-stored);assert abs(actual-stored)<1e-7
out=args.out;out.mkdir(parents=True,exist_ok=True)
with (out/'stage07_response_by_task.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
(out/'stage07_saved_array_verification.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks))
