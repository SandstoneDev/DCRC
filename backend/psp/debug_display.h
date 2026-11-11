/* Owned, synchronous GE menu pass at a closed game-list boundary. MIT. */
#pragma once
#include <stdint.h>
typedef struct { int x,y; uint32_t color; const char *text; } DebugDrawLine;
typedef struct { int x,y,width,height; uint32_t color; } DebugDrawRect;
int draw_debug_ready(void);
void draw_debug_screen(const DebugDrawLine *lines, unsigned count,
                       const DebugDrawRect *rects, unsigned rect_count);
void draw_debug_reset_meter(void);
int draw_gu_fps_enabled(void);
int draw_gu_mip_limit(void);
