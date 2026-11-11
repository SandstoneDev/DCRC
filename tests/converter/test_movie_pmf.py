"""Synthetic syntax only; no encoded game frames or decoder compatibility claim."""
import importlib
from pathlib import Path
import struct
import tempfile
import unittest


def sps(width=480,profile=77,level=21,refs=1,sps_id=0):
    bits=[]
    def u(value,n): bits.extend((value>>i)&1 for i in range(n-1,-1,-1))
    def ue(value):
        value+=1;n=value.bit_length()-1;bits.extend([0]*n);u(value,n+1)
    u(profile,8);u(0,8);u(level,8);ue(sps_id);ue(0);ue(0);ue(0);ue(refs);u(0,1);ue(width//16-1);ue(16);u(1,1)
    bits.append(1)
    while len(bits)%8: bits.append(0)
    return bytes([0x67])+bytes(sum(bits[j+i]<<(7-i) for i in range(8)) for j in range(0,len(bits),8))


def stream(b_picture=False):
    nal=lambda b:b'\0\0\0\1'+b
    return nal(b'\x09\xf0')+nal(sps())+nal(b'\x68\xc0')+nal(b'\x65\xb8')+nal(b'\x09\xf0')+nal(b'\x41'+(b'\xa0' if b_picture else b'\xe0'))


class MoviePmfTest(unittest.TestCase):
    def setUp(self):
        self.mux=importlib.import_module('tools.movie_pmfmux')
        self.info=importlib.import_module('tools.movie_pmfinfo')

    def test_synthetic_syntax_roundtrip(self):
        data,stats=self.mux.mux(stream())
        parsed=self.info.analyze_bytes(data)
        self.assertEqual(self.info.check(parsed),[])
        self.assertEqual(stats['access_units'],2)
        self.assertEqual((parsed['sps']['profile'],parsed['sps']['level']), (77,21))
        self.assertEqual((parsed['sps']['width'],parsed['sps']['height']),(480,272))
        self.assertEqual(len(data)%2048,0)
        self.assertEqual(parsed['header']['last_ts']-parsed['header']['first_ts'],6006)
        self.assertFalse(parsed['audio'])

    def test_reject_empty_b_picture_and_truncated_sps(self):
        for value in (b'',stream(True),b'\0\0\1\x09\xf0\0\0\1\x67\0\0\1\x68\xc0\0\0\1\x65\xb8'):
            with self.assertRaises((ValueError,self.mux.MuxError)):
                self.mux.mux(value)

    def test_exclusive_write_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'own.pmf'
            self.mux.write_checked(stream(),target)
            before=target.read_bytes()
            with self.assertRaises(FileExistsError): self.mux.write_checked(stream(),target)
            self.assertEqual(target.read_bytes(),before)
            self.assertEqual(self.info.check(self.info.analyze(target)),[])

    def test_bit_reader_and_stream_counts_bounded(self):
        for action in (lambda:self.info.Bits(b'').u(1),lambda:self.info.Bits(bytes(16)).ue()):
            with self.assertRaises(ValueError): action()
        bad=bytearray(2048);bad[:8]=b'PSMF0015';struct.pack_into('>H',bad,0x80,65535)
        with self.assertRaises(ValueError): self.info.read_header(bad)

    def test_malformed_sei_declines(self):
        for value in (b'\x06\xff',b'\x06\x05\x10x',b'\x06\x05\xff'):
            with self.assertRaises(self.mux.MuxError): self.mux.sei_messages(value)

    def test_every_later_sps_and_parameter_reference_checked_before_write(self):
        first=self.mux.split_nals(stream())[:4]
        for changed in (sps(width=640),sps(profile=66),sps(refs=2),sps(level=22),sps(sps_id=1),bytes([0x67,77,64])+sps()[3:]):
            for idr in (False,True):
                with self.subTest(sps=changed.hex(),idr=idr),tempfile.TemporaryDirectory() as tmp:
                    nals=first+[b'\x09\xf0',changed,b'\x68\xc0',b'\x65\xb8' if idr else b'\x41\xe0']
                    target=Path(tmp)/'bad.pmf'
                    with self.assertRaises((ValueError,self.mux.MuxError)):
                        self.mux.write_checked(b''.join(b'\0\0\0\1'+n for n in nals),target)
                    self.assertFalse(target.exists())
        wrong_pps=first+[b'\x09\xf0',sps(),b'\x68\xa0',b'\x65\xb8'] # PPS references absent SPS1
        with self.assertRaises((ValueError,self.mux.MuxError)):
            self.mux.mux(b''.join(b'\0\0\0\1'+n for n in wrong_pps))
        wrong_slice=first+[b'\x09\xf0',sps(),b'\x68\xc0',b'\x65\xb4'] # Picture references absent PPS1
        with self.assertRaises((ValueError,self.mux.MuxError)):
            self.mux.mux(b''.join(b'\0\0\0\1'+n for n in wrong_slice))

    def test_info_rejects_later_changed_sps_but_identical_repeat_passes(self):
        first=self.mux.split_nals(stream())[:4];es=b''.join(b'\0\0\0\1'+n for n in first+first)
        data,stats=self.mux.mux(es);self.assertEqual(stats['access_units'],2)
        self.assertFalse(self.info.check(self.info.analyze_bytes(data)))
        needle=b'\0\0\0\1'+sps();first_pos=data.find(needle);second=data.find(needle,first_pos+len(needle))
        self.assertGreater(second,0)
        bad=bytearray(data);bad[second+5]=66
        self.assertTrue(self.info.check(self.info.analyze_bytes(bad)))


if __name__=='__main__': unittest.main()
