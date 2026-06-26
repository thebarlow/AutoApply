# Output formats (#6B-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users pick a named output format (Bullet list / Paragraph) per LLM-authored résumé prose field; the format drives both the LLM's returned JSON shape and the deterministic rendering.

**Architecture:** A new pure registry (`core/output_formats.py`) defines the formats. `FieldNode` gains an `output_format` attribute; section presets default the prose fields. `section_generator` injects an "# Output Format" block into each section prompt and coerces the response per field; `tree_assembler` renders by the stored value's structure. A one-time backfill converts existing Experience bullet-strings into arrays. A profile-tree `<select>` lets users change a field's format.

**Tech Stack:** Python (Pydantic v2, pytest), React (Vitest + RTL), no new dependencies.

## Global Constraints

- Tree-v1 résumé only; do NOT touch the legacy `ResumeGeneration` whole-résumé path or cover letters. (Spec: "Tree-v1 résumé only.")
- Ship exactly **two** formats: `bullets` ("Bullet list") and `paragraph` ("Paragraph"). (Spec: "Initial set: two formats.")
- Format is the single driver: a field's `output_format` maps via the registry to a storage `kind` + render + LLM shape. Empty `output_format` = today's behavior (back-compat, no coercion). (Spec §2, §Decisions.)
- The format `kind` alignment: `bullets` → `FieldNode.kind="bullets"` (stored `list[str]`); `paragraph` → `kind="markdown"` (stored `str`). (Spec §1.)
- An `output_format` not found in the registry is treated as unset — never crash a prompt build or render. (Spec §Error handling.)
- The migration backfill is idempotent, fills only fields whose `output_format` is unset, never overwrites a user-set format, and a DB backup is taken before running. (Spec §6.)
- No new npm or pip dependencies.
- Release constraint: merges to LOCAL `main` only — do NOT push `main`.

**Reference patterns (read before starting):**
- `core/profile_tree.py:28-54` — `FieldNode` (fields + the `value` normalizer that coerces by `kind`).
- `core/section_presets.py` — preset section/template factories (where defaults are set); `SECTION_PROMPT_DEFAULTS` pattern at the top.
- `core/section_generator.py:59-107` — `_outputable`, `_outputable_specs`, `_build_scalar_prompt`, `_build_list_prompt`; `:115-200` — `generate_resume_by_section` (where values are stored into `out`).
- `core/tree_assembler.py:19-34` — `_render_field`; `:141-170` — `_list_rows` / `_experience_section_md`.
- `core/profile_tree.py:298-320` — `backfill_section_prompts` (the backfill pattern to mirror) and `scripts/backfill_section_prompts.py` + `scripts/__init__.py`.
- `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx:23-58` — `FieldView` (where the format `<select>` goes); `fieldWidgets.jsx:316-324` — `FieldWidget` kind dispatch.
- `react-dashboard/src/components/widgets/profile-tree/treeOps.js:195-212` — `setLlmInstructions` / `toggleLlmWritten` (op pattern); `ProfileTreeEditor.jsx:42-52` — the `ops` object.
- `react-dashboard/src/api.js` — `_fetch` + export pattern.
- `web/routers/skills.py` or `web/routers/config.py` — simple GET endpoint pattern.

---

### Task 1: Output format registry

**Files:**
- Create: `core/output_formats.py`
- Test: `tests/core/test_output_formats.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass(frozen=True) OutputFormat` with fields `id: str`, `label: str`, `kind: str`, `prompt_shape: str`.
  - `get_format(format_id: str) -> OutputFormat | None`
  - `all_formats() -> list[OutputFormat]`
  - `DEFAULT_FORMAT_ID = "paragraph"`
  - module constants `BULLETS`, `PARAGRAPH`.

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_output_formats.py`:

```python
from __future__ import annotations

from core.output_formats import (
    OutputFormat, get_format, all_formats, DEFAULT_FORMAT_ID, BULLETS, PARAGRAPH,
)


def test_registry_has_exactly_two_formats():
    ids = {f.id for f in all_formats()}
    assert ids == {"bullets", "paragraph"}


def test_bullets_aligns_to_bullets_kind():
    assert BULLETS.id == "bullets"
    assert BULLETS.kind == "bullets"
    assert BULLETS.label == "Bullet list"
    assert BULLETS.prompt_shape.strip()


def test_paragraph_aligns_to_markdown_kind():
    assert PARAGRAPH.id == "paragraph"
    assert PARAGRAPH.kind == "markdown"
    assert PARAGRAPH.label == "Paragraph"


def test_get_format_returns_none_for_unknown():
    assert get_format("nope") is None
    assert get_format("") is None


def test_default_format_id_is_registered():
    assert get_format(DEFAULT_FORMAT_ID) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_output_formats.py -q`
Expected: FAIL — `ModuleNotFoundError: core.output_formats`.

- [ ] **Step 3: Write the registry**

Create `core/output_formats.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_output_formats.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add core/output_formats.py tests/core/test_output_formats.py
git commit -m "[feat] Add output format registry (bullets, paragraph)"
```

---

### Task 2: `FieldNode.output_format` schema attribute

**Files:**
- Modify: `core/profile_tree.py` (the `FieldNode` model, around line 35)
- Test: `tests/core/test_profile_tree.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `FieldNode.output_format: str = ""` — an optional attribute later tasks read via `getattr(field, "output_format", "")` / `field.output_format`. Serializes through `model_dump`/`model_validate`.

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_profile_tree.py`:

```python
def test_field_output_format_defaults_empty_and_round_trips():
    from core.profile_tree import FieldNode
    f = FieldNode(name="Summary", key="summary", kind="markdown")
    assert f.output_format == ""
    f2 = FieldNode(name="Summary", key="summary", kind="bullets", output_format="bullets")
    dumped = f2.model_dump(mode="json")
    assert dumped["output_format"] == "bullets"
    assert FieldNode.model_validate(dumped).output_format == "bullets"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_profile_tree.py::test_field_output_format_defaults_empty_and_round_trips -q`
Expected: FAIL — `output_format` is not a field / `AttributeError`.

- [ ] **Step 3: Add the attribute**

In `core/profile_tree.py`, in the `FieldNode` model, add the attribute immediately after the `llm_instructions: str = ""` line (around line 35):

```python
    llm_instructions: str = ""
    output_format: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_profile_tree.py -q`
Expected: PASS (all existing + the new test).

- [ ] **Step 5: Commit**

```bash
git add core/profile_tree.py tests/core/test_profile_tree.py
git commit -m "[feat] Add FieldNode.output_format attribute"
```

---

### Task 3: Generation wiring — "# Output Format" block + response coercion

**Files:**
- Modify: `core/section_generator.py`
- Test: `tests/core/test_section_generator_formats.py` (create)

**Interfaces:**
- Consumes: `core.output_formats.get_format`; `FieldNode.output_format` (Task 2).
- Produces (module-internal, used by later behavior): a `_format_block(fields) -> str` helper and per-field coercion applied inside `generate_resume_by_section` so a `bullets`-format field is stored as `list[str]` and a `paragraph`-format field as `str`.

**Behavior:** When a section's prompt is built, append an "# Output Format" block listing each outputable field (by key) that has a registered format, with its `prompt_shape`. After the LLM response returns, coerce each authored field's value to its format's `kind` before storing into `out`.

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_section_generator_formats.py`:

```python
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, RootNode, SectionNode
from core.section_generator import _format_block, _coerce_to_format


def _exp_section():
    item = GroupNode(name="Experience Item", children=[
        FieldNode(name="Company", key="company", kind="text", value="Acme"),
        FieldNode(name="Summary", key="summary", kind="bullets",
                  llm_output=True, output_format="bullets"),
    ])
    return SectionNode(name="Experience", role="experience", children=[
        ListNode(name="Experience", item_template=item, children=[item.model_copy(deep=True)]),
    ])


def test_format_block_lists_outputable_formatted_fields():
    fields = _exp_section().children[0].children[0].children
    block = _format_block(fields)
    assert "# Output Format" in block
    assert '"summary"' in block
    assert "array of concise bullet strings" in block
    # non-output / unformatted fields are not listed
    assert '"company"' not in block


def test_format_block_empty_when_no_formats():
    fields = [FieldNode(name="X", key="x", kind="markdown", llm_output=True)]
    assert _format_block(fields) == ""


def test_coerce_bullets_splits_string_into_list():
    f = FieldNode(name="S", key="summary", kind="bullets", llm_output=True, output_format="bullets")
    assert _coerce_to_format("- did A\n- did B", f) == ["did A", "did B"]
    assert _coerce_to_format(["x", " y "], f) == ["x", "y"]


def test_coerce_paragraph_joins_list_into_string():
    f = FieldNode(name="H", key="hero", kind="markdown", llm_output=True, output_format="paragraph")
    assert _coerce_to_format(["one", "two"], f) == "one\ntwo"
    assert _coerce_to_format("hello", f) == "hello"


def test_coerce_passthrough_when_no_format():
    f = FieldNode(name="H", key="hero", kind="markdown", llm_output=True)
    assert _coerce_to_format("hello", f) == "hello"
    assert _coerce_to_format(["a"], f) == ["a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_section_generator_formats.py -q`
Expected: FAIL — `_format_block` / `_coerce_to_format` not defined.

- [ ] **Step 3: Implement the helpers and wire them in**

In `core/section_generator.py`, add the import near the top (after the existing `from core.profile_tree import ...`):

```python
from core.output_formats import get_format
```

Add these two helpers (place them after `_outputable_specs`, around line 66):

```python
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
```

Now append the format block to both prompt builders. In `_build_scalar_prompt`, change the final `return (...)` so the block is inserted before the `'Return JSON: ...'` line:

```python
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
```

In `_build_list_prompt`, insert the block (built from every entry's fields) before the final `'Return JSON: ...'` line:

```python
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
```

Finally, apply coercion where values are stored in `generate_resume_by_section`. Replace the two storage sites (the list branch and the scalar/group branch near the end of the function):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_section_generator_formats.py tests/core/test_section_generator.py tests/core/test_section_generator_filter.py -q`
Expected: PASS (new file + the two existing generator suites still green — existing trees have no `output_format`, so `_format_block` is empty and `_coerce_to_format` passes values through).

- [ ] **Step 5: Commit**

```bash
git add core/section_generator.py tests/core/test_section_generator_formats.py
git commit -m "[feat] Section generator: # Output Format block + per-field coercion"
```

---

### Task 4: Rendering — render the body by its structure

**Files:**
- Modify: `core/tree_assembler.py` (`_experience_section_md`, around line 153)
- Test: `tests/core/test_tree_assembler_formats.py` (create)

**Interfaces:**
- Consumes: nothing new (renders the already-coerced value).
- Produces: a `_render_body(value) -> str` helper; the experience formatter renders its `summary` value through it (a `list` → `- ` lines, a `str` → prose). The generic `_render_field` already handles `bullets`/`markdown` for non-experience sections; this task only fixes the bespoke experience formatter that read the raw value as a string.

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_tree_assembler_formats.py`:

```python
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode
from core.tree_assembler import _experience_section_md, _render_body


def _exp(summary_value, kind):
    entry = GroupNode(name="Experience Item", children=[
        FieldNode(name="Title", key="title", kind="text", value="Engineer"),
        FieldNode(name="Company", key="company", kind="text", value="Acme"),
        FieldNode(name="Summary", key="summary", kind=kind, value=summary_value),
    ])
    return SectionNode(name="Experience", role="experience", children=[
        ListNode(name="Experience", item_template=entry.model_copy(deep=True), children=[entry]),
    ])


def test_render_body_list_becomes_bullets():
    assert _render_body(["did A", "did B"]) == "- did A\n- did B"


def test_render_body_string_is_prose():
    assert _render_body("Led a team.") == "Led a team."


def test_experience_renders_bullets_for_list_value():
    md = _experience_section_md(_exp(["shipped X", "owned Y"], "bullets"))
    assert "- shipped X" in md and "- owned Y" in md
    assert "### Engineer, Acme" in md


def test_experience_renders_paragraph_for_string_value():
    md = _experience_section_md(_exp("Led a cross-functional team.", "markdown"))
    assert "Led a cross-functional team." in md
    assert "- Led" not in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_tree_assembler_formats.py -q`
Expected: FAIL — `_render_body` not defined; the list-value case renders `['shipped X', 'owned Y']` (str of a list) rather than bullets.

- [ ] **Step 3: Implement**

In `core/tree_assembler.py`, add the helper above `_experience_section_md` (around line 152):

```python
def _render_body(value: object) -> str:
    """Render an authored body value: a list → ``- `` bullet lines, else prose."""
    if isinstance(value, list):
        items = [str(x).strip() for x in value if str(x).strip()]
        return "\n".join(f"- {x}" for x in items)
    return str(value).strip()
```

Then in `_experience_section_md`, replace the summary handling so it renders structurally:

```python
def _experience_section_md(section: SectionNode) -> str:
    rows = _list_rows(section)
    if not rows:
        return ""
    parts = [f"## {section.name}"]
    for r in rows:
        dates = " – ".join(
            x for x in (str(r.get("start", "")).strip(), str(r.get("end", "")).strip()) if x
        )
        heading = f"### {str(r.get('title', '')).strip()}, {str(r.get('company', '')).strip()}".strip(", ")
        if dates:
            heading += f" ({dates})"
        block = heading
        summary = _render_body(r.get("summary", ""))
        if summary:
            block += "\n\n" + summary
        parts.append(block)
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_tree_assembler_formats.py tests/core/test_tree_assembler.py tests/core/test_tree_assembler_lists.py tests/core/test_tree_assembler_presets.py -q`
Expected: PASS (new file + the existing assembler suites — existing string summaries still render as prose, unchanged).

- [ ] **Step 5: Commit**

```bash
git add core/tree_assembler.py tests/core/test_tree_assembler_formats.py
git commit -m "[feat] Tree assembler: render experience body by structure (bullets/prose)"
```

---

### Task 5: Preset defaults

**Files:**
- Modify: `core/section_presets.py` (`experience_template`, `summary_section`, `projects_template`)
- Test: `tests/core/test_section_default_prompts.py` (append) — reuses the existing `legacy_to_tree` test file in that suite, or create `tests/core/test_preset_output_formats.py`.

**Interfaces:**
- Consumes: format ids `"bullets"`, `"paragraph"`.
- Produces: preset prose fields carry `output_format` and aligned `kind`: Experience item `summary` → `output_format="bullets"`, `kind="bullets"`; Summary `hero` → `output_format="paragraph"` (kind stays `markdown`); Project `description` → `output_format="paragraph"` (kind stays `markdown`).

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_preset_output_formats.py`:

```python
from __future__ import annotations

from core.profile_tree import legacy_to_tree


def _field(root, role, key):
    section = next(s for s in root.children if s.role == role)
    child = section.children[0]
    if child.type == "list":
        fields = child.children[0].children  # first instance, cloned from template
    elif child.type == "group":
        fields = child.children
    else:
        fields = [child]
    return next(f for f in fields if f.key == key)


def test_experience_summary_defaults_to_bullets():
    root = legacy_to_tree({"work_history": [{"title": "Eng", "company": "Acme", "summary": "x"}]})
    f = _field(root, "experience", "summary")
    assert f.output_format == "bullets"
    assert f.kind == "bullets"


def test_summary_hero_defaults_to_paragraph():
    root = legacy_to_tree({"hero": "I build things."})
    f = _field(root, "summary", "hero")
    assert f.output_format == "paragraph"
    assert f.kind == "markdown"


def test_project_description_defaults_to_paragraph():
    root = legacy_to_tree({"projects": [{"name": "P", "description": "d"}]})
    f = _field(root, "projects", "description")
    assert f.output_format == "paragraph"
    assert f.kind == "markdown"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_preset_output_formats.py -q`
Expected: FAIL — `output_format` is empty on the preset fields; experience `summary.kind` is `markdown`, not `bullets`.

- [ ] **Step 3: Set the preset defaults**

In `core/section_presets.py`:

In `experience_template`, change the `summary` field:

```python
            FieldNode(
                name="Summary", key="summary", kind="bullets", order=4,
                llm_output=True, output_format="bullets",
            ),
```

In `summary_section`, change the `hero` field:

```python
            FieldNode(
                name="Summary", key="hero", kind="markdown", order=0,
                llm_output=True, output_format="paragraph",
            )
```

In `projects_template`, change the `description` field:

```python
            FieldNode(
                name="Description",
                key="description",
                kind="markdown",
                order=1,
                llm_output=True,
                output_format="paragraph",
            ),
```

**Also** propagate `output_format` when `legacy_to_tree` clones list instances from a template. In `core/profile_tree.py`, find the `_instances` inner helper inside `legacy_to_tree` (around line 222) where each instance field is built as `FieldNode(name=t.name, key=t.key, kind=t.kind, order=t.order, llm_output=t.llm_output, value=vals.get(t.key, ""))`, and add `output_format` so list-item fields (Experience `summary`, Project `description`) carry the template's format:

```python
                FieldNode(
                    name=t.name,
                    key=t.key,
                    kind=t.kind,
                    order=t.order,
                    llm_output=t.llm_output,
                    output_format=getattr(t, "output_format", ""),
                    value=vals.get(t.key, ""),
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_preset_output_formats.py tests/core/test_tree_assembler_presets.py tests/core/test_job_generate_tree.py tests/core/test_section_default_prompts.py -q`
Expected: PASS. If a preset/golden test in `test_tree_assembler_presets.py` asserted the old experience `summary` markdown-string rendering, update that assertion to the structured bullets rendering (the experience body is now `list[str]`); show the change in the same commit.

- [ ] **Step 5: Commit**

```bash
git add core/section_presets.py tests/core/test_preset_output_formats.py tests/core/test_tree_assembler_presets.py
git commit -m "[feat] Preset output-format defaults (experience=bullets, summary/projects=paragraph)"
```

---

### Task 6: Migration backfill

**Files:**
- Modify: `core/profile_tree.py` (add `backfill_output_formats`)
- Create: `scripts/backfill_output_formats.py`
- Test: `tests/core/test_backfill_output_formats.py` (create)

**Interfaces:**
- Consumes: `RootNode`, format ids.
- Produces: `backfill_output_formats(root: RootNode) -> bool` — fills default output formats on the known prose fields when unset, converting an Experience `summary` **string** into a `list[str]` (split on bullet lines) and setting `kind="bullets"`; sets `paragraph` on Summary `hero` and Project `description` when unset. Idempotent; never overwrites a field that already has an `output_format`. Returns True if anything changed.

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_backfill_output_formats.py`:

```python
from __future__ import annotations

from core.profile_tree import legacy_to_tree, backfill_output_formats, RootNode


def _legacy_tree_with_string_summary():
    """A tree as older profiles stored it: experience summary is a markdown
    string of bullets, no output_format anywhere."""
    root = legacy_to_tree({
        "hero": "I build reliable systems.",
        "work_history": [{"title": "Eng", "company": "Acme", "summary": "- shipped X\n- owned Y"}],
        "projects": [{"name": "P", "description": "A tool."}],
    })
    # Simulate the pre-feature shape: strip output_format and force the legacy kind/value.
    for s in root.children:
        for f in _all_fields(s):
            f.output_format = ""
            if f.key == "summary":
                f.kind = "markdown"
                f.value = "- shipped X\n- owned Y"
    return root


def _all_fields(node):
    out = []
    children = getattr(node, "children", [])
    for c in children:
        if c.type == "field":
            out.append(c)
        else:
            out += _all_fields(c)
    if getattr(node, "type", "") == "list":
        out += _all_fields(node.item_template)
    return out


def test_backfill_splits_experience_string_into_bullets():
    root = _legacy_tree_with_string_summary()
    changed = backfill_output_formats(root)
    assert changed is True
    exp = next(s for s in root.children if s.role == "experience")
    summary = next(f for f in exp.children[0].children[0].children if f.key == "summary")
    assert summary.output_format == "bullets"
    assert summary.kind == "bullets"
    assert summary.value == ["shipped X", "owned Y"]


def test_backfill_sets_paragraph_on_hero_and_description():
    root = _legacy_tree_with_string_summary()
    backfill_output_formats(root)
    hero = next(f for f in _all_fields(next(s for s in root.children if s.role == "summary")) if f.key == "hero")
    desc = next(f for f in _all_fields(next(s for s in root.children if s.role == "projects")) if f.key == "description")
    assert hero.output_format == "paragraph"
    assert desc.output_format == "paragraph"


def test_backfill_is_idempotent():
    root = _legacy_tree_with_string_summary()
    backfill_output_formats(root)
    assert backfill_output_formats(root) is False


def test_backfill_preserves_user_set_format():
    root = _legacy_tree_with_string_summary()
    exp = next(s for s in root.children if s.role == "experience")
    summary = next(f for f in exp.children[0].children[0].children if f.key == "summary")
    summary.output_format = "paragraph"  # user chose paragraph
    summary.kind = "markdown"
    backfill_output_formats(root)
    assert summary.output_format == "paragraph"  # untouched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_backfill_output_formats.py -q`
Expected: FAIL — `backfill_output_formats` not defined.

- [ ] **Step 3: Implement the backfill helper**

In `core/profile_tree.py`, add after `backfill_section_prompts` (around line 320):

```python
# Default output formats by (section role, field key) for the preset prose fields.
_OUTPUT_FORMAT_DEFAULTS: dict[tuple[str, str], str] = {
    ("experience", "summary"): "bullets",
    ("summary", "hero"): "paragraph",
    ("projects", "description"): "paragraph",
}


def _split_bullets(text: str) -> list[str]:
    """Split a markdown bullet string into a clean list of bullet bodies."""
    return [
        ln.lstrip("-*• \t").strip()
        for ln in str(text).splitlines()
        if ln.strip()
    ]


def backfill_output_formats(root: RootNode) -> bool:
    """Fill default output formats on the known prose fields, in place.

    For each ``(section role, field key)`` in ``_OUTPUT_FORMAT_DEFAULTS`` whose
    field has no ``output_format`` yet: set the default format and, for a
    ``bullets`` default, align ``kind`` to ``bullets`` and split a stored string
    value into a list. Idempotent; never overwrites a user-set format. Returns
    True if anything changed.
    """
    from core.output_formats import get_format

    changed = False
    for section in root.children:
        role = section.role or ""
        child = section.children[0] if section.children else None
        if child is None:
            continue
        if child.type == "list":
            field_lists = [g.children for g in (list(child.children) + [child.item_template])]
        elif child.type == "group":
            field_lists = [child.children]
        else:  # bare field
            field_lists = [[child]]
        for fields in field_lists:
            for f in fields:
                fmt_id = _OUTPUT_FORMAT_DEFAULTS.get((role, f.key))
                if not fmt_id or getattr(f, "output_format", ""):
                    continue
                fmt = get_format(fmt_id)
                if fmt is None:
                    continue
                f.output_format = fmt_id
                if fmt.kind == "bullets" and f.kind != "bullets":
                    if isinstance(f.value, str):
                        f.value = _split_bullets(f.value)
                    f.kind = "bullets"
                changed = True
    return changed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_backfill_output_formats.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Write the backfill script**

Create `scripts/backfill_output_formats.py`:

```python
"""One-time backfill: seed default output formats into stored profile trees.

New profiles get the defaults from the section presets. Existing profiles carry
a persisted ``profile_tree`` whose prose fields predate output formats; this
script fills those (splitting Experience bullet-strings into arrays) in place.

Idempotent and non-destructive: only fields with no ``output_format`` on the
known preset roles are touched. TAKE A DB BACKUP FIRST. Run from the project root:

    python -m scripts.backfill_output_formats
"""

from __future__ import annotations

import json

from core.profile_tree import RootNode, backfill_output_formats
from core.user import User
from db.database import SessionLocal


def run() -> int:
    """Backfill every stored profile tree. Returns the count of rows changed."""
    db = SessionLocal()
    changed = 0
    try:
        for row in db.query(User).all():
            data = json.loads(row.data) if row.data else {}
            tree_raw = data.get("profile_tree")
            if not tree_raw:
                continue
            root = RootNode.model_validate(tree_raw)
            if backfill_output_formats(root):
                data["profile_tree"] = root.model_dump(mode="json")
                row.data = json.dumps(data)
                changed += 1
                print(f"  profile {row.id} ({row.name}): output formats seeded")
        if changed:
            db.commit()
    finally:
        db.close()
    return changed


if __name__ == "__main__":
    n = run()
    print(f"Backfill complete: {n} profile(s) updated.")
```

- [ ] **Step 6: Verify the script imports and is runnable (no DB mutation in the test)**

Run: `python -c "import scripts.backfill_output_formats as m; print(callable(m.run))"`
Expected: prints `True`.

- [ ] **Step 7: Commit**

```bash
git add core/profile_tree.py scripts/backfill_output_formats.py tests/core/test_backfill_output_formats.py
git commit -m "[feat] Backfill: seed output formats + split experience bullets in stored trees"
```

---

### Task 7: Backend formats endpoint + profile-tree format picker

**Files:**
- Create: `web/routers/output_formats.py`
- Modify: `web/main.py` (register the router)
- Modify: `react-dashboard/src/api.js` (add `getOutputFormats`)
- Modify: `react-dashboard/src/components/widgets/profile-tree/treeOps.js` (add `setOutputFormat`)
- Modify: `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx` (add `ops.setOutputFormat`)
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx` (`FieldView` renders the `<select>`)
- Test (backend): `tests/web/test_output_formats_endpoint.py` (create)
- Test (frontend): `react-dashboard/src/components/widgets/profile-tree/treeOps.outputFormat.test.js` (create)

**Interfaces:**
- Consumes: `core.output_formats.all_formats` (Task 1); `FieldNode.output_format` (Task 2).
- Produces: `GET /api/output-formats` → `[{ "id", "label", "kind" }]`; frontend `getOutputFormats()`, `setOutputFormat(tree, fieldId, formatId, kind)`, `ops.setOutputFormat`, and a `<select>` in `FieldView` for LLM-authored prose fields.

- [ ] **Step 1: Write the failing backend test**

Create `tests/web/test_output_formats_endpoint.py`:

```python
from fastapi.testclient import TestClient
from web.main import app


def test_output_formats_endpoint_lists_registry():
    client = TestClient(app)
    r = client.get("/api/output-formats")
    assert r.status_code == 200
    data = r.json()
    ids = {d["id"] for d in data}
    assert ids == {"bullets", "paragraph"}
    bullets = next(d for d in data if d["id"] == "bullets")
    assert bullets["label"] == "Bullet list"
    assert bullets["kind"] == "bullets"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/web/test_output_formats_endpoint.py -q`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Implement the endpoint and register it**

Create `web/routers/output_formats.py`:

```python
from __future__ import annotations

from fastapi import APIRouter

from core.output_formats import all_formats

router = APIRouter()


@router.get("/api/output-formats")
def list_output_formats() -> list[dict[str, str]]:
    """The output-format registry for the profile-tree format picker."""
    return [{"id": f.id, "label": f.label, "kind": f.kind} for f in all_formats()]
```

In `web/main.py`, register it alongside the other routers (match the existing `include_router` pattern — find an existing `from web.routers import ...` / `app.include_router(...)` block and add):

```python
from web.routers import output_formats as output_formats_router
app.include_router(output_formats_router.router)
```

- [ ] **Step 4: Run the backend test**

Run: `python -m pytest tests/web/test_output_formats_endpoint.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing frontend op test**

Create `react-dashboard/src/components/widgets/profile-tree/treeOps.outputFormat.test.js`:

```js
import { describe, it, expect } from 'vitest'
import { setOutputFormat } from './treeOps'

const tree = {
  type: 'root', id: 'r', children: [
    { type: 'section', id: 's', role: 'experience', children: [
      { type: 'list', id: 'l', item_template: { type: 'group', id: 't', children: [] }, children: [
        { type: 'group', id: 'g', children: [
          { type: 'field', id: 'f1', key: 'summary', kind: 'markdown', value: 'x', output_format: '' },
        ] },
      ] },
    ] },
  ],
}

describe('setOutputFormat', () => {
  it('sets output_format and aligns kind on the field', () => {
    const next = setOutputFormat(tree, 'f1', 'bullets', 'bullets')
    const f = next.children[0].children[0].children[0].children[0]
    expect(f.output_format).toBe('bullets')
    expect(f.kind).toBe('bullets')
  })

  it('does not mutate the input tree', () => {
    setOutputFormat(tree, 'f1', 'bullets', 'bullets')
    const f = tree.children[0].children[0].children[0].children[0]
    expect(f.output_format).toBe('')
  })
})
```

- [ ] **Step 6: Run it to verify it fails**

Run (from `react-dashboard/`): `npm run test -- treeOps.outputFormat`
Expected: FAIL — `setOutputFormat` is not exported.

- [ ] **Step 7: Implement the op and wire the UI**

In `treeOps.js`, add after `setLlmInstructions` (around line 197):

```js
// Set a field's output format and align its storage kind to that format.
export function setOutputFormat(tree, fieldId, formatId, kind) {
  return updateNode(tree, fieldId, (f) => ({ ...f, output_format: formatId, kind }))
}
```

In `ProfileTreeEditor.jsx`, import `setOutputFormat` with the other `treeOps` imports and add to the `ops` object (after `setInstructions`):

```js
    setOutputFormat: useCallback(
      (id, formatId, kind) => setTree((t) => setOutputFormat(t, id, formatId, kind)), []),
```

In `api.js`, add:

```js
export const getOutputFormats = () => _fetch('/api/output-formats')
```

In `TreeNode.jsx`, add a format `<select>` to `FieldView`, shown only for LLM-authored prose fields (`written` and `kind` is `markdown` or `bullets`). Add the import and a small fetch-once hook at the top of the file:

```js
import { useState, useEffect } from 'react'
import { getOutputFormats } from '../../../api'

// Module-level cache so every field doesn't refetch the small registry.
let _formatsCache = null
function useOutputFormats() {
  const [formats, setFormats] = useState(_formatsCache || [])
  useEffect(() => {
    if (_formatsCache) return
    getOutputFormats().then((f) => { _formatsCache = f; setFormats(f) }).catch(() => {})
  }, [])
  return formats
}
```

Then in `FieldView`, compute and render the picker (place the `<select>` inside the header `<span>` next to the toggles, gated on `written` and a prose kind):

```jsx
function FieldView({ field, fieldsEditable, ops, tree }) {
  const written = !!field.llm_output
  const [promptOpen, setPromptOpen] = useState(false)
  const formats = useOutputFormats()
  const isProse = field.kind === 'markdown' || field.kind === 'bullets'
  return (
    <div className={rowWrap}>
      <div className={headerRow}>
        <RenameLabel
          name={field.name} editable={fieldsEditable}
          onRename={(n) => ops.rename(field.id, n)}
        />
        <span className="inline-flex items-center gap-1">
          <LlmWriteToggle written={written} onToggle={() => ops.toggleWritten(field.id)} />
          <VisibleToggle visible={field.visible} onToggle={() => ops.toggleVisible(field.id)} label="in output" />
          {written && isProse && formats.length > 0 && (
            <select
              aria-label="Output format"
              className="bg-white/5 border border-space-border rounded text-xs text-space-text px-1 py-0.5"
              value={field.output_format || ''}
              onChange={(e) => {
                const fmt = formats.find((x) => x.id === e.target.value)
                if (fmt) ops.setOutputFormat(field.id, fmt.id, fmt.kind)
              }}
            >
              {!field.output_format && <option value="">Format…</option>}
              {formats.map((f) => (
                <option key={f.id} value={f.id}>{f.label}</option>
              ))}
            </select>
          )}
          {written && (
            <button
              type="button" aria-label="Edit field prompt" title="Field prompt"
              className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
              onClick={() => setPromptOpen(true)}
            >💬</button>
          )}
        </span>
      </div>
      <div className={field.visible ? '' : 'opacity-50'}>
        <FieldWidget field={field} onChange={(v) => ops.setValue(field.id, v)} />
      </div>
      {promptOpen && (
        <PromptEditorModal
          node={field} isSection={false} label="Field"
          value={field.llm_instructions || ''} tree={tree}
          onChange={(t) => ops.setInstructions(field.id, t)}
          onClose={() => setPromptOpen(false)}
        />
      )}
    </div>
  )
}
```

Note: keep the existing `import { useState } from 'react'` line consolidated — if the file already imports `useState`, merge `useEffect` into that import rather than duplicating.

- [ ] **Step 8: Run the frontend op test + full suites + build**

Run (from `react-dashboard/`): `npm run test -- treeOps.outputFormat` then `npm run test` then `npm run build`
Expected: the op test passes; full Vitest suite passes; build succeeds.

- [ ] **Step 9: Run the full backend suite for regressions**

Run: `python -m pytest -q`
Expected: pass (the 4 known pre-existing/environmental failures from the project baseline may remain; no NEW failures introduced by this task).

- [ ] **Step 10: Commit**

```bash
git add web/routers/output_formats.py web/main.py react-dashboard/src/api.js \
  react-dashboard/src/components/widgets/profile-tree/treeOps.js \
  react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx \
  react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx \
  tests/web/test_output_formats_endpoint.py \
  react-dashboard/src/components/widgets/profile-tree/treeOps.outputFormat.test.js
git commit -m "[feat] Output-format picker: registry endpoint + profile-tree select"
```

---

## Notes for the implementer

- **Back-compat is load-bearing:** a field with empty `output_format` must behave exactly as today everywhere — `_format_block` returns `""`, `_coerce_to_format` passes through, and the renderer sees the same string values. Existing suites must stay green without edits except where Task 5 intentionally flips the Experience default (update only those golden assertions).
- **The Experience data-shape flip happens in Task 5**, after the generator (Task 3) and renderer (Task 4) already handle both shapes — so the build stays coherent between tasks.
- **Do not run the backfill script against the dev DB as part of a task.** It mutates data and requires a manual DB backup; running it is a post-merge manual step the controller handles, like the section-prompt backfill.
- **Do not touch** `core/job.py`'s legacy `ResumeGeneration` path, cover generation, or `ListNode.bullet_style`.
- When editing `TreeNode.jsx`, the file already imports from `react`; merge new hooks into the existing import line rather than adding a second `import ... from 'react'`.
