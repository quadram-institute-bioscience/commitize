"""Prompt construction for commit message generation."""

from __future__ import annotations

from commitize.git import StagedChange

SYSTEM_CONVENTIONAL = """\
You write git commit messages from a diff. Follow the Conventional Commits \
format: a subject line like "type(scope): summary" (types: feat, fix, docs, \
style, refactor, perf, test, chore, build, ci), max 72 characters, imperative \
mood, no trailing period. Optionally follow with a blank line and a short \
body (bullet points ok) explaining the "why" if it's not obvious. Output \
ONLY the commit message text -- no markdown fences, no commentary."""

SYSTEM_PLAIN = """\
You write git commit messages from a diff. Write a short imperative subject \
line (max 72 characters, no trailing period), optionally followed by a blank \
line and a brief body explaining the "why" if it's not obvious. Output ONLY \
the commit message text -- no markdown fences, no commentary."""


def build_system_prompt(style: str) -> str:
    return SYSTEM_CONVENTIONAL if style == "conventional" else SYSTEM_PLAIN


def build_user_prompt(change: StagedChange) -> str:
    parts = [f"File changes:\n{change.stat}", f"Diff:\n{change.diff}"]
    if change.truncated:
        parts.append(
            "(Diff was truncated for length; the file summary above is complete.)"
        )
    return "\n\n".join(parts)
