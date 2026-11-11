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

@pytest.mark.parametrize('changed', [False, True])
def test_resume_legacy_owned_border(tmp_path, monkeypatch, changed):
    from dcrc import disc
    from dcrc.border import encode_border
    from dcrc.package import claim_output, write_manifest
    from dcrc.pipeline import convert

    class IdentifyReached(Exception):
        pass

    def stop_after_preflight(*args, **kwargs):
        raise IdentifyReached

    disc_path = tmp_path / 'own.gdi'
    disc_path.touch()
    image = tmp_path / 'old.png'
    Image.new('RGB', (16, 16), 'blue').save(image)
    output = tmp_path / 'output'
    claim_output(output, 'sa1_us_1005')
    border = output / 'border.bin'
    original = encode_border(image)
    border.write_bytes(original)
    write_manifest(output, {'profile': 'sa1_us_1005', 'options': {'border_mode': 'default'}})
    if changed:
        border.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    before = border.read_bytes()
    monkeypatch.setattr(disc, 'inspect_source', stop_after_preflight)
    options = ConversionOptions(disc_path, output, border_mode='none')
    if changed:
        with pytest.raises(ConverterError) as error:
            convert(options)
        assert error.value.code == 'foreign_content'
    else:
        with pytest.raises(IdentifyReached):
            convert(options)
    assert border.read_bytes() == before


def test_changed_payload_keeps_previous_manifest(tmp_path):
    from dcrc.package import MANIFEST, write_manifest
    from dcrc.storage import file_digest

    border = tmp_path / 'border.bin'
    border.write_bytes(b'original border')
    metadata = {'profile': 'sa1_us_1005'}
    write_manifest(tmp_path, metadata)
    saved = (tmp_path / MANIFEST).read_bytes()
    expected = {'border.bin': file_digest(border)}
    border.write_bytes(b'changed border')
    with pytest.raises(ConverterError) as error:
        write_manifest(tmp_path, metadata, owned=expected)
    assert error.value.code == 'write_readback'
    assert (tmp_path / MANIFEST).read_bytes() == saved
