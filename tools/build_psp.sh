#!/bin/sh
# Optional Unix development build. The converter uses its native build adapter.
set -eu
if [ "$#" -ne 2 ]; then
  echo 'usage: build_psp.sh GENERATED_ROOT EXTERNAL_BUILD_DIR' >&2
  exit 2
fi
: "${PSPDEV:?Set PSPDEV to an independently installed public PSPDEV toolchain}"
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
toolchain="$PSPDEV/psp/share/pspdev.cmake"
test -f "$toolchain"
cmake -S "$root" -B "$2" -DCMAKE_TOOLCHAIN_FILE="$toolchain" -DSA1_RECOMP_OUT="$1" -DTARGET=psp
cmake --build "$2"
