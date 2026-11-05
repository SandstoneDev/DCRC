/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 SandstoneDev
 * Own platform-neutral controller; actions are requests to an owner adapter.
 */
#include "debug_menu.h"
#include <string.h>

static int *field(DebugMenuValues *v, int setting)
{
    switch (setting) {
    case DM_ASPECT: return &v->aspect;
    case DM_FPS: return &v->fps;
    case DM_FRAME_SKIP: return &v->frame_skip;
    case DM_MIPS: return &v->mips;
    case DM_SOUND: return &v->audio;
    case DM_VOICE: return &v->voice;
    case DM_STAGE: return &v->stage;
    case DM_ACT: return &v->act;
    case DM_CHARACTER: return &v->character;
    case DM_RINGS_LOCK: return &v->rings_lock;
    case DM_LIVES_LOCK: return &v->lives_lock;
    case DM_DLC_CHOICE: return &v->dlc;
    default: return NULL;
    }
}
int debug_menu_setting_value(const DebugMenuValues *v, int setting)
{
    DebugMenuValues copy = *v;
    int *p = field(&copy, setting);
    return p ? *p : 0;
}
static void range(const DebugMenu *m, int setting, int *lo, int *hi)
{
    *lo = 0; *hi = 1;
    switch (setting) {
    case DM_FRAME_SKIP: *hi = 60; break;
    case DM_MIPS: case DM_ACT: *lo = 1; *hi = 8; break;
    case DM_VOICE: *lo = -1; break;
    case DM_STAGE: *hi = m->stage_count ? m->stage_count - 1 : 0; break;
    case DM_CHARACTER: *hi = 5; break;
    case DM_DLC_CHOICE: *lo = -1; *hi = m->dlc_count - 1; break;
    default: break;
    }
}
static void normalize(const DebugMenu *m, DebugMenuValues *v)
{
    int s, lo, hi;
    for (s = 0; s < DM_SETTING_COUNT; s++) {
        int *p = field(v, s);
        range(m, s, &lo, &hi);
        if (*p < lo) *p = lo;
        if (*p > hi) *p = hi;
    }
    v->rings_lock = v->lives_lock = 0;
}
void debug_menu_init(DebugMenu *m, const DebugMenuValues *current,
                     const DebugMenuValues *defaults, int stage_count, int dlc_count)
{
    static const DebugMenuValues base = {1,1,0,8,1,-1,0,1,0,0,0,-1};
    memset(m, 0, sizeof *m);
    m->stage_count = stage_count > 0 ? stage_count : 0;
    m->dlc_count = dlc_count > 0 ? dlc_count : 0;
    m->values = current ? *current : base;
    m->defaults = defaults ? *defaults : base;
    normalize(m, &m->values);
    normalize(m, &m->defaults);
    m->opened = m->saved = m->values;
}
static const int rows[DM_PAGE_COUNT][4] = {
    {DM_ASPECT,DM_FPS,DM_FRAME_SKIP,DM_MIPS},
    {DM_SOUND,DM_VOICE,-1,-1},
    {DM_STAGE,DM_ACT,DM_CHARACTER,DM_ROW_WARP},
    {DM_RINGS_LOCK,DM_LIVES_LOCK,DM_ROW_ADD_RINGS,DM_ROW_ADD_LIVES},
    {DM_DLC_CHOICE,-1,-1,-1}
};
int debug_menu_row_count(int page)
{
    static const int counts[DM_PAGE_COUNT] = {4,2,4,4,1};
    return page >= 0 && page < DM_PAGE_COUNT ? counts[page] : 0;
}
int debug_menu_row_id(int page, int index)
{
    return index >= 0 && index < debug_menu_row_count(page) ? rows[page][index] : -1;
}
const char *debug_menu_page_label(int page)
{
    static const char *const names[] = {"Graphics","Audio","Gameplay","Cheats","DLC"};
    return page >= 0 && page < DM_PAGE_COUNT ? names[page] : "";
}
const char *debug_menu_row_label(int row)
{
    static const char *const labels[] = {
        "Aspect ratio","FPS display","Frame skip","Mip levels","Sound","Voice language",
        "Stage","Act","Character","Keep rings","Keep lives","DLC event",
        "Warp / restart stage","Add rings","Add lives"
    };
    return row >= 0 && row <= DM_ROW_ADD_LIVES ? labels[row] : "";
}
void debug_menu_mark_saved(DebugMenu *m) { m->saved = m->values; }
int debug_menu_dirty(const DebugMenu *m)
{
    int s;
    for (s = 0; s < DM_SETTING_COUNT; s++)
        if (debug_menu_setting_value(&m->values,s) != debug_menu_setting_value(&m->saved,s)) return 1;
    return 0;
}
static uint32_t direction(uint32_t held)
{
    if ((held & (DM_UP|DM_DOWN)) == DM_UP) return DM_UP;
    if ((held & (DM_UP|DM_DOWN)) == DM_DOWN) return DM_DOWN;
    if ((held & (DM_LEFT|DM_RIGHT)) == DM_LEFT) return DM_LEFT;
    if ((held & (DM_LEFT|DM_RIGHT)) == DM_RIGHT) return DM_RIGHT;
    if ((held & (DM_TAB_PREV|DM_TAB_NEXT)) == DM_TAB_PREV) return DM_TAB_PREV;
    if ((held & (DM_TAB_PREV|DM_TAB_NEXT)) == DM_TAB_NEXT) return DM_TAB_NEXT;
    return 0;
}
static uint32_t repeat(DebugMenu *m, uint32_t held, uint32_t dt)
{
    uint32_t key = direction(held), limit = m->repeating ? 100u : 350u;
    if (!key || key != m->repeat_key) {
        m->repeat_key = key; m->repeat_ms = 0; m->repeating = 0;
        return key;
    }
    /* Compare before adding: even an unbounded caller interval cannot overflow.
     * Drop excess time deliberately; a stall must not emit a burst of actions. */
    if (dt >= limit - m->repeat_ms) {
        m->repeat_ms = 0; m->repeating = 1;
        return key;
    }
    m->repeat_ms += dt;
    return 0;
}
static DebugMenuEvent changed(DebugMenu *m, int setting, int value)
{
    DebugMenuEvent e = {DM_NONE,DM_NO_SETTING};
    int *p = field(&m->values, setting);
    if (p && *p != value) { *p = value; e.action = DM_CHANGED; e.changed = setting; }
    return e;
}
DebugMenuEvent debug_menu_step(DebugMenu *m, uint32_t held, uint32_t elapsed_ms)
{
    DebugMenuEvent e = {DM_NONE,DM_NO_SETTING};
    uint32_t active, edge, key;
    int row, lo, hi, value;
    held &= (1u << 13) - 1u;
    m->blocked &= held;
    active = held & ~m->blocked;
    edge = active & ~m->previous;
    m->previous = held;
    if (edge & DM_TOGGLE) {
        m->open = !m->open; m->help = 0;
        m->blocked = held; m->repeat_key = m->repeat_ms = 0; m->repeating = 0;
        if (m->open) { m->opened = m->values; m->page = DM_GRAPHICS; m->cursor = 0; }
        e.action = m->open ? DM_OPEN : DM_CLOSE;
        return e;
    }
    if (!m->open) return e;
    if (m->help) {
        if (edge & (DM_BACK|DM_HELP|DM_ACCEPT)) {
            m->help = 0; m->blocked = held; e.action = DM_HELP_CHANGED;
        }
        return e;
    }
    if (edge & DM_BACK) {
        m->open = 0; m->blocked = held; m->repeat_key = 0;
        e.action = DM_CLOSE; return e;
    }
    if (edge & DM_SAVE) { e.action = DM_SAVE_REQUEST; return e; }
    if (edge & DM_REVERT) { m->values = m->opened; e.action = DM_REVERTED; return e; }
    if (edge & DM_HELP) { m->help = 1; e.action = DM_HELP_CHANGED; return e; }
    /* Guard cursor/page as these fields are public for a renderer. */
    if (m->page < 0 || m->page >= DM_PAGE_COUNT) m->page = DM_GRAPHICS;
    if (m->cursor < 0 || m->cursor >= debug_menu_row_count(m->page)) m->cursor = 0;
    row = debug_menu_row_id(m->page,m->cursor);
    if ((edge & DM_DEFAULTS) && row < DM_SETTING_COUNT)
        return changed(m,row,debug_menu_setting_value(&m->defaults,row));
    key = repeat(m,active,elapsed_ms);
    if (key == DM_TAB_PREV || key == DM_TAB_NEXT) {
        m->page = (m->page + (key == DM_TAB_NEXT ? 1 : DM_PAGE_COUNT-1)) % DM_PAGE_COUNT;
        m->cursor = 0; return e;
    }
    if (key == DM_UP || key == DM_DOWN) {
        int n = debug_menu_row_count(m->page);
        m->cursor = (m->cursor + (key == DM_DOWN ? 1 : n-1)) % n; return e;
    }
    if (row >= DM_SETTING_COUNT) {
        if (edge & DM_ACCEPT) {
            if (row == DM_ROW_WARP && m->stage_count) e.action = DM_WARP;
            if (row == DM_ROW_ADD_RINGS) e.action = DM_ADD_RINGS;
            if (row == DM_ROW_ADD_LIVES) e.action = DM_ADD_LIVES;
        }
        return e;
    }
    if (key != DM_LEFT && key != DM_RIGHT && !(edge & DM_ACCEPT)) return e;
    range(m,row,&lo,&hi);
    value = debug_menu_setting_value(&m->values,row);
    if (key == DM_LEFT) { if (value > lo) value--; }
    else if (value < hi) value++;
    else if (edge & DM_ACCEPT) value = lo;
    return changed(m,row,value);
}
