import json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import archive_io as io

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.ident={'study':'fixture'};self.store=io.Campaign(self.root/'drive',self.root/'local',self.ident);self.store.activate()
        self.payload=self.store.local/'units'/'u'/'state.pt';self.payload.parent.mkdir(parents=True);self.payload.write_bytes(b'old')
    def tearDown(self):self.store.lease.release();self.temp.cleanup()
    def test_two_generations_and_throttle(self):
        self.store.checkpoint(True);first=io.sha(self.store.drive/'CHECKPOINT.zip')
        self.payload.write_bytes(b'new');self.store.checkpoint(True)
        self.assertEqual(first,io.sha(self.store.drive/'CHECKPOINT_PREVIOUS.zip'))
        self.assertFalse(self.store.checkpoint(False));self.assertEqual(len(list(self.store.drive.glob('*.zip'))),2)
    def test_failed_publish_retains_current(self):
        self.store.checkpoint(True);old=io.sha(self.store.drive/'CHECKPOINT.zip');self.payload.write_bytes(b'new')
        actual=io.publish
        def fail(local,dest):
            if Path(dest).name=='CHECKPOINT.zip':raise OSError('injected write failure')
            return actual(local,dest)
        with patch.object(io,'publish',fail):
            with self.assertRaises(OSError):self.store.checkpoint(True)
        self.assertEqual(io.sha(self.store.drive/'CHECKPOINT.zip'),old)
    def test_other_session_rejected(self):
        with self.assertRaises(RuntimeError):io.Campaign(self.store.drive,self.root/'other',self.ident).activate()
    def test_corrupt_and_unsafe_archives_rejected(self):
        self.store.checkpoint(True);p=self.store.drive/'CHECKPOINT.zip'
        with zipfile.ZipFile(p,'a') as z:z.writestr('../escape',b'bad')
        with self.assertRaises(RuntimeError):io.verify(p,self.ident,'CHECKPOINT')
    def test_final_has_no_pt_and_prunes_verified_checkpoints(self):
        self.store.checkpoint(True);p=self.payload.with_suffix('.json');p.write_text('{"meaningful":true}')
        final=self.store.finish();m=io.verify(final,self.ident,'FINISHED')
        self.assertFalse(any(x['path'].endswith('.pt') for x in m['files']));self.assertEqual(len(list(self.store.drive.glob('*.zip'))),1)
    def test_manifest_payload_tampering_rejected(self):
        self.store.checkpoint(True);p=self.store.drive/'CHECKPOINT.zip';dest=self.root/'bad.zip'
        with zipfile.ZipFile(p) as src,zipfile.ZipFile(dest,'w') as z:
            for n in src.namelist():z.writestr(n,b'changed' if n.endswith('state.pt') else src.read(n))
        with self.assertRaises(RuntimeError):io.verify(dest,self.ident,'CHECKPOINT')

if __name__=='__main__':unittest.main()
