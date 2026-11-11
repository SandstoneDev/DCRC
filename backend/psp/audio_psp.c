/* audio_psp.c - backend/audio.h on the PSP: one sceAudio channel fed by its
 * own thread.
 *
 * Normal playback follows the owner's old DCRC mechanism: this single output
 * worker renders1024 samples per hardware-paced block. The guest thread owns
 * files, compressed SPSC rings, commands and the unchanged735/frame clock.
 * Shared bank/init/state changes use a bounded cooperative core semaphore.
 * Strict/recording mode retains the original735/frame PCM ring below.
 * No ME, extra PCM queue, output-rate or pitch adjustment is used.
 *
 * Part of sa1-psp (MIT). */
#include "../audio.h"
#include "hle.h"
#include "../audio_pause_clock.h"
#include "audio_movie.h"
#include "sound/snd_host.h"
#include "../audio_realtime.h"

#include <pspkernel.h>
#include <pspaudio.h>
#include <pspintrman.h>
#include <string.h>

#define AUD_BLOCK 1024u                 /* frames per sceAudio output (23 ms) */
#define AUD_RING 8192u                  /* frames; a power of two */
#define AUD_START 2048u                 /* frames buffered before the first output */
#define AUD_MAX 4096u                   /* frames (93 ms): beyond this a push is dropped */

int audio_psp_enabled = 1;              /* main_psp.c --no-audio */
int audio_psp_out2 = 1;                 /* sceAudioOutput2 (ec +0.35 ms, ss +0.22 a frame); main_psp.c --audio-chan: a sceAudio channel (ec +2.1, ss +1.9; 2026-10-27) */

static int16_t ring[2 * AUD_RING] __attribute__((aligned(64)));
static int16_t block[2][2 * AUD_BLOCK] __attribute__((aligned(64)));
static volatile uint32_t wr, rd;        /* frames, free-running */
static volatile int run;
static int ch = -1;
static SceUID th = -1, sema = -1, core_sema = -1;
static int shutdown_failed;
int audio_psp_shutdown_failed(void){return shutdown_failed;}
static int core_enter(uint32_t timeout_us){
    SceUInt timeout=timeout_us;
    return core_sema<0?-1:sceKernelWaitSema(core_sema,1,&timeout);
}
static void core_leave(void){
    if(sceKernelSignalSema(core_sema,1)<0)shutdown_failed=1;
}
static void core_wake(void){if(sema>=0)sceKernelSignalSema(sema,1);}
static void core_yield(void){sceKernelDelayThread(1000);}
static const snd_async_ops real_ops={core_enter,core_leave,core_wake,core_yield};
static void worker_fpu(void){
#ifdef __mips__
    uint32_t old;
    __asm__ volatile("cfc1 %0, $31":"=r"(old));
    old=audio_realtime_fcsr(old);
    __asm__ volatile("ctc1 %0, $31"::"r"(old));
#endif
}
static volatile int waiting;            /* the thread sleeps on sema until a push */
static uint32_t starves, dropped;
static uint64_t starve_us;
static uint64_t wait_since;
static uint64_t wait_pause_start;
static uint32_t pushed_frames, output_calls, output_errors;
static volatile int output_busy;
static volatile int menu_paused;
static volatile int pause_ack;
static int movie_pause_owned;
static uint32_t movie_discarded_frames;
static uint64_t menu_pause_start,menu_pause_total;
void audio_psp_pause(int on) {
    unsigned intr=sceKernelCpuSuspendIntr();
    uint64_t now=sa1_plat_time_us();
    if(on && !menu_paused){menu_pause_start=now;menu_paused=1;}
    else if(!on && menu_paused){menu_pause_total+=now-menu_pause_start;menu_paused=0;}
    sceKernelCpuResumeIntr(intr);
    if(sema>=0)sceKernelSignalSema(sema,1);
}
int audio_psp_movie_pause(int on) {
    if(on){
        if(movie_pause_owned)return 0;
        if(ch<0||th<0||!run)return 0;
        if(menu_paused)return -1; /* never take another pause owner's token */
        audio_psp_pause(1);
        uint64_t deadline=sa1_plat_time_us()+500000u;
        while(!pause_ack||output_busy){
            if(sa1_plat_time_us()>=deadline){audio_psp_pause(0);return -1;}
            sceKernelDelayThread(1000);
        }
        /* OutputBlocking returning is not proof that the DAC finished the
         * last queued block. The movie has not acquired any audio channel yet. */
        for(;;){
            int rest=audio_psp_out2?sceAudioOutput2GetRestSample():sceAudioGetChannelRestLen(ch);
            if(rest<0||sa1_plat_time_us()>=deadline){
                sa1_log("audio-movie: hardware drain declined rest=%d",rest);
                audio_psp_pause(0);return -1;
            }
            if(!rest)break;
            sceKernelDelayThread(1000);
        }
        movie_pause_owned=1;
    }else{
        if(!movie_pause_owned)return 0;
        if(ch>=0&&run&&(!menu_paused||!pause_ack||output_busy))return -1;
    }
    /* The consumer acknowledged it is outside its copy/output region; the
     * producer is this blocked owner thread. Retire old music without any
     * Output2/SRC release/re-reserve, including on the way back to gameplay. */
    unsigned intr=sceKernelCpuSuspendIntr();
    uint32_t queued=wr-rd;
    if(queued<=AUD_RING)movie_discarded_frames+=queued;
    rd=wr;
    sceKernelCpuResumeIntr(intr);
    if(!on){movie_pause_owned=0;audio_psp_pause(0);}
    return 0;
}
static uint64_t pause_clock(void) {
    unsigned intr=sceKernelCpuSuspendIntr();
    uint64_t result=menu_pause_total+(menu_paused?sa1_plat_time_us()-menu_pause_start:0);
    sceKernelCpuResumeIntr(intr);return result;
}

/* Owner-thread reporting only; snapshots include the output thread's 64-bit
 * fields coherently. No output-thread logging/card IO and no new waits. */
void audio_psp_report(void) {
    unsigned intr = sceKernelCpuSuspendIntr();
    uint32_t fill = wr - rd, pushes = pushed_frames, drops = dropped;
    uint32_t waits = starves, calls = output_calls, errors = output_errors;
    int busy = output_busy, sleeping = waiting, open = ch >= 0;
    uint64_t us = starve_us, since = wait_since;
    uint64_t sample_us = sa1_plat_time_us();
    if (since) {
        uint64_t pause_now=menu_pause_total+(menu_paused?sample_us-menu_pause_start:0);
        us+=audio_unpaused_wait(sample_us-since,pause_now-wait_pause_start);
    }
    sceKernelCpuResumeIntr(intr);
    sa1_log("audio-output: mono_us=%llu cumulative=1 open=%d enabled=%d output2=%d ring_frames=%u ring_valid=%d pushed_frames=%u dropped_frames=%u output_calls=%u output_errors=%u",
        (unsigned long long)sample_us, open, audio_psp_enabled, audio_psp_out2, fill, fill <= AUD_RING,
        pushes, drops, calls, errors);
    sa1_log("audio-wait: mono_us=%llu starvation_waits=%u starvation_us=%llu waiting=%d output_busy=%d queued_is_not_played=1",
        (unsigned long long)sample_us, waits, (unsigned long long)us, sleeping, busy);
    sa1_log("audio-movie: pause_ack=%d pause_owned=%d discarded_stale_frames=%u",pause_ack,movie_pause_owned,movie_discarded_frames);
}

static int out_thread(SceSize args, void *argp) {
    (void)args; (void)argp;
    worker_fpu();
    int b = 0;
    while (!snd_host_async_active()&&wr-rd<AUD_START&&run) {
        if(menu_paused){pause_ack=1;sceKernelDelayThread(10000);continue;}
        pause_ack=0;waiting=1;sceKernelWaitSema(sema,1,NULL);
    }
    while (run) {
        if(menu_paused){pause_ack=1;sceKernelDelayThread(10000);continue;}
        pause_ack=0;
        int16_t *o = block[b];
        if(snd_host_async_active()) {
            /* Busy includes core reads, not just hardware submission. The existing
             * pause ACK therefore covers both decoder and PCM reader ownership. */
            output_busy=1;waiting=0;
            int got=snd_host_async_render(o,AUD_BLOCK);
            if(got<=0){
                output_busy=0;waiting=1;
                SceUInt timeout=10000u;
                sceKernelWaitSema(sema,1,got<0?&timeout:NULL);
                continue;
            }
            if(menu_paused||!run){output_busy=0;continue;}
            pushed_frames+=(uint32_t)got;
        } else {
            if (wr - rd < AUD_BLOCK) {
                const uint64_t t0 = sa1_plat_time_us();
                const uint64_t p0 = pause_clock();
                unsigned intr = sceKernelCpuSuspendIntr();
                wait_since = t0;
                wait_pause_start=p0;
                sceKernelCpuResumeIntr(intr);
                while (run && (menu_paused || wr-rd<AUD_BLOCK)) {
                    if(menu_paused){pause_ack=1;sceKernelDelayThread(10000);}
                    else if(pause_ack){pause_ack=0;}
                    else {waiting=1;sceKernelWaitSema(sema,1,NULL);}
                }
                /* Retire the pause ACK before consuming a resumed block. */
                pause_ack=0;
                uint64_t elapsed=sa1_plat_time_us()-t0,paused=pause_clock()-p0;
                intr = sceKernelCpuSuspendIntr();
                starves++; starve_us += audio_unpaused_wait(elapsed,paused); wait_since = 0;
                sceKernelCpuResumeIntr(intr);
                if (!run) break;
            }
            for (uint32_t i = 0; i < AUD_BLOCK; ) {     /* at most two runs around the ring's end */
                const uint32_t at = (rd + i) & (AUD_RING - 1), k = AUD_RING - at < AUD_BLOCK - i ? AUD_RING - at : AUD_BLOCK - i;
                memcpy(o + 2 * i, ring + 2 * at, 4 * k);
                i += k;
            }
            rd += AUD_BLOCK;
        }
        sceKernelDcacheWritebackRange(o, sizeof block[0]);
        unsigned intr = sceKernelCpuSuspendIntr();
        output_calls++; output_busy = 1;
        sceKernelCpuResumeIntr(intr);
        int rc = audio_psp_out2 ? sceAudioOutput2OutputBlocking(PSP_AUDIO_VOLUME_MAX, o)
            : sceAudioOutputBlocking(ch, PSP_AUDIO_VOLUME_MAX, o);
        intr = sceKernelCpuSuspendIntr();
        if (rc < 0) output_errors++;
        output_busy = 0;
        sceKernelCpuResumeIntr(intr);
        /* Failed OutputBlocking does not pace the real-time mixer. Bound retry
         * work to one block period, with the CPU available to the game/exit. */
        if(rc<0)sceKernelDelayThread((AUD_BLOCK*1000000u+44099u)/44100u);
        b ^= 1;
    }
    pause_ack=0;return 0;
}

int audio_open(uint32_t rate, uint32_t channels) {
    if (!audio_psp_enabled || rate != 44100 || channels != 2 || ch>=0 || th>=0 || core_sema>=0 || sema>=0) return -1;
    ch = audio_psp_out2 ? sceAudioOutput2Reserve(AUD_BLOCK) : sceAudioChReserve(PSP_AUDIO_NEXT_CHANNEL, AUD_BLOCK, PSP_AUDIO_FORMAT_STEREO);
    if (audio_psp_out2 && ch >= 0) ch = 0;
    if (ch < 0) { sa1_log("audio: sceAudioChReserve failed (%08x)", (unsigned)ch); return -1; }
    wr=rd=0;
    sema = sceKernelCreateSema("sa1_audio",0,0,1,NULL);
    if(sema<0){audio_close();return -1;}
    if(snd_host_async_allowed()){
        core_sema=sceKernelCreateSema("sa1_core",0,1,1,NULL);
        if(core_sema<0){audio_close();return -1;}
        snd_host_async_set(&real_ops);
    }
    run=1;
    th=sceKernelCreateThread("sa1_audio",out_thread,0x12,0x4000,0,NULL);
    if(th<0){run=0;audio_close();return -1;}
    if(sceKernelStartThread(th,0,NULL)<0){
        run=0;
        if(sceKernelDeleteThread(th)<0){shutdown_failed=1;return -1;}
        th=-1;audio_close();return -1;
    }
    sa1_log("audio: %s %d, %u-frame blocks, %u frames buffered before the start; realtime=%d", audio_psp_out2 ? "sceAudioOutput2" : "sceAudio channel", ch, AUD_BLOCK, snd_host_async_active()?0u:AUD_START,snd_host_async_active());
    return 0;
}

void audio_push(const int16_t *samples, uint32_t frames) {
    if (ch < 0) return;
    if (wr - rd + frames > AUD_MAX) { dropped += frames; return; }
    for (uint32_t i = 0; i < frames; ) {
        const uint32_t at = (wr + i) & (AUD_RING - 1), k = AUD_RING - at < frames - i ? AUD_RING - at : frames - i;
        memcpy(ring + 2 * at, samples + 2 * i, 4 * k);
        i += k;
    }
    __asm__ volatile("sync" ::: "memory");   /* the samples before the index */
    wr += frames;
    pushed_frames += frames;
    if (waiting) { waiting = 0; sceKernelSignalSema(sema, 1); }   /* no polling: the thread waits for this */
}

uint32_t audio_queued_frames(void) { return ch < 0 ? 0 : (wr - rd) + AUD_BLOCK; }

void audio_close(void) {
    if(ch<0&&th<0&&sema<0&&core_sema<0)return;
    run=0;
    if(sema>=0)sceKernelSignalSema(sema,1);
    if(th>=0){
        SceUInt timeout=1500000u;
        if(sceKernelWaitThreadEnd(th,&timeout)<0||sceKernelDeleteThread(th)<0){
            shutdown_failed=1;sa1_log("audio: cleanup retained: worker ownership uncertain");return;
        }
        th=-1;
    }
    if(ch>=0){
        /* A joined producer does not prove the device consumed its last block.
         * Wait for the hardware reader before releasing this reserved channel. */
        uint64_t deadline=sa1_plat_time_us()+500000u;
        for(;;){
            int rest=audio_psp_out2?sceAudioOutput2GetRestSample():sceAudioGetChannelRestLen(ch);
            if(rest<0||sa1_plat_time_us()>=deadline){
                shutdown_failed=1;sa1_log("audio: cleanup retained: hardware drain rest=%d",rest);return;
            }
            if(!rest)break;
            sceKernelDelayThread(1000);
        }
        int rc=audio_psp_out2?sceAudioOutput2Release():sceAudioChRelease(ch);
        if(rc<0){shutdown_failed=1;sa1_log("audio: cleanup retained: channel release %d",rc);return;}
        ch=-1;
    }
    snd_host_async_set(NULL); /* only after proved join */
    if(core_sema>=0){if(sceKernelDeleteSema(core_sema)<0){shutdown_failed=1;return;}core_sema=-1;}
    if(sema>=0){if(sceKernelDeleteSema(sema)<0){shutdown_failed=1;return;}sema=-1;}
    waiting=0;shutdown_failed=0;
    sa1_log("audio: %u waits for the game (%.1f s in all), %u frames dropped",starves,starve_us/1e6,dropped);
}
