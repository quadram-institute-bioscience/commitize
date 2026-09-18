import subprocess

from typer.testing import CliRunner

from commitize import cli
from commitize.messages import CommitMessage

runner = CliRunner()


def _init_repo_with_staged_change(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "hello.txt").write_text("hello\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=path, check=True)


def test_commit_flow_with_yes_flag(tmp_path, monkeypatch):
    _init_repo_with_staged_change(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(cli, "global_config_path", lambda: tmp_path / "unused_global.toml")

    monkeypatch.setattr(
        cli,
        "generate_commit_message",
        lambda client, change, config: CommitMessage(subject="feat: add hello", body=""),
    )

    result = runner.invoke(cli.app, ["commit", "--yes"])

    assert result.exit_code == 0, result.output
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert log.stdout.strip() == "feat: add hello"


def test_dry_run_does_not_commit(tmp_path, monkeypatch):
    _init_repo_with_staged_change(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    monkeypatch.setattr(
        cli,
        "generate_commit_message",
        lambda client, change, config: CommitMessage(subject="feat: add hello", body=""),
    )

    result = runner.invoke(cli.app, ["commit", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "feat: add hello" in result.output
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True
    )
    assert log.returncode != 0  # no commits were ever made


def test_verbose_mode_reports_model_and_llm_progress(tmp_path, monkeypatch):
    _init_repo_with_staged_change(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(cli, "global_config_path", lambda: tmp_path / "unused_global.toml")

    monkeypatch.setattr(
        cli,
        "generate_commit_message",
        lambda client, change, config: CommitMessage(subject="feat: add hello", body=""),
    )

    result = runner.invoke(cli.app, ["commit", "--dry-run", "--verbose"])

    assert result.exit_code == 0, result.output
    assert "Using provider openrouter with model openai/gpt-4o-mini" in result.output
    assert "Requesting commit message from LLM..." in result.output
    assert "LLM response received." in result.output


def test_no_staged_changes_errors(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli.app, ["commit", "--yes"])

    assert result.exit_code == 1


def test_unstaged_fallback_stages_and_commits(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "hello.txt").write_text("hello\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    monkeypatch.setattr(
        cli,
        "generate_commit_message",
        lambda client, change, config: CommitMessage(subject="feat: add hello", body=""),
    )

    result = runner.invoke(cli.app, ["commit", "--yes"])

    assert result.exit_code == 0, result.output
    assert "Unstaged changes" in result.output
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert log.stdout.strip() == "feat: add hello"
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert "hello.txt" in tracked.stdout


def test_unstaged_fallback_respects_commitize_ignore(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "keep.txt").write_text("keep\n")
    (tmp_path / "secret.log").write_text("secret\n")
    (tmp_path / ".commitize-ignore").write_text("*.log\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    seen = {}

    def _fake(client, change, config):
        seen["files"] = change.files
        return CommitMessage(subject="chore: add keep", body="")

    monkeypatch.setattr(cli, "generate_commit_message", _fake)

    result = runner.invoke(cli.app, ["commit", "--yes"])

    assert result.exit_code == 0, result.output
    assert seen["files"] == ["keep.txt"]
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert "keep.txt" in tracked
    assert "secret.log" not in tracked
    assert ".commitize-ignore" not in tracked


def test_config_init_writes_defaults(tmp_path, monkeypatch):
    target = tmp_path / "config.toml"
    monkeypatch.setattr(cli, "global_config_path", lambda: target)

    result = runner.invoke(cli.app, ["config", "init"])
    assert result.exit_code == 0, result.output
    assert "[providers.openrouter]" in target.read_text()

    result = runner.invoke(cli.app, ["config", "init"])
    assert result.exit_code == 1
    assert "already exists" in result.output

    result = runner.invoke(cli.app, ["config", "init", "--force"])
    assert result.exit_code == 0, result.output


def _init_repo_with_commit(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "hello.txt").write_text("hello\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: add hello"], cwd=path, check=True)


def test_release_prints_changelog(tmp_path, monkeypatch):
    _init_repo_with_commit(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(cli, "global_config_path", lambda: tmp_path / "unused_global.toml")
    monkeypatch.setattr(
        cli,
        "generate_changelog",
        lambda client, commits, existing_text=None: "## New features\n- add hello",
    )

    result = runner.invoke(cli.app, ["release"])

    assert result.exit_code == 0, result.output
    assert "## New features" in result.output
    assert "- add hello" in result.output


def test_release_writes_output_file(tmp_path, monkeypatch):
    _init_repo_with_commit(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(cli, "global_config_path", lambda: tmp_path / "unused_global.toml")
    monkeypatch.setattr(
        cli,
        "generate_changelog",
        lambda client, commits, existing_text=None: "## Bug fixes\n- fix thing",
    )

    result = runner.invoke(cli.app, ["release", "-o", "CHANGELOG.md"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "CHANGELOG.md").read_text().startswith("## Bug fixes")


def test_release_integrates_existing_changelog(tmp_path, monkeypatch):
    _init_repo_with_commit(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(cli, "global_config_path", lambda: tmp_path / "unused_global.toml")
    (tmp_path / "CHANGELOG.md").write_text("## Old release\n- old stuff\n")

    seen = {}

    def _fake(client, commits, existing_text=None):
        seen["existing_text"] = existing_text
        return "## New features\n- new stuff\n\n## Old release\n- old stuff"

    monkeypatch.setattr(cli, "generate_changelog", _fake)

    result = runner.invoke(cli.app, ["release", "-o", "CHANGELOG.md"])

    assert result.exit_code == 0, result.output
    assert seen["existing_text"].startswith("## Old release")
    assert "new stuff" in (tmp_path / "CHANGELOG.md").read_text()


def test_release_no_commits_errors(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli.app, ["release"])

    assert result.exit_code == 1
    assert "No commits" in result.output
