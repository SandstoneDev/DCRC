/* Intentional menu pause must not become an audio-starvation interval. MIT. */
#pragma once
#include <stdint.h>
static inline uint64_t audio_unpaused_wait(uint64_t elapsed,uint64_t paused){return elapsed>paused?elapsed-paused:0;}
