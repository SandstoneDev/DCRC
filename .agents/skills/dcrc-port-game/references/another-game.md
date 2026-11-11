# Another game: explicitly unfinished

DCRC currently hard-codes the supported profile in validation, generation and
packaging. It is not enough to add a TOML file, rename `sa1_us_1005`, copy Sonic
addresses or remove its hash gate. No second game's compatibility is claimed.

First make a private feasibility record from a user-authorized copy: exact
version hashes, boot format/load/entry facts, overlays, relocation rules, memory
map, interrupt/callback behaviour, SDK-call families and required asset formats.
Separate observed facts from hypotheses. Public Ghidra can aid local analysis;
its decompiler output remains private and is not rewritten into shipped C.

Research the title's actual disc revision and platform before selecting tools.
Start with public hardware documentation, maintainer repositories and the
game's own load/call evidence. For a community decompilation, record its target
region/version, source revision and per-component licence; compare function
behaviour, formats and callers against the supplied disc. A matching name or
address map for another revision is a lead, not a usable binding. Unlicensed
game/SDK reconstruction supplies research facts, not runtime code to copy.

Determine what is reusable and what is title-specific: disc reader, SH-4 ISA
semantics and process/receipt machinery may be reusable; function discovery,
HLE seams, save protocol, renderer inputs and asset policy need fresh proof.
Only introduce a profile registry/generalized validator when a real second
profile supplies its requirements. Keep the first profile's tests as controls.
Identify the concrete hard-coded callers in validation, generation, build and
packaging; a second profile must reach the real converter path, not an isolated
demo. Obtain tools through the [public dependency sources](public-resources.md)
and use the dependency-research skill when the required host build is missing.

A reviewed behavioural interface should state register/stack ABI, guest address
ranges, ownership/lifetimes, errors and callback ordering. Implement portable
synthetic tests before guest integration. An SDK stub that returns success while
discarding work does not establish a port. Do not link a confidential SDK or copy
an existing proprietary implementation to fill a seam.
Prove code coverage through overlay switches, physical/cached address aliases,
indirect function tables and co-resident modules. Audit outgoing service calls,
including save/error/callback operations and motion/renderer formats. Generate
from original local bytes only where a real fallback exists; unknown services
must remain reported as unsupported instead of becoming success stubs.

Use successive evidence gates: compatible input recognition; bounded extraction;
all required code units generated; real target linkage/import validation; verified
local folder; authorized title/menu/gameplay/save/audio/exit checks; then owner
hardware evaluation. Keep each result scoped. A boot screenshot, emulator speed
or one stage cannot prove a full story, another game or real PSP performance.

Publish only reviewed own/licensed runtime/tools and minimal compatibility facts.
If a required dependency or source is missing, use dependency research; record
the unresolved requirement instead of inventing a download or readiness claim.
