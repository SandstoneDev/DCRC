"""Compile the actual movie pause seam; synthetic SDK scheduling only."""
from pathlib import Path
import argparse,json,subprocess,os
ROOT=Path(__file__).resolve().parents[2]
def function(s,name):
    a=s.index(name+'(');a=s.rfind('\n',0,a)+1;b=s.index('{',a);n=1;i=b+1
    while n:
        n+=(s[i]=='{')-(s[i]=='}');i+=1
    return s[a:i]
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--wsl');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'backend/psp/audio_psp.c').read_text(encoding='utf8')
    code=r'''
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#define AUD_RING8192 8192u
#define AUD_RING AUD_RING8192
static int ch=0,th=2,run=1,sema=3,menu_paused,pause_ack,movie_pause_owned,output_busy;
static uint32_t wr=3000,rd=17,movie_discarded_frames;
static uint64_t now,menu_pause_start,menu_pause_total;
static int simulate_ack=1,simulate_busy,signals,delays;
static int audio_psp_out2=1,hardware_rest,query_error,rest_stuck,output2_queries,channel_queries;
static unsigned sceKernelCpuSuspendIntr(void){return 0;}
static void sceKernelCpuResumeIntr(unsigned n){(void)n;}
static uint64_t sa1_plat_time_us(void){return now;}
static int sceKernelSignalSema(int s,int n){assert(s==3&&n==1);signals++;return 0;}
static void sa1_log(const char *s,...){(void)s;}
static int sceAudioOutput2GetRestSample(void){output2_queries++;return query_error?-7:hardware_rest;}
static int sceAudioGetChannelRestLen(int c){assert(c==ch);channel_queries++;return query_error?-7:hardware_rest;}
static int sceKernelDelayThread(unsigned us){now+=us;delays++;if(simulate_ack){pause_ack=1;output_busy=simulate_busy;}if(hardware_rest&&!rest_stuck)hardware_rest--;return 0;}
'''+function(source,'audio_psp_pause')+'\n'+function(source,'audio_psp_movie_pause')+r'''
static void reset(void){ch=0;th=2;run=1;menu_paused=pause_ack=movie_pause_owned=output_busy=0;wr=3000;rd=17;now=0;movie_discarded_frames=0;simulate_ack=1;simulate_busy=0;signals=delays=0;audio_psp_out2=1;hardware_rest=query_error=rest_stuck=output2_queries=channel_queries=0;}
int main(void){
 reset();output_busy=1;assert(!audio_psp_movie_pause(1));
 assert(menu_paused&&pause_ack&&movie_pause_owned&&!output_busy&&rd==wr&&movie_discarded_frames==2983&&delays>0);
 assert(!audio_psp_movie_pause(1)&&movie_discarded_frames==2983);
 wr+=100;assert(!audio_psp_movie_pause(0));assert(!menu_paused&&!movie_pause_owned&&rd==wr&&movie_discarded_frames==3083);
 assert(!audio_psp_movie_pause(0));
 reset();simulate_ack=0;assert(audio_psp_movie_pause(1)<0);assert(!movie_pause_owned&&!menu_paused&&rd==17&&now==500000);
 reset();simulate_busy=1;assert(audio_psp_movie_pause(1)<0);assert(!movie_pause_owned&&!menu_paused&&rd==17);
 reset();menu_paused=1;assert(audio_psp_movie_pause(1)<0&&menu_paused&&delays==0&&rd==17);
 reset();ch=-1;assert(!audio_psp_movie_pause(1)&&!movie_pause_owned&&!menu_paused&&rd==17);
 reset();assert(!audio_psp_movie_pause(1));output_busy=1;assert(audio_psp_movie_pause(0)<0&&movie_pause_owned&&menu_paused);
 output_busy=0;assert(!audio_psp_movie_pause(0)&&!movie_pause_owned&&!menu_paused);
 reset();hardware_rest=3;assert(!audio_psp_movie_pause(1)&&output2_queries>=3&&!channel_queries&&now>=3000);assert(!audio_psp_movie_pause(0));
 reset();audio_psp_out2=0;hardware_rest=3;assert(!audio_psp_movie_pause(1)&&channel_queries>=3&&!output2_queries);assert(!audio_psp_movie_pause(0));
 reset();query_error=1;assert(audio_psp_movie_pause(1)<0&&!movie_pause_owned&&!menu_paused&&rd==17);
 reset();hardware_rest=3;rest_stuck=1;assert(audio_psp_movie_pause(1)<0&&!movie_pause_owned&&!menu_paused&&rd==17);
 puts("actual audio movie ACK/drain/stale-flush/timeout/ownership PASS");return 0;
}
'''
    fixture=a.out/'audio_movie_actual.c';fixture.write_text(code,encoding='utf8')
    def path(p):
        s=str(p.resolve());return '/mnt/'+s[0].lower()+s[2:].replace('\\','/') if a.wsl else s
    lead=['wsl','-d',a.wsl,'--'] if a.wsl else [];exe=a.out/'audio_movie_actual'
    result=subprocess.run(lead+['gcc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined',path(fixture),'-o',path(exe)],capture_output=True,text=True,encoding="utf8",errors="replace")
    assert result.returncode==0,result.stderr
    done=subprocess.run(lead+[path(exe)],capture_output=True,text=True,encoding="utf8",errors="replace");assert done.returncode==0,done.stderr
    # Removing either ACK or output-drain guard must make the same oracle fail.
    mutations=[]
    for name,needle,replacement in [('ack','while(!pause_ack||output_busy)','while(output_busy)'),('busy','while(!pause_ack||output_busy)','while(!pause_ack)'),('drain','if(!rest)break;','if(rest>=0)break;')]:
        assert needle in code
        bad=a.out/(name+'.c');bad.write_text(code.replace(needle,replacement),encoding='utf8');target=a.out/name
        r=subprocess.run(lead+['gcc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined',path(bad),'-o',path(target)],capture_output=True,text=True,encoding="utf8",errors="replace");assert not r.returncode,r.stderr
        r=subprocess.run(lead+[path(target)],capture_output=True,text=True,encoding="utf8",errors="replace");assert r.returncode!=0,name
        mutations.append(dict(name=name,killed=True))
    (a.out/'VERIFIED.json').write_text(json.dumps(dict(status='PASS',stdout=done.stdout,mutations=mutations),indent=2),encoding='utf8')
    print(done.stdout.strip(),'mutants',len(mutations))
if __name__=='__main__':main()
