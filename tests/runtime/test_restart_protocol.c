/* Synthetic launch requests, no game data. MIT. */
#include "../../backend/psp/chain_protocol.h"
#include <assert.h>
#include <string.h>
int main(void) {
    sa1_chain_args r={0};
    strcpy(r.from,"ms0:/PSP/GAME/DCRC_OWN/EBOOT.PBP");
    strcpy(r.next,"ms0:/PSP/GAME/DCRC_OTHER/EBOOT.PBP");
    r.magic=SA1_CHAIN_MAGIC;assert(sa1_chain_request_valid(&r));
    strcpy(r.next,r.from);assert(!sa1_chain_request_valid(&r));
    r.magic=SA1_RESTART_MAGIC;assert(sa1_chain_request_valid(&r));
    strcpy(r.next,"ms0:/PSP/GAME/DCRC_OTHER/EBOOT.PBP");
    assert(!sa1_chain_request_valid(&r));
    strcpy(r.next,r.from);strcpy(r.from,"ms0:/PSP/GAME/DCRC_OWN/../EBOOT.PBP");
    assert(!sa1_chain_request_valid(&r));
    r.magic=0;assert(!sa1_chain_request_valid(&r));
    return 0;
}
