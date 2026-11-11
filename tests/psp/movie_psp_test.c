/* Actual leaf body + own synthetic SDK faults, no codec/game data. MIT.
 * test_movie_psp.py creates movie_psp_test_impl.inc from the current source. */
#include "movie_sdk_stubs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include <assert.h>
static void *test_memalign(size_t,size_t);
static void test_free(void *);
#define memalign test_memalign
#define free test_free
#include "movie_psp_test_impl.inc"
#undef memalign
#undef free
static unsigned checks,fails;
#define CK(x) do{checks++;if(!(x)){fails++;fprintf(stderr,"line%d %s\n",__LINE__,#x);}}while(0)
static const char *fault="";
static int bad(const char *s){return strcmp(fault,s)==0||(!strcmp(fault,"present_end")&&(!strcmp(s,"present")||!strcmp(s,"end")));}
static uint64_t clock_us;
static FILE *fds[16];
static int opens,mod1,mod2,decoder,ring_live,channel,thread_live,waits,ends,begins,presents,polls;
static int au_count,outputs,skip_script,buttons_seen,audio_on,me_ok=1,exit_poll;
static int last_nonzero;static uint32_t last_produced,last_output_calls;
static int stream_live,es_live,flushed,end_good;
static int polls_at_rest=-1;
static void *block;static MovieAudio *worker;
static int (*fill_cb)(void*,int,void*);static void *fill_arg,*fill_data;
static unsigned freed_blocks;
void sa1_log(const char *s,...){(void)s;}
uint64_t sceKernelGetSystemTimeWide(void){clock_us+=1000;return clock_us;}
int sceKernelDelayThread(unsigned n){clock_us+=n;return 0;}
unsigned sceKernelCpuSuspendIntr(void){return 0;}void sceKernelCpuResumeIntr(unsigned n){(void)n;}
int sceIoOpen(const char *p,int f,int m){(void)f;(void)m;for(int i=3;i<16;i++)if(!fds[i]){fds[i]=fopen(p,"rb");if(fds[i]){opens++;return i;}return -1;}return -1;}
SceOff sceIoLseek(int f,SceOff p,int w){return fseek(fds[f],(long)p,w)?-1:ftell(fds[f]);}
int sceIoRead(int f,void *p,unsigned n){
 if(bad("read"))return -1;
 long at=ftell(fds[f]);int got=(int)fread(p,1,n,fds[f]);uint8_t *h=p;
 if(at==0&&n==2048&&got==2048){
  if(bad("header_version"))h[7]='4';
  if(bad("header_width"))h[0x8e]=40;
  if(bad("header_height"))h[0x8f]=30;
  if(bad("header_streams"))h[0x81]=2;
  if(bad("header_sid"))h[0x82]=0xe1;
  if(bad("header_pts"))memcpy(h+0x5a,h+0x54,6);
  if(bad("header_pts_high"))h[0x54]=1;
  if(bad("header_offset"))h[9]=1;
  if(bad("header_size"))h[15]^=1;
  if(bad("header_lengths"))h[0x53]^=1;
  if(bad("header_pts_long")){uint64_t end=UINT64_C(90000)+UINT64_C(90000)*3600+1;for(unsigned j=0;j<6;j++)h[0x5f-j]=(uint8_t)(end>>(j*8));memcpy(h+0x74,h+0x5a,6);}
 }
 return got;
}
int sceIoClose(int f){int n=fclose(fds[f]);fds[f]=NULL;opens--;return n;}
static void *test_memalign(size_t a,size_t n){(void)a;if(bad("allocation")||bad("partition"))return NULL;block=malloc(n);return block;}
static void test_free(void *p){if(p&&p==block){assert(!decoder&&!ring_live&&end_good);block=NULL;freed_blocks++;}free(p);}
int sceKernelAllocPartitionMemory(int a,const char *b,int c,unsigned n,void *p){(void)a;(void)b;(void)c;(void)p;if(!bad("partition"))return -1;block=malloc(n);return block?90:-1;}
void *sceKernelGetBlockHeadAddr(int n){assert(n==90);return block;}int sceKernelFreePartitionMemory(int n){assert(n==90);free(block);block=NULL;freed_blocks++;return 0;}
void sceKernelDcacheWritebackRange(const void *p,unsigned n){assert(p&&n);}
void sceKernelDcacheWritebackInvalidateRange(const void *p,unsigned n){assert(p&&n);}
void sceKernelDcacheInvalidateRange(const void *p,unsigned n){assert(p&&n);}
int sceKernelCreateThread(const char *n,int (*f)(SceSize,void*),int p,unsigned s,int a,void *o){(void)n;(void)f;(void)p;(void)s;(void)a;(void)o;if(bad("thread_create"))return -1;thread_live=1;return 80;}
int sceKernelStartThread(int t,SceSize n,void *p){assert(t==80&&n==sizeof worker);if(bad("thread_start"))return -1;worker=*(MovieAudio**)p;return 0;}
int sceKernelWaitThreadEnd(int t,unsigned *n){assert(t==80&&*n==1500000);waits++;if(bad("late_error"))worker->errors++;return bad("join")?-1:0;}
int sceKernelDeleteThread(int t){assert(t==80);if(bad("delete"))return -1;thread_live=0;worker=NULL;return 0;}
int sceAudioChReserve(int a,unsigned n,int f){assert(a==PSP_AUDIO_NEXT_CHANNEL&&n==2048&&f==PSP_AUDIO_FORMAT_STEREO);if(bad("channel"))return -1;channel=1;return 4;}
int sceAudioChRelease(int c){assert(c==4);if(bad("release"))return -1;channel=0;return 0;}
int sceAudioGetChannelRestLen(int c){assert(c==4);if(polls_at_rest<0)polls_at_rest=polls;return bad("rest_query")?-1:0;}
int sceAudioOutputPannedBlocking(int c,int l,int r,void *p){assert(c==4&&l==32768&&r==32768&&p);outputs++;worker->quit=1;return bad("output")?-1:0;}
int sceUtilityLoadModule(int m){if(bad("preloaded"))return (int)ERR_LOADED;if(bad(m==1?"avcodec":"mpegbase"))return -1;if(m==1)mod1++;else mod2++;return 0;}
int sceUtilityUnloadModule(int m){if(m==1)mod1--;else mod2--;return 0;}
int sceMpegInit(void){return bad("init")?-1:0;}void sceMpegFinish(void){}
int sceMpegQueryMemSize(int n){assert(n==0);return bad("sizes")?-1:65536;}
int sceMpegRingbufferQueryMemSize(int n){assert(n==256);return 550912;}
int sceMpegRingbufferConstruct(SceMpegRingbuffer *r,int n,void *p,int bytes,int (*cb)(void*,int,void*),void *a){assert(r&&n==256&&bytes==550912);if(bad("ring"))return -1;ring_live=1;fill_cb=cb;fill_arg=a;fill_data=p;return 0;}
void sceMpegRingbufferDestruct(SceMpegRingbuffer *r){assert(r&&!decoder);ring_live=0;}
int sceMpegCreate(SceMpeg *m,void *p,int n,SceMpegRingbuffer *r,int stride,int a,int b){assert(p&&n==65536&&r&&stride==512&&!a&&!b);if(bad("create"))return -1;*m=(void*)123;decoder=1;return 0;}
void sceMpegDelete(SceMpeg *m){assert(m&&!stream_live&&!es_live);decoder=0;}
int sceMpegAvcDecodeMode(SceMpeg *m,SceMpegAvcMode *v){assert(m&&v->iUnk0==-1&&v->iPixelFormat==0);return bad("mode")?-1:0;}
int sceMpegQueryStreamOffset(SceMpeg *m,void *p,int *v){assert(m&&p&&((uintptr_t)p&63u)==0);*v=2048;return bad("offset")?-1:0;}
int sceMpegQueryStreamSize(void *p,int *v){assert(p);*v=6144;return bad("size")?-1:0;}
SceMpegStream *sceMpegRegistStream(SceMpeg *m,int a,int b){assert(m&&!a&&!b);if(bad("register"))return NULL;stream_live=1;return (void*)456;}
void sceMpegUnRegistStream(SceMpeg m,SceMpegStream *s){assert(current&&m==&current->mpeg&&s==(void*)456&&flushed);stream_live=0;}
void *sceMpegMallocAvcEsBuf(SceMpeg *m){assert(m);if(bad("es"))return NULL;es_live=1;return (void*)789;}
void sceMpegFreeAvcEsBuf(SceMpeg *m,void *p){assert(m&&p==(void*)789&&flushed);es_live=0;}
int sceMpegInitAu(SceMpeg *m,void *p,SceMpegAu *a){assert(m&&p&&a);return bad("au")?-1:0;}
int sceMpegFlushAllStream(SceMpeg *m){assert(m);if(bad("flush"))return -1;flushed=1;return 0;}
int sceMpegRingbufferAvailableSize(SceMpegRingbuffer *r){assert(r);if(au_count>=2){if(bad("eof_available_negative"))return -1;if(bad("eof_available_large"))return 257;}return bad("available")?-1:256;}
int sceMpegRingbufferPut(SceMpegRingbuffer *r,int n,int a){assert(r&&n<=64&&a==256);return fill_cb(fill_data,n,fill_arg);}
int sceMpegGetAvcAu(SceMpeg *m,SceMpegStream *s,SceMpegAu *a,int *p){assert(m&&s&&p);if(bad("get_au"))return -1;if(au_count>=2)return (int)ERR_NO_DATA;a->iPts=90000+(unsigned)au_count*3003;au_count++;return 0;}
int sceMpegAvcDecode(SceMpeg *m,SceMpegAu *a,int stride,void *p,int *got){assert(m&&a&&stride==512);if(bad("decode"))return -1;uint16_t *picture=*(uint16_t**)p;for(unsigned i=0;i<STRIDE*HEIGHT;i++)picture[i]=(uint16_t)au_count;*got=1;return 0;}
int sceMpegAvcDecodeStop(SceMpeg *m,int stride,void *p,int *got){assert(m&&stride==512&&p);*got=0;return bad("decode_stop")?-1:0;}
int sceCtrlPeekBufferPositive(SceCtrlData *p,int n){assert(n==1);p->Buttons=skip_script?(buttons_seen<2?PSP_CTRL_CROSS:buttons_seen==2?0:PSP_CTRL_START):0;buttons_seen++;return 1;}
static int host_begin(void *p){(void)p;begins++;return bad("begin")?-1:0;}
static int host_present(void *p,const uint16_t *pic,unsigned stride){(void)p;assert(stride==512&&pic[0]>=1&&pic[0]<=2);presents++;return bad("present")?-1:0;}
static int host_end(void *p){(void)p;ends++;last_nonzero=(int)current->audio.any_nonzero_pcm;last_produced=current->audio.produced_frames;last_output_calls=current->audio.output_calls;if(bad("end"))return -1;end_good=1;return 0;}
static int host_poll(void *p){(void)p;polls++;assert(polls<10000);if(worker&&worker->wr>worker->rd){worker->quit=0;MovieAudio *arg=worker;audio_worker(sizeof arg,&arg);}return exit_poll;}
static int host_audio(void *p){(void)p;return audio_on;}static int host_me(void *p){(void)p;return me_ok;}
static MoviePspHost hooks={NULL,host_begin,host_present,host_end,host_poll,host_audio,host_me};
static void reset(const char *f){assert(!current&&!block&&!opens&&!mod1&&!mod2&&!decoder&&!ring_live&&!channel&&!thread_live&&!stream_live&&!es_live);fault=f;au_count=outputs=begins=ends=presents=polls=waits=buttons_seen=skip_script=exit_poll=audio_on=flushed=end_good=0;me_ok=1;worker=NULL;last_nonzero=-1;last_produced=last_output_calls=0;polls_at_rest=-1;}
static void fixtures(void){
 FILE *f=fopen("video.pmf","wb");assert(f);uint8_t h[8192]={0};memcpy(h,"PSMF0015",8);h[10]=8;h[14]=24;h[0x53]=62;
 h[0x57]=1;h[0x58]=0x5f;h[0x59]=0x90;h[0x5d]=1;h[0x5e]=0x77;h[0x5f]=6;h[0x68]=h[0x69]=1;h[0x6d]=36;
 memcpy(h+0x6e,h+0x54,12);h[0x7b]=1;h[0x7f]=18;h[0x81]=1;h[0x82]=0xe0;h[0x8e]=30;h[0x8f]=17;
 assert(fwrite(h,1,sizeof h,f)==sizeof h);fclose(f);
 f=fopen("sound.wav","wb");assert(f);uint8_t wav[52]={0};memcpy(wav,"RIFF",4);wav[4]=44;memcpy(wav+8,"WAVEfmt ",8);wav[16]=16;wav[20]=1;wav[22]=2;wav[24]=0x44;wav[25]=0xac;wav[32]=4;wav[34]=16;memcpy(wav+36,"data",4);wav[40]=8;wav[44]=1;assert(fwrite(wav,1,sizeof wav,f)==sizeof wav);fclose(f);
 f=fopen("silent.wav","wb");assert(f);wav[44]=0;assert(fwrite(wav,1,sizeof wav,f)==sizeof wav);fclose(f);
 f=fopen("bad.wav","wb");assert(f);fwrite("nope",1,4,f);fclose(f);
}
int main(void){fixtures();reset("");
 CK(movie_psp_play(NULL,NULL,&hooks)==MOVIE_PSP_NOT_PLAYED);me_ok=0;CK(movie_psp_play("video.pmf",NULL,&hooks)==MOVIE_PSP_NOT_PLAYED&&begins==0);me_ok=1;
 CK(movie_psp_play("absent.pmf",NULL,&hooks)==MOVIE_PSP_NOT_PLAYED&&begins==0);
 CK(movie_psp_play("video.pmf",NULL,&hooks)==MOVIE_PSP_FINISHED&&presents==2&&begins==1&&ends==1);CK(!movie_psp_live()&&movie_psp_paused_us()>0&&movie_psp_heartbeat()>0);
 reset("preloaded");CK(movie_psp_play("video.pmf",NULL,&hooks)==MOVIE_PSP_FINISHED&&!mod1&&!mod2);
 reset("partition");CK(movie_psp_play("video.pmf",NULL,&hooks)==MOVIE_PSP_FINISHED&&!block);
 const char *headers[]={"header_version","header_width","header_height","header_streams","header_sid","header_pts","header_pts_high","header_offset","header_size","header_lengths","header_pts_long"};
 for(unsigned i=0;i<sizeof headers/sizeof *headers;i++){reset(headers[i]);unsigned freed=freed_blocks;CK(movie_psp_play("video.pmf",NULL,&hooks)==MOVIE_PSP_FAILED);CK(freed_blocks==freed&&!mod1&&!mod2&&!current&&!block);}
 const char *errors[]={"begin","avcodec","mpegbase","init","sizes","allocation","ring","create","mode","offset","size","register","es","au","available","read","get_au","decode","present","eof_available_negative","eof_available_large"};
 for(unsigned i=0;i<sizeof errors/sizeof *errors;i++){reset(errors[i]);CK(movie_psp_play("video.pmf",NULL,&hooks)==MOVIE_PSP_FAILED);CK(!movie_psp_live()&&!block&&!opens&&!mod1&&!mod2&&!decoder&&!ring_live);}
 reset("");skip_script=1;CK(movie_psp_play("video.pmf",NULL,&hooks)==MOVIE_PSP_SKIPPED&&buttons_seen>=4&&ends==1);
 reset("");exit_poll=1;CK(movie_psp_play("video.pmf",NULL,&hooks)==MOVIE_PSP_EXIT&&presents==0&&ends==1);
 reset("");audio_on=1;uint32_t calls_before=totals.audio_output_calls,frames_before=totals.played_frames,produced_before=totals.produced_frames;
 CK(movie_psp_play("video.pmf","sound.wav",&hooks)==MOVIE_PSP_FINISHED&&outputs==1&&!channel&&!thread_live);
 CK(totals.audio_output_calls==calls_before+1&&totals.played_frames==frames_before+2048&&totals.produced_frames==produced_before+2&&totals.any_nonzero_pcm);
 reset("");audio_on=1;CK(movie_psp_play("video.pmf","silent.wav",&hooks)==MOVIE_PSP_FINISHED&&last_nonzero==0&&last_produced==2&&last_output_calls==1);
 reset("");CK(movie_psp_play("video.pmf","sound.wav",&hooks)==MOVIE_PSP_FINISHED&&last_nonzero==0&&last_produced==0&&last_output_calls==0);
 const char *soft[]={"channel","thread_create","thread_start"};
 for(unsigned i=0;i<3;i++){reset(soft[i]);audio_on=1;CK(movie_psp_play("video.pmf","sound.wav",&hooks)==MOVIE_PSP_FAILED);CK(!current&&!thread_live&&!channel&&!block);}
 reset("");audio_on=1;CK(movie_psp_play("video.pmf","missing.wav",&hooks)==MOVIE_PSP_FAILED&&!current&&!opens);
 reset("");audio_on=1;CK(movie_psp_play("video.pmf","bad.wav",&hooks)==MOVIE_PSP_FAILED&&!current&&!opens);
 reset("output");audio_on=1;calls_before=totals.audio_output_calls;frames_before=totals.played_frames;
 CK(movie_psp_play("video.pmf","sound.wav",&hooks)==MOVIE_PSP_FAILED&&outputs==1);
 CK(totals.audio_output_calls==calls_before&&totals.played_frames==frames_before&&last_nonzero==1&&last_produced==2&&last_output_calls==0);
 reset("late_error");audio_on=1;uint32_t errors_before=totals.audio_errors;
 CK(movie_psp_play("video.pmf","sound.wav",&hooks)==MOVIE_PSP_FAILED);
 CK(totals.audio_errors==errors_before+1);
 const char *retained[]={"join","delete","release","end","present_end","flush","decode_stop","rest_query"};
 for(unsigned i=0;i<8;i++){reset(retained[i]);audio_on=1;unsigned freed=freed_blocks;CK(movie_psp_play("video.pmf","sound.wav",&hooks)==MOVIE_PSP_CLEANUP_FATAL);CK(current&&block&&decoder&&ring_live&&freed_blocks==freed);if(i==0||i>=5)CK(ends==0);if(i>=3)CK(thread_live&&channel);if(i==7)CK(polls==polls_at_rest);MovieCtx *owned=current;CK(movie_psp_play("video.pmf",NULL,&hooks)==MOVIE_PSP_CLEANUP_FATAL&&current==owned);fault="";CK(movie_psp_shutdown()==0&&!movie_psp_live());CK(!block&&!decoder&&!ring_live&&!channel&&!thread_live&&!opens);CK(movie_psp_shutdown()==0);}
 reset("");MovieCtx c;memset(&c,0,sizeof c);c.sound=c.anchored=1;c.anchor=90000;c.audio.rd=3;c.audio.wr=4;c.audio.rd_us=clock_us;CK(clock90(&c)>90000&&c.hold_us);c.sound=0;uint32_t last=clock90(&c);clock_us+=10000;CK(clock90(&c)>last);
 movie_psp_report();printf("movie_psp %u checks %u failures\n",checks,fails);return fails?1:0;
}
