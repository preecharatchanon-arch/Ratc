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
import subprocess
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
    # Execute the generated manifest script with Leaflet doubles. A local-file
    # export must retain route overlays while making zero external tile calls.
    from app.exports import _driver_html
    route = {'truck_id': 1, 'geometry': [[7, 100], [7.01, 100.01]], 'stops': [
        {'kind': 'depot', 'sequence': 0, 'lat': 7, 'lon': 100},
        {'kind': 'customer', 'sequence': 1, 'lat': 7.01, 'lon': 100.01}]}
    status = {'phase': 'optimized', 'title': 'Complete', 'detail': 'Checked', 'badge': 'OPTIMIZED', 'completed': True}
    html = _driver_html(route, 1, status)
    assert '<meta name="referrer" content="strict-origin">' in html
    script = re.findall(r'<script>(.*?)</script>', html, re.S)[0]
    node_check = r"""
const vm=require('node:vm'), assert=require('node:assert/strict');
let input='';process.stdin.on('data',x=>input+=x);process.stdin.on('end',()=>{
const code=JSON.parse(input);
for(const protocol of ['file:','data:','http:','https:']){
  const calls=[],notice={textContent:''};let overlays=0,markers=0;
  const shape={addTo(){return this},getBounds(){return {isValid:()=>true}}};
  const map={fitBounds(){},setView(){}};
  const context={location:{protocol},document:{getElementById(){return notice}},
    L:{map(){return map},tileLayer(url,options){calls.push({url,options});return {addTo(){return this},on(name,fn){this[name]=fn;fn();return this}}},
      polyline(){overlays++;return shape},circleMarker(){markers++;return {bindPopup(){return this},addTo(){return this}}}}};
  vm.runInNewContext(code,context);
  assert.equal(overlays,1);assert.equal(markers,2);
  assert.equal(calls.length,['http:','https:'].includes(protocol)?1:0);
  for(const {url,options} of calls){
    assert.equal(url,'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
    assert.equal(options.referrerPolicy,'strict-origin');
    assert.ok(options.attribution.includes('openstreetmap.org/copyright'));
    assert.ok(notice.textContent.includes('unavailable'));
  }
}
console.log('PASS: exported route overlays, no local-file tile requests, HTTP(S) tile policy and failure notice');
});
"""
    subprocess.run(['node', '-e', node_check], input=json.dumps(script), text=True, check=True)
    for name in ['app.js', 'driver.js', 'simulation.js']:
        js = (SOURCE / 'app/static' / name).read_text()
        assert 'https://{s}.tile.openstreetmap.org' not in js, name
        assert "referrerPolicy:'strict-origin'" in js, name
        assert 'openstreetmap.org/copyright' in js, name
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
