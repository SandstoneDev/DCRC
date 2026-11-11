"""Actual public output-worker pause/resume scheduling; synthetic SDK only. MIT."""
from pathlib import Path
import argparse,subprocess,json,hashlib
ROOT=Path(__file__).resolve().parents[2]
def function(s,n):
 a=s.index(n+'(');a=s.rfind('\n',0,a)+1;i=s.index('{',a)+1;d=1
 while d:d+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--wsl');a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
 s=(ROOT/'backend/psp/audio_psp.c').read_text(encoding='utf8')
 code=r'''#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef unsigned SceSize;
#define AUD_BLOCK 1024u
#define AUD_RING 8192u
#define AUD_START 2048u
#define PSP_AUDIO_VOLUME_MAX 32768
static int16_t ring[2*AUD_RING],block[2][2*AUD_BLOCK];
static volatile uint32_t wr,rd;static volatile int run,waiting,menu_paused,pause_ack,output_busy;
static int sema=3,ch=1,audio_psp_out2;
static uint32_t starves,output_calls,output_errors;static uint64_t starve_us,wait_since,wait_pause_start,menu_pause_total,menu_pause_start,now;
static int hardware_calls,resumed,wait_calls,resume_ready,copy_checks;
static uint64_t sa1_plat_time_us(void){if(resumed&&hardware_calls==2)assert(pause_ack==0);return now;}
static unsigned sceKernelCpuSuspendIntr(void){return 0;}
static void sceKernelCpuResumeIntr(unsigned n){(void)n;}
static int sceKernelWaitSema(int s,int n,void*p){(void)p;assert(s==3&&n==1);wait_calls++;
 if(!resumed)menu_paused=1;else wr=rd+AUD_BLOCK;return 0;}
static int sceKernelDelayThread(unsigned us){now+=us;
 if(menu_paused&&!resumed){assert(pause_ack==1);resumed=1;menu_paused=0;if(resume_ready)wr=rd+AUD_BLOCK;}return 0;}
static uint64_t audio_unpaused_wait(uint64_t elapsed,uint64_t paused){return elapsed>paused?elapsed-paused:0;}
/* This is after the copy but BEFORE output_busy=1: the old stale ACK could
 * incorrectly let the owner retire the ring at this scheduling boundary. */
static void sceKernelDcacheWritebackRange(const void*p,unsigned n){assert((p==block[0]||p==block[1])&&n==sizeof block[0]);assert(pause_ack==0);copy_checks++;}
static int output(const void*p){assert((p==block[0]||p==block[1])&&output_busy&&pause_ack==0);hardware_calls++;if(hardware_calls==3)run=0;return 0;}
static int sceAudioOutput2OutputBlocking(int v,void*p){assert(v==PSP_AUDIO_VOLUME_MAX);return output(p);}
static int sceAudioOutputBlocking(int c,int v,void*p){assert(c==ch&&v==PSP_AUDIO_VOLUME_MAX);return output(p);}
'''+function(s,'pause_clock')+'\n'+function(s,'out_thread')+r'''
int main(void){for(int backend=0;backend<2;backend++)for(int ready=0;ready<2;ready++){
 audio_psp_out2=backend;resume_ready=ready;wr=AUD_START;rd=0;run=1;menu_paused=pause_ack=output_busy=0;
 resumed=wait_calls=hardware_calls=copy_checks=0;out_thread(0,NULL);
 assert(resumed&&hardware_calls==3&&copy_checks==3&&!pause_ack&&!output_busy);
 assert(wait_calls==(ready?1:2));}
 puts("actual audio worker resume-ready/starved ACK clearing both output APIs PASS");return 0;}
'''
 f=a.out/'worker.c';f.write_text(code,encoding='utf8');exe=a.out/'worker'
 def u(p):
  t=p.resolve().as_posix();return '/mnt/'+t[0].lower()+t[2:]if a.wsl else t
 lead=['wsl','-d',a.wsl,'--']if a.wsl else[]
 r=subprocess.run(lead+['gcc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',u(f),'-o',u(exe)],capture_output=True,text=True,encoding='utf8',errors='replace');(a.out/'compile.log').write_text(r.stdout+r.stderr,encoding='utf8');assert not r.returncode,r.stderr
 r=subprocess.run(lead+[u(exe)],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=30);(a.out/'RESULT.log').write_text(r.stdout+r.stderr,encoding='utf8');assert not r.returncode,r.stderr
 (a.out/'VERIFIED.json').write_text(json.dumps({'status':'PASS','source_sha256':hashlib.sha256((ROOT/'backend/psp/audio_psp.c').read_bytes()).hexdigest(),'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2),encoding='utf8');print(r.stdout.strip())
if __name__=='__main__':main()
