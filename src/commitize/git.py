"""Git plumbing: staged diff retrieval, stats, and commit execution."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class NotAGitRepoError(RuntimeError):
    pass


class NoStagedChangesError(RuntimeError):
    pass


@dataclass
class StagedChange:
    diff: str
    stat: str
    truncated: bool


def _run(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def is_git_repo(cwd: Path | None = None) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def stage_all(cwd: Path | None = None) -> None:
    """Stage modifications/deletions to already-tracked files (like `git commit -a`)."""
    _run(["add", "--update"], cwd=cwd)


def get_staged_change(
    cwd: Path | None = None, max_diff_bytes: int = 8000
) -> StagedChange:
    if not is_git_repo(cwd):
        raise NotAGitRepoError("Not inside a git repository")

    stat = _run(["diff", "--cached", "--stat"], cwd=cwd)
    if not stat.strip():
        raise NoStagedChangesError(
            "No staged changes. Stage files with `git add`, or pass --all."
        )

    diff = _run(["diff", "--cached"], cwd=cwd)
    truncated = False
    if len(diff.encode("utf-8")) > max_diff_bytes:
        diff = diff.encode("utf-8")[:max_diff_bytes].decode("utf-8", errors="ignore")
        truncated = True

    return StagedChange(diff=diff, stat=stat, truncated=truncated)


def commit(subject: str, body: str = "", sign_off: bool = False, cwd: Path | None = None) -> None:
    args = ["commit", "-m", subject]
    if body.strip():
        args += ["-m", body]
    if sign_off:
        args.append("--signoff")
    _run(args, cwd=cwd)
