TARGET = sa1chain
OBJS = chain_main.o
INCDIR = .
# Kernel libc lacks GCC's synthesized stpcpy; keep the explicit libc calls.
CFLAGS = -O2 -G0 -Wall -fno-builtin
BUILD_PRX = 1
USE_KERNEL_LIBS = 1
USE_KERNEL_LIBC = 1
PSP_FW_VERSION = 660
LIBS = -lpspsystemctrl_kernel
PSPSDK = $(shell psp-config --pspsdk-path)
include $(PSPSDK)/lib/build.mak
