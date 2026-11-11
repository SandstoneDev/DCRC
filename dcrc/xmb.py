"""User-local XMB art and music. Own DCRC code, MIT, SandstoneDev 2026.

Only user inputs supply pictures/audio. PVR/ADX are bounded format readers;
no game payload, game decoder body, or private SDK definitions are included.
ATRAC encoding is an external atracdenc process (LGPL-2.1 upstream:
https://github.com/dcherednik/atracdenc). RIFF/OMA container facts follow its
public liboma format and FFmpeg's public omadec/ATRAC RIFF readers.
Title placement is read from the locally verified boot animation records.
"""
from __future__ import annotations
import hashlib, io, math, os, re, shutil, struct, sys, wave
from pathlib import Path
from .errors import Cancelled, ConverterError
from .storage import plain_path, reject_links, file_digest, fingerprint
from .profiles import decode_overlay, BOOT_BYTES, BOOT_SHA256
from .process import CommandRunner

ATRAC_GUID=bytes.fromhex('bfaa23e958cb7144a119fffa01e4ce62')
MAX_ART=4<<20
MAX_AUDIO=64<<20
MAX_SND0=500000
ART=(('title','TITLE.PRS','Title artwork (first tile)','beta_title0'),
     ('sega','SEGALOGO.PRS','SEGA artwork (first tile)','segalogo0'))


def _fail(message):raise ConverterError('xmb_media',message)
def _cancel(cancel):
    if cancel is not None and (cancel.is_set() if hasattr(cancel,'is_set') else cancel()):raise Cancelled()


def _bounded(path,limit):
    path=plain_path(path)
    if not path.is_file() or not 0<path.stat().st_size<=limit:_fail('Media is missing or exceeds its size bound.')
    with path.open('rb') as f:raw=f.read(limit+1)
    if not 0<len(raw)<=limit:_fail('Media changed or exceeds its size bound.')
    return raw


def _raw_digest(raw):
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def _snapshot_audio(source,work,cancel):
    """Freeze bytes before external decoding; identity describes these exact bytes."""
    source=plain_path(source)
    if not source.is_file() or not 0<source.stat().st_size<=MAX_AUDIO:_fail('Music input is missing or exceeds 64 MiB.')
    suffix=source.suffix.lower()
    if not re.fullmatch(r'\.[a-z0-9]{1,8}',suffix):suffix='.bin'
    target=work/('source'+suffix);digest=hashlib.sha256();count=0
    with source.open('rb') as src,target.open('xb') as dst:
        while True:
            _cancel(cancel);block=src.read(1<<20)
            if not block:break
            count+=len(block)
            if count>MAX_AUDIO:_fail('Music input grew beyond 64 MiB while freezing.')
            if dst.write(block)!=len(block):_fail('Cannot write frozen audio input.')
            digest.update(block)
    if not count:_fail('Music input became empty while freezing.')
    return target,dict(bytes=count,sha256=digest.hexdigest())


def _folder(data_root):
    root=plain_path(data_root)
    for p in (root/'SONICADV',root):
        reject_links(p)
        if p.is_dir() and any(name in _entries(p) for _,name,_,_ in ART):return p
    _fail('The extracted SONICADV media directory is missing.')


def _entries(root):
    result={}
    for i,p in enumerate(root.iterdir()):
        if i>=4096:_fail('Media directory exceeds 4096 entries.')
        reject_links(p);key=p.name.upper()
        if key in result:_fail('Ambiguous media names differing only in case.')
        if p.is_file():result[key]=p
    return result


def _adx(raw):
    if len(raw)<20 or raw[:2]!=b'\x80\x00' or raw[4:7]!=b'\x03\x12\x04':_fail('Unsupported ADX header.')
    channels=raw[7];rate,samples=struct.unpack_from('>II',raw,8)
    if channels not in (1,2) or not 8000<=rate<=48000 or not 0<samples<=rate*7200:_fail('Invalid ADX rate/channels/length.')
    return dict(rate=rate,channels=channels,samples=samples,seconds=samples/rate)


def decode_art(compressed,texture_name=None):
    """Decode a bounded supported PVM tile (legacy first-tile API)."""
    from .media import archive_tiles,decode_tile
    try:
        tiles=archive_tiles(compressed)
        for tile in tiles:
            if texture_name is None or tile[0]==texture_name:return decode_tile(tile).convert('RGB')
        _fail('Selected artwork tile is absent.')
    except ConverterError:raise
    except (ValueError,IndexError,struct.error,UnicodeError) as e:raise ConverterError('xmb_media',f'Invalid picture archive: {e}') from e



def compose_title(compressed,boot):
    """Render user animation facts into the 640x480 title canvas.

    US1.005 table address 8C1C3B54 (20-byte sprite animation records), used by
    fn099DA0: six ordinary Sprite2D calls at origin320,0 and unit scale.
    Only address/format facts live here; UVs/texture order come from user bytes.
    """
    from PIL import Image,ImageOps
    offset=0x8c1c3b54-0x8c010000
    if offset+120>len(boot):_fail('Title animation records are outside the boot file.')
    out=Image.new('RGB',(640,480));seen=set()
    for i in range(6):
        w,h,cx,cy,u0,v0,u1,v1,tex,attr=struct.unpack_from('<8hHH',boot,offset+20*i)
        if (w,h)!=(256,256) or cx not in (-128,128,384) or cy not in (-256,0) or {u0,u1}!={0,256} or {v0,v1}!={0,256} or tex>=6 or attr or (cx,cy) in seen:_fail('Unsupported title animation record.')
        seen.add((cx,cy));image=decode_art(compressed,'beta_title'+str(tex))
        if image.size!=(256,256):_fail('Title tile dimensions differ from animation.')
        if u0>u1:image=ImageOps.mirror(image)
        if v0>v1:image=ImageOps.flip(image)
        out.paste(image,(320-cx,-cy))
    # The stored animation is the mirrored intro pose. An XMB cover uses
    # an explicit final presentation mirror, so title lettering reads normally.
    return ImageOps.mirror(out)


def _boot(root):
    path=plain_path(root.parent/'1ST_READ.BIN')
    if not path.exists():return None  # A bare media folder offers explicitly labelled first-tile art.
    raw=_bounded(path,BOOT_BYTES)
    if len(raw)!=BOOT_BYTES or hashlib.sha256(raw).hexdigest()!=BOOT_SHA256:_fail('Unsupported boot identity for title composition.')
    return raw


def _catalog(read,entries,preview=False,event=None,cancel=None,boot=None):
    result=dict(format='DCRC_XMB_CATALOG_V1',images=[],tracks=[])
    for identity,name,label,tile in ART:
        _cancel(cancel)
        if name not in entries:continue
        raw=read(name,MAX_ART)
        image=compose_title(raw,boot) if identity=='title' and boot is not None else decode_art(raw,tile)
        if identity=='title' and boot is not None:label='Title artwork'
        item=dict(id=identity,label=label,source='SONICADV/'+name,width=image.width,height=image.height)
        if preview:
            image.thumbnail((480,272));out=io.BytesIO();image.save(out,format='PNG');item['preview_png']=out.getvalue()
        result['images'].append(item)
        if event:event(dict(type='progress',stage='xmb_preview',message=label,progress=.3))
    from .media import archive_tiles,decode_tile,decode_picture
    # Archive/pixel limits bound discovery; unsupported formats remain unavailable.
    scanned_bytes=0
    def gallery_order(name):
        # Menu illustrations first; scene texture atlases must not consume the gallery cap.
        priority=0 if name in ('TITLE.PRS','SEGALOGO.PRS') else 1 if name.startswith(('AVA_','HD_','C_SELECT','CON_REGULAR','LOGO','ENDING')) else 2 if name.startswith('BG_') else 3 if name in ('SONIC.PRS','MILES.PRS','KNUCKLES.PRS','AMY.PRS','BIG.PRS','E102.PRS') else 4
        return priority,name
    for name in sorted(entries,key=gallery_order):
        _cancel(cancel)
        if not re.fullmatch(r'[A-Z0-9_.-]{1,100}',name):continue
        candidates=[]
        try:
            if name.endswith(('.PRS','.PVM')):
                raw=read(name,MAX_ART);scanned_bytes+=len(raw)
                if scanned_bytes>128<<20:
                    result['images_truncated']=True;break
                for tile in archive_tiles(raw):
                    _cancel(cancel)
                    try:
                        decoded=decode_tile(tile,(160,100) if preview else (1,1))
                        candidates.append(('pvm:'+name+':'+tile[0],tile[0],decoded))
                    except ConverterError:continue
            elif name.endswith(('.PNG','.JPG','.JPEG','.BMP')):
                candidates=[('img:'+name,name,decode_picture(read(name,MAX_ART)))]
        except (ConverterError,ValueError,IndexError,struct.error,UnicodeError):continue
        for identity,label,image in candidates:
            item=dict(id=identity,label=label,archive=name,source='SONICADV/'+name,width=image.info.get('catalog_size',image.size)[0],height=image.info.get('catalog_size',image.size)[1])
            if preview:
                image.thumbnail((160,100));out=io.BytesIO();image.save(out,format='PNG');item['preview_png']=out.getvalue()
            result['images'].append(item)
            if len(result['images'])>=512:
                result['images_truncated']=True;break
        if len(result['images'])>=512:break
        if event:event(dict(type='progress',stage='xmb_preview',message=name,progress=.5))
    for name in sorted(entries):
        _cancel(cancel)
        if name.endswith('.ADX'):
            try:info=_adx(read(name,128,True))
            except ConverterError:continue  # Unsupported tracks are not offered as selectable audio.
            result['tracks'].append(dict(id=name,label=name,source='SONICADV/'+name,**info))
    return result


def inspect_media(data_root,*,event=None,cancel=None):
    """Metadata only; IDs and paths are portable, no external tool is run."""
    _cancel(cancel);root=_folder(data_root);entries=_entries(root)
    def read(name,limit,head=False):
        _cancel(cancel)
        if head:
            with entries[name].open('rb') as f:return f.read(limit)
        return _bounded(entries[name],limit)
    return _catalog(read,entries,event=event,cancel=cancel,boot=_boot(root))


def inspect_source_media(source,*,event=None,cancel=None):
    """Bounded preview from folder/GDI/ISO; boot identity only, not full verification.

    preview_png is memory-only PNG bytes. This is not a conversion receipt;
    the normal pipeline still validates every required boot/overlay hash.
    """
    from . import disc
    _cancel(cancel);source=plain_path(source);image=None
    try:
        if source.is_dir():
            root=source/'data' if (source/'data'/'1ST_READ.BIN').is_file() else source
            entries=disc._folder_entries(root);byname={e['path'].upper():e for e in entries}
            def read_path(name,limit,head=False):
                e=byname[name]
                if not head and e['bytes']>limit:_fail('Preview input exceeds its bound.')
                path=plain_path(root/e['path'])
                with path.open('rb') as f:return f.read(limit if head else limit+1)
        else:
            image=disc._Image(source);byname={e['path'].upper():e for e in image.files()}
            def read_path(name,limit,head=False):
                e=byname[name]
                if not head and e['bytes']>limit:_fail('Preview input exceeds its bound.')
                result=bytearray()
                for block in image.extent(e['lba'],min(e['bytes'],limit)):
                    _cancel(cancel);result.extend(block)
                return bytes(result)
        boot=byname.get('1ST_READ.BIN')
        if not boot or boot['bytes']!=BOOT_BYTES:_fail('Preview requires the supported US1.005 boot file.')
        _cancel(cancel)
        boot_raw=read_path('1ST_READ.BIN',BOOT_BYTES)
        if hashlib.sha256(boot_raw).hexdigest()!=BOOT_SHA256:_fail('Unsupported boot identity for media preview.')
        media={k[len('SONICADV/'):]:e for k,e in byname.items() if k.startswith('SONICADV/') and '/' not in k[len('SONICADV/'): ]}
        result=_catalog(lambda n,z,head=False:read_path('SONICADV/'+n,z,head),media,True,event,cancel,boot_raw)
        result['verification']='boot_hash_only_preview';return result
    except (OSError,ValueError,KeyError) as e:raise ConverterError('xmb_preview',f'Cannot preview source media: {e}') from e
    finally:
        if image:image.close()


def _chunks(raw):
    if not 12<=len(raw)<=MAX_SND0 or raw[:4]!=b'RIFF' or raw[8:12]!=b'WAVE' or struct.unpack_from('<I',raw,4)[0]!=len(raw)-8:_fail('Invalid SND0 RIFF size/header.')
    chunks={};p=12
    while p<len(raw):
        if p+8>len(raw):_fail('Truncated SND0 chunk header.')
        key,size=struct.unpack_from('<4sI',raw,p);end=p+8+size
        if end+(size&1)>len(raw) or key in chunks:_fail('Invalid/duplicate SND0 chunk.')
        chunks[key]=raw[p+8:end];p=end+(size&1)
    return chunks


def validate_at3(raw):
    """Strict outer container validation; coded ATRAC frames are not decoded here."""
    c=_chunks(raw);fmt=c.get(b'fmt ',b'');fact=c.get(b'fact',b'');body=c.get(b'data',b'')
    if len(fmt)<16 or len(fact)<4:_fail('SND0 requires format and sample-count chunks.')
    tag,ch,rate,byte_rate,align=struct.unpack_from('<HHIIH',fmt)
    plus=tag==0xfffe and len(fmt)>=52 and fmt[24:40]==ATRAC_GUID
    atrac3=tag==0x270 and len(fmt)>=32
    if not (plus or atrac3) or ch!=2 or rate!=44100 or not 0<align<=8192 or not byte_rate or not body or len(body)%align:_fail('SND0 requires complete stereo 44100 Hz ATRAC3plus/ATRAC3 frames.')
    samples=struct.unpack_from('<I',fact)[0];coded=len(body)//align*(2048 if plus else 1024)
    if not 0<samples<=coded:_fail('Invalid SND0 sample count.')
    if b'smpl' in c:
        s=c[b'smpl']
        if len(s)<60 or struct.unpack_from('<I',s,28)[0]!=1:_fail('Invalid SND0 loop.')
        start,end=struct.unpack_from('<II',s,44)
        if start>end or end>=coded:_fail('SND0 loop lies outside coded frames.')
    return dict(codec='ATRAC3plus' if plus else 'ATRAC3',samples=samples,seconds=samples/44100,rate=rate,channels=ch,bytes=len(raw))


def _riff(parts):
    b=b'WAVE'+b''.join(k+struct.pack('<I',len(v))+v+bytes(len(v)&1) for k,v in parts)
    return b'RIFF'+struct.pack('<I',len(b))+b


def wrap_oma(raw,samples):
    """Normalize external atracdenc ATRAC3plus OMA into PSP RIFF + loop metadata."""
    p=0
    if raw[:3]==b'ea3':
        if len(raw)<10 or any(v&128 for v in raw[6:10]):_fail('Invalid OMA tag size.')
        p=10+sum(v<<(7*(3-i)) for i,v in enumerate(raw[6:10]))
    if p+96>len(raw) or raw[p:p+3]!=b'EA3' or raw[p+5]!=96:_fail('Invalid encoder OMA header.')
    word=struct.unpack_from('>I',raw,p+32)[0];align=(word&1023)*8+8;body=raw[p+96:]
    if word>>24!=1 or (word>>13&7)!=1 or (word>>10&7)!=2 or not body or len(body)%align:_fail('Encoder did not produce 44100 Hz stereo ATRAC3plus.')
    delay=4096
    if not 0<samples<=len(body)//align*2048-delay-368:_fail('Encoder output is too short for the selected segment.')
    fmt=struct.pack('<HHIIHHHHI',0xfffe,2,44100,align*44100//2048,align,0,34,2048,3)+ATRAC_GUID+struct.pack('>HH',256,(1<<13)|(2<<10)|(align//8-1))+bytes(8)
    loop=struct.pack('<9I',0,0,22676,60,0,0,0,1,0)+struct.pack('<6I',0,0,delay,delay+samples-1,0,0)
    result=_riff([(b'fmt ',fmt),(b'fact',struct.pack('<II',samples,delay)),(b'smpl',loop),(b'data',body)])
    validate_at3(result);return result


class _Cancellation:
    def __init__(self,cancel):self.cancel=cancel
    def is_set(self):
        c=self.cancel;return bool(c is not None and (c.is_set() if hasattr(c,'is_set') else c()))


def resolve_encoder(given=None):
    """Find, but never execute, explicit / portable-bundle / PATH atracdenc."""
    value=given
    if not value:
        from .media_tools import bundle_root
        root=bundle_root()
        if root is not None:
            candidate=root/'tools'/'atracdenc'/('atracdenc.exe' if os.name=='nt' else 'atracdenc')
            reject_links(candidate)
            if candidate.is_file():value=candidate
    if not value:value=shutil.which('atracdenc')
    if not value:_fail('Install atracdenc or select its executable explicitly: https://github.com/dcherednik/atracdenc')
    path=plain_path(value)
    if not path.is_file():_fail('atracdenc executable is missing.')
    return path


def _tool(value,name):
    if isinstance(value,dict):value=value.get(name)
    from .media_tools import find_tool
    path=find_tool(name,value or None) if name in ('ffmpeg','ffprobe') else value or shutil.which(name)
    if not path:_fail(f'Install {name} or select its executable explicitly. https://github.com/dcherednik/atracdenc' if name=='atracdenc' else 'Install FFmpeg: https://ffmpeg.org/download.html')
    path=plain_path(path)
    if not path.is_file():_fail(f'{name} executable is missing.')
    return path


def _sound(source,out,selection,ffmpeg,event,cancel):
    raw=None
    if source.suffix.lower()=='.at3':
        raw=_bounded(source,MAX_SND0);validate_at3(raw)
        return raw,dict(input=_raw_digest(raw),encoding='ready_at3')
    encoder=resolve_encoder(selection.get('xmb_encoder'));ff=_tool(ffmpeg,'ffmpeg')
    start=float(selection.get('xmb_music_start',0));seconds=float(selection.get('xmb_music_seconds',6))
    if not math.isfinite(start) or not math.isfinite(seconds) or not 0<=start<=7200 or not 1<=seconds<=10:_fail('Music start must be finite and duration 1..10 seconds.')
    work=out/'encode';work.mkdir();source,identity=_snapshot_audio(source,work,cancel)
    runner=CommandRunner(work/'commands.log',event,_Cancellation(cancel))
    runner.run([str(ff),'-hide_banner','-v','error','-nostdin','-n','-ss',str(start),*(['-f','adx'] if source.suffix.lower()=='.adx' else []),'-i',str(source),'-t',str(seconds),'-vn','-ac','2','-ar','44100','-c:a','pcm_s16le',str(work/'segment.wav')],label='xmb_pcm')
    _cancel(cancel)
    try:
        with wave.open(str(work/'segment.wav'),'rb') as f:
            if (f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getcomptype())!=(2,2,44100,'NONE'):_fail('FFmpeg did not produce stereo 44100 Hz PCM.')
            if not 44100<=f.getnframes()<=441000:_fail('Selected music segment is empty/too short/too long.')
            pcm=f.readframes(441001);samples=len(pcm)//4
        with wave.open(str(work/'input.wav'),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(44100);f.writeframes(pcm+bytes(4*(4096+368+4096)))
    except (wave.Error,EOFError) as e:raise ConverterError('xmb_audio',f'Invalid decoded PCM: {e}') from e
    runner.run([str(encoder),'-e','atrac3plus','-i','input.wav','-o','output.oma'],cwd=work,label='xmb_atrac')
    _cancel(cancel);raw=wrap_oma(_bounded(work/'output.oma',MAX_SND0),samples)
    return raw,dict(input=identity,encoder=file_digest(encoder),ffmpeg=file_digest(ff),start=start,seconds=seconds,encoding='atracdenc_atrac3plus')


def prepare_xmb(data_root,out,selection,*,ffmpeg=None,event=None,cancel=None):
    """Create new local icon0/pic1/snd0 artifacts, never overwrite existing output.

    Each game-art slot independently selects a catalog ID (default title).
    Title uses the verified local boot animation, or its labelled first tile
    for a bare media folder. SEGA is its first tile only; no layout is inferred.
    Disabled slots do not discover encoders or require an extracted game tree.
    """
    from PIL import Image,ImageOps
    _cancel(cancel);selection=dict(selection);modes={}
    for key,default in (('icon','game'),('background','game'),('music','none')):
        mode=selection.get('xmb_'+key+'_mode',default)
        if mode not in ('game','file','none'):_fail('XMB mode must be game, file, or none.')
        modes[key]=mode
    art_ids={key:selection.get('xmb_'+key+'_art','title') for key in ('icon','background')}
    from .media import valid_artwork_id,split_artwork_id,selected_image
    if any(not valid_artwork_id(value) for value in art_ids.values()):_fail('Choose valid game artwork from the catalog.')
    start=selection.get('xmb_music_start',0);seconds=selection.get('xmb_music_seconds',6)
    try:valid=math.isfinite(float(start)) and math.isfinite(float(seconds)) and 0<=float(start)<=7200 and 1<=float(seconds)<=10
    except (ValueError,TypeError):valid=False
    if modes['music']!='none' and not valid:_fail('Music start must be finite and duration 1..10 seconds.')
    root=_folder(data_root) if 'game' in modes.values() else None;entries=_entries(root) if root else {}
    track=selection.get('xmb_track','TITLE.ADX')
    if modes['music']=='game' and (not isinstance(track,str) or not re.fullmatch(r'[A-Za-z0-9_]+\.ADX',track,re.I) or track.upper() not in entries):_fail('Choose an existing catalog ADX track; paths are not accepted.')
    out=plain_path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):_fail('XMB output must be a new or empty directory.')
    out.mkdir(parents=True,exist_ok=True);result=dict(icon0=None,pic1=None,snd0=None);files={};inputs={};game_images={}
    for key,slot,size in (('icon','icon0',(144,80)),('background','pic1',(480,272))):
        _cancel(cancel);mode=modes[key]
        if mode=='none':continue
        if mode=='game':
            identity_id=art_ids[key]
            name,tile=split_artwork_id(identity_id)
            if name not in entries:_fail('Selected game artwork is missing: '+name)
            if identity_id not in game_images:
                path=entries[name];raw=_bounded(path,MAX_ART);boot=_boot(root) if identity_id=='title' else None
                game_image,_=selected_image(lambda n,z:raw if n==name else _bounded(entries[n],z),identity_id,boot)
                game_identity=dict(id=identity_id,source='SONICADV/'+name,layout='boot_animation' if boot is not None else 'selected_tile' if identity_id.startswith('pvm:') else 'image_file' if identity_id.startswith('img:') else 'first_tile',input=_raw_digest(raw))
                if boot is not None:game_identity['boot_sha256']=hashlib.sha256(boot).hexdigest()
                game_images[identity_id]=(game_image,game_identity)
            image,identity=game_images[identity_id]
        else:
            value=selection.get('xmb_'+key+'_file')
            if not value:_fail('Choose a picture file.')
            path=plain_path(value);raw=_bounded(path,32<<20)
            try:
                with Image.open(io.BytesIO(raw)) as original:
                    if not 0<original.width*original.height<=16000000:_fail('Picture exceeds 16 million pixels.')
                    original.load();oriented=ImageOps.exif_transpose(original)
                    image=Image.new('RGB',oriented.size);rgba=oriented.convert('RGBA');image.paste(rgba,mask=rgba.getchannel('A'))
            except (OSError,ValueError,Image.DecompressionBombError) as e:raise ConverterError('xmb_picture',f'Cannot read selected picture: {e}') from e
            identity=dict(input=_raw_digest(raw),source='user_file')
        if image.mode=='RGBA':
            flat=Image.new('RGB',image.size);flat.paste(image,mask=image.getchannel('A'));image=flat
        image=ImageOps.fit(image,size,method=Image.Resampling.LANCZOS);path=out/(slot.upper()+'.PNG')
        with path.open('xb') as stream:image.save(stream,format='PNG')
        result[slot]=path;files[path.name]=file_digest(path);inputs[slot]=identity
    if modes['music']!='none':
        _cancel(cancel)
        if modes['music']=='game':source=entries[track.upper()];_adx(_bounded(source,MAX_AUDIO)[:128])
        else:
            if not selection.get('xmb_music_file'):_fail('Choose an audio or ready AT3 file.')
            source=plain_path(selection['xmb_music_file'])
        raw,info=_sound(source,out,selection,ffmpeg,event,cancel);validate_at3(raw);p=out/'SND0.AT3'
        with p.open('xb') as f:f.write(raw)
        result['snd0']=p;files[p.name]=file_digest(p);inputs['snd0']=info
    result['files']=files;result['inputs']=inputs;result['fingerprint']=fingerprint(dict(format='DCRC_XMB_V1',modes=modes,inputs=inputs,files=files))
    return result
