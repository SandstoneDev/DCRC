import re
import threading
from pathlib import Path

from gui.session_log import SessionLog


def test_one_dated_file_keeps_operations_errors_and_worker_output(tmp_path):
    log = SessionLog(tmp_path)
    log.write('DLC catalog started')
    log.event({'type': 'log', 'message': 'download 12/24'})
    log.event({'type': 'error', 'message': 'network error', 'detail': 'trace detail'})
    log.event({'type': 'finished', 'result': {'images': [{'preview_png': b'PRIVATE_BYTES'}]}})
    assert re.fullmatch(r'DCRC_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_.+\.log', log.path.name)
    assert list(tmp_path.glob('*.log')) == [log.path]
    text = log.path.read_text(encoding='utf8')
    assert all(s in text for s in ('DLC catalog started', 'download 12/24', 'network error', 'trace detail'))
    assert 'PRIVATE_BYTES' not in text


def test_parallel_messages_and_native_already_logged_no_duplicate(tmp_path):
    log = SessionLog(tmp_path)
    threads = [threading.Thread(target=lambda n=n: log.write(f'line-{n}')) for n in range(30)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    with log.path.open('a', encoding='utf8') as stream: stream.write('native output\n')
    log.event({'type': 'log', 'message': 'native output', 'log_path': str(log.path)})
    text = log.path.read_text(encoding='utf8')
    assert text.count('native output') == 1
    assert len([s for s in text.splitlines() if 'line-' in s]) == 30


def test_same_second_instances_have_distinct_files(tmp_path):
    assert SessionLog(tmp_path).path != SessionLog(tmp_path).path


def test_source_frontend_never_writes_a_foreign_interpreter_bundle(tmp_path,monkeypatch):
    from gui import session_log
    bundle=tmp_path/'foreign';(bundle/'python').mkdir(parents=True);(bundle/'app/gui').mkdir(parents=True)
    (bundle/'BUNDLE_MANIFEST.json').write_text('{}');(bundle/'app/gui/run_gui.py').touch()
    monkeypatch.setattr(session_log.sys,'executable',str(bundle/'python/python.exe'))
    monkeypatch.setenv('APPDATA',str(tmp_path/'settings'))
    log=session_log.start_app_log()
    assert log.path.parent==tmp_path/'settings/DCRC Converter/logs'
    assert not (bundle/'logs').exists()
