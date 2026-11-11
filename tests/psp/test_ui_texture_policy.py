#!/usr/bin/env python3
"""Actual bind/pool code, synthetic live textures; no PSP/game input. MIT."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def extract(source,name):
    m=re.search(r'(?m)^[^\n;{}]*\b'+name+r'\([^;{}]*\)\s*\{',source)
    if not m:return ''
    end=source.index('{',m.start())+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[m.start():end]


PREFIX=r'''
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "DRAW_HEADER"
#include "POOL_HEADER"
#define TEX_MAX 2048
#define TEX_LEVELS 8
GTEX
static gtex texs[TEX_MAX];
static struct {uint32_t texture_bytes;}stats;
typedef struct {uint32_t promoted,cold_lost,drop_refused;}detail_stats;
static detail_stats ui_stats,sky_stats;
static uint32_t bound_tex,tex_epoch;static int tex_flush_pending,gu_debug,in_model_build,replay_v2=16;
static float tex_su=-1,tex_sv=-1;
enum {SH_WRAP,SH_FILTER,SH_TFUNC,SH_BLENDF,SH_N};
typedef struct {int v[SH_N];uint32_t bfix[2];}ge_shadow;static ge_shadow sh;
static int sh_off,hle_strict;
static struct {unsigned binds;}rc;
static uint32_t commands[512];static struct {uint32_t*current;}context;static typeof(context)*gu_list=&context;
static unsigned checks,failures,mode_calls,block_calls,image_calls,flushes,waits,logs;static int last_mxl=-1,last_min,last_mag;
#define CHECK(x) do{checks++;if(!(x)){failures++;printf("FAIL:%d:%s\n",__LINE__,#x);}}while(0)
enum {GU_CLAMP=1,GU_REPEAT=0,GU_NEAREST_MIPMAP_NEAREST=4,GU_NEAREST=0,GU_LINEAR_MIPMAP_LINEAR=7,GU_LINEAR=1,GU_TCC_RGB=0,GU_TCC_RGBA=1,GU_TFX_REPLACE=3,GU_TFX_DECAL=1,GU_TFX_MODULATE=0};
static int sh_set(int k,int v){if(sh.v[k]==v&&!sh_off)return 0;sh.v[k]=v;return 1;}
static void sh_reset(ge_shadow*x){memset(x,0xff,sizeof*x);}
static void sa1_log(const char*s,...){(void)s;logs++;}
static void ge_wait(void){waits++;}
static void sceKernelDcacheWritebackRange(void*p,uint32_t n){(void)p;(void)n;}
static int fmt_psm(int n){return n;}
static int ge_exp(int n){return n?31-__builtin_clz((unsigned)n):-1;}
static void spring_trace(int a,uint32_t b,uint32_t c,int d,int e,float f,float g,uint32_t h){(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;}
static uint16_t hle_rd16(uint32_t a){(void)a;return 4;}
const char*texture_name(uint32_t h){(void)h;return "synthetic";}
static int sega_tile_sampler_clamp(const draw_state*s,int a,int b,uint32_t h,int w,int z,int f,const char*n){(void)s;(void)a;(void)b;(void)h;(void)w;(void)z;(void)f;(void)n;return 0;}
static uint32_t mirror_variant(uint32_t h,int u,int v){unsigned k=(unsigned)u|((unsigned)v<<1);return texs[h].mirror[k]?texs[h].mirror[k]:h;}
static uint32_t block_words[32];
static uint32_t*bind_block(uint32_t h,const gtex*t){(void)h;block_calls++;last_mxl=t->levels-1;return block_words;}
static void sceGuTexFlush(void){flushes++;}
static void sceGuClutMode(int a,int b,int c,int d){(void)a;(void)b;(void)c;(void)d;}
static void sceGuClutLoad(int a,const void*p){(void)a;(void)p;}
static void sceGuTexMode(int f,int m,int c,int s){(void)f;(void)c;(void)s;mode_calls++;last_mxl=m;}
static void sceGuTexImage(int l,int w,int h,int b,const void*p){(void)l;(void)w;(void)h;(void)b;(void)p;image_calls++;}
static void sceGuTexScale(float u,float v){(void)u;(void)v;}
static void sceGuTexWrap(int u,int v){(void)u;(void)v;}
static void sceGuTexFilter(int a,int b){last_min=a;last_mag=b;}
static void sceGuTexFunc(int a,int b){(void)a;(void)b;}
'''

CASES=r'''
static uint8_t chunk[TEXPOOL_CHUNK];static unsigned chunks;
static void*chunk_alloc(void){return chunks++==0?chunk:NULL;}
static void moved(int h,uint8_t*p){texs[h].mem=p;}
static void evict(int h){(void)h;CHECK(0);}
static void setup(void){
 memset(texs,0,sizeof texs);memset(&ui_stats,0,sizeof ui_stats);memset(&sky_stats,0,sizeof sky_stats);memset(&sh,0xff,sizeof sh);
 mode_calls=block_calls=image_calls=flushes=waits=logs=chunks=0;bound_tex=tex_epoch=0;tex_flush_pending=0;last_mxl=-1;tex_su=tex_sv=-1;context.current=commands;replay_v2=16;
 texpool_ops op={chunk_alloc,moved,evict,pool_drop_top};texpool_init(&op,0,1);texpool_set_frame(1);
}
static void pressure(int ui){
 setup();gtex*t=&texs[1];t->w=t->h=256;t->levels=6;uint32_t n=0;uint8_t*p;
 for(int l=0;l<6;l++){t->off[l]=n;t->tbw[l]=256>>l;n+=(256u>>l)*(256u>>l)*2;}
 t->bytes=t->total=n;stats.texture_bytes=n;int b=texpool_alloc(n,1,0,1,&p);CHECK(b>=0);t->mem=p;texpool_touch(b);
 if(ui)texture_ui_protect(1);
 CHECK(texpool_alloc(700000,2,0,1,&p)>=0);texs[2].levels=1;
 int r=texpool_alloc(200000,3,0,1,&p);
 if(ui){CHECK(r<0&&t->w==256&&t->levels==6&&texpool_get_stats()->drops==0);CHECK(ui_stats.drop_refused==1);}
 else CHECK(r>=0&&t->w==128&&t->levels==5&&texpool_get_stats()->drops==1);
}
int main(void){
 static uint8_t pixels[4096];setup();texs[1]=(gtex){.w=64,.h=64,.levels=4,.mem=pixels,.fmt=DRAW_FMT_5650};
 draw_state s={0};s.texture=1;s.layer=DRAW_LAYER_3D;s.filter=DRAW_FILTER_POINT;
 bind_texture(&s);CHECK(last_mxl==3&&block_calls==1&&mode_calls==0);CHECK(!texs[1].ui_protected&&ui_stats.promoted==0);ge_shadow model_end=sh;
 s.layer=DRAW_LAYER_2D;bind_texture(&s);CHECK(last_mxl==0&&block_calls==1&&mode_calls==1&&image_calls==1);CHECK(texs[1].ui_protected&&ui_stats.promoted==1);
 s.layer=DRAW_LAYER_3D;bind_texture(&s);CHECK(last_mxl==3&&block_calls==2);
 s.layer=DRAW_LAYER_2D;bind_texture(&s);CHECK(last_mxl==0&&block_calls==2&&mode_calls==2);CHECK(ui_stats.promoted==1&&ui_stats.cold_lost==0);
 /* The cached model's shadow merge must carry the effective mip count. */
 sh_merge(&model_end);bound_tex=1;
 bind_texture(&s);CHECK(last_mxl==0&&mode_calls==3&&block_calls==2);
 s.filter=DRAW_FILTER_BILINEAR;bind_texture(&s);CHECK(last_min==GU_LINEAR_MIPMAP_LINEAR&&last_mag==GU_LINEAR&&last_mxl==0);
 setup();texs[1]=(gtex){.w=64,.h=64,.levels=4,.mem=pixels};s=(draw_state){0};s.texture=1;s.layer=DRAW_LAYER_2D;replay_v2=8;
 bind_texture(&s);CHECK(last_mxl==0&&context.current==commands+4&&block_calls==0);
 s.layer=DRAW_LAYER_3D;bind_texture(&s);CHECK(last_mxl==3&&context.current==commands+17);
 s.layer=DRAW_LAYER_2D;bind_texture(&s);CHECK(last_mxl==0&&context.current==commands+21);
 setup();texs[1]=(gtex){.w=64,.h=64,.levels=3,.mem=pixels,.fmt=DRAW_FMT_5650};
 texs[2]=(gtex){.w=128,.h=64,.levels=3,.mem=pixels,.fmt=DRAW_FMT_5650,.hidden=1,.parent=1,.pk=1};texs[1].mirror[1]=2;
 s=(draw_state){0};s.texture=1;s.layer=DRAW_LAYER_2D;s.flip_u=1;bind_texture(&s);
 CHECK(texs[1].ui_protected&&texs[2].ui_protected);CHECK(last_mxl==0&&tex_su==.5f);
 CHECK(pool_drop_top(1)==0&&pool_drop_top(2)==0);CHECK(texs[1].w==64&&texs[2].w==128);
 setup();texs[1]=(gtex){.w=32,.h=32,.levels=3,.mem=pixels,.top_drops=2};texture_ui_protect(1);texture_ui_protect(1);
 CHECK(ui_stats.cold_lost==1&&ui_stats.promoted==1&&logs==1);CHECK(texs[1].w==32&&texs[1].top_drops==2);
 texs[3]=(gtex){.w=64,.h=64,.levels=4,.mem=pixels,.dying=1};texture_ui_protect(3);CHECK(!texs[3].ui_protected);
 texture_ui_protect(0);texture_ui_protect(TEX_MAX);CHECK(ui_stats.promoted==1);
 texs[4]=(gtex){.w=64,.h=64,.levels=3,.mem=pixels,.hidden=1,.parent=1,.pk=1};texture_ui_protect(4);CHECK(!texs[4].ui_protected);
 setup();texs[1]=(gtex){.w=64,.h=64,.levels=3,.mem=pixels};texs[4]=(gtex){.w=64,.h=64,.levels=3,.mem=pixels,.hidden=1,.parent=1,.pk=1};texture_ui_protect(4);CHECK(!texs[1].ui_protected&&ui_stats.promoted==0);
 s=(draw_state){0};s.texture=1;s.layer=DRAW_LAYER_2D;bind_texture(&s);CHECK(texs[1].ui_protected);
 texs[1].mirror[1]=4;s.flip_u=1;bind_texture(&s);CHECK(texs[4].ui_protected&&last_mxl==0);
 setup();for(unsigned i=1;i<=12;i++){texs[i]=(gtex){.w=32,.h=32,.levels=3,.mem=pixels,.top_drops=2};texture_ui_protect(i);texture_ui_protect(i);}
 CHECK(ui_stats.promoted==12&&ui_stats.cold_lost==12&&logs==8);
 pressure(0);pressure(1);
 printf("UI texture policy: %u checks, %u failures\n",checks,failures);return failures?1:0;}
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=ROOT/'backend/psp/draw_gu.c');p.add_argument('--out',type=Path,default=ROOT/'work/C95_visual_audit/ui_policy');args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    source=args.source.read_text(encoding='utf8');start=source.index('typedef struct {',source.index('#define TEX_LEVELS 8'));end=source.index('} gtex;',start)+8;gtex=source[start:end]
    # Legacy RED source has no classification fields/helper. Supply inert
    # fixture metadata so its unchanged production behavior can execute.
    if 'ui_protected' not in gtex:gtex=gtex.replace('} gtex;','uint8_t ui_protected,top_drops; } gtex;')
    protect=extract(source,'texture_ui_protect') or 'static void texture_ui_protect(uint32_t h){(void)h;}'
    code=PREFIX.replace('DRAW_HEADER',(ROOT/'backend/draw.h').as_posix()).replace('POOL_HEADER',(ROOT/'backend/texpool.h').as_posix()).replace('GTEX',gtex)
    code+='\n'+extract(source,'texture_detail_protect')+'\n'+protect+'\n'+extract(source,'texture_hud_detail')+'\n'+extract(source,'texture_sky_detail')+'\n'+extract(source,'sh_merge')+'\n'+extract(source,'pool_drop_top')+'\n'+extract(source,'bind_texture')+CASES
    path=args.out/'actual.c';path.write_text(code,encoding='utf8');exe=args.out/'actual'
    r=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-function','-fsanitize=address,undefined','-g',str(path),str(ROOT/'backend/texpool.c'),'-lm','-o',str(exe)],capture_output=True,text=True)
    (args.out/'compile.log').write_text(r.stdout+r.stderr,encoding='utf8')
    if r.returncode:print(r.stderr);return r.returncode
    r=subprocess.run([str(exe)],capture_output=True,text=True);(args.out/'run.log').write_text(r.stdout+r.stderr,encoding='utf8');print(r.stdout+r.stderr)
    (args.out/'RESULT.json').write_text(json.dumps({'exit':r.returncode,'functions':{n:hashlib.sha256(extract(source,n).encode()).hexdigest() for n in ('texture_ui_protect','pool_drop_top','bind_texture')}},indent=2)+'\n',encoding='utf8');return r.returncode


if __name__=='__main__':raise SystemExit(main())
