/* Own bounded VMU transactions, MIT. Journals are the authority; VMS/VME are
 * compatibility exports. No rename dependency (host0 supports neither atomic
 * replace nor durable directory renames). A successful write means a synced,
 * reread COMMIT, even when exporting the compatibility file subsequently fails.
 * Single writer: callers must serialize operations on a store. */
#pragma once
#include "../hle/shinobi/vmu_store.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define VT_MAX 102400u
#define VT_HEAD 80u
#define VT_CAP (VT_MAX+VT_HEAD)
typedef struct {
 void *ctx;
 /* read: whole size, -1 absent, -2 oversized/malformed, -3 I/O error.
  * I/O uncertainty must abort selection, never overwrite an unread slot. */
 int (*read)(void*,const char*,void*,uint32_t);
 /* write must check every byte, close and storage sync before returning0. */
 int (*write)(void*,const char*,const void*,uint32_t);
 int (*remove)(void*,const char*);
} vt_io;
typedef struct {unsigned char *bytes;vmu_file_info info;uint64_t generation;int slot,deleted;} vt_value;
static uint32_t vt_u32(const unsigned char*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void vt_p32(unsigned char*p,uint32_t v){for(int i=0;i<4;i++)p[i]=(unsigned char)(v>>(8*i));}
static uint32_t vt_crc(const void*buf,uint32_t n){const unsigned char*p=buf;uint32_t c=~0u;while(n--){c^=*p++;for(int j=0;j<8;j++)c=(c>>1)^(0xedb88320u&-(c&1));}return ~c;}
static int vt_name(const char*n){if(!n)return 0;unsigned i;for(i=0;i<13&&n[i];i++){unsigned c=(unsigned char)n[i];if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'||c=='.'))return 0;}return i>0&&i<=12&&strcmp(n,".")&&strcmp(n,"..");}
static int vt_meta(const vmu_file_info*i){return i&&i->size&&i->size<=VT_MAX&&i->type<=1&& (i->copy_flag==0||i->copy_flag==255)&& (i->type==VMU_STORE_DATA?i->header_block==0:(i->header_block==1&&i->size>=1024&&i->size<=65536&&i->size%512==0));}
static void vt_path(char p[32],const char*n,const char*ext){snprintf(p,32,"%s.%s",n,ext);}
static void vt_free(vt_value*v){free(v->bytes);v->bytes=NULL;}
static void vt_pack(unsigned char*b,const char*n,const void*data,const vmu_file_info*i,uint64_t gen,int del,int committed){
 memset(b,0,VT_HEAD);memcpy(b,"DVMUTX01",8);vt_p32(b+8,1);vt_p32(b+12,committed?0x434f4d54u:0x50524550u);vt_p32(b+16,(uint32_t)gen);vt_p32(b+20,(uint32_t)(gen>>32));vt_p32(b+24,del);
 vt_p32(b+28,i->size);vt_p32(b+32,i->type);vt_p32(b+36,i->header_block);vt_p32(b+40,i->copy_flag);memcpy(b+44,n,strlen(n));
 if(i->size)memcpy(b+VT_HEAD,data,i->size);
 vt_p32(b+60,vt_crc(b+VT_HEAD,i->size));vt_p32(b+64,vt_crc(b,64));
}
static int vt_unpack(unsigned char*b,int len,const char*n,vt_value*v){
 if(len<(int)VT_HEAD||memcmp(b,"DVMUTX01",8)||vt_u32(b+8)!=1||vt_u32(b+12)!=0x434f4d54u||vt_u32(b+64)!=vt_crc(b,64))return -2;
 char name[16]={0};memcpy(name,n,strlen(n));if(memcmp(b+44,name,16))return -2;
 for(int k=68;k<80;k++)if(b[k])return -2;
 v->generation=vt_u32(b+16)|((uint64_t)vt_u32(b+20)<<32);v->deleted=(int)vt_u32(b+24);v->info=(vmu_file_info){vt_u32(b+28),vt_u32(b+32),vt_u32(b+36),vt_u32(b+40)};
 if(!v->generation||v->deleted<0||v->deleted>1|| (v->deleted?(v->info.size||v->info.type||v->info.header_block||v->info.copy_flag):!vt_meta(&v->info)))return -2;
 if(v->info.size>VT_MAX||len!=(int)(VT_HEAD+v->info.size)||vt_u32(b+60)!=vt_crc(b+VT_HEAD,v->info.size))return -2;
 return 0;
}
/* Legacy .tmp has no journal identity. Adopt only complete VMS with its own
 * exact extent and CRC16, never because it happens to be larger. */
static int vt_vms(const unsigned char*b,int n){
 if(n<128)return 0;
 unsigned icons=b[64]|b[65]<<8,eye=b[68]|b[69]<<8;static const unsigned ez[]={0,0x1f80,0x11c0,0x800};
 if(icons<1||icons>3||eye>3)return 0;
 uint32_t len=128+icons*512+ez[eye],data=vt_u32(b+72);if(data>VT_MAX||len>VT_MAX-data)return 0;len+=data;if(((len+511)&~511u)!=(unsigned)n)return 0;
 unsigned crc=0;for(unsigned k=0;k<len;k++){crc^=(unsigned)((k==70||k==71)?0:b[k])<<8;for(int j=0;j<8;j++)crc=(crc&0x8000)?((crc<<1)^0x1021)&65535:(crc<<1)&65535;}return crc==(unsigned)(b[70]|b[71]<<8);
}
static int vt_load(const vt_io*io,const char*n,vt_value*out){
 memset(out,0,sizeof *out);out->slot=-1;if(!vt_name(n))return -2;
 unsigned char*b=malloc(VT_CAP);if(!b)return -2;int bad=0;char p[32];
 for(int s=0;s<2;s++){
  vt_path(p,n,s?"VMJ1":"VMJ0");int len=io->read(io->ctx,p,b,VT_CAP);if(len==-1)continue;if(len==-3){free(b);vt_free(out);return -2;}vt_value v={0};
  if(len<0||vt_unpack(b,len,n,&v)){bad=1;continue;}
  if(out->slot>=0&&v.generation==out->generation){free(b);vt_free(out);return -2;}
  if(out->slot<0||v.generation>out->generation){unsigned char*q=malloc(v.info.size?v.info.size:1);if(!q){free(b);vt_free(out);return -2;}memcpy(q,b+VT_HEAD,v.info.size);vt_free(out);*out=v;out->bytes=q;out->slot=s;}
 }
 if(out->slot>=0){free(b);return out->deleted?-1:0;}
 /* No valid journal: legacy DATA remains compatible. A typed export must
  * independently validate, and competing kinds fail closed. */
 vt_path(p,n,"VME");int en=io->read(io->ctx,p,b,VT_CAP);vt_value ev={0};if(en==-3){free(b);return -2;}int exec_ok=en>=0&&!vt_unpack(b,en,n,&ev)&&!ev.deleted&&ev.info.type==VMU_STORE_EXEC;
 unsigned char*eb=NULL;if(exec_ok){eb=malloc(ev.info.size);if(!eb){free(b);return -2;}memcpy(eb,b+VT_HEAD,ev.info.size);}
 vt_path(p,n,"VMS");int len=io->read(io->ctx,p,b,VT_MAX);if(len==-3){free(eb);free(b);return -2;}int primary_good=len>0;
 if(en!=-1){if(!exec_ok||len!=-1){free(eb);free(b);return -2;}*out=ev;out->slot=-1;out->bytes=eb;free(b);return 0;}
 vt_path(p,n,"VMS.tmp");unsigned char*t=malloc(VT_MAX);if(!t){free(b);return -2;}int tn=io->read(io->ctx,p,t,VT_MAX);if(tn==-3){free(t);free(b);return -2;}
 if(tn!=-1){int pg=primary_good&&vt_vms(b,len),tg=tn>0&&vt_vms(t,tn);if(pg&&tg&&(len!=tn||memcmp(b,t,(size_t)len))){free(t);free(b);return -2;}if(!pg){if(!tg){free(t);free(b);return -2;}memcpy(b,t,tn);len=tn;primary_good=1;}}
 free(t);if(bad&&primary_good&&!vt_vms(b,len)){free(b);return -2;}if(!primary_good){free(b);return len==-1&&!bad?-1:-2;}
 out->bytes=b;out->info=(vmu_file_info){(uint32_t)len,VMU_STORE_DATA,0,0};return 0;
}
static int vt_stat(const vt_io*io,const char*n,vmu_file_info*i){vt_value v;int r=vt_load(io,n,&v);if(!r)*i=v.info;vt_free(&v);return r;}
static int32_t vt_read(const vt_io*io,const char*n,void*b,uint32_t max){vt_value v;int r=vt_load(io,n,&v);if(!r){uint32_t z=v.info.size<max?v.info.size:max;if(z)memcpy(b,v.bytes,z);r=(int)z;}vt_free(&v);return r;}
static int vt_commit(const vt_io*io,const char*n,const void*data,const vmu_file_info*i,int del){
 if(!vt_name(n)||(!del&&(!vt_meta(i)||!data)))return -2;
 vt_value old;int r=vt_load(io,n,&old);
 if(r==-2){vt_free(&old);return -2;}if(del&&r){vt_free(&old);return -1;}if(!del&&!r&&old.info.type!=i->type){vt_free(&old);return -2;}
 uint64_t gen=old.generation;if(gen==UINT64_MAX){vt_free(&old);return -2;}int slot=old.slot==0?1:0;vt_free(&old);gen++;
 vmu_file_info zero={0};if(del)i=&zero;unsigned char*b=malloc(VT_HEAD+i->size),*check=malloc(VT_HEAD+i->size);if(!b||!check){free(b);free(check);return -2;}
 char p[32];vt_path(p,n,slot?"VMJ1":"VMJ0");vt_pack(b,n,data,i,gen,del,0);
 if(io->write(io->ctx,p,b,VT_HEAD+i->size))goto fail;
 if(io->read(io->ctx,p,check,VT_HEAD+i->size)!=(int)(VT_HEAD+i->size)||memcmp(b,check,VT_HEAD+i->size))goto fail;
 vt_pack(b,n,data,i,gen,del,1);if(io->write(io->ctx,p,b,VT_HEAD+i->size))goto fail;
 if(io->read(io->ctx,p,check,VT_HEAD+i->size)!=(int)(VT_HEAD+i->size)||memcmp(b,check,VT_HEAD+i->size))goto fail;
 /* Durable authority is established. Export/cleanup failure cannot turn a
  * committed transaction into a reported failed write. */
 if(del){const char*ext[]={"VMS","VME","VMS.tmp"};for(unsigned k=0;k<3;k++){vt_path(p,n,ext[k]);io->remove(io->ctx,p);}}
 else{vt_path(p,n,i->type==VMU_STORE_EXEC?"VME":"VMS");io->write(io->ctx,p,i->type==VMU_STORE_EXEC?b:(const unsigned char*)data,i->size+(i->type==VMU_STORE_EXEC?VT_HEAD:0));}
 free(b);free(check);return 0;
fail:free(b);free(check);return -2;
}
/* Enumerators use this for all physical representations, then vt_stat and
 * deduplication: a tombstone never appears as a live directory entry. */
static int vt_suffix(const char*a,const char*b){while(*a&&*b){unsigned x=(unsigned char)*a++,y=(unsigned char)*b++;if(x>='a'&&x<='z')x-=32;if(y>='a'&&y<='z')y-=32;if(x!=y)return 0;}return !*a&&!*b;}
static int vt_candidate(const char*f,char n[13]){size_t z=strlen(f);const char*ext[]={".VMS",".VME",".VMJ0",".VMJ1",".VMS.tmp"};for(unsigned k=0;k<5;k++){size_t e=strlen(ext[k]);if(z>e&&z-e<=12&&vt_suffix(f+z-e,ext[k])){memcpy(n,f,z-e);n[z-e]=0;return vt_name(n);}}return 0;}
