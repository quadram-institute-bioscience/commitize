"""Loading and matching of ``.commitize-ignore`` files.

The format is a small, gitignore-like subset:

* one pattern per line; blank lines and ``#`` comments are ignored
* ``!`` at the start negates a pattern (re-includes a previously ignored path)
* a trailing ``/`` restricts the pattern to directories
* a pattern containing ``/`` is anchored to the repo root, otherwise it
  matches a path component (e.g. ``*.log`` matches ``logs/a.log``)
* ``*``, ``?`` and ``[...]`` behave as in :mod:`fnmatch`
"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

IGNORE_FILENAME = ".commitize-ignore"


def ignore_file_path(cwd: Path | None = None, filename: str = IGNORE_FILENAME) -> Path | None:
    """Path to the ignore file at the git repo root, or None if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return Path(result.stdout.strip()) / filename


def load_patterns(
    cwd: Path | None = None, filename: str = IGNORE_FILENAME
) -> list[str]:
    path = ignore_file_path(cwd, filename)
    if path is None or not path.exists():
        return []
    patterns: list[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


class IgnoreMatcher:
    """Matches repo-relative paths against a list of gitignore-style patterns."""

    def __init__(self, patterns: list[str] | None = None):
        self._patterns = patterns or []

    def __bool__(self) -> bool:
        return bool(self._patterns)

    def match(self, path: str) -> bool:
        path = path.replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        ignored = False
        for pattern in self._patterns:
            negate = pattern.startswith("!")
            candidate = pattern[1:] if negate else pattern
            if self._matches(candidate, path):
                ignored = not negate
        return ignored

    @staticmethod
    def _matches(pattern: str, path: str) -> bool:
        dir_only = pattern.endswith("/")
        pattern = pattern.rstrip("/")
        if not pattern:
            return False
        anchored = pattern.startswith("/") or "/" in pattern
        pattern = pattern.lstrip("/")

        if dir_only and (path == pattern or path.startswith(pattern + "/")):
            return True

        if anchored:
            return fnmatch.fnmatch(path, pattern)

        if fnmatch.fnmatch(path.rsplit("/", 1)[-1], pattern):
            return True
        return any(fnmatch.fnmatch(part, pattern) for part in path.split("/"))
