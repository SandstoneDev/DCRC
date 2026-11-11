"""Shared GUI/CLI conversion pipeline. Every game-derived byte is made locally."""
from dataclasses import dataclass,asdict
from pathlib import Path
import hashlib,json,os,shutil,struct,sys,threading,time,uuid
from . import __version__
from .errors import ConverterError,Cancelled
from .models import ConversionOptions
from .media_tools import find_tool
from .storage import StageCache,file_digest,fingerprint,tree_files,write_json,read_json,checked_path
from .process import CommandRunner
from .runtime_source import runtime_root,source_files,snapshot
from .package import claim_output,write_manifest,verify_folder,configure_folder,runtime_text,MANIFEST,OWNER,MUTABLE,RUNTIME_KEYS

@dataclass
class ConversionResult:
    folder: Path
    manifest: Path
    work: Path
    elapsed: float
    cache_hits: tuple

def identify(source,event=None,cancel_event=None):
    try:
        from .disc import inspect_source
        result=inspect_source(Path(source),progress=event,cancel=cancel_event)
        return dict(result,ok=True,message='Supported Sonic Adventure USA V1.005')
    except Cancelled:raise
    except ConverterError as e:return {'ok':False,'code':e.code,'message':e.message,'hint':e.hint}

def _copy(src,dst,expected):
    src,dst=Path(src),Path(dst)
    if dst.is_file() and file_digest(dst)==expected:return
    dst.parent.mkdir(parents=True,exist_ok=True)
    temporary=dst.with_name(dst.name+'.dcrc-'+uuid.uuid4().hex+'.tmp')
    with src.open('rb') as f,temporary.open('xb') as out:
        shutil.copyfileobj(f,out,4<<20);out.flush();os.fsync(out.fileno())
    if file_digest(temporary)!=expected:raise ConverterError('write_readback',f'Output write failed verification: {dst}')
    os.replace(temporary,dst)
    if file_digest(dst)!=expected:raise ConverterError('write_readback',f'Final output differs after write: {dst}')

def _write_text(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.dcrc-'+uuid.uuid4().hex+'.tmp')
    with temporary.open('x',encoding='utf-8',newline='\n') as f:f.write(text);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)

def _write_binary(path,content):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.dcrc-'+uuid.uuid4().hex+'.tmp')
    with temporary.open('xb') as f:f.write(content);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)

def _movie_sources(output,movies=None):
    """Check ownership before any package write; never adopt changed old media."""
    from .package import _manifest
    output=Path(output);folder=checked_path(output,'data/MOVIE')
    previous=_manifest(output)['files'] if (output/MANIFEST).is_file() else {}
    desired=movies['files'] if movies else {}
    sources={}
    if folder.exists() and not folder.is_dir():
        if movies:raise ConverterError('foreign_content','Existing MOVIE path is not a directory; it has been preserved.')
        return sources
    for rel,actual in tree_files(folder).items() if folder.is_dir() else ():
        name='data/MOVIE/'+rel;owned=previous.get(name)
        expected={k:owned[k] for k in ('bytes','sha256')} if owned else None
        requested=desired.get('MOVIE/'+rel)
        if movies:
            if actual!=requested and actual!=expected:
                raise ConverterError('foreign_content','Existing movies are unowned or modified; they have been preserved. Choose a new output folder.')
            # A cancelled package may already contain the exact requested bytes.
            # Unknown extras cannot become an unmanaged playback source.
            if requested is None and expected is None:
                raise ConverterError('foreign_content','Unmanaged movie content has been preserved. Choose a new output folder.')
        if expected==actual and requested is None:sources[name]=checked_path(output,name)
    if movies:
        data=Path(movies['data_root'])
        for rel in desired:sources['data/'+rel]=checked_path(data,rel)
    return sources

def convert(options,event=None,cancel_event=None,*,log_path=None):
    if isinstance(options,dict):options=ConversionOptions(**options)
    if not isinstance(options,ConversionOptions):raise ConverterError('options','Expected ConversionOptions.')
    o=options.validate();start=time.monotonic();stop=cancel_event or threading.Event();callback=event or (lambda v:None);hits=[]
    border_blob=None
    retained_border=None
    existing_border=checked_path(o.output,'border.bin')
    if o.border_mode=='custom':
        from .border import encode_border
        border_blob=encode_border(o.border_image)
    if existing_border.exists():
        if not existing_border.is_file():
            raise ConverterError('foreign_content','The existing border path is not a file. Choose a new output folder.')
        actual=file_digest(existing_border)
        requested=None if border_blob is None else {
            'bytes':len(border_blob),'sha256':hashlib.sha256(border_blob).hexdigest()}
        if actual!=requested:
            from .package import _manifest
            previous=_manifest(o.output)['files'] if (o.output/MANIFEST).is_file() else {}
            owned=previous.get('border.bin')
            if not owned or actual!={k:owned[k] for k in ('bytes','sha256')}:
                raise ConverterError('foreign_content','Existing border is unowned or modified; choose a new output folder.')
        if border_blob is None:
            retained_border=actual
    def emit(value):
        if value.get('state')=='cached':hits.append(value['stage'])
        callback(value)
    def check():
        if stop.is_set():raise Cancelled()
    def stage(message):check();emit({'type':'stage','stage':message,'state':'running','message':message})
    from .disc import inspect_source
    from .profiles import load_profile,PROFILE_DIR
    from .toolchain import resolve
    from .native_build import build,make_pbp
    source=runtime_root()
    for protected in (source,Path(__file__).resolve().parents[1]):
        for target in (o.output,o.work):
            if target.is_relative_to(protected):
                rel=target.relative_to(protected)
                if not rel.parts or rel.parts[0] not in ('work','build','private','out'):
                    raise ConverterError('unsafe_output','Game-derived output/work must stay outside the maintained application source.')
    stage('identify')
    identity=inspect_source(o.source,progress=emit,cancel=stop);check()
    movie_tools=None
    if o.movies:
        from .movies import resolve_tools
        movie_tools=resolve_tools(o.ffmpeg,cancel=stop)
    tc=resolve(o.toolchain)
    records=source_files(source);runtime_fp=fingerprint(records)
    profile_fp=fingerprint(tree_files(PROFILE_DIR));toolchain_fp=tc.fingerprint();check()
    emit({'type': 'log', 'message': f'DCRC {__version__} runtime {runtime_fp}, profile {profile_fp}'})
    emit({'type': 'log', 'message': f'Work folder: {o.work}'})
    cache=StageCache(o.work,emit)
    log=Path(log_path) if log_path else o.work/'logs'/('conversion_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]+'.log')
    runner=CommandRunner(log,event=emit,cancel_event=stop)
    worker=Path(__file__).with_name('worker.py')
    engine={p.name:file_digest(p) for p in (Path(__file__).with_name('native_build.py'),Path(__file__).with_name('toolchain.py'),Path(__file__).with_name('worker.py'))}
    snapshot_result=cache.run('source',runtime_fp,lambda run:snapshot(source,run/'source'))
    frozen=Path(snapshot_result['source_root'])
    def data_stage(name,args):
        def run(out):
            report=out/'RESULT.json'
            runner.run([sys.executable,'-B',worker,name,*args(out),'--report',report],cwd=source,label=name)
            check();return read_json(report)
        return run
    extract_impl={name:file_digest(Path(__file__).with_name(name)) for name in ('disc.py','profiles.py','worker.py')}
    extraction=cache.run('extract',{'input':identity['fingerprint'],'implementation':extract_impl,'profile':profile_fp},
        data_stage('extract',lambda out:['--source',o.source,'--out',out/'data']))
    data=Path(extraction['data_root'])
    presentation=None
    def check_xmb_inputs():check()
    if any(getattr(o,'xmb_'+kind+'_mode')!='none' for kind in ('icon','background','music')):
        # Appearance is an independent local stage: never changes generated game C.
        from .xmb import prepare_xmb,resolve_encoder
        import PIL
        selection={k:v for k,v in o.to_dict().items() if k.startswith('xmb_')}
        custom_inputs={}
        for kind in ('icon','background','music'):
            if selection['xmb_'+kind+'_mode']=='file':
                p=getattr(o,'xmb_'+kind+'_file');custom_inputs[kind]=file_digest(p)
        xmb_tools={}
        ready_at3=o.xmb_music_mode=='file' and o.xmb_music_file.suffix.lower()=='.at3'
        if o.xmb_music_mode!='none' and not ready_at3:
            encoder=resolve_encoder(o.xmb_encoder);selection['xmb_encoder']=str(encoder)
            from .media_tools import find_tool
            ff=find_tool('ffmpeg',o.ffmpeg)
            if ff is None or not ff.is_file():raise ConverterError('xmb_tool','Choose FFmpeg to decode the selected XMB music.')
            xmb_tools={'encoder':file_digest(encoder),'ffmpeg':file_digest(ff)}
        def check_xmb_inputs():
            check()
            for kind,expected in custom_inputs.items():
                if file_digest(getattr(o,'xmb_'+kind+'_file'))!=expected:
                    raise ConverterError('xmb_changed','An XMB input changed during conversion; the output was not adopted.')
            if xmb_tools and (file_digest(encoder)!=xmb_tools['encoder'] or file_digest(ff)!=xmb_tools['ffmpeg']):
                raise ConverterError('xmb_tool_changed','An XMB encoder changed during conversion.')
        def xmb_stage(out):
            frozen_selection=dict(selection)
            for kind,expected in custom_inputs.items():
                original=getattr(o,'xmb_'+kind+'_file')
                target=out/'inputs'/(kind+original.suffix.lower())
                _copy(original,target,expected) # Consume only bytes verified against the cache key.
                frozen_selection['xmb_'+kind+'_file']=target
            prepared=prepare_xmb(data,out/'media',frozen_selection,ffmpeg=ff if xmb_tools else o.ffmpeg,event=emit,cancel=stop)
            for kind,expected in custom_inputs.items():
                slot={'icon':'icon0','background':'pic1','music':'snd0'}[kind]
                if prepared.get('inputs',{}).get(slot,{}).get('input')!=expected:
                    raise ConverterError('xmb_changed','XMB conversion consumed different bytes from its verified input.')
            result={k:str(v) if isinstance(v,Path) else v for k,v in prepared.items()}
            result['artifacts']={k:str(prepared[k])for k in ('icon0','pic1','snd0')if prepared.get(k)}
            result['manifest']=str(out/'XMB_MANIFEST.json')
            write_json(out/'XMB_MANIFEST.json',{'fingerprint':prepared['fingerprint'],'files':prepared['files']})
            return result
        presentation=cache.run('xmb',{'input':identity['fingerprint'],'selection':selection,'custom':custom_inputs,
            'tools':xmb_tools,'pillow':PIL.__version__,'implementation':{name:file_digest(Path(__file__).with_name(name)) for name in ('xmb.py','media.py','media_tools.py')},
            'prs':records.get('tools/prs.py')},xmb_stage)
        check_xmb_inputs()
        for slot,name in (('icon0','ICON0.PNG'),('pic1','PIC1.PNG'),('snd0','SND0.AT3')):
            if presentation.get(slot):
                p=Path(presentation[slot]);owned=Path(presentation['manifest']).parent
                if (presentation['artifacts'].get(slot)!=str(p) or not p.resolve().is_relative_to(owned.resolve())
                        or file_digest(p)!=presentation['files'][name]):
                    raise ConverterError('xmb_changed','Cached XMB media changed after verification.')
    movies=None
    if o.movies:
        from .movies import inspect_movies,stage_movies,NAMES
        movie_input=inspect_movies(data,cancel=stop)
        movie_impl={'stage':file_digest(Path(__file__).with_name('movies.py')),
            **{name:file_digest(source/'tools'/name) for name in ('movie_pmfmux.py','movie_pmfinfo.py')}}
        movies=cache.run('movies',{'input':movie_input['fingerprint'],'tools':movie_tools['identity'],'implementation':movie_impl},
            lambda out:stage_movies(data,out,movie_tools,runner,event=emit,cancel=stop,
                expected_fingerprint=movie_input['fingerprint'],expected_tool_identity=movie_tools['identity']))
        expected_names={f'MOVIE/{name}.{ext}' for name in NAMES for ext in ('pmf','wav')}|{'MOVIE/movies.json'}
        if (movies.get('fingerprint')!=movie_input['fingerprint'] or movies.get('tool_identity')!=movie_tools['identity']
                or set(movies.get('files',{}))!=expected_names or tree_files(Path(movies['data_root']))!=movies['files']):
            raise ConverterError('movies_changed','Cached movies differ from the selected source, encoder or verified output.')
    # Run before costly generation/build as well as before any package mutation.
    movie_sources=_movie_sources(o.output,movies)
    emitter_fp=fingerprint({k:v for k,v in records.items() if k.startswith(('recomp/emitter/','recomp/sa1_us_1005/'))})
    generate_impl={name:file_digest(Path(__file__).with_name(name)) for name in ('generate.py','profiles.py','worker.py')}
    generation=cache.run('generate',{'input':identity['fingerprint'],'emitter':emitter_fp,'profile':profile_fp,'implementation':generate_impl},
        data_stage('generate',lambda out:['--source',frozen,'--data',data,'--out',out/'generated','--jobs',str(o.jobs)]))
    check()
    compiled=cache.run('build',{'generated':generation['fingerprint'],'runtime':runtime_fp,'toolchain':toolchain_fp,'engine':engine},
        lambda out:build(frozen,Path(generation['generated']),out/'build',tc,runner,jobs=o.jobs,title='DCRC Port'))
    asset_code=fingerprint({k:v for k,v in records.items() if k.startswith('tools/')})
    asset_impl={name:file_digest(Path(__file__).with_name(name)) for name in ('worker.py','profiles.py')}
    converted=cache.run('assets',{'input':identity['fingerprint'],'tools':asset_code,'world_textures':o.world_textures,'profile':profile_fp,'implementation':asset_impl},
        data_stage('assets',lambda out:['--source',frozen,'--data',data,'--out',out/'payload','--world',str(o.world_textures)]))
    content=None
    if o.dlc_dir:
        from .capabilities import DLC_NOTICE
        emit({'type':'log','message':DLC_NOTICE})
        from .content import inspect_content,stage_content
        content_input=inspect_content(o.dlc_dir)
        content=cache.run('content',{'input':content_input['fingerprint'],
            'implementation':file_digest(Path(__file__).with_name('content.py'))},
            lambda out:dict(stage_content(o.dlc_dir,out/'data',
                expected_fingerprint=content_input['fingerprint']),payload_root=str(out)))
        if content.get('fingerprint')!=content_input['fingerprint']:
            raise ConverterError('content_changed','Cached DLC content differs from the selected input.')
        for skipped in content.get('skipped',[]):
            emit({'type':'log','stage':'content','message':'DLC skipped: '+str(skipped.get('reason','unsupported'))})
    retained_content={}
    if content and (o.output/'data/dlc').exists():
        from .package import _manifest
        previous=_manifest(o.output)['files'] if (o.output/MANIFEST).is_file() else {}
        for rel in tree_files(o.output/'data/dlc'):
            if 'data/dlc/'+rel not in previous:
                raise ConverterError('foreign_content','Existing DLC files are not owned by this package; choose a new output folder.')
            name='data/dlc/'+rel
            if 'dlc/'+rel not in content['files']:
                expected={key:previous[name][key] for key in ('bytes','sha256')}
                if file_digest(o.output/name)!=expected:
                    raise ConverterError('foreign_content','An obsolete DLC file was modified; it has been preserved.')
                retained_content[name]=o.output/name
    if movies and tree_files(Path(movies['data_root']))!=movies['files']:
        raise ConverterError('movies_changed','Verified movie output changed before packaging.')
    movie_sources=_movie_sources(o.output,movies)
    if retained_border is not None:
        existing_border=checked_path(o.output,'border.bin')
        if not existing_border.is_file() or file_digest(existing_border)!=retained_border:
            raise ConverterError('foreign_content','The existing border changed during conversion. It has been preserved.')
        emit({'type':'message','stage':'package','message':'Reusing the verified existing 4:3 border.'})
    check_xmb_inputs();stage('package');claim_output(o.output,o.profile)
    payload=Path(converted['payload_root']);sources=dict(movie_sources)
    if border_blob is not None:
        border_path=checked_path(o.work,'borders/'+hashlib.sha256(border_blob).hexdigest()+'.bin')
        _write_binary(border_path,border_blob);sources['border.bin']=border_path
    for rel in converted['files']:
        sources['data/'+rel]=payload/'data'/rel
    if content:
        for rel in content['files']:
            sources['data/'+rel]=Path(content['payload_root'])/'data'/rel
        sources.update(retained_content)
    for name in ('EBOOT.PBP','sa1exc.prx','sa1prof.prx','sa1me.prx','sa1chain.prx'):
        p=Path(compiled['artifacts'][name])
        if not p.is_file():raise ConverterError('build_artifact',f'Missing real game artifact: {name}')
        sources[name]=p
    if presentation is not None:
        # Repack media/title only; retain DATA.PSP byte-for-byte.
        pbp=Path(sources['EBOOT.PBP']).read_bytes();offsets=list(struct.unpack_from('<8I',pbp,8))
        renamed=checked_path(o.work,'presentation/'+fingerprint({'data':file_digest(sources['EBOOT.PBP']),
            'title':o.title,'xmb':presentation['fingerprint']})+'.PBP')
        media={}
        for slot in ('icon0','pic1','snd0'):
            if not presentation.get(slot):media[slot]=b'';continue
            expected_media=presentation['files'][{'icon0':'ICON0.PNG','pic1':'PIC1.PNG','snd0':'SND0.AT3'}[slot]]
            with Path(presentation[slot]).open('rb') as f:raw=f.read(expected_media['bytes']+1)
            if {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}!=expected_media:
                raise ConverterError('xmb_changed','XMB media changed before PBP packaging.')
            media[slot]=raw
        _write_binary(renamed,make_pbp(pbp[offsets[6]:offsets[7]],o.title,media['icon0'],pic1=media['pic1'],snd0=media['snd0']))
        sources['EBOOT.PBP']=renamed
    elif o.title!='DCRC Port':
        pbp=Path(sources['EBOOT.PBP']).read_bytes();offsets=list(struct.unpack_from('<8I',pbp,8))
        renamed=checked_path(o.work,'titles/'+fingerprint({'data':file_digest(sources['EBOOT.PBP']),'title':o.title})+'.PBP')
        _write_binary(renamed,make_pbp(pbp[offsets[6]:offsets[7]],o.title,pbp[offsets[1]:offsets[2]]))
        sources['EBOOT.PBP']=renamed
    sources['LICENSE.txt']=frozen/'LICENSE'
    from .runtime_source import NOTICES
    for notice in NOTICES:
        sources[notice]=frozen/notice
    expected={'border.bin':retained_border} if retained_border is not None else {}
    for n,(rel,src) in enumerate(sorted(sources.items())):
        check();expected[rel]=file_digest(src);_copy(src,checked_path(o.output,rel),expected[rel])
        emit({'type':'progress','stage':'package','progress':(n+1)/len(sources),'message':rel})
    args,ini=runtime_text(o)
    old_ini=checked_path(o.output,'data/sa1psp.ini')
    if old_ini.is_file():
        known={'voice','audio','renderer','land_cull','event_skip','math','aspect','frame_skip',
               'gu_max_mip','mip_levels','fps_hud','debug_menu','start_stage','start_character','start_act','movies','dither'}
        extra=[line for line in old_ini.read_text(encoding='utf-8-sig').splitlines() if '=' in line and line.split('=',1)[0].strip() not in known and not line.split('=',1)[0].strip().startswith('control_')]
        if extra:ini+='\n# Additional player settings\n'+'\n'.join(extra)+'\n'
    _write_text(checked_path(o.output,'args.txt'),args)
    _write_text(checked_path(o.output,'data/sa1psp.ini'),ini)
    write_json(checked_path(o.output,'dcrc_settings.json'),{k:getattr(o,k) for k in RUNTIME_KEYS})
    _write_text(checked_path(o.output,'LOCAL_BUILD.txt'),
        'DCRC local conversion\nThis folder contains material generated locally from your own supported disc.\n'
        'Keep it for your own use; do not share this PSP folder or generated game code/assets.\n'
        'Copy this entire folder to PSP/GAME on a PSP that runs homebrew.\n'
        'Supported hardware: PSP-2000/3000-class64MB; real PSP speed/quality still require testing.\n')
    for rel in ('args.txt','data/sa1psp.ini','dcrc_settings.json','LOCAL_BUILD.txt'):expected[rel]=file_digest(checked_path(o.output,rel))
    metadata={'profile':o.profile,'converter_version':__version__,'options':o.to_dict(),
        'input':{'fingerprint':identity['fingerprint'],'boot':identity['boot'],'version':identity.get('version')},
        'fingerprints':{'runtime':runtime_fp,'profile':profile_fp,'toolchain':toolchain_fp,'generated':generation['fingerprint']},
        'build_validation':compiled['validation'],'movies':{'enabled':o.movies,'input_fingerprint':movies['fingerprint'] if movies else None},'quality':{'world_textures':o.world_textures,'scope':'selected Emerald Coast world assets only','land_distance':o.land_distance},
        'content':None if content is None else {'count':len(content.get('entries',[])),'input_fingerprint':content['fingerprint'],'opaque_only':True,'guest_decoder_included':False,'gameplay_verified':False},
        'game_derived_output':True,'processing':'local-only','hardware_acceptance':'not established by conversion'}
    check();write_manifest(o.output,metadata,owned=expected)
    stage('verify');result=verify_folder(o.output)
    if not result['ok']:raise ConverterError('write_readback','The PSP folder failed final full SHA256 verification.',str(result['problems']))
    check();emit({'type':'stage','stage':'complete','state':'done','message':f'Converted folder verified: {o.output}','progress':1.0})
    return ConversionResult(o.output,o.output/MANIFEST,o.work,time.monotonic()-start,tuple(hits))

def repair_folder(folder,source=None,toolchain=None,event=None,cancel_event=None):
    from .package import _manifest
    folder=Path(folder);m=_manifest(folder)
    values=dict(m.get('options',{}));values.update(output=folder)
    if source is not None:values['source']=source
    if toolchain is not None:values['toolchain']=toolchain
    preserved={rel:checked_path(folder,rel).read_bytes() for rel in MUTABLE if checked_path(folder,rel).is_file()}
    try:
        result=convert(ConversionOptions(**values),event=event,cancel_event=cancel_event)
    finally:
        for rel,content in preserved.items():_write_binary(checked_path(folder,rel),content)
    return result
