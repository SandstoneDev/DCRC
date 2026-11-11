/* Own PSP audio-worker FCSR policy, MIT, Copyright (c) 2026 SandstoneDev.
 * Match the primary guest-thread mixer: traps/causes off, flush, round to zero.
 * This does not change the game thread, output rate or any sample values. */
#pragma once
#include <stdint.h>
static inline uint32_t audio_realtime_fcsr(uint32_t old) {
    return (old & ~0x0003ff83u) | 0x01000001u;
}
