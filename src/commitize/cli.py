from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from commitize import __version__
from commitize.config import (
    Config,
    global_config_path,
    local_config_target,
    set_value,
    write_defaults,
)
from commitize.git import (
    NoStagedChangesError,
    NoUnstagedChangesError,
    NotAGitRepoError,
    commit as git_commit,
    get_staged_change,
    get_unstaged_change,
    stage_all,
    stage_paths,
)
from commitize.llm import LLMAuthError, LLMRequestError, OpenAICompatibleClient
from commitize.messages import CommitMessage, generate_commit_message
from commitize.providers import build_client, list_providers

app = typer.Typer(
    no_args_is_help=False,
    add_completion=True,
    help="Generate git commit messages with an LLM, then commit.",
)
config_app = typer.Typer(no_args_is_help=True, help="View and edit commitize configuration.")
providers_app = typer.Typer(no_args_is_help=True, help="Inspect configured LLM providers.")
app.add_typer(config_app, name="config")
app.add_typer(providers_app, name="providers")

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"commitize {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
    stage_all_: bool = typer.Option(False, "--all", "-a", help="Stage tracked modifications first (like `git commit -a`)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the generated message without committing."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print provider/model selection and LLM call progress."),
    provider: Optional[str] = typer.Option(None, "--provider", help="Override the configured provider."),
    model: Optional[str] = typer.Option(None, "--model", help="Override the configured model."),
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
) -> None:
    if ctx.invoked_subcommand is None:
        run_commit_flow(
            yes=yes,
            stage_all_=stage_all_,
            dry_run=dry_run,
            verbose=verbose,
            provider=provider,
            model=model,
        )


@app.command("commit")
def commit_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
    stage_all_: bool = typer.Option(False, "--all", "-a", help="Stage tracked modifications first (like `git commit -a`)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the generated message without committing."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print provider/model selection and LLM call progress."),
    provider: Optional[str] = typer.Option(None, "--provider", help="Override the configured provider."),
    model: Optional[str] = typer.Option(None, "--model", help="Override the configured model."),
) -> None:
    """Generate a commit message from the staged diff and commit."""
    run_commit_flow(
        yes=yes,
        stage_all_=stage_all_,
        dry_run=dry_run,
        verbose=verbose,
        provider=provider,
        model=model,
    )


def run_commit_flow(
    yes: bool,
    stage_all_: bool,
    dry_run: bool,
    verbose: bool,
    provider: Optional[str],
    model: Optional[str],
) -> None:
    config = Config.load()

    if stage_all_:
        stage_all()

    max_diff_bytes = int(config.get("commit.max_diff_bytes", 8000))
    ignore_file = str(config.get("commit.ignore_file", ".commitize-ignore"))
    try:
        change, needs_staging = _select_change(max_diff_bytes, ignore_file)
    except NotAGitRepoError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1)
    except (NoStagedChangesError, NoUnstagedChangesError) as exc:
        console.print(f"[yellow]{exc}[/]")
        raise typer.Exit(1)

    title = "Unstaged changes" if needs_staging else "Staged changes"
    console.print(Panel(change.stat.strip() or "(no file stat)", title=title))
    if needs_staging:
        console.print(
            "[yellow]No staged changes; analysing unstaged files "
            f"(respecting {ignore_file}).[/]"
        )

    client = _build_client(config, provider, model, verbose)
    if client is None:
        raise typer.Exit(1)

    message = _generate(client, config, change, verbose)
    if message is None:
        raise typer.Exit(1)

    while True:
        console.print(Panel(message.full_text, title="Generated commit message", style="cyan"))

        if dry_run:
            return

        if yes:
            choice = "y"
        else:
            question = (
                "Stage these files and commit with this message?"
                if needs_staging
                else "Commit with this message?"
            )
            choice = Prompt.ask(question, choices=["y", "e", "r", "n"], default="y")

        if choice == "y":
            if needs_staging:
                stage_paths(change.files)
            sign_off = bool(config.get("commit.sign_off", False))
            git_commit(message.subject, message.body, sign_off=sign_off)
            console.print("[green]Committed.[/]")
            return
        elif choice == "e":
            edited = _edit_in_editor(message.full_text)
            lines = edited.splitlines()
            message = CommitMessage(
                subject=lines[0].strip() if lines else "",
                body="\n".join(lines[1:]).strip(),
            )
            continue
        elif choice == "r":
            message = _generate(client, config, change, verbose)
            if message is None:
                raise typer.Exit(1)
            continue
        else:
            console.print("[yellow]Aborted, nothing committed.[/]")
            return


def _select_change(max_diff_bytes: int, ignore_file: str):
    """Prefer staged changes; fall back to analysing unstaged files."""
    try:
        return get_staged_change(max_diff_bytes=max_diff_bytes), False
    except NoStagedChangesError:
        pass
    change = get_unstaged_change(max_diff_bytes=max_diff_bytes, ignore_file=ignore_file)
    return change, True


def _build_client(
    config: Config, provider: Optional[str], model: Optional[str], verbose: bool
) -> Optional[OpenAICompatibleClient]:
    provider_name = provider or config.provider_name()
    try:
        client = build_client(config, provider_name=provider, model_override=model)
    except KeyError as exc:
        console.print(f"[red]Error generating message:[/] {exc}")
        return None

    if verbose:
        console.print(
            "[dim]Using provider "
            f"{provider_name} with model {client.model} ({client.base_url}).[/]"
        )
    return client


def _generate(
    client: OpenAICompatibleClient, config: Config, change, verbose: bool
) -> Optional[CommitMessage]:
    if verbose:
        console.print("[dim]Requesting commit message from LLM...[/]")
    try:
        message = generate_commit_message(client, change, config)
    except (LLMAuthError, LLMRequestError) as exc:
        console.print(f"[red]Error generating message:[/] {exc}")
        return None
    if verbose:
        console.print("[dim]LLM response received.[/]")
    return message


def _edit_in_editor(initial_text: str) -> str:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write(initial_text)
        path = f.name
    subprocess.run([editor, path])
    text = Path(path).read_text()
    os.unlink(path)
    return text


# --- config subcommands ---------------------------------------------------


def _config_path(is_global: bool) -> Path:
    if is_global:
        return global_config_path()
    try:
        return local_config_target()
    except RuntimeError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1)


@config_app.command("show")
def config_show() -> None:
    """Print the effective merged configuration with provenance."""
    config = Config.load()
    for key, value in config.iter_leaves():
        if key.split(".")[-1] in ("api_key",) and value:
            value = "***"
        source = config.source_of(key)
        console.print(f"[bold]{key}[/] = {value}  [dim]({source})[/]")


@config_app.command("get")
def config_get(key: str) -> None:
    """Print the effective value of a dotted config key."""
    config = Config.load()
    value = config.get(key)
    if value is None:
        console.print(f"[yellow]{key} is not set[/]")
        raise typer.Exit(1)
    console.print(value)


@config_app.command("set")
def config_set(
    key: str,
    value: str,
    global_: bool = typer.Option(False, "--global", help="Write to the global config (default)."),
    local: bool = typer.Option(False, "--local", help="Write to the repo-local .commitize.toml instead."),
) -> None:
    """Set a dotted config key, e.g. `commitize config set providers.openrouter.model openai/gpt-4o`."""
    is_global = global_ or not local
    path = _config_path(is_global)
    set_value(path, key, value)
    console.print(f"Set [bold]{key}[/] = {value} in {path}")


@config_app.command("init")
def config_init(
    global_: bool = typer.Option(False, "--global", help="Initialize the global config (default)."),
    local: bool = typer.Option(False, "--local", help="Initialize the repo-local .commitize.toml instead."),
    force: bool = typer.Option(False, "--force", help="Overwrite the file if it already exists."),
) -> None:
    """Write the default configuration to the config file, ready to edit."""
    is_global = global_ or not local
    path = _config_path(is_global)
    if not write_defaults(path, force=force):
        console.print(
            f"[yellow]{path} already exists; use --force to overwrite.[/]"
        )
        raise typer.Exit(1)
    console.print(f"Wrote default configuration to {path}")


@config_app.command("edit")
def config_edit(
    global_: bool = typer.Option(False, "--global", help="Edit the global config (default)."),
    local: bool = typer.Option(False, "--local", help="Edit the repo-local .commitize.toml instead."),
) -> None:
    """Open the config file in $EDITOR."""
    is_global = global_ or not local
    path = _config_path(is_global)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("")
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(path)])


@config_app.command("path")
def config_path(
    global_: bool = typer.Option(False, "--global", help="Show the global config path (default)."),
    local: bool = typer.Option(False, "--local", help="Show the repo-local .commitize.toml path instead."),
) -> None:
    """Print the config file path."""
    is_global = global_ or not local
    console.print(str(_config_path(is_global)))


# --- providers subcommands -------------------------------------------------


@providers_app.command("list")
def providers_list() -> None:
    """List configured provider presets."""
    config = Config.load()
    for p in list_providers(config):
        console.print(
            f"[bold]{p['name']}[/]  model={p['model']}  base_url={p['base_url']}  "
            f"api_key_env={p['api_key_env']}"
        )


if __name__ == "__main__":
    app()
