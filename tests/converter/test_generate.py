import tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
from dcrc.generate import generate

ROOT=Path(__file__).resolve().parents[2]
class GenerateTests(unittest.TestCase):
 def test_explicit_input_all58_and_no_source_update(self):
  calls=[]
  def run(argv,**kwargs):
   calls.append(argv);self.assertNotIn('--update-hle',argv);out=Path(argv[argv.index('--out')+1]);out.mkdir(parents=True,exist_ok=True)
   self.assertEqual(argv[1],'-B')
   if 'emit_sa1.py' in str(argv[2]):(out/'game_000.c').write_text('/* synthetic */');(out/'game_table.c').write_text('/* synthetic */');(out/'game.h').write_text('/* synthetic */')
   else:
    name=out.name;(out/f'ovl_{name}_000.c').write_text('/* synthetic */');(out/f'ovl_{name}_table.c').write_text('/* synthetic */');(out/f'ovl_{name}.h').write_text('/* synthetic */')
   return subprocess.CompletedProcess(argv,0,'ok','')
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);data=root/'data';data.mkdir();(data/'1ST_READ.BIN').write_bytes(b'x');(data/'SONICADV').mkdir()
   with patch('dcrc.generate.verify_folder',return_value={'profile':'sa1_us_1005','fingerprint':'fixture'}),patch('dcrc.generate.prs_decompress',return_value=b'synthetic'),patch('dcrc.generate.subprocess.run',side_effect=run):
    from dcrc.profiles import load_profile
    for ov in load_profile()['overlays']:(data/ov['file']).write_bytes(b'x')
    result=generate(data,root/'gen',ROOT,jobs=2)
   self.assertEqual(len(calls),59);self.assertEqual(result['overlays'],58);self.assertTrue(result['files']);self.assertTrue(all('--functions'in a for a in calls))
 def test_existing_output_rejected_before_process(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);out=p/'out';out.mkdir();(out/'mine').write_text('keep')
   with patch('dcrc.generate.subprocess.run')as run:self.assertRaises(Exception,generate,p,out,ROOT);run.assert_not_called()

if __name__=='__main__':unittest.main()
