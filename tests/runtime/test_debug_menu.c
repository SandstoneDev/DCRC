/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 SandstoneDev
 * Host-only controller checks. Compile with backend/debug_menu.c.
 */
#include "../../backend/debug_menu.h"
#include <limits.h>
#include <stdio.h>
#include <string.h>
static int checks, failures;
#define CHECK(x) do { checks++; if (!(x)) { failures++; fprintf(stderr,"line %d: %s\n",__LINE__,#x); } } while(0)
static DebugMenuEvent press(DebugMenu *m, uint32_t key) {
    debug_menu_step(m,0,0); return debug_menu_step(m,key,0);
}
static void open_menu(DebugMenu *m) {
    CHECK(press(m,DM_TOGGLE).action==DM_OPEN); debug_menu_step(m,0,0);
}
static void focus(DebugMenu *m,int page,int row) { m->page=page; m->cursor=row; }
int main(void) {
    DebugMenu m;
    DebugMenuValues v={1,1,0,8,1,1,2,3,0,1,1,1};
    DebugMenuValues def={0,0,1,4,1,-1,0,1,0,1,1,-1};
    debug_menu_init(&m,&v,&def,4,3);
    CHECK(!m.open); CHECK(!m.help); CHECK(!debug_menu_dirty(&m));
    CHECK(m.values.aspect==1 && m.values.mips==8 && m.values.stage==2);
    CHECK(!m.values.rings_lock && !m.values.lives_lock);
    CHECK(!m.defaults.rings_lock && !m.defaults.lives_lock);
    CHECK(press(&m,DM_DOWN).action==DM_NONE && !m.open);
    /* Opening chord semantic components cannot activate or move the first row. */
    DebugMenuEvent e=press(&m,DM_TOGGLE|DM_ACCEPT|DM_DOWN);
    CHECK(e.action==DM_OPEN && m.open && m.cursor==0);
    CHECK(debug_menu_step(&m,DM_TOGGLE|DM_ACCEPT|DM_DOWN,UINT32_MAX).action==DM_NONE);
    CHECK(m.cursor==0 && m.values.aspect==1);
    debug_menu_step(&m,0,0);
    CHECK(press(&m,DM_LEFT).changed==DM_ASPECT && m.values.aspect==0);
    CHECK(debug_menu_dirty(&m));
    CHECK(debug_menu_step(&m,DM_LEFT,349).action==DM_NONE);
    CHECK(debug_menu_step(&m,DM_LEFT,1).action==DM_NONE); /* range clamp, no change */
    CHECK(press(&m,DM_RIGHT).changed==DM_ASPECT && m.values.aspect==1);
    CHECK(press(&m,DM_DOWN).action==DM_NONE && m.cursor==1);
    debug_menu_step(&m,DM_DOWN,349); CHECK(m.cursor==1);
    debug_menu_step(&m,DM_DOWN,1); CHECK(m.cursor==2);
    debug_menu_step(&m,DM_DOWN,99); CHECK(m.cursor==2);
    debug_menu_step(&m,DM_DOWN,1); CHECK(m.cursor==3);
    debug_menu_step(&m,DM_DOWN,UINT32_MAX); CHECK(m.cursor==0); /* bounded, no catch-up burst */
    int cursor=m.cursor;
    press(&m,DM_UP|DM_DOWN); CHECK(m.cursor==cursor);
    CHECK(press(&m,DM_TAB_PREV).action==DM_NONE && m.page==DM_DLC && m.cursor==0);
    press(&m,DM_TAB_NEXT); CHECK(m.page==DM_GRAPHICS);
    focus(&m,DM_GRAPHICS,2);
    for(int i=0;i<70;i++) press(&m,DM_RIGHT);
    CHECK(m.values.frame_skip==60);
    for(int i=0;i<70;i++) press(&m,DM_LEFT);
    CHECK(m.values.frame_skip==0);
    focus(&m,DM_GRAPHICS,3);
    for(int i=0;i<12;i++) press(&m,DM_LEFT);
    CHECK(m.values.mips==1);
    CHECK(press(&m,DM_DEFAULTS).changed==DM_MIPS && m.values.mips==4);
    CHECK(press(&m,DM_HELP).action==DM_HELP_CHANGED && m.help);
    press(&m,DM_RIGHT|DM_DOWN); CHECK(m.values.mips==4 && m.cursor==3);
    CHECK(press(&m,DM_BACK).action==DM_HELP_CHANGED && !m.help && m.open);
    focus(&m,DM_AUDIO,1);
    for(int i=0;i<4;i++) press(&m,DM_LEFT);
    CHECK(m.values.voice==-1);
    for(int i=0;i<4;i++) press(&m,DM_RIGHT);
    CHECK(m.values.voice==1);
    focus(&m,DM_GAMEPLAY,0);
    for(int i=0;i<8;i++) press(&m,DM_RIGHT);
    CHECK(m.values.stage==3);
    focus(&m,DM_GAMEPLAY,1);
    for(int i=0;i<12;i++) press(&m,DM_RIGHT);
    CHECK(m.values.act==8);
    focus(&m,DM_GAMEPLAY,2);
    for(int i=0;i<12;i++) press(&m,DM_RIGHT);
    CHECK(m.values.character==5);
    focus(&m,DM_GAMEPLAY,3);
    CHECK(press(&m,DM_ACCEPT).action==DM_WARP);
    CHECK(debug_menu_step(&m,DM_ACCEPT,5000).action==DM_NONE);
    CHECK(press(&m,DM_LEFT|DM_RIGHT).action==DM_NONE);
    focus(&m,DM_CHEATS,0);
    CHECK(press(&m,DM_ACCEPT).changed==DM_RINGS_LOCK && m.values.rings_lock==1);
    CHECK(debug_menu_step(&m,DM_ACCEPT,5000).action==DM_NONE);
    CHECK(press(&m,DM_DEFAULTS).changed==DM_RINGS_LOCK && !m.values.rings_lock);
    focus(&m,DM_CHEATS,2); CHECK(press(&m,DM_ACCEPT).action==DM_ADD_RINGS);
    focus(&m,DM_CHEATS,3); CHECK(press(&m,DM_ACCEPT).action==DM_ADD_LIVES);
    focus(&m,DM_DLC,0);
    for(int i=0;i<8;i++) press(&m,DM_RIGHT);
    CHECK(m.values.dlc==2);
    for(int i=0;i<8;i++) press(&m,DM_LEFT);
    CHECK(m.values.dlc==-1);
    CHECK(press(&m,DM_SAVE).action==DM_SAVE_REQUEST && debug_menu_dirty(&m));
    CHECK(debug_menu_step(&m,DM_SAVE,10000).action==DM_NONE);
    debug_menu_mark_saved(&m); CHECK(!debug_menu_dirty(&m));
    CHECK(press(&m,DM_REVERT).action==DM_REVERTED);
    CHECK(m.values.aspect==v.aspect && m.values.stage==v.stage && m.values.act==v.act);
    CHECK(!m.values.rings_lock && debug_menu_dirty(&m));
    CHECK(press(&m,DM_BACK|DM_ACCEPT).action==DM_CLOSE && !m.open);
    CHECK(debug_menu_step(&m,DM_ACCEPT,1000).action==DM_NONE && !m.open);
    open_menu(&m); CHECK(m.opened.act==m.values.act);
    CHECK(press(&m,DM_TOGGLE).action==DM_CLOSE);
    CHECK(debug_menu_step(&m,DM_TOGGLE,UINT32_MAX).action==DM_NONE && !m.open);
    CHECK(debug_menu_row_count(-1)==0 && debug_menu_row_count(DM_PAGE_COUNT)==0);
    CHECK(debug_menu_row_id(0,-1)==-1 && debug_menu_row_id(0,99)==-1);
    CHECK(debug_menu_row_id(DM_GAMEPLAY,3)==DM_ROW_WARP);
    CHECK(strcmp(debug_menu_page_label(DM_CHEATS),"Cheats")==0);
    CHECK(strcmp(debug_menu_row_label(DM_ROW_WARP),"Warp / restart stage")==0);
    CHECK(debug_menu_row_label(-1)!=NULL && debug_menu_page_label(-1)!=NULL);
    CHECK(debug_menu_setting_value(&m.values,DM_NO_SETTING)==0);
    CHECK(debug_menu_setting_value(&m.values,DM_MIPS)==m.values.mips);
    /* Bad config must never create out-of-range state or enable cheats. */
    v=(DebugMenuValues){-9,8,999,0,8,-9,999,0,999,1,1,999};
    debug_menu_init(&m,&v,&v,0,0);
    CHECK(m.values.aspect==0 && m.values.fps==1 && m.values.frame_skip==60);
    CHECK(m.values.mips==1 && m.values.audio==1 && m.values.voice==-1);
    CHECK(m.values.stage==0 && m.values.act==1 && m.values.character==5 && m.values.dlc==-1);
    CHECK(!m.values.rings_lock && !m.values.lives_lock);
    open_menu(&m); focus(&m,DM_GAMEPLAY,3);
    CHECK(press(&m,DM_ACCEPT).action==DM_NONE); /* empty catalog cannot request a warp */
    focus(&m,DM_DLC,0); press(&m,DM_RIGHT); CHECK(m.values.dlc==-1);
    debug_menu_init(&m,NULL,NULL,INT_MAX,INT_MAX);
    CHECK(m.values.aspect==1 && m.values.mips==8 && m.values.audio==1 && m.values.act==1);
    CHECK(m.values.voice==-1 && m.values.dlc==-1 && !m.open);
    /* Public labels and rows cover each setting exactly once. */
    unsigned seen=0;
    for(int p=0;p<DM_PAGE_COUNT;p++) for(int r=0;r<debug_menu_row_count(p);r++) {
        int id=debug_menu_row_id(p,r); CHECK(debug_menu_row_label(id)[0]!=0);
        if(id<DM_SETTING_COUNT) { CHECK(!(seen&(1u<<id))); seen|=1u<<id; }
    }
    CHECK(seen==(1u<<DM_SETTING_COUNT)-1u);
    /* Save / reset / revert are explicit, debounced requests, never side effects
     * of tab movement, popup dismissal, or a held key from the opening chord. */
    debug_menu_init(&m,NULL,NULL,3,2);
    open_menu(&m);
    focus(&m,DM_GRAPHICS,0);
    press(&m,DM_LEFT); CHECK(m.values.aspect==0);
    CHECK(press(&m,DM_BACK).action==DM_CLOSE && m.values.aspect==0);
    open_menu(&m);
    press(&m,DM_RIGHT); CHECK(m.values.aspect==1);
    CHECK(press(&m,DM_REVERT).action==DM_REVERTED && m.values.aspect==0);
    CHECK(debug_menu_step(&m,DM_REVERT,1000).action==DM_NONE);
    CHECK(press(&m,DM_HELP).action==DM_HELP_CHANGED);
    CHECK(press(&m,DM_SAVE).action==DM_NONE && m.help);
    CHECK(press(&m,DM_ACCEPT).action==DM_HELP_CHANGED && !m.help);
    CHECK(debug_menu_step(&m,DM_ACCEPT,1000).action==DM_NONE && m.values.aspect==0);
    debug_menu_step(&m,0,0);
    CHECK(press(&m,DM_SAVE|DM_ACCEPT).action==DM_SAVE_REQUEST && m.values.aspect==0);
    debug_menu_mark_saved(&m); CHECK(!debug_menu_dirty(&m));
    m.page=-1; m.cursor=INT_MAX;
    press(&m,DM_RIGHT); CHECK(m.page==DM_GRAPHICS && m.cursor==0 && m.values.aspect==1);
    CHECK(press(&m,DM_TOGGLE|DM_DEFAULTS|DM_ACCEPT).action==DM_CLOSE);
    CHECK(debug_menu_step(&m,DM_DEFAULTS|DM_ACCEPT,1000).action==DM_NONE);
    CHECK(!m.open && m.values.aspect==1);
    printf("debug_menu: %d checks, %d failures\n",checks,failures);
    return failures?1:0;
}
