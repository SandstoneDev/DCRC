"""Offline, lossy EC world-asset resolution cap; MIT, no bundled game data.

Only exact private policy matches in three named EC archives may change.
All references to those assets change; this is not universal actor preservation.
Output must be a new file. Other archive payloads remain byte-identical.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prs import prs_decompress

CARRIERS=frozenset(['BEACH01.PRS','BEACH02.PRS','BEACH03.PRS'])
def need(ok,why):
    if not ok:raise ValueError(why)
def align(n,a):return (n+a-1)//a*a
def digest(data):return hashlib.sha256(data).hexdigest()
def file_hash(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as f:
        while data:=f.read(1<<20):result.update(data)
    return result.hexdigest()
def read_policy(path):
    text=Path(path).read_text(encoding='ascii');need(len(text)<=1<<20,'policy too large')
    rows=text.splitlines();need(rows and rows[0]=='SA1_WORLD_TEXTURE_POLICY_V1','policy header')
    result={}
    for row in rows[1:]:
        fields=row.split();need(len(fields)==4 and re.fullmatch('[0-9a-fA-F]{8}',fields[0]),'policy row')
        g=int(fields[0],16);w=int(fields[1]);h=int(fields[2]);name=fields[3]
        need(g!=0xffffffff and g not in result and len(result)<2048,'duplicate/invalid GBIX')
        need(all(8<=n<=1024 and n&(n-1)==0 for n in [w,h]) and 0<len(name.encode('ascii'))<=28,'policy metadata')
        result[g]=(w,h,name)
    need(result,'empty policy');return result
def prs_literals(data):
    out=bytearray();control=-1;used=8
    def bit(b):
        nonlocal control,used
        if used==8:control=len(out);out.append(0);used=0
        out[control]|=b<<used;used+=1
    for b in data:bit(1);out.append(b)
    bit(0);bit(1);out+=b'\0\0';return bytes(out)
def pvr_info(raw):
    off=0;gbix=None
    if raw[:4]==b'GBIX':
        need(len(raw)>=12,'short GBIX');n=struct.unpack_from('<I',raw,4)[0]
        need(n>=4 and 8+n<=len(raw),'GBIX bounds');gbix=struct.unpack_from('<I',raw,8)[0];off=8+n
    need(off+16<=len(raw) and raw[off:off+4]==b'PVRT','PVR header')
    size,pix,fmt,_,w,h=struct.unpack_from('<IBBHHH',raw,off+4)
    need(size>=8 and off+8+size==len(raw),'PVR chunk bounds')
    need(all(1<=n<=1024 and n&(n-1)==0 for n in [w,h]),'PVR dimensions')
    return {'gbix':gbix,'pixfmt':pix,'datafmt':fmt,'w':w,'h':h,'off':off,'data':raw[off+16:]}
def twiddle(x,y,w,h):
    s=min(w,h);bits=s.bit_length()-1;block=(x if w>=h else y)>>bits
    x&=s-1;y&=s-1
    return (block<<(2*bits))+sum(((y>>b&1)<<(2*b))|((x>>b&1)<<(2*b+1)) for b in range(bits))
def decode565(raw):
    p=pvr_info(raw);w,h,d,f=p['w'],p['h'],p['data'],p['datafmt']
    need(p['pixfmt']==1,'only source RGB565 is supported')
    def word(i):
        need(i+2<=len(d),'truncated texture data');return struct.unpack_from('<H',d,i)[0]
    if f==9:
        need(len(d)>=2*w*h,'short rectangle');return list(struct.unpack_from('<'+'H'*(w*h),d))
    if f==2:
        base=2+2*(w*w-1)//3 if w==h else 0
        return [word(base+2*twiddle(x,y,w,h)) for y in range(h) for x in range(w)]
    need(f==4 and w>=2 and h>=2,'unsupported RGB565 source layout')
    base=2048+sum(1 if k<2 else 1<<(2*(k-1)) for k in range(w.bit_length()-1))
    need(len(d)>=base+w*h//4,'short VQ mip data');out=[0]*(w*h)
    for y in range(h//2):
        for x in range(w//2):
            code=d[base+twiddle(x,y,w//2,h//2)]
            for dx,dy,k in [(0,0,0),(0,1,1),(1,0,2),(1,1,3)]:out[(2*y+dy)*w+2*x+dx]=word(code*8+2*k)
    return out
def box565(data,w,h,cap):
    need(all(1<=n<=1024 and n&(n-1)==0 for n in [w,h,cap]) and len(data)==w*h,'filter bounds')
    nw,nh=w,h
    while max(nw,nh)>cap:nw=max(1,nw//2);nh=max(1,nh//2)
    sx,sy=w//nw,h//nh;out=[]
    for y in range(nh):
        for x in range(nw):
            pixels=[data[(y*sy+dy)*w+x*sx+dx] for dy in range(sy) for dx in range(sx)]
            out.append(sum(((sum((v>>shift)&mask for v in pixels)//len(pixels))<<shift) for shift,mask in [(11,31),(5,63),(0,31)]))
    return out,nw,nh
def rectangle(data,w,h):
    payload=struct.pack('<'+'H'*len(data),*data)
    return b'PVRT'+struct.pack('<IBBHHH',8+len(payload),1,9,0,w,h)+payload
def parse_pvm(data):
    need(len(data)>=12 and data[:4]==b'PVMH','PVM header')
    size,flags,count=struct.unpack_from('<IHH',data,4);start=8+size
    need(flags in (9,0x109) and 0<count<=2048,'unsupported PVM flags/count')
    need(start<=len(data) and start%32==0 and 12+34*count<=start,'PVM directory bounds/alignment')
    rows=[];cursor=start
    for i in range(count):
        index,name,g=struct.unpack_from('<H28sI',data,12+34*i)
        name=name.split(b'\0')[0].decode('ascii');need(name,'unnamed PVM entry')
        begin=cursor;need(cursor+16<=len(data),'short PVM image')
        if data[cursor:cursor+4]==b'GBIX':
            gn=struct.unpack_from('<I',data,cursor+4)[0];need(gn>=4 and cursor+8+gn+16<=len(data),'PVM GBIX bounds');cursor+=8+gn
        need(data[cursor:cursor+4]==b'PVRT','missing PVM texture')
        end=cursor+8+struct.unpack_from('<I',data,cursor+4)[0];need(end<=len(data),'PVM texture bounds')
        raw=data[begin:end];p=pvr_info(raw);need(p['gbix'] in (None,g),'PVM/PVR GBIX conflict')
        rows.append({**p,'gbix':g,'name':name,'id':index,'raw':raw,'start':begin});cursor=align(end,32)
    need(cursor<=len(data),'PVM terminal padding');return rows
def transform_pvm(data,policy,cap):
    rows=parse_pvm(data);out=bytearray(data[:rows[0]['start']]);changes=[]
    for p in rows:
        raw=p['raw'];key=(p['w'],p['h'],p['name'])
        if p['pixfmt']==1 and policy.get(p['gbix'])==key and max(p['w'],p['h'])>cap:
            image,w,h=box565(decode565(raw),p['w'],p['h'],cap)
            raw=raw[:p['off']]+rectangle(image,w,h)
            changes.append({'gbix':p['gbix'],'name':p['name'],'old':[p['w'],p['h']],'new':[w,h],
                            'source_chunk_sha256':digest(p['raw']),'output_chunk_sha256':digest(raw)})
        out+=raw;out+=bytes((-len(out))%32)
    if not changes:return data,[]
    need(len(parse_pvm(out))==len(rows),'rebuilt PVM');return bytes(out),changes
def read_pack(f):
    f.seek(0,2);size=f.tell();f.seek(0);head=f.read(16)
    need(len(head)==16 and head[:8]==b'SA1PAK\0\1','PAK header')
    n,b=struct.unpack_from('<II',head,8);need(0<n<65536 and b==40*n and 16+b<=size,'PAK directory bounds')
    directory=f.read(b);rows=[];last=align(16+b,2048)
    for i in range(n):
        raw,off,z=struct.unpack_from('<32sII',directory,40*i);name=raw.rstrip(b'\0').decode('ascii')
        need(name and '\0' not in name and '/' not in name and '\\' not in name and len(name)<=32,'PAK name')
        need(off%2048==0 and off>=last and off+z<=size,'PAK payload bounds/overlap')
        need(not rows or name>rows[-1][0],'PAK duplicate/unsorted names');rows.append((name,off,z));last=align(off+z,2048)
    return rows
def convert(source,output,policy,cap):
    source,output=Path(source),Path(output)
    if output.exists():raise FileExistsError(output)
    need(cap in (64,128),'cap must be64 or128')
    replacements={};changes={};hashes={}
    with source.open('rb') as f:
        rows=read_pack(f)
        for name,off,size in rows:
            if name not in CARRIERS:continue
            f.seek(off);raw=f.read(size)
            try:pvm=prs_decompress(raw)
            except (IndexError,ValueError) as e:raise ValueError('invalid source PRS '+name) from e
            new,changed=transform_pvm(pvm,policy,cap)
            if changed:
                encoded=prs_literals(new);need(prs_decompress(encoded)==new,'PRS encode roundtrip')
                replacements[name]=encoded;changes[name]=changed
        need(replacements,'no eligible textures changed')
        position=align(16+40*len(rows),2048);outrows=[]
        for name,off,size in rows:
            z=len(replacements[name]) if name in replacements else size;outrows.append((name,position,z));position=align(position+z,2048)
        created=False
        try:
            with output.open('xb') as dst:
                created=True
                dst.write(b'SA1PAK\0\1'+struct.pack('<II',len(rows),40*len(rows)))
                for name,off,size in outrows:dst.write(struct.pack('<32sII',name.encode('ascii'),off,size))
                for (name,off,size),(_,new_off,_) in zip(rows,outrows):
                    dst.write(bytes(new_off-dst.tell()));f.seek(off);src_hash=hashlib.sha256();out_hash=hashlib.sha256()
                    if name in replacements:
                        original=f.read(size);src_hash.update(original);out_hash.update(replacements[name]);dst.write(replacements[name])
                    else:
                        left=size
                        while left:
                            data=f.read(min(left,1<<20));need(data,'short source read');src_hash.update(data);out_hash.update(data);dst.write(data);left-=len(data)
                    hashes[name]={'source':src_hash.hexdigest(),'output':out_hash.hexdigest(),'changed':name in replacements}
                dst.write(bytes(position-dst.tell()))
        except BaseException:
            if created and output.exists():output.unlink()
            raise
    with output.open('rb') as f:
        for name,off,size in read_pack(f):
            f.seek(off);need(digest(f.read(size))==hashes[name]['output'],'output payload readback '+name)
    return {'quality':'lossy named EC world assets; all consumers of selected assets affected',
            'source_sha256':file_hash(source),'output_sha256':file_hash(output),'cap':cap,
            'changed_files':sorted(changes),'changes':changes,'payloads':hashes}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--policy',type=Path,required=True);parser.add_argument('--max-size',type=int,choices=[64,128],required=True)
    args=parser.parse_args();report=convert(args.source,args.output,read_policy(args.policy),args.max_size)
    print(json.dumps(report,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
