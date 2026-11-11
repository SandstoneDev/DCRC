"""The same local pipeline as the window, for terminals and automation."""
from pathlib import Path
from dataclasses import asdict
import argparse,json,sys,threading,signal
from . import __version__
from .errors import ConverterError,Cancelled
from .models import ConversionOptions,STAGES,CHARACTERS
from .capabilities import PROFILE_CAPABILITIES

def _world(value):
    if value=='original':return 0
    try:result=int(value)
    except ValueError:raise argparse.ArgumentTypeError('Choose original,64 or128.')
    if result not in (0,64,128):raise argparse.ArgumentTypeError('Choose original,64 or128.')
    return result

def _settings(p,conversion=False):
    p.add_argument('--control',dest='control_map',action='append',help='Guest input only: physical=action; HOME/menu unaffected.')
    p.add_argument('--dither',choices=['on','opaque','off'],default='on' if conversion else None)
    p.add_argument('--movies',action=argparse.BooleanOptionalAction,default=False if conversion else None)
    p.add_argument('--land-distance',type=int,default=100 if conversion else None)
    p.add_argument('--aspect',choices=['wide','16:9','4:3'],default='wide' if conversion else None)
    p.add_argument('--frame-skip',default='auto' if conversion else None)
    p.add_argument('--mip-levels',type=int,default=8 if conversion else None)
    p.add_argument('--fps','--show-fps',dest='show_fps',action=argparse.BooleanOptionalAction,default=True if conversion else None)
    p.add_argument('--audio',action=argparse.BooleanOptionalAction,default=True if conversion else None)
    p.add_argument('--voice',choices=['en','ja','game'],default='en' if conversion else None)
    p.add_argument('--stage',dest='startup_stage',choices=STAGES,default='normal' if conversion else None)
    p.add_argument('--character',dest='startup_character',choices=CHARACTERS,default='sonic' if conversion else None)
    p.add_argument('--act',dest='startup_act',type=int,default=1 if conversion else None)

def parser():
    p=argparse.ArgumentParser(prog='dcrc',description='DCRC Converter — your supported Dreamcast GDI to a locally built PSP folder.')
    p.add_argument('--version',action='version',version='DCRC Converter '+__version__)
    commands=p.add_subparsers(dest='command',required=True)
    identify=commands.add_parser('identify',help='Read-only supported-version and content-hash check.');identify.add_argument('source',type=Path);identify.add_argument('--json',action='store_true')
    c=commands.add_parser('convert',help='Extract, generate, compile, convert and verify locally.')
    c.add_argument('source',type=Path);c.add_argument('--out',dest='output',required=True,type=Path,help='Exact PSP game folder to create (not the memory-stick root).')
    c.add_argument('--work',type=Path);c.add_argument('--toolchain',type=Path);c.add_argument('--jobs',type=int,default=ConversionOptions.__dataclass_fields__['jobs'].default)
    c.add_argument('--border-image',type=Path,help='Optional own image; requires a reviewed border-capable runtime.')
    c.add_argument('--border-mode',choices=['none','custom'],default=None)
    c.add_argument('--dlc-dir',type=Path,help='Optional own extracted VMI/VMS folder; copied locally as opaque events.')
    for kind in ('icon','background','music'):
        c.add_argument('--xmb-'+kind+'-mode',choices=['game','file','none'],default='none')
        c.add_argument('--xmb-'+kind+'-file',type=Path)
    c.add_argument('--xmb-icon-art',default='title');c.add_argument('--xmb-background-art',default='title')
    c.add_argument('--xmb-track',default='TITLE.ADX');c.add_argument('--xmb-music-start',type=float,default=0)
    c.add_argument('--xmb-music-seconds',type=float,default=6);c.add_argument('--xmb-encoder',type=Path);c.add_argument('--ffmpeg',type=Path)
    c.add_argument('--profile',default='sa1_us_1005');c.add_argument('--preset',choices=['psp','original'],default='psp')
    c.add_argument('--world-textures',type=_world,default=None,help='original,64 or128; resolution cap applies to selected Emerald Coast world assets.')
    c.add_argument('--title',default='DCRC Port');c.add_argument('--json',action='store_true');c.add_argument('--verbose',action='store_true');_settings(c,True)
    v=commands.add_parser('verify',help='Full SHA256/size verification against the local output manifest.');v.add_argument('folder',type=Path);v.add_argument('--json',action='store_true')
    r=commands.add_parser('repair',help='Restore an owned folder while keeping saves and player settings.');r.add_argument('folder',type=Path);r.add_argument('--source',type=Path);r.add_argument('--toolchain',type=Path);r.add_argument('--json',action='store_true')
    cfg=commands.add_parser('configure',help='Apply runtime settings without recompiling or changing saves.');cfg.add_argument('folder',type=Path);cfg.add_argument('--json',action='store_true');_settings(cfg)
    d=commands.add_parser('doctor',help='Check the supplied native SDK, runtime source and supported profile.');d.add_argument('--toolchain',type=Path);d.add_argument('--json',action='store_true')
    media=commands.add_parser('media',help='Inspect user-local artwork/music without converting.');media.add_argument('source',type=Path);media.add_argument('--json',action='store_true')
    dlc=commands.add_parser('dlc-catalog',help='Optional network catalog; not guest gameplay verification.');dlc.add_argument('--out',type=Path,required=True);dlc.add_argument('--json',action='store_true')
    download=commands.add_parser('dlc-download',help='Download checked opaque events; public decoder is excluded.');download.add_argument('catalog',type=Path);download.add_argument('--id',dest='ids',action='append',required=True);download.add_argument('--out',type=Path,required=True);download.add_argument('--json',action='store_true')
    return p

def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
    argv=list(sys.argv[1:] if argv is None else argv)
    commands={'convert','identify','verify','repair','configure','doctor','media','dlc-catalog','dlc-download'}
    if argv and not argv[0].startswith('-') and argv[0]not in commands:argv.insert(0,'convert')
    a=parser().parse_args(argv);is_json=getattr(a,'json',False);verbose=getattr(a,'verbose',False)
    def event(e):
        if is_json:return
        if e.get('type')=='stage':print(e.get('message',e.get('stage','')),flush=True)
        elif verbose:print(e.get('message',''),flush=True)
    stop=threading.Event();old_signal=None
    if threading.current_thread() is threading.main_thread():
        old_signal=signal.getsignal(signal.SIGINT);signal.signal(signal.SIGINT,lambda *_:stop.set())
    try:
        from .pipeline import convert,identify,repair_folder
        from .package import verify_folder,configure_folder,RUNTIME_KEYS
        if a.command=='dlc-catalog':
            from .dlc_download import discover_catalog
            from .storage import write_json
            r=discover_catalog(event=event,cancel=stop,preflight=True);write_json(a.out,r)
        elif a.command=='dlc-download':
            from .dlc_download import download_events
            from .storage import read_json
            catalog=read_json(a.catalog)
            r=download_events(catalog,a.ids,a.out,expected_fingerprint=catalog['fingerprint'],event=event,cancel=stop)
            from .capabilities import DLC_NOTICE
            r['capability_notice']=DLC_NOTICE
        elif a.command=='media':
            from .xmb import inspect_source_media
            r=inspect_source_media(a.source,event=event,cancel=stop)
            r['images']=[{k:v for k,v in image.items()if k!='preview_png'}for image in r.get('images',[])]
        elif a.command=='identify':
            r=identify(a.source,cancel_event=stop)
            if not is_json:r={k:r[k]for k in ('ok','profile','title','region','version','boot','message','hint')if k in r}
        elif a.command=='convert':
            values=vars(a).copy()
            for name in ('command','preset','json','verbose'):values.pop(name,None)
            if values['world_textures']is None:values['world_textures']=0 if a.preset=='original' else 64
            from .controls import parse_bindings
            values['control_map']=parse_bindings(values.get('control_map'))
            result=convert(ConversionOptions(**values),event=event,cancel_event=stop)
            r=dict(asdict(result),ok=True)
            if values.get('dlc_dir'):
                from .capabilities import DLC_NOTICE
                r['dlc_notice']=DLC_NOTICE
        elif a.command=='verify':r=verify_folder(a.folder)
        elif a.command=='configure':
            values={key:getattr(a,key)for key in RUNTIME_KEYS if hasattr(a,key)and getattr(a,key)is not None}
            if 'control_map'in values:
                from .controls import parse_bindings
                values['control_map']=parse_bindings(values['control_map'])
            r=configure_folder(a.folder,**values)
        elif a.command=='repair':r=dict(asdict(repair_folder(a.folder,a.source,a.toolchain,event=event,cancel_event=stop)),ok=True)
        else:
            from .toolchain import resolve
            from .runtime_source import runtime_root,source_files
            from .profiles import load_profile
            tc=resolve(a.toolchain);profile=load_profile();files=source_files(runtime_root())
            r={'ok':True,'converter':__version__,'profile':profile['id'],'supported_version':profile['version'],
               'boot':profile['boot'],'capabilities':PROFILE_CAPABILITIES,'native_toolchain':str(tc.root),'runtime_source_files':len(files),'requires_wsl':False}
        print(json.dumps(r,ensure_ascii=False,indent=2,default=str))
        return 0 if r.get('ok',True) else 2
    except KeyboardInterrupt:
        print('Cancelled. Completed work is retained.',file=sys.stderr);return 130
    except ConverterError as e:
        r={'ok':False,'code':e.code,'message':e.message,'hint':e.hint}
        print(json.dumps(r,ensure_ascii=False,indent=2),file=sys.stderr);return 130 if isinstance(e,Cancelled)else 2
    finally:
        if old_signal is not None:signal.signal(signal.SIGINT,old_signal)

if __name__=='__main__':raise SystemExit(main())
