"""Model 2: per-section, schema-driven résumé generation.

Walks the profile tree and makes one focused LLM call per section that has
unlocked LLM-outputable fields, returning authored values keyed by field node
id. Pure of DB; reuses core.job's hardened JSON call. See
docs/superpowers/specs/2026-06-20-section-generation-design.md.
"""

from __future__ import annotations

from typing import Any, Union

from pydantic import BaseModel, Field

from core.profile_tree import FieldNode, GroupNode, ListNode, RootNode, SectionNode

Value = Union[str, list[str]]


class SectionOutput(BaseModel):
    """One section's LLM output. Scalar sections fill ``fields``; list sections
    fill ``entries`` (keyed by entry node id, then field key)."""

    fields: dict[str, Value] = Field(default_factory=dict)
    entries: dict[str, dict[str, Value]] = Field(default_factory=dict)


def _outputable(field: FieldNode) -> bool:
    """A field the LLM should (re)write this run: outputable and not pinned."""
    return field.llm_output and not field.regen_lock


def _render_field_context(field: FieldNode) -> str:
    """One context line for an immutable/context-only field."""
    val = field.value if isinstance(field.value, str) else ", ".join(field.value)
    return f"- {field.name} ({field.key}): {val}"


def _group_context(group: GroupNode) -> list[str]:
    """Context lines for a group's non-outputable, visible fields."""
    return [
        _render_field_context(f)
        for f in group.children
        if f.visible and not f.llm_output
    ]


def _outputable_specs(group: GroupNode) -> list[str]:
    """Instruction lines for a group's unlocked outputable fields."""
    return [
        f'- "{f.key}": {f.llm_instructions or ("Write the " + f.name)}'
        for f in group.children
        if _outputable(f)
    ]


def _build_scalar_prompt(section: SectionNode, group: GroupNode, job_ctx: str) -> str:
    """Prompt for a section whose child is a single group (or bare field wrapped)."""
    ctx = "\n".join(_group_context(group)) or "(none)"
    specs = "\n".join(_outputable_specs(group))
    return (
        f"You are tailoring the résumé section '{section.name}' to a job.\n\n"
        f"JOB:\n{job_ctx}\n\n"
        f"EXISTING SECTION DATA (anchors — do not change these):\n{ctx}\n\n"
        f"Write tailored content for these fields:\n{specs}\n\n"
        'Return JSON: {"fields": {"<field_key>": "<value>"}} containing exactly '
        "the field keys above."
    )


def _build_list_prompt(section: SectionNode, lst: ListNode, job_ctx: str) -> str:
    """Prompt for a repeating-list section (one call authors every entry)."""
    blocks = []
    for entry in lst.children:
        ctx = "\n".join(_group_context(entry)) or "(none)"
        specs = "\n".join(_outputable_specs(entry))
        blocks.append(f'ENTRY id="{entry.id}":\nanchors:\n{ctx}\nwrite:\n{specs}')
    body = "\n\n".join(blocks)
    return (
        f"You are tailoring the résumé section '{section.name}' to a job. Each "
        f"entry is a separate item; write its fields using its own anchors.\n\n"
        f"JOB:\n{job_ctx}\n\n{body}\n\n"
        'Return JSON: {"entries": {"<entry_id>": {"<field_key>": "<value>"}}} '
        "with an object for every entry id above."
    )


def _section_child(section: SectionNode):
    """A section has exactly one child (validated)."""
    return section.children[0] if section.children else None


def generate_resume_by_section(
    root: RootNode, job_ctx: str, client: Any, model: str
) -> dict[str, Value]:
    """Author every unlocked outputable field across visible sections.

    Makes one LLM call per section that has unlocked outputable fields. A section
    whose call fails to parse contributes nothing (its fields fall back to stored
    values downstream) and generation continues with the next section.

    Args:
        root: The profile tree.
        job_ctx: Job context markdown (extracted description).
        client: OpenAI-compatible client.
        model: Model identifier.

    Returns:
        ``field_node_id -> authored value`` for every authored field.
    """
    from core.job import _llm_json_with_retry  # local import avoids a cycle

    out: dict[str, Value] = {}
    for section in root.children:
        if not section.visible:
            continue
        child = _section_child(section)
        if isinstance(child, ListNode):
            entries_with_work = [e for e in child.children if any(_outputable(f) for f in e.children)]
            if not entries_with_work:
                continue
            prompt = _build_list_prompt(section, child, job_ctx)
        elif isinstance(child, GroupNode):
            if not any(_outputable(f) for f in child.children):
                continue
            prompt = _build_scalar_prompt(section, child, job_ctx)
        elif isinstance(child, FieldNode):
            if not _outputable(child):
                continue
            # Wrap the bare field as a one-field group for uniform handling.
            prompt = _build_scalar_prompt(section, GroupNode(name=section.name, children=[child]), job_ctx)
        else:
            continue

        try:
            result = _llm_json_with_retry(
                prompt, client, model, SectionOutput, max_tokens=8192,
                empty_msg=f"Section '{section.name}' generation returned empty content.",
            )
        except Exception:
            continue  # failed section falls back to stored values

        if isinstance(child, ListNode):
            by_id = {e.id: e for e in child.children}
            for entry_id, kv in result.entries.items():
                entry = by_id.get(entry_id)
                if entry is None:
                    continue
                for f in entry.children:
                    if _outputable(f) and f.key in kv:
                        out[f.id] = kv[f.key]
        else:
            group = child if isinstance(child, GroupNode) else None
            fields = group.children if group else [child]
            for f in fields:
                if _outputable(f) and f.key in result.fields:
                    out[f.id] = result.fields[f.key]
    return out
