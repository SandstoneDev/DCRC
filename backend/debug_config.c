#include "debug_config.h"
#include <ctype.h>
#include <string.h>
static int text_ok(const char *s,int key) {
    if (!s || !*s) return 0;
    for (;*s;s++) if ((unsigned char)*s<32 || (key && !(isalnum((unsigned char)*s)||*s=='_'))) return 0;
    return 1;
}
static int add(char *out,size_t cap,size_t *n,const char *s,size_t bytes) {
    if (*n>=cap || bytes>=cap-*n) return 0;
    memcpy(out+*n,s,bytes);*n+=bytes;out[*n]=0;return 1;
}
int debug_ini_update(const char *old,size_t size,const DebugIniPair *pairs,size_t count,char *out,size_t cap) {
    if (!old || !out || !cap || size>16384 || count>32 || (!pairs&&count) || memchr(old,0,size)) return -1;
    for(size_t i=0;i<count;i++) if(!text_ok(pairs[i].key,1)||!text_ok(pairs[i].value,0)) return -1;
    size_t n=0;out[0]=0;
    for(size_t at=0;at<size;) {
        size_t end=at;while(end<size && old[end]!='\n')end++;
        if(end<size)end++;
        size_t k=at;while(k<end && (old[k]==' '||old[k]=='\t'))k++;
        int owned=0;
        for(size_t i=0;i<count;i++) {
            size_t len=strlen(pairs[i].key);
            if(len>end-k || memcmp(old+k,pairs[i].key,len))continue;
            size_t eq=k+len;while(eq<end&&(old[eq]==' '||old[eq]=='\t'))eq++;
            if(eq<end && old[eq]=='='){owned=1;break;}
        }
        if(!owned && !add(out,cap,&n,old+at,end-at))return -1;
        at=end;
    }
    if(n && out[n-1]!='\n' && !add(out,cap,&n,"\n",1))return -1;
    for(size_t i=0;i<count;i++) {
        if(!add(out,cap,&n,pairs[i].key,strlen(pairs[i].key)) || !add(out,cap,&n," = ",3)
            || !add(out,cap,&n,pairs[i].value,strlen(pairs[i].value)) || !add(out,cap,&n,"\n",1))return -1;
    }
    return (int)n;
}
