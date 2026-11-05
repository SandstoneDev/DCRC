# First compatibility profile

The supported input is the user's own Sonic Adventure USA V1.005 GDI with its
track files. `dcrc/data/sa1_us_1005/profile.json` identifies the executable and
58 decoded overlays by size/SHA256. Those hashes establish compatibility.

The profile contains addresses, ranges, names and function-discovery origins,
not instructions, IR, game images or generated source. Discovery originally
used Dream-Recomp as a separate GPLv2 program; see CREDITS.md. Conversion now
uses this repository's own MIT SH-4 emitter and the address-only catalogs.

The source distribution omits manual native transcriptions of several game
functions. Their address facts remain in the catalogs, while their native-wrap
bindings are absent. A local conversion therefore emits the original bodies
from the supplied executable. The supported renderer is TA; reduced native
static-distance experiments are not enabled by this source profile. Optional
external DLC payload loading is also omitted. These differences must not be
described as a performance-equivalent replacement for another local build.

Run the shared converter for ordinary use; it passes explicit input/output
arguments to both main and overlay emitters. No ambient private dump path is
required. Generated C belongs only in an ignored or external work directory.
