"""The source bundle is an allowlist, never a filtered repository copy."""
import os,subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from converter.build_bundle import source_files, copy_sources, portable_pth, build, digest, ENTRY_POINTS, SDK_REQUIRED


class BundleTests(unittest.TestCase):
    def test_whitelist_and_game_bytes_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'source'
            names = ('dcrc/pipeline.py', 'gui/app.py', 'backend/psp/main_psp.c',
                     'hle/ninja/texture.c', 'recomp/emitter/sh4emit/emit.py',
                     'converter/support/me_import.S', 'tools/convert_assets.py',
                     'work/secret.py', 'build/secret.c', 'private/game.py', '.git/config',
                     'dcrc/data/1ST_READ.BIN', 'hle/test.PBP', 'recomp/generated/game.c',
                     'gui/__pycache__/app.pyc', 'backend/psp/game.BLB',
                     'dcrc/data/generated.c', 'recomp/sa1_us_1005/game.c')
            for name in names:
                p = root/name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(name.encode())
            chosen = {p.relative_to(root).as_posix() for p in source_files(root)}
            self.assertEqual(chosen, set(names[:7]))
            out = Path(tmp)/'out'
            manifest = copy_sources(root, out)
            self.assertEqual(len(manifest), 7)
            self.assertEqual((out/'gui/app.py').read_bytes(), b'gui/app.py')
            with self.assertRaises(FileExistsError):
                copy_sources(root, out)

    def test_symlink_outside_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'source'
            (root/'dcrc').mkdir(parents=True)
            target = Path(tmp)/'secret.py'
            target.write_text('private')
            try:
                (root/'dcrc/x.py').symlink_to(target)
            except OSError:
                self.skipTest('symlink permission unavailable')
            with self.assertRaises(ValueError):
                list(source_files(root))

    def test_python_search_path_has_only_new_app(self):
        pth = portable_pth('python314.zip')
        self.assertIn('../app', pth)
        self.assertNotIn('PS2RC', pth)
        self.assertNotIn('import site', pth)

    def test_isolated_paths_import_own_nested_movie_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle, foreign = root/'bundle', root/'foreign_checkout'
            python = bundle/'python'
            python.mkdir(parents=True)
            for base, name, text in (
                (bundle, 'app/dcrc/__init__.py', ''),
                (bundle, 'app/dcrc/movies.py', 'from tools import movie_pmfmux\nvalue = movie_pmfmux.ORIGIN\n'),
                (bundle, 'app/source/tools/movie_pmfmux.py', 'ORIGIN = "own bundled tooling"\n'),
                (foreign, 'tools/__init__.py', ''),
                (foreign, 'tools/movie_pmfmux.py', 'ORIGIN = "wrong old checkout"\n'),
                (foreign, 'checkout_only.py', 'raise AssertionError("foreign dependency")\n'),
            ):
                path = base/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding='utf8')
            pth = python/'python._pth'
            pth.write_text(portable_pth(), encoding='utf8')
            # Use only the exact portable path entries, with hostile cwd/PYTHONPATH.
            # No source checkout, host site-packages or old bundle supplies tools.
            code = ("import sys; from pathlib import Path; "
                    "p=Path(sys.argv[1]); "
                    "sys.path=[str((p.parent/x).resolve()) for x in p.read_text().splitlines()]; "
                    "import dcrc.movies; assert dcrc.movies.value=='own bundled tooling'; "
                    "exec('try: import checkout_only\\nexcept ModuleNotFoundError: pass\\nelse: raise AssertionError(\"foreign path leaked\")'); "
                    "print(dcrc.movies.value)")
            env = dict(os.environ, PYTHONPATH=str(foreign))
            result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(pth)],
                                    cwd=foreign, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'own bundled tooling')

    def test_complete_layout_is_new_and_manifest_readback_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, python, tc, licenses = [root/n for n in ('source', 'python', 'sdk', 'licenses')]
            def put(base, name, text='synthetic'):
                path = base/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            for name in ('LICENSE', 'converter/README.md', 'gui/run_gui.py', 'dcrc/__main__.py',
                         'dcrc/data/profile.json', 'dcrc/data/world.policy', 'backend/psp/main.c',
                         'converter/support/me_import.S', 'tools/land_convert.py', 'work/secret.py'):
                put(src, name)
            for name in ENTRY_POINTS:
                put(src, name)
            for name in ('python.exe', 'pythonw.exe', 'python314._pth',
                         'Lib/site-packages/PySide6/QtWidgets.pyd',
                         'Lib/site-packages/PySide6/plugins/platforms/qwindows.dll'):
                put(python, name)
            put(python, 'python314._pth', '../old-private-app\n')
            for name in ('bin/psp-gcc.exe', 'licenses/gcc/COPYING', 'BUILDINFO.txt'):
                put(tc, name)
            for name in SDK_REQUIRED:
                put(tc, name)
            put(tc, 'work/secret.bin')
            put(python, 'private/secret.bin')
            for name in ('Python-LICENSE.txt', 'Qt/LGPL-3.0.txt', 'Qt/SOURCE.txt'):
                put(licenses, name)
            output = src/'work'/'new app Юникод'
            record = build(src, output, python, tc, licenses)
            self.assertFalse(record['game_data_included'])
            self.assertNotIn('python_origin', record)
            self.assertNotIn('toolchain_origin', record)
            self.assertTrue((output/'app/source/backend/psp/main.c').exists())
            self.assertTrue((output/'app/dcrc/data/world.policy').exists())
            self.assertTrue((output/'app/converter/support/me_import.S').exists())
            self.assertTrue((output/'app/source/converter/support/me_import.S').exists())
            self.assertFalse((output/'app/source/work').exists())
            self.assertFalse((output/'toolchain/work').exists())
            self.assertFalse((output/'python/private').exists())
            self.assertEqual((python/'python314._pth').read_text(), '../old-private-app\n')
            self.assertNotIn('old-private', (output/'python/python314._pth').read_text())
            for name, expected in record['files'].items():
                self.assertEqual(digest(output/name), expected)
            with self.assertRaises(FileExistsError):
                build(src, output, python, tc, licenses)
            (src/'dcrc/pipeline.py').unlink()
            with self.assertRaises(ValueError):
                build(src, root/'incomplete', python, tc, licenses)
            self.assertFalse((root/'incomplete').exists())

    def test_sdk_preflight_covers_native_resolver(self):
        from dcrc.toolchain import REQUIRED
        self.assertFalse(set(REQUIRED)-set(SDK_REQUIRED))


if __name__ == '__main__':
    unittest.main()
