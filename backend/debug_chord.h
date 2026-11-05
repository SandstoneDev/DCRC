/* Own physical-chord admission, shared by closed polling and modal input. MIT. */
#pragma once
#include "debug_menu.h"
typedef struct {uint32_t previous,blocked;} DebugChord;
static inline DebugMenuEvent debug_menu_raw_step(DebugMenu *m,DebugChord *c,
    uint32_t raw,uint32_t chord,uint32_t semantic,uint32_t elapsed_ms){
    c->blocked&=raw;
    int full=(raw&chord)==chord,was=(c->previous&chord)==chord;
    uint32_t bits=c->blocked?0:(m->open?semantic:0);
    if(full&&!was&&!c->blocked)bits=DM_TOGGLE;
    /* Neutral updates while closed are essential: release must also clear
     * the semantic controller's previous/blocked toggle after chord-close. */
    DebugMenuEvent e=debug_menu_step(m,bits,elapsed_ms);
    if(e.action==DM_OPEN||e.action==DM_CLOSE)c->blocked|=raw;
    c->previous=raw;
    return e;
}
