# Another game: explicitly unfinished

DCRC currently hard-codes the supported profile in validation, generation and
packaging. It is not enough to add a TOML file, rename `sa1_us_1005`, copy Sonic
addresses or remove its hash gate. No second game's compatibility is claimed.

First make a private feasibility record from a user-authorized copy: exact
version hashes, boot format/load/entry facts, overlays, relocation rules, memory
map, interrupt/callback behaviour, SDK-call families and required asset formats.
Separate observed facts from hypotheses. Public Ghidra can aid local analysis;
its decompiler output remains private and is not rewritten into shipped C.

Determine what is reusable and what is title-specific: disc reader, SH-4 ISA
semantics and process/receipt machinery may be reusable; function discovery,
HLE seams, save protocol, renderer inputs and asset policy need fresh proof.
Only introduce a profile registry/generalized validator when a real second
profile supplies its requirements. Keep the first profile's tests as controls.

A reviewed behavioural interface should state register/stack ABI, guest address
ranges, ownership/lifetimes, errors and callback ordering. Implement portable
synthetic tests before guest integration. An SDK stub that returns success while
discarding work does not establish a port. Do not link a confidential SDK or copy
an existing proprietary implementation to fill a seam.

Use successive evidence gates: compatible input recognition; bounded extraction;
all required code units generated; real target linkage/import validation; verified
local folder; authorized title/menu/gameplay/save/audio/exit checks; then owner
hardware evaluation. Keep each result scoped. A boot screenshot, emulator speed
or one stage cannot prove a full story, another game or real PSP performance.

Publish only reviewed own/licensed runtime/tools and minimal compatibility facts.
If a required dependency or source is missing, use dependency research; record
the unresolved requirement instead of inventing a download or readiness claim.
