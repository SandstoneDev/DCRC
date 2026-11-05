# Release boundaries and meaningful checks

| Material | Source/tool release treatment |
|---|---|
| Reviewed own code/docs | Include with the project's licence and retained upstream attribution |
| Compatibility facts | Minimal hashes/addresses/bounds/formats only; inspect for embedded instructions/IR |
| Third-party code/binaries | Include only within verified licence/source obligations; preserve notices |
| User disc, extracted files, generated game C/objects/EBOOT, converted assets, patches/captures | Keep local; do not include in a public source/tool archive |
| Proprietary SDK/BIOS/keys/confidential manuals or copied implementations | Exclude; do not replace missing dependencies with these |
| Private history, logs, saves, machine paths, credentials | Exclude or sanitize intentionally; do not publish private evidence directories |

Audit the whole proposed archive and any history proposed for publication, not
only the current tracked filenames. Scanner success is a useful check, not proof
of provenance or licence compliance. Do not rewrite/delete original history to
make a scan pass without the owner's explicit authorization.

An inherited MIT header does not make translated game code publishable. Examine
guest-specific routines and transplanted/decompiler-shaped helpers. If a routine
is excluded, test the real user-side generated fallback; a silent stub is not a
compatibility fix. Keep this distinction in release status.

For binaries, keep full component notices and exact source/build identities.
Inspect PE imports and actual loader paths; an ordinary import-table check does
not cover every delay-load, optional plugin or Windows version. Microsoft runtime
redistributables are separate from open-source Qt/Python; never label them MIT.
Under an open-source-only vendoring policy, leave non-open binaries out of the
source export and document verified prerequisites separately.

Preserve mutable player settings/saves during repair. Verify a new output with
the same work does not skip staging, and same-size corruption invalidates cache.
Confirm source snapshots remain unchanged during actual child-process work.

Use neutral own branding and referential compatibility names. Do not package
game artwork, music or screenshots as a launcher asset. Keep public issue reports
to sanitized diagnostics rather than memory dumps or generated game binaries.

Final status must distinguish source audit, portable smoke, own-disc functional
conversion and real PSP acceptance. A checked download link is not a checked
binary; a hash match is not a licence grant; an emulator result is not hardware FPS.
