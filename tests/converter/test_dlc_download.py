"""Synthetic HTTP/VMU data only. No downloaded DLC belongs in fixtures."""
import copy
import http.client as httplib
import io
import json
import socket
import struct
import threading
from pathlib import Path

import pytest

from dcrc import dlc_download as dlc
from dcrc.errors import Cancelled, ConverterError


def paragraph(stem='Test', title='Synthetic event', host='dc.dreamcast-talk.com', scheme='http'):
    prefix = f'{scheme}://{host}/dlc/sa1/{stem}'
    return f'<p><strong>{title}</strong><br>Own description<br>Download: <a href="{prefix}.VMI">VMI</a> | <a href="{prefix}.VMS">VMS</a></p>'


def container(canonical='SONICADV_505'):
    meta, image = bytearray(108), bytearray(1024)
    meta[4:18] = b'Synthetic test'
    meta[88:100] = canonical.encode('ascii')
    struct.pack_into('<I', meta, 104, len(image))
    struct.pack_into('<H', image, 0x40, 1)
    struct.pack_into('<I', image, 0x48, len(image)-640)
    return bytes(meta), bytes(image)


class Response(io.BytesIO):
    def __init__(self, data, url, headers=None, status=200, on_read=None):
        super().__init__(data)
        self.url, self.headers, self.status = url, headers or {}, status
        self.on_read = on_read

    def geturl(self):
        return self.url

    def read(self, n=-1):
        result = super().read(n)
        if self.on_read:
            self.on_read()
        return result

    def read1(self,n=-1):
        return self.read(n)


@pytest.fixture
def http(monkeypatch):
    routes, calls = {}, []

    def build(*handlers):
        redirect = next(h for h in handlers if isinstance(h, dlc._Redirect))

        class Opener:
            def open(self, req, timeout):
                while True:
                    calls.append(req.full_url)
                    action = routes[req.full_url]
                    if isinstance(action, Exception):
                        raise action
                    if isinstance(action, str):
                        req = redirect.redirect_request(req, None, 302, 'redirect', {}, action)
                        continue
                    data, options = action if isinstance(action, tuple) else (action, {})
                    return Response(data, req.full_url, **options)
        return Opener()

    monkeypatch.setattr(dlc.urllib.request, 'build_opener', build)
    return routes, calls


def setup(http, html=None):
    routes, calls = http
    routes[dlc.SOURCE_URL] = (html or paragraph()).encode()
    catalog = dlc.discover_catalog()
    meta, image = container()
    for entry in catalog['entries']:
        routes[entry['vmi_url']] = meta
        routes[entry['vms_url']] = image
    return catalog


def download(catalog, target, ids=None, **kw):
    return dlc.download_events(catalog, ids or [catalog['entries'][0]['id']], target,
                               expected_fingerprint=catalog['fingerprint'], **kw)


def test_realistic_catalog_https_classification_and_portability(http):
    c = setup(http, paragraph('Alpha', 'Event (US)')+paragraph('JP', 'Event (JP)')+
              paragraph('PAL', 'Event (PAL)')+paragraph('VPAmy', 'Menu Voice Pack: Amy')+
              paragraph('Theme', 'Japanese Christmas Event'))
    assert len(c['entries']) == 5
    assert [e['region'] for e in c['entries']] == ['US','JP','PAL','unknown','unknown']
    assert [e['supported'] for e in c['entries']] == [True,False,False,False,True]
    assert all(e['vmi_url'].startswith('https://') for e in c['entries'])
    assert c['entries'][-1]['reason'] == 'guest_compatibility_unknown'
    assert http[1] == [dlc.SOURCE_URL]  # No legacy HTTP request.


@pytest.mark.parametrize('html', [paragraph()+paragraph(), paragraph().replace('.VMS','_other.VMS'),
    paragraph().replace('.VMS',''), '<p>No DLC pairs</p>', paragraph().replace('dc.dreamcast-talk.com','evil.test')])
def test_catalog_fail_closed_ambiguous_missing_or_foreign(http, html):
    http[0][dlc.SOURCE_URL] = html.encode()
    with pytest.raises(ConverterError):
        dlc.discover_catalog()


def test_download_full_readback_offline_reuse_and_private_path_only_in_return(http, tmp_path):
    c = setup(http)
    result = download(c, tmp_path/'download')
    assert Path(result['source_dir']).is_absolute()
    assert result['inspect_report']['count'] == 1
    assert len(result['downloaded']) == 1 and result['receipt'] == 'dlc_download.json'
    receipt = Path(result['source_dir']).parent/result['receipt']
    text = receipt.read_text()
    assert str(tmp_path) not in text and 'source_dir' not in text
    calls = list(http[1])
    mtimes = {p:p.stat().st_mtime_ns for p in receipt.parent.rglob('*') if p.is_file()}
    assert download(c, receipt.parent) == result
    assert http[1] == calls and all(p.stat().st_mtime_ns == n for p,n in mtimes.items())


@pytest.mark.parametrize('mode', ['foreign','modified','extra','receipt','other_selection'])
def test_existing_destination_requires_exact_owned_unchanged(http, tmp_path, mode):
    c = setup(http)
    target = tmp_path/'download'
    if mode == 'foreign':
        target.mkdir(); (target/'keep').write_text('mine')
    else:
        download(c, target)
        if mode == 'modified': next((target/'source').glob('*.vms')).write_bytes(b'changed')
        if mode == 'extra': (target/'extra').write_text('mine')
        if mode == 'receipt': (target/'dlc_download.json').write_text('{}')
        if mode == 'other_selection':
            c = copy.deepcopy(c); c['entries'][0]['label'] += ' changed'
            c['fingerprint'] = dlc.fingerprint({k:v for k,v in c.items() if k!='fingerprint'})
    before = {str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file()}
    calls = list(http[1])
    with pytest.raises(ConverterError): download(c, target)
    assert calls == http[1]
    assert before == {str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file()}


@pytest.mark.parametrize('url', ['http://dc.dreamcast-talk.com/dlc/sa1/Test.VMI',
    'https://evil.test/dlc/sa1/Test.VMI', 'https://dc.dreamcast-talk.com:444/dlc/sa1/Test.VMI',
    'https://x@dc.dreamcast-talk.com/dlc/sa1/Test.VMI',
    'https://dc.dreamcast-talk.com/dlc/sa1/%2e%2e/Test.VMI',
    'https://dc.dreamcast-talk.com/dlc/sa1/Test.VMI?secret=1'])
def test_redirect_validated_before_contact(http, tmp_path, url):
    c = setup(http); first = c['entries'][0]['vmi_url']; http[0][first] = url
    with pytest.raises(ConverterError): download(c, tmp_path/'out')
    assert url not in http[1] and not (tmp_path/'out').exists()


def test_allowed_redirect_and_loop_bound(http, tmp_path):
    c = setup(http); first = c['entries'][0]['vmi_url']
    other = 'https://dc.dreamcastlive.net/dlc/sa1/Test.VMI'
    http[0][first] = other; http[0][other] = container()[0]
    result = download(c, tmp_path/'one')
    assert result['downloaded'][0]['vmi']['final_url'] == other
    http[0][other] = first
    start = len(http[1])
    with pytest.raises(ConverterError): download(c, tmp_path/'different_parent'/'two')
    assert len(http[1])-start == 4 and not (tmp_path/'different_parent'/'two').exists()


@pytest.mark.parametrize('where,options', [
    ('page', {'data': b'x'*(524288+1)}), ('vmi', {'data': b'x'*109}),
    ('vms', {'data': b'x'*102401}), ('vms', {'data': b'x'*1023}),
    ('vmi', {'headers': {'Content-Length':'109'}}),
    ('vmi', {'headers': {'Content-Length':'107'}}),
    ('vmi', {'headers': {'Content-Encoding':'gzip'}}),
    ('vmi', {'headers': {'Content-Length':'invalid'}}), ('vmi', {'status':206})])
def test_http_size_compression_length_and_status_bounds(http, tmp_path, where, options):
    c = setup(http)
    key = dlc.SOURCE_URL if where == 'page' else c['entries'][0][where+'_url']
    value = dict(options); data = value.pop('data', container()[0 if where=='vmi' else 1])
    http[0][key] = (data,value)
    with pytest.raises(ConverterError):
        dlc.discover_catalog() if where == 'page' else download(c,tmp_path/'out')
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('when', ['before','read','before_publish'])
def test_cooperative_cancel_leaves_no_success_receipt(http, tmp_path, when):
    c = setup(http); cancel = threading.Event()
    if when == 'before': cancel.set()
    if when == 'read':
        http[0][c['entries'][0]['vms_url']] = (container()[1],{'on_read':cancel.set})
    def event(e):
        if when == 'before_publish' and e.get('state') == 'validated': cancel.set()
    with pytest.raises(Cancelled): download(c,tmp_path/'out',cancel=cancel,event=event)
    assert not (tmp_path/'out'/'dlc_download.json').exists()


def test_catalog_fingerprint_and_unsupported_ids_checked_before_io(http, tmp_path):
    c = setup(http, paragraph()+paragraph('VPAmy','Menu Voice Pack: Amy'))
    calls = list(http[1])
    with pytest.raises(ConverterError): download(c,tmp_path/'a',ids=['vpamy'])
    with pytest.raises(ConverterError): download(c,tmp_path/'b',ids=['missing'])
    changed = copy.deepcopy(c); changed['entries'][0]['vmi_url'] = 'https://evil.test/a.VMI'
    with pytest.raises(ConverterError): download(changed,tmp_path/'c')
    assert calls == http[1] and not list(tmp_path.iterdir())


@pytest.mark.parametrize('name', ['SONICADV_V14','SONICADV_005'])
def test_header_family_rejected_before_vms_download(http, tmp_path, name):
    c = setup(http); http[0][c['entries'][0]['vmi_url']] = container(name)[0]
    with pytest.raises(ConverterError): download(c,tmp_path/'out')
    assert c['entries'][0]['vms_url'] not in http[1] and not (tmp_path/'out').exists()


def test_symlink_destination_refused(http, tmp_path):
    c=setup(http); real=tmp_path/'real'; real.mkdir()
    try: (tmp_path/'link').symlink_to(real,target_is_directory=True)
    except OSError: pytest.skip('Host does not permit symlinks')
    calls=list(http[1])
    with pytest.raises(ConverterError): download(c,tmp_path/'link')
    assert calls==http[1] and not list(real.iterdir())


@pytest.mark.parametrize('damage',['crc','size','icon','declared'])
def test_container_faults_never_publish_ready(http,tmp_path,damage):
    c=setup(http); meta,image=map(bytearray,container())
    if damage=='crc': struct.pack_into('<H',image,0x46,123)
    if damage=='size': image.pop()
    if damage=='icon': struct.pack_into('<H',image,0x40,2)
    if damage=='declared': struct.pack_into('<I',meta,104,1536)
    http[0][c['entries'][0]['vmi_url']]=bytes(meta)
    http[0][c['entries'][0]['vms_url']]=bytes(image)
    with pytest.raises(ConverterError): download(c,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_ready_cache_metadata_is_verified(http,tmp_path):
    c=setup(http); download(c,tmp_path/'out')
    p=tmp_path/'out'/'dlc_download.json'; data=json.loads(p.read_text())
    data['downloaded'][0]['canonical']='SONICADV_599'; p.write_text(json.dumps(data))
    with pytest.raises(ConverterError): download(c,tmp_path/'out')


def test_job_snapshots_catalog_before_callback_or_ui_changes(http,tmp_path):
    c=setup(http); original=copy.deepcopy(c)
    def event(e):
        if e.get('state')=='running': c['entries'][0]['vms_url']='https://evil.test/file.VMS'
    result=download(c,tmp_path/'out',event=event)
    assert result['catalog_fingerprint']==original['fingerprint']
    assert result['downloaded'][0]['vms_url']==original['entries'][0]['vms_url']


def test_concurrent_creator_not_overwritten_and_no_ready(http,tmp_path,monkeypatch):
    c=setup(http); original=dlc.os.link
    def collide(source,target):
        if Path(target).suffix == '.vmi':
            Path(target).write_bytes(b'foreign concurrent bytes')
        return original(source,target)
    monkeypatch.setattr(dlc.os,'link',collide)
    with pytest.raises(ConverterError): download(c,tmp_path/'out')
    assert (tmp_path/'out/source/test.vmi').read_bytes()==b'foreign concurrent bytes'
    assert not (tmp_path/'out/dlc_download.json').exists()


def test_temp_collision_preserves_foreign_file(monkeypatch,tmp_path):
    class FixedUUID:
        hex='collision'
    monkeypatch.setattr(dlc.uuid,'uuid4',lambda:FixedUUID())
    target=tmp_path/'event.vmi'
    foreign=tmp_path/'.event.vmi.collision.partial'
    foreign.write_bytes(b'foreign preexisting bytes')
    with pytest.raises(FileExistsError):dlc._publish_new(target,b'new owned bytes')
    assert foreign.read_bytes()==b'foreign preexisting bytes'
    assert not target.exists()


@pytest.mark.parametrize('signal',['cancel','budget'])
def test_actual_httpresponse_checks_before_accumulating_whole_body(monkeypatch,signal):
    """No external network: actual stdlib buffering over a local socket pair."""
    left,right=socket.socketpair();left.settimeout(2);right.settimeout(2)
    cancel=threading.Event();reading=threading.Event();release=threading.Event();stop=threading.Event()
    clock=[0.0]
    monkeypatch.setattr(dlc.time,'monotonic',lambda:clock[0])
    sent=[]
    def server():
        try:
            right.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 108\r\n\r\n')
            if not reading.wait(2):return
            sent.extend(range(3))
            if signal=='cancel':cancel.set()
            else:clock[0]=dlc.RESOURCE_SECONDS+1
            right.sendall(b'xxx')
            # read(n) cannot return until this tail arrives; read1 can return
            # the first fragment and observe cancellation before the tail.
            release.wait(1)
            if not stop.is_set():right.sendall(b'x'*105);sent.extend(range(105))
        except OSError:
            pass  # Reader may close immediately on cancellation.
        finally:
            right.close()
    thread=threading.Thread(target=server);thread.start()
    response=httplib.HTTPResponse(left)
    read,read1=response.read,response.read1
    def enter_read(n):reading.set();return read(n)
    def enter_read1(n):reading.set();return read1(n)
    response.read,response.read1=enter_read,enter_read1
    class Opener:
        def open(self,req,timeout):
            assert timeout==dlc.TIMEOUT
            response.begin();response.url=req.full_url;return response
    monkeypatch.setattr(dlc.urllib.request,'build_opener',lambda *_:Opener())
    try:
        with pytest.raises(Cancelled if signal=='cancel' else ConverterError) as caught:
            dlc._fetch('https://dc.dreamcast-talk.com/dlc/sa1/Slow.VMI',108,'vmi',cancel)
        if signal=='budget':assert caught.value.code=='dlc_timeout'
        assert len(sent)==3  # Old read(n) waits for and consumes the 105-byte tail.
    finally:
        stop.set();release.set();response.close();left.close();thread.join(3)
    assert not thread.is_alive()


def test_cancel_during_disk_publication_partial_is_unclaimed_and_preserved(http,tmp_path,monkeypatch):
    c=setup(http); cancel=threading.Event(); original=dlc._publish_new
    def publish(path,data):
        original(path,data)
        if path.suffix == '.vmi': cancel.set()
    monkeypatch.setattr(dlc,'_publish_new',publish)
    with pytest.raises(Cancelled): download(c,tmp_path/'out',cancel=cancel)
    assert not (tmp_path/'out/dlc_download.json').exists()
    before={p:p.read_bytes()for p in (tmp_path/'out').rglob('*')if p.is_file()}
    calls=list(http[1])
    with pytest.raises(ConverterError): download(c,tmp_path/'out')
    assert calls==http[1] and all(p.read_bytes()==data for p,data in before.items())


def test_network_failure_has_no_server_body_or_local_path(http,tmp_path):
    c=setup(http);http[0][c['entries'][0]['vmi_url']]=OSError('secret local-path credentials')
    with pytest.raises(ConverterError)as caught:download(c,tmp_path/'out')
    assert 'secret'not in str(caught.value) and 'private'not in str(caught.value)
    assert not (tmp_path/'out').exists()


def test_catalog_count_and_empty_duplicate_selection_bounds(http,tmp_path):
    http[0][dlc.SOURCE_URL]=''.join(paragraph('Item'+str(i))for i in range(33)).encode()
    with pytest.raises(ConverterError):dlc.discover_catalog()
    c=setup(http)
    for ids in ([],['test','test'],['test']*33,'test'):
        with pytest.raises(ConverterError):
            dlc.download_events(c,ids,tmp_path/'out',expected_fingerprint=c['fingerprint'])
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('code,attempts', [(503,3),(429,3),(404,1)])
def test_http_retry_category_bounded_and_sanitized(http,tmp_path,monkeypatch,code,attempts):
    import urllib.error
    c=setup(http);url=c['entries'][0]['vmi_url']
    http[0][url]=urllib.error.HTTPError(url,code,'secret',{},None)
    monkeypatch.setattr(dlc,'RETRY_DELAYS',(0,0))
    start=http[1].count(url)
    with pytest.raises(ConverterError) as caught:download(c,tmp_path/'out')
    assert http[1].count(url)-start==attempts
    assert f'HTTP {code}' in str(caught.value) and 'Synthetic event (VMI)' in str(caught.value)
    assert 'secret' not in str(caught.value)


def test_tls_error_not_retried_or_bypassed(http,tmp_path):
    import ssl,urllib.error
    c=setup(http);url=c['entries'][0]['vmi_url']
    http[0][url]=urllib.error.URLError(ssl.SSLCertVerificationError('private credentials'))
    mirror=url.replace('dc.dreamcast-talk.com','dc.dreamcastlive.net');http[0][mirror]=http[0][url]
    with pytest.raises(ConverterError) as caught:download(c,tmp_path/'out')
    assert caught.value.code=='dlc_tls' and 'certificate' in str(caught.value)
    assert http[1].count(url)==1 and 'private' not in str(caught.value)


def test_resume_good_pairs_after_later_network_failure(http,tmp_path):
    c=setup(http,paragraph('Alpha')+paragraph('Beta'))
    beta=c['entries'][1];http[0][beta['vmi_url']]=OSError('unavailable')
    target=tmp_path/'out'
    with pytest.raises(ConverterError):download(c,target,ids=['alpha','beta'])
    assert not target.exists()
    alpha=c['entries'][0];before=http[1].count(alpha['vmi_url'])
    http[0][beta['vmi_url']]=container()[0]
    r=download(c,target,ids=['alpha','beta'])
    assert len(r['downloaded'])==2 and http[1].count(alpha['vmi_url'])==before


def test_modified_saved_pair_refused_before_network(http,tmp_path):
    c=setup(http,paragraph('Alpha')+paragraph('Beta'));http[0][c['entries'][1]['vmi_url']]=OSError()
    target=tmp_path/'out'
    with pytest.raises(ConverterError):download(c,target,ids=['alpha','beta'])
    cache=next(tmp_path.glob('.dcrc-dlc-pairs-*'));p=cache/'alpha.json'
    value=json.loads(p.read_text());value['item']['canonical']='SONICADV_599';p.write_text(json.dumps(value))
    before=list(http[1])
    with pytest.raises(ConverterError) as caught:download(c,target,ids=['alpha','beta'])
    assert caught.value.code=='dlc_cache' and http[1]==before


def test_transient_retry_cancelled_during_backoff(http,tmp_path,monkeypatch):
    c=setup(http);cancel=threading.Event();url=c['entries'][0]['vmi_url']
    http[0][url]=TimeoutError()
    monkeypatch.setattr(dlc.time,'sleep',lambda _:cancel.set())
    with pytest.raises(Cancelled):download(c,tmp_path/'out',cancel=cancel)
    assert http[1].count(url)==1



def test_explicit_preflight_disables_non_us_family_before_selection(http):
    c=setup(http);http[0][c['entries'][0]['vmi_url']]=container('SONICADV_001')[0]
    checked=dlc.discover_catalog(preflight=True)
    assert checked['entries'][0]['supported'] is False
    assert checked['entries'][0]['reason']=='unsupported_us_name_family'
    dlc._validate_catalog(checked,checked['fingerprint'])


def test_tls_mirror_same_path_still_validates_container_and_records_provenance(http,tmp_path):
    import ssl,urllib.error
    c=setup(http);entry=c['entries'][0]
    for kind,data in zip(('vmi','vms'),container()):
        url=entry[kind+'_url'];http[0][url]=urllib.error.URLError(ssl.SSLCertVerificationError())
        http[0][url.replace('dc.dreamcast-talk.com','dc.dreamcastlive.net')]=data
    r=download(c,tmp_path/'out')
    assert r['downloaded'][0]['vmi']['url']==entry['vmi_url']
    assert r['downloaded'][0]['vmi']['final_url'].startswith('https://dc.dreamcastlive.net/')



def test_transient_timeout_recovers_within_attempt_bound(monkeypatch):
    calls=[]
    def fetch(*args):
        calls.append(args)
        if len(calls)<3:raise dlc._error('transient','DLC server connection/read timed out.')
        return b'bounded',args[0]
    monkeypatch.setattr(dlc,'_fetch_once',fetch)
    monkeypatch.setattr(dlc,'RETRY_DELAYS',(0,0))
    url='https://dc.dreamcast-talk.com/dlc/sa1/Test.VMI'
    assert dlc._fetch(url,108,'vmi',None)==(b'bounded',url)
    assert len(calls)==3



def test_new_output_and_narrower_selection_reuse_shared_verified_pair(http,tmp_path):
    c=setup(http,paragraph('Alpha')+paragraph('Beta'))
    http[0][c['entries'][1]['vmi_url']]=OSError('unavailable')
    with pytest.raises(ConverterError):download(c,tmp_path/'events_first',ids=['alpha','beta'])
    before=list(http[1]);result=download(c,tmp_path/'events_second',ids=['alpha'])
    assert http[1]==before and len(result['downloaded'])==1
    assert not (tmp_path/'events_first').exists()
    assert len(list(tmp_path.glob('.dcrc-dlc-pairs-*')))==1


def test_shared_cache_concurrent_identical_publication_is_verified(http,tmp_path,monkeypatch):
    c=setup(http);original=dlc.os.link
    def collide(source,target):
        if Path(target).suffix=='.json' and Path(target).name!='dlc_download.json':
            Path(target).write_bytes(Path(source).read_bytes())
        return original(source,target)
    monkeypatch.setattr(dlc.os,'link',collide)
    result=download(c,tmp_path/'out')
    assert len(result['downloaded'])==1


def test_shared_cache_foreign_concurrent_publication_is_preserved(http,tmp_path,monkeypatch):
    c=setup(http);original=dlc.os.link
    def collide(source,target):
        if Path(target).suffix=='.json':Path(target).write_bytes(b'foreign cache')
        return original(source,target)
    monkeypatch.setattr(dlc.os,'link',collide)
    with pytest.raises(ConverterError) as caught:download(c,tmp_path/'out')
    assert caught.value.code=='dlc_cache'
    assert next(tmp_path.glob('.dcrc-dlc-pairs-*/test.json')).read_bytes()==b'foreign cache'
    assert not (tmp_path/'out').exists()
