"""Summarize attributed sensory thresholds without treating them as ENaC activity."""
from pathlib import Path
import csv, json, time, hashlib, sys

E=Path(__file__).absolute().parents[1]
P=E.parent.parent
D=P/'data/functional'
O=E/'runs/published_sensory'

def read(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))

def save(name,rows):
    with (O/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)

def balance(seq):
    return sum(seq.count(x) for x in 'RK')-sum(seq.count(x) for x in 'DE')

def main():
    start=time.monotonic();O.mkdir(parents=True,exist_ok=True)
    files=[D/'hofmann2021_patent_prolyl_thresholds.csv',D/'juenger2022_sensory_thresholds.csv',P/'data/saltiness/benchmark_records.csv']
    patent,paper,benchmark=map(read,files)
    labels={r['sequence']:r for r in benchmark}
    # Ambiguous PP rows and < entries are never coerced to measured thresholds.
    usable={r['sequence']:r for r in patent if not r['record_flag'] and r['broth_effect_as_printed']=='Salt enhancing'}
    rows=[]
    for s,r in usable.items():
        rows.append(dict(sequence=s,source_group='hofmann2021_patent_Table4',
            reported_salt_modulation_threshold_uM=float(r['broth_threshold_mM_as_printed'])*1000,
            reported_quality=r['broth_effect_as_printed'],matrix='model broth; composition not verified',pH='',
            nominal_sidechain_balance=balance(s),contains_arginine='R' in s,contains_lysine='K' in s,
            ENaC_activity_interpretation='not established by this sensory record'))
    for r in paper:
        if 'salty' not in r['modulation_quality'].split(';'):continue
        s=r['sequence']
        rows.append(dict(sequence=s,source_group='juenger2022_SI_TableS5',
            reported_salt_modulation_threshold_uM=float(r['modulation_threshold_uM']),
            reported_quality=r['modulation_quality'],matrix=r['modulation_matrix'],pH=r['pH'],
            nominal_sidechain_balance=balance(s),contains_arginine='R' in s,contains_lysine='K' in s,
            ENaC_activity_interpretation='not established by this sensory record'))
    save('published_salt_modulation_controls.csv',rows)
    pairs=[]
    for a,b,question in [('RP','KP','Arg-to-Lys substitution'),('VP','PV','Residue order at fixed composition')]:
        ta=float(usable[a]['broth_threshold_mM_as_printed']);tb=float(usable[b]['broth_threshold_mM_as_printed'])
        pairs.append(dict(reference=a,comparison=b,comparison_question=question,source_group='hofmann2021_patent_Table4',
            reference_threshold_mM=ta,comparison_threshold_mM=tb,comparison_to_reference_threshold_ratio=tb/ta,
            statistical_uncertainty='not available; ratio of reported point thresholds only',
            interpretation='Both reported salt enhancing in model broth; not a receptor potency ratio or a quantified sodium reduction'))
    save('within_source_sensory_pairs.csv',pairs)
    overlap=[]
    for r in rows:
        b=labels.get(r['sequence'])
        overlap.append(dict(sequence=r['sequence'],source_group=r['source_group'],
            existing_benchmark_record=b is not None,existing_label=b['label'] if b else '',
            existing_phenotype=b['phenotype'] if b else '',existing_references=b['references'] if b else '',
            interpretation='Context-dependent labels; benchmark absence is not inactivity; overlap is not held-out validation'))
    save('published_sensory_benchmark_overlap.csv',overlap)
    paper_salt=[r for r in rows if r['source_group']=='juenger2022_SI_TableS5']
    result=dict(scope='Analysis of newly recovered published sensory evidence; no activity model or wet-lab work',
        patent_rows=len(patent),primary_paper_SI_rows=len(paper),
        patent_conflicting_PP_rows=sum(r['record_flag']=='conflicting_duplicate_PP' for r in patent),
        primary_paper_numeric_modulation_thresholds=sum(bool(r['modulation_threshold_uM']) for r in paper),
        primary_paper_salt_modulation_sequences=[r['sequence'] for r in paper_salt],
        primary_paper_salt_threshold_range_uM=[min(r['reported_salt_modulation_threshold_uM'] for r in paper_salt),max(r['reported_salt_modulation_threshold_uM'] for r in paper_salt)],
        primary_paper_salt_sequences_with_Arg_or_Lys=sum(r['contains_arginine'] or r['contains_lysine'] for r in paper_salt),
        primary_paper_salt_sequences_absent_from_benchmark=[r['sequence'] for r in paper_salt if r['sequence'] not in labels],
        benchmark_negative_with_published_broth_enhancement=[r['sequence'] for r in rows if r['sequence'] in labels and labels[r['sequence']]['label']=='0'],
        current_KP_status='Published sensory salt-enhancement evidence; human taste-cell assay activity remains unverified',
        limits=['Do not rank thresholds across distinct matrices or protocols.',
                'A reported salt descriptor in a threshold task is not an effect-size curve or demonstrated sodium replacement.',
                'Missing modulation and non-salt descriptors are not verified salt-negative labels.',
                'Nominal side-chain balance omits terminal and pH-dependent charge; no causal charge effect is estimated.',
                'Water bitterness and broth enhancement cannot define a same-matrix sensory selectivity window.',
                'Patent family versions are one evidence source; do not count them as replications.'])
    (O/'published_sensory_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    receipt=dict(CPU_only=True,GPU_required=False,python=sys.version,elapsed_s=time.monotonic()-start,
        input_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (O/'published_sensory_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
