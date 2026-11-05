"""Independent review regressions against the production converter modules."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import threading
import time

import pytest

from dcrc.errors import Cancelled, ConverterError
from dcrc.storage import StageCache
from dcrc.process import CommandRunner
from dcrc.storage import file_digest


def _directory_link(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            raise
        # Own newly created test directories, no shell data supplied by a user.
        result = subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(link),str(target)],
                                capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            pytest.skip('Test machine cannot create a directory reparse point')


def test_stage_cache_rejects_linked_parent_before_any_action_write(tmp_path):
    outside = tmp_path/'outside-owned-work'; outside.mkdir()
    cache = StageCache(tmp_path/'work')
    _directory_link(tmp_path/'work'/'stages',outside)
    calls = []
    def action(run):
        calls.append(run)
        (run/'payload').write_bytes(b'own synthetic payload')
        return {'path':str(run/'payload')}
    with pytest.raises(ConverterError):
        cache.run('extract',{'input':'fixture'},action)
    assert calls == []
    assert list(outside.iterdir()) == []


def test_stage_cache_rejects_relocated_symlink_root_before_claim(tmp_path):
    outside = tmp_path/'outside'; outside.mkdir()
    link = tmp_path/'linked-work'; _directory_link(link,outside)
    with pytest.raises(ConverterError):
        StageCache(link)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize('damage',['json_array','typed_path'])
def test_invalid_json_receipt_schema_regenerates_instead_of_crashing_or_returning_invalid_paths(tmp_path,damage):
    cache = StageCache(tmp_path/'work')
    calls = []
    def action(run):
        calls.append(run)
        (run/'payload').write_bytes(b'own synthetic bytes')
        return {'data_root':str(run)}
    cache.run('extract','fixture',action)
    receipt = next((tmp_path/'work'/'stages').rglob('receipt.json'))
    old = json.loads(receipt.read_text())
    if damage == 'json_array':
        receipt.write_text('[]')
    else:
        old['result']['data_root'] = 0
        receipt.write_text(json.dumps(old))
    result = cache.run('extract','fixture',action)
    if damage == 'json_array':
        assert len(calls) == 2
    assert isinstance(result['data_root'],str)
    assert Path(result['data_root']).is_dir()


def test_cache_hit_does_not_trust_unhashed_outer_result_file_list(tmp_path):
    cache = StageCache(tmp_path/'work')
    def action(run):
        (run/'payload').write_bytes(b'own synthetic payload')
        return {'payload_root':str(run),'files':{'payload':file_digest(run/'payload')}}
    first = cache.run('assets','fixture',action)
    assert set(first['files']) == {'payload'}
    receipt = next((tmp_path/'work'/'stages').rglob('receipt.json'))
    outer = json.loads(receipt.read_text())
    outer['result']['files'] = {}
    receipt.write_text(json.dumps(outer))
    # Run files have not changed at all. This outer-only corruption must not
    # silently suppress owned payload paths on a later package/verify run.
    again = cache.run('assets','fixture',action)
    assert set(again['files']) == {'payload'}


def test_cache_result_receipt_does_not_make_an_empty_payload_stage_successful(tmp_path):
    cache = StageCache(tmp_path/'work')
    with pytest.raises(ConverterError) as error:
        cache.run('assets','fixture',lambda run:{})
    assert error.value.code == 'empty_stage'


def _alive(pid):
    if os.name != 'nt':
        try:
            os.kill(pid,0)
            return True
        except ProcessLookupError:
            return False
    import ctypes as c
    from ctypes import wintypes as w
    kernel = c.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD,w.BOOL,w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE,c.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        return False
    try:
        code = w.DWORD()
        return bool(kernel.GetExitCodeProcess(handle,c.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(handle)


def test_silent_parent_and_grandchild_cancel_without_killing_unrelated_python(tmp_path):
    stop = threading.Event()
    child_pid_file = tmp_path/'owned-child.json'
    # This process was not created by CommandRunner and must survive Stop.
    creation = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    unrelated = subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],**creation)
    runner = CommandRunner(tmp_path/'owned.log',cancel_event=stop)
    parent = ('import subprocess,sys,time,json; from pathlib import Path; '
              'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
              'Path(sys.argv[1]).write_text(json.dumps(child.pid)); time.sleep(30)')
    started = time.monotonic()
    def cancel_after_child():
        for _ in range(200):
            if child_pid_file.exists():
                stop.set()
                return
            time.sleep(.02)
        stop.set()
    trigger = threading.Thread(target=cancel_after_child)
    trigger.start()
    try:
        with pytest.raises(Cancelled):
            runner.run([sys.executable,'-c',parent,str(child_pid_file)])
        trigger.join(timeout=1)
        assert child_pid_file.exists(), 'owned child must exist before testing tree cancellation'
        child_pid = json.loads(child_pid_file.read_text())
        for _ in range(100):
            if not _alive(child_pid):
                break
            time.sleep(.02)
        assert not _alive(child_pid)
        assert unrelated.poll() is None
        assert time.monotonic()-started < 7
    finally:
        stop.set()
        trigger.join(timeout=1)
        unrelated.terminate()
        unrelated.wait(timeout=3)


def test_custom_title_cache_same_size_corruption_is_not_promoted_to_verified_output(tmp_path,monkeypatch):
    """Use synthetic cached stage boundaries; exercise actual title/copy/manifest path."""
    import dcrc.disc as disc
    import dcrc.profiles as profiles
    import dcrc.toolchain as toolchains
    import dcrc.pipeline as pipeline
    from dcrc.models import ConversionOptions
    from dcrc.native_build import make_pbp
    from dcrc.package import verify_folder
    source = tmp_path/'disc.gdi';source.write_text('own fixture, not a real image')
    frozen = tmp_path/'frozen';frozen.mkdir();(frozen/'LICENSE').write_text('own licence fixture')
    from dcrc.runtime_source import NOTICES
    for rel in NOTICES:
        path=frozen/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('Synthetic notice fixture')
    raw = tmp_path/'raw';raw.mkdir()
    generated = tmp_path/'generated';generated.mkdir()
    profile = tmp_path/'profile';profile.mkdir()
    artifacts = tmp_path/'artifacts';artifacts.mkdir()
    original = make_pbp(b'own synthetic stage payload','DCRC Port')
    files = {}
    for name in ('EBOOT.PBP','sa1exc.prx','sa1prof.prx','sa1me.prx','sa1chain.prx'):
        p = artifacts/name;p.write_bytes(original if name == 'EBOOT.PBP' else b'own helper fixture')
        files[name] = str(p)
    payload = tmp_path/'payload';(payload/'data').mkdir(parents=True)
    (payload/'data/asset.bin').write_bytes(b'own asset fixture')
    results = {'source':{'source_root':str(frozen)},'extract':{'data_root':str(raw)},
               'generate':{'generated':str(generated),'fingerprint':'fixture-generation'},
               'build':{'artifacts':files,'validation':{}},
               'assets':{'payload_root':str(payload),'files':{'asset.bin':file_digest(payload/'data/asset.bin')}}}
    class CachedStages:
        def __init__(self,root,event=None):Path(root).mkdir(parents=True,exist_ok=True)
        def run(self,name,key,action):return results[name]
    class Toolchain:
        def fingerprint(self):return 'own-fixture-toolchain'
    monkeypatch.setattr(disc,'inspect_source',lambda *args,**kwargs:{'fingerprint':'own-source','boot':{'fixture':True}})
    monkeypatch.setattr(profiles,'PROFILE_DIR',profile)
    monkeypatch.setattr(toolchains,'resolve',lambda path:Toolchain())
    monkeypatch.setattr(pipeline,'runtime_root',lambda:frozen)
    monkeypatch.setattr(pipeline,'source_files',lambda root:{})
    monkeypatch.setattr(pipeline,'StageCache',CachedStages)
    options = ConversionOptions(source,tmp_path/'out',work=tmp_path/'work',title='Own custom title')
    pipeline.convert(options)
    baseline = (options.output/'EBOOT.PBP').read_bytes()
    assert verify_folder(options.output)['ok']
    for rel in NOTICES:
        assert (options.output/rel).read_bytes() == (frozen/rel).read_bytes()
    notice=options.output/NOTICES[-1]
    notice.write_text('Changed notice fixture')
    assert not verify_folder(options.output)['ok']
    notice.write_bytes((frozen/NOTICES[-1]).read_bytes())
    cached = next((options.work/'titles').glob('*.PBP'))
    damaged = bytearray(cached.read_bytes());damaged[0] ^= 255;cached.write_bytes(damaged)
    pipeline.convert(options)
    assert (options.output/'EBOOT.PBP').read_bytes() == baseline
    assert verify_folder(options.output)['ok']


def test_repair_cancel_after_settings_write_preserves_original_user_bytes(tmp_path,monkeypatch):
    import dcrc.pipeline as pipeline
    from dcrc.package import claim_output,write_manifest
    folder = tmp_path/'out';claim_output(folder,'sa1_us_1005')
    (folder/'data').mkdir()
    args = b'--land-distance 77\n# handwritten setting\n'
    ini = b'voice = ja\n# keep this byte for byte\n'
    (folder/'args.txt').write_bytes(args)
    (folder/'data/sa1psp.ini').write_bytes(ini)
    write_manifest(folder,{'profile':'sa1_us_1005','options':{'source':str(tmp_path/'fixture.gdi'),'output':str(folder)}})
    def fail_after_setting_write(options,**kwargs):
        (folder/'args.txt').write_text('--land-distance 100\n')
        (folder/'data/sa1psp.ini').write_text('voice = en\n')
        raise Cancelled('own simulated cancellation at final verify boundary')
    monkeypatch.setattr(pipeline,'convert',fail_after_setting_write)
    with pytest.raises(Cancelled):
        pipeline.repair_folder(folder)
    assert (folder/'args.txt').read_bytes() == args
    assert (folder/'data/sa1psp.ini').read_bytes() == ini
