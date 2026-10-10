from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1]
m=json.loads((root/'PACKAGE_MANIFEST.json').read_text())
expected={x['path'] for x in m['files']}
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='PACKAGE_MANIFEST.json' and '__pycache__' not in p.parts}
assert expected==actual,'Package membership differs'
for e in m['files']:
 b=(root/e['path']).read_bytes();assert len(b)==e['bytes'] and hashlib.sha256(b).hexdigest()==e['sha256'],e['path']
print('Verified',len(expected),'package payloads')
