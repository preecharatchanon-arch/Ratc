"""Validate project navigation and frozen-artifact integrity using only stdlib.

Run from any working directory: python verification/verify_layout.py
This checks the organized release; it does not rerun scientific experiments.
"""
from pathlib import Path
import ast, base64, csv, hashlib, io, json, re, urllib.parse, zipfile

ROOT=Path(__file__).resolve().parent.parent
REPO=ROOT.parent.parent
ALIASES={
    'CaSR_Research_Workbench.ipynb':'experiments/01-casr-models-and-docking/CaSR_Research_Workbench.ipynb',
    'sensory-continuation/Saltiness_Sensory_Validation.ipynb':'experiments/02-sensory-source-transfer/Saltiness_Sensory_Validation.ipynb',
    'assay-conditions/Saltiness_Assay_Conditions.ipynb':'experiments/03-assay-dose-response/Saltiness_Assay_Conditions.ipynb',
}

def published(path):
    return path.is_file() and not any(p in {'runs','cache','__pycache__','.venv'} for p in path.relative_to(ROOT).parts)

def slug(text):
    text=re.sub(r'[`*_]','',text.strip()).lower()
    return re.sub(r'[^\w\- ]','',text).replace(' ','-')

def anchors(path):
    result=set();fenced=False
    for line in path.read_text().splitlines():
        if line.lstrip().startswith(('```','~~~')):fenced=not fenced;continue
        if fenced:continue
        m=re.match(r'^#{1,6}\s+(.*)',line)
        if m:result.add(slug(m.group(1)))
    return result

def main():
    files=[p for p in ROOT.rglob('*') if published(p)]
    with (ROOT/'verification/FILE_INDEX.csv').open(newline='') as f:
        inventory=list(csv.DictReader(f))
    indexed=[row['path'] for row in inventory]
    expected={p.relative_to(ROOT).as_posix() for p in files}
    assert len(indexed)==len(set(indexed)), 'duplicate paths in FILE_INDEX.csv'
    assert set(indexed)==expected, ('file index coverage mismatch',
        sorted(expected-set(indexed)), sorted(set(indexed)-expected))
    markdown_links=0;colab_links=0;payloads=0;zips=0
    for p in files:
        if p.suffix=='.py':compile(p.read_text(),str(p),'exec')
        if p.suffix=='.md':
            for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)\)',p.read_text()):
                if target.startswith('https://colab.research.google.com/github/preecharatchanon-arch/Ratc/blob/main/'):
                    rel=target.split('/blob/main/',1)[1];assert (REPO/rel).is_file(),(p,target);colab_links+=1
                if target.startswith(('http:','https:','mailto:','sandbox:')):continue
                rel,sep,anchor=target.partition('#');dest=(p.parent/urllib.parse.unquote(rel)).resolve() if rel else p
                assert dest.exists(),(p,target);markdown_links+=1
                if sep and dest.suffix=='.md':assert urllib.parse.unquote(anchor) in anchors(dest),(p,target)
    for old,new in ALIASES.items():
        assert (ROOT/old).read_bytes()==(ROOT/new).read_bytes(),old
    canonical_notebooks=sorted(p for p in (ROOT/'experiments').rglob('*.ipynb') if published(p))
    for notebook_path in canonical_notebooks:
        new=notebook_path.relative_to(ROOT).as_posix()
        n=json.loads(notebook_path.read_text());payload=None;expected=None
        for c in n['cells']:
            if c['cell_type']!='code':continue
            assert c.get('execution_count') is not None,(new,'unexecuted cell')
            assert not any(o.get('output_type')=='error' for o in c.get('outputs',[])),new
            tree=ast.parse(''.join(c['source']))
            for node in ast.walk(tree):
                if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                    name=node.targets[0].id
                    if name=='EMBEDDED_INPUTS':payload=base64.b64decode(ast.literal_eval(node.value))
                    if name in ['INPUT_SHA256','PAYLOAD_SHA256']:expected=ast.literal_eval(node.value)
        assert hashlib.sha256(payload).hexdigest()==expected,new
        with zipfile.ZipFile(io.BytesIO(payload)) as z:assert z.testzip() is None,new
        payloads+=1
    for p in (ROOT/'archives').glob('*.zip'):
        with zipfile.ZipFile(p) as z:assert z.testzip() is None,p
        zips+=1
    index={r['path']:r for r in json.loads((REPO/'ARTIFACT_CHECKSUMS.json').read_text())}
    for p in files:
        rel=p.relative_to(REPO).as_posix();raw=p.read_bytes()
        assert rel in index,('not indexed',rel)
        assert index[rel]['bytes']==len(raw) and index[rel]['sha256']==hashlib.sha256(raw).hexdigest(),rel
    with (ROOT/'verification/PATH_MAP.csv').open() as f:
        moves=list(csv.DictReader(f))
    for m in moves:
        p=REPO/m['new_path'];assert p.is_file(),m['new_path']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==m['new_sha256'],m['new_path']
    result=dict(project_files=len(files),local_markdown_targets=markdown_links,colab_targets=colab_links,
                indexed_current_files=len(indexed),all_current_files_indexed=True,
                unchanged_notebook_aliases=3,verified_notebook_payloads=payloads,CRC_verified_run_archives=zips,
                mapped_original_files=len(moves),all_current_file_checksums_match=True,
                scope='Organization and artifact integrity; no fresh biological validation or full research rerun')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
