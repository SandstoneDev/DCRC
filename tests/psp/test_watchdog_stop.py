#!/usr/bin/env python3
"""Exercise the actual crash_psp.c watchdog section with host SDK stubs.

No PSP build or game data. Run under a host with cc + pthreads:
  python3 tests/psp/test_watchdog_stop.py
Outputs stay in ignored work/C82_watchdog_stop. Part of sa1-psp (MIT).
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work/C82_watchdog_stop"
OUT.mkdir(parents=True, exist_ok=True)
source = (ROOT / "backend/psp/crash_psp.c").read_text()
watchdog = source[source.index("static uint32_t (*wd_frame)"):]
prefix = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <stdlib.h>
typedef unsigned SceSize;
typedef unsigned SceUInt;
typedef int SceUID;
int plat_watchdog_stop(void);
int sceKernelDelayThread(unsigned);
int sceKernelCreateThread(const char *,int (*)(SceSize,void *),int,int,int,void *);
int sceKernelStartThread(int,unsigned,void *);
int sceKernelWaitThreadEnd(int,SceUInt *);
int sceKernelDeleteThread(int);
void sa1_log(const char *,...);
void plat_log_flush(void);
'''
suffix = r'''
static pthread_t worker;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed=PTHREAD_COND_INITIALIZER;
static int sleeping, release_delay, active, delays, failures;
static int creates, starts, waits, deletes, reads, logs, flushes;
static int create_result=7, start_result, wait_result, delete_result;
static int (*entry)(SceSize,void *);
#define CHECK(x) do { if (!(x)) { printf("FAIL line %d: %s\n",__LINE__,#x); failures++; } } while(0)
static uint32_t frame(void) { reads++; return 9; }
void sa1_log(const char *f,...) { (void)f; logs++; }
void plat_log_flush(void) { flushes++; }
static void *run(void *p) { (void)p; entry(0,NULL); return NULL; }
int sceKernelCreateThread(const char *n,int (*f)(SceSize,void *),int p,int s,int a,void *o) {
 (void)n;(void)p;(void)s;(void)a;(void)o;creates++;entry=f;return create_result;
}
int sceKernelStartThread(int id,unsigned n,void *p) {
 (void)n;(void)p;CHECK(id==7);starts++;
 if(start_result<0)return start_result;
 active=1; CHECK(pthread_create(&worker,NULL,run,NULL)==0);return 0;
}
int sceKernelDelayThread(unsigned delay) {
 CHECK(delay==1000000);
 /* A bad old infinite loop exits on its second delay, so RED terminates
  * instead of hanging the host runner after its forbidden postwake work. */
 if(++delays>1)pthread_exit(NULL);
 pthread_mutex_lock(&lock);sleeping=1;pthread_cond_broadcast(&changed);
 while(!release_delay)pthread_cond_wait(&changed,&lock);
 pthread_mutex_unlock(&lock);return 0;
}
int sceKernelWaitThreadEnd(int id,SceUInt *timeout) {
 CHECK(id==7);CHECK(timeout && *timeout==1500000);waits++;
 if(wait_result<0)return wait_result;
 pthread_mutex_lock(&lock);release_delay=1;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&lock);
 if(active){CHECK(pthread_join(worker,NULL)==0);active=0;}return 0;
}
int sceKernelDeleteThread(int id) { CHECK(id==7);CHECK(!active);deletes++;return delete_result; }
static void start(void) {
 plat_watchdog_start(frame,1);
 if(active){pthread_mutex_lock(&lock);while(!sleeping)pthread_cond_wait(&changed,&lock);pthread_mutex_unlock(&lock);}
}
int main(int argc,char **argv) {
 CHECK(argc==2);const char *mode=argv[1];
 CHECK(plat_watchdog_stop()==0);CHECK(plat_watchdog_stop()==0);
 CHECK(waits==0 && deletes==0);
 if(!strcmp(mode,"create-fail")) {
  create_result=-11;start();CHECK(creates==1 && starts==0);
  CHECK(plat_watchdog_stop()==0 && waits==0 && deletes==0);
 } else if(!strcmp(mode,"start-fail")) {
  start_result=-22;start();CHECK(starts==1 && deletes==1 && !active);
  CHECK(plat_watchdog_stop()==0 && waits==0 && deletes==1);
 } else if(!strcmp(mode,"start-delete-fail")) {
  start_result=-22;delete_result=-55;start();CHECK(deletes==1 && !active);
  CHECK(plat_watchdog_stop()==-55 && waits==0 && deletes==2);
  delete_result=0;CHECK(plat_watchdog_stop()==0 && deletes==3);
 } else {
  start();CHECK(reads==1 && sleeping && logs==0 && flushes==0);
  if(!strcmp(mode,"wait-fail")) {
   wait_result=-44;CHECK(plat_watchdog_stop()==-44);CHECK(waits==1 && deletes==0 && active);
   wait_result=0;
  }
  if(!strcmp(mode,"delete-fail")) {
   delete_result=-55;CHECK(plat_watchdog_stop()==-55);CHECK(waits==1 && deletes==1 && !active);
   delete_result=0;
  }
  CHECK(plat_watchdog_stop()==0);
  CHECK(!active && reads==1 && logs==0 && flushes==0 && delays==1);
  CHECK(waits==(!strcmp(mode,"wait-fail")?2:1));
  CHECK(deletes==(!strcmp(mode,"delete-fail")?2:1));
  int w=waits,d=deletes;CHECK(plat_watchdog_stop()==0);CHECK(waits==w && deletes==d);
 }
 printf("watchdog_stop %s: failures=%d\n",mode,failures);
 return failures?1:0;
}
'''
harness = OUT / "watchdog_host.c"
harness.write_text(prefix + watchdog + suffix)
exe = OUT / "watchdog_host"
compile_run = subprocess.run([
    "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pthread",
    "-fsanitize=address,undefined", "-fno-omit-frame-pointer", str(harness), "-o", str(exe)
], text=True, capture_output=True)
output = compile_run.stdout + compile_run.stderr
failed = compile_run.returncode != 0
if not failed:
    for mode in ("normal", "create-fail", "start-fail", "start-delete-fail", "wait-fail", "delete-fail"):
        run = subprocess.run([str(exe), mode], text=True, capture_output=True, timeout=10)
        output += run.stdout + run.stderr + f"exit={run.returncode}\n"
        failed |= run.returncode != 0
print(output, end="")
(OUT / "latest.log").write_text(output)
raise SystemExit(1 if failed else 0)
