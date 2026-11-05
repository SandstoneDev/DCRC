/* Own menu adapter. Only the owning game thread calls these. MIT. */
#pragma once
#include <stdint.h>
void debug_psp_init(const char *base,const char *data,const volatile int *home,void (*restart)(void));
void debug_psp_poll(void);
void debug_psp_boundary(void);
int debug_psp_capture(void);
uint32_t debug_psp_heartbeat(void);
uint64_t debug_psp_paused_us(void);
void debug_psp_cheats(void);
