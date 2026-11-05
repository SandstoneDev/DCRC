# Dependency decision record

Keep a private machine-specific acquisition record and a sanitized public
component manifest. Public metadata must not expose user paths, tokens or logs.
Record these fields; use unknown where a fact has not been established:

| Field | Required evidence |
|---|---|
| Component and purpose | Actual caller/build input; shipped, build-only, optional or research-only |
| Source | Canonical upstream URL and final URL after redirects |
| Identity | Tag/version/commit, artifact name, host/target architecture |
| Integrity | SHA256+size of acquired bytes; signed upstream digest if provided |
| Licence | Exact revision's licence files, notices, exceptions and source requirements |
| Build provenance | Source hashes/revisions, patches, tool versions and relevant flags |
| Compatibility | Required executables/headers/libs and observed smoke result |
| Decision | Accepted for stated scope, candidate, rejected or unresolved; reason |

A calculated hash proves content identity, not publisher authenticity. Do not
invent upstream checksums or treat an unsigned mirror as an official release.

When a link fails, record checked date, response/error and where the replacement
was discovered. Recheck the maintainer's root site and repository before broad
search. If no verified replacement exists, keep the dependency unresolved and
continue work that does not require it. Do not modify the product to hide it.

Useful starting points: [PSPDEV](https://github.com/pspdev/pspdev),
[PSPSDK](https://github.com/pspdev/pspsdk),
[newlib PSP fork](https://github.com/pspdev/newlib),
[GCC](https://gcc.gnu.org/onlinedocs/),
[MSYS2](https://www.msys2.org/),
[MinGW-w64](https://www.mingw-w64.org/).
The newlib fork is explicitly a platform fork, not proof that it matches any
previously bundled binary. Obtain versions from actual manifests, not these
landing pages' latest-release labels.
