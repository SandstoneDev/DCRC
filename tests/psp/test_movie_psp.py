"""Compile the actual own movie leaf against synthetic SDK substitutes.

PSP includes are removed only in the ignored host copy; production has no test
switch. No codec binaries, PMF media, game input, builds or emulator are used.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asan", action="store_true")
    parser.add_argument("--cc", help="Host compiler executable; defaults to CC or PATH")
    args = parser.parse_args()
    output = ROOT / "work/C94_movie/host"
    output.mkdir(parents=True, exist_ok=True)

    def mapped(path):
        text = str(path).replace("\\", "/")
        if args.asan and os.name == "nt":
            return "/mnt/" + text[0].lower() + text[2:]
        return text

    source = (ROOT / "backend/psp/movie_psp.c").read_text(encoding="utf8")
    source = re.sub(r'^#include <psp[^\n]+\n', '', source, flags=re.M)
    source = source.replace('#include "hle.h"\n', '')
    source = source.replace('"movie_psp.h"', '"' + mapped(ROOT / "backend/psp/movie_psp.h") + '"')
    source = source.replace('"../movie_wav.h"', '"' + mapped(ROOT / "backend/movie_wav.h") + '"')
    (output / "movie_psp_test_impl.inc").write_text(source, encoding="utf8")
    exe = output / ("movie_psp_asan" if args.asan else "movie_psp_test.exe")
    flags = ["-std=c11", "-Wall", "-Wextra", "-Werror"]
    if args.asan:
        flags += ["-fsanitize=address,undefined"]
    env = dict(os.environ)
    compiler = args.cc or env.get("CC")
    if args.asan and os.name == "nt":
        prefix = ["wsl.exe", "--exec", compiler or "gcc"]
    else:
        compiler = compiler or shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")
        if not compiler:
            parser.error("Select a host compiler with --cc or CC, or install it on PATH")
        prefix = [compiler]
    compile_args = prefix + flags + ["-I" + mapped(output), mapped(ROOT / "tests/psp/movie_psp_test.c"),
                                   mapped(ROOT / "backend/movie_wav.c"), "-o", mapped(exe)]
    subprocess.run(compile_args, cwd=ROOT, env=env, check=True)
    run = ["wsl.exe", "--cd", mapped(output), "--exec", mapped(exe)] if args.asan and os.name == "nt" else [str(exe)]
    subprocess.run(run, cwd=output, env=env, check=True)


if __name__ == "__main__":
    main()
