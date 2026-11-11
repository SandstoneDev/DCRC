/* Own host substitutes for public PSP call shapes, not firmware code. MIT. */
#include <stdint.h>
#include <stddef.h>
typedef int SceUID,SceInt32;
typedef unsigned SceUInt;
typedef size_t SceSize;
typedef int64_t SceOff;
typedef void *ScePVoid,*SceMpeg;
typedef void SceMpegStream;
typedef struct {uint32_t unused;} SceMpegRingbuffer;
typedef struct {uint32_t iPts;} SceMpegAu;
typedef struct {int iUnk0,iPixelFormat;} SceMpegAvcMode;
typedef struct {uint32_t Buttons;} SceCtrlData;
#define PSP_O_RDONLY 0
#define PSP_SEEK_SET 0
#define PSP_SEEK_END 2
#define PSP_SMEM_High 1
#define PSP_AUDIO_NEXT_CHANNEL -1
#define PSP_AUDIO_FORMAT_STEREO 0
#define PSP_AUDIO_VOLUME_MAX 32768
#define PSP_MODULE_AV_AVCODEC 1
#define PSP_MODULE_AV_MPEGBASE 2
#define SCE_MPEG_AVC_FORMAT_5650 0
#define PSP_CTRL_CROSS 1u
#define PSP_CTRL_START 2u
void sa1_log(const char *,...);
uint64_t sceKernelGetSystemTimeWide(void);
int sceKernelDelayThread(unsigned);
unsigned sceKernelCpuSuspendIntr(void);
void sceKernelCpuResumeIntr(unsigned);
int sceIoOpen(const char *,int,int);
SceOff sceIoLseek(int,SceOff,int);
int sceIoRead(int,void *,unsigned);
int sceIoClose(int);
int sceKernelAllocPartitionMemory(int,const char *,int,unsigned,void *);
void *sceKernelGetBlockHeadAddr(int);
int sceKernelFreePartitionMemory(int);
void sceKernelDcacheWritebackRange(const void *,unsigned);
void sceKernelDcacheWritebackInvalidateRange(const void *,unsigned);
void sceKernelDcacheInvalidateRange(const void *,unsigned);
int sceKernelCreateThread(const char *,int (*)(SceSize,void *),int,unsigned,int,void *);
int sceKernelStartThread(int,SceSize,void *);
int sceKernelWaitThreadEnd(int,unsigned *);
int sceKernelDeleteThread(int);
int sceAudioChReserve(int,unsigned,int);
int sceAudioChRelease(int);
int sceAudioGetChannelRestLen(int);
int sceAudioOutputPannedBlocking(int,int,int,void *);
int sceUtilityLoadModule(int);
int sceUtilityUnloadModule(int);
int sceMpegInit(void);
void sceMpegFinish(void);
int sceMpegQueryMemSize(int);
int sceMpegRingbufferQueryMemSize(int);
int sceMpegRingbufferConstruct(SceMpegRingbuffer *,int,void *,int,int (*)(void *,int,void *),void *);
void sceMpegRingbufferDestruct(SceMpegRingbuffer *);
int sceMpegCreate(SceMpeg *,void *,int,SceMpegRingbuffer *,int,int,int);
void sceMpegDelete(SceMpeg *);
int sceMpegAvcDecodeMode(SceMpeg *,SceMpegAvcMode *);
int sceMpegQueryStreamOffset(SceMpeg *,void *,int *);
int sceMpegQueryStreamSize(void *,int *);
SceMpegStream *sceMpegRegistStream(SceMpeg *,int,int);
void sceMpegUnRegistStream(SceMpeg,SceMpegStream *);
void *sceMpegMallocAvcEsBuf(SceMpeg *);
void sceMpegFreeAvcEsBuf(SceMpeg *,void *);
int sceMpegInitAu(SceMpeg *,void *,SceMpegAu *);
int sceMpegFlushAllStream(SceMpeg *);
int sceMpegRingbufferAvailableSize(SceMpegRingbuffer *);
int sceMpegRingbufferPut(SceMpegRingbuffer *,int,int);
int sceMpegGetAvcAu(SceMpeg *,SceMpegStream *,SceMpegAu *,int *);
int sceMpegAvcDecode(SceMpeg *,SceMpegAu *,int,void *,int *);
int sceMpegAvcDecodeStop(SceMpeg *,int,void *,int *);
int sceCtrlPeekBufferPositive(SceCtrlData *,int);
