/* Startup warp contract on synthetic guest memory. No game data. MIT. */
#include "../../hle/hle.h"
#include <stdio.h>
#include <stdarg.h>
#include <assert.h>
static uint8_t ram[SA1_RAM_SIZE+SA1_RAM_EXTRA];
uint8_t *const sa1_ram=ram;
static uint32_t mode, words[6];
static int writes, last_bits;
int hle_strict;
void sa1_log(const char *fmt, ...) { (void)fmt; }
static void test_wr16(uint32_t addr, uint32_t value) {
    static const uint32_t a[5]={0x8c7493bau,0x8c7493bcu,0x8c7493beu,0x8c7493c0u,0x8c7493c8u};
    int i; for(i=0;i<5;i++) if(a[i]==addr) break;
    assert(i<5); words[i]=value; writes++; last_bits=16; WR16(addr,0,value);
}
static void test_wr32(uint32_t addr, uint32_t value) { assert(addr==0x8c760970u); words[5]=value; mode=value; writes++; last_bits=32; WR32(addr,0,value); }
#define hle_wr16 test_wr16
#define hle_wr32 test_wr32
#include "../../hle/game/startup.c"
static void fresh(void) {
    memset(&startup_ini,0,sizeof startup_ini); memset(&startup_cli,0,sizeof startup_cli);
    memset(&startup_active,0,sizeof startup_active); memset(words,0,sizeof words);
    startup_armed=0; mode=1; WR32(0x8c760970u,0,mode); writes=0;
}
static void option(const char *k,const char *v,int cli) { assert(hle_startup_setting(k,v,cli)==1); }
static void test_missing_return(void) {
    fresh();
    hle_startup_prepare(0);
    WR32(0x8c760970u,0,4);
    WR16(0x8c7493bau,0,0);
    WR16(0x8c7493bcu,0,0);
    assert(!hle_startup_missing_return(1401)); /* ordinary boot */

    fresh();
    option("start_stage","speed_highway",0);
    hle_startup_prepare(0);
    hle_startup_frame(12);
    assert(!hle_startup_missing_return(13)); /* action stage still running */
    WR16(0x8c7493bau,0,0);
    WR16(0x8c7493bcu,0,0);
    WR32(0x8c760970u,0,5);
    assert(!hle_startup_missing_return(912)); /* another game mode */
    WR32(0x8c760970u,0,4);
    WR16(0x8c7493b6u,0,4);
    WR16(0x8c7493c4u,0,3);
    /* Previous and return metadata cannot make the current stage supported. */
    assert(hle_startup_missing_return(913));
    assert(!hle_startup_missing_return(1402)); /* one recovery per boot */
}
int main(void) {
    uint16_t level=99,act=99,ch=99;int enabled=-1;
    fresh();option("start_stage","ec",0);option("start_act","2",0);option("start_character","tails",0);
    hle_startup_prepare(0);assert(!hle_startup_get(&level,&act,&ch,&enabled));
    assert(level==1&&act==1&&ch==2&&enabled==1&&!hle_startup_cli_active());
    option("start_stage","off",1);hle_startup_prepare(0);
    assert(!hle_startup_get(&level,&act,&ch,&enabled)&&!enabled&&hle_startup_cli_active());
    fresh(); hle_startup_prepare(0); hle_startup_frame(12); assert(writes==0);
    option("start_stage","emerald_coast",0); option("start_act","1",0); option("start_character","sonic",0);
    hle_startup_prepare(0); hle_startup_frame(11); assert(writes==0);
    hle_startup_frame(12); assert(writes==6 && words[0]==1 && words[1]==0 && words[2]==1 && words[3]==0 && words[4]==0 && words[5]==4 && last_bits==32);
    hle_startup_frame(12); hle_startup_frame(13); assert(writes==6);
    fresh(); option("start_stage","ss",0); option("start_character","tails",0);
    option("start_stage","1:2:4",1); option("start_act","2",1); option("start_character","knuckles",1);
    hle_startup_prepare(0); hle_startup_frame(12); assert(words[0]==1 && words[1]==1 && words[4]==3);
    fresh(); option("start_stage","ss",0); option("start_act","6",0); option("start_stage","ec",1);
    hle_startup_prepare(0); hle_startup_frame(12); assert(words[1]==0); /* CLI preset includes its default act */
    fresh(); option("start_act","2",0); option("start_stage","ec",0);
    hle_startup_prepare(0); hle_startup_frame(12); assert(words[1]==1); /* INI order is irrelevant */
    const char *badstage[]={"", "1:0:4junk", "-1:0:4", "44:0:4", "1:8:4", "1:0:99", "ec:1", "1:0", "unknown"};
    for(unsigned i=0;i<sizeof badstage/sizeof *badstage;i++) {
        fresh(); assert(hle_startup_setting("start_stage",badstage[i],0)==-1);
        hle_startup_prepare(0); hle_startup_frame(12); assert(writes==0);
    }
    const char *badact[]={"0", "9", "-1", "1x", "9999999999999999999999999"};
    for(unsigned i=0;i<sizeof badact/sizeof *badact;i++) {
        fresh(); option("start_stage","ec",0); assert(hle_startup_setting("start_act",badact[i],0)==-1);
        hle_startup_prepare(0); hle_startup_frame(12); assert(writes==0);
    }
    const char *chars[]={"sonic","tails","knuckles","amy","gamma","big"};
    const unsigned ids[]={0,2,3,5,6,7};
    for(int i=0;i<6;i++) { fresh(); option("start_stage","ec",0); option("start_character",chars[i],0); hle_startup_prepare(0); hle_startup_frame(12); assert(words[4]==ids[i]); }
    fresh(); option("start_stage","ec",0); assert(hle_startup_setting("start_character","eggman",0)==-1); hle_startup_prepare(0); hle_startup_frame(12); assert(writes==0);
    fresh(); option("start_stage","ec",0); option("start_stage","off",1); hle_startup_prepare(0); hle_startup_frame(12); assert(writes==0);
    fresh(); assert(hle_startup_setting("start_stage",NULL,1)==-1); option("start_stage","ec",0); hle_startup_prepare(0); hle_startup_frame(12); assert(writes==0);
    fresh(); option("start_stage","ec",0); hle_startup_prepare(1); hle_startup_frame(12); assert(writes==0);
    fresh(); option("start_stage","ec",0); hle_strict=1; hle_startup_prepare(0); hle_startup_frame(12); assert(writes==0); hle_strict=0;
    fresh(); option("start_stage","ec",0); hle_startup_prepare(0); mode=4; WR32(0x8c760970u,0,mode); hle_startup_frame(12); mode=1; WR32(0x8c760970u,0,mode); hle_startup_frame(13); assert(writes==0);
    assert(hle_startup_setting("unrelated","on",0)==0);
    test_missing_return();
    puts("startup warp tests PASS");
}
