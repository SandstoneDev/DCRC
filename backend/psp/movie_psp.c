/* Own firmware movie leaf, MIT, Copyright (c) 2026 SandstoneDev.
 * Streaming/clock policy adapted from the owner's DCRC/PS2RC player.
 * Uses public PSPSDK interfaces. No game code, proprietary SDK bodies,
 * framebuffer ownership or movie-number mapping lives here. */
#include "movie_psp.h"
#include "../movie_wav.h"
#include "hle.h"
#include <pspkernel.h>
#include <pspctrl.h>
#include <pspaudio.h>
#include <pspmpeg.h>
#include <psputility.h>
#include <pspintrman.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PACK 2048u
#define RING_PACKS 256
#define STRIDE 512u
#define HEIGHT 272u
#define PIC_BYTES (STRIDE*HEIGHT*2u)
#define FRAME_TICKS 3003u
#define AUD_FRAMES 2048u
#define AUD_RATE 44100u
#define AUD_SLOTS 16u
#define AUD_LEAD 12u
#define AUD_BYTES (AUD_FRAMES*4u)
#define SIDE_STAGE 32768u
#define ERR_NO_DATA UINT32_C(0x80618001)
#define ERR_LOADED UINT32_C(0x80111102)
/* Deliberate opaque headroom around PUBLIC SDK types, not private layouts. */
typedef union {SceMpegRingbuffer sdk;uint8_t headroom[256];} RingRecord;
typedef union {SceMpegAu sdk;uint8_t headroom[256];} AuRecord;
typedef union {SceMpegAvcMode sdk;uint8_t headroom[256];} ModeRecord;
typedef struct {SceUID fd;int64_t pos,size;} MovieFile;
typedef struct {
    int16_t *slots;
    volatile uint32_t wr,rd,errors,underruns,output_calls,played_frames,produced_frames,any_nonzero_pcm;
    volatile uint64_t rd_us;
    volatile int quit,running;
    int channel;
} MovieAudio;
typedef struct MovieCtx {
    MoviePspHost host;
    MovieFile video,wave;
    MovieWav wav;
    MovieAudio audio;
    RingRecord ring;
    AuRecord au;
    SceMpeg mpeg;
    SceMpegStream *stream;
    void *es,*allocation,*work,*ring_mem;
    uint16_t *picture;
    SceUID partition,thread;
    int thread_started,thread_joined,inited,ring_built,created,decoded,decode_stopped,flushed;
    int avcodec_owned,mpeg_owned,began,ended,sound,wave_ready,read_error;
    uint32_t first_pts,last_pts,read_pos,read_end,total,shown,dropped,decoded_count,sound_blocks;
    uint32_t hold,anchor,drop_run;
    int32_t present_late_min,present_late_max;
    uint64_t hold_us,start_us;
    int anchored;
    int result;
    const char *failure;
    int failure_code;
    uint8_t header_storage[PACK+63u]; /* calloc need not align the context64 */
} MovieCtx;
static MovieCtx *current;
static uint32_t heartbeat;
static uint64_t paused_total;
static struct {uint32_t attempts,finished,skipped,exits,failed,missing,shown,dropped,underruns,audio_errors,max_bytes,audio_output_calls,played_frames,produced_frames,any_nonzero_pcm;} totals;
static uint64_t now_us(void){return (uint64_t)sceKernelGetSystemTimeWide();}
uint32_t movie_psp_heartbeat(void){return heartbeat;}
int movie_psp_live(void){return current!=NULL;}
uint64_t movie_psp_paused_us(void){return paused_total+(current&&current->began?now_us()-current->start_us:0);}
static uint32_t be32(const uint8_t *p){return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];}
static uint32_t be16(const uint8_t *p){return (uint32_t)p[0]<<8|p[1];}
static uint64_t be48(const uint8_t *p){uint64_t v=0;for(unsigned i=0;i<6;i++)v=(v<<8)|p[i];return v;}
/* Own converter's public PSMF0015 contract, checked BEFORE firmware/alloc.
 * The stage separately validates every AVC SPS; this is not an H.264 parser. */
static int header_valid(const uint8_t *h,uint64_t file_size){
    if(file_size<2u*PACK||file_size>UINT32_MAX||memcmp(h,"PSMF0015",8)||be32(h+8)!=PACK||
       be32(h+12)!=file_size-PACK||be32(h+12)%PACK)return 0;
    if(be32(h+0x50)!=62||h[0x68]!=1||h[0x69]!=1||be32(h+0x6a)!=36||
       be16(h+0x7a)!=1||be32(h+0x7c)!=18||be16(h+0x80)!=1)return 0;
    if(h[0x82]!=0xe0||h[0x83]!=0||h[0x8e]!=480/16||h[0x8f]!=HEIGHT/16)return 0;
    uint64_t first=be48(h+0x54),last=be48(h+0x5a);
    return first<=UINT32_MAX&&last<=UINT32_MAX&&last>first&&last-first<=UINT64_C(90000)*3600&&
        !memcmp(h+0x54,h+0x6e,12);
}
static int fail(MovieCtx *m,const char *where,int code){m->failure=where;m->failure_code=code;return 0;}
static void file_close(MovieFile *f){if(f->fd>=0)sceIoClose(f->fd);f->fd=-1;}
static int file_open(MovieFile *f,const char *path){
    if(!path||!path[0])return 0;
    f->fd=sceIoOpen(path,PSP_O_RDONLY,0);if(f->fd<0)return 0;
    f->size=sceIoLseek(f->fd,0,PSP_SEEK_END);
    if(f->size<=0||sceIoLseek(f->fd,0,PSP_SEEK_SET)!=0){file_close(f);return 0;}
    f->pos=0;return 1;
}
static int64_t file_read(void *opaque,uint64_t off,void *dst,uint32_t bytes){
    MovieFile *f=opaque;
    if(f->fd<0||off>(uint64_t)f->size||bytes>(uint64_t)f->size-off)return -1;
    if(off!=(uint64_t)f->pos){if(sceIoLseek(f->fd,(SceOff)off,PSP_SEEK_SET)!=(SceOff)off)return -1;f->pos=(int64_t)off;}
    int n=sceIoRead(f->fd,dst,bytes);if(n>0)f->pos+=n;return n;
}
static SceInt32 ring_fill(ScePVoid dst,SceInt32 packets,ScePVoid opaque){
    MovieCtx *m=opaque;
    if(packets<=0||packets>RING_PACKS)return 0;
    uint32_t bytes=(uint32_t)packets*PACK,left=m->read_end-m->read_pos;
    if(bytes>left)bytes=left;
    bytes-=bytes%PACK;
    if(!bytes)return 0;
    if(file_read(&m->video,m->read_pos,dst,bytes)!=(int64_t)bytes){m->read_error=1;return -1;}
    m->read_pos+=bytes;return (SceInt32)(bytes/PACK);
}
static int audio_worker(SceSize size,void *argument){
    if(size!=sizeof(MovieAudio*)||!argument)return -1;
    MovieAudio *a=*(MovieAudio**)argument;int dry=0;
    while(!a->quit){
        if(a->rd==a->wr){if(!dry&&a->rd)a->underruns++;dry=1;sceKernelDelayThread(2000);continue;}
        dry=0;
        int rc=sceAudioOutputPannedBlocking(a->channel,PSP_AUDIO_VOLUME_MAX,PSP_AUDIO_VOLUME_MAX,a->slots+(a->rd%AUD_SLOTS)*AUD_FRAMES*2);
        unsigned intr=sceKernelCpuSuspendIntr();
        if(rc<0){a->errors++;a->quit=1;}
        else {a->rd_us=now_us();a->rd++;a->output_calls++;a->played_frames+=AUD_FRAMES;}
        sceKernelCpuResumeIntr(intr);
    }
    a->running=0;return 0;
}
static uint32_t clock90(MovieCtx *m){
    unsigned intr=sceKernelCpuSuspendIntr();
    uint32_t rd=m->audio.rd,wr=m->audio.wr;uint64_t consumed=m->audio.rd_us;
    sceKernelCpuResumeIntr(intr);
    uint64_t now=now_us();
    if(m->sound&&m->anchored&&rd>=2&&wr>rd){
        uint64_t extra=now>=consumed?(now-consumed)*AUD_RATE/1000000u:0;
        uint64_t frames=(uint64_t)(rd-2)*AUD_FRAMES+(extra<AUD_FRAMES?extra:AUD_FRAMES);
        m->hold=m->anchor+(uint32_t)(frames*90000u/AUD_RATE);m->hold_us=now;return m->hold;
    }
    if(!m->hold_us)return m->hold;
    if(now<m->hold_us){m->hold_us=now;return m->hold;}
    return m->hold+(uint32_t)((now-m->hold_us)*9u/100u);
}
static int allocate(MovieCtx *m,uint32_t bytes){
    m->allocation=memalign(64,bytes);
#if UINTPTR_MAX<=UINT32_MAX
    if(m->allocation&&((uintptr_t)m->allocation>=0x0c000000u||bytes>0x0c000000u-(uintptr_t)m->allocation)){free(m->allocation);m->allocation=NULL;}
#endif
    if(m->allocation){m->work=m->allocation;return 1;}
    if(bytes>UINT32_MAX-63u)return 0;
    m->partition=sceKernelAllocPartitionMemory(2,"dcrc_movie",PSP_SMEM_High,bytes+63u,NULL);
    if(m->partition<0)return 0;
    void *p=sceKernelGetBlockHeadAddr(m->partition);
    if(!p)return 0;
    m->work=(void*)(((uintptr_t)p+63u)&~(uintptr_t)63u);return 1;
}
static int open_decoder(MovieCtx *m,const char *wave){
    uint8_t *header=(uint8_t*)(((uintptr_t)m->header_storage+63u)&~(uintptr_t)63u);
    if(m->video.size<2*(int64_t)PACK||file_read(&m->video,0,header,PACK)!=PACK||!header_valid(header,(uint64_t)m->video.size))return fail(m,"header_contract",-1);
    m->first_pts=be32(header+0x56);m->last_pts=be32(header+0x5c);m->hold=m->first_pts;
    int audio=m->host.audio_enabled&&m->host.audio_enabled(m->host.opaque);
    int wave_open=audio&&file_open(&m->wave,wave);
    if(audio&&!wave_open)return fail(m,"wave_open",-1);
    int rc=sceUtilityLoadModule(PSP_MODULE_AV_AVCODEC);
    if(rc<0&&(uint32_t)rc!=ERR_LOADED)return fail(m,"avcodec",rc);
    m->avcodec_owned=rc>=0;
    rc=sceUtilityLoadModule(PSP_MODULE_AV_MPEGBASE);
    if(rc<0&&(uint32_t)rc!=ERR_LOADED)return fail(m,"mpegbase",rc);
    m->mpeg_owned=rc>=0;
    rc=sceMpegInit();if(rc<0)return fail(m,"init",rc);m->inited=1;
    int work=sceMpegQueryMemSize(0),ring=sceMpegRingbufferQueryMemSize(RING_PACKS);
    if(work<=0||ring<=0)return fail(m,"sizes",work<=0?work:ring);
    uint64_t a=((uint64_t)(unsigned)work+63u)&~UINT64_C(63),b=((uint64_t)(unsigned)ring+63u)&~UINT64_C(63);
    uint64_t total=a+b+PIC_BYTES+(wave_open?AUD_SLOTS*AUD_BYTES+SIDE_STAGE:0u);
    if(total>INT32_MAX)return fail(m,"size_overflow",-1);
    m->total=(uint32_t)total;if(!allocate(m,m->total))return fail(m,"allocation",-1);
    m->ring_mem=(uint8_t*)m->work+a;m->picture=(uint16_t*)((uint8_t*)m->ring_mem+b);
    memset(m->work,0,(size_t)total);sceKernelDcacheWritebackInvalidateRange(m->work,m->total);
    if(wave_open){
        m->audio.slots=(int16_t*)((uint8_t*)m->picture+PIC_BYTES);
        uint8_t *stage=(uint8_t*)m->audio.slots+AUD_SLOTS*AUD_BYTES;
        int w=movie_wav_open(&m->wav,file_read,&m->wave,(uint64_t)m->wave.size,stage,SIDE_STAGE);
        m->wave_ready=w==MOVIE_WAV_OK&&m->wav.rate==AUD_RATE;
        if(!m->wave_ready)return fail(m,"wave_format",w<0?w:MOVIE_WAV_E_FORMAT);
    }
    rc=sceMpegRingbufferConstruct(&m->ring.sdk,RING_PACKS,m->ring_mem,ring,ring_fill,m);
    if(rc<0)return fail(m,"ring",rc);
    m->ring_built=1;
    rc=sceMpegCreate(&m->mpeg,m->work,work,&m->ring.sdk,STRIDE,0,0);
    if(rc<0)return fail(m,"create",rc);
    m->created=1;
    ModeRecord mode;memset(&mode,0,sizeof mode);mode.sdk.iUnk0=-1;mode.sdk.iPixelFormat=SCE_MPEG_AVC_FORMAT_5650;
    rc=sceMpegAvcDecodeMode(&m->mpeg,&mode.sdk);if(rc<0)return fail(m,"mode",rc);
    SceInt32 offset=0,size=0;rc=sceMpegQueryStreamOffset(&m->mpeg,header,&offset);
    if(rc<0||offset<(int)PACK||offset%(int)PACK)return fail(m,"stream_offset",rc);
    rc=sceMpegQueryStreamSize(header,&size);
    if(rc<0||size<=0||size%(int)PACK||(uint64_t)(unsigned)offset+(unsigned)size>(uint64_t)m->video.size)return fail(m,"stream_size",rc);
    m->read_pos=(uint32_t)offset;m->read_end=(uint32_t)offset+(uint32_t)size;
    m->stream=sceMpegRegistStream(&m->mpeg,0,0);if(!m->stream)return fail(m,"register",-1);
    m->es=sceMpegMallocAvcEsBuf(&m->mpeg);if(!m->es)return fail(m,"es",-1);
    rc=sceMpegInitAu(&m->mpeg,m->es,&m->au.sdk);if(rc<0)return fail(m,"au",rc);
    if(m->wave_ready){
        m->audio.channel=sceAudioChReserve(PSP_AUDIO_NEXT_CHANNEL,AUD_FRAMES,PSP_AUDIO_FORMAT_STEREO);
        if(m->audio.channel>=0){
            m->thread=sceKernelCreateThread("dcrc_movie_audio",audio_worker,0x10,0x4000,0,NULL);
            if(m->thread>=0){
                MovieAudio *argument=&m->audio;m->audio.running=1;
                rc=sceKernelStartThread(m->thread,sizeof argument,&argument);
                if(rc>=0){m->thread_started=1;m->sound=1;}
                else m->audio.running=0;
            }
        }
        if(!m->sound)return fail(m,"audio_start",m->audio.channel<0?m->audio.channel:m->thread<0?m->thread:rc);
    }
    return 1;
}
/* A failed join/release retains the ENTIRE context, decoder, files and block.
 * Caller must not resume/restart the game while ownership is uncertain. */
static int close_decoder(MovieCtx *m){
    m->audio.quit=1;
    if(m->thread>=0){
        if(m->thread_started&&!m->thread_joined){SceUInt wait=1500000;if(sceKernelWaitThreadEnd(m->thread,&wait)<0)return -1;m->thread_joined=1;}
    }
    if(m->audio.channel>=0){
        uint64_t start=now_us();
        for(;;){
            int rest=sceAudioGetChannelRestLen(m->audio.channel);
            if(rest<0){fail(m,"audio_rest_query",rest);return -1;}
            if(!rest)break;
            heartbeat++;m->host.poll(m->host.opaque);if(now_us()-start>1000000u)return -1;sceKernelDelayThread(2000);
        }
    }
    if(m->created){
        if(m->decoded&&!m->decode_stopped){
            void *out[1]={m->picture};SceInt32 got=0;
            sceKernelDcacheWritebackInvalidateRange(m->picture,PIC_BYTES);
            int rc=sceMpegAvcDecodeStop(&m->mpeg,STRIDE,out,&got);
            if(rc<0){fail(m,"close_decode_stop",rc);return -1;}
            m->decode_stopped=1;
        }
        if(!m->flushed){int rc=sceMpegFlushAllStream(&m->mpeg);if(rc<0){fail(m,"close_flush",rc);return -1;}m->flushed=1;}
    }
    /* A failed present can leave a GE reader in flight. Restore/drain BEFORE
     * deleting any retained worker handle or releasing the picture storage. */
    if(m->began&&!m->ended){if(m->host.end(m->host.opaque)<0)return -1;m->ended=1;}
    if(m->thread>=0){if(sceKernelDeleteThread(m->thread)<0)return -1;m->thread=-1;}
    if(m->audio.channel>=0){if(sceAudioChRelease(m->audio.channel)<0)return -1;m->audio.channel=-1;}
    if(m->created){
        /* Public PSPSDK declares these destructors void. A normal return is
         * their synchronous completion contract, not a checked error status. */
        if(m->es){sceMpegFreeAvcEsBuf(&m->mpeg,m->es);m->es=NULL;}
        /* PSPSDK's UnRegistStream prototype uses void* here; firmware takes
         * the address of the handle, consistently with the other calls. */
        if(m->stream){sceMpegUnRegistStream((SceMpeg)&m->mpeg,m->stream);m->stream=NULL;}
        sceMpegDelete(&m->mpeg);m->created=0;
    }
    if(m->ring_built){sceMpegRingbufferDestruct(&m->ring.sdk);m->ring_built=0;}
    if(m->inited){sceMpegFinish();m->inited=0;}
    if(m->partition>=0){if(sceKernelFreePartitionMemory(m->partition)<0)return -1;m->partition=-1;}
    free(m->allocation);m->allocation=NULL;
    if(m->mpeg_owned){if(sceUtilityUnloadModule(PSP_MODULE_AV_MPEGBASE)<0)return -1;m->mpeg_owned=0;}
    if(m->avcodec_owned){if(sceUtilityUnloadModule(PSP_MODULE_AV_AVCODEC)<0)return -1;m->avcodec_owned=0;}
    file_close(&m->wave);file_close(&m->video);return 0;
}
static int finish_context(MovieCtx *m){
    int result=m->result;
    if(result==MOVIE_PSP_FINISHED&&m->audio.errors)result=MOVIE_PSP_FAILED;
    sa1_log("movie: result=%d step=%s code=%08x shown=%u dropped=%u decoded=%u sound_blocks=%u underruns=%u audio_errors=%u bytes=%u real_us=%llu",
        result,m->failure?m->failure:"none",(unsigned)m->failure_code,m->shown,m->dropped,m->decoded_count,m->sound_blocks,m->audio.underruns,m->audio.errors,m->total,(unsigned long long)(now_us()-m->start_us));
    sa1_log("movie-av: first90=%u last90=%u wav_anchored=%d present_start_late90_min=%d max=%d is_not_LCD_or_DAC_time=1",
        m->first_pts,m->last_pts,m->anchored,m->present_late_min,m->present_late_max);
    sa1_log("movie-audio: audio_output_calls=%u output_errors=%u played_frames=%u produced_frames=%u underruns=%u any_nonzero_pcm=%u output_calls_are_successful=1 played_includes_padding=1 is_not_DAC_time=1",
        m->audio.output_calls,m->audio.errors,m->audio.played_frames,m->audio.produced_frames,m->audio.underruns,m->audio.any_nonzero_pcm);
    totals.shown+=m->shown;totals.dropped+=m->dropped;totals.underruns+=m->audio.underruns;totals.audio_errors+=m->audio.errors;
    totals.audio_output_calls+=m->audio.output_calls;totals.played_frames+=m->audio.played_frames;totals.produced_frames+=m->audio.produced_frames;totals.any_nonzero_pcm|=m->audio.any_nonzero_pcm;
    if(m->total>totals.max_bytes)totals.max_bytes=m->total;
    if(result==MOVIE_PSP_FINISHED)totals.finished++;else if(result==MOVIE_PSP_SKIPPED)totals.skipped++;else if(result==MOVIE_PSP_EXIT)totals.exits++;else totals.failed++;
    if(m->began)paused_total+=now_us()-m->start_us;
    current=NULL;free(m);return result;
}
int movie_psp_shutdown(void){
    MovieCtx *m=current;if(!m)return 0;
    if(close_decoder(m)<0)return -1;
    finish_context(m);return 0;
}
static int run_movie(MovieCtx *m){
    int read_done=0,video_done=0,stopped=0,pending=0,audio_done=!m->sound;
    uint32_t pts=0,last_pts=m->first_pts-FRAME_TICKS,ptsq[16];unsigned qh=0,qn=0;
    uint64_t progress=now_us(),no_data=0,drain=0;uint32_t last_rd=0;
    int released=0;uint32_t previous=0;
    for(;;){
        heartbeat++;if(m->host.poll(m->host.opaque))return MOVIE_PSP_EXIT;
        uint64_t now=now_us();SceCtrlData pad;
        if(sceCtrlPeekBufferPositive(&pad,1)>0){
            if(!pad.Buttons)released=1;
            uint32_t pressed=pad.Buttons&~previous;previous=pad.Buttons;
            if(released&&(pressed&(PSP_CTRL_CROSS|PSP_CTRL_START)))return MOVIE_PSP_SKIPPED;
        }
        if(m->audio.errors)return fail(m,"audio_output",-1),MOVIE_PSP_FAILED;
        int worked=0;
        if(!read_done){
            int available=sceMpegRingbufferAvailableSize(&m->ring.sdk);
            if(available<0||available>RING_PACKS)return fail(m,"ring_available",available),MOVIE_PSP_FAILED;
            if(available>=32||(available>0&&m->read_end-m->read_pos<32*PACK)){
                int put=sceMpegRingbufferPut(&m->ring.sdk,available<64?available:64,available);
                if(put<0||m->read_error)return fail(m,"read",put),MOVIE_PSP_FAILED;
                worked=put>0;
            }
            read_done=m->read_pos>=m->read_end;
        }
        for(int n=0;m->sound&&!audio_done&&n<6;n++){
            uint32_t queued=m->audio.wr-m->audio.rd;
            if(queued>=AUD_LEAD||queued>=AUD_SLOTS-2)break;
            int16_t *slot=m->audio.slots+(m->audio.wr%AUD_SLOTS)*AUD_FRAMES*2;
            int got=movie_wav_read(&m->wav,slot,AUD_FRAMES);
            if(got<0)return fail(m,"wave_read",got),MOVIE_PSP_FAILED;
            if(got>0){
                m->audio.produced_frames+=(uint32_t)got;
                if(!m->audio.any_nonzero_pcm)for(int i=0;i<got*2;i++)if(slot[i]){m->audio.any_nonzero_pcm=1;break;}
                if((unsigned)got<AUD_FRAMES)memset(slot+2*got,0,(AUD_FRAMES-(unsigned)got)*4u);
                if(!m->anchored){m->anchor=m->first_pts;m->anchored=1;}
                sceKernelDcacheWritebackRange(slot,AUD_BYTES);__sync_synchronize();m->audio.wr++;m->sound_blocks++;worked=1;
            }
            if((unsigned)got<AUD_FRAMES){audio_done=1;break;}
        }
        if(!video_done&&!pending){
            void *out[1]={m->picture};SceInt32 got=0,attr=0;
            if(stopped)video_done=1;
            else {
                int rc=sceMpegGetAvcAu(&m->mpeg,m->stream,&m->au.sdk,&attr);
                if((uint32_t)rc==ERR_NO_DATA){
                    if(!no_data)no_data=now;
                    int available=sceMpegRingbufferAvailableSize(&m->ring.sdk);
                    if(available<0||available>RING_PACKS)return fail(m,"ring_eof_available",available),MOVIE_PSP_FAILED;
                    if(read_done&&(available>=RING_PACKS||now-no_data>2000000u)){
                        sceKernelDcacheWritebackInvalidateRange(m->picture,PIC_BYTES);
                        int stop=m->decoded?sceMpegAvcDecodeStop(&m->mpeg,STRIDE,out,&got):0;
                        if(stop<0)return fail(m,"decode_stop",stop),MOVIE_PSP_FAILED;
                        m->decode_stopped=1;stopped=1;
                        if(got>0&&qn){pending=1;pts=ptsq[qh];qh=(qh+1)%16;qn--;}else video_done=1;
                    }
                } else if(rc<0)return fail(m,"get_au",rc),MOVIE_PSP_FAILED;
                else {
                    no_data=0;sceKernelDcacheWritebackInvalidateRange(m->picture,PIC_BYTES);
                    rc=sceMpegAvcDecode(&m->mpeg,&m->au.sdk,STRIDE,out,&got);
                    if(rc<0)return fail(m,"decode",rc),MOVIE_PSP_FAILED;
                    m->decoded=1;m->decoded_count++;
                    uint32_t next=m->au.sdk.iPts!=UINT32_MAX?m->au.sdk.iPts:last_pts+FRAME_TICKS;last_pts=next;
                    if(qn==16)return fail(m,"pts_queue",-1),MOVIE_PSP_FAILED;
                    ptsq[(qh+qn)%16]=next;qn++;
                    if(got>0){pending=1;pts=ptsq[qh];qh=(qh+1)%16;qn--;}
                    worked=1;
                }
            }
        }
        if(pending){
            if(!m->shown&&!m->anchored)m->hold=pts;
            int32_t late=(int32_t)(clock90(m)-pts);
            if(late>(int32_t)(2*FRAME_TICKS)&&m->drop_run<4&&!stopped){pending=0;m->dropped++;m->drop_run++;worked=1;}
            else if(late>=-(int32_t)(FRAME_TICKS/2)){
                sceKernelDcacheInvalidateRange(m->picture,PIC_BYTES);
                if(m->host.present(m->host.opaque,m->picture,STRIDE)<0)return fail(m,"present",-1),MOVIE_PSP_FAILED;
                if(!m->shown)m->present_late_min=m->present_late_max=late;
                else {if(late<m->present_late_min)m->present_late_min=late;if(late>m->present_late_max)m->present_late_max=late;}
                if(!m->hold_us)m->hold_us=now_us();
                pending=0;m->drop_run=0;m->shown++;worked=1;
            }
        }
        if(video_done&&!pending&&audio_done){
            if(!m->sound||m->audio.rd==m->audio.wr)return m->shown?MOVIE_PSP_FINISHED:MOVIE_PSP_FAILED;
            if(!drain)drain=now;
            if(now-drain>3000000u)return fail(m,"audio_drain",-1),MOVIE_PSP_FAILED;
        }
        if(worked||m->audio.rd!=last_rd){progress=now;last_rd=m->audio.rd;}
        else if(now-progress>5000000u)return fail(m,"stall",-1),MOVIE_PSP_FAILED;
        sceKernelDelayThread(worked?1000:3000);
    }
}
int movie_psp_play(const char *pmf,const char *wave,const MoviePspHost *host){
    if(current)return MOVIE_PSP_CLEANUP_FATAL;
    if(!pmf||!host||!host->begin||!host->present||!host->end||!host->poll||!host->me_available||host->me_available(host->opaque)<=0)return MOVIE_PSP_NOT_PLAYED;
    MovieCtx *m=calloc(1,sizeof *m);if(!m)return MOVIE_PSP_FAILED;
    m->host=*host;m->video.fd=m->wave.fd=m->partition=m->thread=m->audio.channel=-1;
    if(!file_open(&m->video,pmf)){totals.missing++;free(m);return MOVIE_PSP_NOT_PLAYED;}
    current=m;m->start_us=now_us();
    if(host->begin(host->opaque)<0){file_close(&m->video);current=NULL;free(m);return MOVIE_PSP_FAILED;}
    m->began=1;totals.attempts++;
    m->result=open_decoder(m,wave)?run_movie(m):MOVIE_PSP_FAILED;
    if(close_decoder(m)<0){m->result=MOVIE_PSP_CLEANUP_FATAL;sa1_log("movie: cleanup uncertain; all live resources retained, game must exit");return MOVIE_PSP_CLEANUP_FATAL;}
    return finish_context(m);
}
void movie_psp_report(void){
    sa1_log("movie: attempts=%u finished=%u skipped=%u exits=%u failed=%u missing=%u shown=%u dropped=%u underruns=%u audio_errors=%u audio_output_calls=%u played_frames=%u produced_frames=%u any_nonzero_pcm=%u max_bytes=%u retained=%d paused_us=%llu",
        totals.attempts,totals.finished,totals.skipped,totals.exits,totals.failed,totals.missing,totals.shown,totals.dropped,totals.underruns,totals.audio_errors,totals.audio_output_calls,totals.played_frames,totals.produced_frames,totals.any_nonzero_pcm,totals.max_bytes,movie_psp_live(),(unsigned long long)movie_psp_paused_us());
}
