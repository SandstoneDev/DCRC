"""Shared GUI/CLI conversion pipeline. Every game-derived byte is made locally."""
from dataclasses import dataclass,asdict
from pathlib import Path
import json,os,shutil,struct,sys,threading,time,uuid
from . import __version__
from .errors import ConverterError,Cancelled
from .models import ConversionOptions
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

def convert(options,event=None,cancel_event=None):
    if isinstance(options,dict):options=ConversionOptions(**options)
    if not isinstance(options,ConversionOptions):raise ConverterError('options','Expected ConversionOptions.')
    o=options.validate();start=time.monotonic();stop=cancel_event or threading.Event();callback=event or (lambda v:None);hits=[]
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
    tc=resolve(o.toolchain)
    records=source_files(source);runtime_fp=fingerprint(records)
    profile_fp=fingerprint(tree_files(PROFILE_DIR));toolchain_fp=tc.fingerprint();check()
    cache=StageCache(o.work,emit)
    log=o.work/'logs'/('conversion_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]+'.log')
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
    check();stage('package');claim_output(o.output,o.profile)
    payload=Path(converted['payload_root']);sources={}
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
    # Title is packaging-only: no C regeneration or recompilation is required.
    if o.title!='DCRC Port':
        pbp=Path(sources['EBOOT.PBP']).read_bytes();offsets=list(struct.unpack_from('<8I',pbp,8))
        renamed=checked_path(o.work,'titles/'+fingerprint({'data':file_digest(sources['EBOOT.PBP']),'title':o.title})+'.PBP')
        _write_binary(renamed,make_pbp(pbp[offsets[6]:offsets[7]],o.title,pbp[offsets[1]:offsets[2]]))
        sources['EBOOT.PBP']=renamed
    sources['LICENSE.txt']=frozen/'LICENSE'
    from .runtime_source import NOTICES
    for notice in NOTICES:
        sources[notice]=frozen/notice
    expected={}
    for n,(rel,src) in enumerate(sorted(sources.items())):
        check();expected[rel]=file_digest(src);_copy(src,checked_path(o.output,rel),expected[rel])
        emit({'type':'progress','stage':'package','progress':(n+1)/len(sources),'message':rel})
    args,ini=runtime_text(o)
    old_ini=checked_path(o.output,'data/sa1psp.ini')
    if old_ini.is_file():
        known={'voice','audio','renderer','land_cull','event_skip','math','aspect','frame_skip',
               'gu_max_mip','mip_levels','fps_hud','debug_menu','start_stage','start_character','start_act'}
        extra=[line for line in old_ini.read_text(encoding='utf-8-sig').splitlines() if '=' in line and line.split('=',1)[0].strip() not in known]
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
        'build_validation':compiled['validation'],'quality':{'world_textures':o.world_textures,'scope':'selected Emerald Coast world assets only','land_distance':o.land_distance},
        'game_derived_output':True,'processing':'local-only','hardware_acceptance':'not established by conversion'}
    check();m=write_manifest(o.output,metadata,owned=expected)
    for rel,e in expected.items():
        if {k:m['files'][rel][k] for k in ('bytes','sha256')}!=e:raise ConverterError('write_readback',f'Payload changed during manifest creation: {rel}')
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
