"""GUI boundary tests; worker/validation need no Qt installation."""
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gui.controller import Task, settings_values, save_settings, load_settings

try:
    from PySide6.QtWidgets import QApplication
    from gui.app import Window
except ImportError:
    QApplication = None


class GuiBoundaryTests(unittest.TestCase):
    def test_quality_and_normal_boot_defaults(self):
        values = settings_values({})
        self.assertEqual((values['world_textures'], values['land_distance']), (64, 100))
        self.assertEqual(values['startup_stage'], 'normal')
        self.assertEqual(values['frame_skip'], 'auto')
        self.assertEqual((values['mip_levels'], values['voice']), (8, 'en'))

    def test_settings_reject_out_of_range_and_unknown(self):
        for data in ({'land_distance': 0}, {'land_distance': 101}, {'world_textures': 32},
                     {'mip_levels': 9}, {'frame_skip': '1'}, {'aspect': '16:10'},
                     {'startup_act': 0}, {'voice': 'de'}, {'audio': 'false'}, {'world_textures': False}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                settings_values(data)

    def test_cancel_waits_for_worker_and_no_auto_run(self):
        task = Task()
        entered = threading.Event()
        release = threading.Event()
        def operation(event, cancel):
            entered.set()
            event({'type': 'log', 'message': 'started'})
            cancel.wait(2)
            release.wait(2)
            return 'finished cleanup'
        self.assertFalse(task.running)
        task.start(operation)
        self.assertTrue(entered.wait(2))
        task.cancel()
        self.assertTrue(task.running)
        with self.assertRaises(RuntimeError):
            task.start(operation)
        release.set()
        task.thread.join(2)
        rows = task.drain()
        self.assertEqual(rows[-1]['type'], 'cancelled')
        self.assertNotIn('finished', [r['type'] for r in rows])

    def test_result_and_exception_are_delivered_to_ui(self):
        task = Task()
        task.start(lambda event, cancel: {'supported': False})
        task.thread.join(2)
        self.assertEqual(task.drain()[-1]['result'], {'supported': False})
        def fail(event, cancel):
            raise ValueError('unsupported version')
        task.start(fail)
        task.thread.join(2)
        self.assertEqual(task.drain()[-1]['message'], 'unsupported version')

    def test_unicode_settings_atomic_and_corrupt_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'настройки'/'gui.json'
            save_settings(p, {'source': 'inputs/own-disc.gdi', 'audio': False})
            self.assertEqual(load_settings(p)['source'], 'inputs/own-disc.gdi')
            self.assertEqual(list(p.parent.glob('*.tmp')), [])
            p.write_text('broken', encoding='utf8')
            self.assertEqual(load_settings(p), {})


@unittest.skipUnless(QApplication, 'Portable PySide runtime required for actual widget tests')
class QtBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.window = Window(Path(self.temp.name)/'settings.json')

    def tearDown(self):
        self.window.close()
        self.application.processEvents()
        self.temp.cleanup()

    def test_opening_never_launches_work_and_normal_boot_ignores_warp(self):
        self.window.show()
        self.application.processEvents()
        self.assertFalse(self.window.task.running)
        self.assertEqual(self.window.values()['startup_stage'], 'normal')
        self.assertFalse(self.window.controls['startup_character'].isEnabled())
        self.assertFalse(self.window.controls['startup_act'].isEnabled())

    def test_unsupported_identity_cannot_start_convert(self):
        self.window.controls['source'].setText('unsupported.gdi')
        with patch('dcrc.pipeline.identify',return_value={'ok':False,'message':'wrong boot hash'}), patch('dcrc.pipeline.convert') as convert:
            self.window.convert()
            self.window.task.thread.join(2)
            self.window.poll()
        self.assertFalse(self.window.task.pending)
        convert.assert_not_called()
        self.assertIn('wrong boot hash',self.window.version.text())

    def test_identify_forwards_progress_and_cancellation_to_public_core(self):
        calls = []
        def identify(source, *, event, cancel_event):
            calls.append((source, cancel_event))
            event({'type': 'progress', 'progress': .5, 'stage': 'identify'})
            return {'ok': False, 'message': 'Unsupported version',
                    'files': [{'path': 'PRIVATE_DISC_FILE'}]*2000}
        self.window.controls['source'].setText('own image.gdi')
        with patch('dcrc.pipeline.identify', identify):
            self.window.identify()
            self.window.task.thread.join(2)
            self.window.poll()
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][1], self.window.task.cancel_event)
        self.assertEqual(self.window.identity['ok'], False)
        self.assertIn('Unsupported version', self.window.version.text())
        self.assertLess(len(self.window.version.text()), 2000)
        self.assertNotIn('PRIVATE_DISC_FILE', self.window.version.text())

    def test_close_requests_cancel_and_waits_for_worker_cleanup(self):
        entered = threading.Event()
        release = threading.Event()
        def operation(event, cancel):
            entered.set()
            cancel.wait(2)
            release.wait(2)
        self.window.show()
        self.window.begin('Test cleanup', operation)
        self.assertTrue(entered.wait(2))
        self.window.close()
        self.application.processEvents()
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window.task.cancel_event.is_set())
        release.set()
        self.window.task.thread.join(2)
        self.window.poll()
        self.assertFalse(self.window.isVisible())


if __name__ == '__main__':
    unittest.main()
