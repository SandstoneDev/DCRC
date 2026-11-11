"""Checked network DLC must reach conversion rather than silently disappear."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'windows' if os.name == 'nt' else 'offscreen')
try:
    from PySide6 import QtCore, QtWidgets as W
    from gui.app import Window
except ImportError:
    W = None


@unittest.skipUnless(W, 'Embedded Qt runtime required')
class SelectedDlcConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = W.QApplication.instance() or W.QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.w = Window(self.root/'preferences.json')
        self.w.set_language('en')
        self.disc = self.root/'own.gdi'
        self.disc.write_bytes(b'own synthetic fixture')
        self.w.controls['source'].setText(str(self.disc))
        self.w.auto_check_timer.stop()
        self.w.identity = {'ok': True}
        self.w.identity_source = str(self.disc)
        self.w.controls['output'].setText(str(self.root/'output'))
        self.w.controls['dlc_download_root'].setText(str(self.root/'downloads'))
        self.w.dlc_catalog = {'fingerprint': 'synthetic-catalog', 'entries': [
            {'id': 'event-a', 'label': 'Synthetic event', 'region': 'US',
             'supported': True, 'reason': 'guest_validation_required'}]}
        self.w._apply_catalog()
        self.w.dlc_list.topLevelItem(0).setCheckState(0, QtCore.Qt.Checked)

    def tearDown(self):
        self.w.close()
        self.app.processEvents()
        self.tmp.cleanup()

    def finish(self):
        for _ in range(4):
            if self.w.task.thread:
                self.w.task.thread.join(3)
            self.w.poll()
            if not self.w.task.pending:
                return
        self.fail('conversion did not finish')

    def download(self, catalog, ids, destination, **kwargs):
        self.assertEqual(ids, ['event-a'])
        self.assertEqual(kwargs['expected_fingerprint'], 'synthetic-catalog')
        self.assertFalse(destination.exists())
        source = destination/'source'
        source.mkdir(parents=True)
        return {'source_dir': str(source)}

    def test_checked_events_are_downloaded_and_given_to_the_converter(self):
        converted = []
        with patch('dcrc.dlc_download.download_events', self.download), patch('dcrc.pipeline.convert', lambda options, **kw: converted.append(options.dlc_dir) or {'ok': True}):
            self.w.convert()
            self.finish()
        self.assertEqual(len(converted), 1)
        self.assertIsNotNone(converted[0])
        self.assertTrue(converted[0].is_dir())
        self.assertEqual(converted[0], Path(self.w.controls['dlc_dir'].text()))

    def test_download_failure_does_not_start_a_dlc_free_build(self):
        from dcrc.errors import ConverterError
        converted = []
        with patch('dcrc.dlc_download.download_events', side_effect=ConverterError('download', 'Synthetic server failure')), patch('dcrc.pipeline.convert', lambda options, **kw: converted.append(options) or {'ok': True}):
            self.w.convert()
            self.finish()
        self.assertEqual(converted, [])
        self.assertIn('Synthetic server failure', self.w.stage.text())

    def test_cancel_after_download_prevents_build_and_repeat_click_is_owned(self):
        entered, release = threading.Event(), threading.Event()
        converted = []
        def download(*args, **kwargs):
            entered.set()
            release.wait(3)
            return self.download(*args, **kwargs)
        with patch('dcrc.dlc_download.download_events', download), patch('dcrc.pipeline.convert', lambda options, **kw: converted.append(options) or {'ok': True}):
            self.w.convert()
            try:
                self.assertTrue(entered.wait(1))
                self.w.convert()
                self.w.stop()
            finally:
                release.set()
                self.finish()
        self.assertEqual(converted, [])

    def test_no_checked_events_preserves_the_explicit_local_folder(self):
        self.w.dlc_list.topLevelItem(0).setCheckState(0, QtCore.Qt.Unchecked)
        source = self.root/'manual-events'
        source.mkdir()
        self.w.controls['dlc_dir'].setText(str(source))
        converted = []
        with patch('dcrc.dlc_download.download_events', side_effect=AssertionError('Unexpected download')), patch('dcrc.pipeline.convert', lambda options, **kw: converted.append(options.dlc_dir) or {'ok': True}):
            self.w.convert()
            self.finish()
        self.assertEqual(converted, [source])

    def test_checked_events_require_a_download_folder(self):
        self.w.controls['dlc_download_root'].clear()
        converted = []
        with patch('dcrc.pipeline.convert', lambda options, **kw: converted.append(options) or {'ok': True}):
            self.w.convert()
            self.finish()
        self.assertEqual(converted, [])
        self.assertIn('download', self.w.log.toPlainText().lower())
