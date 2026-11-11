/* Own Ninja screen-print adapter. MIT, Copyright (c) 2026 SandstoneDev.
 * ABI/layout facts: original US1.005 print entries and public Ninja/Kamui
 * declarations. No SDK implementation or atlas pixels are embedded here.
 * The default atlas is read from the player's loaded image, then owned by
 * the raw UI service independently of ordinary texlists.
 */
#include "ninja.h"
#include "print.h"
#include <string.h>

#define PRINT_COLOR   0x8c89055cu
#define PRINT_SCALE   0x8c890560u
#define PRINT_SURFACE 0x8c890564u
#define PRINT_TCW     0x8c89058cu
#define PRINT_TSP     0x8c890590u
#define PRINT_PCW     0x8c890594u
#define PRINT_ISP     0x8c890598u
#define PRINT_ATLAS   0x8c673d94u
#define STRIP_POINTER 0x8c88fcb4u
static uint32_t print_token;

void ninja_print_reset(void) { texture_raw_release(print_token);print_token=0; }

/* njInitPrint(texture,size,type). Default atlas:128x128 twiddled1555.
 * Publish only after allocation and UI retention succeed; a failed re-init
 * keeps the previous atlas, scale, colour and header available to callers. */
void sdk_8c6406ac(sh4_ctx *c) {
    HLE_ENTER(0x8c6406acu,"njInitPrint");
    uint32_t source=ARG0?ARG0:PRINT_ATLAS,size=ARG0?ARG1:128u,type=ARG0?ARG2:0x100u;
    uint32_t sh=hle_rd32(STRIP_POINTER),physical=sh&0x1fffffffu;
    texture_raw_ref ref;
    if(!hle_in_ram(sh) || physical<0x0c000000u || physical>0x0d200000u-256u ||
       !texture_raw_acquire(source,size,size,type,"ninja_print",&ref)) {
        sa1_log("njInitPrint: atlas unavailable; previous owner retained");RET(-1);return;
    }
    /* The SDK's public surface mirror remains meaningful to guest readers;
     * physical texture addresses, as elsewhere in this HLE, encode a handle. */
    uint32_t fmt=type&255u,handle=ref.tcw&0x1fffffu;
    const uint32_t surface[10]={2,1,fmt<<27,size,size,size*size*2u,
        type>>8==1?4u:0u,handle*8u,0xa4000000u|handle*8u,0x04000000u|handle*8u};
    for(unsigned i=0;i<10;i++)hle_wr32(PRINT_SURFACE+i*4u,surface[i]);
    hle_wr32(PRINT_COLOR,0xffbfbfbfu);hle_wrf(PRINT_SCALE,8.0f);
    hle_wr32(sh,0x00600608u);hle_wr32(sh+4,0);hle_wr32(sh+8,2);hle_wr32(sh+12,0);
    hle_wr32(sh+32,2);hle_wr32(sh+64,0);hle_wr32(sh+68,1);hle_wr32(sh+108,PRINT_SURFACE);
    kamui_commit_strip_head(sh);
    /* Packed colour belongs to this print contract. The current HLE's
     * internal colour/modifier field can otherwise retain another draw's value. */
    uint32_t pcw=hle_rd32(sh+0x90)&~0x30u;
    uint32_t tsp=(hle_rd32(sh+0x98)&~63u)|ref.tsp;
    hle_wr32(sh+0x90,pcw);hle_wr32(sh+0x98,tsp);hle_wr32(sh+0x9c,ref.tcw);
    hle_wr32(PRINT_PCW,pcw);hle_wr32(PRINT_ISP,hle_rd32(sh+0x94));
    hle_wr32(PRINT_TSP,tsp);hle_wr32(PRINT_TCW,ref.tcw);
    uint32_t previous=print_token;print_token=ref.token;texture_raw_release(previous);
}
void sdk_8c640752(sh4_ctx *c) {
    HLE_ENTER(0x8c640752u,"njExitPrint");(void)c;ninja_print_reset();
}
void sdk_8c64075a(sh4_ctx *c) {
    HLE_ENTER(0x8c64075au,"njPrintSize");hle_wrf(PRINT_SCALE,(float)(uint16_t)ARG0);
}
void sdk_8c640766(sh4_ctx *c) {
    HLE_ENTER(0x8c640766u,"njPrintColor");hle_wr32(PRINT_COLOR,ARG0);
}

/* Binary digits, most significant requested bit first, using SH4 SHLD count
 * semantics. Coordinates are signed16 character cells; size changes
 * both the cell spacing and the glyph's square screen extent. */
void sdk_8c640ce8(sh4_ctx *c) {
    HLE_ENTER(0x8c640ce8u,"njPrintB");
    texture_raw_ref ref;
    int32_t digits=(int32_t)ARG2;uint32_t count=digits>0?(uint32_t)digits:0;
    uint64_t bytes=32u+(uint64_t)count*128u;
    if(!texture_raw_get(print_token,&ref) || bytes>UINT32_MAX ||
       !kamui_can_append(KM_LIST_TR,(uint32_t)bytes)) {
        sa1_log("njPrintB: atlas or complete TA span unavailable");RET(-1);return;
    }
    float scale=hle_rdf(PRINT_SCALE);
    uint32_t x=FTRC((float)(int16_t)(ARG0>>16)*scale);
    uint32_t y=FTRC((float)(int16_t)ARG0*scale),color=hle_rd32(PRINT_COLOR),value=ARG1;
    uint32_t original_pointer=kamui_buffer_ptr(KM_LIST_TR);
    uint32_t header[8]={hle_rd32(PRINT_PCW),hle_rd32(PRINT_ISP),hle_rd32(PRINT_TSP),hle_rd32(PRINT_TCW),0,0,0,0};
    hle_wr32(NJ_CUR_GINDEX,0xfffffffeu);kamui_mark2d_begin();kamui_append(KM_LIST_TR,header);
    for(uint32_t i=count;i;i--) {
        uint32_t shifted=value;SHLD(shifted,0u-(i-1u));unsigned bit=shifted&1u;
        float left=(float)(int16_t)x,top=(float)(int16_t)y;
        float u=1.0f/1024.0f+(float)bit/16.0f,v=1.0f/1024.0f+3.0f/16.0f;
        for(unsigned k=0;k<4;k++)kamui_put_vertex(KM_LIST_TR,k==3?0xf0000000u:0xe0000000u,
            left+(k>=2?scale:0),top+(k&1?scale:0),1.0f,
            u+(k>=2?63.0f/1024.0f:0),v+(k&1?63.0f/1024.0f:0),color,0);
        x=FTRC(left+scale);
    }
    kamui_mark2d_end();
    kamui_buffer_set(KM_LIST_TR,(original_pointer&0xfc000000u)|(kamui_buffer_ptr(KM_LIST_TR)&0x03ffffffu));
}
void ninja_print_state(hle_state_io *io) {
    uint32_t token=hle_state_loading(io)?0:print_token;
    hle_state_optional_blob(io,"ninja.print",&token,sizeof token);
    if(hle_state_loading(io) && !hle_state_error(io)) {
        texture_raw_ref ref;
        if(token && !texture_raw_get(token,&ref))hle_state_fail(io,"invalid print atlas owner");
        else print_token=token;
    }
}
