/* snd_host.c - main-side sound glue (see snd_host.h).
 *
 * Part of sa1-psp (MIT). */
#include "snd_host.h"
#include "../hle.h"
#include "../../backend/audio.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int snd_voice_lang = -1;
int snd_voice_lang_cli = -2;
int snd_guest_timing = 1;
uint64_t snd_render_us, snd_render_frames;

static snd_shared *sh;
static snd_core *core;
static int device_ok = -1;          /* -1 not tried, 0 none, 1 open */
static FILE *wav;
static uint32_t wav_frames;

/* One feeder per stream: which file, where the ADX starts, and the next
 * block group to send in play order (snd_core.h, the loop rule). */
typedef struct feeder {
    uint8_t on, done;
    char path[128];
    uint8_t pending;                /* started, the core not told yet (in the padding: states keep their size) */
    uint32_t base, size;
    adx_info info;
    uint32_t q;                     /* play-order index of the next group */
    uint32_t gen;
    uint64_t start_clock;           /* frame clock when it plays (status 3) */
} feeder;
/* The console's ADXT player (Flycast, every voice line of a Station Square
 * cutscene) shows status 1 for 6 frames after a start and 2 for 2 more
 * before it plays (3), and 4 over the last 22 frames before it ends (5);
 * from 3 to 5 is the stream's length. */
#define STREAM_PREP_FRAMES 8
#define STREAM_PREP2_FRAMES 2
#define STREAM_DRAIN_FRAMES 22
static feeder feed[SND_STREAMS];
static uint32_t generation;
/* The frame clock: output samples of every guest frame so far, 735 a frame,
 * advanced whether or not the core renders.  What the guest sees of a
 * stream is computed from it and the stream's header, never from the
 * core's progress, so it is the same when the core runs late on another
 * processor, or not at all (audio = off). */
static uint64_t clock_samples;
static const snd_async_ops *async_ops;
int snd_audio_enabled = 1;
void snd_host_set_audio(int enabled) {
    if(snd_host_begin_update(0)<0)return;
    if(enabled && !snd_audio_enabled && device_ok==0)device_ok=-1;
    snd_audio_enabled=enabled?1:0;
    snd_host_end_update();
    if(async_ops)async_ops->wake();
}

/* Own real-time adaptation of the owner's old DCRC output-worker mechanism.
 * Guest status/time deliberately remain guest-clocked. No file IO on worker. */
static unsigned update_depth;
static int async_fault,async_used;
static uint32_t cmd_dropped, cmd_waits, update_denied, async_lock_denied,bootstrap_denied;
static uint64_t async_samples, stream_short[2];
int snd_host_async_allowed(void) { return !hle_strict && !wav; }
int snd_host_async_active(void) { return async_ops != NULL; }
void snd_host_async_set(const snd_async_ops *ops) { async_ops=ops;if(ops)async_used=1; }
int snd_host_begin_update(uint32_t slots) {
    if(slots>SND_CMD_RING)return -1;
    if(update_depth){ /* only the guest owner nests; worker never calls here */
        if(sh&&sh->cmds.head-sh->cmds.tail>SND_CMD_RING-slots)return -1;
        update_depth++;return 0;
    }
    for(unsigned tries=0;tries<=100;tries++) {
        if(!sh||sh->cmds.head-sh->cmds.tail<=SND_CMD_RING-slots) {
            if(async_ops&&async_ops->enter(500000u)<0){update_denied++;return -1;}
            update_depth=1;return 0; /* sole producer: room cannot shrink */
        }
        if(!async_ops){int16_t dummy[2];snd_core_render(core,dummy,0);continue;}
        if(tries==100)break;
        async_ops->wake();async_ops->yield();cmd_waits++;
    }
    update_denied++;return -1;
}
void snd_host_end_update(void) {
    if(update_depth&&!--update_depth&&async_ops){async_ops->leave();async_ops->wake();}
}
int snd_host_required_cmd(uint8_t op,uint8_t a,int32_t x,int32_t y) {
    snd_cmd cmd={op,a,0,0,x,y};
    if(!sh||!update_depth||snd_cmd_push(sh,&cmd)<0) {
        /* Failed mandatory publication never exposes changed bytes to mixer. */
        async_fault=1;cmd_dropped++;return -1;
    }
    return 0;
}
int snd_host_async_render(int16_t *out,uint32_t n) {
    if(!async_ops||!core)return -1;
    if(async_ops->enter(5000u)<0){async_lock_denied++;return -1;}
    if(async_fault){async_ops->leave();return -1;}
    uint32_t played[2],gen[2];
    for(int i=0;i<2;i++){played[i]=sh->status[i].played;gen[i]=sh->status[i].generation;}
    uint32_t count=snd_audio_enabled?n:0;
    uint64_t t=sa1_plat_time_us();snd_core_render(core,out,count);
    snd_render_us+=sa1_plat_time_us()-t;
    if(count){snd_render_frames++;async_samples+=count;}
    for(int i=0;i<2;i++)if(sh->status[i].state==3) {
        uint32_t got=sh->status[i].played-(gen[i]==sh->status[i].generation?played[i]:0);
        if(got<count)stream_short[i]+=count-got;
    }
    async_ops->leave();return (int)count;
}

snd_shared *snd_host_shared(void) { return sh; }

void snd_host_cmd(uint8_t op, uint8_t a, uint8_t b, uint8_t c, int32_t x, int32_t y) {
    if (!sh) return;
    snd_cmd k = { op, a, b, c, x, y };
    if(snd_cmd_push(sh,&k)==0){if(async_ops&&!snd_audio_enabled)async_ops->wake();return;}
    if(async_ops){
        /* Never wait with the core gate held; never render on the producer. */
        if(!update_depth)for(unsigned i=0;i<100;i++){
            async_ops->wake();async_ops->yield();cmd_waits++;
            if(snd_cmd_push(sh,&k)==0)return;
        }
        cmd_dropped++;return;
    }
    int16_t tmp[2];snd_core_render(core,tmp,0);
    if(snd_cmd_push(sh,&k)<0)cmd_dropped++;
}

void snd_host_init(void) {
    if(snd_host_begin_update(0)<0)return;
    if (!sh) {
        sh = calloc(1, sizeof *sh);
        sh->sound_ram = calloc(1, SND_RAM_SIZE);
        core = calloc(1, snd_core_size());
    } else {
        memset(sh->sound_ram, 0, SND_RAM_SIZE);
        uint8_t *ram = sh->sound_ram;
        memset(sh, 0, sizeof *sh);
        sh->sound_ram = ram;
    }
    snd_core_init(core, sh);
    async_fault=0;
    /* SA1_SND_MUTE=fx,music,voice: leave those out of the mix (stems for
     * the M3 exit test); everything still runs */
    const char *mu = getenv("SA1_SND_MUTE");
    if (mu) sh->mute = (strstr(mu, "fx") ? SND_MUTE_FX : 0) | (strstr(mu, "music") ? SND_MUTE_MUSIC : 0) | (strstr(mu, "voice") ? SND_MUTE_VOICE : 0);
    const char *so = getenv("SA1_SND_SOLO");      /* BANK:PROGRAM, with SA1_SND_MUTE=music,voice */
    if (so) { int b = 0, pr = 0; if (sscanf(so, "%d:%d", &b, &pr) == 2) sh->solo = 0x10000u | (uint32_t)(b & 0xFF) << 8 | (uint32_t)(pr & 0xFF); }
    memset(feed, 0, sizeof feed);
    generation = 0;
    clock_samples = 0;
    snd_host_end_update();
}

/* ---- streams ---------------------------------------------------------------- */
static uint32_t play_group(const feeder *f, uint32_t q) {
    uint32_t G = adx_play_groups(&f->info);
    if (q < G) return q;
    uint32_t L = adx_group_of(f->info.loop_start);
    return L + (q - G) % (G - L);
}

/* Main-thread file IO only. This changes a private feeder or the main-owned
 * feeder cursor, never core metadata. Caller publishes bytes through SPSC head. */
static uint32_t fetch_groups(feeder *f,uint8_t *buf,uint32_t room) {
    uint32_t gb=adx_group_bytes(&f->info),G=adx_play_groups(&f->info);
    if(!f->info.loop&&f->q>=G){f->done=1;return 0;}
    uint32_t g0=play_group(f,f->q),n=0;
    while(n<64&&n<room){
        if(!f->info.loop&&f->q+n>=G)break;
        if(play_group(f,f->q+n)!=g0+n)break;
        n++;
    }
    if(!n)return 0;
    int got=sa1_plat_file_read_stream(f->path,f->base+f->info.data_off+g0*gb,buf,n*gb);
    if(got<(int)(n*gb)){if(got<0)got=0;memset(buf+got,0,n*gb-(uint32_t)got);}
    f->q+=n;return n*gb;
}
static uint32_t stream_target(const feeder *f) {
    uint32_t want=(f->info.rate/4/ADX_BLOCK_SAMPLES+2)*adx_group_bytes(&f->info);
    return want>SND_STREAM_RING/2?SND_STREAM_RING/2:want;
}
/* Same quarter-second target and64KB rings as before; no output-thread IO. */
static void feed_stream(int si) {
    feeder *f=&feed[si];if(!f->on||f->done||f->pending)return;
    snd_byte_ring *r=&sh->stream_data[si];uint32_t gb=adx_group_bytes(&f->info);
    uint8_t buf[ADX_BLOCK*ADX_MAX_CH*64];
    while(SND_STREAM_RING-snd_ring_free(r)<stream_target(f)&&snd_ring_free(r)>=gb){
        uint32_t n=fetch_groups(f,buf,snd_ring_free(r)/gb);if(!n)return;
        snd_ring_write(r,buf,n);
    }
}

int snd_stream_start(int si, const char *path, uint32_t off, uint32_t size) {
    if (!sh || si < 0 || si >= SND_STREAMS) return -1;
    uint8_t hdr[0x80];
    int got = sa1_plat_file_read(path, off, hdr, sizeof hdr);
    adx_info info;
    if (got < 0x20 || adx_parse(hdr, (uint32_t)got, &info) != 0) {
        sa1_log("snd: stream %d: \"%s\" +0x%x is not an ADX this decoder plays", si, path, off);
        return -1;
    }
    (void)size;
    if(snd_host_begin_update(1)<0)return -1;
    feeder *f = &feed[si];
    if(f->on&&!f->pending&&snd_host_required_cmd(SND_CMD_STREAM_STOP,(uint8_t)si,0,0)<0){snd_host_end_update();return -1;}
    memset(f, 0, sizeof *f);
    snprintf(f->path, sizeof f->path, "%s", path);
    f->base = off; f->size = size; f->info = info; f->on = 1;
    f->gen = ++generation;
    f->start_clock = clock_samples + (uint64_t)STREAM_PREP_FRAMES * SND_FRAME_SAMPLES;
    f->pending = 1;
    snd_host_end_update();
    return 0;
}

/* The core starts a stream when the guest sees it play. */
static void begin_stream(int si) {
    feeder *f=&feed[si];if(!f->on||!f->pending||clock_samples<f->start_clock)return;
    if(!async_ops){ /* preserve the original deterministic path, including no temporary allocation */
        f->pending=0;sh->stream_info[si]=f->info;
        uint32_t pos=sh->stream_data[si].head;feed_stream(si);
        snd_host_cmd(SND_CMD_STREAM_START,(uint8_t)si,0,0,(int32_t)pos,(int32_t)f->gen);return;
    }
    /* Bootstrap IO is private and outside the core gate: the worker can keep
     * rendering the old generation until this transaction is ready to publish. */
    feeder staged=*f;uint32_t want=stream_target(f),gb=adx_group_bytes(&f->info),bytes=0;
    sa1_temp_block temp={NULL,-1};
    uint8_t *buf=sa1_plat_temp_alloc(want,&temp);if(!buf){bootstrap_denied++;return;}
    while(bytes+gb<=want){uint32_t got=fetch_groups(&staged,buf+bytes,(want-bytes)/gb);if(!got)break;bytes+=got;}
    if(!bytes||snd_host_begin_update(1)<0){sa1_plat_temp_free(&temp);return;}
    snd_byte_ring *r=&sh->stream_data[si];
    if(snd_ring_free(r)<bytes){snd_host_end_update();sa1_plat_temp_free(&temp);return;}
    uint32_t pos=r->head;
    sh->stream_info[si]=f->info;snd_ring_write(r,buf,bytes);
    if(snd_host_required_cmd(SND_CMD_STREAM_START,(uint8_t)si,(int32_t)pos,(int32_t)f->gen)==0){
        *f=staged;f->pending=0;
    }
    snd_host_end_update();sa1_plat_temp_free(&temp);
}

void snd_stream_stop(int si) {
    if (!sh || si < 0 || si >= SND_STREAMS) return;
    if(snd_host_begin_update(1)<0)return;
    feed[si].on = 0;
    snd_host_required_cmd(SND_CMD_STREAM_STOP,(uint8_t)si,0,0);
    snd_host_end_update();
}

void snd_stream_volume(int si, int32_t v) { snd_host_cmd(SND_CMD_STREAM_VOL, (uint8_t)si, 0, 0, v, 0); }

/* Source samples a stream has played by now (loops counted on). */
static uint64_t stream_pos(const feeder *f) {
    if (clock_samples < f->start_clock) return 0;
    uint64_t elapsed = clock_samples - f->start_clock;
    return elapsed * f->info.rate / SND_RATE;
}

uint32_t snd_stream_state(int si) {
    if (!sh || si < 0 || si >= SND_STREAMS || !feed[si].on) return 0;
    const feeder *f = &feed[si];
    if (clock_samples < f->start_clock)
        return f->start_clock - clock_samples > (uint64_t)STREAM_PREP2_FRAMES * SND_FRAME_SAMPLES ? 1 : 2;
    if (f->info.loop) return 3;
    uint64_t p = stream_pos(f);
    if (p >= f->info.samples) return 5;
    if ((f->info.samples - p) * SND_RATE < (uint64_t)STREAM_DRAIN_FRAMES * SND_FRAME_SAMPLES * f->info.rate) return 4;
    return 3;
}

void snd_stream_time(int si, uint32_t *count, uint32_t *rate) {
    *count = 0; *rate = 1;
    if (!sh || si < 0 || si >= SND_STREAMS || !feed[si].on) return;
    const feeder *f = &feed[si];
    uint64_t p = stream_pos(f);
    if (!f->info.loop && p > f->info.samples) p = f->info.samples;
    *count = (uint32_t)p;
    *rate = f->info.rate;
}

/* ---- output ------------------------------------------------------------------ */
static void wav_header(FILE *f, uint32_t frames) {
    uint32_t data = frames * 4;
    uint8_t h[44] = { 'R','I','F','F', 0,0,0,0, 'W','A','V','E', 'f','m','t',' ', 16,0,0,0, 1,0, 2,0,
                      0x44,0xAC,0,0, 0x10,0xB1,2,0, 4,0, 16,0, 'd','a','t','a', 0,0,0,0 };
    uint32_t riff = 36 + data;
    for (int i = 0; i < 4; i++) { h[4 + i] = (uint8_t)(riff >> (8 * i)); h[40 + i] = (uint8_t)(data >> (8 * i)); }
    fseek(f, 0, SEEK_SET);
    fwrite(h, 1, sizeof h, f);
    fseek(f, 0, SEEK_END);
}

static void wav_close(void) {
    if (!wav) return;
    wav_header(wav, wav_frames);
    fclose(wav);
    wav = NULL;
}

void snd_host_set_wav(const char *path) {
    if(async_ops){sa1_log("snd: WAV recording unavailable during realtime playback");return;}
    wav = fopen(path, "wb");
    if (!wav) { sa1_log("snd: cannot write %s", path); return; }
    wav_header(wav, 0);
    atexit(wav_close);
    sa1_log("snd: recording to %s", path);
}

void snd_host_frame(void) {
    if (!sh) return;
    if (device_ok < 0) {
        device_ok = snd_audio_enabled && audio_open(SND_RATE, 2) == 0;
        sa1_log("snd: %s", device_ok ? "audio device open (44.1 kHz stereo)" : "no audio device; the core runs silent");
    }
    clock_samples += SND_FRAME_SAMPLES;
    for (int si = 0; si < SND_STREAMS; si++) begin_stream(si);
    if (!snd_audio_enabled) return;
    for (int si = 0; si < SND_STREAMS; si++) feed_stream(si);
    if(async_ops)return; /* hardware worker owns real-time PCM, never guest clock */
    int16_t out[2 * SND_FRAME_SAMPLES];
    uint64_t t0 = sa1_plat_time_us();
    snd_core_render(core, out, SND_FRAME_SAMPLES);
    snd_render_us += sa1_plat_time_us() - t0;
    snd_render_frames++;
    if (device_ok) audio_push(out, SND_FRAME_SAMPLES);
    if (wav) { fwrite(out, 4, SND_FRAME_SAMPLES, wav); wav_frames += SND_FRAME_SAMPLES; }
    for (int si = 0; si < SND_STREAMS; si++) feed_stream(si);
}

/* ---- save states ---------------------------------------------------------------- */
void snd_host_state(hle_state_io *io) {
    if (!sh) snd_host_init();
    if(!sh||snd_host_begin_update(0)<0){hle_state_fail(io,"sound core is busy");return;}
    /* the two host pointers (the core's to the shared block, the shared
     * block's to sound RAM) are not state: zero them in the saved bytes,
     * so a state is the same whichever process wrote it, and set them back */
    uint8_t *ram = sh->sound_ram;
    sh->sound_ram = NULL;
    snd_core_rebind(core, NULL);
    hle_state_blob(io, "snd.shared", sh, sizeof *sh);
    hle_state_blob(io, "snd.core", core, snd_core_size());
    sh->sound_ram = ram;
    snd_core_rebind(core, sh);
    hle_state_blob(io, "snd.ram", ram, SND_RAM_SIZE);
    hle_state_blob(io, "snd.feed", feed, sizeof feed);
    hle_state_blob(io, "snd.gen", &generation, sizeof generation);
    hle_state_blob(io, "snd.clock", &clock_samples, sizeof clock_samples);
    snd_host_end_update();
}

void snd_sd_report(void);       /* sd.c */
void snd_adxt_report(void);     /* adxt.c */

void snd_host_report(void) {
    if(snd_host_begin_update(0)<0){sa1_log("snd: report declined: core busy");return;}
    uint64_t us=snd_render_us,calls=snd_render_frames,samples=async_samples;
    uint64_t short0=stream_short[0],short1=stream_short[1];
    uint32_t dropped=cmd_dropped,waits=cmd_waits,denied=update_denied,worker_denied=async_lock_denied,bootstrap=bootstrap_denied;
    int fault=async_fault;
    snd_host_end_update(); /* card/log IO must never hold the core gate */
    snd_sd_report();snd_adxt_report();
    sa1_log("snd-realtime: active=%d used=%d fault=%d pcm_samples=%llu cmd_dropped=%u cmd_waits=%u update_denied=%u worker_lock_denied=%u bootstrap_denied=%u stream_short_bgm=%llu voice=%llu guest_clock_unchanged=1",
        async_ops!=NULL,async_used,fault,(unsigned long long)samples,dropped,waits,denied,worker_denied,bootstrap,
        (unsigned long long)short0,(unsigned long long)short1);
    if(calls)sa1_log("snd: core %.1f us per render (decode + mix; guest quantum %u samples), %llu calls; output latency %u frames",
        (double)us/(double)calls,SND_FRAME_SAMPLES,(unsigned long long)calls,device_ok>0?audio_queued_frames():0);
    sa1_log("snd-clock: cumulative=1 guest_samples=%llu mix_frames=%llu mix_us=%llu enabled=%d device=%d queue_estimate_only=1",
        (unsigned long long)clock_samples,(unsigned long long)calls,(unsigned long long)us,snd_audio_enabled,device_ok);
}
