---
name: dcrc-release-audit
description: Audit an explicitly requested DCRC source export or portable release candidate for game-derived content, private data, third-party provenance and reproducible package integrity. This skill does not authorize publication or deployment.
---

# Audit a DCRC release candidate

Work on a new export/candidate, preserving source and private witnesses. State
the exact scope: source tree, portable tools, documentation or locally generated
game output. A successful local game conversion is not a distributable game build.

Use [the release boundaries](references/release-boundaries.md). Start from an
explicit file allowlist, not a recursive repository copy with guessed exclusions.
Review source content as well as filenames: a renamed/compressed payload, generated
C, SDK transcription or byte array is still derived content.

Check every actual third-party component against its revision's licence and
source/build provenance. Retain CountAllegrex's MIT notice. Distinguish licence
compliance from authorship/derivation review. Do not infer that an entire SDK,
wheel or inherited runtime has one licence from its top-level label.

Run the repository's applicable public-clean checks and independently inspect
the candidate. Validate archive membership, SHA256/size and source bindings.
For a portable app, verify isolated paths, GUI/CLI entry points and dependency
resolution using the candidate's own interpreter/tools, with no game job on open.
Use explicit `-B` for child Python invocations under isolated `._pth`.
For optional FFmpeg/ATRAC tools, bind the packaged binaries to their exact
sources, patches, build options and complete notices. Verify selected local
media and opaque DLC do not enter the source/tool archive. Review advertised
features against current capability gates and functional evidence; compilation,
download and package readback do not establish gameplay compatibility.

Report findings with exact relative file locations, completed checks and limits.
If content/provenance is unresolved, mark the affected candidate unready; do not
erase private originals or silently relabel licences. Prepare the concrete local
result, then leave any unrequested commit/push/upload/deploy unperformed.
