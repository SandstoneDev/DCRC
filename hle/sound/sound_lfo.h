// license:BSD-3-Clause
// copyright-holders:ElSemi, Deunan Knute, R. Belmont
// thanks-to: kingshriek
/* Standalone adaptation of MAME AICA LFO unsigned amplitude-wave generation.
 * Source: MAME df3bcbba30251a393d8bb33a356c6c2ee93c34e9
 * src/devices/sound/aica.cpp:1589-1646 (BSD-3-Clause).
 * Original copyright holders: ElSemi, Deunan Knute, R. Belmont.
 * Standalone adaptation and independent deterministic noise: DCRC contributors, 2026.
 *
 * Changes: class/table writes become a bounded scalar helper; phase is reduced
 * modulo256; MAME's external RNG is replaced with an own deterministic phase
 * hash; rounded nominal frequencies become nearest integer sample intervals.
 * Both-random-wave interval1 is retained as an explicit compatibility rule.
 * This selects a new reference LFO model: audio/phase/PSP parity is UNPROVEN.
 * No code from Flycast's GPL LFO helpers is included.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met:
 *
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its
 *    contributors may be used to endorse or promote products derived from
 *    this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
 * IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
 * TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
 * PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT
 * HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
 * TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
 * PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
 * LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
 * NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
 * SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
#ifndef DCRC_SOUND_LFO_H
#define DCRC_SOUND_LFO_H
#include <stdint.h>

/* MAME LFO_Init's unsigned ALFO convention. These are amplitude waves,
 * also usable by the caller's existing centered pitch-ratio table. The
 * latter composition is a compatibility choice, not MAME PLFO emulation. */
static inline uint8_t dcrc_lfo_wave(uint32_t wave, uint32_t p) {
    uint32_t a;
    p &= 255u;
    switch (wave) {
    case 0:
        a = 255u - p;
        break;
    case 1:
        if (p < 128u) a = 255u;
        else a = 0;
        break;
    case 2:
        if (p < 128u) a = 255u - p * 2u;
        else a = p * 2u - 256u;
        break;
    default: {
        /* Own repeatable phase hash; NOT a measured AICA noise generator,
         * MAME machine RNG, or Flycast noise mapping. No persistent state. */
        uint32_t x = (p + 1u) * 40503u;
        x ^= x >> 7;
        a = (x >> 13) & 255u;
        break;
    }
    }
    return (uint8_t)a;
}

static inline uint32_t dcrc_lfo_period(uint32_t reg) {
    /* Nearest sample counts round(44100 / (256 * MAME LFOFreq[n])).
     * Derived from the BSD source's32 rounded nominal Hz values; this is
     * deliberately NOT a claim of exact physical divider timing. */
    static const uint16_t interval[32] = {
        1013,907,749,638,507,442,383,313,253,221,187,157,124,108,92,76,
        60,52,44,36,28,24,20,16,12,10,8,6,4,3,2,1
    };
    /* ALFOWS bits3..4 and PLFOWS bits8..9 both select random. */
    if ((reg & 0x318u) == 0x318u) return 1;
    return interval[(reg >> 10) & 31u];
}
#endif
