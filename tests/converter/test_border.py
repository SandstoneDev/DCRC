import struct
from pathlib import Path
import pytest
from PIL import Image
from dcrc.errors import ConverterError
from dcrc.models import ConversionOptions

def test_border_edge_mapping_and_padding(tmp_path):
    from dcrc.border import encode_border
    image=Image.new('RGB',(480,272),(0,255,0))
    image.paste((255,0,0),(0,0,60,272));image.paste((0,0,255),(420,0,480,272))
    path=tmp_path/'own.png';image.save(path)
    blob=encode_border(path)
    assert struct.unpack_from('<4I',blob)==(0x31524244,128,512,131072)
    pixels=struct.unpack_from('<65536H',blob,16)
    for y in (0,135,271,272,511):
        assert pixels[y*128:y*128+64]==(31,)*64
        assert pixels[y*128+64:y*128+128]==(0xf800,)*64
    assert len(blob)==131088

def test_border_option_and_cli(tmp_path,monkeypatch):
    from dcrc.capabilities import PROFILE_CAPABILITIES
    monkeypatch.setitem(PROFILE_CAPABILITIES,'custom_border',True)
    from dcrc.cli import parser
    source=tmp_path/'own.gdi';source.touch();png=tmp_path/'border.png';Image.new('RGB',(32,32)).save(png)
    o=ConversionOptions(source,tmp_path/'out',border_image=png).validate()
    assert o.border_image==png.resolve()
    a=parser().parse_args(['convert',str(source),'--out',str(tmp_path/'out'),'--border-image',str(png)])
    assert a.border_image==png
    with pytest.raises(ConverterError):ConversionOptions(source,tmp_path/'out',border_image=tmp_path/'missing.png').validate()

def test_bad_border_declines(tmp_path):
    from dcrc.border import encode_border
    path=tmp_path/'bad.png';path.write_bytes(b'not an image')
    with pytest.raises(ConverterError):encode_border(path)


def test_border_honors_jpeg_exif_without_changing_source(tmp_path):
    from dcrc.border import encode_border
    from dcrc.storage import file_digest
    image=Image.new('RGB',(40,80),'red');image.paste(Image.new('RGB',(40,40),'blue'),(0,40))
    exif=Image.Exif();exif[274]=6
    path=tmp_path/'rotated.jpg';image.save(path,quality=100,subsampling=0,exif=exif)
    before=file_digest(path);pixels=struct.unpack_from('<65536H',encode_border(path),16)
    assert pixels[50*128+20]==0xf800  # Clockwise rotation puts blue at the left.
    assert pixels[50*128+64+20]==31
    assert file_digest(path)==before


def test_border_alpha_flattens_on_black_before_existing_resize(tmp_path):
    from dcrc.border import encode_border
    from dcrc.storage import file_digest
    image=Image.new('RGBA',(480,272),(0,0,255,255))
    image.paste((255,0,0,0),(0,0,60,272));image.paste((0,255,0,128),(420,0,480,272))
    path=tmp_path/'transparent.png';image.save(path);before=file_digest(path)
    pixels=struct.unpack_from('<65536H',encode_border(path),16)
    assert pixels[20]==0  # Hidden transparent red must not become an opaque red field.
    assert pixels[64+20]==1024  # Half-alpha green is composited against black.
    assert file_digest(path)==before
