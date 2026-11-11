/* VMU durable journal adapter. Own implementation, MIT. */
#include "../vmu_transaction.h"
#include "vmu_default_path.h"
#include <unistd.h>
#include <pspiofilemgr.h>
#define VMU_ENOENT ((int)0x80010002u)
#define VMU_EEXIST ((int)0x80010011u)

static char vmu_dir[300];
static int io_path(char *path,size_t cap,const char *dir,const char *name){
    if(!dir[0])return -2;
    int n=snprintf(path,cap,"%s/%s",dir,name);
    return n<0||(size_t)n>=cap?-2:0;
}
static int io_read(void*c,const char*n,void*b,uint32_t cap){
 char p[350];if(io_path(p,sizeof p,c,n))return -3;SceIoStat s;int sr=sceIoGetstat(p,&s);if(sr<0)return sr==VMU_ENOENT?-1:-3;
 if(s.st_size<0||(uint64_t)s.st_size>cap)return -2;
 SceUID f=sceIoOpen(p,PSP_O_RDONLY,0);if(f<0)return -3;
 int z=sceIoRead(f,b,(unsigned)s.st_size);int closed=sceIoClose(f);return closed<0||z!=s.st_size?-3:z;
}
static int vmu_write(const char *dir,const char *name,const void *buf,uint32_t bytes,int flags){
    char path[350];
    if(io_path(path,sizeof path,dir,name))return -2;
    SceUID file=sceIoOpen(path,PSP_O_WRONLY|PSP_O_CREAT|flags,0777);
    if(file<0)return file;
    int written=sceIoWrite(file,buf,bytes);
    int closed=sceIoClose(file);
    if(written!=(int)bytes || closed<0)return written<0?written:closed<0?closed:-2;
    char device[32];
    size_t colon=strcspn(dir,":");
    if(dir[colon]!=':' || colon+1>=sizeof device)return -2;
    memcpy(device,dir,colon+1);
    device[colon+1]='\0';
    return sceIoSync(device,0);
}
static int io_write(void*c,const char*n,const void*b,uint32_t z){
    return vmu_write(c,n,b,z,PSP_O_TRUNC)<0?-2:0;
}
static int io_remove(void*c,const char*n){char p[350];return io_path(p,sizeof p,c,n)?-2:sceIoRemove(p);}
static int list_valid;
static const vt_io storage={vmu_dir,io_read,io_write,io_remove};

/* Report absence only for the SDK's definite ENOENT. */
static int vmu_directory(const char *path,int *raw){
    SceIoStat stat={0};
    *raw=sceIoGetstat(path,&stat);
    if(*raw==VMU_ENOENT)return 0;
    if(*raw<0)return -1;
    return FIO_S_ISDIR(stat.st_mode)?1:-2;
}

static int vmu_ensure_parent(const char *path,int *raw){
    int state=vmu_directory(path,raw);
    if(state)return state;
    *raw=sceIoMkdir(path,0777);
    if(*raw<0 && *raw!=VMU_EEXIST)return -1;
    state=vmu_directory(path,raw);
    return state?state:-1;
}

static int vmu_read_entry(SceUID dir,SceIoDirent *entry){
    memset(entry,0,sizeof *entry);
    int result=sceIoDread(dir,entry);
    entry->d_name[sizeof entry->d_name-1]='\0';
    return result;
}

static int vmu_stage_legacy(const char *legacy,const char *stage,int *raw){
    SceUID dir=sceIoDopen(legacy);
    if(dir<0){*raw=dir;return -1;}
    unsigned char *copy=NULL;
    int result=0;
    int read;
    SceIoDirent entry;
    while((read=vmu_read_entry(dir,&entry))>0){
        char name[13];
        if(!vt_candidate(entry.d_name,name))continue;
        /* Keep both journal generations and compatibility exports. Reading
         * just the active VMU entry would lose tombstones and recovery data. */
        if(!FIO_S_ISREG(entry.d_stat.st_mode)){*raw=-2;result=-1;break;}
        if(!copy){
            copy=malloc(2*VT_CAP);
            if(!copy){*raw=-2;result=-1;break;}
        }
        int bytes=io_read((void *)legacy,entry.d_name,copy,VT_CAP);
        if(bytes<0){*raw=bytes;result=-1;break;}
        *raw=vmu_write(stage,entry.d_name,copy,(uint32_t)bytes,PSP_O_EXCL);
        if(*raw<0){result=-1;break;}
        int checked=io_read((void *)stage,entry.d_name,copy+VT_CAP,VT_CAP);
        if(checked!=bytes || memcmp(copy,copy+VT_CAP,(size_t)bytes)){
            *raw=checked<0?checked:-2;
            result=-1;
            break;
        }
        result=1;
    }
    if(read<0){*raw=read;result=-1;}
    int closed=sceIoDclose(dir);
    if(closed<0){*raw=closed;result=-1;}
    free(copy);
    return result;
}

/* stage is a directory this call created exclusively. Only remove its own
 * flat VMU copies, leaving unexpected entries and interrupted prior stages. */
static void vmu_discard_stage(const char *stage){
    SceUID dir=sceIoDopen(stage);
    if(dir<0)return;
    SceIoDirent entry;
    while(vmu_read_entry(dir,&entry)>0){
        char name[13],path[350];
        if(FIO_S_ISREG(entry.d_stat.st_mode) && vt_candidate(entry.d_name,name) &&
           !io_path(path,sizeof path,stage,entry.d_name))sceIoRemove(path);
    }
    if(sceIoDclose(dir)<0)return;
    dir=sceIoDopen(stage);
    if(dir<0)return;
    int read;
    while((read=vmu_read_entry(dir,&entry))>0)
        if(strcmp(entry.d_name,".") && strcmp(entry.d_name,".."))break;
    if(sceIoDclose(dir)==0 && read==0)sceIoRmdir(stage);
}

int vmu_default_path(char *out,size_t cap,const char *base,int *raw){
    *raw=0;
    const char *device=NULL;
    if(!strncmp(base,"ms0:/",5))device="ms0:";
    else if(!strncmp(base,"ef0:/",5))device="ef0:";
    if(!device){
        int n=snprintf(out,cap,"%s/vmu",base);
        return n<0||(size_t)n>=cap?-3:0;
    }

    char psp[12],parent[36],legacy[300],stage[80];
    snprintf(psp,sizeof psp,"%s/PSP",device);
    snprintf(parent,sizeof parent,"%s/DCRC_SAVES",psp);
    if(io_path(out,cap,parent,"SA1_US_1005"))return -3;
    int state=vmu_directory(out,raw);
    if(state)return state;
    if(io_path(legacy,sizeof legacy,base,"vmu"))return -3;
    int legacy_state=vmu_directory(legacy,raw);
    if(legacy_state<0)return legacy_state;
    state=vmu_ensure_parent(psp,raw);
    if(state<0)return state;
    state=vmu_ensure_parent(parent,raw);
    if(state<0)return state;

    unsigned slot;
    for(slot=0;slot<32;slot++){
        snprintf(stage,sizeof stage,"%s/DCRC_VMU_STAGE_%02u",parent,slot);
        *raw=sceIoMkdir(stage,0777);
        if(*raw==0)break;
        if(*raw!=VMU_EEXIST)return -1;
    }
    if(slot==32)return -1;
    int copied=legacy_state?vmu_stage_legacy(legacy,stage,raw):0;
    if(copied<0){vmu_discard_stage(stage);return -1;}

    /* Publish only a fully checked directory, on the same PSP device and in
     * the same parent. A concurrent destination wins without modification. */
    state=vmu_directory(out,raw);
    if(state){vmu_discard_stage(stage);return state;}
    *raw=sceIoRename(stage,out);
    if(*raw<0){
        int collision=*raw==VMU_EEXIST;
        vmu_discard_stage(stage);
        if(collision && vmu_directory(out,raw)==1)return 1;
        return -1;
    }
    *raw=sceIoSync(device,0);
    if(*raw<0)return -1;
    state=vmu_directory(out,raw);
    return state==1?2+copied:state<0?state:-1;
}

static int32_t st_read(const char*n,void*b,uint32_t max){return vt_read(&storage,n,b,max);}
static int st_stat(const char*n,vmu_file_info*i){return vt_stat(&storage,n,i);}
static int st_typed(const char*n,const void*b,uint32_t z,const vmu_file_info*i){list_valid=0;if(!i||z!=i->size)return -2;return vt_commit(&storage,n,b,i,0);}
static int st_write(const char*n,const void*b,uint32_t z){vmu_file_info i={z,VMU_STORE_DATA,0,0};return st_typed(n,b,z,&i);}
static int st_remove(const char*n){list_valid=0;return vt_commit(&storage,n,NULL,NULL,1);}
typedef struct {char name[13];uint32_t size;} entry;
static int cmp_entry(const void*a,const void*b){return strcmp(((const entry*)a)->name,((const entry*)b)->name);}
/* Only absence/tombstones may be skipped. A corrupt/uncertain file must
 * invalidate the entire snapshot, otherwise HLE would invent free blocks. */
static int add_entry(entry *e,int *count,const char *f) {
    char name[13];
    if(!vt_candidate(f,name))return 0;
    for(int j=0;j<*count;j++)if(!strcmp(e[j].name,name))return 0;
    vmu_file_info info;
    int status=vt_stat(&storage,name,&info);
    if(status==-1)return 0;
    if(status||*count>=200)return -2;
    memcpy(e[*count].name,name,strlen(name)+1);
    e[*count].size=info.size;
    (*count)++;
    return 0;
}
/* index0 starts a stable enumeration. Mutations and mount/init invalidate;
 * external filesystem writers are observed at the next index0 refresh.
 * read/stat remain live. The synchronous HLE serializes enumeration. */
static int st_list(int index,char name[13],uint32_t*size){
 static entry e[200];static int n;
 if(index<0)return -1;
 if(!vmu_dir[0])return -2; /* failed mount must not enumerate the current directory */
 if(index==0||!list_valid){list_valid=0;n=0;
    SceUID d=sceIoDopen(vmu_dir);
    if(d<0)return -2;
    SceIoDirent de;memset(&de,0,sizeof de);
    int rd=0,scan_error=0;
    while((rd=sceIoDread(d,&de))>0) {
        if(!FIO_S_ISDIR(de.d_stat.st_mode)&&add_entry(e,&n,de.d_name)) {
            scan_error=-2;break;
        }
        memset(&de,0,sizeof de);
    }
    int closed=sceIoDclose(d);
    if(scan_error||rd<0||closed<0)return -2;
qsort(e,(size_t)n,sizeof *e,cmp_entry);list_valid=1;
 }
 if(index>=n)return -1;
 memset(name,0,13);memcpy(name,e[index].name,strlen(e[index].name));*size=e[index].size;return 0;}
static const vmu_store_ops psp_ops={st_read,st_write,st_remove,st_list,st_stat,st_typed};
void vmu_store_psp_init(const char *dir) {
    list_valid=0;
    if(!dir||strlen(dir)>=sizeof vmu_dir) {vmu_dir[0]=0;hle_vmu_store=&psp_ops;return;}
    if(strchr(dir,':')) memcpy(vmu_dir,dir,strlen(dir)+1);
    else {
        char cwd[300];
        if(!getcwd(cwd,sizeof cwd)||!strchr(cwd,':')) {vmu_dir[0]=0;hle_vmu_store=&psp_ops;return;}
        size_t a=strlen(cwd),b=strlen(dir);
        if(a+b+2>sizeof vmu_dir) {vmu_dir[0]=0;hle_vmu_store=&psp_ops;return;}
        memcpy(vmu_dir,cwd,a);vmu_dir[a]='/';memcpy(vmu_dir+a+1,dir,b+1);
    }
    sceIoMkdir(vmu_dir, 0777);
    hle_vmu_store = &psp_ops;
}

const char *vmu_store_psp_dir(void) { return vmu_dir; }
