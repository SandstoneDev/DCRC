# Notices and scope

Substantial portions originate in CountAllegrex's MIT-licensed
[sa1-psp](https://github.com/countallegrex/sa1-psp), baseline
`c3d128badaa9906f919e27345ad908d50785e1f8`.
The complete original notice is retained in `LICENSES/sa1-psp-MIT.txt`.
New converter, GUI, source-packaging and agent-toolkit work is by SandstoneDev.

`hle/sound/sound_lfo.h` adapts the amplitude-wave definitions in MAME's AICA
implementation, revision `df3bcbba30251a393d8bb33a356c6c2ee93c34e9`, under
BSD-3-Clause. Copyright holders: ElSemi, Deunan Knute, R. Belmont; thanks to
kingshriek. The full notice remains in that header. Its deterministic noise and
rounded frequency projection are identified adaptations, not a hardware-parity
claim. This file is not relicensed by the root MIT notice.

The optional PSPLink patches retain their upstream BSD notices. Public PSPSDK
ABI declarations use separately installed open homebrew headers/import macros.
No proprietary console SDK, ROM/BIOS/font dump or custom-firmware implementation
archive is included. SDK/debug-font notices must accompany a binary distribution
when applicable; obtain all dependency notices from the corresponding sources.

Compatibility catalogs contain entry/end addresses, discovery origins, hashes,
bounds and asset identifiers. Dream-Recomp GPLv2 discovery was a separate tool;
its program source/executable is not linked or copied into the MIT emitter.
Flycast and PPSSPP were research/test references, not relicensed source donors.

The reviewed tree excludes known manual game-body transcriptions and the
optional external-DLC decoder. Their input-side functions are emitted locally
from the user's supported disc where applicable. Generated game code/assets,
compiled game programs, states and captured fixtures are never public inputs.

The root MIT licence covers the applicable source code and documentation in
this repository. Sonic Adventure, its executable, its assets, the Sega Katana
SDK and code generated from them remain the property of their respective
owners. No upstream claim of ownership or accuracy overrides a file-level
provenance review.
