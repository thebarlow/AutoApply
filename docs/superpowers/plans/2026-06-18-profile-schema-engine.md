# Profile Schema Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a recursive, typed tree as the new source of truth for profile structure, with a backward-compatibility adapter so the existing generation/rendering/UI keep working unchanged and migrated profiles produce byte-identical résumé output.

**Architecture:** A new pure module `core/profile_tree.py` defines a closed-vocabulary recursive node model (root → section → list/group → field) as Pydantic models, plus `validate_tree`, a `tree_to_legacy` adapter, and a `legacy_to_tree` migrator. `core/section_presets.py` holds the preset section subtrees that mirror today's master profile field-for-field. `core/user.py` persists the tree in the existing `user_profile.data` JSON column and derives the legacy typed attributes from it on every load, so no downstream code changes.

**Tech Stack:** Python 3, Pydantic v2, SQLAlchemy (existing), pytest.

## Global Constraints

- Python: type hints, `black` formatting, Google-style docstrings (global CLAUDE.md).
- Prefer standard library; Pydantic v2 is already a project dependency.
- Commit format: `[type] Imperative subject` — types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`. No Claude attribution.
- Tests live under `tests/core/`, named `test_*.py`; run with `pytest`.
- The tree models **résumé-document sections only**. Job-search metadata (`target_roles`, `target_salary_min/max`, `resume_path`, `md_path`) stays as flat keys in `user_profile.data` and is NOT moved into the tree.
- Migration presets must mirror the legacy master profile exactly so `assemble_resume_markdown` output is byte-identical post-migration (flat skills `taglist`; work-history fields `company/title/start/end/summary`).
- Custom (non-`role`) sections are storable but invisible on generated documents until sub-project #4 — documented, accepted gap.

## File Structure

- **Create** `core/profile_tree.py` — node models, `TreeValidationError`, `validate_tree`, `tree_to_legacy`, `legacy_to_tree`.
- **Create** `core/section_presets.py` — preset section subtree builders.
- **Modify** `core/user.py` — `_hydrate`/`_to_dict` persist + derive from `profile_tree`; one-time migration on load.
- **Create** `tests/core/test_profile_tree.py` — model + validation + adapter + round-trip tests.
- **Modify** `tests/core/test_user.py` — add migration/idempotency tests.
- **Docs** `core/CONTEXT.md`, `ARCHITECTURE.md`.

---

### Task 1: Node models

**Files:**
- Create: `core/profile_tree.py`
- Test: `tests/core/test_profile_tree.py`

**Interfaces:**
- Produces: `FieldNode`, `GroupNode`, `ListNode`, `SectionNode`, `RootNode` (Pydantic v2 models). Field on every node: `id: str`, `name: str`, `order: int`, `visible: bool`. `FieldNode` adds `key: str`, `kind: Literal["text","markdown","bullets","taglist"]`, `value: str | list[str]`, `llm_output: bool`, `llm_instructions: str`, `llm_input: bool`, `regen_lock: bool`, `min: int | None`, `max: int | None`. `GroupNode` adds `children: list[FieldNode]`, `regen_lock: bool`. `ListNode` adds `bullet_style: str`, `item_template: GroupNode`, `children: list[GroupNode]`. `SectionNode` adds `role: str | None`, `children: list` (union of List/Group/Field). `RootNode` adds `children: list[SectionNode]`. A `value` normalizer coerces `text`/`markdown` → `str`, `bullets`/`taglist` → `list[str]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_profile_tree.py
from __future__ import annotations

import pytest


def test_field_text_value_coerces_to_str():
    from core.profile_tree import FieldNode

    f = FieldNode(name="Email", key="email", kind="text", value="a@b.com")
    assert f.value == "a@b.com"
    assert isinstance(f.id, str) and f.id


def test_field_taglist_value_coerces_to_list():
    from core.profile_tree import FieldNode

    f = FieldNode(name="Skills", key="skills", kind="taglist", value=["Python", "SQL"])
    assert f.value == ["Python", "SQL"]


def test_field_text_given_none_becomes_empty_string():
    from core.profile_tree import FieldNode

    f = FieldNode(name="Phone", key="phone", kind="text", value=None)
    assert f.value == ""


def test_nested_tree_builds():
    from core.profile_tree import FieldNode, GroupNode, ListNode, RootNode, SectionNode

    item = GroupNode(
        name="item",
        children=[FieldNode(name="Company", key="company", kind="text")],
    )
    sect = SectionNode(
        name="Experience",
        role="experience",
        children=[ListNode(name="Experience", item_template=item, children=[])],
    )
    root = RootNode(children=[sect])
    assert root.children[0].children[0].item_template.children[0].key == "company"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_profile_tree.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.profile_tree'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/profile_tree.py
"""Recursive, typed profile/résumé tree: closed node vocabulary + adapters.

Pure module — no DB, no LLM. ``RootNode`` is the source of truth for profile
structure; ``tree_to_legacy`` projects it into today's flat profile shape and
``legacy_to_tree`` migrates an old flat profile into the default preset tree.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


def _new_id() -> str:
    """Return a fresh hex node id."""
    return uuid.uuid4().hex


class FieldNode(BaseModel):
    """A leaf value. ``key`` is the stable machine identifier (rename-safe)."""

    type: Literal["field"] = "field"
    id: str = Field(default_factory=_new_id)
    name: str = ""
    key: str = ""
    order: int = 0
    visible: bool = True
    kind: Literal["text", "markdown", "bullets", "taglist"] = "text"
    value: Union[str, list[str]] = ""
    llm_output: bool = False
    llm_instructions: str = ""
    llm_input: bool = False
    regen_lock: bool = False
    min: Optional[int] = None
    max: Optional[int] = None

    @model_validator(mode="after")
    def _normalize_value(self) -> "FieldNode":
        if self.kind in ("text", "markdown"):
            if isinstance(self.value, list):
                self.value = " ".join(str(v) for v in self.value)
            elif self.value is None:
                self.value = ""
            else:
                self.value = str(self.value)
        else:  # bullets, taglist
            if isinstance(self.value, str):
                self.value = [self.value] if self.value else []
            elif self.value is None:
                self.value = []
            else:
                self.value = [str(v) for v in self.value]
        return self


class GroupNode(BaseModel):
    """A bundle of fields; also serves as a list's item instance/template."""

    type: Literal["group"] = "group"
    id: str = Field(default_factory=_new_id)
    name: str = ""
    order: int = 0
    visible: bool = True
    regen_lock: bool = False
    children: list[FieldNode] = Field(default_factory=list)


class ListNode(BaseModel):
    """A repeating container; every child conforms to ``item_template``."""

    type: Literal["list"] = "list"
    id: str = Field(default_factory=_new_id)
    name: str = ""
    order: int = 0
    visible: bool = True
    bullet_style: str = "none"
    item_template: GroupNode = Field(default_factory=GroupNode)
    children: list[GroupNode] = Field(default_factory=list)


SectionChild = Union[ListNode, GroupNode, FieldNode]


class SectionNode(BaseModel):
    """A top-level block. ``role`` ties presets to the legacy adapter."""

    type: Literal["section"] = "section"
    id: str = Field(default_factory=_new_id)
    name: str = ""
    role: Optional[str] = None
    order: int = 0
    visible: bool = True
    children: list[SectionChild] = Field(default_factory=list)


class RootNode(BaseModel):
    """The profile/résumé root."""

    type: Literal["root"] = "root"
    id: str = Field(default_factory=_new_id)
    children: list[SectionNode] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_profile_tree.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add core/profile_tree.py tests/core/test_profile_tree.py
git commit -m "[feat] Add recursive profile-tree node models"
```

---

### Task 2: Tree validation

**Files:**
- Modify: `core/profile_tree.py`
- Test: `tests/core/test_profile_tree.py`

**Interfaces:**
- Consumes: the node models from Task 1.
- Produces: `class TreeValidationError(Exception)` and `def validate_tree(root: RootNode) -> None` (raises `TreeValidationError`). Rules: globally-unique `id`; sibling `order` unique within each parent; a `SectionNode` has exactly one child whose type is list/group/field; within any group, field `key`s are unique; each `ListNode` child group conforms to `item_template` (same multiset of `(key, kind)`); `bullets` fields satisfy `0 <= min <= max` when both set.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/core/test_profile_tree.py
def _experience_section():
    from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode

    tmpl = GroupNode(
        name="item",
        children=[
            FieldNode(name="Company", key="company", kind="text"),
            FieldNode(name="Title", key="title", kind="text"),
        ],
    )
    inst = GroupNode(
        name="item",
        children=[
            FieldNode(name="Company", key="company", kind="text", value="Acme"),
            FieldNode(name="Title", key="title", kind="text", value="SWE"),
        ],
    )
    return SectionNode(
        name="Experience",
        role="experience",
        children=[ListNode(name="Experience", item_template=tmpl, children=[inst])],
    )


def test_validate_accepts_conforming_tree():
    from core.profile_tree import RootNode, validate_tree

    validate_tree(RootNode(children=[_experience_section()]))  # no raise


def test_validate_rejects_nonconforming_list_item():
    from core.profile_tree import (
        FieldNode, GroupNode, ListNode, RootNode, SectionNode,
        TreeValidationError, validate_tree,
    )

    tmpl = GroupNode(children=[FieldNode(name="Company", key="company", kind="text")])
    bad = GroupNode(children=[FieldNode(name="Other", key="other", kind="text")])
    root = RootNode(children=[
        SectionNode(name="Experience", role="experience",
                    children=[ListNode(item_template=tmpl, children=[bad])])
    ])
    with pytest.raises(TreeValidationError):
        validate_tree(root)


def test_validate_rejects_duplicate_sibling_order():
    from core.profile_tree import (
        RootNode, SectionNode, TreeValidationError, validate_tree,
    )

    root = RootNode(children=[
        SectionNode(name="A", order=0, children=[]),
        SectionNode(name="B", order=0, children=[]),
    ])
    with pytest.raises(TreeValidationError):
        validate_tree(root)


def test_validate_rejects_section_with_two_children():
    from core.profile_tree import (
        FieldNode, RootNode, SectionNode, TreeValidationError, validate_tree,
    )

    root = RootNode(children=[
        SectionNode(name="X", children=[
            FieldNode(name="a", key="a", kind="text"),
            FieldNode(name="b", key="b", kind="text"),
        ])
    ])
    with pytest.raises(TreeValidationError):
        validate_tree(root)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_profile_tree.py -k validate -v`
Expected: FAIL with `ImportError: cannot import name 'validate_tree'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/profile_tree.py
class TreeValidationError(Exception):
    """Raised when a profile tree violates a structural invariant."""


def _shape(group: GroupNode) -> list[tuple[str, str]]:
    """Return the sorted ``(key, kind)`` multiset that defines a group's shape."""
    return sorted((f.key, f.kind) for f in group.children)


def validate_tree(root: RootNode) -> None:
    """Validate structural invariants of a profile tree.

    Args:
        root: The tree to validate.

    Raises:
        TreeValidationError: If any invariant is violated.
    """
    seen_ids: set[str] = set()

    def visit(node: object) -> None:
        nid = getattr(node, "id", None)
        if nid is not None:
            if nid in seen_ids:
                raise TreeValidationError(f"Duplicate node id: {nid}")
            seen_ids.add(nid)

        if isinstance(node, GroupNode):
            keys = [f.key for f in node.children]
            if len(set(keys)) != len(keys):
                raise TreeValidationError(f"Duplicate field key in group {node.name!r}")

        if isinstance(node, FieldNode) and node.kind == "bullets":
            if node.min is not None and node.max is not None and not (0 <= node.min <= node.max):
                raise TreeValidationError(f"Invalid bullets bounds in field {node.name!r}")

        if isinstance(node, SectionNode):
            if len(node.children) != 1:
                raise TreeValidationError(
                    f"Section {node.name!r} must have exactly one child"
                )
            child = node.children[0]
            if not isinstance(child, (ListNode, GroupNode, FieldNode)):
                raise TreeValidationError(f"Section {node.name!r} has invalid child type")

        if isinstance(node, ListNode):
            tmpl_shape = _shape(node.item_template)
            for item in node.children:
                if _shape(item) != tmpl_shape:
                    raise TreeValidationError(
                        f"List {node.name!r} item does not conform to item_template"
                    )

        children = getattr(node, "children", None)
        if children is not None:
            orders = [getattr(c, "order", 0) for c in children]
            if len(set(orders)) != len(orders):
                raise TreeValidationError("Duplicate sibling order")
            for c in children:
                visit(c)
        if isinstance(node, ListNode):
            visit(node.item_template)

    visit(root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_profile_tree.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add core/profile_tree.py tests/core/test_profile_tree.py
git commit -m "[feat] Add profile-tree structural validation"
```

---

### Task 3: Presets + migration (`legacy_to_tree`)

**Files:**
- Create: `core/section_presets.py`
- Modify: `core/profile_tree.py`
- Test: `tests/core/test_profile_tree.py`

**Interfaces:**
- Consumes: node models (Task 1), `validate_tree` (Task 2).
- Produces, in `core/section_presets.py`: `header_section()`, `summary_section()`, `experience_template()`, `education_template()`, `projects_template()`, `skills_section()`, each returning the relevant node. In `core/profile_tree.py`: `def legacy_to_tree(data: dict) -> RootNode` — builds the default preset tree from a legacy profile dict. Field `key`s used by the adapter: header → `first_name,last_name,email,phone,location,github,linkedin,website`; summary → `hero`; experience item → `company,title,start,end,summary`; education item → `institution,degree,field,graduated,gpa`; projects item → `name,description,url,technologies`; skills → single `skills` taglist field.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/core/test_profile_tree.py
LEGACY = {
    "first_name": "Matt", "last_name": "Barlow", "hero": "Engineer",
    "email": "m@x.com", "phone": "555", "location": "Remote",
    "github": "gh", "linkedin": "li", "website": "w",
    "skills": ["Python", "SQL"],
    "work_history": [
        {"company": "Acme", "title": "SWE", "start": "2022", "end": "Now", "summary": "Built."},
    ],
    "education": [
        {"institution": "Columbia", "degree": "B.S.", "field": "EE", "graduated": "2018", "gpa": 3.5},
    ],
    "projects": [
        {"name": "auto_apply", "description": "Pipeline", "url": "u", "technologies": ["Python"]},
    ],
}


def test_legacy_to_tree_is_valid_and_has_sections():
    from core.profile_tree import legacy_to_tree, validate_tree

    root = legacy_to_tree(LEGACY)
    validate_tree(root)
    roles = [s.role for s in root.children]
    assert roles == ["header", "summary", "experience", "education", "projects", "skills"]


def test_legacy_to_tree_populates_experience_item():
    from core.profile_tree import legacy_to_tree

    root = legacy_to_tree(LEGACY)
    exp = next(s for s in root.children if s.role == "experience")
    item = exp.children[0].children[0]
    vals = {f.key: f.value for f in item.children}
    assert vals["company"] == "Acme" and vals["summary"] == "Built."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_profile_tree.py -k legacy_to_tree -v`
Expected: FAIL with `ImportError: cannot import name 'legacy_to_tree'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/section_presets.py
"""Preset section subtrees mirroring the legacy master profile field-for-field.

Migration and (later) the builder gallery both consume these. Item templates
mirror today's stored profile so a migrated profile renders identically.
"""
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode

_HEADER_KEYS = [
    ("first_name", "First Name"), ("last_name", "Last Name"),
    ("email", "Email"), ("phone", "Phone"), ("location", "Location"),
    ("github", "GitHub"), ("linkedin", "LinkedIn"), ("website", "Website"),
]


def header_section() -> SectionNode:
    """Contact block: a group of text fields keyed by legacy contact field."""
    fields = [
        FieldNode(name=label, key=key, kind="text", order=i)
        for i, (key, label) in enumerate(_HEADER_KEYS)
    ]
    return SectionNode(
        name="Header", role="header", order=0,
        children=[GroupNode(name="Contact", children=fields)],
    )


def summary_section() -> SectionNode:
    """Profile summary: one markdown field (maps to legacy ``hero``)."""
    return SectionNode(
        name="Summary", role="summary", order=1,
        children=[FieldNode(name="Summary", key="hero", kind="markdown", llm_output=True)],
    )


def experience_template() -> GroupNode:
    """One work-history item, mirroring ``WorkHistoryEntry``."""
    return GroupNode(name="Experience Item", children=[
        FieldNode(name="Company", key="company", kind="text", order=0),
        FieldNode(name="Title", key="title", kind="text", order=1),
        FieldNode(name="Start", key="start", kind="text", order=2),
        FieldNode(name="End", key="end", kind="text", order=3),
        FieldNode(name="Summary", key="summary", kind="markdown", order=4, llm_output=True),
    ])


def education_template() -> GroupNode:
    """One education item, mirroring ``EducationEntry``."""
    return GroupNode(name="Education Item", children=[
        FieldNode(name="Institution", key="institution", kind="text", order=0),
        FieldNode(name="Degree", key="degree", kind="text", order=1),
        FieldNode(name="Field", key="field", kind="text", order=2),
        FieldNode(name="Graduated", key="graduated", kind="text", order=3),
        FieldNode(name="GPA", key="gpa", kind="text", order=4),
    ])


def projects_template() -> GroupNode:
    """One project item, mirroring ``ProjectEntry``."""
    return GroupNode(name="Project Item", children=[
        FieldNode(name="Name", key="name", kind="text", order=0),
        FieldNode(name="Description", key="description", kind="markdown", order=1, llm_output=True),
        FieldNode(name="URL", key="url", kind="text", order=2),
        FieldNode(name="Technologies", key="technologies", kind="taglist", order=3),
    ])


def skills_section() -> SectionNode:
    """Skills: one flat taglist field (mirrors legacy ``skills`` list)."""
    return SectionNode(
        name="Skills", role="skills", order=5,
        children=[FieldNode(name="Skills", key="skills", kind="taglist")],
    )
```

```python
# append to core/profile_tree.py
def _gpa_to_str(v: object) -> str:
    if v in (None, "", 0, 0.0):
        return ""
    return str(v)


def legacy_to_tree(data: dict) -> "RootNode":
    """Build the default preset tree from a legacy flat profile dict."""
    from core.section_presets import (
        education_template, experience_template, header_section,
        projects_template, skills_section, summary_section,
    )

    def _instances(rows: list[dict], template: GroupNode, mapper) -> list[GroupNode]:
        items: list[GroupNode] = []
        for i, row in enumerate(rows or []):
            vals = mapper(row)
            fields = [
                FieldNode(
                    name=t.name, key=t.key, kind=t.kind, order=t.order,
                    llm_output=t.llm_output, value=vals.get(t.key, ""),
                )
                for t in template.children
            ]
            items.append(GroupNode(name=template.name, order=i, children=fields))
        return items

    header = header_section()
    for f in header.children[0].children:
        f.value = data.get(f.key, "") or ""

    summary = summary_section()
    summary.children[0].value = data.get("hero", "") or ""

    exp_tmpl = experience_template()
    experience = SectionNode(name="Experience", role="experience", order=2, children=[
        ListNode(name="Experience", item_template=exp_tmpl,
                 children=_instances(data.get("work_history"), exp_tmpl, lambda r: r))
    ])

    edu_tmpl = education_template()
    education = SectionNode(name="Education", role="education", order=3, children=[
        ListNode(name="Education", item_template=edu_tmpl,
                 children=_instances(
                     data.get("education"), edu_tmpl,
                     lambda r: {**r, "gpa": _gpa_to_str(r.get("gpa"))}))
    ])

    proj_tmpl = projects_template()
    projects = SectionNode(name="Projects", role="projects", order=4, children=[
        ListNode(name="Projects", item_template=proj_tmpl,
                 children=_instances(data.get("projects"), proj_tmpl, lambda r: r))
    ])

    skills = skills_section()
    skills.children[0].value = list(data.get("skills") or [])

    return RootNode(children=[header, summary, experience, education, projects, skills])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_profile_tree.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add core/section_presets.py core/profile_tree.py tests/core/test_profile_tree.py
git commit -m "[feat] Add section presets and legacy-to-tree migration"
```

---

### Task 4: Adapter (`tree_to_legacy`) + golden round-trip

**Files:**
- Modify: `core/profile_tree.py`
- Test: `tests/core/test_profile_tree.py`

**Interfaces:**
- Consumes: node models, `legacy_to_tree`, `core.document_assembler.assemble_resume_markdown`, `core.document_builder.build_resume_document`.
- Produces: `def tree_to_legacy(root: RootNode) -> dict` returning keys `first_name,last_name,hero,email,phone,location,github,linkedin,website,skills,work_history,education,projects` (the document-section subset; metadata keys are NOT produced). `work_history`/`education`/`projects` are lists of dicts whose keys match the legacy dataclasses (`WorkHistoryEntry`, `EducationEntry` with float `gpa`, `ProjectEntry`).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/core/test_profile_tree.py
def test_tree_to_legacy_round_trips_fields():
    from core.profile_tree import legacy_to_tree, tree_to_legacy

    out = tree_to_legacy(legacy_to_tree(LEGACY))
    assert out["email"] == "m@x.com"
    assert out["skills"] == ["Python", "SQL"]
    assert out["work_history"][0] == {
        "company": "Acme", "title": "SWE", "start": "2022", "end": "Now", "summary": "Built.",
    }
    assert out["education"][0]["gpa"] == 3.5
    assert out["projects"][0]["technologies"] == ["Python"]


def test_golden_round_trip_markdown_identical():
    """legacy -> tree -> legacy must produce byte-identical assembled markdown."""
    from types import SimpleNamespace

    from core.document_assembler import assemble_resume_markdown
    from core.document_builder import build_resume_document
    from core.profile_tree import legacy_to_tree, tree_to_legacy
    from core.schemas import ResumeGeneration
    from core.user import EducationEntry, ProjectEntry, WorkHistoryEntry

    def _user(d: dict):
        u = SimpleNamespace(**{k: "" for k in (
            "first_name", "last_name", "email", "phone", "location",
            "github", "linkedin", "website")})
        u.first_name = d["first_name"]; u.last_name = d["last_name"]
        u.email = d["email"]; u.phone = d["phone"]; u.location = d["location"]
        u.github = d["github"]; u.linkedin = d["linkedin"]; u.website = d["website"]
        u.skills = d["skills"]
        u.work_history = [WorkHistoryEntry(**e) for e in d["work_history"]]
        u.education = [EducationEntry(**e) for e in d["education"]]
        u.projects = [ProjectEntry(**e) for e in d["projects"]]
        u.full_name = lambda: f"{d['first_name']} {d['last_name']}".strip()
        return u

    gen = ResumeGeneration()  # empty prose; structure-only comparison
    db = None
    before = assemble_resume_markdown(build_resume_document(_user(LEGACY), gen, _StubDB()))
    after_legacy = tree_to_legacy(legacy_to_tree(LEGACY))
    after = assemble_resume_markdown(build_resume_document(_user(after_legacy), gen, _StubDB()))
    assert before == after


class _StubDB:
    def query(self, *a, **k):
        return self

    def filter_by(self, *a, **k):
        return self

    def first(self):
        return None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_profile_tree.py -k "tree_to_legacy or golden" -v`
Expected: FAIL with `ImportError: cannot import name 'tree_to_legacy'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/profile_tree.py
def _section_by_role(root: "RootNode", role: str) -> Optional[SectionNode]:
    for s in root.children:
        if s.role == role:
            return s
    return None


def _gpa_to_float(v: object) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def tree_to_legacy(root: "RootNode") -> dict:
    """Project a profile tree into the legacy flat document-section dict."""
    out: dict = {
        "first_name": "", "last_name": "", "hero": "", "email": "", "phone": "",
        "location": "", "github": "", "linkedin": "", "website": "",
        "skills": [], "work_history": [], "education": [], "projects": [],
    }

    header = _section_by_role(root, "header")
    if header and header.children and isinstance(header.children[0], GroupNode):
        for f in header.children[0].children:
            if f.key in out:
                out[f.key] = f.value

    summary = _section_by_role(root, "summary")
    if summary and summary.children and isinstance(summary.children[0], FieldNode):
        out["hero"] = summary.children[0].value

    skills = _section_by_role(root, "skills")
    if skills and skills.children and isinstance(skills.children[0], FieldNode):
        out["skills"] = list(skills.children[0].value)

    def _rows(role: str) -> list[dict]:
        sect = _section_by_role(root, role)
        if not sect or not sect.children or not isinstance(sect.children[0], ListNode):
            return []
        return [{f.key: f.value for f in item.children} for item in sect.children[0].children]

    out["work_history"] = [
        {"company": r.get("company", ""), "title": r.get("title", ""),
         "start": r.get("start", ""), "end": r.get("end", ""),
         "summary": r.get("summary", "")}
        for r in _rows("experience")
    ]
    out["education"] = [
        {"institution": r.get("institution", ""), "degree": r.get("degree", ""),
         "field": r.get("field", ""), "graduated": r.get("graduated", ""),
         "gpa": _gpa_to_float(r.get("gpa", ""))}
        for r in _rows("education")
    ]
    out["projects"] = [
        {"name": r.get("name", ""), "description": r.get("description", ""),
         "url": r.get("url", ""), "technologies": list(r.get("technologies", []))}
        for r in _rows("projects")
    ]
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_profile_tree.py -v`
Expected: PASS (all tests, including the golden round-trip)

- [ ] **Step 5: Commit**

```bash
git add core/profile_tree.py tests/core/test_profile_tree.py
git commit -m "[feat] Add tree-to-legacy adapter with golden round-trip test"
```

---

### Task 5: Wire the tree into `User` (persist, derive, migrate)

**Files:**
- Modify: `core/user.py` (`_hydrate` ~lines 86-123, `_to_dict` ~lines 125-153)
- Modify: `tests/core/test_user.py`
- Docs: `core/CONTEXT.md`, `ARCHITECTURE.md`

**Interfaces:**
- Consumes: `legacy_to_tree`, `tree_to_legacy`, `validate_tree`, `RootNode` from `core.profile_tree`.
- Produces: `User.profile_tree: RootNode` instance attribute, always set after hydration. `_hydrate` returns `True` (triggering a save) when it had to migrate a legacy profile that lacked `profile_tree`. `_to_dict` includes `"profile_tree": <json>`. Derived legacy attrs (`work_history`, `education`, `projects`, `skills`, contact fields, `hero`) come from the tree, not raw.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/core/test_user.py
def test_load_migrates_legacy_profile_to_tree(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()

    user = User.load(db_session)
    assert getattr(user, "profile_tree", None) is not None
    assert [s.role for s in user.profile_tree.children][0] == "header"
    # Derived legacy attrs survive the round-trip.
    assert user.email == "matt@example.com"
    assert user.skills == ["Python", "SQL"]
    assert user.work_history[0].company == "Acme"
    # Migration persisted the tree.
    stored = json.loads(db_session.query(User).first().data)
    assert "profile_tree" in stored


def test_migration_is_idempotent(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()

    User.load(db_session)
    data_after_first = db_session.query(User).first().data
    User.load(db_session)
    data_after_second = db_session.query(User).first().data
    assert data_after_first == data_after_second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_user.py -k migrat -v`
Expected: FAIL with `AssertionError` (no `profile_tree` attribute / not stored)

- [ ] **Step 3: Write minimal implementation**

Modify `core/user.py` `_hydrate` — replace the raw-driven section assignments. After `raw = json.loads(self.data or "{}")`, build/derive the tree before setting the legacy attrs:

```python
        raw = json.loads(self.data or "{}")

        from core.profile_tree import (
            RootNode, legacy_to_tree, tree_to_legacy, validate_tree,
        )
        tree_raw = raw.get("profile_tree")
        migrated_tree = False
        if tree_raw:
            self.profile_tree = RootNode.model_validate(tree_raw)
        else:
            self.profile_tree = legacy_to_tree(raw)
            migrated_tree = True
        validate_tree(self.profile_tree)
        derived = tree_to_legacy(self.profile_tree)
        raw = {**raw, **derived}  # tree is source of truth for document sections
```

Leave the existing `self.first_name = raw.get(...)` block and below **unchanged** — they now read the tree-derived values. Change the existing `return False` at the end of `_hydrate` to:

```python
        return migrated_tree
```

Modify `_to_dict` — add the tree to the serialized dict (before `return d` / the refine keys):

```python
        d["profile_tree"] = self.profile_tree.model_dump(mode="json")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_user.py -v`
Expected: PASS (existing tests + the two new migration tests). Then run the full core suite to confirm no regression in the generation/assembler path:

Run: `pytest tests/core -v`
Expected: PASS (no regressions)

- [ ] **Step 5: Update docs**

In `core/CONTEXT.md`, add to the Files list:
```
├── profile_tree.py      # Recursive typed profile/résumé tree (closed node vocab) + validate_tree + tree_to_legacy adapter + legacy_to_tree migration
├── section_presets.py   # Preset section subtrees mirroring the legacy master profile (header/summary/experience/education/projects/skills)
```
And add a short section:
```
## Profile Schema Engine

`profile_tree.py` is the source of truth for profile structure: a recursive,
closed-vocabulary node tree (root → section → list/group → field). `User`
stores it as `profile_tree` inside `user_profile.data` and derives the legacy
typed attrs (`work_history`/`education`/`projects`/`skills`/contact/`hero`) from
it on every load via `tree_to_legacy`, so generation/rendering/UI are unchanged.
Legacy profiles are migrated once on load via `legacy_to_tree`. Job-search
metadata (target roles/salary, resume/md paths) stays as flat `data` keys, not
in the tree. **Known gap:** custom (non-`role`) sections are storable but do not
appear on generated documents until sub-project #4.
```
In `ARCHITECTURE.md`, under the LLM & Document section, note the schema engine landed as sub-project #1 (tree source of truth + legacy adapter; downstream stages pending).

- [ ] **Step 6: Commit**

```bash
git add core/user.py tests/core/test_user.py core/CONTEXT.md ARCHITECTURE.md
git commit -m "[feat] Make profile tree the source of truth with legacy adapter"
```

---

## Self-Review

**Spec coverage:**
- Node model / closed vocabulary → Task 1. ✓
- Item-template enforcement → Task 2 (conformance check). ✓
- Validation rules (unique order/id, single section child, bullets bounds, key uniqueness) → Task 2. ✓
- Presets → Task 3. ✓
- Migration (`legacy_to_tree`, idempotent) → Tasks 3 & 5. ✓
- Adapter (`tree_to_legacy`) + byte-identical golden test → Task 4. ✓
- Storage in `user_profile.data` → Task 5. ✓
- Unified profile/document model → established by the tree being source of truth + shared node vocab (Task 5); the per-job transform is #3/#4, out of scope. ✓
- Docs / known custom-section gap → Task 5 Step 5. ✓

**Spec divergence (intentional, tightening):** spec §1a illustrated Skills as a list of `{category, entries}` groups and Experience with a `bullets` description + hidden `skills_used`. The plan's migration presets instead mirror the legacy master profile exactly (flat `skills` taglist; experience `summary` markdown) so output is byte-identical. The richer shapes are examples of what users build in #2, not the migration baseline. Noted in Global Constraints.

**Type consistency:** `FieldNode.key`/`kind`/`value`, `GroupNode.children`, `ListNode.item_template`/`children`, `SectionNode.role`/`children`, `RootNode.children`, `validate_tree`, `legacy_to_tree`, `tree_to_legacy` are referenced consistently across Tasks 1–5. Adapter output keys match the legacy dataclasses consumed by `document_builder`.

**No placeholders:** every code/test step contains complete content.
