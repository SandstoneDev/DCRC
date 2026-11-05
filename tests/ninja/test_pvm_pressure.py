#!/usr/bin/env python3
"""Compile actual PVM HLE with controlled endpoint/allocator stubs (host only).

Synthetic archives contain no game data. This proves header parsing/remapping,
not PRS decompression, image decoding, guest loading, GE state, or PSP pixels.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import tempfile


def extract(source, name):
    match = re.search(r"(?m)^[^\n;{}]*\b" + name + r"\([^;{}]*\)\s*\{", source)
    if not match:
        raise ValueError("missing actual function " + name)
    end = source.index("{", match.start()) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


STUBS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <limits.h>
typedef struct { uint32_t r[16]; } sh4_ctx;
/* Extra physical guard bytes let old malformed-table controls finish and
 * report logical-bound violations, rather than aborting the whole suite. */
static uint8_t ram[0x1000000u + 128u];
static uint64_t decode_us, create_us;
static uint32_t total_bytes;
static int ntex, deny_heap, alloc_calls, loads, log_calls, errors;
static unsigned checks, failures;
static uint32_t loaded_gbix[128], loaded_size[128];
static char loaded_name[128][40];
static uint32_t data_addr, tl_addr=0x8c300000u, names_addr=0x8c310000u;
static unsigned header_padding;
static uint32_t rd32le(const void *p) { uint32_t v; memcpy(&v,p,4); return v; }
static uint16_t rd16le(const void *p) { uint16_t v; memcpy(&v,p,2); return v; }
static uint32_t rd(uint32_t a) { return rd32le(ram+(a&0xffffffu)); }
static void wr(uint32_t a,uint32_t v) { memcpy(ram+(a&0xffffffu),&v,4); }
static void put16(uint32_t a,uint16_t v) { memcpy(ram+(a&0xffffffu),&v,2); }
static void *fault_calloc(size_t n,size_t s) { alloc_calls++; return deny_heap?NULL:calloc(n,s); }
static void *fault_malloc(size_t n) { alloc_calls++; return deny_heap?NULL:malloc(n); }
#define ARG0 (c->r[4])
#define ARG1 (c->r[5])
#define RET(v) (c->r[0]=(uint32_t)(v))
#define HLE_ENTER(a,b) ((void)0)
#define SA1_RAM_SIZE 0x1000000u
#define SA1_RAM_EXTRA 0u
#define SA1_RAM_MASK 0xffffffu
#define hle_ptr(a) (ram+((a)&0xffffffu))
#define hle_in_ram(a) (((a)&0x1fffffffu)>=0xc000000u && ((a)&0x1fffffffu)<0xd000000u)
#define hle_rd32(a) rd(a)
#define hle_wr32(a,v) wr(a,v)
#define MAGIC_ARCHIVE 0x484d5650u
#define MAGIC_GINDEX 0x58494247u
#define MAGIC_TEXTURE 0x54525650u
#define G_TEX_ERR 0x8c100000u
#define ATTR_GLOBALINDEX 0x80000000u
#define CHECK(q) do { checks++; if (!(q)) { failures++; printf("FAIL %d: %s\n",__LINE__,#q); } } while(0)
static uint64_t sa1_plat_time_us(void) { return 0; }
static const char *shinobi_last_opened_file(void) { return "synthetic.PRS"; }
static uint32_t entry_addr(uint32_t i) { return 0x8c200000u+68u*i; }
static void sa1_log(const char *s,...) { (void)s; log_calls++; }
static void texname_string(uint32_t a,char *out,unsigned n) {
    uint32_t p=rd(a); unsigned i=0;
    if (!hle_in_ram(p)) { if(n)*out=0; return; }
    for (;i+1<n && i<28;i++) { out[i]=(char)ram[(p+i)&0xffffffu]; if(!out[i])break; }
    out[i]=0;
}
static int load_entry(const void *p,uint32_t size,uint32_t gbix,const char *name) {
    (void)p; CHECK(loads<128); if(loads>=128)return -1;
    loaded_gbix[loads]=gbix; loaded_size[loads]=size;
    snprintf(loaded_name[loads],sizeof loaded_name[loads],"%s",name);
    return loads++;
}
'''

CASES = r'''
static void reset(int heap) {
    memset(ram,0,sizeof ram); memset(loaded_name,0,sizeof loaded_name);
    loads=log_calls=errors=alloc_calls=0; deny_heap=heap; data_addr=0xcd00000u;
    wr(tl_addr,names_addr); wr(tl_addr+4,86);
    for (unsigned i=0;i<100;i++) {
        uint32_t str=0x8c320000u+32u*i;
        snprintf((char*)hle_ptr(str),32,"name%03u",i);
        wr(names_addr+12u*i,str); wr(names_addr+12u*i+4,0x81005000u+i);
        wr(names_addr+12u*i+8,entry_addr(900u+i));
    }
}
static uint32_t archive(unsigned n,unsigned flags) {
    unsigned stride=2u+((flags&8u)?28u:0u)+((flags&4u)?2u:0u)+((flags&2u)?2u:0u)+((flags&1u)?4u:0u);
    uint32_t end=12u+n*stride+header_padding, q=12;
    wr(data_addr,MAGIC_ARCHIVE); wr(data_addr+4,end-8u);
    put16(data_addr+8,(uint16_t)flags); put16(data_addr+10,(uint16_t)n);
    for(unsigned i=0;i<n;i++) {
        put16(data_addr+q,(uint16_t)(1000u+i)); q+=2;
        if(flags&8u) { snprintf((char*)hle_ptr(data_addr+q),28,"name%03u",i);q+=28; }
        if(flags&4u) {put16(data_addr+q,0xabcd);q+=2;}
        if(flags&2u) {put16(data_addr+q,0x1234);q+=2;}
        if(flags&1u) {wr(data_addr+q,17179u+i);q+=4;}
        uint32_t chunk=data_addr+end+16u*i;
        wr(chunk,MAGIC_TEXTURE);wr(chunk+4,8);wr(chunk+8,0x11223344u+i);
    }
    CHECK(q+header_padding==end); return end;
}
static uint32_t invoke(void) {
    sh4_ctx c={0};c.r[4]=data_addr;c.r[5]=tl_addr;sdk_8c608134(&c);return c.r[0];
}
static void valid(unsigned n,unsigned flags,int heap,int permute,int missing_names) {
    unsigned before=failures;
    reset(heap);wr(tl_addr+4,n);archive(n,flags);
    if(permute) for(unsigned i=0;i<n;i++)wr(names_addr+12u*i,0x8c320000u+32u*(n-1u-i));
    if(missing_names)wr(tl_addr,0);
    CHECK(invoke()==1); CHECK(loads==(int)n); CHECK(rd(tl_addr+4)==n);
    if(heap)CHECK(alloc_calls==0); /* No header heap dependency, even for count0. */
    for(unsigned i=0;i<n;i++) {
        CHECK(loaded_gbix[i]==((flags&1u)?17179u+i:UINT32_MAX));
        CHECK(loaded_size[i]==16);
        char name[40];snprintf(name,sizeof name,(flags&8u)?"name%03u":"pvm entry",i);
        CHECK(strcmp(loaded_name[i],name)==0);
        if(!missing_names) {
            unsigned slot=permute&&(flags&8u)?n-1u-i:i;
            CHECK(rd(names_addr+12u*slot+8)==entry_addr(i));
            CHECK(rd(names_addr+12u*slot+4)==((flags&1u)?0x81000000u+17179u+i:0x81005000u+slot));
        }
    }
    if(failures!=before)printf("case n=%u flags=%x heap=%d permute=%d no_names=%d padding=%u: %u failures\n",n,flags,heap,permute,missing_names,header_padding,failures-before);
}
static void malformed(unsigned kind) {
    reset(0);archive(1,15);uint32_t old=rd(names_addr+8),oldattr=rd(names_addr+4);
    if(kind==0)wr(data_addr+4,0);           /* header end before12 */
    if(kind==1)wr(data_addr+4,8);           /* entry table extends beyond declared header */
    if(kind==2)wr(data_addr+4,0x400000u);   /* header extends beyond remaining guest RAM */
    if(kind==3)wr(data_addr+4,UINT32_MAX);  /* 8+hsize overflow */
    if(kind==4) {                         /* valid header, incomplete record near RAM end */
        data_addr=0xcffffe0u;wr(data_addr,MAGIC_ARCHIVE);wr(data_addr+4,24);
        put16(data_addr+8,15);put16(data_addr+10,1);
    }
    CHECK(invoke()==UINT32_MAX);CHECK(loads==0);
    CHECK(rd(names_addr+8)==old);CHECK(rd(names_addr+4)==oldattr);CHECK(rd(tl_addr+4)==86);
}
int main(void) {
    /*86 mirrors BEACH02 record count, with synthetic content only. */
    valid(86,0x109,1,0,0);valid(86,0x109,0,0,0);
    for(unsigned flags=0;flags<16;flags++) {
        valid(3,flags,0,0,0); valid(3,flags,1,0,0);
    }
    valid(3,15,1,1,0);valid(3,8,1,1,0); /* exact by-name remap */
    valid(3,1,1,0,1);valid(3,9,1,0,1); /* no names: loads without writes */
    valid(0,0,1,0,0); valid(0,15,0,0,0);
    header_padding=8;valid(86,0x109,1,0,0);header_padding=0;
    for(unsigned k=0;k<5;k++)malformed(k);
    printf("pvm_pressure: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    source_path = args.source or root / "hle/ninja/texture.c"
    source = source_path.read_text()
    helpers = re.findall(r"(?m)^static[^\n;{}]*\b(pvm_\w+)\([^;{}]*\)\s*\{", source)
    actual = "\n".join(extract(source, n) for n in helpers + ["sdk_8c608134"])
    # No unreferenced-stub errors when the allocation dependency is removed.
    code = STUBS + '\n#define calloc fault_calloc\n#define malloc fault_malloc\n'
    code += actual + '\n#undef calloc\n#undef malloc\n' + CASES
    temporary = tempfile.TemporaryDirectory() if args.out is None else None
    out = Path(temporary.name) if temporary else args.out
    out.mkdir(parents=True, exist_ok=True)
    cfile = out / "actual_pvm_pressure.c"
    cfile.write_text(code)
    exe = out / "actual_pvm_pressure"
    command = ["cc", "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
               "-Wno-unused-function", "-fno-strict-aliasing", "-fsanitize=address,undefined",
               str(cfile), "-o", str(exe)]
    build = subprocess.run(command, capture_output=True, text=True)
    if build.returncode:
        raise SystemExit(build.stdout + build.stderr)
    run = subprocess.run([str(exe)], capture_output=True, text=True)
    output = run.stdout + run.stderr
    (out / "pvm_pressure.log").write_text(output)
    (out / "SOURCE.json").write_text(json.dumps({
        "source": str(source_path), "sha256": hashlib.sha256(source.encode()).hexdigest(),
        "function": "sdk_8c608134", "helpers": helpers, "exit": run.returncode,
        "scope": "Actual parser; controlled load_entry, memory, allocator and platform endpoints. Synthetic data only."
    }, indent=2) + "\n")
    print(output, end="")
    raise SystemExit(run.returncode)


if __name__ == "__main__":
    main()
