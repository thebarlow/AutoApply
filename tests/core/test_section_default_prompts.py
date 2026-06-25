from __future__ import annotations

from core.profile_tree import backfill_section_prompts, legacy_to_tree
from core.section_presets import SECTION_PROMPT_DEFAULTS


def _roles(root):
    return {s.role: s for s in root.children}


def test_legacy_to_tree_seeds_section_prompts():
    """A freshly built tree carries the role-keyed default prompts."""
    root = legacy_to_tree({})
    sections = _roles(root)
    for role, default in SECTION_PROMPT_DEFAULTS.items():
        assert sections[role].prompt == default


def test_header_and_education_have_no_default_prompt():
    """Roles without a default are left blank."""
    sections = _roles(legacy_to_tree({}))
    assert sections["header"].prompt == ""
    assert sections["education"].prompt == ""


def test_backfill_fills_only_empty_prompts():
    """Backfill seeds blank section prompts and reports a change."""
    root = legacy_to_tree({})
    for s in root.children:
        s.prompt = ""  # simulate a legacy persisted tree

    changed = backfill_section_prompts(root)

    assert changed is True
    sections = _roles(root)
    for role, default in SECTION_PROMPT_DEFAULTS.items():
        assert sections[role].prompt == default


def test_backfill_preserves_user_authored_prompts():
    """A non-empty section prompt is never overwritten."""
    root = legacy_to_tree({})
    sections = _roles(root)
    sections["summary"].prompt = "my custom summary guidance"

    backfill_section_prompts(root)

    assert _roles(root)["summary"].prompt == "my custom summary guidance"


def test_backfill_idempotent():
    """Running backfill on an already-seeded tree changes nothing."""
    root = legacy_to_tree({})
    assert backfill_section_prompts(root) is False
