/* Own movie presentation policy, MIT. No game code or asset bytes. */
#ifndef DCRC_MOVIE_LAYOUT_H
#define DCRC_MOVIE_LAYOUT_H
#include <stdint.h>
#define MOVIE_SLICES 16u
typedef struct {float u,v,x,y,z;} movie_sprite;
/* The decoder owns exactly512x272 pixels. Two legal POT images avoid claiming
 * 512x512 resident pixels or filtering across an unallocated final row. */
static inline unsigned movie_band_height(unsigned band){return band?16u:256u;}
static inline unsigned movie_band_offset(unsigned band){return band?512u*256u*2u:0u;}
static inline int movie_band_vertices(movie_sprite *v,int wide,unsigned band){
    if(!v||band>1)return 0;
    float left=wide?0.0f:60.0f,width=wide?480.0f:360.0f;
    float u0=wide?60.5f:60.0f,uw=wide?359.0f:360.0f;
    float top=band?256.0f:0.0f,height=(float)movie_band_height(band);
    for(unsigned i=0;i<MOVIE_SLICES;i++){
        float a=(float)i/MOVIE_SLICES,b=(float)(i+1)/MOVIE_SLICES;
        v[2*i]=(movie_sprite){u0+uw*a,0,left+width*a,top,0};
        v[2*i+1]=(movie_sprite){u0+uw*b,height,left+width*b,top+height,0};
    }
    return 1;
}
#endif
