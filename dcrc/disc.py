"""Read-only GDI/ISO9660 and extracted-folder input (Python stdlib, MIT)."""
from __future__ import annotations
import hashlib,json,os,re,shlex,struct
from pathlib import Path
from .errors import ConverterError,Cancelled
from . import profiles

SECTOR=2048
MAX_FILES=100000
MAX_DIRECTORY=16*1024*1024

def _fail(message,code='INVALID_SOURCE'):raise ConverterError(code,message)
def _cancel(cancel):
    if cancel is not None and (cancel.is_set()if hasattr(cancel,'is_set')else cancel()):raise Cancelled()
def _link(p):
    if p.is_symlink()or bool(getattr(p,'is_junction',lambda:False)()):return True
    if os.name=='nt':
        try:return bool(getattr(p.lstat(),'st_file_attributes',0)&0x400) # reparse point, including Python3.11 junctions
        except FileNotFoundError:return False
    return False
def _plain_path(p):
    p=Path(os.path.abspath(p))
    if any(_link(q)for q in (p,*p.parents)):_fail(f'Symbolic links/junctions are not accepted: {p}','UNSAFE_PATH')
    return p
def _name(name):
    if not name or name in ('.','..')or any(c in name for c in '/\\:<>"|?*')or any(ord(c)<32 or ord(c)==127 for c in name)or name[-1]in '. 'or len(name)>128:_fail(f'Unsafe disc filename: {name!r}','UNSAFE_PATH')
    if name.split('.')[0].upper()in {'CON','PRN','AUX','NUL',*(f'COM{i}'for i in range(1,10)),*(f'LPT{i}'for i in range(1,10))}:_fail(f'Reserved output filename: {name}','UNSAFE_PATH')
    return name
def _relative(name):
    if name.startswith(('/','\\'))or ':'in name:_fail('Absolute track paths are not accepted','UNSAFE_PATH')
    parts=name.replace('\\','/').split('/')
    for p in parts:_name(p)
    return Path(*parts)
def _fingerprint(files):return hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
def _destination(path):
    p=_plain_path(path)
    if p.exists()and(not p.is_dir()or any(p.iterdir())):_fail(f'Destination must be a new or empty directory: {p}','OUTPUT_EXISTS')
    return p

class _Track:
    def __init__(self,path,lba,size,offset,sectors):
        self.path,self.lba,self.size,self.offset,self.sectors=path,lba,size,offset,sectors
        self.f=path.open('rb')
    def close(self):self.f.close()
    def read(self,lba,count):
        if lba<self.lba or count<0 or lba+count>self.lba+self.sectors:_fail('ISO extent exceeds a data track')
        self.f.seek(self.offset+(lba-self.lba)*self.size);raw=self.f.read(count*self.size)
        if len(raw)!=count*self.size:_fail('Short read from source track')
        if self.size==2048:return raw
        out=bytearray(count*SECTOR)
        for i in range(count):
            r=raw[i*self.size:(i+1)*self.size]
            if r[:12]!=b'\0'+b'\xff'*10+b'\0':_fail('Invalid raw sector sync')
            bcd=lambda v:(v>>4)*10+(v&15)
            # GD-ROM extends the minute nibble past99 (e.g.121 minutes).
            if any((v&15)>9 for v in r[12:15])or any((v>>4)>9 for v in r[13:15])or bcd(r[13])>=60 or bcd(r[14])>=75:_fail('Invalid sector address')
            address=(bcd(r[12])*60+bcd(r[13]))*75+bcd(r[14])-150
            if address!=lba+i:_fail('Raw sector address disagrees with GDI LBA')
            if r[15]==1:off=16
            elif r[15]==2 and r[16:20]==r[20:24]and not(r[18]&0x20):off=24
            else:_fail('Only Mode1 or Mode2 Form1 data sectors are supported')
            out[i*SECTOR:(i+1)*SECTOR]=r[off:off+SECTOR]
        return bytes(out)

class _Image:
    def __init__(self,source):
        self.tracks=[];self.metadata=[]
        try:
            if source.suffix.lower()=='.iso':
                n=source.stat().st_size
                if not n or n%SECTOR:_fail('ISO must contain complete 2048-byte sectors')
                self.tracks=[_Track(source,0,2048,0,n//2048)];self.metadata=[{'number':1,'lba':0,'kind':4,'sector_size':2048,'file':source.name,'offset':0,'sectors':n//2048}]
                return
            if source.suffix.lower()!='.gdi':_fail('Select a GDI with its tracks or an extracted data folder.','UNSUPPORTED_IMAGE')
            if source.stat().st_size>1024*1024:_fail('Oversized GDI descriptor')
            lines=[s.strip()for s in source.read_text(encoding='utf-8-sig').splitlines()if s.strip()]
            if not lines or not re.fullmatch(r'[0-9]+',lines[0]):_fail('Invalid GDI track count')
            rows=[shlex.split(s)for s in lines[1:]]
            if not 1<=int(lines[0])<=99 or len(rows)!=int(lines[0]):_fail('GDI track count does not match descriptor')
            seen=set();previous=-1
            for row in rows:
                if len(row)!=6:_fail('Each GDI track must contain six fields')
                n,lba,kind,ss,name,off=row;n,lba,kind,ss,off=map(int,(n,lba,kind,ss,off))
                if n in seen or n<1 or lba<0 or lba<=previous or kind not in (0,4)or ss not in (2048,2352)or off<0:_fail('Invalid GDI track geometry')
                seen.add(n);previous=lba;rel=_relative(name);p=_plain_path(source.parent/rel)
                if not p.is_file()or not p.resolve().is_relative_to(source.parent.resolve()):_fail(f'Missing or escaped track: {name}')
                z=p.stat().st_size-off
                if z<=0 or z%ss:_fail('Track offset/size does not describe complete sectors')
                self.metadata.append({'number':n,'lba':lba,'kind':kind,'sector_size':ss,'file':rel.as_posix(),'offset':off,'sectors':z//ss})
            for i,m in enumerate(self.metadata):
                count=m['sectors']
                if i+1<len(self.metadata):count=min(count,self.metadata[i+1]['lba']-m['lba'])
                same=[q['offset']for q in self.metadata if q['file']==m['file']and q['offset']>m['offset']]
                if same:count=min(count,(min(same)-m['offset'])//m['sector_size'])
                if count<=0:_fail('Empty or overlapping GDI track')
                m['sectors']=count
                if m['kind']==4:self.tracks.append(_Track(source.parent/m['file'],m['lba'],m['sector_size'],m['offset'],count))
            if not self.tracks:_fail('No GDI data tracks')
        except BaseException:
            self.close();raise
    def close(self):
        for t in self.tracks:t.close()
    def extent(self,lba,size):
        if lba<0 or size<0 or size>2**31:_fail('Invalid ISO extent size')
        left=size
        while left:
            t=next((t for t in self.tracks if t.lba<=lba<t.lba+t.sectors),None)
            if t is None:_fail(f'ISO extent is outside data tracks at LBA {lba}')
            count=min((left+SECTOR-1)//SECTOR,t.lba+t.sectors-lba,512)
            b=t.read(lba,count)[:left];yield b;left-=len(b);lba+=count
    def files(self):
        pvd=None
        for t in reversed(self.tracks):
            if t.sectors<=16:continue
            p=t.read(t.lba+16,1)
            if p[:7]==b'\1CD001\1':pvd=p;break
        if pvd is None:_fail('No ISO9660 primary volume descriptor')
        if pvd[128:132]!=b'\0\10\10\0':_fail('ISO logical blocks must be2048 bytes')
        def u32(r,i):
            a=struct.unpack_from('<I',r,i)[0]
            if a!=struct.unpack_from('>I',r,i+4)[0]:_fail('ISO endian extent fields disagree')
            return a
        def rec(r):
            if len(r)<34 or r[0]!=len(r)or r[1]or r[26]or r[27]or r[25]&0x80:_fail('Unsupported or malformed ISO record')
            if r[32]<1 or 33+r[32]>len(r):_fail('Truncated ISO filename')
            return u32(r,2),u32(r,10),bool(r[25]&2),r[33:33+r[32]]
        n=pvd[156]
        if n<34 or 156+n>len(pvd):_fail('Invalid ISO root record')
        lba,size,isdir,_=rec(pvd[156:156+n])
        if not isdir:_fail('ISO root must be a directory')
        out=[];visited=set();names=set();directory_bytes=0
        def walk(lba,size,prefix,depth):
            nonlocal directory_bytes
            if depth>32 or (lba,size)in visited:_fail('ISO directory cycle or excessive depth')
            if size>MAX_DIRECTORY or directory_bytes+size>64*1024*1024:_fail('Oversized ISO directory')
            visited.add((lba,size));directory_bytes+=size;data=b''.join(self.extent(lba,size));pos=0
            while pos<len(data):
                n=data[pos]
                if n==0:pos=(pos//SECTOR+1)*SECTOR;continue
                if n<34 or pos+n>len(data)or pos%SECTOR+n>SECTOR:_fail('ISO record exceeds directory sector')
                e,z,d,name=rec(data[pos:pos+n]);pos+=n
                if name in (b'\0',b'\1'):continue
                try:name=name.decode('ascii').split(';')[0]
                except UnicodeDecodeError:_fail('Non-ASCII ISO filename')
                name=_name(name);path=prefix+name;fold=path.casefold()
                if fold in names:_fail(f'Duplicate normalized ISO path: {path}','PATH_COLLISION')
                names.add(fold)
                if len(names)>MAX_FILES or len(path)>1024:_fail('ISO file/path limit exceeded')
                if d:walk(e,z,path+'/',depth+1)
                else:out.append({'path':path,'bytes':z,'lba':e})
        walk(lba,size,'',0)
        return sorted(out,key=lambda e:e['path'])

def _folder_entries(root):
    entries=[];seen=set()
    for base,dirs,files in os.walk(root,followlinks=False):
        for name in dirs+files:
            if not name.isascii():_fail(f'Expected ASCII game filenames, found: {name}','UNSAFE_PATH')
            _name(name);p=_plain_path(Path(base)/name);rel=p.relative_to(root).as_posix();fold=rel.casefold()
            if fold in seen:_fail(f'Duplicate normalized source path: {rel}','PATH_COLLISION')
            seen.add(fold)
            if len(seen)>MAX_FILES:_fail('Too many extracted files')
            if p.is_file():entries.append({'path':rel,'bytes':p.stat().st_size})
            elif not p.is_dir():_fail('Only regular files/directories are accepted')
    return sorted(entries,key=lambda e:e['path'])

def _inspect(source,progress=None,cancel=None):
    _cancel(cancel);source=_plain_path(source)
    if not source.exists():_fail(f'Source not found: {source}','MISSING_SOURCE')
    image=None
    try:
        if source.is_dir():
            root=source/'data'if(source/'data'/'1ST_READ.BIN').is_file()else source;root=_plain_path(root);entries=_folder_entries(root);kind='folder'
            def chunks(e):
                p=_plain_path(root/e['path'])
                with p.open('rb')as f:
                    while b:=f.read(1024*1024):yield b
        else:
            image=_Image(source);entries=image.files();kind=source.suffix.lower()[1:]
            def chunks(e):return image.extent(e['lba'],e['bytes'])
        total=sum(e['bytes']for e in entries);done=0;files=[]
        for e in entries:
            h=hashlib.sha256();n=0
            for b in chunks(e):_cancel(cancel);h.update(b);n+=len(b)
            if n!=e['bytes']:_fail(f'Source size changed: {e["path"]}')
            files.append({'path':e['path'],'bytes':n,'sha256':h.hexdigest()});done+=n
            if progress:progress({'type':'progress','stage':'identify','message':e['path'],'progress':done/total if total else 1})
        byname={e['path']:e for e in entries}
        def read(name):
            _cancel(cancel)
            return b''.join(chunks(byname[name]))
        identity=profiles.validate_files(files,read)
        return {**identity,'kind':kind,'source':str(source),'data_root':str(root)if kind=='folder'else None,'tracks':image.metadata if image else [],'files':files,'fingerprint':_fingerprint(files)}
    finally:
        if image:image.close()

def inspect_source(source,progress=None,cancel=None):
    try:return _inspect(Path(source),progress,cancel)
    except (ConverterError,Cancelled):raise
    except (OSError,ValueError,UnicodeError,struct.error)as e:raise ConverterError('INVALID_SOURCE',f'Cannot inspect source: {e}')from e

def _extract_source(source,destination,progress=None,cancel=None):
    """Verify before writing, then exclusive-copy with full hash readback."""
    destination=_destination(destination);source=_plain_path(source)
    if destination==source or destination.is_relative_to(source)or source.is_relative_to(destination):_fail('Source and destination must not contain each other','UNSAFE_PATH')
    identity=_inspect(source,progress,cancel);_cancel(cancel);destination.mkdir(parents=True,exist_ok=True);image=None
    try:
        if identity['kind']=='folder':
            root=Path(identity['data_root'])
            def chunks(name):
                with _plain_path(root/name).open('rb')as f:
                    while b:=f.read(1024*1024):yield b
        else:
            image=_Image(source);byname={e['path']:e for e in image.files()}
            def chunks(name):e=byname[name];return image.extent(e['lba'],e['bytes'])
        total=sum(e['bytes']for e in identity['files']);done=0
        for e in identity['files']:
            _cancel(cancel);target=_plain_path(destination/e['path']);target.parent.mkdir(parents=True,exist_ok=True);_plain_path(target);h=hashlib.sha256();n=0
            with target.open('xb')as f:
                for b in chunks(e['path']):_cancel(cancel);f.write(b);h.update(b);n+=len(b)
            if n!=e['bytes']or h.hexdigest()!=e['sha256']:_fail(f'Source changed while extracting: {e["path"]}')
            with target.open('rb')as f:
                check=hashlib.file_digest(f,'sha256').hexdigest()
            if check!=e['sha256']:_fail(f'Extraction readback differs: {e["path"]}')
            done+=n
            if progress:progress({'type':'progress','stage':'extract','message':e['path'],'progress':done/total if total else 1})
        return {**identity,'data_root':str(destination)}
    finally:
        if image:image.close()

def extract_source(source,destination,progress=None,cancel=None):
    try:return _extract_source(source,destination,progress,cancel)
    except (ConverterError,Cancelled):raise
    except FileExistsError as e:raise ConverterError('OUTPUT_EXISTS',f'Extraction refuses to overwrite a file: {e}')from e
    except (OSError,ValueError,UnicodeError,struct.error)as e:raise ConverterError('INVALID_SOURCE',f'Cannot extract source: {e}')from e
