/* Pure observed-visible-picture meter; every value is an observed lower
 * bound, not optical proof or an estimate from guest frame progress. MIT. */
#pragma once
#include "display_counter.h"

typedef struct fps_meter {
    uint64_t start_us, last_us;
    uint32_t start_visible, last_visible, last_guest, scene, fps_tenths, frame_us;
    unsigned started, valid, uncertain;
} fps_meter;

static inline void fps_meter_reset(fps_meter *m) { *m=(fps_meter){0}; }
static inline void fps_meter_warm(fps_meter *m,const display_counter *c,
                                 uint64_t now_us,uint32_t guest,uint32_t scene) {
    m->start_us=m->last_us=now_us;
    m->start_visible=m->last_visible=c->visible;
    m->last_guest=guest; m->scene=scene;
    m->started=1; m->valid=0; m->fps_tenths=0; m->frame_us=0;
}
static inline void fps_meter_sample(fps_meter *m,const display_counter *c,
                                    uint64_t now_us,uint32_t guest,uint32_t scene) {
    m->uncertain |= c->query_errors || c->coverage_gaps || c->unresolved
        || c->complete_errors || c->schedule_errors || c->hidden || c->foreground_unknown;
    /* A half-range delta distinguishes an ordinary visible-counter wrap
     * from counter reset/backward movement. Guest progress only detects
     * discontinuity; it never contributes to the measured frame rate. */
    if (!m->started || now_us<m->last_us || guest<m->last_guest || scene!=m->scene
        || now_us-m->last_us>UINT64_C(5000000)
        || (uint32_t)(c->visible-m->last_visible)>UINT32_MAX/2u
        || (uint32_t)(c->visible-m->start_visible)>UINT32_MAX/2u) {
        fps_meter_warm(m,c,now_us,guest,scene);
        return;
    }
    m->last_us=now_us; m->last_visible=c->visible; m->last_guest=guest;
    uint64_t elapsed=now_us-m->start_us;
    if (elapsed<UINT64_C(1000000)) return;
    uint32_t pictures=c->visible-m->start_visible;
    uint64_t tenths=((uint64_t)pictures*UINT64_C(10000000)+elapsed/2u)/elapsed;
    m->fps_tenths=tenths>9999u?9999u:(uint32_t)tenths;
    /* Rounded mean observed-picture interval, independently of rounded FPS.
     * Quotient/remainder avoids overflowing elapsed + pictures/2. */
    uint64_t period=pictures ? elapsed/pictures + (elapsed%pictures >= (pictures+1u)/2u) : 0;
    m->frame_us=period>UINT32_MAX ? UINT32_MAX : (uint32_t)period;
    m->valid=1;
    m->start_us=now_us; m->start_visible=c->visible;
}
static inline void fps_meter_format(const fps_meter *m,char *out,unsigned cap) {
    if (!out || !cap) return;
    char text[10]="FPS --.-";
    if (m->valid) {
        uint32_t value=m->fps_tenths>9999u?9999u:m->fps_tenths;
        uint32_t whole=value/10u;
        unsigned pos=4;
        text[3]=m->uncertain?'~':' ';
        if (whole>=100u) text[pos++]=(char)('0'+whole/100u);
        if (whole>=10u) text[pos++]=(char)('0'+whole/10u%10u);
        text[pos++]=(char)('0'+whole%10u);
        text[pos++]='.';
        text[pos++]=(char)('0'+value%10u);
        text[pos]=0;
    }
    unsigned i=0;
    while (i+1<cap && text[i]) { out[i]=text[i]; i++; }
    out[i]=0;
}
static inline unsigned fps_meter_style_uint(char *text,unsigned pos,uint32_t n,unsigned width) {
    char digits[10]; unsigned count=0;
    do { digits[count++]=(char)('0'+n%10u); n/=10u; } while (n);
    for (unsigned i=count;i<width;i++) text[pos++]=' ';
    while (count) text[pos++]=digits[--count];
    return pos;
}
/* Reference HUD style; ms is the mean observed-picture interval, not CPU
 * time. The FPS~ marker keeps the observed lower-bound uncertainty visible. */
static inline void fps_meter_style_text(const fps_meter *m,char *out,unsigned cap) {
    if (!out || !cap) return;
    char text[32]="--.- FPS --- ms";
    if (m->valid) {
        uint32_t value=m->fps_tenths>9999u ? 9999u : m->fps_tenths;
        unsigned p=fps_meter_style_uint(text,0,value/10u,2);
        text[p++]='.'; text[p++]=(char)('0'+value%10u);
        text[p++]=' '; text[p++]='F'; text[p++]='P'; text[p++]='S';
        if (m->uncertain) text[p++]='~';
        text[p++]=' ';
        if (m->frame_us) {
            uint64_t ms=((uint64_t)m->frame_us+500u)/1000u;
            p=fps_meter_style_uint(text,p,ms>99999u?99999u:(uint32_t)ms,3);
        } else { text[p++]='-'; text[p++]='-'; text[p++]='-'; }
        text[p++]=' '; text[p++]='m'; text[p++]='s'; text[p]=0;
    }
    unsigned i=0;
    while (i+1<cap && text[i]) { out[i]=text[i]; i++; }
    out[i]=0;
}
