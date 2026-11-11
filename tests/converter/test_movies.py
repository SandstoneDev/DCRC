"""Synthetic user inputs and argv runner; no game/movie/SDK fixtures."""
import hashlib,json,struct,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from test_movie_pmf import stream
from dcrc import movies
from dcrc.errors import Cancelled,ConverterError


def sfd():
    adx=bytearray(32+36);adx[:4]=b'\x80\0\0\x1c';adx[4:8]=bytes((3,18,4,2));struct.pack_into('>II',adx,8,44100,32)
    payload=b'\x0f'+adx
    return b'\0\0\1\xba\x21'+bytes(7)+b'\0\0\1\xc0'+len(payload).to_bytes(2,'big')+payload+b'\0\0\1\xb9'

def wav():
    fmt=struct.pack('<HHIIHHHH',17,2,44100,44236,2048,4,2,2041)
    chunks=b'fmt '+struct.pack('<I',20)+fmt+b'fact'+struct.pack('<II',4,32)+b'data'+struct.pack('<I',2048)+bytes(2048)
    return b'RIFF'+struct.pack('<I',len(chunks)+4)+b'WAVE'+chunks

def inputs(root):
    root.mkdir();overlay=bytearray(movies.MOVIE_BIN_BYTES);pos=0x10000
    for i,name in enumerate(movies.NAMES):
        text=(name+'.SFD').encode()+b'\0';overlay[pos:pos+len(text)]=text
        struct.pack_into('<III',overlay,movies.TABLE_OFFSET+12*i,movies.MOVIE_BASE+pos,movies.FLAGS[i],movies.FRAMES[i]);pos+=len(text)
        (root/(name+'.SFD')).write_bytes(sfd())
    (root/'MOVIE.BIN').write_bytes(overlay)
    return hashlib.sha256(overlay).hexdigest()


class Runner:
    def __init__(self,callback=None):self.calls=[];self.callback=callback
    def run(self,argv,cwd=None,env=None,label=''):
        assert all(isinstance(v,str) for v in argv)
        self.calls.append(argv)
        if self.callback:self.callback()
        if '-version' in argv:(Path(cwd)/'ffmpeg-version.log').write_text('ffmpeg version own-test\n',encoding='utf8')
        elif '-show_program_version' in argv:Path(argv[argv.index('-o')+1]).write_text(json.dumps({'program_version':{'version':'own-test'}}),encoding='utf8')
        elif '-count_frames' in argv:Path(argv[argv.index('-o')+1]).write_text(json.dumps({'streams':[{'codec_name':'h264','nb_read_frames':'2'}]}),encoding='utf8')
        elif '-c:v' in argv:
            assert '-n' in argv and '-y' not in argv and argv[argv.index('-vf')+1]==movies.video_filter()
            Path(argv[-1]).write_bytes(stream())
        elif '-c:a' in argv:Path(argv[-1]).write_bytes(wav())
        else:assert '-xerror' in argv


class MoviesTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'source';digest=inputs(self.source)
        self.patch=patch.object(movies,'MOVIE_BIN_SHA256',digest);self.patch.start();self.addCleanup(self.patch.stop)
        tool=self.root/'tools';tool.mkdir();self.ffmpeg=tool/'ffmpeg.exe';self.probe=tool/'ffprobe.exe'
        self.ffmpeg.write_bytes(b'own synthetic encoder identity');self.probe.write_bytes(b'own synthetic probe identity')
    def stage(self,runner=None,**kw):
        return movies.stage_movies(self.source,self.root/'output',self.ffmpeg,runner or Runner(),**kw)

    def test_input_only_inspection_and_mapping(self):
        with patch.object(movies.shutil,'which',side_effect=AssertionError('must not discover disabled tools')):
            result=movies.inspect_movies(self.source)
        self.assertEqual([r['id'] for r in result['movies']],list(range(10)))
        self.assertEqual(result['settings']['content'],[60,0,360,272])
        self.assertEqual(len(result['inputs']),11)
        self.assertNotIn(str(self.source),json.dumps(result))

    def test_complete_mock_stage_frozen_inputs_and_readback(self):
        before=movies.inspect_movies(self.source);runner=Runner();tools=movies.resolve_tools(self.ffmpeg)
        result=self.stage(runner,expected_fingerprint=before['fingerprint'],expected_tool_identity=tools['identity'])
        self.assertEqual(result['fingerprint'],before['fingerprint']);self.assertEqual(len(result['files']),21)
        self.assertEqual(movies.inspect_movies(self.source),before)
        data=Path(result['data_root'])
        for relative,digest in result['files'].items():self.assertEqual(movies._digest(data/relative),digest)
        for argv in runner.calls:
            if '-i' in argv:self.assertNotIn(str(self.source),argv[argv.index('-i')+1])
        report=json.loads(Path(result['manifest']).read_text())
        self.assertEqual(report['tool_versions'],{'ffmpeg':'own-test','ffprobe':'own-test'})
        self.assertNotIn(str(self.root),json.dumps(report))

    def test_header_only_report_uses_exact_new_runner_stdout(self):
        class HeaderOnly(Runner):
            def __init__(inner):
                super().__init__();inner.log_path=self.root/'runner.log'
                inner.log_path.write_text('ffmpeg version stale-before-run\n',encoding='utf8')
            def run(inner,argv,**kw):
                super().run(argv,**kw)
                if '-version' in argv:
                    (Path(kw['cwd'])/'ffmpeg-version.log').write_text('ffmpeg started\nReport written\nCommand line\nLog level32\n',encoding='utf8')
                    with inner.log_path.open('a',encoding='utf8') as log:log.write('ffmpeg version current-stdout\n')
        result=self.stage(HeaderOnly())
        self.assertEqual(json.loads(Path(result['manifest']).read_text())['tool_versions']['ffmpeg'],'current-stdout')

    def test_invalid_new_stdout_segment_cannot_reuse_stale_banner(self):
        for kind,text in (('missing','not a version\n'),('ambiguous','ffmpeg version first\nffmpeg version second\n'),('oversize','x'*(4*1024*1024+1))):
            class BadLog(Runner):
                def __init__(inner):
                    super().__init__();inner.log_path=self.root/(kind+'.log')
                    inner.log_path.write_text('ffmpeg version stale-before-run\n',encoding='utf8')
                def run(inner,argv,**kw):
                    super().run(argv,**kw)
                    if '-version' in argv:
                        (Path(kw['cwd'])/'ffmpeg-version.log').write_text('ffmpeg version misleading-report\n',encoding='utf8')
                        with inner.log_path.open('a',encoding='utf8') as log:log.write(text)
            with self.subTest(kind=kind),self.assertRaises(ConverterError):
                movies.stage_movies(self.source,self.root/('output_'+kind),self.ffmpeg,BadLog())

    def test_version_log_truncation_and_replacement_declined(self):
        runner=Runner();runner.log_path=self.root/'version.log'
        runner.log_path.write_text('older command\n'*100,encoding='utf8')
        mark=movies._command_log_mark(runner);runner.log_path.write_text('ffmpeg version replacement\n',encoding='utf8')
        with self.assertRaises(ConverterError):movies._ffmpeg_version(mark,self.root/'unused_report')
        mark=movies._command_log_mark(runner);runner.log_path.rename(self.root/'old_version.log')
        runner.log_path.write_text('x'*mark[1]+'ffmpeg version different-file\n',encoding='utf8')
        with self.assertRaises(ConverterError):movies._ffmpeg_version(mark,self.root/'unused_report')

    def test_foreign_output_and_overlap_rejected_before_mutation(self):
        out=self.root/'output';out.mkdir();keep=out/'keep';keep.write_text('foreign')
        runner=Runner()
        with self.assertRaises(ConverterError):self.stage(runner)
        self.assertEqual(list(out.iterdir()),[keep]);self.assertFalse(runner.calls)
        with self.assertRaises(ConverterError):movies.stage_movies(self.source,self.source/'new',self.ffmpeg,runner)
        self.assertFalse((self.source/'new').exists())

    def test_expected_source_and_tool_fingerprints_before_writes(self):
        for kwargs in ({'expected_fingerprint':'wrong'},{'expected_tool_identity':{}}):
            with self.assertRaises(ConverterError):self.stage(**kwargs)
            self.assertFalse((self.root/'output').exists())

    def test_source_mutation_during_commands_declined(self):
        once=[False]
        def mutate():
            if not once[0]:once[0]=True;(self.source/(movies.NAMES[0]+'.SFD')).write_bytes(sfd()+b'changed')
        with self.assertRaises(ConverterError):self.stage(Runner(mutate))
        self.assertFalse((self.root/'output/movies_report.json').exists())

    def test_frozen_input_mutation_during_commands_declined(self):
        once=[False]
        def mutate():
            if not once[0]:
                once[0]=True;path=self.root/'output/work'/ (movies.NAMES[0]+'.SFD');path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaises(ConverterError):self.stage(Runner(mutate))
        self.assertFalse((self.root/'output/movies_report.json').exists())

    def test_frozen_copy_readback_checked_before_commands(self):
        original=Path.open
        class DamagedCopy:
            def __init__(self,stream):self.stream=stream
            def __enter__(self):self.stream.__enter__();return self
            def __exit__(self,*args):return self.stream.__exit__(*args)
            def write(self,data):self.stream.write(data+b'changed');return len(data)
        def opening(path,mode='r',*args,**kwargs):
            f=original(path,mode,*args,**kwargs)
            return DamagedCopy(f) if mode=='xb' and path.suffix=='.SFD' and path.parent.name=='work' else f
        runner=Runner()
        with patch.object(Path,'open',opening),self.assertRaises(ConverterError):self.stage(runner)
        self.assertFalse(runner.calls);self.assertFalse((self.root/'output/movies_report.json').exists())

    def test_cancellation_has_no_output_claim(self):
        cancel=threading.Event();cancel.set()
        with self.assertRaises(Cancelled):self.stage(cancel=cancel)
        self.assertFalse((self.root/'output').exists())

    def test_cancellation_after_owned_command_has_no_receipt(self):
        cancel=threading.Event()
        with self.assertRaises(Cancelled):self.stage(Runner(cancel.set),cancel=cancel)
        self.assertFalse((self.root/'output/movies_report.json').exists())

    def test_tool_mutation_during_commands_declined(self):
        once=[False]
        def mutate():
            if not once[0]:once[0]=True;self.ffmpeg.write_bytes(b'changed synthetic encoder identity')
        with self.assertRaises(ConverterError):self.stage(Runner(mutate))
        self.assertFalse((self.root/'output/movies_report.json').exists())

    def test_invalid_frame_count_is_converter_error(self):
        class BadProbe(Runner):
            def run(self,argv,**kw):
                super().run(argv,**kw)
                if '-count_frames' in argv:Path(argv[argv.index('-o')+1]).write_text(json.dumps({'streams':[{'codec_name':'h264','nb_read_frames':'N/A'}]}),encoding='utf8')
        with self.assertRaises(ConverterError) as error:self.stage(BadProbe())
        self.assertEqual(error.exception.code,'movies_verify')

    def test_unambiguous_sonicadv_child_and_argument_overlap(self):
        container=self.root/'container';container.mkdir();self.source.rename(container/'SONICADV')
        self.assertEqual(len(movies.inspect_movies(container)['movies']),10)
        with self.assertRaises(ConverterError):movies.stage_movies(container,container/'output',self.ffmpeg,Runner())
        self.assertFalse((container/'output').exists())
        (container/'MOVIE.BIN').write_bytes((container/'SONICADV/MOVIE.BIN').read_bytes())
        with self.assertRaises(ConverterError):movies.inspect_movies(container)

    def test_tool_discovery_explicit_missing_and_sibling(self):
        with patch.object(movies.shutil,'which',side_effect=AssertionError('sibling must win')):
            result=movies.resolve_tools(self.ffmpeg)
        self.assertEqual(Path(result['ffprobe']),self.probe)
        with self.assertRaises(ConverterError):movies.resolve_tools(self.root/'missing')
        before=movies.resolve_tools(self.ffmpeg);self.ffmpeg.write_bytes(b'replaced own tool')
        with self.assertRaises(ConverterError):movies.resolve_tools(before)

    def test_missing_audio_truncated_pes_and_wav_declined(self):
        for i,value in enumerate((b'no audio',sfd()[:-20])):
            src=self.root/f'bad{i}';dst=self.root/f'out{i}';src.write_bytes(value)
            with self.assertRaises(ConverterError):movies.demux_adx(src,dst)
        bad=self.root/'bad.wav';bad.write_bytes(wav()[:-1])
        with self.assertRaises(ConverterError):movies.wav_info(bad)
        data=bytearray(wav()[:61]);struct.pack_into('<I',data,4,len(data)-8);struct.pack_into('<I',data,56,1);bad.write_bytes(data)
        with self.assertRaises(ConverterError):movies.wav_info(bad)

    def test_partial_ima_tail_rejected_for_runtime_contract(self):
        partial=bytearray(wav()[:76]);struct.pack_into('<I',partial,4,len(partial)-8)
        struct.pack_into('<I',partial,48,9);struct.pack_into('<I',partial,56,16)
        path=self.root/'partial_tail.wav';path.write_bytes(partial)
        with self.assertRaises(ConverterError):movies.wav_info(path)

    def test_movie_overlay_version_and_pointer_bounds(self):
        overlay=self.source/'MOVIE.BIN';data=bytearray(overlay.read_bytes());struct.pack_into('<I',data,movies.TABLE_OFFSET,0xFFFFFFFF)
        overlay.write_bytes(data)
        with self.assertRaises(ConverterError):movies.inspect_movies(self.source)
        with patch.object(movies,'MOVIE_BIN_SHA256',hashlib.sha256(data).hexdigest()):
            with self.assertRaises(ConverterError):movies.inspect_movies(self.source)

    def test_reparse_rejection(self):
        link=self.root/'linked'
        try:link.symlink_to(self.source,target_is_directory=True)
        except OSError:self.skipTest('symlink privilege unavailable')
        with self.assertRaises(ConverterError):movies.inspect_movies(link)


if __name__=='__main__':unittest.main()
