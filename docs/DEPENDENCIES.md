# Dependencies and source locations

`dependencies.json` records public source/licence locations and the version
identities examined during preparation. A recorded licence SHA identifies that
licence document, not a compiler/archive checksum. No dependency executable,
SDK installation, proprietary runtime or game material is vendored here.

## Required for the current Windows converter

- [CPython](https://www.python.org/downloads/): Python3.11+; the tested embedded
  interpreter family was3.14.3. Source/licensing: [CPython](https://github.com/python/cpython).
- [Pillow](https://github.com/python-pillow/Pillow), [pyelftools](https://github.com/eliben/pyelftools):
  versions in requirements.txt. pyelftools' vendored Construct has its own notice.
- Optional GUI: [Qt for Python](https://doc.qt.io/qtforpython-6/), PySide6-Essentials
  and Shiboken versions in requirements-gui.txt. Use the LGPL distribution and
  retain its complete notices/source requirements when making a binary package.
- A native Windows PSP homebrew SDK: `bin/psp-gcc.exe`, `psp-fixup-imports.exe`,
  `psp-prxgen.exe`, `psp-strip.exe`, PSPSDK headers/libraries and target libc.
  Select it with `--toolchain`, or DCRC_TOOLCHAIN. It is an external installation.

## PSP toolchain sources

The authoritative homebrew project is [PSPDEV](https://pspdev.github.io/):
[installation](https://pspdev.github.io/installation.html),
[master build repository](https://github.com/pspdev/pspdev),
[Allegrex toolchain](https://github.com/pspdev/psptoolchain-allegrex),
[PSPSDK](https://github.com/pspdev/pspsdk).
GCC/binutils/newlib and host dependencies keep their own licences; PSPSDK's BSD
notice does not relicense the complete toolchain.

Official PSPDEV builds primarily document Unix-like hosts. Those SDKs can be used
with the CMake development route; the present converter adapter requires native
Windows tools and does not silently invoke WSL/Docker. A publicly documented
Windows/MSYS2 source-build candidate is
[dmang-dev/pspdev-win](https://github.com/dmang-dev/pspdev-win) (MIT entry scripts,
underlying components retain their own licences). It is a community port,
not an official PSPDEV binary or an already validated drop-in DCRC SDK.
Its documented tools need the MSYS2 runtime. Inspect/pin its source, build/install
outside this repository, record all component licences and run DCRC doctor plus
compile/link checks before adopting it. Do not blindly execute a fetched script.

The original development machine's compiler package/build receipts are not
public dependencies. This repository provides no unverifiable private SDK path
or binary download. If an exact supported host package cannot be established,
use `.agents/skills/dcrc-dependency-research/SKILL.md` to research current primary
sources and produce a reviewed build recipe; report the gap instead of guessing.

## Optional development tools

- [CMake](https://cmake.org/), [Ninja](https://ninja-build.org/), a host C compiler;
  [SDL2](https://github.com/libsdl-org/SDL) and system OpenGL for desktop graphics.
- [PPSSPP](https://www.ppsspp.org/) for functional/visual checks, not PSP speed.
- [Ghidra](https://github.com/NationalSecurityAgency/ghidra) and open SH-4 binutils
  for analysis of locally supplied inputs. No commercial disassembler or private
  MCP/debugger installation is assumed by the agent skills.
- [Dream-Recomp](https://github.com/phobos665/dream-recomp), GPLv2, for optional
  separate discovery; the normal converter already has a facts-only profile and
  its own emitter. [Flycast](https://github.com/flyinghead/flycast), GPLv2, is an
  external reference emulator. Their implementations are not copied into MIT HLE.
- [PSPLink USB](https://github.com/pspdev/psplinkusb) for explicitly coordinated
  device diagnostics; its BSD patch sources are optional. No device action is
  authorized merely by installing a tool or opening a skill.

## When a link fails

Use the repository dependency-research skill. Check the maintainer's current
repository, releases, licence at the exact revision and official replacements.
Record changed URLs/version/source checksums and verify the required interface.
Do not turn a mirror, a similar package or a proprietary SDK into an assumed
replacement. If no permitted implementation/information is found, keep the
feature unavailable and record the open research task.
