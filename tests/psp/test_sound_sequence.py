"""Actual SD/host/core integration, synthetic own sound-bank bytes only."""
from pathlib import Path
import argparse,re,subprocess,os
ROOT=Path(__file__).resolve().parents[2]
def unix(p):return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]if os.name=='nt' else p.as_posix()
def clean(p):return '\n'.join(l for l in p.read_text(encoding='utf8').splitlines()if not l.startswith('#include "'))
def main():
    a=argparse.ArgumentParser();a.add_argument('--out',type=Path,required=True);a.add_argument('--expect-red',action='store_true');a.add_argument('--core',type=Path);a.add_argument('--direct-only',action='store_true');args=a.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    prefix=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "snd_host.h"
static int hle_strict,worker_io,temp_deny,temp_calls;
static int (*io_probe)(void);
typedef struct {void *ptr;int32_t uid;} sa1_temp_block;
static void *sa1_plat_temp_alloc(uint32_t n,sa1_temp_block *b){temp_calls++;b->ptr=temp_deny?NULL:malloc(n);return b->ptr;}
static void sa1_plat_temp_free(sa1_temp_block *b){free(b->ptr);b->ptr=NULL;b->uid=-1;}
static uint64_t fake_us;
static uint32_t pushed;
static uint8_t guest[4096];
typedef struct {uint32_t r[16];} sh4_ctx;
#define HLE_ENTER(a,b) ((void)c,(void)(a),(void)(b))
#define ARG0 (c->r[4])
#define ARG1 (c->r[5])
#define ARG2 (c->r[6])
#define ARG3 (c->r[7])
#define STACK_ARG(i) (0u)
#define RET(x) (c->r[0]=(uint32_t)(x))
static uint32_t hle_rd8(uint32_t a){return guest[a%sizeof guest];}
static uint32_t hle_rd32(uint32_t a){return hle_rd8(a)|hle_rd8(a+1)<<8|hle_rd8(a+2)<<16|hle_rd8(a+3)<<24;}
static void hle_wr8(uint32_t a,uint32_t x){guest[a%sizeof guest]=(uint8_t)x;}
static void hle_wr32(uint32_t a,uint32_t x){for(int i=0;i<4;i++)hle_wr8(a+i,x>>(8*i));}
static void guest32(uint32_t a,uint32_t x){hle_wr32(a,x);}
static uint64_t sa1_plat_time_us(void){return fake_us;}
static void sa1_log(const char *f,...){(void)f;}
static int audio_open(uint32_t rate,uint32_t channels){return rate==44100&&channels==2?0:-1;}
static void audio_push(const int16_t *s,uint32_t n){(void)s;pushed+=n;}
static uint32_t audio_queued_frames(void){return 0;}
static int sa1_plat_file_read(const char *p,uint32_t off,void *out,uint32_t n){
 (void)p;if(worker_io)abort();if(io_probe)io_probe();if(off)return -1;uint8_t h[128]={0x80,0,0,60,3,18,4,1,0,0,0xac,0x44,0,6,0xba,0xa8,1,0xf4,3};
 h[27]=1;h[36]=0;h[37]=6;h[38]=0xba;h[39]=0xa8;if(n>128)n=128;memcpy(out,h,n);return n;
}
static int sa1_plat_file_read_stream(const char *p,uint32_t off,void *out,uint32_t n){(void)p;if(worker_io)abort();if(io_probe)io_probe();uint8_t *b=out;for(uint32_t i=0;i<n;i++){unsigned k=(off-64+i)%18;b[i]=k==0?0:k==1?1:0x11;}return n;}
void snd_adxt_report(void){}
'''
    code=('#define DIRECT_ONLY 1\n'if args.direct_only else'')+prefix+'\n#include <assert.h>\n'+clean(ROOT/'hle/sound/snd_host.c')+'\n'+clean(ROOT/'hle/sound/sd.c')+'\n'+clean(ROOT/'hle/state.c')+'\n'+(ROOT/'tests/sound/snd_sequence_test.c').read_text()
    c=out/'sequence_actual.c';c.write_text(code,encoding='utf8');exe=out/'sequence_actual';lead=['wsl','--']if os.name=='nt'else[]
    cmd=lead+['gcc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-parentheses','-fsanitize=address,undefined','-I'+unix(ROOT/'hle/sound'),'-I'+unix(ROOT/'hle'),unix(c),unix((args.core or ROOT/'hle/sound/snd_core.c').resolve()),unix(ROOT/'hle/sound/adx.c'),'-lm','-o',unix(exe)]
    cp=subprocess.run(cmd,capture_output=True,text=True,encoding="utf8",errors="replace");(out/'compile.log').write_text(cp.stdout+cp.stderr,encoding="utf8");assert cp.returncode==0,cp.stderr
    cp=subprocess.run(lead+[unix(exe)],capture_output=True,text=True,encoding="utf8",errors="replace",timeout=30);(out/('RED.log'if args.expect_red else'GREEN.log')).write_text(cp.stdout+cp.stderr,encoding="utf8")
    if args.expect_red:assert cp.returncode!=0 and ('FAIL sequence outputs audible PCM'in cp.stderr or 'direct_isolation'in cp.stderr);print('RED confirmed: existing sequence SDK stub fails required sequence/isolation contract')
    else:assert cp.returncode==0,cp.stdout+cp.stderr;print(cp.stdout.strip())
if __name__=='__main__':main()
