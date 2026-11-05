"""Import user-local opaque VMI/VMS pairs for the supported US profile.

No payload decoding, keys, bundled event data, archive extraction or downloads.
Outer checks match hle/game/optional_content.c; the original guest remains the
authority on payload region, stage and character compatibility. SONICADV_5xx
is the US loader's discoverable filename family, not a decoded-region claim.
"""
from pathlib import Path
import binascii
import hashlib
import os
import re
import struct

from .errors import ConverterError
from .storage import file_digest, fingerprint, plain_path, reject_links

MAX_EVENTS = 32
MAX_IMAGE = 200 * 512
MAX_FILES = 4096


def _digest(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def _read(path, low, high, reason):
    path = plain_path(path)
    if not path.is_file():
        raise ConverterError('content_source', 'Content input is not a regular file.')
    size = path.stat().st_size
    if not low <= size <= high:
        raise ValueError(reason)
    with path.open('rb') as stream:
        data = stream.read(high + 1)
    if len(data) != size or path.stat().st_size != size:
        raise ConverterError('content_changed', 'Content input changed while reading.')
    return data


def _files(root):
    paths = []
    scanned = 0
    for folder, dirs, names in os.walk(root, followlinks=False, onerror=_walk_error):
        dirs.sort(key=lambda s: (s.casefold(), s))
        scanned += len(dirs) + len(names)
        if scanned > MAX_FILES:
            raise ConverterError('content_limit', 'Content folder exceeds the 4096-entry scan bound.')
        for name in dirs + names:
            reject_links(Path(folder) / name)
        for name in names:
            path = Path(folder) / name
            if path.is_file():
                paths.append(path.relative_to(root).as_posix())
    return sorted(paths, key=lambda s: (s.casefold(), s))


def _walk_error(error):
    raise ConverterError('content_source', 'Cannot enumerate the content folder.', str(error)) from error


def _outer(meta, image):
    canonical = meta[88:100].decode('ascii', errors='replace')
    if not re.fullmatch(r'SONICADV_[0-9A-F]{3}', canonical):
        raise ValueError('invalid_canonical_name')
    if canonical[9] != '5':
        raise ValueError('unsupported_us_name_family')
    n = len(image)
    if n % 512:
        raise ValueError('vms_block_boundary')
    if struct.unpack_from('<I', meta, 104)[0] != n:
        raise ValueError('vmi_declared_size')
    if struct.unpack_from('<H', image, 0x40)[0] != 1:
        raise ValueError('vms_icon_count')
    if struct.unpack_from('<H', image, 0x44)[0] != 0:
        raise ValueError('vms_eyecatch')
    if struct.unpack_from('<I', image, 0x48)[0] != n - 640:
        raise ValueError('vms_payload_size')
    expected = struct.unpack_from('<H', image, 0x46)[0]
    if expected and binascii.crc_hqx(image[:0x46] + b'\0\0' + image[0x48:], 0) != expected:
        raise ValueError('vms_crc')
    return canonical


def _label(meta, canonical, used):
    text = meta[4:36].split(b'\0', 1)[0].decode('ascii', errors='replace')
    text = ' '.join(re.sub(r'[^ -~]|\|', ' ', text).split()) or canonical
    if text.startswith('#') or text.casefold() in ('off', 'none') or text.isdecimal():
        text = canonical + ' ' + text
    base, number = text[:63], 1
    text = base
    while text.casefold() in used:
        number += 1
        suffix = f' [{number}]'
        text = base[:63-len(suffix)] + suffix
    used.add(text.casefold())
    return text


def inspect_content(source_dir: Path):
    """Return portable catalog, explicit skips and content fingerprint; no writes.

    Entries use source-relative vmi/vms paths and SHA256/byte digests. Exact
    duplicate pairs are skipped; canonical-name collisions with other bytes
    remain separate choices. Unsupported/invalid pairs are never called valid.
    Symlinks/junctions and unreadable input fail the inspection, not just a row.
    """
    root = plain_path(source_dir)
    if not root.is_dir():
        raise ConverterError('content_source', 'Choose an existing folder of VMI/VMS pairs.')
    try:
        paths = _files(root)
        by_name = {}
        for relative in paths:
            by_name.setdefault(relative.casefold(), []).append(relative)
        entries, skipped, paired, seen, labels = [], [], set(), set(), set()
        for relative in paths:
            if Path(relative).suffix.casefold() != '.vmi':
                continue
            partner = str(Path(relative).with_suffix('.vms')).replace('\\', '/')
            matches = by_name.get(partner.casefold(), [])
            metadata_matches = by_name[relative.casefold()]
            paired.update(matches)
            reason = 'missing_vms' if not matches else None
            if len(matches) > 1 or len(metadata_matches) > 1:
                reason = 'ambiguous_case_insensitive_pair'
            if reason:
                skipped.append({'path': relative, 'reason': reason})
                continue
            try:
                meta = _read(root/relative, 108, 108, 'vmi_size')
                image = _read(root/matches[0], 1024, MAX_IMAGE, 'vms_size')
                canonical = _outer(meta, image)
            except ValueError as error:
                skipped.append({'path': relative, 'reason': str(error)})
                continue
            md, vd = _digest(meta), _digest(image)
            identity = (md['sha256'], vd['sha256'])
            if identity in seen:
                skipped.append({'path': relative, 'reason': 'duplicate_pair'})
                continue
            seen.add(identity)
            if len(entries) == MAX_EVENTS:
                skipped.append({'path': relative, 'reason': 'catalog_limit'})
                continue
            entries.append({'label': _label(meta, canonical, labels), 'canonical': canonical,
                            'vmi': relative, 'vms': matches[0], 'vmi_digest': md, 'vms_digest': vd})
        for relative in paths:
            if Path(relative).suffix.casefold() == '.vms' and relative not in paired:
                skipped.append({'path': relative, 'reason': 'missing_vmi'})
        result = {'format': 'DCRC_CONTENT_V1', 'entries': entries, 'count': len(entries),
                  'skipped': sorted(skipped, key=lambda e: (e['path'].casefold(), e['path']))}
        result['fingerprint'] = fingerprint(result)
        return result
    except OSError as error:
        raise ConverterError('content_source', 'Cannot read the selected content folder.', str(error)) from error


def stage_content(source_dir: Path, destination_data: Path, *, expected_fingerprint=None):
    """Create NEW data/dlc only; preserve existing data and all user input.

    Report files are data-relative SHA256/byte digests, including events.txt.
    No existing dlc path is adopted or overwritten. Failure leaves any partial
    new output unclaimed; callers must not issue a successful package receipt.
    Content may mount but still be declined by the guest's original parser.
    """
    source, destination = plain_path(source_dir), plain_path(destination_data)
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ConverterError('content_path', 'Content input and output folders must not overlap.')
    target = destination/'dlc'
    reject_links(target)
    if target.exists():
        raise ConverterError('content_output', 'The output already contains dlc; choose a new content staging folder.')
    report = inspect_content(source)
    if expected_fingerprint is not None and report['fingerprint']!=expected_fingerprint:
        raise ConverterError('content_changed','DLC input changed after the pipeline cache key was computed.')
    if not report['entries']:
        raise ConverterError('content_empty', 'No supported US-family VMI/VMS pairs were found.',
                             'Inspect the selected folder; non-5xx names and invalid containers are unsupported.')
    # Freeze bounded selected bytes before output writes and compare inspection
    # digests, so changed input cannot silently stage under an older fingerprint.
    frozen = []
    for entry in report['entries']:
        pair = []
        for kind, low, high in (('vmi',108,108), ('vms',1024,MAX_IMAGE)):
            try:
                data = _read(source/entry[kind],low,high,'changed_size')
            except (ValueError, OSError) as error:
                raise ConverterError('content_changed', 'Content input changed before staging.') from error
            if _digest(data) != entry[kind+'_digest']:
                raise ConverterError('content_changed', 'Content input changed before staging.')
            pair.append(data)
        frozen.append(pair)
    try:
        destination.mkdir(parents=True, exist_ok=True)
        target.mkdir()  # exclusive claim, including a concurrent creator
        (target/'events').mkdir()
        files, entries, lines = {}, [], []
        for index, (entry, buffers) in enumerate(zip(report['entries'], frozen)):
            staged = dict(entry)
            for kind, data in zip(('vmi','vms'), buffers):
                relative = f'dlc/events/event{index:02}.{kind}'
                with (destination/relative).open('xb') as stream:
                    stream.write(data)
                expected = _digest(data)
                if file_digest(destination/relative) != expected:
                    raise ConverterError('content_readback', 'Content copy failed SHA256/size readback.')
                files[relative] = expected
                staged[kind] = relative
            entries.append(staged)
            lines.append(f"{entry['label']}|{staged['vmi']}|{staged['vms']}\n")
        catalog = ''.join(lines).encode('ascii')
        with (target/'events.txt').open('xb') as stream:
            stream.write(catalog)
        if file_digest(target/'events.txt') != _digest(catalog):
            raise ConverterError('content_readback', 'Content catalog failed SHA256/size readback.')
        files['dlc/events.txt'] = _digest(catalog)
        return dict(report, entries=entries, files=files)
    except OSError as error:
        raise ConverterError('content_output', 'Could not create the new content staging directory.', str(error)) from error
