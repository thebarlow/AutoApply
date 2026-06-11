# db/ Context

## Schema Management

**Startup is Alembic-only (Phase 3).** `init_db()` runs `alembic upgrade head` to
bring the schema current, then runs the idempotent seeders. `create_all` and the
hand-rolled `_migrate_*` functions have been **retired from the production path**.
Add schema changes by autogenerating a new Alembic migration (see below), never by
hand-writing `ALTER TABLE` in `database.py`.

The **test suite still uses `create_all`** (each test builds an in-memory SQLite via
`Base.metadata.create_all` and overrides `get_db`) for speed — it does not run Alembic.
`tests/db/test_alembic_parity.py` gates that the two schemas stay identical.

### Migration history (retired)

The table below records the columns that the now-deleted `_migrate_*` functions used to
add. These are all folded into the Alembic baseline (`3433821457fb`); the functions no
longer exist.

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

## Prompt seeding at startup

`init_db` runs these idempotent seeders after `alembic upgrade head`. Fresh DBs get the
correct prompt content directly from the seeders, so the old one-time `_migrate_resume_*_v2`
content-forcing migrations have been retired (the already-ported dev DB ran them once).

| Seeder | Effect |
|---|---|
| `seed_prompt_defaults` (`db/seed.py`) | Seeds `prompt_defaults` rows from `prompts/defaults/*.md`. |
| `migrate_file_prompts_to_db` (`db/seed.py`) | One-time import of legacy file-based prompts into the `prompts` table. |
| `_seed_ats_parse_prompt` (`db/database.py`) | Seeds the `ats_parse` `PromptDefault` row (used by the ATS semantic layer). |

## Alembic migrations (Phase 1+)

Schema changes are managed exclusively by Alembic (`alembic/`). The legacy hand-written
`_migrate_*` functions in `db/database.py` have been removed (Phase 3).

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

The running app boots via `alembic upgrade head` inside `init_db` (Phase 3). The test
suite still builds schema via `create_all` for in-memory speed; the parity gate keeps
the two in sync.

### Tenant scoping (Phase 2)

Every tenant-owned table (`jobs`, `documents`, `skill_aliases`) carries
`profile_id` (= `user_profile.id`). **Rule:** never `db.query(Job/Document/SkillAlias)`
directly — read through `web.tenancy.scoped(db, Model, profile_id)`; writes set
`profile_id`. Routers inject `current_profile_id` (dev stub → `Config['dev_tenant_id']`,
default 1) and pass it down into `core/`. A `before_flush` guard (`db/events.py`)
fails any tenant insert missing `profile_id`. Phase 3 ports existing SQLite data into
tenant `profile_id=1` and cuts startup over to `alembic upgrade head`.
