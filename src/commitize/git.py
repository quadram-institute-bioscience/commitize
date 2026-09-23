"""Git plumbing: staged diff retrieval, stats, and commit execution."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from commitize.ignore import IgnoreMatcher, load_patterns


class NotAGitRepoError(RuntimeError):
    pass


class NoStagedChangesError(RuntimeError):
    pass


class NoUnstagedChangesError(RuntimeError):
    pass


class NoCommitsError(RuntimeError):
    pass


@dataclass
class StagedChange:
    diff: str
    stat: str
    truncated: bool
    files: list[str] = field(default_factory=list)


@dataclass
class CommitInfo:
    hash: str
    subject: str
    body: str


def _run(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _run_allow_diff(args: list[str], cwd: Path | None = None) -> str:
    """Like ``_run`` but tolerates exit code 1 (used by ``git diff --no-index``)."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode not in (0, 1):
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


def stage_paths(paths: list[str], cwd: Path | None = None) -> None:
    """Stage the given repo-relative paths."""
    if paths:
        _run(["add", "--", *paths], cwd=cwd)


def _truncate(diff: str, max_diff_bytes: int) -> tuple[str, bool]:
    if len(diff.encode("utf-8")) > max_diff_bytes:
        diff = diff.encode("utf-8")[:max_diff_bytes].decode("utf-8", errors="ignore")
        return diff, True
    return diff, False


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
    diff, truncated = _truncate(diff, max_diff_bytes)
    files = _run(["diff", "--cached", "--name-only"], cwd=cwd).splitlines()

    return StagedChange(diff=diff, stat=stat, truncated=truncated, files=files)


def _status_entries(cwd: Path | None = None) -> list[tuple[str, str]]:
    """Return (status, path) pairs for every changed/untracked file."""
    out = _run(["status", "--porcelain", "--untracked-files=all"], cwd=cwd)
    entries: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:  # renames show as "old -> new"
            path = path.split(" -> ", 1)[1]
        entries.append((status, path.strip('"')))
    return entries


def get_unstaged_change(
    cwd: Path | None = None,
    max_diff_bytes: int = 8000,
    matcher: IgnoreMatcher | None = None,
    ignore_file: str = ".commitize-ignore",
) -> StagedChange:
    """Analyse working-tree changes (tracked modifications + untracked files).

    Files matching ``.commitize-ignore`` are skipped.
    """
    if not is_git_repo(cwd):
        raise NotAGitRepoError("Not inside a git repository")

    if matcher is None:
        patterns = load_patterns(cwd, ignore_file)
        matcher = IgnoreMatcher(patterns + [ignore_file])

    entries = _status_entries(cwd)
    tracked = [
        path for status, path in entries if not status.startswith("??") and not matcher.match(path)
    ]
    untracked = [
        path for status, path in entries if status.startswith("??") and not matcher.match(path)
    ]
    files = tracked + untracked

    if not files:
        raise NoUnstagedChangesError(
            "No staged changes and no unstaged changes to analyse."
        )

    stat_parts: list[str] = []
    diff_parts: list[str] = []

    if tracked:
        stat_parts.append(_run(["diff", "--stat", "--", *tracked], cwd=cwd))
        diff_parts.append(_run(["diff", "--", *tracked], cwd=cwd))

    for path in untracked:
        stat_parts.append(
            _run_allow_diff(["diff", "--no-index", "--stat", "--", os.devnull, path], cwd=cwd)
        )
        diff_parts.append(
            _run_allow_diff(["diff", "--no-index", "--", os.devnull, path], cwd=cwd)
        )

    diff, truncated = _truncate("".join(diff_parts), max_diff_bytes)
    return StagedChange(
        diff=diff, stat="".join(stat_parts), truncated=truncated, files=files
    )


def get_recent_commit_subjects(cwd: Path | None = None, limit: int = 15) -> list[str]:
    """Subjects of the latest non-merge commits, newest first ([] if none)."""
    if limit <= 0:
        return []
    try:
        out = _run(["log", f"-n{limit}", "--no-merges", "--pretty=format:%s"], cwd=cwd)
    except RuntimeError:  # e.g. a repo with no commits yet
        return []
    return [line for line in out.splitlines() if line.strip()]


_COMMIT_SEPARATOR = "\x1e"
_COMMIT_FIELD = "\x1f"


def _last_release_tag(cwd: Path | None = None) -> str | None:
    """Most recent tag reachable from HEAD, or None if the repo has no tags."""
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_commits_since_last_release(cwd: Path | None = None) -> list[CommitInfo]:
    """Commit subjects/bodies since the latest release tag (or all commits)."""
    if not is_git_repo(cwd):
        raise NotAGitRepoError("Not inside a git repository")

    last_tag = _last_release_tag(cwd)
    range_spec = f"{last_tag}..HEAD" if last_tag else "HEAD"
    fmt = f"%H{_COMMIT_FIELD}%s{_COMMIT_FIELD}%b{_COMMIT_SEPARATOR}"
    try:
        out = _run(["log", range_spec, "--pretty=format:" + fmt], cwd=cwd)
    except RuntimeError:
        raise NoCommitsError("No commits found since the last release.")

    commits: list[CommitInfo] = []
    for record in out.split(_COMMIT_SEPARATOR):
        record = record.strip()
        if not record:
            continue
        parts = record.split(_COMMIT_FIELD, 2)
        commits.append(
            CommitInfo(
                hash=parts[0],
                subject=parts[1] if len(parts) > 1 else "",
                body=parts[2] if len(parts) > 2 else "",
            )
        )

    if not commits:
        raise NoCommitsError("No commits found since the last release.")
    return commits


def commit(subject: str, body: str = "", sign_off: bool = False, cwd: Path | None = None) -> None:
    args = ["commit", "-m", subject]
    if body.strip():
        args += ["-m", body]
    if sign_off:
        args.append("--signoff")
    _run(args, cwd=cwd)
