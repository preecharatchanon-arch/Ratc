"""Deterministic server simulator and crash recovery tests; no research data."""
import contextlib, copy, hashlib, io, json, shutil, tempfile, unittest, uuid, zipfile
from pathlib import Path
import numpy as np
from archive_io import Campaign, pack, sha, verify, write_json
from checkpoint15 import IncrementalCampaign,CheckpointBlocked


class SimulatedDisconnect(BaseException):pass


class LocalBackend:
    """Persists service state across fresh clients; simulates exact server checksums."""
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.db=self.root/'server.json'
        self.nodes=json.loads(self.db.read_text()) if self.db.exists() else {'run':dict(id='run',name='Stage14',mimeType='application/vnd.google-apps.folder',parents=[],appProperties={})}
        self.run_id='run';self.on_progress=lambda:None;self.hook=lambda event,m:None
        self.other_project_bytes=0;self.other_account_bytes=0;self.limit=15_000_000_000;self.uploads=[]
        self._persist()
    def _persist(self):write_json(self.db,self.nodes)
    def list(self,parent):return [self.meta(i) for i,m in self.nodes.items() if parent in m.get('parents',[])]
    def meta(self,file_id):
        m=copy.deepcopy(self.nodes[file_id])
        if m['mimeType']!='application/vnd.google-apps.folder':
            b=(self.root/file_id).read_bytes();m.update(size=str(len(b)),quotaBytesUsed=str(len(b)),md5Checksum=hashlib.md5(b).hexdigest())
        return m
    def mkdir(self,parent,name,tag):
        i=uuid.uuid4().hex;self.nodes[i]=dict(id=i,name=name,mimeType='application/vnd.google-apps.folder',parents=[parent],appProperties=dict(nexus15=tag,kind='store'))
        self._persist();return self.meta(i)
    def put(self,parent,name,path,props=None,replace_id=None):
        kind=(props or {}).get('kind','lease' if name=='LEASE.json' else 'file')
        self.hook('before_'+kind,None);i=replace_id or uuid.uuid4().hex
        if replace_id:m=self.nodes[i];m['name']=name
        else:self.nodes[i]=dict(id=i,name=name,mimeType='application/octet-stream',parents=[parent],appProperties=props or {})
        shutil.copyfile(path,self.root/i);self._persist();m=self.meta(i);self.uploads.append((kind,int(m['size'])))
        self.hook('after_'+kind,m);return m
    def download(self,file_id,path):
        self.hook('before_download',None);Path(path).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.root/file_id,path)
        self.hook('after_download',None);return self.meta(file_id)
    def read_json(self,file_id):return json.loads((self.root/file_id).read_text())
    def delete(self,file_id):
        m=self.meta(file_id);self.hook('before_delete',m)
        self.nodes.pop(file_id);(self.root/file_id).unlink(missing_ok=True);self._persist();self.hook('after_delete',m)
    def set_heads(self,folder,current,previous,tag,expected):
        p=self.nodes[folder]['appProperties'];assert (p.get('current',''),p.get('previous',''))==tuple(expected)
        self.hook('before_heads',None);p.update(current=current or '',previous=previous or '');self._persist();self.hook('after_heads',None)
        return self.meta(folder)
    def rename(self,file_id,name):
        self.hook('before_rename',None);self.nodes[file_id]['name']=name;self._persist();self.hook('after_rename',None)
        return self.meta(file_id)
    def usage(self,store_id):
        project=sum(int(self.meta(i).get('quotaBytesUsed',0)) for i in self.nodes)
        cp=sum(int(self.meta(i).get('quotaBytesUsed',0)) for i,m in self.nodes.items()
               if store_id in m.get('parents',[]) or m['name'] in ('CHECKPOINT.zip','CHECKPOINT_PREVIOUS.zip'))
        return dict(project_bytes=project+self.other_project_bytes,checkpoint_bytes=cp,
                    account_bytes=project+self.other_account_bytes,account_limit=self.limit,includes_trash=True)


def seed_legacy(backend,root,identity={'test':15}):
    payload=Path(root)/'seed';f=payload/'units'/'U'/'value.json';f.parent.mkdir(parents=True,exist_ok=True);f.write_text('{"value":1}')
    z=pack(payload,Path(root)/'legacy.zip',identity,'CHECKPOINT',[f])
    p=Path(root)/'identity.json';write_json(p,identity);backend.put('run','IDENTITY.json',p)
    backend.put('run','CHECKPOINT.zip',z);backend.put('run','CHECKPOINT_PREVIOUS.zip',z)


def start(backend,root,identity={'test':15},name='local'):
    c=IncrementalCampaign(Path(root)/'mounted',Path(root)/name,identity,backend);c.require_checkpoint=True;c.block_size=1024
    assert c.activate()=='CHECKPOINT';return c


class IncrementalTests(unittest.TestCase):
    def test_migration_restore_two_points_cleanup_and_unchanged_no_upload(self):
        with tempfile.TemporaryDirectory() as td:
            b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td)
            self.assertEqual(c.checkpoint_seconds,900);c.checkpoint(True);self.assertTrue(any(m['name']=='CHECKPOINT.zip' for m in b.list('run')))
            old_blob_bytes=sum(n for k,n in b.uploads if k=='blob');c.checkpoint(True)
            self.assertEqual(sum(n for k,n in b.uploads if k=='blob'),old_blob_bytes)
            self.assertFalse(any(m['name'].startswith('CHECKPOINT.') or m['name']=='CHECKPOINT_PREVIOUS.zip' for m in b.list('run')))
            self.assertEqual(sum(c._owned(m,'commit') for m in b.list(c.store_id)),2)
            c.lease.release();fresh=LocalBackend(b.root);r=start(fresh,td,name='restored')
            self.assertEqual(json.loads((r.local/'units/U/value.json').read_text()),{'value':1});r.lease.release()

    def test_incremental_fortran_columns_share_old_chunks_and_restore_arrays(self):
        from runner14 import save
        with tempfile.TemporaryDirectory() as td:
            b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.checkpoint(True)
            rng=np.random.default_rng(75);Y=np.asfortranarray(rng.normal(size=(1024,12)).astype('float32'));p=c.local/'units/U/operator_h16.resume.npz'
            save(p,Y=np.asfortranarray(Y[:,:8]),meta=np.asarray('x'));c.checkpoint(True)
            first=c.current['payload']['files']['units/U/operator_h16.resume.npz']
            first_ids={r['id'] for m in first['members'] for r in m['chunks']}
            before=sum(n for k,n in b.uploads if k=='blob')
            save(p,Y=Y,meta=np.asarray('x'));c.checkpoint(True)
            second=c.current['payload']['files']['units/U/operator_h16.resume.npz']
            ids={r['id'] for m in second['members'] for r in m['chunks']}
            self.assertTrue(first_ids<=ids)
            self.assertLess(sum(n for k,n in b.uploads if k=='blob')-before,Y.nbytes*.7)
            c.lease.release();r=start(LocalBackend(b.root),td,name='restored')
            with np.load(r.local/p.relative_to(c.local),allow_pickle=False) as z:
                self.assertTrue(np.array_equal(z['Y'],Y));self.assertTrue(z['Y'].flags.f_contiguous)
            r.lease.release()

    def test_disconnect_at_upload_commit_pointer_and_gc_preserves_a_valid_point(self):
        events=['before_blob','after_blob','before_commit','after_commit','before_heads','after_heads','before_delete','after_delete']
        for target in events:
            with self.subTest(target=target),tempfile.TemporaryDirectory() as td:
                b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.checkpoint(True);c.checkpoint(True)
                (c.local/'units/U/value.json').write_text('{"value":2}')
                fired=[False]
                def hook(event,m):
                    if event==target and not fired[0]:fired[0]=True;raise SimulatedDisconnect()
                b.hook=hook
                with self.assertRaises(SimulatedDisconnect):c.checkpoint(True)
                self.assertTrue(fired[0]);b.hook=lambda event,m:None;c.lease.release()
                r=start(LocalBackend(b.root),td,name='restored')
                expected=2 if target in ('after_heads','before_delete','after_delete') else 1
                self.assertEqual(json.loads((r.local/'units/U/value.json').read_text())['value'],expected)
                r.checkpoint(True);r.lease.release()

    def test_corrupt_newest_object_falls_back_without_erasing_predecessor(self):
        with tempfile.TemporaryDirectory() as td:
            b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.checkpoint(True)
            (c.local/'units/U/value.json').write_text('{"value":2}');c.checkpoint(True)
            latest=c.current['payload']['files']['units/U/value.json']['object']['id']
            (b.root/latest).write_bytes(b'bad');c.lease.release()
            r=start(LocalBackend(b.root),td,name='restored')
            self.assertEqual(json.loads((r.local/'units/U/value.json').read_text())['value'],1)
            r.checkpoint(True);r.lease.release()

    def test_quota_blocks_before_upload_and_keeps_saved_progress(self):
        with tempfile.TemporaryDirectory() as td:
            b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.checkpoint(True)
            (c.local/'units/U/value.json').write_text('{"value":2}');before=list(b.uploads)
            b.other_account_bytes=15_000_000_000
            self.assertRaises(CheckpointBlocked,c.checkpoint,True)
            self.assertEqual([x for x in b.uploads[len(before):] if x[0] in ('blob','commit')],[])
            c.lease.release();r=start(LocalBackend(b.root),td,name='restored')
            self.assertEqual(json.loads((r.local/'units/U/value.json').read_text())['value'],1);r.lease.release()

    def test_changed_legacy_checkpoint_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.checkpoint(True)
            old=next(m for m in b.list('run') if m['name']=='CHECKPOINT.zip');(b.root/old['id']).write_bytes(b'changed by other runtime')
            self.assertRaises(CheckpointBlocked,c.checkpoint,True)
            self.assertTrue((b.root/old['id']).exists());c.lease.release()

    def test_unrelated_store_file_is_never_collected(self):
        with tempfile.TemporaryDirectory() as td:
            b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.checkpoint(True)
            p=Path(td)/'personal.txt';p.write_text('protected');m=b.put(c.store_id,'personal.txt',p)
            c.checkpoint(True);self.assertTrue((b.root/m['id']).exists());c.lease.release()

    def test_account_and_checkpoint_limits_block_before_data_upload(self):
        for constraint in ('account','checkpoint'):
            with self.subTest(constraint=constraint),tempfile.TemporaryDirectory() as td:
                b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.checkpoint(True)
                (c.local/'units/U/value.json').write_text('{"value":2}')
                if constraint=='account':b.other_account_bytes=15_000_000_000
                else:c.checkpoint_limit=1
                before=len(b.uploads);self.assertRaises(CheckpointBlocked,c.checkpoint,True)
                self.assertFalse(any(k in ('blob','commit') for k,n in b.uploads[before:]));c.lease.release()

    def test_empty_store_after_failed_first_upload_imports_legacy_and_probe_is_removed(self):
        with tempfile.TemporaryDirectory() as td:
            b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td)
            def fail(event,m):
                if event=='before_blob':raise ConnectionError('first upload failed')
            b.hook=fail;self.assertRaises(ConnectionError,c.checkpoint,True);b.hook=lambda *a:None
            self.assertFalse(b.list(c.store_id));c.lease.release()
            r=start(LocalBackend(b.root),td,name='restored');self.assertEqual(r.restored_from,'CHECKPOINT.zip')
            r.transport_preflight();self.assertFalse(r.backend.list(r.store_id));r.checkpoint(True)
            self.assertTrue(any(m['name']=='CHECKPOINT.zip' for m in r.backend.list('run')))
            r.checkpoint(True);self.assertFalse(any(m['name']=='CHECKPOINT.zip' for m in r.backend.list('run')));r.lease.release()

    def test_service_outage_does_not_roll_back_a_newer_checkpoint(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.checkpoint(True)
            (c.local/'units/U/value.json').write_text('{"value":2}');c.checkpoint(True);current=c.current['meta']['id'];heads=c.expected_heads;c.lease.release()
            fresh=LocalBackend(b.root);original=fresh.read_json
            def read(file_id):
                if file_id==current:raise ConnectionError('service unavailable')
                return original(file_id)
            with patch.object(fresh,'read_json',side_effect=read):
                self.assertRaisesRegex(ConnectionError,'service unavailable',start,fresh,td,name='restore')
            p=fresh.meta(c.store_id)['appProperties'];self.assertEqual((p['current'],p['previous']),heads)

    def test_runtime_workspace_inside_drive_is_rejected_without_touching_files(self):
        with tempfile.TemporaryDirectory() as td:
            drive=Path(td)/'drive';p=drive/'units/protected.txt';p.parent.mkdir(parents=True);p.write_text('preserve')
            b=LocalBackend(Path(td)/'server')
            self.assertRaises(RuntimeError,IncrementalCampaign,drive,drive/'local',{'test':15},b)
            self.assertEqual(p.read_text(),'preserve');self.assertFalse((drive/'local').exists())

    def test_recent_and_stolen_session_leases_prevent_a_second_writer(self):
        with tempfile.TemporaryDirectory() as td:
            b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td)
            self.assertRaises(RuntimeError,start,LocalBackend(b.root),td,name='second')
            p=b.root/c.lease.file_id;d=json.loads(p.read_text());d['token']='another-owner';p.write_text(json.dumps(d))
            self.assertRaises(RuntimeError,c.checkpoint,True);c.lease.release()
            self.assertTrue(p.exists())

    def test_real_64_mib_boundary_deduplicates_appended_matrix_columns(self):
        from runner14 import save
        with tempfile.TemporaryDirectory() as td:
            b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.block_size=64*1024**2;c.checkpoint(True)
            Y=np.asfortranarray(np.random.default_rng(817).standard_normal((524288,48),dtype=np.float32))
            p=c.local/'units/U/operator_large.resume.npz';save(p,Y=np.asfortranarray(Y[:,:32]));c.checkpoint(True)
            first=c.current['payload']['files']['units/U/operator_large.resume.npz']['members'][0]['chunks'][0]
            before=sum(n for k,n in b.uploads if k=='blob');save(p,Y=Y);c.checkpoint(True)
            second=c.current['payload']['files']['units/U/operator_large.resume.npz']['members'][0]['chunks'][0]
            self.assertEqual(first['id'],second['id']);extra=sum(n for k,n in b.uploads if k=='blob')-before
            self.assertLess(extra,40*1024**2);c.lease.release();r=start(LocalBackend(b.root),td,name='restored')
            self.assertTrue(np.array_equal(np.load(r.local/p.relative_to(c.local))['Y'],Y));r.lease.release()

    def test_actual_operator_recovery_all_four_passes_is_bitwise(self):
        import torch
        from operators import rs_basis
        from runner14 import OperatorJournal
        torch.set_num_threads(2)
        for dtype in (torch.float32,torch.float64):
            torch.manual_seed(871);A=torch.randn(10,14,dtype=dtype)
            class Matrix:
                outputs=10;parameters=14;device=torch.device('cpu');H=2
                def jvp(self,u):return A@u
                def vjp(self,r):return A.T@r
            Matrix.dtype=dtype
            baseline,info=rs_basis(Matrix(),8,3,719,1)
            for position in (3,11,19,27):
                with self.subTest(dtype=dtype,position=position),tempfile.TemporaryDirectory() as td:
                    b=LocalBackend(Path(td)/'server');seed_legacy(b,td);c=start(b,td);c.checkpoint(True)
                    path=c.local/'units/U/operator_actual.resume.npz';j=OperatorJournal(path,c);count=[0];original=j.save
                    def due():count[0]+=1;return count[0]==position
                    def stop(*args):original(*args);raise SimulatedDisconnect()
                    j.due=due;j.save=stop
                    self.assertRaises(SimulatedDisconnect,rs_basis,Matrix(),8,3,719,1,journal=j)
                    c.lease.release();r=start(LocalBackend(b.root),td,name='restored');j2=OperatorJournal(r.local/path.relative_to(c.local),r)
                    j2.due=lambda:False;got,other=rs_basis(Matrix(),8,3,719,1,journal=j2)
                    self.assertTrue(torch.equal(got,baseline));self.assertTrue(np.array_equal(other['ritz_gram'],info['ritz_gram']));r.lease.release()


if __name__=='__main__':unittest.main()
