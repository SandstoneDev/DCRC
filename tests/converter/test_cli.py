"""Public CLI smoke/regressions on synthetic owned data; no SDK/game input."""
from __future__ import annotations
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
import io,json,os,signal,subprocess,sys,tempfile,threading,unittest
from unittest.mock import patch
from dcrc.errors import Cancelled
from dcrc.models import ConversionOptions
from dcrc.package import claim_output,write_manifest

ROOT=Path(__file__).resolve().parents[2]

def invoke(*args,cp932=False):
    env=os.environ.copy()
    if cp932:env.update(PYTHONIOENCODING='cp932',PYTHONUTF8='0')
    # Keep bytes: text=True would decode UTF8 output using the host codepage.
    return subprocess.run([sys.executable,'-m','dcrc',*(str(a)for a in args)],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)

def response(result):
    return json.loads((result.stdout or result.stderr).decode('utf-8'))

def contents(root):
    return {p.relative_to(root).as_posix():p.read_bytes()for p in root.rglob('*')if p.is_file()}

class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
    def tearDown(self):self.temporary.cleanup()

    def owned_folder(self):
        folder=self.root/'owned 日本語';claim_output(folder,'sa1_us_1005');(folder/'data').mkdir()
        (folder/'EBOOT.PBP').write_bytes(b'Synthetic own CLI payload. Never executable.')
        (folder/'data/SONICADV.PAK').write_bytes(b'Synthetic own asset placeholder.')
        (folder/'args.txt').write_text('--land-distance 100\n',encoding='utf-8')
        (folder/'data/sa1psp.ini').write_text('voice = en\nmy_player_key = retained\n',encoding='utf-8')
        (folder/'vmu').mkdir();(folder/'vmu/player.vms').write_bytes(b'own synthetic save')
        (folder/'notes.txt').write_text('user note',encoding='utf-8')
        metadata={'profile':'sa1_us_1005','options':ConversionOptions(source=self.root/'source',output=folder).to_dict()}
        write_manifest(folder,metadata,owned=['EBOOT.PBP','data/SONICADV.PAK','args.txt','data/sa1psp.ini'])
        return folder

    def test_help_is_utf8_bytes_under_cp932(self):
        r=invoke('--help',cp932=True)
        self.assertEqual(r.returncode,0,r.stderr.decode('utf-8','replace'))
        help_text=r.stdout.decode('utf-8')
        self.assertIn('DCRC Converter',help_text);self.assertIn('\u2014',help_text)
        self.assertIn('convert',help_text);self.assertNotIn(b'Traceback',r.stderr)
        self.assertEqual(r.stderr,b'')

    def test_invalid_source_friendly_exit2_and_no_work_writes(self):
        missing=self.root/'missing-確認.gdi'
        for args in [('identify',missing,'--json'),('convert',missing,'--out',self.root/'out','--work',self.root/'work','--json')]:
            with self.subTest(args=args):
                r=invoke(*args,cp932=True);self.assertEqual(r.returncode,2)
                d=response(r);self.assertFalse(d['ok']);self.assertTrue(d['message'])
                self.assertNotIn(b'Traceback',r.stdout+r.stderr)
        self.assertFalse((self.root/'out').exists());self.assertFalse((self.root/'work').exists())

    def test_unsupported_executable_precedes_work_creation(self):
        source=self.root/'foreign';source.mkdir();(source/'1ST_READ.BIN').write_bytes(b'not supported');(source/'SONICADV').mkdir()
        r=invoke('convert',source,'--out',self.root/'out','--work',self.root/'work','--json')
        self.assertEqual(r.returncode,2);self.assertFalse(response(r)['ok'])
        self.assertFalse((self.root/'out').exists());self.assertFalse((self.root/'work').exists())

    def test_configure_verify_preserve_payload_save_and_unknown_files(self):
        folder=self.owned_folder();before=contents(folder)
        r=invoke('verify',folder,'--json');self.assertEqual(r.returncode,0);self.assertTrue(response(r)['ok']);self.assertEqual(contents(folder),before)
        r=invoke('configure',folder,'--land-distance','100','--aspect','4:3','--no-fps','--voice','ja','--json',cp932=True)
        self.assertEqual(r.returncode,0,r.stderr.decode('utf-8','replace'));settings=response(r)['settings']
        self.assertEqual(settings['land_distance'],100);self.assertFalse(settings['show_fps'])
        after=contents(folder)
        for path in ('EBOOT.PBP','data/SONICADV.PAK','vmu/player.vms','notes.txt','.dcrc_owner.json'):self.assertEqual(after[path],before[path],path)
        self.assertIn('--land-distance 100',after['args.txt'].decode());self.assertNotIn('--fps-hud',after['args.txt'].decode())
        self.assertIn('fps_hud = off',after['data/sa1psp.ini'].decode());self.assertIn('aspect = 4:3',after['data/sa1psp.ini'].decode())
        self.assertIn('voice = ja',after['data/sa1psp.ini'].decode());self.assertIn('my_player_key = retained',after['data/sa1psp.ini'].decode())
        r=invoke('verify',folder,'--json');self.assertEqual(r.returncode,0);self.assertTrue(response(r)['ok']);self.assertEqual(contents(folder),after)

    def test_verify_same_size_corruption_is_readonly_exit2(self):
        folder=self.owned_folder();p=folder/'EBOOT.PBP';bad=bytearray(p.read_bytes());bad[3]^=1;p.write_bytes(bad);before=contents(folder)
        r=invoke('verify',folder,'--json');self.assertEqual(r.returncode,2);d=response(r)
        self.assertFalse(d['ok']);self.assertTrue(any('EBOOT.PBP'in e for e in d['problems']));self.assertEqual(contents(folder),before)

    def test_invalid_configure_changes_nothing(self):
        folder=self.owned_folder();before=contents(folder)
        for value in ('0','75'):
            r=invoke('configure',folder,'--land-distance',value,'--json')
            self.assertEqual(r.returncode,2);self.assertFalse(response(r)['ok']);self.assertEqual(contents(folder),before)

    def test_sigint_sets_pipeline_cancel_event_and_restores_handler(self):
        if threading.current_thread()is not threading.main_thread():self.skipTest('signal handlers require main thread')
        from dcrc.cli import main
        old=signal.getsignal(signal.SIGINT);seen=[]
        def inspect(source,progress=None,cancel=None):
            self.assertFalse(cancel.is_set());handler=signal.getsignal(signal.SIGINT);self.assertTrue(callable(handler))
            handler(signal.SIGINT,None);self.assertTrue(cancel.is_set());seen.append(True)
            raise Cancelled()
        stdout,stderr=io.StringIO(),io.StringIO()
        # Call only the installed handler: never send an OS SIGINT to the
        # shared test runner or any concurrently compiling process.
        with patch('dcrc.disc.inspect_source',side_effect=inspect),redirect_stdout(stdout),redirect_stderr(stderr):code=main(['identify','synthetic.gdi','--json'])
        self.assertEqual(seen,[True]);self.assertIs(signal.getsignal(signal.SIGINT),old)
        result=json.loads(stdout.getvalue()or stderr.getvalue());self.assertFalse(result['ok']);self.assertEqual(result['code'],'cancelled')
        self.assertEqual(code,130)

if __name__=='__main__':unittest.main()
