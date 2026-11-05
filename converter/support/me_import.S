/* Own firmware-660 ABI imports; NIDs independently read from accepted SDK metadata. */
.set noreorder
#include "pspimport.s"
IMPORT_START "ThreadManForKernel", 0x00090000
IMPORT_FUNC "ThreadManForKernel", 0xCEADEB47, sceKernelDelayThread
IMPORT_FUNC "ThreadManForKernel", 0x369ED59D, sceKernelGetSystemTimeLow
