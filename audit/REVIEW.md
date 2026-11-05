# Source preparation review

The source view has per-file SHA256/size, licence, category and provenance
records in PROVENANCE.json. The publication gate checks working files, actual
staged blobs and all available Git objects; it rejects unknown provenance,
private host paths, common credential patterns, executable/game payloads,
links and the known excluded translations. A fresh repository contains no
private development history. Empty-index checks cover zero staged files.

Human/agent review covered runtime/HLE, emitter/profile facts, converter/GUI,
developer tools, documentation and portable skills. The explicit exclusions and
changed TA/audio profile are explained in docs/PROVENANCE.md. Machine checks do
not establish authorship or detect every possible encoded payload.

The reviewed source completed a cold user-disc conversion with no stage-cache
hits. The resulting normal boot and Emerald Coast route completed bounded
functional runs in PPSSPP with final reports and clean process exit. Captures,
game outputs, build logs and the user disc remain outside this repository.
This is not real-PSP performance or audio acceptance. Source-only synthetic
tests and the auditor's negative/regression tests are provided for repetition.

Dependency source/licence URLs were checked during preparation. The catalogue
records licence-text hashes, not download-artifact hashes. External native
SDK binaries are not bundled; their exact local build recipe remains an
unresolved binary-distribution dependency. Research and validate an official
replacement before proposing a portable executable release. Source archive
export is a separate audited operation; no publication is implied.
