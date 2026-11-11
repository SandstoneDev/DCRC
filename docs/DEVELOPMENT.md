# Development

Use Python3.11+ and install `requirements.txt` and `requirements-dev.txt`. The optional GUI adds
`requirements-gui.txt`. Run tests from the repository root:

```sh
python -B -m pytest tests/converter tests/audit -q
python -B tests/emitter/run_tests.py
python -B tools/audit_release.py --root . --history
```

Some native/GUI tests require an explicitly selected SDK, host compiler or Qt.
Report skips as skips. Synthetic tests generate their fixtures in temporary
directories; never replace them with captured game/BIOS data. Real conversion
tests use the developer's supported image and an external/ignored work folder.

The converter runs: identify/full hashes → extract → main+58overlay emission →
optional local media → PSP compilation/link/helper/PBP → assets/XMB →
settings/package → readback. Network DLC acquisition is an explicit GUI/CLI
action; conversion itself consumes the resulting local input.
`dcrc.worker` is the owned long-stage subprocess entry. Both workers and emitters
need explicit `-B` because an embedded Python `._pth` may ignore environment-only
bytecode controls. Receipt keys bind input, code, profile and toolchain contents.

## Tools

The public tool sources support PRS/overlay analysis, local asset conversion,
texture diagnostics, input tapes, state/trace comparison, PSP profiling/addr2line,
host synthetic checks and optional PSPLink diagnostics. Commands take local
inputs; read each tool's `--help` or header before use. Device-specific tools
must receive an explicit device/path and are never part of automatic conversion.
A matching community decomp can help identify contracts, but its source/licence,
version and completeness need independent checks. Decompiled game/SDK bodies do
not become public HLE merely by renaming them. Chao code/service coverage remains
unsupported; see COMPATIBILITY.md.

Legacy optimization experiments and private captured data are not a development
dependency. Do not reconstruct missing data from a published receipt or invent
old performance results.

The optional desktop backend uses CMake, a C/C++ compiler, SDL2 and system OpenGL;
`SA1_NO_SDL` is a headless option. Configure `SA1_RECOMP_OUT` explicitly when
building a game. PSP CMake builds require the separately installed SDK toolchain
file; the Windows converter instead calls native tools directly without make.

## New game work

Read `.agents/skills/dcrc-port-game/SKILL.md`. Establish readable user input,
version hashes, executable/overlay bounds, independent SH-4 instruction tests,
host hardware/library contracts and a minimal functional route. Facts belong in
a profile; generated functions and translated library bodies stay local.
Do not copy proprietary SDK code or a decompiler-shaped function into HLE.
Prefer the existing emitter fallback when a native accelerator's provenance
cannot be established.

PPSSPP is a functional/visual aid. Measure drawn frames, real elapsed time,
game progress and stability on the actual PSP for acceptance. An intentional
quality reduction is labelled; missing near geometry, broken UI, sound,
gameplay/collision or unsafe memory/thread behavior is a bug.
