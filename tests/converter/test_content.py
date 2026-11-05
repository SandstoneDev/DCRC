"""Synthetic VMU containers only; no downloaded or extracted game bytes."""
import binascii
import shutil
import struct
from pathlib import Path

import pytest

from dcrc.content import inspect_content, stage_content
from dcrc.errors import ConverterError
from dcrc.storage import file_digest


def pair(root, stem='sample', canonical='SONICADV_505', label='Synthetic event', crc=False):
    root.mkdir(parents=True, exist_ok=True)
    vmi = bytearray(108)
    desc = label.encode('ascii')[:32]
    vmi[4:4+len(desc)] = desc
    vmi[88:100] = canonical.encode('ascii')
    struct.pack_into('<I', vmi, 104, 1024)
    vms = bytearray(1024)
    struct.pack_into('<H', vms, 0x40, 1)
    struct.pack_into('<I', vms, 0x48, 1024-640)
    vms[640:656] = b'own test payload'
    if crc:
        struct.pack_into('<H', vms, 0x46, binascii.crc_hqx(vms, 0))
    a, b = root/(stem+'.VMI'), root/(stem+'.vMs')
    a.write_bytes(vmi); b.write_bytes(vms)
    return a, b


def test_stage_opaque_pairs_catalog_and_full_readback(tmp_path):
    source, destination = tmp_path/'source', tmp_path/'output'/'data'
    a, b = pair(source/'nested', crc=True)
    original = (a.read_bytes(), b.read_bytes())
    destination.mkdir(parents=True)
    (destination/'keep.txt').write_text('foreign data remains')
    result = stage_content(source, destination)
    assert result['count'] == 1 and result['skipped'] == []
    assert result['entries'][0]['canonical'] == 'SONICADV_505'
    assert (destination/'dlc/events/event00.vmi').read_bytes() == original[0]
    assert (destination/'dlc/events/event00.vms').read_bytes() == original[1]
    assert (a.read_bytes(), b.read_bytes()) == original
    assert (destination/'dlc/events.txt').read_text() == 'Synthetic event|dlc/events/event00.vmi|dlc/events/event00.vms\n'
    assert set(result['files']) == {'dlc/events.txt','dlc/events/event00.vmi','dlc/events/event00.vms'}
    for name, digest in result['files'].items():
        assert file_digest(destination/name) == digest
    assert (destination/'keep.txt').read_text() == 'foreign data remains'


def test_fingerprint_is_portable_and_changes_with_selected_bytes(tmp_path):
    a, b = pair(tmp_path/'one')
    shutil.copytree(tmp_path/'one', tmp_path/'two')
    first = inspect_content(tmp_path/'one')
    assert first == inspect_content(tmp_path/'two')
    data = bytearray(b.read_bytes()); data[-1] ^= 1; b.write_bytes(data)
    assert inspect_content(tmp_path/'one')['fingerprint'] != first['fingerprint']


@pytest.mark.parametrize('damage', ['vmi_size','vmi_length','name','lowercase','icon_count','eyecatch','payload_size','crc','unaligned','too_big','too_small'])
def test_invalid_outer_container_is_reported_not_staged(tmp_path, damage):
    source = tmp_path/'source'
    a, b = pair(source, crc=True)
    meta, data = bytearray(a.read_bytes()), bytearray(b.read_bytes())
    if damage == 'vmi_size': meta.pop()
    if damage == 'vmi_length': struct.pack_into('<I',meta,104,1025)
    if damage == 'name': meta[88] = ord('X')
    if damage == 'lowercase': meta[88] = ord('s')
    if damage == 'icon_count': struct.pack_into('<H',data,0x40,2)
    if damage == 'eyecatch': struct.pack_into('<H',data,0x44,1)
    if damage == 'payload_size': struct.pack_into('<I',data,0x48,1)
    if damage == 'crc': data[-1] ^= 1
    if damage == 'unaligned': data.append(0)
    if damage == 'too_big': data.extend(bytes(200*512))
    if damage == 'too_small': data = data[:512]
    a.write_bytes(meta); b.write_bytes(data)
    inspected = inspect_content(source)
    assert inspected['count'] == 0 and inspected['skipped'][0]['reason']
    destination = tmp_path/'output'
    with pytest.raises(ConverterError) as caught:
        stage_content(source,destination)
    assert caught.value.code == 'content_empty'
    assert not destination.exists()


def test_us_family_is_explicit_not_a_payload_region_claim(tmp_path):
    pair(tmp_path/'source', 'japanese', 'SONICADV_003')
    pair(tmp_path/'source', 'compatible', 'SONICADV_5AF')
    inspected = inspect_content(tmp_path/'source')
    assert inspected['count'] == 1
    assert inspected['entries'][0]['canonical'] == 'SONICADV_5AF'
    assert inspected['skipped'][0]['reason'] == 'unsupported_us_name_family'


def test_missing_pair_and_orphan_are_reported(tmp_path):
    source = tmp_path/'source'
    a, b = pair(source); b.unlink()
    (source/'orphan.VMS').write_bytes(b'not parsed without metadata')
    result = inspect_content(source)
    assert result['count'] == 0
    assert {x['reason'] for x in result['skipped']} == {'missing_vms','missing_vmi'}


def test_case_insensitive_stem_pairing_and_generated_paths(tmp_path):
    a, b = pair(tmp_path/'source', 'Odd Name (test)')
    b.rename(b.with_name('ODD NAME (TEST).VMS'))
    result = stage_content(tmp_path/'source',tmp_path/'destination')
    assert result['count'] == 1
    assert all('Odd' not in name and '..' not in name for name in result['files'])


def test_duplicates_preserve_different_variants_and_labels_are_safe(tmp_path):
    source = tmp_path/'source'
    pair(source, 'one', label='A|event')
    pair(source, 'two', label='A event')
    a, b = pair(source, 'three', label='Distinct variant')
    data = bytearray(b.read_bytes()); data[-1] = 2; b.write_bytes(data)
    shutil.copyfile(a,source/'copy.VMI'); shutil.copyfile(b,source/'copy.VMS')
    result = inspect_content(source)
    assert result['count'] == 3
    labels = [e['label'] for e in result['entries']]
    assert len({x.casefold() for x in labels}) == 3
    assert all('|' not in x and 0 < len(x) < 64 and x.isascii() for x in labels)
    assert any(x['reason'] == 'duplicate_pair' for x in result['skipped'])


def test_maximum_32_valid_pairs_and_stable_order(tmp_path):
    source = tmp_path/'source'
    for i in range(34): pair(source,f'{i:02}',label=f'Event {i}')
    result = inspect_content(source)
    assert result['count'] == 32 and len(result['skipped']) == 2
    assert all(x['reason'] == 'catalog_limit' for x in result['skipped'])
    assert result == inspect_content(source)


def test_existing_dlc_never_overwritten(tmp_path):
    source, destination = tmp_path/'source', tmp_path/'destination'
    pair(source)
    (destination/'dlc').mkdir(parents=True)
    keep = destination/'dlc'/'events.txt'; keep.write_text('mine')
    with pytest.raises(ConverterError): stage_content(source,destination)
    assert keep.read_text() == 'mine'
    assert list((destination/'dlc').iterdir()) == [keep]


@pytest.mark.parametrize('destination', ['source','source/output'])
def test_output_cannot_modify_input_tree(tmp_path,destination):
    source = tmp_path/'source'; pair(source)
    before = {p.name:p.read_bytes() for p in source.iterdir()}
    with pytest.raises(ConverterError): stage_content(source,tmp_path/destination)
    assert {p.name:p.read_bytes() for p in source.iterdir()} == before


def test_directory_links_rejected_before_output(tmp_path):
    source = tmp_path/'source'; pair(source)
    try: (source/'link').symlink_to(source,target_is_directory=True)
    except OSError: pytest.skip('Directory symlink privilege unavailable')
    with pytest.raises(ConverterError): stage_content(source,tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_missing_source_is_an_explicit_error(tmp_path):
    with pytest.raises(ConverterError): inspect_content(tmp_path/'missing')


@pytest.mark.parametrize('label',['#not a catalog comment','off','NONE','123','A|B'])
def test_labels_cannot_be_runtime_comments_or_selection_keywords(tmp_path,label):
    pair(tmp_path/'source',label=label)
    result = stage_content(tmp_path/'source',tmp_path/'output')
    entry = result['entries'][0]
    assert not entry['label'].startswith('#')
    assert entry['label'].casefold() not in ('off','none')
    assert not entry['label'].isdecimal()
    assert len((tmp_path/'output/dlc/events.txt').read_text().split('|')) == 3


def test_changed_source_before_stage_cannot_use_old_fingerprint(tmp_path,monkeypatch):
    from dcrc import content
    source = tmp_path/'source'; a, b = pair(source)
    original = content.inspect_content
    def changed(path):
        result = original(path)
        raw = bytearray(b.read_bytes()); raw[-1] ^= 1; b.write_bytes(raw)
        return result
    monkeypatch.setattr(content,'inspect_content',changed)
    with pytest.raises(ConverterError) as caught:
        stage_content(source,tmp_path/'output')
    assert caught.value.code == 'content_changed'
    assert not (tmp_path/'output').exists()


def test_readback_mismatch_never_returns_success(tmp_path,monkeypatch):
    from dcrc import content
    pair(tmp_path/'source')
    monkeypatch.setattr(content,'file_digest',lambda p:{'bytes':1,'sha256':'0'*64})
    with pytest.raises(ConverterError) as caught:
        stage_content(tmp_path/'source',tmp_path/'output')
    assert caught.value.code == 'content_readback'
