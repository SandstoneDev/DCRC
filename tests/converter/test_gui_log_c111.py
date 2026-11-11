"""Owner regressions: live log follows output and diagnostics stay inside it."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'windows' if os.name == 'nt' else 'offscreen')
try:
    from PySide6 import QtCore, QtWidgets as W
    from gui.app import Window
except ImportError:
    W = None


@unittest.skipUnless(W, 'Embedded Qt runtime required')
class ConversionLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = W.QApplication.instance() or W.QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.w = Window(self.root/'gui.json')
        self.w.setAttribute(QtCore.Qt.WA_DontShowOnScreen)
        self.w.set_language('en')
        self.w.timer.stop()
        self.w.auto_check_timer.stop()
        self.w.tabs.setCurrentIndex(5)
        self.w.resize(900, 620)
        self.w.show()
        self.app.processEvents()

    def tearDown(self):
        self.w.close()
        self.app.processEvents()
        self.tmp.cleanup()

    def test_new_worker_output_scrolls_to_the_last_line(self):
        self.w.log.setPlainText('\n'.join(f'older line {i}' for i in range(400)))
        self.app.processEvents()
        bar = self.w.log.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        bar.setValue(0)
        self.w.job = 'Convert'
        self.w.task.post({'type': 'log', 'message': 'LATEST COMPILER OUTPUT'})
        self.w.poll()
        self.app.processEvents()
        self.assertEqual(bar.value(), bar.maximum())
        self.assertTrue(self.w.log.toPlainText().endswith('LATEST COMPILER OUTPUT'))

    def test_follow_output_also_works_at_the_log_retention_limit(self):
        self.w.log.setPlainText('\n'.join(f'older line {i}' for i in range(10000)))
        self.app.processEvents()
        bar = self.w.log.verticalScrollBar()
        bar.setValue(0)
        self.w.job = 'Convert'
        self.w.task.post({'type': 'log', 'message': 'LATEST RETAINED OUTPUT'})
        self.w.poll()
        self.app.processEvents()
        self.assertLessEqual(self.w.log.document().blockCount(), 10000)
        self.assertEqual(bar.value(), bar.maximum())

    def test_long_diagnostics_are_logged_without_expanding_the_footer(self):
        raw = '$ compiler ' + 'private/source/and/include/path/' * 150
        self.w.job = 'Convert'
        self.w.task.post({'type': 'log', 'message': raw})
        self.w.poll()
        self.app.processEvents()
        self.assertIn(raw, self.w.log.toPlainText())
        self.assertIn(raw, self.w.session_log.path.read_text(encoding='utf8'))
        self.assertNotEqual(self.w.inline_status.text(), raw)
        self.assertTrue(self.w.inline_status.isHidden())
        self.assertLess(self.w.next.geometry().bottom(), self.w.centralWidget().height())

    def test_one_open_folder_button_and_no_manual_save_requirement(self):
        buttons = self.w.tabs.widget(5).findChildren(W.QPushButton)
        self.assertFalse(any('Save' in button.text() for button in buttons))
        opened = []
        button = next(button for button in buttons if button.text() == 'Open logs folder')
        with patch('gui.app.QtGui.QDesktopServices.openUrl', side_effect=lambda url: opened.append(url.toLocalFile()) or True):
            button.click()
        self.assertEqual([Path(name) for name in opened], [self.w.session_log.path.parent])
        self.assertNotIn(str(self.w.session_log.path), self.w.log_path.text())

    def test_log_write_failure_preserves_successful_result(self):
        from types import SimpleNamespace
        self.w.job='Convert'
        with patch.object(self.w.session_log,'write',side_effect=OSError('sensitive-unwritable-path')):
            self.w.task.post({'type':'finished','result':SimpleNamespace(folder=self.root/'output')})
            self.w.poll()
        self.assertEqual(self.w.stage.text(),'Complete')
        self.assertIn('Output:',self.w.log.toPlainText())
        self.assertIn('Session log is unavailable',self.w.log.toPlainText())
        self.assertNotIn('sensitive-unwritable-path',self.w.log.toPlainText())
        self.assertFalse(self.w.task.pending)

    def test_log_write_failure_preserves_primary_error(self):
        self.w.job='Convert'
        with patch.object(self.w.session_log,'write',side_effect=OSError('sensitive-unwritable-path')):
            self.w.task.post({'type':'error','message':'Primary conversion failure'})
            self.w.poll()
        self.assertIn('Primary conversion failure',self.w.stage.text())
        self.assertIn('Session log is unavailable',self.w.log.toPlainText())
        self.assertNotIn('sensitive-unwritable-path',self.w.log.toPlainText())

    def test_log_write_failure_preserves_playback_error(self):
        self.w.job='Prepare music preview'
        with patch.object(self.w.session_log,'write',side_effect=OSError('sensitive-unwritable-path')), patch('gui.media_picker.play_wav',side_effect=RuntimeError('Playback refused')):
            self.w.task.post({'type':'finished','result':self.root/'preview.wav'})
            self.w.poll()
        self.assertIn('Audio playback failed: Playback refused',self.w.stage.text())
        self.assertIn('Session log is unavailable',self.w.log.toPlainText())
        self.assertNotIn('sensitive-unwritable-path',self.w.log.toPlainText())

    def test_portable_startup_saves_automatically_beside_the_converter(self):
        from gui import run_gui
        bundle = self.root/'portable'
        (bundle/'python').mkdir(parents=True)
        (bundle/'app/gui').mkdir(parents=True)
        (bundle/'BUNDLE_MANIFEST.json').write_text('{}')
        (bundle/'app/gui/run_gui.py').write_text('# fixture')
        captured = []
        def start(session_log):
            captured.append(session_log.path)
            session_log.write('worker diagnostics persisted without a Save click')
            return 0
        with patch('sys.executable', str(bundle/'python/python.exe')), patch('gui.session_log.__file__',str(bundle/'app/gui/session_log.py')), patch.dict(os.environ, APPDATA=str(self.root/'appdata')), patch('gui.app.main', start):
            self.assertEqual(run_gui.main(), 0)
        self.assertEqual(captured[0].parent, bundle/'logs')
        self.assertEqual(list((bundle/'logs').glob('*.log')), captured)
        self.assertIn('without a Save click', captured[0].read_text(encoding='utf8'))

    def test_unwritable_portable_folder_falls_back_to_user_logs(self):
        from gui import run_gui
        bundle = self.root/'portable'
        (bundle/'python').mkdir(parents=True)
        (bundle/'app/gui').mkdir(parents=True)
        (bundle/'BUNDLE_MANIFEST.json').write_text('{}')
        (bundle/'app/gui/run_gui.py').write_text('# fixture')
        real_mkdir = Path.mkdir
        attempted = []
        def mkdir(path, *args, **kwargs):
            if path == bundle/'logs':
                attempted.append(path)
                raise PermissionError('fixture read-only installation')
            return real_mkdir(path, *args, **kwargs)
        captured = []
        with patch('sys.executable', str(bundle/'python/python.exe')), patch('gui.session_log.__file__',str(bundle/'app/gui/session_log.py')), patch.dict(os.environ, APPDATA=str(self.root/'appdata')), patch.object(Path, 'mkdir', mkdir), patch('gui.app.main', lambda session_log: captured.append(session_log.path) or 0):
            self.assertEqual(run_gui.main(), 0)
        self.assertEqual(attempted, [bundle/'logs'])
        self.assertEqual(captured[0].parent, self.root/'appdata/DCRC Converter/logs')
        self.assertTrue(captured[0].is_file())
