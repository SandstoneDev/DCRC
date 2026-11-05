/* Synthetic far-plane tests, compiled by test_mesh_far.py with the actual
 * backend clip_plane/lerp routines. No game data. Part of sa1-psp (MIT). */
#include "../../backend/psp/mesh_far.h"
#include <stdio.h>
#include <string.h>
static unsigned checks,failures,emits;
static draw_vertex emitted[4][4]; static int lengths[4];
#define CHECK(q) do{checks++;if(!(q)){failures++;printf("FAIL %d: %s\n",__LINE__,#q);}}while(0)
static void capture(const draw_vertex *v,int n){CHECK(emits<4 && n>=3 && n<=4);if(emits<4){memcpy(emitted[emits],v,(size_t)n*sizeof *v);lengths[emits++]=n;}}
static float area(const draw_vertex *v){return (v[1].x-v[0].x)*(v[2].y-v[0].y)-(v[1].y-v[0].y)*(v[2].x-v[0].x);}
int main(void){
 float m[16]={0};m[0]=m[5]=m[11]=1;m[15]=10;
 float b[4]={0,0,0,1};CHECK(mesh_far_bound(m,b,20)==MESH_FAR_INSIDE);CHECK(mesh_far_bound(m,b,5)==MESH_FAR_OUT);
 CHECK(mesh_far_bound(m,b,10)==MESH_FAR_CROSS);CHECK(mesh_far_bound(m,b,0)==MESH_FAR_UNKNOWN);
 m[11]=NAN;CHECK(mesh_far_bound(m,b,10)==MESH_FAR_UNKNOWN);m[11]=1;
 b[3]=-1;CHECK(mesh_far_bound(m,b,10)==MESH_FAR_UNKNOWN);b[3]=1;
 draw_vertex v[4]={{0,0,.2f,0,0,0xff000000,0xff000000},{2,0,.2f,1,0,0xffffffff,0xffffffff},{0,2,.2f,0,1,0xff808080,0xff808080},{2,2,.2f,1,1,0xffffffff,0xffffffff}};
 emits=0;CHECK(!mesh_far_emit(v,4,10,clip_far_plane,capture));CHECK(emits==1&&lengths[0]==4&&!memcmp(v,emitted[0],sizeof v));
 emits=0;CHECK(!mesh_far_emit(v,4,0,clip_far_plane,capture));CHECK(emits==1&&!memcmp(v,emitted[0],sizeof v));
 emits=0;CHECK(!mesh_far_emit(v,4,NAN,clip_far_plane,capture));CHECK(emits==1&&!memcmp(v,emitted[0],sizeof v));
 for(int i=0;i<4;i++)v[i].w=.1f;
 emits=0;CHECK(!mesh_far_emit(v,4,10,clip_far_plane,capture));CHECK(emits==1&&!memcmp(v,emitted[0],sizeof v)); /* boundary retained */
 for(int i=0;i<3;i++)v[i].w=.05f;
 emits=0;CHECK(mesh_far_emit(v,3,10,clip_far_plane,capture));CHECK(emits==0);
 v[0].w=.2f;v[1].w=.2f;v[2].w=.05f;
 emits=0;CHECK(mesh_far_emit(v,3,10,clip_far_plane,capture));CHECK(emits==1&&lengths[0]==4);
 for(int i=0;i<lengths[0];i++)CHECK(emitted[0][i].w>=.1f-1e-7f);
 CHECK(area(emitted[0])>0);
 /* Edge from v1(w=.2,u=1) to v2(w=.05,u=0): t=2/3,
  * perspective-correct u=(.2*(1-t))/.1=2/3, not linear1/3. */
 CHECK(fabsf(emitted[0][2].u-2.0f/3.0f)<1e-6f || fabsf(emitted[0][3].u-2.0f/3.0f)<1e-6f);
 /* GE Gouraud colors are screen-linear (PPSSPP Software/Rasterizer.cpp
  * flatColor0/color0Planes path), unlike perspective-correct texture UVs. */
 for(int i=0;i<lengths[0];i++)if(fabsf(emitted[0][i].u-2.0f/3.0f)<1e-6f)CHECK((emitted[0][i].color&255u)==170u&&emitted[0][i].ocolor==emitted[0][i].color);
 draw_vertex old_poly[4],new_poly[4];int old_n=clip_plane(v,3,old_poly,2,.1f,-1),new_n=clip_far_plane(v,3,new_poly,2,.1f,-1);
 CHECK(old_n==new_n && new_n==4);
 for(int i=0;i<new_n;i++)CHECK(!memcmp(&old_poly[i],&new_poly[i],5*sizeof(float))); /* geometry+UV byte-identical */
 v[0].w=.2f;v[1].w=.05f;v[2].w=.2f;v[3].w=.05f;
 emits=0;CHECK(mesh_far_emit(v,4,10,clip_far_plane,capture));CHECK(emits==2);
 for(unsigned k=0;k<emits;k++)CHECK(area(emitted[k])>0); /* odd strip triangle winding */
 v[0].w=NAN;emits=0;CHECK(!mesh_far_emit(v,4,10,clip_far_plane,capture));CHECK(emits==1&&!memcmp(v,emitted[0],sizeof v));
 /* Existing near clip followed by far plane preserves near vertices and
  * wound triangles even when near clipping first produces a quad. */
 draw_mesh_vertex a={0,0,.5f,0,0,0xff112233,0xff010203},d={2,0,5,1,0,0xff334455,0xff030405},e={0,2,20,0,1,0xff556677,0xff050607};
 m[15]=0;draw_vertex near[4];int n=draw_cpu_tri(m,&a,&d,&e,near);CHECK(n==4);
 emits=0;CHECK(mesh_far_emit(near,n,10,clip_far_plane,capture));CHECK(emits>0);
 int near_kept=0;for(unsigned k=0;k<emits;k++){CHECK(area(emitted[k])>0);for(int i=0;i<lengths[k];i++)near_kept|=emitted[k][i].w==1.0f;}CHECK(near_kept);
 for(unsigned k=0;k<emits;k++)for(int i=0;i<lengths[k];i++)CHECK(emitted[k][i].w>=.1f-1e-6f&&emitted[k][i].w<=1.0f+1e-6f);
 printf("mesh_far_test: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
