# DCRC Converter

## Start the portable converter

1. [Download the Windows x64 ZIP](https://github.com/SandstoneDev/DCRC/releases/download/v0.1.1/DCRC-Converter-Windows-x64-v0.1.1.zip).
2. Extract the entire archive into a writable folder.
3. Open **DCRC Converter.exe**.

The archive includes Python, Qt, the native PSP toolchain, FFmpeg, FFprobe
and the ATRAC encoder. It is ready to run from the extracted folder.

In the portable Windows app, **Check for updates** reads the official DCRC
GitHub release. **Download update** verifies the ZIP and installs it in a
new sibling folder. Open the updated converter from the same window.
Existing conversion outputs and the previous converter folder are preserved.

## Run from source

For a source checkout, open a terminal in the repository folder.

```powershell
python -m pip install -r requirements-gui.txt
python -B gui/run_gui.py
```

Use [the dependency guide](../docs/DEPENDENCIES.md) to install a compatible native
Windows PSP toolchain for source builds. Configure it through `DCRC_TOOLCHAIN`
or the advanced settings. CLI-only source use needs `requirements.txt`.

## Use the window

1. **Disc:** choose the supported US V1.005 GDI and its tracks. Identity is checked
   automatically and summarized in readable form. An extracted directory is an
   advanced input with the same hashes. Optional Find/Download DLC stays here;
   download has one progress dialog. Checked catalogue events are prepared by the
   final Convert task. Errors/cancellation never silently omit selected events.
2. **Output:** choose the exact new PSP game folder. Existing foreign folders and
   unknown player files are preserved. Work/SDK resolution is automatic in a
   complete portable layout; advanced fields permit explicit overrides. On
   Windows, a deeply nested output uses a work folder under local app data to
   keep compiler paths short. If a deep folder causes a missing source error,
   choose a short **Work folder** under **Advanced build options**.
3. **Appearance:** edit the local title, browse images from the supplied game or
   local files, audition music and choose its start/1–10 second clip. A custom
   side image is an optional local 4:3 setting. When converting into an existing
   DCRC output, the converter can keep a border that matches its manifest.
4. **Settings:** choose original or explicitly reduced world textures, aspect,
   audio/voice, frame skip and mips. This public TA profile requires full static
   distance100. Supported movie/border/dither controls follow the actual
   [capability table](../dcrc/capabilities.py); other profiles are not assumed.
5. **Controls:** assign PSP digital buttons to Dreamcast actions. Analog movement,
   physical HOME and the DCRC menu chord keep their platform roles.
6. **Convert:** the final navigation button starts conversion with in-window
   progress and a following log. Cancel waits for owned processes to stop;
   partial output is not marked ready. Closing during a job requests cancellation.

One dated session log is saved automatically, including worker/compiler output.
Use **Open logs folder**. The portable app writes beside itself in `logs`; a
source/read-only launch uses the application-data fallback. There is no manual
Save requirement. Logs can include local paths and should be redacted before
publication. Source captures, saves and game binaries are not bug-report attachments.

GUI and CLI use the same core. CLI defaults to title-only/no optional XMB media
and no movie conversion; select media explicitly when wanted. FFmpeg/ffprobe is
used for preview/movie/audio conversion; an external ATRAC encoder produces XMB
music. Explicit tool paths take priority over the app's own tools, then PATH.
Tools from a different embedded interpreter are not adopted as this app's bundle.

The PSP preset is world64/full100. World64/128 reduce selected Emerald Coast
assets and their consumers; they are quality choices, not lossless optimizations
or frame-rate guarantees. Normal startup is default. Warps do not establish
that every stage/character route, Chao or DLC is supported. Read
[compatibility](../docs/COMPATIBILITY.md) and [the PSP menu guide](../docs/IN_GAME_MENU.md).

## Build a local portable package

Use a new output folder and separately audited dependencies:

```text
python -B converter/build_bundle.py --out ../local-converter --python-from ../embedded-python --toolchain ../native-psp-sdk --licenses ../component-notices --cc ../host-compiler/bin/gcc.exe
```

Optional `--ffmpeg-dependency` and `--atrac-dependency` select dependency folders
with the builder's required manifests, source identities and notices. These
options validate the actual selected files; they do not grant redistribution
rights or supply an SDK. No binaries, firmware, generated C or game assets are
added to this repository. An exact per-component source/build/licence inventory
is required before publishing a portable binary.

The source allowlist excludes Git internals and work/build/private data. The
builder rejects an existing destination and reads back its SHA256/size manifest.
A static bundle check is distinct from a complete own-disc conversion and actual
PSP acceptance. Qt remains in separate replaceable files with its own notices.
Nothing is automatically installed on a device or launched in an emulator.
