/* Kernel handoff for local tests. CFW mechanism validated in old DCRC;
 * bounded protocol and failure exit belong to this adapter. MIT. */
#include <pspkernel.h>
#include <psploadexec_kernel.h>
#include <pspinit.h>
#include <pspiofilemgr.h>
#include <stdio.h>
#include <string.h>
#include "chain_protocol.h"
PSP_MODULE_INFO("sa1chain",PSP_MODULE_KERNEL,1,0);
PSP_NO_CREATE_MAIN_THREAD();
int sctrlKernelLoadExecVSHWithApitype(int,const char *,struct SceKernelLoadExecVSHParam *);
static sa1_chain_args request;
static int stub_linked(void *fn) {
    uint32_t w=*(volatile uint32_t *)fn;
    if ((w>>26)!=2) return 0;
    uint32_t target=(((uint32_t)fn+4)&0xf0000000u)|((w&0x03ffffffu)<<2);
    return (target&0x7f000000u)==0x08000000u;
}
static void marker(const char *stage,int rc) {
    char path[256],line[96];strcpy(path,request.from);strcpy(path+strlen(path)-9,"chain.log");
    int n=snprintf(line,sizeof line,"SA1_CHAIN stage=%s rc=%08x\n",stage,(unsigned)rc);
    int fd=sceIoOpen(path,PSP_O_WRONLY|PSP_O_CREAT|PSP_O_APPEND,0666);
    if(fd>=0){if(n>0 && n<(int)sizeof line)sceIoWrite(fd,line,(unsigned)n);sceIoClose(fd);}
}
static int worker(SceSize n,void *p) {
    (void)n;(void)p;
    struct SceKernelLoadExecVSHParam param;memset(&param,0,sizeof param);
    param.size=sizeof param;param.args=strlen(request.next)+1;param.argp=request.next;param.key="game";
    marker("kernel_loadexec",0);
    int rc=sctrlKernelLoadExecVSHWithApitype(PSP_INIT_APITYPE_MS2,request.next,&param);
    marker("kernel_return_exit",rc);
    sceKernelExitGame(); /* any returned LoadExec is a failed transition */
    sceKernelExitDeleteThread(0);
    return 0;
}
int module_start(SceSize n,void *p) {
    if(!p || n!=sizeof request)return 1;
    memcpy(&request,p,sizeof request);
    if(!sa1_chain_request_valid(&request))return 1;
    if(!stub_linked((void *)sctrlKernelLoadExecVSHWithApitype))return 1;
    SceUID th=sceKernelCreateThread("sa1_chain",worker,0x10,0x2000,0,NULL);
    if(th<0)return 1;
    int rc=sceKernelStartThread(th,0,NULL);
    if(rc<0){sceKernelDeleteThread(th);return 1;}
    return 0;
}
int module_stop(SceSize n,void *p){(void)n;(void)p;return 0;}
