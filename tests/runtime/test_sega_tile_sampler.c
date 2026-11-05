/* Synthetic sampler policy and edge colours; no game bytes. MIT. */
#include "../../backend/sega_tile_sampler.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static unsigned checks,failures;
#define CHECK(x) do { checks++; if(!(x)) { failures++; fprintf(stderr,"line %d: %s\n",__LINE__,#x); } } while(0)
static draw_state state(void) {
    draw_state s={0};s.texture=7;s.layer=DRAW_LAYER_3D_43;s.filter=DRAW_FILTER_BILINEAR;return s;
}
static int policy(const draw_state *s,int strict,unsigned mode,unsigned resolved,int w,int h,int fmt,const char *name) {
    return sega_tile_sampler_clamp(s,strict,mode,resolved,w,h,fmt,name);
}
/* A synthetic blue edge with white on the opposite edge. At mip1 the
 * minified pixel lies just before texel0's centre and repeat reads white.
 * Clamp reads blue at both taps. No geometry or UV change is necessary. */
static double red_edge(int clamp) {
    const double local_y=(145.5*480.0/272.0)-256.0;
    double t=local_y/2.0-0.5;
    double mip1=clamp?0.0:-t*255.0;
    return log2(480.0/272.0)*mip1;
}
int main(void) {
    draw_state s=state(),before=s;
    char name[]="segalogo0";
    for(int i=0;i<6;i++) {name[8]=(char)('0'+i);CHECK(policy(&s,0,1,7,256,256,DRAW_FMT_5650,name)==1);}
    CHECK(!memcmp(&s,&before,sizeof s));
    CHECK(!policy(NULL,0,1,7,256,256,DRAW_FMT_5650,name));
    CHECK(!policy(&s,1,1,7,256,256,DRAW_FMT_5650,name));
    for(unsigned m=0;m<32;m++)if(m!=1)CHECK(!policy(&s,0,m,7,256,256,DRAW_FMT_5650,name));
    for(unsigned l=0;l<4;l++)if(l!=DRAW_LAYER_3D_43){s.layer=(uint8_t)l;CHECK(!policy(&s,0,1,7,256,256,DRAW_FMT_5650,name));}
    s=state();
    CHECK(!policy(&s,0,1,0,256,256,DRAW_FMT_5650,name));
    CHECK(!policy(&s,0,1,8,256,256,DRAW_FMT_5650,name));
    s.texture=0;CHECK(!policy(&s,0,1,0,256,256,DRAW_FMT_5650,name));s=state();
    CHECK(!policy(&s,0,1,7,128,256,DRAW_FMT_5650,name));
    CHECK(!policy(&s,0,1,7,256,128,DRAW_FMT_5650,name));
    CHECK(!policy(&s,0,1,7,0,256,DRAW_FMT_5650,name));
    for(int f=1;f<=DRAW_FMT_T8;f++)CHECK(!policy(&s,0,1,7,256,256,f,name));
    s.filter=DRAW_FILTER_POINT;CHECK(!policy(&s,0,1,7,256,256,DRAW_FMT_5650,name));
    s.filter=255;CHECK(!policy(&s,0,1,7,256,256,DRAW_FMT_5650,name));
    for(int f=DRAW_FILTER_BILINEAR;f<=DRAW_FILTER_TRILINEAR_B;f++){s.filter=(uint8_t)f;CHECK(policy(&s,0,1,7,256,256,DRAW_FMT_5650,name));}s=state();
    s.flip_u=1;CHECK(!policy(&s,0,1,7,256,256,DRAW_FMT_5650,name));s=state();
    s.flip_v=1;CHECK(!policy(&s,0,1,7,256,256,DRAW_FMT_5650,name));s=state();
    s.clamp_u=s.clamp_v=1;before=s;CHECK(!policy(&s,0,1,7,256,256,DRAW_FMT_5650,name));CHECK(!memcmp(&s,&before,sizeof s));s=state();
    s.clamp_u=1;CHECK(policy(&s,0,1,7,256,256,DRAW_FMT_5650,name));s=state();
    s.clamp_v=1;CHECK(policy(&s,0,1,7,256,256,DRAW_FMT_5650,name));s=state();
    const char *bad[]={NULL,"","?","segalogo","segalogo6","segalogo9","segalogo/","segalogo00","segalogo0x","SEGALOGO0","othername","segalogp0"};
    for(unsigned i=0;i<sizeof bad/sizeof *bad;i++)CHECK(!policy(&s,0,1,7,256,256,DRAW_FMT_5650,bad[i]));
    /* Same numeric handle, different live name: there is no cached admission. */
    CHECK(policy(&s,0,1,7,256,256,DRAW_FMT_5650,"segalogo0"));
    CHECK(!policy(&s,0,1,7,256,256,DRAW_FMT_5650,"reused_slot"));
    CHECK(red_edge(0)>24.0&&red_edge(0)<25.0);CHECK(red_edge(1)==0.0);
    printf("sega_tile_sampler: %u checks, %u failures; synthetic repeat R%.5f -> clamp R%.1f\n",checks,failures,red_edge(0),red_edge(1));
    return failures?1:0;
}
