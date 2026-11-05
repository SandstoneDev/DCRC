#include "../../backend/psp/display_counter.h"
#include <assert.h>
int main(void){
    display_counter c={0};dc_schedule(&c,1,0x04000000,1,0x04044000);
    dc_observe(&c,1,0x04044000,1);assert(c.pending_seq==1&&!c.visible);
    dc_observe(&c,1,0x04000000,1);dc_untracked_reuse(&c);assert(c.visible==1&&!c.pending_seq);
    dc_schedule(&c,2,0x04044000,1,0x04000000);dc_observe(&c,0,0,1);
    dc_untracked_reuse(&c);assert(!c.pending_seq&&c.unresolved==1);
    dc_observe(&c,1,0x04044000,1);assert(c.visible==1);return 0;
}
