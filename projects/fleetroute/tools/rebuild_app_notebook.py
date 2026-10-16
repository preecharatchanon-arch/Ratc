"""Repack the notebook from its existing member list and the reviewed source tree."""
import base64
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'
NOTEBOOK = ROOT / 'FleetRoute_App.ipynb'


def rebuild():
    notebook = json.loads(NOTEBOOK.read_text())
    cell = next(c for c in notebook['cells'] if 'EMBEDDED_APP_ZIP_B64 =' in ''.join(c.get('source', [])))
    code = ''.join(cell['source'])
    pattern = r'EMBEDDED_APP_ZIP_B64 = """(.*?)"""'
    match = re.search(pattern, code, re.S)
    original = zipfile.ZipFile(io.BytesIO(base64.b64decode(match[1], validate=True)))
    manifest_path = SOURCE / 'RELEASE_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    for name in manifest['files']:
        data = (SOURCE / name).read_bytes()
        manifest['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    solver_sha = hashlib.sha256((SOURCE / 'solver.cpp').read_bytes()).hexdigest()
    assert solver_sha == manifest['solver_source_sha256'], 'Optimizer identity changed'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for info in original.infolist():
            rel = Path(info.filename).relative_to('fleetroute_app')
            assert '..' not in rel.parts
            archive.writestr(info, (SOURCE / rel).read_bytes())
    raw = output.getvalue()
    code = code[:match.start(1)] + base64.b64encode(raw).decode() + code[match.end(1):]
    for key, data in [('EMBEDDED_APP_SHA256', raw), ('EXPECTED_RELEASE_MANIFEST_SHA256', manifest_path.read_bytes())]:
        code = re.sub(key + r' = "[a-f0-9]+"', key + ' = "' + hashlib.sha256(data).hexdigest() + '"', code)
    cell['source'] = code.splitlines(keepends=True)
    NOTEBOOK.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n')
    print('Rebuilt notebook; optimizer unchanged:', solver_sha)


if __name__ == '__main__':
    rebuild()
