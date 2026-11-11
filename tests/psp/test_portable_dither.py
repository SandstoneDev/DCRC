from pathlib import Path
import subprocess,re
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'backend/psp/draw_gu.c').read_text()
def fun(name):
 m=re.search(r'(?m)^[^\n;{}]*\b'+name+r'\([^;{}]*\)\s*\{',s);a=m.start();b=s.index('{',a);i=b+1;d=1
 while d:d+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]
code=r'''#include <stdint.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
#define GU_DITHER 1
#define SH_DITHER 0
static struct {int v[1];} sh;
static int dither_requested,dither_active,dither_restore_pending,state=1,commands;
static void sceGuEnable(int x){assert(x==GU_DITHER);state=1;commands++;}
static void sceGuDisable(int x){assert(x==GU_DITHER);state=0;commands++;}
static void sh_enable(int k,int on){assert(k==SH_DITHER);if(sh.v[k]!=on){sh.v[k]=on;if(on)sceGuEnable(GU_DITHER);else sceGuDisable(GU_DITHER);}}
'''+ '\n'.join(fun(n)for n in ['draw_gu_set_dither','dither_latch','dither_restore_baseline','dither_clear_policy','sh_dither_draw'])+r'''
int main(void){
 assert(draw_gu_set_dither("on"));dither_latch();dither_clear_policy();sh_dither_draw(1);sh_dither_draw(0);assert(state&&commands==0);
 assert(draw_gu_set_dither("opaque"));assert(dither_requested==1);dither_latch();dither_clear_policy();assert(state);
 sh.v[0]=-1;sh_dither_draw(1);assert(state);sh_dither_draw(0);assert(!state);sh_dither_draw(1);assert(state);
 assert(draw_gu_set_dither("off"));dither_latch();dither_clear_policy();assert(!state);sh.v[0]=-1;sh_dither_draw(1);assert(!state);
 assert(draw_gu_set_dither("on"));dither_latch();dither_clear_policy();assert(state);int before=commands;sh_dither_draw(0);assert(state&&commands==before);
 assert(!draw_gu_set_dither("x"));puts("actual portable dither modes/state/default stream PASS");
}
'''
# Actual model CALL consumer with only allocation/geometry production stubbed;
# its policy stamp is extracted from the real producer's final statements.
stamp=re.search(r'g->list_epoch = tex_epoch; g->list_ok = [^;]+;',s).group(0)
model=r'''
static unsigned tex_epoch=7,tex_flush_pending,bound_tex;static float tex_su,tex_sv;
static int builds,merges;
typedef struct {int sets,list_ok,sh_end;unsigned list_epoch,tex_end;float su_end,sv_end;unsigned *list;} gmodel;
static gmodel gmodels[1];static unsigned words[64];
static struct {unsigned *current;} storage,*gu_list=&storage;
static void sceGuTexFlush(void){}
static void sh_merge(const int*p){(void)p;merges++;}
static void model_build_list(gmodel*g){builds++;
'''+stamp+r'''}
'''+fun('model_call')
out=ROOT/'work/portable_feature_tests/dither';out.mkdir(parents=True,exist_ok=True);f=out/'parser.c';code=code.replace('int main(void)','int dither_checks(void)')+model+'''\nint main(void){dither_checks();gmodels[0].sets=1;gmodels[0].list=words;storage.current=words;dither_active=0;model_call(0);assert(builds==1&&gmodels[0].list_ok==1);model_call(0);assert(builds==1);dither_active=1;model_call(0);assert(builds==2&&gmodels[0].list_ok==2);dither_active=2;model_call(0);assert(builds==3&&gmodels[0].list_ok==3);tex_epoch++;model_call(0);assert(builds==4);puts("actual cached CALL policy invalidation PASS");return 0;}\n''';f.write_text(code)
u=lambda p:'/mnt/'+p.resolve().drive[0].lower()+p.resolve().as_posix()[2:]
r=subprocess.run(['wsl','gcc','-std=c11','-fsanitize=address,undefined',u(f),'-o',u(out/'parser')],capture_output=True);assert not r.returncode,r.stderr
r=subprocess.run(['wsl',u(out/'parser')],capture_output=True);(out/'RESULT.log').write_bytes(r.stdout+r.stderr);assert not r.returncode,r.stderr
print(r.stdout.decode())

# Omitting policy from cached CALL admission must be caught by the same oracle.
needle='g->list_ok != dither_active+1 || '
assert needle in code
bad=out/'cache_policy_mutant.c';bad.write_text(code.replace(needle,''))
r=subprocess.run(['wsl','gcc','-std=c11','-fsanitize=address,undefined',u(bad),'-o',u(out/'cache_policy_mutant')],capture_output=True);assert not r.returncode,r.stderr
r=subprocess.run(['wsl',u(out/'cache_policy_mutant')],capture_output=True);(out/'MUTANT.log').write_bytes(r.stdout+r.stderr);assert r.returncode!=0
print('cached CALL policy semantic mutant rejected')
