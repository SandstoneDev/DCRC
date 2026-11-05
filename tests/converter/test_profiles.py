import json,tempfile,unittest,hashlib,shutil,re
from pathlib import Path
from unittest.mock import patch
from dcrc import profiles

class ProfileTests(unittest.TestCase):
 def test_facts_only_complete_profile(self):
  p=profiles.load_profile();self.assertEqual(p['id'],'sa1_us_1005');self.assertEqual(len(p['overlays']),58);self.assertEqual(len(p['catalogs']),59);self.assertEqual(p['boot']['bytes'],6735488)
  for unit,entry in p['catalogs'].items():
   path=profiles.PROFILE_DIR/entry['file'];b=path.read_bytes();self.assertEqual(hashlib.sha256(b).hexdigest(),entry['sha256']);d=json.loads(b);self.assertEqual(set(d),{'functions'})
   for row in d['functions']:self.assertEqual(set(row),{'entry','end','origin'})
 def test_unknown_profile_and_foreign_boot_rejected(self):
  self.assertRaises(Exception,profiles.load_profile,'other')
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);(root/'1ST_READ.BIN').write_bytes(b'wrong');(root/'SONICADV').mkdir();self.assertRaises(Exception,profiles.verify_folder,root)
 def test_metadata_no_private_paths(self):
  for p in profiles.PROFILE_DIR.rglob('*'):
   if p.is_file():
    s=p.read_text();self.assertIsNone(re.search(r'(?<![A-Za-z])[A-Za-z]:[\\/]',s));self.assertNotIn('/mnt/',s)
 def test_catalog_same_size_corruption(self):
  with tempfile.TemporaryDirectory()as d:
   out=Path(d)/'profile';shutil.copytree(profiles.PROFILE_DIR,out);p=out/'functions/main.json';b=bytearray(p.read_bytes());b[30]^=1;p.write_bytes(b)
   with patch('dcrc.profiles.PROFILE_DIR',out):self.assertRaises(Exception,profiles.load_profile)
 def test_prs_bounds_without_game_data(self):
  # Literal A then end marker; output limit is enforced before any append.
  self.assertEqual(profiles.decode_overlay(b'\x05A\0\0',1),b'A')
  self.assertRaises(ValueError,profiles.decode_overlay,b'\x05A\0\0',0)
  self.assertRaises(ValueError,profiles.decode_overlay,b'\x00\x00',32)

if __name__=='__main__':unittest.main()
