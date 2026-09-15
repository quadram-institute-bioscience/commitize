"""Provider presets: named configs that point OpenAICompatibleClient at a given API."""

from __future__ import annotations

from commitize.config import Config
from commitize.llm import OpenAICompatibleClient

# Extra headers recommended/required by specific providers, keyed by provider name.
EXTRA_HEADERS: dict[str, dict[str, str]] = {
    "openrouter": {
        "HTTP-Referer": "https://github.com/commitize",
        "X-Title": "commitize",
    },
}


def build_client(
    config: Config, provider_name: str | None = None, model_override: str | None = None
) -> OpenAICompatibleClient:
    name = provider_name or config.provider_name()
    provider_cfg = config.provider_config(name)
    api_key = config.resolve_api_key(name)

    return OpenAICompatibleClient(
        base_url=provider_cfg["base_url"],
        api_key=api_key,
        model=model_override or provider_cfg["model"],
        extra_headers=EXTRA_HEADERS.get(name, {}),
    )


def list_providers(config: Config) -> list[dict[str, str]]:
    providers = config.get("providers", {})
    return [
        {
            "name": name,
            "base_url": cfg.get("base_url", ""),
            "model": cfg.get("model", ""),
            "api_key_env": cfg.get("api_key_env", ""),
        }
        for name, cfg in providers.items()
    ]
