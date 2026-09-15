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


def test_no_staged_changes_errors(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli.app, ["commit", "--yes"])

    assert result.exit_code == 1
