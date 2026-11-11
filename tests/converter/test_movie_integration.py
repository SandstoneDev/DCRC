"""Own synthetic movie-stage/package integration; never invokes an encoder."""
import json
import threading
from pathlib import Path

import pytest

from dcrc.errors import Cancelled,ConverterError
from dcrc.models import ConversionOptions
from dcrc.storage import StageCache,file_digest,tree_files
from test_content_pipeline import pipeline_fixture


@pytest.fixture(autouse=True)
def enabled_hook_contract(monkeypatch):
    # Exercises prepared converter integration independently of release enablement.
    from dcrc.capabilities import PROFILE_CAPABILITIES
    monkeypatch.setitem(PROFILE_CAPABILITIES,'movie_playback',True)


def test_movie_defaults_cli_and_typed_gui(tmp_path):
    from dcrc.cli import parser
    from gui.controller import settings_values
    source=tmp_path/'source';source.write_text('own fixture')
    o=ConversionOptions(source,tmp_path/'out')
    assert o.movies is False and o.ffmpeg is None
    assert parser().parse_args(['convert',str(source),'--out',str(tmp_path/'out')]).movies is False
    assert parser().parse_args(['configure',str(tmp_path/'out')]).movies is None
    assert parser().parse_args(['convert',str(source),'--out',str(tmp_path/'out'),'--no-movies']).movies is False
    assert parser().parse_args(['convert',str(source),'--out',str(tmp_path/'out'),'--ffmpeg','own-encoder']).ffmpeg==Path('own-encoder')
    assert settings_values({})['movies'] is False
    with pytest.raises(ValueError):settings_values({'movies':'false'})
    with pytest.raises(ConverterError):ConversionOptions(source,tmp_path/'out',movies=1).validate()


@pytest.fixture
def movie_pipeline(pipeline_fixture,monkeypatch):
    import dcrc.movies as movies
    pipeline,options,state=pipeline_fixture
    options.movies=True
    tools_folder=pipeline.runtime_root()/'tools';tools_folder.mkdir()
    for name in ('movie_pmfmux.py','movie_pmfinfo.py'):(tools_folder/name).write_text('own synthetic implementation boundary')
    state.update(movie_actions=0,resolve_calls=0,version='first',order=[],wrong_movie_fp=False,wrong_tool=False,damage=False)
    tools={'ffmpeg':'own-ffmpeg','ffprobe':'own-ffprobe','identity':{'ffmpeg':{'bytes':1,'sha256':'1'*64},'ffprobe':{'bytes':1,'sha256':'2'*64}}}
    def inspect(source,*,cancel=None):return {'fingerprint':state['version'],'inputs':{},'movies':[]}
    def resolve(*a,**kw):state['resolve_calls']+=1;return tools
    def stage(source,out,ffmpeg,runner,event=None,cancel=None,*,expected_fingerprint=None,expected_tool_identity=None):
        assert expected_fingerprint==state['version'] and expected_tool_identity==tools['identity']
        state['movie_actions']+=1
        data=out/'data';folder=data/'MOVIE';folder.mkdir(parents=True)
        state['media_data']=data
        for name in movies.NAMES:
            for ext in ('pmf','wav'):(folder/(name+'.'+ext)).write_bytes(('own '+name+ext+state['version']).encode())
        (folder/'movies.json').write_text('own synthetic index')
        files=tree_files(data)
        if state['damage']:(folder/(movies.NAMES[0]+'.pmf')).write_bytes(b'changed after receipt')
        return {'data_root':str(data),'files':files,'fingerprint':'bad' if state['wrong_movie_fp'] else state['version'],
                'tool_identity':{} if state['wrong_tool'] else tools['identity']}
    monkeypatch.setattr(movies,'inspect_movies',inspect)
    monkeypatch.setattr(movies,'resolve_tools',resolve)
    monkeypatch.setattr(movies,'stage_movies',stage)
    original=pipeline.StageCache
    class Stages(original):
        def __init__(self,root,event=None):
            super().__init__(root,event);self.movies=StageCache(Path(root)/'movies-fixture',event)
        def run(self,name,key,action):
            state['order'].append(name)
            if name=='build' and state.get('during_build'):state['during_build']()
            return self.movies.run(name,key,action) if name=='movies' else super().run(name,key,action)
    monkeypatch.setattr(pipeline,'StageCache',Stages)
    return pipeline,options,state,tools


def test_movies_cache_stage_order_and_disabled_retention(movie_pipeline):
    from dcrc.package import verify_folder
    pipeline,o,s,tools=movie_pipeline
    pipeline.convert(o)
    assert s['order'].index('extract')<s['order'].index('movies')<s['order'].index('build')
    before=tree_files(o.output/'data/MOVIE');assert len(before)==21
    assert 'movies = on' in (o.output/'data/sa1psp.ini').read_text()
    pipeline.convert(o);assert s['movie_actions']==1
    tools['identity']['ffmpeg']['sha256']='3'*64
    pipeline.convert(o);assert s['movie_actions']==2
    (pipeline.runtime_root()/'tools/movie_pmfmux.py').write_text('own changed format implementation')
    pipeline.convert(o);assert s['movie_actions']==3
    o.movies=False;calls=s['resolve_calls'];pipeline.convert(o)
    assert s['resolve_calls']==calls and tree_files(o.output/'data/MOVIE')==before
    manifest=json.loads((o.output/'dcrc_manifest.json').read_text())
    assert all('data/MOVIE/'+rel in manifest['files'] for rel in before)
    assert 'movies = off' in (o.output/'data/sa1psp.ini').read_text() and verify_folder(o.output)['ok']


def test_missing_movie_tool_fails_before_work_or_heavy_stages(movie_pipeline,monkeypatch):
    import dcrc.movies as movies
    pipeline,o,s,_=movie_pipeline
    def missing(*a,**kw):raise ConverterError('movies_tools','Choose ffmpeg or turn movies off.')
    monkeypatch.setattr(movies,'resolve_tools',missing)
    with pytest.raises(ConverterError):pipeline.convert(o)
    assert not o.work.exists() and not o.output.exists() and s['order']==[]


@pytest.mark.parametrize('flag',['wrong_movie_fp','wrong_tool','damage'])
def test_movie_result_rechecked_before_build_or_package(movie_pipeline,flag):
    pipeline,o,s,_=movie_pipeline;s[flag]=True
    with pytest.raises(ConverterError):pipeline.convert(o)
    assert 'build' not in s['order'] and not o.output.exists()


@pytest.mark.parametrize('modified_owned',[False,True])
def test_movies_preserve_foreign_or_modified_files(movie_pipeline,modified_owned):
    pipeline,o,s,_=movie_pipeline
    if modified_owned:pipeline.convert(o)
    else:
        o.movies=False;pipeline.convert(o);o.movies=True
    p=o.output/'data/MOVIE/SLH448_1.pmf';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'own modified or foreign file')
    before=tree_files(o.output)
    with pytest.raises(ConverterError):pipeline.convert(o)
    assert tree_files(o.output)==before


@pytest.mark.parametrize('update',[False,True])
def test_movies_cancelled_package_resumes_without_overwrite(movie_pipeline,update):
    pipeline,o,s,_=movie_pipeline
    if update:pipeline.convert(o);s['version']='second'
    stop=threading.Event()
    def event(e):
        if e.get('type')=='progress' and e.get('message')=='data/MOVIE/SA1_600.pmf':stop.set()
    with pytest.raises(Cancelled):pipeline.convert(o,event=event,cancel_event=stop)
    p=o.output/'data/MOVIE/SA1_600.pmf';digest=file_digest(p);stamp=p.stat().st_mtime_ns
    pipeline.convert(o)
    assert file_digest(p)==digest and p.stat().st_mtime_ns==stamp


def test_disabled_movies_preserve_unknown_and_do_not_adopt_modified_media(movie_pipeline):
    pipeline,o,s,_=movie_pipeline;pipeline.convert(o)
    p=o.output/'data/MOVIE/SLH448_1.pmf';p.write_bytes(b'own changed movie')
    unknown=p.parent/'notes.txt';unknown.write_bytes(b'own notes')
    o.movies=False;pipeline.convert(o)
    assert p.read_bytes()==b'own changed movie' and unknown.read_bytes()==b'own notes'
    m=json.loads((o.output/'dcrc_manifest.json').read_text())
    assert 'data/MOVIE/SLH448_1.pmf' not in m['files'] and 'data/MOVIE/notes.txt' not in m['files']
    before=tree_files(o.output);o.movies=True
    with pytest.raises(ConverterError):pipeline.convert(o)
    assert tree_files(o.output)==before


def test_configure_old_default_off_enable_requires_all_owned_assets(tmp_path):
    from dcrc.package import claim_output,write_manifest,configure_folder
    from dcrc.movies import NAMES
    p=tmp_path/'out';claim_output(p,'sa1_us_1005');(p/'data').mkdir()
    (p/'args.txt').write_text('own args');write_manifest(p,{'profile':'sa1_us_1005','options':{}})
    configure_folder(p,aspect='4:3')
    assert 'movies = off' in (p/'data/sa1psp.ini').read_text()
    before=tree_files(p)
    with pytest.raises(ConverterError,match='[Rr]econvert'):configure_folder(p,movies=True)
    assert tree_files(p)==before
    media=p/'data/MOVIE';media.mkdir()
    for name in NAMES:
        for ext in ('pmf','wav'):(media/(name+'.'+ext)).write_bytes(b'own synthetic media')
    # Mere presence is not ownership.
    with pytest.raises(ConverterError):configure_folder(p,movies=True)
    m=json.loads((p/'dcrc_manifest.json').read_text());write_manifest(p,{'profile':'sa1_us_1005','options':m['options']})
    configure_folder(p,movies=True);assert 'movies = on' in (p/'data/sa1psp.ini').read_text()
    (media/'SA1_600.wav').write_bytes(b'modified')
    before=tree_files(p)
    with pytest.raises(ConverterError):configure_folder(p,movies=True)
    assert tree_files(p)==before


@pytest.mark.parametrize('target',['stage','output'])
def test_movie_mutation_during_build_declined_before_package_writes(movie_pipeline,target):
    pipeline,o,s,_=movie_pipeline
    if target=='output':pipeline.convert(o)
    before=tree_files(o.output) if o.output.exists() else None
    def mutate():
        p=(s['media_data'] if target=='stage' else o.output/'data')/'MOVIE/SLH448_1.pmf'
        p.write_bytes(b'own mutation while build was running')
    s['during_build']=mutate
    with pytest.raises(ConverterError):pipeline.convert(o)
    if target=='stage':assert not o.output.exists()
    else:
        after=tree_files(o.output)
        changed=[name for name in before if before[name]!=after[name]]
        assert changed==['data/MOVIE/SLH448_1.pmf']
