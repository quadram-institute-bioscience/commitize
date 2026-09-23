"""Repository context sent alongside the diff: maintainer guidance and recent history.

Guidance comes from an optional ``.commitize-context.md`` at the repo root,
written by the maintainers for commitize (scope names, conventions, ...).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from commitize.git import get_recent_commit_subjects

CONTEXT_FILENAME = ".commitize-context.md"


@dataclass
class RepoContext:
    guidance: str = ""
    guidance_file: str | None = None
    guidance_truncated: bool = False
    recent_commits: list[str] = field(default_factory=list)


def _repo_root(cwd: Path | None = None) -> Path | None:
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
    return Path(result.stdout.strip())


def load_guidance(
    cwd: Path | None = None, filename: str = CONTEXT_FILENAME, max_bytes: int = 4000
) -> tuple[str, bool]:
    """Return (text, truncated) for the context file, or ("", False) if absent."""
    root = _repo_root(cwd)
    if root is None or not filename:
        return "", False
    path = root / filename
    if not path.is_file():
        return "", False
    data = path.read_bytes()
    truncated = len(data) > max_bytes
    text = data[:max_bytes].decode("utf-8", errors="ignore").strip()
    return text, truncated


def load_repo_context(
    cwd: Path | None = None,
    context_file: str = CONTEXT_FILENAME,
    max_context_bytes: int = 4000,
    recent_commits: int = 15,
) -> RepoContext:
    guidance, truncated = load_guidance(cwd, context_file, max_context_bytes)
    return RepoContext(
        guidance=guidance,
        guidance_file=context_file if guidance else None,
        guidance_truncated=truncated,
        recent_commits=get_recent_commit_subjects(cwd, recent_commits),
    )
