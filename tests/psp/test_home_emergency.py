"""Run actual callback functions against a synthetic PSP clock/wait service."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[2] / 'backend/psp/main_psp.c').read_text()
def function(name):
    return re.search(r'static int ' + name + r'\([^)]*\)\s*\{.*?\n\}', source, re.S).group(0)

harness = r'''
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
typedef unsigned SceSize;
typedef int SceUID;
static volatile int home_exit_requested;
static uint64_t clock_us;
static int (*home_callback)(int,int,void *);
static int callbacks, mode, wait_calls;
static jmp_buf exit_point;
static uint64_t sa1_plat_time_us(void) { return clock_us; }
static int sceKernelCreateCallback(const char *n, int (*cb)(int,int,void *), void *p) {
    (void)n; (void)p; home_callback = cb; return 1;
}
static int sceKernelRegisterExitCallback(int cb) { (void)cb; return 0; }
static int sceKernelSleepThreadCB(void) { return 0; }
static int sceKernelDelayThreadCB(unsigned delay) {
    ++wait_calls;
    if (mode == 2 && home_exit_requested) return -1;
    /* Early return simulates release-wait/spurious returns. Repeated HOME
       callbacks cannot restart the grace interval. */
    unsigned advance = mode == 1 && delay > 100000 ? 100000 : delay;
    clock_us += advance;
    if (!home_exit_requested || mode == 1) {
        ++callbacks; home_callback(0, 0, 0);
    }
    assert(wait_calls < 1000);
    return 0;
}
static void sceKernelExitGame(void) { longjmp(exit_point, 1); }
'''
harness += function('exit_callback') + '\n' + function('callback_thread')
harness += r'''
int main(void) {
    for (mode = 0; mode < 3; ++mode) {
        clock_us = 0; home_exit_requested = 0; wait_calls = callbacks = 0;
        if (!setjmp(exit_point)) {
            callback_thread(0, 0);
            assert(!"callback thread returned without emergency process exit");
        }
        assert(home_exit_requested && callbacks > 0);
        if (mode != 2) assert(clock_us == 5100000);
        else assert(clock_us == 100000); /* failed wait does not busy-spin */
    }
    puts("HOME deadline/repeated-callback/wait-error harness PASS");
}
'''
with tempfile.TemporaryDirectory(prefix='sa1-home-exit-') as tmp:
    tmp = Path(tmp)
    (tmp / 'test.c').write_text(harness)
    binary = tmp / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c99', '-Wall', '-Wextra',
                    '-Wno-unused-function', '-Werror', str(tmp / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
