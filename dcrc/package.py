"""Owned PSP output, editable settings, and independent full content verification."""
from pathlib import Path
from dataclasses import fields
import hashlib,uuid
from .errors import ConverterError
from .models import ConversionOptions
from .storage import read_json,write_json,checked_path,reject_links,file_digest,tree_files

MANIFEST='dcrc_manifest.json'
OWNER='.dcrc_owner.json'
MUTABLE={'args.txt','data/sa1psp.ini','dcrc_settings.json'}
RUNTIME_KEYS={'land_distance','aspect','frame_skip','mip_levels','show_fps','audio','voice',
              'startup_stage','startup_character','startup_act','control_map','movies','dither'}

def claim_output(folder,profile):
    folder=Path(folder);reject_links(folder)
    if folder.exists():
        if not folder.is_dir():raise ConverterError('output','Output is not a directory.')
        if any(folder.iterdir()):
            marker=folder/OWNER;reject_links(marker)
            if not marker.is_file():raise ConverterError('foreign_output','The nonempty output folder was not made by DCRC. Choose a new folder.')
            m=read_json(marker)
            if not isinstance(m,dict) or m.get('format')!='DCRC_OUTPUT_V1' or m.get('profile')!=profile:
                raise ConverterError('foreign_output','The output belongs to another converter/profile.')
            return
    folder.mkdir(parents=True,exist_ok=True)
    write_json(folder/OWNER,{'format':'DCRC_OUTPUT_V1','profile':profile,'id':uuid.uuid4().hex})

def write_manifest(folder,metadata,mutable=None,owned=None):
    folder=Path(folder);mutable=set(mutable or MUTABLE)
    if not mutable<=MUTABLE:raise ConverterError('manifest','Invalid mutable payload classification.')
    if owned is None:
        owned=[p for p in tree_files(folder) if p not in (MANIFEST,OWNER) and not p.startswith('vmu/')]
    result={}
    for rel in sorted(set(owned)):
        if rel in (MANIFEST,OWNER) or rel.startswith('vmu/'):continue
        p=checked_path(folder,rel)
        if not p.is_file():raise ConverterError('manifest',f'Missing payload while creating manifest: {rel}')
        actual=file_digest(p)
        if isinstance(owned,dict) and actual!=owned[rel]:
            raise ConverterError('write_readback',f'Payload changed before manifest publication: {rel}')
        result[rel]=dict(actual,mutable=rel in mutable)
    m=dict(metadata,format='DCRC_PACKAGE_V1',files=result)
    write_json(folder/MANIFEST,m)
    return m

def _manifest(folder):
    folder=Path(folder);reject_links(folder);reject_links(folder/MANIFEST)
    m=read_json(folder/MANIFEST)
    if not isinstance(m,dict) or m.get('format')!='DCRC_PACKAGE_V1' or m.get('profile')!='sa1_us_1005' or not isinstance(m.get('files'),dict):
        raise ConverterError('manifest','This is not a supported DCRC output manifest.')
    if len(m['files'])>20000:raise ConverterError('manifest','Output manifest is too large.')
    for rel,e in m['files'].items():
        checked_path(folder,rel)
        if not isinstance(e,dict) or type(e.get('bytes')) is not int or e['bytes']<0 or not isinstance(e.get('sha256'),str) or len(e['sha256'])!=64:
            raise ConverterError('manifest','Invalid output digest.')
        if e.get('mutable') and rel not in MUTABLE:raise ConverterError('manifest','Only player settings may be mutable.')
    return m

def verify_folder(folder):
    folder=Path(folder);m=_manifest(folder);problems=[];checked=0
    for rel,e in m['files'].items():
        p=checked_path(folder,rel)
        if not p.is_file():problems.append(f'Missing: {rel}');continue
        if e.get('mutable'):continue
        checked+=1
        if file_digest(p)!={k:e[k] for k in ('bytes','sha256')}:problems.append(f'SHA256/size mismatch: {rel}')
    return {'ok':not problems,'status':'PASS' if not problems else 'FAIL','checked':checked,
            'profile':m['profile'],'folder':str(folder.resolve()),'problems':problems}

def runtime_text(options):
    args=[f'--land-distance {options.land_distance}','--stats 120']
    ini='# DCRC player settings. Quality/runtime options may be edited locally.\n'
    ini+=f'voice = {options.voice}\naudio = '+('on' if options.audio else 'off')+'\n'
    from .capabilities import PROFILE_CAPABILITIES
    if PROFILE_CAPABILITIES['movie_playback']:ini+='movies = '+('on' if options.movies else 'off')+'\n'
    if PROFILE_CAPABILITIES['configurable_dither']:ini+=f'dither = {options.dither}\n'
    ini+='renderer = ta\nland_cull = on\nevent_skip = on\nmath = native\n'
    ini+=f'aspect = {options.aspect}\nframe_skip = {options.frame_skip}\nmip_levels = {options.mip_levels}\n'
    ini+='fps_hud = '+('on' if options.show_fps else 'off')+'\ndebug_menu = on\n'
    ini+=f'start_stage = {"off" if options.startup_stage=="normal" else options.startup_stage}\n'
    ini+=f'start_character = {options.startup_character}\nstart_act = {options.startup_act}\n'
    for physical,action in options.control_map.items():ini+=f'control_{physical} = {action}\n'
    return '\n'.join(args)+'\n',ini

def configure_folder(folder,**runtime_options):
    folder=Path(folder);m=_manifest(folder)
    if set(runtime_options)-RUNTIME_KEYS:raise ConverterError('settings','Changing world assets requires conversion from the source disc.')
    old=m.get('options',{});values={f.name:old[f.name] for f in fields(ConversionOptions) if f.name in old}
    values.update(runtime_options);values.update(source=Path('.'),output=Path('.'),work=None,toolchain=None)
    opts=ConversionOptions(**values).validate(check_paths=False)
    if opts.movies:
        from .movies import NAMES
        for name in NAMES:
            for extension in ('pmf','wav'):
                rel=f'data/MOVIE/{name}.{extension}';owned=m['files'].get(rel)
                p=checked_path(folder,rel)
                if not owned or owned.get('mutable') or not p.is_file() or file_digest(p)!={k:owned[k] for k in ('bytes','sha256')}:
                    raise ConverterError('movies_assets','Reconvert from your own disc with movies enabled before turning FMV on. Movie assets are missing, unowned or modified.')
    args,ini=runtime_text(opts)
    # Known runtime settings change; retain unrelated hand-written INI keys.
    old_ini=checked_path(folder,'data/sa1psp.ini')
    if old_ini.exists():
        known={'voice','audio','renderer','land_cull','event_skip','math','aspect','frame_skip',
               'gu_max_mip','mip_levels','fps_hud','debug_menu','start_stage','start_character','start_act','movies','dither'}
        extra=[line for line in old_ini.read_text(encoding='utf-8-sig').splitlines()
               if '=' in line and line.split('=',1)[0].strip() not in known and not line.split('=',1)[0].strip().startswith('control_')]
        if extra:ini+='\n# Additional player settings\n'+'\n'.join(extra)+'\n'
    for rel,text in [('args.txt',args),('data/sa1psp.ini',ini)]:
        p=checked_path(folder,rel);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8',newline='\n')
    settings={k:getattr(opts,k) for k in RUNTIME_KEYS}
    write_json(checked_path(folder,'dcrc_settings.json'),settings)
    m['options']=dict(old,**settings)
    for rel in MUTABLE:
        p=checked_path(folder,rel)
        if p.is_file():m['files'][rel]=dict(file_digest(p),mutable=True)
    write_json(folder/MANIFEST,m)
    return {'ok':True,'folder':str(folder),'settings':settings}
