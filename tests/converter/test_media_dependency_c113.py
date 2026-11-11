"""Dependency receipts and discovery are not distribution permission."""
import json
from pathlib import Path
import pytest
from converter.build_bundle import verify_ffmpeg_dependency,copy_ffmpeg_dependency,digest
from dcrc import media_tools

def dependency(root):
    root.mkdir();files={}
    for name in ('ffmpeg.exe','ffprobe.exe','README.txt','PROVENANCE.json','LICENSE.GPL-2.0.txt'):
        p=root/name;p.write_bytes(b'synthetic dependency fixture')
        e=digest(p);files[name]={'bytes':e['size'],'sha256':e['sha256']}
    (root/'MANIFEST.json').write_text(json.dumps({'format':'DCRC_FFMPEG_DEPENDENCY_V1','files':files}),encoding='utf8')
    return files

def test_exact_copy_readback_and_changed_or_unlisted_file_declined(tmp_path):
    source=tmp_path/'dependency';files=dependency(source)
    assert verify_ffmpeg_dependency(source)==files
    assert copy_ffmpeg_dependency(source,tmp_path/'copy')==files
    (source/'unlisted.bin').write_bytes(b'unknown')
    with pytest.raises(ValueError):verify_ffmpeg_dependency(source)
    (source/'unlisted.bin').unlink()
    (source/'ffmpeg.exe').write_bytes(b'changed')
    with pytest.raises(ValueError):verify_ffmpeg_dependency(source)

def test_foreign_interpreter_sibling_never_supplies_media_tool(tmp_path,monkeypatch):
    python=tmp_path/'foreign/python/python.exe';python.parent.mkdir(parents=True);python.touch()
    sibling=tmp_path/'foreign/tools/ffmpeg/ffmpeg.exe';sibling.parent.mkdir(parents=True);sibling.touch()
    monkeypatch.setattr(media_tools.sys,'executable',str(python))
    monkeypatch.setattr(media_tools.shutil,'which',lambda name:None)
    assert media_tools.find_tool('ffmpeg') is None
    assert media_tools.find_tool('ffmpeg',sibling)==sibling.resolve()
