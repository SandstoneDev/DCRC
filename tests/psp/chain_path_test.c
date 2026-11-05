/* Synthetic chain-target allowlist checks. No game data.
 * cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined
 *   tests/psp/chain_path_test.c -o work/chain_path_test
 * Part of sa1-psp (MIT). */
#include "../../backend/psp/chain_path.h"
#include <stdio.h>
#include <string.h>

static int checks, failures;
#define CHECK(x, why) do { checks++; if (!(x)) { failures++; printf("FAIL: %s\n",why); } } while (0)
int main(void) {
    static const char *valid[]={
        "ms0:/PSP/GAME/DCRC_SA1_82_A/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_SA1_82_B/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_SA1_82_C/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_SA1_82_D/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_a/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_0/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC__/EBOOT.PBP"
    };
    static const char *invalid[]={
        "", "ms0:/PSP/GAME/DCRC_/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_", "ms0:/PSP/GAME/DCRC_A/",
        "ms0:/PSP/GAME/DCRC_A/EBOOT.PBP.extra",
        "ms0:/PSP/GAME/DCRC_A/EBOOT.PBP/",
        "ms0:/PSP/GAME/DCRC_A/OTHER.PBP",
        "ms0:/PSP/GAME/DCRC_A/EBOOT.pbp",
        "MS0:/PSP/GAME/DCRC_A/EBOOT.PBP",
        "ms0:/psp/GAME/DCRC_A/EBOOT.PBP",
        "ef0:/PSP/GAME/DCRC_A/EBOOT.PBP",
        "host0:/PSP/GAME/DCRC_A/EBOOT.PBP",
        "ms0:/PSP/GAME/OTHER_DCRC_A/EBOOT.PBP",
        "beforems0:/PSP/GAME/DCRC_A/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_A_B/EBOOT.PBPafter",
        "ms0:/PSP/GAME/DCRC_A/../DCRC_B/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_../EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_A/B/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_A\\B/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_A:B/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_A-B/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_A B/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_A.B/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_%41/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_A\n/EBOOT.PBP",
        "ms0:/PSP/GAME/DCRC_\xc3\xa9/EBOOT.PBP"
    };
    CHECK(!sa1_chain_path_valid(NULL),"NULL rejected");
    for (unsigned i=0;i<sizeof valid/sizeof *valid;i++) CHECK(sa1_chain_path_valid(valid[i]),valid[i]);
    for (unsigned i=0;i<sizeof invalid/sizeof *invalid;i++) CHECK(!sa1_chain_path_valid(invalid[i]),invalid[i]);
    static const char prefix[]="ms0:/PSP/GAME/DCRC_", suffix[]="/EBOOT.PBP";
    char boundary[256];
    memset(boundary,'A',sizeof boundary);
    memcpy(boundary,prefix,sizeof prefix-1);
    memcpy(boundary+254-(sizeof suffix-1),suffix,sizeof suffix);
    CHECK(strlen(boundary)==254 && sa1_chain_path_valid(boundary),"255 bytes including NUL accepted");
    memset(boundary,'A',sizeof boundary);
    memcpy(boundary,prefix,sizeof prefix-1);
    memcpy(boundary+255-(sizeof suffix-1),suffix,sizeof suffix);
    CHECK(strlen(boundary)==255 && !sa1_chain_path_valid(boundary),"256 bytes including NUL rejected");
    memset(boundary,'A',sizeof boundary);
    memcpy(boundary,prefix,sizeof prefix-1);
    CHECK(!sa1_chain_path_valid(boundary),"unterminated 256-byte input rejected without overread");
    for (unsigned i=0;i<sizeof prefix-1;i++) {
        char truncated[sizeof prefix];
        memcpy(truncated,prefix,i); truncated[i]=0;
        CHECK(!sa1_chain_path_valid(truncated),"truncated prefix rejected");
    }
    printf("chain_path_test: %d checks, %d failures\n",checks,failures);
    return failures?1:0;
}
