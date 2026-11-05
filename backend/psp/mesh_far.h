/* Explicit quality far plane for native static LAND. Pure policy; MIT. */
#pragma once
#include "../draw.h"
#include <math.h>

enum { MESH_FAR_UNKNOWN=-1, MESH_FAR_INSIDE, MESH_FAR_OUT, MESH_FAR_CROSS };
static inline int mesh_far_valid(float far) { return isfinite(far) && far>0.0f && isfinite(1.0f/far); }
static inline int mesh_far_bound(const float *m,const float *b,float far) {
    if (!mesh_far_valid(far)) return MESH_FAR_UNKNOWN;
    for (int i=0;i<16;i++) if (!isfinite(m[i])) return MESH_FAR_UNKNOWN;
    for (int i=0;i<4;i++) if (!isfinite(b[i])) return MESH_FAR_UNKNOWN;
    if (b[3]<0) return MESH_FAR_UNKNOWN;
    float a=m[3]*b[0],c=m[7]*b[1],d=m[11]*b[2];
    float z=(a+c)+(d+m[15]);
    /* L1 bounds the transformed sphere radius without a square root. */
    float r=b[3]*(fabsf(m[3])+fabsf(m[7])+fabsf(m[11]));
    float margin=2.e-5f*(fabsf(a)+fabsf(c)+fabsf(d)+fabsf(m[15])+r+far+1.0f);
    if (!isfinite(z)||!isfinite(r)||!isfinite(margin)) return MESH_FAR_UNKNOWN;
    if (z+r<far-margin) return MESH_FAR_INSIDE;
    if (z-r>far+margin) return MESH_FAR_OUT;
    return MESH_FAR_CROSS;
}
typedef int (*mesh_far_clipper)(const draw_vertex *,int,draw_vertex *,int,float,float);
typedef void (*mesh_far_writer)(const draw_vertex *,int);
/* draw_cpu_tri produces a 3/4 vertex strip. All inside/unknown is passed
 * byte-for-byte. Crossers use the backend's existing perspective lerp. */
static inline int mesh_far_emit(const draw_vertex *v,int n,float far,mesh_far_clipper clip,mesh_far_writer emit) {
    if (!mesh_far_valid(far) || n<3 || n>4) { emit(v,n); return 0; }
    float w=1.0f/far; int inside=1;
    for (int i=0;i<n;i++) {
        if (!isfinite(v[i].x)||!isfinite(v[i].y)||!isfinite(v[i].w)||!(v[i].w>0)||!isfinite(v[i].u)||!isfinite(v[i].v)) { emit(v,n); return 0; }
        inside &= v[i].w>=w;
    }
    if (inside) { emit(v,n); return 0; }
    for (int i=0;i+2<n;i++) {
        draw_vertex tri[3]={v[(i&1)?i+1:i],v[(i&1)?i:i+1],v[i+2]}, poly[4];
        int k=clip(tri,3,poly,2,w,-1.0f);
        if (k<0) emit(tri,3);
        else if (k==3) emit(poly,3);
        else if (k==4) { draw_vertex strip[4]={poly[0],poly[1],poly[3],poly[2]}; emit(strip,4); }
    }
    return 1;
}
