"""Download verified Windows portable updates from the official DCRC releases."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import http.client
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import time
import urllib.error
from urllib.parse import urlsplit
import urllib.request
from uuid import uuid4
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile
from zlib import error as DeflateError

from .errors import Cancelled, ConverterError
from .storage import file_digest


RELEASES_URL = 'https://github.com/SandstoneDev/DCRC/releases'
LATEST_URL = 'https://api.github.com/repos/SandstoneDev/DCRC/releases/latest'
_CDN_HOSTS = {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
_MANIFEST = 'BUNDLE_MANIFEST.json'
_RECEIPT = '.dcrc-release.json'
_BUNDLE_FORMAT = 'DCRC_PORTABLE_WINDOWS_X64_V1'
_RECEIPT_FORMAT = 'DCRC_RELEASE_INSTALL_V1'
_ARCHIVE_ROOT = 'DCRC Converter/'
_REQUIRED_FILES = {
    'DCRC Converter.exe', 'app/gui/run_gui.py', 'app/dcrc/__init__.py',
    'python/python.exe', 'python/pythonw.exe', 'toolchain/bin/psp-gcc.exe',
}
_VERSION = re.compile(r'(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){2}')
_HASH = re.compile(r'[0-9a-f]{64}')
_REVISION_LABEL = re.compile(r'DCRC release revision ([1-9][0-9]{0,8})')
_WINDOWS_DEVICE = re.compile(r'(?:CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³]|CONIN\$|CONOUT\$)', re.I)
_MAX_METADATA = 2 << 20
_MAX_MANIFEST = 4 << 20
_MAX_ARCHIVE = 768 << 20
_MAX_UNPACKED = 2 << 30
_MAX_FILE = 384 << 20
_MAX_MEMBERS = 12000
_CHUNK = 1 << 20
_REPARSE = 0x400


class UpdateError(ConverterError):
    def __init__(self, message):
        super().__init__('update', message)


@dataclass(frozen=True)
class ReleaseUpdate:
    version: str
    archive_name: str
    size: int
    sha256: str
    notes_url: str
    revision: int | None = None


def _cancel(cancelled):
    if cancelled is not None and cancelled():
        raise Cancelled('Update cancelled.')


def _version(value):
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise UpdateError('Expected a stable converter version.')
    return tuple(map(int, value.split('.')))


def _revision(value):
    if value is not None and (type(value) is not int or not 1 <= value <= 999999999):
        raise UpdateError('Invalid converter release revision.')
    return value


def _archive_name(version):
    return f'DCRC-Converter-Windows-x64-v{version}.zip'


def _asset_url(version, name):
    return f'{RELEASES_URL}/download/v{version}/{name}'


def _safe_download_url(url, initial, allow_cdn):
    if url == initial:
        return
    try:
        parts = urlsplit(url)
        if (allow_cdn and len(url) <= 8192
                and not any(ch.isspace() or ord(ch) < 32 or ch == '\\' for ch in url)
                and parts.scheme == 'https' and parts.netloc in _CDN_HOSTS
                and parts.path.startswith('/') and not parts.fragment):
            return
    except ValueError:
        pass
    raise UpdateError('The update server redirected outside the allowed GitHub endpoints.')


class _ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 3

    def __init__(self, initial, allow_cdn):
        self.initial = initial
        self.allow_cdn = allow_cdn

    def redirect_request(self, request, response, code, message, headers, new_url):
        _safe_download_url(new_url, self.initial, self.allow_cdn)
        return super().redirect_request(request, response, code, message, headers, new_url)


class _NoPublishedRelease(Exception):
    pass


def _chunks(url, limit, *, expected=None, cancelled=None):
    is_asset = url != LATEST_URL
    headers = {'User-Agent': 'DCRC-Converter', 'Accept-Encoding': 'identity'}
    if not is_asset:
        headers['Accept'] = 'application/vnd.github+json'
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_ReleaseRedirect(url, is_asset))
    deadline = time.monotonic() + (900 if limit == _MAX_ARCHIVE else 30)
    try:
        _cancel(cancelled)
        with opener.open(request, timeout=8) as response:
            _safe_download_url(response.geturl(), url, is_asset)
            if response.status != 200 or response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise UpdateError('GitHub did not return a complete update response.')
            declared = response.headers.get('Content-Length')
            if declared is not None:
                if not re.fullmatch(r'[0-9]{1,10}', declared) or int(declared) > limit:
                    raise UpdateError('GitHub returned an invalid update size.')
                declared = int(declared)
                if expected is not None and declared != expected:
                    raise UpdateError('The download size differs from the published asset.')
            size = 0
            while True:
                _cancel(cancelled)
                part = response.read1(min(_CHUNK, limit + 1 - size))
                if time.monotonic() > deadline:
                    raise UpdateError('The update download timed out.')
                if not part:
                    break
                size += len(part)
                if size > limit or (expected is not None and size > expected):
                    raise UpdateError('The download exceeds the published size.')
                yield part
            if (expected is not None and size != expected) or (declared is not None and size != declared):
                raise UpdateError('The download ended before the published size.')
    except urllib.error.HTTPError as error:
        error.close()
        if not is_asset and error.code == 404:
            raise _NoPublishedRelease from None
        raise UpdateError(f'GitHub returned HTTP {error.code} while checking or downloading the update.') from None
    except (OSError, http.client.HTTPException):
        raise UpdateError('The secure connection to GitHub failed.') from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate metadata key.')
        result[key] = value
    return result


def _decode_metadata(data):
    try:
        value = json.loads(data, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        raise UpdateError('The update metadata is invalid.') from None
    if not isinstance(value, dict):
        raise UpdateError('The update metadata is invalid.')
    return value


def _plain_directory(path):
    path = Path(path).absolute()
    try:
        for directory in (*reversed(path.parents), path):
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE:
                raise UpdateError('Choose a portable folder without linked directories.')
    except OSError:
        raise UpdateError('The portable folder is unavailable.') from None
    return path.resolve()


def _local_metadata(root, name, limit):
    path = root / name
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE
                or not 0 < info.st_size <= limit):
            raise UpdateError('The local converter metadata is invalid.')
        with path.open('rb') as stream:
            data = stream.read(limit + 1)
    except FileNotFoundError:
        return {}
    except OSError:
        raise UpdateError('The local converter metadata could not be read.') from None
    if len(data) != info.st_size:
        raise UpdateError('The local converter metadata changed while it was read.')
    return _decode_metadata(data)


def portable_root():
    """Find the installed portable bundle when imported from its app folder."""
    package = Path(__file__).absolute().parent
    if package.parent.name != 'app':
        return None
    root = package.parent.parent
    if (root / _MANIFEST).is_file() and (root / 'DCRC Converter.exe').is_file():
        return root
    return None


def _asset(release, version, name, limit):
    assets = release.get('assets')
    if not isinstance(assets, list):
        raise UpdateError('GitHub did not return release assets.')
    matches = [asset for asset in assets if isinstance(asset, dict) and asset.get('name') == name]
    if len(matches) != 1:
        raise UpdateError('The release must include one Windows ZIP and its SHA256 file.')
    asset = matches[0]
    if (asset.get('state') != 'uploaded' or asset.get('browser_download_url') != _asset_url(version, name)
            or type(asset.get('size')) is not int or not 0 < asset['size'] <= limit):
        raise UpdateError('The published release asset is invalid.')
    return asset


def check_for_update(current_version, install_root, *, cancelled=None):
    """Return a verified asset descriptor if a newer stable package is available."""
    current = _version(current_version)
    root = _plain_directory(install_root)
    installed = _local_metadata(root, _MANIFEST, _MAX_MANIFEST)
    if installed.get('format') != _BUNDLE_FORMAT:
        raise UpdateError('Updates require a packaged Windows portable converter.')
    installed_revision = _revision(installed.get('release_revision'))
    receipt = _local_metadata(root, _RECEIPT, 4096)
    installed_hash = receipt.get('archive_sha256')
    if (receipt.get('format') != _RECEIPT_FORMAT or receipt.get('version') != current_version
            or not isinstance(installed_hash, str) or not _HASH.fullmatch(installed_hash)):
        installed_hash = None

    try:
        metadata = b''.join(_chunks(LATEST_URL, _MAX_METADATA, cancelled=cancelled))
    except _NoPublishedRelease:
        return None
    release = _decode_metadata(metadata)
    if release.get('draft') is not False or release.get('prerelease') is not False:
        raise UpdateError('GitHub did not return a published stable release.')
    tag = release.get('tag_name')
    if not isinstance(tag, str) or not tag.startswith('v'):
        raise UpdateError('GitHub did not return a stable version tag.')
    version = tag[1:]
    target = _version(version)
    if target < current:
        return None
    name = _archive_name(version)
    asset = _asset(release, version, name, _MAX_ARCHIVE)
    label = asset.get('label')
    match = _REVISION_LABEL.fullmatch(label) if isinstance(label, str) else None
    revision = int(match[1]) if match else None
    if target == current:
        if revision is not None and installed_revision is not None and revision < installed_revision:
            return None
        if installed_hash is None and (revision is None or installed_revision is None or revision <= installed_revision):
            return None

    checksum = _asset(release, version, name + '.sha256', 4096)
    checksum_data = b''.join(_chunks(checksum['browser_download_url'], 4096, expected=checksum['size'],
                                    cancelled=cancelled))
    match = re.fullmatch(rb'([0-9a-fA-F]{64})[ \t]+\*?' + re.escape(name.encode('ascii')) + rb'\r?\n?',
                         checksum_data)
    if match is None:
        raise UpdateError('The published SHA256 file does not name the Windows ZIP.')
    expected_hash = match[1].decode('ascii').lower()
    api_hash = asset.get('digest')
    if api_hash is not None and api_hash != f'sha256:{expected_hash}':
        raise UpdateError('GitHub asset digest and published SHA256 do not agree.')
    if target == current and expected_hash == installed_hash:
        return None
    return ReleaseUpdate(version, name, asset['size'], expected_hash, f'{RELEASES_URL}/tag/{tag}', revision)


def _member_path(value):
    path = PurePosixPath(value)
    if (not path.parts or len(value) > 500 or path.is_absolute() or path.as_posix() != value
            or len(path.parts) > 40):
        raise UpdateError('The update archive contains an unsafe path.')
    for part in path.parts:
        if (part == '..' or len(part) > 200 or part.endswith(('.', ' '))
                or any(ch in '<>:"/\\|?*' or ord(ch) < 32 for ch in part)
                or _WINDOWS_DEVICE.fullmatch(part.partition('.')[0].rstrip(' '))):
            raise UpdateError('The update archive contains an unsafe Windows path.')
    return path


def _archive_files(bundle):
    entries = bundle.infolist()
    if not 0 < len(entries) <= _MAX_MEMBERS:
        raise UpdateError('The update archive has too many entries.')
    files = {}
    spelling = {}
    seen = set()
    total = 0
    for entry in entries:
        name = entry.orig_filename
        if not name.startswith(_ARCHIVE_ROOT):
            raise UpdateError('The update archive has an unexpected root folder.')
        kind = stat.S_IFMT(entry.external_attr >> 16)
        directory = entry.is_dir()
        if (entry.flag_bits & 1 or entry.external_attr & _REPARSE
                or kind not in (0, stat.S_IFDIR if directory else stat.S_IFREG)
                or (directory and entry.file_size != 0)):
            raise UpdateError('The update archive contains a link or unsupported entry.')
        if name in seen:
            raise UpdateError('The update archive contains duplicate entries.')
        seen.add(name)
        if name == _ARCHIVE_ROOT and directory:
            continue
        relative = name.removeprefix(_ARCHIVE_ROOT)
        path = _member_path(relative.removesuffix('/') if directory else relative)
        for parent in (*reversed(path.parents), path):
            if parent == PurePosixPath('.'):
                continue
            canonical = parent.as_posix()
            key = canonical.casefold()
            record = (canonical, parent == path and not directory)
            if spelling.setdefault(key, record) != record:
                raise UpdateError('The update archive contains conflicting Windows paths.')
        if directory:
            continue
        if entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED) or not 0 <= entry.file_size <= _MAX_FILE:
            raise UpdateError('The update archive contains an unsupported file.')
        total += entry.file_size
        if total > _MAX_UNPACKED:
            raise UpdateError('The unpacked update exceeds its size limit.')
        files[path.as_posix()] = entry
    return files


def _extract(archive, output, update, cancelled):
    try:
        with ZipFile(archive) as bundle:
            files = _archive_files(bundle)
            manifest_entry = files.get(_MANIFEST)
            if manifest_entry is None or not 0 < manifest_entry.file_size <= _MAX_MANIFEST:
                raise UpdateError('The update archive has no valid bundle manifest.')
            manifest_raw = bundle.read(manifest_entry)
            manifest = _decode_metadata(manifest_raw)
            records = manifest.get('files')
            if (manifest.get('format') != _BUNDLE_FORMAT or manifest.get('game_data_included') is not False
                    or not isinstance(records, dict) or not _REQUIRED_FILES <= records.keys()
                    or any(name.casefold() in {_MANIFEST.casefold(), _RECEIPT.casefold()} for name in records)
                    or set(files) != records.keys() | {_MANIFEST}):
                raise UpdateError('The update bundle does not match its portable manifest.')
            revision = _revision(manifest.get('release_revision'))
            if update.revision is not None and revision != update.revision:
                raise UpdateError('The update bundle revision does not match the release asset.')
            output.mkdir()
            for name, record in records.items():
                _cancel(cancelled)
                entry = files[name]
                if (not isinstance(record, dict) or type(record.get('size')) is not int
                        or record['size'] != entry.file_size or not isinstance(record.get('sha256'), str)
                        or not _HASH.fullmatch(record['sha256'])):
                    raise UpdateError('The update bundle contains an invalid file receipt.')
                target = output.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                size = 0
                with bundle.open(entry) as source, target.open('xb') as destination:
                    while part := source.read(_CHUNK):
                        _cancel(cancelled)
                        size += len(part)
                        if size > record['size']:
                            raise UpdateError('A file exceeds its declared size.')
                        destination.write(part)
                if size != record['size'] or file_digest(target) != {'bytes': size, 'sha256': record['sha256']}:
                    raise UpdateError('A file failed the update manifest SHA256 check.')
            with (output / _MANIFEST).open('xb') as stream:
                stream.write(manifest_raw)
    except (BadZipFile, DeflateError, EOFError, RuntimeError) as error:
        if isinstance(error, ConverterError):
            raise
        raise UpdateError('The downloaded ZIP archive could not be verified.') from None


def install_update(update, install_root, *, progress=None, cancelled=None):
    """Install into a fresh sibling directory and return it without launching it."""
    _version(update.version)
    _revision(update.revision)
    if (update.archive_name != _archive_name(update.version) or type(update.size) is not int
            or not 0 < update.size <= _MAX_ARCHIVE or not isinstance(update.sha256, str)
            or not _HASH.fullmatch(update.sha256)):
        raise UpdateError('Invalid verified update descriptor.')
    root = _plain_directory(install_root)
    if _local_metadata(root, _MANIFEST, _MAX_MANIFEST).get('format') != _BUNDLE_FORMAT:
        raise UpdateError('Updates require a packaged Windows portable converter.')
    parent = root.parent
    if parent == root:
        raise UpdateError('Place the portable converter in a folder before updating it.')
    _cancel(cancelled)
    try:
        # The temporary tree contains only files created by this operation.
        with tempfile.TemporaryDirectory(prefix='.dcrc-update-', dir=parent, ignore_cleanup_errors=True) as staging:
            temporary = Path(staging)
            if temporary.resolve().parent != parent:
                raise UpdateError('Could not create a staging folder beside the current converter.')
            archive = temporary / update.archive_name
            if progress is not None:
                progress(0, update.size)
            digest = sha256()
            size = 0
            with archive.open('xb') as stream:
                for part in _chunks(_asset_url(update.version, update.archive_name), _MAX_ARCHIVE,
                                    expected=update.size, cancelled=cancelled):
                    stream.write(part)
                    digest.update(part)
                    size += len(part)
                    if progress is not None:
                        progress(size, update.size)
            if size != update.size or digest.hexdigest() != update.sha256:
                raise UpdateError('The Windows ZIP failed the published SHA256 check.')
            output = temporary / 'verified'
            _extract(archive, output, update, cancelled)
            receipt = {'format': _RECEIPT_FORMAT, 'version': update.version, 'archive_sha256': update.sha256}
            with (output / _RECEIPT).open('x', encoding='utf-8') as stream:
                json.dump(receipt, stream)
            _cancel(cancelled)
            destination = parent / f'DCRC Converter {update.version}-{uuid4().hex}'
            if destination.exists() or destination.is_symlink():
                raise UpdateError('The new converter folder already exists.')
            if output.resolve().parent != temporary or destination.resolve().parent != parent:
                raise UpdateError('The update staging location changed before installation.')
            return output.rename(destination)
    except OSError:
        raise UpdateError('Could not install the update beside the current converter.') from None
