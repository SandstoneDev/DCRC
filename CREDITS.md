# Credits and component licences

## Project foundation

DCRC builds on **CountAllegrex's [sa1-psp](https://github.com/countallegrex/sa1-psp)**:
its SH-4 emitter/runtime, HLE and PSP/desktop backends provide the project's
foundation. Preserve the upstream MIT licence and the notice
`Copyright (c) 2026 CountAllegrex` in substantial copies. The repository LICENSE
does not grant rights to any commercial game, its assets or proprietary SDKs.

The converter, GUI, native Windows build adapter, portability integration,
publication audit and portable agent kit are by **SandstoneDev**.

The reviewed `sound_lfo.h` adapts MAME AICA amplitude-wave generation under
BSD-3-Clause: **ElSemi, Deunan Knute and R. Belmont**, with thanks to
**kingshriek**. Source revision
[`df3bcbba30251a393d8bb33a356c6c2ee93c34e9`](https://github.com/mamedev/mame/blob/df3bcbba30251a393d8bb33a356c6c2ee93c34e9/src/devices/sound/aica.cpp).
The full notice remains in the header. The new LFO reference is not asserted to
match console sound phase/noise. See docs/PROVENANCE.md.

DCRC's converter, frontend and integration work retain their applicable project
notices. PS2RC inspired the converter workflow; its custom-licensed implementation
and unrelated dependency list are not copied into this project.

Historical compatibility discovery used
[Dream-Recomp](https://github.com/phobos665/dream-recomp), separately, at
revision `51a148c7bf9191fa8593e707c4996cf887076b33`.
Its [licence at that revision](https://raw.githubusercontent.com/phobos665/dream-recomp/51a148c7bf9191fa8593e707c4996cf887076b33/LICENSE)
is GPLv2. The converter uses the own emitter and fact catalogs; Dream-Recomp is
not linked or required at runtime. This credit is not a claim that GPL source
has been relicensed as MIT.

## Converter and optional portable components

The source repository and a binary distribution are different inventories.
Include only components actually selected for an archive; keep their complete
licence files, version identities, source pointers and required exceptions.

| Component | Role and licence scope | Primary source |
|---|---|---|
| CPython / Python Software Foundation and contributors | Converter interpreter; PSF licence and bundled third-party notices | [Python licensing](https://docs.python.org/3/license.html) |
| Qt, PySide6, Shiboken / The Qt Company and contributors | Optional GUI/portable runtime; selected LGPLv3 distribution with separate replaceable libraries; retain full notices/source requirements | [Qt for Python licences](https://doc.qt.io/qtforpython-6/licenses.html) |
| Pillow / PIL contributors | Included in the inspected Python dependency set; MIT-CMU plus the wheel's complete third-party notices | [Pillow](https://pillow.readthedocs.io/en/stable/about.html) |
| pyelftools and contributors | ELF/DWARF developer tooling dependency; public-domain/Unlicense text; its vendored Construct has a separate licence | [pyelftools](https://github.com/eliben/pyelftools) |
| PSPDEV / PSPSDK contributors | Public homebrew headers, libraries and build tools; PSPSDK BSD-style three-clause notice, with separate toolchain component licences | [PSPDEV](https://pspdev.github.io/), [PSPSDK](https://github.com/pspdev/pspsdk) |
| GNU GCC and GNU binutils contributors | Native cross-compilation tools; retain the applicable GPL/LGPL texts and GCC runtime exceptions | [GCC](https://gcc.gnu.org/), [binutils](https://sourceware.org/binutils/) |
| newlib / libgloss contributors | Target C runtime; per-file permissive and other notices in COPYING.NEWLIB/COPYING.LIBGLOSS | [PSP newlib fork](https://github.com/pspdev/newlib) |
| pthread-embedded and its contributors | SDK threading component; inspect its LGPL/exception/per-file notices rather than calling the SDK all-BSD | [pthread-embedded](https://github.com/pspdev/pthread-embedded) |
| GMP, MPFR and MPC contributors | Statically included compiler dependencies in the inspected native toolchain; retain applicable LGPL/GPL notices and source obligations | [GMP](https://gmplib.org/), [MPFR](https://www.mpfr.org/), [MPC](https://www.multiprecision.org/mpc/) |
| ISL contributors | Compiler dependency; MIT notice in the inspected toolchain | [ISL](https://libisl.sourceforge.io/) |
| MinGW-w64 / winpthreads contributors | Windows host compiler/launcher support; mixed ZPL/BSD/public-domain/LGPL and other per-file notices | [MinGW-w64](https://www.mingw-w64.org/) |
| zlib and Zstandard contributors | Notices present in the inspected Windows toolchain; preserve them when that component set is redistributed | [zlib](https://www.zlib.net/), [Zstandard](https://github.com/meta/zstd) |

The inspected Pillow wheel's full notice also identifies Brotli, FreeType,
HarfBuzz, Little CMS, libavif, libjpeg-turbo, libpng, libwebp, OpenJPEG, TIFF,
XZ and zlib-ng. Retain that complete notice and required FreeType attribution;
do not replace it with a one-line MIT label. Qt and CPython also contain their
own third-party notices; the component manifests, not this overview, govern
their exact binary contents.

Some CPython/Qt Windows distributions include Microsoft Visual C++ runtime DLLs.
Those are Microsoft redistributables, not open-source DCRC, CPython or Qt code.
Do not vendor them in an open-source-only source export. Any separately proposed
portable binary package must identify and satisfy their own redistribution terms.
See [Microsoft's redistribution documentation](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170).

Public CFW ABI tables are references for the own minimal import declarations in
`converter/support/`; no CFW implementation archive is thereby included or
relicensed. Preserve the declarations' provenance and review actual linked inputs.

## Development-only or optional tools

Desktop builds can use SDL2 (zlib licence) and the system OpenGL implementation;
they are not requirements of the native PSP converter. See
[SDL licensing](https://www.libsdl.org/license.php) and [OpenGL](https://www.khronos.org/opengl/).
[CMake](https://cmake.org/documentation/), [Ninja](https://ninja-build.org/),
[MSYS2](https://www.msys2.org/) and MinGW-w64 support development/packaging when
selected. Their installation does not make them shipped runtime components.

[Ghidra](https://github.com/NationalSecurityAgency/ghidra),
[KallistiOS](https://github.com/KallistiOS/KallistiOS) and
[PPSSPP](https://www.ppsspp.org/) are optional analysis/reference/test projects,
not bundled game data or mandatory runtime dependencies. Credit any actual
future source reuse according to the particular files' licences.

[Flycast](https://github.com/flyinghead/flycast) was an external Dreamcast
reference/oracle and a source of public hardware-parameter facts. Its GPL source
is not relicensed as this project's MIT code. Numerical Yamaha ADPCM parameters
are also corroborated by MAME's BSD AICA implementation. The emitter uses public
Renesas SH-4 ISA documentation, not another recompiler's implementation.

Optional PSPLink patch sources retain the BSD-3-Clause notice of the
[PSPLink USB project](https://github.com/pspdev/psplinkusb), including TyRaNiD
and contributors. They are development-only sources; no PSPLink binary, custom
firmware or proprietary console SDK is shipped here.

[SA Tools / Sonic Adventure Toolset](https://github.com/X-Hax/sa_tools) by
X-Hax and contributors provided public format references for model handling.
[Marcus Comstedt's Dreamcast programming notes](https://mc.pp.se/dc/)
provided BIOS interface facts. These are reference credits, not incorporated
tool implementations or permission to copy proprietary game data. If a reference
is temporarily inaccessible, use the dependency-research skill before replacing it.

Commercial game, platform and publisher names identify compatibility only.
Their owners do not endorse this project. No game executable/assets, console
BIOS, keys or confidential SDK material are provided by this credit document.
