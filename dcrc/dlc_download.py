"""Explicit, bounded local download of opaque optional VMU events.

No payloads are bundled and normal conversion/import stays offline. The site
catalog describes source claims, not proven guest compatibility or permission
to redistribute the files. HTTPS hashes record observed bytes, not signatures.
Cancellation and the body budget are checked between single transport reads.
Connect/header parsing has a socket timeout, not a hard total wall deadline:
a peer that trickles headers can delay reaching the cooperative body checks.
"""
from pathlib import Path
from html.parser import HTMLParser
import base64
import socket
import ssl
import errno
import hashlib
import copy
import json
import os
import re
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .content import MAX_EVENTS, MAX_IMAGE, _outer, inspect_content
from .errors import Cancelled, ConverterError
from .storage import file_digest, fingerprint, plain_path, reject_links

SOURCE_URL = 'https://dreamcastlive.net/sonic-adventure-dlc/'
ASSET_HOSTS = frozenset(('dc.dreamcast-talk.com', 'dc.dreamcastlive.net'))
MAX_PAGE = 512 * 1024
MAX_RECEIPT = 256 * 1024
TIMEOUT = 5
RESOURCE_SECONDS = 30
RECEIPT = 'dlc_download.json'
FETCH_ATTEMPTS = 3
RETRY_DELAYS = (0.25, 0.75)
ENTRY_KEYS = {'id', 'label', 'kind', 'region', 'supported', 'reason', 'vmi_url', 'vms_url'}


def _error(code, message):
    return ConverterError('dlc_' + code, message)


def _cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled('DLC download cancelled. No partial download is ready for import.')


def _event(event, **values):
    if event:
        event(dict(type='stage', stage='dlc_download', **values))


def _url(value, role, *, catalog_link=False):
    """Validate before contact. Legacy catalog hrefs alone may be upgraded."""
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() or ord(c) < 32 for c in value):
        raise _error('url', 'DLC URL is not an allowed HTTPS endpoint.')
    try:
        p = urllib.parse.urlsplit(value)
        if (p.username is not None or p.password is not None or p.query or p.fragment
                or p.port not in (None, 443) or '%' in value or '\\' in value):
            raise ValueError()
        scheme = p.scheme
        if catalog_link and scheme == 'http':
            scheme = 'https'  # Never request the legacy HTTP link.
        if scheme != 'https':
            raise ValueError()
        canonical = urllib.parse.urlunsplit(('https', p.hostname or '', p.path, '', ''))
        if role == 'page':
            if canonical != SOURCE_URL:
                raise ValueError()
        elif (p.hostname not in ASSET_HOSTS or role not in ('vmi', 'vms')
              or not re.fullmatch(r'/dlc/sa1/[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.' + role,
                                  p.path, re.IGNORECASE)):
            raise ValueError()
        return canonical
    except (ValueError, TypeError):
        raise _error('url', 'DLC URL is not an allowed HTTPS endpoint.') from None


class _Redirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, role):
        self.role = role

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = _url(newurl, self.role)  # Validate BEFORE urllib opens it.
        count = getattr(req, '_dlc_redirects', 0) + 1
        if count > 3:
            raise _error('redirect', 'DLC endpoint exceeded the three-redirect limit.')
        next_request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if next_request is None:
            raise _error('redirect', 'DLC endpoint returned an unsupported redirect.')
        next_request._dlc_redirects = count
        return next_request


def _fetch_once(url, limit, role, cancel):
    _cancel(cancel)
    url = _url(url, role)
    request = urllib.request.Request(url, headers={
        'User-Agent': 'DCRC-local-content/1', 'Accept-Encoding': 'identity'})
    opener = urllib.request.build_opener(_Redirect(role))  # No cookie/auth handlers.
    started = time.monotonic()
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            _cancel(cancel)
            final = _url(response.geturl(), role)
            if response.status != 200:
                raise _error('http', f'DLC endpoint returned HTTP {int(response.status)}; complete file required.')
            encoding = response.headers.get('Content-Encoding', 'identity').strip().lower()
            if encoding != 'identity':
                raise _error('encoding', 'Compressed DLC responses are not accepted.')
            declared = response.headers.get('Content-Length')
            if declared is not None:
                if not re.fullmatch(r'[0-9]{1,10}', declared) or int(declared) > limit:
                    raise _error('size', 'DLC response exceeds its byte limit or has an invalid length.')
                declared = int(declared)
            data = bytearray()
            while True:
                _cancel(cancel)
                if time.monotonic() - started > RESOURCE_SECONDS:
                    raise _error('timeout', 'DLC response exceeded its read time budget.')
                # HTTPResponse.read(n) may accumulate n bytes through many recv
                # calls. read1 performs at most one underlying read, allowing
                # cancellation/budget checks even when a peer trickles bytes.
                part = response.read1(min(16384, limit + 1 - len(data)))
                _cancel(cancel)
                if time.monotonic() - started > RESOURCE_SECONDS:
                    raise _error('timeout', 'DLC response exceeded its read time budget.')
                if not part:
                    break
                data.extend(part)
                if len(data) > limit:
                    raise _error('size', 'DLC response exceeds its byte limit.')
            if declared is not None and len(data) != declared:
                raise _error('short', 'DLC response length does not match the declared length.')
            return bytes(data), final
    except (OSError, urllib.error.URLError, ValueError) as error:
        # Only allowlisted public categories/codes reach UI; never exception text.
        if isinstance(error, urllib.error.HTTPError):
            status = error.code
            error.close()
            code = 'transient' if status in (408, 429, 500, 502, 503, 504) else 'http'
            raise _error(code, f'DLC endpoint returned HTTP {status}.') from None
        reason = getattr(error, 'reason', error)
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise _error('tls', 'DLC server TLS certificate verification failed; secure connection refused.') from None
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise _error('transient', 'DLC server connection/read timed out.') from None
        if isinstance(reason, socket.gaierror):
            raise _error('transient', 'DLC server DNS lookup failed.') from None
        if isinstance(reason, OSError) and reason.errno in (errno.ECONNRESET, errno.ECONNREFUSED, errno.ECONNABORTED):
            raise _error('transient', 'DLC server connection was interrupted/refused.') from None
        raise _error('network', 'DLC server could not be read (network/transport error).') from None


def _fetch(url, limit, role, cancel):
    # Existing redirect policy already authorizes these two hosts. A mirror is
    # separately observed bytes, never asserted identical to the failing source.
    try:
        return _fetch_retry(url,limit,role,cancel)
    except ConverterError as error:
        if error.code != "dlc_tls" or role not in ("vmi","vms"):
            raise
        parsed = urllib.parse.urlsplit(_url(url,role))
        alternate = next(host for host in sorted(ASSET_HOSTS) if host != parsed.hostname)
        mirror = _url(urllib.parse.urlunsplit(("https",alternate,parsed.path,"","")),role)
        return _fetch_retry(mirror,limit,role,cancel)


def _fetch_retry(url, limit, role, cancel):
    for attempt in range(FETCH_ATTEMPTS):
        try:
            return _fetch_once(url, limit, role, cancel)
        except ConverterError as error:
            if error.code != 'dlc_transient' or attempt + 1 == FETCH_ATTEMPTS:
                raise
            deadline = time.monotonic() + RETRY_DELAYS[attempt]
            while time.monotonic() < deadline:
                _cancel(cancel)
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))


def _cached_pair(cache, entry):
    path = plain_path(cache / (entry['id'] + '.json'))
    if not path.exists():
        return None
    try:
        if not path.is_file() or path.stat().st_size > MAX_RECEIPT:
            raise ValueError()
        saved = json.loads(path.read_text(encoding='utf-8'))
        if set(saved) != {'format','entry','item','vmi','vms'} or saved['format'] != 'DCRC_DLC_PAIR_V1' or saved['entry'] != entry:
            raise ValueError()
        pair = [base64.b64decode(saved[k], validate=True) for k in ('vmi','vms')]
        item = saved['item']
        if set(item) != ENTRY_KEYS | {'canonical','vmi','vms'} or any(item[k] != entry[k] for k in ENTRY_KEYS):
            raise ValueError()
        if len(pair[0]) != 108 or not 1024 <= len(pair[1]) <= MAX_IMAGE or item['canonical'] != _outer(*pair):
            raise ValueError()
        for kind, data in zip(('vmi','vms'),pair):
            info = item[kind]
            if set(info) != {'url','final_url','digest'} or info['url'] != entry[kind+'_url'] or info['digest'] != _digest(data):
                raise ValueError()
            _url(info['final_url'],kind)
        return item, pair
    except (ValueError, TypeError, KeyError, OSError, UnicodeError):
        raise _error('cache', 'Saved DLC pair is modified or invalid. Choose a new download folder; files are preserved.') from None


def _save_pair(cache, entry, item, meta, image):
    cache.parent.mkdir(parents=True, exist_ok=True)
    plain_path(cache.parent)
    cache.mkdir(exist_ok=True)
    plain_path(cache)
    value = dict(format='DCRC_DLC_PAIR_V1', entry=entry, item=item,
                 vmi=base64.b64encode(meta).decode('ascii'), vms=base64.b64encode(image).decode('ascii'))
    data = json.dumps(value, sort_keys=True).encode('utf-8')
    if len(data) > MAX_RECEIPT:
        raise _error('size', 'Saved DLC pair exceeds its byte limit.')
    try:
        _publish_new(cache/(entry['id']+'.json'),data)
    except FileExistsError:
        # Another downloader may publish the same verified pair first. Never
        # overwrite or adopt differing bytes/provenance, even if both are valid.
        existing = _cached_pair(cache,entry)
        if existing != (item,[meta,image]):
            raise _error('cache', 'Concurrent DLC cache publication differs. Existing files are preserved.') from None


def _classification(label, stem):
    kind = 'voice' if 'menu voice pack' in label.casefold() or stem.casefold().startswith('vp') else 'event'
    match = re.search(r'\((US|JP|PAL)\)', label, re.IGNORECASE)
    region = match.group(1).upper() if match else 'unknown'
    reason = ('voice_pack_unsupported' if kind == 'voice' else
              'region_not_supported' if region in ('JP', 'PAL') else
              'guest_compatibility_unknown' if region == 'unknown' else 'guest_validation_required')
    return kind, region, reason not in ('voice_pack_unsupported', 'region_not_supported'), reason


def _entry(label, links):
    label = ' '.join(label.split())
    if not label or len(label) > 128 or any(not c.isprintable() for c in label):
        raise _error('catalog', 'DLC catalog contains an invalid label.')
    by_type = {}
    for link in links:
        path = urllib.parse.urlsplit(link).path
        role = path.rsplit('.', 1)[-1].lower()
        if role not in ('vmi', 'vms') or role in by_type:
            raise _error('catalog', 'DLC catalog has duplicate or incomplete pairs.')
        by_type[role] = _url(link, role, catalog_link=True)
    if set(by_type) != {'vmi', 'vms'}:
        raise _error('catalog', 'DLC catalog has duplicate or incomplete pairs.')
    a, b = (urllib.parse.urlsplit(by_type[k]) for k in ('vmi', 'vms'))
    stem = a.path.rsplit('/', 1)[-1].rsplit('.', 1)[0]
    if a.hostname != b.hostname or a.path[:-4].casefold() != b.path[:-4].casefold():
        raise _error('catalog', 'DLC catalog pairs must have one host and matching file stems.')
    kind, region, supported, reason = _classification(label, stem)
    return dict(id=stem.lower(), label=label, kind=kind, region=region, supported=supported,
                reason=reason, vmi_url=by_type['vmi'], vms_url=by_type['vms'])


class _CatalogParser(HTMLParser):
    """Accept explicit paired anchors in a labeled paragraph, never scripts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.entries = []

    def handle_starttag(self, tag, attrs):
        if tag == 'p':
            if self.current is not None:
                self.handle_endtag('p')
            self.current = dict(label=[], links=[], title=True)
        elif self.current is not None:
            if tag == 'br':
                self.current['title'] = False
            if tag == 'a':
                hrefs = [v for k,v in attrs if k == 'href']
                if any(isinstance(v,str) and (re.search(r'\.(vmi|vms)(?:[?#]|$)',v,re.I)
                                             or '/dlc/sa1/' in v) for v in hrefs):
                    if len(hrefs) != 1:
                        raise _error('catalog', 'DLC catalog contains an ambiguous anchor.')
                    self.current['links'].append(hrefs[0])

    def handle_data(self, text):
        if self.current is not None and self.current['title']:
            self.current['label'].append(text)

    def handle_endtag(self, tag):
        if tag == 'p' and self.current is not None:
            if self.current['links']:
                self.entries.append(_entry(''.join(self.current['label']),self.current['links']))
                if len(self.entries) > MAX_EVENTS:
                    raise _error('catalog', 'DLC catalog exceeds the 32-entry limit.')
            self.current = None


def _validate_catalog(catalog, expected):
    try:
        if (not isinstance(catalog,dict) or set(catalog) != {'format','source_url','entries','fingerprint'}
                or catalog['format'] != 'DCRC_DLC_CATALOG_V1' or catalog['source_url'] != SOURCE_URL
                or not isinstance(catalog['entries'],list) or not 1 <= len(catalog['entries']) <= MAX_EVENTS):
            raise ValueError()
        seen = set()
        for entry in catalog['entries']:
            if not isinstance(entry,dict) or set(entry) != ENTRY_KEYS:
                raise ValueError()
            a = _entry(entry['label'],[entry['vmi_url'],entry['vms_url']])
            # Stored catalog URLs must already be HTTPS; no caller-supplied downgrades.
            _url(entry['vmi_url'],'vmi'); _url(entry['vms_url'],'vms')
            if a['supported'] and entry['supported'] is False and entry['reason'] in ('metadata_unavailable','unsupported_us_name_family','invalid_metadata'):
                a['supported'], a['reason'] = False, entry['reason']
            if a != entry or type(entry['supported']) is not bool or entry['id'] in seen:
                raise ValueError()
            seen.add(entry['id'])
        actual = fingerprint({k:v for k,v in catalog.items() if k != 'fingerprint'})
        if actual != catalog['fingerprint'] or actual != expected:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise _error('catalog', 'DLC catalog changed or is invalid. Refresh the catalog and select again.') from None


def discover_catalog(*, event=None, cancel=None, preflight=False):
    """Fetch only the fixed page. Returns source claims, never compatibility proof."""
    _event(event,state='running',message='Reading the optional DLC catalog.')
    data, _ = _fetch(SOURCE_URL,MAX_PAGE,'page',cancel)
    try:
        parser = _CatalogParser()
        parser.feed(data.decode('utf-8',errors='strict'))
        parser.close()
        parser.handle_endtag('p')
    except (UnicodeError, ValueError):
        raise _error('catalog', 'DLC catalog is not a supported UTF-8 page.') from None
    if preflight:
        eligible = [e for e in parser.entries if e['supported']]
        for index, entry in enumerate(eligible):
            _event(event,state='running',message=f'Checking optional event metadata: {entry["label"]}.',progress=index/len(eligible))
            try:
                meta, _ = _fetch(entry['vmi_url'],108,'vmi',cancel)
                if len(meta) != 108:
                    raise _error('container','VMI must contain exactly 108 bytes.')
                size = struct.unpack_from('<I',meta,104)[0]
                if not re.fullmatch(rb'SONICADV_5[0-9A-F]{2}',meta[88:100]):
                    entry['supported'], entry['reason'] = False, 'unsupported_us_name_family'
                elif not 1024 <= size <= MAX_IMAGE or size % 512:
                    entry['supported'], entry['reason'] = False, 'invalid_metadata'
            except Cancelled:
                raise
            except ConverterError as error:
                entry['supported'], entry['reason'] = False, 'metadata_unavailable'
                _event(event,state='unavailable',message=f'{entry["label"]}: {error.message}',id=entry['id'])
    catalog = dict(format='DCRC_DLC_CATALOG_V1',source_url=SOURCE_URL,entries=parser.entries)
    catalog['fingerprint'] = fingerprint(catalog)
    _validate_catalog(catalog,catalog['fingerprint'])
    _cancel(cancel)
    _event(event,state='done',message='DLC catalog loaded; guest compatibility remains unverified.')
    return catalog


def _digest(data):
    return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def _result(destination, receipt):
    return dict(source_dir=str(destination/'source'),catalog_fingerprint=receipt['catalog_fingerprint'],
                inspect_report=receipt['inspect_report'],downloaded=receipt['downloaded'],
                skipped=receipt['skipped'],receipt=RECEIPT)


def _reuse(destination, catalog, ids, cancel):
    """No foreign adoption or repairs. Exact owned ready output is reused offline."""
    try:
        if {p.name for p in destination.iterdir()} != {'source',RECEIPT}:
            raise ValueError()
        marker = plain_path(destination/RECEIPT)
        if not marker.is_file() or marker.stat().st_size > MAX_RECEIPT:
            raise ValueError()
        receipt = json.loads(marker.read_text(encoding='utf-8'))
        if (receipt['format'] != 'DCRC_DLC_DOWNLOAD_V1' or receipt['catalog'] != catalog
                or receipt['catalog_fingerprint'] != catalog['fingerprint'] or receipt['ids'] != ids):
            raise ValueError()
        if set(receipt) != {'format','catalog','catalog_fingerprint','ids','files','inspect_report','downloaded','skipped'}:
            raise ValueError()
        source = plain_path(destination/'source')
        expected_names = {i+'.'+kind for i in ids for kind in ('vmi','vms')}
        if not source.is_dir() or {p.name for p in source.iterdir()} != expected_names:
            raise ValueError()
        expected_keys = {'source/'+name for name in expected_names}
        if set(receipt['files']) != expected_keys:
            raise ValueError()
        for name in sorted(expected_names):
            _cancel(cancel)
            path = plain_path(source/name)
            size = path.stat().st_size
            bounded = size == 108 if name.endswith('.vmi') else 1024 <= size <= MAX_IMAGE and size % 512 == 0
            if not path.is_file() or not bounded or file_digest(path) != receipt['files']['source/'+name]:
                raise ValueError()
        report = inspect_content(source)
        if (not report['count'] or any(s['reason'] != 'duplicate_pair' for s in report['skipped'])
                or report != receipt['inspect_report']):
            raise ValueError()
        selected = {e['id']:e for e in catalog['entries'] if e['id'] in ids}
        if sorted(item['id'] for item in receipt['downloaded']) != ids:
            raise ValueError()
        for item in receipt['downloaded']:
            if set(item) != ENTRY_KEYS | {'canonical','vmi','vms'}:
                raise ValueError()
            entry = selected[item['id']]
            if any(item[key] != entry[key] for key in ENTRY_KEYS):
                raise ValueError()
            for kind in ('vmi','vms'):
                info = item[kind]
                if (set(info) != {'url','final_url','digest'} or info['url'] != entry[kind+'_url']
                        or info['digest'] != receipt['files']['source/'+item['id']+'.'+kind]):
                    raise ValueError()
                _url(info['final_url'],kind)
            meta = (source/(item['id']+'.vmi')).read_bytes()
            image = (source/(item['id']+'.vms')).read_bytes()
            if item['canonical'] != _outer(meta,image):
                raise ValueError()
        if receipt['skipped'] != [dict(id=e['id'],reason=e['reason'])for e in catalog['entries'] if not e['supported']]:
            raise ValueError()
        _cancel(cancel)
        return _result(destination,receipt)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        raise _error('ownership', 'DLC destination is foreign, incomplete or modified. Choose a new folder; existing files are preserved.') from None


def _publish_new(path, data):
    """Atomic no-replace publication within an exclusively claimed new folder.

    A temporary same-directory hard link is removed immediately; final output
    has a single link. Unlike replace/rename, link creation cannot overwrite an
    existing foreign entry on POSIX either. Unsupported filesystems fail closed.
    """
    reject_links(path)
    temporary = path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.partial')
    created = False
    try:
        with temporary.open('xb') as stream:
            created = True
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if file_digest(temporary) != _digest(data):
            raise _error('readback', 'DLC write failed SHA256/size verification.')
        os.link(temporary,path)  # Atomic and fails if destination already exists.
    finally:
        if created:
            temporary.unlink(missing_ok=True)
    if file_digest(path) != _digest(data):
        raise _error('readback', 'DLC write failed SHA256/size verification.')


def download_events(catalog, ids, destination, *, expected_fingerprint, event=None, cancel=None):
    """Download explicit event IDs into a new folder, or verify/reuse exact output.

    Verified pairs are saved in a sibling cache and checked again on retry.
    All bounded pairs are fetched/validated before claiming the output. A failed
    disk publication remains unclaimed (no ready receipt); nothing is deleted or
    adopted on retry. source_dir is absolute only in the returned local result;
    the persisted receipt contains portable names, public URLs and byte hashes.
    """
    _cancel(cancel)
    catalog = copy.deepcopy(catalog)  # The UI's later edits cannot change a running job.
    _validate_catalog(catalog,expected_fingerprint)
    if (not isinstance(ids,(list,tuple)) or not 1 <= len(ids) <= MAX_EVENTS
            or any(not isinstance(i,str) for i in ids) or len(set(ids)) != len(ids)):
        raise _error('selection', 'Choose one or more distinct event IDs from the current catalog.')
    ids = sorted(ids)
    lookup = {e['id']:e for e in catalog['entries']}
    if any(i not in lookup for i in ids):
        raise _error('selection', 'A selected DLC ID is absent from the catalog. Refresh and select again.')
    if any(not lookup[i]['supported'] for i in ids):
        raise _error('unsupported', 'Selected voice packs or explicitly JP/PAL events are unsupported by this US event importer.')
    destination = plain_path(destination)
    if destination.exists():
        if not destination.is_dir():
            raise _error('ownership', 'Choose a new DLC download folder.')
        return _reuse(destination,catalog,ids,cancel)
    cache = plain_path(destination.parent/('.dcrc-dlc-pairs-'+catalog['fingerprint']))
    downloaded, buffers = [], {}
    _event(event,state='running',message='Downloading selected optional events; none are enabled automatically.')
    for index, identifier in enumerate(ids):
        entry = lookup[identifier]
        cached = _cached_pair(cache, entry)
        if cached is not None:
            item, (meta, image) = cached
            downloaded.append(item)
            buffers[identifier+'.vmi'], buffers[identifier+'.vms'] = meta, image
            _event(event,state='validated',message=f'Reused verified event {index+1}/{len(ids)}: {entry["label"]}.',id=identifier,progress=(index+1)/len(ids))
            continue
        def fetch_resource(role, limit):
            _event(event,state='running',message=f'Downloading {entry["label"]} ({role.upper()}).',id=identifier,progress=index/len(ids))
            try:
                return _fetch(entry[role+'_url'],limit,role,cancel)
            except Cancelled:
                raise
            except ConverterError as error:
                raise _error(error.code.removeprefix('dlc_'), f'{entry["label"]} ({role.upper()}): {error.message} Verified earlier pairs are retained for retry.') from None
        meta, meta_url = fetch_resource('vmi',108)
        if len(meta) != 108:
            raise _error('container', f'{entry["label"]} (VMI): metadata must contain exactly 108 bytes.')
        name = meta[88:100]
        size = struct.unpack_from('<I',meta,104)[0]
        if not re.fullmatch(rb'SONICADV_5[0-9A-F]{2}',name) or not 1024 <= size <= MAX_IMAGE or size % 512:
            raise _error('unsupported', f'{entry["label"]} (VMI): metadata is not a supported bounded US-family event. Refresh the catalog to check availability; verified earlier pairs are retained.')
        image, image_url = fetch_resource('vms',size)
        try:
            if not 1024 <= len(image) <= MAX_IMAGE:
                raise ValueError()
            canonical = _outer(meta,image)
        except (ValueError,struct.error):
            raise _error('container', f'{entry["label"]}: VMI/VMS pair failed opaque container validation.') from None
        item = dict(entry,canonical=canonical)
        for kind,data,final in (('vmi',meta,meta_url),('vms',image,image_url)):
            buffers[identifier+'.'+kind] = data
            item[kind] = dict(url=entry[kind+'_url'],final_url=final,digest=_digest(data))
        try:
            _save_pair(cache,entry,item,meta,image)
        except OSError:
            raise _error('cache', 'Verified DLC pair could not be saved. Existing files are preserved; retry or choose a new folder.') from None
        downloaded.append(item)
        _event(event,state='validated',message=f'Validated optional event {index+1}/{len(ids)}.',id=identifier,progress=(index+1)/len(ids))
    _cancel(cancel)
    # Reject a concurrent creator as well; no existing path is adopted.
    try:
        destination.parent.mkdir(parents=True,exist_ok=True)
        plain_path(destination.parent)
        destination.mkdir()
        source = destination/'source'; source.mkdir()
        files = {}
        for name,data in sorted(buffers.items()):
            _cancel(cancel)
            _publish_new(source/name,data)
            files['source/'+name] = _digest(data)
        report = inspect_content(source)
        if not report['count'] or any(s['reason'] != 'duplicate_pair' for s in report['skipped']):
            raise _error('container', 'Downloaded files did not pass final event inspection.')
        receipt = dict(format='DCRC_DLC_DOWNLOAD_V1',catalog=catalog,catalog_fingerprint=catalog['fingerprint'],
                       ids=ids,files=files,inspect_report=report,downloaded=downloaded,
                       skipped=[dict(id=e['id'],reason=e['reason'])for e in catalog['entries'] if not e['supported']])
        data = (json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
        if len(data) > MAX_RECEIPT:
            raise _error('size', 'DLC receipt exceeds its byte limit.')
        _cancel(cancel)
        _publish_new(destination/RECEIPT,data)  # Ready marker is last; no partial success.
        _event(event,state='done',message='DLC download verified. Events remain off until selected in the game.')
        return _result(destination,receipt)
    except OSError:
        raise _error('output', 'DLC output could not be created. Partial output is unclaimed; choose a new folder. Existing files are preserved.') from None
