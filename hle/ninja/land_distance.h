/* Opt-in whole static LAND distance policy. Part of sa1-psp (MIT).
 * Read afresh, keep on uncertainty; this is a visual reduction, not culling parity. */
#ifndef SA1_LAND_DISTANCE_H
#define SA1_LAND_DISTANCE_H
#include <stdint.h>
#include <string.h>
#include <math.h>
typedef struct { uint32_t checked, cuts, scan, fallback; } land_distance_stats;
typedef const uint8_t *(*land_distance_reader)(uint32_t, uint32_t);
static inline int land_distance_parse(const char *s) {
    unsigned n=0;
    if (!s || !*s) return 0;
    for (; *s; s++) { if (*s<'0' || *s>'9' || n>100) return 0; n=n*10u+(unsigned)(*s-'0'); }
    return n>=1 && n<=100 ? (int)n : 0;
}
static inline int land_distance_span(uint32_t a,uint32_t n) {
    uint32_t segment=a>>29, physical=a&0x1fffffffu;
    return (segment==0 || segment==4 || segment==5) && !(a&3u) && n && n<=0x1000000u
        && physical>=0x0c000000u && physical-0x0c000000u<=0x1000000u-n;
}
static inline const uint8_t *ld_read(land_distance_reader read,uint32_t a,uint32_t n) {
    return land_distance_span(a,n) ? read(a,n) : NULL;
}
static inline uint32_t ld_u32(const void *p) { uint32_t n; memcpy(&n,p,4); return n; }
static inline uint16_t ld_u16(const void *p) { uint16_t n; memcpy(&n,p,2); return n; }
static inline float ld_f32(const void *p) { float n; memcpy(&n,p,4); return n; }
static inline int ld_finite(float n) { return isfinite(n) && fabsf(n)<=1.e16f; }
/* Validated static LAND eligibility and cap, independent of whole-model depth. */
static inline float land_distance_cap(land_distance_reader read,uint32_t model,const float b[4],const float m[16],int pct,land_distance_stats *st) {
    /* Default does not call the reader, even for malformed arguments. */
    if (pct>=100 || pct<1 || !read) return 0;
    st->checked++;
    const uint8_t *p=ld_read(read,0x8c7596f4u,4), *lt, *cols, *visible;
    if (!p || !(lt=ld_read(read,ld_u32(p),16))) goto keep;
    p=(ld_u16(lt+4)&4u) ? lt+8 : ld_read(read,0x8c88f614u,4);
    if (!p) goto keep;
    float far=ld_f32(p), cap=far*((float)pct/100.0f);
    if (!ld_finite(far) || !(far>0) || !ld_finite(cap) || !(cap>0)) goto keep;
    for (unsigned i=0;i<4;i++) if (!ld_finite(b[i])) goto keep;
    for (unsigned i=0;i<16;i++) if (!ld_finite(m[i])) goto keep;
    if (b[3]<0 || !land_distance_span(model,40)) goto keep;
    unsigned ncol=ld_u16(lt), nvis;
    uint32_t base=ld_u32(lt+12);
    if (!ncol || ncol>32767 || !(cols=ld_read(read,base,ncol*36u))) goto keep;
    p=ld_read(read,0x8c75a308u,4);
    if (!p || !(nvis=ld_u16(p)) || nvis>1024 || nvis>ncol || !(visible=ld_read(read,0x8c75a30cu,nvis*4u))) goto keep;
    int match=0;
    for (unsigned i=0;i<nvis;i++) {
        uint32_t a=ld_u32(visible+4u*i), physical=a&0x1fffffffu, start=base&0x1fffffffu;
        if (!land_distance_span(a,36) || physical<start || physical-start>=ncol*36u || (physical-start)%36u) goto keep;
        const uint8_t *col=cols+(physical-start), *obj=ld_read(read,ld_u32(col+24),8);
        if (!obj || !land_distance_span(ld_u32(obj+4),40)) goto keep;
        if ((ld_u32(obj+4)&0x1fffffffu)!=(model&0x1fffffffu)) continue;
        /* DRAWN, collision size, SOLID/WATER/FOOTPRINTS are static metadata.
         * MOVES, TURNED, FAR and every unknown bit still decline. */
        uint32_t flags=ld_u32(col+32);
        if (!(flags&0x80000000u) || (flags&~0xe0100003u)) goto keep;
        match=1;
    }
    if (!match) goto keep;
    return cap;
keep:
    st->fallback++; return 0;
}
/* Optional whole-point shortcut after the eligibility proof above. Partial
 * models retain the cap for backend cell/triangle clipping. */
static inline int land_distance_cut_at(land_distance_reader read,uint32_t model,const float b[4],const float m[16],float cap,land_distance_stats *st) {
    float a=m[2]*b[0], d=m[6]*b[1], e=m[10]*b[2];
    float z=(a+d)+(e+m[14]), radius=b[3]*(fabsf(m[2])+fabsf(m[6])+fabsf(m[10]));
    float margin=2.e-5f*(fabsf(a)+fabsf(d)+fabsf(e)+fabsf(m[14])+radius+cap+1.0f);
    if (!ld_finite(z) || !ld_finite(radius) || !ld_finite(margin) || !(z-radius>cap+margin)) goto keep;
    const uint8_t *p=ld_read(read,model,40);
    if (!p) goto keep;
    uint32_t n=ld_u32(p+8), padded=n+(n&1u);
    if (!n || n>65536 || !(p=ld_read(read,ld_u32(p),padded*12u))) goto keep;
    for (unsigned i=0;i<padded;i++,p+=12) {
        st->scan++;
        float x=ld_f32(p), y=ld_f32(p+4), q=ld_f32(p+8);
        if (!ld_finite(x) || !ld_finite(y) || !ld_finite(q)) goto keep;
        a=m[2]*x; d=m[6]*y; e=m[10]*q; z=(a+d)+(e+m[14]);
        margin=2.e-5f*(fabsf(a)+fabsf(d)+fabsf(e)+fabsf(m[14])+cap+1.0f);
        if (!ld_finite(a) || !ld_finite(d) || !ld_finite(e) || !ld_finite(z) || !ld_finite(margin) || !(z>cap+margin)) goto keep;
    }
    st->cuts++; return 1;
keep:
    st->fallback++; return 0;
}
static inline int land_distance_cut(land_distance_reader read,uint32_t model,const float b[4],const float m[16],int pct,land_distance_stats *st) {
    float cap=land_distance_cap(read,model,b,m,pct,st);
    return cap>0 ? land_distance_cut_at(read,model,b,m,cap,st) : 0;
}
#endif
