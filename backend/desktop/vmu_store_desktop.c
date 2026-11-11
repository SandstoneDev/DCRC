/* VMU durable journal adapter. Own implementation, MIT. */
#include "../vmu_transaction.h"
#include <errno.h>
#ifdef _WIN32
#include <windows.h>
#include <direct.h>
#include <io.h>
#else
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#endif
static char vmu_dir[1024];
static int io_path(char*p,size_t cap,const char*n){if(!vmu_dir[0])return -2;int z=snprintf(p,cap,"%s/%s",vmu_dir,n);return z<0||(size_t)z>=cap?-2:0;}
static int io_read(void*c,const char*n,void*b,uint32_t cap){
 (void)c;char p[1100];if(io_path(p,sizeof p,n))return -3;
 FILE*f=fopen(p,"rb");if(!f)return errno==ENOENT?-1:-3;
 int seek=fseek(f,0,SEEK_END);long z=ftell(f);int r=-3;
 if(!seek&&z>=0){if((uint64_t)z>cap)r=-2;else if(!fseek(f,0,SEEK_SET)){size_t got=fread(b,1,(size_t)z,f);if(!ferror(f)&&got==(size_t)z)r=(int)z;}}
 int closed=fclose(f);return closed?-3:r;
}
#ifndef _WIN32
/* Sync the directory entry as well as the file. Sync its parent too: this
 * covers a newly created VMU directory, not merely updates inside an old one. */
static int sync_directory(const char *path) {
    int fd=open(path,O_RDONLY);
    if(fd<0)return -1;
    int flushed=fsync(fd),closed=close(fd);
    return flushed||closed?-1:0;
}
static int sync_store_directory(void) {
    char parent[sizeof vmu_dir];
    memcpy(parent,vmu_dir,strlen(vmu_dir)+1);
    size_t n=strlen(parent);
    while(n>1&&parent[n-1]=='/')parent[--n]=0;
    char *slash=strrchr(parent,'/');
    if(!slash)memcpy(parent,".",2);
    else if(slash==parent)slash[1]=0;
    else *slash=0;
    int child=sync_directory(vmu_dir),outer=sync_directory(parent);
    return child||outer?-1:0;
}
#endif
static int io_write(void*c,const char*n,const void*b,uint32_t z){(void)c;char p[1100];if(io_path(p,sizeof p,n))return -2;FILE*f=fopen(p,"wb");if(!f)return -2;int ok=fwrite(b,1,z,f)==z;int flush=fflush(f);
#ifdef _WIN32
 int sync=_commit(_fileno(f));
#else
 int sync=fsync(fileno(f));
#endif
 int closed=fclose(f);
#ifndef _WIN32
 int ds=sync_store_directory();
 ok=ok&&ds==0;
#endif
 return ok&&flush==0&&sync==0&&closed==0?0:-2;}
static int io_remove(void*c,const char*n){(void)c;char p[1100];return io_path(p,sizeof p,n)?-2:remove(p);}
static int list_valid;
static const vt_io storage={NULL,io_read,io_write,io_remove};
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
 if(index==0||!list_valid){list_valid=0;n=0;
#ifdef _WIN32
    char pattern[1100];snprintf(pattern,sizeof pattern,"%s/*",vmu_dir);
    WIN32_FIND_DATAA data;HANDLE d=FindFirstFileA(pattern,&data);
    if(d==INVALID_HANDLE_VALUE) {
        DWORD error=GetLastError(),attrs=GetFileAttributesA(vmu_dir);
        if(error!=ERROR_FILE_NOT_FOUND||attrs==INVALID_FILE_ATTRIBUTES||!(attrs&FILE_ATTRIBUTE_DIRECTORY))return -2;
    } else {
        int scan_error=0;
        do {
            if(!(data.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY)&&add_entry(e,&n,data.cFileName)) {scan_error=-2;break;}
        } while(FindNextFileA(d,&data));
        DWORD error=GetLastError();BOOL closed=FindClose(d);
        if(scan_error||!closed||error!=ERROR_NO_MORE_FILES)return -2;
    }
#else
    DIR *d=opendir(vmu_dir);
    if(!d)return -2;
    int scan_error=0;
    for(;;) {
        errno=0;
        struct dirent *de=readdir(d);
        if(!de) {if(errno)scan_error=-2;break;}
        if(add_entry(e,&n,de->d_name)) {scan_error=-2;break;}
    }
    int closed=closedir(d);
    if(scan_error||closed)return -2;
#endif
qsort(e,(size_t)n,sizeof *e,cmp_entry);list_valid=1;
 }
 if(index>=n)return -1;
 memset(name,0,13);memcpy(name,e[index].name,strlen(e[index].name));*size=e[index].size;return 0;}
static const vmu_store_ops desktop_ops={st_read,st_write,st_remove,st_list,st_stat,st_typed};
void vmu_store_desktop_init(const char *dir) {
    list_valid=0;
    if (dir) {
        size_t z=strlen(dir);
        if(z>=sizeof vmu_dir) {vmu_dir[0]=0;hle_vmu_store=&desktop_ops;return;}
        memcpy(vmu_dir,dir,z+1);
    }
    else {
        char exe[1024] = "";
#ifdef _WIN32
        GetModuleFileNameA(NULL, exe, sizeof exe);
#else
        ssize_t r = readlink("/proc/self/exe", exe, sizeof exe - 1);
        exe[r > 0 ? r : 0] = 0;
#endif
        char *slash = strrchr(exe, '/'), *bs = strrchr(exe, '\\');
        if (bs && (!slash || bs > slash)) slash = bs;
        if (slash) {
            size_t z=(size_t)(slash-exe);
            if(z+5>sizeof vmu_dir) {vmu_dir[0]=0;hle_vmu_store=&desktop_ops;return;}
            memcpy(vmu_dir,exe,z);memcpy(vmu_dir+z,"/vmu",5);
        }
        else snprintf(vmu_dir, sizeof vmu_dir, "vmu");
    }
#ifdef _WIN32
    _mkdir(vmu_dir);
#else
    mkdir(vmu_dir, 0777);
#endif
    hle_vmu_store = &desktop_ops;
}

const char *vmu_store_desktop_dir(void) { return vmu_dir; }
