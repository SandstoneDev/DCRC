"""Owned synthetic XMB inputs; no game/media fixtures."""
import io, json, struct, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageOps
from dcrc import xmb
from dcrc.errors import ConverterError, Cancelled
from tools.psp_world_textures import prs_literals


def pvm(name='beta_title0', color=0xf800):
    directory=struct.pack('<H28sI',0,name.encode(),42)
    start=64
    image=b'PVRT'+struct.pack('<IBBHHH',8+128,1,1,0,8,8)+struct.pack('<64H',*([color]*64))
    raw=b'PVMH'+struct.pack('<IHH',start-8,9,1)+directory
    return raw+bytes(start-len(raw))+image+bytes((-len(image))%32)


def riff(parts):
    body=b'WAVE'+b''.join(k+struct.pack('<I',len(v))+v+bytes(len(v)%2) for k,v in parts)
    return b'RIFF'+struct.pack('<I',len(body))+body


def at3():
    fmt=struct.pack('<HHIIHHHHI',0xfffe,2,44100,44100,2048,0,34,2048,3)+xmb.ATRAC_GUID+bytes(12)
    return riff([(b'fmt ',fmt),(b'fact',struct.pack('<II',2048,0)),(b'data',bytes(2048))])


class XmbTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.data=self.root/'data';self.data.mkdir();self.game=self.data/'SONICADV';self.game.mkdir()
        (self.game/'TITLE.PRS').write_bytes(prs_literals(pvm()))
        (self.game/'SEGALOGO.PRS').write_bytes(prs_literals(pvm('segalogo0',0x001f)))
        adx=bytearray(128);adx[:8]=b'\x80\0\0\x7c\3\x12\4\2';struct.pack_into('>II',adx,8,44100,44100*20)
        (self.game/'TITLE.ADX').write_bytes(adx)
    def test_catalog_portable_and_actual_track_header(self):
        c=xmb.inspect_media(self.data)
        self.assertEqual(c['tracks'][0]['id'],'TITLE.ADX');self.assertEqual(c['tracks'][0]['seconds'],20)
        self.assertEqual(c['images'][0]['id'],'title');self.assertNotIn(str(self.root),json.dumps(c))
    def test_default_images_dimensions_and_color(self):
        result=xmb.prepare_xmb(self.data,self.root/'out',{})
        self.assertIsNone(result['snd0'])
        for slot,size in [('icon0',(144,80)),('pic1',(480,272))]:
            with Image.open(result[slot]) as im:self.assertEqual(im.size,size);self.assertEqual(im.mode,'RGB');self.assertEqual(im.getpixel((0,0)),(255,0,0))
        self.assertNotIn(str(self.root),json.dumps(result['files']))
    def test_game_art_ids_select_independent_slots_and_preserve_source(self):
        from dcrc.storage import file_digest
        before={p.name:file_digest(p)for p in self.game.iterdir()}
        expected={'title':(255,0,0),'sega':(0,0,255)}
        for number,(icon,background) in enumerate((('title','title'),('sega','title'),('title','sega'),('sega','sega'))):
            r=xmb.prepare_xmb(self.data,self.root/('selected'+str(number)),
                dict(xmb_icon_art=icon,xmb_background_art=background))
            for slot,identity in (('icon0',icon),('pic1',background)):
                with Image.open(r[slot]) as im:self.assertEqual(im.getpixel((0,0)),expected[identity])
                meta=r['inputs'][slot];self.assertEqual(meta['id'],identity)
                filename='TITLE.PRS' if identity=='title' else 'SEGALOGO.PRS'
                self.assertEqual(meta['source'],'SONICADV/'+filename)
                self.assertEqual(meta['input'],before[filename])
        self.assertEqual(before,{p.name:file_digest(p)for p in self.game.iterdir()})
    def test_sega_first_tile_does_not_require_title_or_animation(self):
        (self.game/'TITLE.PRS').unlink()
        with patch.object(xmb,'_boot',side_effect=AssertionError('SEGA has no inferred animation layout')):
            r=xmb.prepare_xmb(self.data,self.root/'sega',dict(xmb_icon_art='sega',xmb_background_art='sega'))
        self.assertEqual(r['inputs']['icon0']['layout'],'first_tile')
        with Image.open(r['pic1']) as im:self.assertEqual(im.getpixel((0,0)),(0,0,255))
    def test_title_keeps_composition_while_sega_uses_first_tile(self):
        with patch.object(xmb,'_boot',return_value=b'own synthetic animation'),patch.object(xmb,'compose_title',return_value=Image.new('RGB',(640,480),(0,255,0))) as compose:
            r=xmb.prepare_xmb(self.data,self.root/'mixed',dict(xmb_icon_art='title',xmb_background_art='sega'))
        compose.assert_called_once()
        with Image.open(r['icon0']) as im:self.assertEqual(im.getpixel((0,0)),(0,255,0))
        with Image.open(r['pic1']) as im:self.assertEqual(im.getpixel((0,0)),(0,0,255))
        self.assertEqual(r['inputs']['icon0']['layout'],'boot_animation')
        self.assertEqual(r['inputs']['pic1']['layout'],'first_tile')
    def test_invalid_game_art_id_rejected_before_output(self):
        for slot in ('icon','background'):
            for value in ('unknown','TITLE.PRS','../sega','',None):
                out=self.root/'invalid'
                with self.subTest(slot=slot,value=value),self.assertRaises(ConverterError):
                    xmb.prepare_xmb(self.data,out,{'xmb_'+slot+'_art':value})
                self.assertFalse(out.exists())
    def test_none_needs_no_game_or_tools(self):
        r=xmb.prepare_xmb(self.root/'absent',self.root/'out',dict(xmb_icon_mode='none',xmb_background_mode='none'))
        self.assertTrue(all(r[k] is None for k in ('icon0','pic1','snd0')))
    def test_custom_crop_alpha_and_no_overwrite(self):
        p=self.root/'art.png';Image.new('RGBA',(300,300),(10,20,30,255)).save(p)
        s=dict(xmb_icon_mode='file',xmb_icon_file=p,xmb_background_mode='none')
        r=xmb.prepare_xmb(self.data,self.root/'out',s)
        with Image.open(r['icon0']) as im:self.assertEqual(im.size,(144,80))
        with self.assertRaises(ConverterError):xmb.prepare_xmb(self.data,self.root/'out',s)
    def test_custom_jpeg_exif_orientation_matches_preview_without_changing_source(self):
        from dcrc.storage import file_digest
        image=Image.new('RGB',(40,80),'red')
        image.paste(Image.new('RGB',(40,40),'blue'),(0,40))
        exif=Image.Exif();exif[274]=6  # Stored portrait pixels, displayed clockwise.
        source=self.root/'rotated.jpg';image.save(source,quality=100,subsampling=0,exif=exif)
        before=file_digest(source)
        r=xmb.prepare_xmb(self.data,self.root/'oriented',dict(xmb_icon_mode='file',
            xmb_icon_file=source,xmb_background_mode='none'))
        with Image.open(r['icon0']) as actual:
            left,right=actual.getpixel((10,10)),actual.getpixel((130,10))
            self.assertGreater(left[2],220);self.assertLess(left[0],30)
            self.assertGreater(right[0],220);self.assertLess(right[2],30)
        self.assertEqual(file_digest(source),before)
        self.assertEqual(r['inputs']['icon0']['input'],before)
    def test_ready_at3_validated_not_reencoded(self):
        p=self.root/'music.at3';p.write_bytes(at3())
        r=xmb.prepare_xmb(self.data,self.root/'out',dict(xmb_icon_mode='none',xmb_background_mode='none',xmb_music_mode='file',xmb_music_file=p))
        self.assertEqual(r['snd0'].read_bytes(),at3())
    def test_reject_bad_riff_and_nonatrac(self):
        valid=at3()
        for raw in (valid[:-1],valid+b'x',valid.replace(xmb.ATRAC_GUID,bytes(16)),riff([(b'fmt ',bytes(16)),(b'data',bytes(100))])):
            with self.subTest(raw=raw[:40]),self.assertRaises(ConverterError):xmb.validate_at3(raw)
    def test_reject_invalid_modes_track_traversal_and_nonfinite(self):
        for s in ({'xmb_icon_mode':'wat'},{'xmb_music_mode':'game','xmb_track':'../TITLE.ADX'}, {'xmb_music_mode':'game','xmb_music_seconds':float('nan')},{'xmb_music_mode':'game','xmb_music_seconds':12}):
            with self.subTest(s=s),self.assertRaises(ConverterError):xmb.prepare_xmb(self.data,self.root/('out'+str(len(list(self.root.iterdir())))),s)
    def test_pvr_size_format_twiddle_and_bounds(self):
        im=xmb.decode_art(prs_literals(pvm()))
        self.assertEqual(im.getpixel((7,7)),(255,0,0))
        for bad in (b'bad',prs_literals(pvm()[:-40]),prs_literals(pvm().replace(b'PVRT',b'XXXX'))):
            with self.assertRaises(ConverterError):xmb.decode_art(bad)
    def test_pvr_terminal_alignment_padding(self):
        raw=bytearray(pvm());struct.pack_into('<I',raw,68,8+128+16)
        self.assertEqual(xmb.decode_art(prs_literals(raw)).size,(8,8))
        raw[-1]=1
        with self.assertRaises(ConverterError):xmb.decode_art(prs_literals(raw))
    def test_source_preview_boot_only_folder_and_cancel_during(self):
        boot=b'owned synthetic boot';(self.data/'1ST_READ.BIN').write_bytes(boot)
        import hashlib
        with patch.object(xmb,'BOOT_BYTES',len(boot)),patch.object(xmb,'BOOT_SHA256',hashlib.sha256(boot).hexdigest()):
            with patch.object(xmb,'compose_title',return_value=Image.new('RGB',(640,480))):c=xmb.inspect_source_media(self.data)
            self.assertEqual(c['verification'],'boot_hash_only_preview')
            self.assertTrue(c['images'][0]['preview_png'].startswith(b'\x89PNG'))
            calls=[]
            def cancel():calls.append(1);return len(calls)>2
            with self.assertRaises(Cancelled):xmb.inspect_source_media(self.data,cancel=cancel)
        with self.assertRaises(ConverterError):xmb.inspect_source_media(self.data)
    def test_title_composition_reads_user_animation_not_archive_order(self):
        boot=bytearray(0x1b3b54+120)
        records=[]
        for i,tex in enumerate((2,1,0,5,4,3)):
            rec=(256,256,384-256*(i%3),-256*(i//3),256,0,0,256,tex,0)
            struct.pack_into('<8hHH',boot,0x1b3b54+i*20,*rec)
        def tile(_raw,name):
            n=int(name[-1]);im=Image.new('RGB',(256,256),(n*30,0,0));im.putpixel((255,0),(255,255,255));return im
        with patch.object(xmb,'decode_art',side_effect=tile):
            im=ImageOps.mirror(xmb.compose_title(b'owned',bytes(boot)))
            self.assertEqual(im.size,(640,480));self.assertEqual(im.getpixel((0,10)),(60,0,0))
            self.assertEqual(im.getpixel((200,10)),(30,0,0));self.assertEqual(im.getpixel((500,10)),(0,0,0))
            self.assertEqual(im.getpixel((192,0)),(255,255,255))
            struct.pack_into('<h',boot,0x1b3b54,999)
            with self.assertRaises(ConverterError):xmb.compose_title(b'owned',bytes(boot))
    def test_source_preview_actual_virtual_iso_reader(self):
        from test_disc import image,record
        import hashlib
        src=image(self.root/'disc',ss=2048,base=0);track=src.parent/'one.bin';raw=bytearray(track.read_bytes())
        directory=record(b'\0',20,2048,True)+record(b'\1',20,2048,True)+record('1ST_READ.BIN;1',21,5)+record('SONICADV',22,2048,True)
        raw[20*2048:21*2048]=directory+bytes(2048-len(directory))
        art=prs_literals(pvm());directory=record(b'\0',22,2048,True)+record(b'\1',20,2048,True)+record('TITLE.PRS;1',23,len(art))
        raw[22*2048:23*2048]=directory+bytes(2048-len(directory));raw[23*2048:23*2048+len(art)]=art;track.write_bytes(raw)
        with patch.object(xmb,'BOOT_BYTES',5),patch.object(xmb,'BOOT_SHA256',hashlib.sha256(b'hello').hexdigest()),patch.object(xmb,'compose_title',return_value=Image.new('RGB',(640,480))):
            c=xmb.inspect_source_media(src);self.assertEqual(c['images'][0]['id'],'title');self.assertEqual(len(c['tracks']),0)
    def test_encoder_package_resolution_and_explicit_override(self):
        bundle=self.root/'bundle';(bundle/'python').mkdir(parents=True);tools=bundle/'tools'/'atracdenc';tools.mkdir(parents=True)
        p=tools/'atracdenc.exe';p.write_bytes(b'owned fake encoder');other=self.root/'encoder';other.write_bytes(b'fake')
        with patch.object(xmb.sys,'executable',str(bundle/'python'/'python.exe')),patch('dcrc.media_tools.__file__',str(bundle/'app/dcrc/media_tools.py')),patch.object(xmb.shutil,'which',side_effect=AssertionError('must use packaged tool')):
            self.assertEqual(xmb.resolve_encoder(),p.resolve());self.assertEqual(xmb.resolve_encoder(other),other.resolve())
    def test_mock_external_audio_commands_frames_and_failure(self):
        calls=[];root=self.root
        class Runner:
            def __init__(self,*args):pass
            def run(self,argv,cwd=None,label=''):
                calls.append(argv)
                if label=='xmb_pcm':
                    self_test.assertIn('adx',argv)
                    with xmb.wave.open(argv[-1],'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(44100);w.writeframes(bytes(44100*4))
                else:
                    h=bytearray(96);h[:3]=b'EA3';h[5]=96;struct.pack_into('>I',h,32,(1<<24)|(1<<13)|(2<<10)|255)
                    (Path(cwd)/'output.oma').write_bytes(h+bytes(2048*27))
        self_test=self;tool=self.root/'tool';tool.write_bytes(b'owned stub identity')
        with patch.object(xmb,'CommandRunner',Runner):
            r=xmb.prepare_xmb(self.data,self.root/'out',dict(xmb_icon_mode='none',xmb_background_mode='none',xmb_music_mode='game',xmb_encoder=tool),ffmpeg=tool)
        self.assertEqual(len(calls),2);self.assertEqual(xmb.validate_at3(r['snd0'].read_bytes())['samples'],44100)
        self.assertEqual(calls[1][-4:],['-i','input.wav','-o','output.oma'])
        class Failed(Runner):
            def run(self,*a,**kw):raise ConverterError('command_failed','encoder failed')
        with patch.object(xmb,'CommandRunner',Failed),self.assertRaises(ConverterError):xmb.prepare_xmb(self.data,self.root/'fail',dict(xmb_icon_mode='none',xmb_background_mode='none',xmb_music_mode='game',xmb_encoder=tool),ffmpeg=tool)
        self.assertFalse((self.root/'fail'/'SND0.AT3').exists())
    def test_reject_symlink_media_input(self):
        p=self.root/'link';
        try:p.symlink_to(self.data,target_is_directory=True)
        except OSError:self.skipTest('host symlink unavailable')
        with self.assertRaises(ConverterError):xmb.inspect_media(p)
    def test_art_aba_reports_exact_consumed_bytes(self):
        import hashlib
        def png(color):
            b=io.BytesIO();Image.new('RGB',(32,32),color).save(b,format='PNG');return b.getvalue()
        original=png('red');consumed=png('blue');source=self.root/'custom.png';source.write_bytes(original)
        real=xmb._bounded
        def swap(path,limit):
            if Path(path)==source:
                source.write_bytes(consumed);raw=real(path,limit);source.write_bytes(original);return raw
            return real(path,limit)
        with patch.object(xmb,'_bounded',side_effect=swap):
            r=xmb.prepare_xmb(self.data,self.root/'out',dict(xmb_icon_mode='file',xmb_icon_file=source,xmb_background_mode='none'))
        self.assertEqual(source.read_bytes(),original)
        with Image.open(r['icon0']) as im:self.assertEqual(im.getpixel((0,0)),(0,0,255))
        self.assertEqual(r['inputs']['icon0']['input'],dict(bytes=len(consumed),sha256=hashlib.sha256(consumed).hexdigest()))
        self.assertNotEqual(r['inputs']['icon0']['input']['sha256'],hashlib.sha256(original).hexdigest())
    def test_audio_encoder_reads_owned_snapshot_after_original_mutates(self):
        import hashlib
        source=self.root/'custom.wav';original=b'owned audio A';source.write_bytes(original);calls=[]
        class Runner:
            def __init__(self,*args):pass
            def run(self,argv,cwd=None,label=''):
                calls.append(argv)
                if label=='xmb_pcm':
                    path=Path(argv[argv.index('-i')+1]);source.write_bytes(b'owned audio B')
                    self_test.assertNotEqual(path,source);self_test.assertEqual(path.read_bytes(),original)
                    with xmb.wave.open(argv[-1],'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(44100);w.writeframes(bytes(44100*4))
                else:
                    h=bytearray(96);h[:3]=b'EA3';h[5]=96;struct.pack_into('>I',h,32,(1<<24)|(1<<13)|(2<<10)|255)
                    (Path(cwd)/'output.oma').write_bytes(h+bytes(2048*27))
        self_test=self;tool=self.root/'tool';tool.write_bytes(b'own stub')
        with patch.object(xmb,'CommandRunner',Runner):
            r=xmb.prepare_xmb(self.data,self.root/'out',dict(xmb_icon_mode='none',xmb_background_mode='none',xmb_music_mode='file',xmb_music_file=source,xmb_encoder=tool),ffmpeg=tool)
        self.assertEqual(r['inputs']['snd0']['input'],dict(bytes=len(original),sha256=hashlib.sha256(original).hexdigest()))
    def test_ready_at3_identity_is_consumed_raw(self):
        import hashlib
        source=self.root/'custom.at3';original=at3();changed=bytearray(original);changed[-1]=1;source.write_bytes(original)
        real=xmb._bounded
        def swap(path,limit):
            if Path(path)==source:return bytes(changed)
            return real(path,limit)
        with patch.object(xmb,'_bounded',side_effect=swap):r=xmb.prepare_xmb(self.data,self.root/'out',dict(xmb_icon_mode='none',xmb_background_mode='none',xmb_music_mode='file',xmb_music_file=source))
        self.assertEqual(r['inputs']['snd0']['input']['sha256'],hashlib.sha256(changed).hexdigest())
    def test_cancel_before_io(self):
        e=threading.Event();e.set()
        with self.assertRaises(Cancelled):xmb.inspect_source_media(self.root/'missing.gdi',cancel=e)
        with self.assertRaises(Cancelled):xmb.prepare_xmb(self.data,self.root/'out',{},cancel=e)
    def test_missing_encoder_truthful_no_silent_music(self):
        with patch.object(xmb.sys,'executable',str(self.root/'host-python.exe')),patch.object(xmb.shutil,'which',return_value=None),self.assertRaisesRegex(ConverterError,'atracdenc'):
            xmb.prepare_xmb(self.data,self.root/'out',dict(xmb_icon_mode='none',xmb_background_mode='none',xmb_music_mode='game'))
    def test_oma_rewrap_exact_body_and_bad_header(self):
        h=bytearray(96);h[:3]=b'EA3';h[5]=96;struct.pack_into('>I',h,32,(1<<24)|(1<<13)|(2<<10)|255)
        r=xmb.wrap_oma(bytes(h)+bytes(2048*5),2048)
        info=xmb.validate_at3(r);self.assertEqual(info['samples'],2048);self.assertEqual(info['codec'],'ATRAC3plus')
        with self.assertRaises(ConverterError):xmb.wrap_oma(bytes(h)+b'x',2048)
    def test_fingerprint_ignores_local_input_output_roots(self):
        a=xmb.prepare_xmb(self.data,self.root/'out1',{})
        b=xmb.prepare_xmb(self.data,self.root/'out2',{})
        self.assertEqual(a['fingerprint'],b['fingerprint'])

if __name__=='__main__':unittest.main()
