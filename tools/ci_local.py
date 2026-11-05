#!/usr/bin/env python3
"""Run source-only checks; optional game/SDK validation is separate."""
from pathlib import Path
import subprocess
import sys

def main():
    root = Path(__file__).resolve().parents[1]
    checks = [
        [sys.executable, '-B', '-m', 'pytest', '-q', 'tests/converter', 'tests/audit'],
        [sys.executable, '-B', 'tests/emitter/run_tests.py'],
        [sys.executable, '-B', 'tests/runtime/run_tests.py'],
        [sys.executable, '-B', 'tools/audit_release.py', '--history'],
    ]
    for command in checks:
        result = subprocess.run(command, cwd=root, check=False)
        if result.returncode:
            return result.returncode
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
