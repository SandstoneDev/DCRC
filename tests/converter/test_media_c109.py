"""Owned synthetic media codec and exact catalog selection tests."""
import hashlib,io,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from dcrc import media,xmb
from dcrc.errors import ConverterError,Cancelled
from tools.psp_world_textures import prs_literals
from test_xmb import pvm

class MediaTests(unittest.TestCase):
    def test_ids(self):
        for identity in ('title','sega','pvm:FOO.PRS:hello_0','img:EXAMPLE.PNG'):self.assertTrue(media.valid_artwork_id(identity))
        for identity in ('pvm:../x:tile','img:/tmp/foo','pvm:A.PRS:x:y',None):self.assertFalse(media.valid_artwork_id(identity))
    def test_pixels_and_layouts(self):
        for pix,value,want in ((0,0xfc00,(255,0,0,255)),(1,0x07e0,(0,255,0,255)),(2,0x8f00,(255,0,0,136))):
            for fmt in (1,9,0x0d):
                with self.subTest(pix=pix,fmt=fmt):
                    im=media.decode_tile(('tile',pix,fmt,4,2,struct.pack('<8H',*([value]*8))))
                    self.assertEqual(im.getpixel((3,1)),want)
        im=media.decode_tile(('tile',0,1,1,1,struct.pack('<H',0x7c00)))
        self.assertEqual(im.getpixel((0,0)),(255,0,0,0))
    def test_vq_axis_order(self):
        table=struct.pack('<4H',0xf800,0x07e0,0x001f,0xffff)+bytes(2040)
        im=media.decode_tile(('tile',1,3,2,2,table+b'\0'))
        self.assertEqual(list(im.getdata()),[(255,0,0,255),(0,0,255,255),(0,255,0,255),(255,255,255,255)])
    def test_twiddle_nonuniform(self):
        words=[0]*8
        for y in range(2):
            for x in range(4):words[media._morton(x,y,4,2)]=0xf800 if x==3 and y==1 else 0x001f
        im=media.decode_tile(('t',1,1,4,2,struct.pack('<8H',*words)))
        self.assertEqual(im.getpixel((3,1)),(255,0,0,255));self.assertEqual(im.getpixel((2,1)),(0,0,255,255))
    def test_reject_bounds(self):
        for data in (b'',bytes(40),bytes(8)+b'\1'):
            with self.assertRaises(ConverterError):media.decode_tile(('t',1,1,2,2,data))
        with self.assertRaises(ConverterError):media.archive_tiles(pvm()[:-33])
    def test_cancelled_preview_never_starts_tool(self):
        with self.assertRaises(Cancelled):media.preview_source_audio('missing',None,0,6,'missing.wav',cancel=lambda:True)
    def test_preview_sampling_matches_exact_pixels(self):
        tile=('t',1,1,4,2,struct.pack('<8H',0xf800,0x07e0,0x001f,0xffff,0,0,0,0))
        full=media.decode_tile(tile);small=media.decode_tile(tile,(2,1))
        self.assertEqual(small.info['catalog_size'],(4,2))
        for x in range(2):self.assertEqual(small.getpixel((x,0)),full.getpixel((x*2,0)))
    def test_catalog_export_and_conversion_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game=root/'SONICADV';game.mkdir();(game/'TITLE.PRS').write_bytes(prs_literals(pvm()))
            (game/'EXTRA.PVM').write_bytes(pvm('extra',0x07e0));Image.new('RGB',(5,6),'blue').save(game/'OWN.PNG')
            catalog=xmb.inspect_media(root);ids={i['id'] for i in catalog['images']}
            self.assertIn('pvm:EXTRA.PVM:extra',ids);self.assertIn('img:OWN.PNG',ids)
            (root/'1ST_READ.BIN').write_bytes(b'boot')
            with patch('dcrc.profiles.BOOT_BYTES',4),patch('dcrc.profiles.BOOT_SHA256',hashlib.sha256(b'boot').hexdigest()):
                exported=media.export_source_image(root,'pvm:EXTRA.PVM:extra',root/'export.png')
                with Image.open(exported) as im:self.assertEqual(im.getpixel((0,0)),(0,255,0,255))
                with self.assertRaises(FileExistsError):media.export_source_image(root,'pvm:EXTRA.PVM:extra',root/'export.png')
            (root/'1ST_READ.BIN').unlink()
            result=xmb.prepare_xmb(root,root/'output',{'xmb_icon_art':'pvm:EXTRA.PVM:extra','xmb_background_art':'img:OWN.PNG'})
            with Image.open(result['icon0']) as im:self.assertEqual(im.getpixel((0,0)),(0,255,0))
            with Image.open(result['pic1']) as im:self.assertEqual(im.getpixel((0,0)),(0,0,255))
    def test_audio_rejects_invalid_segments_before_tools(self):
        for start,seconds in ((-1,3),(0,11),(float('nan'),2),(1,0)):
            with self.assertRaises(ConverterError):media.preview_source_audio('missing',None,start,seconds,'missing.wav')
