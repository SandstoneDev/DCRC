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

SOURCE_TREES = {
    'dcrc': {'.py', '.json', '.txt', '.policy'}, 'gui': {'.py'},
    'backend': {'.c', '.h', '.S', '.s', '.inc', '.cmake'}, 'hle': {'.c', '.h', '.S', '.s', '.inc'},
    'recomp/emitter': {'.py', '.c', '.h', '.S', '.md'},
    'recomp/sa1_us_1005': {'.toml', '.tsv', '.txt', '.md'},
    'converter/support': {'.S', '.h', '.md'},
}
TOOLS = ('convert_assets.py', 'land_convert.py', 'prs.py', 'psp_world_textures.py', 'psp_hot_order.txt',
         'psp_hot_order.py', 'gen_overlay_registry.py')
ROOT_FILES = ('LICENSE', 'CMakeLists.txt', 'CREDITS.md', 'NOTICE.md',
              'LICENSES/sa1-psp-MIT.txt', 'LICENSES/PSPLink-BSD-3-Clause.txt',
              'LICENSES/MAME-BSD-3-Clause.txt')
SKIP = {'__pycache__', '.git', 'work', 'build', 'private', 'generated', '.pytest_cache'}
ENTRY_POINTS = ('gui/run_gui.py', 'gui/app.py', 'gui/controller.py', 'dcrc/__main__.py',
                'dcrc/pipeline.py', 'dcrc/worker.py', 'dcrc/models.py', 'dcrc/native_build.py', 'converter/README.md',
                'LICENSE', 'CMakeLists.txt', 'CREDITS.md', 'NOTICE.md',
                'LICENSES/sa1-psp-MIT.txt', 'LICENSES/PSPLink-BSD-3-Clause.txt',
                'LICENSES/MAME-BSD-3-Clause.txt')
SDK_REQUIRED = ('bin/psp-gcc.exe', 'bin/psp-fixup-imports.exe', 'bin/psp-prxgen.exe', 'bin/psp-strip.exe',
                'psp/sdk/include/pspkernel.h', 'psp/sdk/include/pspimport.s', 'psp/sdk/lib/prxspecs',
                'psp/sdk/lib/linkfile.prx', 'psp/sdk/lib/prxexports.o', 'psp/sdk/lib/libpspgu.a', 'psp/lib/libc.a')


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
    return f'{zip_name}\n.\nLib\nDLLs\nLib/site-packages\n../app\n'


def copy_tree(source, target):
    source = Path(source).resolve()
    for path in source.rglob('*'):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ValueError('Dependency symlink refused: ' + str(path))
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*SKIP, '*.pyc'))


def build(source, output, python_from, toolchain, licenses, cc=None, receipt=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    python_from, toolchain, licenses = map(lambda p: Path(p).resolve(), (python_from, toolchain, licenses))
    if output.exists():
        raise FileExistsError('New output required: ' + str(output))
    if receipt and Path(receipt).resolve().is_relative_to(output):
        raise ValueError('Private build receipt must be outside the user bundle')
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
        env = dict(os.environ)
        env['PATH'] = str(Path(cc).resolve().parent) + os.pathsep + env.get('PATH', '')
        subprocess.run([str(cc), '-O2', '-municode', '-mwindows', '-static',
                        str(source/'converter/launcher.c'), '-o', str(output/'DCRC Converter.exe')], env=env, check=True)
    manifest = {p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    record = dict(status='PASS_STATIC_BUNDLE_REQUIRES_FUNCTIONAL_TEST', files=manifest,
                  source_manifest=source_manifest, game_data_included=False,
                  launcher_built=bool(cc))
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
    a = parser.parse_args(argv)
    record = build(a.source, a.out, a.python_from, a.toolchain, a.licenses, a.cc, a.receipt)
    print(json.dumps({'status': record['status'], 'files': len(record['files']), 'output': str(a.out)}))


if __name__ == '__main__':
    main()
