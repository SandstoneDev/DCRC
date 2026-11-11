from pathlib import Path
import re,subprocess
ROOT=Path(__file__).resolve().parents[2];s=(ROOT/'backend/psp/draw_gu.c').read_text()
m=re.search(r'(?m)^static void frame_clear\(void\) \{',s);a=m.start();i=s.index('{',a)+1;d=1
while d:d+=(s[i]=='{')-(s[i]=='}');i+=1
code=r'''#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#define SCR_W 480
#define SCR_H 272
#define GU_FALSE 0
#define GU_COLOR_BUFFER_BIT 1
#define GU_DEPTH_BUFFER_BIT 2
static int aspect_wide,swap_pending,swap_vcount,clip_x,clip_w=480;static unsigned color,pixels[480],frame_clear_argb=0x12345;
static struct {uint64_t swap_wait_us;} gs;
static void dither_clear_policy(void){}
static int sceDisplayGetVcount(void){return 0;}
static void sceDisplayWaitVblankStart(void){}
static uint64_t sa1_plat_time_us(void){return 0;}
static void display_observe(void){}
static void sh_zoff(int x){(void)x;}static void sh_zmask(int x){(void)x;}
/* Exact shipped libpspgu.a adds x+w-1: width semantics, verified by objdump. */
static void sceGuScissor(int x,int y,int w,int h){assert(y==0&&h==272&&x>=0&&x+w<=480);clip_x=x;clip_w=w;}
static void sceGuClearColor(unsigned x){color=x;}
static void sceGuClearDepth(unsigned x){(void)x;}
static void sceGuClear(unsigned bits){if(bits&GU_COLOR_BUFFER_BIT)for(int x=clip_x;x<clip_x+clip_w;x++)pixels[x]=color;}
static unsigned abgr(unsigned x){return x;}
/* Geometry itself separately tested against actual border_draw. */
static void border_draw(void){for(int x=0;x<60;x++)pixels[x]=0xbeef;for(int x=420;x<480;x++)pixels[x]=0xbeef;}
'''+s[a:i]+r'''
int main(void){
 frame_clear();for(int x=0;x<480;x++)assert(pixels[x]==((x<60||x>=420)?0xbeef:(frame_clear_argb|0xff000000u)));
 assert(clip_x==60&&clip_w==360);aspect_wide=1;frame_clear();for(int x=0;x<480;x++)assert(pixels[x]==(frame_clear_argb|0xff000000u));
 puts("actual public frame_clear preserves both 4:3 bars under shipped width semantics PASS");return 0;}
'''
out=ROOT/'work/portable_feature_tests/scissor';out.mkdir(parents=True,exist_ok=True);p=out/'scissor.c';p.write_text(code)
u=lambda p:'/mnt/'+p.resolve().drive[0].lower()+p.resolve().as_posix()[2:]
r=subprocess.run(['wsl','gcc','-std=c11','-fsanitize=address,undefined',u(p),'-o',u(out/'scissor')],capture_output=True);assert not r.returncode,r.stderr
r=subprocess.run(['wsl',u(out/'scissor')],capture_output=True);(out/'RESULT.log').write_bytes(r.stdout+r.stderr);assert not r.returncode,r.stderr;print(r.stdout.decode())
