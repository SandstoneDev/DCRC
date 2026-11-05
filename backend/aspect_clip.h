/* Only the ordinary full screen clip is eligible for live aspect changes. MIT. */
#pragma once
#include "draw.h"
static inline int debug_aspect_clip(int old_wide,int new_wide,float clip[4]){
    float old_left=old_wide?DRAW_WIDE_LEFT:0.0f;
    if(clip[0]!=old_left || clip[1]!=0.0f || clip[2]!=639.0f-old_left || clip[3]!=479.0f)return 0;
    float new_left=new_wide?DRAW_WIDE_LEFT:0.0f;
    clip[0]=new_left;clip[2]=639.0f-new_left;return 1;
}
