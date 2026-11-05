"""Portable resolution must not silently select WSL or execute candidates."""
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class ToolchainTest(unittest.TestCase):
    def api(self):
        try:
            return importlib.import_module('dcrc.toolchain')
        except ImportError:
            self.fail('native toolchain resolver is not implemented')

    def test_explicit_missing_never_falls_back(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(Exception):
                api.resolve(Path(d) / 'missing')

    def test_relative_root_normalized_and_tool_hashes_not_version_only(self):
        api = self.api()
        with tempfile.TemporaryDirectory(prefix='DCRC sdk ') as d:
            p = Path(d)
            for rel in api.REQUIRED:
                f = p / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b'fixture')
            tc = api.resolve(p)
            self.assertTrue(tc.tool('psp-gcc').is_absolute())
            self.assertEqual(tc.env()['PSPDEV'], str(p.resolve()))
            before = tc.fingerprint()
            tc.tool('psp-gcc').write_bytes(b'changed')
            self.assertNotEqual(tc.fingerprint(), before)

    def test_build_environment_excludes_external_gcc_headers_and_executables(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for rel in api.REQUIRED:
                f = p/rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b'fixture')
            with patch.dict(os.environ,{'GCC_EXEC_PREFIX':'untrusted','CPATH':'other-sdk','LIBRARY_PATH':'other-sdk'}):
                env = api.resolve(p).env()
            self.assertTrue('GCC_EXEC_PREFIX' not in env)
            self.assertTrue('CPATH' not in env)
            self.assertTrue('LIBRARY_PATH' not in env)


if __name__ == '__main__':
    unittest.main()
