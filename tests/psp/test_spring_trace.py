#!/usr/bin/env python3
"""Opt-in spring diagnostics on actual mirror/bind C bodies; own synthetic data."""
from pathlib import Path
import argparse,re,subprocess
R=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=R/'backend/psp/draw_gu.c');p.add_argument('--out',type=Path,default=R/'work/C85_jump_pad/trace_host');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
s=a.source.read_text()
def fn(name):
 m=re.search(r'(?m)^[^\n;{}]*\b'+name+r'\([^;{}]*\)\s*\{',s);assert m,name
 end=s.index('{',m.start())+1;n=1
 while n:n+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[m.start():end]
start=s.find('/* Opt-in round-spring');end=s.index('/* The mirrored variant of slot')
diag=s[start:end] if start>=0 else 'static int spring_trace_on=-1; static unsigned spring_trace_seen;'
prefix=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "backend/draw.h"
#define TEX_MAX 8
typedef struct{int w,h,fmt,clut_fmt,levels,tbw[8],pblk;uint8_t*mem;uint32_t off[8],mirror[4],mfail,parent,bytes;uint16_t*clut;int hidden,pk;}gtex;
static gtex texs[TEX_MAX];static struct{unsigned texture_bytes;}stats;static struct{unsigned mirror_fail,mirrors;}gs;
static uint32_t mirror_epoch,mirror_need,tex_frame,bound_tex;
static int gu_debug,max_levels=8,tex_pool_on=1,tex_flush_pending,replay_v2,in_model_build;
static float tex_su=-1,tex_sv=-1;static struct{unsigned binds;}rc;
typedef struct{unsigned*current;}List;
static unsigned words[100];static List listobj,*gu_list=&listobj;
static unsigned allocations,slots,builds,logs,names,envs,commands,failures,checks,cmdhash;
static int fail_at,slot_ok=1,build_fail,target=1;static const char*env_value;
static char trace[8192];static uint8_t pixels[64*64*2],mirrored[128*128*2];
#define CHECK(x)do{checks++;if(!(x)){failures++;printf("FAIL %d %s\n",__LINE__,#x);}}while(0)
static uint32_t hle_frame_count(void){return 240;}
static const char*texture_name(uint32_t h){(void)h;names++;return target?"banehead":"other";}
static char*test_getenv(const char*k){CHECK(!strcmp(k,"SA1_SPRING_TRACE"));envs++;return(char*)env_value;}
static void sa1_log(const char*f,...){va_list a;va_start(a,f);size_t n=strlen(trace);vsnprintf(trace+n,sizeof trace-n,f,a);va_end(a);strncat(trace,"\n",sizeof trace-strlen(trace)-1);logs++;}
static void*test_malloc(size_t n){allocations++;return allocations==(unsigned)fail_at?NULL:malloc(n);}
static void*test_calloc(size_t n,size_t z){allocations++;return allocations==(unsigned)fail_at?NULL:calloc(n,z);}
typedef struct{void*ptr;int32_t uid;}sa1_temp_block;
static void*sa1_plat_temp_alloc(uint32_t n,sa1_temp_block*b){b->ptr=test_malloc(n);b->uid=-1;return b->ptr;}
static void sa1_plat_temp_free(sa1_temp_block*b){free(b->ptr);b->ptr=NULL;b->uid=-1;}
static int free_slot(void){slots++;return slot_ok?2:0;}
static int fmt_bits(int f){(void)f;return 16;}
static uint32_t row_bytes(int w,int bits){return(uint32_t)w*(unsigned)bits/8;}
static void unswizzle(uint8_t*d,const uint8_t*s,uint32_t rb,uint32_t rows){memcpy(d,s,rb*rows);}
static unsigned px_get(const uint8_t*b,uint32_t rb,int bits,int x,int y){(void)bits;uint16_t n;memcpy(&n,b+y*rb+x*2,2);return n;}
static void px_set(uint8_t*b,uint32_t rb,int bits,int x,int y,unsigned v){(void)bits;uint16_t n=(uint16_t)v;memcpy(b+y*rb+x*2,&n,2);}
static int texture_build(int h,int w,int ht,int f,const uint8_t*p,int cf,uint16_t*cl,int own,int cache){(void)p;(void)own;(void)cache;builds++;if(build_fail)return-1;texs[h].w=w;texs[h].h=ht;texs[h].fmt=f;texs[h].clut_fmt=cf;texs[h].clut=cl;texs[h].mem=mirrored;texs[h].levels=1;texs[h].tbw[0]=w;return 0;}
static uint32_t texpool_psp_bytes(int w,int h,int bits,int n,void*p){(void)n;(void)p;return(unsigned)w*(unsigned)h*(unsigned)bits/8;}
enum{SH_WRAP,SH_FILTER,SH_TFUNC,GU_CLAMP,GU_REPEAT,GU_NEAREST_MIPMAP_NEAREST,GU_NEAREST,GU_LINEAR_MIPMAP_LINEAR,GU_LINEAR,GU_TCC_RGB,GU_TCC_RGBA,GU_TFX_REPLACE,GU_TFX_DECAL,GU_TFX_MODULATE};
static void command(unsigned k){commands++;cmdhash=cmdhash*16777619u^k;}
static int sh_set(int k,int v){command((unsigned)(k*256+v));return 1;}
static void texpool_touch(int i){command((unsigned)i+100);}
static uint32_t*bind_block(uint32_t h,const gtex*t){(void)h;(void)t;return NULL;}
static int fmt_psm(int f){return f;}
static int ge_exp(int n){return n?31-__builtin_clz((unsigned)n):-1;}
static void sceGuTexFlush(void){command(1000);}
static void sceGuClutMode(int a,int b,int c,int d){command((unsigned)(a+b+c+d+2000));}
static void sceGuClutLoad(int n,void*p){(void)p;command((unsigned)n+3000);}
static void sceGuTexMode(int a,int b,int c,int d){command((unsigned)(a+b+c+d+4000));}
static void sceGuTexImage(int l,int w,int h,int tbw,const void*p){(void)p;command((unsigned)(l+w+h+tbw+5000));}
static void sceGuTexScale(float u,float v){uint32_t a,b;memcpy(&a,&u,4);memcpy(&b,&v,4);command(a);command(b);}
static void sceGuTexWrap(int u,int v){command((unsigned)(u+v+6000));}
static void sceGuTexFilter(int u,int v){command((unsigned)(u+v+7000));}
static void sceGuTexFunc(int u,int v){command((unsigned)(u+v+8000));}
#define malloc test_malloc
#define calloc test_calloc
#define getenv test_getenv
'''
suffix=r'''
#undef malloc
#undef calloc
#undef getenv
static void reset(const char*e){memset(texs,0,sizeof texs);memset(&stats,0,sizeof stats);memset(&gs,0,sizeof gs);memset(trace,0,sizeof trace);texs[1].mem=pixels;texs[1].w=texs[1].h=64;texs[1].levels=1;texs[1].tbw[0]=64;mirror_epoch=mirror_need=0;tex_frame=1;fail_at=build_fail=0;slot_ok=target=1;allocations=slots=builds=logs=names=envs=commands=cmdhash=0;env_value=e;spring_trace_on=-1;spring_trace_seen=0;RESET_EXTRA tex_su=tex_sv=-1;bound_tex=0;listobj.current=words;replay_v2=in_model_build=tex_flush_pending=0;}
static draw_state state(void){draw_state s={0};s.texture=1;s.flip_u=1;s.clamp_v=1;return s;}
static unsigned signature(void){return cmdhash^commands^allocations*31^slots*67^builds*101^texs[1].mirror[1]*127^gs.mirrors*131^mirror_need;}
int main(void){
 draw_state s=state();unsigned sigoff[4];
 for(int f=0;f<4;f++){
  reset(NULL);if(f<2)fail_at=f+1;else if(f==2)slot_ok=0;else build_fail=1;
  bind_texture(&s);CHECK(texs[1].mirror[1]==0);CHECK(tex_su==1&&tex_sv==1);CHECK(allocations==2&&slots==1);CHECK(logs==0&&names==0);sigoff[f]=signature();
  for(int i=0;i<20;i++){mirror_variant(1,1,0);}CHECK(logs==0&&names==0&&envs==1);CHECK(allocations==2&&slots==1);
  fail_at=build_fail=0;slot_ok=1;mirror_epoch++;bind_texture(&s);CHECK(tex_su==.5f&&tex_sv==1&&texs[1].mirror[1]==2);CHECK(logs==0&&names==0);
 }
 reset("0");bind_texture(&s);CHECK(logs==0&&names==0&&envs==1);
 for(int f=0;f<4;f++){
  const char*reason[]={"lin","out","slot","build"};reset("1");if(f<2)fail_at=f+1;else if(f==2)slot_ok=0;else build_fail=1;
  bind_texture(&s);CHECK(signature()==sigoff[f]);CHECK(logs==2);CHECK(strstr(trace,reason[f])!=NULL);CHECK(strstr(trace,"bind-base")!=NULL);CHECK(strstr(trace,"lin_bytes=8192 out_bytes=16388")!=NULL);CHECK(strstr(trace,"base=1 actual=1 dims=64x64")!=NULL);
  unsigned n=allocations;for(int i=0;i<100;i++)bind_texture(&s);CHECK(allocations==n&&logs==3);CHECK(strstr(trace,"epoch-defer")!=NULL);
  fail_at=build_fail=0;slot_ok=1;mirror_epoch++;bind_texture(&s);CHECK(logs==5);CHECK(strstr(trace,"success")!=NULL);CHECK(strstr(trace,"bind-mirror")!=NULL);CHECK(strstr(trace,"base=1 actual=2 dims=128x64")!=NULL);CHECK(strstr(trace,"scale=0.5,1")!=NULL);
 }
 reset("1");texs[1].mirror[1]=2;texs[2]=texs[1];texs[2].w=128;bind_texture(&s);CHECK(logs==1&&allocations==0);CHECK(strstr(trace,"bind-mirror")!=NULL);unsigned prior_names=names;for(int i=0;i<300;i++)bind_texture(&s);CHECK(logs==1&&names==prior_names);
 texs[1].mirror[1]=0;fail_at=1;mirror_epoch++;bind_texture(&s);CHECK(strstr(trace,"reason=lin")!=NULL);CHECK(logs==3); /* earlier bind success must not suppress a new failure */
 reset("1");target=0;fail_at=1;bind_texture(&s);CHECK(logs==0&&names>0&&allocations==2);
 reset("1");bind_texture(&s);unsigned head_logs=logs;target=0;texs[2].w=64;bind_texture(&s);CHECK(logs==head_logs);target=1;bind_texture(&s);CHECK(logs==head_logs+1); /* reused handle must recheck the current name */
 reset("1");bind_texture(&s);CHECK(strstr(trace,"raw=9")!=NULL);s.clamp_u=1;unsigned image_allocs=allocations;bind_texture(&s);CHECK(allocations==image_allocs&&tex_su==1);CHECK(strstr(trace,"fallback-after-success")!=NULL&&strstr(trace,"raw=d")!=NULL);s=state();
 reset("1");for(int f=0;f<4;f++){texs[1].mirror[1]=0;mirror_epoch++;fail_at=f<2?(int)allocations+f+1:0;slot_ok=f!=2;build_fail=f==3;bind_texture(&s);bind_texture(&s);}
 fail_at=build_fail=0;slot_ok=1;mirror_epoch++;bind_texture(&s);unsigned total=logs;CHECK(total==8);for(int i=0;i<300;i++){texs[1].mirror[1]=0;mirror_epoch++;fail_at=(int)allocations+1;bind_texture(&s);}CHECK(logs==total+1);CHECK(strstr(trace,"fallback-after-success")!=NULL);
 fail_at=0;mirror_epoch++;bind_texture(&s);CHECK(strstr(trace,"recreate")!=NULL);CHECK(strstr(trace,"bind-change")!=NULL);
 texs[1].w=texs[1].h=32;texs[2].w=64;texs[2].h=32;bind_texture(&s);CHECK(strstr(trace,"dims=64x32 source=32x32")!=NULL);CHECK(strstr(trace,"lin_bytes=2048 out_bytes=4100")!=NULL);
 for(int i=0;i<300;i++){texs[1].w=texs[1].h=(i&1)?32:64;bind_texture(&s);}CHECK(logs<=12);CHECK(strlen(trace)<sizeof trace-1);
 printf("spring_trace: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
'''
# Baseline source has no helper; stubs are intentionally unused until the fix.
suffix=suffix.replace('RESET_EXTRA','spring_trace_lines=spring_trace_changes=0;memset(&spring_trace_last,0,sizeof spring_trace_last);' if 'spring_trace_last' in diag else '')
code=prefix+'\n'+diag+'\n'+fn('mirror_variant')+'\n'+fn('bind_texture')+'\n'+suffix
(a.out/'spring_trace.c').write_text(code)
cmd=['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-fno-strict-aliasing','-fsanitize=address,undefined','-I'+str(R),str(a.out/'spring_trace.c'),'-o',str(a.out/'spring_trace')]
b=subprocess.run(cmd,capture_output=True,text=True);out=b.stdout+b.stderr;rc=b.returncode
if not rc:
 r=subprocess.run([str(a.out/'spring_trace')],capture_output=True,text=True,timeout=30);out+=r.stdout+r.stderr;rc=r.returncode
out+=f'exit={rc}\n';(a.out/'spring_trace.log').write_text(out);print(out,end='');raise SystemExit(rc)
