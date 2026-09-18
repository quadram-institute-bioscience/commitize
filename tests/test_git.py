import subprocess

import pytest

from commitize.git import (
    NoCommitsError,
    NoStagedChangesError,
    NoUnstagedChangesError,
    NotAGitRepoError,
    commit,
    get_commits_since_last_release,
    get_staged_change,
    get_unstaged_change,
    is_git_repo,
    stage_paths,
)
from commitize.ignore import IgnoreMatcher


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


def test_staged_change_lists_files(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "hello.txt").write_text("hello\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True)

    change = get_staged_change(cwd=tmp_path)
    assert change.files == ["hello.txt"]


def test_unstaged_change_includes_tracked_and_untracked(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("one\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)

    (tmp_path / "tracked.txt").write_text("one\ntwo\n")
    (tmp_path / "untracked.txt").write_text("brand new\n")

    change = get_unstaged_change(cwd=tmp_path)
    assert set(change.files) == {"tracked.txt", "untracked.txt"}
    assert "two" in change.diff
    assert "brand new" in change.diff

    stage_paths(change.files, cwd=tmp_path)
    staged = get_staged_change(cwd=tmp_path)
    assert set(staged.files) == {"tracked.txt", "untracked.txt"}


def test_unstaged_change_respects_ignore(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "keep.txt").write_text("keep\n")
    (tmp_path / "secret.log").write_text("secret\n")

    matcher = IgnoreMatcher(["*.log"])
    change = get_unstaged_change(cwd=tmp_path, matcher=matcher)

    assert change.files == ["keep.txt"]


def test_unstaged_change_all_ignored_raises(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "secret.log").write_text("secret\n")

    matcher = IgnoreMatcher(["*.log"])
    with pytest.raises(NoUnstagedChangesError):
        get_unstaged_change(cwd=tmp_path, matcher=matcher)


def test_commits_since_last_release_not_a_repo(tmp_path):
    with pytest.raises(NotAGitRepoError):
        get_commits_since_last_release(cwd=tmp_path)


def test_commits_since_last_release_no_commits(tmp_path):
    _init_repo(tmp_path)
    with pytest.raises(NoCommitsError):
        get_commits_since_last_release(cwd=tmp_path)


def test_commits_since_last_release_all_without_tag(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    commit("feat: add a", "adds a", cwd=tmp_path)
    (tmp_path / "b.txt").write_text("b\n")
    subprocess.run(["git", "add", "b.txt"], cwd=tmp_path, check=True)
    commit("fix: add b", "adds b", cwd=tmp_path)

    commits = get_commits_since_last_release(cwd=tmp_path)
    assert [c.subject for c in commits] == ["fix: add b", "feat: add a"]
    assert commits[0].body == "adds b"


def test_commits_since_last_release_respects_tag(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    commit("feat: add a", cwd=tmp_path)
    subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp_path, check=True)

    (tmp_path / "b.txt").write_text("b\n")
    subprocess.run(["git", "add", "b.txt"], cwd=tmp_path, check=True)
    commit("feat: add b", cwd=tmp_path)

    commits = get_commits_since_last_release(cwd=tmp_path)
    assert [c.subject for c in commits] == ["feat: add b"]
