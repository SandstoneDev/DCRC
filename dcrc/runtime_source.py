"""Explicit source allowlist shared by cold jobs; no private/build trees."""
from pathlib import Path
import shutil
from .storage import file_digest, fingerprint, reject_links
from .errors import ConverterError

TREES={'backend':{'.c','.h','.S','.s','.inc','.cmake'},'hle':{'.c','.h','.S','.s','.inc'},
       'recomp/emitter':{'.py','.c','.h','.S','.md'},
       'recomp/sa1_us_1005':{'.toml','.tsv','.txt','.md'},
       'converter/support':{'.S','.h','.md'}}
TOOLS=('convert_assets.py','land_convert.py','prs.py','psp_world_textures.py',
       'psp_hot_order.txt','psp_hot_order.py','gen_overlay_registry.py')
SKIP={'__pycache__','.git','work','build','private','generated','.pytest_cache'}
NOTICES=('CREDITS.md','NOTICE.md','LICENSES/sa1-psp-MIT.txt',
         'LICENSES/PSPLink-BSD-3-Clause.txt','LICENSES/MAME-BSD-3-Clause.txt')

def runtime_root():
    base=Path(__file__).resolve().parents[1]
    return base/'source' if (base/'source/CMakeLists.txt').is_file() else base

def source_files(root):
    root=Path(root);files={}
    for tree,extensions in TREES.items():
        directory=root/tree
        if not directory.is_dir():raise ConverterError('runtime_source',f'Missing runtime source tree: {tree}')
        for p in sorted(directory.rglob('*')):
            if any(part in SKIP for part in p.relative_to(directory).parts):continue
            reject_links(p)
            if p.is_file() and (p.suffix in extensions or p.name in ('CMakeLists.txt','Makefile')):
                files[p.relative_to(root).as_posix()]=file_digest(p)
    for rel in ('LICENSE','CMakeLists.txt',*NOTICES,*('tools/'+name for name in TOOLS)):
        p=root/rel
        if not p.is_file():raise ConverterError('runtime_source',f'Missing runtime source: {rel}')
        files[rel]=file_digest(p)
    return files

def snapshot(root,destination):
    root,destination=Path(root),Path(destination)
    if destination.exists():raise ConverterError('runtime_source','Source snapshot destination must be new.')
    files=source_files(root);destination.mkdir(parents=True)
    for rel,e in files.items():
        src=root/rel;dst=destination/rel;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dst)
        if file_digest(dst)!=e:raise ConverterError('source_changed',f'Runtime source changed while taking snapshot: {rel}')
    return {'source_root':str(destination.resolve()),'fingerprint':fingerprint(files),'files':files}
