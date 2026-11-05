"""Compatibility facts and strict validation of locally supplied game data.

Part of DCRC (MIT). No game payload is bundled with this module.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from .errors import ConverterError

PROFILE_ID='sa1_us_1005'
PROFILE_DIR=Path(__file__).resolve().parent/'data'/PROFILE_ID
BOOT_SHA256='45bc5d3c25dcfe2cc2c5701311d46783f33e4daa44a951cd9896724d66f0367a'
BOOT_BYTES=6735488

def _error(message):raise ConverterError('PROFILE_INVALID',message)

def load_profile(profile_id=PROFILE_ID):
    if profile_id!=PROFILE_ID:raise ConverterError('UNSUPPORTED_PROFILE',f'Unsupported profile: {profile_id}')
    try:
        p=json.loads((PROFILE_DIR/'profile.json').read_text(encoding='utf-8'))
        if p['id']!=PROFILE_ID or p['schema']!=1 or p['boot']!={'path':'1ST_READ.BIN','bytes':BOOT_BYTES,'sha256':BOOT_SHA256}:_error('Invalid supported boot identity in profile')
        if len(p['overlays'])!=58 or len(p['catalogs'])!=59:_error('Incomplete compatibility profile')
        names=[o['name']for o in p['overlays']]
        if len(set(names))!=58 or set(p['catalogs'])!={'main',*names}:_error('Duplicate or missing profile units')
        for unit,c in p['catalogs'].items():
            rel=Path(c['file'])
            if rel.is_absolute()or any(x in ('..','')for x in rel.parts):_error('Invalid catalog path')
            file=PROFILE_DIR/rel
            if file.is_symlink()or not file.resolve().is_relative_to(PROFILE_DIR.resolve()):_error('Catalog must remain in profile')
            raw=file.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=c['sha256']:_error(f'Catalog checksum differs: {unit}')
            facts=json.loads(raw)
            if set(facts)!={'functions'}or len(facts['functions'])!=c['rows']:_error(f'Catalog schema differs: {unit}')
            seen=set()
            for f in facts['functions']:
                if set(f)!={'entry','end','origin'}:_error('Catalog may contain only entry/end/origin facts')
                if not all(isinstance(f[k],str)and re.fullmatch(r'0x[0-9a-fA-F]{8}',f[k])for k in ('entry','end')):_error('Invalid catalog address')
                e,z=int(f['entry'],16),int(f['end'],16)
                if e%2 or z%2 or z<e or e in seen or f['origin']not in ('seed','call','pointer','branch','sweep'):_error('Invalid catalog function boundary')
                seen.add(e)
        return p
    except ConverterError:raise
    except (OSError,ValueError,KeyError,TypeError)as e:raise ConverterError('PROFILE_INVALID',f'Cannot read compatibility profile: {e}')from e

def decode_overlay(src:bytes,limit:int=32*1024*1024)->bytes:
    """Bounded PRS decoder; reads only the supplied stream, bounds output."""
    out=bytearray();pos=flags=left=0
    def byte():
        nonlocal pos
        if pos>=len(src):raise ValueError('truncated PRS stream')
        v=src[pos];pos+=1;return v
    def bit():
        nonlocal flags,left
        if not left:flags=byte();left=8
        v=flags&1;flags>>=1;left-=1;return v
    while True:
        if bit():
            if len(out)>=limit:raise ValueError('PRS output exceeds configured size')
            out.append(byte());continue
        if bit():
            a,b=byte(),byte()
            if a==b==0:return bytes(out)
            offset=((b<<8|a)>>3)-8192;size=a&7;size=byte()+1 if not size else size+2
        else:size=(bit()<<1|bit())+2;offset=byte()-256
        if len(out)+size>limit or len(out)+offset<0:raise ValueError('PRS copy is outside configured output')
        for _ in range(size):out.append(out[len(out)+offset])

def validate_files(files,read):
    """Validate a hashed logical file manifest and its bounded file reader."""
    p=load_profile();byname={f['path']:f for f in files};boot=byname.get('1ST_READ.BIN')
    if not boot or boot['bytes']!=BOOT_BYTES or boot['sha256']!=BOOT_SHA256:
        raise ConverterError('UNSUPPORTED_GAME','The supplied executable is not Sonic Adventure USA V1.005.',f'Expected 1ST_READ.BIN SHA-256 {BOOT_SHA256}')
    checked=[]
    for ov in p['overlays']:
        item=byname.get(ov['file'])
        if not item:raise ConverterError('MISSING_DATA',f'Missing required overlay: {ov["file"]}')
        if item['bytes']>ov['bytes']*2+65536:raise ConverterError('INVALID_OVERLAY',f'Oversized PRS input: {ov["file"]}')
        try:decoded=decode_overlay(read(ov['file']),ov['bytes'])
        except (ValueError,IndexError)as e:raise ConverterError('INVALID_OVERLAY',f'Invalid PRS overlay {ov["file"]}: {e}')from e
        if len(decoded)!=ov['bytes']or hashlib.sha256(decoded).hexdigest()!=ov['sha256']:
            raise ConverterError('UNSUPPORTED_GAME',f'Overlay differs from the supported version: {ov["file"]}')
        checked.append({'path':ov['file'],'bytes':len(decoded),'sha256':ov['sha256']})
    return {'profile':p['id'],'title':p['title'],'region':p['region'],'product':p['product'],'version':p['version'],'boot':dict(p['boot']),'overlays':checked}

def verify_folder(folder):
    from .disc import inspect_source
    return inspect_source(Path(folder))

def identify(source):
    from .disc import inspect_source
    return inspect_source(source)
