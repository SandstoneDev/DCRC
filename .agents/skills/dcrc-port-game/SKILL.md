---
name: dcrc-port-game
description: Develop DCRC's supported Dreamcast-to-PSP conversion pipeline or investigate a new Dreamcast game profile. Use for disc/profile, SH-4 emission, HLE, native PSP build and converter integration; do not treat other games as already supported.
---

# Develop a DCRC game port

Read repository AGENTS.md and locate the requested layer before editing. Use
the existing converter API instead of creating a second GUI-only pipeline.
Inspect the checkout's [capability table](../../../dcrc/capabilities.py) and
profile facts before planning a feature: a CLI flag, successful conversion or
compiled helper does not establish an accepted runtime path.

For PSP menu/aspect/startup and opaque DLC mounting, read docs/IN_GAME_MENU.md.
Keep explicit CLI precedence and ordinary VMU activation requirements; do not
restore excluded payload decoders or promise live character replacement.

For the implemented profile, read [the current pipeline](references/us1005-pipeline.md).
For another title/version, read [the new-game boundary](references/another-game.md).
For PSP/dependency facts, use [public resources](references/public-resources.md).

Keep the user's disc, disassembly, decompiler output, generated C, game binaries
and captures in private local work. A public profile contains compatibility
facts only; it cannot smuggle instructions or game data as JSON, arrays or patches.
Do not replace an unimplemented guest function with silent success to obtain a
boot claim. Implement from a reviewed behaviour contract or keep a genuine
user-side generated fallback, then test the observable path.
An unavailable fallback remains an explicit compatibility gap. Cover required
overlay callbacks and services such as save access and animated model drawing;
loading their textures alone does not make those routes supported.

For a change, establish the relevant failure/behaviour, make the narrow change,
and run checks that distinguish the intended result from stale-cache success.
Use synthetic tests where possible. Own-disc builds and functional runs require
the user's authorized input and test scope; no automatic emulator or card action.

Bind results to input/profile/runtime/toolchain/settings/output content. Preserve
guest timing, IRQ and audio contracts. Display submissions or guest vblanks are
not automatically visible frames. State observation gaps and measurement limits.

Finish with the supported behaviour, evidence and outstanding compatibility work.
Do not claim a generic second-game porter or PSP performance from a PC run.
