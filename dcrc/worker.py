"""Owned subprocess entry for long data stages; no shell or private paths."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dcrc.errors import ConverterError
from dcrc.storage import write_json,file_digest,tree_files,fingerprint

def assets(data,output,source,world):
    import importlib.util
    data,output,source=Path(data),Path(output),Path(source)
    sys.path.insert(0,str(source/'tools'))
    from convert_assets import main as stage_assets
    from land_convert import main as stage_land
    argv=sys.argv[:]
    try:
        sys.argv=['convert_assets.py','--data',str(data),'--out',str(output),'--pack','--native']
        stage_assets()
        for level in (1,27,28):
            sys.argv=['land_convert.py','--data',str(data),'--out',str(output/'data'),'--level',str(level)]
            stage_land()
        if world:
            from psp_world_textures import convert,read_policy
            from dcrc.profiles import PROFILE_DIR
            original=output/'data/SONICADV.PAK';changed=output/'data/SONICADV.world.pak'
            report=convert(original,changed,read_policy(PROFILE_DIR/'world_textures.policy'),world)
            # Both files belong to this newly created stage only. The raw
            # source and earlier stages remain intact; keep original as witness.
            original.rename(output/'SONICADV.original.pak')
            changed.rename(original)
            write_json(output/'WORLD_TEXTURES.json',report)
    finally:sys.argv=argv
    files=tree_files(output/'data')
    if len(list((output/'data/native').glob('LAND_*.BIN')))!=21:raise ConverterError('assets','Expected21 converted native LAND files.')
    return {'payload_root':str(output.resolve()),'data_root':str((output/'data').resolve()),'files':files,'fingerprint':fingerprint(files),'world_textures':world}

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['extract','generate','assets']);p.add_argument('--source',required=True,type=Path);p.add_argument('--data',type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--report',required=True,type=Path);p.add_argument('--jobs',type=int,default=1);p.add_argument('--world',type=int,default=0);a=p.parse_args()
    def progress(value):print('DCRC_EVENT '+json.dumps(value,ensure_ascii=False),flush=True)
    try:
        if a.stage=='extract':
            from dcrc.disc import extract_source
            result=extract_source(a.source,a.out,progress=progress)
        elif a.stage=='generate':
            from dcrc.generate import generate
            result=generate(a.data,a.out,a.source,a.jobs)
        else:result=assets(a.data,a.out,a.source,a.world)
        write_json(a.report,result);return 0
    except ConverterError as e:
        print(f'{e.code}: {e.message}\n{e.hint}',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
