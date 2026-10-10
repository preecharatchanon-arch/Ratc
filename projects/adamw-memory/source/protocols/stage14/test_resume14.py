"""Operational recovery tests; no research observations."""
import contextlib, io, json, shutil, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from archive_io import Campaign, pack, sha, write_json
from resume14 import progress


class RecoveryTests(unittest.TestCase):
    def checkpoint(self, root, value):
        payload=root/'payload';f=payload/'units'/'U'/'value.json'
        f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(value))
        return pack(payload,root/f'{value}.zip',{'test':1},'CHECKPOINT',[f])

    def test_missing_identity_or_checkpoint_refuses_fresh_run(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);camp=Campaign(root/'drive',root/'local',{'test':1});camp.require_checkpoint=True
            self.assertRaisesRegex(RuntimeError,'IDENTITY.json is missing',camp.activate)
            self.assertFalse((root/'drive'/'IDENTITY.json').exists())
            write_json(root/'drive'/'IDENTITY.json',{'test':1})
            self.assertRaisesRegex(RuntimeError,'no saved checkpoint',camp.activate)
            self.assertFalse((root/'drive'/'LEASE.json').exists())

    def test_valid_archive_restores_and_discards_uncommitted_local_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);z=self.checkpoint(root,1);camp=Campaign(root/'drive',root/'local',{'test':1})
            write_json(root/'drive'/'IDENTITY.json',{'test':1});shutil.copyfile(z,root/'drive'/'CHECKPOINT.zip')
            stale=root/'local'/'units'/'stale.json';stale.parent.mkdir(parents=True);stale.write_text('{}')
            camp.require_checkpoint=True;self.assertEqual(camp.activate(),'CHECKPOINT')
            self.assertEqual(camp.restored_sha256,sha(z));self.assertFalse(stale.exists())
            self.assertEqual(json.loads((root/'local'/'units'/'U'/'value.json').read_text()),1)
            camp.lease.release()

    def test_corruption_falls_back_but_missing_progress_never_restarts(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);z=self.checkpoint(root,1);drive=root/'drive';drive.mkdir()
            write_json(drive/'IDENTITY.json',{'test':1});shutil.copyfile(z,drive/'CHECKPOINT_PREVIOUS.zip')
            (drive/'CHECKPOINT.zip').write_bytes(b'broken')
            camp=Campaign(drive,root/'local',{'test':1});camp.require_checkpoint=True
            self.assertEqual(camp.activate(),'CHECKPOINT');self.assertEqual(camp.restored_from,'CHECKPOINT_PREVIOUS.zip')
            camp.lease.release();camp.required_paths=('units/newer/COMPLETE.json',)
            before=(root/'local'/'units'/'U'/'value.json').read_bytes()
            self.assertRaisesRegex(RuntimeError,'predates verified progress',camp.activate)
            self.assertEqual((root/'local'/'units'/'U'/'value.json').read_bytes(),before)
            self.assertEqual((drive/'CHECKPOINT.zip').read_bytes(),b'broken')
            self.assertFalse((drive/'LEASE.json').exists())

    def test_previous_is_explicit_and_does_not_modify_current(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=self.checkpoint(root,1);b=self.checkpoint(root,2);drive=root/'drive';drive.mkdir()
            write_json(drive/'IDENTITY.json',{'test':1});shutil.copyfile(a,drive/'CHECKPOINT_PREVIOUS.zip');shutil.copyfile(b,drive/'CHECKPOINT.zip')
            current=sha(drive/'CHECKPOINT.zip');camp=Campaign(drive,root/'local',{'test':1})
            camp.require_checkpoint=True;camp.resume_from='previous';self.assertEqual(camp.activate(),'CHECKPOINT')
            self.assertEqual(json.loads((root/'local'/'units'/'U'/'value.json').read_text()),1)
            self.assertEqual(sha(drive/'CHECKPOINT.zip'),current);camp.lease.release()

    def test_active_lease_protects_existing_run(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);first=Campaign(root/'drive',root/'one',{'test':1});first.activate()
            other=Campaign(root/'drive',root/'two',{'test':1});other.require_checkpoint=True
            self.assertRaisesRegex(RuntimeError,'Another recent session',other.activate)
            self.assertTrue(first.lease.path.exists());first.lease.release()


if __name__=='__main__':unittest.main()
