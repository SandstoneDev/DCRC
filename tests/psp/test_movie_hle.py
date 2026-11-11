"""Compile actual overlay-entry adapter with a controlled native backend."""
from pathlib import Path
import argparse,subprocess,json
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--wsl');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'hle/overlay/movie.c').read_text(encoding='utf8').replace('#include "../hle.h"','').replace('#include "movie.h"','')
    code=r'''
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
typedef struct {uint32_t r[16];} sh4_ctx;
static int hle_strict,native_calls,skip_logs;static int32_t native_result;static uint32_t last_id,entry;
static void (*registered)(sh4_ctx*);
#define HLE_ENTER(address,label) do {(void)(address);(void)(label);} while(0)
static void sa1_log(const char *s,...){(void)s;skip_logs++;}
static void sa1_register_fn(uint32_t address,void(*function)(sh4_ctx*)){entry=address;registered=function;}
'''+source+r'''
int32_t sa1_platform_movie_play(uint32_t id){native_calls++;last_id=id;return native_result;}
int main(void){
 hle_movie_init();assert(entry==0x8ceb0000u&&registered);
 sh4_ctx c;memset(&c,0x57,sizeof c);c.r[4]=0;native_result=1;registered(&c);
 assert(c.r[0]==1&&native_calls==1&&last_id==0);
 for(unsigned id=1;id<10;id++){c.r[4]=id;native_result=0;registered(&c);assert(c.r[0]==0&&last_id==id);}
 c.r[4]=0;native_result=-1;registered(&c);assert(c.r[0]==UINT32_MAX);
 int before=native_calls;hle_strict=1;native_result=1;registered(&c);assert(c.r[0]==UINT32_MAX&&native_calls==before);
 hle_strict=0;hle_movies_enabled=0;registered(&c);assert(c.r[0]==UINT32_MAX&&native_calls==before);
 for(unsigned i=1;i<16;i++)if(i!=4)assert(c.r[i]==0x57575757u);
 assert(skip_logs==2);puts("actual movie entry finish/skip/strict/config/register preservation PASS");return 0;
}
'''
    fixture=a.out/'movie_hle_actual.c';fixture.write_text(code,encoding='utf8')
    def path(p):
        s=str(p.resolve());return '/mnt/'+s[0].lower()+s[2:].replace('\\','/') if a.wsl else s
    lead=['wsl','-d',a.wsl,'--'] if a.wsl else [];exe=a.out/'movie_hle_actual'
    r=subprocess.run(lead+['gcc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',path(fixture),'-o',path(exe)],capture_output=True,text=True,encoding="utf8",errors="replace");assert not r.returncode,r.stderr
    r=subprocess.run(lead+[path(exe)],capture_output=True,text=True,encoding="utf8",errors="replace");assert not r.returncode,r.stderr
    (a.out/'VERIFIED.json').write_text(json.dumps(dict(status='PASS',stdout=r.stdout),indent=2),encoding='utf8');print(r.stdout.strip())
if __name__=='__main__':main()
