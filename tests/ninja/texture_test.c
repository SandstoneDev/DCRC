/* Texture sharing under backend allocation pressure. Synthetic input only.
 * The real texture loader/decoder run against a backend that can refuse a
 * new allocation. No game assets or generated game code are needed.
 *
 * cc -std=c11 -Wall -Wextra -Wno-unused-parameter -ffunction-sections
 *   -fdata-sections -Ibackend -Irecomp/emitter/runtime
 *   tests/ninja/texture_test.c hle/ninja/pvr_decode.c
 *   -Wl,--gc-sections -o work/texture_test && work/texture_test
 *
 * Part of sa1-psp (MIT). */
#ifndef TEXTURE_TEST_SOURCE
#define TEXTURE_TEST_SOURCE "../../hle/ninja/texture.c"
#endif
#include TEXTURE_TEST_SOURCE

static uint8_t ram[SA1_RAM_SIZE + SA1_RAM_EXTRA];
uint8_t *const sa1_ram = ram;
static unsigned creates, destroys, next_handle = 1;
static int refuse, failures;
static uint8_t alive[32];
#define CHECK(x, why) do { if (!(x)) { printf("FAIL: %s\n", why); failures++; } } while (0)

void sa1_log(const char *fmt, ...) { (void)fmt; }
uint64_t sa1_plat_time_us(void) { return 0; }
uint32_t draw_texture_create(int w, int h, int fmt, const void *pixels, int cf, const void *clut) {
    creates++;
    if (refuse) return 0;
    CHECK(w == 8 && h == 8 && fmt == DRAW_FMT_5650, "backend receives decoded format/dimensions");
    CHECK(((const uint16_t *)pixels)[0] == 31, "backend receives red PSP-order texel");
    CHECK(next_handle < sizeof alive, "test handle capacity");
    alive[next_handle] = 1;
    return next_handle++;
}
void draw_texture_destroy(uint32_t h) {
    CHECK(h < sizeof alive && alive[h], "destroy only a live backend handle");
    alive[h] = 0; destroys++;
}

static void put32(uint8_t *p, uint32_t v) {
    for (int i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i));
}
static void image(uint8_t *p, uint32_t gbix) {
    memset(p, 0, 28 + 128);
    put32(p, MAGIC_GINDEX); put32(p + 4, 4); put32(p + 8, gbix);
    put32(p + 12, MAGIC_TEXTURE); put32(p + 16, 8 + 128);
    p[20] = 1; p[21] = 9; p[24] = 8; p[26] = 8;
    for (int i = 0; i < 64; i++) { p[28 + 2 * i] = 0; p[29 + 2 * i] = 0xf8; }
}
static uint32_t references(int i) { return hle_rd32(entry_addr((uint32_t)i) + 64); }

int main(int argc, char **argv) {
    int pressure = !(argc == 2 && strcmp(argv[1], "--control") == 0);
    uint8_t p[28 + 128];
    memlist_base = 0x8c001000; memlist_count = 8;
    image(p, 123);
    int a = load_entry(p, sizeof p, PVR_NO_GINDEX, "synthetic first");
    CHECK(a >= 0 && texture_count() == 1, "first load creates one texture");
    uint32_t h = slots[a].handle;
    CHECK(references(a) == 1 && creates == 1, "first reference and backend allocation");

    /* The exact live texture already exists. A new texlist reference must
     * not depend on room for a temporary duplicate backend texture. */
    refuse = pressure;
    int b = load_entry(p, sizeof p, PVR_NO_GINDEX, "synthetic duplicate");
    CHECK(b == a, "duplicate load succeeds with no new backend room");
    if (pressure) CHECK(creates == 1 && destroys == 0, "shared load avoids temporary backend allocation/destruction");
    CHECK(references(a) == 2 && slots[a].handle == h && alive[h], "shared reference retains original live handle");
    CHECK(texture_from_tcw(h) == h && total_bytes == 128 && ntex == 1, "binding and accounting remain live");

    unsigned calls = creates;
    CHECK(load_entry(p, 12, 123, "truncated header") < 0, "same GBIX does not bypass header validation");
    p[21] = 0xff;
    CHECK(load_entry(p, sizeof p, 123, "unsupported decode") < 0, "same GBIX does not bypass decoder validation");
    p[21] = 9;
    CHECK(load_entry(p, 20, 123, "truncated texture header") < 0, "same GBIX does not bypass texture header bounds");
    p[24] = 7;
    CHECK(load_entry(p, sizeof p, 123, "unsupported dimensions") < 0, "same GBIX does not bypass dimension validation");
    p[24] = 8;
    CHECK(references(a) == 2 && creates == calls, "invalid input preserves live entry and refcount");

    image(p, 456); refuse = 1;
    CHECK(load_entry(p, sizeof p, PVR_NO_GINDEX, "new GBIX refused") < 0, "unshared allocation failure remains an error");
    CHECK(texture_count() == 1 && references(a) == 2, "failed new load preserves shared entry");
    refuse = 0;
    release_entry(entry_addr((uint32_t)a));
    CHECK(references(a) == 1 && alive[h], "first release keeps shared texture");
    release_entry(entry_addr((uint32_t)a));
    CHECK(texture_count() == 0 && !alive[h] && texture_from_tcw(h) == 0, "last release clears backend and binding");
    image(p, 123);
    int c = load_entry(p, sizeof p, PVR_NO_GINDEX, "reload after release");
    CHECK(c >= 0 && slots[c].handle != h && references(c) == 1, "released GBIX gets a fresh handle");

    /* Header-less GBIX fallback and the raw texinfo path use the same key
     * policy. No-index images remain distinct allocations. */
    refuse = pressure;
    CHECK(load_entry(p + 12, sizeof p - 12, 123, "hinted duplicate") == c, "archive GBIX hint shares after decode");
    CHECK(load_entry_ex(p + 28, 128, 123, "raw duplicate", 8, 8, 0x901) == c, "raw texinfo hint shares after decode");
    CHECK(references(c) == 3, "all supported load forms acquire a reference");
    refuse = 0;
    int d = load_entry(p + 12, sizeof p - 12, PVR_NO_GINDEX, "no index first");
    int e = load_entry(p + 12, sizeof p - 12, PVR_NO_GINDEX, "no index second");
    CHECK(d >= 0 && e >= 0 && d != e && slots[d].handle != slots[e].handle, "no-index images never share");
    texture_init();
    CHECK(texture_count() == 0 && total_bytes == 0, "reset destroys all surviving entries");
    if (failures) { printf("texture_test: %d failures\n", failures); return 1; }
    puts("texture_test: ok");
    return 0;
}
