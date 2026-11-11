/* Own synthetic optional border format/geometry checks; no image bytes. MIT. */
#include "../../backend/border_image.h"
#include <stdio.h>
#include <string.h>
static unsigned checks,failures;
#define CHECK(x) do{checks++;if(!(x)){failures++;fprintf(stderr,"line %d: %s\n",__LINE__,#x);}}while(0)
static void word(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8));}
int main(void){
    uint8_t h[16];word(h,BORDER_IMAGE_MAGIC);word(h+4,128);word(h+8,512);word(h+12,131072);
    CHECK(border_image_header_valid(h,16));CHECK(!border_image_header_valid(NULL,16));
    for(unsigned n=0;n<16;n++)CHECK(!border_image_header_valid(h,n));
    CHECK(!border_image_header_valid(h,17));
    for(unsigned i=0;i<16;i++){h[i]^=1;CHECK(!border_image_header_valid(h,16));h[i]^=1;}
    word(h+12,UINT32_MAX);CHECK(!border_image_header_valid(h,16));word(h+12,131072);
    CHECK(sizeof(border_image_vertex)==16);
    border_image_vertex v[4];border_image_vertices(v);
    CHECK(v[0].x==0&&v[0].y==0&&v[1].x==60&&v[1].y==272);
    CHECK(v[2].x==420&&v[2].y==0&&v[3].x==480&&v[3].y==272);
    CHECK(v[0].u==0&&v[1].u==60&&v[2].u==64&&v[3].u==124);
    for(unsigned i=0;i<4;i++)CHECK(v[i].v==(i%2?272:0)&&v[i].z==0&&v[i].color==UINT32_MAX&&v[i].pad==0);
    CHECK(border_image_visible(0,0,1));CHECK(!border_image_visible(1,0,1));
    CHECK(!border_image_visible(0,1,1));CHECK(!border_image_visible(0,0,0));
    CHECK(border_image_memory_fits(0x08800000u,131072));
    CHECK(border_image_memory_fits(0x0c000000u-131072u,131072));
    CHECK(!border_image_memory_fits(0x0c000000u-131071u,131072));
    CHECK(!border_image_memory_fits(0,131072));CHECK(!border_image_memory_fits(UINTPTR_MAX,131072));
    CHECK(!border_image_memory_fits(0x0c000000u,1));
    printf("border_image: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
