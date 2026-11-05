/* Synthetic opaque VMU content contracts. No game files/decoder. MIT. */
#include "../../hle/hle.h"
#include "../../hle/game/content_mount.h"
#include "../../hle/game/dlc_event.h"
#include "../../hle/shinobi/vmu_store.h"
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <stdlib.h>
#include <assert.h>
static unsigned checks;
#define CK(x) do { assert(x); ++checks; } while (0)
static uint8_t ram[SA1_RAM_SIZE+SA1_RAM_EXTRA];
uint8_t *const sa1_ram=ram;
int hle_strict;
const vmu_store_ops *hle_vmu_store;
void sa1_log(const char *fmt,...) { (void)fmt; }
static char manifest[20000];
static uint8_t avmi[108],bvmi[108],avms[1024],bvms[1536];
static int fail_read,base_writes,base_removes;
static uint32_t a_size_override,vmi_size_override;
static int stress,stress_count=200,stress_changed,base_lists,fail_write,fail_remove;
static const char *names[]={"A_SAVE","SONICADV_505","SONICADV_599","SONICADV_ALF","Z_SAVE"};
static int32_t base_read(const char *n,void *b,uint32_t cap) {
 for(unsigned i=0;i<5;i++) if(!strcmp(n,names[i])) { if(cap) ((uint8_t*)b)[0]=(uint8_t)(40+i);return cap?1:0; }
 return -1;
}
static int base_write(const char *n,const void *b,uint32_t z) { (void)n;(void)b;(void)z;base_writes++;if(stress)stress_changed=1;return fail_write?-1:0; }
static int base_remove(const char *n) { (void)n;base_removes++;if(stress)stress_count--;return fail_remove?-1:0; }
static int base_list(int i,char n[13],uint32_t *z) { if(stress){base_lists++;if(i<0||i>=stress_count)return -1;snprintf(n,13,"A%03u_SAVE",(unsigned)i%1000u);*z=stress_changed?1024:512;return 0;}if(i<0||i>=5)return -1;strcpy(n,names[i]);*z=512;return 0; }
static const vmu_store_ops ops={base_read,base_write,base_remove,base_list};
static const void *file(const char *p,uint32_t *z) {
 if(!strcmp(p,"dlc/events.txt")){*z=(uint32_t)strlen(manifest);return manifest;}
 if(!strcmp(p,"dlc/a.vmi")){*z=sizeof avmi;return avmi;}
 if(!strcmp(p,"dlc/b.vmi")){*z=sizeof bvmi;return bvmi;}
 if(!strcmp(p,"dlc/a.vms")){*z=sizeof avms;return avms;}
 if(!strcmp(p,"dlc/b.vms")){*z=sizeof bvms;return bvms;}
 return NULL;
}
int sa1_plat_file_size(const char *p,uint32_t *z) { if(!file(p,z))return -1;if(!strcmp(p,"dlc/a.vms")&&a_size_override)*z=a_size_override;if(!strcmp(p,"dlc/a.vmi")&&vmi_size_override)*z=vmi_size_override;return 0; }
int sa1_plat_file_read(const char *p,uint32_t off,void *b,uint32_t n) {
 uint32_t z;const uint8_t *s=file(p,&z);if(!s||off>z||n>z-off||fail_read)return -1;memcpy(b,s+off,n);return (int)n;
}
static void le16(uint8_t *p,unsigned x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static void le32(uint8_t *p,uint32_t x){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
static uint16_t crc(const uint8_t *p,unsigned n){unsigned c=0;for(unsigned i=0;i<n;i++){c^=(i==0x46||i==0x47?0:p[i])<<8;for(unsigned j=0;j<8;j++)c=((c<<1)^((c&0x8000)?0x1021u:0))&65535u;}return (uint16_t)c;}
static void fixtures(void){
 for(unsigned i=0;i<sizeof avms;i++)avms[i]=(uint8_t)(i*29u+3u);
 for(unsigned i=0;i<sizeof bvms;i++)bvms[i]=(uint8_t)(i*17u+91u);
 memset(avmi,0,sizeof avmi);memset(bvmi,0,sizeof bvmi);
 memcpy(avmi+88,"SONICADV_505",12);memcpy(bvmi+88,"SONICADV_506",12);
 le32(avmi+104,sizeof avms);le32(bvmi+104,sizeof bvms);
 le16(avms+0x40,1);le16(avms+0x44,0);le32(avms+0x48,sizeof avms-640);le16(avms+0x46,0);
 le16(bvms+0x40,1);le16(bvms+0x44,0);le32(bvms+0x48,sizeof bvms-640);le16(bvms+0x46,crc(bvms,sizeof bvms));
 strcpy(manifest,"# user-local catalog\r\nFirst | dlc/a.vmi | dlc/a.vms\r\nSecond|dlc/b.vmi|dlc/b.vms\n");
}
static void start_off(void){CK(hle_dlc_setting("dlc_event","off",1)==1);hle_dlc_start();CK(hle_content_selected()==-1);CK(hle_vmu_store==&ops);}
static void rejected(void){CK(hle_content_select(0)<0);CK(hle_content_selected()==-1);CK(hle_vmu_store==&ops);}
int main(void){
 fixtures();hle_vmu_store=&ops;hle_content_set_resuming(0);
 CK(hle_dlc_setting("unrelated","0",0)==0);
 hle_dlc_start();CK(hle_content_count()==2);CK(hle_content_selected()==-1);
 CK(!strcmp(hle_content_label(0),"First"));CK(hle_content_label(-1)==NULL);CK(hle_content_label(2)==NULL);
 CK(hle_dlc_setting("dlc_event","First",0)==1);hle_dlc_start();CK(hle_content_selected()==0);CK(hle_vmu_store!=&ops);
 uint8_t got[2048];memset(got,0,sizeof got);
 CK(hle_vmu_store->read("SONICADV_505",got,sizeof got)==sizeof avms);CK(!memcmp(got,avms,sizeof avms));
 memset(got,0,sizeof got);CK(hle_vmu_store->read("SONICADV_505",got,7)==7);CK(!memcmp(got,avms,7));
 CK(hle_vmu_store->read("SONICADV_599",got,sizeof got)<0);CK(hle_vmu_store->read("A_SAVE",got,1)==1&&got[0]==40);
 CK(hle_vmu_store->read("SONICADV_ALF",got,1)==1&&got[0]==43);
 const char *want[]={"A_SAVE","SONICADV_505","SONICADV_ALF","Z_SAVE"};char n[13];uint32_t z;
 for(int i=0;i<4;i++){CK(!hle_vmu_store->list(i,n,&z));CK(!strcmp(n,want[i]));CK(z==(i==1?sizeof avms:512));}
 CK(hle_vmu_store->list(-1,n,&z)<0);CK(hle_vmu_store->list(4,n,&z)<0);CK(hle_vmu_store->list(999,n,&z)<0);
 CK(hle_vmu_store->write("SONICADV_505",got,1)<0);CK(hle_vmu_store->write("sonicadv_599",got,1)<0);
 CK(hle_vmu_store->remove("SONICADV_505")<0);CK(hle_vmu_store->remove("SONICADV_599")<0);
 CK(base_writes==0&&base_removes==0);CK(hle_vmu_store->write("A_SAVE",got,1)==0);CK(hle_vmu_store->remove("SONICADV_ALF")==0);CK(base_writes==1&&base_removes==1);
 hle_wr32(0x8c161cacu,1);CK(strstr(hle_content_status(),"VMU")!=NULL);hle_wr32(0x8c161cacu,0);
 CK(hle_content_select(1)==0);CK(hle_content_selected()==1);CK(hle_vmu_store->read("SONICADV_505",got,sizeof got)<0);CK(hle_vmu_store->read("SONICADV_506",got,sizeof got)==sizeof bvms);CK(!memcmp(got,bvms,sizeof bvms));
 CK(hle_content_select(-1)==0);CK(hle_vmu_store==&ops);CK(hle_vmu_store->read("SONICADV_505",got,1)==1&&got[0]==41);CK(hle_vmu_store->read("SONICADV_599",got,1)==1&&got[0]==42);
 CK(hle_content_select(-1)==0);CK(hle_content_select(2)<0);CK(hle_vmu_store==&ops);
 CK(hle_content_select(0)==0);CK(hle_content_select(-2)<0);CK(hle_content_selected()==-1&&hle_vmu_store==&ops);
 hle_strict=1;rejected();hle_strict=0;CK(hle_content_select(0)==0);hle_content_set_resuming(1);CK(hle_content_selected()==-1&&hle_vmu_store==&ops);rejected();hle_content_set_resuming(0);
 hle_vmu_store=NULL;CK(hle_content_select(0)<0);CK(hle_vmu_store==NULL);hle_vmu_store=&ops;
 /* Every rejected container unmounts, without touching persistent saves. */
 vmi_size_override=107;rejected();vmi_size_override=0;
 const uint32_t badsize[]={1,512,1023,1025,102912,0xffffffffu};
 for(unsigned i=0;i<sizeof badsize/sizeof *badsize;i++){a_size_override=badsize[i];rejected();}a_size_override=0;
 CK(hle_content_select(1)==0);avmi[88]='X';rejected();avmi[88]='S';
 le32(avmi+104,1);rejected();le32(avmi+104,sizeof avms);
 le16(avms+0x40,2);rejected();le16(avms+0x40,1);
 le16(avms+0x44,1);rejected();le16(avms+0x44,0);
 le32(avms+0x48,1);rejected();le32(avms+0x48,sizeof avms-640);
 le16(avms+0x46,crc(avms,sizeof avms));CK(hle_content_select(0)==0);avms[900]^=1;rejected();avms[900]^=1;
 le16(avms+0x46,0);CK(hle_content_select(0)==0); /* Original unused CRC convention, opaque bytes retained. */
 fail_read=1;rejected();fail_read=0;
 /* Invalid CLI owns precedence; later valid CLI corrects it. */
 CK(hle_dlc_setting("dlc_event",NULL,1)<0);CK(hle_dlc_setting("dlc_event","First",0)==1);hle_dlc_start();CK(hle_content_selected()==-1);
 CK(hle_dlc_setting("dlc_event","1",1)==1);hle_dlc_start();CK(hle_content_selected()==1);
 CK(hle_dlc_setting("dlc_event","missing",1)==1);hle_dlc_start();CK(hle_content_selected()==-1);CK(strstr(hle_content_status(),"selection")!=NULL);
 CK(hle_dlc_setting("dlc_vms","dlc/a.vms",1)<0);hle_dlc_start();CK(hle_content_selected()==-1);
 start_off();
 const char *bad[]={"Bad|../a.vmi|dlc/a.vms\n","Bad|/a.vmi|dlc/a.vms\n","Bad|C:a.vmi|dlc/a.vms\n","Bad|dlc\\a.vmi|dlc/a.vms\n","Bad|dlc//a.vmi|dlc/a.vms\n","Bad|dlc/./a.vmi|dlc/a.vms\n","Bad|dlc/.. /a.vmi|dlc/a.vms\n","Bad|dlc/.../a.vmi|dlc/a.vms\n","Bad|dlc/a.vmi|dlc/a.vms|extra\n","Bad|dlc/a.vmi\n","|dlc/a.vmi|dlc/a.vms\n","Bad|dlc/a.vmi|dlc/a.vms\nBad|dlc/b.vmi|dlc/b.vms\n"};
 for(unsigned i=0;i<sizeof bad/sizeof *bad;i++){strcpy(manifest,bad[i]);hle_dlc_start();CK(hle_content_count()==0);CK(hle_content_selected()==-1);}
 fixtures();manifest[0]=(char)0xff;hle_dlc_start();CK(hle_content_count()==0);
 manifest[0]=0;for(int i=0;i<33;i++){char line[100];snprintf(line,sizeof line,"Event%d|dlc/a.vmi|dlc/a.vms\n",i);strcat(manifest,line);}hle_dlc_start();CK(hle_content_count()==0);
 manifest[0]=0;for(int i=0;i<32;i++){char line[100];snprintf(line,sizeof line,"Event%d|dlc/a.vmi|dlc/a.vms\n",i);strcat(manifest,line);}hle_dlc_start();CK(hle_content_count()==32);CK(hle_content_select(31)==0);start_off();
 char label[65],path[257];memset(label,'L',63);label[63]=0;memset(path,'P',255);path[255]=0;
 snprintf(manifest,sizeof manifest,"%s|%s|dlc/a.vms\n",label,path);hle_dlc_start();CK(hle_content_count()==1);
 path[255]='P';path[256]=0;snprintf(manifest,sizeof manifest,"First|%s|dlc/a.vms\n",path);hle_dlc_start();CK(hle_content_count()==0);
 label[63]='L';label[64]=0;snprintf(manifest,sizeof manifest,"%s|dlc/a.vmi|dlc/a.vms\n",label);hle_dlc_start();CK(hle_content_count()==0);
 memset(manifest,'A',700);manifest[700]=0;hle_dlc_start();CK(hle_content_count()==0);
 fixtures();start_off();CK(hle_content_count()==2);CK(base_writes==1&&base_removes==1);
 /* At200 real VMU files each backend list call can rescan/sort the directory.
  * One complete overlay enumeration must not cause quadratically many calls. */
 stress=1;CK(hle_content_select(0)==0);base_lists=0;
 for(int i=0;i<201;i++)CK(hle_vmu_store->list(i,n,&z)==0);
 CK(hle_vmu_store->list(201,n,&z)<0);
 printf("base-list calls for201 entries: %d\n",base_lists);fflush(stdout);
 CK(base_lists<=201);
 stress_changed=1;CK(hle_vmu_store->list(0,n,&z)==0&&z==1024);CK(base_lists<=402);
 stress_changed=0;CK(hle_vmu_store->list(0,n,&z)==0&&z==512);CK(base_lists<=603);
 CK(hle_vmu_store->write("A000_SAVE",got,1)==0);
 CK(hle_vmu_store->list(5,n,&z)==0&&z==1024);CK(base_lists<=804);
 CK(hle_vmu_store->remove("A199_SAVE")==0);
 CK(hle_vmu_store->list(199,n,&z)==0&&!strcmp(n,"SONICADV_505"));CK(hle_vmu_store->list(200,n,&z)<0);CK(base_lists<=1004);
 stress_changed=0;CK(hle_vmu_store->list(0,n,&z)==0&&z==512);
 fail_write=1;CK(hle_vmu_store->write("A000_SAVE",got,1)<0);fail_write=0;
 CK(hle_vmu_store->list(5,n,&z)==0&&z==1024);
 fail_remove=1;CK(hle_vmu_store->remove("A198_SAVE")<0);fail_remove=0;
 CK(hle_vmu_store->list(198,n,&z)==0&&!strcmp(n,"SONICADV_505"));CK(hle_vmu_store->list(199,n,&z)<0);
 stress_count=201;CK(hle_vmu_store->list(0,n,&z)<0); /* Foreign contract violation declines, stays bounded. */
 stress_count=200;CK(hle_vmu_store->list(0,n,&z)==0);
 CK(hle_content_select(-1)==0&&hle_vmu_store==&ops);
 printf("PASS %u opaque-content checks; no payload decoder/game bytes\n",checks);
 return 0;
}
