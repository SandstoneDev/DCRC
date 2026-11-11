/* cfg.c - system settings and the VMU/backup library: the answers a console
 * with the US settings, an erased flash user partition and, when the
 * backend provides one (vmu_store.h), a VMU in port A1 gives.
 *
 * Part of sa1-psp (MIT). */
#include "shinobi.h"
#include "../state.h"
#include "vmu_store.h"
#include <string.h>

/* syCfg: 0x8C5FF2CC Init(work) -> 0; 0x8C5FF2DE Exit -> 0;
 * 0x8C5FF31E GetSoundMode(&mode) -> *mode = 0 (stereo);
 * 0x8C5FF39C GetLanguage(&lang) -> *lang = 1 (English). */
void sdk_8c5ff2cc(sh4_ctx *c) { HLE_ENTER(0x8c5ff2ccu, "syCfgInit"); RET(ARG0 ? 0 : -1); }
void sdk_8c5ff2de(sh4_ctx *c) { HLE_ENTER(0x8c5ff2deu, "syCfgExit"); RET(0); }
void sdk_8c5ff31e(sh4_ctx *c) { HLE_ENTER(0x8c5ff31eu, "syCfgGetSoundMode"); hle_wr32(ARG0, 0); RET(0); }
void sdk_8c5ff39c(sh4_ctx *c) { HLE_ENTER(0x8c5ff39cu, "syCfgGetLanguage"); hle_wr32(ARG0, 1); RET(0); }

/* Flash user partition (game settings block): 0x8C604044 open -> -8 (no
 * KATANA_FLASH header, so the game uses its defaults), 0x8C6041D4 read
 * request -> -11 (not open), 0x8C604250 status -> 1 (done; 2 would be
 * polled forever), 0x8C6042E4 close. */
void sdk_8c604044(sh4_ctx *c) { HLE_ENTER(0x8c604044u, "syFlashOpen"); RET(-8); }
void sdk_8c6041d4(sh4_ctx *c) { HLE_ENTER(0x8c6041d4u, "syFlashReadBlock"); RET(-11); }
void sdk_8c604250(sh4_ctx *c) { HLE_ENTER(0x8c604250u, "syFlashServer"); RET(1); }
void sdk_8c6042e4(sh4_ctx *c) { HLE_ENTER(0x8c6042e4u, "syFlashClose"); }

/* bu (VMU file system, "bu Ver 1.44").  With hle_vmu_store NULL no VMU is
 * inserted; existing ordinary operations retain their legacy no-card answers.
 * The additional operations below complete real no-card errors.  With a store (vmu_store.h), drive 0 (port A
 * slot 1) holds one standard VMU: 200 user blocks of 512 bytes whose files
 * are the store's files.  The library's two layers (wrappers at
 * 0x8C602B68.., a worker core at 0x8C647xxx over maple) are replaced at the
 * wrapper level, and asynchronous operations finish inside the call, since
 * the game spins on buIsBusy without running the server.  Drive = port*2 +
 * slot-1.  Errors are 16-bit codes, sign-extended: -1 busy, -255 no card,
 * -252 no room, -251 no such file / no more files, -245 bad name.
 * 0x8C602B68 buInit(size class, drive mask, work, init_cb): calls init_cb at
 *   once (the game sets its callbacks there); a VMU in the mask is mounted by
 *   the next buExecServer, which calls complete_cb(drive, 1 = mount, 0, 0) as
 *   the real server does when it sees a new card.
 * 0x8C6033E4 buIsBusy(drive) -> 0 (the game spins while it is -1).
 * 0x8C602DF2 buIsMounted(drive) -> 1/0.
 * 0x8C602F5C buGetDiskInfo(drive, info): 56 bytes; the game reads only the
 *   free blocks at +36 (no VMU: 0xFF01).
 * 0x8C602FB8 / 0x8C602FE6 buFindFirstFile / buFindNextFile(drive, buf):
 *   12-char name + NUL (no VMU: -2 / 0).
 * 0x8C603384 buIsExistFile(drive, name) -> 0 / -251 (no VMU: 0xFF01).
 * 0x8C603474 buGetFileSize(drive, name) -> blocks.
 * 0x8C603508 buLoadFile(drive, name, buf, blocks; 0 = whole file), op 11.
 * 0x8C603560 buSaveFile(drive, name, image, blocks, @sp time, @sp+4 flags),
 *   op 12 (no VMU: -1, busy): needs the free blocks plus the old file's.
 *   Both report through complete_cb(drive, op, result, 0).
 * 0x8C602CB8 buExecServer, 0x8C602BF0 detach server.
 * 0x8C602DDA / 0x8C602DE0: completion and progress callbacks, kept.
 * buMakeBackupFileImage 0x8C6037A0 and buCalcBackupFileSize 0x8C603998 are
 * pure computation in the SDK; see their HLE below (no VMU: 0, as the seam
 * stubs answered). */
const vmu_store_ops *hle_vmu_store;
static uint32_t bu_complete_cb, bu_progress_cb;
static int32_t bu_last_error[8];
static uint8_t bu_busy[8];
static int bu_mount_pending, bu_find_cursor;   /* not in save states */

#define BU_BLOCKS 200
#define BU_ERR_NOROOM (-252)
#define BU_ERR_NOFILE (-251)
#define BU_ERR_NAME (-245)
#define BU_ERR_BROKEN (-191)

static int bu_present(uint32_t drive) { return hle_vmu_store && drive == 0; }
static int bu_catalog(uint32_t *used, char executable[13]);

/* The guest name at a (1 to 12 chars) into n; -1 if empty or too long. */
static int bu_name(uint32_t a, char n[13]) {
    for (int i = 0; i < 13; i++) {
        n[i] = (char)hle_rd8(a + i);
        if (!n[i]) return i ? 0 : -1;
    }
    return -1;
}
static uint32_t bu_blocks_of(uint32_t bytes) { return bytes / 512 + (bytes % 512 != 0); }
static int32_t bu_used_blocks(void) {
    char n[13]; uint32_t sz, used = 0;
    if (!hle_vmu_store->list) return BU_ERR_BROKEN;
    for (int i = 0; i <= BU_BLOCKS; i++) {
        int r=hle_vmu_store->list(i,n,&sz);
        if(r==-1)return (int32_t)used;
        if(r || i==BU_BLOCKS || bu_blocks_of(sz)>BU_BLOCKS-used)return BU_ERR_BROKEN;
        used+=bu_blocks_of(sz);
    }
    return BU_ERR_BROKEN;
}
static int32_t bu_file_blocks(const char *name) {
    char n[13]; uint32_t sz;
    if (!hle_vmu_store->list) return -2;
    for (int i = 0; i <= BU_BLOCKS; i++) {
        memset(n,0,sizeof n);int r=hle_vmu_store->list(i,n,&sz);
        if(r)return r==-1?-1:-2;
        if(i==BU_BLOCKS || !memchr(n,0,sizeof n) || bu_blocks_of(sz)>BU_BLOCKS)return -2;
        if (!strcmp(n, name)) return (int32_t)bu_blocks_of(sz);
    }
    return -2;
}
static void bu_complete(sh4_ctx *c, uint32_t drive, uint32_t op, int32_t result) {
    if(drive<8){bu_last_error[drive]=result;bu_busy[drive]=0;}
    sa1_log("bu: drive %u op %u -> %d", (unsigned)drive, (unsigned)op, (int)result);
    if (bu_complete_cb) hle_call_guest(c, bu_complete_cb, drive, op, (uint32_t)result, 0);
}

void sdk_8c602b68(sh4_ctx *c) {
    HLE_ENTER(0x8c602b68u, "buInit");
    uint32_t cb = ARG3;
    memset(bu_last_error,0,sizeof bu_last_error);memset(bu_busy,0,sizeof bu_busy);
    bu_mount_pending = bu_present(0) && (ARG1 & 1);
    RET(0);
    if (cb) {
        sa1_log("buInit: calling the game's init callback 0x%08x", (unsigned)cb);
        hle_call_guest(c, cb, 0, 0, 0, 0);
        RET(0);
    }
}
void sdk_8c6033e4(sh4_ctx *c) { HLE_ENTER(0x8c6033e4u, "buIsBusy"); RET(ARG0<8&&bu_busy[ARG0]?-1:0); }
void sdk_8c602df2(sh4_ctx *c) { HLE_ENTER(0x8c602df2u, "buIsMounted"); RET(bu_present(ARG0)); }
void sdk_8c602f5c(sh4_ctx *c) {
    HLE_ENTER(0x8c602f5cu, "buGetDiskInfo");
    uint32_t drive = ARG0, info = ARG1;
    if (!bu_present(drive)) { RET(0xFF01); return; }
    uint32_t used; char executable[13];
    int result=bu_catalog(&used,executable);
    if(result){RET(result);return;}
    uint32_t fr=BU_BLOCKS-used;
    for (uint32_t i = 0; i < 56; i++) hle_wr8(info + i, 0);
    hle_wr16(info + 32, 256);            /* blocks on the card */
    hle_wr16(info + 34, BU_BLOCKS);      /* user blocks */
    hle_wr16(info + 36, fr);             /* free user blocks */
    hle_wr16(info + 38, fr);
    hle_wr16(info + 40, 128);
    hle_wr16(info + 42, executable[0] ? 0 : fr < 128 ? fr : 128);
    hle_wr16(info + 44, 512);            /* block size */
    hle_wr16(info + 48, 1999);           /* card date 1999-01-01 (a Friday) */
    hle_wr8(info + 50, 1);
    hle_wr8(info + 51, 1);
    hle_wr8(info + 55, 5);
    RET(0);
}
static void bu_find(sh4_ctx *c, int first) {
    uint32_t buf = ARG1;
    char n[13]; uint32_t sz;
    if (first) bu_find_cursor = 0;
    int r=hle_vmu_store->list?hle_vmu_store->list(bu_find_cursor,n,&sz):-2;
    if(r){RET(r==-1?BU_ERR_NOFILE:BU_ERR_BROKEN);return;}
    bu_find_cursor++;
    for (int i = 0; i < 12; i++) hle_wr8(buf + i, (uint8_t)n[i]);
    hle_wr8(buf + 12, 0);
    RET(0);
}
void sdk_8c602fb8(sh4_ctx *c) {
    HLE_ENTER(0x8c602fb8u, "buFindFirstFile");
    if (!bu_present(ARG0)) { RET(-2); return; }
    bu_find(c, 1);
}
void sdk_8c602fe6(sh4_ctx *c) {
    HLE_ENTER(0x8c602fe6u, "buFindNextFile");
    if (!bu_present(ARG0)) { RET(0); return; }
    bu_find(c, 0);
}
void sdk_8c603384(sh4_ctx *c) {
    HLE_ENTER(0x8c603384u, "buIsExistFile");
    char n[13];
    if (!bu_present(ARG0)) { RET(0xFF01); return; }
    if (bu_name(ARG1, n)) { RET(BU_ERR_NAME); return; }
    int32_t b=bu_file_blocks(n);
    RET(b>=0?0:b==-1?BU_ERR_NOFILE:BU_ERR_BROKEN);
}
void sdk_8c603474(sh4_ctx *c) {
    HLE_ENTER(0x8c603474u, "buGetFileSize");
    char n[13];
    if (!bu_present(ARG0)) { RET(0); return; }
    if (bu_name(ARG1, n)) { RET(BU_ERR_NAME); return; }
    int32_t b = bu_file_blocks(n);
    RET(b>=0?b:b==-1?BU_ERR_NOFILE:BU_ERR_BROKEN);
}
static uint8_t bu_buf[BU_BLOCKS * 512];
void sdk_8c603508(sh4_ctx *c) {
    HLE_ENTER(0x8c603508u, "buLoadFile");
    uint32_t drive = ARG0, buf = ARG2, blocks = ARG3;
    char n[13];
    if (!bu_present(drive)) { RET(0); return; }
    int32_t r = BU_ERR_NOFILE;
    if (bu_name(ARG1, n)) r = BU_ERR_NAME;
    else {
        int32_t got = hle_vmu_store->read(n, bu_buf, sizeof bu_buf);
        if(got < -1) r=BU_ERR_BROKEN;
        if (got >= 0) {
            uint32_t want = blocks ? blocks * 512 : (uint32_t)got;
            if (want > (uint32_t)got) want = (uint32_t)got;
            for (uint32_t i = 0; i < want; i++) hle_wr8(buf + i, bu_buf[i]);
            r = 0;
        }
    }
    bu_complete(c, drive, 11, r);
    RET(0);
}
void sdk_8c603560(sh4_ctx *c) {
    HLE_ENTER(0x8c603560u, "buSaveFile");
    uint32_t drive = ARG0, buf = ARG2, blocks = ARG3;
    char n[13];
    if (!bu_present(drive)) { RET(-1); return; }
    int32_t r;
    if (bu_name(ARG1, n)) r = BU_ERR_NAME;
    else {
        int32_t old = bu_file_blocks(n);
        int32_t total=bu_used_blocks();
        uint32_t replaced=old>0?(uint32_t)old:0;
        uint32_t used=total>=0?(uint32_t)total:0;
        if(old < -1 || total<0 || replaced>used)r=BU_ERR_BROKEN;
        else if (blocks == 0 || blocks > BU_BLOCKS-(used-replaced)) r = BU_ERR_NOROOM;
        else {
            for (uint32_t i = 0; i < blocks * 512; i++) bu_buf[i] = (uint8_t)hle_rd8(buf + i);
            r = hle_vmu_store->write(n, bu_buf, blocks * 512) == 0 ? 0 : -248;   /* write error */
            if (r == 0 && bu_progress_cb) hle_call_guest(c, bu_progress_cb, drive, 12, blocks, blocks);
        }
    }
    bu_complete(c, drive, 12, r);
    RET(0);
}
void sdk_8c602cb8(sh4_ctx *c) {
    HLE_ENTER(0x8c602cb8u, "buExecServer");
    if (bu_mount_pending && bu_complete_cb) {
        bu_mount_pending = 0;
        bu_complete(c, 0, 1, 0);
    }
}
void sdk_8c602bf0(sh4_ctx *c) { HLE_ENTER(0x8c602bf0u, "buDetachServer"); }
void sdk_8c602dda(sh4_ctx *c) { HLE_ENTER(0x8c602ddau, "buSetCompleteCallback"); bu_complete_cb = ARG0; }
void sdk_8c602de0(sh4_ctx *c) { HLE_ENTER(0x8c602de0u, "buSetProgressCallback"); bu_progress_cb = ARG0; }

/* 0x8C603998 buCalcBackupFileSize(icons 1..3, eyecatch type 0..3, data
 * bytes) -> blocks of the VMS image, -256 on a bad argument.
 * 0x8C6037A0 buMakeBackupFileImage(dst, desc) -> blocks: the VMS file image
 * from desc (+0 title, +18 comment, +52 creator: strings; +68 palette ptr,
 * +72 icons ptr, +76 u16 icons, +78 u16 anim speed, +80 eyecatch ptr, +84
 * u16 eyecatch type, +88 data ptr, +92 u32 data bytes).  Image: 0x00 title
 * (16, space padded), 0x10 comment (32, space padded), 0x30 creator (16, NUL
 * padded), 0x40 u16 icons, 0x42 u16 speed, 0x44 u16 eyecatch type (0 with
 * no eyecatch), 0x46 u16 CRC-16/0x1021 (initial 0, over the unpadded image
 * with this field 0), 0x48 u32 data bytes, 0x60 palette (32), 0x80 icons
 * (512 each), eyecatch, data, zeros to a block boundary. */
static const uint32_t bu_eyecatch_bytes[4] = { 0, 0x1f80, 0x11c0, 0x800 };
static int32_t bu_image_bytes(uint32_t icons, uint32_t eye, uint32_t data) {
    if (icons < 1 || icons > 3 || eye > 3) return -256;
    return (int32_t)(128 + 512 * icons + bu_eyecatch_bytes[eye] + data);
}
void sdk_8c603998(sh4_ctx *c) {
    HLE_ENTER(0x8c603998u, "buCalcBackupFileSize");
    if (!hle_vmu_store) { RET(0); return; }   /* the old seam stub's answer */
    int32_t n = bu_image_bytes(ARG0, ARG1, ARG2);
    RET(n < 0 ? n : (int32_t)bu_blocks_of((uint32_t)n));
}
static void bu_put_str(uint32_t dst, uint32_t src, uint32_t len, uint8_t pad) {
    uint32_t i = 0;
    for (; i < len; i++) { uint8_t b = (uint8_t)hle_rd8(src + i); if (!b) break; hle_wr8(dst + i, b); }
    for (; i < len; i++) hle_wr8(dst + i, pad);
}
static void bu_copy(uint32_t dst, uint32_t src, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) hle_wr8(dst + i, src ? hle_rd8(src + i) : 0);
}
void sdk_8c6037a0(sh4_ctx *c) {
    HLE_ENTER(0x8c6037a0u, "buMakeBackupFileImage");
    if (!hle_vmu_store) { RET(0); return; }
    uint32_t dst = ARG0, d = ARG1;
    uint32_t icons = hle_rd16(d + 76), eye_p = hle_rd32(d + 80), eye = eye_p ? hle_rd16(d + 84) : 0;
    uint32_t data_p = hle_rd32(d + 88), data = hle_rd32(d + 92);
    int32_t n = bu_image_bytes(icons, eye, data);
    if (n < 0) { RET(n); return; }
    uint32_t total = bu_blocks_of((uint32_t)n) * 512;
    for (uint32_t i = 0; i < 0x80; i++) hle_wr8(dst + i, 0);
    bu_put_str(dst + 0x00, d + 0, 16, ' ');
    bu_put_str(dst + 0x10, d + 18, 32, ' ');
    bu_put_str(dst + 0x30, d + 52, 16, 0);
    hle_wr16(dst + 0x40, icons);
    hle_wr16(dst + 0x42, hle_rd16(d + 78));
    hle_wr16(dst + 0x44, eye);
    hle_wr32(dst + 0x48, data);
    bu_copy(dst + 0x60, hle_rd32(d + 68), 32);
    uint32_t o = 0x80;
    bu_copy(dst + o, hle_rd32(d + 72), 512 * icons); o += 512 * icons;
    bu_copy(dst + o, eye_p, bu_eyecatch_bytes[eye]); o += bu_eyecatch_bytes[eye];
    bu_copy(dst + o, data_p, data); o += data;
    for (; o < total; o++) hle_wr8(dst + o, 0);
    uint32_t crc = 0;
    for (uint32_t i = 0; i < (uint32_t)n; i++) {
        crc ^= (uint32_t)hle_rd8(dst + i) << 8;
        for (int k = 0; k < 8; k++) crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
    }
    hle_wr16(dst + 0x46, crc & 0xffff);
    RET(total / 512);
}


/* Own bounded file-store VMU services. API/format facts are independently
 * checked against the supported input. No SDK/game function body copied.
 * The folder store has a compact virtual allocation: one executable at the
 * low end, DATA packed from the high end; no physical FAT is emulated. */
#define BU_ERR_PARAM (-256)
#define BU_ERR_NOCARD (-255)
#define BU_ERR_WRITE (-192)
static int bu_span(uint32_t a,uint32_t n){
    uint32_t top=a>>29,p=a&0x1fffffffu;
    if(top!=0&&top!=4&&top!=5)return 0;
    return p>=0x0c000000u&&p-0x0c000000u<SA1_RAM_SIZE+SA1_RAM_EXTRA&&
        n<=SA1_RAM_SIZE+SA1_RAM_EXTRA-(p-0x0c000000u);
}
static int bu_host_name(const char*n){
    for(unsigned i=0;i<13;i++){
        unsigned char z=(unsigned char)n[i];if(!z)return i>0;
        if(!((z>='A'&&z<='Z')||(z>='a'&&z<='z')||(z>='0'&&z<='9')||z=='_'||z=='-'||z=='.'))return 0;
    }return 0;
}
static int bu_safe_name(uint32_t a,char n[13]){return bu_span(a,13)&&!bu_name(a,n)&&bu_host_name(n);}
static int bu_meta_valid(const vmu_file_info*i){
    if(!i->size||i->size>sizeof bu_buf||i->type>VMU_STORE_EXEC||
       (i->copy_flag!=0&&i->copy_flag!=255)||i->header_block>=bu_blocks_of(i->size))return 0;
    return i->type!=VMU_STORE_EXEC||(i->header_block==1&&i->size>=1024&&i->size<=128u*512u&&!(i->size&511));
}
static int bu_stat_file(const char*n,vmu_file_info*i){
    if(hle_vmu_store->stat){int r=hle_vmu_store->stat(n,i);return r?r:(bu_meta_valid(i)?0:-2);}
    char found[13];uint32_t z;
    for(int k=0;k<=BU_BLOCKS;k++){
        int r=hle_vmu_store->list(k,found,&z);if(r)return r==-1?-1:-2;
        if(k==BU_BLOCKS||!bu_host_name(found))return -2;
        if(!strcmp(n,found)){*i=(vmu_file_info){z,VMU_STORE_DATA,0,0};return bu_meta_valid(i)?0:-2;}
    }return -2;
}
static int bu_catalog(uint32_t*used,char executable[13]){
    char n[13];uint32_t z;*used=0;executable[0]=0;
    if(!hle_vmu_store->list||!hle_vmu_store->read)return BU_ERR_BROKEN;
    for(int k=0;k<=BU_BLOCKS;k++){
        memset(n,0,sizeof n);int r=hle_vmu_store->list(k,n,&z);if(r==-1)return 0;if(r||k==BU_BLOCKS||!bu_host_name(n))return BU_ERR_BROKEN;
        vmu_file_info i;if(bu_stat_file(n,&i)||i.size!=z)return BU_ERR_BROKEN;
        uint32_t blocks=bu_blocks_of(z);if(blocks>BU_BLOCKS-*used)return BU_ERR_BROKEN;*used+=blocks;
        if(i.type==VMU_STORE_EXEC){if(executable[0])return BU_ERR_BROKEN;memcpy(executable,n,13);}
    }return BU_ERR_BROKEN;
}
static int bu_begin(sh4_ctx*c,uint32_t drive){
    if(drive>=8){RET(BU_ERR_PARAM);return 0;}
    if(bu_busy[drive]){RET(-1);return 0;}bu_busy[drive]=1;return 1;
}
static void bu_finish(sh4_ctx*c,uint32_t drive,uint32_t op,int32_t result){bu_complete(c,drive,op,result);RET(0);}
void sdk_8c602f8a(sh4_ctx*c){
    HLE_ENTER(0x8c602f8au,"buGetDiskFree");uint32_t drive=ARG0,type=ARG1,used;char exec[13];
    if(drive>=8||type>1){RET(BU_ERR_PARAM);return;}if(bu_busy[drive]){RET(-1);return;}
    if(!bu_present(drive)){RET(BU_ERR_NOCARD);return;}int r=bu_catalog(&used,exec);
    if(r){RET(r);return;}uint32_t free=BU_BLOCKS-used;
    RET(type?(exec[0]?0:free<128?free:128):free);
}
void sdk_8c603078(sh4_ctx*c){
    HLE_ENTER(0x8c603078u,"buFindExecFile");uint32_t used;char exec[13];
    if(ARG0>=8||!bu_span(ARG1,13)){RET(BU_ERR_PARAM);return;}
    if(bu_busy[ARG0]){RET(-1);return;}if(!bu_present(ARG0)){RET(BU_ERR_NOCARD);return;}
    int r=bu_catalog(&used,exec);if(r||!exec[0]){RET(r?r:BU_ERR_NOFILE);return;}
    for(unsigned i=0;i<13;i++) { hle_wr8(ARG1+i,(uint8_t)exec[i]); }
    RET(0);
}
void sdk_8c6033fe(sh4_ctx*c){HLE_ENTER(0x8c6033feu,"buGetLastError");RET(ARG0>=8?BU_ERR_PARAM:bu_busy[ARG0]?-1:bu_last_error[ARG0]);}
void sdk_8c603292(sh4_ctx*c){
    HLE_ENTER(0x8c603292u,"buDeleteFile");uint32_t d=ARG0;char n[13];vmu_file_info i;if(!bu_begin(c,d))return;
    int r=!bu_present(d)?BU_ERR_NOCARD:!bu_safe_name(ARG1,n)?BU_ERR_NAME:0;
    if(!r){int q=bu_stat_file(n,&i);r=q==-1?BU_ERR_NOFILE:q?BU_ERR_BROKEN:!hle_vmu_store->remove||hle_vmu_store->remove(n)?-246:0;}
    bu_finish(c,d,7,r);
}
void sdk_8c6034a2(sh4_ctx*c){
    HLE_ENTER(0x8c6034a2u,"buDefragDisk");uint32_t d=ARG0,used;char exec[13];if(!bu_begin(c,d))return;
    int r=!bu_present(d)?BU_ERR_NOCARD:!bu_span(ARG1,512)?BU_ERR_PARAM:bu_catalog(&used,exec);
    /* A validated compact virtual catalog is already defragmented. */
    bu_finish(c,d,9,r);
}
void sdk_8c6035be(sh4_ctx*c){
    HLE_ENTER(0x8c6035beu,"buSaveExecFile");uint32_t d=ARG0,buf=ARG2,blocks=ARG3,used;char n[13],exec[13];if(!bu_begin(c,d))return;
    int r=!bu_present(d)?BU_ERR_NOCARD:!bu_span(c->r[15],8)?BU_ERR_PARAM:!bu_safe_name(ARG1,n)?BU_ERR_NAME:0;
    /* Own US AL_MAIN SaveExec sites pass VERIFY|COPYDISABLE (0x800000ff).
     * write_typed must verify its durable commit before reporting success.
     * The time argument is accepted; this virtual store does not model dates. */
    uint32_t flags=r?0:STACK_ARG(1);
    if(!r&&(blocks<2||blocks>128||!bu_span(buf,blocks*512u)||(flags&~0x800000ffu)||((flags&255)!=0&&(flags&255)!=255)))r=BU_ERR_PARAM;
    if(!r)r=bu_catalog(&used,exec);
    if(!r&&exec[0])r=-247;
    if(!r){vmu_file_info old;int q=bu_stat_file(n,&old);if(q!=-1)r=q?BU_ERR_BROKEN:-250;}
    if(!r&&blocks>BU_BLOCKS-used)r=BU_ERR_NOROOM;
    if(!r&&!hle_vmu_store->write_typed)r=BU_ERR_WRITE;
    if(!r){for(uint32_t k=0;k<blocks*512u;k++)bu_buf[k]=(uint8_t)hle_rd8(buf+k);
        vmu_file_info info={blocks*512u,VMU_STORE_EXEC,1,flags&255u};
        if(hle_vmu_store->write_typed(n,bu_buf,info.size,&info))r=BU_ERR_WRITE;
        if(!r&&bu_progress_cb)hle_call_guest(c,bu_progress_cb,d,13,blocks,blocks);}
    bu_finish(c,d,13,r);
}
static void bu_range(sh4_ctx*c,int rewrite){
    uint32_t d=ARG0,buf=ARG2,start=ARG3,op=rewrite?20:14;char n[13];vmu_file_info info;if(!bu_begin(c,d))return;
    int r=!bu_present(d)?BU_ERR_NOCARD:!bu_span(c->r[15],4)?BU_ERR_PARAM:!bu_safe_name(ARG1,n)?BU_ERR_NAME:0;
    uint32_t blocks=r?0:STACK_ARG(0),off=0,bytes=0;
    if(!r){int q=bu_stat_file(n,&info);r=q==-1?BU_ERR_NOFILE:q?BU_ERR_BROKEN:0;}
    /* Positive ranges are supported; zero-length semantics of Ex are not
     * assumed from ordinary buLoadFile's different whole-file convention. */
    if(!r&&(start>BU_BLOCKS||!blocks||blocks>BU_BLOCKS))r=BU_ERR_PARAM;
    if(!r){off=start*512u;bytes=blocks*512u;if(off>info.size||bytes>info.size-off||!bu_span(buf,bytes))r=BU_ERR_PARAM;}
    if(!r&&rewrite&&(info.type!=VMU_STORE_EXEC||!hle_vmu_store->write_typed))r=BU_ERR_NAME;
    if(!r){int32_t got=hle_vmu_store->read(n,bu_buf,sizeof bu_buf);if(got<0||(uint32_t)got!=info.size)r=BU_ERR_BROKEN;}
    if(!r&&rewrite){for(uint32_t k=0;k<bytes;k++)bu_buf[off+k]=(uint8_t)hle_rd8(buf+k);if(hle_vmu_store->write_typed(n,bu_buf,info.size,&info))r=BU_ERR_WRITE;}
    else if(!r)for(uint32_t k=0;k<bytes;k++)hle_wr8(buf+k,bu_buf[off+k]);
    bu_finish(c,d,op,r);
}
void sdk_8c60361c(sh4_ctx*c){HLE_ENTER(0x8c60361cu,"buLoadFileEx");bu_range(c,0);}
void sdk_8c603672(sh4_ctx*c){HLE_ENTER(0x8c603672u,"buRewriteExecFile");bu_range(c,1);}

/* pdLcd / VMU screen: none present. */
void sdk_8c602ab4(sh4_ctx *c) { HLE_ENTER(0x8c602ab4u, "pdLcdIsStandard"); RET(0); }
void sdk_8c602998(sh4_ctx *c) { HLE_ENTER(0x8c602998u, "pdLcdDirection"); RET(0); }
void sdk_8c602a6a(sh4_ctx *c) { HLE_ENTER(0x8c602a6au, "pdVmsLcdWrite"); RET(-2); }

/* syHw / syCache: cache maintenance and hardware init are nothing here.
 * 0x8C6024D0 syHwInit, 0x8C6024FA syHwInit2, 0x8C5FC58A write-back range,
 * 0x8C5FC81C invalidate all, 0x8C5FC0C2 instruction-cache invalidate (the
 * game calls it after loading code overlays), 0x8C603B84 sysinfo/flash ID
 * patch. */
void sdk_8c6024d0(sh4_ctx *c) { HLE_ENTER(0x8c6024d0u, "syHwInit"); }
void sdk_8c6024fa(sh4_ctx *c) { HLE_ENTER(0x8c6024fau, "syHwInit2"); }
void sdk_8c5fc58a(sh4_ctx *c) { HLE_ENTER(0x8c5fc58au, "syCacheWriteBack"); }
void sdk_8c5fc81c(sh4_ctx *c) { HLE_ENTER(0x8c5fc81cu, "syCacheInvalidateAll"); }
void sdk_8c5fc0c2(sh4_ctx *c) { HLE_ENTER(0x8c5fc0c2u, "syCacheICI"); }
void sdk_8c603b84(sh4_ctx *c) { HLE_ENTER(0x8c603b84u, "syBtSysInfoInit"); RET(0); }

/* 0x8C604500: the SDK's byte memcpy(dst, src, n). */
void sdk_8c604500(sh4_ctx *c) {
    HLE_ENTER(0x8c604500u, "memcpy (SDK)");
    uint32_t d = ARG0, s = ARG1, n = ARG2;
    for (uint32_t i = 0; i < n; i++) hle_wr8(d + i, hle_rd8(s + i));
}
/* 0x8C6044E0: the same family's longword copy (dst, src, n longwords; the
 * halfword one is at 0x8C6044F0).  It was a seam stub returning 0; the
 * Chaos 0 boss copies its body's vertices into a heap buffer with it at
 * init (ovl B_CHAOS0 0x8C9034C0), and the buffer kept the allocator's
 * all-ones fill, which the game's clipper turned into the cyan prism of
 * the maintainer's shots 10 and 11 (docs/m2-render-report.md section 10). */
void sdk_8c6044e0(sh4_ctx *c) {
    HLE_ENTER(0x8c6044e0u, "memcpy32 (SDK)");
    uint32_t d = ARG0, s = ARG1, n = ARG2, v = 0;
    for (uint32_t i = 0; i < n; i++) { v = hle_rd32(s + 4 * i); hle_wr32(d + 4 * i, v); }
    RET(v);
}

void shinobi_cfg_state(hle_state_io *io) {
    hle_state_blob(io, "bu.complete", &bu_complete_cb, sizeof bu_complete_cb);
    hle_state_blob(io, "bu.progress", &bu_progress_cb, sizeof bu_progress_cb);
    if (hle_state_loading(io)) {
        int32_t restored[8] = {0};
        if (hle_state_optional_blob(io,"bu.last_error",restored,sizeof restored) >= 0)
            memcpy(bu_last_error,restored,sizeof bu_last_error);
    } else hle_state_optional_blob(io,"bu.last_error",bu_last_error,sizeof bu_last_error);
}
