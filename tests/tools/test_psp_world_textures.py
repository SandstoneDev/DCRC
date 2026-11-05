"""Synthetic offline world quality transform tests, no game assets. MIT."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('worldtex',ROOT/'tools/psp_world_textures.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def pvrt(w,h,fmt=2,pix=1,gbix=7):
    if fmt==2:
        base=2+2*(w*w-1)//3 if w==h else 0
        data=bytearray(base+2*w*h)
        for y in range(h):
            for x in range(w):struct.pack_into('<H',data,base+2*m.twiddle(x,y,w,h),(x%32)<<11|(y%64)<<5|((x+y)%32))
    elif fmt==4:
        base=2048+sum(1 if k<2 else 1<<(2*(k-1)) for k in range(w.bit_length()-1))
        data=bytearray(base+w*h//4)
        for i,c in enumerate([0xf800,0x07e0,0x001f,0xffff]):struct.pack_into('<H',data,2*i,c)
    else:data=bytes(w*h*2)
    prefix=b'GBIX'+struct.pack('<II',4,gbix)
    return prefix+b'PVRT'+struct.pack('<IBBHHH',8+len(data),pix,fmt,0,w,h)+data

def pvm(chunks,names=None,gbixes=None):
    names=names or ['world']*len(chunks);gbixes=gbixes or [7]*len(chunks)
    head=bytearray(b'PVMH'+bytes(4)+struct.pack('<HH',0x109,len(chunks)))
    for i,(name,g) in enumerate(zip(names,gbixes)):head+=struct.pack('<H28sI',i,name.encode(),g)
    head+=bytes((-len(head))%32);struct.pack_into('<I',head,4,len(head)-8)
    for chunk in chunks:head+=chunk;head+=bytes((-len(head))%32)
    return bytes(head)

def pak(path,payloads):
    items=sorted(payloads.items());offset=m.align(16+40*len(items),2048);records=[]
    for name,data in items:records.append((name,offset,len(data)));offset=m.align(offset+len(data),2048)
    out=bytearray(b'SA1PAK\0\1'+struct.pack('<II',len(items),40*len(items)))
    for name,off,n in records:out+=struct.pack('<32sII',name.encode(),off,n)
    for (name,off,n),(_,data) in zip(records,items):out+=bytes(off-len(out))+data
    out+=bytes(offset-len(out));path.write_bytes(out)

class WorldTextureTest(unittest.TestCase):
    def test_prs_literals_all_bit_boundaries(self):
        for n in range(35):
            src=bytes(range(n));self.assertEqual(m.prs_decompress(m.prs_literals(src)),src)

    def test_twiddle_mip_decode(self):
        data=m.decode565(pvrt(8,8))
        self.assertEqual(data[0],0);self.assertEqual(data[3*8+5],5<<11|3<<5|8)
        self.assertEqual(len(set(m.twiddle(x,y,16,8) for y in range(8) for x in range(16))),128)

    def test_vq_mip_decode(self):
        data=m.decode565(pvrt(8,8,4))
        self.assertEqual(data[:2],[0xf800,0x001f]);self.assertEqual(data[8:10],[0x07e0,0xffff])

    def test_pvm_header_only_gbix(self):
        src=pvm([pvrt(128,128)[12:]],['world'],[7])
        out,changes=m.transform_pvm(src,{7:(128,128,'world')},64)
        self.assertEqual(len(changes),1);self.assertEqual(m.parse_pvm(out)[0]['gbix'],7)
        conflict=pvm([pvrt(8,8,gbix=8)],['world'],[7])
        with self.assertRaises(ValueError):m.parse_pvm(conflict)

    def test_filter_and_rectangle_roundtrip(self):
        data,w,h=m.box565([0xf800,0x07e0,0x001f,0xffff],2,2,1)
        self.assertEqual((w,h),(1,1));self.assertEqual(data,[15<<11|31<<5|15])
        self.assertEqual(m.decode565(m.rectangle(data,w,h)),data)

    def test_invalid_filter_bounds(self):
        for args in [([],2,2,1),([0],1,1,0),([0]*6,3,2,1),([0],1,1,3)]:
            with self.assertRaises(ValueError):m.box565(*args)

    def test_pvm_exact_nonmatches_alpha_and_metadata(self):
        selected=pvrt(128,128);alpha=pvrt(128,128,pix=2,gbix=8);other=pvrt(8,8,gbix=9)
        src=pvm([selected,alpha,other],['world','world','actor'],[7,8,9])
        policy={7:(128,128,'world'),8:(128,128,'world')}
        out,changes=m.transform_pvm(src,policy,64)
        old=m.parse_pvm(src);new=m.parse_pvm(out)
        self.assertEqual(len(changes),1);self.assertEqual(len(new),3)
        self.assertEqual(new[0]['w'],64);self.assertEqual(new[0]['datafmt'],9)
        self.assertEqual(new[1]['raw'],old[1]['raw']);self.assertEqual(new[2]['raw'],old[2]['raw'])
        self.assertEqual(out[:struct.unpack_from('<I',out,4)[0]+8],src[:struct.unpack_from('<I',src,4)[0]+8])
        self.assertTrue(all(r['start']%32==0 for r in new))
        self.assertEqual(m.transform_pvm(src,{7:(128,128,'WORLD')},64),(src,[]))
        self.assertEqual(m.transform_pvm(src,{7:(64,128,'world')},64),(src,[]))

    def test_bounds_policy_and_pack(self):
        for data in [b'',b'PVMH'+bytes(20),pvm([pvrt(8,8)])[:-20]]:
            with self.assertRaises(ValueError):m.parse_pvm(data)
        for data in [pvrt(8,8)[:-200],pvrt(8,8,4)[:-20]]:
            with self.assertRaises(ValueError):m.decode565(data)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=p/'source.pak';out=p/'new.pak';policy=p/'policy.txt'
            policy.write_text('SA1_WORLD_TEXTURE_POLICY_V1\n00000007 128 128 world\n')
            rows={'BEACH01.PRS':m.prs_literals(pvm([pvrt(128,128)])),'SONIC.PRS':b'protected actor bytes','UI.PVR':b'font bytes'}
            pak(src,rows);before=src.read_bytes();report=m.convert(src,out,m.read_policy(policy),64)
            self.assertEqual(src.read_bytes(),before);self.assertEqual(report['changed_files'],['BEACH01.PRS'])
            with out.open('rb') as f:
                for name,off,n in m.read_pack(f):
                    f.seek(off);raw=f.read(n)
                    if name!='BEACH01.PRS':self.assertEqual(raw,rows[name])
            with self.assertRaises(FileExistsError):m.convert(src,out,m.read_policy(policy),64)
            with self.assertRaises(FileExistsError):m.convert(src,src,m.read_policy(policy),64)
            policy.write_text('SA1_WORLD_TEXTURE_POLICY_V1\n00000007 128 128 world\n00000007 128 128 world\n')
            with self.assertRaises(ValueError):m.read_policy(policy)
            src.write_bytes(before[:80])
            with src.open('rb') as f:
                with self.assertRaises(ValueError):m.read_pack(f)

if __name__=='__main__':unittest.main()
