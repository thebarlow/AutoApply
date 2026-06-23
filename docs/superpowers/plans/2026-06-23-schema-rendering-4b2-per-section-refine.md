# 4B-2 Per-Section Résumé Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the interim "re-author every section" auto-refine for tree-v1 résumés with a per-section engine: one sectioned-eval call scores each regenerable section, only sub-threshold sections are regenerated (with their own issues as critique), and the loop stops when all regenerable sections meet the threshold.

**Architecture:** A new sectioned-eval prompt + `SectionEvalResponse` schema feed `Job.evaluate_resume_sections`, which scores only regenerable sections (unlocked `llm_output` fields) keyed by section name. `generate_resume_by_section` gains optional `only_sections`/`critiques` params so a subset can be regenerated with targeted critique. A new orchestrator `_run_resume_section_refinement` in `web/intake_pipeline.py` carries authored values across turns (`authored_values_from_tree`), regenerates only failing sections, re-persists tree-v1, and restores the best-by-min turn. Cover letters and legacy `ResumeDocument` rows keep the existing whole-document loop unchanged; user feedback-refine (`_refine_doc_md`) is untouched (deferred to 4D).

**Tech Stack:** Python 3, Pydantic v2, pytest, SQLite/SQLAlchemy, DB-backed prompts.

## Global Constraints

- **Local `main` only** — do NOT push `main` (part of the unfinished #4–#6/#5 swap).
- **Threshold** is the existing single knob `resume_refine_pass_score` (default 0.80) for every section — no new config.
- **Stop rule:** loop stops when every regenerable section's score ≥ threshold, or `max_turns` is reached.
- **Overall score per turn = the MIN of the regenerable sections' scores;** best-turn restore picks the highest min.
- **Section identity = `SectionNode.name`** (the `## Heading` the renderer emits, unique within a résumé). Map eval results back to tree sections by name; drop any returned name not in the current regenerable set.
- **Regenerable section** = a section with ≥1 unlocked `llm_output` field (`core.section_generator._outputable`). Only these are scored/regenerated.
- **Untouched:** cover letters, legacy `ResumeDocument` résumé rows (whole-document loop), `resume_eval` prompt, `EvalResponse`, and `_refine_doc_md` (4B-1 interim, used by feedback-refine until 4D).
- **New prompt key** is exactly `resume_eval_sectioned`. Discriminator/storage stays `schema:"tree-v1"`.
- `generate_resume_by_section`'s new params are **optional with behavior-preserving defaults** so 4B-1 call sites are unaffected.

---

### Task 1: `SectionEvalResponse` / `SectionScore` schemas

**Files:**
- Modify: `core/schemas.py` (add next to `EvalResponse`, ~line 46)
- Test: `tests/core/test_schemas_section_eval.py` (create)

**Interfaces:**
- Consumes: existing `Issue` (`core/schemas.py:39`), the `[0,1]` clamp pattern used by `EvalResponse.score`.
- Produces: `SectionScore{section: str, score: float, issues: list[Issue]}`, `SectionEvalResponse{sections: list[SectionScore]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_schemas_section_eval.py
from core.schemas import SectionEvalResponse, parse_llm_json


def test_parses_per_section_scores():
    raw = (
        '{"sections": [{"section": "Summary", "score": 0.9, "issues": []},'
        '{"section": "Experience", "score": 0.4, '
        '"issues": [{"category": "tailoring", "description": "too generic"}]}]}'
    )
    resp = parse_llm_json(raw, SectionEvalResponse)
    assert len(resp.sections) == 2
    assert resp.sections[0].section == "Summary"
    assert resp.sections[1].score == 0.4
    assert resp.sections[1].issues[0].category == "tailoring"


def test_score_clamped_to_unit_interval():
    resp = parse_llm_json(
        '{"sections": [{"section": "S", "score": 1.7, "issues": []}]}',
        SectionEvalResponse,
    )
    assert resp.sections[0].score == 1.0


def test_empty_sections_default():
    resp = parse_llm_json("{}", SectionEvalResponse)
    assert resp.sections == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_schemas_section_eval.py -v`
Expected: FAIL — `ImportError: cannot import name 'SectionEvalResponse'`

- [ ] **Step 3: Write minimal implementation**

In `core/schemas.py`, after `EvalResponse` (and reusing the same `_clamp_unit`/validator
pattern already used there — match the existing code exactly; the snippet below assumes the
module already defines `Issue` and a unit-clamp `@field_validator` style):

```python
class SectionScore(BaseModel):
    """One section's evaluation: name (matches a tree SectionNode.name), score, issues."""

    section: str = ""
    score: float = 0.0
    issues: list[Issue] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def _clamp_score(cls, v: float) -> float:
        return _clamp_unit(v)  # use the SAME helper/validator EvalResponse.score uses


class SectionEvalResponse(BaseModel):
    """Per-section résumé evaluation: one SectionScore per scored section."""

    sections: list[SectionScore] = Field(default_factory=list)
```

If `EvalResponse` clamps inline rather than via a shared `_clamp_unit`, mirror that exact
mechanism instead of inventing a new helper.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_schemas_section_eval.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/schemas.py tests/core/test_schemas_section_eval.py
git commit -m "[feat] Add SectionEvalResponse/SectionScore schemas for per-section eval"
```

---

### Task 2: `resume_eval_sectioned` prompt key + default

**Files:**
- Create: `prompts/defaults/resume_eval_sectioned.md`
- Modify: `db/seed.py:13-16` (`PROMPT_TYPE_KEYS`), `core/user.py:25-35` (`_PROMPT_LABELS`)
- Test: `tests/db/test_sectioned_prompt_seed.py` (create)

**Interfaces:**
- Consumes: `db.seed.seed_prompt_defaults` (seeds `prompt_defaults` from `prompts/defaults/<key>.md` for missing rows), `User.resolve_prompt` (auto-repairs a missing per-profile row from the default).
- Produces: prompt key `"resume_eval_sectioned"` resolvable via `user.resolve_prompt("resume_eval_sectioned")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_sectioned_prompt_seed.py
from db.seed import PROMPT_TYPE_KEYS


def test_key_registered():
    assert "resume_eval_sectioned" in PROMPT_TYPE_KEYS


def test_default_file_seeds_and_resolves(db_session):
    """seed_prompt_defaults loads the .md; resolve_prompt returns it for a fresh profile."""
    from db.database import User
    from db.seed import seed_prompt_defaults
    from core.user import User as UserEntity  # adapt to the real User entity import

    seed_prompt_defaults(db_session)
    db_session.add(User(id=1, name="T", data="{}"))
    db_session.commit()
    u = UserEntity.load(db_session, profile_id=1)
    content = u.resolve_prompt("resume_eval_sectioned")
    assert "{current_document}" in content
    assert "{sections_to_score}" in content
    assert '"sections"' in content
```

Adapt fixture/import names to those used by existing `tests/db/*` and `tests/core/test_job.py`
(`db_session`, the `User` ORM model vs the `core.user.User` entity). Keep the assertions
identical: the default contains `{current_document}`, `{sections_to_score}`, and a `"sections"`
JSON key.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/db/test_sectioned_prompt_seed.py -v`
Expected: FAIL — key not in `PROMPT_TYPE_KEYS` / default file missing.

- [ ] **Step 3: Write minimal implementation**

Create `prompts/defaults/resume_eval_sectioned.md` (mirror `resume_eval.md`'s context/rubric,
sectioned output):

```markdown
You are a resume quality evaluator. Score EACH listed section of the resume below against the job requirements. Return ONLY a JSON object — no prose, no code fences.

# Job Requirements
Required Skills: {job.ext_required_skills}
Preferred Skills: {job.ext_preferred_skills}
Tech Stack: {job.ext_tech_stack}

# Candidate Credentials (for hallucination detection)
Skills: {user.skills}
Degrees: {user.education_degrees}

# Resume Under Review
{current_document}

# Sections to score (use these exact names)
{sections_to_score}

# Output schema
{"sections": [{"section": "<exact name>", "score": 0.0, "issues": [{"category": "keyword_coverage|hallucination|overclaiming|structure|tailoring", "description": "..."}]}]}

Rules:
- Return exactly one object per section name listed above, using the name verbatim.
- score: 0.0 (poor) to 1.0 (excellent), calibrated per section — 0.8 means genuinely strong.
- issues: concrete, actionable, max 15 words each; empty array if none; max 4 per section.
- keyword_coverage: a skill in BOTH the candidate's Skills AND the job's Required/Preferred skills MUST appear where relevant (treat synonyms, e.g. NLP = Natural Language Processing, as covered). Never flag skills the candidate does not have.
- hallucination: flag hard tools/technologies/credentials NOT in the candidate's lists. Never soft skills.
- overclaiming: phrasing implying a title/seniority/scope/outcome the candidate did not hold.
- tailoring: generic content not reflecting this specific job/company.
- structure: bullets over 120 chars or malformed content within the section.
```

In `db/seed.py`, add the key to `PROMPT_TYPE_KEYS`:

```python
PROMPT_TYPE_KEYS = (
    "scoring", "resume", "cover", "extraction", "resume_parse",
    "resume_eval", "resume_refine", "cover_eval", "cover_refine",
    "resume_eval_sectioned",
)
```

In `core/user.py`, add the label:

```python
    "resume_eval": "Resume Evaluator",
    "resume_eval_sectioned": "Resume Section Evaluator",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/db/test_sectioned_prompt_seed.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add prompts/defaults/resume_eval_sectioned.md db/seed.py core/user.py tests/db/test_sectioned_prompt_seed.py
git commit -m "[feat] Register resume_eval_sectioned prompt key + default"
```

---

### Task 3: `authored_values_from_tree` carry-forward helper

**Files:**
- Modify: `core/document_tree.py` (add helper)
- Test: `tests/core/test_document_tree.py` (add cases)

**Interfaces:**
- Consumes: `core.profile_tree` node types (`RootNode`, `SectionNode`, `ListNode`, `GroupNode`, `FieldNode`).
- Produces: `authored_values_from_tree(root: RootNode) -> dict[str, Value]` — `field_id → value` for every `llm_output` field anywhere in the tree.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/core/test_document_tree.py
from core.document_tree import authored_values_from_tree
from core.profile_tree import FieldNode, GroupNode, ListNode, RootNode, SectionNode


def test_authored_values_collects_only_llm_output_fields():
    root = RootNode(children=[
        SectionNode(name="Summary", role="summary", order=0, children=[
            GroupNode(name="g", children=[
                FieldNode(name="Hero", key="hero", kind="markdown", value="S", llm_output=True),
                FieldNode(name="Email", key="email", kind="text", value="e", llm_output=False),
            ]),
        ]),
        SectionNode(name="Experience", role="experience", order=1, children=[
            ListNode(name="X", item_template=GroupNode(name="t", children=[
                FieldNode(name="Summary", key="summary", kind="markdown", value="", llm_output=True),
            ]), children=[
                GroupNode(name="e", children=[
                    FieldNode(name="Summary", key="summary", kind="markdown",
                              value="did things", llm_output=True),
                ]),
            ]),
        ]),
    ])
    out = authored_values_from_tree(root)
    hero_id = root.children[0].children[0].children[0].id
    exp_id = root.children[1].children[0].children[0].children[0].id
    assert out == {hero_id: "S", exp_id: "did things"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_document_tree.py::test_authored_values_collects_only_llm_output_fields -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Write minimal implementation**

In `core/document_tree.py`:

```python
def authored_values_from_tree(root: RootNode) -> dict[str, Value]:
    """``field_id -> value`` for every ``llm_output`` field anywhere in the tree.

    Seeds the cumulative authored map so per-section refinement can regenerate
    only failing sections while passing sections keep their current values.
    """
    out: dict[str, Value] = {}

    def _visit_group(group: GroupNode) -> None:
        for f in group.children:
            if f.llm_output:
                out[f.id] = f.value

    for s in root.children:
        child = s.children[0] if s.children else None
        if isinstance(child, ListNode):
            for entry in child.children:
                _visit_group(entry)
        elif isinstance(child, GroupNode):
            _visit_group(child)
        elif isinstance(child, FieldNode):
            if child.llm_output:
                out[child.id] = child.value
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_document_tree.py -v`
Expected: PASS (all existing + new)

- [ ] **Step 5: Commit**

```bash
git add core/document_tree.py tests/core/test_document_tree.py
git commit -m "[feat] authored_values_from_tree: collect llm_output field values for carry-forward"
```

---

### Task 4: `generate_resume_by_section` — `only_sections` + `critiques`

**Files:**
- Modify: `core/section_generator.py` (`generate_resume_by_section`, `_build_scalar_prompt`, `_build_list_prompt`)
- Test: `tests/core/test_section_generator_filter.py` (create)

**Interfaces:**
- Consumes: existing `generate_resume_by_section` internals.
- Produces: `generate_resume_by_section(root, job_ctx, client, model, resolve=None, only_sections: set[str] | None = None, critiques: dict[str, list[dict]] | None = None)`. When `only_sections` is set, sections whose `name` is not in it are skipped. When `critiques[section.name]` exists, a `FIX THESE ISSUES:` block is appended to that section's prompt.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_section_generator_filter.py
from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode
from core.section_generator import generate_resume_by_section


class _FakeResp:
    def __init__(self, fields): self.fields = fields; self.entries = {}


def _root():
    return RootNode(children=[
        SectionNode(name="Summary", role="summary", order=0, children=[
            GroupNode(name="g", children=[
                FieldNode(name="Hero", key="hero", kind="markdown", value="", llm_output=True),
            ]),
        ]),
        SectionNode(name="Skills", role="skills", order=1, children=[
            GroupNode(name="g2", children=[
                FieldNode(name="Skills", key="skills", kind="taglist", value=[], llm_output=True),
            ]),
        ]),
    ])


def test_only_sections_limits_regeneration(monkeypatch):
    root = _root()
    seen_prompts = []

    def fake_call(prompt, client, model, schema, **kw):
        seen_prompts.append(prompt)
        return _FakeResp({"hero": "new", "skills": ["x"]})

    monkeypatch.setattr("core.job._llm_json_with_retry", fake_call)
    out = generate_resume_by_section(root, "ctx", object(), "m", only_sections={"Summary"})

    hero_id = root.children[0].children[0].children[0].id
    skills_id = root.children[1].children[0].children[0].id
    assert hero_id in out          # Summary regenerated
    assert skills_id not in out    # Skills skipped
    assert len(seen_prompts) == 1  # only one section called


def test_critique_block_injected(monkeypatch):
    root = _root()
    seen = []

    def fake_call(prompt, client, model, schema, **kw):
        seen.append(prompt); return _FakeResp({"hero": "new"})

    monkeypatch.setattr("core.job._llm_json_with_retry", fake_call)
    generate_resume_by_section(
        root, "ctx", object(), "m",
        only_sections={"Summary"},
        critiques={"Summary": [{"category": "tailoring", "description": "too generic"}]},
    )
    assert "FIX THESE ISSUES" in seen[0]
    assert "too generic" in seen[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_section_generator_filter.py -v`
Expected: FAIL — `generate_resume_by_section() got an unexpected keyword argument 'only_sections'`.

- [ ] **Step 3: Write minimal implementation**

In `core/section_generator.py`:

1. Add a critique helper:

```python
def _critique_block(critique: "list[dict] | None") -> str:
    """A 'fix these issues' block for a section prompt, or '' if no critique."""
    if not critique:
        return ""
    lines = "\n".join(f"- {i.get('description', '')}".rstrip() for i in critique)
    return f"\nFIX THESE ISSUES from the previous draft:\n{lines}\n"
```

2. Thread an optional `critique` into the two prompt builders — append `_critique_block(critique)`
   just before the final `Return JSON:` instruction in both `_build_scalar_prompt` and
   `_build_list_prompt` (add a `critique=None` param to each):

```python
def _build_scalar_prompt(section, group, job_ctx, critique=None):
    ...
    return (
        f"{guide}You are tailoring the résumé section '{section.name}' to a job.\n\n"
        f"JOB:\n{job_ctx}\n\n"
        f"EXISTING SECTION DATA (anchors — do not change these):\n{ctx}\n\n"
        f"Write tailored content for these fields:\n{specs}\n"
        f"{_critique_block(critique)}\n"
        'Return JSON: {"fields": {"<field_key>": "<value>"}} containing exactly '
        "the field keys above."
    )
```

(Do the analogous append in `_build_list_prompt` before its `Return JSON:` line.)

3. In `generate_resume_by_section`, add the params and the filter + critique lookup:

```python
def generate_resume_by_section(
    root, job_ctx, client, model, resolve=None,
    only_sections=None, critiques=None,
):
    ...
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
            ...
            prompt = _build_list_prompt(section, child, job_ctx, critique=section_critique)
        elif isinstance(child, GroupNode):
            ...
            prompt = _build_scalar_prompt(section, child, job_ctx, critique=section_critique)
        elif isinstance(child, FieldNode):
            ...
            prompt = _build_scalar_prompt(
                section, GroupNode(name=section.name, children=[child]), job_ctx,
                critique=section_critique,
            )
        ...
```

Keep the rest of the function (LLM call, result mapping) exactly as-is.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_section_generator_filter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/section_generator.py tests/core/test_section_generator_filter.py
git commit -m "[feat] generate_resume_by_section: only_sections filter + per-section critique"
```

---

### Task 5: `Job.evaluate_resume_sections`

**Files:**
- Modify: `core/job.py` (add method near `_evaluate_doc_md`, ~line 500)
- Test: `tests/core/test_job_section_eval.py` (create)

**Interfaces:**
- Consumes: stored tree-v1 résumé row (`Document.fetch` + `deserialize_document_tree`), `core.section_generator._outputable`, the rendered `.md` body (same source as `_evaluate_doc_md`), `parse_llm_json(..., SectionEvalResponse)`, `_apply_template`.
- Produces: `evaluate_resume_sections(self, eval_prompt: str, user, client, model, db) -> dict[str, dict]` → `{section_name: {"score": float, "issues": list[dict]}}` for regenerable sections only; returns `{}` if there are no regenerable sections.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_job_section_eval.py  (copy the in-memory db_session fixture from tests/core/test_job.py)
import json

from core.job import Job, _OUTPUTS_DIR
from core.resume_document_io import serialize_document_tree
from core.document_tree import build_resume_document_tree
from db.database import Document, User


def _seed(db_session):
    data = {"first_name": "Jane", "last_name": "Doe", "email": "j@x.co", "skills": ["py"]}
    db_session.add(User(name="Jane Doe", data=json.dumps(data)))
    db_session.commit()
    from core.user import User as UserEntity
    return UserEntity.load(db_session)


def test_evaluate_resume_sections_maps_by_name_and_filters(db_session, monkeypatch):
    user = _seed(db_session)
    root = user.profile_tree_root()
    tree = build_resume_document_tree(root, {})
    job = Job(job_key="ev1", title="t", company="c", profile_id=1)
    db_session.add(job); db_session.commit()
    Document.upsert(db_session, "ev1", "resume", serialize_document_tree(tree), profile_id=1)
    (_OUTPUTS_DIR).mkdir(parents=True, exist_ok=True)
    (_OUTPUTS_DIR / "ev1_resume.md").write_text("# Jane Doe\n\n## Summary\n\nx\n", encoding="utf-8")

    # LLM returns a score for a regenerable section + a bogus non-regenerable one.
    def fake_call(prompt, client, model, **kw):
        return ('{"sections": [{"section": "Summary", "score": 0.5, "issues": []},'
                '{"section": "Header", "score": 0.1, "issues": []}]}')
    monkeypatch.setattr("core.job.call_llm", fake_call)

    out = job.evaluate_resume_sections("{current_document}\n{sections_to_score}",
                                       user, object(), "m", db_session)
    assert "Summary" in out
    assert out["Summary"]["score"] == 0.5
    assert "Header" not in out   # non-regenerable name dropped
```

Adapt fixtures/imports to the real ones (`db_session`, `User` ORM vs `core.user.User`).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_job_section_eval.py -v`
Expected: FAIL — `AttributeError: 'Job' object has no attribute 'evaluate_resume_sections'`.

- [ ] **Step 3: Write minimal implementation**

In `core/job.py` add (imports `SectionEvalResponse` from `core.schemas`,
`deserialize_document_tree` already imported, `_outputable` from `core.section_generator`):

```python
    def _regenerable_section_names(self, db: Session) -> list[str]:
        """Names of stored tree-v1 sections that have an unlocked llm_output field."""
        from core.section_generator import _outputable
        from core.profile_tree import GroupNode, ListNode, FieldNode
        row = Document.fetch(db, self.job_key, "resume", profile_id=self.profile_id)
        if row is None or not is_tree_v1(row.structured_json):
            return []
        root = deserialize_document_tree(row.structured_json)
        names: list[str] = []
        for s in root.children:
            if not s.visible or s.locked:
                continue
            child = s.children[0] if s.children else None
            groups = (child.children if isinstance(child, ListNode)
                      else [child] if isinstance(child, GroupNode) else [])
            has = any(
                _outputable(f) for g in groups for f in g.children
            ) if groups else (isinstance(child, FieldNode) and _outputable(child))
            if has:
                names.append(s.name)
        return names

    def evaluate_resume_sections(
        self, eval_prompt: str, user: Any, client: Any, model: str, db: Session,
    ) -> dict:
        """Per-section résumé evaluation. Returns {section_name: {score, issues}} for
        regenerable sections only (others are dropped)."""
        from core.schemas import SectionEvalResponse
        names = self._regenerable_section_names(db)
        if not names:
            return {}
        md_path = _OUTPUTS_DIR / f"{self.job_key}_resume.md"
        body = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        prompt = eval_prompt.replace("{current_document}", body)
        prompt = prompt.replace("{sections_to_score}", "\n".join(names))
        prompt = _apply_template(prompt, {"job": self, "user": user})
        raw = call_llm(prompt, client, model, max_tokens=8192)
        parsed = parse_llm_json(raw, SectionEvalResponse)
        allowed = set(names)
        return {
            s.section: {"score": s.score, "issues": [i.model_dump() for i in s.issues]}
            for s in parsed.sections if s.section in allowed
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_job_section_eval.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/job.py tests/core/test_job_section_eval.py
git commit -m "[feat] Job.evaluate_resume_sections: per-section scoring of regenerable sections"
```

---

### Task 6: Orchestrator `_run_resume_section_refinement` + dispatch

**Files:**
- Modify: `web/intake_pipeline.py` (add `_run_resume_section_refinement`; dispatch from `_run_doc_refinement`)
- Test: `tests/web/test_section_refinement.py` (create)

**Interfaces:**
- Consumes: `Job.evaluate_resume_sections`, `generate_resume_by_section(..., only_sections=, critiques=)`, `authored_values_from_tree`, `build_resume_document_tree`, `serialize_document_tree`, `is_tree_v1`/`deserialize_document_tree`, the module-level `_render_doc_from_json` (from 4B-1), `Document.upsert/fetch`, `get_client_for_profile`, `meter_action`, `_emit`, `llm_status`.
- Produces: `_run_resume_section_refinement(job_key, profile_id)` — runs the per-section loop for a tree-v1 résumé; `_run_doc_refinement` calls it when `doc_type=="resume"` and the stored row is tree-v1, else runs the existing whole-document loop unchanged.

**Loop semantics (per Global Constraints):** seed authored from the stored tree; each turn:
eval → `min_score` = min of section scores → record score/turns/log + emit → `failing` = sections
< `pass_score` → if none, stop (success) → if `turn==max_turns`, stop → regenerate only `failing`
with their issues as critique → overlay into authored → rebuild + persist tree-v1 + re-render →
snapshot. Finally restore the best-by-min turn.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_section_refinement.py
import json
from pathlib import Path

import pytest

import web.intake_pipeline as ip
from core.job import Job, _OUTPUTS_DIR
from core.document_tree import build_resume_document_tree
from core.resume_document_io import serialize_document_tree, is_tree_v1
from db.database import Document, User


def test_only_failing_section_regenerated_and_stops_when_all_pass(db_session, monkeypatch, tmp_path):
    # --- seed a tree-v1 resume with two regenerable sections ---
    data = {"first_name": "Jane", "last_name": "Doe", "email": "j@x.co",
            "hero": "old", "skills": ["py"]}
    db_session.add(User(name="Jane Doe", data=json.dumps(data))); db_session.commit()
    from core.user import User as UserEntity
    user = UserEntity.load(db_session)
    root = user.profile_tree_root()
    tree = build_resume_document_tree(root, {})
    job = Job(job_key="sr1", title="t", company="c", profile_id=1)
    db_session.add(job); db_session.commit()
    Document.upsert(db_session, "sr1", "resume", serialize_document_tree(tree), profile_id=1)

    # eval: Summary fails on turn 1 then passes; Skills always passes.
    calls = {"n": 0}
    def fake_eval(self, eval_prompt, user, client, model, db):
        calls["n"] += 1
        summ = 0.4 if calls["n"] == 1 else 0.95
        return {"Summary": {"score": summ, "issues": [{"category": "tailoring", "description": "g"}]},
                "Skills": {"score": 0.95, "issues": []}}
    monkeypatch.setattr(Job, "evaluate_resume_sections", fake_eval)

    regen_sections = []
    def fake_regen(root, job_ctx, client, model, resolve=None, only_sections=None, critiques=None):
        regen_sections.append(set(only_sections or set()))
        return {}   # no field changes needed for the assertion
    monkeypatch.setattr("web.intake_pipeline.generate_resume_by_section", fake_regen)
    # avoid Chromium
    monkeypatch.setattr("core.job.Job.generate_resume_pdf", lambda self, *a, **k: None)

    ip._run_resume_section_refinement("sr1", 1)

    assert regen_sections == [{"Summary"}]   # only the failing section, exactly one regen turn
    row = Document.fetch(db_session, "sr1", "resume", profile_id=1)
    assert is_tree_v1(row.structured_json)
```

Adapt to real fixtures. The binding assertions: only the failing section is regenerated; the
loop stops once all pass; the row stays tree-v1. (If the loop needs the resume generation
prompt, the seeded profile's default prompts cover it; stub `get_client_for_profile` if the
test environment has no platform key — mirror the existing intake_pipeline tests.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_section_refinement.py -v`
Expected: FAIL — `AttributeError: module 'web.intake_pipeline' has no attribute '_run_resume_section_refinement'`.

- [ ] **Step 3: Write minimal implementation**

Add to `web/intake_pipeline.py` (model snapshot/restore on the existing `_run_doc_refinement`
helpers; reuse module-level `_render_doc_from_json`):

```python
def _run_resume_section_refinement(job_key: str, profile_id: int) -> None:
    """Per-section auto-refine for a tree-v1 résumé: score each regenerable section,
    regenerate only sub-threshold sections (with their issues as critique), repeat
    until all pass or max_turns; restore the best-by-min turn."""
    import json as _json
    from pathlib import Path
    from core.document_tree import authored_values_from_tree, build_resume_document_tree
    from core.profile_tree import resolve_profile_tokens
    from core.resume_document_io import (
        serialize_document_tree, deserialize_document_tree, is_tree_v1,
    )
    from core.job import Job, _apply_template
    from core.user import User, PromptNotConfiguredError
    from db.database import Document

    _OUTPUTS = Path(__file__).parent.parent / "generator" / "outputs"
    template_path = Path(__file__).parent.parent / "generator" / "resume_template.html"

    db = SessionLocal()
    try:
        job = Job.get(job_key, db, profile_id)
        if job is None:
            return
        user = User.load(db, profile_id)
        if not getattr(user, "resume_refine_enabled", True):
            return
        max_turns = int(getattr(user, "resume_refine_max_turns", 3))
        pass_score = float(getattr(user, "resume_refine_pass_score", 0.80))
        if max_turns == 0:
            return

        row = Document.fetch(db, job_key, "resume", profile_id)
        if row is None or not is_tree_v1(row.structured_json):
            return  # dispatch guard should prevent this, but be safe

        try:
            eval_prompt = user.resolve_prompt("resume_eval_sectioned")
            gen_prompt = user.resolve_prompt("resume")
        except PromptNotConfiguredError as exc:
            print(f"[section-refine] {job_key}: prompt not configured — {exc}", flush=True)
            return
        eval_client, eval_model = get_client_for_profile(
            user, getattr(user, "prompt_resume_eval_sectioned_model", "") or "")
        gen_client, gen_model = get_client_for_profile(
            user, getattr(user, "prompt_resume_model", "") or "")

        root = user.profile_tree_root()
        authored = authored_values_from_tree(deserialize_document_tree(row.structured_json))
        job_ctx = job.build_resume_prompt(user, gen_prompt, db)

        def resolve(text: str) -> str:
            return _apply_template(resolve_profile_tokens(root, text), {"job": job, "user": user})

        def _snapshot(n: int) -> None:
            r = Document.fetch(db, job_key, "resume", profile_id)
            if r is not None:
                (_OUTPUTS / f"{job_key}_resume_turn_{n}.json").write_text(
                    r.structured_json, encoding="utf-8")

        eval_log: list[dict] = []
        _snapshot(0)
        for turn in range(1, max_turns + 1):
            llm_status.start(job_key, "resume_eval")
            try:
                with meter_action(db, profile_id, action="eval", job_key=job_key):
                    scores = job.evaluate_resume_sections(eval_prompt, user, eval_client, eval_model, db)
            except Exception as exc:
                db.rollback()
                print(f"[section-refine] {job_key}: eval turn {turn} failed — {exc}", flush=True)
                _restore_best_sections(db, job_key, profile_id, eval_log, template_path)
                return
            finally:
                llm_status.finish(job_key, "resume_eval")

            if not scores:
                return  # nothing regenerable
            min_score = min(s["score"] for s in scores.values())
            failing = {n for n, s in scores.items() if s["score"] < pass_score}
            eval_log.append({"turn": turn, "score": min_score,
                             "issues": [i for s in scores.values() for i in s["issues"]],
                             "passed": not failing})
            job.resume_eval_score = min_score
            job.resume_eval_turns = turn
            job.resume_eval_log = _json.dumps(eval_log)
            job.last_result_error = None
            db.commit(); db.refresh(job); _emit(job)
            _snapshot(turn)

            if not failing:
                return
            if turn >= max_turns:
                _restore_best_sections(db, job_key, profile_id, eval_log, template_path)
                return

            llm_status.start(job_key, "resume_refine")
            try:
                critiques = {n: scores[n]["issues"] for n in failing}
                with meter_action(db, profile_id, action="refine", job_key=job_key):
                    new_vals = generate_resume_by_section(
                        root, job_ctx, gen_client, gen_model, resolve=resolve,
                        only_sections=failing, critiques=critiques)
                authored.update(new_vals)
                doc_tree = build_resume_document_tree(root, authored)
                Document.upsert(db, job_key, "resume",
                                serialize_document_tree(doc_tree), profile_id=profile_id)
                job.write_resume_markdown(doc_tree)
                job.generate_resume_pdf(template_path, db, max_pages=1)
                db.commit(); db.refresh(job); _emit(job)
            except Exception as exc:
                db.rollback()
                print(f"[section-refine] {job_key}: refine turn {turn} failed — {exc}", flush=True)
                _restore_best_sections(db, job_key, profile_id, eval_log, template_path)
                return
            finally:
                llm_status.finish(job_key, "resume_refine")
    finally:
        db.close()


def _restore_best_sections(db, job_key, profile_id, eval_log, template_path) -> None:
    """Re-persist + re-render the highest-min turn's snapshot (tree-v1)."""
    from pathlib import Path
    if not eval_log:
        return
    best = max(eval_log, key=lambda e: e["score"])
    snap = (Path(__file__).parent.parent / "generator" / "outputs"
            / f"{job_key}_resume_turn_{best['turn']}.json")
    if not snap.exists():
        return
    structured_json = snap.read_text(encoding="utf-8")
    cur = Document.fetch(db, job_key, "resume", profile_id)
    if cur is not None and cur.structured_json == structured_json:
        return
    Document.upsert(db, job_key, "resume", structured_json, profile_id)
    job = Job.get(job_key, db, profile_id)
    if job is not None:
        _render_doc_from_json(job, "resume", structured_json, template_path, db)
        job.resume_eval_score = best["score"]
        db.commit(); db.refresh(job); _emit(job)
```

Then add the dispatch at the TOP of `_run_doc_refinement`, after `job`/row are available
(before the existing eval/refine loop body):

```python
    if doc_type == "resume":
        from core.resume_document_io import is_tree_v1
        _row = Document.fetch(db, job_key, "resume", profile_id)
        if _row is not None and is_tree_v1(_row.structured_json):
            db.close()  # the section routine opens its own session
            _run_resume_section_refinement(job_key, profile_id)
            return
```

Place this guard so it runs before the whole-document loop and after the `db = SessionLocal()`
open; ensure no double-close (return immediately after delegating). Confirm against the actual
structure of `_run_doc_refinement` — if `db` is opened later, put the delegation right after the
session opens and the `Document` import is available.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_section_refinement.py tests/web/test_intake_pipeline.py tests/web/test_intake_pipeline_render.py -v`
Expected: PASS (existing whole-document loop tests stay green)

- [ ] **Step 5: Commit**

```bash
git add web/intake_pipeline.py tests/web/test_section_refinement.py
git commit -m "[feat] Per-section tree-v1 résumé auto-refine orchestrator + dispatch"
```

---

## Self-Review Notes (carry into final whole-branch review)

- **Spec coverage:** Task 1 = schemas; Task 2 = prompt key; Task 3 = carry-forward; Task 4 =
  regen filter+critique; Task 5 = sectioned eval; Task 6 = orchestrator+dispatch. Stop-rule,
  min-score, threshold-reuse, name-mapping, regenerable-only, best-by-min restore all land in
  Tasks 5–6.
- **Field-name verification each implementer must do:** the Job model's refine fields are
  referenced as `resume_eval_score`, `resume_eval_turns`, `resume_eval_log`,
  `resume_refine_enabled`, `resume_refine_max_turns`, `resume_refine_pass_score`,
  `prompt_resume_model`. Confirm these exact attribute names exist on `Job`/`User` (grep the
  models); the existing `_run_doc_refinement` uses `getattr(user, f"{doc_type}_refine_*")` and
  `setattr(job, f"{doc_type}_eval_score")` — match whatever those resolve to for resume.
- **`prompt_resume_eval_sectioned_model`** likely does NOT exist as a column — `get_client_for_profile`
  with an empty model string must fall back to the platform default (as other paths do with
  `... or ""`). Verify; if a model column is required, pass `""`.
- **Dispatch placement is the main integration risk** — the exact insertion point depends on
  `_run_doc_refinement`'s current structure (where `db`/`job`/`row` become available). The
  implementer must read that function and place the guard so the whole-document loop is fully
  bypassed for tree-v1 résumés with no double session-close.
- **Untouched (do not modify):** `_refine_doc_md` (4B-1 interim, feedback-refine until 4D),
  `resume_eval`, `EvalResponse`, cover paths, legacy `ResumeDocument` rendering.
- **Out of scope:** per-section threshold config/UI, per-section best-turn restore, 4C ATS, 4D
  DocumentModal, cover sectioning.
- **Carry-forward still open from 4B-1:** remove orphaned `core/tree_render.py` (still imported
  by `tests/core/test_tree_render.py` — needs the test removed too + approval); pull duplicated
  test fixtures into a `conftest.py`.
