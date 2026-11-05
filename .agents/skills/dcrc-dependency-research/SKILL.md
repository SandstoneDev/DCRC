---
name: dcrc-dependency-research
description: Investigate a missing DCRC dependency, broken documentation link, absent developer skill or replacement tool. Verify primary sources, licences, target compatibility and provenance before proposing installation or reuse.
---

# Research a missing dependency

Establish the required capability from current callers and the failing action:
host OS/architecture, target ABI, required tools/headers/libs, version constraints
and whether it is runtime, build-only, test-only or historical research. A similar
project name is not evidence of equivalence.

Check repository manifests and available tools read-only. If a private skill is
missing, recover its required public capability from project APIs and official
documentation; do not request proprietary manuals or fabricate its contents.

Start with the maintainer's official site/repository. Inspect the proposed
version, licence, releases and source/build instructions. For a failed URL,
follow documented redirects or upstream references and record the outcome. A
timeout/502 is unavailable evidence, not proof a project is dead. A verified fork
can be a candidate, but label it as a fork and compare ABI/licence/version scope.

Use [the evidence record](references/evidence-record.md). Read source/install
scripts before executing them. Do not execute retrieved snippets merely because
they appeared in a search result. No proprietary/pirated SDK, leaked headers,
keys or game files may silently replace an open dependency.

Report the concrete candidate, evidence and remaining blocker. Download/install
or change configuration only within the user's authorization. Do not claim an
untested Windows SDK works because its Linux build or documentation exists.
