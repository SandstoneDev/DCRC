/* Own text configuration update; unknown player keys remain intact. MIT. */
#pragma once
#include <stddef.h>
typedef struct { const char *key; const char *value; } DebugIniPair;
/* NUL-terminated input/output. Returns output bytes excluding NUL, or -1. */
int debug_ini_update(const char *old,size_t old_size,const DebugIniPair *pairs,
                     size_t count,char *out,size_t cap);
