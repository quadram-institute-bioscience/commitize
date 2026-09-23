"""Prompt construction for commit message generation."""

from __future__ import annotations

from commitize.context import RepoContext
from commitize.git import CommitInfo, StagedChange

_BODY_RULES = """\
Body: most commits need none. The body is only for OTHER changes that the \
subject line does not cover and that someone reading `git log` would want to \
know about. Write each as a "- " bullet in the imperative, at most five, \
wrapped at 72 columns, after a blank line.

A separate change qualifies for a bullet if it is visible outside the code \
it touches, for example:
- behaviour a user or caller can observe (features, options, commands, \
outputs, defaults, error handling)
- public API, config format or file format changes
- added, removed or upgraded dependencies
- a substantial refactor, removal or move of code

These are part of the subject's change, not separate changes, so they never \
get a bullet: passing a new value through functions, updating call sites, \
tests for the change, docs or help text for the change. Formatting, \
whitespace, import order, typo and comment fixes never get one either.

Example: a diff adds a --json flag, threads it through three functions, \
adds tests for it, and also raises the default timeout. The message is:

  feat(cli): add --json flag for machine-readable output

  - Raise the default request timeout from 10s to 30s

Without the timeout change it would be the subject line alone.

The user message may start with context about the repository:
- Maintainer guidance: rules the maintainers wrote for commit messages in \
this repository. Follow them; they override the defaults above.
- Recent commit subjects: match their scope names, casing and wording where \
they fit. Never copy their content.
The message describes only what the diff shows, never the context.

If an author summary is given, it names the most important thing this \
change does. Build the subject line around it, using the diff for accuracy \
and detail.

Output ONLY the commit message text -- no markdown fences, no commentary."""

SYSTEM_CONVENTIONAL = f"""\
You write git commit messages from a diff. Follow the Conventional Commits \
format: a subject line like "type(scope): summary" (types: feat, fix, docs, \
style, refactor, perf, test, chore, build, ci), max 72 characters, imperative \
mood, no trailing period.

{_BODY_RULES}"""

SYSTEM_PLAIN = f"""\
You write git commit messages from a diff. Write a short imperative subject \
line (max 72 characters, no trailing period).

{_BODY_RULES}"""


def build_system_prompt(style: str) -> str:
    return SYSTEM_CONVENTIONAL if style == "conventional" else SYSTEM_PLAIN


def build_user_prompt(
    change: StagedChange,
    summary: str | None = None,
    context: RepoContext | None = None,
) -> str:
    parts = []
    if context and context.guidance:
        parts.append(f"Maintainer guidance:\n<guidance>\n{context.guidance}\n</guidance>")
    if context and context.recent_commits:
        subjects = "\n".join(f"- {s}" for s in context.recent_commits)
        parts.append(f"Recent commit subjects (newest first):\n{subjects}")
    if summary and summary.strip():
        parts.append(f"Author summary (the main point of this change):\n{summary.strip()}")
    parts += [f"File changes:\n{change.stat}", f"Diff:\n{change.diff}"]
    if change.truncated:
        parts.append(
            "(Diff was truncated for length; the file summary above is complete.)"
        )
    return "\n\n".join(parts)


SYSTEM_CHANGELOG = """\
You write changelog entries from a list of git commit messages. Group the \
changes under exactly these three headings, in this order:

## New features
## Bug fixes
## Other changes

Use concise, imperative bullet points (one per meaningful change), deduplicate \
closely related commits, and drop trivial noise such as formatting-only tweaks \
and merge commits. Output ONLY the changelog text -- no markdown fences, no \
commentary."""


def build_changelog_system_prompt() -> str:
    return SYSTEM_CHANGELOG


def build_changelog_user_prompt(
    commits: list[CommitInfo], existing: str | None = None
) -> str:
    lines = ["Commits since the last release:"]
    for commit in commits:
        entry = f"- {commit.subject}"
        if commit.body:
            entry += f"\n  {commit.body}"
        lines.append(entry)

    parts = ["\n".join(lines)]
    if existing:
        parts.append(
            "Here is the existing changelog. Integrate the new changes by adding "
            "a new section for this release at the top, keeping the existing "
            f"content below unchanged:\n\n{existing}"
        )
    return "\n\n".join(parts)
