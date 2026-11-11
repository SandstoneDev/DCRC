/* Own optional firmware movie leaf. MIT, Copyright (c) 2026 SandstoneDev.
 * No game IDs, guest state, framebuffer addresses or asset paths. */
#ifndef DCRC_MOVIE_PSP_H
#define DCRC_MOVIE_PSP_H
#include <stdint.h>
typedef struct MoviePspHost {
    void *opaque;
    int (*begin)(void *); /* 0 success: renderer/audio quiesced, profile invalidated */
    int (*present)(void *,const uint16_t *picture,unsigned stride); /* 0 success; synchronous picture read completion */
    int (*end)(void *); /* 0 GPU drained/restored; negative retains picture/resources */
    int (*poll)(void *); /* nonzero exit request; service heartbeat/power */
    int (*audio_enabled)(void *); /* absent/zero means silent, wall-clock playback */
    int (*me_available)(void *); /* required positive; uncertainty declines */
} MoviePspHost;
enum MoviePspResult {
    MOVIE_PSP_NOT_PLAYED=0,MOVIE_PSP_FINISHED=1,MOVIE_PSP_SKIPPED=2,MOVIE_PSP_EXIT=3,
    MOVIE_PSP_FAILED=-1,MOVIE_PSP_CLEANUP_FATAL=-2
};
int movie_psp_play(const char *pmf,const char *wav,const MoviePspHost *host);
uint32_t movie_psp_heartbeat(void);
uint64_t movie_psp_paused_us(void);
int movie_psp_live(void); /* active or retained after uncertain worker teardown */
int movie_psp_shutdown(void); /* owner thread only; retry retained teardown */
void movie_psp_report(void);
#endif
