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
| `account` | `Account` | Login-identity owner, 1:1 → `user_profile` (unique `profile_id`); unique `email`; `is_admin`; `banned` (bool — suspends login and all API access; set by `POST /api/admin/users/{id}/access`); `credit_balance` (cached running total); `credit_rate` (per-account tier multiplier). Not tenant-guarded. | Auth / Credits |
| `identity` | `Identity` | OAuth `(provider, provider_subject)` (unique together) → `account`. Many identities per account (link-by-verified-email). Not tenant-guarded. | Auth |
| `credit_ledger` | `CreditLedger` | Append-only credit history: `profile_id, delta, reason, action, job_key, raw_cost_usd, meta, created_by, created_at`. Source of truth for `account.credit_balance`. Not tenant-guarded (keyed by `profile_id` but not in `_TENANT_TABLES`). | Credits |
| `allowed_email` | `AllowedEmail` | Runtime invite allowlist: `email` (unique, lowercased via validator), `invited_by` (FK → `account.id`), `created_at`, `tier` (default `standard`), `is_admin` (default false). `tier`/`is_admin` carry the intended user type, applied to the `Account` at first-login provisioning (`_provision_account`); env `ADMIN_EMAILS` still OR's into admin. Supplements the `ALLOWED_EMAILS` env var — `is_allowed_email` checks both. Rows upserted by `POST /api/admin/invite` (repeat email updates type + resends). | Auth |

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

### Known issue: SQLite `skill_aliases` PK from `bdf3f4523095`

Migration `bdf3f4523095` moves `skill_aliases` from a single-column PK (`alias_key`)
to a composite PK (`profile_id, alias_key`). On SQLite this needs a table rebuild
(`batch_alter_table(..., recreate='always')`). Some older local dev DBs ended up
**stamped at head while still carrying the old `PRIMARY KEY (alias_key)`** — i.e. the
column was added but the PK rebuild never took. Symptom: provisioning a *second*
tenant fails with `UNIQUE constraint failed: skill_aliases.alias_key` (the default
aliases collide across profiles), which surfaces at OAuth login as a spurious
`BetaAccessDenied` ("closed beta") because `resolve_or_provision_account` swallows the
`IntegrityError` and re-raises denial. Fix on the affected DB: rebuild the table with
`PRIMARY KEY (profile_id, alias_key)` (preserve rows). Verify with
`SELECT sql FROM sqlite_master WHERE name='skill_aliases'`. Fresh DBs built via
`create_all` are unaffected (the model has the composite PK), so the parity gate
doesn't catch it.

### Tenant scoping (Phase 2)

Every tenant-owned table (`jobs`, `documents`, `skill_aliases`) carries
`profile_id` (= `user_profile.id`). **Rule:** never `db.query(Job/Document/SkillAlias)`
directly — read through `web.tenancy.scoped(db, Model, profile_id)`; writes set
`profile_id`. Routers inject `current_profile_id` (dev stub → `Config['dev_tenant_id']`,
default 1) and pass it down into `core/`. A `before_flush` guard (`db/events.py`)
fails any tenant insert missing `profile_id`. Phase 3 (DONE) ported existing SQLite
data into tenant `profile_id=1` and cut startup over to `alembic upgrade head`.

### Auth identity tables (Auth sub-project — DONE & live)

Two non-tenant-guarded tables (not in `_TENANT_TABLES`, so the `before_flush`
guard does not require `profile_id` on them):
- `account` (`Account`) — one per login identity, 1:1 → `user_profile` via a unique
  `profile_id`; `email` unique; `is_admin`.
- `identity` (`Identity`) — an OAuth `(provider, provider_subject)` (unique together)
  → `account`. One account can have multiple identities (Google + GitHub linked by
  verified email).

Added by Alembic migration `5285bd395643` (chained onto `bdf3f4523095`; **current
head**). On first OAuth login `web/auth/identity.resolve_or_provision_account`
provisions a profile (seeded prompts + skill aliases) for a new email; the **first
admin login claims the existing `profile_id=1`**. In production `current_profile_id`
resolves the session account's profile (the dev stub still applies locally / in
tests). Auth logic + flow live in `web/` — see `web/CONTEXT.md` → "Access control".

### Credits tables (Credits & Metering sub-project — DONE)

Added by Alembic migration `85e2c6aab4f8_add_credits.py` (chained onto
`5285bd395643`; **current head**):
- `account.credit_balance` (INTEGER, cached running total) and
  `account.credit_rate` (FLOAT, per-account tier multiplier — `0` = free/
  ungated dev tier).
- `credit_ledger` (`CreditLedger`) — one row per grant/debit; `delta` is
  signed (positive = grant, negative = debit). `reason` is `signup_grant` |
  `admin_grant` | `debit`; `action`/`job_key`/`raw_cost_usd`/`meta` are
  populated for debit rows by `core/metering.meter_action`.

`reconcile_balance(db, profile_id)` (`core/credits.py`) recomputes
`account.credit_balance` from `SUM(credit_ledger.delta)` if drift is
suspected — there's no scheduled job for this yet, it's a manual repair tool.
See `core/CONTEXT.md` → "Credits & Metering" for the conversion formula and
gating logic.
