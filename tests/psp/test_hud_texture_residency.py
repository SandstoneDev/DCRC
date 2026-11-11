#!/usr/bin/env python3
"""Cold HUD reclaim regression: actual GU callback + pool, synthetic data. MIT."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

from test_ui_texture_policy import ROOT, PREFIX, CASES, extract


HUD_CASES = r'''
static uint8_t pixels[65536];
static void rectangle(unsigned h,int w,int height,int fmt,const char*name){
 gtex*t=&texs[h];*t=(gtex){.w=w,.h=height,.fmt=fmt,.mem=pixels};live_names[h]=name;
 int n=0;for(int l=0;(w>>l)>=8&&(height>>l)>=8;l++){t->off[t->levels]=n;t->tbw[t->levels++]=w>>l;n+=(w>>l)*(height>>l)*2;}
 t->bytes=t->total=n;stats.texture_bytes+=n;
}
static void image(unsigned h,int size,int fmt,const char*name){rectangle(h,size,size,fmt,name);}
static void cold_pressure(const char*name,int size,int fmt,int keep){
 setup();memset(live_names,0,sizeof live_names);image(1,size,fmt,name);gtex*t=&texs[1];
 uint8_t*p;CHECK(texpool_alloc(t->total,1,0,1,&p)>=0);t->mem=p;
 CHECK(texpool_alloc(TEXPOOL_CHUNK-t->total-4096,2,0,1,&p)>=0);texs[2].levels=1;
 /* No bind or 2D submission has happened when the next load needs room. */
 int r=texpool_alloc(4300,3,0,1,&p);
 if(keep){CHECK(r<0);CHECK(t->w==size&&t->top_drops==0);CHECK(t->ui_protected&1);CHECK(ui_stats.cold_lost==0);}
 else {CHECK(r>=0);CHECK(t->w==size/2&&t->top_drops==1);CHECK(!t->ui_protected);}
}
static void pause_pressure(const char*name,int w,int height,int fmt,int keep){
 setup();memset(live_names,0,sizeof live_names);rectangle(1,w,height,fmt,name);gtex*t=&texs[1];
 uint8_t*p;CHECK(texpool_alloc(t->total,1,0,1,&p)>=0);t->mem=p;
 uint8_t before[65536];uint32_t original_total=t->total;
 for(uint32_t i=0;i<original_total;i++)p[i]=(uint8_t)(i*13u+(i>>8)+(i>>16));
 memcpy(before,p,original_total);
 CHECK(texpool_alloc(TEXPOOL_CHUNK-t->total-4096,2,0,1,&p)>=0);texs[2].levels=1;
 int r=texpool_alloc(4300,3,0,1,&p); /* still before first 2D bind */
 if(keep){CHECK(r<0);CHECK(t->w==w&&t->h==height&&t->total==original_total&&t->top_drops==0);
  CHECK((t->ui_protected&1)&&ui_stats.cold_lost==0);CHECK(texpool_get_stats()->drops==0);
  CHECK(!memcmp(t->mem,before,original_total));
 }else{CHECK(r>=0);CHECK(t->w==w/2&&t->h==height/2&&t->top_drops==1);CHECK(!t->ui_protected);}
}
int main(void){
 cold_pressure("hyoji_head",64,DRAW_FMT_4444,1);
 const char*life[]={"hyoji_zanki_s","hyoji_zanki_t","hyoji_zanki_k","hyoji_zanki_a","hyoji_zanki_e","hyoji_zankib"};
 for(unsigned i=0;i<sizeof life/sizeof life[0];i++)cold_pressure(life[i],32,DRAW_FMT_5650,1);
 for(int i=0;i<10;i++){char name[24];snprintf(name,sizeof name,"snum_%d",i);cold_pressure(name,16,DRAW_FMT_4444,1);
  snprintf(name,sizeof name,"digit%d",i);cold_pressure(name,32,DRAW_FMT_4444,1);}
 cold_pressure("snum_co",16,DRAW_FMT_4444,1);cold_pressure("colon",32,DRAW_FMT_4444,1);
 cold_pressure("ordinary_world",64,DRAW_FMT_4444,0);
 cold_pressure("hyoji_head_extra",64,DRAW_FMT_4444,0);
 cold_pressure("hyoji_head",32,DRAW_FMT_4444,0);
 cold_pressure("hyoji_head",64,DRAW_FMT_5650,0);
 cold_pressure("hyoji_zanki_s",32,DRAW_FMT_4444,0);
 cold_pressure("snum_10",16,DRAW_FMT_4444,0);
 cold_pressure("digit01",32,DRAW_FMT_4444,0);
 /* Original US1.005 pause-bank metadata only; synthetic pixels, no assets.
  * GBIX: title365743; English labels10000201/10000200/10000202;
  * shared panel365745/365746/365744. Role guard uses current live name/shape/format. */
 pause_pressure("npa_pause",256,64,DRAW_FMT_4444,1);
 const char*pause[]={"npa_restart","npa_saikai","npa_stop","nbutton_kage","nbutton_waku"};
 for(unsigned i=0;i<sizeof pause/sizeof pause[0];i++)pause_pressure(pause[i],128,32,DRAW_FMT_4444,1);
 pause_pressure("nbutton_ita",128,32,DRAW_FMT_5650,1);
 pause_pressure("npa_restart_extra",128,32,DRAW_FMT_4444,0);
 pause_pressure("NPA_RESTART",128,32,DRAW_FMT_4444,0);
 pause_pressure("npa_restart",64,32,DRAW_FMT_4444,0);
 pause_pressure("npa_restart",128,64,DRAW_FMT_4444,0);
 pause_pressure("npa_restart",128,32,DRAW_FMT_5650,0);
 pause_pressure("npa_pause",128,32,DRAW_FMT_4444,0);
 pause_pressure("nbutton_ita",128,32,DRAW_FMT_4444,0);
 pause_pressure("ordinary_world",128,32,DRAW_FMT_4444,0);
 /* Early protection must leave unrelated reclaim candidates available. */
 setup();rectangle(1,128,32,DRAW_FMT_4444,"npa_restart");rectangle(2,128,32,DRAW_FMT_4444,"ordinary_world");
 uint8_t*pp;CHECK(texpool_alloc(texs[1].total,1,0,1,&pp)>=0);texs[1].mem=pp;
 CHECK(texpool_alloc(texs[2].total,2,0,1,&pp)>=0);texs[2].mem=pp;
 CHECK(texpool_alloc(TEXPOOL_CHUNK-texs[1].total-texs[2].total-4096,3,0,1,&pp)>=0);texs[3].levels=1;
 CHECK(texpool_alloc(4300,4,0,1,&pp)>=0);
 CHECK(texs[1].w==128&&texs[1].h==32&&texs[1].top_drops==0&&(texs[1].ui_protected&1));
 CHECK(texs[2].w==64&&texs[2].h==16&&texs[2].top_drops==1&&texpool_get_stats()->drops==1);
 /* Reconstruct original dimensions only for this live incarnation; no restoration. */
 setup();rectangle(1,32,8,DRAW_FMT_4444,"npa_restart");texs[1].top_drops=2;CHECK(texture_hud_detail(1));
 texture_ui_protect(1);CHECK(texs[1].w==32&&texs[1].h==8&&ui_stats.cold_lost==1);
 setup();rectangle(1,128,32,DRAW_FMT_4444,"npa_restart");texs[1].hidden=1;CHECK(!texture_hud_detail(1));
 texs[1].hidden=0;texs[1].dying=1;CHECK(!texture_hud_detail(1));texs[1].dying=0;
 live_names[1]="ordinary_world";CHECK(!texture_hud_detail(1));CHECK(pool_drop_top(1)>0);
 /* Reclaim must continue to an ordinary world candidate after keeping HUD,
  * instead of turning one protected image into a global allocation failure. */
 setup();image(1,64,DRAW_FMT_4444,"hyoji_head");image(2,64,DRAW_FMT_4444,"ordinary_world");
 uint8_t*p;CHECK(texpool_alloc(texs[1].total,1,0,1,&p)>=0);texs[1].mem=p;
 CHECK(texpool_alloc(texs[2].total,2,0,1,&p)>=0);texs[2].mem=p;
 CHECK(texpool_alloc(TEXPOOL_CHUNK-texs[1].total-texs[2].total-4096,3,0,1,&p)>=0);texs[3].levels=1;
 CHECK(texpool_alloc(4300,4,0,1,&p)>=0);
 CHECK(texs[1].w==64&&texs[1].top_drops==0&&(texs[1].ui_protected&1));
 CHECK(texs[2].w==32&&texs[2].top_drops==1&&texpool_get_stats()->drops==1);
 /* Reused backend slots must qualify their current name and dimensions. */
 setup();image(1,64,DRAW_FMT_4444,"hyoji_head");CHECK(texture_hud_detail(1));
 live_names[1]="world_after_reload";CHECK(!texture_hud_detail(1));CHECK(pool_drop_top(1)>0);
 CHECK(texs[1].w==32&&!texs[1].ui_protected);
 setup();image(1,64,DRAW_FMT_4444,"hyoji_head");texs[1].hidden=1;CHECK(!texture_hud_detail(1));
 texs[1].hidden=0;texs[1].dying=1;CHECK(!texture_hud_detail(1));
 texs[1].dying=0;texs[1].mem=NULL;CHECK(!texture_hud_detail(1));
 CHECK(!texture_hud_detail(0)&&!texture_hud_detail(TEX_MAX));
 printf("Cold HUD residency: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, default=ROOT/'backend/psp/draw_gu.c')
    p.add_argument('--out', type=Path, default=ROOT/'work/C100_hud/residency')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    source = a.source.read_text(encoding='utf8')
    start = source.index('typedef struct {', source.index('#define TEX_LEVELS 8'))
    end = source.index('} gtex;', start)+8
    prefix = PREFIX.replace('DRAW_HEADER', (ROOT/'backend/draw.h').as_posix()).replace('POOL_HEADER', (ROOT/'backend/texpool.h').as_posix()).replace('GTEX', source[start:end])
    prefix = prefix.replace('const char*texture_name(uint32_t h){(void)h;return "synthetic";}', 'static const char*live_names[TEX_MAX];const char*texture_name(uint32_t h){return live_names[h]?live_names[h]:"?";}')
    names = ('texture_detail_protect', 'texture_ui_protect', 'texture_hud_detail', 'texture_sky_detail', 'pool_drop_top')
    functions = '\n'.join(extract(source, n) for n in names)
    if not extract(source, 'texture_hud_detail'):
        functions += '\nstatic int texture_hud_detail(uint32_t h){(void)h;return 0;}\n'
    code = prefix+'\n'+functions+CASES[:CASES.index('int main(void)')]+HUD_CASES
    path = a.out/'actual.c'
    path.write_text(code, encoding='utf8')
    exe = a.out/'actual'
    b = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-variable', '-Wno-unused-function', '-fsanitize=address,undefined', '-g', str(path), str(ROOT/'backend/texpool.c'), '-lm', '-o', str(exe)], capture_output=True, text=True)
    (a.out/'compile.log').write_text(b.stdout+b.stderr, encoding='utf8')
    if b.returncode:
        print(b.stderr)
        return b.returncode
    r = subprocess.run([str(exe)], capture_output=True, text=True)
    (a.out/'run.log').write_text(r.stdout+r.stderr, encoding='utf8')
    print(r.stdout+r.stderr)
    (a.out/'RESULT.json').write_text(json.dumps({'exit': r.returncode, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'functions': {n: hashlib.sha256(extract(source, n).encode()).hexdigest() for n in names}}, indent=2)+'\n', encoding='utf8')
    return r.returncode


if __name__ == '__main__':
    raise SystemExit(main())
