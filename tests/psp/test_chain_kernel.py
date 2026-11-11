"""Host-check actual kernel handoff body with deterministic SDK services (MIT).

Scope: only the MIPS import-stub instruction inspection is replaced by a
controlled boolean. This does not prove PSP import relocation, CFW LoadExec,
thread scheduling, FAT aliasing beyond ASCII case, or hardware transition.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'backend/psp/chain/chain_main.c').read_text()
source, count = re.subn(
    r'static int stub_linked\(void \*fn\) \{.*?^\}',
    'static int stub_linked(void *fn) { (void)fn; return test_linked; }',
    source, count=1, flags=re.S | re.M)
assert count == 1, 'MIPS-only stub inspection seam changed; review extraction'

stub = r'''
#ifndef TEST_PSP_H
#define TEST_PSP_H
#include <stdint.h>
#include <stddef.h>
typedef int SceUID; typedef unsigned SceSize;
struct SceKernelLoadExecVSHParam { SceSize size; SceSize args; void *argp; const char *key; };
#define PSP_MODULE_INFO(a,b,c,d)
#define PSP_NO_CREATE_MAIN_THREAD()
#define PSP_MODULE_KERNEL 0x1000
#define PSP_INIT_APITYPE_MS2 0x141
#define PSP_O_WRONLY 2
#define PSP_O_CREAT 0x200
#define PSP_O_APPEND 0x100
int sceIoOpen(const char *,int,int);
int sceIoWrite(int,const void *,unsigned);
int sceIoClose(int);
int sceKernelCreateThread(const char *,int (*)(SceSize,void *),int,int,unsigned,void *);
int sceKernelStartThread(int,SceSize,void *);
int sceKernelDeleteThread(int);
void sceKernelExitGame(void);
void sceKernelExitDeleteThread(int);
#endif
'''
harness = r'''
#include <stdio.h>
#include <string.h>
#include "pspkernel.h"
#include "chain_protocol.h"
static int checks,errors,test_linked,create_rc,start_rc,loadexec_rc,open_rc;
static int creates,starts,deletes,execs,exits,thread_exits,opens,writes,closes;
static int (*entry)(SceSize,void *);
static char events[128],logs[1024];
static const char *from="ms0:/PSP/GAME/DCRC_CURRENT/EBOOT.PBP";
static const char *next="ms0:/PSP/GAME/DCRC_NEXT/EBOOT.PBP";
static const char *expected_log="ms0:/PSP/GAME/DCRC_CURRENT/chain.log";
#define CHECK(x) do { checks++; if(!(x)){errors++;printf("FAIL line %d: %s\n",__LINE__,#x);} } while(0)
static void event(char c){size_t n=strlen(events);CHECK(n+1<sizeof events);events[n]=c;events[n+1]=0;}
int sceIoOpen(const char *p,int f,int m){CHECK(!strcmp(p,expected_log));CHECK(f==(PSP_O_WRONLY|PSP_O_CREAT|PSP_O_APPEND));CHECK(m==0666);opens++;return open_rc;}
int sceIoWrite(int fd,const void *p,unsigned n){CHECK(fd==3);CHECK(strlen(logs)+n<sizeof logs);strncat(logs,p,n);writes++;return (int)n;}
int sceIoClose(int fd){CHECK(fd==3);closes++;return 0;}
int sceKernelCreateThread(const char *name,int (*fn)(SceSize,void *),int priority,int stack,unsigned attr,void *opt){CHECK(!strcmp(name,"sa1_chain"));CHECK(priority==0x10&&stack==0x2000&&attr==0&&opt==NULL);creates++;entry=fn;return create_rc;}
int sceKernelStartThread(int th,SceSize n,void *p){CHECK(th==7&&n==0&&p==NULL);starts++;return start_rc;}
int sceKernelDeleteThread(int th){CHECK(th==7);deletes++;return 0;}
int sctrlKernelLoadExecVSHWithApitype(int api,const char *path,struct SceKernelLoadExecVSHParam *p){CHECK(api==PSP_INIT_APITYPE_MS2);CHECK(!strcmp(path,next));CHECK(p->size==sizeof *p);CHECK(p->args==strlen(next)+1);CHECK(!strcmp(p->argp,next));CHECK(!strcmp(p->key,"game"));execs++;event('L');return loadexec_rc;}
void sceKernelExitGame(void){exits++;event('G');}
void sceKernelExitDeleteThread(int code){CHECK(code==0);thread_exits++;event('D');}
#include "kernel_body.c"
static sa1_chain_args args;
static void reset(void){
 memset(&args,0,sizeof args);args.magic=SA1_CHAIN_MAGIC;strcpy(args.from,from);strcpy(args.next,next);
 test_linked=1;create_rc=7;start_rc=0;loadexec_rc=-123;open_rc=3;
 creates=starts=deletes=execs=exits=thread_exits=opens=writes=closes=0;entry=NULL;events[0]=logs[0]=0;
}
static void rejected(void){CHECK(module_start(sizeof args,&args)!=0);CHECK(creates==0&&starts==0&&execs==0&&opens==0&&deletes==0);}
int main(void){
 reset();CHECK(module_start(sizeof args,NULL)!=0);CHECK(module_start(sizeof args-1,&args)!=0);CHECK(module_start(sizeof args+1,&args)!=0);CHECK(creates==0);
 reset();args.magic^=1;rejected();
 reset();memset(args.from,'X',sizeof args.from);rejected();
 reset();memset(args.next,'X',sizeof args.next);rejected();
 reset();strcpy(args.next,"ms0:/PSP/GAME/OTHER/EBOOT.PBP");rejected();
 reset();strcpy(args.next,"ms0:/PSP/GAME/DCRC_../EBOOT.PBP");rejected();
 reset();strcpy(args.next,"ms0:/PSP/GAME/DCRC_A/B/EBOOT.PBP");rejected();
 reset();strcpy(args.next,from);rejected();
 reset();strcpy(args.next,"ms0:/PSP/GAME/DCRC_current/EBOOT.PBP");rejected();
 reset();test_linked=0;rejected();
 reset();create_rc=-5;CHECK(module_start(sizeof args,&args)!=0);CHECK(creates==1&&starts==0&&deletes==0&&execs==0);
 reset();start_rc=-6;CHECK(module_start(sizeof args,&args)!=0);CHECK(creates==1&&starts==1&&deletes==1&&execs==0&&exits==0);
 for(int rc=-1;rc<=1;rc++){
  reset();loadexec_rc=rc;CHECK(module_start(sizeof args,&args)==0);CHECK(creates==1&&starts==1&&deletes==0&&execs==0&&entry!=NULL);
  /* StartModule caller storage is not retained by the delayed worker. */
  memset(&args,0,sizeof args);CHECK(entry(0,NULL)==0);
  CHECK(execs==1&&exits==1&&thread_exits==1&&deletes==0);CHECK(!strcmp(events,"LGD"));
  CHECK(opens==2&&writes==2&&closes==2);CHECK(strstr(logs,"stage=kernel_loadexec")!=NULL);CHECK(strstr(logs,"stage=kernel_return_exit")!=NULL);
 }
 reset();open_rc=-1;CHECK(module_start(sizeof args,&args)==0);CHECK(entry(0,NULL)==0);CHECK(exits==1&&thread_exits==1&&opens==2&&writes==0&&closes==0);
 from="ms0:/PSP/GAME/sonictest/EBOOT.PBP";next=from;
 expected_log="ms0:/PSP/GAME/sonictest/chain.log";
 reset();args.magic=SA1_RESTART_MAGIC;
 CHECK(module_start(sizeof args,&args)==0);CHECK(creates==1&&starts==1&&entry!=NULL);
 memset(&args,0,sizeof args);CHECK(entry!=NULL&&entry(0,NULL)==0);
 CHECK(execs==1&&exits==1&&thread_exits==1&&opens==2&&writes==2&&closes==2);
 reset();args.magic=SA1_RESTART_MAGIC;
 strcpy(args.next,"ms0:/PSP/GAME/another_game/EBOOT.PBP");rejected();
 reset();rejected(); /* ordinary cross-app magic never permits this path */
 CHECK(module_stop(0,NULL)==0);
 printf("chain kernel actual body: %d checks, %d errors (MIPS stub check mocked)\n",checks,errors);return errors?1:0;
}
'''

# Verify the owning thread closes runtime resources before either handoff path.
main = (root / 'backend/psp/main_psp.c').read_text()
body = re.search(r'static void report_and_exit\(int code\) \{(.*?)^\}', main, re.S | re.M).group(1)
ordered = ['prof_stop();', 'plat_watchdog_stop()', 'draw_shutdown();',
           'audio_close();', 'sa1_chain_prepare(', 'reports_complete=1',
           'plat_log_close();', 'plat_files_close_all();', 'sa1_chain_launch(',
           'sceKernelExitGame();\n    exit(code);']
# Earlier failure branches close their own diagnostics before returning. The
# final occurrences belong to the ordinary fallthrough handoff path.
positions = [body.rindex(text) for text in ordered]
assert positions == sorted(positions), 'owner cleanup/report/chain ordering changed'
assert re.search(r'no_crash_screen\s*&&\s*prof\s*==\s*NULL', body)
with tempfile.TemporaryDirectory() as directory:
    p = Path(directory)
    for name in ['pspkernel.h', 'psploadexec_kernel.h', 'pspinit.h', 'pspiofilemgr.h']:
        (p / name).write_text(stub)
    (p / 'kernel_body.c').write_text(source)
    (p / 'test.c').write_text(harness)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra',
                    '-Werror', '-fsanitize=address,undefined', '-I'+str(p),
                    '-I'+str(root / 'backend/psp'), str(p / 'test.c'),
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
print('chain owner cleanup source contract PASS')
