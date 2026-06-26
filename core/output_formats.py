"""Output formats: named descriptors that bind an LLM JSON shape, a storage
kind, and a render behavior for an LLM-authored résumé prose field.

Pure module — no DB, LLM, or filesystem. A field references a format by id;
the format's ``kind`` aligns the FieldNode storage/render, and ``prompt_shape``
is injected into the section generation prompt's "# Output Format" block.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputFormat:
    """One output format.

    Attributes:
        id: Stable identifier stored on a field (e.g. ``"bullets"``).
        label: Human label for the picker (e.g. ``"Bullet list"``).
        kind: The ``FieldNode.kind`` this format aligns to — ``"bullets"``
            (stored ``list[str]``) or ``"markdown"`` (stored ``str``).
        prompt_shape: Per-field instruction text for the prompt's
            "# Output Format" block describing the JSON shape to return.
    """

    id: str
    label: str
    kind: str
    prompt_shape: str


BULLETS = OutputFormat(
    id="bullets",
    label="Bullet list",
    kind="bullets",
    prompt_shape=(
        "an array of concise bullet strings, one achievement per bullet, "
        "at most 2 bullets, each at most 120 characters"
    ),
)

PARAGRAPH = OutputFormat(
    id="paragraph",
    label="Paragraph",
    kind="markdown",
    prompt_shape="a single flowing paragraph string, no bullet points",
)

_REGISTRY: dict[str, OutputFormat] = {f.id: f for f in (BULLETS, PARAGRAPH)}

DEFAULT_FORMAT_ID = "paragraph"


def get_format(format_id: str) -> OutputFormat | None:
    """Return the registered format for ``format_id``, or None if unknown/empty."""
    return _REGISTRY.get(format_id or "")


def all_formats() -> list[OutputFormat]:
    """All registered formats, registry order."""
    return list(_REGISTRY.values())
