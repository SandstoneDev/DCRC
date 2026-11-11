# Compatibility and evidence boundaries

The implemented input profile is Sonic Adventure Dreamcast USA V1.005. Matching
boot/overlay hashes establish a compatible revision, not ownership or complete
game support. The public runtime uses TA rendering and full static distance100;
it excludes the private handwritten native accelerators. There is no claim of
performance or byte/visual/audio parity with other development builds.

## Current scope

- The reviewed profile has one main image and58code overlays/59function catalogues.
  No second game/version is enabled by changing a title or disabling its hash gate.
- Normal boot, menu, selected gameplay routes and PSP settings are the intended
  development path. Every story, character, boss, event and save transition has
  not been accepted on hardware.
- **Chao Garden/race are unsupported.** Their required program modules and some
  VMU/motion/render service contracts are outside the active profile. Entering
  those routes may trap. Adding an entry alone does not provide their dependency
  coverage; no silent success stub is substituted.
- Movie playback, user-local side images, dithering and input remapping are
  exposed according to `dcrc/capabilities.py`. A new runtime option needs actual
  source/build/functional checks before its capability is enabled.
- Optional network events are downloaded/imported only as local opaque VMI/VMS
  inputs. A checked, downloaded or mounted entry is not verified playable DLC.
  Normal VMU selection and an ordinary scene load are required; the private
  event decoder is excluded from this public tree.

## Rendering, sound and acceptance

World64/128 are deliberate reductions for selected assets; original textures
remain available. They do not establish a universal UI/actor classifier. Mip
reclaim under memory pressure, mirrored repeats and unrecognized UI/sky roles
can affect quality. Protecting known roles is not proof that every surface
retains its original detail or that allocation failure is impossible.

The host sound mixer and generic sequence parser read the user's local banks.
The separately attributed public LFO reference may differ in phase/noise. No
complete sound/voice parity claim follows from a note request or nonzero PCM.

PPSSPP supplies functional and visual evidence. It may expose different memory
headroom from a real PSP. Its speed, a clear screenshot, API clock readback or
a successful frame-limit exit does not establish hardware speed, memory safety
under every route or full-game acceptance. Test actual PSP quality, gameplay,
audio, saves and clean exit on the intended device/settings.
