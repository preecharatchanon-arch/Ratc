"""Frozen input provenance, finite JSON and atomic geometry cache envelopes."""
import hashlib,json,os,zipfile
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
def load(p):return json.loads(Path(p).read_text())
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n');os.replace(temp,path)
def source_hash():
    return digest({p.name:sha(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.suffix in ('.py','.json','.md','.zip')})
def frozen_data():
    provenance=load(ROOT/'frozen_provenance.json')
    if sha(ROOT/'frozen_source_results.zip')!=provenance['original_result_sha256']:raise ValueError('Frozen original ZIP changed')
    for name,expected in provenance['files'].items():
        if sha(ROOT/name)!=expected:raise ValueError('Frozen source file changed: '+name)
    cases=load(ROOT/'cases.json');profiles=load(ROOT/'frozen_profiles.json')
    if len(cases)!=43 or len({c['family'] for c in cases})!=20 or set(profiles)!={c['id'] for c in cases}:raise ValueError('Incomplete frozen inputs')
    # Compare compact replay inputs to the unmodified uploaded archive, not merely
    # to an easily rehashed feature JSON. The GPU API never receives target labels.
    with zipfile.ZipFile(ROOT/'frozen_source_results.zip') as z:
        if z.testzip() is not None:raise ValueError('Frozen original CRC failure')
        if load(ROOT/'cases.json')!=json.loads(z.read('source/inputs.json')):raise ValueError('Frozen case mismatch')
        for c in cases:
            e=json.loads(z.read('profiles/'+c['id']+'.json'));r=e['payload'];p=profiles[c['id']]
            expected=e.pop('sha256')
            if expected!=digest(e):raise ValueError('Original profile checksum mismatch')
            wanted={'prompt_ids':r['selection']['ids'],'response_ids':r['token_ids'],'text':r['text'],'trace':r['trace'],
                    'vectors':{a:r['vectors'][a] for a in ('structure','aggregate','prose_control')},'source_record_sha256':expected}
            if p!=wanted or len(p['response_ids'])!=128:raise ValueError('Frozen profile mismatch: '+c['id'])
    return cases,profiles

def cache_identity(run,case,profile):
    return {'run':run,'id':case['id'],'model':case['model'],'frozen_profile':profile['source_record_sha256']}
def put(path,identity,payload):
    data={'identity':identity,'payload':payload};data['sha256']=digest(data);save(path,data)
def verify_payload(payload,profile):
    from geometry_measures import geometry_from_gram
    if payload['prompt_ids_sha256']!=digest(profile['prompt_ids']) or payload['response_ids_sha256']!=digest(profile['response_ids']):raise ValueError('Geometry token identity mismatch')
    n=len(profile['response_ids']);g=np.asarray(payload['centered_gram'],float);adj=np.asarray(payload['adjacent_distances'],float)
    if g.shape!=(n,n) or adj.shape!=(n-1,):raise ValueError('Wrong geometry cache dimensions')
    if not isinstance(payload['reference_checked'],bool) or not payload['wall_seconds']>0:raise ValueError('Invalid measurement metadata')
    depth=payload['num_decoder_blocks'];index=payload['block_index']
    if not isinstance(depth,int) or depth<1 or index!=int(np.ceil(.75*depth))-1:raise ValueError('Wrong fixed decoder block')
    if not isinstance(payload['hidden_width'],int) or payload['hidden_width']<1:raise ValueError('Invalid hidden width')
    rebuilt=geometry_from_gram(g,adj)
    # Eigensolver roundoff can vary slightly across Colab CPU hosts. This
    # tolerance is far below a usable feature difference; envelope hashes still
    # require byte integrity and material rehashed feature edits are rejected.
    np.testing.assert_allclose(rebuilt,payload['features'],atol=1e-8,rtol=0,err_msg='Geometry cache features do not reconstruct')
    return payload
def verify_cache(root,run,cases,profiles):
    lookup={c['id']:c for c in cases};records={}
    for path in sorted((Path(root)/'profiles').glob('*.json')):
        if path.stem not in lookup:raise ValueError('Unexpected geometry cache input: '+path.name)
        data=load(path);checksum=data.pop('sha256',None)
        if digest(data)!=checksum:raise ValueError('Geometry checksum mismatch: '+path.name)
        if data['identity']!=cache_identity(run,lookup[path.stem],profiles[path.stem]):raise ValueError('Geometry campaign identity mismatch')
        records[path.stem]=verify_payload(data['payload'],profiles[path.stem])
    return records
