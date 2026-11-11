from hashlib import sha256
from io import BytesIO
import json
import stat
from urllib.error import HTTPError
from zipfile import ZipFile, ZipInfo

import pytest

from dcrc import updater
from dcrc.errors import Cancelled


def installed(tmp_path, revision=None):
    root = tmp_path / 'current'
    root.mkdir()
    manifest = {'format': 'DCRC_PORTABLE_WINDOWS_X64_V1'}
    if revision is not None:
        manifest['release_revision'] = revision
    (root / 'BUNDLE_MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
    (root / 'personal.txt').write_text('preserve me', encoding='utf-8')
    return root


def official_release(monkeypatch, version='0.1.0', revision=None, digest='a' * 64):
    name = f'DCRC-Converter-Windows-x64-v{version}.zip'
    download = f'{updater.RELEASES_URL}/download/v{version}/{name}'
    checksum = f'{digest}  {name}\n'.encode('ascii')
    assets = [
        {'name': name, 'size': 100, 'state': 'uploaded', 'browser_download_url': download,
         'digest': f'sha256:{digest}', 'label': f'DCRC release revision {revision}' if revision else None},
        {'name': name + '.sha256', 'size': len(checksum), 'state': 'uploaded',
         'browser_download_url': download + '.sha256'},
    ]
    release = {'tag_name': 'v' + version, 'draft': False, 'prerelease': False, 'assets': assets}
    calls = []

    def chunks(url, limit, **options):
        calls.append(url)
        if url == updater.LATEST_URL:
            yield json.dumps(release).encode('ascii')
        elif url == download + '.sha256':
            yield checksum
        else:
            pytest.fail('Checking for updates tried to download the ZIP.')

    monkeypatch.setattr(updater, '_chunks', chunks)
    return release, calls


def test_same_tag_requires_verified_digest_or_newer_revision(tmp_path, monkeypatch):
    root = installed(tmp_path, revision=2)
    release, calls = official_release(monkeypatch, revision=2)
    assert updater.check_for_update('0.1.0', root) is None
    assert calls == [updater.LATEST_URL]
    release['assets'][0]['label'] = 'DCRC release revision 3'
    assert updater.check_for_update('0.1.0', root).revision == 3
    (root / '.dcrc-release.json').write_text(json.dumps({
        'format': 'DCRC_RELEASE_INSTALL_V1', 'version': '0.1.0', 'archive_sha256': 'a' * 64,
    }), encoding='utf-8')
    assert updater.check_for_update('0.1.0', root) is None
    release, _ = official_release(monkeypatch, revision=2, digest='b' * 64)
    assert updater.check_for_update('0.1.0', root).sha256 == 'b' * 64
    release['assets'][0]['label'] = 'DCRC release revision 1'
    assert updater.check_for_update('0.1.0', root) is None


def test_stable_release_and_matching_checksum(tmp_path, monkeypatch):
    root = installed(tmp_path)
    release, _ = official_release(monkeypatch, version='0.1.1')
    assert updater.check_for_update('0.1.1', root) is None
    assert updater.check_for_update('0.1.2', root) is None
    assert updater.check_for_update('0.1.0', root).version == '0.1.1'
    release['assets'][0]['digest'] = 'sha256:' + 'c' * 64
    with pytest.raises(updater.UpdateError, match='do not agree'):
        updater.check_for_update('0.1.0', root)
    release['prerelease'] = True
    with pytest.raises(updater.UpdateError, match='stable release'):
        updater.check_for_update('0.1.0', root)


def test_repository_with_no_published_releases(tmp_path, monkeypatch):
    root = installed(tmp_path)

    class EmptyReleases:
        def open(self, request, timeout):
            assert request.full_url == updater.LATEST_URL
            raise HTTPError(request.full_url, 404, 'Not Found', {}, BytesIO())

    monkeypatch.setattr(updater.urllib.request, 'build_opener', lambda *_: EmptyReleases())
    assert updater.check_for_update('0.1.0', root) is None


def archive_bytes(*, extra=None, file_hash_mismatch=False, revision=3):
    files = {name: f'fixture: {name}'.encode('ascii') for name in updater._REQUIRED_FILES}
    records = {name: {'size': len(payload), 'sha256': sha256(payload).hexdigest()}
               for name, payload in files.items()}
    if file_hash_mismatch:
        records['DCRC Converter.exe']['sha256'] = '0' * 64
    manifest = {'format': 'DCRC_PORTABLE_WINDOWS_X64_V1', 'game_data_included': False,
                'release_revision': revision, 'files': records}
    output = BytesIO()
    with ZipFile(output, 'w') as bundle:
        for name, payload in files.items():
            bundle.writestr('DCRC Converter/' + name, payload)
        bundle.writestr('DCRC Converter/BUNDLE_MANIFEST.json', json.dumps(manifest))
        if extra is not None:
            bundle.writestr(extra, b'extra')
    return output.getvalue(), files


def descriptor(payload, digest=None):
    return updater.ReleaseUpdate('0.1.0', 'DCRC-Converter-Windows-x64-v0.1.0.zip', len(payload),
                                 digest or sha256(payload).hexdigest(), updater.RELEASES_URL, 3)


def test_update_keeps_current_bundle_and_writes_verified_receipt(tmp_path, monkeypatch):
    root = installed(tmp_path)
    payload, files = archive_bytes()
    update = descriptor(payload)
    monkeypatch.setattr(updater, '_chunks', lambda *args, **kwargs: iter((payload,)))
    progress = []
    destination = updater.install_update(update, root, progress=lambda n, total: progress.append((n, total)))
    assert destination.parent == root.parent and destination != root
    assert (root / 'personal.txt').read_text(encoding='utf-8') == 'preserve me'
    assert progress == [(0, len(payload)), (len(payload), len(payload))]
    assert {name: (destination / name).read_bytes() for name in files} == files
    receipt = json.loads((destination / '.dcrc-release.json').read_text(encoding='utf-8'))
    assert receipt['archive_sha256'] == update.sha256
    assert not list(tmp_path.glob('.dcrc-update-*'))


@pytest.mark.parametrize('entry', (
    'DCRC Converter/../outside.txt', 'DCRC Converter/app/gui/RUN_GUI.PY',
    'DCRC Converter/App/gui/other.py', 'DCRC Converter/COM1.txt',
    'DCRC Converter/trailing-dot.', 'DCRC Converter/stream:extra',
))
def test_reject_unsafe_entries_before_install(tmp_path, monkeypatch, entry):
    root = installed(tmp_path)
    payload, _ = archive_bytes(extra=entry)
    monkeypatch.setattr(updater, '_chunks', lambda *args, **kwargs: iter((payload,)))
    with pytest.raises(updater.UpdateError):
        updater.install_update(descriptor(payload), root)
    assert set(tmp_path.iterdir()) == {root}


def test_reject_links_bad_hash_and_cancellation(tmp_path, monkeypatch):
    root = installed(tmp_path)
    link = ZipInfo('DCRC Converter/linked')
    link.create_system = 3
    link.external_attr = stat.S_IFLNK << 16
    payload, _ = archive_bytes(extra=link)
    monkeypatch.setattr(updater, '_chunks', lambda *args, **kwargs: iter((payload,)))
    with pytest.raises(updater.UpdateError, match='contains a link'):
        updater.install_update(descriptor(payload), root)

    payload, _ = archive_bytes(file_hash_mismatch=True)
    with pytest.raises(updater.UpdateError, match='published SHA256'):
        updater.install_update(descriptor(payload, '0' * 64), root)
    with pytest.raises(updater.UpdateError, match='manifest SHA256'):
        updater.install_update(descriptor(payload), root)
    with pytest.raises(Cancelled):
        updater.install_update(descriptor(payload), root, cancelled=lambda: True)
    assert set(tmp_path.iterdir()) == {root}
