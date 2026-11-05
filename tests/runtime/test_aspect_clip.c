#include "../../backend/aspect_clip.h"
#include <assert.h>
#include <string.h>
int main(void){
    float c[4]={0,0,639,479};assert(debug_aspect_clip(0,1,c));
    assert(c[0]==DRAW_WIDE_LEFT && c[2]==639-DRAW_WIDE_LEFT);
    assert(debug_aspect_clip(1,0,c));assert(c[0]==0&&c[2]==639);
    c[1]=5;float before[4];memcpy(before,c,sizeof c);
    assert(!debug_aspect_clip(0,1,c)&&!memcmp(c,before,sizeof c));
    return 0;
}
