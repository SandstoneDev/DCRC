"""Own synthetic converter tests; no game inputs or generated code."""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from dcrc.errors import ConverterError, Cancelled
from dcrc.models import ConversionOptions
from dcrc.storage import fingerprint_tree, StageCache, write_json, file_digest
from dcrc.package import verify_folder, configure_folder, claim_output, write_manifest
from dcrc.process import CommandRunner


def options(tmp_path, **kw):
    source = tmp_path/'source.gdi'; source.write_text('synthetic')
    return ConversionOptions(source=source, output=tmp_path/'out', **kw)


@pytest.mark.parametrize('kw', [dict(land_distance=0), dict(land_distance=101),
    dict(world_textures=32), dict(mip_levels=0), dict(mip_levels=9),
    dict(frame_skip='force:0'), dict(aspect='stretch'), dict(voice='fr'),
    dict(startup_character='shadow'), dict(startup_act=0), dict(jobs=0)])
def test_invalid_setting_is_rejected_before_outputs(tmp_path, kw):
    with pytest.raises(ConverterError): options(tmp_path, **kw).validate()
    assert not (tmp_path/'out').exists()


def test_normal_boot_and_psp_quality_default(tmp_path):
    o=options(tmp_path).validate()
    assert (o.world_textures,o.land_distance,o.startup_stage)==(64,100,'normal')


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows PSP compiler path limit')
def test_deep_output_uses_short_local_work_folder(tmp_path, monkeypatch):
    o = options(tmp_path)
    o.output = tmp_path / ('long-download-folder-' * 5) / 'game'
    local = Path(tmp_path.anchor) / 'dcrc-test-local'
    monkeypatch.setenv('LOCALAPPDATA', str(local))

    assert o.validate().work == local / 'DCRC' / 'work'
    assert not o.output.exists()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows PSP compiler path limit')
def test_short_and_explicit_work_paths_are_kept(tmp_path):
    root = Path(tmp_path.anchor) / 'dcrc-test-short'
    o = options(tmp_path)
    o.output = root / 'game'
    assert o.validate().work == root / '.dcrc-work'
    o.work = root / 'chosen'
    assert o.validate().work == root / 'chosen'


def test_source_output_overlap_rejected(tmp_path):
    source=tmp_path/'input';source.mkdir()
    with pytest.raises(ConverterError): ConversionOptions(source,source/'result').validate()


def test_content_fingerprint_detects_same_size_change(tmp_path):
    p=tmp_path/'a';p.write_bytes(b'aaaa');first=fingerprint_tree(tmp_path)
    p.write_bytes(b'bbbb');assert fingerprint_tree(tmp_path)!=first


def test_stage_cache_hashes_outputs_and_preserves_failed_run(tmp_path):
    cache=StageCache(tmp_path/'work');calls=[]
    def action(out):
        calls.append(out);(out/'payload').write_bytes(b'abcd');return {'file':str(out/'payload')}
    a=cache.run('extract','key1',action);assert len(calls)==1
    assert cache.run('extract','key1',action)==a and len(calls)==1
    Path(a['file']).write_bytes(b'xxxx')
    b=cache.run('extract','key1',action);assert len(calls)==2 and b!=a
    assert Path(a['file']).read_bytes()==b'xxxx'
    def fail(out):
        (out/'partial').write_text('keep');raise Cancelled()
    with pytest.raises(Cancelled):cache.run('compile','key2',fail)
    assert list((tmp_path/'work').rglob('partial'))

def test_foreign_work_folder_is_not_claimed(tmp_path):
    p=tmp_path/'work';p.mkdir();(p/'keep').write_text('keep')
    with pytest.raises(ConverterError):StageCache(p)
    assert not (p/'dcrc_workspace.json').exists()

def test_stage_result_cannot_point_to_another_run(tmp_path):
    cache=StageCache(tmp_path/'work')
    def action(out):
        (out/'payload').write_text('owned')
        return {'file':str(tmp_path/'outside')}
    with pytest.raises(ConverterError):cache.run('copy','key',action)


def test_foreign_nonempty_folder_is_not_claimed(tmp_path):
    p=tmp_path/'out';p.mkdir();(p/'my-file').write_text('keep')
    with pytest.raises(ConverterError):claim_output(p,'sa1_us_1005')
    assert (p/'my-file').read_text()=='keep'


def synthetic_package(tmp_path):
    p=tmp_path/'out';claim_output(p,'sa1_us_1005');(p/'data').mkdir()
    (p/'EBOOT.PBP').write_bytes(b'synthetic-eboot')
    (p/'data/asset').write_bytes(b'abcd')
    (p/'args.txt').write_text('--land-distance 100\n')
    write_manifest(p,{'profile':'sa1_us_1005','options':{}},mutable={'args.txt'})
    return p


def test_verify_is_content_based_and_mutable_settings_do_not_break_it(tmp_path):
    p=synthetic_package(tmp_path);assert verify_folder(p)['ok']
    (p/'args.txt').write_text('user choices')
    (p/'vmu').mkdir();(p/'vmu/save').write_bytes(b'own-save')
    assert verify_folder(p)['ok']
    (p/'data/asset').write_bytes(b'xxxx');r=verify_folder(p)
    assert not r['ok'] and any('asset' in str(v) for v in r['problems'])


@pytest.mark.parametrize('bad',['../outside','/absolute','volume:forbidden','data/../../outside','data\\..\\outside'])
def test_manifest_cannot_read_outside_output(tmp_path,bad):
    p=synthetic_package(tmp_path);m=json.loads((p/'dcrc_manifest.json').read_text())
    m['files'][bad]={'bytes':4,'sha256':'0'*64,'mutable':False}
    write_json(p/'dcrc_manifest.json',m)
    with pytest.raises(ConverterError):verify_folder(p)


def test_configure_preserves_saves_and_rejects_injected_cli(tmp_path):
    p=synthetic_package(tmp_path);(p/'vmu').mkdir();(p/'vmu/save').write_text('keep')
    configure_folder(p,land_distance=100,aspect='4:3',show_fps=False)
    text=(p/'args.txt').read_text();assert '--land-distance 100' in text and '--aspect' not in text
    ini=(p/'data/sa1psp.ini').read_text();assert 'aspect = 4:3' in ini
    assert '--frames' not in text and '--no-pad' not in text and '--stage' not in text
    assert (p/'vmu/save').read_text()=='keep'
    with pytest.raises(ConverterError):configure_folder(p,frame_skip='off\n--frames 1')


def test_silent_process_cancel_is_bounded(tmp_path):
    stop=threading.Event();runner=CommandRunner(tmp_path/'process.log',cancel_event=stop)
    timer=threading.Timer(.2,stop.set);timer.start();start=time.monotonic()
    try:
        with pytest.raises(Cancelled):runner.run([sys.executable,'-c','import time; time.sleep(30)'])
    finally:timer.cancel()
    assert time.monotonic()-start<5


def test_process_argv_is_not_a_shell(tmp_path):
    runner=CommandRunner(tmp_path/'process.log')
    runner.run([sys.executable,'-c','import sys;print(sys.argv[1])','a & echo unsafe'])
    assert 'a & echo unsafe' in (tmp_path/'process.log').read_text()
