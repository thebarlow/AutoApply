# Generator Design Spec

**Stage 4 of the auto-apply pipeline.** A Python module that takes `approved` jobs from SQLite, generates a tailored resume and cover letter using the Anthropic SDK, renders PDFs via Pandoc+XeLaTeX, writes artifact paths back to the job record, and transitions state `approved` → `generated`.

---

## Goal

When a user approves a job in the Review Queue, generation starts automatically in the background. The user sees the card fade out immediately and can continue reviewing. Artifacts land in `jobs/outputs/` and the job record is updated when generation completes. Failures transition the job to `failed` state for later retry via the Dashboard.

---

## Architecture

`generator/generator.py` owns the full pipeline. The web layer spawns a background thread on approve; the thread calls `generate_job(job_key)` which opens its own DB session, runs generation, and closes the session when done.

```
web/routers/jobs.py
  └── on approve → threading.Thread(target=generate_job, args=(job_key,))

generator/generator.py
  ├── generate_job(job_key)                               ← thread entry point
  ├── build_resume_prompt(job, profile, template) → str
  ├── build_cover_prompt(job, profile, template)  → str
  ├── call_claude(prompt, client) → str                  ← Anthropic SDK
  ├── render_pdf(md_path, pdf_path)                      ← Pandoc subprocess
  └── render_resume_pdf(md_path, pdf_path, job_key)      ← 1-page fit logic
```

The background thread opens its own `SessionLocal()` session — it cannot share the PATCH request's session, which is already closed by the time generation runs.

---

## Triggering

The PATCH handler in `web/routers/jobs.py` already transitions job state to `approved` and returns the updated job. After the DB commit, if the new state is `approved`, it spawns a daemon thread targeting `generate_job`. The handler returns immediately — generation is fully decoupled from the HTTP response.

---

## Generation Pipeline

`generate_job(job_key)` executes these steps in order:

1. Open a fresh DB session
2. Load the job by `job_key` (exit silently if not found)
3. Load `UserProfile` from DB
4. Load resume and cover letter prompt templates from the `config` table
5. Build resume prompt from job fields + profile + template
6. Call Anthropic SDK → resume markdown
7. Strip any header block Claude added despite instructions
8. Write `jobs/outputs/{job_key}_resume.md`
9. Render resume PDF with 1-page fit logic → `jobs/outputs/{job_key}_resume.pdf`
10. Build cover letter prompt from job fields + profile + template
11. Call Anthropic SDK → cover letter markdown
12. Write `jobs/outputs/{job_key}_cover.md`
13. Render cover letter PDF → `jobs/outputs/{job_key}_cover.pdf`
14. Write `resume_path`, `cover_path` back to job record
15. Transition state `approved` → `generated`, commit
16. Close DB session

---

## Prompts

Prompt templates are stored in the `config` table under two keys:

| Config key | Description |
|---|---|
| `resume_prompt_template` | Full resume generation instructions with `{profile}` and `{job}` placeholders |
| `cover_prompt_template` | Full cover letter generation instructions with `{profile}` and `{job}` placeholders |

Templates are seeded into the DB by `db/seed.py` on first run. They can be edited directly in the DB without touching code — no file dependencies.

At generation time, `generate_job` loads the templates from the DB, then `build_resume_prompt` and `build_cover_prompt` format the `{profile}` and `{job}` placeholders with structured text rendered from the `UserProfile` and `Job` objects.

**`{profile}` renders:**
- Name, skills, target roles, target salary range
- Work history entries (title, company, dates, summary)
- Education entries (institution, degree, field, graduated, GPA)

**`{job}` renders:**
- Title, company, location, salary, description

The generator fails with a clear error if either template key is missing from the config table.

---

## Error Handling

Any exception raised during steps 4–15 is caught. On failure:
- Job state transitions to `failed`
- Exception is logged to stderr
- DB session is closed

`failed` is a retryable state. The Dashboard (future) will surface failed jobs and allow retry. The generator does not implement retry logic itself.

---

## Artifacts

| File | Description |
|---|---|
| `jobs/outputs/{job_key}_resume.md` | Tailored resume markdown |
| `jobs/outputs/{job_key}_resume.pdf` | Rendered resume PDF (1-page) |
| `jobs/outputs/{job_key}_cover.md` | Cover letter markdown |
| `jobs/outputs/{job_key}_cover.pdf` | Rendered cover letter PDF |

`jobs/outputs/` already exists. The generator does not manage the `jobs/pending/` or `jobs/processed/` directories — those belong to the legacy skill pipeline.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `generator/__init__.py` | Create | Package marker |
| `generator/generator.py` | Create | Full generation pipeline |
| `web/routers/jobs.py` | Modify | Spawn background thread on approve |
| `db/seed.py` | Modify | Seed `resume_prompt_template` and `cover_prompt_template` config keys |
| `tests/generator/__init__.py` | Create | Package marker |
| `tests/generator/test_generator.py` | Create | Prompt + DB state transition tests |

---

## Testing

`tests/generator/test_generator.py` uses in-memory SQLite + StaticPool (same pattern as `tests/web/`). `call_claude` and PDF rendering functions are mocked — they require external dependencies (Anthropic API, Pandoc, XeLaTeX) not suitable for unit tests.

**Prompt tests:**
- `test_build_resume_prompt_contains_job_fields` — assert title, company, description appear in output
- `test_build_resume_prompt_contains_profile_fields` — assert skills, work history, education appear
- `test_build_cover_prompt_contains_job_and_profile` — same for cover letter prompt
- `test_generate_job_fails_if_template_missing` — assert state transitions to `failed` when config key absent

**State transition tests:**
- `test_generate_job_transitions_to_generated` — mock `call_claude` + rendering, assert state becomes `generated`, resume_path and cover_path are set
- `test_generate_job_transitions_to_failed_on_claude_error` — mock `call_claude` to raise, assert state becomes `failed`
- `test_generate_job_transitions_to_failed_on_render_error` — mock rendering to raise, assert state becomes `failed`
