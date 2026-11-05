"""Compile the actual PSP chain adapter with deterministic SDK services. MIT."""
from pathlib import Path
import os,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
stub=r'''
#ifndef TEST_PSP_H
#define TEST_PSP_H
#include <stdint.h>
#include <stddef.h>
typedef int SceUID; typedef unsigned SceSize;
typedef struct { unsigned st_mode; long long st_size; } SceIoStat;
struct SceKernelLoadExecParam { SceSize size;SceSize args;void *argp;char *key; };
#define PSP_O_WRONLY 2
#define PSP_O_CREAT 0x200
#define PSP_O_APPEND 0x100
int sceIoGetstat(const char *,SceIoStat *);
int sceIoOpen(const char *,int,int);int sceIoWrite(int,const void *,unsigned);int sceIoClose(int);
int kuKernelLoadModule(const char *,int,void *);
int sceKernelStartModule(int,unsigned,void *,int *,void *);
int sceKernelUnloadModule(int);
int sceKernelDelayThread(unsigned);
int sceKernelLoadExec(const char *,struct SceKernelLoadExecParam *);
#endif
'''
harness=r'''
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include "pspkernel.h"
static int checks,errors,exists=1,loadrc=7,startrc=0,statusrc=0,loads,starts,execs,delays,unloads;
static volatile int cancel;static int cancel_on_load,cancel_on_user_marker;
#define CHECK(x) do { checks++;if(!(x)){errors++;printf("FAIL line %d: %s\n",__LINE__,#x);} }while(0)
void sa1_log(const char *s,...) {(void)s;}
int sceIoGetstat(const char *p,SceIoStat *s){(void)p;s->st_size=12345;return exists?0:-1;}
int sceIoOpen(const char*p,int f,int m){(void)p;(void)f;(void)m;return 3;}
int sceIoWrite(int f,const void*p,unsigned n){(void)f;if(cancel_on_user_marker&&strstr((const char *)p,"stage=user_loadexec"))cancel=1;return n;}
int sceIoClose(int f){(void)f;return 0;}
int kuKernelLoadModule(const char*p,int f,void*x){(void)f;(void)x;CHECK(strstr(p,"/sa1chain.prx")!=NULL);loads++;if(cancel_on_load)cancel=1;return loadrc;}
int sceKernelStartModule(int m,unsigned n,void*p,int*s,void*x){(void)m;(void)n;(void)p;(void)x;starts++;*s=statusrc;return startrc;}
int sceKernelUnloadModule(int m){(void)m;unloads++;return 0;}
int sceKernelDelayThread(unsigned us){CHECK(us<=5000000);delays++;return 0;}
int sceKernelLoadExec(const char*p,struct SceKernelLoadExecParam*s){CHECK(!strcmp(p,"ms0:/PSP/GAME/DCRC_NEXT/EBOOT.PBP"));CHECK(s->args==strlen(p)+1);execs++;return -123;}
#include "CHAIN_SOURCE"
static const char *next="ms0:/PSP/GAME/DCRC_NEXT/EBOOT.PBP",*base="ms0:/PSP/GAME/DCRC_CURRENT";
static void reset(void){exists=1;loadrc=7;startrc=0;statusrc=0;loads=starts=execs=delays=unloads=0;cancel=0;cancel_on_load=0;cancel_on_user_marker=0;sa1_chain_set_next(NULL);}
int main(void){
 reset();CHECK(!sa1_chain_prepare(0,"time_limit",0,1,base));
 CHECK(sa1_chain_set_next("../outside/EBOOT.PBP")<0);CHECK(!sa1_chain_prepare(0,"time_limit",0,1,base));
 CHECK(sa1_chain_set_next(next)==0);
 CHECK(!sa1_chain_prepare(1,"time_limit",0,1,base));CHECK(!sa1_chain_prepare(0,"home",1,1,base));CHECK(!sa1_chain_prepare(0,"frame_limit",1,1,base));CHECK(!sa1_chain_prepare(0,"return",0,1,base));CHECK(!sa1_chain_prepare(0,"time_limit",0,0,base));
 exists=0;CHECK(!sa1_chain_prepare(0,"time_limit",0,1,base));exists=1;
 CHECK(!sa1_chain_prepare(0,"time_limit",0,1,"ms0:/PSP/GAME/OUTSIDE"));
 CHECK(!sa1_chain_prepare(0,"time_limit",0,1,"ms0:/PSP/GAME/DCRC_NEXT"));
 CHECK(sa1_chain_prepare(0,"time_limit",0,1,base));sa1_chain_launch(&cancel);CHECK(loads==1&&starts==1&&execs==0&&delays==1);
 reset();sa1_chain_set_next(next);CHECK(sa1_chain_prepare(0,"frame_limit",0,1,base));loadrc=-1;sa1_chain_launch(&cancel);CHECK(loads==1&&starts==0&&execs==1&&delays==0);
 reset();sa1_chain_set_next(next);CHECK(sa1_chain_prepare(0,"time_limit",0,1,base));statusrc=1;sa1_chain_launch(&cancel);CHECK(execs==1&&unloads==1&&delays==0);
 reset();sa1_chain_set_next(next);CHECK(sa1_chain_prepare(0,"time_limit",0,1,base));startrc=-2;sa1_chain_launch(&cancel);CHECK(execs==1&&unloads==1&&delays==0);
 reset();sa1_chain_launch(&cancel);CHECK(loads==0&&execs==0&&starts==0);
 reset();sa1_chain_set_next("ms0:/PSP/GAME/DCRC_current/EBOOT.PBP");CHECK(!sa1_chain_prepare(0,"time_limit",0,1,base));
 reset();sa1_chain_set_next(next);CHECK(sa1_chain_prepare(0,"time_limit",0,1,base));cancel=1;sa1_chain_launch(&cancel);CHECK(loads==0&&execs==0&&starts==0);
 reset();sa1_chain_set_next(next);CHECK(sa1_chain_prepare(0,"time_limit",0,1,base));cancel_on_load=1;sa1_chain_launch(&cancel);CHECK(loads==1&&unloads==1&&execs==0&&starts==0);
 reset();sa1_chain_set_next(next);CHECK(sa1_chain_prepare(0,"time_limit",0,1,base));loadrc=-1;cancel_on_user_marker=1;sa1_chain_launch(&cancel);CHECK(loads==1&&execs==0&&starts==0);
 printf("chain adapter: %d checks, %d errors\n",checks,errors);return errors?1:0;
}
'''.replace('CHAIN_SOURCE',str(root/'backend/psp/chain_psp.c'))
with tempfile.TemporaryDirectory() as d:
 p=Path(d)
 for name in ['pspkernel.h','pspiofilemgr.h','psploadexec.h','kubridge.h']:(p/name).write_text(stub)
 (p/'test.c').write_text(harness)
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+str(p),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
