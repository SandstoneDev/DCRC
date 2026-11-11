#!/usr/bin/env python3
"""Exact live EC sky sampler role, actual bind/pool code; synthetic only. MIT."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
from test_ui_texture_policy import ROOT, PREFIX, CASES, extract


SKY_CASES=r'''
int main(void){static uint8_t pixels[256*256*2];
 const char*names[]={"sonic_sky1","ecsc_s_bkca","ecsc_s_bkcb","ecsc_s_bkcc","ecsc_s_bkcd"};
 int dims[]={256,256,128,128,16};int fmts[]={DRAW_FMT_5650,DRAW_FMT_5650,DRAW_FMT_5650,DRAW_FMT_5650,DRAW_FMT_4444};
 for(int i=0;i<5;i++){
  setup();texs[1]=(gtex){.w=dims[i],.h=dims[i],.levels=4,.mem=pixels,.fmt=fmts[i]};live_names[1]=names[i];
  CHECK(texture_sky_detail(1)==1);draw_state s={0};s.texture=1;s.layer=DRAW_LAYER_3D;bind_texture(&s);
  CHECK(last_mxl==0&&sky_stats.promoted==1&&ui_stats.promoted==0&&(texs[1].ui_protected&2));
 }
 const char*miss[]={"sonic_sky","sonic_sky10","SONIC_SKY1","sonic_sky1_extra","ecsc_s_bkce","ecsc_s_cla","stg_s_bkfirec","?"};
 for(unsigned i=0;i<sizeof miss/sizeof miss[0];i++){
  setup();texs[1]=(gtex){.w=256,.h=256,.levels=4,.mem=pixels,.fmt=DRAW_FMT_5650};live_names[1]=miss[i];
  CHECK(texture_sky_detail(1)==0);draw_state s={0};s.texture=1;s.layer=DRAW_LAYER_3D;bind_texture(&s);CHECK(last_mxl==3&&sky_stats.promoted==0);
 }
 for(int bad=0;bad<6;bad++){
  setup();texs[1]=(gtex){.w=256,.h=256,.levels=4,.mem=pixels,.fmt=DRAW_FMT_5650};live_names[1]="sonic_sky1";
  if(bad==0)texs[1].fmt=DRAW_FMT_4444;if(bad==1)texs[1].w=128;if(bad==2)texs[1].h=128;
  if(bad==3)texs[1].top_drops=7;if(bad==4)texs[1].dying=1;if(bad==5)texs[1].hidden=1;
  CHECK(texture_sky_detail(1)==0);
 }
 setup();texs[1]=(gtex){.w=32,.h=32,.levels=3,.mem=pixels,.fmt=DRAW_FMT_5650,.top_drops=3};live_names[1]="sonic_sky1";
 draw_state s={0};s.texture=1;s.layer=DRAW_LAYER_3D;bind_texture(&s);bind_texture(&s);
 CHECK(last_mxl==0&&sky_stats.cold_lost==1&&sky_stats.promoted==1&&logs==1&&texs[1].w==32);
 /* A new backend incarnation must requalify the current name and MXL,
  * including reuse of the same handle/address/dimensions. */
 setup();texs[1]=(gtex){.w=256,.h=256,.levels=4,.mem=pixels,.fmt=DRAW_FMT_5650};live_names[1]="sonic_sky1";bind_texture(&s);CHECK(last_mxl==0);
 texs[1]=(gtex){.w=256,.h=256,.levels=4,.mem=pixels,.fmt=DRAW_FMT_5650};live_names[1]="ordinary_world";bind_texture(&s);CHECK(last_mxl==3&&texs[1].ui_protected==0);
 live_names[1]="sonic_sky1";bind_texture(&s);CHECK(last_mxl==0&&block_calls==1);
 setup();texs[1]=(gtex){.w=128,.h=128,.levels=4,.mem=pixels,.fmt=DRAW_FMT_5650};live_names[1]="ecsc_s_bkcb";
 texs[2]=(gtex){.w=256,.h=128,.levels=4,.mem=pixels,.fmt=DRAW_FMT_5650,.hidden=1,.parent=1,.pk=1};texs[1].mirror[1]=2;s.flip_u=1;bind_texture(&s);
 CHECK(last_mxl==0&&(texs[1].ui_protected&2)&&(texs[2].ui_protected&2)&&tex_su==.5f);CHECK(last_name_handle==1);
 setup();texs[1]=(gtex){.w=128,.h=128,.levels=4,.mem=pixels,.fmt=DRAW_FMT_5650};live_names[1]="ecsc_s_bkcb";
 texs[2]=(gtex){.w=256,.h=128,.levels=4,.mem=pixels,.fmt=DRAW_FMT_5650,.hidden=1,.parent=3,.pk=1};texs[1].mirror[1]=2;bind_texture(&s);
 CHECK(last_mxl==3&&sky_stats.promoted==0&&texs[2].ui_protected==0);
 setup();texs[1]=(gtex){.w=256,.h=256,.levels=6,.fmt=DRAW_FMT_5650};live_names[1]="sonic_sky1";
 gtex*t=&texs[1];uint32_t n=0;uint8_t*p;for(int l=0;l<6;l++){t->off[l]=n;t->tbw[l]=256>>l;n+=(256u>>l)*(256u>>l)*2;}
 t->bytes=t->total=n;stats.texture_bytes=n;CHECK(texpool_alloc(n,1,0,1,&p)>=0);t->mem=p;s.flip_u=0;bind_texture(&s);
 CHECK(texpool_alloc(700000,3,0,1,&p)>=0);texs[3].levels=1;CHECK(texpool_alloc(200000,4,0,1,&p)<0);
 CHECK(t->w==256&&texpool_get_stats()->drops==0&&sky_stats.drop_refused==1);
 setup();for(unsigned i=1;i<=12;i++){texs[i]=(gtex){.w=32,.h=32,.levels=3,.mem=pixels,.fmt=DRAW_FMT_5650,.top_drops=3};live_names[i]="sonic_sky1";s.texture=i;bind_texture(&s);}
 CHECK(sky_stats.promoted==12&&sky_stats.cold_lost==12&&logs==8);

 /* A later first bind cannot recover discarded pixels. Every exact loaded
  * sky role must veto its first reclaim before it has ever been bound. */
 const char*cold_names[]={"sonic_sky1","ecsc_s_bkca","ecsc_s_bkcb","ecsc_s_bkcc","ecsc_s_bkcd","obj_sssky_d","obj_sssky_e","obj_sssky_n","obj_ssskybb_n"};
 const int cold_dims[]={256,256,128,128,16,256,256,256,128};
 for(unsigned i=0;i<sizeof cold_names/sizeof cold_names[0];i++){
  setup();int d=cold_dims[i];texs[1]=(gtex){.w=d,.h=d,.levels=2,.fmt=i==4?DRAW_FMT_4444:DRAW_FMT_5650};live_names[1]=cold_names[i];
  gtex*q=&texs[1];uint32_t basebytes=(uint32_t)d*d*2;q->off[0]=0;q->off[1]=basebytes;q->total=q->bytes=basebytes+basebytes/4;stats.texture_bytes=q->total;
  uint8_t*mem;CHECK(texpool_alloc(q->total,1,0,1,&mem)>=0);q->mem=mem;
  CHECK(texture_sky_detail(1)==1);CHECK(pool_drop_top(1)==0);
  CHECK(q->w==d&&q->h==d&&q->top_drops==0&&q->levels==2);
  CHECK((q->ui_protected&2)&&sky_stats.promoted==1&&sky_stats.cold_lost==0);
  CHECK(pool_drop_top(1)==0&&sky_stats.promoted==1&&sky_stats.drop_refused==2);
 }
 const char*ssmiss[]={"obj_sssky","obj_sssky_d_extra","OBJ_SSSKY_D","obj_sssky_x"};
 for(unsigned i=0;i<sizeof ssmiss/sizeof ssmiss[0];i++){
  setup();texs[1]=(gtex){.w=256,.h=256,.levels=2,.mem=pixels,.fmt=DRAW_FMT_5650};live_names[1]=ssmiss[i];CHECK(texture_sky_detail(1)==0);
 }
 for(unsigned i=0;i<4;i++)for(unsigned bad=0;bad<5;bad++){
  setup();int d=i==3?128:256;texs[1]=(gtex){.w=d,.h=d,.levels=2,.mem=pixels,.fmt=DRAW_FMT_5650};live_names[1]=cold_names[i+5];
  if(bad==0)texs[1].fmt=DRAW_FMT_4444;if(bad==1)texs[1].w=d/2;if(bad==2)texs[1].h=d/2;
  if(bad==3)texs[1].hidden=1;if(bad==4)texs[1].dying=1;CHECK(texture_sky_detail(1)==0);
 }
 printf("Sky texture policy: %u checks, %u failures\n",checks,failures);return failures?1:0;}
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=ROOT/'backend/psp/draw_gu.c');p.add_argument('--out',type=Path,default=ROOT/'work/C95_visual_audit/sky_policy');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    source=a.source.read_text(encoding='utf8');start=source.index('typedef struct {',source.index('#define TEX_LEVELS 8'));end=source.index('} gtex;',start)+8
    prefix=PREFIX.replace('DRAW_HEADER',(ROOT/'backend/draw.h').as_posix()).replace('POOL_HEADER',(ROOT/'backend/texpool.h').as_posix()).replace('GTEX',source[start:end])
    prefix=prefix.replace('const char*texture_name(uint32_t h){(void)h;return "synthetic";}', 'static const char*live_names[TEX_MAX];static uint32_t last_name_handle;const char*texture_name(uint32_t h){last_name_handle=h;return live_names[h]?live_names[h]:"?";}')
    names=('texture_detail_protect','texture_ui_protect','texture_hud_detail','texture_sky_detail','sh_merge','pool_drop_top','bind_texture')
    functions='\n'.join(extract(source,n) for n in names)
    if not extract(source,'texture_sky_detail'):functions+='\nstatic int texture_sky_detail(uint32_t h){(void)h;return 0;}\n'
    common=CASES[:CASES.index('int main(void)')]
    code=prefix+'\n'+functions+common+SKY_CASES
    path=a.out/'actual.c';path.write_text(code,encoding='utf8');exe=a.out/'actual'
    b=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-function','-Wno-misleading-indentation','-fsanitize=address,undefined','-g',str(path),str(ROOT/'backend/texpool.c'),'-lm','-o',str(exe)],capture_output=True,text=True)
    (a.out/'compile.log').write_text(b.stdout+b.stderr,encoding='utf8')
    if b.returncode:print(b.stderr);return b.returncode
    r=subprocess.run([str(exe)],capture_output=True,text=True);(a.out/'run.log').write_text(r.stdout+r.stderr,encoding='utf8');print(r.stdout+r.stderr)
    (a.out/'RESULT.json').write_text(json.dumps({'exit':r.returncode,'functions':{n:hashlib.sha256(extract(source,n).encode()).hexdigest() for n in names if extract(source,n)}},indent=2)+'\n',encoding='utf8');return r.returncode


if __name__=='__main__':raise SystemExit(main())
