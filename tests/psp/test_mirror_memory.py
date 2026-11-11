#!/usr/bin/env python3
"""Actual PSP mirror/pool/build functions under synthetic allocation pressure.

No PSP SDK/game data; run with host cc (ASAN+UBSan). Part of sa1-psp (MIT).
"""
from pathlib import Path
import argparse,re,subprocess
R=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=R/'backend/psp/draw_gu.c');p.add_argument('--out',type=Path,default=R/'work/C86_mirror/memory');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
s=a.source.read_text()
def fn(name):
 m=re.search(r'(?m)^[^\n;{}]*\b'+name+r'\([^;{}]*\)\s*\{',s);assert m,name
 end=s.index('{',m.start())+1;n=1
 while n:n+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[m.start():end]
g=s[s.index('typedef struct {',s.index('#define TEX_LEVELS')):s.index('static gtex texs')]
prefix=r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include "backend/draw.h"
#include "backend/texpool.c"
#define TEX_MAX 16
#define TEX_LEVELS 8
'''+g+r'''
static gtex texs[TEX_MAX];
static struct{const uint8_t*mem;}bind_key[TEX_MAX];
static uint32_t bound_tex,free_later[TEX_MAX];static int list_open,ge_inflight,nfree_later,cur_valid;
static struct{unsigned texture_bytes,textures_alive;}stats;
static struct{unsigned mirror_fail,mirrors;}gs;
static int gu_debug,max_levels=8,tex_pool_on=1,in_replay=1;
static uint32_t tex_frame=1,tex_log_frame=~0u,tex_epoch,mirror_need,mirror_epoch;
static int deny_stage,deny_align,partition_ok=1,stage_live,part_live,align_calls,waits,checks,failures;
static unsigned temp_calls;static uint8_t golden[21760];static int golden_set;
static int chunks;static uint8_t chunk_mem[TEXPOOL_CHUNK];
static void sa1_log(const char*f,...){(void)f;}
static void pool_log(const char*f){(void)f;}
static void spring_trace(unsigned n,uint32_t a,uint32_t b,int c,int d,float e,float f,uint32_t g){(void)n;(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;}
static void ge_wait(void){waits++;}
static void sceKernelDcacheWritebackRange(const void*p,unsigned n){(void)p;(void)n;}
static void*chunk_alloc(void){if(chunks++)return NULL;return chunk_mem;}
static void move_block(int n,uint8_t*p){(void)n;(void)p;}
static void evict_block(int n){(void)n;abort();}
static uint32_t drop_block(int n){(void)n;abort();}
static const texpool_ops test_ops={chunk_alloc,move_block,evict_block,drop_block};
static void*host_align(size_t al,size_t n){align_calls++;return deny_align?NULL:aligned_alloc(al,(n+al-1)&~(al-1));}
static void*host_malloc(size_t n){if(deny_stage&&(n==8192||n==16388))return NULL;return malloc(n);}
static void*host_calloc(size_t n,size_t z){if(deny_stage&&(n*z==8192||n*z==16388))return NULL;return calloc(n,z);}
/* Shared temporary API stand-in; replaced by the public declaration's exact
 * spelling once integrated. Heap denial with independent fallback ownership. */
typedef struct{void*ptr;int32_t uid;}sa1_temp_block;
static void*sa1_plat_temp_alloc(uint32_t n,sa1_temp_block*t){temp_calls++;t->uid=-1;t->ptr=host_malloc(n);if(!t->ptr&&partition_ok){t->ptr=malloc(n);t->uid=1;part_live++;}if(t->ptr){memset(t->ptr,0xa5,n);stage_live++;}return t->ptr;}
static void sa1_plat_temp_free(sa1_temp_block*t){if(t->ptr){free(t->ptr);stage_live--;if(t->uid>=0)part_live--;}t->ptr=NULL;t->uid=-1;}
#define malloc host_malloc
#define calloc host_calloc
#define memalign host_align
'''
suffix=r'''
#undef malloc
#undef calloc
#undef memalign
#define CHECK(x)do{checks++;if(!(x)){failures++;printf("FAIL %d %s\n",__LINE__,#x);}}while(0)
static void setup(void){memset(texs,0,sizeof texs);memset(&stats,0,sizeof stats);memset(&gs,0,sizeof gs);texpool_init(&test_ops,0,1);texpool_set_frame(1);chunks=0;deny_stage=deny_align=0;partition_ok=1;stage_live=part_live=align_calls=waits=temp_calls=0;mirror_need=mirror_epoch=0;tex_frame=1;tex_log_frame=~0u;tex_pool_on=in_replay=1;max_levels=8;gu_debug=0;bound_tex=list_open=ge_inflight=nfree_later=cur_valid=0;}
static void cleanup(void){for(unsigned i=1;i<TEX_MAX;i++)if(texs[i].mem)tex_mem_free(&texs[i]);CHECK(stage_live==0&&part_live==0);}
static void base(void){uint16_t p[64*64];for(unsigned i=0;i<4096;i++)p[i]=(uint16_t)(i*37u+17u);CHECK(texture_build(1,64,64,DRAW_FMT_5650,(const uint8_t*)p,0,NULL,0,0)==0);stats.textures_alive++;stats.texture_bytes+=texs[1].bytes;}
static void verify(unsigned h){CHECK(h!=1&&h<TEX_MAX);if(h==1||h>=TEX_MAX)return;CHECK(texs[h].w==128&&texs[h].h==64);CHECK(texs[h].hidden&&texs[h].parent==1&&texs[1].mirror[1]==h);CHECK(texs[h].levels==4&&texs[h].total==sizeof golden);if(!golden_set){memcpy(golden,texs[h].mem,sizeof golden);golden_set=1;}CHECK(memcmp(golden,texs[h].mem,sizeof golden)==0);uint8_t lin[128*64*2];unswizzle(lin,texs[h].mem,256,64);for(unsigned y=0;y<64;y++)for(unsigned x=0;x<128;x++){unsigned sx=x<64?x:127-x;CHECK(((uint16_t*)lin)[y*128+x]==(uint16_t)((y*64+sx)*37u+17u));}}
int main(void){
 setup();base();unsigned h=mirror_variant(1,1,0);verify(h);CHECK(align_calls==0);cleanup();
 /* Actual PSP85 f3992: 8192/16388B libc staging requests both fail. */
 setup();base();deny_stage=1;h=mirror_variant(1,1,0);verify(h);CHECK(stage_live==0&&part_live==0);cleanup();
 setup();base();deny_stage=1;partition_ok=0;h=mirror_variant(1,1,0);CHECK(h==1&&texs[1].mirror[1]==0);unsigned calls=temp_calls;CHECK(mirror_variant(1,1,0)==1&&temp_calls==calls);CHECK(stage_live==0&&part_live==0);partition_ok=1;mirror_epoch++;h=mirror_variant(1,1,0);verify(h);cleanup();
 /* Actual f6554: no pool gap for21760B while smaller outside-pool
  * allocation remains available. No reclamation/GE wait during replay. */
 setup();base();uint8_t*dummy=NULL;unsigned used=texpool_get_stats()->used;CHECK(texpool_alloc(TEXPOOL_CHUNK-used-16,15,0,0,&dummy)>=0);int w=waits;h=mirror_variant(1,1,0);verify(h);if(h!=1){CHECK(texs[h].pblk==0);CHECK(texs[h].levels==4);}CHECK(align_calls==1&&waits==w);if(h!=1){list_open=1;draw_texture_destroy(1);CHECK(texs[1].dying&&texs[h].mem&&nfree_later==1&&free_later[0]==1&&waits==w);list_open=0;uint32_t ep=tex_epoch;texture_release(1);CHECK(!texs[1].mem&&!texs[h].mem&&tex_epoch>ep);CHECK(stats.textures_alive==0&&stats.texture_bytes==0);}cleanup();
 /* A full pool must still not send ordinary textures outside it. */
 setup();base();used=texpool_get_stats()->used;CHECK(texpool_alloc(TEXPOOL_CHUNK-used-16,15,0,0,&dummy)>=0);uint16_t p[128*64]={0};CHECK(texture_build(2,128,64,DRAW_FMT_5650,(uint8_t*)p,0,NULL,0,0)<0);CHECK(align_calls==0);cleanup();
 /* Both sources denied: bounded retry, no partial cached success. */
 setup();base();used=texpool_get_stats()->used;CHECK(texpool_alloc(TEXPOOL_CHUNK-used-16,15,0,0,&dummy)>=0);deny_align=1;h=mirror_variant(1,1,0);CHECK(h==1&&texs[1].mirror[1]==0&&mirror_need>0);unsigned n=align_calls;CHECK(mirror_variant(1,1,0)==1&&align_calls==(int)n);CHECK(!texs[2].mem&&!texs[2].pblk);deny_align=0;mirror_epoch++;h=mirror_variant(1,1,0);verify(h);cleanup();
 uint32_t hash=2166136261u;for(unsigned i=0;i<sizeof golden;i++)hash=(hash^golden[i])*16777619u;printf("mirror normal mip bytes fnv32=%08x\n",hash);
 printf("mirror_memory: %d checks, %d failures\n",checks,failures);return failures?1:0;
}
'''
names=['fmt_bits','row_bytes','px_get','px_set','unpack','pack','halve16','halve','swizzle','unswizzle']
if 'static uint8_t *mirror_heap_alloc(' in s:
 prefix+='\nstatic uint32_t mirror_heap_allocs,mirror_heap_fail;\n'
 names+=['mirror_heap_in_ram','mirror_heap_alloc']
 suffix=suffix.replace('printf("mirror_memory:',r'''
 CHECK(mirror_heap_in_ram(0x0bfff000u,4096));CHECK(!mirror_heap_in_ram(0x0bfff000u,4097));CHECK(!mirror_heap_in_ram(0x0c000000u,1));CHECK(!mirror_heap_in_ram(0,1));CHECK(!mirror_heap_in_ram(UINTPTR_MAX,64));
 setup();texs[1].hidden=1;texs[1].mem=chunk_mem;texs[1].total=TEXPOOL_CHUNK-16;unsigned ac=align_calls;CHECK(mirror_heap_alloc(32)==NULL&&align_calls==(int)ac);texs[1].mem=NULL;uint8_t*ok=mirror_heap_alloc(32);CHECK(ok!=NULL);free(ok);
 printf("mirror_memory:''')
names+=['tex_mem_alloc','tex_mem_free','texture_build','free_slot','texture_release','draw_texture_destroy','mirror_variant']
# Extract the real frame-start retry block; only the external room result is
# stubbed, so the policy under test cannot drift into a duplicate model.
block_start=s.index('    if (mirror_need &&',s.index('void draw_begin_frame('))
block_end=s.index('{',block_start)+1;depth=1
while depth:
 depth+=(s[block_end]=='{')-(s[block_end]=='}');block_end+=1
room_block=s[block_start:block_end]
prefix+='\nstatic uint32_t mirror_room_frame;static int mirror_room_ok,room_result,room_calls;static uint32_t room_bytes;\nstatic int retry_room(uint32_t n){room_calls++;room_bytes=n;return room_result;}\nstatic void retry_frame(void){tex_frame++;\n#define texpool_make_room retry_room\n'+room_block+'\n#undef texpool_make_room\n}\n'
suffix=suffix.replace(' uint32_t hash=2166136261u;',r'''
 /* The pool can remain full while an independent heap block becomes free.
  * Recheck the failed mirror on the existing 60-frame retry boundary. */
 setup();base();used=texpool_get_stats()->used;CHECK(texpool_alloc(TEXPOOL_CHUNK-used-16,15,0,0,&dummy)>=0);
 deny_align=1;h=mirror_variant(1,1,0);CHECK(h==1&&mirror_need>0);deny_align=0;
 mirror_room_frame=0;mirror_room_ok=room_result=room_calls=0;tex_frame=59;retry_frame();
 CHECK(room_calls==1&&room_bytes>0&&!mirror_room_ok&&mirror_need==0&&mirror_epoch==1);
 h=mirror_variant(1,1,0);verify(h);CHECK(texs[h].pblk==0);cleanup();
 /* Persistent denial stays bounded: no allocation storm or stale queued
  * byte accumulation between scheduled attempts. */
 setup();base();used=texpool_get_stats()->used;CHECK(texpool_alloc(TEXPOOL_CHUNK-used-16,15,0,0,&dummy)>=0);
 deny_align=1;CHECK(mirror_variant(1,1,0)==1);mirror_room_frame=0;mirror_room_ok=room_result=room_calls=0;
 tex_frame=59;retry_frame();CHECK(mirror_epoch==1&&mirror_need==0);CHECK(mirror_variant(1,1,0)==1);uint32_t queued=mirror_need;unsigned retry_allocs=align_calls;
 for(unsigned f=61;f<120;f++){retry_frame();CHECK(mirror_variant(1,1,0)==1);CHECK(align_calls==(int)retry_allocs&&mirror_need==queued&&room_calls==1);}
 retry_frame();CHECK(room_calls==2&&mirror_epoch==2&&mirror_need==0);CHECK(mirror_variant(1,1,0)==1);CHECK(align_calls==(int)retry_allocs+1);cleanup();
 uint32_t hash=2166136261u;''')
code=prefix+'\n'+'\n'.join(fn(n)for n in names)+'\n'+suffix
(a.out/'mirror_memory.c').write_text(code)
b=subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-deprecated-declarations','-fno-strict-aliasing','-fsanitize=address,undefined','-I'+str(R),str(a.out/'mirror_memory.c'),'-o',str(a.out/'mirror_memory')],capture_output=True,text=True);out=b.stdout+b.stderr;rc=b.returncode
if not rc:
 r=subprocess.run([str(a.out/'mirror_memory')],capture_output=True,text=True,timeout=30);out+=r.stdout+r.stderr;rc=r.returncode
out+=f'exit={rc}\n';(a.out/'mirror_memory.log').write_text(out);print(out,end='');raise SystemExit(rc)
