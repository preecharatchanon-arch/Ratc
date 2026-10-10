"""Small verified archives; one rolling checkpoint, plus a predecessor."""
import hashlib,json,os,shutil,time,zipfile
from pathlib import Path,PurePosixPath


def check(ok,msg):
    if not ok:raise RuntimeError(msg)


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


def write_json(path,x):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    with open(temp,'w') as f:json.dump(x,f,sort_keys=True,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def safe(n):
    p=PurePosixPath(n);check(n and not p.is_absolute() and '..' not in p.parts and '\\' not in n,'Unsafe ZIP path')


def pack(root,target,identity,kind,files):
    root=Path(root);target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);entries=[]
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for f in sorted(set(Path(p) for p in files)):
            n=f.relative_to(root).as_posix();safe(n);z.write(f,n)
            entries.append({'path':n,'bytes':f.stat().st_size,'sha256':sha(f)})
        z.writestr('MANIFEST.json',json.dumps({'identity':identity,'kind':kind,'files':entries},sort_keys=True))
    verify(target,identity,kind)
    return target


def verify(path,identity,kind=None):
    with zipfile.ZipFile(path) as z:
        names=z.namelist();check(len(names)==len(set(names)),'Duplicate members')
        for n in names:safe(n)
        m=json.loads(z.read('MANIFEST.json'));check(m['identity']==identity,'Archive identity mismatch')
        if kind is not None:check(m['kind']==kind,'Archive type mismatch')
        check(len(m['files'])==len({e['path'] for e in m['files']}),'Duplicate manifest entries')
        check(set(names)=={'MANIFEST.json'}|{e['path'] for e in m['files']},'Manifest membership mismatch')
        for e in m['files']:
            h=hashlib.sha256();size=0
            with z.open(e['path']) as f:
                for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b);size+=len(b)
            check(size==e['bytes'] and h.hexdigest()==e['sha256'],'Corrupted archive payload: '+e['path'])
    return m


def unpack(path,root,identity,kind):
    m=verify(path,identity,kind)
    with zipfile.ZipFile(path) as z:
        for e in m['files']:
            dst=Path(root)/e['path'];dst.parent.mkdir(parents=True,exist_ok=True);tmp=dst.with_name(dst.name+'.tmp')
            with z.open(e['path']) as f,open(tmp,'wb') as out:shutil.copyfileobj(f,out)
            os.replace(tmp,dst)
    return m


def publish(local,dest):
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True);digest=sha(local)
    temp=dest.with_name(dest.name+'.uploading')
    with open(local,'rb') as f,open(temp,'wb') as out:
        shutil.copyfileobj(f,out,4*1024*1024);out.flush();os.fsync(out.fileno())
    check(sha(temp)==digest,'Drive read-back failed; prior archive retained')
    os.replace(temp,dest);check(sha(dest)==digest,'Published archive digest differs')
    return dest


class Lease:
    def __init__(self,folder):self.path=Path(folder)/'LEASE.json';self.token=os.urandom(16).hex();self.last=0
    def acquire(self):
        if self.path.exists():
            old=json.loads(self.path.read_text());check(time.time()-old['heartbeat']>900,'Another recent session owns this run')
            self.path.unlink()
        fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'token':self.token,'heartbeat':time.time()},f);f.flush();os.fsync(f.fileno())
        self.last=time.monotonic()
    def pulse(self):
        if time.monotonic()-self.last>30:
            check(json.loads(self.path.read_text())['token']==self.token,'Session lease lost')
            write_json(self.path,{'token':self.token,'heartbeat':time.time()});self.last=time.monotonic()
    def release(self):
        if self.path.exists() and json.loads(self.path.read_text())['token']==self.token:self.path.unlink()

class Campaign:
    """A single cumulative checkpoint plus predecessor, then one final ZIP."""
    def __init__(self,drive,local,identity):
        self.drive=Path(drive);self.local=Path(local);self.identity=identity
        self.drive.mkdir(parents=True,exist_ok=True);self.local.mkdir(parents=True,exist_ok=True)
        self.lease=Lease(self.drive);self.last_checkpoint=time.monotonic()
    def activate(self):
        self.lease.acquire()
        try:
            p=self.drive/'IDENTITY.json'
            if p.exists():check(json.loads(p.read_text())==self.identity,'Code/config/runtime mismatch: refusing changed campaign')
            else:
                check(not list(self.drive.glob('*.zip')),'Existing archives lack identity')
                write_json(p,self.identity)
            # Verified published state is authoritative; discard uncommitted runtime files.
            for top in ('units','metadata','analysis'):
                p=self.local/top
                if p.exists():shutil.rmtree(p)
            bad=False
            for filename,kind in [('NEXUS_STAGE12_FINISHED.zip','FINISHED'),('CHECKPOINT.zip','CHECKPOINT'),('CHECKPOINT_PREVIOUS.zip','CHECKPOINT')]:
                p=self.drive/filename
                if p.exists():
                    try:unpack(p,self.local,self.identity,kind)
                    except (RuntimeError,zipfile.BadZipFile,ValueError,KeyError):
                        if filename!='CHECKPOINT.zip':raise
                        print('Invalid current checkpoint; trying verified predecessor.',flush=True);bad=True;continue
                    return kind
            check(not bad,'No valid checkpoint predecessor; refusing to restart over corrupt saved data')
            return None
        except BaseException:
            self.lease.release();raise
    def pulse(self):self.lease.pulse()
    def files(self,final=False):
        return [p for top in ('units','metadata','analysis') for p in (self.local/top).rglob('*')
                if p.is_file() and not p.name.endswith('.tmp') and (not final or not p.name.endswith('.resume.npz'))]
    def checkpoint(self,force=False):
        self.pulse()
        if not force and time.monotonic()-self.last_checkpoint<900:return False
        z=pack(self.local,self.local/'checkpoint-local.zip',self.identity,'CHECKPOINT',self.files())
        old=self.drive/'CHECKPOINT.zip';previous=self.drive/'CHECKPOINT_PREVIOUS.zip'
        if old.exists():
            try:verify(old,self.identity,'CHECKPOINT')
            except (RuntimeError,zipfile.BadZipFile,ValueError,KeyError):pass
            else:publish(old,previous)
        publish(z,old);verify(old,self.identity,'CHECKPOINT')
        self.last_checkpoint=time.monotonic()
        print('Verified resumable checkpoint:',round(old.stat().st_size/1e6,1),'MB; at most two checkpoint ZIPs on Drive.',flush=True)
        return True
    def finish(self):
        self.pulse();z=pack(self.local,self.local/'finished-local.zip',self.identity,'FINISHED',self.files(final=True))
        dest=publish(z,self.drive/'NEXUS_STAGE12_FINISHED.zip');verify(dest,self.identity,'FINISHED')
        for name in ('CHECKPOINT.zip','CHECKPOINT_PREVIOUS.zip'):
            p=self.drive/name
            if p.exists():p.unlink()
        return dest
