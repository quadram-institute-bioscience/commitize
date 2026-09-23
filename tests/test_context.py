import subprocess

from commitize.context import load_repo_context


def _init_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def test_loads_guidance_from_repo_root(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / ".commitize-context.md").write_text("Scopes: cli, config.\n")
    (tmp_path / "sub").mkdir()

    context = load_repo_context(cwd=tmp_path / "sub")

    assert context.guidance == "Scopes: cli, config."
    assert context.guidance_file == ".commitize-context.md"
    assert context.guidance_truncated is False


def test_missing_guidance_file_is_empty(tmp_path):
    _init_repo(tmp_path)

    context = load_repo_context(cwd=tmp_path)

    assert context.guidance == ""
    assert context.guidance_file is None


def test_guidance_is_truncated_to_max_bytes(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "ctx.md").write_text("x" * 50)

    context = load_repo_context(cwd=tmp_path, context_file="ctx.md", max_context_bytes=10)

    assert context.guidance == "x" * 10
    assert context.guidance_truncated is True


def test_outside_a_repo_has_no_context(tmp_path):
    context = load_repo_context(cwd=tmp_path)

    assert context.guidance == ""
    assert context.recent_commits == []
