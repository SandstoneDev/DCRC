/* Pure instrumentation state, no SDK, waits or rendering decisions. MIT.
 * GetFrameBuf mode 0 observes current LCD buffer; mode 1 is only next VSYNC.
 * Observations count distinct submitted pictures at most once, not refreshes.
 * Missing observations remain unknown: this is an observed lower bound, never
 * an optical proof, nor a claim that every accepted swap reached the display. */
#pragma once
#include <stdint.h>
typedef struct {
    uint32_t submitted, completed, complete_errors, swap_requests, scheduled, schedule_errors;
    uint32_t latched, visible, hidden, foreground_unknown;
    uint32_t query_errors, coverage_gaps, unresolved;
    uint32_t pending_seq, pending_fb;
} display_counter;
static inline uint32_t dc_fb(uint32_t p) { return p & ~UINT32_C(0x40000000); }
static inline void dc_submit(display_counter *c) { c->submitted++; }
static inline void dc_complete(display_counter *c) { c->completed++; }
static inline void dc_schedule(display_counter *c, uint32_t seq, uint32_t fb,
                               int before_ok, uint32_t before_fb) {
    c->scheduled++;
    int repeated_pending = c->pending_seq && c->pending_fb == dc_fb(fb);
    if (c->pending_seq) { c->coverage_gaps++; c->unresolved++; }
    c->pending_seq = 0;
    /* A reused address already current cannot identify the new incarnation. */
    if (!before_ok || repeated_pending || dc_fb(fb) == dc_fb(before_fb)) {
        c->coverage_gaps++; c->unresolved++; return;
    }
    c->pending_seq = seq; c->pending_fb = dc_fb(fb);
}
static inline void dc_observe(display_counter *c, int ok, uint32_t fb, int foreground) {
    if (!ok) { c->query_errors++; return; }
    if (!c->pending_seq || dc_fb(fb) != c->pending_fb) return;
    c->latched++;
    if (foreground == 1) c->visible++;
    else if (foreground == 0) c->hidden++;
    else c->foreground_unknown++;
    c->pending_seq = 0;
}
/* Unobserved game frames become unknown before menu reuses their buffers. */
static inline void dc_untracked_reuse(display_counter *c) {
    if(c->pending_seq){c->coverage_gaps++;c->unresolved++;c->pending_seq=0;}
}
