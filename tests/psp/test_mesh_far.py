#!/usr/bin/env python3
"""Host far-plane proof using actual PSP clip functions. MIT; no game data."""
from pathlib import Path
import subprocess
import re
import argparse

ROOT = Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,default=ROOT/'backend/psp/draw_gu.c')
parser.add_argument('--header',type=Path,default=ROOT/'backend/psp/mesh_far.h')
parser.add_argument('--out',type=Path,default=ROOT/'work/C84_far')
args=parser.parse_args()
OUT = args.out
OUT.mkdir(parents=True, exist_ok=True)
source = args.source.read_text()

def extract(name):
    match=re.search(r'(?m)^[^\n;{}]*\b'+name+r'\([^;{}]*\)\s*\{',source)
    if not match:
        raise RuntimeError("missing function " + name)
    start=match.start()
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]

common='#include "' + (ROOT / 'backend/draw.h').as_posix() + '"\n'
common+='\n'.join(extract(n) for n in ('vtx_copy','lerp_chan','lerp_color','lerp_vertex'))
common+='\n'+extract('clip_far_plane')
pure_test=(ROOT/'tests/psp/mesh_far_test.c').read_text().replace('../../backend/psp/mesh_far.h',args.header.as_posix())
pure=common+'\n'+extract('clip_plane')+'\n'+pure_test
backend_prefix=r'''
#include <stdio.h>
#include <string.h>
typedef struct { float x,y,z,w; } Vec;
typedef struct { Vec x,y,z,w; } ScePspFMatrix4;
typedef struct { float u,v; uint32_t color; float x,y,z; } gu_vtx;
typedef struct { uint32_t color; float x,y,z; } gu_ovtx;
typedef struct { draw_state st; uint32_t vfirst,vcount,ifirst,icount; int off; uint32_t sp0,sp1; } gmset;
typedef struct { gmset *sets; int nsets; gu_vtx *v; gu_ovtx *ov; uint16_t *ix; uint32_t *col; draw_model_cell *cells; draw_model_span *spans; int ncells,nspans,dying; float bound[4]; } gmodel;
#define GMODEL_MAX 4
#define GMODEL_CELL_MAX 8
#define MESH_MAT_MAX 32
#define ITEM_MAX 32
#define TEX_MAX 8
#define PASSES 2
#define PASS_FAR 0
#define PASS_NEAR 1
#define PROJ_3D 1
#define GU_TRIANGLES 4
typedef struct { uint16_t state;uint8_t proj,prim;uint16_t n,on;void *v,*ov;const void *ix;int16_t mat; } gu_item;
static gu_item items[PASSES][ITEM_MAX];static int nitems[PASSES],nmesh_mats,nrstates,cur_proj;
static ScePspFMatrix4 mesh_mats[MESH_MAT_MAX];static uint8_t cell_cls[GMODEL_CELL_MAX];
static gmodel gmodels[GMODEL_MAX];static struct {uint32_t draws;}gms;
static struct {uint32_t dropped;}gs;static draw_stats stats;static draw_cell_stats cst;
static struct {uint32_t whole_out,cell_out,cpu_clipped;}far_stats;
static struct {int pblk;}texs[TEX_MAX];static draw_state cur;static int cur_valid,list_open,headless;
static float depth_split,depth_zn;static int ge_cells,depth_floor;
static unsigned original_mesh,original_model,emits,checks,failures;static draw_vertex output[32][4];static int lengths[32];
#define CHECK(q) do{checks++;if(!(q)){failures++;printf("FAIL backend %d: %s\n",__LINE__,#q);}}while(0)
static int list_full(void){return 0;}static void batch_flush(void){}static void texpool_touch(int b){(void)b;}
void draw_strip(const draw_vertex*v,int n){CHECK(emits<32&&n>=3&&n<=4);if(emits<32){memcpy(output[emits],v,(size_t)n*sizeof*v);lengths[emits++]=n;}}
void draw_set_state(const draw_state*s){cur=*s;cur_valid=1;nrstates=1;}
void draw_mesh(const float m[16],const float b[4],const draw_mesh_vertex*v,int nv,const uint16_t*ix,int ni){(void)m;(void)b;(void)v;(void)nv;(void)ix;(void)ni;original_mesh++;}
int draw_model(uint32_t h,const float m[16]){(void)h;(void)m;original_model++;return 42;}
'''
backend_suffix=r'''
static gu_vtx vertices[9];static uint16_t indices[9];static uint32_t colours[18];static gmset sets[1];static draw_model_cell cells[3];static draw_model_span spans[3];
static void flat_output(unsigned which,uint32_t color,uint32_t offset){
 CHECK(which<emits);if(which<emits)for(int i=0;i<lengths[which];i++){CHECK(output[which][i].color==color);CHECK(output[which][i].ocolor==offset);}
}
static void setup(float*m){
 memset(m,0,16*sizeof*m);m[0]=m[5]=m[11]=1;m[8]=320;m[9]=240;
 memset(gmodels,0,sizeof gmodels);memset(items,0,sizeof items);memset(nitems,0,sizeof nitems);memset(&far_stats,0,sizeof far_stats);memset(&cst,0,sizeof cst);memset(sets,0,sizeof sets);
 original_mesh=original_model=emits=0;cur_valid=list_open=1;headless=0;cur=(draw_state){0};cur.layer=DRAW_LAYER_3D;
 depth_zn=1;depth_split=16;ge_cells=1;depth_floor=4400;nmesh_mats=0;nrstates=1;sets[0].st=cur;sets[0].vcount=9;sets[0].icount=9;sets[0].sp1=3;
 for(int i=0;i<9;i++){indices[i]=(uint16_t)i;vertices[i]=(gu_vtx){.u=(float)(i%3),.v=0,.color=0xff332211,.x=(float)(i%3==1),.y=(float)(i%3==2),.z=i<3?5:i<6?10:20};colours[2*i]=0xff112233;colours[2*i+1]=0;}
 vertices[3].z=8;vertices[4].z=8;vertices[5].z=12;
 for(int i=0;i<3;i++){cells[i]=(draw_model_cell){{0,0,i==0?5:i==1?10:20,i==1?3:.1f},0};spans[i]=(draw_model_span){(uint32_t)(3*i),3,(uint16_t)i,0};}
 gmodels[1]=(gmodel){.sets=sets,.nsets=1,.v=vertices,.ix=indices,.col=colours,.cells=cells,.spans=spans,.ncells=3,.nspans=3,.bound={0,0,10,15}};
}
int main(void){
 float m[16];setup(m);draw_mesh_vertex v[3]={{0,0,8,0,0,0xff112233,0},{1,0,8,1,0,0xff112233,0},{0,1,12,0,1,0xff112233,0}};uint16_t ix[3]={0,1,2};float inside[4]={0,0,5,.1f},outside[4]={0,0,20,.1f},cross[4]={0,0,10,3};
 draw_mesh_far(m,inside,v,3,ix,3,0);CHECK(original_mesh==1&&emits==0);
 draw_mesh_far(m,inside,v,3,ix,3,NAN);CHECK(original_mesh==2&&emits==0);
 draw_mesh_far(m,inside,v,3,ix,3,10);CHECK(original_mesh==3&&emits==0);
 draw_mesh_far(m,outside,v,3,ix,3,10);CHECK(original_mesh==3&&emits==0&&far_stats.whole_out==1);
 draw_mesh_far(m,cross,v,3,ix,3,10);CHECK(emits==1&&lengths[0]==4);
 setup(m);CHECK(draw_model_far(1,m,0)==42&&original_model==1);CHECK(draw_model_far(1,m,NAN)==42&&original_model==2);
 memcpy(gmodels[1].bound,inside,sizeof inside);CHECK(draw_model_far(1,m,10)==42&&original_model==3);
 memcpy(gmodels[1].bound,outside,sizeof outside);CHECK(draw_model_far(1,m,10)==1&&original_model==3&&far_stats.whole_out==1);
 setup(m);CHECK(draw_model_far(1,m,10)==1);CHECK(far_stats.cell_out==1&&far_stats.cpu_clipped==1);
 CHECK(nitems[PASS_NEAR]==1&&items[PASS_NEAR][0].n==3);CHECK(emits==1&&lengths[0]==4);CHECK(cur.layer==DRAW_LAYER_3D);
 for(unsigned k=0;k<emits;k++)for(int i=0;i<lengths[k];i++)CHECK(output[k][i].w>=.1f-1e-6f);
 setup(m);cells[1].bound[0]=100000;CHECK(draw_model_far(1,m,10)==1);CHECK(emits==0&&far_stats.cpu_clipped==0&&far_stats.cell_out==1); /* view OUT stays OUT, never forced CPU */
 setup(m);CHECK(model_cells(&gmodels[1],m,0)==1);CHECK(nitems[PASS_NEAR]==1&&items[PASS_NEAR][0].n==6);CHECK(nitems[PASS_FAR]==1&&items[PASS_FAR][0].n==3);CHECK(emits==0&&far_stats.cell_out==0&&far_stats.cpu_clipped==0);
 setup(m);gmodels[1].ncells=0;gmodels[1].col=NULL;CHECK(draw_model_far(1,m,10)==1);CHECK(original_model==0&&emits==2);CHECK(output[0][0].color==0xff112233);
 setup(m);gmodels[1].ncells=0;gmodels[1].col=NULL;sets[0].st.use_alpha=1;sets[0].st.blend_dst=DRAW_BLEND_INV_SRC_ALPHA;
 CHECK(draw_model_far(1,m,10)==42&&original_model==1&&emits==0);
 setup(m);m[3]=NAN;CHECK(draw_model_far(1,m,10)==42&&original_model==1);draw_mesh_far(m,cross,v,3,ix,3,10);CHECK(original_mesh==1);
 /* Flat GE triangles use original indexed vertex2 as provoking vertex;
  * clipping must preserve both colors even if that vertex is removed. */
 setup(m);cur.texture=1;for(int i=0;i<3;i++){v[i].color=0xff000001u+(uint32_t)(i*16);v[i].ocolor=0xff010101u+(uint32_t)i;}
 draw_mesh_far(m,cross,v,3,ix,3,10);CHECK(emits==1);flat_output(0,v[2].color,v[2].ocolor);
 setup(m);cur.texture=1;v[0].z=.5f;draw_mesh_far(m,cross,v,3,ix,3,10);CHECK(emits>0);for(unsigned k=0;k<emits;k++)flat_output(k,v[2].color,v[2].ocolor);v[0].z=8;
 setup(m);sets[0].st.texture=1;for(int i=0;i<9;i++){colours[2*i]=0xff112200u+(uint32_t)i;colours[2*i+1]=0xff223300u+(uint32_t)i;}
 CHECK(draw_model_far(1,m,10)==1);CHECK(emits==1);flat_output(0,colours[10],colours[11]);
 setup(m);sets[0].st.texture=1;gmodels[1].ncells=0;for(int i=0;i<9;i++){colours[2*i]=0xff112200u+(uint32_t)i;colours[2*i+1]=0xff223300u+(uint32_t)i;}
 CHECK(draw_model_far(1,m,10)==1);CHECK(emits==2);flat_output(0,colours[4],colours[5]);flat_output(1,colours[10],colours[11]);
 setup(m);gmodels[1].ncells=0;gmodels[1].col=NULL;gu_ovtx offsets[9];gmodels[1].ov=offsets;sets[0].st.texture=1;
 for(int i=0;i<9;i++){vertices[i].color=0xff112200u+(uint32_t)i;offsets[i].color=0xff223300u+(uint32_t)i;}
 CHECK(draw_model_far(1,m,10)==1);CHECK(emits==2);flat_output(0,argb_abgr(vertices[2].color),argb_abgr(offsets[2].color));flat_output(1,argb_abgr(vertices[5].color),argb_abgr(offsets[5].color));
 setup(m);cur.gouraud=1;cur.texture=1;v[0].z=v[1].z=5;v[2].z=20;v[1].color=0xffffffff;v[2].color=0xff000000;v[1].ocolor=0xff000000;v[2].ocolor=0xffffffff;
 draw_mesh_far(m,cross,v,3,ix,3,10);CHECK(emits==1);int found=0;
 for(int k=0;k<lengths[0];k++){if(fabsf(output[0][k].u-2.0f/3.0f)<1e-6f){CHECK((output[0][k].color&255u)==85u);CHECK((output[0][k].ocolor&255u)==170u);found=1;}}
 CHECK(found);
 /* Untextured GE stores saturated base+offset BEFORE interpolation. */
 setup(m);cur.gouraud=1;
 for(int i=0;i<3;i++){v[i].color=i==2?0xff000000:0xffc8c8c8;v[i].ocolor=i==2?0:0xff646464;}
 draw_mesh_far(m,cross,v,3,ix,3,8);CHECK(emits==1);found=0;
 for(int k=0;k<lengths[0];k++){if(fabsf(output[0][k].w-.125f)<1e-6f){CHECK(output[0][k].color==0xff808080);CHECK(output[0][k].ocolor==0);found++;}}
 CHECK(found==2);
 setup(m);for(int i=0;i<3;i++){v[i].color=0xffc8c8c8;v[i].ocolor=0xff646464;}
 draw_mesh_far(m,cross,v,3,ix,3,8);CHECK(emits==1);flat_output(0,0xffffffff,0);
 for(int converted=0;converted<2;converted++){
  setup(m);gmodels[1].ncells=0;sets[0].icount=3;sets[0].st.gouraud=1;gmodels[1].col=converted?NULL:colours;
  for(int i=0;i<3;i++){vertices[i].z=i==2?20:5;vertices[i].color=i==2?0xff000000:0xffffffff;colours[2*i]=i==2?0xff000000:0xffc8c8c8;colours[2*i+1]=i==2?0:0xff646464;}
  CHECK(draw_model_far(1,m,8)==1);CHECK(emits==1);found=0;
  for(int k=0;k<lengths[0];k++){if(fabsf(output[0][k].w-.125f)<1e-6f){CHECK(output[0][k].color==0xff808080);CHECK(output[0][k].ocolor==0);found++;}}
  CHECK(found==2);
  emits=0;sets[0].st.gouraud=0;vertices[2].color=0xffffffff;colours[4]=0xffc8c8c8;colours[5]=0xff646464;
  CHECK(draw_model_far(1,m,8)==1);CHECK(emits==1);flat_output(0,0xffffffff,0);
 }
 /* A far0 CPU fallback retains its original raw color inputs. */
 setup(m);sets[0].icount=3;for(int i=0;i<3;i++){colours[2*i]=0xff112200u+(uint32_t)i;colours[2*i+1]=0xff223300u+(uint32_t)i;}
 model_cpu_tris(&gmodels[1],&sets[0],m,0,3,0);CHECK(emits==1&&lengths[0]==3);
 for(int i=0;i<3;i++){CHECK(output[0][i].color==colours[2*i]);CHECK(output[0][i].ocolor==colours[2*i+1]);}
 printf("mesh_far_backend: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
'''
backend=common+'\n#include "'+args.header.as_posix()+'"\n'+backend_prefix
backend+='\n'.join(extract(n) for n in ('argb_abgr','sat_add','cpu_tri_far','cpu_strip_far','draw_mesh_far','model_cpu_tris','model_cells','draw_model_far'))+backend_suffix
failed=False
for name,code in (('far_host',pure),('far_backend',backend)):
    file,exe=OUT/(name+'.c'),OUT/name
    file.write_text(code)
    build=subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-fno-strict-aliasing','-fsanitize=address,undefined',str(file),'-lm','-o',str(exe)],capture_output=True,text=True)
    output=build.stdout+build.stderr;rc=build.returncode
    if not rc:
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
        output+=run.stdout+run.stderr;rc=run.returncode
    print(output,end='');(OUT/(name+'.log')).write_text(output+f'exit={rc}\n');failed|=bool(rc)
raise SystemExit(1 if failed else 0)
