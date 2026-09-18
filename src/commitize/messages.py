"""Orchestrates: staged diff -> prompt -> LLM -> CommitMessage."""

from __future__ import annotations

import re
from dataclasses import dataclass

from commitize.config import Config
from commitize.git import CommitInfo, StagedChange
from commitize.llm import OpenAICompatibleClient
from commitize.prompt import (
    build_changelog_system_prompt,
    build_changelog_user_prompt,
    build_system_prompt,
    build_user_prompt,
)

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n|\n```$")


@dataclass
class CommitMessage:
    subject: str
    body: str

    @property
    def full_text(self) -> str:
        return f"{self.subject}\n\n{self.body}" if self.body else self.subject


def _clean(raw: str) -> str:
    text = raw.strip()
    text = _FENCE_RE.sub("", text).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1].strip()
    return text


def parse_message(raw: str) -> CommitMessage:
    text = _clean(raw)
    lines = text.splitlines()
    subject = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip()
    return CommitMessage(subject=subject, body=body)


def generate_commit_message(
    client: OpenAICompatibleClient, change: StagedChange, config: Config
) -> CommitMessage:
    style = config.get("commit.style", "conventional")
    system = build_system_prompt(style)
    user = build_user_prompt(change)
    raw = client.chat(system=system, user=user)
    return parse_message(raw)


def generate_changelog(
    client: OpenAICompatibleClient,
    commits: list[CommitInfo],
    existing_text: str | None = None,
) -> str:
    system = build_changelog_system_prompt()
    user = build_changelog_user_prompt(commits, existing_text)
    return client.chat(system=system, user=user)
