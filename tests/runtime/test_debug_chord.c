#include "../../backend/debug_chord.h"
#include <assert.h>
int main(void){
    DebugMenu m;DebugChord c={0};debug_menu_init(&m,0,0,4,2);
    const unsigned chord=15;
    assert(debug_menu_raw_step(&m,&c,chord,chord,DM_ACCEPT|DM_DOWN,0).action==DM_OPEN);
    assert(m.open&&c.blocked);
    debug_menu_raw_step(&m,&c,0,chord,0,16);
    assert(debug_menu_raw_step(&m,&c,chord,chord,DM_ACCEPT|DM_DOWN,16).action==DM_CLOSE);
    debug_menu_raw_step(&m,&c,0,chord,0,16);
    assert(debug_menu_raw_step(&m,&c,chord,chord,0,16).action==DM_OPEN);
    assert(m.open);
    /* A new Start press cannot activate save until the entire chord releases. */
    assert(debug_menu_raw_step(&m,&c,chord|16,chord,DM_SAVE,16).action==DM_NONE);
    debug_menu_raw_step(&m,&c,0,chord,0,16);
    assert(debug_menu_raw_step(&m,&c,16,chord,DM_SAVE,16).action==DM_SAVE_REQUEST);
    return 0;
}
