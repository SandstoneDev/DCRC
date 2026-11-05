#include "../../backend/psp/display_counter.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    display_counter c = {0};
    dc_submit(&c); dc_complete(&c);
    dc_schedule(&c, 1, 0x04000000u, 1, 0x04044000u);
    dc_observe(&c, 1, 0x04044000u, 1); assert(c.latched == 0);
    dc_observe(&c, 1, 0x44000000u, 1); assert(c.latched == 1 && c.visible == 1);
    dc_observe(&c, 1, 0x04000000u, 1); assert(c.latched == 1);
    dc_submit(&c); dc_complete(&c);
    dc_schedule(&c, 2, 0x04044000u, 1, 0x04000000u);
    dc_observe(&c, 0, 0, 1); assert(c.query_errors == 1 && c.pending_seq == 2);
    dc_observe(&c, 1, 0x04044000u, 0); assert(c.latched == 2 && c.hidden == 1);
    dc_schedule(&c, 3, 0x04000000u, 1, 0x04044000u);
    dc_schedule(&c, 4, 0x04044000u, 1, 0x04000000u);
    assert(c.coverage_gaps == 1 && c.unresolved == 1);
    dc_observe(&c, 1, 0x04044000u, -1); assert(c.foreground_unknown == 1);
    dc_schedule(&c, 5, 0x04044000u, 1, 0x04044000u);
    assert(c.coverage_gaps == 2 && !c.pending_seq); /* same-address ABA is unknown */
    dc_schedule(&c, 6, 0x04000000u, 0, 0);
    assert(c.coverage_gaps == 3 && !c.pending_seq); /* baseline query failed */
    assert(c.submitted == 2 && c.completed == 2 && c.scheduled == 6);
    /* A failed pre-observation plus a duplicated pending address cannot
     * identify whether its old incarnation latched across the API call. */
    dc_schedule(&c, 7, 0x04000000u, 1, 0x04044000u);
    dc_schedule(&c, 8, 0x04000000u, 1, 0x04044000u);
    assert(!c.pending_seq && c.coverage_gaps == 5);
    /* Both pipeline modes feed the same submit/complete/accepted/observe
     * contract; completion alone and scheduling alone never count display. */
    for (int pipelined = 0; pipelined <= 1; pipelined++) {
        display_counter d = {0};
        for (uint32_t i = 1; i <= 128; i++) {
            uint32_t fb = (i & 1) ? 0x04000000u : 0x04044000u;
            uint32_t prior = (i & 1) ? 0x04044000u : 0x04000000u;
            dc_submit(&d);
            assert(d.latched == i - 1);
            /* pipeline: guest work can occur here without completion */
            if (pipelined) dc_observe(&d, 1, prior, 1);
            dc_complete(&d); dc_schedule(&d, i, fb, 1, prior);
            assert(d.latched == i - 1);
            dc_observe(&d, 1, fb, 1); dc_observe(&d, 1, fb, 1);
        }
        assert(d.submitted == 128 && d.completed == 128);
        assert(d.scheduled == 128 && d.latched == 128 && d.visible == 128);
        assert(!d.coverage_gaps && !d.pending_seq);
    }
    puts("display counter state machine PASS");
    return 0;
}
