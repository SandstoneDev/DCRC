#!/usr/bin/env python3
"""Actual temporary-allocation platform bodies with controlled libc/kernel endpoints."""
from pathlib import Path
import argparse,re,subprocess,json,hashlib
R=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=R/'backend/psp/platform_psp.c');p.add_argument('--out',type=Path,default=R/'work/C86_temp/host');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
s=a.source.read_text()
def fn(name):
 m=re.search(r'(?m)^[^\n;{}]*\b'+name+r'\([^;{}]*\)\s*\{',s)
 if not m:return None
 end=s.index('{',m.start())+1;d=1
 while d:d+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[m.start():end]
alloc=fn('sa1_plat_temp_alloc');release=fn('sa1_plat_temp_free')
fits=fn('temp_heap_fits')
baseline=alloc is None
if baseline:
 # Characterize the old call sites' malloc/free behavior before the API exists.
 alloc='void *sa1_plat_temp_alloc(uint32_t n,sa1_temp_block*b){ if(!b||b->ptr||!n||n>UINT32_MAX-63u)return NULL;b->uid=-1;return b->ptr=malloc(n);}'
 release='void sa1_plat_temp_free(sa1_temp_block*b){if(!b)return;free(b->ptr);b->ptr=NULL;b->uid=-1;}'
prefix=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
typedef int SceUID;
#define PSP_SMEM_Low 0
typedef struct{void*ptr;int32_t uid;}sa1_temp_block;
static uint32_t temp_heap,temp_partition,temp_fail,temp_active,temp_peak_active;
static unsigned checks,failures,heap_calls,heap_frees,kernel_calls,kernel_frees,head_calls;
static int deny_heap,deny_kernel,null_head,next_uid;
static uint8_t raw[131072];static uint32_t kernel_size;
#define CHECK(x)do{checks++;if(!(x)){failures++;printf("FAIL %d %s\n",__LINE__,#x);}}while(0)
static void*test_malloc(size_t n){heap_calls++;return deny_heap?NULL:malloc(n);}
static void test_free(void*p){if(p)heap_frees++;free(p);}
static int sceKernelAllocPartitionMemory(int partition,const char*name,int type,uint32_t bytes,void*addr){kernel_calls++;CHECK(partition==2);CHECK(name!=NULL);CHECK(type==PSP_SMEM_Low);CHECK(addr==NULL);kernel_size=bytes;return deny_kernel?-12:next_uid;}
static void*sceKernelGetBlockHeadAddr(int uid){head_calls++;CHECK(uid==next_uid);return null_head?NULL:raw+3;}
static int sceKernelFreePartitionMemory(int uid){kernel_frees++;CHECK(uid==next_uid);return 0;}
#define malloc test_malloc
#define free test_free
'''
suffix=r'''
#undef malloc
#undef free
int main(void){
 sa1_temp_block b={0,-1};void*p;
 p=sa1_plat_temp_alloc(8192,&b);CHECK(p!=NULL&&p==b.ptr&&b.uid==-1);CHECK(heap_calls==1&&kernel_calls==0);
 sa1_plat_temp_free(&b);CHECK(b.ptr==NULL&&b.uid==-1&&heap_frees==1&&kernel_frees==0);
 sa1_plat_temp_free(&b);CHECK(heap_frees==1&&kernel_frees==0);
 deny_heap=1;next_uid=0;
 p=sa1_plat_temp_alloc(32800,&b);CHECK(p!=NULL&&p==b.ptr&&b.uid==0);CHECK(kernel_calls==1&&head_calls==1);
 if(p){CHECK(((uintptr_t)p&63u)==0);CHECK((uint8_t*)p>=raw+3&&(uint8_t*)p+32800<=raw+3+kernel_size);memset(p,0xab,32800);}
 sa1_plat_temp_free(&b);CHECK(kernel_frees==1&&heap_frees==1&&b.ptr==NULL&&b.uid==-1);
 sa1_plat_temp_free(&b);CHECK(kernel_frees==1);
 next_uid=7;null_head=1;p=sa1_plat_temp_alloc(16388,&b);CHECK(p==NULL&&b.ptr==NULL&&b.uid==-1);CHECK(kernel_frees==2);
 null_head=0;deny_kernel=1;p=sa1_plat_temp_alloc(21760,&b);CHECK(p==NULL&&b.ptr==NULL&&b.uid==-1);CHECK(kernel_frees==2);
 deny_kernel=0;unsigned hc=heap_calls,kc=kernel_calls;
 CHECK(sa1_plat_temp_alloc(0,&b)==NULL);CHECK(sa1_plat_temp_alloc(UINT32_MAX,&b)==NULL);CHECK(heap_calls==hc&&kernel_calls==kc);
 CHECK(sa1_plat_temp_alloc(64,NULL)==NULL);
 deny_heap=0;p=sa1_plat_temp_alloc(32,&b);CHECK(p!=NULL);hc=heap_calls;kc=kernel_calls;
 CHECK(sa1_plat_temp_alloc(64,&b)==NULL&&b.ptr==p);CHECK(heap_calls==hc&&kernel_calls==kc);sa1_plat_temp_free(&b);
 sa1_plat_temp_free(NULL);
 printf("temp_memory: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
'''
unit=a.out/'temp_memory.c'
if 'desktop' in a.source.parts:
 suffix=r'''
#undef malloc
#undef free
int main(void){
 sa1_temp_block b={0,-1};void*p=sa1_plat_temp_alloc(32800,&b);
 CHECK(p!=NULL&&p==b.ptr&&b.uid==-1&&kernel_calls==0);if(p)memset(p,0xab,32800);
 CHECK(sa1_plat_temp_alloc(12,&b)==NULL&&b.ptr==p);
 sa1_plat_temp_free(&b);sa1_plat_temp_free(&b);CHECK(heap_frees==1&&b.ptr==NULL&&b.uid==-1);
 deny_heap=1;CHECK(sa1_plat_temp_alloc(32800,&b)==NULL&&b.ptr==NULL&&kernel_calls==0);
 unsigned n=heap_calls;CHECK(sa1_plat_temp_alloc(0,&b)==NULL);CHECK(sa1_plat_temp_alloc(UINT32_MAX,&b)==NULL);CHECK(sa1_plat_temp_alloc(1,NULL)==NULL);CHECK(n==heap_calls);sa1_plat_temp_free(NULL);
 printf("temp_memory_desktop: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
'''
if fits:
 suffix=suffix.replace('sa1_temp_block b={0,-1};void*p;', '''sa1_temp_block b={0,-1};void*p;
 CHECK(temp_heap_fits(0x08800000u,8192));
 CHECK(temp_heap_fits(0x0bfffff0u,16));
 CHECK(!temp_heap_fits(0x0bfffff0u,17));
 CHECK(!temp_heap_fits(0x0c000000u,1));
 CHECK(!temp_heap_fits(UINTPTR_MAX-4u,16));''')
unit.write_text(prefix+(fits or '')+alloc+'\n'+release+suffix)
binary=a.out/'temp_memory'
cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined',str(unit),'-o',str(binary)]
subprocess.run(cmd,check=True)
r=subprocess.run([str(binary)],capture_output=True,text=True)
(a.out/'temp_memory.log').write_text(r.stdout+r.stderr)
(a.out/'SOURCE.json').write_text(json.dumps(dict(source=str(a.source),sha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),heap_only_baseline=baseline,exit=r.returncode),indent=2))
print(r.stdout+r.stderr,end='');raise SystemExit(r.returncode)
