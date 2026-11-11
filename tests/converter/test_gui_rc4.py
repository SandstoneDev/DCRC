"""Owner RC3 regressions: automatic disc check and one obvious final action."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','windows' if os.name=='nt' else 'offscreen')
try:
    from PySide6 import QtWidgets as W
    from gui.app import Window
except ImportError: W=None


@unittest.skipUnless(W,'Portable Qt required')
class FollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=W.QApplication.instance()or W.QApplication([])
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.w=Window(self.root/'settings.json');self.w.set_language('en')
        self.disc=self.root/'own.gdi';self.disc.write_bytes(b'fixture')
    def tearDown(self):
        self.w.close();self.app.processEvents();self.tmp.cleanup()
    def drain(self):
        for _ in range(5):
            if self.w.task.thread:self.w.task.thread.join(2)
            self.w.poll()
            if not self.w.task.pending:return
        self.fail('Jobs did not settle')
    def test_picking_disc_checks_automatically_without_tab_jump(self):
        calls=[]
        with patch('dcrc.pipeline.identify',lambda path,**kw:calls.append(path)or{'ok':True,'title':'Sonic Adventure'}):
            self.w.controls['source'].setText(str(self.disc))
            self.w.auto_check_timer.timeout.emit();self.drain()
        self.assertEqual(calls,[self.disc]);self.assertTrue(self.w.identity['ok'])
        self.assertEqual(self.w.tabs.currentIndex(),0)
    def test_final_next_is_convert_and_checks_before_conversion(self):
        calls=[];self.w.controls['source'].setText(str(self.disc));self.w.tabs.setCurrentIndex(5)
        self.assertEqual(self.w.next.text(),'Convert')
        self.assertTrue(self.w.start.isHidden())
        with patch('dcrc.pipeline.identify',lambda path,**kw:calls.append('check')or{'ok':True}),patch('dcrc.pipeline.convert',lambda options,**kw:calls.append('convert')or{'ok':True}):
            self.w.next.click();self.drain()
        self.assertEqual(calls,['check','convert'])
    def test_convert_waits_for_an_already_running_auto_check(self):
        entered,release=threading.Event(),threading.Event();calls=[]
        def identify(path,**kw):entered.set();release.wait(2);return{'ok':True}
        self.w.controls['source'].setText(str(self.disc))
        with patch('dcrc.pipeline.identify',identify),patch('dcrc.pipeline.convert',lambda options,**kw:calls.append('convert')or{'ok':True}):
            self.w.auto_check_timer.timeout.emit();self.assertTrue(entered.wait(1))
            self.w.convert();release.set();self.drain()
        self.assertEqual(calls,['convert'])
    def test_unsupported_disc_never_starts_conversion(self):
        self.w.controls['source'].setText(str(self.disc));calls=[]
        with patch('dcrc.pipeline.identify',lambda path,**kw:{'ok':False,'message':'Wrong version'}),patch('dcrc.pipeline.convert',lambda *a,**kw:calls.append(True)):
            self.w.convert();self.drain()
        self.assertEqual(calls,[]);self.assertIn('Wrong version',self.w.version.text())
    def test_dlc_only_dialog_has_progress_bar(self):
        entered,release=threading.Event(),threading.Event()
        def operation(event,cancel):entered.set();release.wait(2);return{'source_dir':'ready'}
        self.w.begin('Download DLC',operation)
        try:
            self.assertTrue(entered.wait(1));self.assertTrue(self.w.inline_bar.isHidden())
            self.assertFalse(self.w.job_dialog.bar.isHidden())
        finally:release.set();self.drain()
    def test_public_distance_is_locked_to_full100(self):
        self.w.distance_slider.setValue(73);self.assertEqual(self.w.values()['land_distance'],100)
        self.w.controls['land_distance'].setValue(52);self.assertEqual(self.w.distance_slider.value(),100)
    def test_playback_failure_is_not_reported_as_playing(self):
        with patch('gui.media_picker.play_wav',side_effect=RuntimeError('audio output unavailable')):
            self.w.begin('Prepare music preview',lambda event,cancel:self.root/'clip.wav');self.drain()
        self.assertIn('audio output unavailable',self.w.stage.text())
        self.assertNotIn('Playing',self.w.inline_status.text())
