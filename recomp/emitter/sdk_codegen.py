"""Validate opt-in SDK function facts against the exact user-local image.

This contains no SDK implementation or game data. Generated bodies remain local
emitter outputs; ordinary HLE seams must never become selected code islands.
"""
import hashlib
import json

from sh4emit.image import phys


def load_sdk_functions(path, image, seams, sdk_range):
    """Return validated (entry, end, origin) facts; never discover extra bodies."""
    with open(path, encoding='utf8') as stream:
        value = json.load(stream)
    if not isinstance(value, dict) or set(value) != {'schema', 'image_sha256', 'functions'}:
        raise ValueError('unknown SDK catalog schema or fields')
    if type(value['schema']) is not int or value['schema'] != 1:
        raise ValueError('unsupported SDK catalog schema')
    if value['image_sha256'] != hashlib.sha256(image.data).hexdigest():
        raise ValueError('SDK catalog image hash mismatch')
    rows = value['functions']
    if not isinstance(rows, list) or not rows:
        raise ValueError('empty SDK function catalog')
    lo, hi = map(phys, sdk_range)
    known = {phys(a) for a in seams}
    result = []
    for row in rows:
        if not isinstance(row, dict) or not {'entry', 'end'} <= set(row) <= {'entry', 'end', 'origin'}:
            raise ValueError('invalid SDK function fields')
        try:
            if not isinstance(row['entry'], str) or not isinstance(row['end'], str):
                raise ValueError()
            raw = [int(row[k], 16) for k in ('entry', 'end')]
            if any(a not in (phys(a), phys(a) | 0x80000000, phys(a) | 0xA0000000) for a in raw):
                raise ValueError()
            entry, end = map(phys, raw)
        except (TypeError, ValueError):
            raise ValueError('invalid SDK function addresses') from None
        origin = row.get('origin', 'sdk-fallback')
        if not isinstance(origin, str) or not origin:
            raise ValueError('invalid SDK function origin')
        if entry & 1 or end & 1 or not lo <= entry < end <= hi or not image.contains(entry, end - entry):
            raise ValueError('SDK function extent outside permitted image range')
        if any(entry <= seam < end for seam in known):
            raise ValueError('SDK function overlaps an existing HLE seam')
        result.append((entry | 0x80000000, end | 0x80000000, origin))
    result.sort()
    if any(left[1] > right[0] for left, right in zip(result, result[1:])):
        raise ValueError('duplicate or overlapping SDK functions')
    return result


def check_sdk_program(program, selected):
    """Reject accidental extra SDK bodies or statically unresolved SDK exits."""
    extents = {phys(entry): phys(end) for entry, end, _ in selected}
    expected = set(extents)
    actual = {entry for entry in program.cfgs if program.in_sdk(entry)}
    if actual != expected:
        raise ValueError('emitted SDK functions differ from the explicit catalog')
    for entry in expected:
        analysis = program.analyses[entry]
        for block in analysis.cfg.blocks.values():
            if block.kind == 'stop':
                raise ValueError('selected SDK function stops or falls off its code range')
            for ins in block.all_instrs():
                if not entry <= ins.pc < extents[entry]:
                    raise ValueError('selected SDK instruction leaves its declared extent')
                if (not program.image.contains(ins.pc, 2)
                        or ins.word != program.image.u16(ins.pc)):
                    raise ValueError('selected SDK instruction was replaced by a fallback NOP')
            if block.branch is not None and block.branch.is_delayed:
                if block.slot is None or block.branch.pc + 2 >= extents[entry]:
                    raise ValueError('selected SDK function omits a required delay slot')
        if any(call.kind == 'sdk_dead' for call in analysis.calls.values()):
            raise ValueError('selected SDK function calls an unlisted SDK target')
        for block in analysis.cfg.blocks:
            for target, _ in analysis.exit_targets(block):
                if (program.in_sdk(target) and target not in expected
                        and target not in program.seam and target not in program.extern):
                    raise ValueError('selected SDK function exits to an unlisted SDK target')
