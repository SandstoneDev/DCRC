"""Opaque-content pipeline ownership/cache regressions; synthetic inputs only."""
from pathlib import Path
import struct

import pytest

from dcrc.errors import ConverterError
from dcrc.models import ConversionOptions
from dcrc.storage import StageCache as RealStageCache, file_digest, tree_files


def pair(folder, stem='one', label='Own fixture'):
    folder.mkdir(parents=True, exist_ok=True)
    meta=bytearray(108);meta[4:4+len(label)]=label.encode('ascii')
    meta[88:100]=b'SONICADV_505';struct.pack_into('<I',meta,104,1024)
    image=bytearray(1024);struct.pack_into('<H',image,0x40,1)
    struct.pack_into('<I',image,0x48,384)
    a,b=folder/(stem+'.vmi'),folder/(stem+'.vms')
    a.write_bytes(meta);b.write_bytes(image)
    return a,b


@pytest.fixture
def pipeline_fixture(tmp_path,monkeypatch):
    import dcrc.disc as disc
    import dcrc.profiles as profiles
    import dcrc.toolchain as toolchains
    import dcrc.pipeline as pipeline
    from dcrc.native_build import make_pbp
    from dcrc.runtime_source import NOTICES
    source=tmp_path/'disc.gdi';source.write_text('own synthetic disc boundary')
    frozen=tmp_path/'frozen';frozen.mkdir();(frozen/'LICENSE').write_text('Own fixture')
    for rel in NOTICES:
        p=frozen/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Own notice fixture')
    raw=tmp_path/'raw';raw.mkdir();generated=tmp_path/'generated';generated.mkdir()
    profile=tmp_path/'profile';profile.mkdir();artifacts=tmp_path/'artifacts';artifacts.mkdir()
    files={}
    for name in ('EBOOT.PBP','sa1exc.prx','sa1prof.prx','sa1me.prx','sa1chain.prx'):
        p=artifacts/name;p.write_bytes(make_pbp(b'own synthetic payload','DCRC Port') if name=='EBOOT.PBP' else b'own helper')
        files[name]=str(p)
    payload=tmp_path/'payload';(payload/'data').mkdir(parents=True)
    (payload/'data/asset').write_bytes(b'own synthetic asset')
    results={'source':{'source_root':str(frozen)},'extract':{'data_root':str(raw)},
             'generate':{'generated':str(generated),'fingerprint':'own-generation'},
             'build':{'artifacts':files,'validation':{}},
             'assets':{'payload_root':str(payload),'files':{'asset':file_digest(payload/'data/asset')}}}
    state={'before_content':None,'wrong_result':False,'content_actions':0,'events':[]}
    class Stages:
        def __init__(self,root,event=None):
            self.cache=RealStageCache(Path(root)/'content-fixture',event)
        def run(self,name,key,action):
            if name!='content':return results[name]
            if state['before_content']:
                hook=state['before_content'];state['before_content']=None;hook()
            def build(out):
                state['content_actions']+=1
                result=action(out)
                if state['wrong_result']:result['fingerprint']='0'*64
                return result
            return self.cache.run(name,key,build)
    class Toolchain:
        def fingerprint(self):return 'own-toolchain'
    monkeypatch.setattr(disc,'inspect_source',lambda *a,**kw:{'fingerprint':'own-disc','boot':{'synthetic':True}})
    monkeypatch.setattr(profiles,'PROFILE_DIR',profile)
    monkeypatch.setattr(toolchains,'resolve',lambda path:Toolchain())
    monkeypatch.setattr(pipeline,'runtime_root',lambda:frozen)
    monkeypatch.setattr(pipeline,'source_files',lambda root:{})
    monkeypatch.setattr(pipeline,'StageCache',Stages)
    options=ConversionOptions(source,tmp_path/'output',work=tmp_path/'work')
    return pipeline,options,state


def test_outer_content_key_mutation_declined_before_stage_writes(pipeline_fixture,tmp_path):
    pipeline,options,state=pipeline_fixture
    _,image=pair(tmp_path/'content');options.dlc_dir=image.parent
    def mutate():
        data=bytearray(image.read_bytes());data[-1]=19;image.write_bytes(data)
    state['before_content']=mutate
    with pytest.raises(ConverterError):pipeline.convert(options)
    assert not options.output.exists()
    assert not list(options.work.rglob('events.txt'))


def test_valid_cache_receipt_wrong_input_fingerprint_cannot_package(pipeline_fixture,tmp_path):
    pipeline,options,state=pipeline_fixture
    pair(tmp_path/'content');options.dlc_dir=tmp_path/'content';state['wrong_result']=True
    # The real StageCache hashes this deliberately wrong result with its files.
    # A pipeline guard is needed even when the complete cache receipt is valid.
    for _ in range(2):
        with pytest.raises(ConverterError):pipeline.convert(options,event=state['events'].append)
        assert not options.output.exists()
    assert state['content_actions']==1
    assert any(e.get('stage')=='content' and e.get('state')=='cached' for e in state['events'])


def test_existing_unowned_content_rejected_before_any_output_mutation(pipeline_fixture,tmp_path):
    pipeline,options,_=pipeline_fixture
    pipeline.convert(options)
    foreign=options.output/'data/dlc/events.txt';foreign.parent.mkdir();foreign.write_bytes(b'own handwritten catalog')
    (foreign.parent/'event00.vms').write_bytes(b'own opaque user data')
    before=tree_files(options.output)
    pair(tmp_path/'content');options.dlc_dir=tmp_path/'content'
    with pytest.raises(ConverterError):pipeline.convert(options)
    assert tree_files(options.output)==before


def test_partial_owned_output_without_manifest_keeps_foreign_content(pipeline_fixture,tmp_path):
    from dcrc.package import claim_output
    pipeline,options,_=pipeline_fixture
    claim_output(options.output,options.profile)
    foreign=options.output/'data/dlc/events.txt';foreign.parent.mkdir(parents=True);foreign.write_text('own partial-import evidence')
    before=tree_files(options.output)
    pair(tmp_path/'content');options.dlc_dir=tmp_path/'content'
    with pytest.raises(ConverterError):pipeline.convert(options)
    assert tree_files(options.output)==before


def test_shrinking_import_preserves_owned_extras_and_can_repeat(pipeline_fixture,tmp_path):
    pipeline,options,_=pipeline_fixture
    pair(tmp_path/'content','one','First fixture')
    a,b=pair(tmp_path/'content','two','Second fixture')
    options.dlc_dir=tmp_path/'content';pipeline.convert(options)
    old=options.output/'data/dlc/events/event01.vms';before=old.read_bytes()
    a.unlink();b.unlink()
    pipeline.convert(options)
    assert old.read_bytes()==before
    catalog=(options.output/'data/dlc/events.txt').read_text()
    assert 'First fixture' in catalog and 'Second fixture' not in catalog
    pipeline.convert(options)
    assert old.read_bytes()==before


def test_reimport_updates_active_owned_files_instead_of_retaining_them(pipeline_fixture,tmp_path):
    pipeline,options,_=pipeline_fixture
    _,image=pair(tmp_path/'content');options.dlc_dir=image.parent
    pipeline.convert(options)
    changed=bytearray(image.read_bytes());changed[-1]=37;image.write_bytes(changed)
    pipeline.convert(options)
    assert (options.output/'data/dlc/events/event00.vms').read_bytes()==changed
