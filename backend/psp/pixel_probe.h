/* Diagnostic screen-space barycentrics, independent of SDK/game bytes. MIT. */
#pragma once
#include <math.h>
static inline int pixel_probe_weights(float x,float y,const float p[6],float out[3]) {
    if (!isfinite(x)||!isfinite(y)) return 0;
    for(int i=0;i<6;i++) if(!isfinite(p[i])) return 0;
    float d=(p[3]-p[5])*(p[0]-p[4])+(p[4]-p[2])*(p[1]-p[5]);
    if (!isfinite(d)||fabsf(d)<1.e-8f) return 0;
    float a=((p[3]-p[5])*(x-p[4])+(p[4]-p[2])*(y-p[5]))/d;
    float b=((p[5]-p[1])*(x-p[4])+(p[0]-p[4])*(y-p[5]))/d;
    float c=1.0f-a-b;
    if(!isfinite(a)||!isfinite(b)||!isfinite(c)||a<0||b<0||c<0) return 0;
    out[0]=a;out[1]=b;out[2]=c;return 1;
}
