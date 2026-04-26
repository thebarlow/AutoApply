# Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the generator module that reads approved jobs from SQLite, generates tailored resume and cover letter PDFs via Claude + Pandoc, writes artifact paths back to the job record, and transitions state `approved` → `generated` (or `failed` on error), triggered as a background thread by the Review Queue PATCH handler.

**Architecture:** `generator/generator.py` owns the full pipeline as a set of pure functions plus a `generate_job` entry point that manages its own DB session. The PATCH handler in `web/routers/jobs.py` spawns a daemon thread on approve. Prompt templates live in the `config` table (seeded by `db/seed.py`) and are loaded at runtime — no file dependencies. LaTeX templates for PDF rendering live in `generator/templates/`.

**Tech Stack:** Python, Anthropic SDK, SQLAlchemy, Pandoc + XeLaTeX, pytest + monkeypatch

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `db/seed.py` | Modify | Add prompt templates + contact link keys to `DEFAULT_CONFIG` |
| `generator/__init__.py` | Create | Package marker |
| `generator/templates/resume_template.tex` | Create | LaTeX resume template (copied from skill) |
| `generator/templates/cover_template.tex` | Create | LaTeX cover letter template (copied from skill) |
| `generator/generator.py` | Create | Full generation pipeline |
| `web/routers/jobs.py` | Modify | Spawn daemon thread on approve |
| `tests/generator/__init__.py` | Create | Package marker |
| `tests/generator/test_generator.py` | Create | All generator tests |
| `tests/db/test_models.py` | Modify | Add seed tests for new config keys |
| `tests/web/test_jobs_api.py` | Modify | Add thread-spawning tests |

---

### Task 1: Seed prompt templates and contact links

**Files:**
- Modify: `db/seed.py`
- Modify: `tests/db/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/db/test_models.py`:

```python
def test_resume_prompt_template_seeded(db_session):
    seed_default_config(db_session)
    row = db_session.query(Config).filter_by(key="resume_prompt_template").first()
    assert row is not None
    assert "{profile}" in row.value
    assert "{job}" in row.value


def test_cover_prompt_template_seeded(db_session):
    seed_default_config(db_session)
    row = db_session.query(Config).filter_by(key="cover_prompt_template").first()
    assert row is not None
    assert "{profile}" in row.value
    assert "{job}" in row.value


def test_contact_link_keys_seeded(db_session):
    seed_default_config(db_session)
    for key in ("resume_github", "resume_linkedin", "resume_website"):
        row = db_session.query(Config).filter_by(key=key).first()
        assert row is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/db/test_models.py::test_resume_prompt_template_seeded tests/db/test_models.py::test_cover_prompt_template_seeded tests/db/test_models.py::test_contact_link_keys_seeded -v
```

Expected: 3 FAIL — `AssertionError: assert None is not None`

- [ ] **Step 3: Add new keys to DEFAULT_CONFIG in db/seed.py**

Replace the entire `DEFAULT_CONFIG` dict in `db/seed.py`:

```python
DEFAULT_CONFIG: dict[str, str] = {
    "w1": "0.5",
    "w2": "0.5",
    "auto_reject_threshold": "0.3",
    "auto_approve_threshold": "0.8",
    "keywords_whitelist": "[]",
    "keywords_blacklist": "[]",
    "location": "",
    "remote_only": "true",
    "full_time_only": "true",
    "target_salary_min": "0",
    "benefits_priorities": "[]",
    "resume_github": "",
    "resume_linkedin": "",
    "resume_website": "",
    "resume_prompt_template": (
        "You are writing a tailored one-page resume in Markdown for a job application.\n\n"
        "# Candidate Profile\n{profile}\n\n"
        "# Job Posting\n{job}\n\n"
        "# Instructions\n"
        "- Output ONLY the resume Markdown body. No preamble, no explanation.\n"
        "- Do NOT include a name or contact block — those are handled separately.\n"
        "- Start directly with the first section header (e.g. ## Profile).\n"
        "- Do not use `---` horizontal rules between sections.\n"
        "- Do not invent experience or skills not in the candidate profile.\n"
        "- Drop the Soft Skills section entirely.\n\n"
        "## Profile\n"
        "- Max 500 characters total.\n\n"
        "## Education\n"
        "- Always include all degrees exactly as written. No bullets.\n\n"
        "## Experience\n"
        "- Always include all entries.\n"
        "- Max 2 bullets per entry, each bullet max 120 characters.\n"
        "- Stress skills and responsibilities directly mentioned in the job description.\n\n"
        "## Projects\n"
        "- Reorder by relevance to this job. Drop least relevant project(s) if needed.\n"
        "- Always include at least 2, max 4 projects.\n"
        "- 1 bullet per project, max 120 characters.\n\n"
        "## Skills\n"
        "- Always include Python, Git, Docker, SQL regardless of job description.\n"
        "- Include only categories that have 2 or more relevant skills for this job.\n"
        "- If a category has only 1 relevant skill, fold it into the nearest adjacent category.\n"
        "- Sort categories by relevance to the job description.\n"
        "- Within each category, list skills directly mentioned in the job description first.\n"
        "- Max 6 categories."
    ),
    "cover_prompt_template": (
        "You are writing a concise cover letter in Markdown for a job application.\n\n"
        "# Candidate Profile\n{profile}\n\n"
        "# Job Posting\n{job}\n\n"
        "# Instructions\n"
        "- Output ONLY the cover letter Markdown. No preamble, no explanation.\n"
        "- Do not use `---` horizontal rules anywhere in the output.\n"
        "- Exactly 3 paragraphs: (1) fit and interest, (2) specific value-add tied to the job description, (3) close.\n"
        "- Address it to the hiring team at the company listed in the job posting.\n"
        "- Do not include a sign-off, name, or contact information at the end — those are added automatically.\n"
        "- Do not invent experience or skills not in the candidate profile."
    ),
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/db/test_models.py::test_resume_prompt_template_seeded tests/db/test_models.py::test_cover_prompt_template_seeded tests/db/test_models.py::test_contact_link_keys_seeded -v
```

Expected: 3 PASS

- [ ] **Step 5: Run full suite to check no regressions**

```bash
pytest -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add db/seed.py tests/db/test_models.py
git commit -m "[feat] Seed resume/cover prompt templates and contact link keys"
```

---

### Task 2: generator package + prompt building functions

**Files:**
- Create: `generator/__init__.py`
- Create: `generator/generator.py` (prompt functions only — rendering and pipeline added in Tasks 3–4)
- Create: `tests/generator/__init__.py`
- Create: `tests/generator/test_generator.py` (prompt tests only)

- [ ] **Step 1: Create package markers**

Create `generator/__init__.py` (empty) and `tests/generator/__init__.py` (empty).

- [ ] **Step 2: Write the failing prompt tests**

Create `tests/generator/test_generator.py`:

```python
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock

from core.types import JobState, UserProfile, WorkHistoryEntry, EducationEntry
from db.models import Base, Job, Config, UserProfileModel
from generator.generator import (
    build_resume_prompt,
    build_cover_prompt,
    strip_header_block,
    call_claude,
    generate_job,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _make_profile() -> UserProfile:
    return UserProfile(
        name="Jane Doe",
        email="jane@example.com",
        phone="555-0100",
        location="Remote",
        skills=["Python", "SQL"],
        work_history=[
            WorkHistoryEntry(
                company="Corp", title="Dev", start="2020", end="2023",
                summary="Built data pipelines."
            )
        ],
        education=[
            EducationEntry(
                institution="MIT", degree="BS", field="CS",
                graduated="2020", gpa=3.8
            )
        ],
        target_salary_min=100000,
        target_salary_max=150000,
        target_roles=["SWE"],
        resume_path="",
    )


def _make_job_obj() -> Job:
    return Job(
        job_key="test_job",
        source="indeed",
        url="https://example.com/1",
        state=JobState.APPROVED.value,
        title="Senior Software Engineer",
        company="Acme Corp",
        location="Remote",
        salary="$140,000",
        description="We need Python and SQL expertise.",
    )


def test_build_resume_prompt_contains_job_fields():
    job = _make_job_obj()
    profile = _make_profile()
    template = "Profile:\n{profile}\nJob:\n{job}"
    result = build_resume_prompt(job, profile, template)
    assert "Senior Software Engineer" in result
    assert "Acme Corp" in result
    assert "Python and SQL expertise" in result


def test_build_resume_prompt_contains_profile_fields():
    job = _make_job_obj()
    profile = _make_profile()
    template = "{profile}\n{job}"
    result = build_resume_prompt(job, profile, template)
    assert "Jane Doe" in result
    assert "Python" in result
    assert "Corp" in result
    assert "MIT" in result
    assert "Built data pipelines" in result


def test_build_cover_prompt_contains_job_and_profile():
    job = _make_job_obj()
    profile = _make_profile()
    template = "{profile}\n{job}"
    result = build_cover_prompt(job, profile, template)
    assert "Jane Doe" in result
    assert "Acme Corp" in result
    assert "Python and SQL expertise" in result
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/generator/test_generator.py::test_build_resume_prompt_contains_job_fields tests/generator/test_generator.py::test_build_resume_prompt_contains_profile_fields tests/generator/test_generator.py::test_build_cover_prompt_contains_job_and_profile -v
```

Expected: ERROR — `ModuleNotFoundError: No module named 'generator.generator'`

- [ ] **Step 4: Create generator/generator.py with prompt building functions**

Create `generator/generator.py`:

```python
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

from core.types import JobState, UserProfile, WorkHistoryEntry, EducationEntry
from db.database import SessionLocal
from db.models import Config, Job, UserProfileModel

_GENERATOR_DIR = Path(__file__).parent
_OUTPUTS_DIR = _GENERATOR_DIR.parent / "jobs" / "outputs"
RESUME_TEMPLATE_PATH = _GENERATOR_DIR / "templates" / "resume_template.tex"
COVER_TEMPLATE_PATH = _GENERATOR_DIR / "templates" / "cover_template.tex"


def _render_profile(profile: UserProfile) -> str:
    work = "\n".join(
        f"- {e.title} at {e.company} ({e.start}–{e.end}): {e.summary}"
        for e in profile.work_history
    )
    education = "\n".join(
        f"- {e.degree} in {e.field} from {e.institution} ({e.graduated}), GPA {e.gpa}"
        for e in profile.education
    )
    return (
        f"Name: {profile.name}\n"
        f"Target roles: {', '.join(profile.target_roles)}\n"
        f"Target salary: ${profile.target_salary_min}–${profile.target_salary_max}\n"
        f"Skills: {', '.join(profile.skills)}\n\n"
        f"Work History:\n{work}\n\n"
        f"Education:\n{education}"
    )


def _render_job(job: Job) -> str:
    return (
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location or 'Not specified'}\n"
        f"Salary: {job.salary or 'Not specified'}\n"
        f"Description:\n{job.description or 'Not provided'}"
    )


def build_resume_prompt(job: Job, profile: UserProfile, template: str) -> str:
    return template.format(profile=_render_profile(profile), job=_render_job(job))


def build_cover_prompt(job: Job, profile: UserProfile, template: str) -> str:
    return template.format(profile=_render_profile(profile), job=_render_job(job))


def _build_frontmatter(
    profile: UserProfile,
    github: str = "",
    linkedin: str = "",
    website: str = "",
) -> str:
    parts = profile.name.split(" ", 1)
    firstname = parts[0]
    lastname = parts[1] if len(parts) > 1 else ""
    lines = [
        "---",
        f"name: {profile.name}",
        f"firstname: {firstname}",
        f"lastname: {lastname}",
        f"email: {profile.email}",
        f"phone: {profile.phone}",
        f"location: {profile.location}",
    ]
    if github:
        lines.append(f"github: {github}")
    if linkedin:
        lines.append(f"linkedin: {linkedin}")
    if website:
        lines.append(f"website: {website}")
    lines.extend(["---", ""])
    return "\n".join(lines) + "\n"


def strip_header_block(md: str) -> str:
    """Remove name/contact header if Claude included one despite instructions."""
    lines = md.splitlines()
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines):
            if lines[i].strip() == "---":
                i += 1
                break
            i += 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("## "):
            break
        if i >= 10:
            break
        i += 1
    return "\n".join(lines[i:])


def call_claude(prompt: str, client: anthropic.Anthropic) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def render_pdf(md_path: Path, pdf_path: Path, template_path: Path) -> None:
    subprocess.run(
        [
            "pandoc", str(md_path),
            "-o", str(pdf_path),
            "--pdf-engine=xelatex",
            f"--template={template_path}",
        ],
        check=True,
    )


def _get_page_count(pdf_path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    raise RuntimeError(f"Could not determine page count for {pdf_path.name}")


def render_resume_pdf(md_path: Path, pdf_path: Path, job_key: str) -> None:
    """Render resume PDF, reducing font/margins to fit one page if needed."""
    attempts = [
        {"fontsize": "11pt", "top": "1.0in", "bottom": "1.0in"},
        {"fontsize": "10pt", "top": "1.0in", "bottom": "1.0in"},
        {"fontsize": "10pt", "top": "0.8in", "bottom": "0.8in"},
    ]
    template_text = RESUME_TEMPLATE_PATH.read_text(encoding="utf-8")
    for s in attempts:
        modified = re.sub(
            r"\\documentclass\[\d+pt\]",
            f"\\\\documentclass[{s['fontsize']}]",
            template_text,
        )
        modified = re.sub(
            r"top=[\d.]+in, bottom=[\d.]+in",
            f"top={s['top']}, bottom={s['bottom']}",
            modified,
        )
        with tempfile.NamedTemporaryFile(
            suffix=".tex", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(modified)
            tmp = Path(f.name)
        try:
            render_pdf(md_path, pdf_path, tmp)
            if _get_page_count(pdf_path) <= 1:
                return
        finally:
            tmp.unlink(missing_ok=True)
    raise RuntimeError(
        f"Resume '{job_key}' exceeds 1 page at minimum settings (10pt, 0.8in margins)."
    )


def generate_job(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[anthropic.Anthropic] = None,
) -> None:
    """Generate resume and cover letter for an approved job. Thread entry point."""
    own_db = db is None
    if own_db:
        db = SessionLocal()
    if client is None:
        client = anthropic.Anthropic()

    try:
        job = db.query(Job).filter_by(job_key=job_key).first()
        if job is None:
            return

        row = db.query(UserProfileModel).first()
        if not row:
            raise RuntimeError("No user profile found in DB.")
        data = json.loads(row.data)
        data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
        data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
        profile = UserProfile(**data)

        resume_tpl = db.query(Config).filter_by(key="resume_prompt_template").first()
        cover_tpl = db.query(Config).filter_by(key="cover_prompt_template").first()
        if not resume_tpl or not cover_tpl:
            raise RuntimeError("Prompt templates not seeded in config table.")

        def _cfg(key: str) -> str:
            r = db.query(Config).filter_by(key=key).first()
            return r.value if r else ""

        frontmatter = _build_frontmatter(
            profile,
            github=_cfg("resume_github"),
            linkedin=_cfg("resume_linkedin"),
            website=_cfg("resume_website"),
        )

        outputs = _OUTPUTS_DIR
        outputs.mkdir(parents=True, exist_ok=True)

        resume_md_path = outputs / f"{job_key}_resume.md"
        resume_pdf_path = outputs / f"{job_key}_resume.pdf"
        resume_md = strip_header_block(call_claude(build_resume_prompt(job, profile, resume_tpl.value), client))
        resume_md_path.write_text(frontmatter + resume_md, encoding="utf-8")
        render_resume_pdf(resume_md_path, resume_pdf_path, job_key)

        cover_md_path = outputs / f"{job_key}_cover.md"
        cover_pdf_path = outputs / f"{job_key}_cover.pdf"
        cover_md = call_claude(build_cover_prompt(job, profile, cover_tpl.value), client)
        cover_md_path.write_text(frontmatter + cover_md, encoding="utf-8")
        render_pdf(cover_md_path, cover_pdf_path, COVER_TEMPLATE_PATH)

        job.resume_path = str(resume_pdf_path)
        job.cover_path = str(cover_pdf_path)
        job.state = JobState.GENERATED.value
        db.commit()

    except Exception as e:
        print(f"[generator] ERROR for {job_key}: {e}", file=sys.stderr)
        try:
            job = db.query(Job).filter_by(job_key=job_key).first()
            if job:
                job.state = JobState.FAILED.value
                db.commit()
        except Exception:
            pass
    finally:
        if own_db:
            db.close()
```

- [ ] **Step 5: Run prompt tests to verify they pass**

```bash
pytest tests/generator/test_generator.py::test_build_resume_prompt_contains_job_fields tests/generator/test_generator.py::test_build_resume_prompt_contains_profile_fields tests/generator/test_generator.py::test_build_cover_prompt_contains_job_and_profile -v
```

Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add generator/__init__.py generator/generator.py tests/generator/__init__.py tests/generator/test_generator.py
git commit -m "[feat] Add generator package with prompt building functions"
```

---

### Task 3: strip_header_block + call_claude tests + LaTeX templates

**Files:**
- Modify: `tests/generator/test_generator.py`
- Create: `generator/templates/resume_template.tex`
- Create: `generator/templates/cover_template.tex`

- [ ] **Step 1: Copy LaTeX templates into the project**

```bash
mkdir -p generator/templates
cp ~/.claude/skills/generate-resume/references/templates/resume_template.tex generator/templates/resume_template.tex
cp ~/.claude/skills/generate-resume/references/templates/cover_template.tex generator/templates/cover_template.tex
```

Expected: both files exist with non-zero size:
```bash
ls -lh generator/templates/
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/generator/test_generator.py`:

```python
def test_strip_header_block_removes_yaml_frontmatter():
    md = "---\nname: John\n---\n## Profile\nSome content"
    result = strip_header_block(md)
    assert result.startswith("## Profile")
    assert "name: John" not in result


def test_strip_header_block_passthrough_when_no_header():
    md = "## Profile\nSome content"
    result = strip_header_block(md)
    assert result == md


def test_call_claude_returns_stripped_text():
    mock_client = MagicMock()
    mock_client.messages.create.return_value.content = [MagicMock(text="  Hello world  ")]
    result = call_claude("some prompt", mock_client)
    assert result == "Hello world"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/generator/test_generator.py::test_strip_header_block_removes_yaml_frontmatter tests/generator/test_generator.py::test_strip_header_block_passthrough_when_no_header tests/generator/test_generator.py::test_call_claude_returns_stripped_text -v
```

Expected: 3 FAIL — `ImportError` (strip_header_block and call_claude not yet importable since generator.py doesn't exist yet in this task... wait, it was created in Task 2). These should FAIL with `ImportError` only if generator.py wasn't created yet. Since Task 2 creates it, these should actually FAIL for a different reason — strip_header_block is already implemented so these might pass. Run and see.

Actually `strip_header_block` and `call_claude` are both implemented in Task 2's `generator.py`. The tests may pass immediately. If they do, that confirms the implementation is correct — proceed to commit.

- [ ] **Step 4: Run tests**

```bash
pytest tests/generator/test_generator.py::test_strip_header_block_removes_yaml_frontmatter tests/generator/test_generator.py::test_strip_header_block_passthrough_when_no_header tests/generator/test_generator.py::test_call_claude_returns_stripped_text -v
```

Expected: 3 PASS (implementation was correct from Task 2)

- [ ] **Step 5: Commit**

```bash
git add generator/templates/ tests/generator/test_generator.py
git commit -m "[feat] Add LaTeX templates and header-strip/call-claude tests"
```

---

### Task 4: generate_job state transition tests

**Files:**
- Modify: `tests/generator/test_generator.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/generator/test_generator.py`:

```python
def _seed_db(db_session) -> None:
    """Seed minimal config, profile, and an approved job for generator tests."""
    db_session.add(Config(key="resume_prompt_template", value="Resume: {profile}\n{job}"))
    db_session.add(Config(key="cover_prompt_template", value="Cover: {profile}\n{job}"))
    db_session.add(Config(key="resume_github", value=""))
    db_session.add(Config(key="resume_linkedin", value=""))
    db_session.add(Config(key="resume_website", value=""))
    profile_data = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "555-0100",
        "location": "Remote",
        "skills": ["Python"],
        "work_history": [],
        "education": [],
        "target_salary_min": 100000,
        "target_salary_max": 150000,
        "target_roles": ["SWE"],
        "resume_path": "",
    }
    db_session.add(UserProfileModel(data=json.dumps(profile_data)))
    db_session.add(Job(
        job_key="test_job",
        source="indeed",
        url="https://example.com/job/1",
        state=JobState.APPROVED.value,
        title="SWE",
        company="Acme",
        description="Python required.",
    ))
    db_session.commit()


def test_generate_job_transitions_to_generated(db_session, monkeypatch, tmp_path):
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.call_claude", lambda prompt, client: "## Profile\nContent here")
    monkeypatch.setattr("generator.generator.render_resume_pdf", lambda *a, **kw: None)
    monkeypatch.setattr("generator.generator.render_pdf", lambda *a, **kw: None)

    generate_job("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.GENERATED.value
    assert job.resume_path is not None
    assert job.cover_path is not None


def test_generate_job_transitions_to_failed_on_claude_error(db_session, monkeypatch, tmp_path):
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)

    def _raise(*a, **kw):
        raise RuntimeError("API error")

    monkeypatch.setattr("generator.generator.call_claude", _raise)

    generate_job("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.FAILED.value


def test_generate_job_transitions_to_failed_on_render_error(db_session, monkeypatch, tmp_path):
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.call_claude", lambda prompt, client: "## Profile\nContent here")

    def _raise(*a, **kw):
        raise RuntimeError("Pandoc failed")

    monkeypatch.setattr("generator.generator.render_resume_pdf", _raise)

    generate_job("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.FAILED.value


def test_generate_job_fails_if_template_missing(db_session, monkeypatch, tmp_path):
    profile_data = {
        "name": "Jane Doe", "email": "jane@example.com", "phone": "555-0100",
        "location": "Remote", "skills": [], "work_history": [], "education": [],
        "target_salary_min": None, "target_salary_max": None,
        "target_roles": [], "resume_path": "",
    }
    db_session.add(UserProfileModel(data=json.dumps(profile_data)))
    db_session.add(Job(
        job_key="no_tpl",
        source="indeed",
        url="https://example.com/job/2",
        state=JobState.APPROVED.value,
        title="SWE",
        company="Acme",
    ))
    db_session.commit()
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)

    generate_job("no_tpl", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="no_tpl").first()
    assert job.state == JobState.FAILED.value
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/generator/test_generator.py::test_generate_job_transitions_to_generated tests/generator/test_generator.py::test_generate_job_transitions_to_failed_on_claude_error tests/generator/test_generator.py::test_generate_job_transitions_to_failed_on_render_error tests/generator/test_generator.py::test_generate_job_fails_if_template_missing -v
```

Expected: 4 FAIL — errors related to missing imports or `generate_job` not defined (since it was stubbed in Task 2 but the tests are new)

Actually `generate_job` IS fully implemented in Task 2's generator.py. These tests should pass if the implementation is correct. Run them and verify.

- [ ] **Step 3: Run tests**

```bash
pytest tests/generator/test_generator.py -v
```

Expected: all tests in the file PASS

- [ ] **Step 4: Run full suite**

```bash
pytest -q
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tests/generator/test_generator.py
git commit -m "[test] Add generate_job state transition tests"
```

---

### Task 5: Spawn background thread on approve

**Files:**
- Modify: `web/routers/jobs.py`
- Modify: `tests/web/test_jobs_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/web/test_jobs_api.py`:

```python
def test_approve_spawns_generation_thread(client, db_session, monkeypatch):
    _make_job(db_session, "job_gen", JobState.PENDING_REVIEW)

    spawned = []

    class MockThread:
        def __init__(self, target, args, daemon):
            spawned.append({"target": target.__name__, "args": args})

        def start(self):
            pass

    monkeypatch.setattr("threading.Thread", MockThread)

    resp = client.patch("/api/jobs/job_gen/state", json={"state": "approved"})
    assert resp.status_code == 200
    assert len(spawned) == 1
    assert spawned[0]["target"] == "generate_job"
    assert spawned[0]["args"] == ("job_gen",)


def test_reject_does_not_spawn_thread(client, db_session, monkeypatch):
    _make_job(db_session, "job_rej", JobState.PENDING_REVIEW)

    spawned = []

    class MockThread:
        def __init__(self, **kwargs):
            spawned.append(kwargs)

        def start(self):
            pass

    monkeypatch.setattr("threading.Thread", MockThread)

    resp = client.patch("/api/jobs/job_rej/state", json={"state": "rejected"})
    assert resp.status_code == 200
    assert len(spawned) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/web/test_jobs_api.py::test_approve_spawns_generation_thread tests/web/test_jobs_api.py::test_reject_does_not_spawn_thread -v
```

Expected: 2 FAIL — `AssertionError: assert 0 == 1` (no thread spawned yet)

- [ ] **Step 3: Modify web/routers/jobs.py to spawn thread on approve**

Replace the full contents of `web/routers/jobs.py`:

```python
from __future__ import annotations

import json
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.types import JobState
from db.database import get_db
from db.models import Job
from generator.generator import generate_job

router = APIRouter(prefix="/api/jobs")

_ALLOWED_PATCH_STATES = {JobState.APPROVED.value, JobState.REJECTED.value}


class StateUpdate(BaseModel):
    state: str


def _serialize(job: Job) -> dict[str, Any]:
    justification = job.score_justification
    if isinstance(justification, str):
        try:
            justification = json.loads(justification)
        except (json.JSONDecodeError, TypeError):
            justification = {}

    return {
        "job_key": job.job_key,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "salary": job.salary,
        "state": job.state,
        "desirability_score": job.desirability_score,
        "fit_score": job.fit_score,
        "final_score": job.final_score,
        "score_justification": justification,
    }


@router.get("")
def get_jobs(state: str = JobState.PENDING_REVIEW.value, db: Session = Depends(get_db)):
    jobs = (
        db.query(Job)
        .filter(Job.state == state)
        .order_by(Job.final_score.desc())
        .all()
    )
    return [_serialize(j) for j in jobs]


@router.patch("/{job_key}/state")
def update_job_state(job_key: str, body: StateUpdate, db: Session = Depends(get_db)):
    if body.state not in _ALLOWED_PATCH_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state: {body.state!r}")

    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job.state = body.state
    db.commit()
    db.refresh(job)

    if job.state == JobState.APPROVED.value:
        t = threading.Thread(target=generate_job, args=(job_key,), daemon=True)
        t.start()

    return _serialize(job)
```

- [ ] **Step 4: Run the two new tests to verify they pass**

```bash
pytest tests/web/test_jobs_api.py::test_approve_spawns_generation_thread tests/web/test_jobs_api.py::test_reject_does_not_spawn_thread -v
```

Expected: 2 PASS

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add web/routers/jobs.py tests/web/test_jobs_api.py
git commit -m "[feat] Spawn generation thread on job approve"
```

---

## Self-Review

**Spec coverage:**
- ✅ Reads approved jobs from SQLite — `generate_job` queries by `job_key`
- ✅ Loads prompt templates from config table — keys `resume_prompt_template`, `cover_prompt_template`
- ✅ Builds prompts from UserProfile + Job — `build_resume_prompt`, `build_cover_prompt`, `_render_profile`, `_render_job`
- ✅ Calls Anthropic SDK — `call_claude` using `claude-sonnet-4-6`
- ✅ Renders PDFs via Pandoc+XeLaTeX — `render_pdf`, `render_resume_pdf` with 1-page fit logic
- ✅ Writes artifact paths back to job record — `job.resume_path`, `job.cover_path`
- ✅ State `approved` → `generated` on success
- ✅ State → `failed` on any exception, with stderr logging
- ✅ Background thread spawned by PATCH handler, returns immediately
- ✅ Thread opens own DB session via `SessionLocal()`
- ✅ Generator fails to `failed` if templates missing from config
- ✅ LaTeX templates in `generator/templates/` — no skill directory dependency
- ✅ Contact links (github, linkedin, website) seeded as empty strings, read from config

**Placeholder scan:** None found.

**Type consistency:**
- `generate_job(job_key, db=None, client=None)` — consistent across Task 2 impl and Task 4/5 tests
- `build_resume_prompt(job, profile, template)` — consistent across impl and tests
- `strip_header_block(md)` — consistent
- `call_claude(prompt, client)` — consistent
- `render_resume_pdf(md_path, pdf_path, job_key)` — consistent
- `render_pdf(md_path, pdf_path, template_path)` — consistent
