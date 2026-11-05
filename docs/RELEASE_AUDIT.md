# Publication audit

The repository is source-only. Audit the exact working view, index and object
database separately before a source export or authorized push:

```sh
python -B tools/audit_release.py --root . --history
python -B tools/audit_release.py --root . --staged
python -B tools/export_source.py --root . --out "../DCRC-source.zip"
```

Configure `core.hooksPath` to `.githooks` to use the local checks. CI repeats
checks after an authorized publication; CI is not a substitute for the local
review before data leaves the machine. Reports must not print matched secrets.

On Unix, enable the hooks with `chmod +x .githooks/pre-commit .githooks/pre-push`.
The source archive records executable modes for hook and shell scripts; retain
them when extracting. The exporter requires an exact provenance/source-view
match, writes only a new external archive, excludes Git internals and ignored
files, and reads back every entry. It does not publish the archive.

The gate checks provenance coverage/content hashes, host paths, credentials,
unreviewed files, unsafe links, generated/binary material and known excluded
sources. Staged mode reads actual index blobs, so cleaning only the working
file does not hide a staged secret. History mode also examines unreachable
objects; it is a content check, not a retroactive licence review for every old
commit. A fresh empty repository has zero historical objects, not a magic
certificate that future commits are safe.

Every new/changed public file needs its provenance entry reviewed and updated.
Do not automatically classify all files as own, suppress a finding by renaming,
or add a blanket path exclusion. Keep real user images, generated C, executable
ports, saves, captures, logs, credentials and private dependency installations
outside the public tree and index. `.gitignore` never clears an already tracked
secret. Stop publication and preserve evidence if an unresolved item remains.

The self-register is scanned as content but cannot contain its own recursive
SHA. Synthetic source tests may contain recognizer strings and constructed
malformed inputs; review context rather than treating a parser literal as a dump.

Binary packages are a separate inventory. Audit every actual component, licence,
source offer, notice and data boundary. The local bundle builder is not a legal
or provenance clearance tool. Microsoft runtime DLLs, proprietary tools, game
art and game-derived results must not be placed in an open-source-only export.
No audit command authorizes commit, push, deployment or publication by itself.
