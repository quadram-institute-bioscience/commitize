import subprocess

from commitize.ignore import IgnoreMatcher, load_patterns


def _init_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def test_load_patterns_skips_comments_and_blanks(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / ".commitize-ignore").write_text("# a comment\n\n*.log\nbuild/\n")

    assert load_patterns(tmp_path) == ["*.log", "build/"]


def test_load_patterns_missing_file_is_empty(tmp_path):
    _init_repo(tmp_path)
    assert load_patterns(tmp_path) == []


def test_matcher_basename_and_path_component():
    matcher = IgnoreMatcher(["*.log"])

    assert matcher.match("app.log") is True
    assert matcher.match("logs/app.log") is True
    assert matcher.match("app.txt") is False


def test_matcher_anchored_pattern():
    matcher = IgnoreMatcher(["docs/*.md"])

    assert matcher.match("docs/readme.md") is True
    assert matcher.match("nested/docs/readme.md") is False


def test_matcher_directory_only():
    matcher = IgnoreMatcher(["build/"])

    assert matcher.match("build") is True
    assert matcher.match("build/out.txt") is True
    assert matcher.match("notbuild/out.txt") is False


def test_matcher_negation():
    matcher = IgnoreMatcher(["*.log", "!keep.log"])

    assert matcher.match("debug.log") is True
    assert matcher.match("keep.log") is False
