/* Own minimal ABI declaration. See IMPORT_PROVENANCE.md; no CFW implementation. */
#ifndef DCRC_KUBRIDGE_H
#define DCRC_KUBRIDGE_H
#include <psptypes.h>
#include <pspmodulemgr.h>
SceUID kuKernelLoadModule(const char *path, int flags, SceKernelLMOption *option);
#endif
