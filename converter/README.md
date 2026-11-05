# DCRC Converter packaging

The source checkout contains no ready executable or dependency binaries. Build
and audit a local Windows package using the instructions below. An eventual
public binary archive is a separate component/licence/provenance review.

On 64-bit Windows, open **DCRC Converter.exe** (or **DCRC Converter.cmd**). Python, Qt and the native
PSP compiler are included alongside the app; no WSL or system Python is needed.
Keep the complete folder together. `dcrc.cmd --help` opens the same core as a CLI.
From a development checkout: `python gui/run_gui.py` with PySide6 installed.

Choose your own Sonic Adventure **US v1.005 GDI and its track files**, check the
version, choose settings and an exact new PSP game folder, then Convert. Other
versions/formats are rejected. An extracted disc folder is an advanced option
with the same identity checks. No game files, generated game C or ready game
EBOOT are shipped. The converter builds from your own supported files locally.

Normal game boot and the explicitly labelled world64/full100 PSP preset are the defaults.
Original world textures preserve the source
assets; maximum64/128 affect selected Emerald Coast world assets and reduce
detail. This reviewed TA source profile currently requires static distance100. The explicit
PSP preset is world64/full distance100. These are quality choices; this app does
not promise a PSP frame rate. Runtime settings can be applied to an existing
owned output; changing world textures requires conversion again.

Cancel requests owned-process shutdown and waits for cleanup. Closing while a
job runs requests cancellation and keeps the window alive until it finishes.
Partial output is not marked ready. Work and diagnostics remain available for
resume. Nothing is automatically copied to a PSP/card or launched in an emulator.

Build a new local bundle with `python converter/build_bundle.py --out NEW_FOLDER
--python-from EMBEDDED_PYTHON --toolchain NATIVE_PSP_SDK --licenses LICENSES
--cc MINGW_GCC`. The source allowlist excludes work/build/private/.git and all
game binaries. The builder rejects existing output folders and writes a full
SHA256/size manifest. Bundle status is static validation, separate from a cold
functional conversion. The native host launcher is optional when building;
the .cmd launcher is always included. MinGW is a developer dependency only.

CPython, PySide6/Qt, Pillow, pyelftools and the PSP compiler/SDK keep their own
notices under `licenses/`. Qt libraries remain separate replaceable files;
their exact source links and LGPL text are included. The upstream runtime's
MIT notice is retained. No PS2RC source implementation is copied into this GUI.
Public distribution requires a separate final provenance/dependency audit.
