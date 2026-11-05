/* Opaque user-local VMU container/mount adapter. Copyright2026 SandstoneDev.
 * MIT. No payload decoder, keys, internal DLC tables, or game instructions.
 * Header facts: KallistiOS dc/vmu_pkg.h; VMI File Name/size fields and the
 * US1.005 loader's fixed640-byte header contract. Raw payload stays opaque. */
#include "../hle.h"
#include "../shinobi/vmu_store.h"
#include "dlc_event.h"
#include "content_mount.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#define MAX_EVENTS 32
#define MAX_CATALOG (32u*640u)
#define MAX_IMAGE (200u*512u)
#define EVENT_HEADER 640u
static struct { char label[64],vmi[256],vms[256]; } catalog[MAX_EVENTS];
static int count,selected=-1,resuming,config_cli,config_bad;
static char config[64]="off",status[144]="Off";
static uint8_t *image;
static uint32_t image_bytes;
static char canonical[13];
static const vmu_store_ops *base;
static const vmu_store_ops overlay;
/* One enumeration snapshot, including one virtual entry; no heap/guest state. */
static struct {char name[13];uint32_t size;} listed[201];
static unsigned listed_count;
static int listed_valid;

static int lower(int c){return c>='A'&&c<='Z'?c+32:c;}
static int same(const char *a,const char *b){while(*a&&lower((unsigned char)*a)==lower((unsigned char)*b))a++,b++;return *a==*b;}
static void note(const char *s){snprintf(status,sizeof status,"%s",s);sa1_log("content: %s",status);}
static void unmount(void){
    if(hle_vmu_store==&overlay)hle_vmu_store=base;
    base=NULL;free(image);image=NULL;image_bytes=0;canonical[0]=0;selected=-1;listed_valid=0;listed_count=0;
}
static uint32_t le32(const uint8_t *p){return p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static unsigned le16(const uint8_t *p){return p[0]|(unsigned)p[1]<<8;}
static int event_name(const char *s){
    static const char prefix[]="sonicadv_";
    for(unsigned i=0;i<9;i++)if(lower((unsigned char)s[i])!=prefix[i])return 0;
    for(unsigned i=9;i<12;i++){int c=lower((unsigned char)s[i]);if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return 0;}
    return s[12]==0;
}
static int path_valid(const char *s){
    unsigned n=0,part=0;
    if(!s||!s[0]||s[0]=='/')return 0;
    for(;;n++){
        unsigned c=(unsigned char)s[n];
        if(n>=256)return 0;
        if(c=='/'||!c){
            unsigned z=n-part;
            if(!z||s[n-1]=='.'||s[n-1]==' ')return 0;
            if(!c)return 1;
            part=n+1;
        }else if(c<32||c>126||c=='\\'||c==':'||c=='|'||c=='*'||c=='?'||c=='<'||c=='>')return 0;
    }
}
static char *trim(char *s){
    while(*s==' '||*s=='\t'||*s=='\r')s++;
    size_t n=strlen(s);while(n&&(s[n-1]==' '||s[n-1]=='\t'||s[n-1]=='\r'))s[--n]=0;
    return s;
}
static int read_catalog(void){
    uint32_t n;count=0;
    if(sa1_plat_file_size("dlc/events.txt",&n)){note("Off; no dlc/events.txt catalog");return 0;}
    if(n>MAX_CATALOG){note("Rejected catalog size");return -1;}
    char *buf=malloc((size_t)n+1u);
    if(!buf){note("Catalog allocation failed");return -1;}
    int ok=sa1_plat_file_read("dlc/events.txt",0,buf,n)==(int)n;
    for(uint32_t i=0;ok&&i<n;i++)if(!buf[i])ok=0;
    buf[n]=0;char *p=buf;unsigned lines=0;
    while(ok&&p<buf+n){
        char *end=strchr(p,'\n');if(end)*end=0;
        if(++lines>64||strlen(p)>=640){ok=0;break;}
        char *label=trim(p);
        if(*label&&*label!='#'){
            char *vmi=strchr(label,'|'),*vms=vmi?strchr(vmi+1,'|'):NULL;
            if(!vmi||!vms||strchr(vms+1,'|')||count==MAX_EVENTS){ok=0;break;}
            *vmi++=0;*vms++=0;label=trim(label);vmi=trim(vmi);vms=trim(vms);
            size_t z=strlen(label);
            if(!z||z>=64||!path_valid(vmi)||!path_valid(vms)){ok=0;break;}
            for(size_t i=0;i<z;i++)if((unsigned char)label[i]<32||(unsigned char)label[i]>126)ok=0;
            for(int i=0;i<count;i++)if(same(label,catalog[i].label))ok=0;
            if(!ok)break;
            strcpy(catalog[count].label,label);strcpy(catalog[count].vmi,vmi);strcpy(catalog[count].vms,vms);count++;
        }
        if(!end)break;
        p=end+1;
    }
    free(buf);
    if(!ok){count=0;note("Rejected catalog syntax/path/duplicate label");return -1;}
    return 0;
}
static int outer_valid(const uint8_t vmi[108],const uint8_t *vms,uint32_t n){
    memcpy(canonical,vmi+88,12);canonical[12]=0;
    if(!event_name(canonical))return 0;
    /* The guest performs case-sensitive canonical-name recognition. */
    for(unsigned i=0;i<12;i++)if(canonical[i]>='a'&&canonical[i]<='z')return 0;
    if(le32(vmi+104)!=n||le16(vms+0x40)!=1||le16(vms+0x44)!=0||le32(vms+0x48)!=n-EVENT_HEADER)return 0;
    unsigned expected=le16(vms+0x46);
    if(expected){
        unsigned crc=0;
        for(uint32_t i=0;i<n;i++){
            crc^=(unsigned)(i==0x46||i==0x47?0:vms[i])<<8;
            for(unsigned bit=0;bit<8;bit++)crc=((crc<<1)^((crc&0x8000)?0x1021u:0))&65535u;
        }
        if(crc!=expected)return 0;
    }
    /* Original events may leave CRC0 unused. No encrypted payload is read
     * here for validation; its original guest parser remains authoritative. */
    return 1;
}
static int32_t overlay_read(const char *name,void *dst,uint32_t cap){
    if(same(name,canonical)){uint32_t n=image_bytes<cap?image_bytes:cap;if(n)memcpy(dst,image,n);return (int32_t)n;}
    if(event_name(name))return -1;
    return base->read(name,dst,cap);
}
static int overlay_write(const char *name,const void *src,uint32_t n){
    if(event_name(name))return -1;
    int rc=base->write(name,src,n);listed_valid=0;return rc;
}
static int overlay_remove(const char *name){
    if(event_name(name))return -1;
    int rc=base->remove(name);listed_valid=0;return rc;
}
static void list_add(const char name[13],uint32_t size){
    memcpy(listed[listed_count].name,name,13);listed[listed_count++].size=size;
}
static int list_refresh(void){
    int inserted=0;listed_count=0;
    for(int i=0;i<=200;i++){
        char n[13]={0};uint32_t z=0;
        if(base->list(i,n,&z)!=0)break;
        /* A VMU contract has at most200 physical files. Never overrun the
         * fixed snapshot if a foreign backend violates that bound. */
        if(i==200){listed_count=0;return -1;}
        n[12]=0;
        if(!inserted&&strcmp(canonical,n)<0){list_add(canonical,image_bytes);inserted=1;}
        if(!event_name(n))list_add(n,z);
    }
    if(!inserted)list_add(canonical,image_bytes);
    listed_valid=1;return 0;
}
static int overlay_list(int index,char name[13],uint32_t *size){
    if(index<0||index>200)return -1;
    /* Index0 starts a fresh enumeration, so external directory changes are
     * observed. Later indices use one stable snapshot. Delegated writes
     * and removes invalidate even on failure (a backend may partly write). */
    if(index==0)listed_valid=0;
    if(!listed_valid&&list_refresh())return -1;
    if((unsigned)index>=listed_count)return -1;
    memcpy(name,listed[index].name,13);*size=listed[index].size;return 0;
}
static const vmu_store_ops overlay={overlay_read,overlay_write,overlay_remove,overlay_list};
int hle_content_count(void){return count;}
const char *hle_content_label(int index){return index>=0&&index<count?catalog[index].label:NULL;}
int hle_content_selected(void){return selected;}
const char *hle_content_status(void){
    if(selected>=0&&(hle_rd32(0x8c161cacu)!=0||hle_rd32(0x8c161ca8u)!=0))return "Selected; normal VMU selection required, then next level load";
    return status;
}
void hle_content_set_resuming(int value){resuming=value!=0;if(resuming){unmount();note("Off for saved-state resume");}}
int hle_content_select(int index){
    unmount();
    if(index==-1){note("Overlay off; base VMU unchanged, guest objects remain until unload");return 0;}
    if(index<0||index>=count){note("Rejected content selection");return -1;}
    if(hle_strict||resuming){note("Off in strict/resume mode");return -1;}
    if(!hle_vmu_store){note("Declined: normal VMU required");return -1;}
    uint32_t n,vn;uint8_t vmi[108];
    if(sa1_plat_file_size(catalog[index].vmi,&vn)||vn!=sizeof vmi||sa1_plat_file_size(catalog[index].vms,&n)
       ||n<1024||n>MAX_IMAGE||n%512){note("Rejected VMI/VMS size or block boundary");return -1;}
    image=malloc(n);
    if(!image){note("Content allocation failed");return -1;}
    if(sa1_plat_file_read(catalog[index].vmi,0,vmi,sizeof vmi)!=(int)sizeof vmi
       ||sa1_plat_file_read(catalog[index].vms,0,image,n)!=(int)n||!outer_valid(vmi,image,n)){
        unmount();note("Rejected VMI/VMS header, name, CRC or read");return -1;
    }
    image_bytes=n;selected=index;base=hle_vmu_store;hle_vmu_store=&overlay;
    note("Selected opaque event; activation on next ordinary level load");return 0;
}
int hle_dlc_setting(const char *key,const char *value,int cli){
    int event=!strcmp(key,"dlc_event"),legacy=!strcmp(key,"dlc_vms")||!strcmp(key,"dlc_vmi");
    if(!event&&!legacy)return 0;
    if(!cli&&config_cli)return 1;
    if(cli)config_cli=1;
    unmount();
    if(value&&(same(value,"off")||same(value,"none"))){strcpy(config,"off");config_bad=0;return 1;}
    size_t n=0;if(value)while(n<sizeof config&&value[n])n++;
    config_bad=!event||!value||!n||n>=sizeof config;
    for(size_t i=0;!config_bad&&i<n;i++)if((unsigned char)value[i]<32||(unsigned char)value[i]>126)config_bad=1;
    if(config_bad){note("Rejected explicit content selection setting");return -1;}
    memcpy(config,value,n+1);return 1;
}
void hle_dlc_start(void){
    unmount();if(read_catalog())return;
    if(config_bad){note("Rejected explicit content selection setting");return;}
    if(same(config,"off")||same(config,"none")){if(count)note("Off");return;}
    int index=-1;unsigned n=0;const char *p=config;
    while(*p>='0'&&*p<='9'&&n<MAX_EVENTS){n=n*10u+(unsigned)(*p-'0');p++;}
    if(!*p&&n<MAX_EVENTS)index=(int)n;
    else for(int i=0;i<count;i++)if(same(config,catalog[i].label)){index=i;break;}
    (void)hle_content_select(index>=0?index:-2);
}
