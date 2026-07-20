# Field-Mapping Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a server-side engine that maps a user's profile + generated documents onto an ATS application form's fields, producing an `ApplicationPlan` that sub-project 3 will use to auto-fill forms.

**Architecture:** A pure canonical field taxonomy + per-ATS static schemas + a question classifier feed a `build_plan()` orchestrator. Objective/EEO answers resolve deterministically from a new profile section; free-text questions get one metered LLM draft (EEO fields are guarded out of the LLM path). The extension enumerates live form fields (read-only) and POSTs them; the plan is persisted on the job and shown in a read-only modal.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, Pydantic, Alembic, pytest; React (Vite) dashboard; MV3 browser extension (vanilla JS).

## Global Constraints

- Python: type hints, `black` formatting, Google-style docstrings. Prefer stdlib.
- The engine is **server-side only**; the extension does DOM I/O and HTTP, no mapping logic.
- **EEO fields are never LLM-inferred** — resolved from stored profile answers or left blank. A deterministic regex guard removes any demographic field from the LLM essay pass before it runs.
- Metering: the `map_fields` action is charged via `core.metering.meter_action` **only when the LLM essay pass runs**; a deterministic-only plan makes no LLM call and is not metered.
- Tenant scoping: every job lookup is `Job.get(job_key, db, profile_id=profile_id)` — never `job_key` alone.
- All new profile answer fields are **optional**; no hard gate on downstream auto-fill.
- Migrations run via Alembic (`db/init_db.py` calls `command.upgrade(cfg, "head")` for both SQLite and Postgres) — one migration, no separate init_db path.
- Follow existing patterns: metered endpoints wrap the body in `with meter_action(...)`; SSE via `web.sse.send`/`_sse_send`; profile data is a JSON blob on `User` (`_hydrate`/`to_dict`), not new columns.
- Canonical ATS coverage for static schemas: **greenhouse, lever, ashby** only.

---

### Task 1: Canonical field taxonomy + deterministic/profile resolvers

**Files:**
- Create: `core/application_fields.py`
- Test: `tests/core/test_application_fields.py`

**Interfaces:**
- Consumes: `core.user.User` (attributes `first_name`, `last_name`, `full_name()`, `email`, `phone`, `linkedin`, `github`, `website`, `location`, and new `application_answers` dict added in Task 3 — until then default `{}`).
- Produces:
  - `FieldKind` = `Literal["deterministic", "eligibility", "eeo", "essay", "unknown"]`
  - `CANONICAL_FIELDS: dict[str, "CanonicalField"]` keyed by canonical key.
  - `CanonicalField` dataclass: `key: str`, `kind: FieldKind`, `resolve: Callable[[ResolveContext], str | None]`.
  - `ResolveContext` dataclass: `user`, `documents: dict[str, str]` (`{"resume_file": path, "cover_letter_text": text}`), `job`, `answers: dict[str, Any]`.
  - `resolve_canonical(key: str, ctx: ResolveContext) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_application_fields.py
from types import SimpleNamespace

from core.application_fields import (
    CANONICAL_FIELDS,
    ResolveContext,
    resolve_canonical,
)


def _ctx(**over):
    user = SimpleNamespace(
        first_name="Ada", last_name="Lovelace", email="ada@example.com",
        phone="555-0100", linkedin="https://linkedin.com/in/ada",
        github="https://github.com/ada", website="", location="London",
        application_answers=over.pop("answers", {}),
    )
    user.full_name = lambda: "Ada Lovelace"
    return ResolveContext(
        user=user,
        documents=over.pop("documents", {"resume_file": "/tmp/r.pdf", "cover_letter_text": "Dear"}),
        job=SimpleNamespace(company="Acme"),
        answers=user.application_answers,
    )


def test_deterministic_fields_resolve_from_user():
    ctx = _ctx()
    assert resolve_canonical("first_name", ctx) == "Ada"
    assert resolve_canonical("full_name", ctx) == "Ada Lovelace"
    assert resolve_canonical("email", ctx) == "ada@example.com"
    assert resolve_canonical("linkedin_url", ctx) == "https://linkedin.com/in/ada"
    assert resolve_canonical("resume_file", ctx) == "/tmp/r.pdf"
    assert resolve_canonical("cover_letter_text", ctx) == "Dear"


def test_eligibility_resolves_from_answers_or_none():
    ctx = _ctx(answers={"eligibility": {"work_authorized": "yes"}})
    assert resolve_canonical("work_authorized", ctx) == "yes"
    assert resolve_canonical("requires_sponsorship", ctx) is None  # unset → None


def test_eeo_resolves_from_answers_or_none():
    ctx = _ctx(answers={"eeo": {"gender": "Decline to self-identify"}})
    assert resolve_canonical("eeo_gender", ctx) == "Decline to self-identify"
    assert resolve_canonical("eeo_veteran", ctx) is None


def test_field_kinds_are_declared():
    assert CANONICAL_FIELDS["first_name"].kind == "deterministic"
    assert CANONICAL_FIELDS["work_authorized"].kind == "eligibility"
    assert CANONICAL_FIELDS["eeo_gender"].kind == "eeo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_fields.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.application_fields'`.

- [ ] **Step 3: Write minimal implementation**

```python
# core/application_fields.py
"""Canonical application-form field taxonomy and value resolvers.

Pure, no LLM, no network. Maps a stable canonical key (e.g. ``first_name``,
``work_authorized``, ``eeo_gender``) to how its value is produced from the user
profile, generated documents, and stored application answers. Consumed by
``core/application_mapper.py``.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Literal

FieldKind = Literal["deterministic", "eligibility", "eeo", "essay", "unknown"]


@dataclasses.dataclass
class ResolveContext:
    """Everything a resolver may read to produce a field value."""

    user: Any
    documents: dict[str, str]
    job: Any
    answers: dict[str, Any]


@dataclasses.dataclass
class CanonicalField:
    """A canonical form field and how to resolve its value."""

    key: str
    kind: FieldKind
    resolve: Callable[[ResolveContext], str | None]


def _u(attr: str) -> Callable[[ResolveContext], str | None]:
    def r(ctx: ResolveContext) -> str | None:
        val = getattr(ctx.user, attr, "") or ""
        return val or None
    return r


def _full_name(ctx: ResolveContext) -> str | None:
    fn = getattr(ctx.user, "full_name", None)
    return (fn() if callable(fn) else None) or None


def _doc(key: str) -> Callable[[ResolveContext], str | None]:
    def r(ctx: ResolveContext) -> str | None:
        return ctx.documents.get(key) or None
    return r


def _answer(group: str, name: str) -> Callable[[ResolveContext], str | None]:
    def r(ctx: ResolveContext) -> str | None:
        val = (ctx.answers.get(group) or {}).get(name)
        return val or None
    return r


def _field(key: str, kind: FieldKind, resolve: Callable[[ResolveContext], str | None]) -> CanonicalField:
    return CanonicalField(key=key, kind=kind, resolve=resolve)


CANONICAL_FIELDS: dict[str, CanonicalField] = {
    f.key: f
    for f in [
        _field("first_name", "deterministic", _u("first_name")),
        _field("last_name", "deterministic", _u("last_name")),
        _field("full_name", "deterministic", _full_name),
        _field("email", "deterministic", _u("email")),
        _field("phone", "deterministic", _u("phone")),
        _field("linkedin_url", "deterministic", _u("linkedin")),
        _field("github_url", "deterministic", _u("github")),
        _field("portfolio_url", "deterministic", _u("website")),
        _field("location", "deterministic", _u("location")),
        _field("resume_file", "deterministic", _doc("resume_file")),
        _field("cover_letter_text", "deterministic", _doc("cover_letter_text")),
        _field("work_authorized", "eligibility", _answer("eligibility", "work_authorized")),
        _field("requires_sponsorship", "eligibility", _answer("eligibility", "requires_sponsorship")),
        _field("willing_to_relocate", "eligibility", _answer("eligibility", "willing_to_relocate")),
        _field("start_date", "eligibility", _answer("eligibility", "start_date")),
        _field("years_experience", "eligibility", _answer("eligibility", "years_experience")),
        _field("eeo_gender", "eeo", _answer("eeo", "gender")),
        _field("eeo_race", "eeo", _answer("eeo", "race_ethnicity")),
        _field("eeo_veteran", "eeo", _answer("eeo", "veteran_status")),
        _field("eeo_disability", "eeo", _answer("eeo", "disability_status")),
    ]
}


def resolve_canonical(key: str, ctx: ResolveContext) -> str | None:
    """Resolve a canonical field's value, or None if unknown/unset."""
    field = CANONICAL_FIELDS.get(key)
    if field is None:
        return None
    return field.resolve(ctx)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_fields.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add core/application_fields.py tests/core/test_application_fields.py
git commit -m "[feat] Add canonical application-field taxonomy + resolvers"
```

---

### Task 2: EEO guard + question classifier

**Files:**
- Create: `core/application_classify.py`
- Test: `tests/core/test_application_classify.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure string logic).
- Produces:
  - `is_eeo_label(label: str) -> bool` — the demographic guard.
  - `match_eligibility(label: str) -> str | None` — returns a canonical eligibility key (`work_authorized`, `requires_sponsorship`, `willing_to_relocate`, `start_date`, `years_experience`) or None.
  - `classify_custom(label: str) -> Literal["eeo", "eligibility", "essay"]` — routing for an enumerated field that did not match a static-schema canonical key. `eeo` wins first (guard), then eligibility keyword, else essay.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_application_classify.py
import pytest

from core.application_classify import classify_custom, is_eeo_label, match_eligibility

EEO_LABELS = [
    "Race / Ethnicity", "What is your gender?", "Gender identity",
    "Are you a protected veteran?", "Veteran status",
    "Disability status", "Do you have a disability?",
    "Hispanic or Latino?", "Sexual orientation",
]


@pytest.mark.parametrize("label", EEO_LABELS)
def test_eeo_guard_catches_demographic_labels(label):
    assert is_eeo_label(label) is True
    assert classify_custom(label) == "eeo"  # guard wins, never essay


@pytest.mark.parametrize("label", [
    "Why do you want to work here?",
    "Tell us about a challenging project",
    "First name", "Email address",
])
def test_eeo_guard_ignores_non_demographic(label):
    assert is_eeo_label(label) is False


def test_eligibility_matching():
    assert match_eligibility("Are you authorized to work in the US?") == "work_authorized"
    assert match_eligibility("Will you now or in the future require sponsorship?") == "requires_sponsorship"
    assert match_eligibility("Are you willing to relocate?") == "willing_to_relocate"
    assert match_eligibility("Earliest start date") == "start_date"
    assert match_eligibility("Years of experience with Python") == "years_experience"
    assert match_eligibility("Why this company?") is None


def test_classify_routes_essay_as_fallback():
    assert classify_custom("Describe your ideal work environment") == "essay"
    assert classify_custom("Are you authorized to work in the US?") == "eligibility"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_classify.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# core/application_classify.py
"""Classify enumerated form-field labels into EEO / eligibility / essay buckets.

Pure string heuristics. The EEO guard is deliberately broad and runs first so a
demographic question can never be routed to the LLM essay pass. Eligibility
matching maps a small set of objective questions to canonical keys; everything
else is treated as a free-text essay question.
"""
from __future__ import annotations

import re
from typing import Literal

# Demographic terms. Broad on purpose: a false positive (an eligibility/essay
# field mislabeled EEO) merely leaves that field blank for manual entry, whereas
# a false negative could let the LLM fabricate a demographic answer.
_EEO_RE = re.compile(
    r"\b(race|ethnicit|gender|sex\b|male\b|female\b|veteran|disab|hispanic|latino|"
    r"sexual orientation|national origin|protected class|self[- ]?identif)\w*",
    re.IGNORECASE,
)

_ELIGIBILITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("work_authorized", re.compile(r"authoriz\w*\s+to\s+work|work\s+authoriz|legally\s+(?:able|entitled)\s+to\s+work", re.I)),
    ("requires_sponsorship", re.compile(r"sponsor", re.I)),
    ("willing_to_relocate", re.compile(r"relocat", re.I)),
    ("start_date", re.compile(r"start\s+date|available.*start|earliest.*start|notice\s+period", re.I)),
    ("years_experience", re.compile(r"years?\s+of\s+experience|how\s+many\s+years", re.I)),
]


def is_eeo_label(label: str) -> bool:
    """True if the label looks like a demographic / EEO self-ID question."""
    return bool(_EEO_RE.search(label or ""))


def match_eligibility(label: str) -> str | None:
    """Return the canonical eligibility key for an objective question, or None.

    The EEO guard takes precedence at the call site (``classify_custom``); this
    function alone does not exclude demographic labels.
    """
    text = label or ""
    for key, pat in _ELIGIBILITY_PATTERNS:
        if pat.search(text):
            return key
    return None


def classify_custom(label: str) -> Literal["eeo", "eligibility", "essay"]:
    """Route a custom (non-static-schema) field. EEO guard wins first."""
    if is_eeo_label(label):
        return "eeo"
    if match_eligibility(label) is not None:
        return "eligibility"
    return "essay"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_classify.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/application_classify.py tests/core/test_application_classify.py
git commit -m "[feat] Add EEO guard + application question classifier"
```

---

### Task 3: Application-answers profile section

**Files:**
- Modify: `core/user.py` (`_hydrate` block ~line 152-191; `to_dict` block ~line 195-227)
- Test: `tests/core/test_application_answers.py`

**Interfaces:**
- Consumes: existing `User._hydrate(raw)` / `User.to_dict()`.
- Produces on `User`:
  - `self.application_answers: dict[str, Any]` — `{"eligibility": {...}, "eeo": {...}}`, round-tripped through `to_dict`.
  - `User.application_answers_complete() -> bool` — True when every eligibility field has a non-empty value **and** every EEO field is either answered or explicitly `"Decline to self-identify"`.
  - Module constants `ELIGIBILITY_KEYS` and `EEO_KEYS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_application_answers.py
import json

from core.user import EEO_KEYS, ELIGIBILITY_KEYS, User


def _user(answers):
    u = User.__new__(User)
    u._hydrate({"application_answers": answers})
    return u


def test_answers_roundtrip_through_to_dict():
    answers = {"eligibility": {"work_authorized": "yes"}, "eeo": {"gender": "Female"}}
    u = _user(answers)
    assert u.application_answers == answers
    # to_dict must carry it back out for persistence
    assert u.to_dict()["application_answers"] == answers


def test_missing_answers_defaults_to_empty():
    u = _user(None)
    assert u.application_answers == {"eligibility": {}, "eeo": {}}


def test_completeness_requires_all_eligibility_and_eeo_choices():
    complete = {
        "eligibility": {k: "yes" for k in ELIGIBILITY_KEYS},
        "eeo": {k: "Decline to self-identify" for k in EEO_KEYS},
    }
    assert _user(complete).application_answers_complete() is True
    partial = {"eligibility": {ELIGIBILITY_KEYS[0]: "yes"}, "eeo": {}}
    assert _user(partial).application_answers_complete() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_answers.py -v`
Expected: FAIL — `ImportError: cannot import name 'EEO_KEYS'`.

- [ ] **Step 3: Write minimal implementation**

Add near the top of `core/user.py` (after imports, module scope):

```python
ELIGIBILITY_KEYS = [
    "work_authorized", "requires_sponsorship", "willing_to_relocate",
    "start_date", "years_experience",
]
EEO_KEYS = ["gender", "race_ethnicity", "veteran_status", "disability_status"]


def _normalize_answers(raw: Any) -> dict[str, dict[str, Any]]:
    """Coerce a stored/partial answers blob to {'eligibility': {}, 'eeo': {}}."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "eligibility": dict(raw.get("eligibility") or {}),
        "eeo": dict(raw.get("eeo") or {}),
    }
```

In `_hydrate`, alongside the other `self.x = raw.get(...)` lines (e.g. after `self.onboarding_tour`):

```python
        self.application_answers = _normalize_answers(raw.get("application_answers"))
```

In `to_dict`, before `apply_flat_to_tree(...)`:

```python
        d["application_answers"] = self.application_answers
```

Add the completeness method to the `User` class:

```python
    def application_answers_complete(self) -> bool:
        """True when eligibility is fully filled and every EEO item is chosen.

        EEO 'Decline to self-identify' counts as a valid choice — the section is
        legally voluntary, so a decline is completion, not a gap.
        """
        elig = self.application_answers.get("eligibility", {})
        eeo = self.application_answers.get("eeo", {})
        elig_ok = all((elig.get(k) or "").strip() for k in ELIGIBILITY_KEYS)
        eeo_ok = all((eeo.get(k) or "").strip() for k in EEO_KEYS)
        return elig_ok and eeo_ok
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_answers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/user.py tests/core/test_application_answers.py
git commit -m "[feat] Add application-answers (eligibility + EEO) profile section"
```

---

### Task 4: Static per-ATS field schemas

**Files:**
- Create: `core/ats_schemas.py`
- Test: `tests/core/test_ats_schemas.py`

**Interfaces:**
- Consumes: canonical keys from Task 1 (`CANONICAL_FIELDS`).
- Produces:
  - `STATIC_SCHEMAS: dict[str, list["SchemaField"]]` keyed by `ats_type` (`greenhouse`, `lever`, `ashby`).
  - `SchemaField` dataclass: `field_id: str` (the ATS's native input name), `label: str`, `canonical_key: str`, `required: bool`.
  - `schema_for(ats_type: str) -> list[SchemaField]` — returns `[]` for unknown ATS.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_ats_schemas.py
from core.application_fields import CANONICAL_FIELDS
from core.ats_schemas import STATIC_SCHEMAS, schema_for


def test_supported_ats_have_schemas():
    assert set(STATIC_SCHEMAS) == {"greenhouse", "lever", "ashby"}


def test_every_schema_field_maps_to_a_real_canonical_key():
    for ats, fields in STATIC_SCHEMAS.items():
        for f in fields:
            assert f.canonical_key in CANONICAL_FIELDS, f"{ats}:{f.field_id}"


def test_greenhouse_covers_core_contact_fields():
    keys = {f.canonical_key for f in schema_for("greenhouse")}
    assert {"first_name", "last_name", "email", "resume_file"} <= keys


def test_unknown_ats_returns_empty():
    assert schema_for("workday") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/core/test_ats_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# core/ats_schemas.py
"""Hand-authored standard-application field maps for supported ATSs.

Maps each ATS's native form-field identifier to a canonical key (see
core/application_fields.py). Only the low-defense, form-based ATSs that
sub-project 3 targets first are covered: greenhouse, lever, ashby. Any other
ats_type has no static schema and relies entirely on dynamic enumeration.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class SchemaField:
    """One field in an ATS's standard application form."""

    field_id: str
    label: str
    canonical_key: str
    required: bool = False


STATIC_SCHEMAS: dict[str, list[SchemaField]] = {
    "greenhouse": [
        SchemaField("first_name", "First Name", "first_name", True),
        SchemaField("last_name", "Last Name", "last_name", True),
        SchemaField("email", "Email", "email", True),
        SchemaField("phone", "Phone", "phone"),
        SchemaField("resume", "Resume/CV", "resume_file", True),
        SchemaField("cover_letter", "Cover Letter", "cover_letter_text"),
        SchemaField("job_application[answers_attributes][linkedin]", "LinkedIn Profile", "linkedin_url"),
    ],
    "lever": [
        SchemaField("name", "Full name", "full_name", True),
        SchemaField("email", "Email", "email", True),
        SchemaField("phone", "Phone", "phone"),
        SchemaField("resume", "Resume/CV", "resume_file", True),
        SchemaField("urls[LinkedIn]", "LinkedIn URL", "linkedin_url"),
        SchemaField("urls[GitHub]", "GitHub URL", "github_url"),
        SchemaField("comments", "Additional information", "cover_letter_text"),
    ],
    "ashby": [
        SchemaField("name", "Name", "full_name", True),
        SchemaField("email", "Email", "email", True),
        SchemaField("phone", "Phone", "phone"),
        SchemaField("resume", "Resume", "resume_file", True),
        SchemaField("linkedin", "LinkedIn", "linkedin_url"),
        SchemaField("github", "GitHub", "github_url"),
    ],
}


def schema_for(ats_type: str) -> list[SchemaField]:
    """Return the static schema for an ATS, or [] if unsupported."""
    return STATIC_SCHEMAS.get(ats_type or "", [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/core/test_ats_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/ats_schemas.py tests/core/test_ats_schemas.py
git commit -m "[feat] Add static ATS field schemas (greenhouse/lever/ashby)"
```

---

### Task 5: Pydantic plan schemas

**Files:**
- Modify: `core/schemas.py` (append models)
- Test: `tests/core/test_application_plan_schema.py`

**Interfaces:**
- Produces (in `core.schemas`):
  - `EnumeratedField(BaseModel)`: `field_id: str`, `label: str = ""`, `input_type: str = "text"`, `options: list[str] = []`, `required: bool = False`.
  - `PlannedField(BaseModel)`: `field_id: str`, `label: str = ""`, `canonical_key: str | None = None`, `value: str | None = None`, `status: Literal["filled","drafted","blank","unknown"]`, `source: str`.
  - `ApplicationPlan(BaseModel)`: `job_key: str`, `ats_type: str | None = None`, `fields: list[PlannedField] = []`, `generated_at: str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_application_plan_schema.py
from core.schemas import ApplicationPlan, EnumeratedField, PlannedField


def test_enumerated_field_defaults():
    f = EnumeratedField(field_id="email")
    assert f.input_type == "text" and f.options == [] and f.required is False


def test_plan_roundtrips_json():
    plan = ApplicationPlan(
        job_key="linkedin_1", ats_type="greenhouse", generated_at="2026-07-20T00:00:00Z",
        fields=[PlannedField(field_id="email", value="a@b.c", status="filled", source="deterministic")],
    )
    dumped = plan.model_dump_json()
    back = ApplicationPlan.model_validate_json(dumped)
    assert back.fields[0].status == "filled"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_plan_schema.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Append to `core/schemas.py` (match the file's existing Pydantic import style; it already imports `BaseModel`):

```python
from typing import Literal  # if not already imported at top


class EnumeratedField(BaseModel):
    """A form field the extension read off a live application page."""

    field_id: str
    label: str = ""
    input_type: str = "text"
    options: list[str] = []
    required: bool = False


class PlannedField(BaseModel):
    """One resolved field in an application plan."""

    field_id: str
    label: str = ""
    canonical_key: str | None = None
    value: str | None = None
    status: Literal["filled", "drafted", "blank", "unknown"]
    source: str


class ApplicationPlan(BaseModel):
    """The computed field→value mapping for one job's application form."""

    job_key: str
    ats_type: str | None = None
    fields: list[PlannedField] = []
    generated_at: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_plan_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/schemas.py tests/core/test_application_plan_schema.py
git commit -m "[feat] Add ApplicationPlan Pydantic schemas"
```

---

### Task 6: The mapping engine

**Files:**
- Create: `core/application_mapper.py`
- Test: `tests/core/test_application_mapper.py`

**Interfaces:**
- Consumes: Task 1 (`ResolveContext`, `resolve_canonical`, `CANONICAL_FIELDS`), Task 2 (`classify_custom`, `match_eligibility`), Task 4 (`schema_for`, `SchemaField`), Task 5 (`ApplicationPlan`, `EnumeratedField`, `PlannedField`).
- Produces:
  - `build_plan(job, user, documents, enumerated_fields=None, draft_essays=None) -> ApplicationPlan`.
    - `documents: dict[str, str]` — `{"resume_file": path|"", "cover_letter_text": text|""}`.
    - `enumerated_fields: list[EnumeratedField] | None`.
    - `draft_essays: Callable[[list[tuple[str, str]]], dict[str, str]] | None` — injected essay drafter mapping `[(field_id, label)] -> {field_id: answer}`. When None, essay fields get `status="unknown"` (no LLM). This injection keeps the engine LLM-free and unit-testable; the endpoint (Task 8) supplies the real LLM-backed drafter.
  - `needs_essay_pass(job, enumerated_fields) -> bool` — True if any enumerated field would route to essay (drives metering in Task 8).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_application_mapper.py
from types import SimpleNamespace

from core.application_mapper import build_plan, needs_essay_pass
from core.schemas import EnumeratedField


def _user(answers=None):
    u = SimpleNamespace(
        first_name="Ada", last_name="Lovelace", email="ada@x.com", phone="",
        linkedin="https://li/ada", github="", website="", location="London",
        application_answers=answers or {"eligibility": {}, "eeo": {}},
    )
    u.full_name = lambda: "Ada Lovelace"
    return u


def _job(ats="greenhouse"):
    return SimpleNamespace(job_key="j1", ats_type=ats, company="Acme")


DOCS = {"resume_file": "/tmp/r.pdf", "cover_letter_text": "Dear Acme"}


def test_static_schema_fields_are_filled_or_blank():
    plan = build_plan(_job(), _user(), DOCS)
    by_key = {f.canonical_key: f for f in plan.fields}
    assert by_key["email"].value == "ada@x.com" and by_key["email"].status == "filled"
    assert by_key["phone"].status == "blank"  # empty profile phone
    assert by_key["resume_file"].value == "/tmp/r.pdf"


def test_eeo_enumerated_field_never_drafted():
    fields = [EnumeratedField(field_id="q_gender", label="What is your gender?")]
    called = {"n": 0}

    def drafter(pairs):
        called["n"] += 1
        return {fid: "SHOULD NOT HAPPEN" for fid, _ in pairs}

    plan = build_plan(_job("other"), _user(), DOCS, enumerated_fields=fields, draft_essays=drafter)
    gender = next(f for f in plan.fields if f.field_id == "q_gender")
    assert gender.status == "blank"  # no stored eeo answer
    assert gender.value is None
    assert called["n"] == 0  # EEO guard kept it out of the drafter entirely


def test_objective_custom_resolves_from_answers():
    fields = [EnumeratedField(field_id="q_auth", label="Are you authorized to work in the US?")]
    user = _user({"eligibility": {"work_authorized": "Yes"}, "eeo": {}})
    plan = build_plan(_job("other"), user, DOCS, enumerated_fields=fields)
    q = next(f for f in plan.fields if f.field_id == "q_auth")
    assert q.value == "Yes" and q.status == "filled"


def test_essay_field_uses_injected_drafter():
    fields = [EnumeratedField(field_id="q_why", label="Why do you want to work here?")]
    plan = build_plan(_job("other"), _user(), DOCS, enumerated_fields=fields,
                      draft_essays=lambda pairs: {fid: "Because..." for fid, _ in pairs})
    q = next(f for f in plan.fields if f.field_id == "q_why")
    assert q.value == "Because..." and q.status == "drafted"


def test_needs_essay_pass_detection():
    assert needs_essay_pass(_job("other"), [EnumeratedField(field_id="q", label="Why us?")]) is True
    assert needs_essay_pass(_job("other"), [EnumeratedField(field_id="g", label="Gender")]) is False
    assert needs_essay_pass(_job("greenhouse"), None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_mapper.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# core/application_mapper.py
"""Build an ApplicationPlan from a job, profile, documents, and enumerated fields.

Pure orchestration over the taxonomy (application_fields), classifier
(application_classify), and static schemas (ats_schemas). No LLM here: free-text
essay drafting is injected via ``draft_essays`` so this module stays
unit-testable and the metering decision lives at the endpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from core.application_classify import classify_custom, is_eeo_label, match_eligibility
from core.application_fields import (
    CANONICAL_FIELDS,
    ResolveContext,
    resolve_canonical,
)
from core.ats_schemas import schema_for
from core.schemas import ApplicationPlan, EnumeratedField, PlannedField

EssayDrafter = Callable[[list[tuple[str, str]]], dict[str, str]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_for(value: str | None, kind: str) -> str:
    if value:
        return "filled"
    if kind in ("deterministic", "eligibility", "eeo"):
        return "blank"
    return "unknown"


def _plan_static_field(field, ctx: ResolveContext) -> PlannedField:
    value = resolve_canonical(field.canonical_key, ctx)
    kind = CANONICAL_FIELDS[field.canonical_key].kind
    return PlannedField(
        field_id=field.field_id, label=field.label,
        canonical_key=field.canonical_key, value=value,
        status=_status_for(value, kind), source="static_schema",
    )


def needs_essay_pass(job: Any, enumerated_fields: list[EnumeratedField] | None) -> bool:
    """True if any enumerated custom field routes to the essay bucket."""
    for f in enumerated_fields or []:
        if _canonical_for_enumerated(f) is not None:
            continue
        if classify_custom(f.label) == "essay":
            return True
    return False


def _canonical_for_enumerated(f: EnumeratedField) -> str | None:
    """Map an enumerated field to a canonical key by id/label, or None.

    Deliberately conservative: exact-key match on field_id, else None (custom).
    """
    if f.field_id in CANONICAL_FIELDS:
        return f.field_id
    return None


def build_plan(
    job: Any,
    user: Any,
    documents: dict[str, str],
    enumerated_fields: list[EnumeratedField] | None = None,
    draft_essays: EssayDrafter | None = None,
) -> ApplicationPlan:
    """Compute the field→value plan for a job's application form."""
    answers = getattr(user, "application_answers", {}) or {}
    ctx = ResolveContext(user=user, documents=documents, job=job, answers=answers)

    planned: list[PlannedField] = []
    seen_ids: set[str] = set()

    # 1. Static schema for the ATS.
    for sf in schema_for(getattr(job, "ats_type", None)):
        planned.append(_plan_static_field(sf, ctx))
        seen_ids.add(sf.field_id)

    # 2. Merge dynamically-enumerated fields.
    essay_pending: list[tuple[str, str]] = []
    essay_slots: dict[str, PlannedField] = {}
    for ef in enumerated_fields or []:
        if ef.field_id in seen_ids:
            continue
        seen_ids.add(ef.field_id)
        canon = _canonical_for_enumerated(ef)
        if canon is not None:
            value = resolve_canonical(canon, ctx)
            planned.append(PlannedField(
                field_id=ef.field_id, label=ef.label, canonical_key=canon,
                value=value, status=_status_for(value, CANONICAL_FIELDS[canon].kind),
                source="enumerated_canonical"))
            continue

        # Custom field: EEO guard first, then eligibility, then essay.
        if is_eeo_label(ef.label):
            value = resolve_canonical(_eeo_key_for(ef.label), ctx) if _eeo_key_for(ef.label) else None
            planned.append(PlannedField(
                field_id=ef.field_id, label=ef.label, canonical_key=_eeo_key_for(ef.label),
                value=value, status=_status_for(value, "eeo"), source="eeo"))
            continue
        elig = match_eligibility(ef.label)
        if elig is not None:
            value = resolve_canonical(elig, ctx)
            planned.append(PlannedField(
                field_id=ef.field_id, label=ef.label, canonical_key=elig,
                value=value, status=_status_for(value, "eligibility"), source="eligibility"))
            continue
        # Essay.
        pf = PlannedField(field_id=ef.field_id, label=ef.label, canonical_key=None,
                          value=None, status="unknown", source="essay")
        planned.append(pf)
        essay_slots[ef.field_id] = pf
        essay_pending.append((ef.field_id, ef.label))

    # 3. Essay pass (injected drafter only; EEO fields are already excluded).
    if essay_pending and draft_essays is not None:
        drafts = draft_essays(essay_pending) or {}
        for fid, answer in drafts.items():
            slot = essay_slots.get(fid)
            if slot is not None and answer:
                slot.value = answer
                slot.status = "drafted"

    return ApplicationPlan(
        job_key=getattr(job, "job_key", ""),
        ats_type=getattr(job, "ats_type", None),
        fields=planned, generated_at=_now(),
    )


def _eeo_key_for(label: str) -> str | None:
    """Map an EEO label to a canonical eeo_* key, or None if only guarded."""
    text = (label or "").lower()
    if "gender" in text or "sex" in text:
        return "eeo_gender"
    if "race" in text or "ethnic" in text or "hispanic" in text or "latino" in text:
        return "eeo_race"
    if "veteran" in text:
        return "eeo_veteran"
    if "disab" in text:
        return "eeo_disability"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_mapper.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add core/application_mapper.py tests/core/test_application_mapper.py
git commit -m "[feat] Add application field-mapping engine (build_plan)"
```

---

### Task 7: DB column + serialize + Alembic migration

**Files:**
- Modify: `core/job.py` (Job columns ~line 296-312; `serialize` ~line 1347)
- Create: `alembic/versions/aa13applyplan01_add_application_plan.py`
- Test: `tests/core/test_application_plan_column.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `Job.application_plan` (Text/JSON string column, nullable); `Job.serialize()` includes `"application_plan"` as a parsed dict-or-None.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_application_plan_column.py
import json

from core.job import Job


def test_serialize_parses_application_plan_json():
    job = Job.__new__(Job)
    job._hydrate_defaults() if hasattr(job, "_hydrate_defaults") else None
    job.application_plan = json.dumps({"job_key": "j1", "fields": []})
    out = job.serialize()
    assert out["application_plan"] == {"job_key": "j1", "fields": []}


def test_serialize_application_plan_none_when_unset():
    job = Job.__new__(Job)
    job.application_plan = None
    assert job.serialize()["application_plan"] is None
```

> Note: existing `serialize` tests construct `Job` a particular way — mirror the construction used in `tests/core/` neighbors (e.g. `test_job_serialize*`) if `Job.__new__` alone is insufficient; the assertion on `application_plan` is what matters.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_plan_column.py -v`
Expected: FAIL — `AttributeError`/`KeyError: 'application_plan'`.

- [ ] **Step 3: Write minimal implementation**

Add to the Job model (near the `apply_url_*` block, ~line 273):

```python
    application_plan = Column(Text)  # JSON ApplicationPlan for this job's form; null=none computed
```

In `Job.serialize()`, add before the return (follow the file's existing JSON-parse helper style; several `ext_*` fields already `json.loads`):

```python
        try:
            application_plan = json.loads(self.application_plan) if self.application_plan else None
        except (ValueError, TypeError):
            application_plan = None
        d["application_plan"] = application_plan
```

Create the Alembic migration:

```python
# alembic/versions/aa13applyplan01_add_application_plan.py
"""add application_plan column to jobs

Revision ID: aa13applyplan01
Revises: aa12atsdetect01
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "aa13applyplan01"
down_revision = "aa12atsdetect01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("application_plan", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "application_plan")
```

- [ ] **Step 4: Run test + migration**

Run: `.venv/Scripts/python -m pytest tests/core/test_application_plan_column.py -v`
Expected: PASS.
Run (idempotency/migration smoke): `.venv/Scripts/python -c "from db.database import init_db; init_db(); init_db()"`
Expected: no error (second run is a no-op; Alembic already at head).

- [ ] **Step 5: Commit**

```bash
git add core/job.py alembic/versions/aa13applyplan01_add_application_plan.py tests/core/test_application_plan_column.py
git commit -m "[feat] Add jobs.application_plan column + serialize + migration"
```

---

### Task 8: Server endpoints (POST/GET application-plan) + pricing + essay drafter

**Files:**
- Modify: `core/pricing.py` (add `map_fields` to `DEFAULT_PRICES`)
- Modify: `web/routers/scraper.py` (add two routes near the `ats-resolution` route ~line 277; imports at top)
- Create: `web/application_plan_service.py` (essay drafter + plan assembly wiring)
- Test: `tests/web/test_application_plan_api.py`, `tests/core/test_pricing_map_fields.py`

**Interfaces:**
- Consumes: Task 3 (`User.application_answers`, `application_answers_complete`), Task 6 (`build_plan`, `needs_essay_pass`), Task 7 (`Job.application_plan`), `core.metering.meter_action`, `core.credits`.
- Produces:
  - `POST /api/scraper/jobs/{job_key}/application-plan` — body `{ enumerated_fields?: EnumeratedField[] }` → returns `ApplicationPlan` dict; persists to `Job.application_plan`; SSE-broadcasts the job; metered `map_fields` **only** when `needs_essay_pass` is true.
  - `GET /api/scraper/jobs/{job_key}/application-plan` → `{ plan: <ApplicationPlan|null>, application_answers_complete: bool }`.
  - `web.application_plan_service.make_essay_drafter(user, job, db, profile_id) -> EssayDrafter` — real LLM-backed drafter (reuses `core.job` generation honesty conventions).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_pricing_map_fields.py
from core.pricing import DEFAULT_PRICES, price_for


def test_map_fields_price_registered():
    assert "map_fields" in DEFAULT_PRICES
    assert price_for("map_fields") == DEFAULT_PRICES["map_fields"]
```

```python
# tests/web/test_application_plan_api.py
# Use the project's existing FastAPI TestClient fixture/conftest (mirror
# tests/web/test_profile_api.py setup). Pseudocode-free, concrete assertions:
import json

from core.job import Job


def test_post_plan_persists_and_returns(client, db, seed_profile):
    # seed a greenhouse job for the test profile (mirror existing job-seeding helper)
    job = _seed_job(db, seed_profile, job_key="j1", ats_type="greenhouse")
    resp = client.post("/api/scraper/jobs/j1/application-plan", json={"enumerated_fields": []})
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_key"] == "j1"
    assert any(f["canonical_key"] == "email" for f in body["fields"])
    # persisted
    stored = json.loads(Job.get("j1", db, profile_id=seed_profile).application_plan)
    assert stored["job_key"] == "j1"


def test_get_plan_returns_stored_and_completeness(client, db, seed_profile):
    _seed_job(db, seed_profile, job_key="j2", ats_type="lever")
    client.post("/api/scraper/jobs/j2/application-plan", json={"enumerated_fields": []})
    resp = client.get("/api/scraper/jobs/j2/application-plan")
    assert resp.status_code == 200
    assert resp.json()["plan"]["job_key"] == "j2"
    assert "application_answers_complete" in resp.json()


def test_post_plan_404_for_missing_job(client, db, seed_profile):
    resp = client.post("/api/scraper/jobs/nope/application-plan", json={})
    assert resp.status_code == 404


def test_cross_tenant_post_cannot_touch_other_job(client, db, other_profile_job):
    # a job owned by a different profile must 404 for this caller
    resp = client.post(f"/api/scraper/jobs/{other_profile_job}/application-plan", json={})
    assert resp.status_code == 404
```

> The `client`, `db`, `seed_profile`, `_seed_job`, `other_profile_job` helpers exist in / mirror `tests/web/conftest.py` and `tests/web/test_profile_api.py`. Reuse them; do not invent a new harness.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/core/test_pricing_map_fields.py tests/web/test_application_plan_api.py -v`
Expected: FAIL — missing price key / 404 route.

- [ ] **Step 3: Write minimal implementation**

Add to `core/pricing.py` `DEFAULT_PRICES`:

```python
    "map_fields": 2,      # LLM essay-draft pass over custom application questions
```

Create `web/application_plan_service.py`:

```python
# web/application_plan_service.py
"""Wiring between the pure mapping engine and the LLM + persistence layers."""
from __future__ import annotations

import logging
from typing import Any

from core.application_mapper import EssayDrafter

logger = logging.getLogger(__name__)


def make_essay_drafter(user: Any, job: Any) -> EssayDrafter:
    """Return a drafter that answers free-text questions grounded in the profile.

    Reuses the existing generation LLM path. Each question is answered honestly
    from profile facts; answers are always marked 'drafted' (needs review) by the
    engine, never auto-submitted.
    """
    from core.job import draft_application_answers  # added below

    def drafter(pairs: list[tuple[str, str]]) -> dict[str, str]:
        try:
            return draft_application_answers(user, job, pairs)
        except Exception:
            logger.exception("[application-plan] essay drafting failed for %s", getattr(job, "job_key", "?"))
            return {}

    return drafter
```

Add a thin LLM helper `draft_application_answers(user, job, pairs)` to `core/job.py`, following the existing `call_llm`/prompt conventions in that file (reuse the module's LLM client construction and the honesty-rule system prompt used by generation). It takes `[(field_id, question)]` and returns `{field_id: answer}`. Keep it one LLM call: send all questions in one structured prompt requesting a JSON object keyed by `field_id`; parse via the existing `parse_llm_json` helper from `core/schemas.py`. (Concrete prompt text: instruct the model to answer each application question in 2-4 sentences using only facts supported by the provided profile/job, never inventing credentials, and to return strict JSON `{field_id: answer}`.)

Add the routes to `web/routers/scraper.py` (imports: `from core.application_mapper import build_plan, needs_essay_pass`; `from core.schemas import EnumeratedField`; `from core.metering import meter_action`; `from core.user import User`; `from web.application_plan_service import make_essay_drafter`; `from core.pricing import price_for`):

```python
class ApplicationPlanRequest(BaseModel):
    enumerated_fields: list[EnumeratedField] = []


def _documents_for(job: Job) -> dict[str, str]:
    """Resume file pointer + cover letter text for plan resolution."""
    cover_text = ""
    if job.cover_path:
        try:
            from pathlib import Path
            cover_text = Path(job.cover_path).read_text(encoding="utf-8")
        except OSError:
            cover_text = ""
    return {"resume_file": job.resume_path or "", "cover_letter_text": cover_text}


@router.post("/jobs/{job_key}/application-plan")
def compute_application_plan(
    job_key: str,
    body: ApplicationPlanRequest,
    db: Session = Depends(get_db),
    profile_id: int = Depends(bearer_or_session_profile),
) -> dict[str, Any]:
    """Compute, persist, and return the application plan for a job's form."""
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    user = User.load(db, profile_id=profile_id)
    documents = _documents_for(job)
    fields = body.enumerated_fields

    if needs_essay_pass(job, fields):
        with meter_action(db, profile_id, action="map_fields", job_key=job_key,
                          price=price_for("map_fields")):
            plan = build_plan(job, user, documents, enumerated_fields=fields,
                              draft_essays=make_essay_drafter(user, job))
    else:
        plan = build_plan(job, user, documents, enumerated_fields=fields)

    job.application_plan = plan.model_dump_json()
    db.commit()
    db.refresh(job)
    try:
        _sse_send("job", job.serialize(), profile_id=profile_id)
    except Exception:
        logger.exception("[application-plan] broadcast failed for %s", job_key)
    return plan.model_dump()


@router.get("/jobs/{job_key}/application-plan")
def get_application_plan(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(bearer_or_session_profile),
) -> dict[str, Any]:
    """Return the last stored plan and the answers-completeness flag."""
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    user = User.load(db, profile_id=profile_id)
    import json
    plan = json.loads(job.application_plan) if job.application_plan else None
    return {"plan": plan, "application_answers_complete": user.application_answers_complete()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/core/test_pricing_map_fields.py tests/web/test_application_plan_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/pricing.py core/job.py web/application_plan_service.py web/routers/scraper.py tests/core/test_pricing_map_fields.py tests/web/test_application_plan_api.py
git commit -m "[feat] Add application-plan endpoints + map_fields metering + essay drafter"
```

---

### Task 9: Frontend API client + read-only plan modal

**Files:**
- Modify: `react-dashboard/src/api.js` (add two functions)
- Create: `react-dashboard/src/components/widgets/ApplicationPlanModal.jsx`
- Modify: the job card component that renders `AtsChip` (find via `grep -rn "AtsChip" react-dashboard/src`) — add a button that opens the modal.
- Test: `react-dashboard/src/components/widgets/ApplicationPlanModal.test.jsx`

**Interfaces:**
- Consumes: `GET /api/scraper/jobs/{job_key}/application-plan`.
- Produces: `getApplicationPlan(jobKey)` in `api.js`; `<ApplicationPlanModal jobKey open onClose />`.

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/components/widgets/ApplicationPlanModal.test.jsx
import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import ApplicationPlanModal from "./ApplicationPlanModal";
import * as api from "../../api";

describe("ApplicationPlanModal", () => {
  it("renders planned fields with status", async () => {
    vi.spyOn(api, "getApplicationPlan").mockResolvedValue({
      plan: { job_key: "j1", ats_type: "greenhouse", fields: [
        { field_id: "email", label: "Email", value: "a@b.c", status: "filled", source: "static_schema" },
        { field_id: "q_why", label: "Why us?", value: "Because", status: "drafted", source: "essay" },
      ] },
      application_answers_complete: false,
    });
    render(<ApplicationPlanModal jobKey="j1" open onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("Email")).toBeInTheDocument());
    expect(screen.getByText("a@b.c")).toBeInTheDocument();
    expect(screen.getByText(/drafted/i)).toBeInTheDocument();
  });

  it("shows empty-state when no plan computed yet", async () => {
    vi.spyOn(api, "getApplicationPlan").mockResolvedValue({ plan: null, application_answers_complete: true });
    render(<ApplicationPlanModal jobKey="j2" open onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/no application plan/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npm test -- ApplicationPlanModal`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Add to `react-dashboard/src/api.js` (match the file's existing `_fetch` helper + export style):

```js
export async function getApplicationPlan(jobKey) {
  return _fetch(`/api/scraper/jobs/${encodeURIComponent(jobKey)}/application-plan`);
}
```

Create the modal (follow the dark-theme + `<select>`-option-black conventions used by existing widgets; keep it read-only):

```jsx
// react-dashboard/src/components/widgets/ApplicationPlanModal.jsx
import { useEffect, useState } from "react";
import { getApplicationPlan } from "../../api";

const STATUS_LABEL = {
  filled: "filled", drafted: "drafted (review)", blank: "blank", unknown: "unknown",
};

export default function ApplicationPlanModal({ jobKey, open, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getApplicationPlan(jobKey)
      .then(setData)
      .finally(() => setLoading(false));
  }, [open, jobKey]);

  if (!open) return null;
  const plan = data?.plan;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <h3>Application plan</h3>
        {loading && <p>Loading…</p>}
        {!loading && !plan && (
          <p>No application plan yet. It’s computed when the extension visits this job’s apply page.</p>
        )}
        {!loading && plan && (
          <table className="plan-table">
            <thead><tr><th>Field</th><th>Value</th><th>Status</th></tr></thead>
            <tbody>
              {plan.fields.map((f) => (
                <tr key={f.field_id}>
                  <td>{f.label || f.field_id}</td>
                  <td>{f.value || <em>—</em>}</td>
                  <td>{STATUS_LABEL[f.status] || f.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <button onClick={onClose}>Close</button>
      </div>
    </div>
  );
}
```

Wire a trigger button into the job-card component next to `AtsChip`:

```jsx
// in the job card component, alongside existing imports:
import ApplicationPlanModal from "./widgets/ApplicationPlanModal"; // adjust relative path
// inside the component:
const [planOpen, setPlanOpen] = useState(false);
// near <AtsChip .../>:
<button className="chip-btn" onClick={() => setPlanOpen(true)}>Plan</button>
<ApplicationPlanModal jobKey={job.job_key} open={planOpen} onClose={() => setPlanOpen(false)} />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd react-dashboard && npm test -- ApplicationPlanModal`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/api.js react-dashboard/src/components/widgets/ApplicationPlanModal.jsx react-dashboard/src/components/widgets/ApplicationPlanModal.test.jsx
git commit -m "[feat] Add read-only application-plan modal + API client"
```

---

### Task 10: Dashboard — Application-answers settings section

**Files:**
- Modify: `react-dashboard/src/api.js` (reuse existing profile-update call; add `getApplicationAnswersComplete` only if not already covered by the profile fetch)
- Create: `react-dashboard/src/components/widgets/ApplicationAnswers.jsx`
- Modify: the settings/profile page that hosts profile sections (find via `grep -rn "settings\|Settings" react-dashboard/src/components` and the profile-tree host) — mount the new section, tier-gated to friends_family/beta (reuse the existing tier-gating pattern used for extension docs / admin panels).
- Test: `react-dashboard/src/components/widgets/ApplicationAnswers.test.jsx`

**Interfaces:**
- Consumes: existing profile GET/PUT (the profile blob now carries `application_answers` from Task 3). If the dashboard writes profile via the profile-tree PUT, ensure `application_answers` is included in the payload (it already round-trips through `User.to_dict`).
- Produces: `<ApplicationAnswers value onChange />` editing `{ eligibility, eeo }`.

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/components/widgets/ApplicationAnswers.test.jsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ApplicationAnswers from "./ApplicationAnswers";

describe("ApplicationAnswers", () => {
  it("renders eligibility + EEO fields and emits changes", () => {
    const onChange = vi.fn();
    render(<ApplicationAnswers value={{ eligibility: {}, eeo: {} }} onChange={onChange} />);
    expect(screen.getByLabelText(/authorized to work/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/gender/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/authorized to work/i), { target: { value: "yes" } });
    expect(onChange).toHaveBeenCalled();
  });

  it("EEO selects include a decline option", () => {
    render(<ApplicationAnswers value={{ eligibility: {}, eeo: {} }} onChange={() => {}} />);
    expect(screen.getByText(/decline to self-identify/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npm test -- ApplicationAnswers`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `react-dashboard/src/components/widgets/ApplicationAnswers.jsx`. Eligibility fields render as yes/no selects + text (`start_date`, `years_experience`); EEO fields render as selects whose options **must** include "Decline to self-identify" and use black option text on the dark theme (per the project convention). Emit the merged `{ eligibility, eeo }` object via `onChange`.

```jsx
// react-dashboard/src/components/widgets/ApplicationAnswers.jsx
const YES_NO = ["", "yes", "no"];
const DECLINE = "Decline to self-identify";
const EEO_OPTIONS = {
  gender: ["", "Male", "Female", "Non-binary", DECLINE],
  race_ethnicity: ["", "American Indian or Alaska Native", "Asian", "Black or African American",
    "Hispanic or Latino", "Native Hawaiian or Pacific Islander", "White", "Two or more races", DECLINE],
  veteran_status: ["", "I am a protected veteran", "I am not a protected veteran", DECLINE],
  disability_status: ["", "Yes, I have a disability", "No, I do not have a disability", DECLINE],
};
const EEO_LABELS = {
  gender: "Gender", race_ethnicity: "Race / Ethnicity",
  veteran_status: "Veteran status", disability_status: "Disability status",
};

export default function ApplicationAnswers({ value, onChange }) {
  const elig = value?.eligibility || {};
  const eeo = value?.eeo || {};
  const setElig = (k, v) => onChange({ eligibility: { ...elig, [k]: v }, eeo });
  const setEeo = (k, v) => onChange({ eligibility: elig, eeo: { ...eeo, [k]: v } });

  return (
    <div className="application-answers">
      <h4>Eligibility</h4>
      <label>Authorized to work (US)?
        <select value={elig.work_authorized || ""} onChange={(e) => setElig("work_authorized", e.target.value)}>
          {YES_NO.map((o) => <option key={o} value={o} style={{ color: "black" }}>{o || "—"}</option>)}
        </select>
      </label>
      <label>Require sponsorship?
        <select value={elig.requires_sponsorship || ""} onChange={(e) => setElig("requires_sponsorship", e.target.value)}>
          {YES_NO.map((o) => <option key={o} value={o} style={{ color: "black" }}>{o || "—"}</option>)}
        </select>
      </label>
      <label>Willing to relocate?
        <select value={elig.willing_to_relocate || ""} onChange={(e) => setElig("willing_to_relocate", e.target.value)}>
          {YES_NO.map((o) => <option key={o} value={o} style={{ color: "black" }}>{o || "—"}</option>)}
        </select>
      </label>
      <label>Earliest start date
        <input value={elig.start_date || ""} onChange={(e) => setElig("start_date", e.target.value)} />
      </label>
      <label>Years of experience
        <input value={elig.years_experience || ""} onChange={(e) => setElig("years_experience", e.target.value)} />
      </label>

      <h4>EEO self-identification (voluntary)</h4>
      {Object.keys(EEO_OPTIONS).map((k) => (
        <label key={k}>{EEO_LABELS[k]}
          <select value={eeo[k] || ""} onChange={(e) => setEeo(k, e.target.value)}>
            {EEO_OPTIONS[k].map((o) => <option key={o} value={o} style={{ color: "black" }}>{o || "—"}</option>)}
          </select>
        </label>
      ))}
    </div>
  );
}
```

Mount it in the settings/profile host, tier-gated to friends_family/beta, wiring `value` from the loaded profile's `application_answers` and persisting via the existing profile PUT (include `application_answers` in the saved blob).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd react-dashboard && npm test -- ApplicationAnswers`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/ApplicationAnswers.jsx react-dashboard/src/components/widgets/ApplicationAnswers.test.jsx react-dashboard/src/api.js
git commit -m "[feat] Add application-answers settings section (eligibility + EEO)"
```

---

### Task 11: Extension — read-only form enumeration + soft nudge

**Files:**
- Create: `browser-extension/content/form_enumerate.js`
- Modify: `browser-extension/content/injector.js` (invoke enumeration on recognized apply pages; POST via service worker)
- Modify: `browser-extension/background/service_worker.js` (add `ENUMERATE_FORM`/plan-POST message handler; reuse `getServer()` + bearer)
- Modify: `browser-extension/manifest.json` (host permissions for the supported ATS apply domains: `*.greenhouse.io`, `*.lever.co`, `*.ashbyhq.com`)
- Modify: `browser-extension/CONTEXT.md` (document the read-only enumeration + nudge + selector fragility)

**Testing:** Manual smoke test only, consistent with the existing extension posture (selectors are not unit-tested). Add smoke steps to `browser-extension/CONTEXT.md` under a new "Application-plan enumeration — PENDING smoke test" entry.

- [ ] **Step 1: Implement `form_enumerate.js`**

A single exported function that walks the page's primary `<form>` and returns `EnumeratedField[]`:

```js
// browser-extension/content/form_enumerate.js
// Read-only enumeration of a live application form. No writing (sub-project 3).
function enumerateForm() {
  const form = document.querySelector("form") || document.body;
  const controls = form.querySelectorAll("input, select, textarea");
  const out = [];
  for (const el of controls) {
    const type = (el.type || el.tagName).toLowerCase();
    if (["hidden", "submit", "button", "search"].includes(type)) continue;
    const id = el.name || el.id || (el.getAttribute("aria-label") || "").slice(0, 60);
    if (!id) continue;
    out.push({
      field_id: id,
      label: labelFor(el),
      input_type: type,
      options: el.tagName === "SELECT" ? [...el.options].map((o) => o.textContent.trim()) : [],
      required: !!el.required,
    });
  }
  return out;
}

function labelFor(el) {
  if (el.id) {
    const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (lab) return lab.textContent.trim();
  }
  const wrap = el.closest("label");
  if (wrap) return wrap.textContent.trim();
  return el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name || "";
}
```

- [ ] **Step 2: Wire enumeration → POST in `injector.js` + `service_worker.js`**

On a recognized apply page for a job already staged (matched by URL/job_key), call `enumerateForm()` and send an `ENUMERATE_FORM` message with `{ job_key, enumerated_fields }`. The service worker POSTs to `${getServer()}/api/scraper/jobs/${job_key}/application-plan` with the bearer token (same auth path as `ats-resolution`). Follow the existing `SCRAPE_JOB` handler shape exactly.

- [ ] **Step 3: Soft nudge**

After a plan POST, if the response route also exposed completeness (or via a `GET .../application-plan`), and `application_answers_complete` is false, show a non-blocking banner in the injected UI: "Complete your application answers to auto-fill more →" linking to `${server}/#/settings` (the answers section). No blocking behavior.

- [ ] **Step 4: manifest + CONTEXT**

Add the three ATS host permissions to `manifest.json`. Document the feature, the soft nudge, and the selector-fragility caveat in `browser-extension/CONTEXT.md`, plus a PENDING smoke-test checklist (enumerate a real Greenhouse/Lever/Ashby form, confirm the POST lands, confirm the plan modal shows the fields, confirm the nudge appears when answers are incomplete).

- [ ] **Step 5: Commit**

```bash
git add browser-extension/
git commit -m "[feat] Add read-only application-form enumeration + soft nudge to extension"
```

---

### Task 12: Docs sync (CONTEXT.md + ARCHITECTURE pointers) + full-suite gate

**Files:**
- Modify: `core/CONTEXT.md`, `web/CONTEXT.md`, `react-dashboard/CONTEXT.md`, `.claude/CLAUDE.md` routing table, `.claude/TODO.md`.

> This is the merge-time doc-sync; the `merge-to-main` skill enforces it. Keep it in this plan so no task is left implicit.

- [ ] **Step 1: Run the full backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS (note the two known pre-existing order-dependent failures tracked in TODO Bugs; nothing new should fail).

- [ ] **Step 2: Run the frontend suite**

Run: `cd react-dashboard && npm test`
Expected: PASS.

- [ ] **Step 3: Update docs**

- `core/CONTEXT.md`: add `application_fields.py`, `application_classify.py`, `ats_schemas.py`, `application_mapper.py`, and the `map_fields` price to the file table + a short "Field-mapping engine" section.
- `web/CONTEXT.md`: document the two `/api/scraper/jobs/{job_key}/application-plan` routes, `map_fields` metering, and `application_plan_service`.
- `react-dashboard/CONTEXT.md`: add `ApplicationPlanModal.jsx` + `ApplicationAnswers.jsx` to the routing table.
- `.claude/CLAUDE.md`: add a routing row for the field-mapping engine (`core/application_*.py`, `core/ats_schemas.py`).
- `.claude/TODO.md`: mark sub-project 2 implemented; note the PENDING extension smoke test.

- [ ] **Step 4: Commit**

```bash
git add core/CONTEXT.md web/CONTEXT.md react-dashboard/CONTEXT.md .claude/CLAUDE.md .claude/TODO.md
git commit -m "[docs] Sync docs for field-mapping engine (sub-project 2)"
```

---

## Self-Review Notes

- **Spec coverage:** taxonomy (T1), EEO guard/classifier (T2), application-answers profile section + completeness (T3), static schemas greenhouse/lever/ashby (T4), Pydantic models (T5), engine with injected essay drafter (T6), DB column+migration (T7), endpoints+metering+drafter (T8), plan modal (T9), answers UI (T10), extension enumeration+nudge (T11), docs+gate (T12). All spec sections map to a task.
- **EEO safety:** enforced in two places — `classify_custom` (T2) and `build_plan`'s explicit `is_eeo_label` branch before the essay bucket (T6); `needs_essay_pass` also excludes EEO so metering never triggers on a demographic-only form.
- **Metering:** `map_fields` charged only when `needs_essay_pass` is true (T6/T8), satisfying the "deterministic-only plans not metered" constraint.
- **Type consistency:** `build_plan`/`needs_essay_pass`/`EssayDrafter` signatures match between T6 (definition) and T8 (call site); `EnumeratedField`/`PlannedField`/`ApplicationPlan` fields match between T5 and consumers.
- **Tenant scoping:** every endpoint uses `Job.get(job_key, db, profile_id=profile_id)` (T8), 404 on miss — cross-tenant test included.
