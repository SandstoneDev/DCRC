/* Own synthetic recording contract; no game bytes. Copyright2026 SandstoneDev, MIT. */
#include "hle.h"
#include "input_tape.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

uint8_t *const sa1_ram=NULL; /* No guest-memory checks are requested. */
hle_pad hle_pad_state;
int hle_strict,hle_aspect_wide=1;
int64_t hle_rtc_epoch;
static uint32_t frame;
uint32_t hle_frame_count(void){return frame;}
void sa1_log(const char *fmt,...){(void)fmt;}

/* Run one case per process, as input_tape's ordinary application lifetime. */
int main(int argc,char **argv){
    assert(argc==5 || argc==6);
    const char *mode=argv[1],*title=argv[2],*out=argv[3];
    int zero=!strcmp(mode,"zero"),wide=!strcmp(mode,"wide");
    int combined=!strcmp(mode,"combined");
    char *args[]={"own-test","--record",(char*)out,"--replay",argc==6?argv[5]:NULL};
    int count=combined?5:3;
    for(int i=1;i<count;i++)assert(input_tape_arg(count,args,&i));
    assert(!input_tape_start(title));assert(hle_strict);
    if(combined){assert(input_tape_aspect_wide()==0);hle_aspect_wide=input_tape_aspect_wide();}
    else hle_aspect_wide=wide; /* Effective INI/CLI selection AFTER start. */
    if(!zero){
        for(frame=1;frame<=2;frame++){
            uint32_t buttons=input_tape_pad(frame,8,0);
            if(combined)assert(buttons==0x20 && hle_pad_state.x==-4 && hle_pad_state.y==6);
            else assert(buttons==8);
            if(frame==1)hle_aspect_wide=!wide; /* Header must be written exactly once. */
        }
        frame=2;
    }
    assert(!input_tape_finish(0,NULL));
    FILE *f=fopen(out,"rb");assert(f);char text[4096];size_t n=fread(text,1,sizeof text-1,f);
    assert(!ferror(f)&&!fclose(f));text[n]=0;
    char *aspect=strstr(text,wide?"\naspect wide\n":"\naspect 4:3\n");assert(aspect);
    assert(!strstr(aspect+1,"\naspect "));
    char *end=strstr(text,zero?"\nend 0\n":"\nend 2\n");assert(end&&aspect<end);
    if(!zero){
        char *pad=strstr(text,combined?"\n1 20 -4 6 1 2 2\n":"\n1 8 0 0 0 0 2\n");
        assert(pad&&aspect<pad);
    }
    puts("record effective aspect PASS");return 0;
}
