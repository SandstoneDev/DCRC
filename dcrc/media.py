"""Bounded local game-media decoding. No payload is distributed with this module."""
import io, re, struct
from .errors import ConverterError

MAX_ARCHIVE=4<<20

def fail(message):raise ConverterError('xmb_media',message)

def valid_artwork_id(value):
    return isinstance(value,str) and (value in ('title','sega') or bool(re.fullmatch(r'pvm:[A-Z0-9_.-]{1,100}:(?:[A-Za-z0-9_. -]{1,28})|img:[A-Z0-9_.-]{1,100}',value)))

def split_artwork_id(value):
    if not valid_artwork_id(value):fail('Invalid game artwork ID.')
    if value.startswith('pvm:'):
        _,archive,tile=value.split(':');return archive,tile
    if value.startswith('img:'):return value[4:],None
    return ('TITLE.PRS','beta_title0') if value=='title' else ('SEGALOGO.PRS','segalogo0')

def archive_tiles(compressed):
    from .profiles import decode_overlay
    if not 0<len(compressed)<=MAX_ARCHIVE:fail('Picture archive exceeds its bound.')
    raw=compressed if compressed[:4]==b'PVMH' else decode_overlay(compressed,MAX_ARCHIVE)
    if len(raw)<12 or raw[:4]!=b'PVMH':fail('Missing picture archive header.')
    size,flags,count=struct.unpack_from('<IHH',raw,4);cursor=8+size
    if flags not in (9,0x109) or not 0<count<=256 or cursor%32 or not 12+34*count<=cursor<=len(raw):fail('Invalid picture directory bounds.')
    tiles=[];names=set()
    for i in range(count):
        name=struct.unpack_from('<H28sI',raw,12+34*i)[1].split(b'\0')[0].decode('ascii')
        if not re.fullmatch(r'[A-Za-z0-9_. -]{1,28}',name) or name in names:fail('Invalid/duplicate picture name.')
        names.add(name)
        if cursor+16>len(raw):fail('Truncated picture chunk.')
        if raw[cursor:cursor+4]==b'GBIX':
            length=struct.unpack_from('<I',raw,cursor+4)[0]
            if length<4 or cursor+8+length+16>len(raw):fail('Invalid GBIX bounds.')
            cursor+=8+length
        if raw[cursor:cursor+4]!=b'PVRT':fail('Missing PVRT chunk.')
        length,pix,fmt,_,w,h=struct.unpack_from('<IBBHHH',raw,cursor+4);end=cursor+8+length
        if length<8 or end>len(raw) or not all(1<=n<=1024 and n&(n-1)==0 for n in (w,h)):fail('Invalid PVR dimensions/bounds.')
        tiles.append((name,pix,fmt,w,h,raw[cursor+16:end]));cursor=(end+31)&~31
    if cursor>len(raw):fail('Truncated picture alignment.')
    return tiles

def _morton(x,y,w,h):
    bits=min(w,h).bit_length()-1;v=((x if w>=h else y)>>bits)<<(2*bits)
    for b in range(bits):v|=((y>>b&1)<<(2*b))|((x>>b&1)<<(2*b+1))
    return v

def decode_tile(tile,preview_size=None):
    from PIL import Image
    name,pix,fmt,w,h,data=tile
    if pix not in (0,1,2) or fmt not in (1,3,9,0x0d):fail('Unsupported PVR pixel/layout format.')
    vq=fmt==3
    if vq and (w<2 or h<2):fail('Invalid VQ dimensions.')
    expected=2048+w*h//4 if vq else w*h*2
    if not 0<=len(data)-expected<=31 or any(data[expected:]):fail('Invalid PVR pixel payload/alignment.')
    ow,oh=w,h
    if preview_size:
        ratio=min(1,preview_size[0]/w,preview_size[1]/h);ow=max(1,int(w*ratio));oh=max(1,int(h*ratio))
    rgba=bytearray(ow*oh*4)
    for dy in range(oh):
        y=min(h-1,dy*h//oh)
        for dx in range(ow):
            x=min(w-1,dx*w//ow)
            if vq:
                code=data[2048+_morton(x//2,y//2,w//2,h//2)]
                index=code*4+(x&1)*2+(y&1)
            else:index=_morton(x,y,w,h) if fmt in (1,0x0d) else y*w+x
            value=struct.unpack_from('<H',data,2*index)[0]
            if pix==1:
                r=value>>11;g=value>>5&63;b=value&31;pixel=((r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2),255)
            elif pix==0:
                r=value>>10&31;g=value>>5&31;b=value&31;pixel=((r<<3)|(r>>2),(g<<3)|(g>>2),(b<<3)|(b>>2),255 if value&0x8000 else 0)
            else:pixel=((value>>8&15)*17,(value>>4&15)*17,(value&15)*17,(value>>12)*17)
            rgba[4*(dy*ow+dx):4*(dy*ow+dx)+4]=bytes(pixel)
    image=Image.frombytes('RGBA',(ow,oh),bytes(rgba));image.info['catalog_size']=(w,h);return image

def decode_picture(raw):
    from PIL import Image,ImageOps
    if not 0<len(raw)<=MAX_ARCHIVE:fail('Picture exceeds its bound.')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ('PNG','JPEG','BMP') or not 0<im.width*im.height<=1048576:fail('Unsupported game picture or pixel bound.')
            im.load();return ImageOps.exif_transpose(im).convert('RGBA')
    except (OSError,ValueError,Image.DecompressionBombError) as e:fail('Invalid game picture: '+str(e))

def selected_image(read,identity,boot=None):
    from .xmb import compose_title
    name,tile=split_artwork_id(identity);raw=read(name,MAX_ARCHIVE)
    if identity=='title' and boot is not None:return compose_title(raw,boot),raw
    if identity.startswith('img:'):return decode_picture(raw),raw
    for item in archive_tiles(raw):
        if item[0]==tile:return decode_tile(item),raw
    fail('Selected artwork tile is missing.')


def _source_access(source,cancel=None):
    """Context manager for bounded folder/disc reads; does not mount or extract."""
    from contextlib import contextmanager
    @contextmanager
    def access():
        from . import disc
        from .storage import plain_path
        from .xmb import _cancel,_fail
        source_path=plain_path(source);image=None
        try:
            if source_path.is_dir():
                root=source_path/'data' if (source_path/'data'/'1ST_READ.BIN').is_file() else source_path
                entries={e['path'].upper():e for e in disc._folder_entries(root)}
                def read(name,limit,head=False):
                    _cancel(cancel);e=entries[name]
                    if not head and not 0<e['bytes']<=limit:_fail('Media exceeds its size bound.')
                    with plain_path(root/e['path']).open('rb') as stream:raw=stream.read(limit if head else limit+1)
                    if not head and len(raw)!=e['bytes']:_fail('Media changed during preview.')
                    return raw
            else:
                image=disc._Image(source_path);entries={e['path'].upper():e for e in image.files()}
                def read(name,limit,head=False):
                    _cancel(cancel);e=entries[name]
                    if not head and not 0<e['bytes']<=limit:_fail('Media exceeds its size bound.')
                    raw=bytearray()
                    for block in image.extent(e['lba'],min(e['bytes'],limit)):_cancel(cancel);raw.extend(block)
                    return bytes(raw)
            yield entries,read
        finally:
            if image:image.close()
    return access()


def export_source_image(source,artwork_id,destination,*,cancel=None,event=None):
    """Export the exact catalog tile/composition to a new PNG; never overwrite."""
    import hashlib
    from .storage import plain_path
    from .profiles import BOOT_BYTES,BOOT_SHA256
    from .xmb import _cancel
    with _source_access(source,cancel) as (entries,read):
        boot=read('1ST_READ.BIN',BOOT_BYTES)
        if len(boot)!=BOOT_BYTES or hashlib.sha256(boot).hexdigest()!=BOOT_SHA256:fail('Unsupported boot identity for media preview.')
        im,_=selected_image(lambda n,z:read('SONICADV/'+n,z),artwork_id,boot)
        _cancel(cancel);destination=plain_path(destination)
        with destination.open('xb') as stream:im.save(stream,format='PNG')
    if event:event(dict(type='progress',stage='xmb_preview',message=artwork_id,progress=1))
    return destination


def preview_source_audio(source,track,start,seconds,destination,*,ffmpeg=None,cancel=None,event=None):
    """Decode a 1..10 second source segment into new stereo 44100 Hz PCM WAV.

    track is the catalog ADX ID, or None when source is a user-selected local file.
    FFmpeg is supplied/resolved exactly as conversion; no ATRAC encoder is needed.
    """
    import math,tempfile,wave
    from .storage import plain_path
    from .process import CommandRunner
    from .xmb import _tool,_cancel,_Cancellation,_snapshot_audio,MAX_AUDIO,_adx
    try:start=float(start);seconds=float(seconds)
    except (TypeError,ValueError):fail('Invalid audio segment.')
    if not math.isfinite(start) or not math.isfinite(seconds) or not 0<=start<=7200 or not 1<=seconds<=10:fail('Audio start must be 0..7200 and duration 1..10 seconds.')
    _cancel(cancel);destination=plain_path(destination)
    if destination.exists():fail('Audio preview output already exists.')
    ff=_tool(ffmpeg,'ffmpeg')
    with tempfile.TemporaryDirectory(prefix='dcrc-audition-') as temp:
        from pathlib import Path
        work=Path(temp)
        if track is not None:
            if not isinstance(track,str) or not re.fullmatch(r'[A-Za-z0-9_]+\.ADX',track,re.I):fail('Invalid catalog audio ID.')
            with _source_access(source,cancel) as (_,read):raw=read('SONICADV/'+track.upper(),MAX_AUDIO)
            _adx(raw[:128]);frozen=work/'source.adx';frozen.write_bytes(raw)
        else:frozen,_=_snapshot_audio(source,work,cancel)
        segment=work/'segment.wav'
        CommandRunner(work/'commands.log',event,_Cancellation(cancel)).run([str(ff),'-hide_banner','-v','error','-nostdin','-n','-ss',str(start),*(['-f','adx'] if frozen.suffix.lower()=='.adx' else []),'-i',str(frozen),'-t',str(seconds),'-vn','-map_metadata','-1','-ac','2','-ar','44100','-c:a','pcm_s16le',str(segment)],label='audio_preview')
        _cancel(cancel)
        with wave.open(str(segment),'rb') as stream:
            requested=round(seconds*44100)
            # ATRAC timestamps can include decoder preroll. Bound it, then
            # write exactly the requested PCM prefix rather than a longer cut.
            if (stream.getnchannels(),stream.getsampwidth(),stream.getframerate(),stream.getcomptype())!=(2,2,44100,'NONE') or not 44100<=stream.getnframes()<=requested+2*44100:fail('Invalid decoded preview WAV.')
            count=min(requested,stream.getnframes());pcm=stream.readframes(count)
            if len(pcm)!=count*4:fail('Truncated decoded preview WAV.')
        with destination.open('xb') as output, wave.open(output,'wb') as stream:
            stream.setparams((2,2,44100,0,'NONE','not compressed'));stream.writeframes(pcm)
    return destination
