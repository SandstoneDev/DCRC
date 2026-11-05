"""Exercise the actual FPS overlay body with SDK stubs (no game data). MIT."""
from pathlib import Path
import re,tempfile,subprocess,os
root=Path(__file__).resolve().parents[2];source=(root/'backend/psp/draw_gu.c').read_text()
match=re.search(r'static void fps_overlay\(void\)\s*\{.*?\n\}',source,re.S)
assert match,'FPS overlay implementation missing (RED)'
body=match.group(0)
setter=re.search(r'int draw_gu_set_fps_hud\(const char \*value\)\s*\{.*?\n\}',source,re.S).group(0)
for forbidden in ('sceDisplayWait','sceGuSync','sceKernelDelay','sceGuDepthRange','sceGum','sceGeEdramGetAddr','pspDebugScreen'):
 assert forbidden not in body,forbidden
harness=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fps_meter.h"
#include "fps_glyphs.h"
#define SCR_W 480
#define SCR_H 272
#define LIST_BYTES (640u<<10)
#define GU_TRUE 1
#define GU_FALSE 0
#define GU_DEPTH_TEST 10
#define GU_FLAT 20
#define GU_SPRITES 30
#define GU_COLOR_8888 0x100
#define GU_VERTEX_16BIT 0x200
#define GU_TRANSFORM_2D 0x400
#define GU_SRC_ALPHA 40
#define GU_ONE_MINUS_SRC_ALPHA 41
#define SH_TEX 0
#define SH_BLEND 1
#define SH_ATEST 2
#define SH_CULL 3
#define SH_FOG 4
#define SH_SHADE 5
#define SH_N 6
struct shadow {int v[SH_N];};static struct shadow sh;
static int headless,list_open=1,aspect_wide=1,fps_hud_on=1;
static char fps_hud_label[9]="83";
static uint32_t fps_hud_draws,fps_hud_skips;
static fps_meter fps_hud_meter;static display_counter display_counts;
unsigned char msx[2048]; /* Synthetic SDK-shaped rows, no real font bytes. */
static uint64_t now;static unsigned used,commands,allocations,draws,observes,depth=1,mask,scissor[4],failures,checks;
static unsigned char memory[FPS_RECTS_MAX*2*12+64] __attribute__((aligned(16)));
#define CHECK(x) do{checks++;if(!(x)){failures++;printf("FAIL %d %s\n",__LINE__,#x);}}while(0)
static void display_observe(void){observes++;}
static unsigned sceKernelCpuSuspendIntr(void){return 0;}
static void sceKernelCpuResumeIntr(unsigned i){(void)i;}
static uint64_t sa1_plat_time_us(void){return now;}
static uint32_t hle_frame_count(void){return 100;}
static uint32_t hle_rd16(uint32_t a){(void)a;return 1;}
static unsigned sceGuCheckList(void){return used;}
static void *sceGuGetMemory(int n){CHECK(n>0&&n<=(int)sizeof memory);allocations++;return memory;}
static void sh_enable(int k,int on){sh.v[k]=on;commands++;}
static void sh_blendfunc(int s,int d,unsigned a,unsigned b){CHECK(s==GU_SRC_ALPHA&&d==GU_ONE_MINUS_SRC_ALPHA&&a==0&&b==0);commands++;}
static int sh_set(int k,int v){int r=sh.v[k]!=v;sh.v[k]=v;return r;}
static void sh_zmask(int x){mask=(unsigned)x;commands++;}
static void sh_reset(struct shadow *s){for(unsigned i=0;i<SH_N;i++)s->v[i]=-1;}
static void sceGuDisable(int x){CHECK(x==GU_DEPTH_TEST);depth=0;commands++;}
static void sceGuEnable(int x){CHECK(x==GU_DEPTH_TEST);depth=1;commands++;}
static void sceGuShadeModel(int x){CHECK(x==GU_FLAT);commands++;}
static void sceGuScissor(int a,int b,int c,int d){scissor[0]=a;scissor[1]=b;scissor[2]=c;scissor[3]=d;commands++;}
static void sceGuDrawArray(int p,int flags,int n,const void*idx,const void*v){
 CHECK(p==GU_SPRITES&&flags==(GU_COLOR_8888|GU_VERTEX_16BIT|GU_TRANSFORM_2D));CHECK(idx==NULL&&v==memory&&n>0&&n<=FPS_RECTS_MAX*2&&n%2==0);CHECK(depth==0&&mask==GU_TRUE&&sh.v[SH_BLEND]==1);draws++;
 struct vertex{uint32_t color;int16_t x,y,z,pad;};const struct vertex *a=v;
 CHECK(a[0].color==0xa0000000u&&a[0].x==0&&a[0].y==0&&a[1].y==10);
 for(int i=2;i<n;i++)CHECK(a[i].color==0xff40ff40u);
 for(int i=0;i<n;i+=2){CHECK(a[i].x>=0&&a[i+1].x<=480&&a[i].y>=0&&a[i+1].y<=272);CHECK(a[i].x<a[i+1].x&&a[i].y<a[i+1].y);CHECK(a[i].z==0&&a[i+1].z==0);}
}
BODY
int main(void){
 memset(msx,0x80,sizeof msx);memset(msx+' '*8,0,8);
 CHECK(draw_gu_set_fps_hud("off")==0&&fps_hud_on==0);CHECK(draw_gu_set_fps_hud("83")==0&&fps_hud_on==1&&!strcmp(fps_hud_label,"83"));CHECK(draw_gu_set_fps_hud("TOO_LONG_LABEL")<0&&fps_hud_on==0);CHECK(draw_gu_set_fps_hud(NULL)<0&&fps_hud_on==0);CHECK(draw_gu_set_fps_hud("on")==0&&fps_hud_on==1);draw_gu_set_fps_hud("83");fps_hud_on=0;fps_overlay();CHECK(commands==0&&draws==0&&allocations==0&&observes==0);
 fps_hud_on=1;headless=1;fps_overlay();CHECK(commands==0&&draws==0&&observes==0);headless=0;
 fps_overlay();CHECK(draws==1&&allocations==1&&fps_hud_draws==1&&depth==1);CHECK(scissor[0]==0&&scissor[2]==480);for(int i=0;i<SH_N;i++)CHECK(sh.v[i]==-1);
 unsigned old=commands;used=LIST_BYTES-8;fps_overlay();CHECK(commands==old&&draws==1&&allocations==1&&fps_hud_skips==1);
 used=0;aspect_wide=0;now=1000000;display_counts.visible=30;fps_overlay();CHECK(draws==2&&depth==1&&scissor[0]==60&&scissor[2]==420);CHECK(fps_hud_meter.valid&&fps_hud_meter.fps_tenths==300);
 printf("FPS GE integration: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
'''.replace('BODY',setter+'\n'+body)
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(harness)
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+str(root/'backend/psp'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
# Critical placement: no HUD commands after Finish or framebuffer ownership transfer.
end=re.search(r'void draw_end_frame\(void\)\s*\{.*?\n\}',source,re.S).group(0)
assert end.index('replay();')<end.index('fps_overlay();')<end.index('sceGuFinish();')<end.index('sceKernelSignalSema(ge_go')
print('FPS overlay submit ordering PASS')
