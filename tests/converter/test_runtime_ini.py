from pathlib import Path
from dcrc.models import ConversionOptions
from dcrc.package import runtime_text

def test_player_options_live_in_editable_ini_not_conflicting_launch_flags():
    opts=ConversionOptions(Path('own.gdi'),Path('new-output'),aspect='4:3',show_fps=False,
        startup_stage='emerald_coast',startup_character='tails',startup_act=2)
    args,ini=runtime_text(opts)
    for flag in ('--aspect','--fps-hud','--frame-skip','--gu-max-mip','--stage','--character','--act'):
        assert flag not in args
    for value in ('aspect = 4:3','fps_hud = off','frame_skip = auto','mip_levels = 8',
                  'start_stage = emerald_coast','start_character = tails','start_act = 2'):
        assert value in ini

def test_normal_boot_explicitly_disables_startup_warp():
    _,ini=runtime_text(ConversionOptions(Path('own.gdi'),Path('new-output')))
    assert 'start_stage = off' in ini



def test_repeat_conversion_replaces_owned_ini_values_and_preserves_user_dlc(tmp_path,monkeypatch):
    """Real packaging/settings path; cached synthetic stages never build or run a game."""
    from dataclasses import replace
    from collections import Counter
    import dcrc.disc as disc
    import dcrc.profiles as profiles
    import dcrc.toolchain as toolchain
    import dcrc.pipeline as pipeline
    import dcrc.runtime_source as runtime_source
    from dcrc.package import verify_folder
    from dcrc.storage import file_digest

    source=tmp_path/'disc.gdi';source.write_text('own synthetic source')
    frozen=tmp_path/'frozen';frozen.mkdir()
    (frozen/'LICENSE').write_text('own synthetic licence')
    for relative in getattr(runtime_source,'NOTICES',()):
        notice=frozen/relative;notice.parent.mkdir(parents=True,exist_ok=True)
        notice.write_text('own synthetic notice')
    artifacts={}
    for name in ('EBOOT.PBP','sa1exc.prx','sa1prof.prx','sa1me.prx','sa1chain.prx'):
        path=tmp_path/name;path.write_bytes(b'own synthetic artifact');artifacts[name]=str(path)
    payload=tmp_path/'payload';(payload/'data').mkdir(parents=True)
    asset=payload/'data/asset';asset.write_bytes(b'own synthetic asset')
    profile=tmp_path/'profile';profile.mkdir()
    results={'source':{'source_root':str(frozen)},'extract':{'data_root':str(tmp_path/'raw')},
             'generate':{'generated':str(tmp_path/'generated'),'fingerprint':'synthetic'},
             'build':{'artifacts':artifacts,'validation':{}},
             'assets':{'payload_root':str(payload),'files':{'asset':file_digest(asset)}}}
    class CachedStages:
        def __init__(self,root,event=None):Path(root).mkdir(parents=True,exist_ok=True)
        def run(self,name,key,action):return results[name]
    class Toolchain:
        def fingerprint(self):return 'synthetic-toolchain'
    monkeypatch.setattr(disc,'inspect_source',lambda *a,**kw:{'fingerprint':'synthetic','boot':{}})
    monkeypatch.setattr(profiles,'PROFILE_DIR',profile)
    monkeypatch.setattr(toolchain,'resolve',lambda path:Toolchain())
    monkeypatch.setattr(pipeline,'runtime_root',lambda:frozen)
    monkeypatch.setattr(pipeline,'source_files',lambda root:{})
    monkeypatch.setattr(pipeline,'StageCache',CachedStages)
    old=ConversionOptions(source,tmp_path/'output',work=tmp_path/'work',aspect='4:3',
        frame_skip='2',mip_levels=2,show_fps=False,audio=True,voice='ja',
        startup_stage='emerald_coast',startup_character='tails',startup_act=2)
    pipeline.convert(old)
    ini=old.output/'data/sa1psp.ini'
    with ini.open('a',encoding='utf-8') as stream:
        stream.write('debug_menu = off\ngu_max_mip = 1\ncustom_user = preserve me\ndlc_event = My local event\n')
    new=replace(old,aspect='wide',frame_skip='off',mip_levels=6,show_fps=True,
        audio=False,voice='game',startup_stage='normal',startup_character='big',startup_act=3)
    pipeline.convert(new)
    text=ini.read_text()
    pairs=[(line.split('=',1)[0].strip(),line.split('=',1)[1].strip())
           for line in text.splitlines() if '=' in line and not line.lstrip().startswith(('#',';'))]
    counts=Counter(key for key,value in pairs)
    expected={'aspect':'wide','frame_skip':'off','mip_levels':'6','fps_hud':'on',
              'debug_menu':'on','voice':'game','audio':'off','renderer':'ta','land_cull':'on',
              'event_skip':'on','math':'native','start_stage':'off','start_character':'big','start_act':'3',
              'custom_user':'preserve me','dlc_event':'My local event'}
    # Public TA and primary native renderer defaults deliberately differ.
    expected['renderer']=dict(line.split('=',1) for line in
        runtime_text(new)[1].replace(' = ','=').splitlines() if '=' in line)['renderer']
    assert {key:counts[key] for key in expected} == dict.fromkeys(expected,1)
    assert dict(pairs) == expected
    assert 'gu_max_mip' not in counts
    assert verify_folder(new.output)['ok']
    pipeline.convert(new)
    assert ini.read_text() == text
