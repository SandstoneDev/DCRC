/* vmu_store.h - where the HLE VMU (cfg.c, bu library) keeps its files: one
 * host file per VMU file, behind a small interface each backend fills in.
 *
 * hle_vmu_store NULL (the default) means no VMU is inserted: ordinary legacy bu operations keep their prior no-card answers; added
 * typed/range services report a completed no-card error.  The desktop backend sets it to a folder store
 * (backend/desktop/vmu_store_desktop.c) unless the run is --strict or
 * --no-vmu.
 *
 * PSP: backend/psp/vmu_store_psp.c (vmu/ beside the EBOOT), set the same
 * way by main_psp.c.
 *
 * Names are VMU file names: up to 12 characters [A-Za-z0-9_.-], NUL
 * terminated.  Sizes are bytes; the bu layer rounds to 512-byte blocks.
 *
 * Part of sa1-psp (MIT). */
#pragma once
#include <stdint.h>

enum { VMU_STORE_DATA=0, VMU_STORE_EXEC=1 };
typedef struct vmu_file_info {
    uint32_t size, type, header_block, copy_flag;
} vmu_file_info;

typedef struct vmu_store_ops {
    /* Reads up to max bytes: bytes read, -1 absent, -2 corrupt/host error. */
    int32_t (*read)(const char *name, void *buf, uint32_t max);
    /* Creates or replaces the file with n bytes: 0, or -1 on a host error. */
    int (*write)(const char *name, const void *buf, uint32_t n);
    /* Deletes the file: 0, or -1 if absent. */
    int (*remove)(const char *name);
    /* The index-th file in a stable order (sorted by name): writes its name
     * (13 bytes with the NUL) and size and returns 0; -1 past the last,
     * -2 on corrupt metadata or an uncertain host read. Index0 refreshes
     * the snapshot; later indexes reuse it until a store mutation/mount. */
    int (*list)(int index, char name[13], uint32_t *size);
    /* Optional typed metadata: 0 found, -1 absent, -2 corrupt/host error.
     * A legacy four-operation store exposes DATA files only. */
    int (*stat)(const char *name, vmu_file_info *info);
    /* Optional complete typed write. 0 means a checked durable commit; a
     * compatibility export may still await recovery from that commit. */
    int (*write_typed)(const char *name, const void *buf, uint32_t n,
                       const vmu_file_info *info);
} vmu_store_ops;

extern const vmu_store_ops *hle_vmu_store;
