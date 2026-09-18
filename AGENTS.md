# commitize — OpenCode instructions

## Setup and running tests

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_cli.py

# Run a specific test
pytest tests/test_cli.py::test_commit_flow_with_yes_flag -v
```

Tests use `pytest` with `respx` for mocking HTTP requests. Fixtures often:
- Initialize a temp git repo via `subprocess.run(["git", "init", ...])`
- Set `OPENROUTER_API_KEY` env var
- Monkeypatch module-level functions (e.g., `cli.generate_commit_message`)

## Project structure

- `src/commitize/` — Main package:
  - `cli.py` — Typer CLI entrypoint; main flow in `run_commit_flow()`
  - `config.py` — Config merging (global `~/.config/commitize/config.toml` + local `.commitize.toml`)
  - `llm.py` / `providers.py` — LLM client building and API handling
  - `git.py` — Git diff and commit operations
- `tests/` — 4 test modules (15 tests total); no pytest.ini, config in `pyproject.toml`

## Key behaviors

- Config is TOML; merged with repo-local overriding global
- Commit flow: stage changes → show preview → prompt (`y/e/r/n`) → commit or abort
- `--yes` skips confirmation; `--dry-run` prints message only; `--all` stages tracked files first
- Editor editing for `e` uses `$EDITOR` (defaults to `vi`)

## Environment requirements

- Python 3.10+
- API keys via env vars (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, etc.)
- Git repo with staged changes required for `commit` command
