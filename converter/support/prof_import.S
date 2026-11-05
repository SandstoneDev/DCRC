/* Own firmware-660 ABI imports; NIDs independently read from accepted SDK metadata. */
.set noreorder
#include "pspimport.s"
IMPORT_START "ThreadManForKernel", 0x00090000
IMPORT_FUNC "ThreadManForKernel", 0x6652B8CA, sceKernelSetAlarm
IMPORT_FUNC "ThreadManForKernel", 0x7E65B999, sceKernelCancelAlarm
