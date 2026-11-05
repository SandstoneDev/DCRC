/* Display policy for the supported US1.005 profile. Own geometry, no game code.
 * Copyright (c) 2026 SandstoneDev. MIT. */
#ifndef DCRC_DISPLAY_ASPECT_H
#define DCRC_DISPLAY_ASPECT_H
#include "draw.h"

enum { DISPLAY_ASPECT_WORLD, DISPLAY_ASPECT_CANVAS, DISPLAY_ASPECT_FULL };

/* Confirmed boot/title/advertise modes only. Unknown and gameplay modes keep
 * the original layer policy; results/transitions are not guessed as menus. */
static inline int display_aspect_frontend(unsigned mode) {
    switch (mode) {
    case 0: case 1: case 11: case 22: case 24: case 25: return 1;
    default: return 0;
    }
}
static inline int display_aspect_layer(unsigned mode, int marked_2d) {
    return display_aspect_frontend(mode) ? DRAW_LAYER_3D_43 :
           marked_2d ? DRAW_LAYER_2D : DRAW_LAYER_3D;
}
static inline int display_aspect_select(int wide, int layer, float xmin, float xmax) {
    if (layer == DRAW_LAYER_3D_43)
        return wide ? DISPLAY_ASPECT_FULL : DISPLAY_ASPECT_CANVAS;
    if (layer == DRAW_LAYER_2D)
        return wide && xmin <= 0.5f && xmax >= 639.5f ?
               DISPLAY_ASPECT_FULL : DISPLAY_ASPECT_CANVAS;
    return DISPLAY_ASPECT_WORLD;
}
#endif
