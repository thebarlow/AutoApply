"""Model 2: per-section, schema-driven résumé generation.

Walks the profile tree and makes one focused LLM call per section that has
unlocked LLM-outputable fields, returning authored values keyed by field node
id. Pure of DB; reuses core.job's hardened JSON call. See
docs/superpowers/specs/2026-06-20-section-generation-design.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Union

from pydantic import BaseModel, Field

from core.output_formats import get_format
from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode, build_section_prompt,
)

Value = Union[str, list[str]]


def _critique_block(critique: "list[dict] | None") -> str:
    """A 'fix these issues' block for a section prompt, or '' if no critique."""
    if not critique:
        return ""
    lines = "\n".join(f"- {i.get('description', '')}".rstrip() for i in critique)
    return f"\nFIX THESE ISSUES from the previous draft:\n{lines}\n"


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


def _format_block(fields: "list[FieldNode]") -> str:
    """An '# Output Format' block naming each outputable, registered-format field
    by key with its required JSON shape. '' when no field has a format."""
    seen: dict[str, str] = {}
    for f in fields:
        if not _outputable(f):
            continue
        fmt = get_format(getattr(f, "output_format", "") or "")
        if fmt and f.key not in seen:
            seen[f.key] = fmt.prompt_shape
    if not seen:
        return ""
    body = "\n".join(f'- "{k}": {shape}' for k, shape in seen.items())
    return f"\n# Output Format\nReturn each field's value exactly in the shape described:\n{body}\n"


def _coerce_to_format(value: "Value", field: "FieldNode") -> "Value":
    """Coerce an authored value to its field's output-format kind. Passes the
    value through unchanged when the field has no registered format."""
    fmt = get_format(getattr(field, "output_format", "") or "")
    if fmt is None:
        return value
    if fmt.kind == "bullets":
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        return [
            ln.lstrip("-*• \t").strip()
            for ln in str(value).splitlines()
            if ln.strip()
        ]
    # markdown / text → a single string
    if isinstance(value, list):
        return "\n".join(str(x) for x in value)
    return str(value)


def _build_scalar_prompt(section: SectionNode, group: GroupNode, job_ctx: str, critique=None) -> str:
    """Prompt for a section whose child is a single group (or bare field wrapped)."""
    ctx = "\n".join(_group_context(group)) or "(none)"
    specs = "\n".join(_outputable_specs(group))
    folded = build_section_prompt(section)
    guide = f"{folded}\n\n" if folded else ""
    return (
        f"{guide}You are tailoring the résumé section '{section.name}' to a job.\n\n"
        f"JOB:\n{job_ctx}\n\n"
        f"EXISTING SECTION DATA (anchors — do not change these):\n{ctx}\n\n"
        f"Write tailored content for these fields:\n{specs}\n"
        f"{_critique_block(critique)}"
        f"{_format_block(group.children)}\n"
        'Return JSON: {"fields": {"<field_key>": "<value>"}} containing exactly '
        "the field keys above."
    )


def _build_list_prompt(section: SectionNode, lst: ListNode, job_ctx: str, critique=None) -> str:
    """Prompt for a repeating-list section (one call authors every unlocked entry)."""
    blocks = []
    for entry in lst.children:
        ctx = "\n".join(_group_context(entry)) or "(none)"
        if entry.locked:
            blocks.append(f'ENTRY id="{entry.id}" (FIXED — do not rewrite):\n{ctx}')
            continue
        specs = "\n".join(_outputable_specs(entry))
        blocks.append(
            f'ENTRY id="{entry.id}":\nanchors:\n{ctx}\nwrite:\n{specs}'
        )
    body = "\n\n".join(blocks)
    folded = build_section_prompt(section)
    guide = f"{folded}\n\n" if folded else ""
    fmt_block = _format_block([f for e in lst.children for f in e.children])
    return (
        f"{guide}You are tailoring the résumé section '{section.name}' to a job. Each "
        f"entry is a separate item; write its fields using its own anchors.\n\n"
        f"JOB:\n{job_ctx}\n\n{body}\n"
        f"{_critique_block(critique)}"
        f"{fmt_block}\n"
        'Return JSON: {"entries": {"<entry_id>": {"<field_key>": "<value>"}}} '
        "with an object for every entry id above that is not FIXED."
    )


def _section_child(section: SectionNode):
    """A section has exactly one child (validated)."""
    return section.children[0] if section.children else None


def generate_resume_by_section(
    root: RootNode,
    job_ctx: str,
    client: Any,
    model: str,
    resolve: "Callable[[str], str] | None" = None,
    only_sections: "set[str] | None" = None,
    critiques: "dict[str, list[dict]] | None" = None,
) -> dict[str, Value]:
    """Author every writable field across visible, unlocked sections.

    Makes one LLM call per unlocked section that has writable fields. ``resolve``,
    when given, is applied to each built prompt to substitute ``{job.*}`` /
    ``{profile.*}`` tokens that the user injected into section/item prompts. A
    locked section is skipped entirely; a locked list entry is passed as fixed
    context and never authored. Failed sections contribute nothing.

    Args:
        root: The profile tree.
        job_ctx: Job context markdown (extracted description).
        client: OpenAI-compatible client.
        model: Model identifier.
        resolve: Optional token-substitution callable applied to each prompt.

    Returns:
        ``field_node_id -> authored value`` for every authored field.
    """
    from core.job import _llm_json_with_retry  # local import avoids a cycle

    apply = resolve or (lambda s: s)
    crit = critiques or {}
    out: dict[str, Value] = {}
    for section in root.children:
        if not section.visible or section.locked:
            continue
        if only_sections is not None and section.name not in only_sections:
            continue
        section_critique = crit.get(section.name)
        child = _section_child(section)
        if isinstance(child, ListNode):
            entries_with_work = [
                e for e in child.children
                if not e.locked and any(_outputable(f) for f in e.children)
            ]
            if not entries_with_work:
                continue
            prompt = _build_list_prompt(section, child, job_ctx, critique=section_critique)
        elif isinstance(child, GroupNode):
            if child.locked or not any(_outputable(f) for f in child.children):
                continue
            prompt = _build_scalar_prompt(section, child, job_ctx, critique=section_critique)
        elif isinstance(child, FieldNode):
            if not _outputable(child):
                continue
            # Wrap the bare field as a one-field group for uniform handling.
            prompt = _build_scalar_prompt(
                section, GroupNode(name=section.name, children=[child]), job_ctx,
                critique=section_critique,
            )
        else:
            continue

        try:
            result = _llm_json_with_retry(
                apply(prompt), client, model, SectionOutput, max_tokens=8192,
                empty_msg=f"Section '{section.name}' generation returned empty content.",
            )
        except Exception:
            continue  # failed section falls back to stored values

        if isinstance(child, ListNode):
            by_id = {e.id: e for e in child.children if not e.locked}
            for entry_id, kv in result.entries.items():
                entry = by_id.get(entry_id)
                if entry is None:
                    continue
                for f in entry.children:
                    if _outputable(f) and f.key in kv:
                        out[f.id] = _coerce_to_format(kv[f.key], f)
        else:
            group = child if isinstance(child, GroupNode) else None
            fields = group.children if group else [child]
            for f in fields:
                if _outputable(f) and f.key in result.fields:
                    out[f.id] = _coerce_to_format(result.fields[f.key], f)
    return out
