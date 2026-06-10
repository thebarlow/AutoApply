# db/ Context

## Schema Management

SQLAlchemy's `create_all` only creates tables that don't already exist — it does **not** add new columns to existing tables. When a new column is added to a model, the live `auto_apply.db` must be migrated manually:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('auto_apply.db')
conn.execute('ALTER TABLE jobs ADD COLUMN <column_name> <TYPE>')
conn.commit()
conn.close()
"
```

### Migration history

Each migration function in `database.py` is idempotent (checks `PRAGMA table_info` before altering).

| Column(s) | Table | Type | Migration fn |
|-----------|-------|------|--------------|
| `extraction_json` (renamed from `extraction_md`) | `jobs` | TEXT | — (manual, 2026-05-08) |
| `ext_salary_min`, `ext_salary_max` | `jobs` | REAL | — (manual, 2026-05-26) |
| `name` | `user_profile` | TEXT | `_migrate_profile_name` |
| `named_providers`, `latex_templates` | `config` (key-value rows) | — | `_migrate_legacy_config` |
| `ext_seniority`, `ext_role_type`, `ext_domain`, `ext_work_arrangement`, `ext_employment_type`, `ext_required_skills`, `ext_preferred_skills`, `ext_tech_stack`, `ext_key_responsibilities`, `ext_company_signals` | `jobs` | TEXT | `_migrate_ext_columns` |
| `unread_indicator`, `last_result_error` | `jobs` | TEXT | `_migrate_unread_indicator_columns` |
| `pending_review_actions` | `jobs` | TEXT (JSON list) | `_migrate_pending_review_actions` |
| `resume_generated_at`, `cover_generated_at` | `jobs` | TEXT | `_migrate_generated_at_columns` |
| `flagged` | `jobs` | BOOLEAN (default 0) | `_migrate_flagged_column` |
| `resume_eval_score`, `resume_eval_turns`, `resume_eval_log`, `cover_eval_score`, `cover_eval_turns`, `cover_eval_log` | `jobs` | REAL/INTEGER/TEXT | `_migrate_resume_eval_columns` |
| `resume_docx_path` | `jobs` | TEXT | `_migrate_resume_docx_column` |

## Tables beyond `jobs` / `config`

| Table | Model | Purpose | Phase |
|---|---|---|---|
| `prompt_defaults` | `PromptDefault` | Factory prompt defaults, one row per `type_key`. Seeded from `prompts/defaults/*.md`. | 2 |
| `prompts` | `Prompt` | Per-profile active prompt slots `(profile_id, type_key)` + per-type `model` override. | 2 |
| `documents` | `Document` | Structured generated artifact per `(job_key, doc_type)`; `structured_json` is the **source of truth**. Unique on `(job_key, doc_type)`. Helpers: `Document.fetch(db, job_key, doc_type)`, `Document.upsert(db, job_key, doc_type, structured_json)` (upsert commits). | 3a |
| `skill_aliases` | `SkillAlias` | Global skill synonym map: `alias_key` (PK, lowercased token) → `canonical` (display = group identity). A group = all rows sharing one canonical; each canonical has a self-row. Seeded from `core/skill_analytics._ALIASES` via `seed_skill_aliases`. | — |

## Prompt-content reseed migrations

These overwrite prompt **content** (not schema) once, gated by a `config` flag, because the new prompt contract is incompatible with the old text:

| Migration fn | Gate (`config` key) | Effect |
|---|---|---|
| `migrate_file_prompts_to_db` (`db/seed.py`) | — | One-time import of legacy file-based prompts into the `prompts` table. |
| `_migrate_resume_prompt_v2` | `resume_prompt_v2` | Force-reseeds the résumé **generation** prompt to the `ResumeGeneration` JSON contract (Phase 3a). |
| `_migrate_resume_refine_prompt_v2` | `resume_refine_prompt_v2` | Force-reseeds the résumé **refine** prompt to the keyed-patch contract (Phase 3b). |
| `_seed_ats_parse_prompt` | — | Seeds the `ats_parse` `PromptDefault` row on first `init_db` run (used by the ATS semantic layer). |

All are called from `init_db` and are idempotent (return early once the gate flag is set).

## Alembic migrations (Phase 1+)

Schema changes are managed by Alembic (`alembic/`), not the legacy hand-written
`_migrate_*` functions in `db/database.py` (those remain only to upgrade old SQLite
files and are slated for removal in a later phase).

- Migrations live in `alembic/versions/`. `alembic/env.py` targets `Base.metadata`
  and reads `DATABASE_URL`.
- Local Postgres: `docker compose up -d`, then set
  `DATABASE_URL=postgresql+psycopg://auto_apply:auto_apply@localhost:5432/auto_apply`.
- Apply migrations: `python -m alembic upgrade head`.
- Create a migration after model changes:
  `python -m alembic revision --autogenerate -m "<message>"` (review the generated
  script before committing).
- **Parity gate:** `tests/db/test_alembic_parity.py` asserts the Alembic-built schema
  matches `Base.metadata.create_all`. It must stay green — if it fails after a model
  change, regenerate/adjust the migration.

The running app and the test suite still build schema via `create_all`/`init_db` in
Phase 1; cutover to `alembic upgrade head` at startup happens with the Postgres data
port in a later phase.
