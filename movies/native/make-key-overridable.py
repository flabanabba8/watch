#!/usr/bin/env python3
"""Turn upstream Luffy's TMDB key constant into a variable so a user-supplied key can override it.

The upstream value is kept exactly as Luffy ships it and is never printed or copied into this repository.
"""
import re
import subprocess
import sys
from pathlib import Path

PATTERN = re.compile(r'^const\s+TMDB_API_KEY\s*=\s*("[^"\r\n]+")\s*$', re.M)


def make_overridable(text):
    matches = list(PATTERN.finditer(text))
    if len(matches) != 1: raise ValueError('Unexpected upstream metadata key declaration')
    match = matches[0]
    return text[:match.start()] + 'var TMDB_API_KEY = ' + match.group(1) + text[match.end():]


def main():
    if len(sys.argv) != 2: raise ValueError('Usage: make-key-overridable.py WORKTREE')
    source = Path(sys.argv[1])/'core'/'tmdb.go'
    source.write_text(make_overridable(source.read_text(encoding='utf-8')), encoding='utf-8')

if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.SubprocessError):
        print('Could not make the upstream metadata key overridable', file=sys.stderr)
        sys.exit(1)
