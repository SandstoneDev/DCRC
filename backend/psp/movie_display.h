/* Renderer-owned movie boundary. MIT. */
#pragma once
#include <stdint.h>
int draw_movie_begin(void);
int draw_movie_present(const uint16_t *picture,unsigned stride);
int draw_movie_end(void); /* negative keeps ownership: GPU drain not proved */
