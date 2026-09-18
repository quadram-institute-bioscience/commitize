# commitize

<img src="commit.svg" style="float:right; width:264px; margin-left:10px;" />

Generate git commit messages from your staged diff using an LLM, review them,
and commit — all from one command. OpenRouter works out of the box; any other
OpenAI-compatible API (OpenAI, Groq, local Ollama, etc.) can be configured too.

## Install

```bash
# with uv (recommended)
uv tool install .

# or with pip, in a virtualenv
pip install .
```

## Quick start

```bash
export OPENROUTER_API_KEY=sk-or-...
git add -p                 # stage what you want to commit
commitize                  # generate a message, review it, commit
```

You'll see the staged file summary and the generated message, then a prompt:

```
Commit with this message? [y/e/r/n]
```

- `y` — commit as-is
- `e` — edit the message in `$EDITOR` first
- `r` — regenerate
- `n` — abort, nothing is committed

The `release` command generates a changelog from commits since the last release tag (git tags ending in `-release`). It groups changes under headings "New features", "Bug fixes", and "Other changes", using an LLM to summarise and deduplicate. If the changelog file exists, new changes are prepended as a new release section while preserving existing content.

If nothing is staged, commitize falls back to analysing your unstaged changes
(tracked modifications and untracked files) and proposes to stage them and
commit. Files listed in a `.commitize-ignore` file at the repo root are skipped.

```bash
# .commitize-ignore (same glob-ish syntax as .gitignore)
*.log
build/
!keep.log
```

## Usage

```bash
commitize                 # same as `commitize commit`
commitize commit --yes    # skip the confirmation prompt
commitize commit --all    # stage tracked modifications first (like `git commit -a`)
commitize commit --dry-run           # print the message, don't commit
commitize commit --provider openai   # use a different configured provider
commitize commit --model gpt-4o      # override the model for this run
commitize release                  # generate a changelog since the last release
commitize release -o CHANGELOG.md  # write to file instead of printing
```

## Configuration

Config lives in two places, merged together (repo-local wins):

- Global: `commitize config path --global` (e.g. `~/.config/commitize/config.toml`)
- Repo-local: `.commitize.toml` at the root of the current git repo

```bash
commitize config init                                   # dump all defaults into the config file, ready to edit
commitize config init --local                           # ...into the repo-local .commitize.toml
commitize config show                                   # effective config + where each value came from
commitize config get providers.openrouter.model
commitize config set providers.openrouter.model openai/gpt-4o --global
commitize config set provider.default openai --local    # override for just this repo
commitize config edit --global                           # open the file in $EDITOR
```

Example config:

```toml
[provider]
default = "openrouter"

[providers.openrouter]
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
model = "openai/gpt-4o-mini"

[providers.openai]
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
model = "gpt-4o-mini"

[commit]
style = "conventional"     # or "plain"
confirm = true
max_diff_bytes = 8000
sign_off = false
ignore_file = ".commitize-ignore"
```

Add your own OpenAI-compatible provider (e.g. a local Ollama server) with:

```bash
commitize config set providers.local.base_url http://localhost:11434/v1 --global
commitize config set providers.local.model llama3.1 --global
commitize config set providers.local.api_key_env LOCAL_API_KEY --global
commitize config set provider.default local --local
```

List configured providers with `commitize providers list`.

## Development

```bash
uv pip install -e ".[dev]"
pytest
```
