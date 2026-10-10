"""Real httplib2/auth/client requests against a local resumable-upload server."""
import contextlib,hashlib,json,os,re,tempfile,threading,unittest,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import httplib2
from google.auth.credentials import AnonymousCredentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.http import HttpRequest,MediaFileUpload
from drive_store15 import DriveBackend,authorized_transport


class UploadServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self):
        super().__init__(('127.0.0.1',0),Handler);self.sessions={};self.files={};self.partial_responses=0
        self.base=f'http://127.0.0.1:{self.server_port}'

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def send(self,status,body=b'',**headers):
        self.send_response(status);self.send_header('Content-Length',str(len(body)))
        for key,value in headers.items():self.send_header(key,value)
        self.end_headers();self.wfile.write(body)
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.sessions[body['id']]={'meta':body,'bytes':bytearray()}
        self.send(200,Location=self.server.base+'/session/'+body['id'])
    def do_PUT(self):
        key=self.path.rsplit('/',1)[-1];session=self.server.sessions[key]
        data=self.rfile.read(int(self.headers.get('Content-Length',0)));span=self.headers.get('Content-Range','')
        found=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',span)
        if not found:self.send(400,b'Unexpected Content-Range');return
        start,end,total=map(int,found.groups())
        if start!=len(session['bytes']) or end-start+1!=len(data):self.send(400,b'Unexpected upload offset');return
        session['bytes'].extend(data)
        if len(session['bytes'])<total:
            self.server.partial_responses+=1
            # Deliberately no Location: this is the exact status that broke Colab.
            self.send(308,Range=f'bytes=0-{len(session["bytes"])-1}')
        else:
            raw=bytes(session['bytes']);m=dict(session['meta'],mimeType='application/octet-stream',size=str(len(raw)),
                md5Checksum=hashlib.md5(raw).hexdigest(),quotaBytesUsed=str(len(raw)))
            self.server.files[key]=(m,raw);self.send(200,json.dumps(m).encode(),**{'Content-Type':'application/json'})
    def do_GET(self):
        key=self.path.rsplit('/',1)[-1]
        if key not in self.server.files:
            self.send(404,json.dumps({'error':{'message':'File not found','code':404}}).encode(),**{'Content-Type':'application/json'});return
        m,raw=self.server.files[key]
        if self.path.startswith('/meta/'):
            self.send(200,json.dumps(m).encode(),**{'Content-Type':'application/json'});return
        r=self.headers.get('Range');found=re.fullmatch(r'bytes=(\d+)-(\d+)',r or '')
        if found:
            lo,hi=map(int,found.groups());hi=min(hi,len(raw)-1);data=raw[lo:hi+1]
            self.send(206,data,**{'Content-Range':f'bytes {lo}-{hi}/{len(raw)}','Content-Type':'application/octet-stream'})
        else:self.send(200,raw,**{'Content-Type':'application/octet-stream'})

class Service:
    """Only endpoint construction is replaced; HttpRequest/upload/auth/HTTP are real."""
    def __init__(self,http,server):self._http=http;self.server=server;self.generated=0
    def files(self):return self
    def generateIds(self,**kw):
        self.generated+=1
        class Result:
            def execute(self,**kw):return {'ids':[uuid.uuid4().hex]}
        return Result()
    def create(self,body,media_body,**kw):
        return HttpRequest(self._http,lambda response,content:json.loads(content),self.server.base+'/init',method='POST',
            body=json.dumps(body),headers={'content-type':'application/json'},resumable=media_body)
    def get(self,fileId,**kw):
        if fileId=='run':
            class Result:
                def execute(self,**kw):return dict(id='run',mimeType='application/vnd.google-apps.folder')
            return Result()
        return HttpRequest(self._http,lambda response,content:json.loads(content),self.server.base+'/meta/'+fileId)
    def get_media(self,fileId):return HttpRequest(self._http,lambda response,content:content,self.server.base+'/media/'+fileId)

@contextlib.contextmanager
def server():
    with patch.dict(os.environ,{'HTTP_PROXY':'','HTTPS_PROXY':'','http_proxy':'','https_proxy':''}):
        s=UploadServer();t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
        try:yield s
        finally:s.shutdown();s.server_close();t.join(timeout=2)

class RealHTTPTests(unittest.TestCase):
    def test_old_bare_transport_reproduces_redirect_error_and_404_does_not_hide_it(self):
        with tempfile.TemporaryDirectory() as td,server() as s:
            p=Path(td)/'data';p.write_bytes(b'x'*(9*1024**2))
            http=AuthorizedHttp(AnonymousCredentials(),http=httplib2.Http(timeout=5,proxy_info=None))
            if 308 not in http.http.redirect_codes:self.skipTest('Installed httplib2 already excludes 308')
            b=DriveBackend(Service(http,s),'run')
            self.assertRaises(httplib2.RedirectMissingLocation,b.put,'run','probe.zip',p)
            self.assertEqual(s.partial_responses,1);self.assertEqual(s.files,{})
            self.assertEqual(b.service.generated,1)
    def test_correct_transport_real_two_chunk_upload_and_multi_chunk_download(self):
        with tempfile.TemporaryDirectory() as td,server() as s:
            p=Path(td)/'data';p.write_bytes(b'NEXUS!'*(9*1024**2//6+1))
            http=authorized_transport(AnonymousCredentials(),timeout=5)
            self.assertNotIn(308,http.http.redirect_codes);self.assertEqual(http.http.timeout,5)
            b=DriveBackend(Service(http,s),'run');m=b.put('run','probe.zip',p,{'kind':'probe'})
            self.assertEqual(s.partial_responses,1);self.assertEqual(m['md5Checksum'],hashlib.md5(p.read_bytes()).hexdigest())
            out=Path(td)/'download';b.download(m['id'],out)
            self.assertEqual(hashlib.sha256(out.read_bytes()).digest(),hashlib.sha256(p.read_bytes()).digest())
            self.assertEqual(b.service.generated,1)

if __name__=='__main__':unittest.main()
