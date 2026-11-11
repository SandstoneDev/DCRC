/* Own PSP default save-location policy, MIT. */
#ifndef SA1_VMU_DEFAULT_PATH_H
#define SA1_VMU_DEFAULT_PATH_H
#include <stddef.h>

/* Run at startup, before mounting or guest access. 0 local on other devices,
 * 1 existing shared store, 2 new empty shared store, 3 shared store copied
 * from this installation's legacy files. A negative result leaves the
 * legacy store intact. Explicit --vmu-dir bypasses the policy. */
int vmu_default_path(char *out, size_t cap, const char *base, int *raw);
#endif
