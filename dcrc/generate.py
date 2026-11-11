"""Run the own emitter on verified local bytes and address-only catalogs (MIT)."""
from __future__ import annotations
import argparse,concurrent.futures,hashlib,json,subprocess,sys
from pathlib import Path
from .errors import ConverterError
from .profiles import load_profile,verify_folder,PROFILE_DIR,decode_overlay as prs_decompress
from .disc import _destination

def _signature(path,root):
    return {'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def generate(data,output,source_root,jobs=1):
    data,output,source_root=Path(data).resolve(),_destination(output),Path(source_root).resolve()
    if isinstance(jobs,bool)or not isinstance(jobs,int)or not 1<=jobs<=64:raise ConverterError('INVALID_OPTIONS','Generation jobs must be1..64')
    if output==data or output.is_relative_to(data)or data.is_relative_to(output):raise ConverterError('UNSAFE_PATH','Generation output and data must not overlap')
    if source_root.is_relative_to(output):raise ConverterError('UNSAFE_PATH','Generation output cannot contain source code')
    if output.is_relative_to(source_root):
        rel=output.relative_to(source_root)
        if not rel.parts or rel.parts[0]not in ('work','build','private')and rel.parts[:2]!=('recomp','out'):
            raise ConverterError('UNSAFE_PATH','Generated output must be separate from maintained source files')
    emitter=source_root/'recomp/emitter'
    for name in ('emit_sa1.py','emit_overlay.py'):
        if not(emitter/name).is_file():raise ConverterError('MISSING_SOURCE',f'Missing own emitter: {emitter/name}')
    profile=load_profile();identity=verify_folder(data)
    if identity.get('data_root'):data=Path(identity['data_root'])
    output.mkdir(parents=True,exist_ok=True);logs=output/'logs';logs.mkdir();bins=output/'overlay-inputs';bins.mkdir()
    def run(argv,label):
        result=subprocess.run([str(v)for v in [argv[0],'-B',*argv[1:]]],cwd=str(source_root),capture_output=True,text=True,encoding='utf-8',errors='replace',shell=False)
        (logs/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:raise ConverterError('GENERATION_FAILED',f'{label} failed with exit{result.returncode}',str(logs/(label+'.log')))
    main=output/'emitter'
    run([sys.executable,emitter/'emit_sa1.py',
         '--bin',data/profile['boot']['path'],
         '--functions',PROFILE_DIR/profile['catalogs']['main']['file'],
         '--sdk-functions',PROFILE_DIR/profile['sdk_fallback']['file'],
         '--out',main],'main')
    def overlay(ov):
        name=ov['name'];target=output/'overlays/emitter'/name;binary=bins/(name+'.bin')
        # Input was validated above; the emitter independently enforces the
        # decoded SHA again, including a change between validation and here.
        binary.write_bytes(prs_decompress((data/ov['file']).read_bytes()))
        run([sys.executable,emitter/'emit_overlay.py',source_root/ov['config'],'--bin',binary,'--functions',PROFILE_DIR/profile['catalogs'][name]['file'],'--main-table',main/'game_table.c','--out',target],name)
        if not(target/f'ovl_{name}_table.c').is_file()or not(target/f'ovl_{name}.h').is_file():raise ConverterError('GENERATION_INCOMPLETE',f'Overlay output missing: {name}')
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs)as pool:
        futures=[pool.submit(overlay,ov)for ov in profile['overlays']]
        for f in concurrent.futures.as_completed(futures):f.result()
    if not(main/'game_table.c').is_file()or not(main/'game.h').is_file():raise ConverterError('GENERATION_INCOMPLETE','Main output is missing')
    files=[_signature(p,output)for p in sorted(output.rglob('*'))if p.is_file()and p.suffix in ('.c','.h')]
    result={'generated':str(output),'profile':profile['id'],'main_chunks':len(list(main.glob('game_[0-9]*.c'))),'overlays':len(profile['overlays']),'files':files,'fingerprint':hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'logs':str(logs)}
    (output/'GENERATION.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--source',required=True,type=Path);p.add_argument('--jobs',type=int,default=1);a=p.parse_args(argv)
    try:result=generate(a.data,a.out,a.source,a.jobs)
    except ConverterError as e:print(str(e),file=sys.stderr);return 1
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
