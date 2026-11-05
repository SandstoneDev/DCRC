# Own PSP import declarations

These small assembly files declare public library names, versions and NIDs.
They contain no custom-firmware implementation or copied static-library member.
The public PSPSDK `pspimport.s` supplies its BSD-licensed import macros.

Primary ABI references:

- [KUBridge declaration](https://github.com/pspdev/psp-cfw-sdk/blob/main/src/KUBridge/KUBridge.S)
- [SystemControl kernel declaration](https://github.com/pspdev/psp-cfw-sdk/blob/main/src/SystemCtrlForKernel/SystemCtrlForKernel.S)
- [Public PSPSDK thread-manager declarations](https://github.com/pspdev/pspsdk/tree/master/src/kernel)

The thread-manager declarations identify the `ThreadManForKernel` firmware660
ABI used by the project's own helpers. Library names/NIDs and calling conventions
are compatibility facts; implementations are not included. A developer must
obtain an appropriate open PSP homebrew SDK separately. Keep its per-file notices
and verify actual linked inputs before distributing any toolchain binaries.

The new Python PBP/SFO writer encodes public file layouts. It does not copy
PS2RC's custom-licensed implementation or include game artwork.
