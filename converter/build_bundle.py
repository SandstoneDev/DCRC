"""Build an asset-free portable Windows app from explicitly allowed source trees.

This is new DCRC packaging code. Reference PS2RC files are never imported/executed.
The builder requires existing licensed CPython/PySide/SDK directories, copied into
a NEW destination. No game binaries, generated C or private work are packaged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SOURCE_TREES = {
    'dcrc': {'.py', '.json', '.txt', '.policy'}, 'gui': {'.py', '.json'},
    'backend': {'.c', '.h', '.S', '.s', '.inc', '.cmake'}, 'hle': {'.c', '.h', '.S', '.s', '.inc'},
    'recomp/emitter': {'.py', '.c', '.h', '.S', '.md'},
    'recomp/sa1_us_1005': {'.toml', '.tsv', '.txt', '.md'},
    'converter/support': {'.S', '.h', '.md'},
}
TOOLS = ('convert_assets.py', 'land_convert.py', 'prs.py', 'psp_world_textures.py', 'psp_hot_order.txt',
         'psp_hot_order.py', 'gen_overlay_registry.py', 'movie_pmfmux.py', 'movie_pmfinfo.py')
ROOT_FILES = ('LICENSE', 'CMakeLists.txt', 'CREDITS.md', 'NOTICE.md',
              'LICENSES/sa1-psp-MIT.txt', 'LICENSES/PSPLink-BSD-3-Clause.txt',
              'LICENSES/MAME-BSD-3-Clause.txt', 'gui/assets/dcrc.ico', 'gui/assets/NOTICE.md')
ATRAC_REQUIRED = {'atracdenc.exe','README.md','SOURCE.txt','licenses/LICENSE.LGPL-2.1.txt',
    'licenses/LICENSE.kissfft.BSD3.txt','licenses/LICENSE.libgha.BSD2.txt','licenses/NOTICE.FFmpeg.txt',
    'licenses/crt-COPYING','licenses/crt-COPYING.MinGW-w64-runtime.txt','licenses/crt-COPYING.MinGW-w64.txt',
    'licenses/gcc-COPYING.RUNTIME','licenses/gcc-COPYING3','licenses/libwinpthread-COPYING',
    'source/atracdenc-0.2.3.tar.xz','source/atracdenc-0.2.3-dcrc-pcm1.tar.xz'}
SKIP = {'__pycache__', '.git', 'work', 'build', 'private', 'generated', '.pytest_cache'}
ENTRY_POINTS = ('gui/run_gui.py', 'gui/app.py', 'gui/controller.py', 'dcrc/__main__.py',
                'dcrc/pipeline.py', 'dcrc/worker.py', 'dcrc/models.py', 'dcrc/native_build.py', 'converter/README.md',
                'LICENSE', 'CMakeLists.txt', 'CREDITS.md', 'NOTICE.md',
                'LICENSES/sa1-psp-MIT.txt', 'LICENSES/PSPLink-BSD-3-Clause.txt',
                'LICENSES/MAME-BSD-3-Clause.txt', 'gui/assets/dcrc.ico')
SDK_REQUIRED = ('bin/psp-gcc.exe', 'bin/psp-fixup-imports.exe', 'bin/psp-prxgen.exe', 'bin/psp-strip.exe',
                'psp/sdk/include/pspkernel.h', 'psp/sdk/include/pspimport.s', 'psp/sdk/lib/prxspecs',
                'psp/sdk/lib/linkfile.prx', 'psp/sdk/lib/prxexports.o', 'psp/sdk/lib/libpspgu.a', 'psp/lib/libc.a',
                'psp/sdk/include/pspmpeg.h','psp/sdk/include/psputility.h',
                'psp/sdk/lib/libpspmpeg.a','psp/sdk/lib/libpsputility.a')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024*1024):
            h.update(block)
    return {'size': Path(path).stat().st_size, 'sha256': h.hexdigest()}


def source_files(root):
    root = Path(root).resolve()
    for name, extensions in SOURCE_TREES.items():
        base = root/name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*')):
            relative = path.relative_to(root)
            if any(part in SKIP for part in relative.parts):
                continue
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)() or (
                    path.exists() and not path.resolve().is_relative_to(root)):
                raise ValueError('Source link refused: ' + str(path))
            if path.is_file() and (path.suffix in extensions or
                                  name not in ('dcrc', 'gui') and path.name in ('CMakeLists.txt', 'Makefile')):
                yield path
    for name in ROOT_FILES + tuple('tools/'+name for name in TOOLS):
        path = root/name
        if path.is_symlink():
            raise ValueError('Source link refused: ' + str(path))
        if path.is_file():
            yield path


def copy_sources(root, output):
    root, output = Path(root).resolve(), Path(output)
    if output.exists():
        raise FileExistsError('New output folder required: ' + str(output))
    files = list(source_files(root))
    output.mkdir(parents=True)
    manifest = {}
    for src in files:
        name = src.relative_to(root).as_posix()
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        manifest[name] = digest(target)
        if manifest[name] != digest(src):
            raise OSError('Copy readback mismatch: ' + name)
    return manifest


def portable_pth(zip_name='python314.zip'):
    # Explicit isolated paths: no host site-packages or previous PS2RC app.
    return f'{zip_name}\n.\nLib\nDLLs\nLib/site-packages\n../app\n../app/source\n'


def copy_tree(source, target):
    source = Path(source).resolve()
    for path in source.rglob('*'):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ValueError('Dependency symlink refused: ' + str(path))
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*SKIP, '*.pyc'))


def verify_ffmpeg_dependency(dependency):
    root=Path(dependency).resolve()
    meta=json.loads((root/'MANIFEST.json').read_text(encoding='utf8'))
    files=meta.get('files',{})
    if meta.get('format')!='DCRC_FFMPEG_DEPENDENCY_V1' or not {'ffmpeg.exe','ffprobe.exe','README.txt','PROVENANCE.json'}.issubset(files):
        raise ValueError('Incomplete FFmpeg dependency/provenance')
    if not ({'LICENSE.GPL-2.0.txt','LICENSE.GPL-3.0.txt'} & set(files)):
        raise ValueError('FFmpeg GPL license text required')
    if not 5<=len(files)<=64:raise ValueError('Invalid FFmpeg file inventory')
    for name,e in files.items():
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name or p.as_posix()!=name:
            raise ValueError('Unsafe FFmpeg dependency path')
        path=root/p
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)() or not path.resolve().is_relative_to(root):
            raise ValueError('FFmpeg dependency link refused')
        if digest(path)!={'size':e['bytes'],'sha256':e['sha256']}:raise ValueError('FFmpeg dependency changed: '+name)
    inventory={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if inventory!=set(files)|{'MANIFEST.json'}:raise ValueError('Unlisted FFmpeg dependency files')
    return files



def copy_ffmpeg_dependency(dependency, target):
    """Copy an inventoried dependency and read back its manifest and every file."""
    source=Path(dependency).resolve();target=Path(target)
    verify_ffmpeg_dependency(source)
    manifest=digest(source/'MANIFEST.json')
    copy_tree(source,target)
    if digest(target/'MANIFEST.json')!=manifest:
        raise ValueError('FFmpeg manifest copy readback mismatch')
    return verify_ffmpeg_dependency(target)


def build_launcher(source, target, cc):
    source = Path(source).resolve()
    cc = Path(cc).resolve()
    windres = cc.with_name('windres.exe' if os.name == 'nt' else 'windres')
    if not windres.is_file():
        raise ValueError('MinGW windres is required for the launcher icon')
    env = dict(os.environ)
    env['PATH'] = str(cc.parent) + os.pathsep + env.get('PATH', '')
    with tempfile.TemporaryDirectory(prefix='dcrc-launcher-') as folder:
        resource = Path(folder) / 'icon.rc'
        resource_object = resource.with_suffix('.o')
        resource.write_text('1 ICON "gui/assets/dcrc.ico"\n', encoding='utf8')
        subprocess.run([str(windres), str(resource), '-O', 'coff', '-o', str(resource_object)],
                       cwd=source, env=env, check=True)
        subprocess.run([str(cc), '-O2', '-municode', '-mwindows', '-static',
                        str(source / 'converter/launcher.c'), str(resource_object), '-o', str(Path(target).resolve())],
                       env=env, check=True)


def build(source, output, python_from, toolchain, licenses, cc=None, receipt=None, atrac_dependency=None,
          ffmpeg_dependency=None, *, release_revision=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    python_from, toolchain, licenses = map(lambda p: Path(p).resolve(), (python_from, toolchain, licenses))
    if output.exists():
        raise FileExistsError('New output required: ' + str(output))
    if release_revision is not None and (type(release_revision) is not int or not 1 <= release_revision < 2**31):
        raise ValueError('Release revision must be a positive 31-bit integer')
    if receipt and Path(receipt).resolve().is_relative_to(output):
        raise ValueError('Private build receipt must be outside the user bundle')
    ffmpeg_files=verify_ffmpeg_dependency(ffmpeg_dependency) if ffmpeg_dependency else None
    if ffmpeg_dependency and output.is_relative_to(Path(ffmpeg_dependency).resolve()):
        raise ValueError("FFmpeg dependency must be outside output")
    atrac_files=None
    if atrac_dependency:
        atrac_dependency=Path(atrac_dependency).resolve()
        if output.is_relative_to(atrac_dependency):raise ValueError('ATRAC dependency must be outside output')
        meta=json.loads((atrac_dependency/'MANIFEST.json').read_text(encoding='utf8'))
        if meta.get('format')!='DCRC_ATRACDENC_DEPENDENCY_V1':raise ValueError('Unverified ATRAC dependency manifest')
        atrac_files=meta.get('files',{})
        if not ATRAC_REQUIRED.issubset(atrac_files) or len(atrac_files)>64:raise ValueError('Incomplete ATRAC licences/corresponding source')
        for name,e in atrac_files.items():
            p=Path(name)
            if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name or p.as_posix()!=name:
                raise ValueError('Unsafe ATRAC dependency path')
            if not (atrac_dependency/p).resolve().is_relative_to(atrac_dependency):
                raise ValueError('ATRAC dependency link escapes source')
            actual=digest(atrac_dependency/p)
            if actual!={'size':e['bytes'],'sha256':e['sha256']}:raise ValueError('ATRAC dependency changed: '+name)
        inventory={p.relative_to(atrac_dependency).as_posix()for p in atrac_dependency.rglob('*')if p.is_file()}
        if inventory!=set(atrac_files)|{'MANIFEST.json'}:raise ValueError('Unlisted ATRAC dependency files')
    for origin in (source, python_from, toolchain, licenses):
        ignored_work = (origin == source and output.is_relative_to(source) and
                        output.relative_to(source).parts and
                        output.relative_to(source).parts[0] in ('work', 'build'))
        if output == origin or output.is_relative_to(origin) and not ignored_work:
            raise ValueError('Output must be separate from input trees')
    required = (python_from/'python.exe', python_from/'pythonw.exe',
                python_from/'Lib/site-packages/PySide6/QtWidgets.pyd',
                python_from/'Lib/site-packages/PySide6/plugins/platforms/qwindows.dll',
                licenses/'Python-LICENSE.txt', licenses/'Qt/LGPL-3.0.txt', licenses/'Qt/SOURCE.txt')
    required += tuple(source/name for name in ENTRY_POINTS)
    required += tuple(toolchain/name for name in SDK_REQUIRED)
    if cc:
        required += (source/'converter/launcher.c',)
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise ValueError('Missing portable dependency/licence: ' + ', '.join(missing))
    output.mkdir(parents=True)
    source_manifest = copy_sources(source, output/'app/source')
    # Core is importable at app/, while runtime/emitter data live under app/source/.
    for name in ('dcrc', 'gui', 'converter'):
        src = output/'app/source'/name
        if src.is_dir():
            shutil.move(str(src), str(output/'app'/name))
    # Keep support under both contracts; these files contain own import declarations.
    support = output/'app/converter/support'
    if support.is_dir():
        shutil.copytree(support, output/'app/source/converter/support')
    copy_tree(python_from, output/'python')
    pths = list((output/'python').glob('python*._pth'))
    if len(pths) != 1:
        raise ValueError('Expected exactly one isolated Python ._pth')
    version = pths[0].stem.removesuffix('._pth')
    pths[0].write_text(portable_pth(version+'.zip'), encoding='utf8')
    copy_tree(toolchain, output/'toolchain')
    if atrac_files is not None:
        copy_tree(atrac_dependency,output/'tools/atracdenc')
        for name,e in atrac_files.items():
            if digest(output/'tools/atracdenc'/name)!={'size':e['bytes'],'sha256':e['sha256']}:
                raise ValueError('ATRAC copy readback mismatch: '+name)
    if ffmpeg_files is not None:
        copy_ffmpeg_dependency(ffmpeg_dependency,output/'tools/ffmpeg')
    # License data are copied separately, including replaceable Qt source pointers.
    (output/'licenses').mkdir()
    for name in ('Python-LICENSE.txt', 'Qt', 'pillow', 'pyelftools'):
        src = licenses/name
        if src.is_dir(): copy_tree(src, output/'licenses'/name)
        elif src.is_file(): shutil.copy2(src, output/'licenses'/name)
    for name in ('LICENSE', 'NOTICE', 'NOTICE.md', 'BUILDINFO.txt', 'licenses'):
        src = toolchain/name
        if src.is_dir(): copy_tree(src, output/'licenses/toolchain'/name)
        elif src.is_file():
            (output/'licenses/toolchain').mkdir(exist_ok=True)
            shutil.copy2(src, output/'licenses/toolchain'/name)
    if not (output/'licenses/toolchain').exists():
        raise ValueError('Toolchain licence/source-offer directory required')
    shutil.copy2(source/'LICENSE', output/'licenses/sa1-psp-LICENSE.txt')
    (output/'licenses/DCRC-NOTICE.txt').write_text(
        'DCRC Converter: new frontend/packaging code; sa1-psp runtime under its included MIT licence.\n'
        'No PS2RC Python/C source copied. CPython, PySide/Qt, Pillow, pyelftools and native SDK retain\n'
        'their separate licences. Qt DLL/PYD files remain replaceable. See Qt/SOURCE.txt and\n'
        'toolchain/ for version/source/build provenance. No game data/generated game C included.\n', encoding='utf8')
    preamble = '@echo off\r\nsetlocal\r\nset PYTHONDONTWRITEBYTECODE=1\r\n'
    (output/'DCRC Converter.cmd').write_text(preamble+'"%~dp0python\\pythonw.exe" -B "%~dp0app\\gui\\run_gui.py" %*\r\n', encoding='utf8')
    (output/'dcrc.cmd').write_text(preamble+'"%~dp0python\\python.exe" -B -m dcrc %*\r\n', encoding='utf8')
    shutil.copy2(source/'converter/README.md', output/'README.md')
    if cc:
        build_launcher(source, output/'DCRC Converter.exe', cc)
    manifest = {p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    record = dict(format='DCRC_PORTABLE_WINDOWS_X64_V1',
                  status='PASS_STATIC_BUNDLE_REQUIRES_FUNCTIONAL_TEST', files=manifest,
                  source_manifest=source_manifest, game_data_included=False,
                  launcher_built=bool(cc), standalone_atrac_tool=bool(atrac_files), standalone_ffmpeg_tools=bool(ffmpeg_files),
                  binary_distribution_clearance=False)
    if release_revision is not None:
        record['release_revision'] = release_revision
    (output/'BUNDLE_MANIFEST.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf8')
    if receipt:
        receipt = Path(receipt)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(dict(status=record['status'], source_origin=str(source),
            python_origin=str(python_from), toolchain_origin=str(toolchain), licenses_origin=str(licenses),
            host_compiler=str(cc) if cc else None, output=str(output),
            manifest=digest(output/'BUNDLE_MANIFEST.json')), indent=2)+'\n', encoding='utf8')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    for name in ('out', 'python-from', 'toolchain', 'licenses'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--cc', type=Path, help='Native MinGW gcc for Unicode .exe launcher')
    parser.add_argument('--receipt', type=Path, help='Private provenance path OUTSIDE the user bundle')
    parser.add_argument('--atrac-dependency',type=Path,help='Local verified encoder with licences and complete corresponding source; not release clearance.')
    parser.add_argument('--ffmpeg-dependency',type=Path,help='Local verified FFmpeg/ffprobe with licence/provenance inventory; not release clearance.')
    parser.add_argument('--release-revision', type=int, help='Monotonic GitHub archive revision for a publication candidate.')
    a = parser.parse_args(argv)
    record = build(a.source, a.out, a.python_from, a.toolchain, a.licenses, a.cc, a.receipt,
                   a.atrac_dependency, a.ffmpeg_dependency, release_revision=a.release_revision)
    print(json.dumps({'status': record['status'], 'files': len(record['files']), 'output': str(a.out)}))


if __name__ == '__main__':
    main()
