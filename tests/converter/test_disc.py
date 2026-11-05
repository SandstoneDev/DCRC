"""Synthetic ISO/GDI boundary tests; no commercial game bytes."""
import tempfile,struct,unittest,threading
from pathlib import Path
from unittest.mock import patch
from dcrc import disc
from dcrc.errors import ConverterError,Cancelled

def both(n):return struct.pack('<I',n)+struct.pack('>I',n)
def record(name,lba,size,directory=False):
 name=name if isinstance(name,bytes)else name.encode('ascii');n=33+len(name)+(len(name)%2==0);r=bytearray(n);r[0]=n;r[2:10]=both(lba);r[10:18]=both(size);r[25]=2 if directory else 0;r[28:32]=b'\1\0\0\1';r[32]=len(name);r[33:33+len(name)]=name;return bytes(r)
def image(root,name='1ST_READ.BIN',ss=2352,mode=1,offset=0,base=45000,split=False):
 sectors=[bytearray(2048)for _ in range(24)];p=sectors[16];p[:7]=b'\1CD001\1';p[80:88]=both(base+24);p[128:132]=b'\0\10\10\0';p[156:190]=record(b'\0',base+20,2048,True)
 directory=record(b'\0',base+20,2048,True)+record(b'\1',base+20,2048,True)+record(name+';1',base+21,5);sectors[20][:len(directory)]=directory;sectors[21][:5]=b'hello'
 def raw(i,s):
  if ss==2048:return bytes(s)
  n=base+i+150;m,n=divmod(n,4500);sec,f=divmod(n,75);bcd=lambda v:(v//10<<4)|(v%10);h=b'\0'+b'\xff'*10+b'\0'+bytes([bcd(m),bcd(sec),bcd(f),mode]);return h+(b'\0'*8 if mode==2 else b'')+bytes(s)+bytes(2352-16-(8 if mode==2 else 0)-2048)
 payload=[raw(i,s)for i,s in enumerate(sectors)];root.mkdir(parents=True,exist_ok=True)
 if split:
  (root/'one.bin').write_bytes(bytes(offset)+b''.join(payload[:21]));(root/'two.bin').write_bytes(b''.join(payload[21:]));lines=['2',f'3 {base} 4 {ss} "one.bin" {offset}',f'4 {base+21} 4 {ss} "two.bin" 0']
 else:(root/'one.bin').write_bytes(bytes(offset)+b''.join(payload));lines=['1',f'3 {base} 4 {ss} "one.bin" {offset}']
 (root/'test.gdi').write_text('\n'.join(lines)+'\n');return root/'test.gdi'

class DiscTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name);self.mock=patch('dcrc.profiles.validate_files',return_value={'profile':'synthetic','title':'Synthetic','boot':{'path':'1ST_READ.BIN'}});self.mock.start()
 def tearDown(self):self.mock.stop();self.tmp.cleanup()
 def test_offset_cooked_mode2_and_multitrack(self):
  for n,ss,mode,off,split in [(0,2352,1,64,False),(1,2048,1,0,False),(2,2352,2,7,False),(3,2352,1,0,True)]:
   with self.subTest(n=n):
    src=image(self.r/str(n),ss=ss,mode=mode,offset=off,split=split);d=disc.inspect_source(src);self.assertEqual(d['files'][0]['bytes'],5);out=self.r/('out'+str(n));result=disc.extract_source(src,out);self.assertEqual((out/'1ST_READ.BIN').read_bytes(),b'hello');self.assertEqual(result['fingerprint'],d['fingerprint'])
 def test_fingerprint_relocation_and_contents(self):
  a=disc.inspect_source(image(self.r/'a'));b=disc.inspect_source(image(self.r/'b'));self.assertEqual(a['fingerprint'],b['fingerprint'])
 def test_high_density_minutes_past99(self):
  self.assertEqual(disc.inspect_source(image(self.r/'late',base=545000))['files'][0]['bytes'],5)
 def test_cooked_zero_based_iso(self):
  src=image(self.r/'cooked',ss=2048,base=0);iso=src.parent/'image.iso';iso.write_bytes((src.parent/'one.bin').read_bytes());self.assertEqual(disc.inspect_source(iso)['kind'],'iso')
 def test_traversal_and_duplicate_destinations_rejected(self):
  for n in ['../ESCAPE','A/B','A\\B','C:BAD','CON','BAD.','A?B','X*Y','A|B']:
   with self.subTest(n=n):
    src=image(self.r/str(abs(hash(n))),name=n);out=self.r/'no';self.assertRaises(Exception,disc.extract_source,src,out);self.assertFalse(out.exists())
 def test_existing_nonempty_never_overwritten(self):
  src=image(self.r/'in');out=self.r/'out';out.mkdir();(out/'keep').write_text('mine');self.assertRaises(Exception,disc.extract_source,src,out);self.assertEqual((out/'keep').read_text(),'mine')
 def test_cancel_before_output(self):
  src=image(self.r/'in');self.assertRaises(Cancelled,disc.extract_source,src,self.r/'out',cancel=lambda:True);self.assertFalse((self.r/'out').exists())
 def test_inspect_cancel_before_read(self):
  src=image(self.r/'in')
  with patch.object(disc._Track,'read',side_effect=AssertionError('cancel must precede reads')):
   self.assertRaises(Cancelled,disc.inspect_source,src,cancel=lambda:True)
 def test_inspect_progress_and_cancel_during_hash(self):
  source=self.r/'hash';source.mkdir();(source/'1ST_READ.BIN').write_bytes(b'hello');(source/'SECOND.BIN').write_bytes(b'world');event=threading.Event();seen=[]
  def progress(e):seen.append(e);event.set()
  self.assertRaises(Cancelled,disc.inspect_source,source,progress=progress,cancel=event)
  self.assertEqual(len(seen),1);self.assertEqual(seen[0]['stage'],'identify');self.assertEqual(seen[0]['progress'],.5);self.assertEqual((source/'SECOND.BIN').read_bytes(),b'world')
 def test_unsupported_boot_never_writes_destination(self):
  source=self.r/'foreign';source.mkdir();(source/'1ST_READ.BIN').write_bytes(b'unsupported');(source/'SONICADV').mkdir();destination=self.r/'uncreated';self.mock.stop()
  with self.assertRaises(ConverterError)as caught:disc.extract_source(source,destination)
  self.assertEqual(caught.exception.code,'UNSUPPORTED_GAME');self.assertFalse(destination.exists())
 def test_bad_track_count_and_descriptor_escape(self):
  src=image(self.r/'in');src.write_text(src.read_text().replace('1\n','2\n',1));self.assertRaises(Exception,disc.inspect_source,src)
  src.write_text('1\n3 45000 4 2352 "../outside.bin" 0\n');self.assertRaises(Exception,disc.inspect_source,src)
 def test_short_sector_and_bad_iso_records(self):
  src=image(self.r/'in',ss=2048);p=src.parent/'one.bin';b=bytearray(p.read_bytes());b[20*2048]=2;p.write_bytes(b);self.assertRaises(Exception,disc.inspect_source,src)
 def test_symlink_input_and_output_rejected(self):
  src=image(self.r/'in');link=self.r/'link.gdi'
  try:link.symlink_to(src)
  except OSError:self.skipTest('host cannot create symlinks')
  self.assertRaises(Exception,disc.inspect_source,link);out=self.r/'out';out.symlink_to(src.parent,target_is_directory=True);self.assertRaises(Exception,disc.extract_source,src,out)
 def test_verified_folder_content_hash_and_collision(self):
  src=self.r/'data';src.mkdir();(src/'1ST_READ.BIN').write_bytes(b'x');a=disc.inspect_source(src);(src/'1ST_READ.BIN').write_bytes(b'y');b=disc.inspect_source(src);self.assertNotEqual(a['fingerprint'],b['fingerprint']);(src/'one').write_text('1');(src/'ONE').write_text('2')
  if len(list(src.glob('*')))==3:self.assertRaises(Exception,disc.inspect_source,src)
 def test_cycle_duplicate_and_endian_extent_rejected(self):
  for case in ('cycle','duplicate','endian','outside','large-dir'):
   with self.subTest(case=case):
    src=image(self.r/case,ss=2048);p=src.parent/'one.bin';b=bytearray(p.read_bytes());r=record(b'\0',45020,2048,True)+record(b'\1',45020,2048,True)
    if case=='cycle':r+=record('LOOP',45020,2048,True)
    elif case=='duplicate':r+=record('FILE;1',45021,5)+record('file;1',45021,5)
    elif case=='outside':r+=record('FILE;1',999999,5)
    elif case=='large-dir':r+=record('HUGE',45020,disc.MAX_DIRECTORY+1,True)
    else:r+=record('FILE;1',45021,5);r=bytearray(r);r[-len(record('FILE;1',45021,5))+6]^=1
    b[20*2048:21*2048]=bytes(2048);b[20*2048:20*2048+len(r)]=r;p.write_bytes(b);self.assertRaises(ConverterError,disc.inspect_source,src)
 def test_mode2_form2_and_truncated_track(self):
  src=image(self.r/'form2',mode=2);p=src.parent/'one.bin';b=bytearray(p.read_bytes());b[16*2352+18]=b[16*2352+22]=0x20;p.write_bytes(b);self.assertRaises(ConverterError,disc.inspect_source,src)
  src=image(self.r/'short');p=src.parent/'one.bin';p.write_bytes(p.read_bytes()[:-1]);self.assertRaises(ConverterError,disc.inspect_source,src)

if __name__=='__main__':unittest.main()
