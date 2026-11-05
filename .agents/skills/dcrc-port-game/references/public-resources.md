# Public resources and scope

Use primary sources and record the actual revision used. A link is an entry
point, not permission to copy every file or proof of binary compatibility.

* [PSPDEV](https://pspdev.github.io/), [PSPSDK source](https://github.com/pspdev/pspsdk)
  and [API documentation](https://pspdev.github.io/pspsdk/): public community PSP
  development interfaces, examples and source. These replace reliance on private
  PSP skills/manuals; they are not Sony's confidential SDK.
* [GCC documentation](https://gcc.gnu.org/onlinedocs/) and
  [GNU binutils documentation](https://sourceware.org/binutils/docs/): compiler,
  assembly/link/ELF tools. Match the manual to the compiler/target revision.
* [KallistiOS](https://github.com/KallistiOS/KallistiOS): public Dreamcast homebrew
  source useful for platform research. It is not a drop-in implementation of a
  commercial game's SDK ABI; check each file's licence before any reuse.
* [Ghidra](https://github.com/NationalSecurityAgency/ghidra): optional local binary
  analysis. It is not required by the normal converter. Keep analysis databases
  and game-derived output private.
* [PPSSPP](https://www.ppsspp.org/): optional functional testing, under the user's
  test authorization. Emulator results do not establish physical PSP speed.
* [Python Windows isolation](https://docs.python.org/3.14/using/windows.html#finding-modules):
  `._pth` and interpreter path behaviour. Test the packaged interpreter itself.
* [Qt for Python](https://doc.qt.io/qtforpython-6/): GUI API; preserve its separate
  licence obligations when redistributing libraries.
* [AGENTS.md format](https://github.com/agentsmd/agents.md) and
  [skill documentation](https://learn.chatgpt.com/docs/build-skills): optional
  agent integration. The project instructions remain readable without a plugin.

If a linked resource fails, use the dependency-research skill. Distinguish a
temporary fetch failure, a redirect, an upstream move and an unavailable project.
Do not turn an unofficial mirror into a trusted SDK source without verification.
