# Source provenance and reviewed profile

`audit/PROVENANCE.json` records a category, licence, source/revision and SHA256
for each proposed public file. Categories are O (own implementation), F (facts)
and T (permitted third-party source). This register is backed by human/agent
source review; a scanner or an MIT header alone is not proof of authorship.

The baseline is CountAllegrex's MIT sa1-psp commit
`c3d128badaa9906f919e27345ad908d50785e1f8`. The public tree starts with fresh
Git history; private development history, captures, local paths, receipts and
compiled products are not imported.

## Deliberate exclusions

Eight upstream accelerator files described ordered native replacements for
game bodies: collision list/sweep/ray/SET scanning and four TA transform/mesh/
strip-writer files. They are not distributed. Their eleven Block-A wrap entries
are removed; address-only facts remain, allowing the own emitter to generate
the originals on the user's computer. Generic TA/banked/2D wrappers remain.

The resulting reviewed profile uses the TA parser. Native static-distance
reduction is not supported, so the UI/CLI retain full100% distance rather than
advertising an inactive control. World texture caps still transform selected
user assets locally. Performance parity with other native variants is unproved.

The PSP backend also has an own guarded boot-tile sampler path. In non-strict
mode 1, live segalogo0..5 images qualify only at 256x256 RGB565, with linear
filtering and no flips. The path clamps effective sampler wrap in both aspect
modes, resolving the current texture name at each qualifying bind. It preserves
raw draw state, UVs and geometry and includes no texture bytes. Own-disc visual
and physical PSP acceptance remain separate from this source review.

The optional external download-event decoder, example oracle instruction tails,
game-body optimization specifications, captured console identifier and unverified
artwork are excluded. BIOS behavior uses a synthetic software identifier, no ROM
font/flash dump. The optional-content adapter mounts opaque user files and contains
no payload decoder. Its original game-side loader/decoder is generated locally;
normal VMU selection is required. See IN_GAME_MENU.md for activation boundaries.

## Sound

The host mixer is a high-level voice/stream/bank implementation. Yamaha ADPCM
coefficients and AICA modulation parameters are numerical format/hardware facts,
corroborated by public MAME/Flycast sources. Mathematical gain/pitch relationships
do not import a game's instruction/register sequence. Runtime banks are read
from the user's files; no sample waveform or game-bank table is shipped.

Two compact LFO helper expressions had uncertain reference provenance. They are
replaced with an attributed BSD-3-Clause adaptation of
[MAME AICA](https://github.com/mamedev/mame/blob/df3bcbba30251a393d8bb33a356c6c2ee93c34e9/src/devices/sound/aica.cpp),
own deterministic noise and rounded nominal intervals. This changes the LFO
reference: phase, frequency, noise and audio parity have not been established
on hardware. It is not described as a lossless sound fix.

## Generic converter and platform additions

The updated frontend, bounded local media readers, automatic session logs and
owned worker orchestration are own code; pictures/audio and converted outputs
come only from the user's inputs. Digital remapping targets guest controls and
does not replace physical HOME or the platform menu chord.

The generic movie/WAV player and PSP display/audio ownership adapters are own
code using public PSPSDK APIs. Game-version filename/entry/result facts are
separate from the firmware-player implementation. Custom DBR1 side images and
dither policy contain no image pixels, private native mesh implementation or
proprietary SDK declarations. Exact reviewed files and modifications are in the
provenance register; other private modules are not transitively admitted.

The bounded sequence parser consumes the user's bank format and synthetic
fixtures; no captured bank, waveform or translated sound-driver body is supplied.
The public MAME-derived LFO header and its BSD notice remain a separate unchanged
component. Known texture-role rules use live metadata/name/size/format facts,
not embedded pictures or a universal lossless-quality claim.

A source audit and an actual local conversion are distinct from binary
redistribution review. FFmpeg/ATRAC/SDK source pointers do not certify every
possible selected compiler, codec or runtime DLL. Keep that complete component
review separate; source exports include no dependency executables.

## Boundaries

External GPL discovery/emulator/toolchain programs keep their licences and run
separately. Their executable/source code is not silently relabelled as MIT.
No proprietary SDK or leaked document is a prerequisite. Missing references are
researched through official/public licensed sources using the dependency skill.

This is a technical provenance/data-boundary review, not a blanket legal opinion.
Unresolved material must remain outside the proposed public export.
