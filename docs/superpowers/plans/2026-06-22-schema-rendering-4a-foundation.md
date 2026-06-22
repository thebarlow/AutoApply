# Profile Schema Engine #4A — Pure Rendering Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure, fully-tested engine that turns a profile tree + LLM-authored values into a self-contained "document tree" and renders it to Markdown — with no wiring into the running generation/render/refine pipeline.

**Architecture:** Two new pure modules. `core/document_tree.py` materializes a *document tree* (deep copy of the profile tree, invisible + `context_only` nodes pruned, authored values baked into fields, locked nodes carried verbatim). `core/tree_assembler.py` renders a document tree to Markdown via a `role → formatter` dispatch table: preset roles (header/summary/experience/education/projects/skills) get fidelity-preserving formatters that mirror today's `document_assembler.py`; unknown/custom roles fall through to a generic formatter. The admin-only dev compare harness is repointed at these modules to dogfood them. No frontmatter. The production generation/PDF/refine paths are untouched (that is 4B).

**Tech Stack:** Python 3, Pydantic v2 (existing `core/profile_tree.py` node models), pytest.

## Global Constraints

- **Release:** merges to LOCAL `main` only — do NOT push `main` (Profile Schema Engine #1–#5/#6 release gate).
- **Purity:** both new modules are pure — no DB, no LLM, no filesystem, no network. Same discipline as `core/document_assembler.py` and `core/profile_tree.py`.
- **No production wiring in 4A:** do not modify `core/job.py`, `core/utils.py`, `web/intake_pipeline.py`, `generator/*.html`, the `documents` storage format, or the ATS gate. The only non-test, non-new-module edit allowed is the dev harness (`web/routers/dev.py`) in Task 6.
- **Tree order is authoritative:** sections render in `root.children` order; no canonical reordering.
- **Code style:** type hints, Google-style docstrings, `black` formatting (project global CLAUDE.md).
- **Run tests from the repo root** with the project venv active: `python -m pytest <path> -v`.

---

### Task 1: Document-tree builder — materialize + prune + bake

**Files:**
- Create: `core/document_tree.py`
- Test: `tests/core/test_document_tree.py`

**Interfaces:**
- Consumes: `core.profile_tree` — `RootNode`, `SectionNode`, `ListNode`, `GroupNode`, `FieldNode`, and `_coerce_field_value(kind: str, raw) -> str | list[str]`.
- Produces: `build_resume_document_tree(root: RootNode, authored: dict[str, str | list[str]]) -> RootNode` — returns a NEW `RootNode` (deep copy; input is never mutated). Sections/entries/fields that are not `visible` are removed; fields where `llm_input and not llm_output` (context-only) are removed; for any remaining field whose `id` is a key in `authored`, the field's `value` is replaced with `_coerce_field_value(field.kind, authored[field.id])`; locked sections/entries are kept as-is (they carry no authored values). A section whose sole child is a bare `FieldNode` that is invisible or context-only is dropped entirely.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_document_tree.py
"""Tests for the document-tree builder (Profile Schema Engine #4A)."""
from __future__ import annotations

from core.document_tree import build_resume_document_tree
from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)


def _summary_section(text: str = "", visible: bool = True) -> SectionNode:
    return SectionNode(
        name="Summary", role="summary", order=1, visible=visible,
        children=[FieldNode(
            name="Summary", key="hero", kind="markdown", order=0,
            llm_output=True, value=text,
        )],
    )


def test_bakes_authored_value_by_field_id():
    sec = _summary_section("OLD")
    fid = sec.children[0].id
    out = build_resume_document_tree(RootNode(children=[sec]), {fid: "NEW"})
    assert out.children[0].children[0].value == "NEW"


def test_input_tree_is_not_mutated():
    sec = _summary_section("OLD")
    fid = sec.children[0].id
    root = RootNode(children=[sec])
    build_resume_document_tree(root, {fid: "NEW"})
    assert root.children[0].children[0].value == "OLD"  # original untouched


def test_drops_invisible_section():
    visible = _summary_section("keep")
    hidden = SectionNode(
        name="Secret", role=None, order=2, visible=False,
        children=[GroupNode(children=[FieldNode(name="X", key="x", value="hide")])],
    )
    out = build_resume_document_tree(RootNode(children=[visible, hidden]), {})
    assert [s.name for s in out.children] == ["Summary"]


def test_drops_invisible_list_entry():
    lst = ListNode(name="Experience", item_template=GroupNode(), children=[
        GroupNode(visible=True, children=[FieldNode(name="Co", key="company", value="A")]),
        GroupNode(visible=False, children=[FieldNode(name="Co", key="company", value="B")]),
    ])
    sec = SectionNode(name="Experience", role="experience", order=0, children=[lst])
    out = build_resume_document_tree(RootNode(children=[sec]), {})
    kept = out.children[0].children[0].children
    assert len(kept) == 1
    assert kept[0].children[0].value == "A"


def test_drops_context_only_field():
    grp = GroupNode(children=[
        FieldNode(name="Anchor", key="anchor", llm_input=True, llm_output=False, value="ctx"),
        FieldNode(name="Body", key="body", kind="markdown", llm_output=True, value="real"),
    ])
    sec = SectionNode(name="Custom", role=None, order=0, children=[grp])
    out = build_resume_document_tree(RootNode(children=[sec]), {})
    keys = [f.key for f in out.children[0].children[0].children]
    assert keys == ["body"]


def test_keeps_locked_entry_verbatim():
    locked = GroupNode(locked=True, children=[
        FieldNode(name="Co", key="company", value="Fixed"),
        FieldNode(name="Sum", key="summary", kind="markdown", llm_output=True, value="orig"),
    ])
    fid = locked.children[1].id
    lst = ListNode(name="Experience", item_template=GroupNode(), children=[locked])
    sec = SectionNode(name="Experience", role="experience", order=0, children=[lst])
    # Even if authored somehow references it, the builder bakes by id; section_generator
    # never authors locked entries, so authored is empty here — value stays "orig".
    out = build_resume_document_tree(RootNode(children=[sec]), {})
    kept = out.children[0].children[0].children[0]
    assert kept.locked is True
    assert kept.children[1].value == "orig"


def test_drops_section_with_invisible_bare_field():
    sec = _summary_section("x", visible=True)
    sec.children[0].visible = False
    out = build_resume_document_tree(RootNode(children=[sec]), {})
    assert out.children == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_document_tree.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.document_tree'`.

- [ ] **Step 3: Implement `core/document_tree.py`**

```python
"""Materialize a self-contained résumé *document tree* from the profile tree.

Pure module — no DB, no LLM, no filesystem. Given a profile ``RootNode`` and the
``field_id -> authored value`` map produced by ``core.section_generator``, returns
a NEW tree (deep copy) in which: invisible sections/entries/fields are removed;
context-only fields (``llm_input and not llm_output``) are removed; authored values
are baked into their fields by id; and locked nodes are carried through verbatim.
This pruned tree is the renderable, snapshot-safe résumé document.
"""
from __future__ import annotations

from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode, _coerce_field_value,
)

Value = "str | list[str]"


def _is_context_only(field: FieldNode) -> bool:
    """A field the LLM only reads (never written to the document)."""
    return field.llm_input and not field.llm_output


def _bake(field: FieldNode, authored: "dict[str, Value]") -> None:
    """Overlay an authored value onto a field, coercing to its kind's type."""
    if field.id in authored:
        field.value = _coerce_field_value(field.kind, authored[field.id])


def _prune_group(group: GroupNode, authored: "dict[str, Value]") -> None:
    """Drop invisible/context-only fields and bake authored values, in place."""
    kept: list[FieldNode] = []
    for f in group.children:
        if not f.visible or _is_context_only(f):
            continue
        _bake(f, authored)
        kept.append(f)
    group.children = kept


def build_resume_document_tree(
    root: RootNode, authored: "dict[str, Value]"
) -> RootNode:
    """Return a renderable document tree: pruned, value-baked deep copy of ``root``.

    Args:
        root: The profile tree (source structure).
        authored: ``field_node_id -> value`` from ``core.section_generator``.

    Returns:
        A new ``RootNode`` containing only visible, non-context-only nodes, with
        authored values baked in and locked nodes carried verbatim. ``root`` is
        not mutated.
    """
    doc = root.model_copy(deep=True)
    sections: list[SectionNode] = []
    for s in doc.children:
        if not s.visible:
            continue
        child = s.children[0] if s.children else None
        if isinstance(child, ListNode):
            entries = [e for e in child.children if e.visible]
            for e in entries:
                _prune_group(e, authored)
            child.children = entries
        elif isinstance(child, GroupNode):
            _prune_group(child, authored)
        elif isinstance(child, FieldNode):
            if not child.visible or _is_context_only(child):
                continue  # bare-field section with nothing to render → drop
            _bake(child, authored)
        sections.append(s)
    doc.children = sections
    return doc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_document_tree.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add core/document_tree.py tests/core/test_document_tree.py
git commit -m "[feat] Document-tree builder: prune + bake authored values (schema #4A)"
```

---

### Task 2: Generic section renderer + assembler entry point

**Files:**
- Create: `core/tree_assembler.py`
- Test: `tests/core/test_tree_assembler.py`

**Interfaces:**
- Consumes: `core.profile_tree` — `FieldNode`, `GroupNode`, `ListNode`, `RootNode`, `SectionNode`.
- Produces:
  - `assemble_resume_tree_markdown(root: RootNode) -> str` — renders every visible section in tree order, each via the `role → formatter` table (default generic), joined by blank lines, trailing newline. Empty sections (formatter returns `""`) are omitted.
  - `_render_field(field: FieldNode) -> list[str]` — `markdown` kind → the value as one block; `taglist` → one `**Name:** a, b, c` line; `bullets`/list → one block of `- item` lines; `text` → `**Name:** value`. Empty values → `[]`.
  - `_generic_section(section: SectionNode) -> str` — `## {name}` + body from the section's single child (list entries separated by blank lines), or `""` if empty.
  - `_RENDERERS: dict[str, "Callable[[SectionNode], str]"]` — role-keyed formatter table (populated fully in Tasks 3–4; in this task it is empty so every section uses `_generic_section`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_tree_assembler.py
"""Tests for the document-tree Markdown assembler (Profile Schema Engine #4A)."""
from __future__ import annotations

from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)
from core.tree_assembler import assemble_resume_tree_markdown


def _custom_list_section() -> SectionNode:
    entry = GroupNode(children=[
        FieldNode(name="Org", key="org", kind="text", value="Red Cross"),
        FieldNode(name="Detail", key="detail", kind="markdown", value="Helped at shelters."),
    ])
    return SectionNode(
        name="Volunteering", role=None, order=10,
        children=[ListNode(name="Volunteering", item_template=GroupNode(), children=[entry])],
    )


def test_custom_section_renders_generically():
    md = assemble_resume_tree_markdown(RootNode(children=[_custom_list_section()]))
    assert md == (
        "## Volunteering\n\n"
        "**Org:** Red Cross\n\n"
        "Helped at shelters.\n"
    )


def test_taglist_field_renders_inline():
    sec = SectionNode(name="Tools", role=None, order=0, children=[
        GroupNode(children=[FieldNode(name="Tools", key="tools", kind="taglist",
                                      value=["Git", "Docker"])]),
    ])
    md = assemble_resume_tree_markdown(RootNode(children=[sec]))
    assert md == "## Tools\n\n**Tools:** Git, Docker\n"


def test_bullets_field_renders_as_list():
    sec = SectionNode(name="Highlights", role=None, order=0, children=[
        GroupNode(children=[FieldNode(name="Points", key="points", kind="bullets",
                                      value=["First", "Second"])]),
    ])
    md = assemble_resume_tree_markdown(RootNode(children=[sec]))
    assert md == "## Highlights\n\n- First\n- Second\n"


def test_empty_section_is_omitted():
    empty = SectionNode(name="Blank", role=None, order=0, children=[
        GroupNode(children=[FieldNode(name="X", key="x", kind="text", value="")]),
    ])
    keep = _custom_list_section()
    md = assemble_resume_tree_markdown(RootNode(children=[empty, keep]))
    assert md.startswith("## Volunteering")
    assert "Blank" not in md


def test_invisible_section_skipped():
    hidden = _custom_list_section()
    hidden.visible = False
    md = assemble_resume_tree_markdown(RootNode(children=[hidden]))
    assert md.strip() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_tree_assembler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.tree_assembler'`.

- [ ] **Step 3: Implement `core/tree_assembler.py`**

```python
"""Render a résumé *document tree* to Markdown via role-dispatched formatters.

Pure module — no DB, no LLM, no filesystem. Preset roles
(header/summary/experience/education/projects/skills) get fidelity-preserving
formatters that mirror ``core.document_assembler``; unknown/custom roles fall
through to ``_generic_section``. Section order is the tree's order — authoritative,
never canonically reordered. There is no YAML front matter; contact and education
are ordinary sections.
"""
from __future__ import annotations

from collections.abc import Callable

from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)


def _render_field(field: FieldNode) -> list[str]:
    """Render one field to zero or more Markdown blocks."""
    val = field.value
    if isinstance(val, list):
        items = [str(x) for x in val if str(x).strip()]
        if not items:
            return []
        if field.kind == "taglist":
            return [f"**{field.name}:** {', '.join(items)}"]
        return ["\n".join(f"- {x}" for x in items)]
    text = str(val).strip()
    if not text:
        return []
    if field.kind == "markdown":
        return [text]
    return [f"**{field.name}:** {text}"]


def _render_group(group: GroupNode) -> list[str]:
    """Render all of a group's fields to a flat list of Markdown blocks."""
    out: list[str] = []
    for f in group.children:
        out += _render_field(f)
    return out


def _generic_section(section: SectionNode) -> str:
    """Render an arbitrary section: ``## name`` + body, or ``""`` if empty."""
    child = section.children[0] if section.children else None
    blocks: list[str] = []
    if isinstance(child, ListNode):
        for entry in child.children:
            eb = _render_group(entry)
            if eb:
                blocks.append("\n\n".join(eb))
    elif isinstance(child, GroupNode):
        eb = _render_group(child)
        if eb:
            blocks.append("\n\n".join(eb))
    elif isinstance(child, FieldNode):
        blocks += _render_field(child)
    if not blocks:
        return ""
    return f"## {section.name}\n\n" + "\n\n".join(blocks)


# Role → formatter. Populated by Tasks 3–4; default is the generic formatter.
_RENDERERS: dict[str, Callable[[SectionNode], str]] = {}


def _render_section(section: SectionNode) -> str:
    fn = _RENDERERS.get(section.role or "", _generic_section)
    return fn(section).strip()


def assemble_resume_tree_markdown(root: RootNode) -> str:
    """Render a document tree to Markdown (no front matter).

    Args:
        root: A document tree (typically from ``build_resume_document_tree``).

    Returns:
        Canonical Markdown: visible sections in tree order, blank-line separated,
        with a trailing newline. Empty sections are omitted.
    """
    sections = [
        rendered
        for s in root.children
        if s.visible and (rendered := _render_section(s))
    ]
    return "\n\n".join(sections) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_tree_assembler.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add core/tree_assembler.py tests/core/test_tree_assembler.py
git commit -m "[feat] Generic document-tree Markdown renderer (schema #4A)"
```

---

### Task 3: Scalar preset formatters — summary, skills, header

**Files:**
- Modify: `core/tree_assembler.py` (add three formatters; register in `_RENDERERS`)
- Test: `tests/core/test_tree_assembler_presets.py`

**Interfaces:**
- Consumes: the Task 2 module internals (`FieldNode`, `GroupNode`, `_RENDERERS`).
- Produces (all `(section: SectionNode) -> str`, registered under their role key):
  - `_summary_section_md` (role `"summary"`) — `## {name}` + the bare markdown field's value; `""` if blank.
  - `_skills_section_md` (role `"skills"`) — `## {name}` + `**{field.name}:** a, b, c` from the bare taglist field; `""` if no items.
  - `_header_section_md` (role `"header"`) — `## {name}` + one `**Label:** value` block per non-empty contact field (preserves the group's field order, which is ATS contact order). `""` if no contact values. (4B moves header to the HTML template; this is the data-complete Markdown fallback.)

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_tree_assembler_presets.py
"""Golden tests for preset-role formatters (Profile Schema Engine #4A)."""
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode
from core.section_presets import header_section, skills_section, summary_section
from core.tree_assembler import assemble_resume_tree_markdown


def test_summary_renders_with_section_name_heading():
    sec = summary_section()
    sec.children[0].value = "Engineer with 5 years experience."
    md = assemble_resume_tree_markdown(RootNode(children=[sec]))
    assert md == "## Summary\n\nEngineer with 5 years experience.\n"


def test_empty_summary_omitted():
    md = assemble_resume_tree_markdown(RootNode(children=[summary_section()]))
    assert md.strip() == ""


def test_skills_renders_inline_joined():
    sec = skills_section()
    sec.children[0].value = ["Python", "FastAPI", "SQL"]
    md = assemble_resume_tree_markdown(RootNode(children=[sec]))
    assert md == "## Skills\n\n**Skills:** Python, FastAPI, SQL\n"


def test_header_renders_contact_fields_in_order():
    sec = header_section()
    by_key = {f.key: f for f in sec.children[0].children}
    by_key["email"].value = "a@b.com"
    by_key["phone"].value = "555-0100"
    md = assemble_resume_tree_markdown(RootNode(children=[sec]))
    # email precedes phone (ATS contact order = group field order); empty fields skipped.
    assert md == "## Header\n\n**Email:** a@b.com\n\n**Phone:** 555-0100\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_tree_assembler_presets.py -v`
Expected: FAIL — `_skills_section_md`/header use generic path, so e.g. the skills/header assertions fail on heading or layout mismatch (generic renders skills identically but header generic == same here; the summary generic also matches). Confirm which fail, then implement to lock the format. (At minimum the registration wiring is the deliverable.)

> Note for implementer: several of these may already pass via the generic formatter
> because the chosen preset Markdown intentionally equals the generic output for
> scalar sections. That is fine — the deliverable is the explicit, registered
> formatters so Task-4 list formatters and #4B/#6 can rely on the dispatch table.
> Keep the tests; they pin the format regardless of which path produces it.

- [ ] **Step 3: Implement the three formatters and register them**

Add to `core/tree_assembler.py` (after `_generic_section`, before `_RENDERERS`):

```python
def _summary_section_md(section: SectionNode) -> str:
    """Profile summary: ``## name`` + the markdown field value."""
    child = section.children[0] if section.children else None
    if not isinstance(child, FieldNode):
        return ""
    text = str(child.value).strip()
    return f"## {section.name}\n\n{text}" if text else ""


def _skills_section_md(section: SectionNode) -> str:
    """Skills: ``## name`` + a single ``**label:** a, b, c`` line."""
    child = section.children[0] if section.children else None
    if not isinstance(child, FieldNode):
        return ""
    items = child.value if isinstance(child.value, list) else []
    items = [str(x) for x in items if str(x).strip()]
    if not items:
        return ""
    return f"## {section.name}\n\n**{child.name}:** {', '.join(items)}"


def _header_section_md(section: SectionNode) -> str:
    """Contact block: one ``**Label:** value`` block per non-empty field, in order."""
    child = section.children[0] if section.children else None
    if not isinstance(child, GroupNode):
        return ""
    blocks: list[str] = []
    for f in child.children:
        val = f.value if isinstance(f.value, str) else ", ".join(str(x) for x in f.value)
        val = val.strip()
        if val:
            blocks.append(f"**{f.name}:** {val}")
    if not blocks:
        return ""
    return f"## {section.name}\n\n" + "\n\n".join(blocks)
```

Then replace the empty `_RENDERERS` initializer with:

```python
_RENDERERS: dict[str, Callable[[SectionNode], str]] = {
    "header": _header_section_md,
    "summary": _summary_section_md,
    "skills": _skills_section_md,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_tree_assembler_presets.py tests/core/test_tree_assembler.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add core/tree_assembler.py tests/core/test_tree_assembler_presets.py
git commit -m "[feat] Scalar preset formatters: summary/skills/header (schema #4A)"
```

---

### Task 4: List preset formatters — experience, education, projects

**Files:**
- Modify: `core/tree_assembler.py` (add three list formatters; extend `_RENDERERS`)
- Test: `tests/core/test_tree_assembler_lists.py`

**Interfaces:**
- Consumes: `ListNode`, `GroupNode`, `_RENDERERS`, and a new helper `_list_rows(section) -> list[dict[str, object]]` that returns, per visible entry, `{field.key: field.value}`.
- Produces (all `(section: SectionNode) -> str`, registered under their role key), mirroring `core/document_assembler.py` but keyed off the section's own `name`:
  - `_experience_section_md` (role `"experience"`) — per entry: `### {title}, {company} ({start} – {end})` then the `summary` markdown as body.
  - `_education_section_md` (role `"education"`) — per entry: `**{degree} in {field}**, {institution} ({graduated})`.
  - `_projects_section_md` (role `"projects"`) — per entry: `**{name}**: {description}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_tree_assembler_lists.py
"""Golden tests for list preset formatters (Profile Schema Engine #4A)."""
from __future__ import annotations

from core.profile_tree import GroupNode, ListNode, RootNode, SectionNode
from core.section_presets import (
    education_template, experience_template, projects_template,
)
from core.tree_assembler import assemble_resume_tree_markdown


def _entry(template_fn, **values) -> GroupNode:
    grp = template_fn()
    for f in grp.children:
        if f.key in values:
            f.value = values[f.key]
    return grp


def _list_section(name: str, role: str, template_fn, entries) -> SectionNode:
    return SectionNode(name=name, role=role, order=0, children=[
        ListNode(name=name, item_template=template_fn(), children=entries),
    ])


def test_experience_entry_heading_and_body():
    e = _entry(experience_template, company="Acme", title="Engineer",
               start="2020", end="2023", summary="Built things.")
    md = assemble_resume_tree_markdown(RootNode(children=[
        _list_section("Experience", "experience", experience_template, [e]),
    ]))
    assert md == (
        "## Experience\n\n"
        "### Engineer, Acme (2020 – 2023)\n\n"
        "Built things.\n"
    )


def test_experience_renamed_section_keeps_user_name():
    e = _entry(experience_template, company="Acme", title="Engineer",
               start="", end="", summary="Did work.")
    md = assemble_resume_tree_markdown(RootNode(children=[
        _list_section("Work History", "experience", experience_template, [e]),
    ]))
    assert md.startswith("## Work History\n\n### Engineer, Acme\n\nDid work.")


def test_education_entry():
    e = _entry(education_template, institution="MIT", degree="BS",
               field="Physics", graduated="2019")
    md = assemble_resume_tree_markdown(RootNode(children=[
        _list_section("Education", "education", education_template, [e]),
    ]))
    assert md == "## Education\n\n**BS in Physics**, MIT (2019)\n"


def test_projects_entry():
    e = _entry(projects_template, name="AutoApply", description="A pipeline.")
    md = assemble_resume_tree_markdown(RootNode(children=[
        _list_section("Projects", "projects", projects_template, [e]),
    ]))
    assert md == "## Projects\n\n**AutoApply**: A pipeline.\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_tree_assembler_lists.py -v`
Expected: FAIL — these roles currently hit `_generic_section`, which renders `**Company:** Acme` field lines rather than the `### Engineer, Acme` heading, so the golden strings do not match.

- [ ] **Step 3: Implement the three list formatters and register them**

Add to `core/tree_assembler.py` (after `_header_section_md`):

```python
def _list_rows(section: SectionNode) -> list[dict[str, object]]:
    """Per visible list entry, a ``{field key: value}`` dict; [] if not a list."""
    child = section.children[0] if section.children else None
    if not isinstance(child, ListNode):
        return []
    return [
        {f.key: f.value for f in entry.children}
        for entry in child.children
        if entry.visible
    ]


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
        summary = str(r.get("summary", "")).strip()
        if summary:
            block += "\n\n" + summary
        parts.append(block)
    return "\n\n".join(parts)


def _education_section_md(section: SectionNode) -> str:
    rows = _list_rows(section)
    if not rows:
        return ""
    lines = [f"## {section.name}"]
    for r in rows:
        line = (
            f"**{str(r.get('degree', '')).strip()} in {str(r.get('field', '')).strip()}**, "
            f"{str(r.get('institution', '')).strip()}"
        ).strip(", ")
        graduated = str(r.get("graduated", "")).strip()
        if graduated:
            line += f" ({graduated})"
        lines.append(line)
    return "\n\n".join(lines)


def _projects_section_md(section: SectionNode) -> str:
    rows = _list_rows(section)
    if not rows:
        return ""
    parts = [f"## {section.name}"]
    for r in rows:
        name = str(r.get("name", "")).strip()
        desc = str(r.get("description", "")).strip()
        nm = f"**{name}**" if name else ""
        parts.append(f"{nm}: {desc}".strip(": ") if nm else desc)
    return "\n\n".join(parts)
```

Extend `_RENDERERS`:

```python
_RENDERERS: dict[str, Callable[[SectionNode], str]] = {
    "header": _header_section_md,
    "summary": _summary_section_md,
    "skills": _skills_section_md,
    "experience": _experience_section_md,
    "education": _education_section_md,
    "projects": _projects_section_md,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_tree_assembler_lists.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add core/tree_assembler.py tests/core/test_tree_assembler_lists.py
git commit -m "[feat] List preset formatters: experience/education/projects (schema #4A)"
```

---

### Task 5: End-to-end golden — migrated profile + custom section

**Files:**
- Test: `tests/core/test_tree_render_e2e.py`

**Interfaces:**
- Consumes: `core.profile_tree.legacy_to_tree`, `core.document_tree.build_resume_document_tree`, `core.tree_assembler.assemble_resume_tree_markdown`.
- Produces: no new code — an integration test proving builder + assembler compose correctly on a realistic tree (a `legacy_to_tree` migration with a custom section appended), and that a custom section appears in the output alongside presets in tree order.

- [ ] **Step 1: Write the test**

```python
# tests/core/test_tree_render_e2e.py
"""End-to-end: build a document tree from a legacy profile + custom section, render."""
from __future__ import annotations

from core.document_tree import build_resume_document_tree
from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode, legacy_to_tree
from core.tree_assembler import assemble_resume_tree_markdown

_PROFILE = {
    "first_name": "Ada", "last_name": "Lovelace", "email": "ada@x.com",
    "hero": "Pioneer.",
    "work_history": [{"company": "Analytical", "title": "Engineer",
                      "start": "1840", "end": "1843", "summary": "Wrote programs."}],
    "education": [{"institution": "Home", "degree": "BS", "field": "Math",
                   "graduated": "1835", "gpa": 4.0}],
    "projects": [], "skills": ["Math", "Logic"],
}


def test_presets_and_custom_section_render_in_tree_order():
    root = legacy_to_tree(_PROFILE)
    custom = SectionNode(name="Awards", role=None, order=99, children=[
        ListNode(name="Awards", item_template=GroupNode(), children=[
            GroupNode(children=[FieldNode(name="Award", key="award",
                                          kind="text", value="First Programmer")]),
        ]),
    ])
    root.children.append(custom)

    # No authored values (simulate generation that changed nothing) — structural snapshot.
    doc = build_resume_document_tree(root, {})
    md = assemble_resume_tree_markdown(doc)

    # Presets present, with their preset formatting.
    assert "### Engineer, Analytical (1840 – 1843)" in md
    assert "**BS in Math**, Home (1835)" in md
    assert "**Skills:** Math, Logic" in md
    # Custom section present and last (tree order).
    assert "## Awards" in md
    assert "**Award:** First Programmer" in md
    assert md.index("## Awards") > md.index("### Engineer")
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/core/test_tree_render_e2e.py -v`
Expected: PASS (1 test). If it fails, the failure is a real composition bug in Task 1/2/4 — fix there, do not weaken the test.

- [ ] **Step 3: Commit**

```bash
git add tests/core/test_tree_render_e2e.py
git commit -m "[test] E2E golden: presets + custom section render in tree order (schema #4A)"
```

---

### Task 6: Dogfood — repoint the dev compare harness at the new modules

**Files:**
- Modify: `web/routers/dev.py` (`_model2_markdown` + imports)

**Interfaces:**
- Consumes: `core.document_tree.build_resume_document_tree`, `core.tree_assembler.assemble_resume_tree_markdown`.
- Produces: `_model2_markdown` now renders via `build_resume_document_tree` + `assemble_resume_tree_markdown` instead of the throwaway `core.tree_render.render_tree_markdown`. This is the only consumer change in 4A and proves the modules work on a real profile + real LLM authored values without touching the production generation/PDF/refine path. `core/tree_render.py` becomes unused (leave it in place; its removal is deferred to 4B and needs explicit approval — do not delete it in this task).

- [ ] **Step 1: Edit `_model2_markdown` and imports in `web/routers/dev.py`**

Replace the import line:

```python
from core.tree_render import render_tree_markdown
```

with:

```python
from core.document_tree import build_resume_document_tree
from core.tree_assembler import assemble_resume_tree_markdown
```

Replace the last two lines of `_model2_markdown`:

```python
    authored = generate_resume_by_section(root, prompt, client, model, resolve=resolve)
    return render_tree_markdown(root, authored)
```

with:

```python
    authored = generate_resume_by_section(root, prompt, client, model, resolve=resolve)
    doc_tree = build_resume_document_tree(root, authored)
    return assemble_resume_tree_markdown(doc_tree)
```

- [ ] **Step 2: Verify imports resolve and nothing else references the old symbol**

Run: `python -c "import web.routers.dev"`
Expected: no error (module imports cleanly).

Run: `python -m pytest tests/core/test_document_tree.py tests/core/test_tree_assembler.py tests/core/test_tree_assembler_presets.py tests/core/test_tree_assembler_lists.py tests/core/test_tree_render_e2e.py -v`
Expected: PASS (all 4A tests green).

- [ ] **Step 3: Commit**

```bash
git add web/routers/dev.py
git commit -m "[refactor] Dev compare harness renders via document-tree builder+assembler (schema #4A)"
```

---

## Self-Review

**Spec coverage:**
- Document-tree materialization (prune invisible + context-only, bake authored, keep locked, no live-profile dependency) → Task 1. ✓
- Generic template-composed renderer, tree order, no frontmatter → Tasks 2–4 (`_RENDERERS` dispatch seam = the "template" hook #6 extends). ✓
- Default contact + education rendering (no frontmatter) → Tasks 3 (header) + 4 (education). ✓
- Custom sections appear → Tasks 2 & 5. ✓
- Pure, no production wiring → Global Constraints + only Task 6 touches a (dev-only) consumer. ✓
- Golden tests for preset-only and custom-section trees → Tasks 3/4/5. ✓
- Deferred to later phases (NOT in 4A): generation switch, storage discriminator, `_render_meta`/`write_resume_markdown` branch, PDF/template HTML rework, refine tree-awareness (4B); ATS gate (4C); DocumentModal (4D); user templates + live preview (#6). ✓

**Placeholder scan:** none — every step has concrete code/commands/expected output.

**Type consistency:** `build_resume_document_tree(root, authored) -> RootNode`, `assemble_resume_tree_markdown(root) -> str`, `_RENDERERS: dict[str, Callable[[SectionNode], str]]`, `_render_field -> list[str]`, `_list_rows -> list[dict]` — names and signatures consistent across Tasks 1–6 and the dev-harness call site.

**Known intentional divergence from legacy:** the summary heading is `## Summary` (the section's name), not the legacy `## Profile`; skills render as a single `**Skills:** …` line rather than per-category groups. Both follow from the tree being authoritative and are pinned by golden tests. Visual fidelity (icon contact grid, styled education) is a 4B/#6 concern at the HTML layer, by design.
