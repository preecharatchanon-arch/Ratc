"""Server-backed Drive transport. Credentials stay in Colab's normal auth flow."""
import hashlib, io, json, time, uuid
from pathlib import Path

FIELDS='id,name,mimeType,size,md5Checksum,quotaBytesUsed,parents,appProperties,trashed,webViewLink'


def authorized_transport(credentials,timeout=60):
    """Use Google's 308-aware factory; bare httplib2.Http breaks chunk uploads."""
    from googleapiclient.http import build_http
    import google_auth_httplib2
    transport=build_http()
    transport.timeout=timeout
    if hasattr(transport,'redirect_codes') and 308 in transport.redirect_codes:
        raise RuntimeError('Drive upload transport incorrectly treats 308 as a redirect')
    return google_auth_httplib2.AuthorizedHttp(credentials,http=transport)


def md5(path):
    h=hashlib.md5()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


class DriveBackend:
    def __init__(self,service,run_id):
        self.service=service;self.run_id=run_id;self.on_progress=lambda:None
        self._written={};self._deleted=set()
        m=self.meta(run_id)
        if m['mimeType']!='application/vnd.google-apps.folder' or m.get('trashed'):
            raise RuntimeError('The saved Stage14 Drive folder is unavailable')

    def _list(self,q):
        rows=[];token=None
        while True:
            r=self.service.files().list(q=q,pageSize=1000,pageToken=token,
                fields=f'nextPageToken,files({FIELDS})',spaces='drive').execute(num_retries=3)
            rows.extend(r.get('files',[]));token=r.get('nextPageToken')
            if not token:return rows

    def list(self,parent):
        rows={m['id']:m for m in self._list(f"'{parent}' in parents and trashed = false") if m['id'] not in self._deleted}
        for file_id,m in self._written.items():
            if parent in m.get('parents',[]) and not m.get('trashed'):rows[file_id]=m
        return list(rows.values())
    def meta(self,file_id):return self.service.files().get(fileId=file_id,fields=FIELDS).execute(num_retries=3)
    def mkdir(self,parent,name,tag):
        file_id=self.service.files().generateIds(count=1,space='drive',type='files').execute(num_retries=3)['ids'][0]
        body=dict(id=file_id,name=name,parents=[parent],mimeType='application/vnd.google-apps.folder',appProperties={'nexus15':tag,'kind':'store'})
        try:self.service.files().create(body=body,fields=FIELDS).execute(num_retries=3)
        except Exception:
            m=self.meta(file_id)
            if m.get('name')!=name or m.get('parents')!=[parent] or m.get('appProperties')!=body['appProperties']:raise
        m=self.meta(file_id)
        if m.get('mimeType')!=body['mimeType'] or m.get('appProperties')!=body['appProperties']:
            raise RuntimeError('Checkpoint folder creation was not server-confirmed')
        self._written[m['id']]=m;return m

    def set_heads(self,folder,current,previous,tag,expected):
        old=self.meta(folder).get('appProperties',{})
        if (old.get('current',''),old.get('previous',''))!=tuple(expected):
            raise RuntimeError('Recovery pointer changed in another session')
        props=dict(nexus15=tag,kind='store',current=current or '',previous=previous or '')
        try:self.service.files().update(fileId=folder,body={'appProperties':props},fields=FIELDS).execute(num_retries=3)
        except Exception:
            m=self.meta(folder)
            if any(m.get('appProperties',{}).get(k,'')!=v for k,v in props.items()):raise
        m=self.meta(folder)
        if any(m.get('appProperties',{}).get(k,'')!=v for k,v in props.items()):raise RuntimeError('Recovery pointer server read-back mismatch')
        self._written[m['id']]=m
        return m

    def put(self,parent,name,path,props=None,replace_id=None):
        from googleapiclient.http import MediaFileUpload
        path=Path(path);expected=md5(path);size=path.stat().st_size
        media=MediaFileUpload(str(path),mimetype='application/octet-stream',chunksize=8*1024**2,resumable=True)
        if replace_id:
            req=self.service.files().update(fileId=replace_id,body={'name':name},media_body=media,fields=FIELDS)
            file_id=replace_id
        else:
            file_id=self.service.files().generateIds(count=1,space='drive',type='files').execute(num_retries=3)['ids'][0]
            req=self.service.files().create(body=dict(id=file_id,name=name,parents=[parent],appProperties=props or {}),media_body=media,fields=FIELDS)
        try:
            result=None
            while result is None:
                self.on_progress();_,result=req.next_chunk(num_retries=3)
        except Exception as upload_error:
            # A completed upload can outlive a lost response. Reuse this exact ID only.
            try:m=self.meta(file_id)
            except Exception:
                # An uncommitted resumable upload normally has no visible file ID.
                # Keep the actual transport error; a metadata 404 is not its cause.
                raise upload_error from None
            if int(m.get('size',-1))!=size or m.get('md5Checksum')!=expected:raise upload_error from None
        m=self.meta(file_id)
        if int(m.get('size',-1))!=size or m.get('md5Checksum')!=expected:
            raise RuntimeError('Server upload checksum/size mismatch; prior commits retained')
        self._written[m['id']]=m;return m

    def download(self,file_id,path):
        from googleapiclient.http import MediaIoBaseDownload
        m=self.meta(file_id);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_name(path.name+'.downloading')
        with open(tmp,'wb') as f:
            dl=MediaIoBaseDownload(f,self.service.files().get_media(fileId=file_id),chunksize=8*1024**2)
            done=False
            while not done:self.on_progress();_,done=dl.next_chunk(num_retries=3)
        if int(m.get('size',-1))!=tmp.stat().st_size or m.get('md5Checksum')!=md5(tmp):
            tmp.unlink(missing_ok=True);raise RuntimeError('Server download checksum mismatch')
        tmp.replace(path);return m

    def read_json(self,file_id):
        b=self.service.files().get_media(fileId=file_id).execute(num_retries=3)
        return json.loads(b.decode() if isinstance(b,bytes) else b)

    def delete(self,file_id):
        try:self.service.files().delete(fileId=file_id).execute(num_retries=3)
        except Exception:
            # A lost deletion response must not turn successful cleanup into a failed save.
            try:self.meta(file_id)
            except Exception as probe:
                if getattr(getattr(probe,'resp',None),'status',None)==404:
                    self._written.pop(file_id,None);self._deleted.add(file_id);return
            raise
        self._written.pop(file_id,None)
        self._deleted.add(file_id)

    def rename(self,file_id,name):
        m=self.service.files().update(fileId=file_id,body={'name':name},fields=FIELDS).execute(num_retries=3)
        m=self.meta(file_id)
        if m.get('name')!=name:raise RuntimeError('Export name publication was not confirmed')
        self._written[m['id']]=m;return m

    def usage(self,store_id):
        # Count owned project descendants, including Trash and pinned binary revisions.
        # Account quota also guards files outside the project-name scope.
        merged={m['id']:m for m in self._list("'me' in owners") if m['id'] not in self._deleted};merged.update(self._written)
        # Direct checkpoint metadata avoids stale global listings resurrecting deleted
        # legacy archives/objects after a reconnect. Only an actual 404 proves deletion.
        if store_id:
            for m in self.list(store_id):merged[m['id']]=m
        initial=list(merged.values())
        for m in initial:
            if (store_id and store_id in m.get('parents',[])) or (self.run_id in m.get('parents',[]) and
                    m.get('name') in ('CHECKPOINT.zip','CHECKPOINT_PREVIOUS.zip')):
                try:merged[m['id']]=self.meta(m['id'])
                except Exception as e:
                    if getattr(getattr(e,'resp',None),'status',None)!=404:raise
                    merged.pop(m['id'],None);self._written.pop(m['id'],None);self._deleted.add(m['id'])
        files=list(merged.values())
        roots={self.run_id}|{f['id'] for f in files if f.get('mimeType')=='application/vnd.google-apps.folder'
                              and f.get('name','').upper().startswith('NEXUS')}
        project=set(roots);store={store_id} if store_id else set()
        changed=True
        while changed:
            changed=False
            for f in files:
                parents=set(f.get('parents',[]))
                if f['id'] not in project and (parents&project or f.get('name','').upper().startswith('NEXUS')):
                    project.add(f['id']);changed=True
                if f['id'] not in store and parents&store:store.add(f['id']);changed=True
        def used(f):return int(f.get('quotaBytesUsed',f.get('size',0)))
        checkpoint_ids=store|{f['id'] for f in files if self.run_id in f.get('parents',[]) and
                              f.get('name') in ('CHECKPOINT.zip','CHECKPOINT_PREVIOUS.zip')}
        quota=self.service.about().get(fields='storageQuota').execute(num_retries=3)['storageQuota']
        account_bytes=max(int(quota['usage']),int(quota['usage'])-int(quota.get('usageInDrive',quota['usage']))+sum(used(f) for f in files))
        return dict(project_bytes=sum(used(f) for f in files if f['id'] in project),
                    checkpoint_bytes=sum(used(f) for f in files if f['id'] in checkpoint_ids),
                    account_bytes=account_bytes,account_limit=int(quota['limit']) if 'limit' in quota else None,
                    includes_trash=True,scope='Owned NEXUS-named files/folders and descendants; saved run; account-wide quota')


class ServerLease:
    """Same 15-minute stale-session rule, confirmed against Drive's server."""
    def __init__(self,backend,local):
        self.backend=backend;self.local=Path(local);self.token=uuid.uuid4().hex;self.file_id=None;self.last=0.;self.writing=False

    def acquire(self):
        rows=[r for r in self.backend.list(self.backend.run_id) if r['name']=='LEASE.json']
        if len(rows)>1:raise RuntimeError('Multiple session leases exist; refusing concurrent writers')
        if rows:
            old=self.backend.read_json(rows[0]['id'])
            if time.time()-old['heartbeat']<=900:raise RuntimeError('Another recent session owns this run; stop it or wait for its lease to expire')
            self.file_id=rows[0]['id']
        self._write()
        self.check()
        self.last=time.monotonic()

    def _write(self):
        self.writing=True
        try:
            self.local.mkdir(parents=True,exist_ok=True);p=self.local/'lease-upload.json'
            p.write_text(json.dumps(dict(token=self.token,heartbeat=time.time())))
            m=self.backend.put(self.backend.run_id,'LEASE.json',p,replace_id=self.file_id)
            self.file_id=m['id'];self.last=time.monotonic()
        finally:self.writing=False

    def check(self):
        rows=[r for r in self.backend.list(self.backend.run_id) if r['name']=='LEASE.json']
        if len(rows)!=1 or rows[0]['id']!=self.file_id or self.backend.read_json(self.file_id).get('token')!=self.token:
            raise RuntimeError('Session lease lost; no checkpoint mutation is allowed')

    def pulse(self,force=False):
        if self.writing:return
        if force or time.monotonic()-self.last>30:self.check();self._write()

    def release(self):
        if self.file_id:
            try:
                if self.backend.read_json(self.file_id).get('token')==self.token:self.backend.delete(self.file_id)
            except Exception:pass  # A lost connection leaves a lease that expires; never delete another owner.
