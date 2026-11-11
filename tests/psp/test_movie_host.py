from pathlib import Path
import re,subprocess
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'backend/psp/main_psp.c').read_text()
def f(n):
 m=re.search(r'(?m)^[^\n;{}]*\b'+n+r'\([^;{}]*\)\s*\{',s);a=m.start();i=s.index('{',a)+1;d=1
 while d:d+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]
code=r'''#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#define PSP_POWER_TICK_ALL 0
static int captured,audio_fail,draw_fail,end_fail,pauses,resumes,begins,ends;
static int pace_set=1,movie_input_release,home_exit_requested,headless,hle_strict,audio_psp_enabled=1,snd_audio_enabled=1;
static void *load_path,*prof;static uint64_t time_limit_us,t0;
static int debug_psp_capture(void){return captured;}
static int audio_psp_movie_pause(int on){if(on){pauses++;return audio_fail?-1:0;}resumes++;return 0;}
static int draw_movie_begin(void){begins++;return draw_fail?-1:0;}
static int draw_movie_end(void){ends++;return end_fail?-1:0;}
static int draw_movie_present(const uint16_t*q,unsigned s){return q&&s==512?0:-1;}
static int scePowerTick(int x){(void)x;return 0;}
static uint64_t sa1_plat_time_us(void){return 100;}
'''+ '\n'.join(f(n)for n in ['movie_begin','movie_end','movie_present','movie_poll','movie_audio','movie_available'])+r'''
int main(void){
 captured=1;assert(movie_begin(0)<0&&!pauses&&!begins);captured=0;
 audio_fail=1;assert(movie_begin(0)<0&&pauses==1&&!begins);audio_fail=0;
 draw_fail=1;assert(movie_begin(0)<0&&resumes==1);draw_fail=0;
 assert(!movie_begin(0));int before=resumes;end_fail=1;assert(movie_end(0)<0&&resumes==before&&!movie_input_release);
 end_fail=0;assert(!movie_end(0)&&resumes==before+1&&!pace_set&&movie_input_release);
 assert(movie_audio(0));snd_audio_enabled=0;assert(!movie_audio(0));assert(movie_available(0));prof=(void*)1;assert(!movie_available(0));prof=0;
 time_limit_us=50;assert(movie_poll(0));time_limit_us=0;assert(!movie_poll(0));home_exit_requested=1;assert(movie_poll(0));
 puts("actual movie host rollback/end ownership/pacing/input quarantine guards PASS");
}
'''
out=ROOT/'work/portable_feature_tests/host';out.mkdir(parents=True,exist_ok=True);q=out/'host.c';q.write_text(code)
u=lambda p:'/mnt/'+p.resolve().drive[0].lower()+p.resolve().as_posix()[2:]
r=subprocess.run(['wsl','gcc','-std=c11','-fsanitize=address,undefined',u(q),'-o',u(out/'host')],capture_output=True);assert not r.returncode,r.stderr
r=subprocess.run(['wsl',u(out/'host')],capture_output=True);(out/'RESULT.log').write_bytes(r.stdout+r.stderr);assert not r.returncode,r.stderr;print(r.stdout.decode())
