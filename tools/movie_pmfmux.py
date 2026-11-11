"""Own PSMF format tooling, originally developed for PS2RC by SandstoneDev,
then adapted through SDXR and DCRC. MIT, Copyright (c) 2026 SandstoneDev.
No proprietary SDK code, executable, game data, or bundled encoder.
"""
import math,os,struct,hashlib
from pathlib import Path
try:
    from . import movie_pmfinfo as pmfinfo
except ImportError:
    import movie_pmfinfo as pmfinfo

PACK = 2048
FRAME = 3003                      # 90 kHz ticks per picture at 30000/1001 fps
MUX_RATE = 25000                  # pack header / PSMF header unit: 50 bytes/s -> 10 Mbit/s
SCR_LEAD = 36000                  # first pack's SCR = first DTS - 0.4 s (90 kHz)
RECOVERY_SEI = bytes.fromhex('060601c480')   # recovery_frame_cnt 0, exact_match 1, broken_link 0
NAL_AUD, NAL_SEI, NAL_SPS, NAL_PPS, NAL_IDR, NAL_SLICE = 9, 6, 7, 8, 5, 1


class MuxError(Exception):
    pass


# ------------------------------------------------------------------------------------------------ NAL units
def split_nals(es):
    """Annex-B -> list of NAL unit bytes (no start code, trailing zero bytes removed)"""
    starts = []
    i = es.find(b'\x00\x00\x01')
    while i >= 0:
        starts.append(i + 3)
        i = es.find(b'\x00\x00\x01', i + 3)
    nals = []
    for k, s in enumerate(starts):
        e = starts[k + 1] - 3 if k + 1 < len(starts) else len(es)
        nal = es[s:e].rstrip(b'\x00')
        if nal:
            nals.append(nal)
    return nals


def escape(rbsp):
    out, z = bytearray(), 0
    for c in rbsp:
        if z >= 2 and c <= 3:
            out.append(3)
            z = 0
        out.append(c)
        z = z + 1 if c == 0 else 0
    return bytes(out)


def sei_messages(nal):
    r=pmfinfo.unescape(nal[1:]);msgs=[];i=0
    def number():
        nonlocal i
        value=0
        while i<len(r):
            c=r[i];i+=1;value+=c
            if c!=255:return value
        raise MuxError('truncated SEI length')
    while i<len(r) and not (i==len(r)-1 and r[i]==0x80):
        kind=number();size=number()
        if size>65535 or size>len(r)-i or len(msgs)>=1024:raise MuxError('invalid SEI payload bounds')
        msgs.append((kind,r[i:i+size]));i+=size
    return msgs


def sei_nal(header_byte, msgs):
    body = bytearray()
    for t, p in msgs:
        for v in (t, len(p)):
            while v >= 255:
                body.append(255)
                v -= 255
            body.append(v)
        body += p
    body.append(0x80)
    return bytes([header_byte]) + escape(bytes(body))


def first_mb_zero(nal):
    """a slice NAL whose first_mb_in_slice is 0 (ue(v) = '1')"""
    return len(nal) > 1 and (nal[1] & 0x80) != 0


def slice_type(nal):
    b = pmfinfo.Bits(pmfinfo.unescape(nal[1:8]))
    b.ue()
    return b.ue() % 5             # 0 P, 1 B, 2 I, 3 SP, 4 SI


def add_delimiters(nals):
    """a stream without access unit delimiters (e.g. OpenH264): one before every picture's first NAL unit - a new
    access unit starts at an SPS / PPS / SEI after a picture, or at a slice with first_mb_in_slice 0"""
    out, have_vcl = [], False
    for nal in nals:
        t = nal[0] & 0x1F
        vcl = t in (NAL_IDR, NAL_SLICE)
        if not out or (have_vcl and (t in (NAL_SPS, NAL_PPS, NAL_SEI) or (vcl and first_mb_zero(nal)))):
            out.append(bytes([NAL_AUD, 0xF0]))           # primary_pic_type 7: any slice type
            have_vcl = False
        out.append(nal)
        have_vcl = have_vcl or vcl
    return out


def access_units(es, keep_userdata=False, recovery_sei=True, insert_aud=True):
    """-> list of {'nals', 'idr', 'ref', 'bytes'}; validates the stream"""
    nals = split_nals(es)
    if not nals:
        raise MuxError('no NAL units (not an Annex-B H.264 stream?)')
    if nals[0][0] & 0x1F != NAL_AUD:
        if not insert_aud or any(n[0] & 0x1F == NAL_AUD for n in nals):
            raise MuxError('the stream does not start with an access unit delimiter (encode with aud=1)')
        nals = add_delimiters(nals)
    try:validated_sps=pmfinfo.parameter_sets(nals)
    except ValueError as error:raise MuxError(str(error)) from error
    aus = []
    for nal in nals:
        t = nal[0] & 0x1F
        if t == NAL_AUD:
            aus.append({'nals': []})
        if t == NAL_SEI and not keep_userdata:
            msgs = sei_messages(nal)
            kept = [m for m in msgs if m[0] != 5]
            if not kept:
                continue
            if len(kept) != len(msgs):
                nal = sei_nal(nal[0], kept)
        aus[-1]['nals'].append(nal)
    sps = validated_sps
    for k, au in enumerate(aus):
        types = [n[0] & 0x1F for n in au['nals']]
        vcl = [n for n in au['nals'] if (n[0] & 0x1F) in (NAL_IDR, NAL_SLICE)]
        if not vcl:
            raise MuxError('access unit %d has no picture' % k)
        if sum(1 for n in vcl if first_mb_zero(n)) != 1 or not first_mb_zero(vcl[0]):
            raise MuxError('access unit %d: %d pictures (one access unit delimiter per picture needed)' % (
                k, sum(1 for n in vcl if first_mb_zero(n))))
        au['idr'] = (vcl[0][0] & 0x1F) == NAL_IDR
        au['ref'] = (vcl[0][0] >> 5) & 3 != 0
        if any(slice_type(n) == 1 for n in vcl):
            raise MuxError('access unit %d has B slices (encode with bframes=0)' % k)
        if not au['ref']:
            raise MuxError('access unit %d is a non-reference picture (encode with bframes=0)' % k)
        if au['idr']:
            if NAL_SPS not in types or NAL_PPS not in types:
                raise MuxError('IDR access unit %d without SPS/PPS (encode with repeat-headers=1)' % k)
            if recovery_sei and not any(n[0] & 0x1F == NAL_SEI and any(t == 6 for t, _ in sei_messages(n))
                                        for n in au['nals']):
                pos = next(i for i, n in enumerate(au['nals']) if (n[0] & 0x1F) in (NAL_IDR, NAL_SLICE))
                au['nals'].insert(pos, RECOVERY_SEI)
        out = bytearray()
        for n in au['nals']:
            out += (b'\x00\x00\x00\x01' if (n[0] & 0x1F) in (NAL_AUD, NAL_SPS, NAL_PPS) else b'\x00\x00\x01') + n
        au['bytes'] = bytes(out)
        if len(out) > 0xFFFF:
            raise MuxError('access unit %d is %d bytes (the random access point record holds 16-bit sizes: '
                           'lower the VBV buffer)' % (k, len(out)))
    if not aus[0]['idr']:
        raise MuxError('the first access unit is not an IDR picture')
    if sps is None or 'width' not in sps:
        raise MuxError('no usable SPS')
    return aus, sps


# ------------------------------------------------------------------------------------------------ MPEG-2 PS
def ts5(prefix, t):
    return bytes([(prefix << 4) | (((t >> 30) & 7) << 1) | 1, (t >> 22) & 0xFF, (((t >> 15) & 0x7F) << 1) | 1,
                  (t >> 7) & 0xFF, ((t & 0x7F) << 1) | 1])


def pack_header(scr27):
    base, ext = scr27 // 300, scr27 % 300
    b = bytearray(b'\x00\x00\x01\xba')
    b.append(0x40 | (((base >> 30) & 7) << 3) | 0x04 | ((base >> 28) & 3))
    b.append((base >> 20) & 0xFF)
    b.append((((base >> 15) & 0x1F) << 3) | 0x04 | ((base >> 13) & 3))
    b.append((base >> 5) & 0xFF)
    b.append(((base & 0x1F) << 3) | 0x04 | ((ext >> 7) & 3))
    b.append(((ext & 0x7F) << 1) | 1)
    b += bytes([(MUX_RATE >> 14) & 0xFF, (MUX_RATE >> 6) & 0xFF, ((MUX_RATE & 0x3F) << 2) | 3, 0xF8])
    return bytes(b)


def system_header(pstd_kb):
    rate = MUX_RATE
    body = bytes([0x80 | ((rate >> 15) & 0x7F), (rate >> 7) & 0xFF, ((rate & 0x7F) << 1) | 1,
                  0x80,                         # audio bound 32, not fixed, not CSPS
                  0xF0,                         # audio lock, video lock, marker, video bound 16
                  0x7F,
                  0xB9, 0xE0 | (pstd_kb >> 8), pstd_kb & 0xFF,     # all video streams, scale 1024
                  0xBD, 0xE3, 0x08])            # private stream 1 bound as in the reference files
    return b'\x00\x00\x01\xbb' + struct.pack('>H', len(body)) + body


def pes(sid, payload, pts=None, dts=None, pstd_kb=None, stuffing=0):
    opt = b''
    f2 = 0
    if pts is not None:
        f2 |= 0xC0
        opt += ts5(3, pts) + ts5(1, dts)
    if pstd_kb is not None:
        f2 |= 0x01
        opt += bytes([0x1E, 0x60 | (pstd_kb >> 8), pstd_kb & 0xFF])
    opt += b'\xff' * stuffing
    body = bytes([0x81, f2, len(opt)]) + opt + payload
    return b'\x00\x00\x01' + bytes([sid]) + struct.pack('>H', len(body)) + body


def padding(n):
    """a padding packet of n bytes in total (n >= 6)"""
    return b'\x00\x00\x01\xbe' + struct.pack('>H', n - 6) + b'\xff' * (n - 6)


def rapi(sid, idx, sizes):
    body = bytes([1, sid]) + struct.pack('>4H', *idx) + b'\0\0\0\0' + struct.pack('>HH', 2 + 4 * len(sizes),
                                                                                 len(sizes))
    body += b''.join(struct.pack('>HH', 0x0080, s) for s in sizes)
    return b'\x00\x00\x01\xbf' + struct.pack('>H', len(body)) + body


def mux(es, first_pts=90000, vbv_kbit=1875, keep_userdata=False, recovery_sei=True, insert_aud=True, sid=0xE0,
        icon=False, version=None):
    """H.264 Annex-B bytes -> (PSMF bytes, stats); version: 4 ASCII digits (default "0015", icon=True -> "0014")"""
    version = (version or ('0014' if icon else '0015')).encode('ascii')
    if len(version) != 4 or not version.isdigit():
        raise MuxError('version must be 4 digits')
    aus, sps = access_units(es, keep_userdata, recovery_sei, insert_aud)
    if sps['width'] > 480 or sps['height'] > 272 or sps['width'] % 16 or sps['height'] % 16:
        raise MuxError('picture %dx%d (the PSP decoder takes up to 480x272 in 16-pixel units)' % (
            sps['width'], sps['height']))
    if not sps.get('frame_mbs_only'):
        raise MuxError('interlaced coding (frame_mbs_only 0)')
    pstd_kb = int(math.ceil(vbv_kbit * 1000 / 8 / 1024.0)) + 6
    if pstd_kb > 0x1FFF:
        raise MuxError('VBV buffer %d kbit too large' % vbv_kbit)
    gops = [k for k, au in enumerate(aus) if au['idr']] + [len(aus)]
    packs = []                      # bytes of each pack (filled with a placeholder SCR first)
    scr_dts = []                    # DTS (90 kHz) of the access unit the pack's first video byte belongs to
    pack_ticks = int(math.ceil(PACK * 27e6 / (MUX_RATE * 50)))
    for g in range(len(gops) - 1):
        a, b = gops[g], gops[g + 1]
        if b - a > 490:
            raise MuxError('group of pictures of %d access units (the record must fit one pack: keyint <= 490)'
                           % (b - a))
        data = b''.join(aus[k]['bytes'] for k in range(a, b))
        starts, o = [], 0
        for k in range(a, b):
            starts.append(o)
            o += len(aus[k]['bytes'])
        ends = [starts[i] + len(aus[a + i]['bytes']) - 1 for i in range(b - a)]
        rap_pack = len(packs)
        pos = 0
        last_pack_of_byte = []      # (first byte, last byte, pack index)
        first = True
        si = 0                      # next access unit start index (relative)
        while pos < len(data) or first:
            head = b''
            room = PACK - 14
            if first:
                rec_len = 6 + 18 + 4 * (b - a)
                head = system_header(pstd_kb)
                room -= len(head) + rec_len
            while si < len(starts) and starts[si] < pos:
                si += 1
            left = len(data) - pos
            ext = 3 if first else 0
            cap0 = room - 9 - ext
            if first or (si < len(starts) and starts[si] < pos + cap0 - 10):
                # an access unit starts here: PTS/DTS of the first one that starts in this PES
                cap = room - 9 - 10 - ext
                k = si
                pts = first_pts + FRAME * (a + k)
                take = min(cap, left)
                ts = (pts, pts - FRAME)
            else:
                cap = cap0
                take = min(cap, left)
                ts = None
            free = cap - take
            stuffing = 0
            if 0 < free < 6:
                stuffing, free = free, 0
            payload = data[pos:pos + take]
            body = pes(sid, payload, *(ts or (None, None)), pstd_kb=pstd_kb if first else None, stuffing=stuffing)
            pk_items = [head, None if first else b'', body]
            if free:
                pk_items.append(padding(free))
            packs.append(pk_items)
            k_first = next(i for i in range(len(starts) - 1, -1, -1) if starts[i] <= pos) if take else len(starts) - 1
            scr_dts.append(first_pts + FRAME * (a + k_first) - FRAME)
            last_pack_of_byte.append((pos, pos + take - 1, len(packs) - 1))
            pos += take
            first = False

        def pack_holding(byte):
            for lo, hi, pi in last_pack_of_byte:
                if lo <= byte <= hi:
                    return pi
            raise MuxError('internal: byte %d not placed' % byte)
        # a group with fewer than four pictures: 0xFFFF for the missing ones (as the reference tool writes)
        idx = [pack_holding(ends[j]) - rap_pack if j < len(ends) else 0xFFFF for j in range(4)]
        packs[rap_pack][1] = rapi(sid, idx, [len(aus[k]['bytes']) for k in range(a, b)])
    # SCR: first DTS - 0.4 s, never closer than one pack time to the previous pack
    out = bytearray()
    scr = None
    for items, dts in zip(packs, scr_dts):
        want = (dts - SCR_LEAD) * 300
        scr = max(want, 0) if scr is None else max(scr + pack_ticks, want)
        pk = pack_header(scr) + b''.join(items)
        if len(pk) != PACK:
            raise MuxError('internal: pack of %d bytes' % len(pk))
        out += pk
    n_frames = len(aus)
    last_ts = first_pts + FRAME * n_frames
    hdr = bytearray(0x800)
    hdr[0:8] = b'PSMF' + version
    struct.pack_into('>II', hdr, 8, 0x800, len(out))
    n = 1
    struct.pack_into('>I', hdr, 0x50, 46 + 16 * n)
    hdr[0x54:0x5A] = first_pts.to_bytes(6, 'big')
    hdr[0x5A:0x60] = last_ts.to_bytes(6, 'big')
    struct.pack_into('>II', hdr, 0x60, MUX_RATE, 90000)
    hdr[0x68], hdr[0x69] = n, 1
    struct.pack_into('>I', hdr, 0x6A, 20 + 16 * n)
    hdr[0x6E:0x74] = first_pts.to_bytes(6, 'big')
    hdr[0x74:0x7A] = last_ts.to_bytes(6, 'big')
    struct.pack_into('>HIH', hdr, 0x7A, 1, 2 + 16 * n, n)
    e = bytearray(16)
    e[0], e[1] = sid, 0
    struct.pack_into('>H', e, 2, 0x2000 | pstd_kb)
    e[12], e[13] = sps['width'] // 16, sps['height'] // 16
    hdr[0x82:0x92] = e
    stats = {'access_units': n_frames, 'idr': len(gops) - 1, 'packs': len(packs), 'bytes': 0x800 + len(out),
             'seconds': n_frames * FRAME / 90000.0, 'max_au': max(len(au['bytes']) for au in aus),
             'video_bytes': sum(len(au['bytes']) for au in aus), 'sps': sps, 'pstd_kb': pstd_kb}
    return bytes(hdr) + bytes(out), stats


def write_checked(es,out_path,**kw):
    data,stats=mux(es,**kw)
    problems=pmfinfo.check(pmfinfo.analyze_bytes(data))
    if problems:raise MuxError('self-check failed: '+'; '.join(problems))
    target=Path(out_path)
    with target.open('xb') as stream:
        if stream.write(data)!=len(data):raise OSError('short PMF write')
        stream.flush();os.fsync(stream.fileno())
    digest=hashlib.sha256()
    with target.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):digest.update(block)
    if digest.digest()!=hashlib.sha256(data).digest():raise MuxError('PMF readback differs')
    stats['check']='ok';return stats

def main():
    import argparse,json
    parser=argparse.ArgumentParser(description='Mux own/local Annex-B H264 to a new PMF file.')
    parser.add_argument('video');parser.add_argument('output');args=parser.parse_args()
    with open(args.video,'rb') as stream:es=stream.read()
    print(json.dumps(write_checked(es,args.output),indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
