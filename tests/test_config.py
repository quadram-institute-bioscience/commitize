from pathlib import Path

from commitize import config as config_mod
from commitize.config import Config, set_value


def test_merge_precedence_local_overrides_global(tmp_path, monkeypatch):
    global_path = tmp_path / "global" / "config.toml"
    local_path = tmp_path / "repo" / ".commitize.toml"
    local_path.parent.mkdir(parents=True)
    global_path.parent.mkdir(parents=True)

    global_path.write_text(
        '[provider]\ndefault = "openai"\n\n[providers.openrouter]\nmodel = "global-model"\n'
    )
    local_path.write_text('[providers.openrouter]\nmodel = "local-model"\n')

    monkeypatch.setattr(config_mod, "global_config_path", lambda: global_path)
    monkeypatch.setattr(config_mod, "find_local_config_path", lambda start=None: local_path)

    cfg = Config.load()

    assert cfg.get("provider.default") == "openai"  # from global, default was "openrouter"
    assert cfg.get("providers.openrouter.model") == "local-model"  # local wins
    assert cfg.get("providers.openrouter.base_url") == "https://openrouter.ai/api/v1"  # default survives

    assert cfg.source_of("providers.openrouter.model") == "local"
    assert cfg.source_of("provider.default") == "global"
    assert cfg.source_of("providers.openrouter.base_url") == "default"


def test_defaults_when_no_files_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "global_config_path", lambda: tmp_path / "nope.toml")
    monkeypatch.setattr(config_mod, "find_local_config_path", lambda start=None: None)

    cfg = Config.load()

    assert cfg.provider_name() == "openrouter"
    assert cfg.get("commit.style") == "conventional"


def test_resolve_api_key_from_env(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "global_config_path", lambda: tmp_path / "nope.toml")
    monkeypatch.setattr(config_mod, "find_local_config_path", lambda start=None: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-123")

    cfg = Config.load()
    assert cfg.resolve_api_key("openrouter") == "sk-test-123"


def test_set_value_creates_and_updates_file(tmp_path):
    path = tmp_path / "config.toml"
    set_value(path, "provider.default", "openai")
    assert 'default = "openai"' in path.read_text()

    set_value(path, "commit.max_diff_bytes", "5000")
    text = path.read_text()
    assert "max_diff_bytes = 5000" in text
    assert 'default = "openai"' in text  # earlier key preserved
