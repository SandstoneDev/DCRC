# Compatibility and evidence boundaries

The implemented input profile is Sonic Adventure Dreamcast USA V1.005. Matching
boot/overlay hashes establish a compatible revision, not ownership or complete
game support. The public runtime uses TA rendering and full static distance100;
it excludes the private handwritten native accelerators. There is no claim of
performance or byte/visual/audio parity with other development builds.

## Current scope

- The profile has one main image, 77 code overlays, 78 function catalogues and
  45 additional SDK function bounds for local generation.
  No second game/version is enabled by changing a title or disabling its hash gate.
- Normal boot, menu, selected gameplay routes and PSP settings are the intended
  development path. Every story, character, boss, event and save transition has
  not been accepted on hardware.
- Chao Garden, Chao Race and thirteen upgrade scenes are part of the generated
  profile. Chao VMU services and Ninja screen printing run in the host adapter.
  Route coverage and portable save compatibility depend on functional testing.
- Movie playback, user-local side images, dithering and input remapping are
  exposed according to `dcrc/capabilities.py`. A new runtime option needs actual
  source/build/functional checks before its capability is enabled.
- Optional network events are downloaded/imported only as local opaque VMI/VMS
  inputs. A checked, downloaded or mounted entry is not verified playable DLC.
  Normal VMU selection and an ordinary scene load are required; the private
  event decoder is excluded from this public tree.

## Rendering, sound and acceptance

PSP games installed on the Memory Stick or internal storage use the shared
`PSP/DCRC_SAVES/SA1_US_1005` folder on that device. If it does not exist,
the first launch initializes it and copies this installation's recognized
legacy VMU files. Existing shared saves and the original legacy files are
preserved. An explicit `--vmu-dir` selects its own location.

World64/128 are deliberate reductions for selected assets; original textures
remain available. They do not establish a universal UI/actor classifier. Mip
reclaim under memory pressure, mirrored repeats and unrecognized UI/sky roles
can affect quality. Protecting known roles is not proof that every surface
retains its original detail or that allocation failure is impossible.

The host sound mixer and generic sequence parser read the user's local banks.
On PSP, the output worker keeps playback fed independently of guest frame
cadence when real-time mixing is enabled. The separately attributed public LFO
reference may differ in phase and noise. Hardware tests establish actual playback.

PPSSPP supplies functional and visual evidence. It may expose different memory
headroom from a real PSP. Its speed, a clear screenshot, API clock readback or
a successful frame-limit exit does not establish hardware speed, memory safety
under every route or full-game acceptance. Test actual PSP quality, gameplay,
audio, saves and clean exit on the intended device/settings.
