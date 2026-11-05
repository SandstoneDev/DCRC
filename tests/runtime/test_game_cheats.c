#include "../../backend/game_cheats.h"
#include <assert.h>
int main(void) {
    DebugCheatContext s={0,4,1,0,3,0,15,0x8c100000,0x8c100100,0x8c100100,1,2,3,0,3};
    assert(debug_cheat_allowed(&s));s.strict=1;assert(!debug_cheat_allowed(&s));s.strict=0;
    s.stable=2;assert(!debug_cheat_allowed(&s));s.stable=3;
    s.work=0x8d000000;assert(!debug_cheat_allowed(&s));s.work=s.linked_work;
    s.linked_work+=4;assert(!debug_cheat_allowed(&s));s.linked_work=s.work;
    s.x=NAN;assert(!debug_cheat_allowed(&s));s.x=1;
    s.mode=11;assert(!debug_cheat_allowed(&s));s.mode=4;
    s.character=7;assert(!debug_cheat_allowed(&s));s.character=0;
    s.substate=4;assert(!debug_cheat_allowed(&s));s.substate=15;
    assert(debug_cheat_allowed(&s));assert(!debug_guest_span(0x8cffffff,4));
    assert(!debug_guest_span(0xec100000,36));assert(debug_guest_span(0xac100000,36));
    return 0;
}
