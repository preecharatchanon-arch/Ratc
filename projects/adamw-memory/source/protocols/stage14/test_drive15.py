"""SDK facade tests: request completion, server checksums, quota and publication."""
import copy,hashlib,json,tempfile,types,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from drive_store15 import DriveBackend
from test_incremental15 import LocalBackend,seed_legacy,start,SimulatedDisconnect
from archive_io import pack

class Request:
    def __init__(self,fn):self.fn=fn
    def execute(self,**kw):return self.fn()
    def next_chunk(self,**kw):return None,self.fn()

class Missing(Exception):
    resp=types.SimpleNamespace(status=404)

class Service:
    def __init__(self):
        self.nodes={'run':dict(id='run',name='Stage14',mimeType='application/vnd.google-apps.folder',parents=[])}
        self.bytes={};self.lost=False;self.bad=False;self.generated=0;self.fail_before=None;self.quota={'usage':'0','usageInDrive':'0','limit':'15000000000'}
    def files(self):return self
    def about(self):return self
    def get(self,fileId=None,**kw):
        def fn():
            if fileId is None:return {'storageQuota':self.quota}
            if fileId not in self.nodes:raise Missing()
            m=copy.deepcopy(self.nodes[fileId])
            if fileId in self.bytes:m.update(size=str(len(self.bytes[fileId])),md5Checksum='bad' if self.bad else hashlib.md5(self.bytes[fileId]).hexdigest())
            return m
        return Request(fn)
    def get_media(self,fileId):return Request(lambda:self.bytes[fileId])
    def list(self,q,**kw):
        if 'in parents' in q:
            parent=q.split("'")[1];rows=[self.get(fileId=i).execute() for i,m in self.nodes.items() if parent in m.get('parents',[]) and not m.get('trashed')]
        else:rows=[self.get(fileId=i).execute() for i in self.nodes]
        return Request(lambda:{'files':rows})
    def generateIds(self,**kw):
        self.generated+=1;return Request(lambda:{'ids':[uuid.uuid4().hex]})
    def create(self,body,media_body=None,**kw):
        def fn():
            if self.fail_before:raise self.fail_before
            m=copy.deepcopy(body);i=m.setdefault('id',uuid.uuid4().hex);m.setdefault('mimeType','application/octet-stream');self.nodes[i]=m
            if media_body is not None:self.bytes[i]=Path(media_body.filename).read_bytes()
            if self.lost:self.lost=False;raise ConnectionError('Injected response loss after server completion')
            return self.get(fileId=i).execute()
        return Request(fn)
    def update(self,fileId,body,media_body=None,**kw):
        def fn():
            self.nodes[fileId].update(copy.deepcopy(body))
            if media_body is not None:self.bytes[fileId]=Path(media_body.filename).read_bytes()
            if self.lost:self.lost=False;raise ConnectionError('Injected response loss after server completion')
            return self.get(fileId=fileId).execute()
        return Request(fn)
    def delete(self,fileId):
        def fn():
            self.nodes.pop(fileId);self.bytes.pop(fileId,None)
            if self.lost:self.lost=False;raise ConnectionError('Deletion response lost')
        return Request(fn)

class MediaUpload:
    def __init__(self,filename,**kw):self.filename=filename
class MediaDownload:
    def __init__(self,out,req,**kw):self.out=out;self.req=req
    def next_chunk(self,**kw):self.out.write(self.req.execute());return None,True

class TransportTests(unittest.TestCase):
    def fake_sdk(self):
        m=types.ModuleType('googleapiclient.http');m.MediaFileUpload=MediaUpload;m.MediaIoBaseDownload=MediaDownload
        return patch.dict('sys.modules',{'googleapiclient.http':m})
    def test_lost_upload_response_reuses_pregenerated_id_and_download_matches(self):
        with tempfile.TemporaryDirectory() as td,self.fake_sdk():
            s=Service();b=DriveBackend(s,'run');p=Path(td)/'a';p.write_bytes(b'completed');s.lost=True
            m=b.put('run','a.zip',p);self.assertEqual(s.generated,1)
            out=Path(td)/'b';b.download(m['id'],out);self.assertEqual(out.read_bytes(),p.read_bytes())
    def test_bad_server_checksum_refuses_upload_and_download(self):
        with tempfile.TemporaryDirectory() as td,self.fake_sdk():
            s=Service();b=DriveBackend(s,'run');p=Path(td)/'a';p.write_bytes(b'x');s.bad=True
            self.assertRaises(RuntimeError,b.put,'run','a.zip',p)
            file_id=next(iter(s.bytes));self.assertRaises(RuntimeError,b.download,file_id,Path(td)/'b')
    def test_upload_error_before_commit_is_not_replaced_by_metadata_404(self):
        with tempfile.TemporaryDirectory() as td,self.fake_sdk():
            s=Service();b=DriveBackend(s,'run');p=Path(td)/'a';p.write_bytes(b'x')
            s.fail_before=ConnectionError('original upload failure')
            self.assertRaisesRegex(ConnectionError,'original upload failure',b.put,'run','a.zip',p)
            self.assertEqual(s.generated,1);self.assertFalse(s.bytes)
    def test_lost_pointer_response_readback_and_conflicting_pointer_guard(self):
        s=Service();b=DriveBackend(s,'run');s.lost=True
        b.set_heads('run','one','two','tag',('',''))
        self.assertRaises(RuntimeError,b.set_heads,'run','three','one','tag',('',''))
        self.assertEqual(s.nodes['run']['appProperties']['current'],'one')
    def test_lost_folder_response_uses_exact_id(self):
        s=Service();b=DriveBackend(s,'run');s.lost=True;m=b.mkdir('run','CHECKPOINTS_15MIN','tag')
        self.assertEqual(s.generated,1);self.assertEqual(m['name'],'CHECKPOINTS_15MIN');self.assertEqual(len(s.nodes),2)
    def test_lost_delete_response_confirms_missing_id(self):
        s=Service();b=DriveBackend(s,'run');m=b.mkdir('run','CHECKPOINTS_15MIN','tag');s.lost=True
        b.delete(m['id']);self.assertNotIn(m['id'],s.nodes)
    def test_quota_counts_trash_revisions_project_descendants_and_account(self):
        s=Service();s.nodes.update({'nx':dict(id='nx',name='NEXUS',mimeType='application/vnd.google-apps.folder',parents=[]),
            'data':dict(id='data',name='data.zip',parents=['nx'],quotaBytesUsed='1100',size='100',trashed=True),
            'cp':dict(id='cp',name='CHECKPOINT.zip',parents=['run'],quotaBytesUsed='200'),
            'other':dict(id='other',name='personal',parents=[],quotaBytesUsed='500')})
        s.quota.update(usage='2100',usageInDrive='1800');u=DriveBackend(s,'run').usage(None)
        self.assertEqual(u['project_bytes'],1300);self.assertEqual(u['checkpoint_bytes'],200);self.assertEqual(u['account_bytes'],2100)
    def test_deleted_file_in_stale_global_listing_is_not_counted_again(self):
        s=Service();s.nodes['old']=dict(id='old',name='CHECKPOINT.zip',parents=['run'],quotaBytesUsed='5000000000');s.bytes['old']=b'old'
        b=DriveBackend(s,'run');stale=b._list("'me' in owners");b.delete('old');original=b._list
        with patch.object(b,'_list',side_effect=lambda q:stale if q=="'me' in owners" else original(q)):
            u=b.usage(None);self.assertEqual(u['checkpoint_bytes'],0);self.assertEqual(u['project_bytes'],0)
    def test_reconnect_direct_metadata_excludes_deleted_legacy_ghost(self):
        s=Service();s.nodes['old']=dict(id='old',name='CHECKPOINT.zip',parents=['run'],quotaBytesUsed='5000000000');s.bytes['old']=b'old'
        b=DriveBackend(s,'run');stale=b._list("'me' in owners");s.nodes.pop('old');s.bytes.pop('old');fresh=DriveBackend(s,'run');original=fresh._list
        with patch.object(fresh,'_list',side_effect=lambda q:stale if q=="'me' in owners" else original(q)):
            u=fresh.usage(None);self.assertEqual(u['checkpoint_bytes'],0);self.assertIn('old',fresh._deleted)
    def test_final_disconnect_during_upload_or_rename_recovers(self):
        for event in ('before_FINISHED','after_FINISHED','before_rename','after_rename'):
            with self.subTest(event=event),tempfile.TemporaryDirectory() as td:
                b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.checkpoint(True);c.checkpoint(True)
                fired=[False]
                def hook(name,m):
                    if name==event and not fired[0]:fired[0]=True;raise SimulatedDisconnect()
                b.hook=hook;self.assertRaises(SimulatedDisconnect,c.finish);b.hook=lambda *a:None;c.lease.release()
                from checkpoint15 import IncrementalCampaign
                fresh=LocalBackend(b.root);r=IncrementalCampaign(Path(td)/'mount',Path(td)/'restore',c.identity,fresh)
                status=r.activate();self.assertEqual(status,'CHECKPOINT' if event=='before_FINISHED' else 'FINISHED')
                self.assertEqual(json.loads((r.local/'units/U/value.json').read_text())['value'],1);r.lease.release()
                if status=='FINISHED':self.assertFalse(fresh.list(r.store_id))

if __name__=='__main__':unittest.main()
