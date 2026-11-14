"""Content receipts and owned work directories. No automatic deletion or GC."""
from pathlib import Path, PurePosixPath
import hashlib,json,os,uuid
from .errors import ConverterError

def file_digest(path):
    path=Path(path); reject_links(path)
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(4<<20),b''):h.update(data)
    return {'bytes':path.stat().st_size,'sha256':h.hexdigest()}

def reject_links(path):
    p=Path(path)
    if p.is_symlink() or getattr(p,'is_junction',lambda:False)():
        raise ConverterError('unsafe_path',f'Linked paths are not accepted: {p}')

def windows_native_path_too_long(path):
    # Use the classic MAX_PATH bound for compiler and intermediate file paths.
    return os.name == 'nt' and len(str(path).encode('utf-16-le', 'surrogatepass')) >= 260 * 2


def plain_path(path):
    p=Path(path).expanduser().absolute()
    for part in (*reversed(p.parents),p):reject_links(part)
    return p.resolve()

def safe_relative(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value:
        raise ConverterError('unsafe_path','Invalid relative path in a conversion receipt.')
    p=PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or str(p)!=value:
        raise ConverterError('unsafe_path','Invalid relative path in a conversion receipt.')
    return p

def checked_path(root,relative):
    rel=safe_relative(relative);p=Path(root)
    reject_links(p)
    for part in rel.parts:p=p/part;reject_links(p)
    if not p.resolve().is_relative_to(Path(root).resolve()):raise ConverterError('unsafe_path','Path leaves the owned directory.')
    return p

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);reject_links(path)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,default=str);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)

def read_json(path):
    reject_links(path)
    try:return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError,ValueError) as e:raise ConverterError('receipt',f'Cannot read conversion receipt: {path}',str(e)) from e

def tree_files(root):
    root=Path(root);reject_links(root);out={}
    for p in sorted(root.rglob('*')):
        reject_links(p)
        if p.is_file():out[p.relative_to(root).as_posix()]=file_digest(p)
    return out

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode('utf-8')).hexdigest()

def fingerprint_tree(root):return fingerprint(tree_files(root))

class StageCache:
    def __init__(self,root,event=None):
        self.root=plain_path(root)
        marker=self.root/'dcrc_workspace.json'
        if self.root.exists() and any(self.root.iterdir()) and not marker.is_file():
            raise ConverterError('foreign_workspace','The nonempty work folder was not made by DCRC. Choose an empty work folder.')
        self.root.mkdir(parents=True,exist_ok=True);self.event=event or (lambda v:None)
        if marker.exists():
            value=read_json(marker)
            if not isinstance(value,dict) or value.get('format')!='DCRC_WORK_V1':raise ConverterError('workspace','Not a DCRC work directory.')
        else:write_json(marker,{'format':'DCRC_WORK_V1','id':uuid.uuid4().hex})

    def run(self,name,key,action):
        safe_relative(name);key=fingerprint(key)
        parent=checked_path(self.root,'stages/'+name+'/'+key);parent.mkdir(parents=True,exist_ok=True);reject_links(parent)
        receipt=parent/'receipt.json'
        if receipt.exists():
            try:
                old=read_json(receipt)
                if not isinstance(old,dict) or old.get('format')!='DCRC_STAGE_V2':raise ValueError('Invalid stage receipt')
                run=checked_path(self.root,old['run'])
                if run.parent!=parent:raise ValueError('Stage belongs to another key')
                result=read_json(run/'DCRC_RESULT.json')
                if old.get('key')==key and isinstance(old.get('files'),dict) and old['files'] and result==old.get('result') and self._result_owned(result,run) and tree_files(run)==old['files']:
                    self.event({'type':'stage','stage':name,'state':'cached','message':f'{name}: cached and SHA256 verified'})
                    return result
            except (ConverterError,KeyError,OSError,TypeError,ValueError):pass
        run=parent/('run_'+uuid.uuid4().hex);run.mkdir()
        self.event({'type':'stage','stage':name,'state':'running','message':f'{name}: running'})
        result=action(run)
        if not self._result_owned(result,run):raise ConverterError('stage_path',f'{name} returned a path outside its owned stage directory.')
        if not tree_files(run):raise ConverterError('empty_stage',f'{name} produced no files.')
        write_json(run/'DCRC_RESULT.json',result)
        files=tree_files(run)
        write_json(receipt,{'format':'DCRC_STAGE_V2','key':key,'run':run.relative_to(self.root).as_posix(),'files':files,'result':result})
        self.event({'type':'stage','stage':name,'state':'done','message':f'{name}: complete and SHA256 verified'})
        return result

    @staticmethod
    def _result_owned(result,run):
        if not isinstance(result,dict):return False
        keys=('file','source_root','data_root','generated','logs','payload_root','manifest')
        if any(k in result and not isinstance(result[k],str) for k in keys):return False
        paths=[result[k] for k in keys if k in result]
        if 'artifacts' in result:
            if not isinstance(result['artifacts'],dict):return False
            paths.extend(result['artifacts'].values())
        return all(isinstance(v,str) and Path(v).resolve().is_relative_to(run.resolve()) for v in paths)
