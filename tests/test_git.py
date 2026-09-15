import subprocess

import pytest

from commitize.git import (
    NoStagedChangesError,
    NotAGitRepoError,
    commit,
    get_staged_change,
    is_git_repo,
)


def _init_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def test_not_a_git_repo(tmp_path):
    assert is_git_repo(tmp_path) is False
    with pytest.raises(NotAGitRepoError):
        get_staged_change(cwd=tmp_path)


def test_no_staged_changes(tmp_path):
    _init_repo(tmp_path)
    with pytest.raises(NoStagedChangesError):
        get_staged_change(cwd=tmp_path)


def test_staged_diff_and_commit(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "hello.txt").write_text("hello\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True)

    change = get_staged_change(cwd=tmp_path, max_diff_bytes=8000)
    assert "hello.txt" in change.stat
    assert "+hello" in change.diff
    assert change.truncated is False

    commit("feat: add hello", "adds a greeting file", cwd=tmp_path)

    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert log.stdout.strip() == "feat: add hello"


def test_diff_truncation(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "big.txt").write_text("x\n" * 5000)
    subprocess.run(["git", "add", "big.txt"], cwd=tmp_path, check=True)

    change = get_staged_change(cwd=tmp_path, max_diff_bytes=100)
    assert change.truncated is True
    assert len(change.diff.encode("utf-8")) <= 100
