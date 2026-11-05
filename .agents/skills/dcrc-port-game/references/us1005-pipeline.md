# Current implemented profile and API

The supported ID is `sa1_us_1005`. Inspect `dcrc/profiles.py` and the corresponding
`dcrc/data/` manifest for exact boot/overlay hashes. GDI plus its tracks is the
primary input; an extracted folder uses the same compatibility gate. Another
region/version is not accepted by changing a label or disabling verification.

The flow is identify/hash → bounded extraction → own main/overlay SH-4 emission →
native compile/link plus helpers → local assets/settings/package → full readback.
Game C, EBOOT and assets are made on the user's machine, never supplied as a
prebuilt game. Inspect current source before relying on an older design document.

## Entry points

* `dcrc.models.ConversionOptions`: source/output/work/toolchain, profile, jobs,
  title and graphics/audio/startup fields; validate in the core.
* `dcrc.pipeline.identify(source, event=None, cancel_event=None)`: compatibility
  dict; unsupported input is explicit. Cancellation must remain cancellation.
* `dcrc.pipeline.convert(options, event=None, cancel_event=None)`: result includes
  folder/manifest/work; `output` is the exact PSP game folder.
* `dcrc.package.verify_folder(folder)`: SHA256/size result. `configure_folder`
  updates supported runtime settings; changing world assets needs conversion.
* `dcrc.process.CommandRunner`: shell-free owned subprocess execution and cancel.
* `dcrc.generate.generate`: reads the user's verified bytes and address catalogs.
* `dcrc.native_build.build`: actual game plus helper build; reject incomplete
  generation instead of falling back to a hello/demo build.
* `dcrc.runtime_source`: explicit source snapshot; `converter/build_bundle.py`:
  portable allowlist, own launcher, independent dependency files and manifest.

Events are dicts with type/message and optional stage/progress. GUI worker events
cross to the UI through its queue; Qt widgets stay on the GUI thread. Closing
requests cancellation and waits for cleanup. Opening the app does not start a job.

## Example source commands

Use paths chosen by the user; keep local work/output outside the public tree:

```text
python -B -m dcrc doctor --toolchain ../native-psp-sdk --json
python -B -m dcrc identify ../own-disc/disc.gdi --json
python -B -m dcrc convert ../own-disc/disc.gdi --out ../local-psp/DCRC_Port --work ../local-work/job --toolchain ../native-psp-sdk --preset psp
python -B -m dcrc verify ../local-psp/DCRC_Port --json
python -B -m unittest discover -s tests/converter -p "test_*.py"
```

In a portable Windows folder, use `dcrc.cmd` or its own `python/python.exe -B`.
Do not accidentally mix global Python, another SDK's headers or a private cache.
An isolated `._pth` can ignore environment-only bytecode suppression: inspect the
actual Python argv of workers and emitters and verify no new frozen-source files.

The PSP preset selects world64/full distance100; original world assets remain an
explicit choice. The curated world policy applies to selected Emerald Coast
assets and all their consumers, not an unproved universal actor/UI classifier.
This source profile uses the TA renderer and accepts full distance100 only.
Normal game boot is the default; advanced stage/character/act combinations are
not all normal routes.

For regressions, cover same-size corruption, changed output, changed settings,
cancel of a silent child, cleanup-before-close, foreign output and player saves.
Run a full own-disc conversion when the authorized task needs it; record actual
readback and functional exit, not merely compilation or a frame-limit message.
