# Resume & Cover Letter Refinement Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After generating a resume or cover letter, automatically run an agentic evaluate→rewrite loop that scores quality and improves the document until it passes a configurable threshold or exhausts a turn limit.

**Architecture:** A background thread spawned after generation runs `run_resume_refinement(job_key)` in `web/intake_pipeline.py`. It alternates between an LLM evaluator call (score + issues) and an LLM rewriter call (improved document) using two new `Job` methods. Results are stored as JSON in new DB columns and surfaced in the job preview via SSE. Refinement config (prompts, models, turn limit, pass score, enabled flag) lives in the user profile JSON blob; the enable toggle is a separate click zone on new prompt cards in the Profile UI.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), React/Tailwind (frontend), pytest with `unittest.mock` (tests), SQLite ALTER TABLE migrations (DB).

---

## File Map

| File | Change |
|---|---|
| `db/database.py` | Add `_migrate_resume_eval_columns()`, call from `init_db()` |
| `core/user.py` | Add 14 refinement fields to `_hydrate()`/`_to_dict()`, extend `_PROMPT_LABELS` |
| `prompts/defaults/resume_eval.md` | New — evaluator prompt for resumes |
| `prompts/defaults/cover_eval.md` | New — evaluator prompt for cover letters |
| `prompts/defaults/resume_refine.md` | New — rewriter prompt for resumes |
| `prompts/defaults/cover_refine.md` | New — rewriter prompt for cover letters |
| `web/routers/prompts.py` | Add 4 new type keys to `_VALID_DEFAULT_KEYS` |
| `core/job.py` | Add `_strip_yaml_frontmatter`, `_evaluate_doc_md`, `_refine_doc_md`, 4 public methods, update `serialize()`, 6 new DB columns |
| `web/intake_pipeline.py` | Add `run_resume_refinement()` and `run_cover_refinement()` |
| `web/routers/jobs.py` | Spawn refinement threads after successful generation |
| `react-dashboard/src/components/widgets/ProfileDetail.jsx` | Add `RefinementPromptModal`, 2 new refinement cards in `PromptsSection` |
| `react-dashboard/src/components/widgets/Settings.jsx` | Add eval score chip + per-turn history to resume/cover tab |
| `tests/test_job_refinement.py` | New — unit tests for evaluate/refine methods |

---

## Task 1: DB Migration — Add Eval Columns

**Files:**
- Modify: `db/database.py`

- [ ] **Step 1: Add migration function**

In `db/database.py`, add after `_migrate_flagged_column()`:

```python
def _migrate_resume_eval_columns() -> None:
    """Add resume/cover eval columns for the refinement loop."""
    new_cols = [
        ("resume_eval_score", "REAL"),
        ("resume_eval_turns", "INTEGER"),
        ("resume_eval_log", "TEXT"),
        ("cover_eval_score", "REAL"),
        ("cover_eval_turns", "INTEGER"),
        ("cover_eval_log", "TEXT"),
    ]
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
        for col, typ in new_cols:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} {typ}"))
        conn.commit()
```

- [ ] **Step 2: Call from init_db()**

In `init_db()`, add after `_migrate_flagged_column()`:

```python
_migrate_resume_eval_columns()
```

- [ ] **Step 3: Verify migration runs**

Run: `python -c "from db.database import init_db; init_db(); print('OK')"`

Expected output: `OK` (no errors)

- [ ] **Step 4: Verify columns exist**

```python
python -c "
from db.database import engine
from sqlalchemy import text
with engine.connect() as c:
    cols = [r[1] for r in c.execute(text('PRAGMA table_info(jobs)')).fetchall()]
    for col in ['resume_eval_score','resume_eval_turns','resume_eval_log','cover_eval_score','cover_eval_turns','cover_eval_log']:
        assert col in cols, f'Missing: {col}'
    print('All 6 columns present')
"
```

Expected: `All 6 columns present`

- [ ] **Step 5: Commit**

```bash
git add db/database.py
git commit -m "[feat] Add resume/cover eval columns to jobs table"
```

---

## Task 2: User Profile — Refinement Config Fields

**Files:**
- Modify: `core/user.py`

- [ ] **Step 1: Extend `_PROMPT_LABELS`**

In `core/user.py`, find `_PROMPT_LABELS` and add 4 entries:

```python
_PROMPT_LABELS: dict[str, str] = {
    "scoring": "Scoring",
    "resume": "Resume Generation",
    "cover": "Cover Letter Generation",
    "extraction": "Description Processing",
    "resume_parse": "Resume Parsing",
    "resume_eval": "Resume Evaluator",
    "resume_refine": "Resume Rewriter",
    "cover_eval": "Cover Letter Evaluator",
    "cover_refine": "Cover Letter Rewriter",
}
```

- [ ] **Step 2: Add fields to `_hydrate()`**

In `_hydrate()`, after the existing `for type_key in _PROMPT_TYPES:` block, add:

```python
        # Refinement config — resume
        self.resume_refine_enabled = bool(raw.get("resume_refine_enabled", True))
        self.resume_refine_max_turns = int(raw.get("resume_refine_max_turns", 1))
        self.resume_refine_pass_score = float(raw.get("resume_refine_pass_score", 0.80))
        for rkey in ("resume_eval", "resume_refine", "cover_eval", "cover_refine"):
            field = f"prompt_{rkey}"
            model_field = f"prompt_{rkey}_model"
            setattr(self, field, raw.get(field, ""))
            setattr(self, model_field, raw.get(model_field, ""))
        # Refinement config — cover
        self.cover_refine_enabled = bool(raw.get("cover_refine_enabled", True))
        self.cover_refine_max_turns = int(raw.get("cover_refine_max_turns", 1))
        self.cover_refine_pass_score = float(raw.get("cover_refine_pass_score", 0.80))
```

- [ ] **Step 3: Add fields to `_to_dict()`**

In `_to_dict()`, after the existing `for type_key in _PROMPT_TYPES:` block, add:

```python
        d["resume_refine_enabled"] = self.resume_refine_enabled
        d["resume_refine_max_turns"] = self.resume_refine_max_turns
        d["resume_refine_pass_score"] = self.resume_refine_pass_score
        d["cover_refine_enabled"] = self.cover_refine_enabled
        d["cover_refine_max_turns"] = self.cover_refine_max_turns
        d["cover_refine_pass_score"] = self.cover_refine_pass_score
        for rkey in ("resume_eval", "resume_refine", "cover_eval", "cover_refine"):
            d[f"prompt_{rkey}"] = getattr(self, f"prompt_{rkey}", "")
            d[f"prompt_{rkey}_model"] = getattr(self, f"prompt_{rkey}_model", "")
```

- [ ] **Step 4: Verify defaults**

```python
python -c "
from db.database import init_db, SessionLocal
init_db()
from core.user import User
db = SessionLocal()
user = User.load(db)
assert user.resume_refine_enabled == True
assert user.resume_refine_max_turns == 1
assert user.resume_refine_pass_score == 0.80
assert user.cover_refine_enabled == True
assert hasattr(user, 'prompt_resume_eval')
print('All refinement defaults OK')
db.close()
"
```

Expected: `All refinement defaults OK`

- [ ] **Step 5: Commit**

```bash
git add core/user.py
git commit -m "[feat] Add refinement config fields to user profile"
```

---

## Task 3: Default Prompt Files

**Files:**
- Create: `prompts/defaults/resume_eval.md`
- Create: `prompts/defaults/cover_eval.md`
- Create: `prompts/defaults/resume_refine.md`
- Create: `prompts/defaults/cover_refine.md`

- [ ] **Step 1: Create `prompts/defaults/resume_eval.md`**

```markdown
You are a resume quality evaluator. Score the resume below against the job requirements.
Return ONLY a JSON object — no prose, no code fences.

# Job Requirements
{job.extracted_description}

# Candidate Skills (for hallucination detection)
{user.skills}

# Resume Under Review
{current_resume}

# Output schema
{"score": 0.0, "issues": [{"category": "keyword_coverage|hallucination|structure|tailoring", "description": "..."}]}

Rules:
- score: 0.0 (poor) to 1.0 (excellent). Be calibrated — 0.8 means genuinely strong.
- issues: concrete, actionable, max 15 words each. Empty array if none.
- keyword_coverage: required/preferred job skills absent from the resume.
- hallucination: skills or credentials NOT present in the candidate skills list.
- structure: formatting violations (bullet over 120 chars, missing section, etc.).
- tailoring: generic content that doesn't reflect this specific job or company.
- Maximum 6 issues total.
```

- [ ] **Step 2: Create `prompts/defaults/cover_eval.md`**

```markdown
You are a cover letter quality evaluator. Score the cover letter below against the job requirements.
Return ONLY a JSON object — no prose, no code fences.

# Job Requirements
{job.extracted_description}

# Candidate Skills (for hallucination detection)
{user.skills}

# Cover Letter Under Review
{current_resume}

# Output schema
{"score": 0.0, "issues": [{"category": "personalization|hallucination|tone|call_to_action", "description": "..."}]}

Rules:
- score: 0.0 (poor) to 1.0 (excellent). Be calibrated — 0.8 means genuinely strong.
- issues: concrete, actionable, max 15 words each. Empty array if none.
- personalization: generic content not tailored to the company or role.
- hallucination: skills or credentials NOT present in the candidate skills list.
- tone: mismatch between letter tone and company signals.
- call_to_action: missing or weak closing statement.
- Maximum 6 issues total.
```

- [ ] **Step 3: Create `prompts/defaults/resume_refine.md`**

```markdown
You are rewriting a resume to address specific quality issues. Produce an improved resume.

# Applicant Details
Hero: {user.hero}
Skills: {user.skills}
Work Experience: {user.work_history}
Projects: {user.projects}

# Job Posting
Title: {job.title}
Company: {job.company}
{job.extracted_description}

# Current Resume (improve this)
{current_resume}

# Issues to Fix
{critique}

# Instructions
- Address every issue listed above.
- Do NOT invent experience, skills, or credentials not present in the applicant details.
- Output ONLY the resume Markdown body. No preamble, no explanation.
- Do NOT include a name or contact block.
- Start directly with the first section header (e.g. ## Profile).
- Do not use `---` horizontal rules between sections.
- Target a single page at standard margins and 10–11pt body text.
```

- [ ] **Step 4: Create `prompts/defaults/cover_refine.md`**

```markdown
You are rewriting a cover letter to address specific quality issues. Produce an improved cover letter.

# Applicant Details
Hero: {user.hero}
Skills: {user.skills}
Work Experience: {user.work_history}

# Job Posting
Title: {job.title}
Company: {job.company}
{job.extracted_description}

# Current Cover Letter (improve this)
{current_resume}

# Issues to Fix
{critique}

# Instructions
- Address every issue listed above.
- Do NOT invent experience, skills, or credentials not present in the applicant details.
- Output ONLY the cover letter body. No preamble, no explanation.
- Three to four paragraphs: opening hook, relevant experience, company fit, call to action.
- Do not include a date or address block.
```

- [ ] **Step 5: Commit**

```bash
git add prompts/defaults/resume_eval.md prompts/defaults/cover_eval.md prompts/defaults/resume_refine.md prompts/defaults/cover_refine.md
git commit -m "[feat] Add default evaluator and rewriter prompt files"
```

---

## Task 4: Expose New Prompt Types in Prompts Router

**Files:**
- Modify: `web/routers/prompts.py`

- [ ] **Step 1: Add new type keys to `_VALID_DEFAULT_KEYS`**

Find `_VALID_DEFAULT_KEYS` in `web/routers/prompts.py` and replace:

```python
_VALID_DEFAULT_KEYS = {"scoring", "resume", "cover", "extraction", "resume_parse"}
```

with:

```python
_VALID_DEFAULT_KEYS = {
    "scoring", "resume", "cover", "extraction", "resume_parse",
    "resume_eval", "resume_refine", "cover_eval", "cover_refine",
}
```

- [ ] **Step 2: Verify endpoint responds**

Start the app (`start.bat`) then run:

```bash
curl http://localhost:8080/api/prompts/defaults/resume_eval
```

Expected: JSON with `path` and `content` fields, content matching the prompt file.

- [ ] **Step 3: Commit**

```bash
git add web/routers/prompts.py
git commit -m "[feat] Expose resume_eval, resume_refine, cover_eval, cover_refine prompt defaults"
```

---

## Task 5: Job Evaluate Methods

**Files:**
- Modify: `core/job.py`
- Create: `tests/test_job_refinement.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_job_refinement.py`:

```python
"""Unit tests for Job evaluate/refine methods."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.job import Job, _strip_yaml_frontmatter


# ─── _strip_yaml_frontmatter ──────────────────────────────────────────────────

class TestStripYamlFrontmatter:
    def test_extracts_frontmatter_and_body(self):
        text = "---\nname: John\nemail: j@example.com\n---\n\n## Profile\nContent here."
        fm, body = _strip_yaml_frontmatter(text)
        assert "name: John" in fm
        assert fm.endswith("\n")
        assert body.strip().startswith("## Profile")

    def test_no_frontmatter_returns_empty_string_and_full_text(self):
        text = "## Profile\nContent."
        fm, body = _strip_yaml_frontmatter(text)
        assert fm == ""
        assert body == text

    def test_only_closing_dashes_present_falls_back(self):
        text = "Some text\n---\nmore"
        fm, body = _strip_yaml_frontmatter(text)
        assert fm == ""
        assert body == text


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_job(job_key: str = "test_job") -> Job:
    job = Job.__new__(Job)
    job.job_key = job_key
    job.title = "Backend Engineer"
    job.company = "Acme"
    job.location = "Remote"
    job.description = "Build things."
    job.salary = None
    for field in [
        "ext_seniority", "ext_role_type", "ext_domain", "ext_work_arrangement",
        "ext_employment_type", "ext_required_skills", "ext_preferred_skills",
        "ext_tech_stack", "ext_key_responsibilities", "ext_company_signals",
    ]:
        setattr(job, field, "")
    return job


def _make_user(skills=None) -> MagicMock:
    user = MagicMock()
    user.hero = "Engineer"
    user.skills = skills or ["Python", "Docker"]
    user.work_history = []
    user.projects = []
    user.first_name = "Jane"
    user.last_name = "Doe"
    user.email = "jane@example.com"
    user.phone = ""
    user.location = "Remote"
    user.target_roles = []
    user.target_salary_min = None
    user.target_salary_max = None
    user.education = []
    return user


def _make_llm_client(response_text: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = response_text
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


# ─── evaluate_resume_md ───────────────────────────────────────────────────────

class TestEvaluateResumeMd:
    def test_returns_score_and_issues(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "test_job_resume.md").write_text(
            "---\nname: Jane Doe\n---\n\n## Profile\nExperienced engineer.",
            encoding="utf-8",
        )
        client = _make_llm_client(json.dumps({
            "score": 0.75,
            "issues": [{"category": "keyword_coverage", "description": "Missing Docker"}],
        }))
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            result = job.evaluate_resume_md("Evaluate: {current_resume}", user, client, "gpt-4o")
        assert result["score"] == 0.75
        assert result["issues"][0]["category"] == "keyword_coverage"

    def test_clamps_score_above_1(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nContent.", encoding="utf-8"
        )
        client = _make_llm_client(json.dumps({"score": 1.5, "issues": []}))
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            result = job.evaluate_resume_md("Eval", user, client, "gpt-4o")
        assert result["score"] == 1.0

    def test_clamps_score_below_0(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nContent.", encoding="utf-8"
        )
        client = _make_llm_client(json.dumps({"score": -0.5, "issues": []}))
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            result = job.evaluate_resume_md("Eval", user, client, "gpt-4o")
        assert result["score"] == 0.0

    def test_strips_frontmatter_before_injecting(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nActual body.",
            encoding="utf-8",
        )
        captured = {}
        def fake_create(**kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"]
            choice = MagicMock()
            choice.message.content = json.dumps({"score": 0.9, "issues": []})
            choice.finish_reason = "stop"
            r = MagicMock()
            r.choices = [choice]
            r.usage = None
            return r
        client = MagicMock()
        client.chat.completions.create.side_effect = fake_create
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            job.evaluate_resume_md("{current_resume}", user, client, "gpt-4o")
        assert "Actual body." in captured["prompt"]
        assert "name: Jane" not in captured["prompt"]

    def test_raises_file_not_found(self, tmp_path):
        job = _make_job()
        user = _make_user()
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            with pytest.raises(FileNotFoundError):
                job.evaluate_resume_md("Eval", user, MagicMock(), "gpt-4o")

    def test_raises_on_invalid_json(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nContent.", encoding="utf-8"
        )
        client = _make_llm_client("not json at all")
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            with pytest.raises(RuntimeError, match="invalid JSON"):
                job.evaluate_resume_md("Eval", user, client, "gpt-4o")

    def test_raises_on_missing_keys(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nContent.", encoding="utf-8"
        )
        client = _make_llm_client(json.dumps({"only_score": 0.5}))
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            with pytest.raises(RuntimeError, match="missing required keys"):
                job.evaluate_resume_md("Eval", user, client, "gpt-4o")
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd C:/Users/barlo/Projects/auto_apply
python -m pytest tests/test_job_refinement.py::TestStripYamlFrontmatter tests/test_job_refinement.py::TestEvaluateResumeMd -v 2>&1 | head -40
```

Expected: errors like `ImportError: cannot import name '_strip_yaml_frontmatter'`

- [ ] **Step 3: Add `_strip_yaml_frontmatter` to `core/job.py`**

After the existing `_apply_template` function, add:

```python
def _strip_yaml_frontmatter(text: str) -> tuple[str, str]:
    """Split a markdown file with YAML front matter into (frontmatter, body).

    Returns ("", text) if no front matter is found.
    """
    if not text.startswith("---"):
        return ("", text)
    end = text.find("\n---", 3)
    if end == -1:
        return ("", text)
    fm_end = end + 4  # past \n---
    if fm_end < len(text) and text[fm_end] == "\n":
        fm_end += 1
    return (text[:fm_end], text[fm_end:])
```

- [ ] **Step 4: Add `_evaluate_doc_md` private method and `evaluate_resume_md` / `evaluate_cover_md` public methods to `Job`**

In `core/job.py`, inside the `Job` class, add after the `score()` method block (after the `# ── Description extraction` comment, before `extract_description`):

```python
    # ── Refinement — evaluation ────────────────────────────────────────────────

    def _evaluate_doc_md(
        self,
        doc_type: str,
        eval_prompt: str,
        user: Any,
        client: Any,
        model: str,
    ) -> dict:
        """Evaluate a generated document (resume or cover letter) for quality.

        Args:
            doc_type: "resume" or "cover".
            eval_prompt: Rendered evaluation prompt template.
            user: Hydrated User instance.
            client: OpenAI-compatible client.
            model: Model identifier string.

        Returns:
            {"score": float, "issues": list[dict]}

        Raises:
            FileNotFoundError: If the document markdown file does not exist.
            RuntimeError: If the LLM returns unparseable or malformed JSON.
        """
        from core.llm import call_llm

        md_path = _OUTPUTS_DIR / f"{self.job_key}_{doc_type}.md"
        if not md_path.exists():
            raise FileNotFoundError(
                f"{doc_type.capitalize()} markdown not found: {md_path}"
            )

        _, body = _strip_yaml_frontmatter(md_path.read_text(encoding="utf-8"))

        prompt = eval_prompt.replace("{current_resume}", body)
        prompt = _apply_template(prompt, {"job": self, "user": user})

        raw = call_llm(prompt, client, model, max_tokens=2048)

        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last > first:
            cleaned = cleaned[first : last + 1]

        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            preview = (raw or "")[:200].replace("\n", " ")
            raise RuntimeError(
                f"Eval LLM returned invalid JSON: {exc}. Preview: {preview!r}"
            ) from exc

        if "score" not in parsed or "issues" not in parsed:
            raise RuntimeError(
                f"Eval response missing required keys; got {sorted(parsed.keys())}"
            )

        score = max(0.0, min(1.0, float(parsed["score"])))
        issues = parsed.get("issues", [])
        if not isinstance(issues, list):
            issues = []

        return {"score": score, "issues": issues}

    def evaluate_resume_md(
        self,
        eval_prompt: str,
        user: Any,
        client: Any,
        model: str,
    ) -> dict:
        """Evaluate the generated resume markdown. Returns {"score", "issues"}."""
        return self._evaluate_doc_md("resume", eval_prompt, user, client, model)

    def evaluate_cover_md(
        self,
        eval_prompt: str,
        user: Any,
        client: Any,
        model: str,
    ) -> dict:
        """Evaluate the generated cover letter markdown. Returns {"score", "issues"}."""
        return self._evaluate_doc_md("cover", eval_prompt, user, client, model)
```

- [ ] **Step 5: Run tests — expect pass**

```bash
python -m pytest tests/test_job_refinement.py::TestStripYamlFrontmatter tests/test_job_refinement.py::TestEvaluateResumeMd -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add core/job.py tests/test_job_refinement.py
git commit -m "[feat] Add evaluate_resume_md and evaluate_cover_md to Job"
```

---

## Task 6: Job Refine Methods

**Files:**
- Modify: `core/job.py`
- Modify: `tests/test_job_refinement.py`

- [ ] **Step 1: Add refine tests to `tests/test_job_refinement.py`**

Append to `tests/test_job_refinement.py`:

```python
# ─── refine_resume_md ─────────────────────────────────────────────────────────

class TestRefineResumeMd:
    def test_overwrites_file_preserving_frontmatter(self, tmp_path):
        job = _make_job()
        user = _make_user()
        original_fm = "---\nname: Jane Doe\nemail: jane@example.com\n---\n\n"
        (tmp_path / "test_job_resume.md").write_text(
            original_fm + "## Profile\nOld content.", encoding="utf-8"
        )
        client = _make_llm_client(
            "## Profile\nImproved content.\n\n## Experience\nBetter bullets."
        )
        db = MagicMock()
        template_path = MagicMock(spec=Path)

        with patch("core.job._OUTPUTS_DIR", tmp_path):
            with patch.object(job, "generate_resume_pdf") as mock_pdf:
                job.refine_resume_md(
                    user, "Rewrite: {current_resume}\nIssues: {critique}",
                    client, "gpt-4o", db,
                    [{"category": "tailoring", "description": "Too generic"}],
                    template_path,
                )
                mock_pdf.assert_called_once_with(template_path, db)

        result = (tmp_path / "test_job_resume.md").read_text(encoding="utf-8")
        assert "name: Jane Doe" in result          # frontmatter preserved
        assert "Improved content." in result        # new content
        assert "Old content." not in result         # old content replaced

    def test_injects_critique_as_json(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nContent.", encoding="utf-8"
        )
        captured = {}
        def fake_create(**kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"]
            choice = MagicMock()
            choice.message.content = "## Profile\nResult."
            choice.finish_reason = "stop"
            r = MagicMock()
            r.choices = [choice]
            r.usage = None
            return r
        client = MagicMock()
        client.chat.completions.create.side_effect = fake_create
        issues = [{"category": "structure", "description": "Bullet too long"}]

        with patch("core.job._OUTPUTS_DIR", tmp_path):
            with patch.object(job, "generate_resume_pdf"):
                job.refine_resume_md(
                    user, "Resume: {current_resume} Critique: {critique}",
                    client, "gpt-4o", MagicMock(), issues, MagicMock(spec=Path),
                )

        assert json.dumps(issues) in captured["prompt"]

    def test_raises_file_not_found(self, tmp_path):
        job = _make_job()
        user = _make_user()
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            with pytest.raises(FileNotFoundError):
                job.refine_resume_md(
                    user, "Rewrite", MagicMock(), "gpt-4o",
                    MagicMock(), [], MagicMock(spec=Path),
                )
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
python -m pytest tests/test_job_refinement.py::TestRefineResumeMd -v 2>&1 | head -20
```

Expected: `AttributeError: ... has no attribute 'refine_resume_md'`

- [ ] **Step 3: Add `_refine_doc_md`, `refine_resume_md`, `refine_cover_md` to `Job`**

In `core/job.py`, inside the `Job` class, add after `evaluate_cover_md`:

```python
    # ── Refinement — rewriting ─────────────────────────────────────────────────

    def _refine_doc_md(
        self,
        doc_type: str,
        user: Any,
        refine_prompt: str,
        client: Any,
        model: str,
        issues: list,
    ) -> None:
        """Rewrite a generated document to address evaluation issues.

        Overwrites the existing markdown file in generator/outputs/ in place.
        Preserves the YAML front matter block from the original file.
        Caller is responsible for calling generate_resume_pdf / generate_cover_pdf
        and committing eval fields to the DB.

        Args:
            doc_type: "resume" or "cover".
            user: Hydrated User instance.
            refine_prompt: Rewriter prompt template.
            client: OpenAI-compatible client.
            model: Model identifier string.
            issues: List of issue dicts from the evaluator.

        Raises:
            FileNotFoundError: If the document markdown file does not exist.
        """
        from core.llm import call_llm
        from core.utils import strip_header_block

        md_path = _OUTPUTS_DIR / f"{self.job_key}_{doc_type}.md"
        if not md_path.exists():
            raise FileNotFoundError(
                f"{doc_type.capitalize()} markdown not found: {md_path}"
            )

        frontmatter, body = _strip_yaml_frontmatter(
            md_path.read_text(encoding="utf-8")
        )

        critique = json.dumps(issues)
        prompt = refine_prompt.replace("{current_resume}", body)
        prompt = prompt.replace("{critique}", critique)
        prompt = _apply_template(prompt, {"job": self, "user": user})

        content = call_llm(prompt, client, model, max_tokens=16384)
        content = strip_header_block(content)
        md_path.write_text(frontmatter + content, encoding="utf-8")

    def refine_resume_md(
        self,
        user: Any,
        refine_prompt: str,
        client: Any,
        model: str,
        db: Any,
        issues: list,
        template_path: Any,
    ) -> None:
        """Rewrite resume markdown and regenerate the PDF.

        Args:
            user: Hydrated User instance.
            refine_prompt: Rewriter prompt template.
            client: OpenAI-compatible client.
            model: Model identifier string.
            db: SQLAlchemy session (passed to generate_resume_pdf).
            issues: List of issue dicts from evaluate_resume_md.
            template_path: Path to the HTML resume template for PDF rendering.
        """
        self._refine_doc_md("resume", user, refine_prompt, client, model, issues)
        self.generate_resume_pdf(template_path, db)

    def refine_cover_md(
        self,
        user: Any,
        refine_prompt: str,
        client: Any,
        model: str,
        db: Any,
        issues: list,
        template_path: Any,
    ) -> None:
        """Rewrite cover letter markdown and regenerate the PDF.

        Args:
            user: Hydrated User instance.
            refine_prompt: Rewriter prompt template.
            client: OpenAI-compatible client.
            model: Model identifier string.
            db: SQLAlchemy session (passed to generate_cover_pdf).
            issues: List of issue dicts from evaluate_cover_md.
            template_path: Path to the HTML cover letter template for PDF rendering.
        """
        self._refine_doc_md("cover", user, refine_prompt, client, model, issues)
        self.generate_cover_pdf(template_path, db)
```

- [ ] **Step 4: Run all tests — expect all pass**

```bash
python -m pytest tests/test_job_refinement.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/job.py tests/test_job_refinement.py
git commit -m "[feat] Add refine_resume_md and refine_cover_md to Job"
```

---

## Task 7: Update `Job.serialize()`

**Files:**
- Modify: `core/job.py`

- [ ] **Step 1: Add eval fields to `serialize()`**

In `core/job.py`, inside `Job.serialize()`, add to the returned dict (after `"flagged": bool(self.flagged),`):

```python
            "resume_eval_score": self.resume_eval_score,
            "resume_eval_turns": self.resume_eval_turns,
            "resume_eval_log": (
                json.loads(self.resume_eval_log)
                if isinstance(self.resume_eval_log, str) and self.resume_eval_log
                else []
            ),
            "cover_eval_score": self.cover_eval_score,
            "cover_eval_turns": self.cover_eval_turns,
            "cover_eval_log": (
                json.loads(self.cover_eval_log)
                if isinstance(self.cover_eval_log, str) and self.cover_eval_log
                else []
            ),
```

- [ ] **Step 2: Verify via Python**

```python
python -c "
from db.database import init_db, SessionLocal
init_db()
from core.job import Job
db = SessionLocal()
job = db.query(Job).first()
if job:
    d = job.serialize()
    assert 'resume_eval_score' in d
    assert 'resume_eval_log' in d
    assert isinstance(d['resume_eval_log'], list)
    print('serialize OK:', d.get('resume_eval_score'), d.get('resume_eval_log'))
else:
    print('No jobs in DB — field check skipped, schema OK')
db.close()
"
```

Expected: no AttributeError, `resume_eval_log` is a list.

- [ ] **Step 3: Commit**

```bash
git add core/job.py
git commit -m "[feat] Add eval fields to Job.serialize()"
```

---

## Task 8: Refinement Loop Functions

**Files:**
- Modify: `web/intake_pipeline.py`

- [ ] **Step 1: Add `run_resume_refinement` and `run_cover_refinement`**

Add the following to the end of `web/intake_pipeline.py`:

```python
def _run_doc_refinement(job_key: str, doc_type: str) -> None:
    """Background refinement loop for a generated document (resume or cover).

    Alternates between LLM evaluation and LLM rewriting until the document
    scores above pass_score or the turn limit is reached.

    Args:
        job_key: Unique job identifier.
        doc_type: "resume" or "cover".
    """
    import json as _json
    from pathlib import Path
    from core.user import PromptNotConfiguredError
    from core.llm import get_client_for_profile

    _GEN_DIR = Path(__file__).parent.parent / "generator"
    _TEMPLATES = {
        "resume": _GEN_DIR / "resume_template.html",
        "cover": _GEN_DIR / "cover_template.html",
    }
    template_path = _TEMPLATES[doc_type]
    score_field = f"{doc_type}_eval_score"
    turns_field = f"{doc_type}_eval_turns"
    log_field = f"{doc_type}_eval_log"
    eval_key = f"{doc_type}_eval"
    refine_key = f"{doc_type}_refine"

    db = SessionLocal()
    try:
        job = Job.get(job_key, db)
        if job is None:
            return
        user = User.load(db)

        enabled = getattr(user, f"{doc_type}_refine_enabled", True)
        max_turns = int(getattr(user, f"{doc_type}_refine_max_turns", 1))
        pass_score = float(getattr(user, f"{doc_type}_refine_pass_score", 0.80))

        if not enabled or max_turns == 0:
            return

        try:
            eval_prompt = user.resolve_prompt(eval_key)
        except PromptNotConfiguredError as exc:
            print(f"[refinement:{doc_type}] {job_key}: eval prompt not configured — {exc}", flush=True)
            return

        try:
            refine_prompt = user.resolve_prompt(refine_key)
        except PromptNotConfiguredError as exc:
            print(f"[refinement:{doc_type}] {job_key}: refine prompt not configured — {exc}", flush=True)
            return

        eval_model = getattr(user, f"prompt_{eval_key}_model", "") or ""
        refine_model = getattr(user, f"prompt_{refine_key}_model", "") or ""

        try:
            eval_client, resolved_eval_model = get_client_for_profile(user, eval_model)
            refine_client, resolved_refine_model = get_client_for_profile(user, refine_model)
        except RuntimeError as exc:
            print(f"[refinement:{doc_type}] {job_key}: LLM client error — {exc}", flush=True)
            return

        eval_log = []
        result = None

        for turn in range(1, max_turns + 1):
            # Step A: Evaluate
            llm_status.start(job_key, f"{doc_type}_eval")
            try:
                print(f"[refinement:{doc_type}] {job_key}: turn {turn} evaluating", flush=True)
                evaluate_fn = getattr(job, f"evaluate_{doc_type}_md")
                result = evaluate_fn(eval_prompt, user, eval_client, resolved_eval_model)
                passed = result["score"] >= pass_score
                eval_log.append({
                    "turn": turn,
                    "score": result["score"],
                    "issues": result["issues"],
                    "passed": passed,
                })
                setattr(job, score_field, result["score"])
                setattr(job, turns_field, turn)
                setattr(job, log_field, _json.dumps(eval_log))
                job.last_result_error = None
                db.commit()
                db.refresh(job)
                _emit(job)
                print(
                    f"[refinement:{doc_type}] {job_key}: turn {turn} score={result['score']:.2f}"
                    + (" ✓ passed" if passed else ""),
                    flush=True,
                )
            except Exception as exc:
                db.rollback()
                job = Job.get(job_key, db)
                job.last_result_error = f"{doc_type.capitalize()} eval turn {turn} failed: {exc}"
                job.unread_indicator = "error"
                db.commit()
                _emit(job)
                print(f"[refinement:{doc_type}] {job_key}: eval failed — {exc}", flush=True)
                return
            finally:
                llm_status.finish(job_key, f"{doc_type}_eval")

            if result["score"] >= pass_score:
                return

            if turn >= max_turns:
                return

            # Step B: Rewrite
            llm_status.start(job_key, f"{doc_type}_refine")
            try:
                print(f"[refinement:{doc_type}] {job_key}: turn {turn} rewriting", flush=True)
                refine_fn = getattr(job, f"refine_{doc_type}_md")
                refine_fn(
                    user, refine_prompt, refine_client, resolved_refine_model,
                    db, result["issues"], template_path,
                )
                db.commit()
                db.refresh(job)
                _emit(job)
                print(f"[refinement:{doc_type}] {job_key}: turn {turn} rewrite complete", flush=True)
            except Exception as exc:
                db.rollback()
                job = Job.get(job_key, db)
                job.last_result_error = f"{doc_type.capitalize()} refine turn {turn} failed: {exc}"
                job.unread_indicator = "error"
                db.commit()
                _emit(job)
                print(f"[refinement:{doc_type}] {job_key}: rewrite failed — {exc}", flush=True)
                return
            finally:
                llm_status.finish(job_key, f"{doc_type}_refine")
    finally:
        db.close()


def run_resume_refinement(job_key: str) -> None:
    """Run the evaluate→rewrite loop for a generated resume."""
    _run_doc_refinement(job_key, "resume")


def run_cover_refinement(job_key: str) -> None:
    """Run the evaluate→rewrite loop for a generated cover letter."""
    _run_doc_refinement(job_key, "cover")
```

- [ ] **Step 2: Verify imports still work**

```bash
python -c "from web.intake_pipeline import run_resume_refinement, run_cover_refinement; print('imports OK')"
```

Expected: `imports OK`

- [ ] **Step 3: Commit**

```bash
git add web/intake_pipeline.py
git commit -m "[feat] Add run_resume_refinement and run_cover_refinement to intake pipeline"
```

---

## Task 9: Auto-Trigger Refinement After Generation

**Files:**
- Modify: `web/routers/jobs.py`

- [ ] **Step 1: Add thread spawn after resume generation**

In `web/routers/jobs.py`, find `generate_resume_endpoint`. After the `_emit(job)` call and before `return job.serialize()`, add:

```python
    # Spawn background refinement loop if enabled
    _maybe_start_refinement(job.job_key, "resume", db)
```

- [ ] **Step 2: Add thread spawn after cover generation**

In `generate_cover_endpoint`, same pattern — after `_emit(job)`, before `return job.serialize()`:

```python
    _maybe_start_refinement(job.job_key, "cover", db)
```

- [ ] **Step 3: Add `_maybe_start_refinement` helper**

Add this function near the top of `web/routers/jobs.py` (after the existing helper functions, before the route definitions):

```python
def _maybe_start_refinement(job_key: str, doc_type: str, db: Session) -> None:
    """Spawn a background refinement thread if the user profile has it enabled."""
    import threading
    try:
        user = User.load(db)
    except RuntimeError:
        return
    enabled = getattr(user, f"{doc_type}_refine_enabled", True)
    max_turns = int(getattr(user, f"{doc_type}_refine_max_turns", 1))
    if not enabled or max_turns == 0:
        return
    if doc_type == "resume":
        from web.intake_pipeline import run_resume_refinement
        threading.Thread(target=run_resume_refinement, args=(job_key,), daemon=True).start()
    else:
        from web.intake_pipeline import run_cover_refinement
        threading.Thread(target=run_cover_refinement, args=(job_key,), daemon=True).start()
```

- [ ] **Step 4: Manual smoke test**

1. Start the app with `start.bat`
2. In the dashboard, select a job that has been extracted and scored
3. Go to the Resume tab and click Generate
4. In the terminal running the server, within a few seconds you should see:
   ```
   [refinement:resume] {job_key}: turn 1 evaluating
   [refinement:resume] {job_key}: turn 1 score=X.XX
   ```
5. If `max_turns > 1` and score is below threshold, also see:
   ```
   [refinement:resume] {job_key}: turn 1 rewriting
   [refinement:resume] {job_key}: turn 2 evaluating
   ```
6. The job card in the dashboard should update via SSE after each step

- [ ] **Step 5: Commit**

```bash
git add web/routers/jobs.py
git commit -m "[feat] Auto-trigger refinement loop after resume/cover generation"
```

---

## Task 10: Frontend — `RefinementPromptModal` Component

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

- [ ] **Step 1: Add `RefinementPromptModal` component**

In `ProfileDetail.jsx`, add this component after the existing `PromptModal` component and before `PromptsSection`:

```jsx
const REFINEMENT_EVAL_CHIPS = [
  { label: 'current doc', token: '{current_resume}' },
]
const REFINEMENT_REFINE_CHIPS = [
  { label: 'current doc', token: '{current_resume}' },
  { label: 'critique', token: '{critique}' },
]

function RefinementPromptModal({ docType, profileId, profileName, profileData, defaultModel, onClose, onSaved }) {
  const label = docType === 'resume' ? 'Resume Refinement' : 'Cover Letter Refinement'

  const [activeTab, setActiveTab] = useState('evaluator')
  const [maxTurns, setMaxTurns] = useState(profileData[`${docType}_refine_max_turns`] ?? 1)
  const [passScore, setPassScore] = useState(profileData[`${docType}_refine_pass_score`] ?? 0.80)

  // Evaluator tab state
  const [evalFile, setEvalFile] = useState(profileData[`prompt_${docType}_eval`] || '')
  const [evalModel, setEvalModel] = useState(profileData[`prompt_${docType}_eval_model`] || '')
  const [evalContent, setEvalContent] = useState('')
  const [evalLoading, setEvalLoading] = useState(false)
  const [evalContentError, setEvalContentError] = useState(null)
  const evalOriginal = useRef('')
  const evalTextareaRef = useRef(null)

  // Rewriter tab state
  const [refineFile, setRefineFile] = useState(profileData[`prompt_${docType}_refine`] || '')
  const [refineModel, setRefineModel] = useState(profileData[`prompt_${docType}_refine_model`] || '')
  const [refineContent, setRefineContent] = useState('')
  const [refineLoading, setRefineLoading] = useState(false)
  const [refineContentError, setRefineContentError] = useState(null)
  const refineOriginal = useRef('')
  const refineTextareaRef = useRef(null)

  // Shared state
  const [promptFiles, setPromptFiles] = useState([])
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [popOut, setPopOut] = useState(false)
  const [saveAsOpen, setSaveAsOpen] = useState(false)
  const [saveAsName, setSaveAsName] = useState('')
  const [saveAsError, setSaveAsError] = useState(null)
  const [saveAsSubmitting, setSaveAsSubmitting] = useState(false)

  const isEval = activeTab === 'evaluator'
  const currentFile = isEval ? evalFile : refineFile
  const setCurrentFile = isEval ? setEvalFile : setRefineFile
  const currentModel = isEval ? evalModel : refineModel
  const setCurrentModel = isEval ? setEvalModel : setRefineModel
  const currentContent = isEval ? evalContent : refineContent
  const setCurrentContent = isEval ? setEvalContent : setRefineContent
  const currentLoading = isEval ? evalLoading : refineLoading
  const currentContentError = isEval ? evalContentError : refineContentError
  const currentOriginal = isEval ? evalOriginal : refineOriginal
  const currentTextareaRef = isEval ? evalTextareaRef : refineTextareaRef
  const currentTypeKey = isEval ? `${docType}_eval` : `${docType}_refine`
  const extraChips = isEval ? REFINEMENT_EVAL_CHIPS : REFINEMENT_REFINE_CHIPS

  useEscape(!popOut, onClose)
  useEscape(popOut, () => setPopOut(false))

  useEffect(() => {
    listPrompts().then(r => setPromptFiles(r.prompts || []))
  }, [])

  // Load default content if file is unset
  useEffect(() => {
    if (!evalFile) {
      setEvalLoading(true)
      getDefaultPrompt(`${docType}_eval`)
        .then(({ path, content }) => { setEvalFile(path); setEvalContent(content); evalOriginal.current = content })
        .catch(() => {})
        .finally(() => setEvalLoading(false))
    }
    if (!refineFile) {
      setRefineLoading(true)
      getDefaultPrompt(`${docType}_refine`)
        .then(({ path, content }) => { setRefineFile(path); setRefineContent(content); refineOriginal.current = content })
        .catch(() => {})
        .finally(() => setRefineLoading(false))
    }
  }, [])

  // Load content when file selection changes
  useEffect(() => {
    if (!evalFile) { setEvalContent(''); return }
    setEvalLoading(true); setEvalContentError(null)
    getPromptFile(evalFile)
      .then(t => { setEvalContent(t); evalOriginal.current = t })
      .catch(() => setEvalContentError('Could not load file'))
      .finally(() => setEvalLoading(false))
  }, [evalFile])

  useEffect(() => {
    if (!refineFile) { setRefineContent(''); return }
    setRefineLoading(true); setRefineContentError(null)
    getPromptFile(refineFile)
      .then(t => { setRefineContent(t); refineOriginal.current = t })
      .catch(() => setRefineContentError('Could not load file'))
      .finally(() => setRefineLoading(false))
  }, [refineFile])

  const isDefaultPrompt = (path) => /[/\\]defaults[/\\]/.test(path)
  const basename = (path) => path?.split(/[\\/]/).pop() ?? ''

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const token = e.dataTransfer.getData('text/plain')
    if (!token || !currentTextareaRef.current) return
    const ta = currentTextareaRef.current
    const offset = ta.selectionStart ?? 0
    const before = currentContent.slice(0, offset)
    const after = currentContent.slice(offset)
    setCurrentContent(before + token + after)
    requestAnimationFrame(() => {
      ta.focus()
      ta.setSelectionRange(offset + token.length, offset + token.length)
    })
  }, [currentContent, currentTextareaRef, setCurrentContent])

  const handleDragOver = (e) => e.preventDefault()

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const result = await uploadPromptFile(file)
      const updated = await listPrompts()
      setPromptFiles(updated.prompts || [])
      setCurrentFile(result.path)
    } catch { setSaveError('Upload failed') }
    finally { setUploading(false); e.target.value = '' }
  }

  const _resolveFile = async (file, content, original, setFile) => {
    if (!file) return file
    if (isDefaultPrompt(file) && content !== original.current) {
      const baseName = basename(file).replace(/\.md$/i, '')
      const filename = `${baseName}_${Date.now()}.md`
      const result = await createPromptFile(filename, content)
      setFile(result.path)
      original.current = content
      return result.path
    } else if (!isDefaultPrompt(file) && content !== original.current) {
      await putPromptFile(file, content)
      original.current = content
    }
    return file
  }

  const handleSave = async () => {
    setSaving(true); setSaveError(null)
    try {
      const resolvedEval = await _resolveFile(evalFile, evalContent, evalOriginal, setEvalFile)
      const resolvedRefine = await _resolveFile(refineFile, refineContent, refineOriginal, setRefineFile)
      const newData = {
        ...profileData,
        [`prompt_${docType}_eval`]: resolvedEval,
        [`prompt_${docType}_eval_model`]: evalModel,
        [`prompt_${docType}_refine`]: resolvedRefine,
        [`prompt_${docType}_refine_model`]: refineModel,
        [`${docType}_refine_max_turns`]: Number(maxTurns),
        [`${docType}_refine_pass_score`]: Number(passScore),
      }
      await updateProfile(profileId, { name: profileName || '', data: newData })
      onSaved(newData)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
      onClose()
    } catch { setSaveError('Save failed') }
    finally { setSaving(false) }
  }

  const openSaveAs = () => {
    const base = currentFile ? basename(currentFile).replace(/\.md$/i, '') : currentTypeKey
    setSaveAsName(isDefaultPrompt(currentFile ?? '') ? `${base}_custom.md` : `${base}_copy.md`)
    setSaveAsError(null); setSaveAsOpen(true)
  }

  const handleSaveAsConfirm = async () => {
    const filename = saveAsName.trim()
    if (!filename) { setSaveAsError('Filename is required'); return }
    const name = filename.endsWith('.md') ? filename : filename + '.md'
    setSaveAsSubmitting(true); setSaveAsError(null)
    try {
      const result = await createPromptFile(name, currentContent)
      const updated = await listPrompts()
      setPromptFiles(updated.prompts || [])
      setCurrentFile(result.path)
      currentOriginal.current = currentContent
      setSaveAsOpen(false)
    } catch (e) {
      const msg = e?.message || ''
      setSaveAsError(msg.includes('409') ? 'A file with that name already exists' : 'Save failed')
    } finally { setSaveAsSubmitting(false) }
  }

  const renderEditor = (extraClass = '') => {
    if (currentLoading) return <p className="text-xs text-space-dim">Loading…</p>
    if (currentContentError) return <p className="text-xs text-red-400">{currentContentError}</p>
    return (
      <textarea
        ref={currentTextareaRef}
        rows={12}
        className={inputClass + ' resize-y font-mono text-xs ' + extraClass}
        value={currentContent}
        onChange={e => setCurrentContent(e.target.value)}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        placeholder={currentFile ? '' : 'Select a file above to edit'}
        disabled={!currentFile}
      />
    )
  }

  const renderChipTray = () => (
    <div className="flex flex-col gap-2">
      <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Insert Variable</label>
      <div className="flex flex-col gap-1.5">
        <p className="text-xs text-space-dim">User</p>
        <div className="flex flex-wrap gap-1.5">
          {USER_CHIPS.map(({ label: l, token }) => (
            <div key={token} draggable onDragStart={e => e.dataTransfer.setData('text/plain', token)}
              className="px-2 py-0.5 rounded-full border border-purple-500/40 bg-purple-500/10 text-xs text-purple-300 cursor-grab select-none">
              {l}
            </div>
          ))}
        </div>
        <p className="text-xs text-space-dim mt-1">Job</p>
        <div className="flex flex-wrap gap-1.5">
          {JOB_CHIPS.map(({ label: l, token }) => (
            <div key={token} draggable onDragStart={e => e.dataTransfer.setData('text/plain', token)}
              className="px-2 py-0.5 rounded-full border border-blue-500/40 bg-blue-500/10 text-xs text-blue-300 cursor-grab select-none">
              {l}
            </div>
          ))}
        </div>
        <p className="text-xs text-space-dim mt-1">Refinement</p>
        <div className="flex flex-wrap gap-1.5">
          {extraChips.map(({ label: l, token }) => (
            <div key={token} draggable onDragStart={e => e.dataTransfer.setData('text/plain', token)}
              className="px-2 py-0.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 text-xs text-emerald-300 cursor-grab select-none">
              {l}
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  const renderTabContent = () => (
    <div className="flex flex-col gap-4">
      {/* File selector */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt File</label>
        <div className="flex gap-2">
          <select className={inputClass + ' flex-1'} value={currentFile}
            onChange={e => setCurrentFile(e.target.value)}>
            <option value="" style={{ color: '#000', backgroundColor: '#fff' }}>— select a file —</option>
            {promptFiles.map(f => (
              <option key={f.path} value={f.path} style={{ color: '#000', backgroundColor: '#fff' }}>{f.name}</option>
            ))}
          </select>
          <label className={`px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text hover:border-purple-500/50 transition-colors cursor-pointer ${uploading ? 'opacity-50 pointer-events-none' : ''}`}>
            {uploading ? '…' : 'Upload'}
            <input type="file" accept=".md" className="hidden" onChange={handleUpload} />
          </label>
        </div>
      </div>
      {/* Model */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Model</label>
        <input className={inputClass} value={currentModel} onChange={e => setCurrentModel(e.target.value)}
          placeholder={defaultModel || 'e.g. gpt-4o-mini (leave blank for profile default)'} />
      </div>
      {/* Chip tray + editor (hidden when popped out) */}
      {!popOut && renderChipTray()}
      {!popOut && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt Text</label>
            <button type="button" onClick={() => setPopOut(true)} className="text-space-dim hover:text-space-text p-1 rounded hover:bg-white/5 transition-colors">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10 2h4v4" /><path d="M14 2L8.5 7.5" /><path d="M6 14H2v-4" /><path d="M2 14l5.5-5.5" />
              </svg>
            </button>
          </div>
          {renderEditor()}
        </div>
      )}
    </div>
  )

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
        <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-space-border shrink-0">
            <span className="text-sm font-semibold text-space-text">{label}</span>
            <button onClick={onClose} className="text-space-dim hover:text-space-text text-lg leading-none">×</button>
          </div>

          {/* Config row */}
          <div className="flex items-center gap-4 px-4 py-2 border-b border-space-border shrink-0">
            <div className="flex items-center gap-2">
              <label className="text-xs text-space-dim whitespace-nowrap">Max Turns</label>
              <input type="number" min="1" max="10" className="w-16 bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text focus:outline-none focus:border-purple-500"
                value={maxTurns} onChange={e => setMaxTurns(Math.max(1, Math.min(10, Number(e.target.value))))} />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-space-dim whitespace-nowrap">Pass Score</label>
              <input type="number" min="0" max="1" step="0.05" className="w-20 bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text focus:outline-none focus:border-purple-500"
                value={passScore} onChange={e => setPassScore(Math.max(0, Math.min(1, Number(e.target.value))))} />
              <span className="text-xs text-space-dim">(0–1)</span>
            </div>
          </div>

          {/* Tab bar */}
          <div className="flex border-b border-space-border shrink-0">
            {[['evaluator', 'Evaluator'], ['rewriter', 'Rewriter']].map(([key, lbl]) => (
              <button key={key} onClick={() => { setActiveTab(key); setPopOut(false) }}
                className={`flex-1 py-2 text-xs font-semibold uppercase tracking-widest transition-colors ${activeTab === key ? 'text-purple-400 border-b-2 border-purple-400 bg-white/5' : 'text-space-dim hover:text-space-text'}`}>
                {lbl}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-4">
            {renderTabContent()}
          </div>

          {/* Footer */}
          <div className="px-4 py-3 border-t border-space-border shrink-0 flex flex-col gap-2">
            {saveError && <p className="text-xs text-red-400">{saveError}</p>}
            {saveAsOpen ? (
              <div className="flex flex-col gap-2">
                {saveAsError && <p className="text-xs text-red-400">{saveAsError}</p>}
                <div className="flex gap-2 items-center">
                  <input autoFocus className={inputClass + ' flex-1 text-xs'} value={saveAsName}
                    onChange={e => { setSaveAsName(e.target.value); setSaveAsError(null) }}
                    onKeyDown={e => { if (e.key === 'Enter') handleSaveAsConfirm(); if (e.key === 'Escape') setSaveAsOpen(false) }}
                    placeholder="filename.md" />
                  <button onClick={handleSaveAsConfirm} disabled={saveAsSubmitting}
                    className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-xs font-semibold shrink-0">
                    {saveAsSubmitting ? '…' : 'Confirm'}
                  </button>
                  <button onClick={() => setSaveAsOpen(false)}
                    className="px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text shrink-0">✕</button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <button onClick={openSaveAs} disabled={saving || currentLoading || !!currentContentError}
                  className="px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text disabled:opacity-50 shrink-0">
                  Save As
                </button>
                <button onClick={handleSave} disabled={saving || currentLoading || !!currentContentError}
                  className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors">
                  {saving ? 'Saving…' : 'Save'}
                </button>
                <button onClick={onClose} className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors">
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Pop-out full editor */}
      {popOut && (
        <div className="fixed inset-0 z-[60] flex flex-col bg-[#0a0a14]">
          <div className="flex items-center justify-between px-4 py-3 border-b border-space-border shrink-0">
            <span className="text-sm font-semibold text-space-text">
              {label} — {activeTab === 'evaluator' ? 'Evaluator' : 'Rewriter'} — Full Editor
            </span>
            <button onClick={() => setPopOut(false)} className="text-space-dim hover:text-space-text text-lg leading-none">×</button>
          </div>
          <div className="flex-1 flex flex-col gap-3 p-4 min-h-0">
            {renderChipTray()}
            <div className="flex flex-col gap-1.5 flex-1 min-h-0">
              <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt Text</label>
              {renderEditor('flex-1 min-h-0')}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify the component renders**

Start the dev server: `cd react-dashboard && npm run dev`

Open the dashboard → User tab → select a profile → open Prompts accordion.

The page should not crash (the new component isn't visible yet — that's Task 11).

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add RefinementPromptModal component to ProfileDetail"
```

---

## Task 11: Frontend — Refinement Cards in PromptsSection

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

- [ ] **Step 1: Update `PromptsSection` to add refinement state and cards**

In `ProfileDetail.jsx`, replace the entire `PromptsSection` function with:

```jsx
function PromptsSection({ data, profileId, profileName, defaultModel, onSave }) {
  const [openModal, setOpenModal] = useState(null)           // typeKey string | null
  const [openRefinement, setOpenRefinement] = useState(null) // 'resume' | 'cover' | null
  const [togglingRefine, setTogglingRefine] = useState(null) // 'resume' | 'cover' | null

  const handleSaved = (typeKey, filePath, modelOverride) => {
    onSave({
      [`prompt_${typeKey}`]: filePath,
      [`prompt_${typeKey}_model`]: modelOverride,
    })
  }

  const handleRefinementSaved = (docType, newData) => {
    onSave(newData)
  }

  const handleToggleRefinement = async (e, docType) => {
    e.stopPropagation()
    if (togglingRefine) return
    setTogglingRefine(docType)
    const field = `${docType}_refine_enabled`
    const current = data[field] !== false // default true
    try {
      await onSave({ [field]: !current })
    } finally {
      setTogglingRefine(null)
    }
  }

  const basename = (path) => path?.split(/[\\/]/).pop() ?? ''
  const truncate = (s, n = 22) => s && s.length > n ? s.slice(0, n) + '…' : s

  return (
    <>
      <AccordionSection id="prompts" title="Prompts">
        <div className="flex flex-col gap-2">

          {/* ── Standard generation prompt cards ── */}
          {PROMPT_TYPE_KEYS.map((typeKey) => {
            const filePath = data[`prompt_${typeKey}`] || ''
            const model = data[`prompt_${typeKey}_model`] || ''
            const configured = filePath && filePath.endsWith('.md')
            const bn = filePath ? basename(filePath) : null

            // After resume, inject resume-refinement card; after cover, inject cover-refinement card
            const refinementDocType = typeKey === 'resume' ? 'resume' : typeKey === 'cover' ? 'cover' : null

            return (
              <div key={typeKey} className="flex flex-col gap-1.5">
                {/* Generation card */}
                <button
                  onClick={() => setOpenModal(typeKey)}
                  className="flex items-start justify-between gap-3 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5 hover:border-purple-500/30 transition-colors text-left w-full"
                >
                  <div className="flex flex-col gap-0.5 min-w-0">
                    <span className="text-xs font-semibold text-space-text flex items-center gap-1">
                      {PROMPT_TYPE_LABELS[typeKey]}
                      <span onClick={e => e.stopPropagation()}>
                        <HelpIcon text={PROMPT_HELP[typeKey] || 'A prompt template used by the LLM.'} />
                      </span>
                    </span>
                    {bn
                      ? <span className="text-xs text-space-dim truncate">{bn}</span>
                      : <span className="text-xs text-red-400/80">Not configured</span>
                    }
                    {model
                      ? <span className="text-xs text-purple-400/70 truncate">{truncate(model)}</span>
                      : defaultModel && <span className="text-xs text-space-dim/50 truncate">{truncate(defaultModel)} (default)</span>
                    }
                  </div>
                  <span className={`shrink-0 text-xs font-medium mt-0.5 ${configured ? 'text-green-400' : 'text-space-dim/40'}`}>
                    {configured ? 'Custom' : 'Default'}
                  </span>
                </button>

                {/* Refinement card — shown only after resume and cover */}
                {refinementDocType && (() => {
                  const evalPath = data[`prompt_${refinementDocType}_eval`] || ''
                  const refinePath = data[`prompt_${refinementDocType}_refine`] || ''
                  const evalModel = data[`prompt_${refinementDocType}_eval_model`] || ''
                  const refineModel = data[`prompt_${refinementDocType}_refine_model`] || ''
                  const enabled = data[`${refinementDocType}_refine_enabled`] !== false
                  const isToggling = togglingRefine === refinementDocType
                  return (
                    <button
                      onClick={() => setOpenRefinement(refinementDocType)}
                      className="flex items-start justify-between gap-3 rounded-lg px-3 py-2.5 bg-white/[0.02] border border-white/5 hover:border-emerald-500/20 transition-colors text-left w-full ml-3"
                    >
                      <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                        <span className="text-xs font-semibold text-space-text/80">
                          {refinementDocType === 'resume' ? 'Resume Refinement' : 'Cover Letter Refinement'}
                        </span>
                        <span className="text-xs text-space-dim/70 truncate">
                          Eval: {evalPath ? truncate(basename(evalPath)) : <span className="text-space-dim/40">default</span>}
                          {evalModel ? <span className="text-purple-400/50"> · {truncate(evalModel, 16)}</span> : null}
                        </span>
                        <span className="text-xs text-space-dim/70 truncate">
                          Rewrite: {refinePath ? truncate(basename(refinePath)) : <span className="text-space-dim/40">default</span>}
                          {refineModel ? <span className="text-purple-400/50"> · {truncate(refineModel, 16)}</span> : null}
                        </span>
                      </div>
                      <button
                        onClick={e => handleToggleRefinement(e, refinementDocType)}
                        disabled={isToggling}
                        title={enabled ? 'Disable refinement' : 'Enable refinement'}
                        className={`shrink-0 text-xs font-medium mt-0.5 px-2 py-0.5 rounded border transition-colors disabled:opacity-50
                          ${enabled
                            ? 'text-emerald-400 border-emerald-500/40 hover:bg-emerald-500/10'
                            : 'text-space-dim/40 border-space-border hover:text-space-dim hover:border-space-border/60'
                          }`}
                      >
                        {enabled ? '✓ On' : '✗ Off'}
                      </button>
                    </button>
                  )
                })()}
              </div>
            )
          })}
        </div>
      </AccordionSection>

      {openModal && (
        <PromptModal
          typeKey={openModal}
          profileId={profileId}
          profileName={profileName}
          profileData={data}
          defaultModel={defaultModel}
          onClose={() => setOpenModal(null)}
          onSaved={handleSaved}
        />
      )}

      {openRefinement && (
        <RefinementPromptModal
          docType={openRefinement}
          profileId={profileId}
          profileName={profileName}
          profileData={data}
          defaultModel={defaultModel}
          onClose={() => setOpenRefinement(null)}
          onSaved={(newData) => handleRefinementSaved(openRefinement, newData)}
        />
      )}
    </>
  )
}
```

- [ ] **Step 2: Manual verification**

1. Open dashboard → User tab → select a profile → expand Prompts accordion
2. Verify 7 items: Scoring, Resume Generation, **Resume Refinement** (indented), Cover Letter Generation, **Cover Letter Refinement** (indented), Description Processing, Resume Parsing
3. Click "✓ On" / "✗ Off" toggle on the Resume Refinement card — it should flip without opening a modal
4. Click the Resume Refinement card body — the `RefinementPromptModal` should open with two tabs (Evaluator / Rewriter), config row at top, chip tray with Refinement section
5. Change max turns to 2, click Save — reopen the card and verify max turns shows 2

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add refinement prompt cards with enable toggle to PromptsSection"
```

---

## Task 12: Frontend — Eval Score Chip + History in PreviewTab

**Files:**
- Modify: `react-dashboard/src/components/widgets/Settings.jsx`

- [ ] **Step 1: Add eval score chip and history to resume/cover content area**

In `Settings.jsx`, find the section that renders `{(contentTab === 'resume' || contentTab === 'cover') && (`. Inside that block, locate where `artifactView === 'markdown'` and `artifactView === 'pdf'` are rendered. Replace the entire resume/cover content block (starting at `{(contentTab === 'resume' || contentTab === 'cover') && (`) with:

```jsx
      {(contentTab === 'resume' || contentTab === 'cover') && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <SubToggle
              options={[
                { key: 'markdown', label: 'Markdown' },
                { key: 'pdf', label: 'PDF' },
              ]}
              value={artifactView}
              onChange={setArtifactView}
            />
            <div className="flex items-center gap-1">
              <button
                onClick={() => setEditDoc(contentTab)}
                disabled={!(contentTab === 'resume' ? hasResume : hasCover)}
                title={(contentTab === 'resume' ? hasResume : hasCover) ? 'Edit markdown and re-render PDF' : 'Generate before editing'}
                className="px-3 py-1 rounded text-xs font-semibold transition-colors border border-space-border text-space-dim hover:text-space-text disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Edit
              </button>
              <HelpIcon text="Generates a tailored resume and cover letter for this job, rendered to PDF. Uses more credits than scoring." />
              <GatedButton
                action="generate"
                onClick={handleAction}
                disabled={actionLoading || !promptOk}
                title={promptMissingTitle || undefined}
                className="px-3 py-1 rounded text-xs font-semibold transition-colors bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading ? '…' : !promptOk ? 'Prompt not set' : (contentTab === 'resume' ? hasResume : hasCover) ? 'Regenerate' : 'Generate'}
              </GatedButton>
            </div>
          </div>
          {actionError && <p className="text-xs text-red-400 break-words">{actionError}</p>}

          {/* Eval score chip */}
          {(() => {
            const evalScore = contentTab === 'resume' ? job.resume_eval_score : job.cover_eval_score
            const evalTurns = contentTab === 'resume' ? job.resume_eval_turns : job.cover_eval_turns
            if (evalScore == null) return null
            const hue = Math.round(evalScore * 120)
            return (
              <div className="flex items-center gap-2">
                <span
                  style={{ color: `hsl(${hue}, 75%, 55%)` }}
                  className="text-sm font-bold tabular-nums"
                >
                  {(evalScore * 10).toFixed(1)}/10
                </span>
                <span className="text-xs text-space-dim">
                  ({evalTurns} turn{evalTurns !== 1 ? 's' : ''})
                </span>
              </div>
            )
          })()}

          {artifactView === 'markdown' && (
            <MarkdownView
              url={contentTab === 'resume'
                ? `/api/jobs/${job.job_key}/resume/markdown?v=${artifactNonce.resume}`
                : `/api/jobs/${job.job_key}/cover/markdown?v=${artifactNonce.cover}`}
            />
          )}
          {artifactView === 'pdf' && (
            <iframe
              src={contentTab === 'resume'
                ? `/api/jobs/${job.job_key}/resume?v=${artifactNonce.resume}`
                : `/api/jobs/${job.job_key}/cover?v=${artifactNonce.cover}`}
              className="w-full h-[600px] rounded border border-space-border"
              title={contentTab === 'resume' ? 'Resume PDF' : 'Cover Letter PDF'}
            />
          )}

          {/* Refinement history */}
          {(() => {
            const evalLog = contentTab === 'resume' ? (job.resume_eval_log || []) : (job.cover_eval_log || [])
            if (!evalLog.length) return null
            return (
              <div className="flex flex-col gap-3 mt-1">
                <hr className="border-space-border" />
                <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">Refinement History</p>
                {evalLog.map((entry, idx) => {
                  const hue = Math.round(entry.score * 120)
                  return (
                    <div key={idx} className="flex flex-col gap-1.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-semibold text-space-dim">Turn {entry.turn}</span>
                        <span style={{ color: `hsl(${hue}, 75%, 55%)` }} className="text-xs font-bold tabular-nums">
                          {(entry.score * 10).toFixed(1)}/10
                        </span>
                        {entry.passed
                          ? <span className="text-xs text-emerald-400">✓ passed</span>
                          : idx === evalLog.length - 1
                            ? <span className="text-xs text-space-dim/50">limit reached</span>
                            : null
                        }
                      </div>
                      {entry.issues && entry.issues.length > 0 && (
                        <ul className="text-xs text-space-text space-y-0.5">
                          {entry.issues.map((issue, i) => (
                            <li key={i} className="flex gap-1.5">
                              <span className="text-space-dim/70 shrink-0">[{issue.category}]</span>
                              <span>{issue.description}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                      {idx < evalLog.length - 1 && <hr className="border-space-border" />}
                    </div>
                  )
                })}
              </div>
            )
          })()}
        </div>
      )}
```

- [ ] **Step 2: Manual verification — with existing job data**

1. In the dashboard, select a job that already has a resume generated
2. Go to the Resume tab
3. If `resume_eval_log` is empty: the eval score chip and history section should not appear — looks identical to before
4. Click Generate — watch the terminal for `[refinement:resume]` log lines
5. After the refinement loop completes, the SSE update should cause the eval score chip to appear above the PDF/Markdown view
6. The history section should show one or more turns with scores and issues

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Add eval score chip and refinement history to resume/cover preview"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| Evaluate → score + structured issues | Task 5: `evaluate_resume_md` |
| Rewrite based on issues | Task 6: `refine_resume_md` |
| Loop: eval → refine → repeat | Task 8: `_run_doc_refinement` |
| Max turns + pass score configurable | Task 2: profile fields; Task 10: UI |
| Auto-trigger after generation | Task 9 |
| Background thread, SSE updates | Task 8 |
| Resume eval log stored in DB | Tasks 1, 7 |
| Refinement cards with enable toggle | Task 11 |
| Enable toggle saves immediately | Task 11: `handleToggleRefinement` |
| RefinementPromptModal: Evaluator + Rewriter tabs | Task 10 |
| RefinementPromptModal: max_turns, pass_score config | Task 10: config row |
| RefinementPromptModal: chip tray with virtual tokens | Task 10: `REFINEMENT_EVAL_CHIPS`, `REFINEMENT_REFINE_CHIPS` |
| Same fork-on-default-edit logic | Task 10: `_resolveFile` |
| Eval score chip above document | Task 12 |
| Per-turn history with issues below document | Task 12 |
| `---` divider between turns | Task 12: `<hr>` between entries |
| ✓ passed / limit reached label on final turn | Task 12: `entry.passed` |
| Cover letter: parallel to resume | Tasks 5–12 (all use `doc_type` parameter) |
| Default prompt files | Task 3 |
| Prompts router exposes new type keys | Task 4 |

**Placeholder scan:** No TBD, TODO, or placeholder text found.

**Type consistency check:**
- `evaluate_resume_md(eval_prompt, user, client, model)` — used identically in Task 5 test and Task 8 loop ✓
- `refine_resume_md(user, refine_prompt, client, model, db, issues, template_path)` — used identically in Task 6 test and Task 8 loop ✓
- `resume_eval_log` (snake_case DB column) → `job.resume_eval_log` in serialize → `job.resume_eval_log` in frontend ✓
- `entry.passed` populated in Task 8 loop, consumed in Task 12 history render ✓
- `${docType}_refine_enabled` (profile field) — written in Task 2, read in Tasks 8, 9, 11 ✓
