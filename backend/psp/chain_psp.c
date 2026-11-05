/* Uses the CFW LoadExecVSH route established by the owner's DCRC tests.
 * No launch happens until the owning thread has closed every report. MIT. */
#include "chain_psp.h"
#include "chain_protocol.h"
#include <pspkernel.h>
#include <pspiofilemgr.h>
#include <psploadexec.h>
#include <kubridge.h>
#include <stdio.h>
#include <string.h>
void sa1_log(const char *fmt,...);
static sa1_chain_args request;
static char module_path[256];
static int ready, invalid;

int sa1_chain_set_next(const char *path) {
    ready=0; request.next[0]=0; invalid=0;
    request.magic=SA1_CHAIN_MAGIC;
    if (!path) return 0;
    if (!sa1_chain_path_valid(path)) { invalid=1; return -1; }
    strcpy(request.next,path); return 0;
}
int sa1_chain_set_restart(const char *base) {
    char path[256];
    int n=snprintf(path,sizeof path,"%s/EBOOT.PBP",base?base:"");
    if(n<0 || n>=(int)sizeof path || sa1_chain_set_next(path)<0) return -1;
    request.magic=SA1_RESTART_MAGIC;
    return 0;
}
int sa1_chain_prepare(int code,const char *reason,int home,int modules_safe,const char *base) {
    ready=0;
    if (invalid) { sa1_log("chain: declined invalid next path"); return 0; }
    if (!request.next[0]) return 0;
    int restart=request.magic==SA1_RESTART_MAGIC;
    if (code || home || !reason || (restart ? strcmp(reason,"menu_restart") :
        (strcmp(reason,"time_limit") && strcmp(reason,"frame_limit")))) {
        sa1_log("chain: stopped (exit is not a successful time/frame limit)"); return 0;
    }
    if (!modules_safe) { sa1_log("chain: declined (requires --no-crash-screen and no profiler)"); return 0; }
    int n=snprintf(request.from,sizeof request.from,"%s/EBOOT.PBP",base?base:"");
    int m=snprintf(module_path,sizeof module_path,"%s/sa1chain.prx",base?base:"");
    if (n<0 || n>=(int)sizeof request.from || m<0 || m>=(int)sizeof module_path
        || !sa1_chain_request_valid(&request)) {
        sa1_log("chain: declined current/self path"); return 0;
    }
    SceIoStat st;
    if (sceIoGetstat(request.next,&st)<0 || st.st_size<8 || sceIoGetstat(module_path,&st)<0 || st.st_size<8) {
        sa1_log("chain: declined missing next EBOOT/helper"); return 0;
    }
    ready=1;
    sa1_log("chain: next %s (launch after reports close)",request.next);
    return 1;
}
/* This separate, closed-per-marker log remains usable after plat_log_close. */
static void marker(const char *stage,int rc) {
    char path[256],line[96]; strcpy(path,request.from);
    strcpy(path+strlen(path)-9,"chain.log");
    int n=snprintf(line,sizeof line,"SA1_CHAIN stage=%s rc=%08x\n",stage,(unsigned)rc);
    int fd=sceIoOpen(path,PSP_O_WRONLY|PSP_O_CREAT|PSP_O_APPEND,0666);
    if (fd>=0) { if(n>0 && n<(int)sizeof line)sceIoWrite(fd,line,(unsigned)n); sceIoClose(fd); }
}
void sa1_chain_launch(const volatile int *cancel) {
    if (!ready) return;
    ready=0;
    if (cancel && *cancel) return;
    int status=-1, mod=kuKernelLoadModule(module_path,0,NULL), start=-1;
    marker("kernel_load",mod);
    if (cancel && *cancel) { if(mod>=0)sceKernelUnloadModule(mod); marker("home_cancel",0); return; }
    /* This last cancellation check commits the handoff. A started kernel
     * worker cannot safely be replaced by a competing LoadExec request. */
    if (mod>=0) start=sceKernelStartModule(mod,sizeof request,&request,&status,NULL);
    /* The worker may replace this process before StartModule returns. */
    if (mod>=0 && start>=0 && status==0) {
        marker("worker_accepted",status);
        sceKernelDelayThread(5000000);
        marker("worker_timeout_exit",0);
        return; /* caller uses ExitGame; never compete with another LoadExec */
    }
    marker("kernel_refused",mod<0?mod:(start<0?start:status));
    if (mod>=0) sceKernelUnloadModule(mod);
    if (cancel && *cancel) { marker("home_cancel",0); return; }
    struct SceKernelLoadExecParam p; memset(&p,0,sizeof p);
    p.size=sizeof p; p.args=strlen(request.next)+1; p.argp=request.next;
    marker("user_loadexec",0);
    if (cancel && *cancel) { marker("home_cancel",0); return; }
    int rc=sceKernelLoadExec(request.next,&p);
    marker("user_return_exit",rc);
}
