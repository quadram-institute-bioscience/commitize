"""Config loading, merging, and editing for commitize.

Precedence (later wins): built-in defaults < global file < repo-local file.
Environment variables and CLI flags are applied on top of this by callers
(git.py / cli.py), not here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import tomlkit
from platformdirs import user_config_dir

APP_NAME = "commitize"
LOCAL_CONFIG_FILENAME = ".commitize.toml"

DEFAULTS: dict[str, Any] = {
    "provider": {"default": "openrouter"},
    "providers": {
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
            "model": "deepseek/deepseek-v4-flash",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
            "model": "gpt-4o-mini",
        },
    },
    "commit": {
        "style": "conventional",
        "confirm": True,
        "max_diff_bytes": 8000,
        "sign_off": False,
        "ignore_file": ".commitize-ignore",
        "context_file": ".commitize-context.md",
        "max_context_bytes": 4000,
        "recent_commits": 15,
    },
}

# Keys under [providers.<name>] whose values should be masked in `config show`.
SECRET_KEYS = {"api_key"}


def global_config_path() -> Path:
    return Path(user_config_dir(APP_NAME)) / "config.toml"


def find_local_config_path(start: Path | None = None) -> Path | None:
    """Return the path to a .commitize.toml at the repo root, if one exists."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start or Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    repo_root = Path(result.stdout.strip())
    candidate = repo_root / LOCAL_CONFIG_FILENAME
    return candidate if candidate.exists() else None


def local_config_target(start: Path | None = None) -> Path:
    """Path a new/edited local config should live at, even if it doesn't exist yet."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start or Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("Not inside a git repository; cannot use --local config")
    return Path(result.stdout.strip()) / LOCAL_CONFIG_FILENAME


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomlkit.parse(path.read_text()).unwrap()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class ResolvedValue:
    value: Any
    source: str  # "default" | "global" | "local"


class Config:
    """Effective merged configuration, with provenance tracking for `show`."""

    def __init__(self, data: dict[str, Any], sources: dict[str, dict[str, Any]]):
        self._data = data
        # sources maps layer name -> raw dict loaded from that layer, for provenance
        self._sources = sources

    @classmethod
    def load(cls, cwd: Path | None = None) -> "Config":
        global_data = _load_toml(global_config_path())
        local_path = find_local_config_path(cwd)
        local_data = _load_toml(local_path) if local_path else {}

        merged = _deep_merge(DEFAULTS, global_data)
        merged = _deep_merge(merged, local_data)

        return cls(
            merged,
            {"default": DEFAULTS, "global": global_data, "local": local_data},
        )

    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def provider_name(self) -> str:
        return self.get("provider.default", "openrouter")

    def provider_config(self, name: str | None = None) -> dict[str, Any]:
        name = name or self.provider_name()
        cfg = self.get(f"providers.{name}")
        if cfg is None:
            raise KeyError(f"No provider named '{name}' in config")
        return cfg

    def source_of(self, dotted_key: str) -> str:
        """Which layer ('local', 'global', or 'default') last set this key."""
        parts = dotted_key.split(".")
        for layer in ("local", "global", "default"):
            node = self._sources[layer]
            found = True
            for part in parts:
                if not isinstance(node, dict) or part not in node:
                    found = False
                    break
                node = node[part]
            if found:
                return layer
        return "default"

    def iter_leaves(self) -> Iterator[tuple[str, Any]]:
        def _walk(prefix: str, node: Any) -> Iterator[tuple[str, Any]]:
            if isinstance(node, dict):
                for k, v in node.items():
                    yield from _walk(f"{prefix}.{k}" if prefix else k, v)
            else:
                yield prefix, node

        yield from _walk("", self._data)

    def resolve_api_key(self, provider_name: str | None = None) -> str | None:
        cfg = self.provider_config(provider_name)
        if "api_key" in cfg and cfg["api_key"]:
            return str(cfg["api_key"])
        env_var = cfg.get("api_key_env")
        if env_var:
            return os.environ.get(env_var)
        return None


def write_defaults(path: Path, force: bool = False) -> bool:
    """Write the built-in defaults to `path`.

    Returns False (writing nothing) if the file already exists and ``force``
    is not set.
    """
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# commitize configuration\n"
        "# Generated by `commitize config init`; these are the built-in defaults.\n"
        "# Edit values as needed, then remove anything you are happy to inherit.\n\n"
    )
    path.write_text(header + tomlkit.dumps(DEFAULTS))
    return True


def set_value(path: Path, dotted_key: str, value: Any) -> None:
    """Set a dotted key inside the TOML file at `path`, creating it if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.parse(path.read_text()) if path.exists() else tomlkit.document()

    parts = dotted_key.split(".")
    node: Any = doc
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], (dict, tomlkit.items.Table)):
            node[part] = tomlkit.table()
        node = node[part]
    node[parts[-1]] = _coerce(value)

    path.write_text(tomlkit.dumps(doc))


def _coerce(value: str) -> Any:
    """Coerce a CLI string value to bool/int/float when it obviously looks like one."""
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    return value
