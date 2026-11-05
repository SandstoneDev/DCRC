#!/usr/bin/env python3
"""Actual standalone HLE + PSP temporary allocator with controlled endpoints.

Synthetic files and guest records only. Host checks do not prove GE pixels,
real PSP allocator behavior, or that a particular stale atlas displays88.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import tempfile


def extract(source, name):
    m = re.search(r"(?m)^[^\n;{}]*\b" + name + r"\([^;{}]*\)\s*\{", source)
    if not m:
        raise ValueError("missing actual function " + name)
    end = source.index("{", m.start()) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[m.start():end]


STUBS = r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <sys/mman.h>
/* Execute the production32-bit platform guard on this64-bit host while
 * retaining host pointers; owned mmap buffers use valid low addresses. */
#undef UINTPTR_MAX
#define UINTPTR_MAX UINT32_MAX
typedef struct {uint32_t r[16];} sh4_ctx;
typedef struct {void *ptr;int32_t uid;} sa1_temp_block;
typedef int SceUID;
#define PSP_SMEM_Low 0
static uint8_t ram[0x1000000];
static uint8_t *heap_mem,*kernel_mem;
static int heap_denied,kernel_denied,short_read,decode_fail,head_fail;
static unsigned checks,failures,heap_calls,heap_frees,kernel_calls,kernel_frees,reads,decodes;
static int heap_live,kernel_live,kernel_uid;
static uint32_t temp_heap,temp_partition,temp_fail,temp_active,temp_peak_active;
static uint32_t rd(uint32_t a){uint32_t v;memcpy(&v,ram+(a&0xffffffu),4);return v;}
static void wr(uint32_t a,uint32_t v){memcpy(ram+(a&0xffffffu),&v,4);}
#define CHECK(q) do{checks++;if(!(q)){failures++;printf("FAIL %d %s\n",__LINE__,#q);}}while(0)
#define hle_rd32(a) rd(a)
#define hle_wr32(a,v) wr(a,v)
#define hle_rd8(a) (ram[(a)&0xffffffu])
#define hle_in_ram(a) (((a)&0x1fffffffu)>=0xc000000u && ((a)&0x1fffffffu)<0xd000000u)
#define hle_ptr(a) (ram+((a)&0xffffffu))
#define ARG0 (c->r[4])
#define RET(v) (c->r[0]=(uint32_t)(v))
#define HLE_ENTER(a,b) ((void)0)
#define ATTR_GLOBALINDEX 0x80000000u
#define ATTR_MEMORY 0x40000000u
#define ATTR_FRAMEBUFFER 0x20000000u
#define ATTR_LOADED 0x01000000u
#define ATTR_TEXINFO 0x00800000u
#define SA1_RAM_SIZE 0x1000000u
#define SA1_RAM_EXTRA 0u
#define SA1_RAM_MASK 0xffffffu
#define MAGIC_GINDEX 0x58494247u
#define MAGIC_TEXTURE 0x54525650u
#define G_TEX_FAILIDX 0x8c88f7a8u
#define NJ_CUR_TEXLIST 0x8c673480u
#define NJ_CUR_GINDEX 0x8c673484u
#define NJ_CUR_BANK 0x8c673488u
static void sa1_log(const char *f,...){(void)f;}
static void shinobi_gdfs_path(char *p,unsigned n,const char *s){snprintf(p,n,"SONICADV/%s",s);}
static int sa1_plat_file_size(const char *p,uint32_t *n){(void)p;*n=32800;return 0;}
static int sa1_plat_file_read(const char *p,uint32_t o,void *b,uint32_t n){
    (void)p;CHECK(o==0&&n==32800);CHECK(heap_live||kernel_live);
    if(kernel_live){CHECK(((uintptr_t)b&63u)==0);CHECK((uint8_t*)b>=kernel_mem+17&&(uint8_t*)b+n<=kernel_mem+17+32800+63);}
    else CHECK(b==heap_mem);
    reads++;memset(b,0,n);
    return short_read?(int)n-1:(int)n;
}
static void *pressure_malloc(size_t n){
    heap_calls++;CHECK(n==32800);CHECK(!heap_live);
    if(heap_denied)return NULL;heap_live=1;return heap_mem;
}
static void pressure_free(void *p){CHECK(p==heap_mem&&heap_live);heap_live=0;heap_frees++;}
static SceUID sceKernelAllocPartitionMemory(int partition,const char *name,int type,uint32_t n,void *hint){
    CHECK(partition==2&&strcmp(name,"sa1_temp")==0&&type==PSP_SMEM_Low&&hint==NULL);
    CHECK(n==32800+63);CHECK(!kernel_live);kernel_calls++;
    if(kernel_denied)return -1;kernel_live=1;kernel_uid=100+(int)kernel_calls;return kernel_uid;
}
static void *sceKernelGetBlockHeadAddr(SceUID id){CHECK(id==kernel_uid&&kernel_live);return head_fail?NULL:kernel_mem+17;}
static int sceKernelFreePartitionMemory(SceUID id){CHECK(id==kernel_uid&&kernel_live);kernel_live=0;kernel_frees++;return 0;}
static uint32_t entry_addr(uint32_t i){return 0x8c200000u+68u*i;}
static int load_entry(const void *p,uint32_t n,uint32_t g,const char *s){
    (void)p;(void)g;(void)s;CHECK(n==32800);CHECK(heap_live||kernel_live);
    int i=(int)decodes++;return decode_fail?-1:i;
}
static int load_entry_ex(const void *p,uint32_t n,uint32_t g,const char *s,uint32_t w,uint32_t h,uint32_t f){
    (void)p;(void)n;(void)g;(void)s;(void)w;(void)h;(void)f;return -1;
}
'''

CASES = r'''
static void run(int heap_fail,int kernel_fail,int read_short,int decode_bad,int no_head){
    memset(ram,0,sizeof ram);heap_calls=heap_frees=kernel_calls=kernel_frees=reads=decodes=0;
    heap_live=kernel_live=0;heap_denied=heap_fail;kernel_denied=kernel_fail;short_read=read_short;decode_fail=decode_bad;head_fail=no_head;
    const uint32_t tl=0x8c1c5458u,names=0x8c310000u,ctx=0x8c320000u;
    const char *str[2]={"hyoji_emblem0","hyoji_emblem1"};
    wr(tl,names);wr(tl+4,2);
    for(unsigned i=0;i<2;i++){
        uint32_t p=0x8c330000u+32u*i;strcpy((char*)hle_ptr(p),str[i]);wr(names+12u*i,p);
        uint32_t e=entry_addr(i);wr(e,13400000u+i);wr(e+4,0);wr(e+8,0x24);wr(e+12,0x1400100u+i);
    }
    int allocation_bad=heap_fail&&(kernel_fail||no_head),failed=allocation_bad||read_short||decode_bad;
    sh4_ctx c={0};c.r[4]=tl;sdk_8c608c82(&c);
    CHECK(c.r[0]==(failed?UINT32_MAX:1u));CHECK(heap_calls==2);
    CHECK(reads==(allocation_bad?0u:2u));CHECK(decodes==((allocation_bad||read_short)?0u:2u));
    CHECK(heap_frees==(heap_fail?0u:2u));CHECK(kernel_calls==(heap_fail?2u:0u));
    CHECK(kernel_frees==((heap_fail&&!kernel_fail)?2u:0u));CHECK(!heap_live&&!kernel_live);CHECK(temp_active==0);
    c.r[4]=tl;sdk_8c608ccc(&c);CHECK(c.r[0]==1);
    wr(ctx,0x12345678u);wr(ctx+4,0x01000222u); /* Controlled preceding atlas, not a captured88texture. */
    int selected=select_texture(0,ctx,ctx+4);
    CHECK(selected==(failed?-1:1));CHECK(rd(ctx+4)==(failed?0x01000222u:0x1400100u));
    CHECK(rd(names+8)==(failed?0:entry_addr(0)));CHECK(rd(names+20)==(failed?0:entry_addr(1)));
}
int main(void){
    /* Model PSP-valid low user addresses so the actual allocator's range
     * checks, if present, are exercised without changing production code. */
    heap_mem=mmap((void*)0x09000000,65536,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    kernel_mem=mmap((void*)0x0a000000,65536,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    if(heap_mem==MAP_FAILED||kernel_mem==MAP_FAILED){perror("mmap test allocation");return 2;}
    CHECK(temp_heap_fits(0x0bff8000u,0x8000u));CHECK(!temp_heap_fits(0x0bff8000u,0x8001u));
    CHECK(!temp_heap_fits(0x0c000000u,1));CHECK(!temp_heap_fits(UINT32_MAX,32800));
    run(0,0,0,0,0); /* libc normal */
    run(1,0,0,0,0); /* heap denied, real API uses kernel-owned block */
    run(1,1,0,0,0); /* both denied: failed names0, previous TCW kept */
    run(0,0,1,0,0);run(1,0,1,0,0); /* short reads never reach decoder */
    run(0,0,0,1,0);run(1,0,0,1,0); /* decode failure still releases scratch */
    run(1,0,0,0,1); /* kernel head lookup fails: exactUID released */
    sa1_temp_block empty={NULL,-1};sa1_plat_temp_free(&empty);sa1_plat_temp_free(NULL);CHECK(temp_active==0);
    heap_denied=kernel_denied=head_fail=0;
    CHECK(sa1_plat_temp_alloc(32800,&empty)==heap_mem);CHECK(temp_active==1);
    unsigned before_calls=heap_calls,before_frees=heap_frees;
    CHECK(sa1_plat_temp_alloc(32800,&empty)==NULL);CHECK(heap_calls==before_calls);
    sa1_plat_temp_free(&empty);CHECK(empty.ptr==NULL&&empty.uid==-1&&temp_active==0);
    sa1_plat_temp_free(&empty);CHECK(heap_frees==before_frees+1);
    munmap(heap_mem,65536);munmap(kernel_mem,65536);
    printf("standalone_texture_pressure: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    texture_path = args.source or root / "hle/ninja/texture.c"
    texture = texture_path.read_text()
    platform_path = root / "backend/psp/platform_psp.c"
    platform = platform_path.read_text()
    kamui = (root / "hle/ninja/kamui.c").read_text()
    code = STUBS + '\n#define malloc pressure_malloc\n#define free pressure_free\n'
    code += '\n'.join(extract(platform, n) for n in ['temp_heap_fits', 'sa1_plat_temp_alloc', 'sa1_plat_temp_free'])
    code += '\n' + '\n'.join(extract(texture, n) for n in ['texname_string', 'load_texname', 'sdk_8c608c82'])
    code += '\n#undef malloc\n#undef free\n'
    code += '\n'.join(extract(kamui, n) for n in ['sdk_8c608ccc', 'select_texture']) + CASES
    temporary = tempfile.TemporaryDirectory() if args.out is None else None
    out = Path(temporary.name) if temporary else args.out
    out.mkdir(parents=True, exist_ok=True)
    cfile = out / "actual_standalone_texture_pressure.c"
    cfile.write_text(code)
    exe = out / "actual_standalone_texture_pressure"
    build = subprocess.run(['cc', '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror',
                            '-Wno-misleading-indentation', '-fno-strict-aliasing',
                            '-fsanitize=address,undefined', str(cfile), '-o', str(exe)],
                           capture_output=True, text=True)
    if build.returncode:
        raise SystemExit(build.stdout + build.stderr)
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    output = result.stdout + result.stderr
    (out / 'standalone_texture_pressure.log').write_text(output)
    (out / 'SOURCE.json').write_text(json.dumps({
        'texture': str(texture_path), 'texture_sha256': hashlib.sha256(texture.encode()).hexdigest(),
        'platform': str(platform_path), 'platform_sha256': hashlib.sha256(platform.encode()).hexdigest(),
        'scope': 'Actual standalone loader, PSP temporary allocator and texture selection; controlled OS/file/decode endpoints.',
        'exit': result.returncode
    }, indent=2) + '\n')
    print(output, end='')
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
