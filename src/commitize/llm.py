"""Minimal OpenAI-compatible chat-completions client, shared by every provider."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


class LLMAuthError(RuntimeError):
    pass


class LLMRequestError(RuntimeError):
    pass


@dataclass
class Usage:
    """Token and cost totals across every successful call made by one client."""

    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float | None = None  # only reported by some providers (OpenRouter, in USD credits)

    def add(self, usage: dict) -> None:
        self.requests += 1
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        if usage.get("cost") is not None:
            self.cost = (self.cost or 0.0) + float(usage["cost"])


@dataclass
class OpenAICompatibleClient:
    base_url: str
    api_key: str | None
    model: str
    extra_headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    usage: Usage = field(default_factory=Usage)

    def chat(self, system: str, user: str) -> str:
        if not self.api_key:
            raise LLMAuthError(
                "No API key found. Set the provider's api_key_env variable, "
                "or run `commitize config set` to configure one."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }

        url = self.base_url.rstrip("/") + "/chat/completions"
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
        except httpx.RequestError as exc:
            raise LLMRequestError(f"Could not reach {url}: {exc}") from exc

        if response.status_code == 401:
            raise LLMAuthError(f"Authentication failed for {self.base_url} (HTTP 401)")
        if response.status_code >= 400:
            raise LLMRequestError(
                f"{self.base_url} returned HTTP {response.status_code}: {response.text[:300]}"
            )

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMRequestError(f"Unexpected response shape from {self.base_url}: {data}") from exc
        self.usage.add(data.get("usage") or {})
        return content
