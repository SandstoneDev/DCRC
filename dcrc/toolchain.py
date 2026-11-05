"""Resolve a portable native PSP SDK without executing discovery candidates."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil

from .errors import ConverterError

TOOLS = ('psp-gcc', 'psp-fixup-imports', 'psp-prxgen', 'psp-strip')
REQUIRED = tuple('bin/' + name + '.exe' for name in TOOLS) + (
    'psp/sdk/include/pspkernel.h', 'psp/sdk/include/pspimport.s',
    'psp/sdk/lib/prxspecs', 'psp/sdk/lib/linkfile.prx',
    'psp/sdk/lib/prxexports.o', 'psp/sdk/lib/libpspgu.a', 'psp/lib/libc.a',
)


class NativeToolchain:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        missing = [name for name in REQUIRED if not (self.root/name).is_file()]
        if missing:
            raise ConverterError('toolchain', 'Incomplete native PSP toolchain: ' + ', '.join(missing),
                                 'Choose the portable toolchain folder containing bin/ and psp/.')

    def tool(self, name):
        if name not in TOOLS:
            raise ConverterError('toolchain', 'Unsupported native tool: ' + str(name))
        return self.root/'bin'/(name + '.exe')

    def env(self):
        result = dict(os.environ)
        for key in ('GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH',
                    'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
                    'DEPENDENCIES_OUTPUT', 'SUNPRO_DEPENDENCIES', 'PSPSDK'):
            result.pop(key, None)
        result['PSPDEV'] = str(self.root)
        result['PSPSDK'] = str(self.root/'psp'/'sdk')
        result['PATH'] = str(self.root/'bin') + os.pathsep + result.get('PATH', '')
        return result

    def fingerprint(self):
        """Content identity covers compiler subprograms, headers and target libraries."""
        digest = hashlib.sha256()
        for path in sorted(self.root.rglob('*')):
            if path.is_file():
                digest.update(path.relative_to(self.root).as_posix().encode('utf8') + b'\0')
                with path.open('rb') as f:
                    while chunk := f.read(1024 * 1024):
                        digest.update(chunk)
                digest.update(b'\0')
        return digest.hexdigest()


def resolve(path=None):
    """An explicit broken SDK is an error; never fall back to WSL or Docker."""
    if isinstance(path, NativeToolchain):
        return path
    if path:
        return NativeToolchain(path)
    if os.environ.get('DCRC_TOOLCHAIN'):
        return NativeToolchain(os.environ['DCRC_TOOLCHAIN'])
    package = Path(__file__).resolve().parents[1]
    for candidate in (package/'toolchain', package.parent/'toolchain'):
        if candidate.is_dir():
            return NativeToolchain(candidate)
    if os.environ.get('PSPDEV'):
        return NativeToolchain(os.environ['PSPDEV'])
    compiler = shutil.which('psp-gcc.exe')
    if compiler:
        return NativeToolchain(Path(compiler).parent.parent)
    raise ConverterError('toolchain', 'No native PSP toolchain found.',
                         'Select the portable toolchain folder. WSL is not required.')
