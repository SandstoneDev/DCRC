"""Own local SFD -> video-only PMF plus IMA WAV stage. MIT, SandstoneDev 2026.
PSMF format tooling originated in our PS2RC/SDXR projects. Encoders are external.
Inputs and all derived movies remain user-local; no game/SDK binaries are shipped.
"""
from __future__ import annotations
import hashlib,json,math,os,re,shutil,struct
from pathlib import Path
from .errors import Cancelled,ConverterError
from .media_tools import find_tool
from .storage import plain_path,reject_links,fingerprint
from tools import movie_pmfmux as pmfmux
from tools import movie_pmfinfo as pmfinfo

MOVIE_BIN_BYTES=184592
MOVIE_BIN_SHA256='84489968b607f6f80a7ad04ad402224ddd951a65e3ae8e18429ecfa17525614b'
MOVIE_BASE=0x8CEB0000
TABLE_OFFSET=0x8EA8
NAMES=('SLH448_1','SAH448_6','SA1_600','SA2_600','SA3_600','SA4_600','SA5_600','SA6_600','SA7_300','SA8_600')
FLAGS=(1,1,2,1,1,1,0,1,1,1)
FRAMES=(170,3180,2870,378,860,550,390,630,300,540)
MAX_SFD=128<<20
MAX_ADX=32<<20
MAX_ENCODED=128<<20
SETTINGS={'format':'DCRC_MOVIES_V1','raster':[480,272],'content':[60,0,360,272],
          'fps':[30000,1001],'profile':'main','level':'2.1','bitrate_kbps':1500,
          'audio':'adpcm_ima_wav','rate':44100,'channels':2,'block_bytes':2048}
X264=':'.join(('ref=1','bframes=0','weightp=0','cabac=1','8x8dct=0','slices=1','keyint=59','min-keyint=12',
    'aud=1','repeat-headers=1','nal-hrd=vbr','pic-struct=1','force-cfr=1','vbv-maxrate=3000','vbv-bufsize=1875',
    'colorprim=smpte170m','transfer=smpte170m','colormatrix=smpte170m','sar=1/1','threads=1','no-deblock=1'))
BITEXACT=['-fflags','+bitexact','-flags','+bitexact','-map_metadata','-1']

def _cancel(cancel):
    if cancel is not None and (cancel.is_set() if hasattr(cancel,'is_set') else cancel()):raise Cancelled()

def _digest(path,cancel=None):
    reject_links(path);digest=hashlib.sha256();count=0
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):
            _cancel(cancel);digest.update(block);count+=len(block)
    if count!=Path(path).stat().st_size:raise ConverterError('movies_changed','Movie input changed while reading.')
    return {'bytes':count,'sha256':digest.hexdigest()}

def _folder(source):
    root=plain_path(source)
    if not root.is_dir():raise ConverterError('movies_source','Choose the extracted movie directory.')
    candidates=[]
    for folder in (root,root/'SONICADV'):
        reject_links(folder)
        if not folder.is_dir():continue
        found=False
        for index,p in enumerate(folder.iterdir()):
            if index>=4096:raise ConverterError('movies_source','Movie directory exceeds the4096-entry bound.')
            if p.name.casefold()=='movie.bin':found=True
        if found:candidates.append(folder)
    if len(candidates)!=1:raise ConverterError('movies_source','Expected one unambiguous MOVIE.BIN directory.')
    return candidates[0]

def _selected(root):
    paths={}
    for index,p in enumerate(root.iterdir()):
        if index>=4096:raise ConverterError('movies_source','Movie directory exceeds the4096-entry bound.')
        reject_links(p)
        key=p.name.casefold()
        if key=='movie.bin' or key in {n.lower()+'.sfd' for n in NAMES}:
            if key in paths or not p.is_file():raise ConverterError('movies_source','Ambiguous or nonregular movie input.')
            paths[key]=p
    required=['movie.bin']+[n.lower()+'.sfd' for n in NAMES]
    if set(paths)!=set(required):raise ConverterError('movies_source','The supported MOVIE.BIN and all10 SFD files are required.')
    return paths

def inspect_movies(sourceFolder,*,cancel=None):
    """Input-only inspection: no encoder lookup/execution, no output writes."""
    root=_folder(sourceFolder);paths=_selected(root);inputs={}
    for key,path in paths.items():
        _cancel(cancel);size=path.stat().st_size
        limit=MOVIE_BIN_BYTES if key=='movie.bin' else MAX_SFD
        if not 0<size<=limit:raise ConverterError('movies_source','Movie input exceeds its supported size bound.')
        inputs[path.name]=_digest(path,cancel)
    digest=inputs[paths['movie.bin'].name]
    if digest!={'bytes':MOVIE_BIN_BYTES,'sha256':MOVIE_BIN_SHA256}:
        raise ConverterError('movies_version','MOVIE.BIN is not the supported US1.005 overlay.')
    data=paths['movie.bin'].read_bytes();entries=[]
    for index,name in enumerate(NAMES):
        pointer,flag,frames=struct.unpack_from('<III',data,TABLE_OFFSET+index*12)
        offset=pointer-MOVIE_BASE
        if not 0<=offset<len(data):raise ConverterError('movies_table','Movie name pointer is outside its overlay.')
        end=data.find(b'\0',offset,min(offset+64,len(data)))
        if end<0 or data[offset:end]!=(name+'.SFD').encode('ascii') or (flag,frames)!=(FLAGS[index],FRAMES[index]):
            raise ConverterError('movies_table','Movie table differs from the supported US1.005 mapping.')
        entries.append({'id':index,'name':name,'source':paths[name.lower()+'.sfd'].name,'flags':flag,'frames':frames})
    result={'format':'DCRC_MOVIES_INPUT_V1','inputs':dict(sorted(inputs.items())), 'movies':entries,'settings':dict(SETTINGS)}
    result['fingerprint']=fingerprint(result);return result

def resolve_tools(ffmpeg=None,*,cancel=None):
    """Explicit, own portable bundle, then PATH; hashes without executing tools."""
    if isinstance(ffmpeg,dict):
        given=ffmpeg
        if any(not isinstance(given.get(key),(str,os.PathLike)) for key in ('ffmpeg','ffprobe')):
            raise ConverterError('movies_tools','Invalid resolved movie tool paths.')
        paths={key:Path(given[key]).expanduser().resolve() for key in ('ffmpeg','ffprobe')}
    else:
        executable=find_tool('ffmpeg',ffmpeg)
        if not executable:raise ConverterError('movies_tools','FFmpeg is required when movies are enabled.','Select ffmpeg with libx264, or disable movies.')
        first=Path(executable).expanduser().resolve()
        sibling=first.with_name('ffprobe.exe' if first.suffix.lower()=='.exe' else 'ffprobe')
        probe=str(sibling) if sibling.is_file() else find_tool('ffprobe')
        if not probe:raise ConverterError('movies_tools','ffprobe was not found next to FFmpeg or on PATH.')
        paths={'ffmpeg':first,'ffprobe':Path(probe).resolve()}
    if any(not p.is_file() for p in paths.values()):raise ConverterError('movies_tools','The selected FFmpeg/ffprobe file does not exist.')
    result={**{key:str(p) for key,p in paths.items()},'identity':{key:_digest(p,cancel) for key,p in paths.items()}}
    if isinstance(ffmpeg,dict) and 'identity' in ffmpeg and result['identity']!=ffmpeg['identity']:
        raise ConverterError('movies_tools_changed','Movie tools changed after discovery.')
    return result

def video_filter():
    return 'scale=360:272:flags=lanczos,pad=480:272:60:0:black,setsar=1,fps=30000/1001,format=yuv420p'

def _exact(stream,n):
    data=stream.read(n)
    if len(data)!=n:raise ConverterError('movies_format','Truncated media packet.')
    return data

def demux_adx(source,target,cancel=None):
    """Bounded MPEG1/2 PES framing, C0 payload only; never executes source data."""
    written=0
    with Path(source).open('rb') as src,Path(target).open('xb') as dst:
        while True:
            _cancel(cancel);code=src.read(4)
            if not code:break
            skipped=0
            while len(code)==4 and code[:3]!=b'\0\0\1':
                code=code[1:]+src.read(1);skipped+=1
                if not skipped%4096:_cancel(cancel)
            if len(code)<4:break
            sid=code[3]
            if sid==0xB9:break
            if sid==0xBA:
                first=_exact(src,1)
                if first[0]&0xF0==0x20:_exact(src,7)
                elif first[0]&0xC0==0x40:
                    rest=_exact(src,9);_exact(src,rest[8]&7)
                else:raise ConverterError('movies_sfd','Unsupported SFD pack header.')
                continue
            if sid==0xBB or 0xBC<=sid<=0xFF:
                size=int.from_bytes(_exact(src,2),'big');payload=_exact(src,size)
                if sid!=0xC0:continue
                pos=0
                if payload and payload[0]&0xC0==0x80:
                    if len(payload)<3:raise ConverterError('movies_sfd','Truncated MPEG2 PES header.')
                    pos=3+payload[2]
                else:
                    while pos<len(payload) and payload[pos]==255:pos+=1
                    if pos<len(payload) and payload[pos]&0xC0==0x40:pos+=2
                    if pos>=len(payload):raise ConverterError('movies_sfd','Missing MPEG1 PES header.')
                    tag=payload[pos]&0xF0
                    if tag==0x20:pos+=5
                    elif tag==0x30:pos+=10
                    elif payload[pos]==0x0F:pos+=1
                    else:raise ConverterError('movies_sfd','Unsupported MPEG1 PES timestamp.')
                if pos>len(payload):raise ConverterError('movies_sfd','PES header exceeds packet.')
                body=payload[pos:];written+=len(body)
                if written>MAX_ADX:raise ConverterError('movies_sfd','ADX stream exceeds the supported bound.')
                if dst.write(body)!=len(body):raise OSError('Short ADX write')
    with Path(target).open('rb') as stream:header=stream.read(32)
    if len(header)<32 or header[:2]!=b'\x80\0':raise ConverterError('movies_audio','Supported movies require their ADX audio stream.')
    encoding,block,bits,channels=header[4:8];rate,samples=struct.unpack_from('>II',header,8)
    offset=int.from_bytes(header[2:4],'big')+4
    if (encoding,block,bits,channels,rate)!=(3,18,4,2,44100) or not samples or offset<20 or offset+math.ceil(samples/32)*36>written:
        raise ConverterError('movies_audio','Unsupported or truncated ADX audio stream.')
    return {'rate':rate,'channels':channels,'frames':samples,'bytes':written}

def wav_info(path):
    """Require whole IMA blocks; the fact count trims their final padding."""
    size=Path(path).stat().st_size;fmt=None;frames=None;data_bytes=None
    if not 0<size<=2*MAX_ADX:raise ConverterError('movies_wav','WAV exceeds the supported size bound.')
    with Path(path).open('rb') as stream:
        header=_exact(stream,12)
        if header[:4]!=b'RIFF' or header[8:]!=b'WAVE' or int.from_bytes(header[4:8],'little')+8!=size:
            raise ConverterError('movies_wav','Invalid RIFF length or WAV header.')
        while stream.tell()+8<=size:
            tag,length=struct.unpack('<4sI',_exact(stream,8));end=stream.tell()+length
            if end>size:raise ConverterError('movies_wav','WAV chunk exceeds file.')
            if tag==b'fmt ':
                if fmt is not None or not 20<=length<=256:raise ConverterError('movies_wav','Invalid WAV format chunk.')
                fmt=struct.unpack_from('<HHIIHHHH',_exact(stream,length))
            elif tag==b'fact':
                if frames is not None or length<4:raise ConverterError('movies_wav','Invalid WAV sample count.')
                frames=int.from_bytes(_exact(stream,4),'little')
            elif tag==b'data':
                if data_bytes is not None:raise ConverterError('movies_wav','Duplicate WAV data chunk.')
                data_bytes=length
            stream.seek(end+(length&1))
    tail=(data_bytes or 0)%2048
    capacity=(data_bytes or 0)//2048*2041
    if not fmt or (fmt[0],fmt[1],fmt[2],fmt[4],fmt[5],fmt[6],fmt[7])!=(17,2,44100,2048,4,2,2041) or not frames or not data_bytes or tail or frames>capacity:
        raise ConverterError('movies_wav','Expected stereo44100 IMA WAV with whole2048-byte blocks and sample count.')
    return {'rate':44100,'channels':2,'frames':frames,'data_bytes':data_bytes,'block_bytes':2048}

def _json(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())

def _read_json(path):
    reject_links(path)
    if not Path(path).is_file() or Path(path).stat().st_size>4<<20:raise ConverterError('movies_probe','Missing or oversized tool report.')
    try:result=json.loads(Path(path).read_text(encoding='utf8'))
    except (ValueError,UnicodeError) as error:raise ConverterError('movies_probe','Invalid JSON tool report.') from error
    if not isinstance(result,dict):raise ConverterError('movies_probe','Expected an object in the tool report.')
    return result

def _command_log_mark(runner):
    """Remember an exact byte boundary, not a search over older commands."""
    raw=getattr(runner,'log_path',None)
    if raw is None:return None # Minimal custom runners can supply the report.
    path=plain_path(raw)
    if not path.exists():return path,0,None
    if not path.is_file():raise ConverterError('movies_probe','Command log is not a regular file.')
    stat=path.stat();return path,stat.st_size,(stat.st_dev,stat.st_ino)

def _ffmpeg_version(mark,report):
    if mark is None:
        path=plain_path(report)
        if not path.is_file() or path.stat().st_size>4<<20:raise ConverterError('movies_probe','Missing or oversized FFmpeg version report.')
        with path.open('rb') as stream:data=stream.read((4<<20)+1)
        if len(data)>4<<20:raise ConverterError('movies_probe','FFmpeg report exceeds its read bound.')
        text=data.decode('utf8',errors='replace')
    else:
        path,start,identity=mark;path=plain_path(path)
        if not path.is_file():raise ConverterError('movies_probe','Command log disappeared during the version probe.')
        stat=path.stat();length=stat.st_size-start
        if not 0<=length<=4<<20 or (identity is not None and identity!=(stat.st_dev,stat.st_ino)):
            raise ConverterError('movies_probe','Command log changed or version output exceeds its bound.')
        with path.open('rb') as stream:
            opened=os.fstat(stream.fileno())
            if (opened.st_dev,opened.st_ino)!=(stat.st_dev,stat.st_ino) or opened.st_size<start+length:
                raise ConverterError('movies_probe','Command log was replaced or truncated before reading.')
            stream.seek(start);data=stream.read(length)
        if len(data)!=length:raise ConverterError('movies_probe','Command log was truncated during the version probe.')
        text=data.decode('utf8',errors='replace')
    versions=re.findall(r'(?m)^ffmpeg version ([^\r\n]{1,200})\r?$',text)
    if len(versions)!=1:raise ConverterError('movies_probe','Expected one FFmpeg version banner from this command.')
    return versions[0]

def stage_movies(sourceFolder,outFolder,ffmpeg,runner,event=None,cancel=None,*,expected_fingerprint=None,expected_tool_identity=None):
    """New isolated stage only. Return data_root/manifest plus portable receipts.
    Cache caller binds input fingerprint, tool identity and implementation hash.
    Partial outputs remain unclaimed on any error/cancellation; no input writes.
    """
    argument=plain_path(sourceFolder);source=_folder(argument);out=plain_path(outFolder)
    if argument.is_relative_to(out) or out.is_relative_to(argument):raise ConverterError('movies_path','Movie input and output must not overlap.')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):raise ConverterError('movies_output','Choose a new empty movie staging folder.')
    inspection=inspect_movies(source,cancel=cancel)
    if expected_fingerprint is not None and inspection['fingerprint']!=expected_fingerprint:raise ConverterError('movies_changed','Movie input changed after its stage key was computed.')
    tools=resolve_tools(ffmpeg,cancel=cancel)
    if expected_tool_identity is not None and tools['identity']!=expected_tool_identity:raise ConverterError('movies_tools_changed','Movie encoder changed after its stage key was computed.')
    _cancel(cancel);out.mkdir(parents=True,exist_ok=True)
    work=out/'work';work.mkdir();data=out/'data';data.mkdir();target=data/'MOVIE';target.mkdir()
    paths=_selected(source);frozen={}
    for key,path in paths.items():
        destination=work/path.name;digest=hashlib.sha256();count=0
        with path.open('rb') as src,destination.open('xb') as dst:
            for block in iter(lambda:src.read(1<<20),b''):
                _cancel(cancel);digest.update(block);count+=len(block)
                if dst.write(block)!=len(block):raise OSError('Short frozen movie copy')
        if {'bytes':count,'sha256':digest.hexdigest()}!=inspection['inputs'][path.name]:raise ConverterError('movies_changed','Movie input changed during its frozen copy.')
        if _digest(destination,cancel)!=inspection['inputs'][path.name]:raise ConverterError('movies_changed','Frozen movie copy failed SHA256/size readback.')
        frozen[key]=destination
    def frozen_unchanged(path):
        if _digest(path,cancel)!=inspection['inputs'][path.name]:
            raise ConverterError('movies_changed','Frozen movie input changed during conversion.')
    def run(argv,label,env=None):
        _cancel(cancel);runner.run([str(a) for a in argv],cwd=work,env=env,label=label);_cancel(cancel)
    env=dict(os.environ);env['FFREPORT']='file=ffmpeg-version.log:level=32'
    version_mark=_command_log_mark(runner)
    run([tools['ffmpeg'],'-report','-version'],'Movie encoder version',env)
    encoder_version=_ffmpeg_version(version_mark,work/'ffmpeg-version.log')
    run([tools['ffprobe'],'-v','error','-show_program_version','-of','json','-o',work/'ffprobe-version.json'],'Movie probe version')
    program=_read_json(work/'ffprobe-version.json').get('program_version')
    if not isinstance(program,dict) or not isinstance(program.get('version'),str) or not 0<len(program['version'])<=200:
        raise ConverterError('movies_probe','ffprobe did not provide a bounded version string.')
    versions={'ffmpeg':encoder_version,'ffprobe':program['version']}
    movies=[];files={}
    for index,entry in enumerate(inspection['movies']):
        name=entry['name'];sfd=frozen[entry['source'].casefold()];es=work/(name+'.264');adx=work/(name+'.adx')
        if event:event({'type':'progress','stage':'movies','progress':index/10,'message':'Converting '+name})
        frozen_unchanged(sfd);audio=demux_adx(sfd,adx,cancel);frozen_unchanged(sfd)
        run([tools['ffmpeg'],'-v','error','-n','-nostdin','-i',sfd,'-map','0:v:0','-an','-vf',video_filter(),
             '-c:v','libx264','-profile:v','main','-level:v','2.1','-preset','medium','-b:v','1500k','-x264-params',X264,*BITEXACT,'-f','h264',es],'Encode movie '+name)
        if not 0<es.stat().st_size<=MAX_ENCODED:raise ConverterError('movies_video','Encoded movie exceeds its supported bound.')
        pmf=target/(name+'.pmf')
        try:
            encoded=es.read_bytes();sps=pmfinfo.parameter_sets(pmfmux.split_nals(encoded))
            if (sps['profile'],sps['level'],sps['width'],sps['height'],sps['ref_frames'])!=(77,21,480,272,1):
                raise ConverterError('movies_video','Encoder did not create the required Main2.1 PSP raster.')
            stats=pmfmux.write_checked(encoded,pmf)
        except (pmfmux.MuxError,ValueError,struct.error,IndexError) as error:
            raise ConverterError('movies_mux','Encoded video does not satisfy the PMF contract.',str(error)) from error
        wav=target/(name+'.wav')
        run([tools['ffmpeg'],'-v','error','-n','-nostdin','-f','adx','-i',adx,'-map','0:a:0','-vn','-af',
             'aresample=44100,asetnsamples=n=2041:p=0','-ac','2','-ar','44100','-c:a','adpcm_ima_wav','-block_size','2048',*BITEXACT,wav],'Encode movie audio '+name)
        sound=wav_info(wav)
        if abs(sound['frames']-audio['frames'])>2041:raise ConverterError('movies_audio','Converted audio sample count differs by more than one IMA block.')
        run([tools['ffmpeg'],'-v','error','-xerror','-nostdin','-i',pmf,'-map','0:v:0','-an','-f','null','-'],'Check movie decode '+name)
        check=work/(name+'_probe.json')
        run([tools['ffprobe'],'-v','error','-select_streams','v:0','-count_frames','-show_entries',
             'stream=codec_name,profile,level,width,height,nb_read_frames','-of','json','-o',check,pmf],'Count movie pictures '+name)
        streams=_read_json(check).get('streams',[])
        valid=isinstance(streams,list) and len(streams)==1 and isinstance(streams[0],dict)
        try:count=int(streams[0].get('nb_read_frames',-1)) if valid else -1
        except (TypeError,ValueError):count=-1
        if not valid or streams[0].get('codec_name')!='h264' or count!=stats['access_units']:
            raise ConverterError('movies_verify','Decoded picture count differs from muxed access units.')
        for artifact in (pmf,wav):files['MOVIE/'+artifact.name]=_digest(artifact,cancel)
        movies.append({**entry,'video':{k:stats[k] for k in ('access_units','packs','seconds','max_au')},'audio':sound})
    for path in frozen.values():frozen_unchanged(path)
    if inspect_movies(source,cancel=cancel)!=inspection:raise ConverterError('movies_changed','Movie source changed during conversion.')
    if resolve_tools(tools,cancel=cancel)['identity']!=tools['identity']:raise ConverterError('movies_tools_changed','Movie tools changed during conversion.')
    portable={'format':'DCRC_MOVIES_V1','fingerprint':inspection['fingerprint'],'inputs':inspection['inputs'],
              'tool_identity':tools['identity'],'tool_versions':versions,'settings':dict(SETTINGS),'movies':movies,'files':files}
    _cancel(cancel);_json(data/'MOVIE'/'movies.json',portable)
    files['MOVIE/movies.json']=_digest(data/'MOVIE'/'movies.json',cancel)
    manifest=out/'movies_report.json';_json(manifest,{**portable,'files':files})
    if event:event({'type':'progress','stage':'movies','progress':1.0,'message':'All10 movies verified'})
    return {'data_root':str(data),'manifest':str(manifest),'fingerprint':inspection['fingerprint'],
            'tool_identity':tools['identity'],'files':files,'movies':movies}
