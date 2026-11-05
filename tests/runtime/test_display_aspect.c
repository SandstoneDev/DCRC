/* Synthetic display geometry; no game assets. Copyright (c) 2026 SandstoneDev. MIT. */
#include "../../backend/display_aspect.h"
#include <math.h>
#include <stdio.h>

static unsigned checks, fails;
#define CHECK(x) do { checks++; if (!(x)) { fails++; fprintf(stderr,"line %d\n",__LINE__); } } while (0)
static float screen_x(int projection, float x) {
    if (projection == DISPLAY_ASPECT_FULL) return x * 480.0f / 640.0f;
    if (projection == DISPLAY_ASPECT_CANVAS) return 60.0f + x * 360.0f / 640.0f;
    return (x - DRAW_WIDE_LEFT) * 480.0f / (DRAW_WIDE_RIGHT - DRAW_WIDE_LEFT);
}
int main(void) {
    unsigned frontend[] = {0,1,11,22,24,25};
    for (unsigned m=0;m<65536;m++) {
        int expected=0;
        for (unsigned i=0;i<sizeof frontend/sizeof *frontend;i++) expected |= m==frontend[i];
        CHECK(display_aspect_frontend(m)==expected);
        for (int marked=0;marked<2;marked++) {
            int layer=display_aspect_layer(m,marked);
            CHECK(layer==(expected ? DRAW_LAYER_3D_43 : marked ? DRAW_LAYER_2D : DRAW_LAYER_3D));
            for (int tile=0;tile<5;tile++) {
                float x0=tile*128.0f, x1=x0+128.0f;
                int p=display_aspect_select(1,layer,x0,x1);
                CHECK(p==(expected ? DISPLAY_ASPECT_FULL : marked ? DISPLAY_ASPECT_CANVAS : DISPLAY_ASPECT_WORLD));
                CHECK(display_aspect_select(0,layer,x0,x1)!=DISPLAY_ASPECT_FULL);
                if (expected) {
                    CHECK(fabsf(screen_x(p,x0)-tile*96.0f)<0.001f);
                    CHECK(fabsf(screen_x(p,x1)-(tile+1)*96.0f)<0.001f);
                }
            }
        }
    }
    CHECK(display_aspect_select(1,DRAW_LAYER_2D,0,640)==DISPLAY_ASPECT_FULL);
    CHECK(display_aspect_select(0,DRAW_LAYER_2D,0,640)==DISPLAY_ASPECT_CANVAS);
    CHECK(display_aspect_select(1,DRAW_LAYER_2D,0.5f,639.5f)==DISPLAY_ASPECT_FULL);
    CHECK(display_aspect_select(1,DRAW_LAYER_2D,0.51f,640)==DISPLAY_ASPECT_CANVAS);
    CHECK(display_aspect_select(1,DRAW_LAYER_2D,0,639.49f)==DISPLAY_ASPECT_CANVAS);
    CHECK(display_aspect_select(1,DRAW_LAYER_3D,-100,740)==DISPLAY_ASPECT_WORLD);
    CHECK(display_aspect_select(0,DRAW_LAYER_3D,-100,740)==DISPLAY_ASPECT_WORLD);
    /* A full fade in 4:3 is scaled into the canvas, not stretched then cropped. */
    int p=display_aspect_select(0,DRAW_LAYER_2D,0,640);
    CHECK(screen_x(p,0)==60 && screen_x(p,640)==420);
    /* Gameplay HUD stays 4:3-sized in wide mode; widening does not stretch glyphs. */
    p=display_aspect_select(1,DRAW_LAYER_2D,20,52);
    CHECK(fabsf(screen_x(p,52)-screen_x(p,20)-18.0f)<0.001f);
    CHECK(fabsf(screen_x(DISPLAY_ASPECT_WORLD,DRAW_WIDE_LEFT))<0.001f);
    CHECK(fabsf(screen_x(DISPLAY_ASPECT_WORLD,DRAW_WIDE_RIGHT)-480)<0.001f);
    printf("display_aspect: %u checks, %u failures\n",checks,fails);
    return fails ? 1 : 0;
}
