from commitize.context import RepoContext
from commitize.git import StagedChange
from commitize.prompt import build_system_prompt, build_user_prompt

CHANGE = StagedChange(diff="+x\n", stat=" a.py | 1 +\n", truncated=False, files=["a.py"])


def test_user_prompt_leads_with_summary():
    prompt = build_user_prompt(CHANGE, summary="  Removed dead code ")
    assert prompt.startswith("Author summary (the main point of this change):\nRemoved dead code\n")
    assert "Diff:\n+x" in prompt


def test_user_prompt_without_summary():
    for summary in (None, "", "   "):
        assert "Author summary" not in build_user_prompt(CHANGE, summary)


def test_system_prompts_share_body_rules():
    for style in ("conventional", "plain"):
        system = build_system_prompt(style)
        assert "author summary" in system
        assert "subject line alone" in system


def test_user_prompt_includes_context_before_diff():
    context = RepoContext(guidance="Scopes: cli.", recent_commits=["feat(cli): add x", "fix: y"])

    prompt = build_user_prompt(CHANGE, summary="Do z", context=context)

    assert "Maintainer guidance:\n<guidance>\nScopes: cli.\n</guidance>" in prompt
    assert "Recent commit subjects (newest first):\n- feat(cli): add x\n- fix: y" in prompt
    assert prompt.index("<guidance>") < prompt.index("Recent commit") < prompt.index("Author summary")
    assert prompt.index("Author summary") < prompt.index("Diff:")


def test_user_prompt_omits_empty_context():
    prompt = build_user_prompt(CHANGE, context=RepoContext())
    assert "guidance" not in prompt
    assert "Recent commit" not in prompt
