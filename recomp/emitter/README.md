# Own SH-4 emitter and runtime

This MIT implementation from CountAllegrex's sa1-psp decodes SH-4 instructions,
builds control-flow/data-flow information and emits C from a user-supplied
executable. Its architecture and ABI helpers are source; emitted game bodies
are user-local output. No game translation is distributed in this directory.

Use `python -B -m dcrc convert` for the supported complete pipeline. For
development, `emit_sa1.py` accepts explicit `--bin`, `--functions` and `--out`;
`emit_overlay.py` also accepts an overlay TOML and `--main-table`. Run either
script with `--help` for its current interface. Do not use `--update-hle` on
unreviewed generated data in a public checkout.

`sh4emit/` contains ISA decoding, register effects, CFG, lowering and formatting.
`runtime/` is the C ABI the local generated files use. The input profile supplies
function boundaries and host bindings. Hardware facts should be verified against
the public Renesas SH-4 software manual and tested with independently authored
instruction vectors; do not replace missing documentation with proprietary SDK
material. The project's dependency-research skill covers missing/dead references.

Synthetic emitter checks live in `tests/emitter/`. Real game or BIOS-derived
fixtures, FSCA tables, generated C and compiled game objects are never fixtures
for the public repository.
