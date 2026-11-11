"""Actual renderer-owned movie functions against synthetic GU/GE state."""
from pathlib import Path
import argparse,subprocess,json,re,hashlib
ROOT=Path(__file__).resolve().parents[2]
def function(s,name):
    a=s.index(name+'(');a=s.rfind('\n',0,a)+1;b=s.index('{',a);n=1;i=b+1
    while n:n+=(s[i]=='{')-(s[i]=='}');i+=1
    return s[a:i]
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--wsl');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'backend/psp/draw_gu.c').read_text(encoding='utf8')
    # Keep the existing ownership/restore oracle at default on, and supply
    # actual renderer dependencies rather than duplicating diagnostic policy.
    helpers='\n'.join(function(source,n) for n in ('dither_restore_baseline','dither_clear_policy'))
    body=helpers+'\n'+'\n'.join(function(source,n) for n in ('draw_movie_begin','draw_movie_present','draw_movie_end'))
    constants=sorted((set(re.findall(r'\bGU_[A-Z0-9_]+\b',body)) | {'GU_DEPTH_TEST','GU_DITHER','GU_PSM_5650','GU_CLAMP','GU_TFX_REPLACE','GU_TCC_RGB','GU_SPRITES','GU_LINEAR','GU_NEAREST'}) - {'GU_TRUE','GU_FALSE'})
    definitions='\n'.join('#define '+n+' '+str(i+2) for i,n in enumerate(constants))
    code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "movie_layout.h"
#define SCR_W480 480
#define SCR_W SCR_W480
#define SCR_H272 272
#define SCR_H SCR_H272
#define BUF_W512 512
#define BUF_W BUF_W512
#define FB_BYTES (512*272*2)
#define LIST_BYTES (640*1024)
#define GU_TRUE 1
#define GU_FALSE 0
'''+definitions+r'''
static int headless,list_open,movie_display_active,aspect_wide,gu_debug;
static int draw_debug_ui_live(void){return 0;}
static int dither_active=0,dither_restore_pending;
static float lod_bias;
static int swap_pending,swap_vcount,list_cached,draw_fb,display_counts,tex_flush_pending;
static int ended,drains,syncs,fail_sync_at,starts,draws,swaps,resets,untracked,images,memcalls,fail_mem_at;
static int depth,dither,mask,filter,clip_x,clip_width,texheight;
static uint8_t memory[8192];static unsigned memory_used;static uint8_t *picture;
static void draw_end_frame(void){ended++;list_open=0;}
static void ge_wait(void){drains++;}
static int sceGuSync(int x,int y){(void)x;(void)y;syncs++;return fail_sync_at==syncs?-1:0;}
static void draw_debug_reset_meter(void){resets++;}
static int sceDisplayGetVcount(void){return 10;}
static int sceDisplayWaitVblankStart(void){return 0;}
static void display_observe(void){}
static unsigned sceKernelCpuSuspendIntr(void){return 0;}
static void sceKernelCpuResumeIntr(unsigned x){(void)x;}
static void dc_untracked_reuse(int *x){(void)x;untracked++;}
static void list_start(void){starts++;memory_used=0;}
static void sceGuScissor(int x,int y,int width,int height){assert(y==0&&height==272);clip_x=x;clip_width=width;}
static void sceGuDepthMask(int x){mask=x;}
static void sceGuClearColor(unsigned x){(void)x;}
static void sceGuClearDepth(unsigned x){(void)x;}
static void sceGuClear(int x){(void)x;}
static void border_draw(void){}
static void sceGuDisable(int x){if(x==GU_DEPTH_TEST)depth=0;if(x==GU_DITHER)dither=0;}
static void sceGuEnable(int x){if(x==GU_DEPTH_TEST)depth=1;if(x==GU_DITHER)dither=1;}
static void sceGuShadeModel(int x){(void)x;}
static void sceGuTexMode(int a,int b,int c,int d){assert(a==GU_PSM_5650&&b==0&&c==0&&d==0);}
static void sceGuTexScale(float x,float y){assert(x==1&&y==1);}
static void sceGuTexOffset(float x,float y){assert(!x&&!y);}
static void sceGuTexLevelMode(int x,float y){(void)x;(void)y;}
static void sceGuTexFilter(int x,int y){assert(x==y);filter=x;}
static void sceGuTexWrap(int x,int y){assert(x==GU_CLAMP&&y==GU_CLAMP);}
static void sceGuTexFunc(int x,int y){assert(x==GU_TFX_REPLACE&&y==GU_TCC_RGB);}
static int sceGuCheckList(void){return (int)memory_used;}
static void *sceGuGetMemory(unsigned n){memcalls++;if(memcalls==fail_mem_at)return NULL;assert(memory_used+n<=sizeof memory);void *p=memory+memory_used;memory_used+=n;return p;}
static void sceGuTexImage(int level,int width,int height,int stride,const void *p){
 assert(!level&&width==512&&stride==512);assert(height==256||height==16);
 assert((const uint8_t*)p>=picture&&(const uint8_t*)p+height*stride*2<=picture+512*272*2);
 assert((const uint8_t*)p==picture+(height==16?512*256*2:0));images++;texheight=height;
}
static void sceGuTexFlush(void){}
static void sceGuDrawArray(int type,int flags,int n,const void *ix,const void *p){
 (void)flags;assert(type==GU_SPRITES&&n==32&&!ix&&p);assert(!depth&&!dither&&mask&&clip_x==0&&clip_width==480);
 assert(filter==(aspect_wide?GU_LINEAR:GU_NEAREST));const movie_sprite *v=p;assert(v[0].v==0&&v[31].v==texheight);draws++;
}
static void play_list_check(unsigned n){assert(n<LIST_BYTES);}
static void sceGuFinish(void){}
static void sceKernelDcacheWritebackAll(void){}
static void sceGuSwapBuffers(void){swaps++;}
'''+body+r'''
int main(void){
 picture=calloc(1,512*272*2);assert(picture);
 headless=1;assert(draw_movie_begin()<0&&!starts);headless=0;list_open=1;
 assert(!draw_movie_begin()&&ended==1&&movie_display_active&&drains>0);assert(draw_movie_begin()<0);
 assert(draw_movie_present((const uint16_t*)picture,511)<0&&!draws);
 for(aspect_wide=0;aspect_wide<2;aspect_wide++){
  assert(!draw_movie_present((const uint16_t*)picture,512));assert(dither&&depth&&!mask);
  assert(!draw_movie_end()&&!movie_display_active&&tex_flush_pending);
  assert(clip_x==(aspect_wide?0:60)&&clip_width==(aspect_wide?480:360));
  assert(!draw_movie_begin());
 }
 assert(draws==4&&images==4&&swaps==2&&untracked==2);
 fail_mem_at=memcalls+2;int oldswap=swaps;
 assert(draw_movie_present((const uint16_t*)picture,512)<0&&swaps==oldswap);
 fail_mem_at=0;fail_sync_at=syncs+1;assert(draw_movie_end()<0&&movie_display_active);
 fail_sync_at=0;assert(!draw_movie_end()&&!movie_display_active);
 assert(!draw_movie_begin());fail_sync_at=syncs+2;
 assert(draw_movie_end()<0&&movie_display_active);fail_sync_at=0;assert(!draw_movie_end());
 free(picture);puts("actual movie display bands/restore/ownership failure+retry PASS");return 0;
}
'''
    fixture=a.out/'movie_display_actual.c';fixture.write_text(code,encoding='utf8')
    def path(p):
        s=str(p.resolve());return '/mnt/'+s[0].lower()+s[2:].replace('\\','/') if a.wsl else s
    lead=['wsl','-d',a.wsl,'--'] if a.wsl else [];exe=a.out/'movie_display_actual'
    r=subprocess.run(lead+['gcc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-I'+path(ROOT/'backend'),path(fixture),'-o',path(exe)],capture_output=True,text=True,encoding="utf8",errors="replace");assert not r.returncode,r.stderr
    r=subprocess.run(lead+[path(exe)],capture_output=True,text=True,encoding="utf8",errors="replace");assert not r.returncode,r.stderr
    (a.out/'VERIFIED.json').write_text(json.dumps(dict(status='PASS',stdout=r.stdout,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        dither_helpers_sha256=hashlib.sha256(helpers.encode()).hexdigest(),
        dither_mode='default on; actual renderer helpers'),indent=2),encoding='utf8');print(r.stdout.strip())
if __name__=='__main__':main()
