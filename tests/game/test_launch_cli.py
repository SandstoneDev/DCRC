"""Execute the real launch-option branches with a recording setter.
The parser itself comes from each backend; this catches missing-value and
next-option consumption independently of the setters' validation tests.
"""
from pathlib import Path
import os, re, subprocess, tempfile
root=Path(__file__).resolve().parents[2]
for backend in ('psp','desktop'):
    source=(root/'backend'/backend/('main_psp.c' if backend=='psp' else 'main.c')).read_text()
    if backend=='psp':
        part=source[source.index('else if (!strcmp(av[i], "--stage"))'):]
        part=part[:part.index(' else if (input_tape_arg')]
    else:
        part=source[source.index('else if (!strcmp(argv[i], "--stage"))'):]
        part=part[:part.index('else if (!strcmp(argv[i], "--no-vmu"))')]
    harness=r'''
#include <assert.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
static int count, no_vmu;
static const char *keys[8], *values[8];
static int set(const char *key,const char *value,int cli) { assert(cli==1); keys[count]=key; values[count++]=value; return value?1:-1; }
#define hle_startup_setting set
#define hle_dlc_setting set
static void parse(int argc,char **argv) {
    int args_c=argc; char **av=argv; (void)args_c; (void)av;
    count=0; no_vmu=0;
    for(int i=0;i<argc;i++) { if(0) {}
''' + part + r'''
    else if(!strcmp(argv[i],"--no-vmu")) no_vmu=1;
    }
}
int main(void) {
    char *one[]={"--stage"}; parse(1,one); assert(count==1 && values[0]==NULL && !strcmp(keys[0],"start_stage"));
    char *next[]={"--dlc-vms","--no-vmu"}; parse(2,next); assert(count==1 && values[0]==NULL && no_vmu);
    char *mixed[]={"--stage","--character","tails","--act","2","--dlc-vmi"};
    parse(6,mixed); assert(count==4 && !values[0] && !strcmp(values[1],"tails") && !strcmp(values[2],"2") && !values[3]);
    puts("launch CLI missing-value/next-option PASS");
}
'''
    with tempfile.TemporaryDirectory(prefix='sa1-launch-') as tmp:
        p=Path(tmp); (p/'test.c').write_text(harness)
        binary=p/('test.exe' if os.name=='nt' else 'test')
        subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
    print(backend,'actual branches checked')
