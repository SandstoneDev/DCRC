/* audio_psp.c - backend/audio.h on the PSP: one sceAudio channel fed by its
 * own thread.
 *
 * The game's thread renders 735 frames per guest frame (hle/sound/snd_host.c)
 * and audio_push copies them into a ring; the output thread takes blocks of
 * AUD_BLOCK frames from the ring and hands each to sceAudioOutputBlocking,
 * which returns when the channel can take the next one, so the hardware
 * paces the thread.  The ring is single producer, single consumer: the game
 * thread moves only the write index, the output thread only the read index.
 * When the game is slower than real time the thread waits for a whole block
 * (the channel plays out what it has, then a gap; padding part-blocks with
 * silence made more, shorter gaps), and counts the waits.  When the game
 * runs ahead (an unpaced run, a catch-up after a load) a push beyond AUD_MAX
 * buffered frames is dropped, so the latency cannot drift.  The mixer
 * itself stays on the game's thread (the Media Engine is not used: the
 * toolchain has no ME loader).
 *
 * Part of sa1-psp (MIT). */
#include "../audio.h"
#include "hle.h"
#include "../audio_pause_clock.h"

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
static SceUID th = -1, sema = -1;
static volatile int waiting;            /* the thread sleeps on sema until a push */
static uint32_t starves, dropped;
static uint64_t starve_us;
static uint64_t wait_since;
static uint64_t wait_pause_start;
static uint32_t pushed_frames, output_calls, output_errors;
static int output_busy;
static volatile int menu_paused;
static uint64_t menu_pause_start,menu_pause_total;
void audio_psp_pause(int on) {
    unsigned intr=sceKernelCpuSuspendIntr();
    uint64_t now=sa1_plat_time_us();
    if(on && !menu_paused){menu_pause_start=now;menu_paused=1;}
    else if(!on && menu_paused){menu_pause_total+=now-menu_pause_start;menu_paused=0;}
    sceKernelCpuResumeIntr(intr);
    if(sema>=0)sceKernelSignalSema(sema,1);
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
}

static int out_thread(SceSize args, void *argp) {
    (void)args; (void)argp;
    int b = 0;
    while (wr - rd < AUD_START && run) { waiting = 1; sceKernelWaitSema(sema, 1, NULL); }
    while (run) {
        if(menu_paused){sceKernelDelayThread(10000);continue;}
        if (wr - rd < AUD_BLOCK) {
            const uint64_t t0 = sa1_plat_time_us();
            const uint64_t p0 = pause_clock();
            unsigned intr = sceKernelCpuSuspendIntr();
            wait_since = t0;
            wait_pause_start=p0;
            sceKernelCpuResumeIntr(intr);
            while (run && (menu_paused || wr-rd<AUD_BLOCK)) {
                if(menu_paused)sceKernelDelayThread(10000);
                else {waiting=1;sceKernelWaitSema(sema,1,NULL);}
            }
            uint64_t elapsed=sa1_plat_time_us()-t0,paused=pause_clock()-p0;
            intr = sceKernelCpuSuspendIntr();
            starves++; starve_us += audio_unpaused_wait(elapsed,paused); wait_since = 0;
            sceKernelCpuResumeIntr(intr);
            if (!run) break;
        }
        int16_t *o = block[b];
        for (uint32_t i = 0; i < AUD_BLOCK; ) {     /* at most two runs around the ring's end */
            const uint32_t at = (rd + i) & (AUD_RING - 1), k = AUD_RING - at < AUD_BLOCK - i ? AUD_RING - at : AUD_BLOCK - i;
            memcpy(o + 2 * i, ring + 2 * at, 4 * k);
            i += k;
        }
        rd += AUD_BLOCK;
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
        b ^= 1;
    }
    return 0;
}

int audio_open(uint32_t rate, uint32_t channels) {
    if (!audio_psp_enabled || rate != 44100 || channels != 2) return -1;
    ch = audio_psp_out2 ? sceAudioOutput2Reserve(AUD_BLOCK) : sceAudioChReserve(PSP_AUDIO_NEXT_CHANNEL, AUD_BLOCK, PSP_AUDIO_FORMAT_STEREO);
    if (audio_psp_out2 && ch >= 0) ch = 0;
    if (ch < 0) { sa1_log("audio: sceAudioChReserve failed (%08x)", (unsigned)ch); return -1; }
    run = 1;
    sema = sceKernelCreateSema("sa1_audio", 0, 0, 1, NULL);
    /* above the game's thread (0x20), so a block is never late because the
     * game is busy; it sleeps in sceAudioOutputBlocking almost all the time */
    th = sceKernelCreateThread("sa1_audio", out_thread, 0x12, 0x4000, 0, NULL);
    if (th < 0 || sceKernelStartThread(th, 0, NULL) < 0) {
        sa1_log("audio: output thread failed (%08x)", (unsigned)th);
        if (audio_psp_out2) sceAudioOutput2Release(); else sceAudioChRelease(ch);
        ch = -1; run = 0;
        return -1;
    }
    sa1_log("audio: %s %d, %u-frame blocks, %u frames buffered before the start", audio_psp_out2 ? "sceAudioOutput2" : "sceAudio channel", ch, AUD_BLOCK, AUD_START);
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
    if (ch < 0) return;
    run = 0;
    if (sema >= 0) sceKernelSignalSema(sema, 1);
    if (th >= 0) { sceKernelWaitThreadEnd(th, NULL); sceKernelDeleteThread(th); th = -1; }
    waiting = 0;
    /* Keep the final summary consumed by the existing devkit log readers. */
    sa1_log("audio: %u waits for the game (%.1f s in all), %u frames dropped", starves, starve_us / 1e6, dropped);
    if (audio_psp_out2) sceAudioOutput2Release(); else sceAudioChRelease(ch);
    ch = -1;
}
