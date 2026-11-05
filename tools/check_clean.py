#!/usr/bin/env python3
"""Compatibility entry point for the source publication audit."""
import sys
from audit_release import main

if __name__ == '__main__':
    args = ['--history' if value == '--all' else value for value in sys.argv[1:]]
    raise SystemExit(main(args or ['--staged']))
