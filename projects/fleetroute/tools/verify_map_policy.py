"""Local HTTP/authentication and embedded-release regression checks; no tile requests."""
import ast
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'


def verify():
    with tempfile.TemporaryDirectory(prefix='fleetroute-map-policy-') as runtime:
        os.environ.update(VRP_RUNTIME_DIR=runtime, VRP_DATABASE_PATH=str(Path(runtime) / 'test.sqlite3'), VRP_APP_TOKEN='local-regression-token')
        sys.path.insert(0, str(SOURCE))
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app, base_url='https://testserver') as client:
            denied = client.get('/', follow_redirects=False)
            assert denied.status_code == 401
            assert denied.headers['referrer-policy'] == 'no-referrer'
            redirect = client.get('/?token=local-regression-token&view=plan', follow_redirects=False)
            assert redirect.status_code == 303
            assert redirect.headers['location'] == '/?view=plan'
            assert redirect.headers['referrer-policy'] == 'no-referrer'
            cookie = redirect.headers['set-cookie']
            assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie
            for path in ['/', '/simulation', '/static/app.js', '/static/driver.js', '/static/simulation.js']:
                response = client.get(path)
                assert response.status_code == 200, (path, response.status_code)
                assert response.headers['referrer-policy'] == 'strict-origin', path
                csp = response.headers['content-security-policy']
                assert 'https://tile.openstreetmap.org' in csp
                assert 'https://services.arcgisonline.com' in csp
                assert "script-src 'self'" in csp and "connect-src 'self'" in csp
    notebook = json.loads((ROOT / 'FleetRoute_App.ipynb').read_text())
    constants = {}
    for cell in notebook['cells']:
        if cell['cell_type'] != 'code':
            continue
        tree = ast.parse(''.join(cell['source']))
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value.value
    raw = base64.b64decode(constants['EMBEDDED_APP_ZIP_B64'], validate=True)
    assert hashlib.sha256(raw).hexdigest() == constants['EMBEDDED_APP_SHA256']
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        manifest_raw = archive.read('fleetroute_app/RELEASE_MANIFEST.json')
        assert hashlib.sha256(manifest_raw).hexdigest() == constants['EXPECTED_RELEASE_MANIFEST_SHA256']
        manifest = json.loads(manifest_raw)
        assert manifest['file_count'] == len(manifest['files'])
        for path, meta in manifest['files'].items():
            data = archive.read('fleetroute_app/' + path)
            assert len(data) == meta['bytes'] and hashlib.sha256(data).hexdigest() == meta['sha256'], path
            assert data == (SOURCE / path).read_bytes(), path
        assert hashlib.sha256(archive.read('fleetroute_app/solver.cpp')).hexdigest() == constants['EXPECTED_SOLVER_SHA256']
    print('PASS: authentication, origin-only referrers, CSP, embedded ZIP, all member hashes, source/payload identity, unchanged optimizer')
    print('Scope: local regression checks; external tile availability and a full application run are separate.')


if __name__ == '__main__':
    verify()
