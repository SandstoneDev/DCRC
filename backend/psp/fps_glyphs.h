/* Pure bitmap-to-rectangle geometry; font bytes belong to caller. MIT. */
#pragma once
#include <stdint.h>
typedef struct fps_rect {int16_t x0,y0,x1,y1;uint32_t color;} fps_rect;
#define FPS_RECTS_MAX 769
/* font is a caller-owned 2048-byte table: 256 characters * 8 rows.
 * Each glyph uses bits 7..1, left to right, with advance7. Bit0 is ignored.
 * No font pixels are embedded here. Output is one translucent-black backdrop
 * and one green rectangle per contiguous horizontal ink run, height1.
 * Truncate text at24 bytes; empty/null input emits nothing. Count before
 * writing, so insufficient capacity or int16 overflow leaves output intact. */
static inline unsigned fps_glyph_rects(const char *text,const uint8_t *font,int x,int y,fps_rect *out,unsigned cap){
 if(!text || !font || !out || !cap) return 0;
 uint8_t rows[24][8];unsigned len=0;
 while(len<24 && text[len]){
  unsigned ch=(unsigned char)text[len];
  for(unsigned row=0;row<8;row++) rows[len][row]=font[8*ch+row];
  len++;
 }
 if(!len) return 0;
 int64_t left=(int64_t)x-2,top=(int64_t)y-1;
 int64_t right=(int64_t)x+7*len+1,bottom=(int64_t)y+9;
 if(left<INT16_MIN || right>INT16_MAX || top<INT16_MIN || bottom>INT16_MAX) return 0;
 unsigned needed=1;
 for(unsigned pass=0;pass<2;pass++){
  if(pass) out[0]=(fps_rect){(int16_t)left,(int16_t)top,(int16_t)right,(int16_t)bottom,UINT32_C(0xa0000000)};
  unsigned n=1;
  for(unsigned i=0;i<len;i++)for(unsigned row=0;row<8;row++)
   for(unsigned col=0;col<7;){
    if(!(rows[i][row]&(0x80u>>col))){col++;continue;}
    unsigned start=col++;
    while(col<7 && (rows[i][row]&(0x80u>>col)))col++;
    if(pass){
     int px=x+(int)(7*i+start),py=y+(int)row;
     out[n]=(fps_rect){(int16_t)px,(int16_t)py,(int16_t)(px+(int)(col-start)),(int16_t)(py+1),UINT32_C(0xff40ff40)};
    }
    n++;
   }
  if(!pass){needed=n;if(n>cap)return 0;}
 }
 return needed;
}
