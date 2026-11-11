/* Own streaming PCM/IMA WAV reader, adapted from the owner's DCRC/PS2RC reader.
 * Copyright (c) 2026 SandstoneDev. MIT. No game data or platform calls. */
#ifndef DCRC_MOVIE_WAV_H
#define DCRC_MOVIE_WAV_H
#include <stdint.h>

typedef int64_t (*movie_wav_read_fn)(void *ctx, uint64_t offset, void *dst, uint32_t bytes);

enum {
    MOVIE_WAV_OK = 0, MOVIE_WAV_E_READ = -1, MOVIE_WAV_E_NOT_WAVE = -2, MOVIE_WAV_E_FORMAT = -3, MOVIE_WAV_E_NO_DATA = -4,
    MOVIE_WAV_E_STAGING = -5
};

typedef struct {
    movie_wav_read_fn read;
    void *ctx;
    uint32_t format;                  /* 1 = PCM s16, 0x11 = IMA ADPCM */
    uint32_t channels, rate, block_align, frames_per_block;
    uint64_t data_off, data_len;      /* the data chunk in the file */
    uint64_t total_frames;            /* from the fact chunk (IMA) or the data size (PCM) */
    uint64_t frames_done;
    uint64_t file_pos;                /* next byte of the data chunk to read (relative to data_off) */
    uint8_t *stage;                   /* staging buffer: whole blocks */
    uint32_t stage_size, stage_len, stage_pos;
    /* IMA: the block being decoded */
    uint32_t blk_frame;               /* next frame index inside the current block (0 = header sample) */
    int32_t pred[2];
    int32_t index[2];
    const uint8_t *blk;               /* the current block inside the staging buffer */
} MovieWav;

/* parses the header (RIFF, fmt, fact, data); 0 or a MOVIE_WAV_E_* code */
int movie_wav_open(MovieWav *w, movie_wav_read_fn read, void *ctx, uint64_t file_size, uint8_t *stage, uint32_t stage_size);
/* up to `frames` stereo frames into dst; returns the frames written (0 = the end), or MOVIE_WAV_E_READ */
int movie_wav_read(MovieWav *w, int16_t *dst, uint32_t frames);
const char *movie_wav_format_name(const MovieWav *w);

#endif
