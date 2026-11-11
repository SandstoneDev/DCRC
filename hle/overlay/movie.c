/* Own host dispatch at the supported profile entry. Entry address is a
 * version fact; guest launcher/callback restoration remains generated. MIT. */
#include "../hle.h"
#include "movie.h"
int hle_movies_enabled=1;
int32_t sa1_platform_movie_play(uint32_t id) __attribute__((weak));

#define MOVIE_ENTRY 0x8CEB0000u

static void movie_entry(sh4_ctx *c) {
    HLE_ENTER(MOVIE_ENTRY, "MOVIE.BIN entry");
    if(!hle_strict&&hle_movies_enabled&&sa1_platform_movie_play){c->r[0]=(uint32_t)sa1_platform_movie_play(c->r[4]);return;}
    sa1_log("movie: id %u skipped (no FMV playback)", c->r[4]);
    c->r[0] = (uint32_t)-1;
}

void hle_movie_init(void) {
    sa1_register_fn(MOVIE_ENTRY, movie_entry);
}
