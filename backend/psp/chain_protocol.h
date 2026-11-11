/* Local user/kernel launch request; copied before the worker starts. MIT. */
#pragma once
#include <stdint.h>
#include "chain_path.h"
#define SA1_CHAIN_MAGIC 0x53414331u
#define SA1_RESTART_MAGIC 0x44525231u
typedef struct {
    uint32_t magic;
    char from[256];
    char next[256];
} sa1_chain_args;
typedef char sa1_chain_abi_size[(sizeof(sa1_chain_args)==516)?1:-1];
/* Test chains can never target themselves. A separately tagged user menu
 * restart must target exactly itself; it cannot change apps. */
static inline int sa1_chain_request_valid(const sa1_chain_args *r) {
    if (!r) return 0;
    if (r->magic==SA1_RESTART_MAGIC)
        return sa1_application_path_same(r->from,r->next);
    return r->magic==SA1_CHAIN_MAGIC && sa1_chain_path_valid(r->from)
        && sa1_chain_path_valid(r->next) && !sa1_chain_path_same(r->from,r->next);
}
