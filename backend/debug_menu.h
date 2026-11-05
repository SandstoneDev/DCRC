/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 SandstoneDev
 * Portable menu state. No rendering, game writes, filesystem or platform calls.
 */
#ifndef DCRC_DEBUG_MENU_H
#define DCRC_DEBUG_MENU_H
#include <stdint.h>

enum DebugMenuInput {
    DM_UP=1u<<0, DM_DOWN=1u<<1, DM_LEFT=1u<<2, DM_RIGHT=1u<<3,
    DM_ACCEPT=1u<<4, DM_BACK=1u<<5, DM_TOGGLE=1u<<6,
    DM_TAB_PREV=1u<<7, DM_TAB_NEXT=1u<<8, DM_SAVE=1u<<9,
    DM_REVERT=1u<<10, DM_DEFAULTS=1u<<11, DM_HELP=1u<<12
};
enum DebugMenuPage { DM_GRAPHICS, DM_AUDIO, DM_GAMEPLAY, DM_CHEATS, DM_DLC, DM_PAGE_COUNT };
enum DebugMenuSetting {
    DM_ASPECT, DM_FPS, DM_FRAME_SKIP, DM_MIPS, DM_SOUND, DM_VOICE,
    DM_STAGE, DM_ACT, DM_CHARACTER, DM_RINGS_LOCK, DM_LIVES_LOCK,
    DM_DLC_CHOICE, DM_SETTING_COUNT, DM_NO_SETTING=-1
};
enum DebugMenuRow { DM_ROW_WARP=DM_SETTING_COUNT, DM_ROW_ADD_RINGS, DM_ROW_ADD_LIVES };
enum DebugMenuAction {
    DM_NONE, DM_OPEN, DM_CLOSE, DM_CHANGED, DM_WARP, DM_ADD_RINGS,
    DM_ADD_LIVES, DM_SAVE_REQUEST, DM_REVERTED, DM_HELP_CHANGED
};
typedef struct {
    int aspect;     /* 0 = 4:3, 1 = wide */
    int fps;
    int frame_skip; /* choice index: 0 = auto, 1 = off, 2..60 = every N */
    int mips;       /* 1..8 */
    int audio;
    int voice;      /* -1 = game, 0 = Japanese, 1 = English */
    int stage;      /* adapter's catalog index, never a guest level ID */
    int act;        /* human 1..8; adapter validates stage/character combination */
    int character;  /* adapter's catalog index 0..5 */
    int rings_lock, lives_lock; /* default OFF; not permission to write guest RAM */
    int dlc;        /* -1 = off, otherwise adapter's catalog index */
} DebugMenuValues;
typedef struct { enum DebugMenuAction action; int changed; } DebugMenuEvent;
typedef struct {
    int open, page, cursor, help;
    DebugMenuValues values, opened, saved, defaults;
    int stage_count, dlc_count;
    uint32_t previous, blocked, repeat_key, repeat_ms;
    int repeating;
} DebugMenu;

/* All calls belong to one owner thread. NULL snapshots use safe defaults.
 * Cheat flags always start off. The defaults snapshot is explicit, not inferred
 * from a different game's settings. Nonpositive catalog counts mean empty.
 */
void debug_menu_init(DebugMenu *, const DebugMenuValues *current,
                     const DebugMenuValues *defaults, int stage_count, int dlc_count);
/* held is a semantic level mask. Toggle/save/actions fire only on rising edges.
 * Directions repeat after 350 ms, then every 100 ms, at most one step per call.
 * Opening and closing quarantine all supplied held bits until each is released.
 * The platform adapter must ALSO quarantine physical raw buttons: semantic bits
 * cannot represent every button in a physical opening chord or its partials.
 * CLOSE keeps session values; REVERT restores the latest opening snapshot.
 * SAVE_REQUEST performs no IO and does not mark anything saved.
 */
DebugMenuEvent debug_menu_step(DebugMenu *, uint32_t held, uint32_t elapsed_ms);
void debug_menu_mark_saved(DebugMenu *); /* call only after successful persistence */
int debug_menu_dirty(const DebugMenu *);
int debug_menu_row_count(int page);
int debug_menu_row_id(int page, int index); /* -1 on invalid input */
const char *debug_menu_page_label(int page);
const char *debug_menu_row_label(int row);
int debug_menu_setting_value(const DebugMenuValues *, int setting);
#endif
