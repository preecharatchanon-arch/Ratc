"""Immutable compressed chunks, two commit records, verified restore and bounded GC."""
import hashlib, json, os, re, shutil, struct, tempfile, time, uuid, zipfile
from pathlib import Path
from archive_io import Campaign, check, pack, sha, unpack, verify, safe, write_json
from drive_store15 import ServerLease, md5

FORMAT='NEXUS-INCREMENTAL-CHECKPOINT-1'
BLOCK=64*1024**2


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(b):return hashlib.sha256(b).hexdigest()


class CheckpointBlocked(RuntimeError):pass


def storage_unavailable(exc):
    """A service/auth outage is not evidence that saved research is corrupt."""
    status=getattr(getattr(exc,'resp',None),'status',None)
    return (status is not None and status!=404) or isinstance(exc,OSError) or \
        type(exc).__module__.startswith(('google.auth.','httplib2'))


class IncrementalCampaign(Campaign):
    def __init__(self,drive,local,identity,backend):
        # Do not create a new mounted Drive folder or use its cache as upload proof.
        self.drive=Path(drive);self.local=Path(local)
        check(self.local.resolve()!=self.drive.resolve() and self.drive.resolve() not in self.local.resolve().parents,
              'The runtime workspace must be outside the durable Drive run folder')
        mounted=Path('/content/drive').resolve()
        check(self.local.resolve()!=mounted and mounted not in self.local.resolve().parents,
              'Loose working data must stay outside the Drive mount')
        self.local.mkdir(parents=True,exist_ok=True)
        self.identity=identity;self.backend=backend;self.tag=digest(canonical(identity))
        self.lease=ServerLease(backend,self.local/'transport');backend.on_progress=self.lease.pulse
        self.last_checkpoint=time.monotonic();self.checkpoint_seconds=900
        self.require_checkpoint=True;self.resume_from='latest';self.required_paths=()
        self.restored_from=None;self.restored_sha256=None;self.restored_bytes=0
        self.store_id=None;self.current=None;self.previous=None;self.legacy=[];self.rows=[]
        self.expected_heads=('','')
        self.checkpoint_limit=None;self.project_limit=None
        self.account_reserve=0;self.cache={};self.block_size=BLOCK

    def _owned(self,m,kind=None):
        p=m.get('appProperties',{})
        return p.get('nexus15')==self.tag and (kind is None or p.get('kind')==kind)

    def _refresh(self):
        self.rows=self.backend.list(self.store_id) if self.store_id else []
        return {r['id']:r for r in self.rows}

    def _envelope(self,payload):return dict(payload=payload,sha256=digest(canonical(payload)))

    def _read_commit(self,m,inventory):
        e=self.backend.read_json(m['id']);p=e['payload']
        check(e['sha256']==digest(canonical(p)),'Commit checksum mismatch')
        check(p['format']==FORMAT and p['identity']==self.identity,'Incremental identity/format mismatch')
        check(isinstance(p['generation'],int) and p['generation']>=1,'Invalid commit generation')
        check(isinstance(p['files'],dict) and p['files'],'Empty checkpoint is not a research recovery point')
        for name,entry in p['files'].items():
            safe(name);check(Path(name).parts[0] in ('units','metadata','analysis'),'Unexpected payload root')
        check(not (set(self.required_paths)-set(p['files'])),'Checkpoint predates verified progress')
        self._verify_refs(p,inventory)
        return dict(meta=m,payload=p,sha256=e['sha256'])

    @staticmethod
    def _refs(p):
        refs={}
        for entry in p['files'].values():
            if entry['kind']=='bundle':items=[entry['object']]
            elif entry['kind']=='opaque':items=entry['chunks']
            elif entry['kind']=='npz':items=[r for member in entry['members'] for r in member['chunks']]
            else:raise RuntimeError('Unknown checkpoint encoding')
            for r in items:
                if r['id'] in refs:check(refs[r['id']]==r,'Conflicting object reference')
                refs[r['id']]=r
        return refs

    def _verify_refs(self,p,inventory=None):
        for r in self._refs(p).values():
            # Direct ID reads avoid a stale folder listing/cache accepting changed bytes.
            m=self.backend.meta(r['id'])
            check(not m.get('trashed') and self._owned(m,'blob') and self.store_id in m.get('parents',[]),
                  'Checkpoint object is missing or belongs to another run')
            check(int(m.get('size',-1))==r['bytes'] and m.get('md5Checksum')==r['md5'],
                  'Checkpoint object server checksum mismatch')

    def _install(self,staging):
        for top in ('units','metadata','analysis'):
            target=self.local/top
            if target.exists():shutil.rmtree(target)
            if (staging/top).exists():os.replace(staging/top,target)

    def _pending_completed_bases(self,commit):
        """Salvage only completed bases anchored to unchanged published unit data."""
        files=commit['payload']['files'];candidates=[];removed=set()
        for p in (self.local/'units').rglob('basis_*.resume.npz') if (self.local/'units').exists() else ():
            name=p.relative_to(self.local).as_posix()
            if name in files:continue
            operator=p.with_name(p.name.replace('basis_','operator_',1));old=operator.relative_to(self.local).as_posix()
            if old in files and not operator.exists():candidates.append((p,name,old));removed.add(old)
        if not candidates:return []
        cfg=self.identity.get('config');env=self.identity.get('environment')
        check(cfg is not None and env is not None,'Pending local basis lacks campaign identity')
        for name,expected in [('CONFIG.json',cfg),('ENVIRONMENT.json',env)]:
            p=self.local/'metadata'/name
            check(p.exists() and json.loads(p.read_text())==expected,
                  'Pending local basis configuration/runtime mismatch; local data retained')
        # Every published scientific unit file must be unchanged except the partial
        # operator whose completion produced this specific cached basis. Metadata
        # source copies may differ after an operational patch; scientific data may not.
        for name,e in files.items():
            if not name.startswith('units/') or name in removed:continue
            p=self.local/name
            exact=p.is_file() and p.stat().st_size==e['source_bytes'] and sha(p)==e['source_sha256']
            if not exact and p.is_file() and e['kind']=='npz':
                # A previous restore re-encodes the ZIP container; array-member
                # bytes remain exact even when the outer compressed-file hash differs.
                with zipfile.ZipFile(p) as z:
                    exact=set(z.namelist())=={m['name'] for m in e['members']}
                    for member in e['members']:
                        h=hashlib.sha256();size=0
                        with z.open(member['name']) as stream:
                            for block in iter(lambda:stream.read(4*1024**2),b''):h.update(block);size+=len(block)
                        exact=exact and size==member['bytes'] and h.hexdigest()==member['sha256']
            check(exact,
                  'Local research differs from its published checkpoint; refusing to merge or overwrite it')
        allowed=set(files)|{name for p,name,old in candidates}
        for p in self.files():
            name=p.relative_to(self.local).as_posix()
            check(not name.startswith('units/') or name in allowed,
                  'Unexpected unsaved local research file; local data retained')
        import numpy as np
        from data13 import seed as research_seed
        for p,name,old in candidates:
            m=re.fullmatch(r'basis_h(\d+)_n(\d+)_l(\d+)\.resume\.npz',p.name)
            unit=re.fullmatch(r'(.+)_(\d+)',p.parent.name)
            check(m is not None and unit is not None,'Invalid pending basis name')
            H,n,l=map(int,m.groups());ds,s=unit.group(1),int(unit.group(2))
            check(ds in cfg['datasets'] and s in cfg['seeds'] and H in (1,cfg['fit_horizon']) and
                  n in cfg['fit_sizes'] and l in (cfg['sketch_columns'],cfg['quality_columns']),
                  'Pending basis is outside the frozen research protocol')
            with np.load(p.parent/'state.resume.npz',allow_pickle=False) as z:theta=z['theta']
            with np.load(p,allow_pickle=False) as z:
                required={'U','ritz_gram','ritz_spectrum','ritz_vectors','columns','power','rng_seed','orthogonality_max_error','seconds'}
                check(set(z.files)==required,'Pending basis payload is incomplete')
                U=z['U'];check(U.shape==(theta.size,max(cfg['ranks'])) and U.dtype==theta.dtype,
                              'Pending basis dimensions/dtype mismatch')
                check(int(z['columns'])==l and int(z['power'])==cfg['sketch_power'] and
                      int(z['rng_seed'])==research_seed(self.identity['version'],'sketch',ds,s,H,n),
                      'Pending basis sketch identity mismatch')
                check(z['ritz_gram'].shape==(l,l) and z['ritz_vectors'].shape==(l,l) and z['ritz_spectrum'].shape==(l,),
                      'Pending basis spectrum/Gram dimensions mismatch')
                check(all(np.isfinite(z[k]).all() for k in required),'Pending basis contains nonfinite values')
                check(0<=float(z['orthogonality_max_error'])<=2e-4 and float(z['seconds'])>=0,
                      'Pending basis numerical qualification mismatch')
        return [name for p,name,old in candidates]

    def _restore(self,commit):
        p=commit['payload'];refs=self._refs(p)
        with tempfile.TemporaryDirectory(prefix='.restore15-',dir=self.local) as td:
            root=Path(td);payload=root/'payload';downloaded={}
            for i,r in enumerate(refs.values(),1):
                self.lease.pulse();f=root/f'{r["id"]}.zip';self.backend.download(r['id'],f)
                check(sha(f)==r['sha256'],'Downloaded checkpoint object SHA256 mismatch');downloaded[r['id']]=f
                if i%16==0 or i==len(refs):print('Restore verified objects:',i,'/',len(refs),flush=True)
            def raw(r):
                with zipfile.ZipFile(downloaded[r['id']]) as z:
                    check(z.namelist()==['payload.bin'],'Unexpected chunk members');b=z.read('payload.bin')
                check(len(b)==r['raw_bytes'] and digest(b)==r['raw_sha256'],'Chunk payload hash mismatch')
                return b
            for name,e in p['files'].items():
                self.lease.pulse();dest=payload/name;dest.parent.mkdir(parents=True,exist_ok=True)
                if e['kind']=='bundle':
                    with zipfile.ZipFile(downloaded[e['object']['id']]) as z:
                        with z.open(name) as src,open(dest,'wb') as out:shutil.copyfileobj(src,out,4*1024**2)
                    check(dest.stat().st_size==e['source_bytes'] and sha(dest)==e['source_sha256'],'Bundle file integrity mismatch')
                elif e['kind']=='opaque':
                    with open(dest,'wb') as out:
                        for r in e['chunks']:out.write(raw(r))
                    check(dest.stat().st_size==e['source_bytes'] and sha(dest)==e['source_sha256'],'Opaque file integrity mismatch')
                else:
                    # ZIP_STORED avoids recompression differences; array bytes/order are exact.
                    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_STORED) as z:
                        for member in e['members']:
                            h=hashlib.sha256();size=0;header=bytes.fromhex(member['header_hex'])
                            safe(member['name']);info=zipfile.ZipInfo(member['name'],date_time=(1980,1,1,0,0,0))
                            with z.open(info,'w',force_zip64=True) as out:
                                out.write(header);h.update(header);size+=len(header)
                                for r in member['chunks']:
                                    b=raw(r);out.write(b);h.update(b);size+=len(b)
                            check(size==member['bytes'] and h.hexdigest()==member['sha256'],'NPZ array member integrity mismatch')
            self._install(payload)
        self.restored_from=f'15-minute commit {p["generation"]}'
        self.restored_sha256=commit['sha256'];self.restored_bytes=sum(r['bytes'] for r in refs.values())
        self.legacy=p.get('legacy',[])

    def activate(self):
        check(self.resume_from in ('latest','previous'),'Resume source must be latest or previous')
        self.lease.acquire()
        try:
            root_rows=self.backend.list(self.backend.run_id)
            ids=[m for m in root_rows if m['name']=='IDENTITY.json'];check(len(ids)==1,'Saved campaign identity is missing/ambiguous')
            check(self.backend.read_json(ids[0]['id'])==self.identity,'Code/config/runtime mismatch')
            finals=[m for m in root_rows if m['name']=='NEXUS_STAGE14_FINISHED.zip']
            check(len(finals)<=1,'Multiple final archives are ambiguous')
            if not finals:
                staged=[m for m in root_rows if self._owned(m,'FINISHED') and
                        m.get('appProperties',{}).get('export_name')=='NEXUS_STAGE14_FINISHED.zip']
                for item in staged:
                    try:
                        with tempfile.TemporaryDirectory(dir=self.local) as td:
                            z=Path(td)/'final.zip';self.backend.download(item['id'],z);fm=verify(z,self.identity,'FINISHED')
                            check(set(self.required_paths)<={e['path'] for e in fm['files']},'Staged final predates verified progress')
                        self.lease.pulse(force=True)
                        finals=[self.backend.rename(item['id'],'NEXUS_STAGE14_FINISHED.zip')];break
                    except Exception as e:
                        if storage_unavailable(e):raise
                        print('Unpublished final export failed verification; recovery checkpoints retained.',flush=True)
            if finals:
                with tempfile.TemporaryDirectory(dir=self.local) as td:
                    z=Path(td)/'final.zip';self.backend.download(finals[0]['id'],z)
                    m=verify(z,self.identity,'FINISHED');check(set(self.required_paths)<={e['path'] for e in m['files']},'Finished archive predates verified progress')
                    dst=Path(td)/'payload';unpack(z,dst,self.identity,'FINISHED');self._install(dst)
                # A disconnect after final publication may have interrupted cleanup.
                for item in root_rows:
                    if item['name']=='CHECKPOINTS_15MIN' and self._owned(item,'store'):
                        self.store_id=item['id'];self._retire_resume_objects()
                self.discard_export('NEXUS_STAGE14_PRIMARY_COHORT.zip','COHORT')
                return 'FINISHED'
            stores=[m for m in root_rows if m['name']=='CHECKPOINTS_15MIN']
            check(len(stores)<=1,'Multiple incremental checkpoint folders; refusing an ambiguous run')
            if stores:
                check(self._owned(stores[0],'store'),'Checkpoint folder belongs to another run')
                self.store_id=stores[0]['id'];inventory=self._refresh();candidates=[]
                props=self.backend.meta(self.store_id).get('appProperties',{})
                self.expected_heads=(props.get('current',''),props.get('previous',''))
                head_ids=self.expected_heads if self.resume_from=='latest' else (self.expected_heads[1],)
                for file_id in head_ids:
                    if not file_id:continue
                    try:
                        m=inventory.get(file_id) or self.backend.meta(file_id)
                        check(self._owned(m,'commit'),'Recovery pointer belongs to another run')
                        candidates.append(self._read_commit(m,inventory))
                    except Exception as e:
                        if storage_unavailable(e):raise
                        print('Invalid recovery record; trying predecessor:',type(e).__name__,flush=True)
                for index,commit in enumerate(candidates):
                    # A storage pause occurs after the completed basis is written
                    # locally and its partial operator is discarded. Preserve that
                    # exact case before a normal restore would overwrite the basis.
                    pending=self._pending_completed_bases(commit) if index==0 and commit['meta']['id']==self.expected_heads[0] else []
                    if pending:
                        self.current=commit;self.previous=candidates[index+1] if index+1<len(candidates) else None
                        self.legacy=commit['payload'].get('legacy',[])
                        self.restored_from=f'15-minute commit {commit["payload"]["generation"]} with verified local completed basis'
                        self.restored_sha256=commit['sha256'];self.restored_bytes=sum(r['bytes'] for r in self._refs(commit['payload']).values())
                        print('PRESERVING LOCALLY COMPLETED BASIS:',', '.join(pending),flush=True)
                        self.checkpoint(True)
                        return 'CHECKPOINT'
                    try:self._restore(commit)
                    except Exception as e:
                        if storage_unavailable(e):raise
                        print('Recovery point failed payload validation; trying predecessor:',type(e).__name__,flush=True);continue
                    self.current=commit;self.previous=candidates[index+1] if index+1<len(candidates) else None
                    selected_heads=(self.current['meta']['id'],self.previous['meta']['id'] if self.previous else '')
                    if selected_heads==self.expected_heads:self._gc()
                    self.last_checkpoint=time.monotonic();return 'CHECKPOINT'
                check(not any(self.expected_heads),'No valid incremental recovery point; saved data retained')
            # Initial migration uses the old fully verified ZIPs; never starts from zero.
            names=['CHECKPOINT_PREVIOUS.zip'] if self.resume_from=='previous' else ['CHECKPOINT.zip','CHECKPOINT_PREVIOUS.zip']
            chosen=None
            for filename in names:
                rows=[m for m in root_rows if m['name']==filename];check(len(rows)<=1,'Duplicate legacy checkpoint names')
                if not rows:continue
                m=rows[0]
                try:
                    with tempfile.TemporaryDirectory(dir=self.local) as td:
                        z=Path(td)/'legacy.zip';self.backend.download(m['id'],z);manifest=verify(z,self.identity,'CHECKPOINT')
                        check(set(self.required_paths)<={e['path'] for e in manifest['files']},'Legacy checkpoint predates verified progress')
                        dst=Path(td)/'payload';unpack(z,dst,self.identity,'CHECKPOINT');self._install(dst)
                        chosen=(m,sha(z));break
                except Exception as e:
                    if storage_unavailable(e):raise
                    print('Legacy checkpoint rejected; trying predecessor:',type(e).__name__,flush=True)
            check(chosen is not None,'No compatible checkpoint found; refusing to start from zero')
            self.restored_from=chosen[0]['name'];self.restored_sha256=chosen[1];self.restored_bytes=int(chosen[0]['size'])
            self.legacy=[dict(id=chosen[0]['id'],md5=chosen[0]['md5Checksum'],bytes=int(chosen[0]['size']))]
            # Only delete a predecessor later if it too was identity/hash verified now.
            for m in root_rows:
                if m['name'] in ('CHECKPOINT.zip','CHECKPOINT_PREVIOUS.zip') and m['id']!=chosen[0]['id']:
                    try:
                        with tempfile.TemporaryDirectory(dir=self.local) as td:
                            z=Path(td)/'backup.zip';self.backend.download(m['id'],z);verify(z,self.identity,'CHECKPOINT')
                        self.legacy.append(dict(id=m['id'],md5=m['md5Checksum'],bytes=int(m['size'])))
                    except Exception as e:
                        if storage_unavailable(e):raise
                        print('Unverified legacy backup retained unchanged.',flush=True)
            return 'CHECKPOINT'
        except BaseException:self.lease.release();raise

    def _budget(self,extra,usage):
        if ((self.checkpoint_limit is not None and usage['checkpoint_bytes']+extra>self.checkpoint_limit) or
            (self.project_limit is not None and usage['project_bytes']+extra>self.project_limit)):
            raise CheckpointBlocked('Storage budget reached before upload. Previous verified checkpoints remain safe. '
                f'Project {usage["project_bytes"]/1e9:.2f} GB; checkpoints {usage["checkpoint_bytes"]/1e9:.2f} GB; incoming {extra/1e9:.2f} GB.')
        limit=usage['account_limit']
        if limit is not None and usage['account_bytes']+extra+self.account_reserve>limit:
            raise CheckpointBlocked('Drive account lacks upload headroom. Previous verified checkpoints remain safe.')

    def transport_preflight(self):
        """Qualify a real multi-chunk upload/download before new GPU work."""
        self.lease.pulse(force=True)
        parent=self.store_id or self.backend.run_id
        # A hard disconnect can leave a completed diagnostic upload. It is never
        # a checkpoint object; delete only this run's explicitly tagged probes.
        for item in self.backend.list(parent):
            if self._owned(item,'transport_probe'):
                self.lease.pulse(force=True);self.backend.delete(item['id'])
        with tempfile.TemporaryDirectory(prefix='.transport15-',dir=self.local) as td:
            path=Path(td)/'upload-check.zip';payload=b'NEXUS verified resumable transport\n'
            with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_STORED) as z:
                with z.open('transport-check.bin','w') as out:
                    block=(payload*(1024**2//len(payload)+1))[:1024**2]
                    for _ in range(9):out.write(block)
            check(path.stat().st_size>8*1024**2,'Preflight must span at least two upload chunks')
            self._budget(path.stat().st_size,self.backend.usage(self.store_id))
            print('Verifying a real multi-chunk Drive upload and download before GPU work...',flush=True)
            m=self.backend.put(parent,'NEXUS_UPLOAD_CHECK.zip',path,{'nexus15':self.tag,'kind':'transport_probe'})
            try:
                downloaded=Path(td)/'download-check.zip';self.backend.download(m['id'],downloaded)
                check(sha(path)==sha(downloaded),'Transport preflight round-trip SHA256 mismatch')
            except BaseException:
                try:self.lease.pulse(force=True);self.backend.delete(m['id'])
                except Exception:pass  # Next preflight removes an owned orphan; retain the original failure.
                raise
            else:
                self.lease.pulse(force=True);self.backend.delete(m['id'])
        print('LIVE DRIVE UPLOAD/DOWNLOAD VERIFIED; temporary probe removed.',flush=True)

    def checkpoint(self,force=False):
        self.pulse()
        if not force and not self.checkpoint_due():return False
        self.lease.pulse(force=True)
        if self.store_id is None:
            self.store_id=self.backend.mkdir(self.backend.run_id,'CHECKPOINTS_15MIN',self.tag)['id']
        inventory=self._refresh();prior=self.current['payload']['files'] if self.current else {}
        trusted={}
        if self.current:
            for r in self._refs(self.current['payload']).values():
                try:m=self.backend.meta(r['id'])
                except Exception:m=None
                if m and m.get('md5Checksum')==r['md5'] and int(m.get('size',-1))==r['bytes']:
                    trusted[(r.get('raw_sha256',''),r['sha256'])]=r
        pending={};entries={};small=[]
        with tempfile.TemporaryDirectory(prefix='.plan15-',dir=self.local) as td:
            plan=Path(td)
            def object_ref(path,raw_sha=None,raw_bytes=None):
                encoded=sha(path);key=encoded
                if key in pending:return pending[key]['ref']
                for r in trusted.values():
                    if r['sha256']==encoded:return r
                expected=md5(path)
                matches=[m for m in inventory.values() if self._owned(m,'blob') and m['name']==f'b_{encoded}.zip'
                         and m.get('md5Checksum')==expected and int(m.get('size',-1))==path.stat().st_size]
                ref=dict(id=matches[0]['id'] if matches else None,sha256=encoded,md5=expected,bytes=path.stat().st_size)
                if raw_sha is not None:ref.update(raw_sha256=raw_sha,raw_bytes=raw_bytes)
                if not matches:
                    dest=plan/f'{encoded}.zip';shutil.copyfile(path,dest);pending[key]=dict(path=dest,ref=ref)
                return ref
            def chunk(b):
                d=digest(b)
                for (raw_sha,_),r in trusted.items():
                    if raw_sha==d and r.get('raw_bytes')==len(b):return r
                path=plan/'encoding.zip'
                with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
                    info=zipfile.ZipInfo('payload.bin',date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                    z.writestr(info,b,compress_type=zipfile.ZIP_DEFLATED,compresslevel=1)
                return object_ref(path,d,len(b))
            for f in self.files():
                self.lease.pulse();name=f.relative_to(self.local).as_posix();stat=f.stat();cache_key=(name,stat.st_size,stat.st_mtime_ns)
                source_sha=self.cache.get(cache_key)
                if source_sha is None:source_sha=sha(f);self.cache[cache_key]=source_sha
                old=prior.get(name)
                if old and old['source_sha256']==source_sha:
                    good_ids={r['id'] for r in trusted.values()}
                    if set(self._refs({'files':{name:old}}))<=good_ids:entries[name]=old;continue
                e=dict(source_sha256=source_sha,source_bytes=stat.st_size)
                structured=f.name.endswith('.resume.npz') and f.name.startswith(('operator_','basis_'))
                if structured:
                    members=[]
                    with zipfile.ZipFile(f) as z:
                        check(len(z.namelist())==len(set(z.namelist())),'Duplicate NPZ members')
                        for n in z.namelist():
                            safe(n)
                            with z.open(n) as src:
                                magic=src.read(8);check(magic[:6]==b'\x93NUMPY','Non-NPY operator snapshot member')
                                check(magic[6] in (1,2,3),'Unknown NPY encoding')
                                count=2 if magic[6]==1 else 4;length_bytes=src.read(count)
                                length=int.from_bytes(length_bytes,'little');check(length<=65536,'Oversized NPY header')
                                header=magic+length_bytes+src.read(length);h=hashlib.sha256(header);size=len(header);parts=[]
                                while True:
                                    b=src.read(self.block_size)
                                    if not b:break
                                    self.lease.pulse();h.update(b);size+=len(b);parts.append(chunk(b))
                                members.append(dict(name=n,header_hex=header.hex(),bytes=size,sha256=h.hexdigest(),chunks=parts))
                    e.update(kind='npz',members=members);entries[name]=e
                elif stat.st_size<=4*1024**2:small.append((name,f,e))
                else:
                    parts=[]
                    with open(f,'rb') as src:
                        for b in iter(lambda:src.read(self.block_size),b''):self.lease.pulse();parts.append(chunk(b))
                    e.update(kind='opaque',chunks=parts);entries[name]=e
            # Bundle new small files; unchanged files continue sharing their earlier bundle.
            while small:
                batch=[];size=0
                while small and (not batch or size+small[0][2]['source_bytes']<=32*1024**2):
                    item=small.pop(0);batch.append(item);size+=item[2]['source_bytes']
                path=plan/'bundle.zip'
                with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
                    for name,f,e in batch:
                        info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                        z.writestr(info,f.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=1)
                ref=object_ref(path)
                for name,f,e in batch:e.update(kind='bundle',object=ref);entries[name]=e
            check(entries,'Refusing an empty recovery point')
            generation=1+max([int(c.get('appProperties',{}).get('generation','0')) for c in self.rows if self._owned(c,'commit')]+[0])
            payload=dict(format=FORMAT,identity=self.identity,generation=generation,created_utc=time.time(),
                         parent=self.current['sha256'] if self.current else None,files=entries,legacy=self.legacy)
            usage=self.backend.usage(self.store_id);incoming=sum(x['ref']['bytes'] for x in pending.values())
            # Commit metadata is conservatively reserved before any data upload.
            self._budget(incoming+len(canonical(self._envelope(payload)))+1024**2,usage)
            for i,item in enumerate(pending.values(),1):
                self.lease.pulse(force=True);r=item['ref']
                m=self.backend.put(self.store_id,f'b_{r["sha256"]}.zip',item['path'],{'nexus15':self.tag,'kind':'blob'})
                check(m['md5Checksum']==r['md5'] and int(m['size'])==r['bytes'],'Uploaded object differs from planned bytes');r['id']=m['id']
                if i%8==0 or i==len(pending):print('Checkpoint uploads confirmed:',i,'/',len(pending),flush=True)
            # Recheck real quota after data uploads, retaining room for the commit record.
            path=plan/'commit.json';path.write_bytes(canonical(self._envelope(payload)))
            self._budget(path.stat().st_size,self.backend.usage(self.store_id))
            self.lease.pulse(force=True)
            m=self.backend.put(self.store_id,f'commit_{generation:08d}_{uuid.uuid4().hex}.json',path,
                               {'nexus15':self.tag,'kind':'commit','generation':str(generation)})
            confirmed=self._read_commit(m,self._refresh())
            check(confirmed['sha256']==digest(canonical(payload)),'Server commit read-back mismatch')
            self.lease.pulse(force=True)
            self.backend.set_heads(self.store_id,m['id'],self.current['meta']['id'] if self.current else '',self.tag,self.expected_heads)
            self.previous=self.current;self.current=confirmed;self.last_checkpoint=time.monotonic()
            self.expected_heads=(m['id'],self.previous['meta']['id'] if self.previous else '')
        self._gc()
        self.cache={k:v for k,v in self.cache.items() if k[0] in entries}
        print('15-MINUTE CHECKPOINT VERIFIED:',generation,f'new upload {incoming/1e6:.1f} MB; shared unchanged data; two recovery records.',flush=True)
        return True

    def _gc(self):
        # Never collect against a partial or stale manifest, or without a verified root.
        if not self.current:return
        self.lease.pulse(force=True);inventory=self._refresh();keep=[self.current]+([self.previous] if self.previous else [])
        props=self.backend.meta(self.store_id).get('appProperties',{})
        check((props.get('current',''),props.get('previous',''))==self.expected_heads,'Recovery pointer changed; no garbage collection allowed')
        for c in keep:self._read_commit(c['meta'],inventory)
        live={r for c in keep for r in self._refs(c['payload'])};commit_ids={c['meta']['id'] for c in keep}
        for m in self.rows:
            if self._owned(m,'commit') and m['id'] not in commit_ids:
                self.lease.pulse(force=True);self.backend.delete(m['id'])
        for m in self.rows:
            if self._owned(m,'blob') and m['id'] not in live:
                self.lease.pulse(force=True);self.backend.delete(m['id'])
        if self.previous:
            existing={m['id']:m for m in self.backend.list(self.backend.run_id)}
            for old in self.legacy:
                m=existing.get(old['id'])
                if not m:continue
                if m.get('md5Checksum')!=old['md5'] or int(m.get('size',-1))!=old['bytes']:
                    raise CheckpointBlocked('A legacy checkpoint changed in another runtime. New save is safe; stop concurrent notebooks before continuing.')
                self.lease.pulse(force=True);self.backend.delete(old['id'])

    def publish_export(self,local,name,kind):
        verify(local,self.identity,kind);size=Path(local).stat().st_size
        self.lease.pulse(force=True);rows=self.backend.list(self.backend.run_id)
        old=[m for m in rows if m['name']==name]
        check(len(old)<=1,'Ambiguous existing export')
        if old and old[0].get('md5Checksum')==md5(local):return old[0]
        # Never replace/delete an unrelated file merely because its name matches.
        if old:
            with tempfile.TemporaryDirectory(dir=self.local) as td:
                backup=Path(td)/'old-export.zip';self.backend.download(old[0]['id'],backup);verify(backup,self.identity,kind)
        staged=[m for m in rows if self._owned(m,kind) and m.get('appProperties',{}).get('export_name')==name and m['name']!=name]
        matches=[m for m in staged if m.get('md5Checksum')==md5(local) and int(m.get('size',-1))==size]
        if matches:m=self.backend.meta(matches[0]['id'])
        else:
            self._budget(size,self.backend.usage(self.store_id))
            m=self.backend.put(self.backend.run_id,name+'.upload_'+uuid.uuid4().hex,local,
                {'nexus15':self.tag,'kind':kind,'export_name':name})
        # Verify a temporary immutable export before retiring the previous canonical export.
        check(m.get('md5Checksum')==md5(local) and int(m.get('size',-1))==size,'Export server checksum mismatch')
        if old:
            self.lease.pulse(force=True);now=self.backend.meta(old[0]['id'])
            check(now.get('md5Checksum')==old[0].get('md5Checksum'),'Previous export changed; preserving it')
            self.backend.delete(old[0]['id'])
        self.lease.pulse(force=True);m=self.backend.rename(m['id'],name)
        for item in staged:
            if item['id']!=m['id']:self.lease.pulse(force=True);self.backend.delete(item['id'])
        return m

    def discard_export(self,name,kind):
        for m in self.backend.list(self.backend.run_id):
            if m['name']==name and self._owned(m,kind):self.lease.pulse(force=True);self.backend.delete(m['id'])

    def finish(self):
        self.pulse();z=pack(self.local,self.local/'finished-local.zip',self.identity,'FINISHED',self.files(final=True))
        m=self.publish_export(z,'NEXUS_STAGE14_FINISHED.zip','FINISHED')
        self.finished_bytes=int(m['size']);self.finished_location=m.get('webViewLink') or (self.drive/'NEXUS_STAGE14_FINISHED.zip')
        # The final ZIP is independently server-confirmed before removing resume chunks.
        self._retire_resume_objects()
        existing={r['id']:r for r in self.backend.list(self.backend.run_id)}
        for old in self.legacy:
            item=existing.get(old['id'])
            if item and item.get('md5Checksum')==old['md5']:
                self.lease.pulse(force=True);self.backend.delete(item['id'])
        return z

    def _retire_resume_objects(self):
        if self.store_id is None:return
        self.lease.pulse(force=True)
        for item in self._refresh().values():
            if self._owned(item) and item.get('appProperties',{}).get('kind') in ('commit','blob'):
                self.lease.pulse(force=True);self.backend.delete(item['id'])
        props=self.backend.meta(self.store_id).get('appProperties',{})
        self.backend.set_heads(self.store_id,'','',self.tag,(props.get('current',''),props.get('previous','')))
