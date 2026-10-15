"""Retrieve original coordinate files; verify hashes and reuse exact snapshots."""
from project_paths import DATA
from pathlib import Path
import concurrent.futures, hashlib, json, urllib.request
ROOT=DATA

def retrieve(record):
    destination=ROOT/record['file']
    def matches(raw):return hashlib.sha256(raw).hexdigest()==record['sha256']
    if destination.is_file() and matches(destination.read_bytes()):return destination.name+' verified cache'
    if record.get('snapshot'):
        raw=(ROOT/record['snapshot']).read_bytes()
    else:
        req=urllib.request.Request(record['url'],headers={'User-Agent':'TRPV1 structural evidence research'})
        with urllib.request.urlopen(req,timeout=90) as response:raw=response.read()
    if not matches(raw):
        raise ValueError('Source version differs from reviewed input: '+record['file']+
                         '. Review the new source explicitly; no silent substitution.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix(destination.suffix+'.part')
    temporary.write_bytes(raw);temporary.replace(destination)
    return destination.name+' retrieved and verified'

if __name__=='__main__':
    records=json.loads((ROOT/'INPUT_MANIFEST.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(retrieve,records):print(result)
