# Resume & Cover Letter Refinement Loop — Design Spec

**Date:** 2026-05-29  
**Status:** Approved for implementation

---

## Overview

After generating a resume or cover letter, an agentic refinement loop automatically runs in the background. It evaluates the document quality, scores it, and rewrites it based on concrete issues — repeating until the score meets a configurable threshold or a turn limit is reached. The final document is what the user sees; per-turn scores and feedback are stored and displayed in the job preview.

---

## Architecture

```
POST /api/jobs/{job_key}/generate/resume   (existing, unchanged trigger)
    └─ _do_generate_resume()               (existing)
    └─ if refine_enabled and max_turns > 0:
         threading.Thread → run_resume_refinement(job_key)

run_resume_refinement(job_key):            (new, background thread)
    for turn in 1..max_turns:
        A. evaluate_resume_md()  → {score, issues[]}
           persist eval log, SSE emit
           if score >= pass_score: break
        B. refine_resume_md()    → overwrites MD + regenerates PDF
           SSE emit
```

Same pattern repeated for cover letter (`run_cover_refinement`).

Two LLM calls per turn (evaluate → refine). The evaluator is isolated from the generation context — it only sees the output and the job requirements — so scores are honest.

---

## Data Model

### User Profile JSON blob (new fields)

Added to `core/user.py` `_hydrate()` and `_to_dict()`. Same 7 fields for both `resume` and `cover`:

| Field | Type | Default |
|---|---|---|
| `resume_refine_enabled` | bool | `True` |
| `prompt_resume_eval` | str (file path) | `""` (falls back to `prompts/defaults/resume_eval.md`) |
| `prompt_resume_eval_model` | str | `""` (falls back to profile default) |
| `prompt_resume_refine` | str (file path) | `""` (falls back to `prompts/defaults/resume_refine.md`) |
| `prompt_resume_refine_model` | str | `""` |
| `resume_refine_max_turns` | int | `1` |
| `resume_refine_pass_score` | float | `0.80` |

Repeat for `cover_refine_enabled`, `prompt_cover_eval`, `prompt_cover_eval_model`, `prompt_cover_refine`, `prompt_cover_refine_model`, `cover_refine_max_turns`, `cover_refine_pass_score`.

### Job DB columns (new, migration in `db/database.py`)

| Column | Type | Description |
|---|---|---|
| `resume_eval_score` | Float | Final eval score (0.0–1.0) after loop |
| `resume_eval_turns` | Integer | Number of evaluation turns run |
| `resume_eval_log` | Text | JSON array of per-turn results |
| `cover_eval_score` | Float | |
| `cover_eval_turns` | Integer | |
| `cover_eval_log` | Text | |

`resume_eval_log` schema:
```json
[
  {
    "turn": 1,
    "score": 0.65,
    "issues": [
      {"category": "keyword_coverage", "description": "Missing Kubernetes"},
      {"category": "tailoring", "description": "Profile doesn't mention Platform Engineer"}
    ]
  },
  {
    "turn": 2,
    "score": 0.85,
    "issues": []
  }
]
```

All six columns added via `_migrate_resume_eval_columns()`, called from `init_db()`.

---

## Backend

### New files

#### `prompts/defaults/resume_eval.md`

Evaluator prompt. Receives the current resume markdown (virtual `{current_resume}` placeholder), job extracted description, and user skills list. Returns only JSON: `{"score": float, "issues": [{category, description}]}`.

Issue categories:
- `keyword_coverage` — required/preferred job skills absent from the resume
- `hallucination` — skills or credentials claimed that are not in the user's actual skills list
- `structure` — formatting violations (bullet over 120 chars, missing section, etc.)
- `tailoring` — generic content that doesn't reflect the specific job

#### `prompts/defaults/cover_eval.md`

Same structure as `resume_eval.md`. Issue categories adjusted for cover letters:
- `personalization` — generic opener not tailored to company/role
- `hallucination` — same as above
- `tone` — mismatch between letter tone and company signals
- `call_to_action` — missing or weak closing

#### `prompts/defaults/resume_refine.md`

Rewriter prompt. Receives full applicant details + job posting (same as `resume.md`) plus the current resume as `{current_resume}` and the issue list as `{critique}`. Outputs improved resume markdown body only. Same formatting rules as `resume.md`.

#### `prompts/defaults/cover_refine.md`

Same pattern for cover letters.

### Modified files

#### `core/user.py`

- `_PROMPT_LABELS` extended with `resume_eval`, `resume_refine`, `cover_eval`, `cover_refine` entries (for `resolve_prompt()` label lookup)
- `_hydrate()` reads the 14 new refinement fields with correct defaults
- `_to_dict()` serializes them back

`resolve_prompt()` already works via `getattr(self, f"prompt_{type_key}", "")` — no changes needed to its logic. Fallback to `prompts/defaults/{type_key}.md` applies.

#### `core/job.py`

Four new methods:

**`evaluate_resume_md(eval_prompt, user, client, model) -> dict`**
- Reads `generator/outputs/{job_key}_resume.md`, strips YAML frontmatter via `strip_header_block` from `core/utils`
- Builds prompt: substitutes `{current_resume}` + `{user.skills}` + `{job.extracted_description}` via `_apply_template` + virtual placeholder handling
- LLM call → strip fences → `json.loads` → validate `score` and `issues` keys
- Returns `{"score": float, "issues": list}`

**`refine_resume_md(user, refine_prompt, client, model, db, issues)`**
- Reads current resume MD (frontmatter-stripped)
- Substitutes `{current_resume}` and `{critique}` (JSON-serialized issues list) as virtual placeholders, then runs `_apply_template` for `{user.*}` / `{job.*}`
- LLM call → strip header block → prepend existing frontmatter → overwrite `{job_key}_resume.md`
- Calls `generate_resume_pdf()` to re-render PDF (this internally commits `resume_path` and `resume_generated_at`)
- Does not commit eval fields; caller commits those after the method returns

**`evaluate_cover_md`** and **`refine_cover_md`** — identical pattern on `_cover.md`.

`serialize()` updated to include `resume_eval_score`, `resume_eval_turns`, `resume_eval_log` (parsed JSON), and cover equivalents.

#### `db/database.py`

New migration function `_migrate_resume_eval_columns()`:
```python
columns = [
    ("resume_eval_score", "REAL"),
    ("resume_eval_turns", "INTEGER"),
    ("resume_eval_log", "TEXT"),
    ("cover_eval_score", "REAL"),
    ("cover_eval_turns", "INTEGER"),
    ("cover_eval_log", "TEXT"),
]
```
Called from `init_db()`.

#### `web/intake_pipeline.py`

New function `run_resume_refinement(job_key: str) -> None`:

1. Open fresh `SessionLocal()`
2. Load `job` and `user`
3. Read refinement config from user profile
4. If `not resume_refine_enabled` or `max_turns == 0`: return
5. Resolve eval prompt via `user.resolve_prompt("resume_eval")`
6. Resolve refine prompt via `user.resolve_prompt("resume_refine")`
7. Build LLM clients for eval and refine models
8. `eval_log = []`, `turns_run = 0`
9. Loop `turn` in `range(1, max_turns + 1)`:
   - `llm_status.start(job_key, "resume_eval")`
   - `result = job.evaluate_resume_md(...)`
   - Append `{turn, score, issues}` to `eval_log`
   - `turns_run = turn`
   - Persist `resume_eval_score`, `resume_eval_turns`, `resume_eval_log` → `db.commit()`
   - `_emit(job)` (SSE)
   - `llm_status.finish(job_key, "resume_eval")`
   - If `result["score"] >= pass_score`: break
   - If `turn < max_turns`:
     - `llm_status.start(job_key, "resume_refine")`
     - `job.refine_resume_md(..., issues=result["issues"])`
     - `db.commit()`
     - `_emit(job)`
     - `llm_status.finish(job_key, "resume_refine")`
10. On any exception per step: log error, persist `last_result_error`, `unread_indicator = "error"`, emit, break loop
11. `db.close()`

`run_cover_refinement(job_key)` — identical, operates on cover fields and methods.

#### `web/routers/jobs.py`

At the end of successful `generate_resume_endpoint()`, after the SSE emit:
```python
user = User.load(db)
if getattr(user, 'resume_refine_enabled', True) and getattr(user, 'resume_refine_max_turns', 1) > 0:
    from web.intake_pipeline import run_resume_refinement
    threading.Thread(target=run_resume_refinement, args=(job.job_key,), daemon=True).start()
```

Same pattern at end of `generate_cover_endpoint()` using `run_cover_refinement`.

---

## Frontend

### `ProfileDetail.jsx` — PromptsSection

**Card ordering** (7 total):
1. Scoring
2. Resume Generation ← unchanged
3. **Resume Refinement** ← new
4. Cover Letter Generation ← unchanged
5. **Cover Letter Refinement** ← new
6. Description Processing
7. Resume Parsing

**Refinement card layout:**
```
┌─────────────────────────────────────────────────────┐
│ Resume Refinement                                    │
│ Eval:    resume_eval_custom.md  ·  gpt-4o-mini       │  ← left/body (opens modal)
│ Rewrite: resume_refine.md       ·  (default)         │
│                                           [toggle ✓] │  ← right, separate click zone
└─────────────────────────────────────────────────────┘
```

Toggle click: `e.stopPropagation()` → flip `resume_refine_enabled` → `updateProfile(profileId, {...profileData, resume_refine_enabled: !current})` → local state update. No modal opened.

Card body click: opens `RefinementPromptModal`.

**`RefinementPromptModal` component** (new, in `ProfileDetail.jsx`):

Props: `docType` (`"resume"` | `"cover"`), `profileId`, `profileName`, `profileData`, `defaultModel`, `onClose`, `onSaved`

Structure:
```
Header: "Resume Refinement" / "Cover Letter Refinement"  ×

Config row:
  Max Turns: [1] (number input, 1–10)
  Pass Score: [0.80] (number input, 0.0–1.0, step 0.05)

Tab bar: [Evaluator] [Rewriter]

Tab content (full PromptModal body):
  - File selector + Upload button
  - Model input
  - Chip tray (User + Job sections, plus Refinement section)
    - Evaluator tab Refinement chips: {current_resume}
    - Rewriter tab Refinement chips: {current_resume}, {critique}
  - Prompt editor (with pop-out)

Footer: [Save As] [Save] [Cancel]
```

Save call: one `updateProfile` with all changed fields:
```js
{
  prompt_resume_eval: evalFile,
  prompt_resume_eval_model: evalModel,
  prompt_resume_refine: refineFile,
  prompt_resume_refine_model: refineModel,
  resume_refine_max_turns: maxTurns,
  resume_refine_pass_score: passScore,
}
```

Same fork-on-default-edit logic as existing `PromptModal` (never mutate `defaults/` files).

### `Settings.jsx` — PreviewTab resume/cover content area

When `contentTab === 'resume'` and `job.resume_eval_log?.length > 0`:

**Above the document** — eval score chip:
```jsx
<div className="flex items-center gap-2">
  <span style={{ color: hsl(score * 120, 75%, 55%) }} className="text-sm font-bold">
    {(score * 10).toFixed(1)}/10
  </span>
  <span className="text-xs text-space-dim">({turns} turn{turns !== 1 ? 's' : ''})</span>
</div>
```

**Below the document** — refinement history:
```
<hr />
Turn 1 — 6.5/10
• [keyword_coverage] Missing Kubernetes
• [tailoring] Profile doesn't mention Platform Engineer

<hr />
Turn 2 — 8.5/10  ✓ passed
• [structure] Bullet slightly over 120 chars
```

Each turn entry:
- Header line: `Turn N — X.X/10` + ✓ if `score >= pass_score`, else if last turn and not passed: `(limit reached)`
- Issues as a bulleted list: `[category] description`
- `<hr className="border-space-border" />` between turns

Same structure for cover letter tab using `cover_eval_log`.

Score chip and history are only rendered when `eval_log` is non-empty. No UI changes when refinement is disabled or hasn't run.

---

## File Changelist

| File | Change |
|---|---|
| `prompts/defaults/resume_eval.md` | New |
| `prompts/defaults/cover_eval.md` | New |
| `prompts/defaults/resume_refine.md` | New |
| `prompts/defaults/cover_refine.md` | New |
| `core/user.py` | Add 14 refinement fields to hydration/serialization; extend `_PROMPT_LABELS` |
| `core/job.py` | Add 4 new methods + 6 new DB columns + update `serialize()` |
| `db/database.py` | Add `_migrate_resume_eval_columns()`, call from `init_db()` |
| `web/intake_pipeline.py` | Add `run_resume_refinement()` and `run_cover_refinement()` |
| `web/routers/jobs.py` | Auto-trigger refinement after successful generate endpoints |
| `react-dashboard/src/components/widgets/ProfileDetail.jsx` | Add `RefinementPromptModal`; update `PromptsSection` with 2 new cards |
| `react-dashboard/src/components/widgets/Settings.jsx` | Add eval score chip + refinement history to resume/cover result view |

---

## Out of Scope (this spec)

- Evaluator prompt is not exposed as a separate card in the main Prompts accordion — only accessible via the Refinement modal
- No manual "re-run refinement" button in the job preview (auto-runs on generate only)
- Cover letter refinement is a direct parallel to resume — no unique cover-specific UI differences
