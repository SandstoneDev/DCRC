# DCRC contributor and coding-agent guide

DCRC converts a supported user-supplied Dreamcast disc into a locally built PSP
folder. Read README.md, LICENSE and CREDITS.md first. The implemented profile is
Sonic Adventure US v1.005; another game's port is research until separately proved.

## Find the responsible layer

* `dcrc/`: shared CLI, disc/profile validation, generation, native build, owned
  work/output, receipts and verification. `python -B -m dcrc --help` lists commands.
* `gui/`: PySide6 frontend. It calls the same core, without automatic conversion.
* `recomp/emitter/`: own SH-4 emitter/runtime; `dcrc/data/` and `recomp/sa1_us_1005/`:
  compatibility facts/configuration. Generated game C is a local output.
* `hle/`, `backend/`: reviewed runtime/HLE and platform code. A licence header
  does not by itself establish that a routine is free of game-derived expression.
* `converter/`: source allowlist, portable packaging and own import declarations.
* `tests/converter/`: synthetic core/GUI/build tests. Run the relevant tests for
  a change; distinguish missing optional dependencies/skips from executed checks.

## Local data and correctness

Keep discs, extracted files, generated game code, objects, game executables,
converted assets, saves, captures and private diagnostics outside the public
source tree. Keep input media unchanged. Never add these to a source archive or
Git history. Hash checks establish supported compatibility, not ownership.

Reject unsupported inputs before output writes. Preserve foreign folders and
unknown player files. Use content hashes and sizes for receipts/readback; size
or timestamps alone do not validate a cache. Keep mutable settings independent
of immutable inputs. Cancellation owns exact processes and waits for cleanup.

Embedded Python can ignore environment variables through `._pth` isolation.
Pass `-B` explicitly to Python workers and emitters; verify that a complete run
does not add bytecode to a frozen source snapshot. Keep work outside the output.

Rendering changes must preserve near geometry, actors, UI, audio/gameplay and
the current full-detail option unless the user explicitly chooses a quality
change. Label texture/distance reductions. Emulator functionality and PC build
time do not establish real PSP speed or hardware acceptance.

## Skills and external information

Repository skills are plain Markdown under `.agents/skills/`. Use:

* `dcrc-port-game` for the existing pipeline or a proposed Dreamcast-to-PSP port.
* `dcrc-dependency-research` for missing tools, dead links or dependency selection.
* `dcrc-release-audit` for an explicitly requested source/package release review.

If an agent cannot discover project skills automatically, read the relevant
SKILL.md directly. Do not assume a globally installed private skill, MCP server,
debugger or machine-specific SDK exists. Public PSPSDK documentation and project
source are the PSP references; no confidential SDK manuals or copied SDK code.

Record source URL, revision/version, licence and SHA256 for third-party material.
An inaccessible page is not evidence that a dependency is abandoned. Research
the maintainer's official replacement; do not silently substitute another SDK,
an unlicensed mirror or an unrelated package with a similar name.

## Scope and delivery

Continue authorized local work without repeated confirmation. Keep build,
emulator and device coordination explicit when multiple contributors are active.
Do not commit, push, publish, deploy or contact third parties without authorization
for that action. A release audit does not itself authorize publication.

Report what changed, which checks actually ran and what remains unproved. Use
relative project paths and neutral examples in public documentation. Preserve
CountAllegrex's upstream MIT notice and each component's actual notices.
