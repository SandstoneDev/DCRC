/* Shared user/kernel allowlist for local DCRC chain targets.
 * At most 255 bytes including NUL; reads at most 256 input bytes.
 * Part of sa1-psp (MIT). */
#pragma once

static inline int sa1_chain_path_valid(const char *s) {
    static const char prefix[]="ms0:/PSP/GAME/DCRC_";
    static const char suffix[]="/EBOOT.PBP";
    const unsigned pre=sizeof prefix-1, tail=sizeof suffix-1;
    if (!s) return 0;
    unsigned n=0;
    while (n<256u && s[n]) n++;
    if (n>=255u || n<pre+1u+tail) return 0;
    for (unsigned i=0;i<pre;i++) if (s[i]!=prefix[i]) return 0;
    for (unsigned i=0;i<tail;i++) if (s[n-tail+i]!=suffix[i]) return 0;
    for (unsigned i=pre;i<n-tail;i++) {
        unsigned char c=(unsigned char)s[i];
        if (!((c>='A' && c<='Z') || (c>='a' && c<='z')
            || (c>='0' && c<='9') || c=='_')) return 0;
    }
    return 1;
}
/* Memory Stick FAT names are case-insensitive. Never chain to our own
 * image through a differently cased spelling. Both strings stay bounded. */
static inline int sa1_chain_path_same(const char *a,const char *b) {
    if (!sa1_chain_path_valid(a) || !sa1_chain_path_valid(b)) return 0;
    for (unsigned i=0;;i++) {
        unsigned char x=(unsigned char)a[i], y=(unsigned char)b[i];
        if (x>='A' && x<='Z') x=(unsigned char)(x+'a'-'A');
        if (y>='A' && y<='Z') y=(unsigned char)(y+'a'-'A');
        if (x!=y) return 0;
        if (!x) return 1;
    }
}
