/* Synthetic LAND distance contracts; no game data. Part of sa1-psp (MIT). */
#define SA1_WRAP_LAND_DISTANCE 1
#include "../../hle/ninja/native_land.c"
#include <stdarg.h>
static uint8_t ram[SA1_RAM_SIZE + SA1_RAM_EXTRA];
uint8_t *const sa1_ram = ram;
int hle_strict;
static unsigned checks, failures, reads, original_calls;
static int observed_cut;
static nl_model fixture;
static sh4_ctx ctx;
static float recorded_far;
static unsigned mesh_records, model_records;
static int fail_model_record, fail_mesh_reserve;
static uint32_t reserved_vertices, reserved_records;
static draw_mesh_vertex recorded_vertices[1];
#define CHECK(q) do { checks++; if (!(q)) { failures++; printf("FAIL line %d: %s\n", __LINE__, #q); } } while (0)
void sa1_log(const char *f, ...) { (void)f; }
uint64_t sa1_plat_time_us(void) { return 0; }
void draw_model_destroy(uint32_t h) { CHECK(0); }
int sa1_plat_file_size(const char *p,uint32_t *n) { CHECK(0); return -1; }
int sa1_plat_file_read(const char *p,uint32_t off,void *dst,uint32_t n) { CHECK(0); return -1; }
int draw_mesh_test(const float m[16],const float b[4]) { return 0; }
int draw_mesh_ge_whole(const float m[16],const float b[4]) { CHECK(0); return 0; }
uint32_t hle_frame_count(void) { return 0; }
int kamui_native_model_far(uint32_t handle,const float m[16],float far_cap,uint32_t *rec) {
    CHECK(handle==7); if (fail_model_record) return 0;
    recorded_far=far_cap; model_records++; *rec=0; return 1;
}
int kamui_native_reserve(uint32_t vertices,uint32_t records) { reserved_vertices=vertices; reserved_records=records; return !fail_mesh_reserve; }
draw_mesh_vertex *kamui_native_mesh_far(uint32_t nv,const float m[16],const float bound[4],const uint16_t *idx,uint32_t ni,uint32_t tag,float far_cap,uint32_t *rec) {
    CHECK(nv==1 && ni==3); recorded_far=far_cap; mesh_records++; *rec=0; return recorded_vertices;
}
static const uint8_t *reader(uint32_t a, uint32_t n) {
    reads++;
    return land_distance_span(a,n) ? ram + ((a & 0x1fffffffu)-0x0c000000u) : NULL;
}
static void w(uint32_t a,uint32_t v) { memcpy(ram+(a&0xffffffu),&v,4); }
static void f(uint32_t a,float v) { memcpy(ram+(a&0xffffffu),&v,4); }
void fn_8c051e56_orig(sh4_ctx *c) { original_calls++; observed_cut = distance_cut(c,&fixture); }
static int cut(void) { land_distance_stats z={0}; return land_distance_cut(reader,0x8c004000u,fixture.bound,ctx.xf,50,&z); }
static float cap(void) { land_distance_stats z={0}; return land_distance_cap(reader,0x8c004000u,fixture.bound,ctx.xf,33,&z); }
static void setup(void) {
    memset(ram,0,sizeof ram); memset(&ctx,0,sizeof ctx); memset(&fixture,0,sizeof fixture);
    fixture.model=0x0c004000u; fixture.conv=1; fixture.bound[2]=80; fixture.bound[3]=1;
    ctx.xf[0]=ctx.xf[5]=ctx.xf[10]=ctx.xf[15]=1;
    ctx.gbr=0x8c007000u;
    w(0x8c7596f4,0x8c001000); w(0x8c001000,2); w(0x8c00100c,0x8c002000);
    w(0x8c75a308,1); w(0x8c75a30c,0x8c002000);
    w(0x8c002018,0x8c003000); w(0x8c002020,0x80000000); w(0x8c003004,0x8c004000);
    w(0x8c004000,0x8c005000); w(0x8c004008,3); f(0x8c88f614,100);
    for(unsigned i=0;i<4;i++) f(0x8c005008+12*i,80);
    hle_strict=0; hle_land_distance_pct=50; distance_active=NULL; mode=1;
}
int main(void) {
    setup(); CHECK(cut());
    CHECK(cap()==33.0f); fixture.bound[2]=20; CHECK(cap()==33.0f); CHECK(!cut()); fixture.bound[2]=80;
    const uint32_t known[]={0x80000001u,0xc0000002u,0xa0100001u,0xe0100003u};
    for(unsigned i=0;i<sizeof known/sizeof *known;i++){w(0x8c002020,known[i]);CHECK(cap()==33.0f);CHECK(cut());}
    const uint32_t excluded[]={0,0x60000001u,0x88000001u,0x90000001u,0x80000020u,0x80200001u,0x80000004u};
    for(unsigned i=0;i<sizeof excluded/sizeof *excluded;i++){w(0x8c002020,excluded[i]);CHECK(cap()==0);}
    w(0x8c002020,0x80000000u);
    reads=0; land_distance_stats z={0}; CHECK(!land_distance_cut(reader,0,fixture.bound,ctx.xf,100,&z)); CHECK(reads==0);
    CHECK(land_distance_parse("50")==50); CHECK(land_distance_parse("1")==1); CHECK(land_distance_parse("100")==100);
    const char *bad[]={NULL,"","0","101","-1","50x"," 50","999999999999999999999"};
    for(unsigned i=0;i<sizeof bad/sizeof *bad;i++){CHECK(!native_land_set_distance(bad[i]));CHECK(hle_land_distance_pct==100);}
    CHECK(native_land_set_distance("050")); CHECK(hle_land_distance_pct==50);
    fixture.bound[3]=40; CHECK(!cut()); fixture.bound[3]=1;
    f(0x8c005008,49); CHECK(!cut()); f(0x8c005008,80);
    f(0x8c00502c,0); CHECK(!cut()); f(0x8c00502c,80); /* odd point padding */
    ctx.xf[14]=-40; CHECK(!cut()); ctx.xf[14]=0;
    ctx.xf[2]=NAN; CHECK(!cut()); ctx.xf[2]=0;
    f(0x8c005000,NAN); CHECK(!cut()); f(0x8c005000,0);
    f(0x8c88f614,NAN); CHECK(!cut()); f(0x8c88f614,100);
    f(0x8c88f614,0); CHECK(!cut()); f(0x8c88f614,-100); CHECK(!cut()); f(0x8c88f614,100);
    fixture.bound[3]=NAN; CHECK(!cut()); fixture.bound[3]=-1; CHECK(!cut()); fixture.bound[3]=1;
    ctx.xf[14]=INFINITY; CHECK(!cut()); ctx.xf[14]=0;
    w(0x8c001004,4); f(0x8c001008,200); CHECK(!cut()); f(0x8c001008,100); CHECK(cut()); w(0x8c001004,0);
    w(0x8c75a308,0); CHECK(!cut()); w(0x8c75a308,1025); CHECK(!cut()); w(0x8c75a308,3); CHECK(!cut()); w(0x8c75a308,1);
    w(0x8c75a30c,0x8c002001); CHECK(!cut()); w(0x8c75a30c,0x8c002048); CHECK(!cut()); w(0x8c75a30c,0x8c002000);
    w(0x8c002020,0x88000000); CHECK(!cut()); w(0x8c002020,0x80000020); CHECK(!cut()); w(0x8c002020,0x80000000);
    w(0x8c75a308,2); w(0x8c75a310,0x8c002024); w(0x8c00203c,0x8c003000); w(0x8c002044,0x88000000); CHECK(!cut());
    w(0x8c002044,0x80000000); CHECK(cut()); w(0x8c75a310,0x8cfffff0); CHECK(!cut()); w(0x8c75a308,1);
    w(0x8c003004,0x8c004100); CHECK(!cut()); w(0x8c003004,0x8c004000);
    w(0x8c004000,0x8cffffe0); CHECK(!cut()); w(0x8c004000,0x8c005000);
    w(0x8c004008,0xffffffff); CHECK(!cut()); w(0x8c004008,3);
    w(0x8c00100c,0x8cfffff0); CHECK(!cut()); w(0x8c00100c,0x8c002000);
    w(0x8c001000,0); CHECK(!cut()); w(0x8c001000,2);
    w(0x8c002018,0x8cffffff); CHECK(!cut()); w(0x8c002018,0x8c003000);
    w(0x8c003004,0xac004000); CHECK(cut()); w(0x8c003004,0x8c004000);
    fixture.bound[2]=50.0001f; CHECK(!cut()); fixture.bound[2]=80;
    CHECK(!distance_cut(&ctx,&fixture)); fn_8c051e56(&ctx); CHECK(observed_cut); CHECK(distance_active==NULL);
    fixture.alpha=1; fn_8c051e56(&ctx); CHECK(!observed_cut); fixture.alpha=0;
    fixture.mixed=1; fn_8c051e56(&ctx); CHECK(!observed_cut); fixture.mixed=0;
    fixture.conv=0; fn_8c051e56(&ctx); CHECK(!observed_cut); fixture.conv=1;
    w(0x8c8ffe1c,1); w(0x8c8ffe24,0x00100000); fn_8c051e56(&ctx); CHECK(!observed_cut);
    w(0x8c8ffe24,0x00400000); fn_8c051e56(&ctx); CHECK(!observed_cut);
    w(0x8c8ffe24,0); fn_8c051e56(&ctx); CHECK(observed_cut);
    w(0x8c8ffe20,0xffffffff); w(0x8c8ffe24,0x2000); fn_8c051e56(&ctx); CHECK(observed_cut); /* observed ordinary LAND */
    w(0x8c8ffe24,0x00500000); fn_8c051e56(&ctx); CHECK(!observed_cut);
    w(0x8c8ffe1c,0); fn_8c051e56(&ctx); CHECK(observed_cut); /* disabled OR does not apply */
    mode=0; fn_8c051e56(&ctx); CHECK(!observed_cut); mode=1;
    sh4_ctx other={0}; distance_active=&other; CHECK(!distance_cut(&ctx,&fixture));
    fn_8c051e56(&ctx); CHECK(observed_cut); CHECK(distance_active==&other); distance_active=NULL;
    hle_strict=1; fn_8c051e56(&ctx); CHECK(!observed_cut); hle_strict=0;
    hle_land_distance_pct=100; fn_8c051e56(&ctx); CHECK(!observed_cut); CHECK(original_calls==14);
    setup(); fixture.bound[2]=20; distance_active=&ctx;
    CHECK(!distance_cut(&ctx,&fixture)); CHECK(dec_far==50.0f); /* partial model keeps cap */
    nl_var variant={0}; nl_set set={0}; nl_vert vert={0}; uint16_t ix[3]={0}; uint32_t end;
    variant.handle=7; set.nat=1; set.vcount=1; set.icount=3;
    fixture.sets=&set; fixture.nset=1; fixture.sv=&vert; fixture.six=ix;
    uint8_t zero=0; draw_state state={0}; fixture.zoff=&zero; variant.st=&state;
    L.models=&fixture; dec=&fixture; dvar=&variant; dec_kind=DEC_SETS;
    CHECK(native_land_set(&ctx,fixture.model,0,0x8c006000u,&end)); CHECK(mesh_records==1); CHECK(recorded_far==50.0f); CHECK(end==0x8c006020u);
    dec_kind=DEC_MODEL; dec_marked=0;
    CHECK(kamui_native_model_far(variant.handle,dec_m,dec_far,&dec_record));
    CHECK(native_land_set(&ctx,fixture.model,0,0x8c006000u,&end)); CHECK(model_records==1); CHECK(recorded_far==50.0f);
    dec_marked=0; dec_far=0;
    CHECK(kamui_native_model_far(variant.handle,dec_m,dec_far,&dec_record));
    CHECK(native_land_set(&ctx,fixture.model,0,0x8c006000u,&end)); CHECK(recorded_far==0); /* unqualified/default record */
    CHECK(!native_land_set(&ctx,0x0c004100u,0,0x8c006000u,&end)); CHECK(model_records==2);
    dec_far=50; native_land_window=0; CHECK(!native_land_decide(&ctx,fixture.model)); CHECK(dec_far==0); CHECK(dec==NULL);
    L.lt=0x8c001000u; L.nmodels=1; L.lo=L.hi=fixture.model;
    nl_set two_sets[2]={set,set}; two_sets[1].vcount=2; fixture.sets=two_sets; fixture.nset=fixture.ngroup=2;
    w(0x8c00400c,0x8c008000); w(0x8c004010,0x8c009000); /* two plain opaque materials */
    uint32_t tex_key[4]={0}; variant.tex=tex_key; fixture.var=&variant; fixture.nvar=1; nopersist=1; native_land_window=1;
    CHECK(native_land_decide(&ctx,fixture.model)); CHECK(dec_far==50.0f); CHECK(dec_kind==DEC_MODEL);
    CHECK(!native_land_decide(&ctx,0x0c004100u)); CHECK(dec_far==0); CHECK(dec==NULL);
    hle_strict=1; CHECK(native_land_decide(&ctx,fixture.model)); CHECK(dec_far==0); hle_strict=0;
    hle_land_distance_pct=100; CHECK(native_land_decide(&ctx,fixture.model)); CHECK(dec_far==0);
    hle_land_distance_pct=50; distance_active=NULL; CHECK(native_land_decide(&ctx,fixture.model)); CHECK(dec_far==0);
    distance_active=&ctx; fixture.alpha=1; CHECK(native_land_decide(&ctx,fixture.model)); CHECK(dec_far==0); fixture.alpha=0;
    fixture.mixed=1; CHECK(!native_land_decide(&ctx,fixture.model)); CHECK(dec_far==0); fixture.mixed=0;
    uint32_t rejected_before=capture_reject, ta_before=st.ta_other;
    fail_model_record=1; CHECK(!native_land_decide(&ctx,fixture.model)); CHECK(dec==NULL); CHECK(dvar==NULL); CHECK(dec_kind==DEC_NONE); fail_model_record=0;
    variant.handle=0; fail_mesh_reserve=1; CHECK(!native_land_decide(&ctx,fixture.model)); CHECK(dec==NULL); CHECK(dvar==NULL); CHECK(dec_kind==DEC_NONE); fail_mesh_reserve=0;
    CHECK(reserved_vertices==3 && reserved_records==2); CHECK(native_land_decide(&ctx,fixture.model)); CHECK(dec_kind==DEC_SETS); CHECK(dec_far==50.0f);
    hle_land_distance_pct=100; fail_mesh_reserve=1; CHECK(!native_land_decide(&ctx,fixture.model)); CHECK(dec==NULL && dvar==NULL && dec_far==0); fail_mesh_reserve=0;
    variant.handle=7; fail_model_record=1; CHECK(!native_land_decide(&ctx,fixture.model)); CHECK(dec==NULL && dvar==NULL && dec_far==0); fail_model_record=0;
    CHECK(capture_reject-rejected_before==4); CHECK(st.ta_other-ta_before==4);
    L.models=NULL;
    CHECK(!land_distance_span(0x2c001000,4)); CHECK(!land_distance_span(0x8d000000,4)); CHECK(!land_distance_span(0x8cffffff,4));
    CHECK(land_distance_span(0xac001000,4)); CHECK(land_distance_span(0x0c001000,4));
    printf("land_distance_test: %u checks, %u failures\n",checks,failures); return failures?1:0;
}
