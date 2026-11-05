/* Own config/launch adapter, using US1.005 bindings, no PC mod-loader code.
 * Ordinary game loading chooses resources/collision/tasks/start position.
 * Part of sa1-psp (MIT). */
#include "startup.h"
#include "../hle.h"
#include <string.h>
#include <ctype.h>

enum { START_STAGE=1, START_ACT=2, START_CHARACTER=4 };
typedef struct {
    unsigned set, bad;
    int enabled;
    uint16_t level, act, preset_act, mode, character;
} startup_options;
static startup_options startup_ini, startup_cli, startup_active;
static int startup_armed;

/* The raw LEVEL:ACT:MODE syntax remains the advanced US1.005 escape hatch.
 * Aliases cover the existing Sonic survey, not a promise every character
 * can finish every stage. Acts in this table are guest zero-based values. */
static const struct { const char *name; uint16_t level,act,mode; } stages[] = {
    {"ec",1,0,4},{"emeraldcoast",1,0,4},
    {"windyvalley",2,0,4},{"twinklepark",3,0,4},{"speedhighway",4,0,4},
    {"redmountain",5,0,4},{"skydeck",6,0,4},{"lostworld",7,0,4},
    {"icecap",8,0,4},{"casinopolis",9,0,4},{"finalegg",10,0,4},
    {"chaos0",15,0,4},{"chaos4",17,0,4},{"chaos6",18,0,4},
    {"egghornet",20,0,4},{"eggviper",22,0,4},
    {"ss",26,3,5},{"stationsquare",26,3,5},
    {"eggcarrieroutside",29,0,5},{"eggcarrierinside",32,0,5},
    {"mysticruins",33,0,5},{"skychase1",36,0,4},{"skychase2",37,0,4}
};
static int normalized(const char *v,char *out,unsigned size) {
    unsigned n=0;
    for (;*v;v++) {
        unsigned char c=(unsigned char)*v;
        if (c=='_' || c=='-' || isspace(c)) continue;
        if (n+1>=size) return 0;
        out[n++]=(char)tolower(c);
    }
    out[n]=0; return 1;
}
static int number(const char **v,unsigned max,uint16_t *out) {
    const char *p=*v; unsigned n=0;
    if (*p<'0' || *p>'9') return 0;
    do {
        unsigned d=(unsigned)(*p-'0');
        if (d>max || n>(max-d)/10u) return 0;
        n=n*10u+d; p++;
    } while (*p>='0' && *p<='9');
    *out=(uint16_t)n; *v=p; return 1;
}
static int stage(const char *v,startup_options *s) {
    char name[64];
    if (!normalized(v,name,sizeof name)) return 0;
    if (!strcmp(name,"off") || !strcmp(name,"none")) { s->enabled=0; return 1; }
    for (unsigned i=0;i<sizeof stages/sizeof *stages;i++) if (!strcmp(name,stages[i].name)) {
        s->level=stages[i].level; s->preset_act=stages[i].act; s->mode=stages[i].mode; s->enabled=1; return 1;
    }
    uint16_t l,a,m; const char *p=v;
    if (!number(&p,43,&l) || *p++!=':' || !number(&p,7,&a) || *p++!=':'
        || !number(&p,5,&m) || *p || (m!=4 && m!=5)) return 0;
    s->level=l; s->preset_act=a; s->mode=m; s->enabled=1; return 1;
}
static int character(const char *v,uint16_t *out) {
    static const struct { const char *name; uint16_t id; } names[] = {
        {"sonic",0},{"tails",2},{"miles",2},{"knuckles",3},
        {"amy",5},{"gamma",6},{"e102",6},{"big",7}
    };
    char name[32]; if (!normalized(v,name,sizeof name)) return 0;
    for (unsigned i=0;i<sizeof names/sizeof *names;i++) if (!strcmp(name,names[i].name)) {
        *out=names[i].id; return 1;
    }
    return 0;
}
int hle_startup_setting(const char *key,const char *value,int cli) {
    startup_options *s=cli?&startup_cli:&startup_ini;
    if (!value) {
        unsigned field=!strcmp(key,"start_stage")?START_STAGE:
            !strcmp(key,"start_act")?START_ACT:!strcmp(key,"start_character")?START_CHARACTER:0;
        if (!field) return 0;
        s->set|=field; s->bad|=field;
        return -1;
    }
    unsigned field; int ok;
    if (!strcmp(key,"start_stage")) { field=START_STAGE; ok=stage(value,s); }
    else if (!strcmp(key,"start_act")) {
        field=START_ACT; const char *p=value; uint16_t act;
        ok=number(&p,8,&act) && !*p && act>=1;
        if (ok) s->act=(uint16_t)(act-1);
    } else if (!strcmp(key,"start_character")) { field=START_CHARACTER; ok=character(value,&s->character); }
    else return 0;
    s->set|=field;
    if (ok) s->bad&=~field; else s->bad|=field;
    return ok?1:-1;
}
static void layer(startup_options *out,const startup_options *s) {
    if (s->set&START_STAGE) {
        out->enabled=s->enabled; out->level=s->level; out->act=s->preset_act; out->mode=s->mode;
        /* A CLI stage preset owns its default act as well. */
        out->bad&=~(START_STAGE|START_ACT);
        out->bad|=s->bad&START_STAGE;
    }
    if (s->set&START_ACT) { out->act=s->act; out->bad=(out->bad&~START_ACT)|(s->bad&START_ACT); }
    if (s->set&START_CHARACTER) { out->character=s->character; out->bad=(out->bad&~START_CHARACTER)|(s->bad&START_CHARACTER); }
}
void hle_startup_prepare(int resuming) {
    memset(&startup_active,0,sizeof startup_active); startup_armed=0;
    layer(&startup_active,&startup_ini); layer(&startup_active,&startup_cli);
    /* An invalid stage can have enabled=0; report the error before off. */
    if (startup_active.bad) { sa1_log("startup: invalid start setting mask=%u; no warp",startup_active.bad); return; }
    if (!startup_active.enabled) return;
    if (resuming) { sa1_log("startup: disabled for saved-state resume"); return; }
    if (hle_strict) { sa1_log("startup: disabled in strict replay mode"); return; }
    startup_armed=1;
    sa1_log("startup: armed level=%u act=%u character=%u mode=%u at fresh frame12 (act is zero-based here)",
        startup_active.level,startup_active.act,startup_active.character,startup_active.mode);
}
void hle_startup_frame(uint32_t frame) {
    if (!startup_armed || frame<12) return;
    startup_armed=0;
    uint32_t mode=hle_rd32(0x8c760970u);
    if (frame!=12 || mode!=1) { sa1_log("startup: skipped frame=%u mode=%u (fresh mode1 required)",frame,mode); return; }
    hle_wr16(0x8c7493c8u,startup_active.character);
    hle_wr16(0x8c7493bau,startup_active.level); hle_wr16(0x8c7493bcu,startup_active.act);
    hle_wr16(0x8c7493beu,startup_active.level); hle_wr16(0x8c7493c0u,startup_active.act);
    hle_wr32(0x8c760970u,startup_active.mode);
    sa1_log("startup: applied level=%u act=%u character=%u mode=%u frame=%u",
        startup_active.level,startup_active.act,startup_active.character,startup_active.mode,frame);
}
int hle_startup_get(uint16_t *level,uint16_t *act,uint16_t *character,int *enabled) {
    if(startup_active.bad || !level || !act || !character || !enabled)return -1;
    *level=startup_active.level;*act=startup_active.act;*character=startup_active.character;
    *enabled=startup_active.enabled;return 0;
}
int hle_startup_cli_active(void){return startup_cli.set!=0;}
