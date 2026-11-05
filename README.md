# DCRC

**Dreamcast → PSP converter and development toolkit.** A supported disc supplied
by the user is extracted, translated, compiled and converted locally into a PSP
folder. No game executable, generated game C or converted game assets are shipped.

**Based on [sa1-psp by CountAllegrex](https://github.com/countallegrex/sa1-psp).**
Its MIT emitter, runtime, HLE and backends are the foundation of this project.
See [CREDITS.md](CREDITS.md), [NOTICE.md](NOTICE.md) and [LICENSE](LICENSE).
The converter workflow was inspired by [PS2RC](https://github.com/SandstoneDev/PS2RC);
its custom-licensed implementation is not copied here.

## Status

This is a source-first preview. The first compatibility profile is **Sonic
Adventure, Dreamcast USA V1.005**, supplied as a GDI with its track files. Other
games and disc revisions are not automatically supported. No ready game download
is provided. Future source/binary releases must pass the publication audit.

The reviewed source profile deliberately uses locally translated original
functions instead of several handwritten native accelerators. Its supported
renderer is TA, with full static draw distance. A separately attributed BSD
reference LFO is used by the host sound mixer. Performance, LFO phase/noise and
audio parity are not asserted to match other builds. Rendering/memory/audio
issues remain; real PSP validation is required for speed and quality claims.

## What you need

- Your own supported GDI and its track files; the converter checks executable
  and overlay hashes before creating output. A hash identifies a version.
- Windows x64 and Python3.11+ for the current native Windows build adapter.
- A separately installed native PSP homebrew SDK containing `psp-gcc.exe`,
  PSPSDK headers/libraries and import/PRX tools. See [dependencies](docs/DEPENDENCIES.md).
- A PSP-2000/3000-class64MB target that runs homebrew. PSP-1000 is not supported
  by the current memory configuration. Hardware acceptance of a new build is
  separate from a successful local conversion.
- Several gigabytes of free local work space, plus the generated PSP folder.

## Convert your own disc

Install the source dependencies from the official Python package index:

```sh
python -m pip install -r requirements.txt
python -B -m dcrc doctor --toolchain "<native-PSP-SDK>"
python -B -m dcrc identify "<your-disc.gdi>"
python -B -m dcrc convert "<your-disc.gdi>" --out "<new-PSP-folder>" --toolchain "<native-PSP-SDK>"
```

For the optional window:

```sh
python -m pip install -r requirements-gui.txt
python -B gui/run_gui.py
```

Choose the GDI, check its version, choose graphics/audio/startup settings and an
exact new output folder, then **Convert / resume**. Normal game boot is the
default. Optional stage/character/act warps override it explicitly. World texture
caps64/128 affect selected Emerald Coast assets and reduce detail; original
textures are available. Reduced static distance is unavailable in this TA profile.

The resulting folder contains `EBOOT.PBP`, helpers and `data/`. Copy the complete
folder into `PSP/GAME` on your own device. Every game-derived result stays local;
do not share the generated PSP folder, generated C, saves or game captures.

In the PSP game, **L+R+Cross+Down** opens the control menu. Release all buttons,
then use L/R for pages and the D-pad to edit. Settings, bounded cheats, startup
level/character selection and opaque user-supplied DLC mounts are described in
[the menu guide](docs/IN_GAME_MENU.md). Optional `--dlc-dir` imports your own
extracted VMI/VMS folder locally. DLC activation requires normal VMU selection.

The source checkout itself contains no portable Windows executable/dependency
bundle. [converter/README.md](converter/README.md) describes local packaging and
the additional dependency/notice audit needed before any binary release.

## Settings, resume and recovery

```sh
python -B -m dcrc verify "<PSP-folder>"
python -B -m dcrc configure "<PSP-folder>" --stage normal --voice en
python -B -m dcrc repair "<PSP-folder>" --source "<your-disc.gdi>" --toolchain "<native-PSP-SDK>"
```

GUI and CLI use the same core. Complete stages are reused only after content
verification; changing the output folder still stages its files. Runtime settings
need no compilation; world texture changes repeat asset conversion. Player saves
and unknown files are preserved by repair. Cancellation shuts down owned processes
and keeps work for diagnosis. No converter action automatically deploys to a card.

## Development toolkit

| Location | Purpose |
|---|---|
| `dcrc/`, `gui/` | Shared converter and optional PySide6 window |
| `recomp/emitter/` | Own SH-4 decoder, CFG/lowering and C runtime ABI |
| `recomp/sa1_us_1005/`, `dcrc/data/` | Address/hash/format compatibility facts |
| `hle/`, `backend/` | Host HLE, TA parser, PSP/desktop backends |
| `tools/`, `tests/` | Analysis, generation, diagnostics and synthetic checks |
| `.agents/skills/` | Portable porting, dependency-research and release-audit skills |
| `audit/` | Reviewed per-file provenance and publication rules |

Read [AGENTS.md](AGENTS.md), [development](docs/DEVELOPMENT.md),
[provenance](docs/PROVENANCE.md) and [release audit](docs/RELEASE_AUDIT.md).
The toolkit is gradually extracted from a working first game. A second game has
not established general portability; adding a game requires analysis, bindings,
runtime work and tests, not just selecting another disc image.

## Credits and licences

Converter/frontend/integration: **SandstoneDev**. Foundation: **CountAllegrex**.
The project retains MIT notices for those portions and BSD-3-Clause notices for
the specifically identified adaptations. External tools keep their own licences.
[CREDITS.md](CREDITS.md) lists actual components and references, including the
PSPDEV community, MAME, Python, Qt/PySide, Pillow, pyelftools and test/discovery tools.

This project is not affiliated with or endorsed by SEGA or Sony. Compatibility
and platform names are used to identify supported inputs/targets; all marks and
commercial game materials remain with their respective owners.
