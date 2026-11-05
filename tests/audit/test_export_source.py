"""Source export must use exactly the audited Git view."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

TOOLS = Path(__file__).resolve().parents[2] / 'tools'
sys.path.insert(0, str(TOOLS))
from export_source import export


class ExportSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'audit').mkdir()
        (self.root / 'README.md').write_text('Synthetic source fixture\n', encoding='utf8')
        (self.root / '.gitignore').write_text('private/\n', encoding='utf8')
        self.records = {}
        for name in ('README.md', '.gitignore'):
            self.record(name)
        self.ledger()

    def record(self, name):
        data = (self.root / name).read_bytes()
        self.records[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'category': 'O', 'license': 'MIT', 'source': {
                'url': 'https://github.com/SandstoneDev/DCRC', 'revision': 'synthetic-test', 'path': name},
            'review': 'Synthetic test fixture, no game data'}

    def ledger(self):
        (self.root / 'audit/PROVENANCE.json').write_text(json.dumps({'schema': 1, 'files': self.records}), encoding='utf8')

    def test_export_readback_and_reproducibility(self):
        first, second = self.base / 'first.zip', self.base / 'second.zip'
        report = export(self.root, first)
        export(self.root, second)
        self.assertEqual(report['files'], 3)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(set(archive.namelist()), {'DCRC/.gitignore', 'DCRC/README.md', 'DCRC/audit/PROVENANCE.json'})
            self.assertEqual(archive.read('DCRC/README.md'), (self.root/'README.md').read_bytes())

    def test_ignored_record_cannot_expand_export(self):
        (self.root / 'private').mkdir()
        (self.root / 'private/notes.txt').write_text('Private local notes', encoding='utf8')
        self.record('private/notes.txt')
        self.ledger()
        out = self.base / 'forbidden.zip'
        with self.assertRaises(ValueError):
            export(self.root, out)
        self.assertFalse(out.exists())

    def test_hook_permissions_survive_source_archive(self):
        (self.root/'.githooks').mkdir()
        name='.githooks/pre-commit'
        (self.root/name).write_text('#!/bin/sh\nexit 0\n', encoding='utf8')
        self.record(name)
        self.ledger()
        out=self.base/'hooks.zip'
        export(self.root,out)
        with zipfile.ZipFile(out) as archive:
            info=archive.getinfo('DCRC/'+name)
            self.assertEqual(info.create_system,3)
            self.assertEqual((info.external_attr >> 16) & 0o777,0o755)
            self.assertEqual((archive.getinfo('DCRC/README.md').external_attr >> 16) & 0o777,0o644)

    def test_dirty_unknown_source_rejected(self):
        (self.root/'extra.py').write_text('print(1)\n', encoding='utf8')
        with self.assertRaises(ValueError):
            export(self.root, self.base/'unknown.zip')

    def test_output_inside_tree_rejected(self):
        with self.assertRaises(ValueError):
            export(self.root, self.root/'source.zip')

    def test_existing_export_preserved(self):
        out = self.base/'existing.zip'
        out.write_bytes(b'Existing owner file')
        with self.assertRaises(FileExistsError):
            export(self.root, out)
        self.assertEqual(out.read_bytes(), b'Existing owner file')


if __name__ == '__main__':
    unittest.main()
