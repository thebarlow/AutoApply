# #5 Onboarding Parse → Schema Sections — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make résumé parsing schema-aware — extract built-in sections as today AND detect novel sections (Certifications, Languages, …), infer a structure for each, and let the user review every section per-section (add/replace/merge/skip) before anything is written, in both onboarding and re-parse.

**Architecture:** The parse LLM gains an open `extra_sections` output. A two-phase API (propose → apply) replaces the single auto-applying parse: propose runs the LLM and returns a `ParseProposal` (built-in + novel rows, no persist); a shared `ParsePreview` UI collects per-section decisions; apply normalizes every section to a `SectionNode` and runs uniform tree ops (add/replace/merge/skip) under the existing tree caps. Built-in extraction and the legacy `parse` endpoint are unchanged.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy (SQLite dev, Postgres hosted) / Pydantic; React (Vite + Vitest/RTL).

## Global Constraints

- **Release:** Merge to LOCAL `main` only. #5 is the LAST sub-project — after it merges the whole swap (#1–#6) is complete; do NOT push `main` without explicit user approval.
- **Back-compat:** Empty `extra_sections` ⇒ built-in extraction and the resulting tree are identical to today. The legacy `POST …/parse` endpoint stays unchanged (built-in only). Built-in sections always apply via the existing preset/flat path, so rendering / generation / ATS are unaffected.
- **Add-only-safe defaults:** a re-parse never overwrites a section that already holds data unless the user explicitly chose replace/merge.
- **Parse kinds (closed):** `markdown`, `bullets`, `taglist`, `fields`, `list` — named to match existing `FieldNode.kind`; NO new node type.
- **Merge** is offered only for `list` (append records), `taglist` (union, case-insensitive dedup), `bullets` (append). `markdown`/`fields` get add/replace/skip only.
- **Tree caps:** every persisted tree passes `validate_tree_limits` (≤500 nodes / ≤6 deep) → 422 on violation.
- Python: type hints, `black`, Google-style docstrings. Prefer stdlib.

**Reference:** spec `docs/superpowers/specs/2026-06-27-onboarding-parse-schema-design.md`. Pattern precedents: `core/schemas.py` `ParseResponse`; `core/section_presets.py` + `core/profile_tree.py` `legacy_to_tree`/`validate_tree_limits`/`apply_flat_to_tree`/`merge_flat_into_stored`; `web/routers/config.py` `parse_profile_from_resume` (lines 862-908); `db/seed.py` `seed_prompt_defaults` + `db/database.py` `_seed_ats_parse_prompt`; `react-dashboard/src/components/Onboarding/StepResume.jsx`; `core/output_formats.py` (registry style).

---

### Task 1: Parse schema — `extra_sections`

**Files:**
- Modify: `core/schemas.py` (after `ParseResponse`, ~line 141)
- Test: `tests/core/test_extra_sections_schema.py`

**Interfaces:**
- Produces: `ParsedField(label:str="", value:str="")`; `ParsedEntry(fields:list[ParsedField])`; `ExtraSection(name:str="", kind:Literal["markdown","bullets","taglist","fields","list"], markdown:str="", items:list[str], fields:list[ParsedField], entries:list[ParsedEntry])`; `ParseResponse.extra_sections: list[ExtraSection] = []`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_extra_sections_schema.py
from core.schemas import ParseResponse, ExtraSection, ParsedField, ParsedEntry


def test_extra_sections_defaults_empty():
    r = ParseResponse()
    assert r.extra_sections == []


def test_parse_response_with_extra_sections_round_trips():
    payload = {
        "first_name": "Ada",
        "extra_sections": [
            {"name": "Certifications", "kind": "list",
             "entries": [{"fields": [{"label": "Name", "value": "AWS SAA"},
                                     {"label": "Year", "value": "2023"}]}]},
            {"name": "Languages", "kind": "taglist", "items": ["English", "Spanish"]},
            {"name": "About", "kind": "markdown", "markdown": "Engineer."},
        ],
    }
    r = ParseResponse.model_validate(payload)
    assert r.first_name == "Ada"
    assert [s.kind for s in r.extra_sections] == ["list", "taglist", "markdown"]
    assert r.extra_sections[0].entries[0].fields[1].value == "2023"
    assert r.extra_sections[1].items == ["English", "Spanish"]


def test_invalid_kind_rejected():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ExtraSection(name="X", kind="paragraph")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_extra_sections_schema.py -q`
Expected: FAIL (ImportError: ExtraSection)

- [ ] **Step 3: Write minimal implementation**

In `core/schemas.py`, add (mirroring the existing `BaseModel` style; `Literal`/`Field` are already imported — confirm and add if missing):

```python
class ParsedField(BaseModel):
    """A label/value pair extracted from a novel résumé section."""

    label: str = ""
    value: str = ""


class ParsedEntry(BaseModel):
    """One record within a novel ``list`` section."""

    fields: list[ParsedField] = Field(default_factory=list)


class ExtraSection(BaseModel):
    """A résumé section that does not map to a built-in profile field.

    ``kind`` selects which payload field carries the content:
    ``markdown`` → ``markdown``; ``bullets``/``taglist`` → ``items``;
    ``fields`` → ``fields``; ``list`` → ``entries``.
    """

    name: str = ""
    kind: Literal["markdown", "bullets", "taglist", "fields", "list"]
    markdown: str = ""
    items: list[str] = Field(default_factory=list)
    fields: list[ParsedField] = Field(default_factory=list)
    entries: list[ParsedEntry] = Field(default_factory=list)
```

And add to `ParseResponse`:

```python
    extra_sections: list[ExtraSection] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_extra_sections_schema.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add core/schemas.py tests/core/test_extra_sections_schema.py
git commit -m "[feat] Parse schema: open extra_sections for novel résumé sections"
```

---

### Task 2: Prompt v2 + reseed upgrade

**Files:**
- Modify: `prompts/defaults/resume_parse.md` (add `extra_sections` instructions + schema)
- Create: `db/migrations_data.py` with `upgrade_resume_parse_prompt(db)` (idempotent)
- Modify: `db/database.py` `init_db()` to call it after seeding (near `_seed_ats_parse_prompt()`, line 308)
- Test: `tests/db/test_reseed_resume_parse.py`

**Interfaces:**
- Consumes: `prompts/defaults/resume_parse.md` (v2 content), the `PromptDefault` + `Prompt` tables.
- Produces: `upgrade_resume_parse_prompt(db: Session) -> int` — updates the `resume_parse` `PromptDefault` row to the v2 file content, and updates every profile `Prompt` row of type `resume_parse` whose content matches the **v1 baseline** (whitespace-normalized) to v2; leaves user-customized prompts untouched. Returns the count of profile rows upgraded. Idempotent (re-running after upgrade is a no-op because content now equals v2, not v1).

- [ ] **Step 1: Capture the v1 baseline**

Read the CURRENT `prompts/defaults/resume_parse.md` in full and copy its exact text into the migration module as `_V1_BASELINE` (this is the content existing stock profiles hold; it is the upgrade-eligibility key). Do this BEFORE editing the file.

- [ ] **Step 2: Write the failing test**

```python
# tests/db/test_reseed_resume_parse.py
from db.database import SessionLocal, Prompt, PromptDefault
from db.migrations_data import upgrade_resume_parse_prompt, _V1_BASELINE
from core.user import User


def _make_profile(db, prompt_content):
    u = User(name="P", data="{}")
    db.add(u); db.flush()
    db.add(Prompt(profile_id=u.id, type_key="resume_parse",
                  content=prompt_content, model="", updated_at="t"))
    db.commit()
    return u.id


def test_stock_prompt_is_upgraded(db_session):
    pid = _make_profile(db_session, _V1_BASELINE)
    n = upgrade_resume_parse_prompt(db_session)
    row = db_session.query(Prompt).filter_by(profile_id=pid, type_key="resume_parse").first()
    assert "extra_sections" in row.content     # v2 marker
    assert n >= 1


def test_customized_prompt_is_left_alone(db_session):
    pid = _make_profile(db_session, _V1_BASELINE + "\n# MY CUSTOM RULE\n")
    upgrade_resume_parse_prompt(db_session)
    row = db_session.query(Prompt).filter_by(profile_id=pid, type_key="resume_parse").first()
    assert "MY CUSTOM RULE" in row.content
    assert "extra_sections" not in row.content


def test_idempotent(db_session):
    _make_profile(db_session, _V1_BASELINE)
    upgrade_resume_parse_prompt(db_session)
    second = upgrade_resume_parse_prompt(db_session)
    assert second == 0
```

> Use the project's existing `db_session` test fixture (check `tests/conftest.py` / how `tests/db/` and `tests/core/test_user.py` build a session). Adapt `_make_profile` to the real `User`/`Prompt` construction if column names differ.

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/db/test_reseed_resume_parse.py -q`
Expected: FAIL (ModuleNotFoundError: db.migrations_data)

- [ ] **Step 4: Write the v2 prompt + migration**

Append to `prompts/defaults/resume_parse.md` (do NOT remove existing fixed-field rules): a new top-level field `extra_sections` in the schema and a guidance block. The instructions must say: put any résumé section that is NOT one of {contact, summary/hero, skills, work experience, education, projects} into `extra_sections`; for each, pick the closest `kind` from `markdown` (a prose block), `bullets` (a bullet list), `taglist` (a flat list of short terms), `fields` (one block of label/value pairs), `list` (repeating records — emit `entries`, each with `fields` of label/value); use `name` for the section heading; preserve wording; never invent. Include a JSON example for one `list` (Certifications) and one `taglist` (Languages).

Create `db/migrations_data.py`:

```python
"""Idempotent data migrations for editable, DB-backed content (prompts)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

_DEFAULTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "defaults"

# Exact v1 shipped content of resume_parse.md — the upgrade-eligibility key.
# Profiles whose resume_parse prompt equals this (whitespace-normalized) are on
# the stock prompt and safe to upgrade; anything else is user-customized.
_V1_BASELINE = """<PASTE EXACT v1 resume_parse.md CONTENT HERE>"""


def _norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in (s or "").strip().splitlines())


def upgrade_resume_parse_prompt(db: Session) -> int:
    """Reseed the resume_parse prompt to v2 for stock (non-customized) profiles.

    Updates the PromptDefault row to the current file content, then upgrades
    every profile Prompt of type ``resume_parse`` whose content matches the v1
    baseline. User-edited prompts are left untouched. Idempotent.

    Returns:
        Number of profile prompt rows upgraded.
    """
    from db.database import Prompt, PromptDefault

    v2 = (_DEFAULTS_DIR / "resume_parse.md").read_text(encoding="utf-8")
    default = db.query(PromptDefault).filter_by(type_key="resume_parse").first()
    if default is not None:
        default.content = v2
    upgraded = 0
    baseline = _norm(_V1_BASELINE)
    for row in db.query(Prompt).filter_by(type_key="resume_parse").all():
        if _norm(row.content) == baseline:
            row.content = v2
            upgraded += 1
    db.commit()
    return upgraded
```

In `db/database.py` `init_db()`, after `_seed_ats_parse_prompt()` (line 308), add:

```python
    from db.migrations_data import upgrade_resume_parse_prompt
    _db = SessionLocal()
    try:
        upgrade_resume_parse_prompt(_db)
    finally:
        _db.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/db/test_reseed_resume_parse.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add prompts/defaults/resume_parse.md db/migrations_data.py db/database.py tests/db/test_reseed_resume_parse.py
git commit -m "[feat] resume_parse prompt v2 (extra_sections) + idempotent reseed for stock profiles"
```

---

### Task 3: `build_section_from_parsed`

**Files:**
- Create: `core/parsed_sections.py`
- Test: `tests/core/test_build_section_from_parsed.py`

**Interfaces:**
- Consumes: `ExtraSection` (Task 1); `SectionNode`/`ListNode`/`GroupNode`/`FieldNode` from `core/profile_tree`.
- Produces: `build_section_from_parsed(extra: ExtraSection, order: int = 0) -> SectionNode`. Novel sections use `role=""`, fields `llm_output=False`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_build_section_from_parsed.py
from core.schemas import ExtraSection, ParsedField, ParsedEntry
from core.parsed_sections import build_section_from_parsed


def test_markdown_kind():
    s = build_section_from_parsed(ExtraSection(name="About", kind="markdown", markdown="Hi."))
    assert s.name == "About" and s.role == ""
    assert len(s.children) == 1
    f = s.children[0]
    assert f.type == "field" and f.kind == "markdown" and f.value == "Hi."
    assert f.llm_output is False


def test_bullets_and_taglist_single_field():
    b = build_section_from_parsed(ExtraSection(name="Wins", kind="bullets", items=["a", "b"]))
    assert b.children[0].kind == "bullets" and b.children[0].value == ["a", "b"]
    t = build_section_from_parsed(ExtraSection(name="Langs", kind="taglist", items=["EN", "ES"]))
    assert t.children[0].kind == "taglist" and t.children[0].value == ["EN", "ES"]


def test_fields_kind_is_one_group():
    s = build_section_from_parsed(ExtraSection(
        name="Links", kind="fields",
        fields=[ParsedField(label="Portfolio", value="x.com"),
                ParsedField(label="Blog", value="y.com")]))
    assert len(s.children) == 1 and s.children[0].type == "group"
    g = s.children[0]
    assert [f.name for f in g.children] == ["Portfolio", "Blog"]
    assert [f.value for f in g.children] == ["x.com", "y.com"]
    assert all(f.kind == "text" for f in g.children)


def test_list_kind_builds_list_with_union_template():
    s = build_section_from_parsed(ExtraSection(
        name="Certifications", kind="list",
        entries=[
            ParsedEntry(fields=[ParsedField(label="Name", value="AWS"),
                                ParsedField(label="Year", value="2023")]),
            ParsedEntry(fields=[ParsedField(label="Name", value="GCP"),
                                ParsedField(label="Issuer", value="Google")]),
        ]))
    lst = s.children[0]
    assert lst.type == "list"
    # union of labels across entries, first-seen order
    assert [f.name for f in lst.item_template.children] == ["Name", "Year", "Issuer"]
    assert len(lst.children) == 2
    first = {f.name: f.value for f in lst.children[0].children}
    assert first["Name"] == "AWS" and first["Year"] == "2023" and first.get("Issuer", "") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_build_section_from_parsed.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# core/parsed_sections.py
"""Build schema tree sections from parsed novel résumé sections (#5)."""
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode
from core.schemas import ExtraSection


def _union_labels(entries) -> list[str]:
    seen: list[str] = []
    for e in entries:
        for f in e.fields:
            if f.label and f.label not in seen:
                seen.append(f.label)
    return seen


def build_section_from_parsed(extra: ExtraSection, order: int = 0) -> SectionNode:
    """Convert a parsed novel section into a generic (role="") SectionNode.

    Field nodes are ``llm_output=False`` — parsed factual content is verbatim,
    not LLM-authored.
    """
    name = extra.name or "Section"
    if extra.kind in ("markdown", "bullets", "taglist"):
        value = extra.markdown if extra.kind == "markdown" else list(extra.items)
        field = FieldNode(name=name, kind=extra.kind, value=value, llm_output=False)
        return SectionNode(name=name, role="", order=order, children=[field])

    if extra.kind == "fields":
        fields = [FieldNode(name=f.label or f"Field {i+1}", kind="text",
                            value=f.value, order=i, llm_output=False)
                  for i, f in enumerate(extra.fields)]
        return SectionNode(name=name, role="", order=order,
                           children=[GroupNode(name=name, children=fields)])

    # kind == "list"
    labels = _union_labels(extra.entries)
    template = GroupNode(name=f"{name} Item", children=[
        FieldNode(name=lbl, kind="text", order=i, llm_output=False)
        for i, lbl in enumerate(labels)
    ])
    children = []
    for e in extra.entries:
        by_label = {f.label: f.value for f in e.fields}
        children.append(GroupNode(name=f"{name} Item", children=[
            FieldNode(name=lbl, kind="text", order=i, value=by_label.get(lbl, ""),
                      llm_output=False)
            for i, lbl in enumerate(labels)
        ]))
    lst = ListNode(name=name, item_template=template, children=children)
    return SectionNode(name=name, role="", order=order, children=[lst])
```

> Confirm `FieldNode` accepts `llm_output` (it is used in `section_presets.py`). If `SectionNode`/`FieldNode` require other defaults, the model defaults cover them. Keep node construction consistent with `core/section_presets.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_build_section_from_parsed.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add core/parsed_sections.py tests/core/test_build_section_from_parsed.py
git commit -m "[feat] build_section_from_parsed: parsed novel section → tree SectionNode"
```

---

### Task 4: Tree apply ops (add / replace / merge / find / built-in normalize)

**Files:**
- Modify: `core/parsed_sections.py`
- Test: `tests/core/test_parsed_section_apply.py`

**Interfaces:**
- Consumes: `RootNode`/`SectionNode`/`ListNode`/`FieldNode` from `core/profile_tree`; `legacy_to_tree` (builds a populated tree from a flat dict); `ParseResponse` (Task 1).
- Produces:
  - `builtin_sections_from_parse(parsed: ParseResponse) -> list[SectionNode]` — the populated preset sections (header/summary/experience/education/projects/skills) for the parsed fixed fields, via `legacy_to_tree` on a flat dict; each carries its `role`.
  - `find_section(root: RootNode, *, name: str = "", role: str = "") -> SectionNode | None` — case-fold name match, or role match when `role` given.
  - `add_section(root, section: SectionNode) -> None` — append with next order.
  - `replace_section(existing: SectionNode, incoming: SectionNode) -> None` — replace `existing.children` with `incoming.children` in place (keep `existing.id`/`name`/`role`/`prompt`).
  - `merge_section(existing: SectionNode, incoming: SectionNode) -> None` — list→append entries; single taglist field→union (case-insensitive dedup); single bullets field→append. Raises `ValueError` if the section shape is not mergeable.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_parsed_section_apply.py
import pytest

from core.profile_tree import RootNode
from core.schemas import ParseResponse, ExtraSection, ParsedField, ParsedEntry
from core.parsed_sections import (
    build_section_from_parsed, builtin_sections_from_parse,
    find_section, add_section, replace_section, merge_section,
)


def _root_with(*sections) -> RootNode:
    return RootNode(children=list(sections))


def test_builtin_sections_have_roles():
    parsed = ParseResponse(first_name="Ada", skills=["Python"],
                           work_history=[{"company": "Acme", "title": "Eng"}])
    roles = {s.role for s in builtin_sections_from_parse(parsed)}
    assert {"skills", "experience"} <= roles


def test_add_and_find():
    root = _root_with()
    sec = build_section_from_parsed(ExtraSection(name="Awards", kind="bullets", items=["x"]))
    add_section(root, sec)
    assert find_section(root, name="awards") is not None


def test_replace_keeps_id():
    sec = build_section_from_parsed(ExtraSection(name="About", kind="markdown", markdown="old"))
    root = _root_with(sec)
    sid = sec.id
    incoming = build_section_from_parsed(ExtraSection(name="About", kind="markdown", markdown="new"))
    replace_section(sec, incoming)
    assert sec.id == sid and sec.children[0].value == "new"


def test_merge_taglist_unions_case_insensitive():
    sec = build_section_from_parsed(ExtraSection(name="Skills", kind="taglist", items=["Python", "Go"]))
    incoming = build_section_from_parsed(ExtraSection(name="Skills", kind="taglist", items=["go", "Rust"]))
    merge_section(sec, incoming)
    vals = sec.children[0].value
    assert "Rust" in vals and len([v for v in vals if v.lower() == "go"]) == 1


def test_merge_list_appends_entries():
    base = build_section_from_parsed(ExtraSection(
        name="Certs", kind="list",
        entries=[ParsedEntry(fields=[ParsedField(label="Name", value="AWS")])]))
    incoming = build_section_from_parsed(ExtraSection(
        name="Certs", kind="list",
        entries=[ParsedEntry(fields=[ParsedField(label="Name", value="GCP")])]))
    merge_section(base, incoming)
    assert len(base.children[0].children) == 2


def test_merge_markdown_raises():
    a = build_section_from_parsed(ExtraSection(name="About", kind="markdown", markdown="a"))
    b = build_section_from_parsed(ExtraSection(name="About", kind="markdown", markdown="b"))
    with pytest.raises(ValueError):
        merge_section(a, b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_parsed_section_apply.py -q`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

Add to `core/parsed_sections.py`. Implement `builtin_sections_from_parse` by constructing a flat dict from the `ParseResponse` fixed fields (mirror the keys the existing `parse` path uses — `first_name`, `last_name`, `hero`, `email`, `phone`, `location`, `github`, `linkedin`, `website`, `skills`, `work_history`, `education`, `projects`) and calling `legacy_to_tree(flat)`, returning `root.children`. Verify the exact `legacy_to_tree` signature and the flat-dict keys it expects (read `core/profile_tree.py` and how `parse_profile_from_resume` feeds `merge_flat_into_stored`). The helpers:

```python
def find_section(root, *, name: str = "", role: str = ""):
    for s in root.children:
        if role and s.role == role:
            return s
        if name and s.name.casefold() == name.casefold():
            return s
    return None


def add_section(root, section) -> None:
    section.order = len(root.children)
    root.children.append(section)


def replace_section(existing, incoming) -> None:
    existing.children = incoming.children


def _single_field(section, kind):
    if len(section.children) == 1 and getattr(section.children[0], "type", "") == "field" \
            and section.children[0].kind == kind:
        return section.children[0]
    return None


def _list_node(section):
    if section.children and getattr(section.children[0], "type", "") == "list":
        return section.children[0]
    return None


def merge_section(existing, incoming) -> None:
    el, il = _list_node(existing), _list_node(incoming)
    if el is not None and il is not None:
        el.children.extend(il.children)
        return
    for kind, combine in (("taglist", _union), ("bullets", _append)):
        ef, inf = _single_field(existing, kind), _single_field(incoming, kind)
        if ef is not None and inf is not None:
            ef.value = combine(ef.value, inf.value)
            return
    raise ValueError("section shape is not mergeable")


def _union(a, b):
    out = list(a)
    seen = {x.casefold() for x in a}
    for x in b:
        if x.casefold() not in seen:
            out.append(x); seen.add(x.casefold())
    return out


def _append(a, b):
    return list(a) + list(b)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_parsed_section_apply.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add core/parsed_sections.py tests/core/test_parsed_section_apply.py
git commit -m "[feat] Parsed-section tree ops: builtin normalize + add/replace/merge/find"
```

---

### Task 5: Propose endpoint + proposal models

**Files:**
- Modify: `core/schemas.py` (proposal models) or a new `core/parse_proposal.py`
- Modify: `web/routers/config.py` (new `POST …/parse/propose`)
- Test: `tests/web/test_parse_propose.py`

**Interfaces:**
- Consumes: `User.from_pdf`/`from_markdown` (returns a dict incl. `extra_sections` once Task 2's prompt is active); `builtin_sections_from_parse`, `find_section`, `build_section_from_parsed` (Tasks 3-4); the profile's stored tree.
- Produces:
  - `ProposedSection(name, kind, origin: Literal["builtin","novel"], builtin_role: str = "", extra_index: int = -1, matches_existing: bool, existing_has_data: bool, default_action, allowed_actions: list[str], preview: dict)`.
  - `ParseProposal(builtin: ParseResponse, extra_sections: list[ExtraSection], sections: list[ProposedSection], is_onboarding: bool)`.
  - `POST /api/config/profiles/{id}/parse/propose` → `ParseProposal` (no persist; same auth/ownership guard as `parse_profile_from_resume`).

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_parse_propose.py
# Use the project's web test client + a monkeypatched User.from_markdown/from_pdf
# that returns a ParseResponse-shaped dict including extra_sections, so no real LLM runs.
def test_propose_returns_builtin_and_novel(client, db_session, monkeypatch, a_profile_with_resume):
    fake = {
        "first_name": "Ada", "skills": ["Python"],
        "work_history": [{"company": "Acme", "title": "Eng"}],
        "extra_sections": [
            {"name": "Certifications", "kind": "list",
             "entries": [{"fields": [{"label": "Name", "value": "AWS"}]}]},
        ],
    }
    monkeypatch.setattr("core.user.User.from_pdf", classmethod(lambda cls, b, db, profile_id=None: fake))
    monkeypatch.setattr("core.user.User.from_markdown", classmethod(lambda cls, t, db, profile_id=None: fake))
    r = client.post(f"/api/config/profiles/{a_profile_with_resume}/parse/propose")
    assert r.status_code == 200
    body = r.json()
    origins = {s["origin"] for s in body["sections"]}
    assert origins == {"builtin", "novel"}
    novel = [s for s in body["sections"] if s["origin"] == "novel"][0]
    assert novel["name"] == "Certifications" and novel["kind"] == "list"
    assert "add" in novel["allowed_actions"] and "merge" in novel["allowed_actions"]
    # nothing persisted
    assert _profile_tree_section_names(db_session, a_profile_with_resume).count("Certifications") == 0
```

> Build `a_profile_with_resume` / `client` / `_profile_tree_section_names` to match existing `tests/web/` fixtures (see `tests/web/test_profile_api.py` for how a profile with an uploaded résumé path is set up, and how the web `TestClient` + auth are constructed). The monkeypatch keeps the LLM out.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_parse_propose.py -q`
Expected: FAIL (404 — endpoint missing)

- [ ] **Step 3: Write minimal implementation**

Add the proposal models, then the endpoint. The endpoint:
1. Owns/loads the profile (mirror `parse_profile_from_resume` guards + résumé-path resolution + `from_pdf`/`from_markdown` dispatch).
2. `parsed = ParseResponse.model_validate(raw_dict)`.
3. Load the profile's stored tree (`RootNode`) to compute matches. `is_onboarding = ` no built-in section currently has data (reuse the profile's `_has_parsed_resume`-style check, or: every built-in section in the stored tree is empty).
4. Build rows:
   - Built-in: for each `s in builtin_sections_from_parse(parsed)` that has any content, make a `ProposedSection(origin="builtin", builtin_role=s.role, name=s.name, kind=<derived>, matches_existing=True, existing_has_data=<existing section populated?>, default_action=..., allowed_actions=...)`.
   - Novel: for each `i, e in enumerate(parsed.extra_sections)`, `matches = find_section(stored_root, name=e.name)`; `ProposedSection(origin="novel", extra_index=i, name=e.name, kind=e.kind, matches_existing=bool(matches), existing_has_data=..., default_action=..., allowed_actions=_allowed(e.kind))`.
5. `_allowed(kind)`: `["add","replace","skip"] + (["merge"] if kind in {"list","taglist","bullets"} else [])`.
6. Defaults: `is_onboarding` → built-in `replace`, novel `add`; else matched-with-data → `skip`, matched-empty → `replace`, unmatched → `add`.
7. `preview`: a small display dict per kind (e.g. `{"count": len(entries)}` for list, `{"items": items[:5]}` for taglist/bullets, `{"chars": len(markdown)}` for markdown, `{"fields": [f.label …]}` for fields).
8. Return `ParseProposal(builtin=parsed.model_copy(update={"extra_sections": []}), extra_sections=parsed.extra_sections, sections=rows, is_onboarding=is_onboarding)`. **Do not persist.**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_parse_propose.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/schemas.py web/routers/config.py tests/web/test_parse_propose.py
git commit -m "[feat] POST parse/propose: schema-aware parse proposal (no persist)"
```

---

### Task 6: Apply endpoint

**Files:**
- Modify: `web/routers/config.py` (new `POST …/parse/apply`)
- Test: `tests/web/test_parse_apply.py`

**Interfaces:**
- Consumes: `ParseProposal` (Task 5, as request body); `builtin_sections_from_parse`, `find_section`, `add_section`, `replace_section`, `merge_section`, `build_section_from_parsed` (Tasks 3-4); `validate_tree_limits`; the profile's stored tree + `merge_flat_into_stored`/serialization used by the existing parse endpoint.
- Produces: `POST /api/config/profiles/{id}/parse/apply` accepting a `ParseProposal` with each `ProposedSection.action` set; persists the tree; returns `{"id", "name", "applied": <count>}`. Preserves LLM-config + file-pointer fields exactly as `parse_profile_from_resume` does.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_parse_apply.py
def test_apply_adds_novel_and_populates_builtin(client, db_session, a_profile_with_resume):
    proposal = {
        "builtin": {"first_name": "Ada", "skills": ["Python"], "work_history": [], "education": [], "projects": []},
        "extra_sections": [
            {"name": "Certifications", "kind": "list",
             "entries": [{"fields": [{"label": "Name", "value": "AWS"}]}]},
        ],
        "is_onboarding": True,
        "sections": [
            {"name": "Skills", "kind": "taglist", "origin": "builtin", "builtin_role": "skills",
             "extra_index": -1, "matches_existing": True, "existing_has_data": False,
             "default_action": "replace", "allowed_actions": ["replace", "skip"],
             "preview": {}, "action": "replace"},
            {"name": "Certifications", "kind": "list", "origin": "novel", "builtin_role": "",
             "extra_index": 0, "matches_existing": False, "existing_has_data": False,
             "default_action": "add", "allowed_actions": ["add", "skip", "merge"],
             "preview": {}, "action": "add"},
        ],
    }
    r = client.post(f"/api/config/profiles/{a_profile_with_resume}/parse/apply", json=proposal)
    assert r.status_code == 200
    names = _profile_tree_section_names(db_session, a_profile_with_resume)
    assert "Certifications" in names
    # skills populated
    assert "Python" in _skills_values(db_session, a_profile_with_resume)


def test_apply_skip_is_noop_and_merge_unions(client, db_session, a_profile_with_skills):
    # existing Skills has ["Go"]; apply merge taglist with ["go","Rust"] → {"Go","Rust"}
    ...
```

> Fill in the second test and the fixtures against the real test helpers. The key assertions: `add` creates a novel section; `replace`/built-in populates preset sections; `skip` changes nothing; `merge` on skills unions case-insensitively; a tree that would exceed caps returns 422.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_parse_apply.py -q`
Expected: FAIL (404)

- [ ] **Step 3: Write minimal implementation**

The endpoint:
1. Owns/loads the profile + parses the body into `ParseProposal`.
2. Reconstruct the authoritative incoming `SectionNode` per row:
   - `origin=="builtin"`: from `{s.role: s for s in builtin_sections_from_parse(proposal.builtin)}[row.builtin_role]`.
   - `origin=="novel"`: `build_section_from_parsed(proposal.extra_sections[row.extra_index])` with `name=row.name` (honor a user rename).
3. Load the stored `RootNode`. For each row by `action`:
   - `skip`: continue.
   - `add`: `add_section(root, incoming)`.
   - `replace`: `existing = find_section(root, name=row.name, role=row.builtin_role or "")`; if found `replace_section(existing, incoming)` else `add_section(root, incoming)`.
   - `merge`: `existing = find_section(...)`; if found `merge_section(existing, incoming)` else `add_section(root, incoming)`.
4. `validate_tree_limits(root)` → `HTTPException(422)` on `TreeValidationError`.
5. Persist the tree back into the profile data, **preserving** LLM-config + file-pointer fields exactly as `parse_profile_from_resume` (lines 892-902). Use the same serialization the tree editor's PUT uses (`row.data = json.dumps(...)` with the updated `profile_tree`). Set `row.name` from `proposal.builtin` name if currently unset.
6. Return `{"id", "name", "applied": <non-skip count>}`.

> Confirm how the stored tree is read/written in `web/routers/config.py` (the tree GET/PUT from #2A: `GET/PUT /api/config/profiles/{id}/tree`). Reuse that serialization path so the written tree matches what the editor expects, and so `apply_flat_to_tree`/legacy derivation stays consistent.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_parse_apply.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/routers/config.py tests/web/test_parse_apply.py
git commit -m "[feat] POST parse/apply: persist per-section decisions (add/replace/merge/skip)"
```

---

### Task 7: API client + `ParsePreview` component

**Files:**
- Modify: `react-dashboard/src/api.js` (`proposeParse`, `applyParse`)
- Create: `react-dashboard/src/components/widgets/parse/ParsePreview.jsx`
- Test: `react-dashboard/src/components/widgets/parse/ParsePreview.test.jsx`

**Interfaces:**
- Consumes: `POST …/parse/propose` + `…/parse/apply`.
- Produces: `proposeParse(profileId)` → proposal; `applyParse(profileId, proposal)`; `ParsePreview({ proposal, onApply, onCancel, applying })` — renders two groups (Standard = `origin:"builtin"`, Additional = `origin:"novel"`), a per-row action `<select>` limited to `allowed_actions` (default `default_action`), a rename `<input>` for novel rows, and Apply/Cancel. Apply calls `onApply(editedProposal)` where each section carries its chosen `action` (+ edited `name`).

- [ ] **Step 1: Write the failing test**

```jsx
// ParsePreview.test.jsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ParsePreview from './ParsePreview'

const proposal = {
  builtin: {}, extra_sections: [{ name: 'Certifications', kind: 'list', entries: [] }],
  is_onboarding: true,
  sections: [
    { name: 'Skills', kind: 'taglist', origin: 'builtin', builtin_role: 'skills', extra_index: -1,
      matches_existing: true, existing_has_data: false, default_action: 'replace',
      allowed_actions: ['replace', 'skip'], preview: {} },
    { name: 'Certifications', kind: 'list', origin: 'novel', builtin_role: '', extra_index: 0,
      matches_existing: false, existing_has_data: false, default_action: 'add',
      allowed_actions: ['add', 'skip', 'merge'], preview: {} },
  ],
}

describe('ParsePreview', () => {
  it('shows both groups and gates actions, applies edited proposal', () => {
    const onApply = vi.fn()
    render(<ParsePreview proposal={proposal} onApply={onApply} onCancel={() => {}} />)
    expect(screen.getByText(/Standard sections/i)).toBeInTheDocument()
    expect(screen.getByText(/Additional sections/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /apply/i }))
    const sent = onApply.mock.calls[0][0]
    expect(sent.sections[0].action).toBe('replace')   // default applied
    expect(sent.sections[1].action).toBe('add')
  })

  it('limits action options to allowed_actions', () => {
    render(<ParsePreview proposal={proposal} onApply={() => {}} onCancel={() => {}} />)
    const selects = screen.getAllByRole('combobox')
    // builtin Skills row: only replace/skip
    const opts = within(selects[0]).getAllByRole('option').map(o => o.value)
    expect(opts.sort()).toEqual(['replace', 'skip'])
  })
})
```

> Import `within` from `@testing-library/react`. Match existing select styling conventions (`bg-white text-black`).

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- ParsePreview`
Expected: FAIL (module not found)

- [ ] **Step 3: Write minimal implementation**

`api.js`:

```js
export const proposeParse = (profileId) =>
  _fetch(`/api/config/profiles/${profileId}/parse/propose`, { method: 'POST' })
export const applyParse = (profileId, proposal) =>
  _fetch(`/api/config/profiles/${profileId}/parse/apply`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(proposal),
  })
```

`ParsePreview.jsx`: hold local `actions` + `names` state seeded from `default_action`/`name`; render the two groups; per row an action `<select>` (options = `allowed_actions`) and, for novel rows, a name `<input>`; show a short `preview` summary; Apply builds `{ ...proposal, sections: proposal.sections.map((s,i)=>({ ...s, action: actions[i], name: names[i] })) }` and calls `onApply`. Match the project's Tailwind/markup conventions.

- [ ] **Step 4: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- ParsePreview`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/api.js react-dashboard/src/components/widgets/parse/ParsePreview.jsx react-dashboard/src/components/widgets/parse/ParsePreview.test.jsx
git commit -m "[feat] ParsePreview component + propose/apply API helpers"
```

---

### Task 8: Wire onboarding (`StepResume`) to propose → preview → apply

**Files:**
- Modify: `react-dashboard/src/components/Onboarding/StepResume.jsx`
- Test: `react-dashboard/src/components/Onboarding/StepResume.test.jsx` (create if absent)

**Interfaces:**
- Consumes: `uploadProfileResume`, `proposeParse`, `applyParse`, `ParsePreview`.
- Produces: after upload, `StepResume` calls `proposeParse`, shows `ParsePreview`; on apply, calls `applyParse` then `onFinish`. Cancel returns to the upload step.

- [ ] **Step 1: Write the failing test**

```jsx
// StepResume.test.jsx — mock ../../api (uploadProfileResume, getProfiles, setActiveProfile,
// getProfile, updateProfile, proposeParse, applyParse) and assert that after parsing,
// ParsePreview is shown, and clicking Apply calls applyParse then onFinish.
```

> Mirror the existing onboarding flow (upload → resolve active profile → attach file). Replace the single `parseProfileResume` call with: `proposeParse(profileId)` → render `ParsePreview` → `applyParse(profileId, edited)` → `onFinish`.

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- StepResume`
Expected: FAIL

- [ ] **Step 3: Implement the two-phase flow** (state: `proposal` null → show uploader; set → show `ParsePreview`). Keep the upload + active-profile + attach steps intact.

- [ ] **Step 4: Run test + full frontend suite**

Run (from `react-dashboard/`): `npm run test -- StepResume` then `npm run test` then `npm run build`
Expected: PASS, build clean.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/Onboarding/StepResume.jsx react-dashboard/src/components/Onboarding/StepResume.test.jsx
git commit -m "[feat] Onboarding: propose→preview→apply parse flow"
```

---

### Task 9: Wire existing-profile re-parse to propose → preview → apply

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx` (the existing re-parse trigger that calls `parseProfileResume`)
- Test: `react-dashboard/src/components/widgets/ProfileDetail.reparse.test.jsx`

**Interfaces:**
- Consumes: `proposeParse`, `applyParse`, `ParsePreview`.
- Produces: the re-parse action opens `ParsePreview` (in a modal/section) instead of immediately applying; on apply, calls `applyParse` and refreshes the profile.

- [ ] **Step 1: Write the failing test**

```jsx
// ProfileDetail.reparse.test.jsx — mock api; trigger re-parse; assert ParsePreview shown;
// Apply → applyParse called with the edited proposal; profile refresh invoked.
```

> Find the current re-parse entry point in `ProfileDetail.jsx` (search for `parseProfileResume`). Replace its handler with propose → `ParsePreview` (modal) → apply → refresh. For re-parse, defaults come from the server (matched-with-data → skip), so existing content is preserved unless the user opts in.

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- ProfileDetail.reparse`
Expected: FAIL

- [ ] **Step 3: Implement** the propose→preview→apply wiring in the re-parse handler (reuse `ParsePreview`).

- [ ] **Step 4: Run test + full frontend suite + build**

Run (from `react-dashboard/`): `npm run test` then `npm run build`
Expected: PASS, build clean.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx react-dashboard/src/components/widgets/ProfileDetail.reparse.test.jsx
git commit -m "[feat] Re-parse: propose→preview→apply with add-only-safe defaults"
```

---

## Final verification (after all tasks)

- [ ] Full backend suite: `python -m pytest -q` — all green; legacy `parse` endpoint + existing parse tests unaffected.
- [ ] Full frontend suite (from `react-dashboard/`): `npm run test` and `npm run build` — green.
- [ ] Manual smoke (defer to user): onboard with a résumé containing a Certifications + Languages section → preview shows them as novel (list / taglist) → apply → they render on the profile and the generated résumé; re-parse an existing profile → matched sections default to skip, novel ones offered to add; Skills re-parse with overlap → merge unions.

## Self-Review notes

- **Spec coverage:** open `extra_sections` (T1), prompt v2 + reseed (T2), builder (T3), apply ops incl. merge rules (T4), propose (T5), apply (T6), preview UI (T7), onboarding wiring (T8), re-parse wiring (T9) — every spec section maps to a task.
- **Back-compat:** empty `extra_sections` unchanged; legacy `parse` untouched; built-in via existing flat/preset path; reseed only upgrades stock prompts.
- **Type consistency:** `ExtraSection`/`ParseResponse.extra_sections` (T1) consumed by T3/T5/T6; `ProposedSection`/`ParseProposal` (T5) consumed by T6/T7; `build_section_from_parsed`/`builtin_sections_from_parse`/`find_section`/`add/replace/merge_section` (T3/T4) consumed by T6; `proposeParse`/`applyParse`/`ParsePreview` (T7) consumed by T8/T9.
- **Merge gating** consistent: `allowed_actions` (T5) ↔ `merge_section` raising on non-mergeable shapes (T4) ↔ UI gating (T7).
