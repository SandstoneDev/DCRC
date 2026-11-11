/* Own optional border format and screen placement, MIT. No image content. */
#ifndef DCRC_BORDER_IMAGE_H
#define DCRC_BORDER_IMAGE_H
#include <stdint.h>
#define BORDER_IMAGE_MAGIC UINT32_C(0x31524244)
#define BORDER_IMAGE_BYTES UINT32_C(131072)
static inline uint32_t border_image_word(const uint8_t *p){
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static inline int border_image_header_valid(const uint8_t *p,unsigned n){
    return p&&n==16&&border_image_word(p)==BORDER_IMAGE_MAGIC&&
        border_image_word(p+4)==128&&border_image_word(p+8)==512&&border_image_word(p+12)==BORDER_IMAGE_BYTES;
}
static inline int border_image_memory_fits(uintptr_t p,uint32_t n){
    return p&&p<UINT32_C(0x0c000000)&&n<=UINT32_C(0x0c000000)-p;
}
static inline int border_image_visible(int wide,int headless,int ready){return !wide&&!headless&&ready;}
typedef struct {uint16_t u,v;uint32_t color;int16_t x,y,z,pad;} border_image_vertex;
static inline void border_image_vertices(border_image_vertex v[4]){
    v[0]=(border_image_vertex){0,0,UINT32_MAX,0,0,0,0};
    v[1]=(border_image_vertex){60,272,UINT32_MAX,60,272,0,0};
    v[2]=(border_image_vertex){64,0,UINT32_MAX,420,0,0,0};
    v[3]=(border_image_vertex){124,272,UINT32_MAX,480,272,0,0};
}
#endif
