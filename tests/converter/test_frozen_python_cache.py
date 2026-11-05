import os
import sys
from dcrc.process import CommandRunner
from dcrc.storage import StageCache


def test_python_workers_do_not_mutate_frozen_source_cache(tmp_path):
    cache=StageCache(tmp_path/'work');calls=[]
    def source(run):
        calls.append(run)
        (run/'own_frozen_module.py').write_text('VALUE = 42\n')
        return {'source_root':str(run)}
    first=cache.run('source','own fixture',source)
    runner=CommandRunner(tmp_path/'process.log')
    runner.run([sys.executable,'-c','import own_frozen_module; assert own_frozen_module.VALUE == 42'],
        cwd=first['source_root'],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='0'))
    second=cache.run('source','own fixture',source)
    assert len(calls)==1
    assert second==first
