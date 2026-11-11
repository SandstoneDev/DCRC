from pathlib import Path
import pytest
from dcrc.controls import DEFAULT_CONTROL_MAP,validate_control_map,parse_bindings
from dcrc.models import ConversionOptions
from dcrc.package import runtime_text
from dcrc.errors import ConverterError

def test_defaults_and_serialization():
    opts=ConversionOptions(Path('.'),Path('out')).validate(check_paths=False)
    assert opts.control_map==DEFAULT_CONTROL_MAP
    _,ini=runtime_text(opts)
    parsed={key.removeprefix('control_'):value.strip() for line in ini.splitlines() if line.startswith('control_') for key,value in [line.replace(' ','').split('=',1)]}
    assert validate_control_map(parsed)==DEFAULT_CONTROL_MAP
    opts.control_map=validate_control_map({"cross":"b","circle":"a","r":"disabled"})
    assert "control_cross = b" in runtime_text(opts)[1]

def test_swaps_disabled_duplicates():
    mapping=parse_bindings(['cross=b','circle=a','select=ltrigger','l=a','r=disabled'])
    assert mapping['cross']=='b' and mapping['circle']=='a'
    assert mapping['l']=='a' and mapping['r']=='disabled'
    assert validate_control_map(mapping)==mapping

@pytest.mark.parametrize('mapping',[{'home':'a'},{'cross':'HOME'},{'cross':None},[],{'cross':'a\ncontrol_home=b'}])
def test_invalid(mapping):
    with pytest.raises(ConverterError):validate_control_map(mapping)

def test_no_shared_defaults():
    a=validate_control_map();a['cross']='disabled'
    assert validate_control_map()['cross']=='a'

def test_cli_parser():
    from dcrc.cli import parser
    assert parser().parse_args(['configure','out','--control','cross=b']).control_map==['cross=b']


def test_configure_existing_roundtrip_and_reset(tmp_path):
    from dcrc.package import configure_folder,write_manifest,MANIFEST
    from dcrc.storage import read_json
    (tmp_path/'data').mkdir()
    (tmp_path/'data/sa1psp.ini').write_text('control_cross = y\ncustom = preserved\n')
    write_manifest(tmp_path,{'profile':'sa1_us_1005','options':{'movies':False}})
    result=configure_folder(tmp_path,control_map={'cross':'b','circle':'a','r':'disabled'})
    assert result['settings']['control_map']['cross']=='b'
    text=(tmp_path/'data/sa1psp.ini').read_text()
    assert text.count('control_cross')==1 and 'control_cross = b' in text
    assert 'custom = preserved' in text
    assert read_json(tmp_path/MANIFEST)['options']['control_map']['r']=='disabled'
    configure_folder(tmp_path,control_map={})
    assert 'control_cross = a' in (tmp_path/'data/sa1psp.ini').read_text()
    assert read_json(tmp_path/'dcrc_settings.json')['control_map']==DEFAULT_CONTROL_MAP

def test_qt_editor_roundtrip(monkeypatch):
    import os
    monkeypatch.setenv('QT_QPA_PLATFORM','windows' if os.name=='nt' else 'offscreen')
    qt=pytest.importorskip('PySide6.QtWidgets')
    from gui.controls import ControlsEditor
    app=qt.QApplication.instance() or qt.QApplication([])
    editor=ControlsEditor({'cross':'b','select':'ltrigger'})
    assert editor.value()['cross']=='b' and editor.value()['select']=='ltrigger'
    editor.set_value({})
    assert editor.value()==DEFAULT_CONTROL_MAP
    editor.deleteLater()
