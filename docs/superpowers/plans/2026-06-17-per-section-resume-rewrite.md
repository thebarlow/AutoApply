# Per-Section Résumé Rewrite (Sub-project A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate résumés section-by-section, where each section can be kept verbatim or LLM-rewritten (with a section default + per-item override), driven by a per-section config on the profile, plus user-creatable/renamable sections.

**Architecture:** Add a `resume_sections` list to `User.data` and a pure resolver module. Rewrite the résumé generation path in `core/job.py` to iterate that list: verbatim sections copy profile/inline prose (no LLM), rewrite sections make their own LLM call + eval/refine loop using a section-scoped prompt, and the results assemble into a section-aware `ResumeDocument` that the existing ATS gate runs on once. The cover-letter path is untouched.

**Tech Stack:** Python 3.13, Pydantic v2, SQLAlchemy (SQLite/Postgres), FastAPI, pytest; React (Vite) for the profile UI.

## Global Constraints

- Python: type hints, `black` formatting, Google-style docstrings. (global CLAUDE.md)
- Built-in structured data (`work_history`, `education`, `projects`, `skills`) stays the source of truth; sections of built-in kind read from it, never duplicate it. (spec)
- Per-item rewrite cascade: effective rewrite = item override if present, else section `rewrite` default. (spec)
- Verbatim path makes **no** LLM call and incurs **no** debit. (spec)
- Each rewrite LLM call (and refine turns) wrapped in `meter_action(db, profile_id, action="generate_resume:<section_id>", job_key=...)`. (spec)
- Section `id` is stable; `label` is user-editable; `kind` ∈ {profile, experience, education, projects, skills, entries, text}. (spec)
- Absent `resume_sections` ⇒ synthesize today's behavior (profile/experience/skills/projects/education; prose sections rewrite=on, education/skills verbatim). Additive on `User.data`; lose no data. (spec)
- Cover letter unchanged. (spec)
- LLM JSON parsing goes through `core.schemas.parse_llm_json` / `_llm_json_with_retry`. (codebase)

---

## File Structure

- **Create** `core/resume_sections.py` — pure: default list, migration, config resolution, per-item cascade. No DB/LLM.
- **Modify** `core/schemas.py` — add `ResumeSectionGeneration`, `ResumeEntryItem`, `ResumeSection`; extend `ResumeDocument` with `sections`.
- **Modify** `core/document_assembler.py` — render from the ordered section list incl. `entries`/`text`.
- **Modify** `core/document_builder.py` — `build_resume_document` walks sections; add `build_section_document`.
- **Modify** `core/job.py` — rewrite `generate_resume_md` to the per-section pipeline; per-section eval/refine; metering.
- **Modify** `core/intake_pipeline.py` — call the per-section pipeline; final ATS gate on assembly.
- **Modify** `db/seed.py` + `prompts/defaults/` — seed `resume_section` default prompt; per-section prompt key resolution.
- **Modify** `core/document_parser.py` — round-trip section-aware documents.
- **Modify** `web/routers/profile.py` (or the profile router) — section CRUD/config endpoints.
- **Modify** `react-dashboard/src/components/widgets/ProfileDetail.jsx` + `react-dashboard/src/api.js` — section config panel.
- **Tests** under `tests/core/`, `tests/web/`.

Before starting, read: `core/CONTEXT.md`, `web/CONTEXT.md`, `react-dashboard/CONTEXT.md`, and the spec `docs/superpowers/specs/2026-06-17-per-section-resume-control-design.md`.

---

## Task 1: Section config model + resolver (pure)

**Files:**
- Create: `core/resume_sections.py`
- Test: `tests/core/test_resume_sections.py`

**Interfaces:**
- Produces:
  - `DEFAULT_SECTIONS() -> list[dict]` — the synthesized default section list.
  - `get_sections(data: dict) -> list[dict]` — returns `data["resume_sections"]` or `DEFAULT_SECTIONS()`.
  - `item_rewrite_enabled(section: dict, ref: str | int) -> bool` — per-item cascade.
  - `is_rewrite_section(section: dict) -> bool` — `bool(section.get("rewrite"))`.
  - `new_section(kind: str, label: str) -> dict` — builds a custom section with a `u_<hex>` id.

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_resume_sections.py
from core import resume_sections as rs


def test_default_sections_shape():
    secs = rs.DEFAULT_SECTIONS()
    by_id = {s["id"]: s for s in secs}
    assert [s["id"] for s in secs] == ["profile", "experience", "skills", "projects", "education"]
    assert by_id["experience"]["rewrite"] is True
    assert by_id["education"]["rewrite"] is False
    assert by_id["skills"]["rewrite"] is False
    assert all(s["builtin"] for s in secs)


def test_get_sections_falls_back_to_default():
    assert rs.get_sections({}) == rs.DEFAULT_SECTIONS()
    custom = [{"id": "x", "label": "X", "kind": "text", "builtin": False, "rewrite": False}]
    assert rs.get_sections({"resume_sections": custom}) == custom


def test_item_rewrite_cascade():
    sec = {"id": "exp", "rewrite": True, "items": {"2": {"rewrite": False}}}
    assert rs.item_rewrite_enabled(sec, 0) is True       # falls back to section default
    assert rs.item_rewrite_enabled(sec, 2) is False      # explicit override (int key)
    assert rs.item_rewrite_enabled(sec, "2") is False     # string key equivalent
    sec_off = {"id": "edu", "rewrite": False, "items": {}}
    assert rs.item_rewrite_enabled(sec_off, 0) is False


def test_new_section_has_unique_prefixed_id():
    a = rs.new_section("text", "Notes")
    b = rs.new_section("entries", "Certs")
    assert a["id"].startswith("u_") and b["id"].startswith("u_") and a["id"] != b["id"]
    assert a["kind"] == "text" and a["builtin"] is False and a["rewrite"] is False
    assert b["content"] == [] and a["content"] == {"text": ""}
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/core/test_resume_sections.py -v`
Expected: FAIL (`ModuleNotFoundError: core.resume_sections`).

- [ ] **Step 3: Implement `core/resume_sections.py`**

```python
"""Pure helpers for the per-section résumé config stored in ``User.data``.

No DB, no LLM. The section list drives generation order, verbatim-vs-rewrite
behavior, per-item overrides, and (later sub-projects) ordering/format.
"""
from __future__ import annotations

import secrets
from typing import Any

BUILTIN_KINDS = ("profile", "experience", "education", "projects", "skills")
CUSTOM_KINDS = ("entries", "text")


def DEFAULT_SECTIONS() -> list[dict]:
    """Synthesize the section list that reproduces today's behavior."""
    def s(sid: str, label: str, kind: str, rewrite: bool) -> dict:
        return {"id": sid, "label": label, "kind": kind, "builtin": True,
                "rewrite": rewrite, "prompt_ref": None, "format": {}, "items": {}}
    return [
        s("profile", "Profile", "profile", True),
        s("experience", "Experience", "experience", True),
        s("skills", "Skills", "skills", False),
        s("projects", "Projects", "projects", True),
        s("education", "Education", "education", False),
    ]


def get_sections(data: dict) -> list[dict]:
    """Return the configured section list, or the default if unset."""
    secs = (data or {}).get("resume_sections")
    return secs if isinstance(secs, list) and secs else DEFAULT_SECTIONS()


def is_rewrite_section(section: dict) -> bool:
    return bool(section.get("rewrite"))


def item_rewrite_enabled(section: dict, ref: Any) -> bool:
    """Effective rewrite flag for one item: override if present, else section default."""
    items = section.get("items") or {}
    override = items.get(str(ref))
    if isinstance(override, dict) and "rewrite" in override:
        return bool(override["rewrite"])
    return is_rewrite_section(section)


def new_section(kind: str, label: str) -> dict:
    """Build a custom section with a stable unique id."""
    if kind not in CUSTOM_KINDS:
        raise ValueError(f"custom section kind must be one of {CUSTOM_KINDS}")
    content: Any = [] if kind == "entries" else {"text": ""}
    return {"id": f"u_{secrets.token_hex(4)}", "label": label, "kind": kind,
            "builtin": False, "rewrite": False, "prompt_ref": None,
            "format": {}, "items": {}, "content": content}
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `python -m pytest tests/core/test_resume_sections.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add core/resume_sections.py tests/core/test_resume_sections.py
git commit -m "[feat] Pure per-section résumé config resolver"
```

---

## Task 2: Per-section schemas + section-aware ResumeDocument

**Files:**
- Modify: `core/schemas.py` (after `ResumeGeneration`, ~line 215; and `ResumeDocument`, ~line 165)
- Test: `tests/core/test_section_schemas.py`

**Interfaces:**
- Consumes: existing `ResumeExperience`, `ResumeProject`, `ResumeSkillGroup`, `EducationItem`.
- Produces:
  - `ResumeEntryItem(title, subtitle, start, end, description)` — custom `entries` item.
  - `ResumeSection(id, label, kind, profile_summary, experience, projects, skills, education, entries, text)` — one assembled section.
  - `ResumeSectionGeneration(profile_summary, experience: list[ExperienceRef], projects: list[ProjectRef], skills: list[ResumeSkillGroup], entries: list[ResumeEntryItem], text: str)` — LLM output for one rewrite section.
  - `ResumeDocument.sections: list[ResumeSection]` (additive; legacy top-level fields retained for back-compat).

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_section_schemas.py
from core.schemas import (ResumeDocument, ResumeSection, ResumeSectionGeneration,
                          ResumeEntryItem, parse_llm_json)


def test_section_generation_parses_entries_and_text():
    raw = '{"profile_summary":"","entries":[{"title":"AWS SAA","subtitle":"Amazon"}],"text":"hello"}'
    g = parse_llm_json(raw, ResumeSectionGeneration)
    assert g.entries[0].title == "AWS SAA"
    assert g.text == "hello"


def test_resume_document_carries_sections():
    doc = ResumeDocument(sections=[ResumeSection(id="profile", label="Profile",
                                                 kind="profile", profile_summary="hi")])
    assert doc.sections[0].kind == "profile"
    # round-trips through JSON (source of truth is JSON in the documents table)
    assert ResumeDocument.model_validate_json(doc.model_dump_json()).sections[0].id == "profile"


def test_entry_item_defaults():
    e = ResumeEntryItem()
    assert e.title == "" and e.description == ""
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/core/test_section_schemas.py -v`
Expected: FAIL (`ImportError: cannot import name 'ResumeSection'`).

- [ ] **Step 3: Add schemas to `core/schemas.py`**

Insert after `ResumeSkillGroup` (line 163) and before `ResumeDocument`:

```python
class ResumeEntryItem(BaseModel):
    """One item of a custom `entries` section."""

    title: str = ""
    subtitle: str = ""
    start: str = ""
    end: str = ""
    description: str = ""  # Markdown — may be LLM-authored or verbatim


class ResumeSection(BaseModel):
    """One assembled résumé section (built-in or custom)."""

    id: str = ""
    label: str = ""
    kind: str = ""
    profile_summary: str = ""
    experience: list["ResumeExperience"] = Field(default_factory=list)
    projects: list["ResumeProject"] = Field(default_factory=list)
    skills: list["ResumeSkillGroup"] = Field(default_factory=list)
    education: list["EducationItem"] = Field(default_factory=list)
    entries: list["ResumeEntryItem"] = Field(default_factory=list)
    text: str = ""
```

Add to `ResumeDocument` (after `section_order`, line 174):

```python
    sections: list[ResumeSection] = Field(default_factory=list)
```

Add after `ResumeGeneration` (line 214):

```python
class ResumeSectionGeneration(BaseModel):
    """LLM output for rewriting ONE section (prose-only, keyed by ref)."""

    profile_summary: str = ""
    experience: list[ExperienceRef] = Field(default_factory=list)
    projects: list[ProjectRef] = Field(default_factory=list)
    skills: list[ResumeSkillGroup] = Field(default_factory=list)
    entries: list[ResumeEntryItem] = Field(default_factory=list)
    text: str = ""
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `python -m pytest tests/core/test_section_schemas.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add core/schemas.py tests/core/test_section_schemas.py
git commit -m "[feat] Section-aware résumé schemas"
```

---

## Task 3: Section-aware assembler

**Files:**
- Modify: `core/document_assembler.py`
- Test: `tests/core/test_section_assembler.py`

**Interfaces:**
- Consumes: `ResumeDocument.sections` from Task 2.
- Produces: `assemble_resume_markdown(doc)` renders from `doc.sections` (ordered) when present, else falls back to the legacy `CANONICAL_SECTIONS` path. Adds `_render_section(section: ResumeSection) -> str`.

- [ ] **Step 1: Write failing test**

```python
# tests/core/test_section_assembler.py
from core.schemas import (ResumeDocument, ResumeSection, ResumeEntryItem,
                          ResumeExperience)
from core.document_assembler import assemble_resume_markdown


def test_assembles_in_section_list_order_with_custom_kinds():
    doc = ResumeDocument(sections=[
        ResumeSection(id="exp", label="Experience", kind="experience",
                      experience=[ResumeExperience(company="Acme", title="Eng",
                                                   description="Did things")]),
        ResumeSection(id="u1", label="Certifications", kind="entries",
                      entries=[ResumeEntryItem(title="AWS SAA", subtitle="Amazon")]),
        ResumeSection(id="u2", label="Note", kind="text", text="A short note."),
    ])
    md = assemble_resume_markdown(doc)
    assert md.index("## Experience") < md.index("## Certifications") < md.index("## Note")
    assert "AWS SAA" in md and "A short note." in md
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest tests/core/test_section_assembler.py -v`
Expected: FAIL (custom labels/order not rendered by legacy path).

- [ ] **Step 3: Implement section rendering**

Add to `core/document_assembler.py`:

```python
def _render_section(section: "ResumeSection") -> str:
    """Render one section to Markdown using its user label as the H2 heading."""
    label = (section.label or section.kind or "").strip()
    kind = section.kind
    if kind == "profile":
        body = section.profile_summary.strip()
    elif kind == "experience":
        body = _experience_body(section.experience)
    elif kind == "education":
        body = _education_body(section.education)
    elif kind == "projects":
        body = _projects_body(section.projects)
    elif kind == "skills":
        body = _skills_body(section.skills)
    elif kind == "entries":
        body = _entries_body(section.entries)
    elif kind == "text":
        body = section.text.strip()
    else:
        body = ""
    if not body.strip():
        return ""
    return f"## {label}\n\n{body}".rstrip()
```

Refactor the existing `_experience_section`/etc. bodies into `_experience_body(items)`, `_education_body(items)`, `_projects_body(items)`, `_skills_body(groups)` (move the loop bodies; keep the legacy `_*_section(doc)` wrappers calling the new `_*_body` for back-compat). Add:

```python
def _entries_body(entries: list) -> str:
    parts: list[str] = []
    for e in entries:
        dates = " – ".join(filter(None, [e.start, e.end]))
        head = e.title.strip()
        if e.subtitle:
            head = f"{head}, {e.subtitle}".strip(", ")
        if dates:
            head += f" ({dates})"
        block = f"### {head}".rstrip() if head else ""
        if e.description.strip():
            block = (block + "\n\n" if block else "") + e.description.strip()
        if block:
            parts.append(block)
    return "\n\n".join(parts)
```

Update `assemble_resume_markdown`:

```python
def assemble_resume_markdown(doc: ResumeDocument) -> str:
    if doc.sections:
        rendered = [r for s in doc.sections if (r := _render_section(s).strip())]
        return "\n\n".join(rendered) + "\n"
    # legacy fallback (documents generated before sections existed)
    sections = [r for name in CANONICAL_SECTIONS
                if (r := _SECTION_RENDERERS[name](doc).strip())]
    return "\n\n".join(sections) + "\n"
```

- [ ] **Step 4: Run tests, verify pass (incl. legacy)**

Run: `python -m pytest tests/core/test_section_assembler.py tests/ -k assembler -v`
Expected: PASS; existing assembler tests still pass (legacy fallback intact).

- [ ] **Step 5: Commit**

```bash
git add core/document_assembler.py tests/core/test_section_assembler.py
git commit -m "[feat] Section-list-driven résumé assembly"
```

---

## Task 4: Seed the default per-section prompt + prompt resolution

**Files:**
- Create: `prompts/defaults/resume_section.md`
- Modify: `db/seed.py` (add `resume_section` to `PROMPT_TYPE_KEYS`/seed map — read the file first to match the existing pattern)
- Create: `core/section_prompts.py`
- Test: `tests/core/test_section_prompts.py`

**Interfaces:**
- Produces: `resolve_section_prompt(db, profile_id, section: dict) -> str` — returns the section's override prompt (DB key `resume_section:<section_id>`) if present, else the seeded `resume_section` default, with `{section_label}`/`{section_kind}` substituted.

- [ ] **Step 1: Write failing test**

```python
# tests/core/test_section_prompts.py
from core.section_prompts import resolve_section_prompt


def test_falls_back_to_default_and_substitutes_label(seeded_db):
    sec = {"id": "u_x", "label": "Certifications", "kind": "entries", "prompt_ref": None}
    out = resolve_section_prompt(seeded_db, profile_id=1, section=sec)
    assert "Certifications" in out  # {section_label} substituted from the default template
```

(Use the project's existing DB fixture pattern from `tests/core/`; if none, create an in-memory DB seeded via `db.seed`.)

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest tests/core/test_section_prompts.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write the default prompt + resolver**

`prompts/defaults/resume_section.md` (a section-scoped rewrite prompt; mirror tone/format of `prompts/defaults/resume.md` but scoped to one section):

```markdown
You are tailoring the "{section_label}" section of a résumé to a specific job.

Rewrite ONLY the prose for the items provided, keyed by their integer `ref`.
Do not invent items, titles, dates, companies, or URLs — those are fixed.
Return JSON matching the ResumeSectionGeneration schema for kind "{section_kind}".

Job posting:
{job}

Candidate profile:
{user}

Items to rewrite (keyed by ref):
{section_items}
```

`core/section_prompts.py`:

```python
"""Resolve the prompt used to rewrite one résumé section."""
from __future__ import annotations

from db.database import Prompt, Session  # match actual prompt model import in db/


def resolve_section_prompt(db: Session, profile_id: int, section: dict) -> str:
    key = section.get("prompt_ref") or "resume_section"
    row = (db.query(Prompt)
             .filter_by(profile_id=profile_id, type_key=key)
             .first())
    if row is None:
        row = db.query(Prompt).filter_by(type_key="resume_section").first()
    content = (row.content if row else "") or ""
    return (content
            .replace("{section_label}", section.get("label", ""))
            .replace("{section_kind}", section.get("kind", "")))
```

> NOTE: before implementing, read `db/seed.py` and the prompts router/model to use the real `Prompt` model fields (`type_key`/`content`/`profile_id` names may differ) and the established seeding mechanism. Adjust the query accordingly.

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/core/test_section_prompts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add prompts/defaults/resume_section.md db/seed.py core/section_prompts.py tests/core/test_section_prompts.py
git commit -m "[feat] Seed + resolve per-section rewrite prompt"
```

---

## Task 5: Per-section builder (one section → ResumeSection)

**Files:**
- Modify: `core/document_builder.py`
- Test: `tests/core/test_section_builder.py`

**Interfaces:**
- Consumes: `resume_sections.item_rewrite_enabled`, `ResumeSectionGeneration`, profile structured data.
- Produces: `build_section(user, section: dict, generation: ResumeSectionGeneration | None, db) -> ResumeSection`. When `generation is None` (verbatim), prose comes from the profile/inline content; when present, rewrite-enabled items take LLM prose and others stay verbatim.

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_section_builder.py
from core.document_builder import build_section
from core.schemas import ResumeSectionGeneration, ExperienceRef


class _U:  # minimal profile stand-in
    work_history = [type("W", (), {"company": "Acme", "title": "Eng", "start": "2020",
                                   "end": "2022", "summary": "verbatim prose"})()]
    education = []; projects = []; skills = []
    first_name = "A"; last_name = "B"; hero = ""


def test_verbatim_section_uses_profile_prose(seeded_db):
    sec = {"id": "exp", "label": "Experience", "kind": "experience", "rewrite": False, "items": {}}
    out = build_section(_U(), sec, None, seeded_db)
    assert out.experience[0].description == "verbatim prose"
    assert out.experience[0].title == "Eng"  # structural fact preserved


def test_rewrite_only_enabled_items(seeded_db):
    sec = {"id": "exp", "label": "Experience", "kind": "experience", "rewrite": True,
           "items": {"0": {"rewrite": True}}}
    gen = ResumeSectionGeneration(experience=[ExperienceRef(ref=0, description="LLM prose")])
    out = build_section(_U(), sec, gen, seeded_db)
    assert out.experience[0].description == "LLM prose"
```

- [ ] **Step 2: Run tests, verify fail**

Run: `python -m pytest tests/core/test_section_builder.py -v`
Expected: FAIL (`ImportError: build_section`).

- [ ] **Step 3: Implement `build_section`**

Add to `core/document_builder.py` a `build_section` that switches on `section["kind"]`:
- `experience`: for each `w` in `user.work_history`, structural fields from `w`; description = LLM prose by ref (from `generation.experience`) **iff** `item_rewrite_enabled(section, i)` and a ref matched, else `w.summary`.
- `projects`: analogous using `user.projects` + `generation.projects`; verbatim description = project's stored description.
- `profile`: `profile_summary` = `generation.profile_summary` if rewrite else `user.hero`.
- `skills`: `generation.skills` if rewrite else group all `user.skills` under a single "Skills" group.
- `education`: always verbatim from `user.education` (use existing `_snapshot_education`).
- `entries`: from `section["content"]`; each item's description = LLM (`generation.entries[i]`) iff enabled, else the inline description.
- `text`: `generation.text` if rewrite else `section["content"]["text"]`.

Return a `ResumeSection(id=section["id"], label=section["label"], kind=section["kind"], …)` populated for that kind only. Show the experience branch fully (mirror `build_resume_document` lines 70–86); apply the same ref/verbatim logic to projects/entries.

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/core/test_section_builder.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add core/document_builder.py tests/core/test_section_builder.py
git commit -m "[feat] Build a single résumé section (verbatim or rewritten)"
```

---

## Task 6: Per-section generation pipeline + metering

**Files:**
- Modify: `core/job.py` (`generate_resume_md`, ~lines 856–887; `build_resume_prompt` for section context)
- Test: `tests/core/test_section_generation.py`

**Interfaces:**
- Consumes: Tasks 1, 4, 5; `core.metering.meter_action`; `_llm_json_with_retry`.
- Produces: rewritten `generate_resume_md(self, user, client, model, db)` (drop the single `prompt_content` arg — callers updated in Task 8) that loops sections, calls the LLM only for rewrite sections, meters each call, assembles a section-aware `ResumeDocument`, persists it, and writes the `.md`.

- [ ] **Step 1: Write failing test (no LLM call for verbatim; one call per rewrite section)**

```python
# tests/core/test_section_generation.py
# Patch the section LLM call to count invocations and assert verbatim sections
# never call it, while each rewrite-enabled section calls exactly once.
# Use a profile with resume_sections = [experience(rewrite True), education(rewrite False)]
# and monkeypatch core.job._llm_json_with_retry to record calls + return a stub
# ResumeSectionGeneration. Assert: 1 call total; assembled doc has both sections;
# education description verbatim; a debit ledger row only for the experience action.
```

(Write this concretely against the project's existing job/db test fixtures — see `tests/core/test_metering.py` for the `_db_with_account` pattern and `tests/core/` job tests for building a `Job`.)

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest tests/core/test_section_generation.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the per-section loop**

Rewrite `generate_resume_md` to:

```python
def generate_resume_md(self, user, client, model, db):
    from core import resume_sections as rs
    from core.section_prompts import resolve_section_prompt
    from core.document_builder import build_section
    from core.metering import meter_action
    from core.schemas import ResumeSectionGeneration, ResumeDocument

    built: list = []
    for section in rs.get_sections(user.data if isinstance(user.data, dict) else {}):
        if not rs.is_rewrite_section(section) and not any(
            rs.item_rewrite_enabled(section, k) for k in (section.get("items") or {})
        ):
            built.append(build_section(user, section, None, db))
            continue
        prompt = self.build_section_prompt(user, section, resolve_section_prompt(db, self.profile_id, section), db)
        with meter_action(db, self.profile_id, action=f"generate_resume:{section['id']}", job_key=self.job_key):
            generation = _llm_json_with_retry(
                prompt, client, model, ResumeSectionGeneration, max_tokens=16384,
                empty_msg="Section generation returned empty content",
            )
        built.append(build_section(user, section, generation, db))

    header = build_resume_header(user, db)
    education = next((s.education for s in built if s.kind == "education"), [])
    doc = ResumeDocument(header=header, sections=built, education=education)
    Document.upsert(db, self.job_key, "resume", doc.model_dump_json(), profile_id=self.profile_id)
    self.write_resume_markdown(doc)
```

Add `build_section_prompt(self, user, section, prompt_content, db)` mirroring `build_resume_prompt` (read its current body first) but substituting `{section_items}` with the section's rewrite-enabled items rendered as `[ref] title …`.

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/core/test_section_generation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/job.py tests/core/test_section_generation.py
git commit -m "[feat] Per-section résumé generation with per-section metering"
```

---

## Task 7: Per-section eval/refine + final ATS gate wiring

**Files:**
- Modify: `core/intake_pipeline.py` (the resume generate→eval→refine→ats orchestration — read it first)
- Modify: `core/job.py` (`_refine_doc_md`/`refine_resume_md` to operate per section)
- Test: `tests/core/test_section_refine.py`, extend `tests/web/test_metered_endpoints.py`

**Interfaces:**
- Consumes: Task 6 output; existing `evaluate_resume_md`, `_refine_doc_md`, `run_ats_check`.
- Produces: per rewrite-section eval/refine loop (reuse `resume_refine_max_turns`/`resume_refine_pass_score`), then one `run_ats_check` on the assembled document.

- [ ] **Step 1: Write failing test** — assert a low-scoring section triggers up to `max_turns` refine calls scoped to that section, and ATS runs once after assembly. (Monkeypatch eval to return a failing then passing score.)

- [ ] **Step 2: Run, verify fail.** `python -m pytest tests/core/test_section_refine.py -v`

- [ ] **Step 3: Implement.** In the orchestration, replace the whole-résumé eval/refine with a per-section loop calling section-scoped eval + `_refine_doc_md` (extended to accept a `section_id` and patch only that section of the stored `ResumeDocument.sections`). Keep `run_ats_check` once on the final assembly. Preserve the "keep best" behavior per section.

- [ ] **Step 4: Run, verify pass.** `python -m pytest tests/core/test_section_refine.py tests/web/test_metered_endpoints.py -v`

- [ ] **Step 5: Commit**

```bash
git add core/intake_pipeline.py core/job.py tests/core/test_section_refine.py tests/web/test_metered_endpoints.py
git commit -m "[feat] Per-section eval/refine + final ATS gate"
```

---

## Task 8: Update generation callers + document_parser round-trip

**Files:**
- Modify: callers of `generate_resume_md` (grep: `generate_resume_md(`) — web routers / intake pipeline — to drop `prompt_content` and pass `(user, client, model, db)`.
- Modify: `core/document_parser.py` to parse a section-aware document (and backfill `sections` from legacy top-level fields when missing).
- Test: `tests/core/test_document_parser.py` (extend)

- [ ] **Step 1: Write failing test** — parsing a legacy `ResumeDocument` (no `sections`) yields `sections` populated from `experience`/`education`/etc.; a section-aware doc round-trips unchanged.

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** the parser backfill + caller signature updates. Run `grep -rn "generate_resume_md(" --include=*.py .` and fix each call site.

- [ ] **Step 4: Run full core+web suite.** `python -m pytest tests/ -q`
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add core/document_parser.py web tests/core/test_document_parser.py
git commit -m "[refactor] Section-aware document parser + caller updates"
```

---

## Task 9: Section config API

**Files:**
- Modify: the profile router (grep: `resume_sections`/profile update endpoint in `web/routers/`)
- Test: `tests/web/test_resume_sections_api.py`

**Interfaces:**
- Produces:
  - `GET /api/profile/sections` → `{sections: [...]}` (from `resume_sections.get_sections`).
  - `PUT /api/profile/sections` body `{sections: [...]}` → validates kinds/ids, persists to `User.data["resume_sections"]`, returns the saved list.

- [ ] **Step 1: Write failing tests** — GET returns defaults when unset; PUT persists and round-trips; PUT rejects an unknown `kind` with 400; tenant scoping respected (uses `current_profile_id` seam).

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** the two endpoints; reuse the existing profile-update/tenancy pattern in the router (read it first). Validate each section has `id`, `label`, `kind ∈ BUILTIN_KINDS ∪ CUSTOM_KINDS`.

- [ ] **Step 4: Run, verify pass.** `python -m pytest tests/web/test_resume_sections_api.py -v`

- [ ] **Step 5: Commit**

```bash
git add web tests/web/test_resume_sections_api.py
git commit -m "[feat] Résumé section config API"
```

---

## Task 10: Profile UI — section config panel

**Files:**
- Modify: `react-dashboard/src/api.js` (add `getResumeSections`, `saveResumeSections`)
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`
- Verify: `cd react-dashboard && npm run build`

**Interfaces:**
- Consumes: Task 9 endpoints.

- [ ] **Step 1: Add API helpers** in `react-dashboard/src/api.js`:

```javascript
export const getResumeSections = () => _fetch('/api/profile/sections').then(r => r.json())
export const saveResumeSections = (sections) =>
  _fetch('/api/profile/sections', { method: 'PUT', body: JSON.stringify({ sections }) }).then(r => r.json())
```

(Match the file's existing `_fetch` wrapper and export style.)

- [ ] **Step 2: Section config panel.** In each profile section's expanded view, add controls bound to the section config: a "Rewrite this section" toggle, per-item "rewrite" checkboxes (for `experience`/`projects`/`entries`), a prompt picker/editor (reuse `PromptsSection`), and section add/rename/delete + custom-kind picker. Persist via `saveResumeSections` on change (optimistic, revert on error). Stub the format/order controls with a disabled "coming soon" affordance (Sub-projects B/C).

- [ ] **Step 3: Build to verify.**

Run: `cd react-dashboard && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Manual smoke (optional).** Use the project's `run`/`verify` skill to confirm toggling rewrite off for Education and generating a résumé produces verbatim education and a debit only for rewrite sections.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/api.js react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Per-section rewrite/prompt config UI in profile"
```

---

## Self-Review

**Spec coverage:** per-section config model (Task 1), schemas/section-aware doc (Task 2), assembly incl. custom kinds (Task 3), per-section prompts (Task 4), verbatim-vs-rewrite + per-item cascade builder (Task 5), per-section LLM calls + metering (Task 6), per-section eval/refine + final ATS gate (Task 7), parser/callers (Task 8), API (Task 9), UI incl. add/rename/delete/custom-kind (Task 10). Custom `entries`/`text` kinds covered in Tasks 1/2/3/5. All spec sub-project-A requirements mapped.

**Deferred to B/C (not this plan):** field-visibility/order controls and visual layout/CSS — stubbed in Task 10.

**Open implementation reads (flagged inline, not placeholders):** exact `Prompt` model field names (Task 4), `build_resume_prompt` body (Task 6), `intake_pipeline` orchestration (Task 7), profile router pattern (Task 9), `_fetch` style (Task 10). Each task says to read the real file first and match the pattern.

**Type consistency:** `ResumeSection`/`ResumeSectionGeneration`/`ResumeEntryItem`/`build_section`/`resolve_section_prompt`/`get_sections`/`item_rewrite_enabled` are used with consistent signatures across Tasks 1–10.
