"""Exploratory summary-data contrast; see frozen PROTOCOL.md before interpreting."""
from pathlib import Path
from decimal import Decimal
import csv, json, hashlib, platform
from scipy.stats import t
import scipy
P=Path(__file__).resolve().parent
freeze=json.loads((P/'design_freeze.json').read_text())
for name,digest in freeze['hashes'].items():
    if hashlib.sha256((P/name).read_bytes()).hexdigest()!=digest:
        raise ValueError('Frozen input changed: '+name)
rows=list(csv.DictReader((P/'functional_data.csv').open()))
if len(rows)!=56: raise ValueError('Expected all 56 source table cells')
for row in rows:
    if row['status']=='not_analyzed' and (row['mean'] or row['sem']):
        raise ValueError('NA must not have numerical values')
    if row['endpoint']=='Emax' and row['sem']:
        raise ValueError('S2 contains no numerical SEM')
selected={}
for receptor in ['WT','N102F']:
    for ligand in ['γ-EV','γ-EVG']:
        r=[r for r in rows if r['endpoint']=='EC50' and r['receptor']==receptor and r['ligand']==ligand]
        if len(r)!=1 or r[0]['unit']!='μM' or r[0]['n']!='3' or not r[0]['sem']:
            raise ValueError('Eligible summary missing or ambiguous')
        selected[(receptor,ligand)]=r[0]
crit=float(t.ppf(1-.05/4,df=2))
directions={('WT','γ-EV'):'lower',('N102F','γ-EV'):'upper',('WT','γ-EVG'):'upper',('N102F','γ-EVG'):'lower'}
def half_last(s): return float(Decimal(1).scaleb(Decimal(s).as_tuple().exponent)/2)
def compute(rounding):
    bounds={}
    for key,r in selected.items():
        m,se=float(r['mean']),float(r['sem']);direction=directions[key]
        halfm=half_last(r['mean']) if rounding else 0.
        halfse=half_last(r['sem']) if rounding else 0.
        v=m-halfm-crit*(se+halfse) if direction=='lower' else m+halfm+crit*(se+halfse)
        bounds[key]=v
    gaps={
      'EV_lower_EC50_after_N102F':bounds[('WT','γ-EV')]-bounds[('N102F','γ-EV')],
      'EVG_higher_EC50_after_N102F':bounds[('N102F','γ-EVG')]-bounds[('WT','γ-EVG')],
      'WT_EVG_more_potent_than_EV':bounds[('WT','γ-EV')]-bounds[('WT','γ-EVG')],
      'N102F_EV_more_potent_than_EVG':bounds[('N102F','γ-EVG')]-bounds[('N102F','γ-EV')]}
    return {'bounds':[{'receptor':k[0],'ligand':k[1],'direction':directions[k],'bound_uM':v} for k,v in bounds.items()],
      'separation_gaps_uM':gaps,
      'primary_opposing_shifts':all(gaps[k]>0 for k in list(gaps)[:2]),
      'secondary_full_rank_reversal':all(gaps[k]>0 for k in list(gaps)[2:])}
result={'scope':'Exploratory summary-data sensitivity; not independent confirmation, binding affinity, sensory prediction or a new biological result',
  'python':platform.python_version(),'scipy':scipy.__version__,
  'n_per_cell':3,'df':2,'directed_bounds':4,'alpha_family':.05,'critical_t':crit,
  'literal':compute(False),'rounding_sensitive':compute(True),
  'descriptive_fold_EC50_N102F_over_WT':{l:float(selected[('N102F',l)]['mean'])/float(selected[('WT',l)]['mean']) for l in ['γ-EV','γ-EVG']},
  'assumptions':['Independent normal raw-scale experiment EC50s within each cell; cannot be checked with n3 summaries',
                 'SEM reflects variation among three experiment-level EC50 estimates',
                 'Rounding sensitivity assumes half last displayed unit for each mean and SEM'],
  'excluded':['Emax inferential comparisons: missing numerical SEM','NA-as-negative labels','Mutant binding-affinity labels','Human efficacy or predictive utility claims']}
(P/'results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False))
