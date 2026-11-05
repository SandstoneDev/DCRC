/* Own sampler policy from texture/layout facts; no game bytes. MIT.
 * Six opaque boot tiles use the full texture rectangle. Repeat filtering
 * can blend an unrelated opposite edge into their shared border. */
#ifndef SA1_SEGA_TILE_SAMPLER_H
#define SA1_SEGA_TILE_SAMPLER_H
#include "draw.h"

/* Caller resolves a currently live backend image and its current HLE name.
 * No handle-only cache: releasing/reusing a slot must requalify its name.
 * Return1 changes effective sampler wrap only; raw state/UV/XY stay intact. */
static inline int sega_tile_sampler_clamp(const draw_state *s,int strict,
        uint32_t mode,uint32_t resolved,int w,int h,int fmt,const char *name) {
    if(!s || strict || mode!=1 || s->layer!=DRAW_LAYER_3D_43 ||
       !s->texture || resolved!=s->texture || w!=256 || h!=256 || fmt!=DRAW_FMT_5650 ||
       s->filter<DRAW_FILTER_BILINEAR || s->filter>DRAW_FILTER_TRILINEAR_B ||
       s->flip_u || s->flip_v || (s->clamp_u && s->clamp_v) || !name) return 0;
    static const char prefix[]="segalogo";
    for(unsigned i=0;i<8;i++)if(name[i]!=prefix[i])return 0;
    return name[8]>='0' && name[8]<='5' && name[9]=='\0';
}
#endif
