# Scorer Design Spec

**Stage 1 of the auto-apply pipeline.** Reads scraped jobs from the DB, scores each against the user's profile using Claude, and transitions state based on configurable thresholds.

---

## Goal

Score every `SCRAPED` job on two dimensions (desirability, fit), compute a weighted final score, and auto-transition to `APPROVED`, `REJECTED`, or `PENDING_REVIEW`.

---

## Architecture

Single-file implementation. No async.

```
scorer/
├── __init__.py
└── scorer.py

scripts/
└── seed_profile.py    # one-time: load profile JSON into user_profile table

tests/scorer/
├── __init__.py
└── test_scorer.py
```

`scorer.py` is run as a module:
```bash
python -m scorer.scorer              # score all SCRAPED jobs
python -m scorer.scorer --job-key KEY  # score one job
```

---

## UserProfile Schema

`core/types.py` defines `UserProfile` with typed sub-schemas for `work_history` and `education`.

**WorkHistoryEntry:**
| Field | Type | Description |
|---|---|---|
| `company` | str | Employer name |
| `title` | str | Job title |
| `start` | str | Start date (YYYY-MM) |
| `end` | str | End date (YYYY-MM), or "present" |
| `summary` | str | Free-text description of role |

**EducationEntry:**
| Field | Type | Description |
|---|---|---|
| `institution` | str | School name |
| `degree` | str | Degree type (B.S., M.S., etc.) |
| `field` | str | Field of study |
| `graduated` | str | Graduation year |
| `gpa` | float | GPA |

`UserProfile` stores these as `list[WorkHistoryEntry]` and `list[EducationEntry]` (dataclasses), not raw dicts. `seed_profile.py` deserializes input JSON into this schema before persisting.

---

## Data Flow

```
scripts/seed_profile.py --input profile.json
        │  upserts JSON into user_profile table
        ▼
python -m scorer.scorer [--job-key KEY]
        │
        ├── load UserProfile from user_profile table
        ├── load w1, w2, auto_reject_threshold, auto_approve_threshold from config table
        ├── query Job(s) with state = SCRAPED
        │
        └── for each job:
              │  build prompt (job fields + UserProfile)
              ▼
            Claude API
              │  returns desirability_score (0–1), fit_score (0–1),
              │  desirability_justification (str), fit_justification (str)
              ▼
            final = w1 * desirability_score + w2 * fit_score
            clamp scores to [0.0, 1.0]
            write to Job:
              - desirability_score, fit_score, final_score
              - score_justification = JSON {"desirability": "...", "fit": "..."}
              - state transition (see below)
            print: [STATE] job_key (final=0.72)
```

---

## Scoring Dimensions

**Desirability score (0–1):** how much the user wants the job
- Salary vs. target
- Remote/location fit
- Full-time vs. contract
- Keyword match (title, company, description)

**Fit score (0–1):** how well the user matches the job requirements
- Required skills vs. user skills
- Years of experience
- Education requirements
- Seniority level

**Final score:** `final = w1 * desirability + w2 * fit`

Weights and thresholds come from the `config` table (seeded by foundation defaults: `w1=0.5`, `w2=0.5`, `auto_reject_threshold=0.3`, `auto_approve_threshold=0.8`).

---

## State Transitions

| Condition | New State |
|---|---|
| `final < auto_reject_threshold` | `REJECTED` |
| `final > auto_approve_threshold` | `APPROVED` |
| otherwise | `PENDING_REVIEW` |

---

## Score Justification Storage

`score_justification` (existing `Text` column on `Job`) stores a JSON object:
```json
{
  "desirability": "Salary matches target range. Remote. Title aligns well.",
  "fit": "Python and SQL match. No ML experience required. BS degree sufficient."
}
```

No schema change to `Job` model required.

---

## Error Handling

| Failure | Behavior |
|---|---|
| No `user_profile` row in DB | Exit immediately with message: `"No user profile found. Run scripts/seed_profile.py first."` |
| Claude returns unparseable response | Log warning with job key and raw response. Leave job as `SCRAPED`. Continue batch. |
| Score outside \[0, 1\] range | Clamp to `[0.0, 1.0]` and log warning. |

Jobs left as `SCRAPED` after a failure are retried on the next run automatically.

---

## Testing

**Unit tests** (no DB, no API):
- `test_compute_final_score` — pure function, parameterized weight/score combos
- `test_determine_state` — all three state transitions + boundary values

**Integration tests** (in-memory DB, mocked Claude):
- `test_score_job_approved` — fixture job + profile, mock Claude response → assert `APPROVED`, correct scores, correct justification JSON
- `test_score_job_rejected` — same, low scores → `REJECTED`
- `test_score_job_pending_review` — mid scores → `PENDING_REVIEW`
- `test_score_batch` — two `SCRAPED` jobs, one non-SCRAPED → only two scored
- `test_malformed_claude_response` — mock returns garbage → job stays `SCRAPED`, no exception raised
- `test_single_job_key_flag` — `--job-key` targets only that job

**seed_profile.py tests:**
- `test_seed_profile_inserts` — inserts profile, asserts DB row
- `test_seed_profile_upserts` — second run updates, no duplicate

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/types.py` | Modify | Add `WorkHistoryEntry`, `EducationEntry` dataclasses; update `UserProfile` to use them |
| `scorer/__init__.py` | Create | Package marker |
| `scorer/scorer.py` | Create | Full scoring pipeline |
| `scripts/seed_profile.py` | Create | Load profile JSON into DB |
| `tests/scorer/__init__.py` | Create | Package marker |
| `tests/scorer/test_scorer.py` | Create | All scorer tests |
