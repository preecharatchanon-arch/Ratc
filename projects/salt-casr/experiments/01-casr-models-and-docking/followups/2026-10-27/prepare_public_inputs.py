"""Restore only the three immutable public inputs needed for model replay."""
import base64,hashlib,json
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parent
FILES=[('chemistry.py','ea0dd73a599703343df7b67ec7bae345edd955aa'),
       ('input/chemical_activity_dataset.csv','910f50506555b4b88053bafa4928f9135a0206d3'),
       ('input/held_out_predictions.csv','512852a3d6c5f6a316528da5d611d00aea4fb244')]
def main():
    for name,expected in FILES:
        path=ROOT/name
        if path.exists():data=path.read_bytes()
        else:
            url='https://api.github.com/repos/preecharatchanon-arch/Ratc/git/blobs/'+expected
            with urlopen(Request(url,headers={'User-Agent':'CaSR-focused-followup/1.0','Accept':'application/vnd.github+json'}),timeout=45) as h:r=json.load(h)
            if r.get('encoding')!='base64':raise ValueError('Unexpected public blob encoding')
            data=base64.b64decode(r['content'])
        actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if actual!=expected:raise ValueError('Frozen source hash differs: '+name)
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);print('Verified',name)
if __name__=='__main__':main()
