"""Storage pause and validated preservation of a locally completed operator basis."""
import json,tempfile,unittest
from dataclasses import asdict,replace
from pathlib import Path
import numpy as np
from runner14 import Config,VERSION,save
from data13 import seed
from archive_io import write_json
from checkpoint15 import IncrementalCampaign,CheckpointBlocked
from test_incremental15 import LocalBackend,seed_legacy,start

class StorageTests(unittest.TestCase):
    def test_no_artificial_caps_and_only_actual_account_capacity_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            c=IncrementalCampaign(Path(td)/'drive',Path(td)/'local',{'test':15},LocalBackend(Path(td)/'server'))
            self.assertIsNone(c.checkpoint_limit);self.assertIsNone(c.project_limit);self.assertEqual(c.account_reserve,0)
            u=dict(checkpoint_bytes=20_000_000_000,project_bytes=30_000_000_000,account_bytes=30_000_000_000,account_limit=100_000_000_000)
            c._budget(670_000_000,u)
            c._budget(670_000_000,dict(u,account_limit=None))
            c._budget(670_000_000,dict(u,account_limit=30_670_000_000))
            self.assertRaises(CheckpointBlocked,c._budget,670_000_000,dict(u,account_limit=30_669_999_999))

    def setup_pending(self,td):
        cfg=json.loads(json.dumps(asdict(replace(Config(),datasets=('CIFAR10',),seeds=(14003,),ranks=(1,2),sketch_columns=4))))
        ident=dict(version=VERSION,config=cfg,environment={'synthetic':'cpu'})
        b=LocalBackend(Path(td)/'server');seed_legacy(b,td,ident);c=start(b,td,ident)
        unit=c.local/'units/CIFAR10_14003';unit.mkdir(parents=True)
        save(unit/'state.resume.npz',theta=np.zeros(14,dtype='float32'))
        save(unit/'operator_h16_n256_l4.resume.npz',Q=np.eye(14,4,dtype='float32'))
        write_json(c.local/'metadata/CONFIG.json',cfg);write_json(c.local/'metadata/ENVIRONMENT.json',ident['environment'])
        c.checkpoint(True);c.checkpoint(True);c.lease.release()
        path=unit/'basis_h16_n256_l4.resume.npz'
        save(path,U=np.eye(14,2,dtype='float32'),ritz_gram=np.eye(4),ritz_spectrum=np.ones(4),ritz_vectors=np.eye(4),
            columns=np.asarray(4),power=np.asarray(1),rng_seed=np.asarray(seed(VERSION,'sketch','CIFAR10',14003,16,256),dtype=np.int64),
            orthogonality_max_error=np.asarray(0.),seconds=np.asarray(1.))
        (unit/'operator_h16_n256_l4.resume.npz').unlink();return b,c,ident,path

    def test_completed_local_basis_is_saved_before_older_restore(self):
        with tempfile.TemporaryDirectory() as td:
            b,c,ident,path=self.setup_pending(td);raw=path.read_bytes();r=start(LocalBackend(b.root),td,ident)
            self.assertEqual(path.read_bytes(),raw);self.assertIn('verified local completed basis',r.restored_from)
            self.assertIn(path.relative_to(r.local).as_posix(),r.current['payload']['files']);r.lease.release()
            fresh=start(LocalBackend(b.root),td,ident,name='fresh')
            self.assertTrue(np.array_equal(np.load(fresh.local/path.relative_to(c.local))['U'],np.eye(14,2,dtype='float32')));fresh.lease.release()

    def test_changed_published_local_data_prevents_merge_without_erasure(self):
        with tempfile.TemporaryDirectory() as td:
            b,c,ident,path=self.setup_pending(td);p=c.local/'units/U/value.json';p.write_text('{"value":99}')
            self.assertRaisesRegex(RuntimeError,'Local research differs',start,LocalBackend(b.root),td,ident)
            self.assertEqual(p.read_text(),'{"value":99}');self.assertTrue(path.exists())

    def test_pending_basis_with_wrong_config_is_retained_and_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            b,c,ident,path=self.setup_pending(td);write_json(c.local/'metadata/CONFIG.json',{'wrong':True})
            self.assertRaisesRegex(RuntimeError,'configuration/runtime mismatch',start,LocalBackend(b.root),td,ident)
            self.assertTrue(path.exists())

if __name__=='__main__':unittest.main()
