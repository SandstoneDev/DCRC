/* Own PSP menu adapter, MIT, Copyright (c) 2026 SandstoneDev.
 * PS2RC supplied UI behavior facts, not implementation source. */
#include "debug_psp.h"
#include "debug_display.h"
#include "../debug_menu.h"
#include "../debug_chord.h"
#include "../debug_config.h"
#include "../game_cheats.h"
#include "../draw.h"
#include "hle.h"
#include "sound/snd_host.h"
#include "game/content_mount.h"
#include "game/startup.h"
#include "chain_path.h"
#include <pspkernel.h>
#include <pspctrl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int draw_gu_set_fps_hud(const char *value);
void draw_gu_set_max_mip(int level);
void audio_psp_pause(int on);
int plat_settings_release(void);
static DebugMenu menu;
static int enabled,running;
static uint32_t heartbeat;
static DebugChord chord_state;
static uint64_t pause_total,pause_start;
static const volatile int *home_exit;
static void (*restart_game)(void);
static char config_path[512],status[160];
static DebugCheatContext cheat;
static DebugMenuValues startup_snapshot;
static DebugCheatContext read_cheat(int advance);
static const struct {const char *label,*key;int acts;} stages[]={
    {"Normal title / menus","off",1},{"Emerald Coast","emerald_coast",2},
    {"Windy Valley","windy_valley",3},{"Twinkle Park","twinkle_park",3},
    {"Speed Highway","speed_highway",3},{"Red Mountain","red_mountain",3},
    {"Sky Deck","sky_deck",3},{"Lost World","lost_world",3},{"Ice Cap","ice_cap",4},
    {"Casinopolis","casinopolis",2},{"Final Egg","final_egg",3},
    {"Chaos 0","chaos0",1},{"Chaos 4","chaos4",1},{"Chaos 6","chaos6",1},
    {"Egg Hornet","egg_hornet",1},{"Egg Viper","egg_viper",1},
    {"Station Square","station_square",6},{"Egg Carrier outside","egg_carrier_outside",6},
    {"Egg Carrier inside","egg_carrier_inside",6},{"Mystic Ruins","mystic_ruins",6},
    {"Sky Chase 1","sky_chase1",1},{"Sky Chase 2","sky_chase2",1}
};
static const char *const characters[]={"sonic","tails","knuckles","amy","gamma","big"};
#define STAGE_COUNT ((int)(sizeof stages/sizeof *stages))
#define CHORD (PSP_CTRL_LTRIGGER|PSP_CTRL_RTRIGGER|PSP_CTRL_CROSS|PSP_CTRL_DOWN)
static void note(const char *s){snprintf(status,sizeof status,"%s",s?s:"");}
static uint32_t raw_pad(void){SceCtrlData p;return sceCtrlPeekBufferPositive(&p,1)>0?p.Buttons:chord_state.previous;}
static uint32_t semantic(uint32_t k){
    uint32_t b=0;
    if(k&PSP_CTRL_UP)b|=DM_UP;if(k&PSP_CTRL_DOWN)b|=DM_DOWN;
    if(k&PSP_CTRL_LEFT)b|=DM_LEFT;if(k&PSP_CTRL_RIGHT)b|=DM_RIGHT;
    if(k&PSP_CTRL_CROSS)b|=DM_ACCEPT;if(k&PSP_CTRL_CIRCLE)b|=DM_BACK;
    if(k&PSP_CTRL_LTRIGGER)b|=DM_TAB_PREV;if(k&PSP_CTRL_RTRIGGER)b|=DM_TAB_NEXT;
    if(k&PSP_CTRL_START)b|=DM_SAVE;if(k&PSP_CTRL_SELECT)b|=DM_REVERT;
    if(k&PSP_CTRL_TRIANGLE)b|=DM_DEFAULTS;if(k&PSP_CTRL_SQUARE)b|=DM_HELP;
    return b;
}
static void apply(int setting){
    DebugMenuValues *v=&menu.values;
    if(setting<0 || setting==DM_ASPECT){
        if(hle_runtime_aspect(v->aspect))draw_set_aspect(v->aspect);
        else {v->aspect=hle_aspect_wide;note("Aspect declined: custom/uninitialized clip, use INI");}
    }
    if(setting<0 || setting==DM_FPS)draw_gu_set_fps_hud(v->fps?"on":"off");
    if(setting<0 || setting==DM_FRAME_SKIP)hle_frame_skip_cli=v->frame_skip==0?-1:v->frame_skip==1?0:v->frame_skip;
    if(setting<0 || setting==DM_MIPS)draw_gu_set_max_mip(v->mips-1);
    if(setting<0 || setting==DM_SOUND)snd_host_set_audio(v->audio);
    if(setting<0 || setting==DM_VOICE)snd_voice_lang=v->voice;
    if(setting<0 || setting==DM_DLC_CHOICE){
        if(hle_content_select(v->dlc)<0)v->dlc=hle_content_selected();
        note(hle_content_status());
    }
    if(v->stage<0 || v->stage>=STAGE_COUNT)v->stage=0;
    if((setting==DM_STAGE || setting==DM_ACT) && v->act>stages[v->stage].acts)v->act=stages[v->stage].acts;
}
static int same_file(const char *path,const char *data,size_t n){
    FILE *f=fopen(path,"rb");if(!f)return 0;
    size_t at=0;char b[512];int ok=1;
    while(at<n){size_t k=n-at<sizeof b?n-at:sizeof b;if(fread(b,1,k,f)!=k||memcmp(b,data+at,k)){ok=0;break;}at+=k;}
    if(ok && fgetc(f)!=EOF)ok=0;
    if(ferror(f))ok=0;if(fclose(f))ok=0;return ok;
}
/* Temporary and backup names are new and owned by this transaction. No
 * inplace fallback: failure retains/restores the prior config and evidence. */
static int save_config(int force_launch){
    if(plat_settings_release()<0){note("Save declined: cached settings handle could not close");return -1;}
    char *old=malloc(16385),*out=malloc(16385);if(!old||!out){free(old);free(out);note("Save declined: not enough temporary memory");return -1;}
    size_t old_n=0;int existed=0;FILE *f=fopen(config_path,"rb");
    if(f){existed=1;old_n=fread(old,1,16385,f);int bad=ferror(f)||old_n>16384;if(fclose(f))bad=1;if(bad){free(old);free(out);note("Save declined: unreadable/oversized INI");return -1;}}
    old[old_n]=0;
    char skip[12],mips[12],act[12],dlc[12];DebugMenuValues *v=&menu.values;
    if(v->frame_skip<2)snprintf(skip,sizeof skip,"%s",v->frame_skip?"off":"auto");else snprintf(skip,sizeof skip,"%d",v->frame_skip);
    snprintf(mips,sizeof mips,"%d",v->mips);snprintf(act,sizeof act,"%d",v->act);
    if(v->dlc<0)strcpy(dlc,"off");else snprintf(dlc,sizeof dlc,"%d",v->dlc);
    DebugIniPair pairs[]={
        {"aspect",v->aspect?"16:9":"4:3"},{"fps_hud",v->fps?"on":"off"},
        {"frame_skip",skip},{"mip_levels",mips},{"audio",v->audio?"on":"off"},
        {"voice",v->voice<0?"game":v->voice?"en":"ja"},{"dlc_event",dlc},
        {"start_stage",stages[v->stage].key},{"start_act",act},{"start_character",characters[v->character]}
    };
    int launch_changed=force_launch || v->stage!=startup_snapshot.stage || v->act!=startup_snapshot.act || v->character!=startup_snapshot.character;
    size_t pair_count=sizeof pairs/sizeof *pairs-(launch_changed?0:3);
    int n=debug_ini_update(old,old_n,pairs,pair_count,out,16385);
    if(n<0){free(old);free(out);note("Save declined: INI too large or malformed");return -1;}
    char tmp[560],bak[560];unsigned tag=(unsigned)sa1_plat_time_us();
    snprintf(tmp,sizeof tmp,"%s.dcrc-%08x.tmp",config_path,tag);
    snprintf(bak,sizeof bak,"%s.dcrc-%08x.bak",config_path,tag);
    if(access(tmp,F_OK)==0||access(bak,F_OK)==0){free(old);free(out);note("Save declined: transaction name exists");return -1;}
    f=fopen(tmp,"wb");int ok=f!=NULL;
    if(f){if(fwrite(out,1,(size_t)n,f)!=(size_t)n||fflush(f))ok=0;if(fclose(f))ok=0;}
    if(ok)ok=same_file(tmp,out,(size_t)n);
    if(ok && existed)ok=same_file(config_path,old,old_n);
    if(ok && !existed && access(config_path,F_OK)==0)ok=0;
    int backed=0,installed=0;
    if(ok&&existed){ok=rename(config_path,bak)==0;backed=ok;}
    if(ok){ok=rename(tmp,config_path)==0;installed=ok;}
    if(ok)ok=same_file(config_path,out,(size_t)n);
    if(!ok&&backed){if(installed)rename(config_path,tmp);if(access(config_path,F_OK)!=0)rename(bak,config_path);}
    if(ok){startup_snapshot=menu.values;debug_menu_mark_saved(&menu);note("Saved + full readback; previous INI kept as .bak");sa1_log("debug-menu: configuration saved/readback; previous backup retained");}
    else note("Save failed; previous config retained/restored; temp kept");
    free(old);free(out);return ok?0:-1;
}
static void value_text(int row,char *out,size_t cap){
    DebugMenuValues *v=&menu.values;
    switch(row){
    case DM_ASPECT:snprintf(out,cap,"%s",v->aspect?"16:9":"4:3");break;
    case DM_FRAME_SKIP:if(v->frame_skip<2)snprintf(out,cap,"%s",v->frame_skip?"Off":"Auto");else snprintf(out,cap,"1 in %d",v->frame_skip);break;
    case DM_MIPS:snprintf(out,cap,"%d (new textures)",v->mips);break;
    case DM_VOICE:snprintf(out,cap,"%s",v->voice<0?"Game":v->voice?"English":"Japanese");break;
    case DM_STAGE:snprintf(out,cap,"%s",stages[v->stage].label);break;
    case DM_ACT:snprintf(out,cap,"%d",v->act);break;
    case DM_CHARACTER:snprintf(out,cap,"%s",characters[v->character]);break;
    case DM_DLC_CHOICE:snprintf(out,cap,"%s",v->dlc<0?"Off (next normal load)":hle_content_label(v->dlc));break;
    case DM_ROW_WARP:snprintf(out,cap,"Cross: save + restart");break;
    case DM_ROW_ADD_RINGS:case DM_ROW_ADD_LIVES:snprintf(out,cap,"Cross: refill to 99");break;
    default:snprintf(out,cap,"%s",debug_menu_setting_value(v,row)?"On":"Off");break;
    }
}
static void render(void){
    char text[20][80];DebugDrawLine lines[20];unsigned n=0;
#define LINE(X,Y,C,T) do{snprintf(text[n],sizeof text[n],"%s",T);lines[n]=(DebugDrawLine){X,Y,C,text[n]};n++;}while(0)
    LINE(16,12,0xffa5f2ffu,"DCRC DEBUG MENU - game paused");
    char title[70];snprintf(title,sizeof title,"L/R: %s   %s",debug_menu_page_label(menu.page),debug_menu_dirty(&menu)?"[unsaved]":"[saved]");
    LINE(16,28,0xffffffffu,title);
    if(menu.help){
        LINE(16,54,0xffffffffu,"Open: L + R + Cross + Down");
        LINE(16,70,0xffffffffu,"Release the chord before Start / Select.");
        LINE(16,86,0xffffffffu,"D-pad: select/change. L/R: switch page.");
        LINE(16,102,0xffffffffu,"Cross: action. Circle: close / back.");
        LINE(16,118,0xffffffffu,"Start: save. Select: revert opening values.");
        LINE(16,134,0xffffffffu,"Triangle: default row. Square: help.");
        LINE(16,150,0xffffffffu,"Stage/character change restarts the game.");
        LINE(16,166,0xffffffffu,"Mip count affects newly loaded textures.");
        LINE(16,182,0xffffffffu,"DLC: next ordinary load after VMU selection.");
    }else{
        for(int i=0;i<debug_menu_row_count(menu.page);i++){
            int row=debug_menu_row_id(menu.page,i);char val[48];value_text(row,val,sizeof val);
            snprintf(text[n],sizeof text[n],"%-22.22s %s",debug_menu_row_label(row),val);
            lines[n]=(DebugDrawLine){20,56+i*20,0xffffffffu,text[n]};n++;
        }
        if(menu.page==DM_CHEATS)LINE(16,158,0xffa5f2ffu,"Cheats: Sonic / Emerald Coast act 1 only.");
        if(menu.page==DM_GAMEPLAY)LINE(16,158,0xffa5f2ffu,"Other character/stage routes may be unsupported.");
        if(menu.page==DM_DLC){LINE(16,150,0xffa5f2ffu,hle_content_status());LINE(16,168,0xffa5f2ffu,"Off unmounts; spawned objects leave on unload.");}
    }
    LINE(16,208,0xffa5f2ffu,chord_state.blocked?"Release ALL buttons before using the menu.":status);
    LINE(16,238,0xffccccccu,"D-pad: edit  L/R: tabs  X: action  O: close");
    LINE(16,254,0xffccccccu,"Start: save  Select: revert  Square: help");
#undef LINE
    draw_debug_screen(lines,n,menu.help?-1:53+menu.cursor*20);
}
static void grant(int rings,int lives){
    DebugCheatContext now=read_cheat(0);
    if(!debug_cheat_allowed(&now)){note("Cheat declined: stable Sonic EC1 gameplay required");return;}
    if(rings&&hle_rd16(0x8c752be4u)<99)hle_wr16(0x8c752be4u,99);
    if(lives&&hle_rd8(0x8c752be0u)<99)hle_wr8(0x8c752be0u,99);
    note("Cheat applied: requested counter refilled to 99");
}
static void event(DebugMenuEvent e){
    switch(e.action){
    case DM_CHANGED:apply(e.changed);if(e.changed==DM_MIPS)note("Mip count applies to newly loaded textures");break;
    case DM_REVERTED:apply(-1);note("Opening values restored for this session");break;
    case DM_SAVE_REQUEST:save_config(0);break;
    case DM_ADD_RINGS:grant(1,0);break;
    case DM_ADD_LIVES:grant(0,1);break;
    case DM_WARP:
        if(!restart_game){note("Restart unavailable for this installation path");break;}
        if(hle_startup_cli_active()){note("Warp declined: remove startup overrides from args.txt");break;}
        if(hle_content_selected()>=0 && menu.values.stage){note("DLC requires normal boot / VMU selection first");break;}
        if(menu.values.act>stages[menu.values.stage].acts){note("Act outside this menu preset's supported range");break;}
        if(save_config(1)==0 && restart_game){menu.open=0;restart_game();}break;
    default:break;
    }
}
void debug_psp_init(const char *base,const char *data,const volatile int *home,void (*restart)(void)){
    home_exit=home;restart_game=restart;
    char self[256];int self_n=snprintf(self,sizeof self,"%s/EBOOT.PBP",base?base:"");
    if(self_n<0||self_n>=(int)sizeof self||!sa1_application_path_valid(self))restart_game=NULL;
    enabled=hle_config_debug_menu && !hle_strict;
    int n=snprintf(config_path,sizeof config_path,"%s/sa1psp.ini",data?data:"data");if(n<0||n>=(int)sizeof config_path)enabled=0;
    int skip=hle_frame_skip_cli!=-2?hle_frame_skip_cli:hle_frame_skip;
    DebugMenuValues v={hle_aspect_wide,draw_gu_fps_enabled(),skip<0?0:skip==0?1:skip,draw_gu_mip_limit(),snd_audio_enabled,snd_voice_lang,0,1,0,0,0,hle_content_selected()};
    uint16_t level=0,act=0,character=0;int startup_enabled=0;
    if(!hle_startup_get(&level,&act,&character,&startup_enabled)){
        static const int levels[]={0,1,2,3,4,5,6,7,8,9,10,15,17,18,20,22,26,29,32,33,36,37};
        static const int chars[]={0,2,3,5,6,7};
        if(startup_enabled)for(int i=1;i<STAGE_COUNT;i++)if(levels[i]==level){v.stage=i;break;}
        v.act=(int)act+1;for(int i=0;i<6;i++)if(chars[i]==character){v.character=i;break;}
    }
    DebugMenuValues defaults={1,1,0,8,1,1,0,1,0,0,0,-1};
    debug_menu_init(&menu,&v,&defaults,STAGE_COUNT,hle_content_count());
    startup_snapshot=menu.values;
    note("L+R+Cross+Down: open. Release chord fully.");
    sa1_log("debug-menu: enabled=%d chord=L+R+Cross+Down restart_is_explicit=1 cheats_default_off=1",enabled);
}
void debug_psp_poll(void){
    if(!enabled || running)return;
    event(debug_menu_raw_step(&menu,&chord_state,raw_pad(),CHORD,0,0));
    if(menu.open)hle_draw_skip=0;
}
int debug_psp_capture(void){return enabled&&(menu.open||chord_state.blocked);}
uint32_t debug_psp_heartbeat(void){return hle_frame_count()+heartbeat;}
uint64_t debug_psp_paused_us(void){return pause_total+(running?sa1_plat_time_us()-pause_start:0);}
void debug_psp_boundary(void){
    if(!enabled||running||!menu.open||!draw_debug_ready())return;
    running=1;pause_start=sa1_plat_time_us();audio_psp_pause(1);
    sa1_log("debug-menu: opened guest=%u mono_us=%llu",hle_frame_count(),(unsigned long long)pause_start);
    uint64_t last=pause_start;
    while(menu.open&&!(home_exit&&*home_exit)){
        uint32_t raw=raw_pad();
        uint64_t now=sa1_plat_time_us();unsigned dt=(unsigned)((now-last)/1000);last=now;
        DebugMenuEvent e=debug_menu_raw_step(&menu,&chord_state,raw,CHORD,semantic(raw),dt);event(e);
        heartbeat++;
        if(!menu.open){chord_state.blocked|=raw;break;}
        render();
    }
    audio_psp_pause(0);pause_total+=sa1_plat_time_us()-pause_start;running=0;
    draw_debug_reset_meter();
    sa1_log("debug-menu: closed guest=%u paused_us=%llu",hle_frame_count(),(unsigned long long)pause_total);
}
static DebugCheatContext read_cheat(int advance){
    uint32_t task=hle_rd32(0x8c78c648u),work=hle_rd32(0x8c78c608u);
    int mode=hle_rd32(0x8c760970u),sub=hle_rd16(0x8c7493b4u);
    int level=hle_rd16(0x8c7493bau),act=hle_rd16(0x8c7493bcu),ch=hle_rd16(0x8c7493c8u);
    int stable=task==cheat.task&&work==cheat.work&&mode==cheat.mode&&sub==cheat.substate
        &&level==cheat.level&&act==cheat.act&&ch==cheat.character?cheat.stable+(advance?1:0):0;
    if(stable>3)stable=3;
    DebugCheatContext now=(DebugCheatContext){hle_strict,mode,level,ch,stable,act,sub,task,work,0,0,0,0,
        (int16_t)hle_rd16(0x8c752be4u),(int8_t)hle_rd8(0x8c752be0u)};
    if(debug_guest_span(task,36)&&debug_guest_span(work,44)){
        now.linked_work=hle_rd32(task+32);
        uint32_t a=hle_rd32(work+32),b=hle_rd32(work+36),c=hle_rd32(work+40);
        memcpy(&now.x,&a,4);memcpy(&now.y,&b,4);memcpy(&now.z,&c,4);
    }
    return now;
}
void debug_psp_cheats(void){
    if(!enabled)return;
    cheat=read_cheat(1);
    if((menu.values.rings_lock||menu.values.lives_lock)&&debug_cheat_allowed(&cheat))grant(menu.values.rings_lock,menu.values.lives_lock);
}
