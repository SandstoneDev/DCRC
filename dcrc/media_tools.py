"""Discovery of local media executables; discovery never executes tools."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import sys
from .storage import plain_path, reject_links


def bundle_root():
    # Only our embedded interpreter layout; source runs must not search siblings.
    python = Path(sys.executable).resolve()
    if python.parent.name.casefold() == 'python':
        root = python.parent.parent
        if Path(__file__).resolve() == root/'app'/'dcrc'/'media_tools.py':
            return root
    return None


def find_tool(name, explicit=None):
    if name not in ('ffmpeg', 'ffprobe'):
        raise ValueError('Unsupported media tool')
    if explicit is not None:
        return plain_path(explicit)
    root = bundle_root()
    if root is not None:
        candidate = root/'tools'/'ffmpeg'/(name+'.exe' if os.name == 'nt' else name)
        reject_links(candidate)
        if candidate.is_file():
            return candidate
    found = shutil.which(name)
    return plain_path(found) if found else None
