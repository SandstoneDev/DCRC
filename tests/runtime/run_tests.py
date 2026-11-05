#!/usr/bin/env python3
"""Build/run synthetic runtime tests; no game, SDK or device input."""
from pathlib import Path
import argparse,os,shutil,subprocess,tempfile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',default=None)
    parser.add_argument('--sanitize',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    cc=args.cc or shutil.which('clang') or shutil.which('gcc') or shutil.which('cc')
    if not cc:parser.error('Install/select a host C compiler with --cc')
    tests=sorted((root/'tests/runtime').glob('test_*.c'))+[root/'tests/game/startup_test.c']
    extra={'test_debug_menu.c':['backend/debug_menu.c'],
           'test_debug_chord.c':['backend/debug_menu.c'],
           'test_debug_config.c':['backend/debug_config.c'],
           'test_content_mount.c':['hle/game/optional_content.c']}
    with tempfile.TemporaryDirectory(prefix='dcrc-runtime-') as work:
        for case in tests:
            out=Path(work)/(case.stem+('.exe' if os.name=='nt' else ''))
            flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                   '-I'+str(root/'hle'),'-I'+str(root/'recomp/emitter/runtime')]
            if args.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
            command=[cc,*flags,str(case),*(str(root/p)for p in extra.get(case.name,[])),'-o',str(out),'-lm']
            subprocess.run(command,check=True,cwd=root)
            subprocess.run([str(out)],check=True,cwd=work)
            print('PASS',case.name,flush=True)
    print(f'{len(tests)} runtime executables PASS')
if __name__=='__main__':main()
