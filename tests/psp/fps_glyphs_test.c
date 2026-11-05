/* Synthetic font geometry only; no SDK font bytes or game data. MIT. */
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include "../../backend/psp/fps_glyphs.h"
static uint8_t font[256*8];
static unsigned checks;
#define CHECK(x) do { checks++; assert(x); } while(0)
static void pixels(unsigned char ch,const uint8_t rows[8]) {
 fps_rect r[FPS_RECTS_MAX];char text[2]={(char)ch,0};
 unsigned n=fps_glyph_rects(text,font,2,1,r,FPS_RECTS_MAX);
 CHECK(n>=1 && n<=33);
 CHECK(r[0].x0==0 && r[0].y0==0 && r[0].x1==10 && r[0].y1==10);
 CHECK(r[0].color==UINT32_C(0xa0000000));
 uint8_t canvas[8][7]={{0}};
 for(unsigned i=1;i<n;i++) {
  CHECK(r[i].color==UINT32_C(0xff40ff40));
  CHECK(r[i].x0>=2 && r[i].x1<=9 && r[i].x0<r[i].x1);
  CHECK(r[i].y0>=1 && r[i].y1<=9 && r[i].y1-r[i].y0==1);
  for(int x=r[i].x0-2;x<r[i].x1-2;x++){CHECK(!canvas[r[i].y0-1][x]);canvas[r[i].y0-1][x]=1;}
 }
 for(unsigned y=0;y<8;y++)for(unsigned x=0;x<7;x++)CHECK(canvas[y][x]==!!(rows[y]&(0x80u>>x)));
}
int main(void) {
 CHECK(FPS_RECTS_MAX==769);
 const uint8_t diagonal[8]={128,64,32,16,8,4,2,1};
 const uint8_t solid[8]={254,254,254,254,254,254,254,254};
 const uint8_t alternating[8]={170,170,170,170,170,170,170,170},blank[8]={0};
 memcpy(font+'A'*8,diagonal,8);memcpy(font+'B'*8,solid,8);
 memcpy(font+255*8,alternating,8);memcpy(font+'X'*8,alternating,8);
 pixels('A',diagonal);pixels('B',solid);pixels(255,alternating);pixels(' ',blank);pixels('?',blank);
 font['?'*8]=128;const uint8_t question[8]={128,0,0,0,0,0,0,0};pixels('?',question);
 struct {uint8_t before[16];fps_rect out[FPS_RECTS_MAX];uint8_t after[16];} guard;
 memset(&guard,165,sizeof guard);uint8_t saved[sizeof guard];memcpy(saved,&guard,sizeof guard);
 CHECK(fps_glyph_rects("A",font,2,1,NULL,769)==0);
 CHECK(fps_glyph_rects("A",NULL,2,1,guard.out,769)==0);
 CHECK(fps_glyph_rects("A",font,2,1,guard.out,0)==0);
 CHECK(fps_glyph_rects(NULL,font,2,1,guard.out,769)==0);
 CHECK(fps_glyph_rects("",font,2,1,guard.out,769)==0);CHECK(!memcmp(saved,&guard,sizeof guard));
 fps_rect expected[769];unsigned n=fps_glyph_rects("AB",font,2,1,expected,769);
 CHECK(n==16);CHECK(expected[0].x1==17 && expected[0].y1==10);
 for(unsigned cap=0;cap<n;cap++){CHECK(fps_glyph_rects("AB",font,2,1,guard.out,cap)==0);CHECK(!memcmp(saved,&guard,sizeof guard));}
 CHECK(fps_glyph_rects("AB",font,2,1,guard.out,n)==n);CHECK(!memcmp(expected,guard.out,n*sizeof *expected));
 CHECK(!memcmp(saved,&guard,16));CHECK(!memcmp(saved+sizeof guard-16,guard.after,16));
 CHECK(!memcmp(saved+16+n*sizeof *expected,(uint8_t *)guard.out+n*sizeof *expected,(769-n)*sizeof *expected));
 for(unsigned i=8;i<n;i++){CHECK(expected[i].x0==9 && expected[i].x1==16);CHECK(expected[i].y0==(int)i-7);}
 char bounded[24];memset(bounded,'X',24);
 memset(&guard,165,sizeof guard);memcpy(saved,&guard,sizeof guard);
 n=fps_glyph_rects(bounded,font,2,1,guard.out,769);
 CHECK(n==769);CHECK(guard.out[0].x1==171 && guard.out[0].y1==10);
 CHECK(!memcmp(saved,&guard,16));CHECK(!memcmp(saved+sizeof guard-16,guard.after,16));
 for(unsigned i=1;i<n;i++){
  fps_rect r=guard.out[i];int lx=r.x0-2;
  CHECK(lx>=0 && lx/7<24 && r.x1==r.x0+1);CHECK(lx%7==0 || lx%7==2 || lx%7==4 || lx%7==6);
  CHECK(r.y0>=1 && r.y0<=8 && r.y1==r.y0+1 && r.color==UINT32_C(0xff40ff40));
 }
 fps_rect longtext[769];CHECK(fps_glyph_rects("XXXXXXXXXXXXXXXXXXXXXXXXB",font,2,1,longtext,UINT_MAX)==769);
 CHECK(!memcmp(longtext,guard.out,sizeof longtext));
 for(unsigned cap=0;cap<769;cap++){
  memset(&guard,165,sizeof guard);memcpy(saved,&guard,sizeof guard);
  CHECK(fps_glyph_rects(bounded,font,2,1,guard.out,cap)==0);CHECK(!memcmp(saved,&guard,sizeof guard));
 }
 CHECK(fps_glyph_rects(" ",font,2,1,expected,1)==1);CHECK(expected[0].color==UINT32_C(0xa0000000));
 /* All byte indices, including final font byte255*8+7. Patterns synthetic. */
 for(unsigned ch=1;ch<256;ch++){
  uint8_t rows[8];for(unsigned y=0;y<8;y++)rows[y]=(uint8_t)(ch+17*y);
  memcpy(font+ch*8,rows,8);pixels((unsigned char)ch,rows);
 }
 memset(&guard,165,sizeof guard);memcpy(saved,&guard,sizeof guard);
 CHECK(fps_glyph_rects("A",font,INT_MAX,1,guard.out,769)==0);
 CHECK(fps_glyph_rects("A",font,2,INT_MAX,guard.out,769)==0);
 CHECK(fps_glyph_rects("A",font,INT_MIN,1,guard.out,769)==0);
 CHECK(fps_glyph_rects("A",font,2,INT_MIN,guard.out,769)==0);
 CHECK(fps_glyph_rects("A",font,INT16_MAX-7,1,guard.out,769)==0);
 CHECK(fps_glyph_rects("A",font,2,INT16_MAX-8,guard.out,769)==0);CHECK(!memcmp(saved,&guard,sizeof guard));
 CHECK(fps_glyph_rects("A",font,INT16_MIN+2,INT16_MIN+1,expected,769)>0);
 CHECK(fps_glyph_rects("A",font,INT16_MAX-8,INT16_MAX-9,expected,769)>0);
 printf("fps_glyphs_test: %u checks PASS\n",checks);return 0;
}
