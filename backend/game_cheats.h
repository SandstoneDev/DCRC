/* Scalar gameplay binding facts and conservative admission; no game body. MIT. */
#pragma once
#include <stdint.h>
#include <math.h>
typedef struct {
    int strict,mode,level,character,stable,act,substate;
    uint32_t task,work,linked_work;
    float x,y,z;
    int rings,lives;
} DebugCheatContext;
static inline int debug_guest_span(uint32_t p,uint32_t n) {
    uint32_t area=p&0xe0000000u,offset=p&0x1fffffffu;
    return (area==0 || area==0x80000000u || area==0xa0000000u)
        && !(p&3u) && offset>=0x0c000000u && offset<0x0d000000u && n<=0x0d000000u-offset;
}
static inline int debug_cheat_allowed(const DebugCheatContext *s) {
    return s && !s->strict && s->mode==4 && s->substate==15
        && s->level==1 && s->act==0 && s->character==0 && s->stable>=3
        && debug_guest_span(s->task,36) && debug_guest_span(s->work,44)
        && (s->work&0x1fffffffu)==(s->linked_work&0x1fffffffu)
        && debug_guest_span(s->linked_work,44)
        && isfinite(s->x)&&isfinite(s->y)&&isfinite(s->z)
        && s->rings>=0&&s->rings<=9999&&s->lives>=0&&s->lives<=127;
}
