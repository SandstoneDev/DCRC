#!/usr/bin/env python3
"""Export the audited source view, without Git internals or ignored local data."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from audit_release import audit, MANIFEST, _git


def export(root, out):
    root, out = root.resolve(), out.resolve()
    if out == root or root in out.parents:
        raise ValueError('Source export must be outside the checkout')
    report = audit(root, history=True)
    if not report['ok']:
        raise ValueError('Source audit failed; inspect tools/audit_release.py output')
    manifest = json.loads((root / MANIFEST).read_text(encoding='utf8'))
    names = sorted(set(manifest['files']) | {MANIFEST})
    view = {name.decode('utf8') for name in
            _git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0') if name}
    if set(names) != view:
        raise ValueError('Provenance inventory must exactly match the audited source view')
    contents = {name: (root / name).read_bytes() for name in names}
    for name, data in contents.items():
        if name != MANIFEST:
            record = manifest['files'][name]
            if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('Source changed during export')
    if not audit(root, history=True)['ok'] or any((root/name).read_bytes() != data for name,data in contents.items()):
        raise ValueError('Source changed during export')
    with zipfile.ZipFile(out, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            item = zipfile.ZipInfo('DCRC/' + name, date_time=(1980, 1, 1, 0, 0, 0))
            executable = name.startswith('.githooks/') or name.endswith('.sh')
            item.create_system = 3
            item.external_attr = (0o100755 if executable else 0o100644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data)
    with zipfile.ZipFile(out) as archive:
        if archive.namelist() != ['DCRC/' + name for name in names]:
            raise ValueError('Export inventory mismatch')
        for name, data in contents.items():
            if archive.read('DCRC/' + name) != data:
                raise ValueError('Export readback mismatch')
    return {'status': 'PASS', 'files': len(names), 'bytes': out.stat().st_size,
            'sha256': hashlib.sha256(out.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.root, args.out), indent=2))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, type(error).__name__ + ': source export failed\n')


if __name__ == '__main__':
    main()
