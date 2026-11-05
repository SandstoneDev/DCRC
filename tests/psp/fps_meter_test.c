/* Synthetic visible-picture FPS meter checks. No game data.
 * cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined
 *   tests/psp/fps_meter_test.c -o work/fps_meter_test
 * Part of sa1-psp (MIT). */
#include "../../backend/psp/fps_meter.h"
#include <stdio.h>
#include <string.h>
#include <stdint.h>

static unsigned checks, failures;
#define CHECK(x, why) do { checks++; if (!(x)) { failures++; printf("FAIL: %s\n",why); } } while (0)
static void expect(const fps_meter *m,const char *want,const char *why) {
    char text[16]; fps_meter_format(m,text,sizeof text);
    CHECK(!strcmp(text,want),why);
}
static void style(const fps_meter *m,const char *want,const char *why) {
    char text[32]; fps_meter_style_text(m,text,sizeof text);
    CHECK(!strcmp(text,want),why);
}
static void begin(fps_meter *m,display_counter *c,uint64_t now,uint32_t guest,uint32_t scene) {
    fps_meter_reset(m); memset(c,0,sizeof *c); fps_meter_sample(m,c,now,guest,scene);
}
int main(void) {
    fps_meter m; display_counter c;
    fps_meter_reset(&m); expect(&m,"FPS --.-","initial placeholder");
    begin(&m,&c,0,0,1);
    fps_meter_sample(&m,&c,0,0,1); expect(&m,"FPS --.-","same timestamp cannot divide by zero");
    c.visible=15; fps_meter_sample(&m,&c,500000,30,1);
    expect(&m,"FPS --.-","subsecond sample stays warm");
    c.visible=30; fps_meter_sample(&m,&c,1000000,60,1);
    expect(&m,"FPS 30.0","visible30 guest60 reports visible rate only");
    c.visible=31; fps_meter_sample(&m,&c,1500000,90,1);
    expect(&m,"FPS 30.0","cached value retained between windows");
    c.visible=60; fps_meter_sample(&m,&c,2000000,120,1);
    expect(&m,"FPS 30.0","next full window updates");
    c.visible=60; fps_meter_sample(&m,&c,3000000,180,1);
    expect(&m,"FPS 0.0","no visible progress reports zero after measured second");

    begin(&m,&c,100,100,1); c.visible=45;
    fps_meter_sample(&m,&c,1500100,190,1);
    expect(&m,"FPS 30.0","actual elapsed microseconds determine rate");
    fps_meter_sample(&m,&c,1400000,200,1);
    expect(&m,"FPS --.-","backward clock warms again");
    c.visible=75; fps_meter_sample(&m,&c,2400000,260,1);
    expect(&m,"FPS 30.0","recovers after backward clock rebase");
    fps_meter_sample(&m,&c,2500000,5,1);
    expect(&m,"FPS --.-","guest rollback warms again");
    c.visible=105; fps_meter_sample(&m,&c,3500000,65,1);
    expect(&m,"FPS 30.0","recovers after guest rollback");
    fps_meter_sample(&m,&c,3600000,66,2);
    expect(&m,"FPS --.-","scene change warms again");
    c.visible=135; fps_meter_sample(&m,&c,4600000,126,2);
    expect(&m,"FPS 30.0","recovers after scene change");
    c.visible=165; fps_meter_sample(&m,&c,9600001,186,2);
    expect(&m,"FPS --.-","gap greater than five seconds rebases");
    c.visible=195; fps_meter_sample(&m,&c,10600001,246,2);
    expect(&m,"FPS 30.0","recovers after pause gap");

    begin(&m,&c,0,0,1); c.visible=150;
    fps_meter_sample(&m,&c,5000000,300,1);
    expect(&m,"FPS 30.0","exactly five seconds remains a valid interval");
    fps_meter_reset(&m); memset(&c,0,sizeof c); c.visible=UINT32_MAX-10;
    fps_meter_sample(&m,&c,0,0,1); c.visible=19;
    fps_meter_sample(&m,&c,1000000,60,1);
    expect(&m,"FPS 30.0","unsigned visible wrap counts thirty pictures");
    c.visible=18; fps_meter_sample(&m,&c,1100000,66,1);
    expect(&m,"FPS --.-","backward large unsigned counter delta rebases");
    c.visible=48; fps_meter_sample(&m,&c,2100000,126,1);
    expect(&m,"FPS 30.0","recovers after counter reset");

    begin(&m,&c,0,0,1);
    c.visible=30; fps_meter_sample(&m,&c,1003344,60,1);
    expect(&m,"FPS 29.9","fractional visible rate formats one decimal");
    c.query_errors=1; fps_meter_sample(&m,&c,1500000,90,1);
    expect(&m,"FPS~29.9","uncertainty marker applies immediately to cached value");
    c.query_errors=0; fps_meter_sample(&m,&c,1600000,96,1);
    expect(&m,"FPS~29.9","uncertainty marker is sticky if counters later clear");
    fps_meter_sample(&m,&c,1700000,97,2);
    expect(&m,"FPS --.-","uncertain scene change still warms numeric value");
    c.visible=60; fps_meter_sample(&m,&c,2700000,157,2);
    expect(&m,"FPS~30.0","warm reset preserves sticky uncertainty");

    for(unsigned flag=0;flag<7;flag++) {
        begin(&m,&c,0,0,1);
        uint32_t *fields[]={&c.complete_errors,&c.schedule_errors,&c.query_errors,
            &c.coverage_gaps,&c.unresolved,&c.hidden,&c.foreground_unknown};
        *fields[flag]=1; c.visible=30; fps_meter_sample(&m,&c,1000000,60,1);
        expect(&m,"FPS~30.0","each cumulative uncertainty source marks lower bound");
    }
    begin(&m,&c,0,0,1); c.visible=1000000;
    fps_meter_sample(&m,&c,1000000,60,1);
    expect(&m,"FPS 999.9","high positive rate is numerically clamped");
    char tiny[4]={'x','x','x','x'};
    fps_meter_format(&m,tiny,0); CHECK(tiny[0]=='x',"zero capacity writes nothing");
    fps_meter_format(&m,NULL,0);
    fps_meter_format(&m,tiny,1); CHECK(tiny[0]==0 && tiny[1]=='x',"capacity one writes only NUL");
    memset(tiny,'x',sizeof tiny); fps_meter_format(&m,tiny,3);
    CHECK(!memcmp(tiny,"FP\0x",4),"small buffer is bounded and terminated");
    char exact[10]; fps_meter_format(&m,exact,sizeof exact);
    CHECK(!strcmp(exact,"FPS 999.9"),"maximum numeric label fits ten bytes");
    fps_meter_reset(&m); style(&m,"--.- FPS --- ms","style warm placeholder");
    begin(&m,&c,0,0,1); c.visible=7; fps_meter_sample(&m,&c,1000000,60,1);
    style(&m," 7.0 FPS 143 ms","style width and observed interval");
    CHECK(m.frame_us==142857,"mean microseconds round from elapsed/pictures");
    c.query_errors=1; fps_meter_sample(&m,&c,1500000,90,1);
    style(&m," 7.0 FPS~ 143 ms","style preserves immediate sticky uncertainty");
    CHECK(m.frame_us==142857,"interval remains cached in partial window");
    begin(&m,&c,0,0,1); c.visible=22; fps_meter_sample(&m,&c,1500000,90,1);
    style(&m,"14.7 FPS  68 ms","reference style fractional rate and width");
    CHECK(m.frame_us==68182,"nonuniform window uses actual elapsed");
    begin(&m,&c,0,0,1); c.visible=2; fps_meter_sample(&m,&c,1001000,60,1);
    CHECK(m.frame_us==500500,"mean period includes fractional milliseconds");
    style(&m," 2.0 FPS 501 ms","milliseconds round actual interval, not rounded FPS reciprocal");
    c.visible=2; fps_meter_sample(&m,&c,2001000,120,1);
    CHECK(m.frame_us==0,"zero visible pictures clears mean period");
    style(&m," 0.0 FPS --- ms","measured zero has no period");
    fps_meter_sample(&m,&c,2101000,121,2);
    CHECK(m.frame_us==0,"warm scene reset clears period");
    style(&m,"--.- FPS --- ms","style warms on scene change");
    m.valid=1; m.fps_tenths=9999; m.frame_us=UINT32_MAX;
    style(&m,"999.9 FPS 99999 ms","style bounded maximum period and rate");
    memset(tiny,'x',sizeof tiny); fps_meter_style_text(&m,tiny,0);
    CHECK(tiny[0]=='x',"style zero capacity writes nothing");
    fps_meter_style_text(&m,NULL,10);
    fps_meter_style_text(&m,tiny,1); CHECK(tiny[0]==0 && tiny[1]=='x',"style capacity one only NUL");
    memset(tiny,'x',sizeof tiny); fps_meter_style_text(&m,tiny,3);
    CHECK(!memcmp(tiny,"99\0x",4),"style truncates with NUL within capacity");
    printf("fps_meter_test: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
