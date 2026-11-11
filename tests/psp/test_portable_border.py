from pathlib import Path
import re,subprocess
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'backend/psp/draw_gu.c').read_text()
def f(n):
 m=re.search(r'(?m)^[^\n;{}]*\b'+n+r'\([^;{}]*\)\s*\{',s);a=m.start();i=s.index('{',a)+1;d=1
 while d:d+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]
body=f('border_draw')+'\n'+f('dither_restore_baseline');const=sorted(set(re.findall(r'\bGU_[A-Z0-9_]+\b',body)) - {'GU_TRUE','GU_FALSE'})
code=r'''#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#include "border_image.h"
#define GU_TRUE 1
#define GU_FALSE 0
#define SCR_W 480
#define SCR_H 272
#define LIST_BYTES 65536
'''+ '\n'.join('#define '+n+' '+str(i+2)for i,n in enumerate(const))+r'''
static int aspect_wide,headless,dither_active,gu_debug,sh,bound_tex,tex_flush_pending;
static float tex_su,tex_sv,lod_bias;
static uint8_t data[BORDER_IMAGE_BYTES],*border_pixels=data;
static unsigned used;static int no_memory,draws,resets,clip_x,clip_width,depth=1,dither=1,mask;
static border_image_vertex vertices[4];
static int sceGuCheckList(void){return used;}
static void *sceGuGetMemory(unsigned n){assert(n==sizeof vertices);return no_memory?0:vertices;}
static void sceGuScissor(int x,int y,int w,int h){assert(!y&&h==272);clip_x=x;clip_width=w;}
static void sceGuDisable(int x){if(x==GU_DEPTH_TEST)depth=0;if(x==GU_DITHER)dither=0;}
static void sceGuEnable(int x){if(x==GU_DEPTH_TEST)depth=1;if(x==GU_DITHER)dither=1;}
static void sceGuDepthMask(int x){mask=x;}
static void sceGuShadeModel(int x){(void)x;}
static void sceGuTexMode(int a,int b,int c,int d){assert(a==GU_PSM_5650&&!b&&!c&&!d);}
static void sceGuTexImage(int l,int w,int h,int stride,const void*p){assert(!l&&w==128&&h==512&&stride==128&&p==data);}
static void sceGuTexScale(float x,float y){assert(x==1&&y==1);}
static void sceGuTexOffset(float x,float y){assert(!x&&!y);}
static void sceGuTexLevelMode(int x,float y){(void)x;(void)y;}
static void sceGuTexFilter(int x,int y){assert(x==GU_NEAREST&&y==GU_NEAREST);}
static void sceGuTexWrap(int x,int y){assert(x==GU_CLAMP&&y==GU_CLAMP);}
static void sceGuTexFunc(int x,int y){assert(x==GU_TFX_REPLACE&&y==GU_TCC_RGB);}
static void sceGuTexFlush(void){}
static void sh_reset(int*p){(void)p;resets++;}
static void sceGuDrawArray(int type,int flags,int n,const void*index,const void*v){(void)flags;assert(type==GU_SPRITES&&n==4&&!index&&v==vertices&&!depth&&!dither&&mask);assert(vertices[0].x==0&&vertices[1].x==60&&vertices[2].x==420&&vertices[3].x==480);draws++;}
'''+f('dither_restore_baseline')+'\n'+f('border_draw')+r'''
int main(void){
 aspect_wide=1;border_draw();assert(!draws);aspect_wide=0;headless=1;border_draw();assert(!draws);headless=0;
 used=LIST_BYTES;border_draw();assert(!draws);used=0;no_memory=1;border_draw();assert(!draws);no_memory=0;
 border_draw();assert(draws==1&&resets==1&&depth&&dither&&!mask&&clip_x==60&&clip_width==360&&tex_flush_pending&&tex_su==-1&&tex_sv==-1);
 dither_active=2;border_draw();assert(draws==2&&!dither);puts("actual optional border guards/geometry/state/public scissor restoration PASS");return 0;
}
'''
out=ROOT/'work/portable_feature_tests/border';out.mkdir(parents=True,exist_ok=True);p=out/'border.c';p.write_text(code)
u=lambda p:'/mnt/'+p.resolve().drive[0].lower()+p.resolve().as_posix()[2:]
r=subprocess.run(['wsl','gcc','-std=c11','-fsanitize=address,undefined','-I'+u(ROOT/'backend'),u(p),'-o',u(out/'border')],capture_output=True);assert not r.returncode,r.stderr
r=subprocess.run(['wsl',u(out/'border')],capture_output=True);(out/'RESULT.log').write_bytes(r.stdout+r.stderr);assert not r.returncode,r.stderr;print(r.stdout.decode())
