#!/usr/bin/env python3
"""Actual PSP mirror retry/model-LRU code against synthetic host stubs.

Run with host cc (ASAN/UBSan), e.g. WSL python3. No PSP SDK or game data.
--source can select a frozen draw_gu.c; outputs stay under ignored work/.
Part of sa1-psp (MIT).
"""
from pathlib import Path
import argparse
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, default=ROOT / "backend/psp/draw_gu.c")
parser.add_argument("--out", type=Path, default=ROOT / "work/C84_texture/actual")
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
source = args.source.read_text()

def function(name):
    start = source.index("static uint32_t " + name + "(")
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]

retry_prefix = r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
typedef struct { int w,h,fmt,clut_fmt; uint8_t *mem; uint32_t off[8],mirror[4],mfail,parent,bytes; uint16_t *clut; int hidden,pk; } gtex;
static gtex texs[8]; static struct { unsigned texture_bytes; } stats;
static uint32_t mirror_epoch,mirror_need,tex_frame;
static int gu_debug,max_levels=8,tex_pool_on=1;
static struct { unsigned mirror_fail,mirrors; } gs;
static unsigned allocations; static int fail_at,slot_ok,build_fail;
static void *test_malloc(size_t n){allocations++;return allocations==(unsigned)fail_at?NULL:malloc(n);}
static __attribute__((unused)) void *test_calloc(size_t n,size_t s){allocations++;return allocations==(unsigned)fail_at?NULL:calloc(n,s);}
typedef struct { void *ptr; int32_t uid; } sa1_temp_block;
static __attribute__((unused)) void *sa1_plat_temp_alloc(uint32_t n,sa1_temp_block*b){b->ptr=test_malloc(n);b->uid=-1;return b->ptr;}
static __attribute__((unused)) void sa1_plat_temp_free(sa1_temp_block*b){free(b->ptr);b->ptr=NULL;b->uid=-1;}
static int fmt_bits(int f){(void)f;return 16;}
static uint32_t row_bytes(int w,int bits){return (uint32_t)w*(uint32_t)bits/8;}
static int free_slot(void){return slot_ok?2:0;}
static void sa1_log(const char *s,...){(void)s;}
static void unswizzle(uint8_t *d,const uint8_t*s,uint32_t rb,uint32_t rows){memcpy(d,s,rb*rows);}
static unsigned px_get(const uint8_t*b,uint32_t rb,int bits,int x,int y){(void)bits;uint16_t n;memcpy(&n,b+y*rb+x*2,2);return n;}
static void px_set(uint8_t*b,uint32_t rb,int bits,int x,int y,unsigned v){(void)bits;uint16_t n=(uint16_t)v;memcpy(b+y*rb+x*2,&n,2);}
static int texture_build(int slot,int w,int h,int f,const uint8_t*p,int cf,uint16_t*cl,int own,int cache){(void)p;(void)f;(void)cf;(void)cl;(void)own;(void)cache;if(build_fail)return -1;texs[slot].w=w;texs[slot].h=h;return 0;}
static uint32_t texpool_psp_bytes(int w,int h,int bits,int n,void*p){(void)n;(void)p;return (uint32_t)w*(uint32_t)h*(uint32_t)bits/8;}
#define malloc test_malloc
#define calloc test_calloc
'''
retry_suffix = r'''
#undef malloc
#undef calloc
static unsigned failures,checks;
#define CHECK(x) do{checks++;if(!(x)){failures++;printf("FAIL line %d: %s\n",__LINE__,#x);}}while(0)
static void setup(void){static uint8_t pixels[512*512*2];memset(texs,0,sizeof texs);texs[1].mem=pixels;texs[1].w=texs[1].h=16;mirror_epoch=mirror_need=0;tex_frame=1;fail_at=build_fail=0;slot_ok=1;allocations=0;tex_pool_on=1;}
int main(void){
 setup();CHECK(mirror_variant(1,1,0)==2);unsigned n=allocations;CHECK(mirror_variant(1,1,0)==2);CHECK(allocations==n); /* cached success */
 for(int failure=0;failure<4;failure++){
  setup();if(failure<2)fail_at=failure+1;else if(failure==2)slot_ok=0;else build_fail=1;
  CHECK(mirror_variant(1,1,0)==1);CHECK(texs[1].mirror[1]==0);CHECK(mirror_need>0);
  n=allocations;uint32_t need=mirror_need;
  CHECK(mirror_variant(1,1,0)==1);CHECK(allocations==n);CHECK(mirror_need==need); /* no repeated allocation/queue in same epoch */
  fail_at=build_fail=0;slot_ok=1;mirror_epoch++;
  CHECK(mirror_variant(1,1,0)==2);CHECK(texs[1].hidden==0 && texs[2].hidden && texs[2].parent==1);
 }
 for(int failure=0;failure<2;failure++){
  setup();tex_pool_on=0;if(failure==0)fail_at=1;else build_fail=1;
  CHECK(mirror_variant(1,1,0)==1);CHECK(texs[1].mirror[1]==0);CHECK(mirror_need==0);
  n=allocations;CHECK(mirror_variant(1,1,0)==1);CHECK(allocations==n);
  fail_at=build_fail=0;tex_frame++;CHECK(mirror_variant(1,1,0)==2); /* no-pool retry is once per frame */
 }
 setup();texs[1].w=512;CHECK(mirror_variant(1,1,0)==1);CHECK(allocations==0);mirror_epoch++;CHECK(mirror_variant(1,1,0)==1);CHECK(allocations==0); /* unsupported size stays cached */
 printf("mirror_retry: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
'''

loop_start = source.index("    for (int s = 0; s < g->nsets; s++) {      /* the pool's LRU")
loop_end = source.index("\n    gms.draws++", loop_start)
pool_path = (ROOT / "backend/texpool.c").as_posix()
lru_prefix = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
'''+ '#include "'+pool_path+'"\n'+r'''
#define TEX_MAX 8
typedef struct { uint32_t texture; int flip_u,flip_v,clamp_u,clamp_v; } draw_state;
typedef struct { draw_state st; } gmset;
typedef struct { gmset *sets; int nsets; } gmodel;
static struct { int pblk; uint32_t mirror[4]; } texs[TEX_MAX];
static uint8_t chunk_memory[TEXPOOL_CHUNK];static int chunk_used,evicted;
static void *alloc_chunk(void){if(chunk_used)return NULL;chunk_used=1;return chunk_memory;}
static void moved(int h,uint8_t*p){(void)h;(void)p;}
static void evict(int h){evicted=h;texpool_free(texs[h].pblk-1);texs[h].pblk=0;}
static uint32_t drop(int h){(void)h;return 0;}
static void draw_model_touch(gmodel *g){
'''
lru_suffix = r'''
}
static unsigned failures,checks;
#define CHECK(x) do{checks++;if(!(x)){failures++;printf("FAIL line %d: %s\n",__LINE__,#x);}}while(0)
static void scenario(int fu,int fv,int cu,int cv,uint32_t resolved,int protect){
 memset(texs,0,sizeof texs);chunk_used=evicted=0;
 texpool_ops callbacks={alloc_chunk,moved,evict,drop};texpool_init(&callbacks,0,1);texpool_set_frame(1);uint8_t*p;
 int base=texpool_alloc(128u<<10,1,0,0,&p),mirror=texpool_alloc(256u<<10,2,1,0,&p),rest=texpool_alloc(640u<<10,3,0,0,&p);
 CHECK(base>=0&&mirror>=0&&rest>=0);texs[1].pblk=base+1;texs[2].pblk=mirror+1;
 for(unsigned i=1;i<4;i++)texs[1].mirror[i]=resolved;
 gmset set={{1,fu,fv,cu,cv}};gmodel model={&set,1};
 for(unsigned frame=2;frame<=100;frame++){texpool_set_frame(frame);draw_model_touch(&model);} /* retained CALL samples resolved mirror on each draw */
 CHECK(blk[base].last==100);texpool_set_frame(101);int request=texpool_alloc(128u<<10,4,1,1,&p);
 CHECK(evicted==(protect?0:2));CHECK(texs[2].pblk==(protect?mirror+1:0));CHECK(protect?request<0:request>=0);
}
int main(void){
 scenario(1,0,0,0,2,1);scenario(0,1,0,0,2,1);scenario(1,1,0,0,2,1);
 scenario(1,0,1,0,2,0);scenario(0,1,0,1,2,0);scenario(0,0,0,0,2,0);
 scenario(1,0,0,0,0,0);scenario(1,0,0,0,TEX_MAX,0);scenario(1,0,0,0,1,0);
 printf("persistent_mirror_lru: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
'''

trace_prefix = ""
trace_code = ""
if "/* Opt-in round-spring" in source:
    trace_prefix = r'''
static uint32_t hle_frame_count(void){return 0;}
static const char *texture_name(uint32_t h){(void)h;return "other";}
static char *mirror_test_getenv(const char *k){(void)k;return NULL;}
#define getenv mirror_test_getenv
'''
    trace_code = source[source.index("/* Opt-in round-spring"):source.index("/* The mirrored variant of slot")]

failed = False
for name, code in (("mirror_retry", retry_prefix + trace_prefix + trace_code + function("mirror_variant") + retry_suffix),
                   ("persistent_mirror_lru", lru_prefix + source[loop_start:loop_end] + lru_suffix)):
    cfile, exe = args.out / (name + ".c"), args.out / name
    cfile.write_text(code)
    build = subprocess.run(["cc", "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", str(cfile), "-o", str(exe)], capture_output=True, text=True)
    output = build.stdout + build.stderr
    rc = build.returncode
    if rc == 0:
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        output += run.stdout + run.stderr
        rc = run.returncode
    output += f"exit={rc}\n"
    (args.out / (name + ".log")).write_text(output)
    print(output, end="")
    failed |= rc != 0
raise SystemExit(1 if failed else 0)
