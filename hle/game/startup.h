/* Fresh-boot stage selection for Sonic Adventure US1.005. MIT. */
#pragma once
#include <stdint.h>
/* 0 unknown key, 1 accepted, -1 invalid. CLI values override INI. */
int hle_startup_setting(const char *key, const char *value, int cli);
/* Called after settings load; restored states never receive a boot warp. */
void hle_startup_prepare(int resuming);
/* Once at the established fresh-boot frame12/mode1 boundary. */
void hle_startup_frame(uint32_t frame);
/* Validated effective launch request, not the live player state. */
int hle_startup_get(uint16_t *level,uint16_t *act,uint16_t *character,int *enabled);
int hle_startup_cli_active(void);
