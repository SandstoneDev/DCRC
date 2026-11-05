/* Owned, synchronous GE menu pass at a closed game-list boundary. MIT. */
#pragma once
#include <stdint.h>
typedef struct { int x,y; uint32_t color; const char *text; } DebugDrawLine;
int draw_debug_ready(void);
void draw_debug_screen(const DebugDrawLine *lines,unsigned count,int highlight_y);
void draw_debug_reset_meter(void);
int draw_gu_fps_enabled(void);
int draw_gu_mip_limit(void);
